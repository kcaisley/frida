"""Properties of the capacitive DAC over generated inputs (Hypothesis): what its arrays' weights and
plates, a run's steps, the settling of single-pole steps, the static linearity of drawn plates, the
bench's capacitance, the behavioral model's switching and the drivers' sizing must do whatever the
array, the time, the scale or the gain, on the synthetic runs of ``test_known_answers``."""

from __future__ import annotations

import itertools
import math
from dataclasses import replace

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from scipy.constants import Boltzmann

from . import subckt
from .analysis import analyze_cap_mismatch, analyze_mismatch, analyze_settling
from .model import Model
from .params import Params, Redundancy, TbParams, WeightImpl, _switched_f
from .test_known_answers import (
    TAUS,
    UNIT8,
    comparator,
    near,
    nominal_sides,
    placed,
    plates_meas,
    rc,
    settling_of,
    settling_run,
    synthetic_table,
    use_table,
)

# a settling example builds a 60 000-point run and a mismatch example walks every decision path:
# fewer examples than the default 100
RUNS = settings(max_examples=30, deadline=None)
FEW = settings(max_examples=15, deadline=None)
MOST_EXTRA = {Redundancy.BINARY: 0, Redundancy.MSB_SPLIT: -1, Redundancy.LSB_SPLIT: -1, Redundancy.MSB_REDIST: -3}


@st.composite
def arrays(draw, most_bits: int = 14) -> Params:
    """Any array ``Params`` admits, 8 to ``most_bits`` bits: a redundant scheme spends 1 to its most
    extra cycles (N - 2 a split, N - 4 the overlay), the binary none."""
    n = draw(st.integers(8, most_bits))
    redundancy = draw(st.sampled_from(list(Redundancy)))
    extra = 0 if redundancy is Redundancy.BINARY else draw(st.integers(1, n - 1 + MOST_EXTRA[redundancy]))
    return Params(
        bits=n,
        redundancy=redundancy,
        extra=extra,
        scale=draw(st.integers(1, 3)),
        weight_impl=draw(st.sampled_from(list(WeightImpl))),
        coarse_weight=draw(st.sampled_from([16, 32, 64])),
    )


# ---- the arrays


@given(params=arrays())
def test_every_array_is_its_binary_steps_spent_redundantly(params: Params) -> None:
    """N - 1 + extra stages, never rising, at least a unit each, summing to the binary 2^(N-1) - 1
    whatever the scheme; none outweighing the stages after it by more than a unit (each decision's
    error recovered later); the decoder's weights summing to 2^N - 1, the full scale less one LSB."""
    weights = Model.weights(params)
    later = [sum(weights[k + 1 :]) for k in range(len(weights))]
    assert len(weights) == params.bits - 1 + params.extra
    assert sum(weights) == 2 ** (params.bits - 1) - 1 and min(weights) >= 1
    assert all(a >= b for a, b in itertools.pairwise(weights))
    assert all(w <= rest + 1 for w, rest in zip(weights, later, strict=True))
    assert sum(2 * w for w in weights) + 1 == 2**params.bits - 1


@given(params=arrays(), vdd=st.floats(0.5, 3.3))
def test_each_stages_plates_less_their_difference_are_its_weight_in_units(params: Params, vdd: float) -> None:
    """main - diff = w units of the side's switched capacitance over the total weight; a strip's two
    plates its pieces' coarse weight together; unit capacitors no difference plate; none negative."""
    main_f, diff_f = Model.plates(params, vdd)
    weights = np.asarray(Model.weights(params), dtype=np.float64)
    unit_f = _switched_f(params, vdd) / weights.sum()
    np.testing.assert_allclose(main_f - diff_f, weights * unit_f, rtol=1e-12)
    assert np.all(diff_f >= 0) and np.all(main_f > 0)
    if params.weight_impl is WeightImpl.UNIT_CAPS:
        assert not diff_f.any()
    else:
        whole = np.ceil(weights / params.coarse_weight) * params.coarse_weight
        np.testing.assert_allclose(main_f + diff_f, whole * unit_f, rtol=1e-12)


