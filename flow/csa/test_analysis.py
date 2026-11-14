"""The amplifier's analyses, metrics and record on synthetic responses whose answers are known in
closed form, as a run's measurement (``flow.pipeline.Meas``) reads: a linear rise and discharge, the
CR-RC pulse and the single-pole step on a simulator's uneven time steps, an undershoot, a response
that outlasts its record or ends with it, no response at all; white noise and an RC low-pass's noise
of known ENC; and the supply sweep and the metrics from results of known values."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest
from hdl21.primitives import MosType
from scipy.constants import Boltzmann, elementary_charge
from scipy.special import lambertw

from flow.pipeline import Meas, MeasInfo, Plot, Sweep, SweepKind

from . import runs
from .analysis import analyze_noise, analyze_pulse, analyze_supply, metrics
from .params import CHARGES_C, SUPPLY_SWEEP, Stimulus, TbParams
from .types import AnalysisNoise, AnalysisPulse, AnalysisSupply, Metrics

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
    # a kink, no smooth maximum: the parabola through the peak sample and its neighbours (rising at
    # s1 = A / 10 ns, falling at s2 = 2 V/us) peaks h (s1 - s2) / (2 (s1 + s2)) after the corner,
    # within half a strobe (h = 50 ps)
    s1 = np.asarray([0.05, 0.1, 0.2]) / PEAKING_S
    vertex = 50e-12 * (s1 - SLOPE_V_PER_S) / (2 * (s1 + SLOPE_V_PER_S))
    assert result.peaking_time_s == pytest.approx(PEAKING_S + vertex, rel=1e-9)
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
    # the amplitude G0 q_k (1 - 0.01 k / 3) against the end-point line 0.99 G0 q: off by
    # 0.01 G0 q_k (1 - k / 3), largest at 0.5 and 1 fC (G0 fC / 300), over 1.98 G0 fC
    assert found.nonlinearity == pytest.approx(0.01 / 3 / 1.98, rel=1e-6)
    # the kinked peak's vertex, as in test_amplitude_peaking_threshold_and_return: within half a strobe
    assert found.peaking_time_s == pytest.approx(PEAKING_S, abs=25e-12)
    assert found.vout_v == pytest.approx(0.5) and found.power_w == pytest.approx(1.2 * 4e-6)
    assert found.tot_2fc_s > 0 and found.return_2fc_s > found.tot_2fc_s
    assert found.enc_electrons == pytest.approx(1e-7 * math.sqrt(1e9 - 1) / GAIN_V_PER_C / elementary_charge, rel=1e-6)
    assert found.charge_gain_min_supply_v_per_c == pytest.approx(GAIN_V_PER_C, rel=1e-6)
    assert all(isinstance(plot, Plot) for plot in record.details)
    assert [plot.name for plot in record.details] == [
        *("pulse_q250", "pulse_q500", "pulse_q1000", "pulse_q2000"),
        *("amplitude_charge", "gain_charge", "tot_charge", "noise_density"),
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
    # no figure of NaN alone: no noise density, time over threshold, peaking time or ENC
    names = {plot.name for plot in record.details}
    assert names.isdisjoint({"noise_density", "tot_charge", "peaking_supply", "enc_supply"})
    assert {"amplitude_charge", "gain_charge", "gain_supply", "power_supply", "pulse_q250"} <= names


def test_the_metrics_take_the_smallest_and_the_largest_charge() -> None:
    result = analyze_pulse([pulse(charge) for charge in CHARGES_C])
    supply = analyze_supply([result, result])
    values = metrics(pulse=result, supply=supply)
    assert values.nonlinearity == pytest.approx(0.0, abs=1e-6)
    assert values.tot_2fc_s == pytest.approx(float(result.tot_s[-1]))
    assert math.isnan(values.noise_out_v)
    assert replace(values, vout_v=0.0).vout_v == 0.0


# ---- closed-form responses on a simulator's time steps ------------------------------------------

# Spectre's own steps where the analysis takes them as they come: uneven, between 10 and STEP_MAX_S
STEP_MAX_S = 100e-12
TAU_S = 10e-9
BASELINE_V = 0.6
IDD_A = 4e-6


def simulator_axis(stop_s: float, seed: int) -> np.ndarray:
    """A transient's time axis from 0 to ``stop_s`` in uneven steps of 10 ps to ``STEP_MAX_S``, the
    same for the same ``seed``, with a point at each corner of the bench's sources (the reset's and
    the injection step's edges), as Spectre places one at every breakpoint."""
    tb = TbParams()
    steps = np.random.default_rng(seed).uniform(10e-12, STEP_MAX_S, int(stop_s / 10e-12) + 1)
    time_s = np.r_[0.0, np.cumsum(steps)]
    edge = float(tb.transition_time_s)
    corners = [float(start) + shift for start in (tb.reset_time_s, tb.inject_time_s) for shift in (0.0, edge)]
    time_s = np.union1d(time_s[time_s < stop_s], [*corners, stop_s])
    # a step of under a picosecond beside a corner merged into it
    keep = np.r_[True, np.diff(time_s) > 1e-12]
    keep[np.searchsorted(time_s, corners)] = True
    return time_s[keep]


