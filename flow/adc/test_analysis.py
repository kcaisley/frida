"""The ADC's analyses: the redundancy of a SAR's weights, each scheme's at every resolution, and the
predicted mismatch statistics, which agree with exact draws of the same arrays."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.adc.analysis import (
    _dnl_quantile,
    _inl_quantile,
    _margin_over_sigma,
    _mismatch_statistics,
    _missing_codes_expected,
    _redundancy_margins,
    analyze_mismatch,
)
from flow.adc.model import AdcBehavioralParams, CdacBehavioralParams
from flow.adc.params import Params, TbParams
from flow.adc.types import AnalysisMismatch
from flow.analysis.calc import calc_drawn_linearity, calc_paths
from flow.analysis.plots import plot_adc_redundancy
from flow.analysis.types import MeasAdc, MeasInfo
from flow.cdac.caparray.model import calc_capacitor_mismatch
from flow.cdac.caparray.subckt import CapArrayConfig, RedunStrat, get_caparray_weights


def test_redundancy_calculator(tmp_path: Path) -> None:
    # q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1} over sum_{j=k}^{M-1} w_j (Ogawa et al., IEICE 2010, Eq. 5)
    margins = _redundancy_margins((4, 3, 2, 1))
    assert margins.tolist() == pytest.approx((30.0, 100 / 6, 0.0, 0.0))
    # binary weights tolerate nothing; one more LSB decision tolerates one LSB weight at each stage
    assert _redundancy_margins((8, 4, 2, 1)).tolist() == pytest.approx((0.0,) * 4)
    assert _redundancy_margins((8, 4, 2, 1, 1)).tolist() == pytest.approx((6.25, 12.5, 25.0, 50.0, 0.0))
    with pytest.raises(ValueError, match="positive SAR weights"):
        _redundancy_margins((4, 0, 1))
    (path,) = plot_adc_redundancy(margins, output_path=tmp_path / "single")
    assert path.read_bytes().startswith(b"%PDF")


def test_14_bit_weight_comparison(tmp_path: Path) -> None:
    binary = tuple(2**bit for bit in range(13, -1, -1))
    redistributed_18 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=4, redun_strat=RedunStrat.MSB_REDIST))
    )
    redistributed_20 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=6, redun_strat=RedunStrat.MSB_REDIST))
    )
    assert tuple(map(len, (binary, redistributed_18, redistributed_20))) == (14, 18, 20)
    assert tuple(map(sum, (binary, redistributed_18, redistributed_20))) == (16383,) * 3
    binary_margin = _redundancy_margins(binary)
    redistributed_18_margin = _redundancy_margins(redistributed_18)
    redistributed_20_margin = _redundancy_margins(redistributed_20)
    assert np.allclose(binary_margin, 0.0)
    assert np.all(redistributed_18_margin[:14] > 0)
    assert np.all(redistributed_20_margin[:16] > 0)

    (path,) = plot_adc_redundancy(
        {
            "14-bit binary": binary_margin,
            "14-bit redistributed (18 stages)": redistributed_18_margin,
            "14-bit redistributed (20 stages)": redistributed_20_margin,
        },
        output_path=tmp_path / "redundancy",
    )
    assert path.name == "redundancy.pdf"
    assert path.read_bytes().startswith(b"%PDF")


def ideal_sar_codes(weights: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Every code's centre converted by an ideal top-plate SAR on ``weights``: the free first
    comparison, each capacitor's step both ways, the comparison after the last; the codes it gives."""
    codes = np.arange(2 * sum(weights) + 2)
    residue = codes + 0.5 - len(codes) / 2
    found = np.zeros_like(codes)
    for weight in weights:
        decision = residue > 0
        found += decision * 2 * weight
        residue = residue - np.where(decision, weight, -weight)
    return codes, found + (residue > 0)


@pytest.mark.parametrize("bits", (10, 11, 12, 13, 14))
def test_every_scheme_reaches_every_code(bits: int) -> None:
    # the decisions' weights of an N-bit converter on its N-1-step DAC: each capacitor's step both
    # ways, then the comparison after the last one switches
    arrays = [CapArrayConfig(n_dac=bits - 1, n_extra=0, redun_strat=RedunStrat.BINARY)] + [
        CapArrayConfig(n_dac=bits - 1, n_extra=extra, redun_strat=scheme)
        for scheme in (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST)
        for extra in range(1, 7)
    ]
    for cdac in arrays:
        weights = get_caparray_weights(cdac)
        assert sum(weights) == 2 ** (bits - 1) - 1  # every scheme the binary total
        margins = _redundancy_margins((*(2 * weight for weight in weights), 1))
        # no stage's error band is lost (a negative margin would be missing codes); the split MSBs
        # and the redistribution give the free first comparison its tolerance, the split LSBs none
        assert np.all(margins >= 0.0), (bits, cdac)
        assert (margins[0] > 0.0) == (cdac.redun_strat in (RedunStrat.MSB_SPLIT, RedunStrat.MSB_REDIST)), cdac
        # and an ideal SAR on the weights converts every code to itself
        codes, found = ideal_sar_codes(weights)
        assert len(codes) == 2**bits and np.array_equal(codes, found), cdac


