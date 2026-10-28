"""The predicted mismatch statistics agree with exact draws of the same arrays."""

import numpy as np

from flow.adc.statistics import MismatchStatistics
from flow.analysis.calc import calc_drawn_linearity, calc_paths
from flow.cdac.caparray.model import calc_capacitor_mismatch

UNIT_F = 1e-15
CODE_MAX = 63  # six bits: five capacitors and the free first comparison
PARASITIC_F = 30e-15


def _weights(caps) -> np.ndarray:
    return np.r_[2 * np.asarray(caps, dtype=np.float64), 1.0]


def _draws(main_f, unit_mismatch, count, seed=0):
    """Each draw's DNL and INL by code, worst |DNL| and |INL|: both sides drawn, no difference plates."""
    rng = np.random.default_rng(seed)
    diff_f = np.zeros_like(main_f)
    dnl, inl = [], []
    for _ in range(count):
        sides = [(calc_capacitor_mismatch(main_f, unit_mismatch=unit_mismatch, rng=rng), diff_f) for _ in "pn"]
        d, i, _missing = calc_drawn_linearity(
            sides, PARASITIC_F, _weights(main_f / UNIT_F), CODE_MAX, nominal=(main_f, diff_f)
        )
        dnl.append(d)
        inl.append(i)
    return np.asarray(dnl), np.asarray(inl)


def test_a_binary_array_converts_one_lsb_a_code() -> None:
    caps = np.array([16, 8, 4, 2, 1], dtype=np.float64)
    steps = caps * (CODE_MAX + 1) / (2 * caps.sum())
    paths = calc_paths(steps, steps, _weights(caps), CODE_MAX)
    assert np.array_equal(paths.code, np.arange(CODE_MAX + 1))
    # a code is the last step wide: one unit of 2 sum(C) / 2^bits
    assert np.allclose(np.diff(paths.lower[1:]), (CODE_MAX + 1) / (2 * caps.sum()))


def test_binary_statistics_match_brute_force_draws() -> None:
    main_f = np.array([16, 8, 4, 2, 1], dtype=np.float64) * UNIT_F
    unit_mismatch = 0.01
    statistics = MismatchStatistics.of(main_f, np.zeros_like(main_f), PARASITIC_F, _weights(main_f / UNIT_F), CODE_MAX)
    # each stage's step: A sqrt(C 1 fF) in the LSB's capacitance, 2 sum(C) / 2^bits
    lsb_f = 2 * main_f.sum() / (CODE_MAX + 1)
    assert np.allclose(statistics.weight_sigma * unit_mismatch, unit_mismatch * np.sqrt(main_f * UNIT_F) / lsb_f)
    assert np.allclose(statistics.dnl_mean, 0.0, atol=1e-9) and np.allclose(statistics.inl_mean, 0.0, atol=1e-9)
    assert np.all(statistics.margin_lsb == 0.0)

    dnl, inl = _draws(main_f, unit_mismatch, 3000)
    # every code's sigma, and the worst code's 95th percentile, within a few percent
    assert np.allclose(np.std(dnl, axis=0), unit_mismatch * statistics.dnl_sigma, rtol=0.06)
    assert np.allclose(np.std(inl, axis=0)[1:-1], unit_mismatch * statistics.inl_sigma[1:-1], rtol=0.06)
    worst_dnl = np.percentile(np.max(np.abs(dnl), axis=1), 95)
    worst_inl = np.percentile(np.max(np.abs(inl), axis=1), 95)
    assert abs(statistics.dnl_quantile(unit_mismatch) / worst_dnl - 1) < 0.08
    # the worst INL's half-sum leaves out the codes a comparator before the last one starts, whose
    # INL also carries the later steps of one side: about a tenth low on so short an array
    assert -0.15 < statistics.inl_quantile(unit_mismatch) / worst_inl - 1 < 0.02
    # the MSB transition spans every capacitor: the largest DNL sigma, from stage 0
    assert np.isclose(statistics.transition_sigma[0], np.max(statistics.dnl_sigma))


def test_redundant_statistics_match_brute_force_draws() -> None:
    # a sub-radix-2 array with every margin at least zero, its weights summing to the code range
    caps = np.array([13, 8, 5, 3, 1, 1], dtype=np.float64)
    main_f = caps * UNIT_F
    unit_mismatch = 0.01
    statistics = MismatchStatistics.of(main_f, np.zeros_like(main_f), PARASITIC_F, _weights(caps), CODE_MAX)
    assert np.all(statistics.margin_lsb >= 0.0) and statistics.margin_lsb[0] > 0.0
    assert np.all(statistics.margin_over_sigma(unit_mismatch)[statistics.margin_lsb > 0] > 0.0)
    dnl, inl = _draws(main_f, unit_mismatch, 3000, seed=1)
    worst_dnl = np.percentile(np.max(np.abs(dnl), axis=1), 95)
    worst_inl = np.percentile(np.max(np.abs(inl), axis=1), 95)
    assert abs(statistics.dnl_quantile(unit_mismatch) / worst_dnl - 1) < 0.10
    assert abs(statistics.inl_quantile(unit_mismatch) / worst_inl - 1) < 0.15


def test_the_predictions_grow_with_the_mismatch() -> None:
    main_f = np.array([16, 8, 4, 2, 1], dtype=np.float64) * UNIT_F
    statistics = MismatchStatistics.of(main_f, np.zeros_like(main_f), PARASITIC_F, _weights(main_f / UNIT_F), CODE_MAX)
    coefficients = (0.001, 0.01, 0.1)
    dnl = [statistics.dnl_quantile(a) for a in coefficients]
    inl = [statistics.inl_quantile(a) for a in coefficients]
    assert dnl == sorted(dnl) and inl == sorted(inl)
    # tenfold the coefficient, tenfold the worst INL of an array without its own error
    assert np.isclose(inl[1] / inl[0], 10.0, rtol=0.02)
    # missing codes only once the mismatch is a large part of an LSB
    assert statistics.missing_codes_expected(0.001) < 1e-6 < statistics.missing_codes_expected(0.1)