@given(params=arrays(), vdd=st.floats(0.5, 3.3), times=st.integers(2, 4))
def test_scaling_the_capacitance_or_the_reference_leaves_every_step_in_lsb(
    params: Params, vdd: float, times: int
) -> None:
    """A run's steps in its LSB are 2^N w / W whatever the reference and however many kT/C minimums:
    more capacitance (``scale``) multiplies every plate, the reference only the volts."""
    base = TbParams(params=params, vdd=vdd, window_s=4e-9, waveform_sample_interval_s=2e-12)
    other = TbParams(
        params=replace(params, scale=times * params.scale), vdd=1.0, window_s=4e-9, waveform_sample_interval_s=2e-12
    )
    weights = np.asarray(base.weights, dtype=np.float64)
    np.testing.assert_allclose(base.ideal_step_v / base.lsb_v, 2**params.bits * weights / weights.sum(), rtol=1e-9)
    np.testing.assert_allclose(other.ideal_step_v / other.lsb_v, base.ideal_step_v / base.lsb_v, rtol=1e-9)
    # every plate scale / V^2 (C = 24 scale kT 4^N / (4 V^2))
    np.testing.assert_allclose(other.main_f / times, base.main_f * vdd**2, rtol=1e-9)


@given(bits=st.integers(8, 14), scale=st.integers(1, 3), vdd=st.floats(0.5, 3.3))
def test_the_kt_c_capacitance_is_scale_times_24_kt_over_the_lsb_squared(bits: int, scale: int, vdd: float) -> None:
    """Both sides' 2 kT/C equal to LSB^2 / 12 at LSB = 2 V / 2^N, ``scale`` times: C = 24 scale kT /
    LSB^2: four times the capacitance a bit, a quarter at twice the reference."""
    params = Params(bits=bits, redundancy=Redundancy.BINARY, extra=0, scale=scale)
    lsb_v = 2 * vdd / 2**bits
    assert _switched_f(params, vdd) == near(24 * scale * Boltzmann * 300.0 / lsb_v**2, rel=1e-12)


# ---- analyze_settling


@RUNS
@given(shift_s=st.floats(0.0, 400e-12))
def test_moving_every_edge_later_changes_no_settling_or_delay(shift_s: float) -> None:
    """The settling and the delay are timed from the state's own edge: the whole response later by
    any time within the window gives the same numbers."""
    base, moved = analyze_settling(settling_run(UNIT8)), analyze_settling(settling_run(UNIT8, shift_s=shift_s))
    for name in ("settling_rise_s", "settling_fall_s", "delay_rise_s", "delay_fall_s"):
        np.testing.assert_allclose(getattr(moved, name), getattr(base, name), atol=0.05e-12, rtol=0, err_msg=name)
    np.testing.assert_allclose(moved.step_rise_v, base.step_rise_v, rtol=1e-9)


@RUNS
@given(lag_s=st.floats(0.0, 300e-12))
def test_a_response_that_starts_later_settles_and_crosses_later_by_as_much(lag_s: float) -> None:
    base, late = analyze_settling(settling_run(UNIT8)), analyze_settling(settling_run(UNIT8, lag_s=lag_s))
    np.testing.assert_allclose(late.settling_s - base.settling_s, lag_s, atol=0.05e-12, rtol=0)
    np.testing.assert_allclose(late.delay_s - base.delay_s, lag_s, atol=0.05e-12, rtol=0)


@RUNS
@given(tau_s=st.floats(20e-12, 250e-12), slower=st.floats(1.0, 1.5))
def test_a_slower_rc_never_settles_sooner(tau_s: float, slower: float) -> None:
    """The MSB an RC of tau, then of a longer tau: its settling, tau ln(|step| / (LSB / 2)), grows."""
    fast = analyze_settling(settling_run(UNIT8, [rc(tau_s), *(rc(t) for t in TAUS[1:])]))
    slow = analyze_settling(settling_run(UNIT8, [rc(tau_s * slower), *(rc(t) for t in TAUS[1:])]))
    ratio = 2**9 * 64 / 127
    assert fast.settling_s[0] == pytest.approx(tau_s * math.log(ratio), abs=0.05e-12)
    assert slow.settling_s[0] >= fast.settling_s[0] - 0.05e-12


@RUNS
@given(scale_v=st.floats(0.3, 1.5))
def test_a_gain_on_every_step_scales_the_lsb_and_keeps_the_settling_and_the_error(scale_v: float) -> None:
    base, scaled = analyze_settling(settling_run(UNIT8)), analyze_settling(settling_run(UNIT8, scale_v=scale_v))
    assert scaled.gain == near(scale_v * base.gain, rel=1e-9)
    assert scaled.lsb_v == near(scale_v * base.lsb_v, rel=1e-9)
    np.testing.assert_allclose(scaled.settling_s, base.settling_s, atol=0.05e-12, rtol=0)
    assert scaled.step_error_lsb == pytest.approx(base.step_error_lsb, abs=1e-6)