def response_run(
    charge: float,
    excursion,
    case: str = "krum",
    *,
    vdd: float = 1.2,
    time_s: np.ndarray | None = None,
    seed: int = 0,
    idd_a: np.ndarray | None = None,
) -> Meas:
    """A charge run of ``case``: the output at ``BASELINE_V`` until the injection step's middle, then
    ``excursion`` of the time since away from the input device's rail (up for an NMOS input, down
    for a PMOS one), on ``time_s`` (a simulator's axis by ``seed`` unless given), ``IDD_A`` drawn
    unless ``idd_a`` is given."""
    tb = TbParams(params=getattr(runs, case)(), charge_c=charge, vdd=vdd)
    time_s = simulator_axis(float(tb.stop_time_s), seed) if time_s is None else time_s
    since = time_s - float(tb.inject_time_s) - float(tb.transition_time_s) / 2
    sign = 1.0 if tb.params.input_xtors is MosType.NMOS else -1.0
    output = BASELINE_V + sign * np.where(since > 0, excursion(np.maximum(since, 0.0)), 0.0)
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"out": output},
        i={"vdd": np.full(len(time_s), IDD_A) if idd_a is None else idd_a},
    )


def crrc(amplitude_v: float, tau_s: float = TAU_S):
    """The CR-RC pulse of ``amplitude_v`` peaking at ``tau_s``: v(t) = A (t/tau) e^(1 - t/tau)."""
    return lambda since: amplitude_v * since / tau_s * np.exp(1 - since / tau_s)


# not in the reference texts: the CR-RC pulse v = A x e^(1 - x), x = t/tau (a detector read-out's
# shaped response to a charge step). dv/dx = A (1 - x) e^(1 - x) vanishes at x = 1 alone: the
# amplitude is A, the peaking time tau. v = a A where (-x) e^(-x) = -a/e, so x = -W(-a/e) (Lambert's
# W): the principal branch before the peak, the branch W_-1 after it.
def crrc_rising(level: float) -> float:
    """Where the CR-RC pulse first reaches ``level`` of its amplitude, in units of tau."""
    return float(-np.real(lambertw(-level / math.e, 0)))


def crrc_falling(level: float) -> float:
    """Where the CR-RC pulse falls back through ``level`` of its amplitude, in units of tau."""
    return float(-np.real(lambertw(-level / math.e, -1)))


# The CR-RC pulse of G q on uneven steps of at most h = 100 ps, tau = 10 ns, the charges out of order
# and each run on its own axis.
# Amplitude G q, peaking time tau (above); charge gain G.
# [Baker] Eq. (2.26), p. 49: the rise time from 10 % to 90 % of the final level, here the amplitude:
# tau (x0(0.9) - x0(0.1)) with x0 = crrc_rising.
# Time over the threshold a = (G q_min / 2) / (G q): tau (x-1(a) - x0(a)). Return to within 5 % of the
# amplitude: tau x-1(0.05) from the injection. Baseline and supply current: constant at rest.
# Tolerances from the sampling: the largest sample lies within h of the peak (peaking time to h)
# and below the peak by at most G q (h/tau)^2 / 2 (amplitude and gain to 5e-5). A crossing is
# interpolated linearly between samples: its level is off by at most h^2 |v''| / 8 plus the 5e-5 of
# the measured amplitude the levels scale with; the worst crossing, the rising 90 % one at x = 0.61
# ((2.6e-5 + 4.5e-5) G q over a slope of 0.58 G q / tau), is within 1.5 ps, so a duration within 3 ps.
@pytest.mark.parametrize("case", ("krum", "krum_pmos"))
def test_a_crrc_pulse_on_uneven_steps(case: str) -> None:
    charges = (2e-15, 0.25e-15, 1e-15, 0.5e-15)
    result = analyze_pulse([response_run(q, crrc(GAIN_V_PER_C * q), case, seed=k) for k, q in enumerate(charges)])
    q = np.asarray(sorted(charges))
    amplitude = GAIN_V_PER_C * q
    assert result.charge_c == pytest.approx(q)
    assert result.vout_v == pytest.approx([BASELINE_V] * 4, rel=1e-12)
    assert result.idd_a == pytest.approx([IDD_A] * 4, rel=1e-12)
    assert result.amplitude_v == pytest.approx(amplitude, rel=5e-5)
    assert result.charge_gain_v_per_c == pytest.approx([GAIN_V_PER_C] * 4, rel=5e-5)
    assert result.peaking_time_s == pytest.approx([TAU_S] * 4, abs=STEP_MAX_S)
    rise = TAU_S * (crrc_rising(0.9) - crrc_rising(0.1))
    assert result.rise_time_s == pytest.approx([rise] * 4, abs=3e-12)
    assert result.threshold_v == pytest.approx([amplitude[0] / 2] * 4, rel=5e-5)
    levels = amplitude[0] / 2 / amplitude
    tot = [TAU_S * (crrc_falling(a) - crrc_rising(a)) for a in levels]
    assert result.tot_s == pytest.approx(tot, abs=3e-12)
    assert result.return_s == pytest.approx([TAU_S * crrc_falling(0.05)] * 4, abs=3e-12)


