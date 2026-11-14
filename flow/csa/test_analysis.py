"""The amplifier's analyses, metrics and record on synthetic responses of known gain, peaking and
discharge and on white noise of known ENC, as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest
from scipy.constants import elementary_charge

from flow.pipeline import Meas, MeasInfo, Plot, Sweep, SweepKind

from . import runs
from .analysis import analyze_noise, analyze_pulse, analyze_supply, metrics
from .params import CHARGES_C, SUPPLY_SWEEP, Stimulus, TbParams
from .types import Metrics

GAIN_V_PER_C = 100e-3 / 1e-15
PEAKING_S = 10e-9
SLOPE_V_PER_S = 2e6  # 10 nA out of 5 fF
INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC))


def pulse(charge: float, case: str = "krum", vdd: float = 1.2, gain: float = GAIN_V_PER_C) -> Meas:
    """An output rising linearly from 0.5 V over 10 ns from the injection step's middle to ``gain``
    of charge, then discharging at 2 V/us back to the baseline (up for an NMOS input, down for a
    PMOS one), drawing 4 uA."""
    tb = TbParams(params=getattr(runs, case)(), charge_c=charge, vdd=vdd)
    time_s = np.arange(0.0, float(tb.stop_time_s), 50e-12)
    since = time_s - float(tb.inject_time_s) - float(tb.transition_time_s) / 2
    amplitude = gain * charge
    excursion = np.clip(
        np.minimum(amplitude * since / PEAKING_S, amplitude - SLOPE_V_PER_S * (since - PEAKING_S)), 0, None
    )
    excursion = np.where(since < 0, 0.0, excursion)
    sign = 1.0 if case != "krum_pmos" else -1.0
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"out": 0.5 + sign * excursion},
        i={"vdd": np.full(len(time_s), 4e-6)},
    )


def noise(density_v_per_rthz: float, case: str = "krum", vdd: float = 1.2) -> Meas:
    """A noise run: white output noise from 1 Hz to 1 GHz, the output at 0.5 V, 4 uA drawn."""
    tb = TbParams(params=getattr(runs, case)(), stimulus=Stimulus.NOISE, charge_c=0.0, vdd=vdd)
    frequency_hz = np.logspace(0, 9, 91)
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
                v={"out": np.asarray([0.5]), "inp": np.asarray([0.3])},
                i={"vdd": np.asarray([4e-6])},
            ),
            "noise": Sweep(
                kind=SweepKind.NOISE,
                x=frequency_hz,
                v={"out": np.full_like(frequency_hz, density_v_per_rthz)},
            ),
        },
    )


@pytest.mark.parametrize("case", ("krum", "krum_pmos"))
def test_amplitude_peaking_threshold_and_return(case) -> None:
    charges = (2e-15, 0.5e-15, 1e-15)
    result = analyze_pulse([pulse(charge, case) for charge in charges])
    assert result.charge_c == pytest.approx([0.5e-15, 1e-15, 2e-15])
    assert result.vout_v == pytest.approx([0.5] * 3)
    assert result.vdd_v == pytest.approx([1.2] * 3)
    assert result.amplitude_v == pytest.approx([0.05, 0.1, 0.2], rel=1e-6)
    assert result.charge_gain_v_per_c == pytest.approx([GAIN_V_PER_C] * 3, rel=1e-6)
    assert result.peaking_time_s == pytest.approx([PEAKING_S] * 3, rel=1e-6)
    assert result.rise_time_s == pytest.approx([0.8 * PEAKING_S] * 3, rel=1e-3)
    # half the smallest amplitude: 25 mV, crossed on the way up and on the discharge
    threshold, amplitude = 0.025, np.asarray([0.05, 0.1, 0.2])
    assert result.threshold_v == pytest.approx([threshold] * 3)
    tot = PEAKING_S * (1 - threshold / amplitude) + (amplitude - threshold) / SLOPE_V_PER_S
    assert result.tot_s == pytest.approx(tot, rel=1e-3)
    # back within 5 % of the amplitude
    assert result.return_s == pytest.approx(PEAKING_S + 0.95 * amplitude / SLOPE_V_PER_S, rel=1e-3)
    assert result.idd_a == pytest.approx([4e-6] * 3)
    assert result.pulse_v.shape == (3, len(result.time_s))


def test_a_held_charge_has_no_peak_threshold_time_or_return() -> None:
    held = pulse(1e-15, "reset")
    output = held.v["out"]
    peak = int(np.argmax(output))
    output[peak:] = output[peak]
    result = analyze_pulse([held])
    assert result.amplitude_v[0] == pytest.approx(0.1, rel=1e-6)
    assert np.isnan(result.peaking_time_s[0]) and np.isnan(result.tot_s[0]) and np.isnan(result.return_s[0])
    assert result.rise_time_s[0] == pytest.approx(0.8 * PEAKING_S, rel=1e-3)


def test_a_tail_outlasting_the_record_keeps_its_peaking_time() -> None:
    # Krummenacher: the same flat top, but the amplifier still peaked; only the return is missing
    long = pulse(1e-15)
    output = long.v["out"]
    output[int(np.argmax(output)) :] = output.max()
    result = analyze_pulse([long])
    assert result.peaking_time_s[0] == pytest.approx(PEAKING_S, rel=1e-6)
    assert np.isnan(result.return_s[0]) and np.isnan(result.tot_s[0])


def test_enc_is_the_rms_noise_over_the_smallest_charge_gain() -> None:
    result = analyze_pulse([pulse(charge) for charge in (0.5e-15, 1e-15)])
    found = analyze_noise([noise(1e-7)], pulse=result)
    rms = 1e-7 * np.sqrt(1e9 - 1)
    assert found.noise_out_v[0] == pytest.approx(rms, rel=1e-6)
    assert found.enc_electrons[0] == pytest.approx(rms / GAIN_V_PER_C / elementary_charge, rel=1e-6)
    assert (found.vout_v[0], found.idd_a[0]) == (0.5, 4e-6)
    assert found.noise_out_v_per_rthz.shape == (1, 91)
    with pytest.raises(ValueError, match="does not match"):
        analyze_noise([noise(1e-7)], pulse=analyze_pulse([pulse(1e-15, "krum_pmos")]))


def test_the_analyses_refuse_the_other_runs() -> None:
    with pytest.raises(ValueError, match="charge runs"):
        analyze_pulse([noise(1e-7)])
    with pytest.raises(ValueError, match="noise runs"):
        analyze_noise([pulse(1e-15)], pulse=analyze_pulse([pulse(1e-15)]))


def test_the_supply_sweep_takes_each_point_s_smallest_charge() -> None:
    points = [analyze_pulse([pulse(0.25e-15, vdd=1.2 * f, gain=GAIN_V_PER_C * f)]) for f in SUPPLY_SWEEP]
    noises = [analyze_noise([noise(1e-7, vdd=1.2 * f)], pulse=point) for f, point in zip(SUPPLY_SWEEP, points)]
    supply = analyze_supply(points, noises=noises)
    assert supply.vdd_v == pytest.approx([1.08, 1.2, 1.32])
    assert supply.charge_gain_v_per_c == pytest.approx([GAIN_V_PER_C * f for f in SUPPLY_SWEEP], rel=1e-6)
    assert supply.power_w == pytest.approx([1.2 * f * 4e-6 for f in SUPPLY_SWEEP])
    assert supply.enc_electrons[0] > supply.enc_electrons[2]
    assert np.isnan(analyze_supply(points).enc_electrons).all()


def instance_runs(case: str) -> dict[str, Meas]:
    """Every run of one instance (``runs.testbenches``'s names): each charge at 1.2 V, the gain
    falling 1 % from the smallest to the largest charge, the smallest charge at the other
    supplies, and white noise of 1e-7 V/sqrt(Hz) but for a reset amplifier."""
    made: dict[str, Meas] = {}
    for k, charge in enumerate(CHARGES_C):
        made[f"q{round(charge * 1e18)}"] = pulse(charge, case, gain=GAIN_V_PER_C * (1 - 0.01 * k / 3))
    held = case == "reset"
    if not held:
        made["noise"] = noise(1e-7, case)
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            made[f"supply_{round(factor * 100)}"] = pulse(min(CHARGES_C), case, vdd=1.2 * factor)
            if not held:
                made[f"supply_{round(factor * 100)}_noise"] = noise(1e-7, case, vdd=1.2 * factor)
    if held:
        # a reset amplifier's response holds the charge: no peak, no return
        for meas in made.values():
            output = meas.v["out"]
            output[int(np.argmax(output)) :] = output.max()
    return made


def test_the_metrics_and_the_record() -> None:
    record = runs.results(instance_runs("krum"))
    found = Metrics(**record.metrics)
    assert found.charge_gain_v_per_c == pytest.approx(GAIN_V_PER_C, rel=1e-6)
    assert found.linearity == pytest.approx(0.99, rel=1e-6)
    assert found.peaking_time_s == pytest.approx(PEAKING_S, rel=1e-6)
    assert found.vout_v == pytest.approx(0.5) and found.power_w == pytest.approx(1.2 * 4e-6)
    assert found.tot_2fc_s > 0 and found.return_2fc_s > found.tot_2fc_s
    assert found.enc_electrons == pytest.approx(1e-7 * math.sqrt(1e9 - 1) / GAIN_V_PER_C / elementary_charge, rel=1e-6)
    assert found.charge_gain_min_supply_v_per_c == pytest.approx(GAIN_V_PER_C, rel=1e-6)
    assert all(isinstance(plot, Plot) for plot in record.details)
    assert [plot.name for plot in record.details] == [
        *("pulse", "amplitude_charge", "gain_charge", "tot_charge", "noise_density"),
        *("gain_supply", "peaking_supply", "enc_supply", "power_supply"),
    ]
    assert record.waves == {"0.25 fC": "q250", "2 fC": "q2000"}


def test_a_reset_amplifier_has_no_noise_peaking_or_return() -> None:
    record = runs.results(instance_runs("reset"))
    found = Metrics(**record.metrics)
    assert found.charge_gain_v_per_c == pytest.approx(GAIN_V_PER_C, rel=1e-6)
    for name in ("peaking_time_s", "tot_2fc_s", "return_2fc_s", "noise_out_v", "enc_electrons"):
        assert math.isnan(getattr(found, name)), name
    assert math.isnan(found.peaking_time_max_supply_s) and math.isnan(found.enc_max_supply_electrons)
    assert "noise_density" not in {plot.name for plot in record.details}


def test_the_metrics_take_the_smallest_and_the_largest_charge() -> None:
    result = analyze_pulse([pulse(charge) for charge in CHARGES_C])
    supply = analyze_supply([result, result])
    values = metrics(pulse=result, supply=supply)
    assert values.linearity == pytest.approx(1.0, rel=1e-6)
    assert values.tot_2fc_s == pytest.approx(float(result.tot_s[-1]))
    assert math.isnan(values.noise_out_v)
    assert replace(values, vout_v=0.0).vout_v == 0.0