@given(
    settling_s=st.floats(10e-12, 2e-9),
    delay_s=st.floats(0.0, 2e-9),
    ratio=st.floats(0.1, 1e5),
)
def test_the_time_constant_brings_the_step_to_half_an_lsb_when_it_settles(
    settling_s: float, delay_s: float, ratio: float
) -> None:
    """Started at the delay, |s| exp(-(t_s - d) / tau) = LSB / 2 at the settling time; none where the
    step is within half an LSB or settles before its delay."""
    tau = settling_of([settling_s], [delay_s], [ratio * 0.5e-3]).tau_s[0]
    if ratio > 1 and settling_s > delay_s:
        assert delay_s + tau * math.log(ratio) == near(settling_s, rel=1e-9)
    else:
        assert tau == 0.0


# ---- analyze_mismatch


@FEW
@given(params=arrays(most_bits=10))
def test_a_perfect_array_converts_perfectly(params: Params) -> None:
    """Drawn as designed, both sides: the DAC and the converter have no DNL or INL, no code missing
    and nothing a calibration need recover, whatever the scheme."""
    main_p, diff_p, main_n, diff_n = nominal_sides(params)
    result = analyze_mismatch(plates_meas(params, [(main_p, diff_p), (main_n, diff_n)]))
    for name in ("dac_inl_lsb", "dac_dnl_lsb", "dnl_lsb", "inl_lsb", "gap_lsb"):
        assert abs(getattr(result, name)[0]) < 1e-6, name
    assert result.missing_codes[0] == 0


@FEW
@given(params=arrays(most_bits=10), times=st.floats(0.2, 5.0), seed=st.integers(0, 2**16))
def test_scaling_every_drawn_plate_leaves_the_linearity(params: Params, times: float, seed: int) -> None:
    """Each step is its plates' share of their top plate: every plate of both sides times any factor
    converts alike."""
    rng = np.random.default_rng(seed)
    main_p, diff_p, main_n, diff_n = (
        plates * (1 + 0.005 * rng.standard_normal(plates.shape)) * (plates > 0) for plates in nominal_sides(params)
    )
    base = analyze_mismatch(plates_meas(params, [(main_p, diff_p), (main_n, diff_n)]))
    scaled = analyze_mismatch(plates_meas(params, [(times * main_p, times * diff_p), (times * main_n, times * diff_n)]))
    for name in ("dac_inl_lsb", "dac_dnl_lsb", "dnl_lsb", "inl_lsb", "gap_lsb", "missing_codes"):
        np.testing.assert_allclose(getattr(scaled, name), getattr(base, name), rtol=1e-6, atol=1e-9, err_msg=name)


# ---- analyze_cap_mismatch