# A reset amplifier holds the charge: the single-pole step A (1 - e^(-t/tau)), tau = 5 ns, held to
# the record's end (440 ns, e^-88 short of A: A in double precision).
# [Baker] Eq. (2.26), p. 49: its 10-90 % rise time is tau ln 9 (2.2 RC there).
# No peak (a reset amplifier's peaking time is NaN), no fall through the threshold (time over
# threshold NaN), never back within 5 % of the baseline (return NaN).
# Tolerance: the interpolated level off by at most h^2 A / (8 tau^2) = 5e-5 A over the slope at the
# 90 % level, 0.1 A / tau: 2.5 ps.
def test_a_reset_amplifier_holds_a_single_pole_step() -> None:
    tau_s, amplitude = 5e-9, 0.1
    result = analyze_pulse([response_run(1e-15, lambda since: amplitude * (1 - np.exp(-since / tau_s)), "reset")])
    assert result.amplitude_v[0] == pytest.approx(amplitude, rel=1e-12)
    assert result.rise_time_s[0] == pytest.approx(tau_s * math.log(9), abs=3e-12)
    assert np.isnan(result.peaking_time_s[0]) and np.isnan(result.tot_s[0]) and np.isnan(result.return_s[0])


# A discharge that passes the baseline: a linear rise to A = 0.1 V over 10 ns, a fall at 2 V/us to an
# undershoot U = 20 mV below the baseline, a recovery at 0.5 V/us. The return is where the output
# stays within 5 % of A of the baseline (AnalysisPulse's definition): the recovery's crossing of
# -0.05 A, at 10 ns + (A + U) / (2 V/us) + (U - 0.05 A) / (0.5 V/us) = 10 + 60 + 30 = 100 ns, not the
# discharge's crossing of +0.05 A (57.5 ns). The time over threshold is the rise's and the fall's
# crossings of A/2: (10 - 5) + 0.05 V / (2 V/us) = 30 ns.
# Tolerance: every crossing lies on a straight segment, exact but for the levels, which scale with the
# largest sample. That falls short of the corner by at most 10 V/us x h / 6 = 0.17 mV (the higher of
# the two samples straddling it, on the rise at 10 V/us and the fall at 2 V/us, a step h apart),
# moving the 5 % level by 8.3 uV (17 ps on the 0.5 V/us recovery) and the threshold A/2 by 83 uV
# (8 ps on the rise and 42 ps on the fall: 50 ps).
def test_an_undershoot_extends_the_return_to_its_recovery() -> None:
    rise_s, fall, recover, amplitude, under = 10e-9, 2e6, 0.5e6, 0.1, 0.02
    bottom_s = rise_s + (amplitude + under) / fall

    def excursion(since: np.ndarray) -> np.ndarray:
        up = amplitude * since / rise_s
        down = amplitude - fall * (since - rise_s)
        back = np.minimum(-under + recover * (since - bottom_s), 0.0)
        return np.where(since < rise_s, up, np.where(since < bottom_s, down, back))

    result = analyze_pulse([response_run(1e-15, excursion)])
    assert result.return_s[0] == pytest.approx(100e-9, abs=17e-12)
    assert result.tot_s[0] == pytest.approx(30e-9, abs=50e-12)
    assert result.peaking_time_s[0] == pytest.approx(rise_s, abs=STEP_MAX_S)


