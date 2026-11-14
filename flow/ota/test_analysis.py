"""The amplifier's analyses, metrics and record on synthetic runs of known gain, bandwidth, phase
margin, rejection, noise, slew and distortion, as a run's measurement (``flow.pipeline.Meas``)
reads."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot, Sweep, SweepKind

from .analysis import analyze_ac, analyze_distortion, analyze_noise, analyze_slew, metrics
from .params import CM_SWEEP, NOMINAL_CM, SINE_STROBE_S, SUPPLY_SWEEP, Bench, Params, TbParams, Topology
from . import runs as block_runs
from .types import Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))


def two_pole(
    gain: float,
    pole_hz: float,
    second_hz: float,
    *,
    tb: TbParams | None = None,
    vbp: float = 0.5,
    third_hz: float | None = None,
    noise_v_per_rthz: float = 10e-9,
) -> Meas:
    """A small-signal run of ``tb`` as an amplifier of low-frequency gain ``gain`` and poles at
    ``pole_hz`` and ``second_hz`` (and ``third_hz``), its input noise white (10 nV/sqrt(Hz)), its
    load bias at ``vbp``, drawing 50 uA; at outp half its gain, the supply passing a tenth and the
    common mode a hundredth. A differential amplifier's response is split between its outputs."""
    tb = TbParams() if tb is None else tb
    frequency_hz = np.logspace(3, 11, 161)
    response = gain / ((1 + 1j * frequency_hz / pole_hz) * (1 + 1j * frequency_hz / second_hz))
    if third_hz is not None:
        response = response / (1 + 1j * frequency_hz / third_hz)
    outputs = {"outp": response} if tb.single_ended else {"outp": response / 2, "outn": -response / 2}
    one = lambda value: np.asarray([value])
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        sweeps={
            "ac": Sweep(kind=SweepKind.AC, x=frequency_hz, v=outputs),
            "xf": Sweep(
                kind=SweepKind.XF,
                x=frequency_hz,
                v={
                    "inp": response / 2 + 0.005,
                    "inn": -response / 2 + 0.005,
                    "vdd": np.full_like(response, 0.1),
                },
            ),
            "noise": Sweep(kind=SweepKind.NOISE, x=frequency_hz, v={"out": noise_v_per_rthz * np.abs(response)}),
            "opdc": Sweep(
                kind=SweepKind.OP,
                x=np.zeros(0),
                v={"vbp": one(vbp)} | {name: one(tb.vout_cm_v) for name in outputs},
                i={"vdd": one(50e-6)},
            ),
        },
    )


def transient(tb: TbParams, time_s: np.ndarray, outp: np.ndarray, inp: np.ndarray) -> Meas:
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"inp": inp, "outp": outp},
        i={"vdd": np.full(len(time_s), 30e-6)},
    )


def step_run(rise_v_per_s: float, fall_v_per_s: float) -> Meas:
    """A unity-gain step run: an output ramping between 0.45 and 0.75 V at the given slopes after
    each input edge (20 ns period: up at 5 ns, down at 15 ns), drawing 30 uA."""
    tb = TbParams(bench=Bench.STEP, vin_cm_v=0.6, vin_step_v=0.3)
    time_s = np.arange(0.0, 20e-9, 5e-12)
    rising = np.clip(0.45 + rise_v_per_s * (time_s - 5e-9), 0.45, 0.75)
    output = np.where(time_s < 15e-9, rising, np.clip(0.75 - fall_v_per_s * (time_s - 15e-9), 0.45, 0.75))
    return transient(tb, time_s, output, np.where((time_s >= 5e-9) & (time_s < 15e-9), 0.75, 0.45))


def sine_run(second_harmonic: float) -> Meas:
    """A unity-gain sine run: an output of 0.95 times a 0.12 V, 10 MHz sine with a second harmonic
    of the given fraction of the fundamental."""
    tb = TbParams(bench=Bench.SINE, vin_cm_v=0.6, vin_amplitude_v=0.12, waveform_sample_interval_s=SINE_STROBE_S)
    time_s = np.arange(0.0, tb.sine_periods / tb.vin_frequency_hz, 100e-12)
    phase = 2 * np.pi * tb.vin_frequency_hz * time_s
    fundamental = 0.95 * 0.12 * np.sin(phase)
    output = 0.6 + fundamental + second_harmonic * 0.95 * 0.12 * np.sin(2 * phase)
    return transient(tb, time_s, output, 0.6 + 0.12 * np.sin(phase))


