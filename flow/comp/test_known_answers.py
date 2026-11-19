"""Known answers for the comparator's analyses and metrics: synthetic runs and decisions whose
answer follows on paper from how they were made, never from the code under test.

The synthetic run (``latch_run``) is a comparator as the testbench reads it: the clock low through
each reset and rising over the transition at its end; the regenerative latch's difference
``V_XY = V_XY0 exp(t / tau_reg)`` from the clock's rise, signed by the input, clipped at the supply
and placed so that it crosses half the supply a chosen delay after the clock's midpoint; the SR
output holding the decision once the latch has split (and the previous one where it has not); the
inputs at their common mode and difference with optional kicks; the supply's charge drawn evenly
over each cycle into the charge meter.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import norm

from flow.pipeline import Meas, MeasInfo, Wave

from . import runs
from .analysis import (
    analyze_clock_check,
    analyze_common_mode,
    analyze_decisions,
    analyze_delay,
    analyze_edge_eye,
    analyze_kickback,
    analyze_metastability,
    analyze_offset_noise,
    analyze_power,
    analyze_response,
    analyze_sampling_noise,
    analyze_scope_edges,
    analyze_scurve,
    analyze_timing,
    metrics,
)
from .params import (
    CHARGE_METER,
    CHARGE_METER_F,
    CHECK_CLOCK_S,
    LARGE_V,
    METASTABILITY_RUN_V,
    METASTABILITY_V,
    NOMINAL_CM,
    SCURVE_DECISIONS,
    SCURVE_V,
    SMALL_V,
    SUPPLY_SWEEP,
    Params,
    TbParams,
)
from .types import (
    AnalysisClockCheck,
    AnalysisCommonMode,
    AnalysisConversions,
    AnalysisDecisions,
    AnalysisDelay,
    AnalysisKickback,
    AnalysisMetastability,
    AnalysisOffsetNoise,
    AnalysisPower,
    AnalysisScurve,
)

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 11, 18, tzinfo=UTC))
TAU_S = 20e-12  # the synthetic latch's regeneration time constant


def kick(at_s: float, amplitude_v: float, width_s: float = 50e-12):
    """A Gaussian bump of ``amplitude_v`` peaking at ``at_s``, as a function of time."""
    return lambda t: amplitude_v * np.exp(-(((t - at_s) / width_s) ** 2))


def latch_run(
    tb: TbParams,
    delays_s,
    *,
    tau_s: float = TAU_S,
    charge_c=None,
    kick_p=None,
    kick_n=None,
    step_s: float = 1e-12,
    coarse: bool = False,
    decision=None,
) -> Meas:
    """A run of ``tb`` whose trial ``k`` splits its latch ``delays_s[k]`` after its clock's midpoint
    (``math.inf``: never), toward the sign of its input (or ``decision[k]`` where given: 1 high),
    drawing ``charge_c[k]`` from the supply over its cycle; on a time axis of ``step_s`` offset by
    half a step and a random sprinkle of points (uneven, as a simulator's steps), or, ``coarse``,
    only the points around each decision's read."""

    trials = len(tb.trial_point)
    starts = tb.trial_start_s
    rises = starts + tb.reset_time_s
    mids = rises + tb.transition_time_s / 2
    vdd = float(tb.vdd)
    if coarse:
        time_s = np.unique(
            np.concatenate(
                [
                    [0.0, tb.stop_s],
                    starts,
                    *(start + np.asarray([1e-12, tb.reset_time_s - 1e-12, tb.cycle_s - 1e-12]) for start in starts),
                    *(read + np.asarray([-1e-12, 0.0, 1e-12]) for read in tb.decision_time_s),
                ]
            )
        )
    else:
        rng = np.random.default_rng(3)
        time_s = np.unique(
            np.concatenate(
                [
                    [0.0, tb.stop_s],
                    np.arange(0.5, tb.stop_s / step_s - 0.5) * step_s,
                    rng.uniform(0.0, tb.stop_s, max(1000, trials * 200)),
                    # the breakpoints a simulator steps to: each cycle's start and the clock's midpoint
                    starts,
                    mids,
                ]
            )
        )
    time_s = time_s[(time_s >= 0.0) & (time_s <= tb.stop_s)]
    trial = np.clip(np.searchsorted(starts, time_s, side="right") - 1, 0, trials - 1)
    points = np.asarray(tb.points)
    cm, diff = points[tb.trial_point[trial], 0], points[tb.trial_point[trial], 1]
    if decision is None:
        high = np.asarray([points[point, 1] >= 0 for point in tb.trial_point])
    else:
        high = np.asarray(decision, dtype=bool)
    sign = np.where(high, 1.0, -1.0)[trial]
    delay = np.asarray(delays_s, dtype=np.float64)[trial]
    clock = vdd * np.clip((time_s - rises[trial]) / tb.transition_time_s, 0.0, 1.0)
    with np.errstate(over="ignore", invalid="ignore"):
        growth = np.where(
            np.isfinite(delay), vdd / 2 * np.exp(np.minimum((time_s - mids[trial] - delay) / tau_s, 50.0)), 0.0
        )
    split = np.where(time_s >= rises[trial], sign * np.minimum(vdd, growth), 0.0)
    # the SR output: each resolved trial's decision, an unresolved one's the previous
    read_s = tb.decision_time_s - mids
    held, state = [], False
    for index in range(trials):
        if delays_s[index] < read_s[index]:
            state = bool(high[index])
        held.append(state)
    out_high = np.asarray(held)[trial]
    v = {
        "clk": clock,
        "latch_p": vdd / 2 + split / 2,
        "latch_n": vdd / 2 - split / 2,
        "outp": np.where(out_high, vdd, 0.0),
        "outn": np.where(out_high, 0.0, vdd),
        "inp": cm + diff / 2 + (kick_p(time_s) if kick_p else 0.0),
        "inn": cm - diff / 2 + (kick_n(time_s) if kick_n else 0.0),
    }
    charges = np.zeros(trials) if charge_c is None else np.asarray(charge_c, dtype=np.float64)
    drawn = np.r_[0.0, np.cumsum(charges)]
    v[CHARGE_METER] = (drawn[trial] + charges[trial] * (time_s - starts[trial]) / tb.cycle_s) / CHARGE_METER_F
    return Meas(group=None, index=None, dut=tb.params, info=INFO, param=tb, time_s=time_s, v=v)


def decisions_of(
    vin_diff_v, decision, *, vin_cm_v: float = 0.6, resolved=None, info: MeasInfo = INFO, param=None
) -> AnalysisDecisions:
    """Trials as a capture gives them: each one's input, decision and (optionally) resolution."""
    vin_diff_v = np.asarray(vin_diff_v, dtype=np.float64)
    tb = TbParams()
    return AnalysisDecisions(
        group=None,
        index=None,
        dut=tb.params,
        info=info,
        param=tb if param is None else param,
        trial_index=np.arange(len(vin_diff_v)),
        vin_diff_v=vin_diff_v,
        vin_cm_v=np.full(len(vin_diff_v), vin_cm_v),
        decision=np.asarray(decision, dtype=np.uint8),
        resolved=None if resolved is None else np.asarray(resolved, dtype=np.bool_),
    )


def expected_curve(inputs_v, offset_v: float, sigma_v: float, trials: int, *, vin_cm_v: float = 0.6, **kw):
    """An S-curve whose every point holds the nearest whole number to its expected count of high
    decisions, P(high) = Phi((V_in - V_OS) / sigma), of ``trials`` each."""
    # [Razavi-ADC] Eq. (6.62), p. 117: the share of ZEROs is the Gaussian noise's area below -V_S
    # [Pelgrom] Practical Hint 12.1, Fig. 12.8, p. 607: the decisions' cumulative Gaussian about the trip level
    inputs_v = np.asarray(inputs_v, dtype=np.float64)
    ones = np.rint(trials * norm.cdf((inputs_v - offset_v) / sigma_v)).astype(int)
    decision = np.concatenate([np.r_[np.ones(k), np.zeros(trials - k)] for k in ones])
    return decisions_of(np.repeat(inputs_v, trials), decision, vin_cm_v=vin_cm_v, **kw)


def chain(meas: Meas):
    """A run's decisions, timing and delay."""
    decisions = analyze_decisions(meas)
    timing = analyze_timing(meas, decisions=decisions)
    return decisions, timing, analyze_delay(meas, decisions=decisions, timing=timing)


# ---------------------------------------------------------------- decisions, timing, delay


def test_decisions_read_each_trials_input_its_sign_and_whether_its_latch_split() -> None:
    """Four trials at -1, -1, +2, +2 mV: the decisions 0, 0, 1, 1; the third one's latch never splits
    (unresolved), so its output holds the second's 0."""
    tb = TbParams(vin_cm_values_v=(0.6,), vin_diff_values_v=(-1e-3, 2e-3), conversions=2)
    decisions = analyze_decisions(latch_run(tb, [150e-12, 150e-12, math.inf, 150e-12]))
    np.testing.assert_array_equal(decisions.vin_diff_v, [-1e-3, -1e-3, 2e-3, 2e-3])
    np.testing.assert_array_equal(decisions.vin_cm_v, [0.6] * 4)
    np.testing.assert_array_equal(decisions.decision, [0, 0, 0, 1])
    assert decisions.resolved is not None
    np.testing.assert_array_equal(decisions.resolved, [True, True, False, True])
    np.testing.assert_array_equal(decisions.trial_index, np.arange(4))


def test_a_latch_still_under_half_the_supply_when_read_is_unresolved() -> None:
    """A latch crossing half the supply after the read (4 ns of evaluation less two and a half
    transitions from the clock's midpoint: 3.95 ns) is unresolved; one crossing before it is not."""
    tb = TbParams(vin_diff_values_v=(1e-3,), conversions=2)
    read_s = tb.evaluation_time_s - 2.5 * tb.transition_time_s
    decisions = analyze_decisions(latch_run(tb, [read_s - 20e-12, read_s + 20e-12], tau_s=5e-12))
    assert decisions.resolved is not None
    assert decisions.resolved.tolist() == [True, False]


def test_the_delay_is_from_the_clocks_midpoint_to_the_latch_at_half_its_swing() -> None:
    """The latch crosses half the supply ``d`` after the clock's midpoint: the clock-to-decision
    delay is ``d`` for each trial."""
    tb = TbParams(vin_diff_values_v=(-1e-3, 0.5e-3, 2e-3), conversions=1)
    delays = [120e-12, 250e-12, 333e-12]
    _, timing, _ = chain(latch_run(tb, delays))
    np.testing.assert_allclose(timing.clock_to_decision_s, delays, atol=0.05e-12)
    assert not timing.unresolved.any()


def test_the_settling_is_to_one_percent_of_the_latchs_final_step() -> None:
    """V_XY = (V_DD / 2) exp((t - d) / tau) from the clock's midpoint, clipped at V_DD: it is within
    1 % of V_DD from t = d + tau ln(2 x 0.99) on (its start, (V_DD / 2) exp(-d / tau), is 1e-5 of
    V_DD or less; the axis fine enough, 0.05 ps, that the clip's kink moves no crossing further)."""
    tb = TbParams(vin_diff_values_v=(1e-3,), conversions=2)
    delays = [250e-12, 400e-12]
    _, timing, _ = chain(latch_run(tb, delays, tau_s=20e-12, step_s=0.05e-12))
    np.testing.assert_allclose(timing.settling_s, np.asarray(delays) + 20e-12 * math.log(1.98), atol=0.1e-12)


def test_an_unresolved_trial_has_no_delay_and_is_left_out_of_the_median() -> None:
    """Three trials at one input of delays 100, 300 and 200 ps: the median 200 ps; with the 300 ps
    one never splitting, the median of 100 and 200 ps, 150 ps; a point with no resolved trial NaN."""
    tb = TbParams(vin_diff_values_v=(1e-3,), conversions=3)
    _, _, delay = chain(latch_run(tb, [100e-12, 300e-12, 200e-12]))
    assert delay.delay_s.shape == (1, 1)
    assert delay.delay_s[0, 0] == pytest.approx(200e-12, abs=0.05e-12)
    _, timing, delay = chain(latch_run(tb, [100e-12, math.inf, 200e-12]))
    assert timing.unresolved.tolist() == [False, True, False]
    assert math.isnan(timing.clock_to_decision_s[1])
    assert delay.delay_s[0, 0] == pytest.approx(150e-12, abs=0.05e-12)
    two = TbParams(vin_diff_values_v=(-1e-3, 1e-3), conversions=1)
    _, _, delay = chain(latch_run(two, [math.inf, 200e-12]))
    np.testing.assert_array_equal(delay.vin_diff_v, [-1e-3, 1e-3])
    assert math.isnan(delay.delay_s[0, 0]) and delay.delay_s[0, 1] == pytest.approx(200e-12, abs=0.05e-12)


def test_the_delay_is_a_row_a_common_mode_and_a_column_an_input_both_ascending() -> None:
    """Two common modes by two inputs, each point's delay its own: rows by common mode, columns by
    input, each ascending."""
    tb = TbParams(vin_cm_values_v=(0.7, 0.5), vin_diff_values_v=(2e-3, -1e-3), conversions=1)
    # the points in order: (0.7, +2), (0.7, -1), (0.5, +2), (0.5, -1) mV
    _, _, delay = chain(latch_run(tb, [100e-12, 200e-12, 300e-12, 400e-12]))
    np.testing.assert_array_equal(delay.vin_cm_v, [0.5, 0.7])
    np.testing.assert_array_equal(delay.vin_diff_v, [-1e-3, 2e-3])
    np.testing.assert_allclose(delay.delay_s, [[400e-12, 300e-12], [200e-12, 100e-12]], atol=0.05e-12)


# ---------------------------------------------------------------- regeneration, clock check


def metastability_law(t0_s: float, tau_s: float, reference_v: float = 0.1):
    """The delay of a latch whose initial imbalance is proportional to its input: halving the input
    adds tau ln 2 ([Razavi-ADC] Eq. (6.43), p. 111: V_XY = V_XY0 exp(t / tau_reg))."""
    return lambda v: t0_s + tau_s * math.log(reference_v / abs(v))


def metastability_run(law, *, check: bool = False, tau_s: float = TAU_S) -> Meas:
    tb = TbParams(vin_diff_values_v=METASTABILITY_RUN_V)
    if check:
        tb = replace(tb, reset_time_s=CHECK_CLOCK_S[0], evaluation_time_s=CHECK_CLOCK_S[1])
    return latch_run(tb, [law(tb.points[point][1]) for point in tb.trial_point], tau_s=tau_s)


def test_the_regeneration_time_constant_is_the_delays_growth_per_e_fold_fall_of_the_input() -> None:
    """d(V) = t_0 + tau ln(0.1 V / V): tau_reg = 25 ps, and the delay at each positive input its law,
    smallest first."""
    law = metastability_law(80e-12, 25e-12)
    meas = metastability_run(law)
    metastability = analyze_metastability(meas, delay=chain(meas)[2])
    np.testing.assert_allclose(metastability.input_v, METASTABILITY_V)
    np.testing.assert_allclose(metastability.delay_s, [law(v) for v in METASTABILITY_V], atol=0.05e-12)
    assert metastability.regeneration_tau_s == pytest.approx(25e-12, rel=1e-3)


def test_the_regeneration_time_constant_is_the_latchs_whatever_its_offset() -> None:
    """A latch of tau_reg 25 ps with a systematic offset of 50 uV (the readme's offsets reach
    0.2 mV): each decision's imbalance is proportional to V_in - V_OS, so its delay is t_0 + tau
    ln(0.1 V / |V_in - V_OS|) and its decision the sign of V_in - V_OS. tau_reg is the latch's 25 ps,
    within a tenth (the two smallest inputs alone read 25 ps ln(250 / 50) / ln 3 = 36.6 ps)."""
    offset_v = 50e-6
    law = metastability_law(80e-12, 25e-12)
    tb = TbParams(vin_diff_values_v=METASTABILITY_RUN_V)
    inputs = [tb.points[point][1] for point in tb.trial_point]
    meas = latch_run(tb, [law(v - offset_v) for v in inputs], decision=[v > offset_v for v in inputs])
    metastability = analyze_metastability(meas, delay=chain(meas)[2])
    assert metastability.regeneration_tau_s == pytest.approx(25e-12, rel=0.1)


def clock_check(at_law, longer_law, *, tau_s: float = TAU_S) -> AnalysisClockCheck:
    results = []
    for law, check in ((at_law, False), (longer_law, True)):
        meas = metastability_run(law, check=check, tau_s=tau_s)
        decisions, _, delay = chain(meas)
        results.append((meas, decisions, analyze_metastability(meas, delay=delay)))
    meas, decisions, metastability = zip(*results, strict=True)
    return analyze_clock_check(list(meas), decisions=list(decisions), metastability=list(metastability))


def test_the_clock_check_passes_a_comparator_the_longer_clock_leaves_alone() -> None:
    """The same delays at 4 ns and 8 ns of evaluation: every decision resolved and alike, the delays
    unchanged, 10 uV decided t_0 + tau ln(0.1 V / 10 uV) = 80 ps + 25 ps ln(1e4) = 310.3 ps after the
    clock: within the clock."""
    law = metastability_law(80e-12, 25e-12)
    check = clock_check(law, law)
    assert check.evaluation_s == pytest.approx(4e-9)
    assert check.unresolved_count == 0 and check.decisions_match
    assert check.delay_change == pytest.approx(0.0, abs=1e-3)
    assert check.resolved_10uv_s == pytest.approx(80e-12 + 25e-12 * math.log(1e4), rel=1e-3)
    assert check.decides_in_time and check.reasons == ()


def test_the_clock_check_fails_a_comparator_too_slow_for_10_uv() -> None:
    """tau 200 ps and t_0 2.318 ns: 0.1 mV decided at 3.70 ns, within the read at 3.95 ns, but 10 uV
    extrapolated to 3.70 ns + 200 ps ln(10) = 4.16 ns, past the 4 ns evaluation."""
    law = metastability_law(3.7e-9 - 200e-12 * math.log(1000), 200e-12)
    check = clock_check(law, law, tau_s=60e-12)
    assert check.unresolved_count == 0 and check.decisions_match
    assert check.resolved_10uv_s == pytest.approx(3.7e-9 + 200e-12 * math.log(10), rel=1e-3)
    assert not check.decides_in_time
    assert len(check.reasons) == 1 and check.reasons[0].startswith("10 uV")


def test_the_clock_check_fails_delays_the_longer_clock_changes_by_more_than_a_tenth() -> None:
    """Delays at the clock 1.25 times the longer clock's: a change of 25 %, past the 10 % allowed."""
    law = metastability_law(80e-12, 25e-12)
    check = clock_check(lambda v: 1.25 * law(v), law)
    assert check.delay_change == pytest.approx(0.25, rel=1e-3)
    assert not check.decides_in_time and any("25%" in reason for reason in check.reasons)


# ---------------------------------------------------------------- kickback, power


def test_the_kickback_is_each_inputs_largest_excursion_in_the_first_cycle() -> None:
    """inp kicked up 5 mV and inn down 2 mV in the first decision, 15 mV in the second: each input's
    largest excursion 5 mV, their difference's 7 mV; the second cycle's left out."""
    tb = TbParams(vin_diff_values_v=(SMALL_V,), conversions=2)
    first, second = tb.reset_time_s + 100e-12, tb.cycle_s + tb.reset_time_s + 100e-12
    meas = latch_run(
        tb,
        [200e-12, 200e-12],
        kick_p=lambda t: kick(first, 5e-3)(t) + kick(second, 15e-3)(t),
        kick_n=kick(first, -2e-3),
    )
    kickback = analyze_kickback(meas)
    assert kickback.kickback_v == pytest.approx(5e-3, rel=1e-3)
    assert kickback.kickback_diff_v == pytest.approx(7e-3, rel=1e-3)


def test_a_common_mode_kick_moves_each_input_but_not_their_difference() -> None:
    tb = TbParams(vin_diff_values_v=(SMALL_V,))
    at_s = tb.reset_time_s + 100e-12
    kickback = analyze_kickback(latch_run(tb, [200e-12], kick_p=kick(at_s, 4e-3), kick_n=kick(at_s, 4e-3)))
    assert kickback.kickback_v == pytest.approx(4e-3, rel=1e-3)
    assert kickback.kickback_diff_v == pytest.approx(0.0, abs=1e-9)


def test_the_energy_per_decision_is_the_supplys_charge_over_a_settled_cycle_times_its_voltage() -> None:
    """Three decisions at one input drawing 30, 10 and 10 fC at 1.2 V: the first (from the operating
    point) left out, 1.2 V x 10 fC = 12 fJ a decision, 12 fJ / 5 ns = 2.4 uW. Two inputs of two
    decisions each drawing 30, 10, 50 and 20 fC at 1.0 V: the second and fourth follow one at their
    input, 1.0 V x 15 fC = 15 fJ ([Baker] Eq. (11.15), p. 355: the energy a cycle is the average
    power over the clock frequency)."""
    one = TbParams(vin_diff_values_v=(1e-3,), conversions=3, vdd=1.2)
    two = TbParams(vin_diff_values_v=(0.5e-3, 100e-3), conversions=2, vdd=1.0)
    power = analyze_power(
        [
            latch_run(one, [200e-12] * 3, charge_c=[30e-15, 10e-15, 10e-15]),
            latch_run(two, [200e-12] * 4, charge_c=[30e-15, 10e-15, 50e-15, 20e-15]),
        ]
    )
    np.testing.assert_allclose(power.supply_v, [1.2, 1.0])
    np.testing.assert_allclose(power.energy_per_decision_j, [12e-15, 15e-15], rtol=1e-9)
    np.testing.assert_allclose(power.average_power_w, [12e-15 / 5e-9, 15e-15 / 5e-9], rtol=1e-9)


def test_a_run_whose_every_decision_follows_another_input_has_no_settled_energy() -> None:
    tb = TbParams(vin_diff_values_v=(0.5e-3, 100e-3), conversions=1)
    power = analyze_power([latch_run(tb, [200e-12] * 2, charge_c=[10e-15, 10e-15])])
    assert math.isnan(power.energy_per_decision_j[0])


# ---------------------------------------------------------------- S-curves, offset, noise


def test_the_scurve_is_each_inputs_share_of_high_resolved_decisions() -> None:
    """At -1 mV: 1 of 4 resolved high, 1 unresolved of 5; at +1 mV: 3 of 3 high; at 0: none
    resolved (NaN), all unresolved; over all: 1 + 2 of 10 unresolved."""
    decisions = decisions_of(
        [-1e-3] * 5 + [1e-3] * 3 + [0.0] * 2,
        [0, 1, 0, 0, 1, 1, 1, 1, 0, 1],
        resolved=[True, True, True, True, False, True, True, True, False, False],
    )
    scurve = analyze_scurve([decisions])
    np.testing.assert_array_equal(scurve.vin_diff_v, [-1e-3, 0.0, 1e-3])
    np.testing.assert_allclose(scurve.probability, [0.25, math.nan, 1.0])
    np.testing.assert_allclose(scurve.unresolved_fraction, [0.2, 1.0, 0.0])
    assert scurve.total_unresolved_fraction == pytest.approx(0.3)


def test_the_offset_and_noise_are_the_generating_gaussians() -> None:
    """Every point of 33 from -2.5 to 2.5 mV holding its expected count of 100,000 decisions of a
    Gaussian of offset 0.2 mV and sigma 0.5 mV: the fit returns both (the counts' rounding moves
    them by under 1e-4 of sigma)."""
    fit = analyze_offset_noise([expected_curve(np.linspace(-2.5e-3, 2.5e-3, 33), 0.2e-3, 0.5e-3, 100_000)])
    assert fit.validity == "valid" and fit.decision_polarity == 1
    assert fit.offset_v == pytest.approx(0.2e-3, abs=1e-3 * 0.5e-3)
    assert fit.noise_sigma_v == pytest.approx(0.5e-3, rel=1e-3)
    assert fit.vin_cm_v == pytest.approx(0.6)
    np.testing.assert_array_equal(fit.trial_count, [100_000] * 33)


def test_a_comparator_deciding_low_for_a_positive_input_has_the_same_offset_and_noise() -> None:
    """The same curve with every decision inverted: decision polarity -1, the same offset and noise."""
    curve = expected_curve(np.linspace(-2.5e-3, 2.5e-3, 33), -0.3e-3, 0.4e-3, 100_000)
    fit = analyze_offset_noise([replace(curve, decision=1 - curve.decision)])
    assert fit.validity == "valid" and fit.decision_polarity == -1
    assert fit.offset_v == pytest.approx(-0.3e-3, abs=1e-3 * 0.4e-3)
    assert fit.noise_sigma_v == pytest.approx(0.4e-3, rel=1e-3)


def test_the_noise_is_the_input_at_which_a_sixth_of_the_decisions_go_wrong() -> None:
    """Four points at -3, -1, +1 and +3 sigma: at +1 sigma Phi(-1) = 15.87 % of the decisions low
    ([Razavi-ADC] Eq. (6.62), p. 117), at -1 sigma as many high, at +-3 sigma 0.13 %: the fit
    gives that sigma and an offset of 0."""
    sigma = 0.3e-3
    fit = analyze_offset_noise([expected_curve(np.asarray([-3, -1, 1, 3]) * sigma, 0.0, sigma, 1_000_000)])
    assert fit.validity == "valid"
    assert fit.offset_v == pytest.approx(0.0, abs=1e-3 * sigma)
    assert fit.noise_sigma_v == pytest.approx(sigma, rel=1e-3)


def test_an_scurve_the_grid_cannot_resolve_is_not_called_valid() -> None:
    """A 50 uV comparator with 1 mV of offset on the characterization's S-curve (``SCURVE_V``, its
    expected counts of ``SCURVE_DECISIONS``): its points at 0.5, 1 and 2 mV read 0, 1/2 and 1, the
    transition between them unresolved (one point inside it). Its noise is either read within a
    quarter of 50 uV or the fit is not valid; the crossings' interpolation alone would read
    (1.68 - 0.66) mV / 2 = 0.51 mV."""
    fit = analyze_offset_noise([expected_curve(SCURVE_V, 1e-3, 50e-6, SCURVE_DECISIONS)])
    assert fit.validity != "valid" or fit.noise_sigma_v == pytest.approx(50e-6, rel=0.25)


def test_too_many_unresolved_decisions_leave_the_curve_unresolved() -> None:
    """2 % of the trials unresolved (past the 1 % allowed): the curve is ``unresolved``, its offset
    and noise NaN; 0.5 % unresolved are left out and the curve fitted."""
    curve = expected_curve(np.linspace(-2e-3, 2e-3, 21), 0.0, 0.5e-3, 1000)
    resolved = np.ones(len(curve.decision), dtype=bool)
    resolved[::50] = False  # 2 %
    slow = analyze_offset_noise([replace(curve, resolved=resolved)])
    assert slow.validity == "unresolved" and math.isnan(slow.offset_v) and math.isnan(slow.noise_sigma_v)
    resolved = np.ones(len(curve.decision), dtype=bool)
    resolved[::200] = False  # 0.5 %
    few = analyze_offset_noise([replace(curve, resolved=resolved)])
    assert few.validity == "valid"
    assert few.noise_sigma_v == pytest.approx(0.5e-3, rel=0.05)


def test_the_common_mode_analysis_fits_each_common_mode_on_its_own() -> None:
    """Three common modes, each with its own Gaussian: their offsets and noises in ascending common
    mode, each curve a row."""
    truths = {0.5: (-0.1e-3, 0.4e-3), 0.6: (0.0, 0.5e-3), 0.7: (0.3e-3, 0.6e-3)}
    inputs = np.linspace(-3e-3, 3e-3, 25)
    curves = [expected_curve(inputs, *truths[cm], 20_000, vin_cm_v=cm) for cm in (0.7, 0.5, 0.6)]
    result = analyze_common_mode(curves)
    np.testing.assert_allclose(result.vin_cm_v, [0.5, 0.6, 0.7])
    assert result.validity == ("valid", "valid", "valid")
    np.testing.assert_allclose(result.offset_v, [truths[cm][0] for cm in (0.5, 0.6, 0.7)], atol=1e-3 * 0.4e-3)
    np.testing.assert_allclose(result.noise_sigma_v, [truths[cm][1] for cm in (0.5, 0.6, 0.7)], rtol=1e-3)
    assert result.vin_diff_v.shape == (3, 25) and result.trial_count.tolist() == [[20_000] * 25] * 3


def test_a_pinned_curve_whose_neighbours_transition_lies_in_its_range_is_stuck() -> None:
    """A curve pinned at 0.95 to 1 over -2 to 2 mV, beside a valid one whose offset (0) lies in that
    range: ``stuck-high``."""
    inputs = np.linspace(-2e-3, 2e-3, 5)
    valid = expected_curve(inputs, 0.0, 0.5e-3, 1000, vin_cm_v=0.6)
    stuck = decisions_of(
        np.repeat(inputs, 100),
        np.concatenate([np.r_[np.ones(ones), np.zeros(100 - ones)] for ones in (95, 96, 98, 100, 100)]),
        vin_cm_v=0.8,
    )
    assert analyze_common_mode([valid, stuck]).validity == ("valid", "stuck-high")


def test_the_sampling_noise_fits_each_coupling_and_mode_its_newest_run_replacing_the_rest() -> None:
    """Two curves (40 % track, 60 % hold) of one run, and 40 % track again in a later run with
    another offset: the 40 % track curve's offset is the later run's."""

    def curve(coupling: float, mode: str, offset_v: float, run: str) -> AnalysisDecisions:
        param = SimpleNamespace(requested_dac_rail_percent=coupling, sampling_mode=mode, tb=TbParams())
        info = replace(INFO, source_path=Path("/captures") / run / "point.h5")
        return expected_curve(np.linspace(-3e-3, 3e-3, 25), offset_v, 0.5e-3, 10_000, info=info, param=param)

    result = analyze_sampling_noise(
        [
            curve(40.0, "track", 0.5e-3, "run_a"),
            curve(60.0, "hold", -0.2e-3, "run_a"),
            curve(40.0, "track", 0.1e-3, "run_b"),
        ]
    )
    assert result.coupling_percent.tolist() == [40.0, 60.0]
    assert result.sampling_mode == ("track", "hold")
    np.testing.assert_allclose(result.offset_v, [0.1e-3, -0.2e-3], atol=0.01 * 0.5e-3)
    np.testing.assert_allclose(result.noise_sigma_v, [0.5e-3, 0.5e-3], rtol=0.01)
    assert result.validity == ("valid", "valid")


# ---------------------------------------------------------------- a converter's captures


PERIOD_S = 10e-9  # the decisions' spacing
HIGH_S = 4e-9  # the clock high, midpoint to midpoint
EDGE_S = 0.2e-9  # each edge's ramp


def pulses(time_s: np.ndarray, rises_s, width_s: float, low: float, high: float) -> np.ndarray:
    """A level ``low`` with a pulse to ``high`` at each rise (ramps of ``EDGE_S``), ``width_s`` from
    the rise's midpoint to the fall's."""
    level = np.zeros_like(time_s)
    for rise in rises_s:
        level += np.clip((time_s - rise) / EDGE_S, 0, 1) - np.clip((time_s - rise - width_s) / EDGE_S, 0, 1)
    return low + (high - low) * level


def toggles(time_s: np.ndarray, at_s, states, low: float, high: float, initial: bool = False) -> np.ndarray:
    """A logic level ``initial`` then each of ``states`` from each of ``at_s`` (ramps of ``EDGE_S``)."""
    level = np.full_like(time_s, float(initial))
    previous = float(initial)
    for at, state in zip(at_s, states, strict=True):
        level += (float(state) - previous) * np.clip((time_s - at) / EDGE_S, 0, 1)
        previous = float(state)
    return low + (high - low) * level


def conversions_of(wave: Wave, decisions: int, *, vdd_a: float = 1.2, vdd_d: float = 1.2) -> AnalysisConversions:
    return AnalysisConversions(
        group=None,
        index=None,
        dut=Params(),
        wave=wave,
        sequence=("1", "0", "1", "0"),
        symbol_rate_hz=1e9,
        decisions=decisions,
        decision_period_s=PERIOD_S,
        conversion_rate_hz=1e9 / 50,
        vdd_a_v=vdd_a,
        vdd_d_v=vdd_d,
    )


JITTER_S = (0.0, 0.3e-9, -0.2e-9, 0.5e-9)
SCOPE_DELAY_S = 2.5e-9


def scope_wave(shifts_s=(0.0, 1.0e-9, 2.5e-9), jitter_s=JITTER_S, delay_s: float = SCOPE_DELAY_S) -> Wave:
    """Scope records of one conversion each, shifted by ``shifts_s``: COMP rising at ``5 ns + k P +
    j_k``, high ``HIGH_S``; COMP_OUT toggling ``delay_s`` after each rise but at the third decision,
    which holds."""
    time_s = np.arange(-5e-9, 60e-9, 0.01e-9)
    comp, out = [], []
    for shift in shifts_s:
        rises = 5e-9 + shift + np.arange(len(jitter_s)) * PERIOD_S + np.asarray(jitter_s)
        comp.append(pulses(time_s, rises, HIGH_S, 0.0, 1.2))
        out.append(toggles(time_s, rises + delay_s, (True, False, False, True), 0.0, 1.0))
    return Wave(
        record_index=np.zeros(len(shifts_s), dtype=int),
        time_s=time_s,
        v={"seq_comp": np.asarray(comp), "comp_out": np.asarray(out)},
    )


def test_the_scope_edges_time_each_decision_from_its_comp_rise() -> None:
    """Every rise's COMP_OUT 2.5 ns after it (midpoint to midpoint) but the third's, which holds; each
    rise's distance from B0's plus k periods the jitter put there; COMP high 4 ns; the rises and
    falls k P + j_k and k P + j_k + 4 ns after B0's."""
    edges = analyze_scope_edges([conversions_of(scope_wave(), 4)])
    assert edges.records == 3 and edges.decision_count == 4
    finite = np.delete(edges.delays_s, 2, axis=1)
    np.testing.assert_allclose(finite, SCOPE_DELAY_S, atol=1e-12)
    assert np.all(np.isnan(edges.delays_s[:, 2]))
    assert edges.unchanged.tolist() == [0, 0, 3, 0]
    assert edges.multiple.tolist() == [0, 0, 0, 0] and edges.unsettled.tolist() == [0, 0, 0, 0]
    np.testing.assert_allclose(edges.jitter_s, np.tile(JITTER_S, (3, 1)), atol=1e-12)
    assert edges.clock_high_s == pytest.approx(HIGH_S, abs=1e-12)
    np.testing.assert_allclose(edges.rise_s, np.arange(4) * PERIOD_S + np.asarray(JITTER_S), atol=1e-12)
    np.testing.assert_allclose(edges.fall_s, np.arange(4) * PERIOD_S + np.asarray(JITTER_S) + HIGH_S, atol=1e-12)
    np.testing.assert_allclose(
        edges.clock_edges_s[:, 0], 5e-9 + EDGE_S / 2 + np.asarray([0.0, 1.0e-9, 2.5e-9]), atol=1e-12
    )
    np.testing.assert_allclose(edges.response_median_s, [SCOPE_DELAY_S, SCOPE_DELAY_S, math.nan, SCOPE_DELAY_S])
    assert edges.decision_period_s == PERIOD_S and edges.conversion_rate_hz == pytest.approx(2e7)
    assert edges.delay_bounds_s == pytest.approx((SCOPE_DELAY_S, SCOPE_DELAY_S), abs=1e-12)


def test_a_comp_out_that_crosses_twice_in_a_decision_is_counted_multiple() -> None:
    wave = scope_wave(shifts_s=(0.0,))
    out = wave.v["comp_out"].copy()
    time_s = wave.time_s
    # a glitch in the second decision: down to 0 and back to 1 before its own transition
    glitch = (time_s >= 15.5e-9) & (time_s < 16.0e-9)
    out[0, glitch] = 0.0
    edges = analyze_scope_edges([conversions_of(replace(wave, v={**wave.v, "comp_out": out}), 4)])
    assert edges.multiple.tolist() == [0, 1, 0, 0]
    assert math.isnan(edges.delays_s[0, 1])


def converter_wave(
    latch_s=(1.0e-9, 1.5e-9, 0.7e-9), sr_s=(1.8e-9, 2.6e-9, 1.2e-9), targets=(True, False, False), conversions: int = 1
) -> Wave:
    """A simulated conversion of three decisions (the clock's ramp starting at 2 ns + k P, high
    ``HIGH_S``): both XC nodes precharged to the supply through each reset, the loser of decision k
    (N where its target is high) at mid-supply ``latch_s[k]`` after the clock's midpoint and below
    it until the reset; the SR output at mid-supply ``sr_s[k]`` after the clock's midpoint on its way
    to each target (held where it already holds it)."""
    time_s = np.arange(0.0, 40e-9, 0.002e-9)
    rises = 2e-9 + np.arange(3) * PERIOD_S
    clock = pulses(time_s, rises, HIGH_S, 0.0, 1.2)
    latch_p, latch_n = np.full_like(time_s, 1.2), np.full_like(time_s, 1.2)
    for rise, at_s, target in zip(rises, latch_s, targets, strict=True):
        # the loser ramps from the supply to 0 over EDGE_S, mid-supply at_s after the clock's midpoint
        fall = np.clip((time_s - (rise + at_s)) / EDGE_S, 0, 1)
        evaluating = (time_s >= rise) & (time_s < rise + HIGH_S + EDGE_S / 2)
        loser = latch_n if target else latch_p
        loser[evaluating] = 1.2 * (1 - fall[evaluating])
    sr = toggles(time_s, rises + np.asarray(sr_s), targets, 0.0, 1.2)
    v = {
        "seq_init": np.full_like(time_s, 1.2),
        "seq_logic": np.zeros_like(time_s),
        "clk_comp": clock,
        "comp.latch_p": latch_p,
        "comp.latch_n": latch_n,
        "comp_out_p": sr,
    }
    return Wave(
        record_index=np.arange(conversions),
        time_s=time_s,
        v={name: np.tile(values, (conversions, 1)) for name, values in v.items()},
    )


def test_the_response_times_the_xc_latch_and_the_sr_output_from_each_clock_rise() -> None:
    """The XC latch valid (its loser past mid-supply) 1.0, 1.5 and 0.7 ns after each clock's
    midpoint; the SR output at mid-supply 1.8 and 2.6 ns after, the third decision's already held
    (low after the second's); each to the sample (2 ps)."""
    response = analyze_response(conversions_of(converter_wave(), 3))
    np.testing.assert_array_equal(response.decision_index, [0, 1, 2])
    np.testing.assert_allclose(response.internal_response_s, [1.0e-9, 1.5e-9, 0.7e-9], atol=2.5e-12)
    np.testing.assert_allclose(response.sr_response_s, [1.8e-9, 2.6e-9, math.nan], atol=2.5e-12)
    assert response.sr_held.tolist() == [False, False, True]
    np.testing.assert_allclose(response.xc_median_s, response.internal_response_s, equal_nan=True)
    np.testing.assert_allclose(response.sr_median_s, response.sr_response_s, equal_nan=True)
    assert response.sample_interval_s == pytest.approx(0.002e-9, rel=1e-6)


def test_the_edge_eye_finds_the_clocks_rises_falls_and_the_supplys_range() -> None:
    """Rises at 0, P and 2P after B0's, the clock high 4 ns (midpoint to midpoint); the maps over
    -0.1 to 1.1 of the larger supply (the analog one's 1.3 V), the eye -0.1 to 1.1 periods."""
    eye = analyze_edge_eye(conversions_of(converter_wave(conversions=2), 3, vdd_a=1.3, vdd_d=1.2))
    assert eye.records == 2 and eye.supply_v == pytest.approx(1.3)
    assert eye.decision_period_s == pytest.approx(PERIOD_S, abs=1e-12)
    np.testing.assert_allclose(eye.decision_edge_s, np.arange(3) * PERIOD_S, atol=1e-12)
    assert eye.clock_high_s == pytest.approx(HIGH_S, abs=1e-11)
    np.testing.assert_allclose(eye.fall_s, np.arange(3) * PERIOD_S + HIGH_S, atol=1e-11)
    assert eye.voltage_v[0] == pytest.approx(-0.13) and eye.voltage_v[-1] == pytest.approx(1.43)
    assert eye.eye_time_s[0] == pytest.approx(-0.1 * PERIOD_S) and eye.eye_time_s[-1] == pytest.approx(1.1 * PERIOD_S)


def test_a_constant_xc_difference_fills_one_voltage_cell_of_the_eye() -> None:
    """|P - N| held at 0.5 V everywhere: every time cell of the XC eye holds all of its decisions in
    the one voltage cell containing 0.5 V."""
    wave = converter_wave()
    v = {
        **wave.v,
        "comp.latch_p": np.full_like(wave.v["comp.latch_p"], 0.9),
        "comp.latch_n": np.full_like(wave.v["comp.latch_n"], 0.4),
    }
    eye = analyze_edge_eye(conversions_of(replace(wave, v=v), 3))
    cell = int(np.searchsorted(eye.voltage_v, 0.5, side="right") - 1)
    np.testing.assert_allclose(eye.xc_eye[cell], 1.0)
    assert np.all(np.isnan(np.delete(eye.xc_eye, cell, axis=0)))


# ---------------------------------------------------------------- metrics


def delay_of(values) -> AnalysisDelay:
    values = np.atleast_2d(np.asarray(values, dtype=np.float64))
    return AnalysisDelay(
        group=None,
        index=None,
        dut=Params(),
        vin_cm_v=np.asarray([0.65]),
        vin_diff_v=np.asarray([SMALL_V, LARGE_V][: values.shape[1]]),
        delay_s=values,
    )


def metric_inputs(**changes):
    inputs = {
        "small": delay_of([[300e-12]]),
        "large": delay_of([[90e-12]]),
        "metastability": AnalysisMetastability(
            group=None,
            index=None,
            dut=Params(),
            input_v=np.asarray([0.1e-3, 0.3e-3]),
            delay_s=np.asarray([400e-12, 370e-12]),
            regeneration_tau_s=27e-12,
        ),
        "power": AnalysisPower(
            group=None,
            index=None,
            dut=Params(),
            supply_v=np.asarray([1.2, 1.2]),
            average_power_w=np.asarray([1e-4, 2e-4]),
            energy_per_decision_j=np.asarray([0.5e-12, 1.0e-12]),
        ),
        "kickback": AnalysisKickback(group=None, index=None, dut=Params(), kickback_v=3e-3, kickback_diff_v=1e-3),
        "supply": [delay_of([[350e-12, 95e-12]]), delay_of([[300e-12, 90e-12]]), delay_of([[280e-12, 85e-12]])],
    }
    inputs.update(changes)
    return inputs


def offset_noise_of(validity: str, offset_v: float = 0.1e-3, sigma_v: float = 0.4e-3, cm: float = 0.65):
    return AnalysisOffsetNoise(
        group=None,
        index=None,
        dut=Params(),
        vin_cm_v=cm,
        vin_diff_v=np.asarray([-1e-3, 0.0, 1e-3]),
        decision_probability=np.asarray([0.0, 0.5, 1.0]),
        trial_count=np.asarray([10, 10, 10]),
        offset_v=offset_v,
        noise_sigma_v=sigma_v,
        decision_polarity=1,
        validity=validity,
    )


def common_mode_of(noises, validity) -> AnalysisCommonMode:
    count = len(noises)
    return AnalysisCommonMode(
        group=None,
        index=None,
        dut=Params(),
        vin_cm_v=np.linspace(0.45, 0.75, count),
        offset_v=np.zeros(count),
        noise_sigma_v=np.asarray(noises),
        decision_polarity=np.ones(count, dtype=int),
        validity=tuple(validity),
        vin_diff_v=np.zeros((count, 3)),
        decision_probability=np.zeros((count, 3)),
        trial_count=np.zeros((count, 3), dtype=int),
    )


def test_the_screen_metrics_are_their_analyses_numbers() -> None:
    """The delays at 0.5 and 100 mV, the 0.1 mV delay (the smallest input's) and tau_reg, each run's
    energy (the small run's first), the kickback, the slowest 0.5 mV delay over the supply (350 ps);
    nothing of the S-curves (None)."""
    values = metrics(**metric_inputs())
    assert values.delay_0p5mv_s == pytest.approx(300e-12)
    assert values.delay_100mv_s == pytest.approx(90e-12)
    assert values.delay_0p1mv_s == pytest.approx(400e-12)
    assert values.regeneration_tau_s == pytest.approx(27e-12)
    assert values.energy_0p5mv_j == pytest.approx(0.5e-12) and values.energy_100mv_j == pytest.approx(1.0e-12)
    assert values.kickback_v == pytest.approx(3e-3) and values.kickback_diff_v == pytest.approx(1e-3)
    assert values.delay_max_supply_s == pytest.approx(350e-12)
    assert values.decides_in_time is None
    assert values.noise_v is None and values.offset_v is None
    assert values.unresolved_fraction is None and values.noise_max_v is None


def test_a_supply_corner_that_did_not_resolve_makes_the_slowest_delay_nan() -> None:
    supply = [delay_of([[350e-12, 95e-12]]), delay_of([[math.nan, 90e-12]]), delay_of([[280e-12, 85e-12]])]
    assert math.isnan(metrics(**metric_inputs(supply=supply)).delay_max_supply_s)


def test_the_noise_and_offset_are_the_nominal_fits_where_valid_and_nan_where_not() -> None:
    scurve = AnalysisScurve(
        group=None,
        index=None,
        dut=Params(),
        vin_diff_v=np.zeros(3),
        probability=np.zeros(3),
        unresolved_fraction=np.zeros(3),
        total_unresolved_fraction=0.02,
    )
    valid = metrics(**metric_inputs(), nominal=offset_noise_of("valid"), scurve=scurve)
    assert valid.noise_v == pytest.approx(0.4e-3) and valid.offset_v == pytest.approx(0.1e-3)
    assert valid.unresolved_fraction == pytest.approx(0.02)
    invalid = metrics(**metric_inputs(), nominal=offset_noise_of("unbracketed"), scurve=scurve)
    assert math.isnan(invalid.noise_v) and math.isnan(invalid.offset_v)


def test_the_largest_noise_is_over_the_valid_common_modes_only_and_needs_more_than_one() -> None:
    """Noises 0.3, 0.9 (not valid) and 0.5 mV: the largest valid 0.5 mV; one common mode alone, None;
    none valid, NaN."""
    many = metrics(
        **metric_inputs(), common_mode=common_mode_of([0.3e-3, 0.9e-3, 0.5e-3], ["valid", "unresolved", "valid"])
    )
    assert many.noise_max_v == pytest.approx(0.5e-3)
    assert metrics(**metric_inputs(), common_mode=common_mode_of([0.3e-3], ["valid"])).noise_max_v is None
    none = metrics(**metric_inputs(), common_mode=common_mode_of([0.3e-3, 0.4e-3], ["unbracketed", "non_monotonic"]))
    assert math.isnan(none.noise_max_v)


def test_the_small_and_large_delays_are_the_slowest_of_their_decisions() -> None:
    """``Metrics.delay_0p5mv_s`` is "Delay at 0.5 mV, the slowest of its decisions" (and
    ``delay_100mv_s`` likewise): three decisions at 0.5 mV of 300 (the first, from the operating
    point), 200 and 210 ps give 300 ps; at 100 mV 120, 80 and 85 ps give 120 ps."""
    small = TbParams(vin_diff_values_v=(SMALL_V,), conversions=3)
    large = TbParams(vin_diff_values_v=(LARGE_V,), conversions=3)
    small_meas, large_meas = latch_run(small, [300e-12, 200e-12, 210e-12]), latch_run(large, [120e-12, 80e-12, 85e-12])
    values = metrics(**metric_inputs(small=chain(small_meas)[2], large=chain(large_meas)[2]))
    assert values.delay_0p5mv_s == pytest.approx(300e-12, abs=0.1e-12)
    assert values.delay_100mv_s == pytest.approx(120e-12, abs=0.1e-12)


# ---------------------------------------------------------------- the record


def scurve_run(tb: TbParams, offset_v: float, sigma_v: float) -> Meas:
    """The nominal S-curve's run: at each point the nearest whole number to its expected count of
    high decisions (P(high) = Phi((V - V_OS) / sigma)), the first of its trials high."""
    points = np.asarray(tb.points)
    ones = np.rint(tb.conversions * norm.cdf((points[:, 1] - offset_v) / sigma_v)).astype(int)
    seen = np.zeros(len(points), dtype=int)
    decision = []
    for point in tb.trial_point:
        decision.append(seen[point] < ones[point])
        seen[point] += 1
    return latch_run(tb, [300e-12] * len(tb.trial_point), decision=decision, coarse=True)


def test_the_record_takes_each_metric_from_its_own_run() -> None:
    """A screen and the nominal S-curve, each run distinct: the metrics are each run's known answer
    (the 0.5 mV run 250 ps and 1.2 V x 40 fC, the 100 mV run 90 ps and 1.2 V x 60 fC, the slowest
    0.5 mV delay over the supply its 90 % corner's 330 ps, the kickback 3 mV, tau 30 ps, the S-curve
    an offset of 0.1 mV and a noise of 0.3 mV within the 80 decisions' rounding)."""
    vdd, cm = 1.2, round(NOMINAL_CM * 1.2, 4)
    nominal = TbParams(vdd=vdd, vin_cm_values_v=(cm,))
    law = metastability_law(60e-12, 30e-12)
    measurements = {}
    for name, check in (("metastability", False), ("metastability_check", True)):
        tb = replace(nominal, vin_diff_values_v=METASTABILITY_RUN_V)
        if check:
            tb = replace(tb, reset_time_s=CHECK_CLOCK_S[0], evaluation_time_s=CHECK_CLOCK_S[1])
        measurements[name] = latch_run(tb, [law(tb.points[p][1]) for p in tb.trial_point])
    small = replace(nominal, vin_diff_values_v=(SMALL_V,), conversions=3)
    large = replace(nominal, vin_diff_values_v=(LARGE_V,), conversions=3)
    measurements["small"] = latch_run(small, [250e-12] * 3, charge_c=[90e-15, 40e-15, 40e-15])
    measurements["large"] = latch_run(large, [90e-12] * 3, charge_c=[90e-15, 60e-15, 60e-15])
    kickback = replace(nominal, vin_diff_values_v=(SMALL_V,))
    measurements["kickback"] = latch_run(kickback, [250e-12], kick_p=kick(kickback.reset_time_s + 100e-12, 3e-3))
    for factor, delay in zip(SUPPLY_SWEEP, (330e-12, 250e-12, 210e-12), strict=True):
        tb = TbParams(
            vdd=round(factor * vdd, 4),
            vin_cm_values_v=(round(NOMINAL_CM * factor * vdd, 4),),
            vin_diff_values_v=(SMALL_V, LARGE_V),
            conversions=2,
        )
        measurements[f"supply_{round(factor * 100)}"] = latch_run(
            tb, [delay, delay, 90e-12, 90e-12], charge_c=[50e-15] * 4
        )
    scurve = replace(
        nominal, vin_diff_values_v=SCURVE_V, conversions=SCURVE_DECISIONS, input_order="shuffled", noise=True
    )
    measurements[f"scurve_cm{round(NOMINAL_CM * 24)}"] = scurve_run(scurve, 0.1e-3, 0.3e-3)
    record = runs.results(measurements)
    values = record.metrics
    assert values["delay_0p5mv_s"] == pytest.approx(250e-12, abs=0.1e-12)
    assert values["delay_100mv_s"] == pytest.approx(90e-12, abs=0.1e-12)
    assert values["delay_0p1mv_s"] == pytest.approx(law(0.1e-3), abs=0.1e-12)
    assert values["regeneration_tau_s"] == pytest.approx(30e-12, rel=1e-3)
    assert values["energy_0p5mv_j"] == pytest.approx(1.2 * 40e-15, rel=1e-9)
    assert values["energy_100mv_j"] == pytest.approx(1.2 * 60e-15, rel=1e-9)
    assert values["kickback_v"] == pytest.approx(3e-3, rel=1e-3)
    assert values["delay_max_supply_s"] == pytest.approx(330e-12, abs=0.1e-12)
    assert values["decides_in_time"] is True
    assert values["offset_v"] == pytest.approx(0.1e-3, abs=0.05 * 0.3e-3)
    assert values["noise_v"] == pytest.approx(0.3e-3, rel=0.05)
    assert values["unresolved_fraction"] == 0.0
    # one common mode: no largest noise over the common mode
    assert values["noise_max_v"] is None
    names = [plot.name for plot in record.details]
    assert sorted(names) == sorted(
        [
            "metastability",
            "noise_cm",
            "offset_cm",
            "delay_supply_0p5mv",
            "delay_supply_100mv",
            "energy_supply",
            "scurve",
        ]
    )
    assert record.waves == {
        "0.5 mV input": "small",
        "100 mV input": "large",
        "metastability": "metastability",
        "kickback": "kickback",
    }


def test_the_metastability_run_reads_its_inputs_in_the_order_applied() -> None:
    """The metastability run applies each input after its negative (-0.1, +0.1, -0.3, +0.3 mV, ...):
    its trials' inputs read back in that order."""
    tb = TbParams(vin_diff_values_v=METASTABILITY_RUN_V)
    decisions = analyze_decisions(latch_run(tb, [200e-12] * len(METASTABILITY_RUN_V), coarse=True))
    np.testing.assert_allclose(decisions.vin_diff_v, METASTABILITY_RUN_V)
    np.testing.assert_array_equal(decisions.decision, [int(v > 0) for v in METASTABILITY_RUN_V])