# The baseline and the supply current at rest: the average over the second half of the time between
# the reset's opening (10 ns) and the injection (60 ns), 35 to 60 ns. The output settles from 0 V to
# the baseline at 30 ns; the current is 50 uA before 30 ns and after 65 ns and between them a ramp
# I0 + k (t - 47.5 ns): its average over 35 to 60 ns, symmetric about 47.5 ns, is I0 (integrated
# exactly by the trapezoid on straight segments, the window's ends interpolated on the ramp).
def test_the_baseline_and_the_current_are_the_averages_at_rest() -> None:
    tb = TbParams(charge_c=1e-15)
    time_s = simulator_axis(float(tb.stop_time_s), 3)
    ramp = (time_s > 30e-9) & (time_s < 65e-9)
    current = np.where(ramp, IDD_A + 2e-6 / 25e-9 * (time_s - 47.5e-9), 50e-6)
    run = response_run(1e-15, crrc(0.1), time_s=time_s, idd_a=current)
    run.v["out"][time_s < 30e-9] = 0.0
    result = analyze_pulse([run])
    assert result.vout_v[0] == pytest.approx(BASELINE_V, rel=1e-12)
    assert result.idd_a[0] == pytest.approx(IDD_A, rel=1e-9)


# A CR-RC pulse slower than its record: tau = 100 ns, the record 440 ns past the injection, where the
# pulse is still 4.4 e^-3.4 = 0.147 of its amplitude, above 5 %: no return (NaN). Its peak (at tau)
# and both crossings of half its amplitude, tau (x-1(0.5) - x0(0.5)) = 244.6 ns, lie inside: those
# hold. Tolerances as for the CR-RC pulse above, (h/tau)^2 a hundred times smaller.
def test_a_pulse_slower_than_its_record_has_no_return() -> None:
    tau_s = 100e-9
    result = analyze_pulse([response_run(1e-15, crrc(0.1, tau_s))])
    assert result.peaking_time_s[0] == pytest.approx(tau_s, abs=STEP_MAX_S)
    assert result.tot_s[0] == pytest.approx(tau_s * (crrc_falling(0.5) - crrc_rising(0.5)), abs=3e-12)
    assert np.isnan(result.return_s[0])


# A record that ends one 100 ps sample after the injection (60.05 ns, on Spectre's 50 ps strobes):
# the excursion is two samples, 0 and v1 = A x e^(1 - x) at x = 100 ps / tau. The analysis sees a
# straight line between them: amplitude v1, peak at the last sample (100 ps), the 10-90 % levels
# 80 % of the step apart (80 ps), half of v1 crossed on the way up but never on the way down (time
# over threshold NaN), never back to the baseline (return NaN). A record of one sample has no rest
# and no response: refused.
def test_a_record_ending_just_after_the_injection() -> None:
    tb = TbParams(charge_c=1e-15)
    inject_s = float(tb.inject_time_s) + float(tb.transition_time_s) / 2
    time_s = np.r_[np.arange(1202) * 50e-12, inject_s + 100e-12]
    result = analyze_pulse([response_run(1e-15, crrc(0.1), time_s=time_s)])
    x = 100e-12 / TAU_S
    assert result.amplitude_v[0] == pytest.approx(0.1 * x * math.exp(1 - x), rel=1e-9)
    assert result.peaking_time_s[0] == pytest.approx(100e-12, rel=1e-6)
    assert result.rise_time_s[0] == pytest.approx(80e-12, rel=1e-6)
    assert np.isnan(result.tot_s[0]) and np.isnan(result.return_s[0])
    with pytest.raises(ValueError):
        analyze_pulse([response_run(1e-15, crrc(0.1), time_s=np.asarray([0.0]))])


# An amplifier that does not respond (the output stays at its baseline): no pulse, so no peak, no
# rise, no time over threshold and no return; each is undefined (NaN), as for a pulse that never
# comes back. A return or peaking time of 0 s would rank a dead amplifier the best on both.
def test_no_response_has_no_peak_or_return() -> None:
    result = analyze_pulse([response_run(1e-15, lambda since: np.zeros_like(since))])
    assert result.amplitude_v[0] == 0.0 and result.charge_gain_v_per_c[0] == 0.0
    assert np.isnan(result.rise_time_s[0]) and np.isnan(result.tot_s[0])
    assert np.isnan(result.peaking_time_s[0]) and np.isnan(result.return_s[0])
    # nor an ENC: no gain to refer the output noise to the input
    found = analyze_noise([noise_run(np.full(91, 1e-7), np.logspace(0, 9, 91))], pulse=result)
    assert found.noise_out_v[0] > 0 and np.isnan(found.enc_electrons[0])


# The responses on one time grid: Spectre writes each charge run at the same 50 ps strobes, so the
# runs share their samples from the injection (60.05 ns, a strobe) on, and the grid is the shortest
# record's (one run stops at 400 ns: 339.95 ns of response). Each row is that charge's CR-RC pulse at
# the grid's times; the samples are the closed form's own (to double precision).
def test_the_responses_share_the_strobes_from_the_injection() -> None:
    strobes = np.arange(10001) * 50e-12
    charge_runs = [
        response_run(q, crrc(GAIN_V_PER_C * q), time_s=strobes if q != 1e-15 else strobes[:8001]) for q in CHARGES_C
    ]
    result = analyze_pulse(charge_runs)
    assert result.time_s[0] == 0.0 and result.time_s[-1] == pytest.approx(339.95e-9, rel=1e-9)
    x = result.time_s / TAU_S
    expected = np.outer(GAIN_V_PER_C * np.asarray(CHARGES_C), x * np.exp(1 - x))
    assert result.pulse_v == pytest.approx(expected, abs=1e-12)