def test_gain_bandwidth_and_phase_margin_of_a_two_pole_amplifier() -> None:
    result = analyze_ac([two_pole(100.0, 1e6, 1e9)])
    # unity gain near the gain-bandwidth product; both poles' phase there sets the margin
    assert result.gain_dc_db[0] == pytest.approx(40.0, abs=0.01)
    assert result.unity_gain_bandwidth_hz[0] == pytest.approx(99.5e6, rel=0.01)
    unity = result.unity_gain_bandwidth_hz[0]
    expected = 180 - np.degrees(np.arctan(unity / 1e6) + np.arctan(unity / 1e9))
    assert result.phase_margin_deg[0] == pytest.approx(expected, abs=0.3)
    assert result.bandwidth_hz[0] == pytest.approx(1e6, rel=0.01)
    assert result.gbw_hz[0] == pytest.approx(100e6, rel=0.01)
    assert np.isnan(result.gain_margin_db[0])  # two poles never turn the phase 180 degrees
    # outp: half the gain (34 dB) over a tenth from the supply and a hundredth from the common mode
    assert result.psrr_dc_db[0] == pytest.approx(20 * np.log10(50 / 0.1), abs=0.01)
    assert result.cmrr_dc_db[0] == pytest.approx(20 * np.log10(50 / 0.01), abs=0.01)
    assert result.psrr_db.shape == result.gain_db.shape
    three = analyze_ac([two_pole(1000.0, 1e5, 1e7, third_hz=2e7)])
    assert (
        three.gain_margin_db[0] < 0
    )  # three close poles: the loop gain exceeds unity where the phase turns 180 degrees
    assert result.power_w[0] == pytest.approx(1.2 * 50e-6)
    assert result.vout_cm_v[0] == pytest.approx(0.6)
    below_unity = analyze_ac([two_pole(0.5, 1e6, 1e9)])
    assert np.isnan(below_unity.unity_gain_bandwidth_hz[0]) and np.isnan(below_unity.phase_margin_deg[0])
    # a load bias the feedback drove below ground: no figure, nor any noise, at that point
    measurements = [two_pole(100.0, 1e6, 1e9), two_pole(100.0, 1e6, 1e9, tb=TbParams(vin_cm_v=0.5), vbp=-4.0)]
    held = analyze_ac(measurements)
    assert np.isfinite(held.gain_dc_db[0]) and np.isnan(held.gain_dc_db[1]) and np.isnan(held.power_w[1])
    assert np.all(np.isnan(held.gain_db[1]))
    assert np.isnan(analyze_noise(measurements, ac=held).noise_in_1mhz_v_per_rthz[1])


def test_a_differential_output_reads_as_the_difference_of_its_outputs() -> None:
    tb = TbParams(params=Params(topology=Topology.TELESCOPIC), vout_cm_v=0.55)
    result = analyze_ac([two_pole(100.0, 1e6, 1e9, tb=tb)])
    assert result.gain_dc_db[0] == pytest.approx(40.0, abs=0.01)
    assert result.vout_cm_v[0] == pytest.approx(0.55)  # the average of both outputs
    # an inverting response reads alike: its phase is taken from the lowest frequency
    inverted = two_pole(100.0, 1e6, 1e9)
    ac = inverted.sweeps["ac"]
    flipped = replace(inverted, sweeps={**inverted.sweeps, "ac": replace(ac, v={"outp": -ac.v["outp"]})})
    assert analyze_ac([flipped]).phase_margin_deg[0] == pytest.approx(
        analyze_ac([inverted]).phase_margin_deg[0], abs=1e-6
    )


def test_input_referred_noise_spot_and_integrated() -> None:
    measurements = [two_pole(100.0, 1e6, 1e9)]
    ac = analyze_ac(measurements)
    noise = analyze_noise(measurements, ac=ac)
    assert noise.noise_in_v_per_rthz[0] == pytest.approx(10e-9)
    assert noise.spot_frequency_hz == pytest.approx(1e6)
    assert noise.noise_in_1mhz_v_per_rthz[0] == pytest.approx(10e-9)
    # white noise integrated from 1 kHz to the unity-gain bandwidth
    assert noise.noise_in_v[0] == pytest.approx(10e-9 * np.sqrt(ac.unity_gain_bandwidth_hz[0] - 1e3), rel=0.01)
    with pytest.raises(ValueError, match="same points"):
        analyze_noise([two_pole(100.0, 1e6, 1e9, tb=TbParams(vin_cm_v=0.5))], ac=ac)


def test_unity_gain_slew_settling_and_overshoot() -> None:
    slew = analyze_slew([step_run(1e9, 2e8)])
    assert slew.vout_low_v[0] == pytest.approx(0.45) and slew.vout_high_v[0] == pytest.approx(0.75)
    assert slew.slew_rate_rise_v_per_s[0] == pytest.approx(1e9, rel=1e-3)
    assert slew.slew_rate_fall_v_per_s[0] == pytest.approx(-2e8, rel=1e-3)
    # within 1 % of the 0.3 V step: 0.297 V of ramp after the edge's middle
    assert slew.settling_rise_s[0] == pytest.approx(0.297e-9, rel=0.02)
    assert slew.settling_fall_s[0] == pytest.approx(1.485e-9, rel=0.01)
    assert slew.overshoot_rise[0] == 0.0 and slew.idd_a[0] == pytest.approx(30e-6)
    assert slew.vout_v.shape == (1, len(slew.time_s))
    with pytest.raises(ValueError, match="step bench"):
        analyze_slew([sine_run(0.01)])


