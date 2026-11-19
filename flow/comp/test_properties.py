"""Properties of the comparator's analyses over generated inputs (Hypothesis): what each must keep
whatever the comparator, stated as an invariance or a closed form, never as the code again.

The synthetic runs and captures are ``test_known_answers``'s."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import norm

from . import analysis
from .analysis import (
    analyze_clock_check,
    analyze_decisions,
    analyze_kickback,
    analyze_metastability,
    analyze_offset_noise,
    analyze_power,
    analyze_scope_edges,
    analyze_scurve,
    analyze_timing,
)
from .params import SCURVE_DECISIONS, SCURVE_V, TbParams
from .test_known_answers import (
    PERIOD_S,
    SCOPE_DELAY_S,
    chain,
    conversions_of,
    decisions_of,
    expected_curve,
    kick,
    latch_run,
    metastability_law,
    scope_wave,
)

# a small metastability run: each of four inputs after its negative
INPUTS_V = (0.1e-3, 0.3e-3, 1e-3, 3e-3)
RUN_V = tuple(v for value in INPUTS_V for v in (-value, value))


def fisher_errors(inputs_v: np.ndarray, trials: int, offset_v: float, sigma_v: float) -> tuple[float, float]:
    """The smallest standard errors any unbiased fit of an S-curve can reach on these inputs (the
    Cramer-Rao bound): binomial counts of P = Phi(z), z = (V - V_OS) / sigma, whose information about
    (V_OS, sigma) is n phi(z)^2 / (P (1 - P)) times [[1, z], [z, z^2]] / sigma^2 at each input."""
    z = (np.asarray(inputs_v) - offset_v) / sigma_v
    p = np.clip(norm.cdf(z), 1e-300, 1 - 1e-16)
    weight = trials * norm.pdf(z) ** 2 / (p * (1 - p)) / sigma_v**2
    information = np.asarray([[np.sum(weight), np.sum(weight * z)], [np.sum(weight * z), np.sum(weight * z**2)]])
    # an information matrix singular to round-off (the transition between two inputs: fewer than two
    # of them tell the offset from the noise) bounds no error: the pair is not identifiable
    eigenvalues = np.linalg.eigvalsh(information)
    if not eigenvalues[0] > 1e-12 * eigenvalues[-1]:
        return math.inf, math.inf
    covariance = np.linalg.inv(information)
    return float(math.sqrt(covariance[0, 0])), float(math.sqrt(covariance[1, 1]))


# ---------------------------------------------------------------- the S-curve fit


def scurve_fit(sigma_v: float, offset_v: float, seed: int):
    """Decisions drawn on the characterization's S-curve (``SCURVE_V``, ``SCURVE_DECISIONS`` a
    point) from a Gaussian of ``offset_v`` and ``sigma_v``, their fit, and its standard errors."""
    rng = np.random.default_rng(seed)
    inputs = np.repeat(np.asarray(SCURVE_V), SCURVE_DECISIONS)
    decision = rng.random(len(inputs)) < norm.cdf((inputs - offset_v) / sigma_v)
    fit = analyze_offset_noise([decisions_of(inputs, decision)])
    return fit, fisher_errors(np.asarray(SCURVE_V), SCURVE_DECISIONS, offset_v, sigma_v)


@settings(derandomize=True, max_examples=60)
@given(
    sigma_v=st.floats(10e-6, 1.5e-3),
    offset_fraction=st.floats(-1.0, 1.0),
    seed=st.integers(0, 2**32 - 1),
)
def test_the_scurve_fit_recovers_a_centred_gaussian_it_was_drawn_with(sigma_v, offset_fraction, seed) -> None:
    """Decisions drawn on the characterization's S-curve from a Gaussian of 10 uV to 1.5 mV
    (``params``: "reading 10 uV to 1.5 mV of noise"), its offset within a sigma of the centre: the
    fit is valid and within five of its standard errors (``fisher_errors``) of both."""
    offset_v = offset_fraction * sigma_v
    fit, (offset_error, sigma_error) = scurve_fit(sigma_v, offset_v, seed)
    assert fit.validity == "valid"
    assert abs(fit.offset_v - offset_v) <= 5 * offset_error
    assert abs(fit.noise_sigma_v - sigma_v) <= 5 * sigma_error


@settings(derandomize=True, max_examples=100)
@given(
    sigma_v=st.floats(10e-6, 1.5e-3),
    offset_fraction=st.floats(-1.0, 1.0),
    seed=st.integers(0, 2**32 - 1),
)
def test_a_valid_scurve_fit_is_within_its_statistical_error_wherever_its_offset(sigma_v, offset_fraction, seed) -> None:
    """The same, the offset anywhere up to 1 mV that leaves the transition (+-2 sigma) inside the
    3 mV span (``params``: "the span wide enough for 1 mV of offset"; the readme's systematic
    offsets reach 1 mV): a fit the analysis calls valid is within five of its standard errors of
    the Gaussian it was drawn with (where the grid cannot resolve it, the fit is not valid)."""
    offset_v = offset_fraction * max(0.0, min(1e-3, 3e-3 - 2 * sigma_v))
    fit, (offset_error, sigma_error) = scurve_fit(sigma_v, offset_v, seed)
    if fit.validity == "valid":
        assert abs(fit.offset_v - offset_v) <= 5 * offset_error
        assert abs(fit.noise_sigma_v - sigma_v) <= 5 * sigma_error


@settings(max_examples=40)
@given(
    sigma_v=st.floats(50e-6, 1e-3),
    offset_v=st.floats(-0.5e-3, 0.5e-3),
    shift_v=st.floats(-1e-3, 1e-3),
    scale=st.floats(0.2, 5.0),
)
def test_shifting_the_inputs_shifts_the_offset_and_scaling_them_scales_both(sigma_v, offset_v, shift_v, scale) -> None:
    """The same decisions on inputs shifted by a volt offset move the offset by it and keep the
    noise; on inputs scaled by k, both scale by k (the curve's shape is the decisions', its axis
    the inputs')."""
    inputs = offset_v + sigma_v * np.linspace(-3, 3, 25)
    curve = expected_curve(inputs, offset_v, sigma_v, 400)
    fit = analyze_offset_noise([curve])
    shifted = analyze_offset_noise([replace(curve, vin_diff_v=curve.vin_diff_v + shift_v)])
    scaled = analyze_offset_noise([replace(curve, vin_diff_v=curve.vin_diff_v * scale)])
    assert fit.validity == shifted.validity == scaled.validity == "valid"
    assert math.isclose(shifted.offset_v, fit.offset_v + shift_v, abs_tol=1e-4 * sigma_v)
    assert math.isclose(shifted.noise_sigma_v, fit.noise_sigma_v, rel_tol=1e-4)
    assert math.isclose(scaled.offset_v, fit.offset_v * scale, abs_tol=1e-4 * sigma_v * scale)
    assert math.isclose(scaled.noise_sigma_v, fit.noise_sigma_v * scale, rel_tol=1e-4)


@settings(max_examples=40)
@given(sigma_v=st.floats(50e-6, 1e-3), offset_v=st.floats(-0.5e-3, 0.5e-3), trials=st.integers(20, 400))
def test_inverting_every_decision_flips_the_polarity_and_keeps_the_fit(sigma_v, offset_v, trials) -> None:
    curve = expected_curve(offset_v + sigma_v * np.linspace(-3, 3, 25), offset_v, sigma_v, trials)
    fit = analyze_offset_noise([curve])
    inverted = analyze_offset_noise([replace(curve, decision=1 - curve.decision)])
    assert (fit.decision_polarity, inverted.decision_polarity) == (1, -1)
    assert inverted.validity == fit.validity
    assert math.isclose(inverted.offset_v, fit.offset_v, abs_tol=1e-4 * sigma_v)
    assert math.isclose(inverted.noise_sigma_v, fit.noise_sigma_v, rel_tol=1e-4)


@given(
    ones=st.lists(st.integers(0, 50), min_size=3, max_size=20),
    seed=st.integers(0, 1000),
)
def test_a_curve_whose_counts_never_fall_is_never_non_monotonic(ones, seed) -> None:
    """Counts of high decisions of 50 at ascending inputs, sorted to never fall: the S-curve's share
    rises with the input, and the offset fit never calls it non-monotonic."""
    counts = sorted(ones)
    inputs = np.repeat(np.arange(len(counts)) * 1e-4, 50)
    decision = np.concatenate([np.r_[np.ones(k), np.zeros(50 - k)] for k in counts])
    order = np.random.default_rng(seed).permutation(len(inputs))
    decisions = decisions_of(inputs[order], decision[order])
    scurve = analyze_scurve([decisions])
    assert np.all(np.diff(scurve.probability) >= 0)
    np.testing.assert_allclose(scurve.probability, np.asarray(counts) / 50)
    assert analyze_offset_noise([decisions]).validity != "non_monotonic"


@given(st.lists(st.tuples(st.sampled_from([-1e-3, 0.0, 1e-3]), st.booleans(), st.booleans()), min_size=1, max_size=60))
def test_the_scurve_is_each_inputs_share_whatever_the_trials_order(trials) -> None:
    """Each input's P(high) is its resolved high decisions over its resolved ones, its unresolved
    share its unresolved over its trials, the same in any order of the trials."""
    inputs = np.asarray([trial[0] for trial in trials])
    decision = np.asarray([trial[1] for trial in trials])
    resolved = np.asarray([trial[2] for trial in trials])
    scurve = analyze_scurve([decisions_of(inputs, decision, resolved=resolved)])
    reversed_ = analyze_scurve([decisions_of(inputs[::-1], decision[::-1], resolved=resolved[::-1])])
    for index, value in enumerate(scurve.vin_diff_v):
        at = inputs == value
        decided = at & resolved
        expected = decision[decided].mean() if decided.any() else math.nan
        np.testing.assert_allclose(scurve.probability[index], expected)
        np.testing.assert_allclose(scurve.unresolved_fraction[index], (~resolved[at]).mean())
    np.testing.assert_allclose(reversed_.probability, scurve.probability)
    assert math.isclose(scurve.total_unresolved_fraction, float((~resolved).mean()))


# ---------------------------------------------------------------- delay and regeneration


@settings(max_examples=25)
@given(t0_s=st.floats(20e-12, 300e-12), tau_s=st.floats(5e-12, 60e-12), shift_s=st.floats(0.0, 500e-12))
def test_the_regeneration_time_constant_is_any_latchs_and_a_fixed_delay_leaves_it(t0_s, tau_s, shift_s) -> None:
    """d(V) = t_0 + tau ln(10 mV / V) over 0.1 to 3 mV: the analysis reads tau, and every delay its
    law; a delay added to every decision (a slower clock to the latch) moves every delay by it and
    leaves tau."""
    tb = TbParams(vin_diff_values_v=RUN_V)
    results = []
    for extra in (0.0, shift_s):
        law = metastability_law(t0_s + extra, tau_s, reference_v=10e-3)
        meas = latch_run(tb, [law(tb.points[point][1]) for point in tb.trial_point], tau_s=10e-12, step_s=0.2e-12)
        results.append(analyze_metastability(meas, delay=chain(meas)[2]))
    base, shifted = results
    assert math.isclose(base.regeneration_tau_s, tau_s, rel_tol=2e-3)
    assert math.isclose(shifted.regeneration_tau_s, tau_s, rel_tol=2e-3)
    law = metastability_law(t0_s, tau_s, reference_v=10e-3)
    np.testing.assert_allclose(base.delay_s, [law(v) for v in INPUTS_V], atol=0.05e-12)
    np.testing.assert_allclose(shifted.delay_s - base.delay_s, shift_s, atol=0.1e-12)


@settings(max_examples=25)
@given(reset_s=st.floats(0.3e-9, 2e-9), delay_s=st.floats(50e-12, 1.5e-9))
def test_moving_the_clocks_rise_within_the_cycle_leaves_every_duration(reset_s, delay_s) -> None:
    """The same latch behind a longer or shorter reset (the clock's rise later or earlier in the
    cycle): the clock-to-decision delays and the settling are the same; a negative input's are its
    positive's."""
    timings = []
    for reset in (1e-9, reset_s):
        tb = TbParams(vin_diff_values_v=(-1e-3, 1e-3), reset_time_s=reset, conversions=1)
        meas = latch_run(tb, [delay_s, delay_s], step_s=0.05e-12)
        timings.append(analyze_timing(meas, decisions=analyze_decisions(meas)))
    base, moved = timings
    np.testing.assert_allclose(base.clock_to_decision_s, delay_s, atol=0.01e-12)
    np.testing.assert_allclose(moved.clock_to_decision_s, base.clock_to_decision_s, atol=0.01e-12)
    np.testing.assert_allclose(moved.settling_s, base.settling_s, atol=0.05e-12)
    assert math.isclose(base.settling_s[0], base.settling_s[1], abs_tol=0.05e-12)


@settings(max_examples=25)
@given(t0_s=st.floats(20e-12, 300e-12), tau_s=st.floats(5e-12, 60e-12))
def test_ten_microvolts_is_decided_tau_ln_10_after_the_smallest_input(t0_s, tau_s) -> None:
    """The extrapolated 10 uV delay is the 0.1 mV delay plus tau_reg ln(0.1 mV / 10 uV): the law's
    own value at 10 uV."""
    law = metastability_law(t0_s, tau_s, reference_v=10e-3)
    results = []
    for check in (False, True):
        tb = TbParams(vin_diff_values_v=RUN_V)
        if check:
            tb = replace(tb, reset_time_s=2e-9, evaluation_time_s=8e-9)
        meas = latch_run(tb, [law(tb.points[point][1]) for point in tb.trial_point], tau_s=10e-12)
        decisions, _, delay = chain(meas)
        results.append((meas, decisions, analyze_metastability(meas, delay=delay)))
    meas, decisions, metastability = zip(*results, strict=True)
    check = analyze_clock_check(list(meas), decisions=list(decisions), metastability=list(metastability))
    assert math.isclose(check.resolved_10uv_s, law(10e-6), rel_tol=1e-3)
    assert check.decides_in_time == (law(10e-6) <= 4e-9)


# ---------------------------------------------------------------- kickback, power


@settings(max_examples=25)
@given(
    amplitude_v=st.floats(0.1e-3, 50e-3),
    scale=st.floats(0.1, 10.0),
    common_v=st.floats(-0.2, 0.2),
)
def test_the_kickback_scales_with_the_kick_and_ignores_the_common_mode(amplitude_v, scale, common_v) -> None:
    """A kick k times larger reads k times larger; both inputs moved by one constant read the same."""
    tb = TbParams(vin_diff_values_v=(0.5e-3,))
    at_s = tb.reset_time_s + 100e-12
    base = analyze_kickback(
        latch_run(tb, [200e-12], kick_p=kick(at_s, amplitude_v), kick_n=kick(at_s, -amplitude_v / 2))
    )
    larger = analyze_kickback(
        latch_run(tb, [200e-12], kick_p=kick(at_s, scale * amplitude_v), kick_n=kick(at_s, -scale * amplitude_v / 2))
    )
    moved = analyze_kickback(
        latch_run(
            replace(tb, vin_cm_values_v=(0.65 + common_v,)),
            [200e-12],
            kick_p=kick(at_s, amplitude_v),
            kick_n=kick(at_s, -amplitude_v / 2),
        )
    )
    assert math.isclose(larger.kickback_v, scale * base.kickback_v, rel_tol=1e-6)
    assert math.isclose(larger.kickback_diff_v, scale * base.kickback_diff_v, rel_tol=1e-6)
    assert math.isclose(moved.kickback_v, base.kickback_v, rel_tol=1e-6, abs_tol=1e-12)
    assert math.isclose(moved.kickback_diff_v, base.kickback_diff_v, rel_tol=1e-6, abs_tol=1e-12)
    assert math.isclose(base.kickback_diff_v, 1.5 * base.kickback_v, rel_tol=1e-6)


@settings(max_examples=40)
@given(
    charges_c=st.lists(st.floats(1e-15, 1e-12), min_size=6, max_size=6),
    vdd=st.floats(0.8, 1.8),
    shuffled=st.booleans(),
)
def test_the_energy_is_the_supply_times_the_mean_charge_of_the_decisions_after_their_own_input(
    charges_c, vdd, shuffled
) -> None:
    """Two inputs of three decisions each, in either order, each drawing its own charge: the energy
    per decision is V_DD times the mean charge of the decisions that follow one at their input, the
    power that over the cycle."""
    tb = TbParams(
        vin_diff_values_v=(0.5e-3, 100e-3), conversions=3, vdd=vdd, input_order="shuffled" if shuffled else "blocked"
    )
    power = analyze_power([latch_run(tb, [200e-12] * 6, charge_c=charges_c)])
    point = tb.trial_point
    steady = [charge for index, charge in enumerate(charges_c) if index > 0 and point[index] == point[index - 1]]
    expected = vdd * float(np.mean(steady)) if steady else math.nan
    np.testing.assert_allclose(power.energy_per_decision_j, [expected], rtol=1e-6)
    np.testing.assert_allclose(power.average_power_w, [expected / tb.cycle_s], rtol=1e-6)


# ---------------------------------------------------------------- a converter's captures


@settings(max_examples=20)
@given(
    shifts=st.lists(st.floats(0.0, 4e-9), min_size=1, max_size=3),
    jitter=st.lists(st.floats(-0.9e-9, 0.9e-9), min_size=3, max_size=3),
)
def test_the_scope_edges_keep_each_delay_and_jitter_wherever_the_record_starts(shifts, jitter) -> None:
    """Records starting anywhere, each decision's COMP rise displaced by its jitter: every delay is
    COMP_OUT's own (but the held decision's, none) and every jitter the displacement from B0's."""
    jitter_s = (0.0, *jitter)
    edges = analyze_scope_edges([conversions_of(scope_wave(shifts_s=tuple(shifts), jitter_s=jitter_s), 4)])
    np.testing.assert_allclose(np.delete(edges.delays_s, 2, axis=1), SCOPE_DELAY_S, atol=1e-12)
    np.testing.assert_allclose(edges.jitter_s, np.tile(jitter_s, (len(shifts), 1)), atol=1e-12)
    np.testing.assert_allclose(edges.rise_s, np.arange(4) * PERIOD_S + np.asarray(jitter_s), atol=1e-12)


@given(
    times=st.lists(st.floats(0.1e-9, 5e-9), min_size=1, max_size=60),
    decisions=st.integers(1, 6),
    seed=st.integers(0, 100),
)
def test_each_decisions_shares_are_its_own_and_sum_to_one(times, decisions, seed) -> None:
    """Response times spread over decisions: each decision with a time has shares summing to one
    and its median the median of its own; a decision without one an empty column."""
    decision = np.random.default_rng(seed).integers(0, decisions, len(times))
    result = analysis._per_decision("xc", decision, np.asarray(times), decisions)
    for index in range(decisions):
        own = np.asarray(times)[decision == index]
        if len(own):
            assert math.isclose(float(np.nansum(result["xc_share"][:, index])), 1.0, rel_tol=1e-9)
            assert math.isclose(float(result["xc_median_s"][index]), float(np.median(own)), rel_tol=1e-12)
        else:
            assert np.all(np.isnan(result["xc_share"][:, index])) and math.isnan(result["xc_median_s"][index])
    assert result["xc_s"][0] <= min(times) and result["xc_s"][-1] >= max(times)