# Runs written on their own uneven steps (the simulator's, unstrobed) share no samples: each row is
# still its charge's response at the grid's times, which takes resampling onto the one grid. Past
# the injection step's second corner (50 ps after its middle, a sample of every run) the CR-RC
# pulse's linear interpolation is off by at most h^2 |v''| / 8 <= 7e-5 G q; before it each run's
# samples straddle the kink at its own steps, off by up to e h / tau G q = 2.7e-2 G q.
def test_responses_on_their_own_steps_are_resampled_onto_the_grid() -> None:
    result = analyze_pulse([response_run(q, crrc(GAIN_V_PER_C * q), seed=k) for k, q in enumerate(CHARGES_C)])
    past = result.time_s >= float(TbParams().transition_time_s) / 2
    x = result.time_s[past] / TAU_S
    assert result.pulse_v.shape == (len(CHARGES_C), len(result.time_s))
    for q, row in zip(CHARGES_C, result.pulse_v, strict=True):
        assert row[past] == pytest.approx(GAIN_V_PER_C * q * x * np.exp(1 - x), abs=1e-4 * GAIN_V_PER_C * q)


# ---- noise ---------------------------------------------------------------------------------------


def noise_run(density: np.ndarray, frequency_hz: np.ndarray, case: str = "krum", vdd: float = 1.2) -> Meas:
    """A noise run: the output noise ``density`` (V/sqrt(Hz)) over ``frequency_hz``, the operating
    point's output at ``BASELINE_V`` and ``IDD_A`` drawn."""
    tb = TbParams(params=getattr(runs, case)(), stimulus=Stimulus.NOISE, charge_c=0.0, vdd=vdd)
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
                v={"out": np.asarray([BASELINE_V])},
                i={"vdd": np.asarray([IDD_A])},
            ),
            "noise": Sweep(kind=SweepKind.NOISE, x=frequency_hz, v={"out": density}),
        },
    )


def pulse_result(case: str = "krum", **values) -> AnalysisPulse:
    """A pulse result of ``case`` with the given arrays, every other field zero, one row a charge."""
    rows = len(values["charge_c"])
    names = ("charge_c", "vdd_v", "vout_v", "amplitude_v", "peaking_time_s", "rise_time_s", "threshold_v")
    filled = {name: np.asarray(values.get(name, np.zeros(rows)), dtype=np.float64) for name in names}
    for name in ("tot_s", "return_s", "idd_a"):
        filled[name] = np.asarray(values.get(name, np.zeros(rows)), dtype=np.float64)
    return AnalysisPulse(
        group=None,
        index=None,
        dut=getattr(runs, case)(),
        time_s=np.asarray(values.get("time_s", np.zeros(2)), dtype=np.float64),
        pulse_v=np.asarray(values.get("pulse_v", np.zeros((rows, 2))), dtype=np.float64),
        **filled,
    )


# An RC low-pass's output noise, R = 100 kOhm, C = 1 pF, T = 300 K, on Spectre's ten points a decade
# from 1 Hz to 1 GHz.
# [Razavi-Analog] Eq. (7.19), p. 229: S_out(f) = 4kTR / (4 pi^2 R^2 C^2 f^2 + 1).
# [Razavi-Analog] Eq. (7.22), p. 229: its integral, between f1 and f2 rather than 0 and infinity,
# P = (2kT / (pi C)) (atan(2 pi R C f2) - atan(2 pi R C f1)), about kT/C (Eq. (7.23)): 64 uV rms.
# The ENC is that over the smallest charge's gain (1e14 V/C at 0.25 fC; 2 fC at 0.98 of it), in
# electrons (not in the reference texts: the detector read-out's equivalent noise charge).
# Tolerance: the trapezoid over ten points a decade overestimates the power of an f^-2 tail by
# cosh(ln 10^0.1) - 1 = 2.7 % a segment and of the flat part not at all, so the rms by under 1.4 %.
def test_the_noise_of_an_rc_low_pass_and_its_enc() -> None:
    resistance, capacitance, temperature = 100e3, 1e-12, 300.0
    frequency_hz = np.logspace(0, 9, 91)
    rc = resistance * capacitance
    density = np.sqrt(4 * Boltzmann * temperature * resistance / (4 * math.pi**2 * rc**2 * frequency_hz**2 + 1))
    known_pulse = pulse_result(charge_c=[2e-15, 0.25e-15], amplitude_v=[0.196, 0.025])
    found = analyze_noise([noise_run(density, frequency_hz)], pulse=known_pulse)
    power = 2 * Boltzmann * temperature / (math.pi * capacitance)
    power *= math.atan(2 * math.pi * rc * 1e9) - math.atan(2 * math.pi * rc * 1.0)
    rms = math.sqrt(power)
    assert found.noise_out_v[0] == pytest.approx(rms, rel=1.4e-2)
    assert found.charge_gain_v_per_c[0] == pytest.approx(1e14, rel=1e-12)
    assert found.enc_electrons[0] == pytest.approx(rms / 1e14 / elementary_charge, rel=1.4e-2)
    assert (found.vout_v[0], found.idd_a[0]) == (BASELINE_V, IDD_A)
    assert found.frequency_hz == pytest.approx(frequency_hz) and found.noise_out_v_per_rthz[0] == pytest.approx(density)