UNIT_F = 1e-15
CODE_MAX = 63  # six bits: five capacitors and the free first comparison
PARASITIC_F = 30e-15


def _weights(caps) -> np.ndarray:
    return np.r_[2 * np.asarray(caps, dtype=np.float64), 1.0]


def _statistics(main_f, weights) -> AnalysisMismatch:
    """The predicted statistics of one side's nominal array, no difference plates."""
    return AnalysisMismatch(
        group=None,
        index=None,
        dut=None,
        **_mismatch_statistics(main_f, np.zeros_like(main_f), PARASITIC_F, weights, CODE_MAX),
    )


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
    statistics = _statistics(main_f, _weights(main_f / UNIT_F))
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
    assert abs(_dnl_quantile(statistics, unit_mismatch) / worst_dnl - 1) < 0.08
    # the worst INL's half-sum leaves out the codes a comparator before the last one starts, whose
    # INL also carries the later steps of one side: about a tenth low on so short an array
    assert -0.15 < _inl_quantile(statistics, unit_mismatch) / worst_inl - 1 < 0.02
    # the MSB transition spans every capacitor: the largest DNL sigma, from stage 0
    assert np.isclose(statistics.transition_sigma[0], np.max(statistics.dnl_sigma))


def test_redundant_statistics_match_brute_force_draws() -> None:
    # a sub-radix-2 array with every margin at least zero, its weights summing to the code range
    caps = np.array([13, 8, 5, 3, 1, 1], dtype=np.float64)
    main_f = caps * UNIT_F
    unit_mismatch = 0.01
    statistics = _statistics(main_f, _weights(caps))
    assert np.all(statistics.margin_lsb >= 0.0) and statistics.margin_lsb[0] > 0.0
    assert np.all(_margin_over_sigma(statistics, unit_mismatch)[statistics.margin_lsb > 0] > 0.0)
    dnl, inl = _draws(main_f, unit_mismatch, 3000, seed=1)
    worst_dnl = np.percentile(np.max(np.abs(dnl), axis=1), 95)
    worst_inl = np.percentile(np.max(np.abs(inl), axis=1), 95)
    assert abs(_dnl_quantile(statistics, unit_mismatch) / worst_dnl - 1) < 0.10
    assert abs(_inl_quantile(statistics, unit_mismatch) / worst_inl - 1) < 0.15


def test_the_predictions_grow_with_the_mismatch() -> None:
    main_f = np.array([16, 8, 4, 2, 1], dtype=np.float64) * UNIT_F
    statistics = _statistics(main_f, _weights(main_f / UNIT_F))
    coefficients = (0.001, 0.01, 0.1)
    dnl = [_dnl_quantile(statistics, a) for a in coefficients]
    inl = [_inl_quantile(statistics, a) for a in coefficients]
    assert dnl == sorted(dnl) and inl == sorted(inl)
    # tenfold the coefficient, tenfold the worst INL of an array without its own error
    assert np.isclose(inl[1] / inl[0], 10.0, rtol=0.02)
    # missing codes only once the mismatch is a large part of an LSB
    assert _missing_codes_expected(statistics, 0.001) < 1e-6 < _missing_codes_expected(statistics, 0.1)


def test_a_captures_mismatch_is_its_nominal_arrays_statistics() -> None:
    """``analyze_mismatch`` of a behavioral capture: the statistics of its P side's plates (the
    capture's own, a nominal array), its top plate's other load, its design weights and its code
    range, under the capture's identity."""
    main_f = np.array([16, 8, 4, 2, 1], dtype=np.float64) * UNIT_F
    design = Params(adc_bits=6, cdac=CapArrayConfig(n_dac=5, n_extra=0, redun_strat=RedunStrat.BINARY))
    cdac = CdacBehavioralParams(main_p_f=tuple(main_f), diff_p_f=(0.0,) * 5, parasitic_f=PARASITIC_F)
    meas = MeasAdc(
        group=3,
        index=0,
        dut=design,
        info=MeasInfo(backend="behavioral", timestamp_utc=datetime(2026, 1, 1, tzinfo=UTC)),
        param=AdcBehavioralParams(tb=TbParams(dut=design), cdac=cdac),
        conversion_index=np.arange(1),
        bout=np.zeros((1, 6), dtype=np.uint8),
        dout_raw=np.zeros(1, dtype=np.int64),
        dout=np.zeros(1, dtype=np.int64),
        vin_diff_v=np.zeros(1),
    )
    mismatch = analyze_mismatch(meas)
    assert mismatch.identity == meas.identity
    expected = _statistics(main_f, _weights(main_f / UNIT_F))
    for name in ("weight_sigma", "transition_sigma", "margin_lsb", "dnl_sigma", "inl_sigma", "width_codes"):
        np.testing.assert_array_equal(getattr(mismatch, name), getattr(expected, name))