def test_a_stuck_output_has_no_edges() -> None:
    stuck = step_run(1e9, 2e8)
    stuck.v["outp"][:] = 0.3
    slew = analyze_slew([stuck])
    assert np.isnan(slew.slew_rate_rise_v_per_s[0]) and np.isnan(slew.settling_fall_s[0])
    assert slew.vout_low_v[0] == pytest.approx(0.3) and slew.idd_a[0] == pytest.approx(30e-6)


def test_unity_gain_harmonic_distortion() -> None:
    distortion = analyze_distortion([sine_run(0.01)])
    # a second harmonic at 1 % of the fundamental: -40 dB
    assert distortion.thd_db[0] == pytest.approx(-40.0, abs=0.1)
    assert distortion.sndr_db[0] == pytest.approx(40.0, abs=0.1)
    assert distortion.gain[0] == pytest.approx(0.95, rel=1e-3)
    with pytest.raises(ValueError, match="sine bench"):
        analyze_distortion([step_run(1e9, 2e8)])


def characterization(params: Params) -> dict[str, Meas]:
    """Every run of ``params`` in TSMC65 (``runs.testbenches``), synthetic: the gain falling 3 dB a
    common-mode step away from mid-supply and rising with the supply; a single-ended amplifier's
    step and sine."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    found = {}
    for name, tb in block_runs.testbenches("tsmc65", params).items():
        if tb.bench is Bench.STEP:
            found[name] = replace(step_run(1e9, 2e8), param=tb, dut=params)
        elif tb.bench is Bench.SINE:
            found[name] = replace(sine_run(0.01), param=tb, dut=params)
        else:
            steps = abs(tb.vin_cm_v / tb.vdd - NOMINAL_CM) * 12
            found[name] = two_pole(100.0 * tb.vdd / 1.2 * 10 ** (-3 * steps / 20), 1e6, 1e9, tb=tb)
    return found


def test_metrics_at_mid_supply_over_the_common_mode_and_the_supply() -> None:
    runs = characterization(Params())
    by_cm = [runs[f"cm_{round(fraction * 24)}"] for fraction in CM_SWEEP]
    by_supply = [runs["cm_12" if factor == 1.0 else f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP]
    ac, supply = analyze_ac(by_cm), analyze_ac(by_supply)
    noise = analyze_noise(by_cm, ac=ac)
    found = metrics(
        ac=ac,
        noise=noise,
        supply=supply,
        slew=analyze_slew([runs["step"]]),
        distortion=analyze_distortion([runs["sine"]]),
    )
    assert isinstance(found, Metrics)
    assert found.gain_dc_db == pytest.approx(40.0, abs=0.01) and found.bandwidth_hz == pytest.approx(1e6, rel=0.01)
    assert found.power_w == pytest.approx(1.2 * 50e-6) and found.vout_cm_v == pytest.approx(0.6)
    assert found.noise_in_1mhz_v_per_rthz == pytest.approx(10e-9)
    # the gain within 6 dB of its mid-supply value: two common-mode steps either side, a third of the supply
    assert found.vin_cm_range_v == pytest.approx(1.2 / 3)
    # the lowest supply's gain, 90 % of the nominal one
    assert found.gain_dc_min_supply_db == pytest.approx(40.0 + 20 * np.log10(0.9), abs=0.01)
    assert found.slew_rate_rise_v_per_s == pytest.approx(1e9, rel=1e-3)
    assert found.slew_rate_fall_v_per_s == pytest.approx(2e8, rel=1e-3)  # reported positive
    assert found.settling_s == pytest.approx(1.485e-9, rel=0.01) and found.thd_db == pytest.approx(-40.0, abs=0.1)
    # a mid-supply point that lost its output has no range; a differential amplifier no unity-gain figures
    lost = analyze_ac([replace(run, sweeps=two_pole(1.0, 1e6, 1e9, tb=run.tb, vbp=-4.0).sweeps) for run in by_cm])
    bare = metrics(ac=lost, noise=analyze_noise(by_cm, ac=lost), supply=supply)
    assert np.isnan(bare.vin_cm_range_v) and bare.slew_rate_rise_v_per_s is None and bare.thd_db is None


def test_the_record_of_a_single_ended_and_of_a_differential_amplifier() -> None:
    single = block_runs.results(characterization(Params()))
    assert set(single.metrics) == {field for field in Metrics.__dataclass_fields__}
    assert all(isinstance(detail, Plot) for detail in single.details)
    names = [detail.name for detail in single.details]
    assert names[-2:] == ["step_response", "spectrum"] and len(set(names)) == len(names) == 14
    assert single.waves == {"unity-gain step": "step", "unity-gain sine": "sine"}
    differential = block_runs.results(characterization(Params(topology=Topology.TELESCOPIC)))
    assert [detail.name for detail in differential.details] == names[:-2] and differential.waves == {}
    assert differential.metrics["thd_db"] is None and differential.metrics["settling_s"] is None
    assert differential.metrics["gain_dc_db"] == pytest.approx(40.0, abs=0.01)