# The fewest points a noise sweep holds, two (fstart < fstop): a flat density d from 1 kHz to 1 MHz
# integrates to d^2 (f2 - f1) ([Razavi-Analog] Eq. (7.20), p. 229, over the band), exactly under the
# trapezoid. Two runs give two rows; runs on different sweeps are refused.
def test_a_flat_density_over_two_points_and_two_runs() -> None:
    frequency_hz = np.asarray([1e3, 1e6])
    known_pulse = pulse_result(charge_c=[0.25e-15], amplitude_v=[0.025])
    found = analyze_noise(
        [noise_run(np.full(2, 1e-7), frequency_hz), noise_run(np.full(2, 2e-7), frequency_hz)], pulse=known_pulse
    )
    rms = 1e-7 * math.sqrt(1e6 - 1e3)
    assert found.noise_out_v == pytest.approx([rms, 2 * rms], rel=1e-12)
    assert found.enc_electrons == pytest.approx([rms / 1e14 / elementary_charge, 2 * rms / 1e14 / elementary_charge])
    with pytest.raises(ValueError, match="one frequency sweep"):
        analyze_noise(
            [noise_run(np.full(2, 1e-7), frequency_hz), noise_run(np.full(2, 1e-7), 2 * frequency_hz)],
            pulse=known_pulse,
        )


# ---- the supply sweep and the metrics ------------------------------------------------------------


# Three supplies, each pulse result's rows by charge (the smallest first, as analyze_pulse sorts
# them): the gathered values are each result's first row, its power the supply times its current
# at rest (P = V_DD I_DD, [Razavi-PLL] Sec. 3.3.2, p. 74), the ENC each noise result's.
def test_the_supply_sweep_gathers_the_smallest_charge() -> None:
    supplies = (1.08, 1.2, 1.32)
    pulses = [
        pulse_result(
            charge_c=[0.25e-15, 2e-15],
            vdd_v=[vdd, vdd],
            amplitude_v=[0.025 * k, 0.2],
            peaking_time_s=[(10 - k) * 1e-9, 1.0],
            idd_a=[(4 + k) * 1e-6, 1.0],
        )
        for k, vdd in enumerate(supplies)
    ]
    noises = [
        AnalysisNoise(
            group=None,
            index=None,
            dut=runs.krum(),
            vout_v=np.asarray([0.5]),
            idd_a=np.asarray([4e-6]),
            noise_out_v=np.asarray([1e-3]),
            charge_gain_v_per_c=np.asarray([1e14]),
            enc_electrons=np.asarray([100.0 + k]),
            frequency_hz=np.asarray([1.0, 10.0]),
            noise_out_v_per_rthz=np.zeros((1, 2)),
        )
        for k in range(3)
    ]
    supply = analyze_supply(pulses, noises=noises)
    assert supply.vdd_v == pytest.approx(supplies)
    assert supply.charge_gain_v_per_c == pytest.approx([0.0, 1e14, 2e14])
    assert supply.peaking_time_s == pytest.approx([10e-9, 9e-9, 8e-9])
    assert supply.enc_electrons == pytest.approx([100.0, 101.0, 102.0])
    assert supply.power_w == pytest.approx([1.08 * 4e-6, 1.2 * 5e-6, 1.32 * 6e-6])
    assert np.isnan(analyze_supply(pulses).enc_electrons).all()
    with pytest.raises(ValueError, match="one noise result a pulse result"):
        analyze_supply(pulses, noises=noises[:2])
    with pytest.raises(ValueError, match="does not match"):
        analyze_supply(pulses, noises=[replace(noises[0], dut=runs.krum_pmos()), *noises[1:]])


