"""The follower's analyses, metrics and record on synthetic runs of known gain, bandwidth,
rejection, impedance and slew, as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot, Sweep, SweepKind

from . import runs
from .analysis import analyze_impedance, analyze_slew, analyze_transfer, metrics
from .params import NOMINAL_VIN, SUPPLY_SWEEP, VIN_SWEEP, Stimulus, TbParams
from .types import Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))


def single_pole(tb: TbParams, value: float, pole_hz: float) -> Meas:
    """A run of ``tb`` with the AC stimulus on the input, its response ``value`` falling at one
    pole ``pole_hz``, or on the output test current, its output impedance so; the output 0.3 V
    below the input, the supply passing a hundredth of ``value``, the supply current 40 uA."""
    frequency_hz = np.logspace(3, 11, 161)
    response = value / (1 + 1j * frequency_hz / pole_hz)
    if tb.stimulus is Stimulus.OUTPUT:
        # what the 1 V behind the test resistance leaves on the output: their divider
        response = response / (tb.test_resistance_ohm + response)
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        sweeps={
            "opdc": Sweep(
                kind=SweepKind.OP,
                x=np.zeros(0),
                v={"vin": np.asarray([tb.vin_v]), "vout": np.asarray([tb.vin_v - 0.3])},
                i={"vdd": np.asarray([40e-6])},
            ),
            "ac": Sweep(kind=SweepKind.AC, x=frequency_hz, v={"vout": response}),
            "xf": Sweep(
                kind=SweepKind.XF,
                x=frequency_hz,
                v={"vdd": np.full(len(frequency_hz), 0.01 * value, dtype=np.complex128)},
            ),
        },
    )


def step(rise_v_per_s: float, fall_v_per_s: float, tb: TbParams | None = None) -> Meas:
    """A step run whose output ramps between 0.6 and 0.9 V at the given slopes after each input
    edge (20 ns period: up at 5 ns, down at 15 ns), drawing 40 uA."""
    tb = tb or TbParams(params=runs.source(), stimulus=Stimulus.STEP, vin_v=0.9, step_v=0.3)
    time_s = np.arange(0.0, 20e-9, 5e-12)
    rising = np.clip(0.6 + rise_v_per_s * (time_s - 5e-9), 0.6, 0.9)
    output = np.where(time_s < 15e-9, rising, np.clip(0.9 - fall_v_per_s * (time_s - 15e-9), 0.6, 0.9))
    vin = np.where((time_s >= 5e-9) & (time_s < 15e-9), 1.05, 0.75)
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"vin": vin, "vout": output},
        i={"vdd": np.full(len(time_s), 40e-6)},
    )


def instance_runs(tb: TbParams) -> dict[str, Meas]:
    """Every run of one instance (``runs.testbenches``'s names) about ``tb``'s supply: a gain of
    0.85 at each input level from 2/12 to 10/12 of the supply and 0.1 outside, a 1 GHz pole, a
    1.5 kohm output impedance, the bandwidth in proportion to the supply, a ramped step."""
    dut, supply = tb.params, tb.vdd
    nominal = NOMINAL_VIN[dut.topology, dut.input_xtors]
    made = {}
    for k, fraction in enumerate(VIN_SWEEP):
        level = replace(tb, vin_v=round(fraction * supply, 4))
        made[f"input_vin_{k}"] = single_pole(level, 0.85 if 2 <= k <= 10 else 0.1, 1e9)
        made[f"output_vin_{k}"] = single_pole(replace(level, stimulus=Stimulus.OUTPUT), 1500.0, 2e9)
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            corner = replace(tb, vdd=round(factor * supply, 4), vin_v=round(nominal * factor * supply, 4))
            made[f"supply_{round(factor * 100)}"] = single_pole(corner, 0.85, factor * 1e9)
    made["step"] = step(
        1e9, 1e8, replace(tb, stimulus=Stimulus.STEP, vin_v=round(nominal * supply, 4), step_v=round(supply / 4, 4))
    )
    return made


TB = TbParams(params=runs.source(), vdd=1.2)


def test_transfer_gain_bandwidth_and_impedance() -> None:
    transfer = analyze_transfer([single_pole(replace(TB, vin_v=vin), 0.85, 1e9) for vin in (0.6, 0.9)])
    assert transfer.gain_dc == pytest.approx([0.85, 0.85], rel=1e-6)
    assert transfer.bandwidth_hz == pytest.approx([1e9, 1e9], rel=0.01)
    assert transfer.level_shift_v == pytest.approx([0.3, 0.3])
    assert transfer.vout_v == pytest.approx([0.3, 0.6]) and transfer.idd_a == pytest.approx([40e-6, 40e-6])
    # the supply passes a hundredth of the input's gain: 40 dB of rejection
    assert transfer.psrr_dc_db == pytest.approx([40.0, 40.0], abs=1e-6)
    assert transfer.gain_db.shape == (2, 161) and transfer.gain_db[0, 0] == pytest.approx(20 * np.log10(0.85))
    output = replace(TB, stimulus=Stimulus.OUTPUT, vin_v=0.9)
    impedance = analyze_impedance([single_pole(output, 1500.0, 2e9)])
    assert impedance.zout_dc_ohm[0] == pytest.approx(1500.0, rel=1e-6)
    # one pole at 2 GHz: the impedance's magnitude a factor sqrt(2) down there
    at_pole = int(np.argmin(np.abs(impedance.frequency_hz - 2e9)))
    assert impedance.zout_ohm[0, at_pole] == pytest.approx(1500.0 / np.sqrt(2), rel=0.01)
    with pytest.raises(ValueError, match="on the input"):
        analyze_transfer([single_pole(output, 1500.0, 2e9)])
    with pytest.raises(ValueError, match="output test current"):
        analyze_impedance([single_pole(replace(TB, vin_v=0.9), 0.85, 1e9)])


def test_slew_rates_settling_and_overshoot_of_a_ramped_step() -> None:
    # 1 V/ns up (the device pulls), 0.1 V/ns down (only the bias current)
    slew = analyze_slew([step(1e9, 1e8)])
    assert slew.vout_low_v[0] == pytest.approx(0.6) and slew.vout_high_v[0] == pytest.approx(0.9)
    assert slew.slew_rate_rise_v_per_s[0] == pytest.approx(1e9, rel=1e-3)
    assert slew.slew_rate_fall_v_per_s[0] == pytest.approx(-1e8, rel=1e-3)
    # within 1 % of the 0.3 V step: 0.297 V of ramp after the edge's middle
    assert slew.settling_rise_s[0] == pytest.approx(0.297e-9, rel=0.02)
    assert slew.settling_fall_s[0] == pytest.approx(2.97e-9, rel=0.01)
    assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0
    assert slew.idd_a[0] == pytest.approx(40e-6)
    with pytest.raises(ValueError, match="step run"):
        analyze_slew([single_pole(TB, 0.85, 1e9)])


def test_a_stuck_output_has_no_edges() -> None:
    stuck = step(1e9, 1e8)
    stuck.v["vout"][:] = 0.6
    slew = analyze_slew([stuck])
    assert np.isnan(slew.slew_rate_rise_v_per_s[0]) and np.isnan(slew.overshoot_fall[0])


def test_the_metrics_take_the_nominal_input_and_the_range_about_it() -> None:
    made = instance_runs(TB)
    transfer = analyze_transfer([made[f"input_vin_{k}"] for k in range(len(VIN_SWEEP))])
    impedance = analyze_impedance([made[f"output_vin_{k}"] for k in range(len(VIN_SWEEP))])
    supply = analyze_transfer([made["supply_90"], made["input_vin_9"], made["supply_110"]])
    values = metrics(transfer=transfer, impedance=impedance, slew=analyze_slew([made["step"]]), supply=supply)
    assert isinstance(values, Metrics)
    # an NMOS source follower's nominal input: 9/12 of the supply
    assert values.vout_v == pytest.approx(0.9 - 0.3) and values.level_shift_v == pytest.approx(0.3)
    assert values.gain_dc == pytest.approx(0.85) and values.bandwidth_hz == pytest.approx(1e9, rel=0.01)
    assert values.psrr_dc_db == pytest.approx(40.0) and values.idd_a == pytest.approx(40e-6)
    assert values.zout_dc_ohm == pytest.approx(1500.0)
    # the gain holds from 2/12 to 10/12 of the supply
    assert values.input_range_v == pytest.approx(8 / 12 * 1.2)
    assert values.slew_rate_rise_v_per_s == pytest.approx(1e9, rel=1e-3)
    assert values.slew_rate_fall_v_per_s == pytest.approx(-1e8, rel=1e-3)
    assert values.bandwidth_min_supply_hz == pytest.approx(0.9e9, rel=0.01)


def test_the_record_reads_every_run_and_names_its_wave() -> None:
    """``results`` from every run ``testbenches`` names: the metrics at the nominal input, the
    plots, the model's curve among them (``vout_vin``), the step the viewer shows."""
    result = runs.results(instance_runs(TB))
    assert list(result.metrics) == [
        "vout_v",
        "level_shift_v",
        "gain_dc",
        "bandwidth_hz",
        "psrr_dc_db",
        "idd_a",
        "zout_dc_ohm",
        "input_range_v",
        "slew_rate_rise_v_per_s",
        "slew_rate_fall_v_per_s",
        "settling_rise_s",
        "settling_fall_s",
        "overshoot_rise",
        "overshoot_fall",
        "bandwidth_min_supply_hz",
    ]
    assert result.metrics["gain_dc"] == pytest.approx(0.85)
    assert [plot.name for plot in result.details] == [
        "vout_vin",
        "gain_vin",
        "bandwidth_vin",
        "zout_vin",
        "psrr_vin",
        "gain_frequency",
        "zout_frequency",
        "gain_supply",
        "bandwidth_supply",
        "psrr_supply",
    ]
    assert all(isinstance(plot, Plot) for plot in result.details)
    vout = result.details[0]
    assert vout.x == pytest.approx([f * 1.2 for f in VIN_SWEEP], abs=1e-4) and list(vout.series) == ["output"]
    response = result.details[5]
    assert len(response.x) == 161 and response.x_log and response.series["gain"][0] == pytest.approx(-1.41, abs=0.01)
    assert result.details[7].x == list(SUPPLY_SWEEP)
    assert result.waves == {"step at the nominal input": "step"}


def test_the_record_takes_the_runs_the_testbenches_name() -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")  # the supply is the kit's
    assert set(instance_runs(TB)) == set(runs.testbenches("tsmc65", TB.params))