@given(
    main=st.floats(0.01, 0.4),
    diff=st.floats(0.0, 0.05),
    bias=st.floats(-0.01, 0.01),
    offset_v=st.floats(-5e-3, 5e-3),
    vdd_dac_v=st.floats(0.6, 1.8),
)
def test_the_bench_recovers_the_fractions_whatever_the_offset_and_the_reference(
    main: float, diff: float, bias: float, offset_v: float, vdd_dac_v: float
) -> None:
    """Curves placed from a stage's main and difference fractions (each direction its own, the
    converter's mode biased by ``bias``), the comparator's offset and the reference: the main,
    difference and effective fractions and the bias come back, on either side."""
    fractions = {}
    for side in ("p", "n"):
        fractions[side, 1, 0] = (main + diff, main + diff)
        fractions[side, 1, 1] = (main - diff + bias, main - diff - bias)
    points, fits = placed(fractions, offset_v=offset_v, vdd_dac_v=vdd_dac_v)
    result = analyze_cap_mismatch(points, transitions=fits, comparator=comparator(offset_v))
    np.testing.assert_allclose(result.main_fraction[:, 1], main, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(result.diff_fraction[:, 1], diff, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(result.effective_fraction[:, 1], main - diff, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(result.direction_bias[:, 1, 1], bias, rtol=1e-9, atol=1e-12)


# ---- the behavioral model


@st.composite
def switching(draw):
    """A side's plates (a stage each, fF), its parasitic and two state rows a conversion."""
    stages = draw(st.integers(1, 6))
    main = np.asarray(draw(st.lists(st.floats(0.1, 50.0), min_size=stages, max_size=stages))) * 1e-15
    diff = np.asarray(draw(st.lists(st.floats(0.0, 5.0), min_size=stages, max_size=stages))) * 1e-15
    parasitic = draw(st.floats(0.0, 100.0)) * 1e-15
    states = st.lists(st.integers(0, 1), min_size=stages, max_size=stages)
    sequence = np.asarray(draw(st.lists(states, min_size=2, max_size=6)))
    return main, diff, parasitic, sequence, draw(st.integers(0, 1)), draw(st.floats(0.3, 3.3))


@given(case=switching())
def test_the_top_plate_keeps_its_charge_and_a_closed_cycle_draws_energy(case) -> None:
    """Floating, the top plate's charge stays: its step times its whole load is each plate's
    capacitance times its bottom plate's step ([Razavi-ADC] Eq. (11.1), p. 210). Over a sequence of
    states back to the first, the capacitors hold what they held: the reference's energy, V times
    its charge, is what the switches burnt, never negative ([Razavi-ADC] Fig. 16.29, p. 348)."""
    main, diff, parasitic, sequence, diffcaps, vref = case
    cycle = np.vstack([sequence, sequence[:1]])
    total = main.sum() + diff.sum() + parasitic
    drawn = 0.0
    for before, after in itertools.pairwise(cycle):
        top, charge, _ = Model.switch(main, diff, parasitic, vref, diffcaps, before[None, :], after[None, :])
        bottom_main = vref * (after - before)
        bottom_diff = vref * ((after ^ diffcaps) - (before ^ diffcaps))
        # to the rounding of a charge of C_total V, a part in 1e12
        floor = 1e-12 * vref * total
        assert top[0] * total == pytest.approx(bottom_main @ main + bottom_diff @ diff, rel=1e-9, abs=floor)
        drawn += charge[0]
    assert vref * drawn >= -1e-12 * vref**2 * total


@given(case=switching(), stage=st.integers(0, 5))
def test_one_stage_switching_alone_is_the_sides_switch(case, stage: int) -> None:
    main, diff, parasitic, sequence, diffcaps, vref = case
    assume(stage < len(main))
    before = sequence[:1]
    after = before.copy()
    after[0, stage] = 1 - after[0, stage]
    whole = Model.switch(main, diff, parasitic, vref, diffcaps, before, after)
    at_vref = after @ main + (after ^ diffcaps) @ diff
    alone = Model.switch_stage(main, diff, parasitic, vref, diffcaps, stage, before[:, stage], after[:, stage], at_vref)
    for one, other in zip(alone, whole, strict=True):
        # to the rounding of a charge of C_total V, a part in 1e12
        np.testing.assert_allclose(one, other, rtol=1e-9, atol=1e-12 * vref * (main.sum() + diff.sum() + parasitic))


@given(params=arrays(), margin=st.floats(1.0, 4.0), settle_ps=st.floats(100.0, 5000.0))
def test_a_designs_model_brings_every_stage_to_half_an_lsb_at_its_budget(
    params: Params, margin: float, settle_ps: float
) -> None:
    """``Model.design``: each stage's step 2^N w / W LSB, decaying from the edge with its time
    constant, is half an LSB at settle_ps / settle_margin."""
    params = replace(params, settle_ps=settle_ps, settle_margin=margin)
    model = Model.design("tsmc65", params, reference_v=1.0)
    weights = np.asarray(Model.weights(params), dtype=np.float64)
    steps = 2**params.bits * weights / weights.sum()
    budget = settle_ps * 1e-12 / margin
    np.testing.assert_allclose(steps * np.exp(-budget / np.asarray(model.tau_s)), 0.5, rtol=1e-9)


@given(
    gain=st.floats(0.5, 1.0),
    errors=st.lists(st.floats(-0.02, 0.02), min_size=9, max_size=9),
    supply=st.floats(0.5, 2.0),
)
def test_the_behavioral_dac_gives_the_measured_steps_and_their_full_scale(gain: float, errors, supply: float) -> None:
    """``Model.behavioral`` from measured steps (the design's at a gain, each off by its own error):
    each side's plates step by half the measured step at the reference, over a whole load of the
    design's plates over the gain; its full scale at any reference half the steps' sum scaled to it."""
    params = Params(bits=10, redundancy=Redundancy.BINARY, extra=0)
    main_f, diff_f = Model.plates(params, 1.2)
    design_f = float(main_f.sum() + diff_f.sum())
    steps = 2 * 1.2 * gain * (main_f - diff_f) / design_f * (1 + np.asarray(errors))
    model = replace(Model.design("tsmc65", params, reference_v=1.2), gain=gain, step_v=tuple(map(float, steps)))
    dac = model.behavioral()
    main = np.asarray(dac.main_p_f)
    load = float(main.sum() + diff_f.sum()) + dac.parasitic_f
    assert load == near(design_f / gain, rel=1e-9)
    np.testing.assert_allclose(1.2 * (main - diff_f) / load, steps / 2, rtol=1e-9)
    assert model.full_scale_v(supply) == near(supply / 1.2 * steps.sum() / 2, rel=1e-9)


@given(
    capacitance=st.lists(st.floats(0.0, 500.0), min_size=1, max_size=8),
    pelgrom=st.floats(0.0, 0.02),
    seed=st.integers(0, 2**16),
)
def test_a_draws_deviation_grows_with_its_coefficient_and_none_stays_none(
    capacitance, pelgrom: float, seed: int
) -> None:
    """``Model.draw``: the deviation is the coefficient times a draw of its own, so twice the
    coefficient on the same draws twice the deviation; a capacitor of none stays none."""
    c_f = np.asarray(capacitance) * 1e-15
    once = Model.draw(c_f, pelgrom=pelgrom, rng=np.random.default_rng(seed)) - c_f
    twice = Model.draw(c_f, pelgrom=2 * pelgrom, rng=np.random.default_rng(seed)) - c_f
    # each deviation is read back off its capacitance: to a few of its doubles' last places
    np.testing.assert_allclose(twice, 2 * once, rtol=1e-6, atol=8 * np.finfo(float).eps * float(c_f.max()))
    assert np.all(once[c_f == 0] == 0)


# ---- the drivers' sizing


@given(
    share=st.floats(1 / 8191, 0.5),
    load_f=st.floats(0.01e-15, 2e-12),
    rho=st.floats(1.0, 3.0),
    settle_ps=st.floats(200.0, 5000.0),
)
def test_a_driver_meets_its_budget_exactly_and_a_heavier_load_asks_less_resistance(
    share: float, load_f: float, rho: float, settle_ps: float
) -> None:
    """Without a chain's delay, R C_L (k - ln 2 + rho ln 2) is the budget: k = ln(2^(N+1) w / W) time
    constants, the first ln 2 of them at rho times the on-resistance; twice the load, half the
    resistance; a longer budget, more."""
    with pytest.MonkeyPatch.context() as patch:
        use_table(patch, synthetic_table(rho=rho))
        _budget_met(share, load_f, rho, settle_ps)


def _budget_met(share: float, load_f: float, rho: float, settle_ps: float) -> None:
    params = Params(bits=14, redundancy=Redundancy.BINARY, extra=0, settle_ps=settle_ps, settle_margin=1.0)
    k = math.log(2**15 * share)
    assume(k > math.log(2))
    r_ohm = subckt._drive_r_ohm(params, share, load_f, "synthetic", False, 4.0)
    assert r_ohm * load_f * (k - math.log(2) + rho * math.log(2)) == near(settle_ps * 1e-12, rel=1e-9)
    assert subckt._drive_r_ohm(params, share, 2 * load_f, "synthetic", False, 4.0) == near(r_ohm / 2, rel=1e-9)
    longer = replace(params, settle_ps=min(5000.0, 1.5 * settle_ps))
    assert subckt._drive_r_ohm(longer, share, load_f, "synthetic", False, 4.0) >= r_ohm


@given(
    to_top=st.floats(0.0, 100.0),
    rest=st.floats(0.0, 100.0),
    shield=st.floats(0.0, 10.0),
    apart=st.floats(0.0, 10.0),
)
def test_a_plates_load_lies_between_its_fixed_capacitance_and_all_of_it(
    to_top: float, rest: float, shield: float, apart: float
) -> None:
    """In series with the rest of the top plate a plate loads its driver with less than its own
    capacitance to it and never less than its fixed capacitances (shield, twice its coupling); the
    series part is the same seen from either side."""
    assume(to_top + rest > 0)
    piece = {
        frozenset(("MAIN", "TOP")): to_top,
        frozenset(("MAIN", "SHIELD")): shield,
        frozenset(("MAIN", "DIFF")): apart,
    }
    load = subckt._plate_load([piece], "MAIN", "DIFF", to_top + rest)
    fixed = shield + 2 * apart
    assert fixed - 1e-9 <= load <= to_top + fixed + 1e-9
    mirrored = {
        frozenset(("MAIN", "TOP")): rest,
        frozenset(("MAIN", "SHIELD")): shield,
        frozenset(("MAIN", "DIFF")): apart,
    }
    assert subckt._plate_load([mirrored], "MAIN", "DIFF", to_top + rest) == pytest.approx(load, rel=1e-9, abs=1e-12)