# The metrics from results of known values: the smallest charge's gain (25 mV / 0.25 fC = 1e14 V/C),
# peaking and rise time, baseline and power (1.2 V x 4.5 uA); the nonlinearity ([Razavi-Analog]
# Fig. 14.4, p. 578): the end-point line through 0 and 196 mV at 2 fC is 24.5, 49 and 98 mV at 0.25,
# 0.5 and 1 fC, the amplitudes 25, 50 and 99 mV off it by 0.5, 1 and 1 mV, the largest 1 mV over
# 196 mV; the 2 fC time over threshold and return; the
# noise and ENC; over the supply the smallest gain, the largest peaking time and ENC, NaN where a
# point is NaN.
def test_the_metrics_of_known_results() -> None:
    known_pulse = pulse_result(
        charge_c=list(CHARGES_C),
        vdd_v=[1.2] * 4,
        vout_v=[0.55, 0.0, 0.0, 0.0],
        amplitude_v=[0.025, 0.05, 0.099, 0.196],
        peaking_time_s=[9e-9, 0.0, 0.0, 0.0],
        rise_time_s=[5e-9, 0.0, 0.0, 0.0],
        tot_s=[20e-9, 40e-9, 60e-9, 80e-9],
        return_s=[50e-9, 0.0, 0.0, 150e-9],
        idd_a=[4.5e-6, 0.0, 0.0, 0.0],
    )
    known_noise = AnalysisNoise(
        group=None,
        index=None,
        dut=runs.krum(),
        vout_v=np.asarray([0.55]),
        idd_a=np.asarray([4.5e-6]),
        noise_out_v=np.asarray([2e-3]),
        charge_gain_v_per_c=np.asarray([1e14]),
        enc_electrons=np.asarray([125.0]),
        frequency_hz=np.asarray([1.0, 10.0]),
        noise_out_v_per_rthz=np.zeros((1, 2)),
    )
    supply = AnalysisSupply(
        group=None,
        index=None,
        dut=runs.krum(),
        vdd_v=np.asarray([1.08, 1.2, 1.32]),
        charge_gain_v_per_c=np.asarray([0.9e14, 1e14, 1.05e14]),
        peaking_time_s=np.asarray([12e-9, 9e-9, 8e-9]),
        enc_electrons=np.asarray([140.0, 125.0, 118.0]),
        power_w=np.asarray([4e-6, 5.4e-6, 7e-6]),
    )
    found = metrics(pulse=known_pulse, noise=known_noise, supply=supply)
    assert found == Metrics(
        charge_gain_v_per_c=pytest.approx(1e14),
        peaking_time_s=9e-9,
        rise_time_s=5e-9,
        vout_v=0.55,
        nonlinearity=pytest.approx(1e-3 / 0.196),
        tot_2fc_s=80e-9,
        return_2fc_s=150e-9,
        power_w=pytest.approx(5.4e-6),
        noise_out_v=2e-3,
        enc_electrons=125.0,
        charge_gain_min_supply_v_per_c=0.9e14,
        peaking_time_max_supply_s=12e-9,
        enc_max_supply_electrons=140.0,
    )
    failed = replace(supply, charge_gain_v_per_c=np.asarray([np.nan, 1e14, 1.05e14]))
    assert math.isnan(metrics(pulse=known_pulse, noise=known_noise, supply=failed).charge_gain_min_supply_v_per_c)


# Every run of one instance as closed forms, through the record (runs.results): the CR-RC pulse at
# each charge (gain G0 (1 - 0.01 k / 3) for the k-th charge, tau = 10 ns), white noise of
# d = 1e-7 V/sqrt(Hz), and at 90 and 110 % of the supply the 0.25 fC pulse with gain G0 f and
# peaking time tau / f and the same noise. The metrics, derived as in the tests above:
# gain G0, peaking time tau, rise tau (x0(0.9) - x0(0.1)), baseline, power 1.2 V x I_DD, the
# nonlinearity (as for instance_runs: (0.01 / 3) / 1.98), the 2 fC time over the threshold a = (0.25 G0 / 2) / (2 x 0.99 G0) and return tau x-1(0.05),
# the rms d sqrt(1 GHz - 1 Hz) and the ENC that over G0 q_e; over the supply the smallest gain
# 0.9 G0, the largest peaking time tau / 0.9 and the largest ENC rms / (0.9 G0 q_e).
def test_the_record_of_closed_form_runs() -> None:
    made: dict[str, Meas] = {}
    for k, q in enumerate(CHARGES_C):
        made[f"q{round(q * 1e18)}"] = response_run(q, crrc(GAIN_V_PER_C * (1 - 0.01 * k / 3) * q), seed=k)
    density, band = 1e-7, np.logspace(0, 9, 91)
    made["noise"] = noise_run(np.full(91, density), band)
    for factor in (0.9, 1.1):
        q = min(CHARGES_C)
        made[f"supply_{round(factor * 100)}"] = response_run(
            q, crrc(GAIN_V_PER_C * factor * q, TAU_S / factor), vdd=1.2 * factor, seed=10 + round(factor * 10)
        )
        made[f"supply_{round(factor * 100)}_noise"] = noise_run(np.full(91, density), band, vdd=1.2 * factor)
    found = Metrics(**runs.results(made).metrics)
    rms = density * math.sqrt(1e9 - 1)
    level = (GAIN_V_PER_C * min(CHARGES_C) / 2) / (GAIN_V_PER_C * 0.99 * max(CHARGES_C))
    assert found.charge_gain_v_per_c == pytest.approx(GAIN_V_PER_C, rel=5e-5)
    assert found.peaking_time_s == pytest.approx(TAU_S, abs=STEP_MAX_S)
    assert found.rise_time_s == pytest.approx(TAU_S * (crrc_rising(0.9) - crrc_rising(0.1)), abs=3e-12)
    assert found.vout_v == pytest.approx(BASELINE_V, rel=1e-12)
    assert found.power_w == pytest.approx(1.2 * IDD_A, rel=1e-12)
    # each amplitude within 5e-5 of its own: the deviations within 1e-4 of the 2 fC amplitude
    assert found.nonlinearity == pytest.approx(0.01 / 3 / 1.98, abs=1e-4)
    assert found.tot_2fc_s == pytest.approx(TAU_S * (crrc_falling(level) - crrc_rising(level)), abs=3e-12)
    assert found.return_2fc_s == pytest.approx(TAU_S * crrc_falling(0.05), abs=3e-12)
    assert found.noise_out_v == pytest.approx(rms, rel=1e-12)
    assert found.enc_electrons == pytest.approx(rms / GAIN_V_PER_C / elementary_charge, rel=5e-5)
    assert found.charge_gain_min_supply_v_per_c == pytest.approx(0.9 * GAIN_V_PER_C, rel=5e-5)
    assert found.peaking_time_max_supply_s == pytest.approx(TAU_S / 0.9, abs=STEP_MAX_S)
    assert found.enc_max_supply_electrons == pytest.approx(rms / (0.9 * GAIN_V_PER_C) / elementary_charge, rel=5e-5)


# A compressing amplitude A(Q) = G Q (1 - Q / Q0), Q0 = 20 fC, over the charges 0.25 to 2 fC.
# [Razavi-Analog] Fig. 14.4, p. 578: the straight line through the end points (0, 0) and
# (Qmax, A(Qmax)) is G Q (1 - Qmax / Q0); the amplitude falls below it by G Q (Qmax - Q) / Q0, which
# peaks at Q = Qmax / 2 (1 fC, one of the charges) at G Qmax^2 / (4 Q0); over A(Qmax) the
# nonlinearity is Qmax / (4 (Q0 - Qmax)) = 2 / 72. A gain ratio of the end charges would read
# (1 - Qmax / Q0) / (1 - Qmin / Q0) instead, which no straight line defines.
def test_the_nonlinearity_of_a_compressing_amplitude() -> None:
    q, q0 = np.asarray(CHARGES_C), 20e-15
    known_pulse = pulse_result(charge_c=q, amplitude_v=GAIN_V_PER_C * q * (1 - q / q0))
    supply = analyze_supply([known_pulse])
    assert metrics(pulse=known_pulse, supply=supply).nonlinearity == pytest.approx(2 / 72, rel=1e-12)


# The CR-RC pulse on Spectre's 50 ps strobes, its peak midway between two of them: tau = 10.025 ns
# after the injection (60.05 ns, a strobe). The largest sample lies 25 ps from the peak. Near it
# v = A (1 + u) e^(-u), u = t/tau - 1, = A (1 - u^2/2 + u^3/3 - ...): the parabola through the
# largest sample and its neighbours misplaces the vertex by about the cubic over the quadratic term
# times h^2 / 2, (2/3) h^2 / (2 tau) = h^2 / (3 tau) = 0.08 ps, so the peaking time holds to 1 ps
# where the largest sample's time would be 25 ps off.
def test_the_peaking_time_between_the_strobes() -> None:
    tau_s, strobes = 10.025e-9, np.arange(10001) * 50e-12
    result = analyze_pulse([response_run(1e-15, crrc(0.1, tau_s), time_s=strobes)])
    assert result.peaking_time_s[0] == pytest.approx(tau_s, abs=1e-12)
    assert result.amplitude_v[0] == pytest.approx(0.1, rel=(25e-12 / tau_s) ** 2)
