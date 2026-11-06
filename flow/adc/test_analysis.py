"""The ADC's analyses, software only: each conversion and waveform analysis on built captures
(``adc_measurement`` and its kin, which flow/analysis's tests share), the analyses on an ADC other
than FRIDA, the three calibrations, the ENOB ladder of the campaign (on a model of ideal blocks of
known impairments), the redundancy of a SAR's weights (each scheme's at every resolution), and the
predicted mismatch statistics, which agree with exact draws of the same arrays."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import hdl21 as h
import numpy as np
import pytest
from scipy import constants

import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow import adc, comp
from flow.adc.analysis import (
    _decode,
    _dnl_quantile,
    _inl_quantile,
    _margin_over_sigma,
    _mismatch_statistics,
    _missing_codes_expected,
    _redundancy_margins,
    analyze_calibration1,
    analyze_calibration2,
    analyze_calibration3,
    analyze_cdac_settling,
    analyze_code_density_nonlinearity,
    analyze_code_distribution,
    analyze_code_spectrum,
    analyze_decision_paths,
    analyze_dynamic,
    analyze_endpoint_nonlinearity,
    analyze_interferer,
    analyze_mismatch,
    analyze_mismatch_draws,
    analyze_noise,
    analyze_operating_conditions,
    analyze_power,
    analyze_power_waveform,
    analyze_ramp,
    analyze_sampling_noise,
    analyze_timing_closure,
    analyze_transfer,
)
from flow.adc.model import AdcBehavioralParams, CdacBehavioralParams
from flow.adc.params import LADDER, LADDER_NAMES, Params, TbParams
from flow.adc.plots import plot_redundancy
from flow.adc.sim import SEQUENCES, AdcSequence
from flow.adc.subckt import calc_ideal_capacitances
from flow.adc.sweep import _extracted, _ladder, campaign
from flow.adc.types import AnalysisMismatch, AnalysisRedundancy
from flow.analysis.calc import calc_drawn_linearity, calc_paths
from flow.analysis.cdac import analyze_cdac_cap_mismatch, analyze_cdac_decisions, analyze_cdac_transition
from flow.analysis.plots import plot_adc_calibration_weights
from flow.analysis.test_cdac import comparator_offset
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
    Identity,
    MeasAdc,
    MeasCdac,
    MeasInfo,
    Wave,
)
from flow.cdac.caparray.model import calc_capacitor_mismatch
from flow.cdac.caparray.subckt import CapArrayConfig, RedunStrat, get_caparray_weights
from flow.plot import render
from flow.scans.params import AdcScanParams
from flow.scans.scan_cdac import _build_cdac_params


def redundancy_of(margins: np.ndarray) -> AnalysisRedundancy:
    """A redundancy result of bare margins (``_redundancy_margins``), as ``analyze_redundancy`` gives
    one, the design's and the calibration's the same."""
    return AnalysisRedundancy(group=None, index=None, dut=None, design_pct=margins, calibrated_pct=margins)


def test_redundancy_calculator(tmp_path: Path) -> None:
    # q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1} over sum_{j=k}^{M-1} w_j (Ogawa et al., IEICE 2010, Eq. 5)
    margins = _redundancy_margins((4, 3, 2, 1))
    assert margins.tolist() == pytest.approx((30.0, 100 / 6, 0.0, 0.0))
    # binary weights tolerate nothing; one more LSB decision tolerates one LSB weight at each stage
    assert _redundancy_margins((8, 4, 2, 1)).tolist() == pytest.approx((0.0,) * 4)
    assert _redundancy_margins((8, 4, 2, 1, 1)).tolist() == pytest.approx((6.25, 12.5, 25.0, 50.0, 0.0))
    with pytest.raises(ValueError, match="positive SAR weights"):
        _redundancy_margins((4, 0, 1))
    # drawn by the redundancy figure, a point a stage
    figure = plot_redundancy(redundancy_of(margins))
    assert figure.x == [0.0, 1.0, 2.0, 3.0] and figure.series == {"Design weights": [30.0, 16.6667, 0.0, 0.0]}
    (path,) = render(figure, tmp_path / "single")
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

    # each array its own figure (one curve a plot: compared, they overlay as instances)
    for name, margin in (
        ("binary", binary_margin),
        ("redistributed_18", redistributed_18_margin),
        ("redistributed_20", redistributed_20_margin),
    ):
        figure = plot_redundancy(redundancy_of(margin))
        assert figure.x == [float(stage) for stage in range(len(margin))] and figure.x_ticks == "step"
        (path,) = render(figure, tmp_path / f"redundancy_{name}")
        assert path.name == f"redundancy_{name}.pdf"
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


def test_the_mismatch_draws_gather_each_ramp_by_its_coefficient() -> None:
    """The Monte Carlo check of the predicted mismatch: each drawn ramp's worst |DNL| and |INL| and
    missing codes, a row a Pelgrom coefficient (ascending) and a column a draw, under their design."""
    base = adc_ramp_measurement()
    draws = [
        replace(base, group=100 + draw, info=replace(base.info, readbacks={"unit_mismatch": coefficient}))
        for coefficient in (0.002, 0.001)
        for draw in range(2)
    ]
    ramps = [analyze_ramp(measurement) for measurement in draws]
    result = analyze_mismatch_draws(draws, ramps=ramps)
    assert result.coefficient.tolist() == [0.001, 0.002]
    assert result.dnl_lsb.shape == result.inl_lsb.shape == result.missing_codes.shape == (2, 2)
    assert (result.group, result.index, result.dut) == (None, None, base.dut)
    np.testing.assert_array_equal(result.inl_lsb[0], [ramps[2].maximum_abs_inl, ramps[3].maximum_abs_inl])
    with pytest.raises(ValueError, match="one ramp analysis a capture"):
        analyze_mismatch_draws(draws, ramps=ramps[:1])


# ---- the conversion and waveform analyses, on built captures

timing_sequences = tuple(
    sequence for name, sequence in SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")
)


def adc_sampling_measurement() -> MeasAdc:
    """Three held samples with known differential spread and common fast ripple."""

    template = adc_measurement([0, 0, 0], internal=True, sample_rate_hz=1e8, waveform_sample_count=101)
    assert template.wave is not None
    assert isinstance(template, MeasAdc)
    wave = template.wave
    assert wave is not None
    repeated = {name: np.repeat(value, 3, axis=0) for name, value in wave.v.items()}
    sample = np.tile(np.where(wave.time_s < 2e-9, 1.2, 0.0), (3, 1))
    comp = np.tile(np.where(wave.time_s < 5e-9, 0.0, 1.2), (3, 1))
    ripple = 1e-3 * np.sin(wave.time_s * 2e9 * np.pi)
    repeated.update(
        seq_samp=sample,
        seq_comp=comp,
        clk_comp=comp,
        clk_samp_p=sample,
        clk_samp_n=sample,
        clk_samp_p_b=1.2 - sample,
        clk_samp_n_b=1.2 - sample,
        vin_p=np.full_like(sample, 0.725),
        vin_n=np.full_like(sample, 0.675),
        vdac_p=0.725 + np.array([-1e-4, 0, 1e-4])[:, None] + ripple,
        vdac_n=np.full_like(sample, 0.675),
    )
    return replace(
        template,
        wave=replace(
            wave,
            record_index=np.arange(3),
            v=repeated,
            i={name: np.repeat(value, 3, axis=0) for name, value in wave.i.items()},
        ),
    )


def test_sampling_noise_interpolates_exactly_one_ns_after_each_sample_edge() -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    edges_s = np.asarray([1.93e-9, 2.17e-9, 2.41e-9])
    sample = np.clip(0.6 + (edges_s[:, None] - wave.time_s) * 1e9, 0.0, 1.2)
    offsets = np.asarray([-1e-4, 0.0, 1e-4])
    vp = 0.725 + offsets[:, None] + wave.time_s * 1e6
    analysis = analyze_sampling_noise(
        replace(measurement, wave=replace(wave, v={**wave.v, "seq_samp": sample, "vdac_p": vp}))
    )
    expected_times = edges_s + 1e-9
    np.testing.assert_allclose(analysis.window_start_s, expected_times, rtol=0, atol=1e-23)
    np.testing.assert_array_equal(analysis.window_start_s, analysis.window_stop_s)
    np.testing.assert_allclose(analysis.held_diff_v, 0.05 + offsets + expected_times * 1e6)
    assert analysis.sigma_v == pytest.approx(np.std(offsets + expected_times * 1e6, ddof=1))


@pytest.mark.parametrize("comp_level", (0.0, 1.2))
def test_sampling_noise_accepts_comparator_already_fired_or_inactive(comp_level) -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    clocks = np.full_like(measurement.wave.v["seq_comp"], comp_level)
    analysis = analyze_sampling_noise(
        replace(
            measurement,
            wave=replace(measurement.wave, v={**measurement.wave.v, "seq_comp": clocks, "clk_comp": clocks}),
        )
    )
    assert len(analysis.held_diff_v) == 3
    assert analysis.sigma_v == pytest.approx(100e-6)


def test_sampling_noise_does_not_extrapolate_past_saved_record() -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    sample = np.tile(np.where(wave.time_s < wave.time_s[-1] - 0.5e-9, 1.2, 0.0), (3, 1))
    with pytest.raises(ValueError, match="outside the waveform"):
        analyze_sampling_noise(replace(measurement, wave=replace(wave, v={**wave.v, "seq_samp": sample})))


def test_sampling_noise_rejects_changing_input_and_missing_sample_edge() -> None:
    measurement = adc_sampling_measurement()
    assert measurement.wave is not None
    with pytest.raises(ValueError, match="fixed differential input"):
        analyze_sampling_noise(
            replace(
                measurement,
                wave=replace(measurement.wave, v={**measurement.wave.v, "vin_p": measurement.wave.v["vdac_p"]}),
            )
        )
    with pytest.raises(ValueError, match="SAMP falling edge"):
        analyze_sampling_noise(
            replace(
                measurement,
                wave=replace(
                    measurement.wave,
                    v={
                        **measurement.wave.v,
                        "seq_samp": np.zeros_like(measurement.wave.v["seq_samp"]),
                    },
                ),
            )
        )


def adc_measurement(
    dout,
    *,
    vin_diff_v: float | Sequence[float] | np.ndarray = 0.0,
    sample_rate_hz: float = 1.0e6,
    input_frequency_hz: float = 10.0e3,
    logic_phase_delay_symbols: float = 0.0,
    observed_adc: int | None = None,
    readbacks: Mapping[str, str | int | float | bool] | None = None,
    internal: bool = False,
    waveform_sample_count: int = 8,
) -> MeasAdc:
    """Build one compact external or internal ADC measurement for numerical tests."""

    dout = np.asarray(dout, dtype=np.int64)
    vin_diff_array = np.asarray(vin_diff_v, dtype=np.float64)
    if vin_diff_array.ndim == 0:
        vin_diff_array = np.full(len(dout), vin_diff_array.item())
    template = adc.TbParams()
    measurement_selection = {}
    if observed_adc is not None:
        measurement_selection = {
            "board_id": 7,
            "observed_adc": observed_adc,
            "active_adc_mask": tuple(int(index == observed_adc) for index in reversed(range(16))),
        }
    tb_params = adc.TbParams(
        conversions=len(dout),
        symbol_rate=sample_rate_hz * len(template.seq_init_pattern),
        vin_diff=h.Vsin.Params(voff=0.0, vamp=0.5, freq=input_frequency_hz),
        seq_logic_pattern=timing_sequences[int(logic_phase_delay_symbols) + 3].logic,
    )
    time_s = np.linspace(0.0, 1.0 / sample_rate_hz, waveform_sample_count)
    zeros = np.zeros((1, len(time_s)))
    daq = {
        "conversion_index": np.arange(len(dout)),
        "bout": np.zeros((len(dout), 17), dtype=np.uint8),
        "dout_raw": dout,
        "dout": dout,
        "vin_diff_v": vin_diff_array,
    }
    if internal:
        return MeasAdc(
            group=tb_params.mc_seed,
            index=tb_params.mc_index,
            dut=tb_params.dut,
            info=MeasInfo(
                backend="spice", timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC), readbacks=dict(readbacks or {})
            ),
            param=tb_params,
            **daq,
            wave=Wave(
                record_index=np.asarray([0], dtype=np.int64),
                time_s=time_s,
                v={
                    "seq_comp": zeros,
                    "seq_logic": zeros,
                    "comp_out": zeros,
                    "vin_p": zeros,
                    "vin_n": zeros,
                    "seq_init": zeros,
                    "seq_samp": zeros,
                    "vdac_p": zeros,
                    "vdac_n": zeros,
                    "clk_samp_p": zeros,
                    "clk_samp_p_b": zeros,
                    "clk_samp_n": zeros,
                    "clk_samp_n_b": zeros,
                    "clk_comp": zeros,
                    "comp_out_p": zeros,
                    "comp_out_n": zeros,
                    "dac_state_p[0]": zeros,
                    "dac_state_p[7]": zeros,
                    "dac_state_p[15]": zeros,
                    "dac_state_n[0]": zeros,
                    "dac_state_n[7]": zeros,
                    "dac_state_n[15]": zeros,
                    "dac_botplate_p[0]": zeros,
                    "dac_botplate_p[7]": zeros,
                    "dac_botplate_p[15]": zeros,
                    "dac_botplate_n[0]": zeros,
                    "dac_botplate_n[7]": zeros,
                    "dac_botplate_n[15]": zeros,
                },
                i={"vdd_a": zeros, "vdd_d": zeros, "vdd_dac": zeros},
            ),
        )
    return MeasAdc(
        group=7 if observed_adc is not None else None,
        index=observed_adc,
        dut=tb_params.dut,
        info=MeasInfo(
            backend="behavioral", timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC), readbacks=dict(readbacks or {})
        ),
        param=AdcScanParams(tb=tb_params, **measurement_selection),
        **daq,
        wave=Wave(
            record_index=np.asarray([0], dtype=np.int64),
            time_s=time_s,
            v={"vin_diff": zeros, "seq_comp": zeros, "seq_logic": zeros, "comp_out": zeros},
        ),
    )


def adc_cdac_settling_measurement() -> MeasAdc:
    """Build one compact internal waveform with three representative CDAC updates."""

    base = adc_measurement([2_048], internal=True)
    assert base.wave is not None
    assert isinstance(base, MeasAdc)
    time_s = np.arange(0.0, 18.51e-9, 10e-12)
    zeros = np.zeros((1, len(time_s)))
    comp_edges_s = 0.5e-9 + np.arange(17) * 1e-9
    logic_edges_s = 0.9e-9 + np.arange(16) * 1e-9

    def pulse_train(edges_s: np.ndarray, width_s: float) -> np.ndarray:
        values = np.zeros_like(time_s)
        for edge_s in edges_s:
            values[(time_s >= edge_s) & (time_s < edge_s + width_s)] = 1.2
        return values

    seq_comp_v = pulse_train(comp_edges_s, 0.3e-9)
    seq_logic_v = pulse_train(logic_edges_s, 0.2e-9)
    comp_out_p_v = np.zeros_like(time_s)
    for cycle, edge_s in enumerate(comp_edges_s):
        comp_out_p_v[time_s >= edge_s + 0.08e-9] = 1.2 * (cycle % 2)
    comp_out_n_v = 1.2 - comp_out_p_v

    wave_values = {name: zeros for name in base.wave.v}
    vdac_p_v = np.full_like(time_s, 0.7)
    vdac_n_v = np.full_like(time_s, 0.7)
    for stage_index, cycle_index, step_v in ((0, 0, 0.12), (7, 7, -0.04), (15, 15, 0.01)):
        logic_edge_s = logic_edges_s[cycle_index]
        switched = time_s >= logic_edge_s
        settling = np.zeros_like(time_s)
        settling[switched] = step_v * (1.0 - np.exp(-(time_s[switched] - logic_edge_s) / 0.05e-9))
        vdac_p_v += settling
        vdac_n_v -= settling
        state_p_v = np.where(switched, 1.2, 0.0)
        state_n_v = 1.2 - state_p_v
        bottom_switched = time_s >= logic_edge_s + 0.05e-9
        wave_values[f"dac_state_p[{stage_index}]"] = state_p_v[None, :]
        wave_values[f"dac_state_n[{stage_index}]"] = state_n_v[None, :]
        wave_values[f"dac_botplate_p[{stage_index}]"] = np.where(bottom_switched, 1.2, 0.0)[None, :]
        wave_values[f"dac_botplate_n[{stage_index}]"] = np.where(bottom_switched, 0.0, 1.2)[None, :]

    wave_values.update(
        {
            "seq_comp": seq_comp_v[None, :],
            "clk_comp": seq_comp_v[None, :],
            "seq_logic": seq_logic_v[None, :],
            "comp_out": comp_out_p_v[None, :],
            "comp_out_p": comp_out_p_v[None, :],
            "comp_out_n": comp_out_n_v[None, :],
            "vdac_p": vdac_p_v[None, :],
            "vdac_n": vdac_n_v[None, :],
        }
    )
    wave = Wave(
        record_index=np.asarray([0]),
        time_s=time_s,
        v={
            **wave_values,
            "comp.latch_p": (1.2 - 0.5 * seq_comp_v)[None, :],
            "comp.latch_n": (1.2 - 0.8 * seq_comp_v)[None, :],
        },
        i={key: zeros for key in base.wave.i},
    )
    return replace(base, wave=wave)


def adc_ramp_measurement(*, cycles: int = 4, observed_adc: int = 0, start_offset: int = 0) -> MeasAdc:
    """Build a repeated monotonic decision ramp whose PWL period matches its capture.

    ``start_offset`` delays the capture start relative to the ramp, so the
    first wrap occurs ``samples_per_cycle - start_offset`` conversions in.
    """

    samples_per_cycle = 4_096
    nominal_weights = np.asarray(
        [2 * value for value in (768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1)] + [1]
    )
    # Convert an ideal linear ramp with a greedy SAR search; the redundant
    # weights represent every raw code, so DOUT_RAW equals BOUT @ weights.
    remaining = np.rint(np.linspace(0.0, np.sum(nominal_weights), samples_per_cycle)).astype(np.int64)
    one_cycle_bout = np.zeros((samples_per_cycle, len(nominal_weights)), dtype=np.uint8)
    for decision, weight in enumerate(nominal_weights):
        one_cycle_bout[:, decision] = remaining >= weight
        remaining -= one_cycle_bout[:, decision] * weight
    bout = np.roll(np.tile(one_cycle_bout, (cycles, 1)), -start_offset, axis=0).astype(np.uint8, copy=False)
    sample_count = len(bout)
    dout_raw = bout @ nominal_weights
    dout = np.rint(dout_raw * 4_095 / np.sum(nominal_weights)).astype(np.int64)
    vin_diff_v = np.tile(np.linspace(-1.0, 1.0, samples_per_cycle, endpoint=False), cycles)
    base = adc_measurement(np.zeros(sample_count, dtype=np.int64), observed_adc=observed_adc)
    assert isinstance(base, MeasAdc)
    params = AdcScanParams(
        tb=adc.TbParams(
            dut=base.param.tb.dut,
            conversions=sample_count,
            symbol_rate=base.param.tb.symbol_rate,
            vin_cm=h.Vdc.Params(dc=0.6),
            vin_diff=h.Vpwl.Params(wave=f"0 -1 {samples_per_cycle / base.sample_rate_hz:.12g} 1"),
        ),
        board_id=7,
        observed_adc=observed_adc,
        active_adc_mask=tuple(int(index == observed_adc) for index in reversed(range(16))),
        campaign="adc_ramp",
    )
    return replace(
        base,
        param=params,
        conversion_index=np.arange(sample_count),
        bout=bout,
        dout_raw=dout_raw,
        dout=dout,
        vin_diff_v=vin_diff_v,
    )


def test_dynamic_analysis_recovers_sine_and_spectral_metrics() -> None:
    rng = np.random.default_rng(12345)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 20_000
    amplitude = 1_500.0
    offset = 2_040.0
    phase = 0.37
    noise_rms = 2.0
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = np.rint(
        offset
        + amplitude * np.sin(2.0 * np.pi * input_frequency_hz * time_s + phase)
        + rng.normal(0.0, noise_rms, sample_count)
    )
    msmt = adc_measurement(
        samples,
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz * (1.0 + 5e-6),
    )
    result = analyze_dynamic(msmt)

    assert result.sample_count == sample_count
    assert result.fitted_frequency_hz == pytest.approx(input_frequency_hz, abs=0.02)
    assert result.amplitude_dout == pytest.approx(amplitude, rel=2e-4)
    assert result.offset_dout == pytest.approx(offset, abs=0.05)
    assert result.phase_rad == pytest.approx(phase, abs=2e-4)
    assert result.residual_rms_dout == pytest.approx(math.hypot(noise_rms, 1 / math.sqrt(12)), rel=0.05)
    assert result.input_referred_residual_rms_v == pytest.approx(result.residual_rms_dout * 0.5 / result.amplitude_dout)
    assert result.input_referred_noise_rms_v > 0
    assert result.enob_bits == pytest.approx((result.sinad_db - 1.76) / 6.02)
    assert len(result.fitted_dout) == sample_count


def test_dynamic_analysis_counts_sine_fit_residual_tails() -> None:
    """Count residuals beyond three fitted sigma without deleting samples."""

    sample_rate_hz = 1.0e6
    input_frequency_hz = 15_625.0
    time_s = np.arange(8_192) / sample_rate_hz
    samples = np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s))
    samples[1_234] += 40.0
    samples[4_321] -= 40.0
    msmt = adc_measurement(
        samples,
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz,
    )

    result = analyze_dynamic(msmt)
    assert result.residual_tail_limit_dout == pytest.approx(3.0 * result.residual_rms_dout)
    assert result.expected_residual_tail_count == pytest.approx(len(samples) * math.erfc(3.0 / math.sqrt(2.0)))
    assert result.negative_residual_tail_count == 1
    assert result.positive_residual_tail_count == 1
    assert result.maximum_abs_residual_dout > 39.0


def test_dynamic_analysis_separates_noise_and_harmonics() -> None:
    rng = np.random.default_rng(7)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 65_536
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = np.rint(
        2_048.0
        + 1_500.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s + 0.2)
        + 15.0 * np.sin(2.0 * np.pi * 2.0 * input_frequency_hz * time_s - 0.1)
        + rng.normal(0.0, 1.0, sample_count)
    )
    result = analyze_dynamic(
        adc_measurement(
            samples,
            sample_rate_hz=sample_rate_hz,
            input_frequency_hz=input_frequency_hz,
        )
    )

    assert result.spectral_snr_db == pytest.approx(59.9, abs=0.5)
    assert result.spectral_thd_db == pytest.approx(-40.0, abs=0.15)
    assert result.spectral_sfdr_db == pytest.approx(40.0, abs=0.15)
    assert result.spectral_sndr_db == pytest.approx(39.96, abs=0.2)
    # referred to full scale, the same SNDR plus the sine's distance below it
    assert result.spectral_enob_fs_bits == pytest.approx(result.spectral_enob_bits - result.amplitude_dbfs / 6.02)


def sar_sine_measurement(
    adc_bits: int, cdac: CapArrayConfig, *, spread: float
) -> tuple[MeasAdc, adc.AnalysisCalibration]:
    """An ideal SAR converting a coherent -0.5 dBFS sine (8,192 conversions): no noise, no
    distortion, its capacitors off their design values by a fixed draw of relative sigma
    ``spread``, and the calibration that knows those weights (a perfect extraction). Its stored
    DOUT decodes the decisions with the design weights."""

    code_max = (1 << adc_bits) - 1
    sample_rate_hz, count, cycles = 10.0e6, 8_192, 1_021
    dut = adc.Params(adc_bits=adc_bits, cdac=cdac)
    template = adc_measurement([0], sample_rate_hz=sample_rate_hz, input_frequency_hz=sample_rate_hz * cycles / count)
    nominal = replace(template, dut=dut).nominal_bout_weights
    capacitors = 1.0 + spread * np.random.default_rng(1).standard_normal(len(nominal) - 1)
    weights = nominal * np.append(capacitors, 1.0)
    weights *= code_max / np.sum(weights)
    # the input in codes; each decision compares it with the DAC, which moves half a weight either way
    sine = 10 ** (-0.5 / 20) * code_max / 2 * np.sin(2 * np.pi * cycles / count * np.arange(count) + 0.3)
    dac = np.zeros(count)
    bout = np.zeros((count, len(weights)), dtype=np.uint8)
    for decision, weight in enumerate(weights):
        bout[:, decision] = sine > dac
        dac += np.where(sine > dac, weight, -weight) / 2
    dout = bout.astype(np.int64) @ nominal
    tb = adc.TbParams(
        dut=dut,
        conversions=count,
        symbol_rate=template.tb.symbol_rate,
        vin_diff=template.tb.vin_diff,
        seq_logic_pattern=template.tb.seq_logic_pattern,
    )
    measurement = replace(
        adc_measurement(dout, sample_rate_hz=sample_rate_hz, input_frequency_hz=sample_rate_hz * cycles / count),
        dut=dut,
        param=AdcScanParams(tb=tb),
        bout=bout,
    )
    calibration = adc.AnalysisCalibration(
        group=measurement.group,
        index=measurement.index,
        dut=dut,
        method="extracted",
        label="The capacitors' own weights",
        code_max=code_max,
        nominal_weights=nominal * code_max / np.sum(nominal),
        calibrated_weights=weights,
        measured_weight_mask=np.append(np.ones(len(capacitors), dtype=np.bool_), False),
        training_sample_count=0,
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )
    return measurement, calibration


@pytest.mark.parametrize(
    ("adc_bits", "cdac"), [(10, CapArrayConfig(n_dac=9, n_extra=3)), (12, CapArrayConfig())], ids=["10b", "12b"]
)
def test_an_ideal_quantizer_reads_its_resolution_referred_to_full_scale(adc_bits: int, cdac: CapArrayConfig) -> None:
    """Quantization alone is the design resolution: decoded unrounded and referred to full scale."""

    # an ideal N-bit quantizer: the design weights, whole codes
    ideal, _ = sar_sine_measurement(adc_bits, cdac, spread=0.0)
    np.testing.assert_array_equal(ideal.dout, np.rint(ideal.dout))
    result = analyze_dynamic(ideal)
    assert result.amplitude_dbfs == pytest.approx(-0.5, abs=0.01)
    assert result.spectral_enob_fs_bits == pytest.approx(adc_bits, abs=0.02)
    # at the test sine's own amplitude it reads half a dB less
    assert result.spectral_enob_bits == pytest.approx(adc_bits - 0.5 / 6.02, abs=0.02)

    # capacitors off their design values: its own weights put each code between whole ones
    measurement, calibration = sar_sine_measurement(adc_bits, cdac, spread=0.003)
    fractional = _decode(measurement.bout, calibration, rounded=False)
    assert np.std(fractional - np.rint(fractional)) > 0.2
    calibrated = analyze_dynamic(measurement, calibration=calibration)
    np.testing.assert_array_equal(calibrated.measured_dout, fractional)
    assert calibrated.spectral_enob_fs_bits == pytest.approx(adc_bits, abs=0.02)
    # whole codes, as an N-bit output word carries them, quantize a second time
    whole = analyze_dynamic(replace(measurement, dout=_decode(measurement.bout, calibration)))
    assert whole.spectral_enob_fs_bits < adc_bits - 0.3


def test_transfer_noise_and_code_density_use_typed_adc_data() -> None:
    msmt = adc_measurement(
        [0, 0, 1, 2, 3, 3],
        vin_diff_v=[-0.1, -0.1, 0.0, 0.0, 0.1, 0.1],
    )
    transfer = analyze_transfer([msmt])
    noise = analyze_code_distribution([msmt])
    linearity = analyze_code_density_nonlinearity(msmt)

    np.testing.assert_allclose(transfer.mean_dout, (0.0, 1.5, 3.0))
    np.testing.assert_array_equal(noise.count.sum(axis=0)[:4], (2, 1, 1, 2))
    # The end codes are excluded; codes 1 and 2 hold one conversion each.
    assert linearity.code[0] == 1
    np.testing.assert_array_equal(linearity.count[:3], (1, 1, 2))
    assert linearity.retained_sample_count == linearity.sample_count == 6


def test_ramp_analysis_derives_period_and_fits_phase_without_detecting_jumps() -> None:
    """Fit the wrap phase instead of assuming the AWG and capture start together."""

    measurement = adc_ramp_measurement()
    analysis = analyze_ramp(measurement)

    assert (analysis.group, analysis.index, analysis.dut) == (7, 0, measurement.dut)
    assert analysis.sample_count == 4 * 4_096
    assert analysis.period_conversions == pytest.approx(4_096, rel=1e-6)
    assert analysis.ramp_frequency_hz == pytest.approx(analysis.sample_rate_hz / 4_096, rel=1e-6)
    assert analysis.decoding == "uncalibrated_dout"
    assert analysis.label == "Ideal weights"
    assert analysis.retained_sample_count == analysis.sample_count - analysis.reset_excluded_sample_count
    assert analysis.count.sum() == analysis.retained_sample_count
    # Bins whose only conversions sit beside a wrap stay empty; all others are populated.
    assert 4_096 - 9 <= len(analysis.transfer_vin_diff_v) <= 4_096


@pytest.mark.parametrize("start_offset", (1_000, 2_917))
def test_ramp_analysis_recovers_random_phase_and_its_retained_mask(start_offset: int) -> None:
    analysis = analyze_ramp(adc_ramp_measurement(start_offset=start_offset))
    first_wrap = 4_096 - start_offset
    assert analysis.first_wrap_conversion == pytest.approx(first_wrap, abs=1.0)
    expected = np.ones(analysis.sample_count, dtype=bool)
    for wrap in analysis.reset_conversion_index:
        expected[max(0, wrap - 1) : wrap + 8] = False
    np.testing.assert_array_equal(analysis.retained, expected)
    assert abs(int(analysis.reset_conversion_index[0]) - first_wrap) <= 1


def test_ramp_analysis_of_a_nominal_simulation_has_no_instance() -> None:
    measurement = adc_ramp_measurement()
    simulated = replace(
        measurement,
        group=None,
        index=None,
        param=replace(
            measurement.param,
            board_id=None,
            observed_adc=None,
            active_adc_mask=None,
        ),
    )

    analysis = analyze_ramp(simulated)

    assert analysis.group is None and analysis.index is None


def test_ramp_analysis_redecodes_with_common_calibration_weights() -> None:
    """Apply any calibration result to stored decisions without new HDF5."""

    measurement = adc_ramp_measurement()
    nominal = analyze_ramp(measurement).weights.astype(np.float64)
    nominal *= 4095.0 / np.sum(nominal)
    calibrated = nominal.copy()
    calibrated[:2] *= (1.02, 0.97)
    calibrated *= 4095.0 / np.sum(calibrated)
    calibration = adc.AnalysisCalibration(
        group=7,
        index=0,
        dut=measurement.dut,
        method="calibration1",
        label="Synthetic calibrated BOUT",
        code_max=4095,
        nominal_weights=nominal,
        calibrated_weights=calibrated,
        measured_weight_mask=np.ones(17, dtype=np.bool_),
        training_sample_count=100,
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )

    uncalibrated = analyze_ramp(measurement)
    analysis = analyze_ramp(measurement, calibration=calibration)

    assert (analysis.decoding, analysis.label) == ("calibration1", "Synthetic calibrated BOUT")
    # Every decoding of one capture shares the nominal phase fit and its retained conversions.
    np.testing.assert_array_equal(analysis.retained, uncalibrated.retained)
    assert analysis.count.sum() == uncalibrated.count.sum() == analysis.retained_sample_count
    assert not np.array_equal(uncalibrated.weights, analysis.weights)
    assert analysis.weights[0] == pytest.approx(calibrated[0])
    decoded = _decode(measurement.bout, calibration)
    distribution = analyze_code_distribution([measurement], calibration=calibration)
    nonlinearity = analyze_code_density_nonlinearity(measurement, calibration=calibration)
    assert distribution.count.sum() == len(decoded)
    assert nonlinearity.count.sum() == np.count_nonzero((decoded >= 1) & (decoded <= 4094))
    with pytest.raises(ValueError, match="does not match"):
        analyze_ramp(measurement, calibration=replace(calibration, index=1))
    with pytest.raises(ValueError, match="does not match"):
        analyze_ramp(measurement, calibration=replace(calibration, dut=replace(measurement.dut, adc_bits=10)))

    # Code-density nonlinearity reuses the ramp's single wrap-exclusion mask.
    ramp = analyze_ramp(measurement)
    retained = analyze_code_density_nonlinearity(measurement, ramp=ramp)
    assert retained.retained_sample_count == ramp.retained_sample_count
    counts = np.bincount(measurement.dout[ramp.retained], minlength=4096)[1:4095]
    np.testing.assert_array_equal(retained.count, counts)


def test_shared_adc_analyses_accept_internal_measurements() -> None:
    """Analyze simulated ADC data through the same public entry points."""

    static = adc_measurement(
        [0, 0, 1, 2, 3, 3],
        vin_diff_v=[-0.1, -0.1, 0.0, 0.0, 0.1, 0.1],
        internal=True,
    )
    assert isinstance(static, MeasAdc)
    assert analyze_transfer([static]).sample_count.sum() == 6
    assert analyze_code_distribution([static]).sample_count.sum() == 6
    assert analyze_code_density_nonlinearity(static).retained_sample_count == 6

    sample_rate_hz = 100_000.0
    input_frequency_hz = 1_000.0
    time_s = np.arange(2_048) / sample_rate_hz
    dynamic = adc_measurement(
        np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s)),
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz,
        internal=True,
    )
    assert analyze_dynamic(dynamic).sample_count == len(time_s)


def test_endpoint_nonlinearity_uses_first_contact_and_omits_unbracketed_endpoints() -> None:
    # Mean codes are [0, 0.5, 0.5, 1.5, 3.5]. The first plateau is
    # reached at input 1; the final 3.5 threshold has no saved crossing.
    measurement = adc_measurement([0, 0, 1, 0, 1, 1, 2, 3, 4], vin_diff_v=[0, 1, 1, 2, 2, 3, 3, 4, 4])
    analysis = analyze_endpoint_nonlinearity(measurement)
    np.testing.assert_array_equal(analysis.code, [1, 2])
    np.testing.assert_allclose(analysis.transition_vin_diff_v, [3.0, 3.5])
    assert analysis.endpoint_lsb_v == pytest.approx(1.25)


def test_endpoint_linearity_interpolates_static_code_transitions() -> None:
    inputs = np.linspace(-0.6, 0.6, 129)
    ideal_codes = np.rint(np.linspace(0.0, 15.0, len(inputs)))
    ideal = analyze_endpoint_nonlinearity(adc_measurement(ideal_codes, vin_diff_v=inputs))
    assert ideal.endpoint_lsb_v == pytest.approx(0.08, abs=0.01)
    assert ideal.missing_codes == 0

    nonlinear_codes = np.rint(
        np.linspace(0.0, 15.0, len(inputs)) + 0.6 * np.sin(np.pi * np.linspace(0.0, 15.0, len(inputs)) / 15.0)
    )
    nonlinear = analyze_endpoint_nonlinearity(adc_measurement(nonlinear_codes, vin_diff_v=inputs))
    assert nonlinear.maximum_abs_inl > 0.05


def test_decision_paths_keep_every_conversion() -> None:
    msmt = adc_measurement([5, 5, 3])
    bout = np.asarray(
        [
            [1, 0, 1] + [0] * 14,
            [1, 0, 1] + [0] * 14,
            [0, 1, 1] + [0] * 14,
        ],
        dtype=np.uint8,
    )
    object.__setattr__(msmt, "bout", bout)
    paths = analyze_decision_paths(msmt)

    assert paths.estimate_dout.shape == (3, 18)
    np.testing.assert_array_equal(paths.final_dout, (5, 5, 3))


def test_cdac_settling_aligns_saved_stages_and_removes_static_levels() -> None:
    measurement = adc_cdac_settling_measurement()
    result = analyze_cdac_settling(measurement)
    assert result.comp_latch_p_v is not None
    assert result.comp_latch_n_v is not None
    np.testing.assert_allclose(result.comp_latch_p_v, 1.2 - 0.5 * result.clk_comp_v)
    np.testing.assert_allclose(result.comp_latch_n_v, 1.2 - 0.8 * result.clk_comp_v)

    assert result.stage_index.tolist() == [0, 7, 15]
    assert result.cycle_index.tolist() == [0, 7, 15]
    assert result.conversion_index.tolist() == [0, 0, 0]
    assert result.time_s[0] == pytest.approx(-0.05e-9, abs=15e-12)
    assert result.time_s[-1] == pytest.approx(1.35e-9, abs=15e-12)
    assert 0.0 in result.time_s
    assert result.clk_comp_v.shape == (3, len(result.time_s))
    settled = (result.time_s >= 0.85e-9) & (result.time_s <= 0.97e-9)
    np.testing.assert_allclose(np.median(result.vdac_p_settling_error_v[:, settled], axis=1), 0.0, atol=1e-6)
    np.testing.assert_allclose(np.median(result.vdac_n_settling_error_v[:, settled], axis=1), 0.0, atol=1e-6)
    np.testing.assert_allclose(result.vdac_p_settling_s, result.vdac_n_settling_s, atol=10e-12)
    assert np.all((result.vdac_p_settling_s > 0.1e-9) & (result.vdac_p_settling_s < 0.3e-9))


def test_cdac_settling_keeps_final_pulse_cut_by_record_boundary() -> None:
    measurement = adc_cdac_settling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    selected = wave.time_s < 16.7e-9
    shortened = replace(
        wave,
        time_s=wave.time_s[selected],
        v={name: values[:, selected] for name, values in wave.v.items()},
        i={name: values[:, selected] for name, values in wave.i.items()},
    )
    result = analyze_cdac_settling(replace(measurement, wave=shortened))
    assert result.stage_index.tolist() == [0, 7, 15]
    assert 1.1e-9 < result.time_s[-1] < 1.21e-9
    assert np.all(result.clk_comp_v[:, -1] > 0.6)


def test_cdac_settling_rejects_missing_reset_inside_record() -> None:
    measurement = adc_cdac_settling_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    comp = wave.v["clk_comp"].copy()
    comp[:, wave.time_s >= 16.5e-9] = 1.2
    with pytest.raises(ValueError, match="cycle 16.*reset edge"):
        analyze_cdac_settling(replace(measurement, wave=replace(wave, v={**wave.v, "clk_comp": comp})))


def test_decision_paths_normalize_redundant_raw_weights() -> None:
    """Keep the running estimate in nominal ADC LSB for non-4095 raw sums."""

    msmt = adc_measurement([4095])
    weights = (768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)
    object.__setattr__(
        msmt,
        "param",
        replace(
            msmt.param,
            tb=replace(
                msmt.param.tb,
                dut=adc.Params(
                    adc_bits=12,
                    cdac=CapArrayConfig(n_dac=11, n_extra=5, weights=weights),
                ),
            ),
        ),
    )
    object.__setattr__(msmt, "bout", np.ones((1, 17), dtype=np.uint8))

    paths = analyze_decision_paths(msmt)

    assert paths.estimate_dout[0, 0] == pytest.approx(2047.5)
    assert paths.estimate_dout[0, -1] == pytest.approx(4095.0)


def test_sequence_logic_timing_uses_the_full_crossing_span() -> None:
    comp = "".join("1" if index in (0, 2, 6, 18) else "0" for index in range(24))
    logic = "".join("1" if index in (1, 3, 7) else "0" for index in range(24))
    # Four COMP rises span 18 symbols: the average period is six rather
    # than the median spacing of four. LOGIC remains one symbol after COMP.
    sequence = AdcSequence(init="1" + "0" * 23, samp="0" * 24, comp=comp, logic=logic)
    assert sequence.logic_timing == pytest.approx((6.0, 1.0))


def test_dynamic_results_retain_rate_frequency_and_logic_phase() -> None:
    measurements = []
    for index, frequency_hz in enumerate((1_000.0, 5_000.0)):
        sample_rate_hz = 100_000.0
        time_s = np.arange(2_048) / sample_rate_hz
        samples = np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * frequency_hz * time_s))
        measurements.append(
            adc_measurement(
                samples,
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=frequency_hz,
                logic_phase_delay_symbols=index - 1,
            )
        )
    results = [analyze_dynamic(measurement) for measurement in measurements]
    np.testing.assert_allclose([result.input_frequency_hz for result in results], (1_000.0, 5_000.0))
    np.testing.assert_allclose([result.sample_rate_hz for result in results], (100_000.0, 100_000.0))
    np.testing.assert_array_equal([result.logic_phase_delay_symbols for result in results], (-1, 0))
    assert all(result.index is None for result in results)
    assert all(result.input_referred_noise_rms_v > 0 for result in results)


def test_power_sweep_uses_active_smu_readbacks() -> None:
    measurements = []
    for adc_index, sample_rate_hz in ((0, 100_000.0), (1, 200_000.0)):
        readbacks = {}
        for rail, current_a in (("vdd_a", 2e-6), ("vdd_d", 40e-6), ("vdd_dac", 20e-6)):
            readbacks[f"{rail}_measured_voltage_v"] = 1.2
            readbacks[f"{rail}_measured_current_a"] = 0.5 * current_a
            readbacks[f"{rail}_active_average_current_a"] = current_a
            readbacks[f"{rail}_active_average_power_w"] = 1.2 * current_a
            if adc_index == 1:
                readbacks[f"{rail}_static_average_power_w"] = 0.25 * 1.2 * current_a
        measurements.append(
            adc_measurement(
                [100, 101, 102] * 3,
                sample_rate_hz=sample_rate_hz,
                observed_adc=adc_index,
                readbacks=readbacks,
            )
        )

    power = [analyze_power(measurement) for measurement in measurements]

    assert [result.index for result in power] == [0, 1]
    np.testing.assert_allclose([result.vdd_d_static_power_w for result in power], (24e-6, 12e-6))
    np.testing.assert_allclose([result.vdd_d_dynamic_power_w for result in power], (24e-6, 36e-6))
    np.testing.assert_allclose([result.total_static_power_w for result in power], (37.2e-6, 18.6e-6))
    np.testing.assert_allclose([result.total_dynamic_power_w for result in power], (37.2e-6, 55.8e-6))
    np.testing.assert_allclose([result.total_power_w for result in power], (74.4e-6, 74.4e-6))


def test_power_sweep_extracts_spice_static_from_settled_idle_tail() -> None:
    readbacks = {
        "vdd_a_active_average_power_w": 999.0e-6,
        "vdd_d_active_average_power_w": 999.0e-6,
        "vdd_dac_active_average_power_w": 999.0e-6,
    }
    measurement = adc_measurement(
        [100, 101, 102],
        readbacks=readbacks,
        internal=True,
        waveform_sample_count=201,
    )
    assert measurement.wave is not None
    assert isinstance(measurement, MeasAdc)
    time_s = measurement.wave.time_s
    seq_init_v = np.zeros_like(measurement.wave.v["seq_init"])
    seq_init_v[0, (time_s >= 25.0e-9) & (time_s <= 50.0e-9)] = 1.2
    active_stop_s = 650.0e-9
    rail_currents = {}
    for rail, static_current_a, active_current_a in (
        ("vdd_a", 2.0e-6, 10.0e-6),
        ("vdd_d", 4.0e-6, 20.0e-6),
        ("vdd_dac", 6.0e-6, 30.0e-6),
    ):
        current_a = np.full_like(measurement.wave.v["seq_init"], active_current_a)
        current_a[0, time_s < 25.0e-9] = 100.0e-6
        current_a[0, time_s > active_stop_s] = static_current_a
        rail_currents[rail] = current_a
    measurement = replace(
        measurement,
        wave=replace(measurement.wave, i=rail_currents, v={**measurement.wave.v, "seq_init": seq_init_v}),
    )
    assert measurement.wave is not None

    power = analyze_power(measurement)

    # INIT crosses halfway between 20 and 25 ns. Integrating the linear
    # current segments from 22.5 to 647.5 ns gives these active means.
    expected_active_w = 1.2e-6 * np.asarray((10.09, 20.08, 30.07))
    # The idle samples span 650..995 ns and include half of the 5 ns
    # transition from active to static current, giving a 10/345 correction.
    expected_static_w = 1.2e-6 * np.asarray((2.0, 4.0, 6.0)) * (1.0 + 10.0 / 345.0)
    assert power.index is None
    np.testing.assert_allclose(
        (power.vdd_a_static_power_w, power.vdd_d_static_power_w, power.vdd_dac_static_power_w),
        expected_static_w,
    )
    np.testing.assert_allclose(
        (power.vdd_a_dynamic_power_w, power.vdd_d_dynamic_power_w, power.vdd_dac_dynamic_power_w),
        expected_active_w - expected_static_w,
    )
    assert power.total_power_w == pytest.approx(72.288e-6)
    aligned = analyze_power_waveform(measurement, power=power)
    assert aligned.time_s[0] == pytest.approx(-12.5e-9)


def test_power_sweep_requires_spice_settled_idle_tail() -> None:
    readbacks = {f"{rail}_active_average_power_w": 10.0e-6 for rail in ("vdd_a", "vdd_d", "vdd_dac")}
    measurement = adc_measurement(
        [100, 101, 102],
        readbacks=readbacks,
        internal=True,
        waveform_sample_count=201,
    )
    assert measurement.wave is not None
    assert isinstance(measurement, MeasAdc)
    time_s = measurement.wave.time_s
    seq_init_v = np.zeros_like(measurement.wave.v["seq_init"])
    seq_init_v[0, time_s <= 5.0e-9] = 1.2
    seq_init_v[0, (time_s >= 630.0e-9) & (time_s <= 635.0e-9)] = 1.2
    measurement = replace(measurement, wave=replace(measurement.wave, v={**measurement.wave.v, "seq_init": seq_init_v}))
    assert measurement.wave is not None

    with pytest.raises(ValueError, match="at least two settled-idle samples"):
        analyze_power(measurement)


def test_noise_sweep_uses_active_rate_while_dynamic_uses_true_repeat_rate() -> None:
    """Keep nominal timing sweeps distinct from the waveform sampling interval."""

    low = adc_measurement(
        [100, 101, 100],
        sample_rate_hz=1.0e6,
        logic_phase_delay_symbols=-3,
    )
    high = adc_measurement(
        [100, 102, 101],
        sample_rate_hz=2.0e6,
        logic_phase_delay_symbols=3,
    )

    noise = [analyze_noise(low), analyze_noise(high)]

    # The default pattern has 160 active symbols within a 256-symbol repeat.
    np.testing.assert_allclose([result.active_conversion_rate_hz for result in noise], [1.6e6, 3.2e6])
    np.testing.assert_allclose([result.comparator_time_percent for result in noise], [12.5, 87.5])
    assert noise[0].input_lsb_v == pytest.approx(1.2 / 4095)
    for result in noise:
        assert result.input_referred_noise_rms_v == pytest.approx(result.std_dout * 1.2 / 4095)
        assert math.isnan(result.pretrigger_vin_diff_mean_v)
        assert math.isnan(result.pretrigger_vin_diff_noise_rms_v)
        # Behavioral captures have no physical readout to distrust.
        assert result.readout_valid


def test_noise_sweep_does_not_treat_constant_codes_as_zero_noise() -> None:
    noise = analyze_noise(adc_measurement([100, 100, 100, 100], sample_rate_hz=1.0e6))

    assert noise.std_dout == 0.0
    assert math.isnan(noise.input_referred_noise_rms_v)
    assert not noise.noise_valid
    assert math.isnan(noise.enob_bits)


def test_noise_sweep_preserves_failed_and_recovered_points() -> None:
    recovered = adc_measurement(
        [100, 101, 100, 101],
        sample_rate_hz=3.0e6,
    )
    settled = adc_measurement(
        [100, 101, 100, 101],
        sample_rate_hz=1.0e6,
    )
    failed = adc_measurement(
        [80, 120, 80, 120],
        sample_rate_hz=2.0e6,
    )

    noise = [analyze_noise(measurement) for measurement in (recovered, settled, failed)]

    assert all(result.noise_valid for result in noise)
    np.testing.assert_allclose([result.sample_rate_hz for result in noise], [3e6, 1e6, 2e6])


@pytest.mark.parametrize("offsets", ((-0.05,), (-0.05, -0.15, 0.05)))
def test_noise_sweep_extracts_pretrigger_input_noise(offsets) -> None:
    msmt = adc_measurement([100, 101, 100])
    assert msmt.wave is not None
    time_s = np.asarray((-2.0, -1.0, 0.0, 1.0)) * 1e-9
    vin_diff_v = np.asarray(offsets)[:, None] + np.asarray((-0.001, 0.001, 0.01, -0.01))
    msmt = replace(
        msmt,
        wave=replace(
            msmt.wave,
            record_index=np.arange(len(offsets)),
            time_s=time_s,
            v={
                **msmt.wave.v,
                "vin_diff": vin_diff_v,
                "seq_comp": np.zeros_like(vin_diff_v),
                "seq_logic": np.zeros_like(vin_diff_v),
                "comp_out": np.zeros_like(vin_diff_v),
            },
        ),
    )
    assert msmt.wave is not None

    noise = analyze_noise(msmt)

    assert noise.pretrigger_vin_diff_mean_v == pytest.approx(-0.05)
    assert noise.pretrigger_vin_diff_noise_rms_v == pytest.approx(0.001)


def test_noise_sweep_accepts_measurement_without_scope_waveform() -> None:
    msmt = replace(adc_measurement([100, 101, 100]), wave=None)

    noise = analyze_noise(msmt)

    assert noise.std_dout == pytest.approx(np.std([100, 101, 100]))
    assert math.isnan(noise.pretrigger_vin_diff_mean_v)
    assert math.isnan(noise.pretrigger_vin_diff_noise_rms_v)


def tone_codes(sample_rate_hz: float, *, tone_hz: float, count: int = 32_768, seed: int = 1) -> np.ndarray:
    """Codes of a 3-LSB tone on 1-LSB white noise, rounded like a converter."""

    time_s = np.arange(count) / sample_rate_hz
    noise = np.random.default_rng(seed).normal(0.0, 1.0, count)
    return np.rint(2_000.0 + 3.0 * np.sin(2.0 * np.pi * tone_hz * time_s) + noise)


def test_code_spectrum_splits_a_tone_from_the_white_floor() -> None:
    spectrum = analyze_code_spectrum(adc_measurement(tone_codes(1.0e6, tone_hz=123.4e3), sample_rate_hz=1.0e6))

    assert spectrum.spectrum_valid
    # Input-referred through the nominal 1.2-V / 4095-code LSB.
    assert spectrum.input_lsb_v == pytest.approx(1.2 / 4095)
    np.testing.assert_allclose(spectrum.asd_v_per_sqrt_hz, spectrum.asd_lsb_per_sqrt_hz * 1.2 / 4095)
    assert spectrum.peak_frequency_hz == pytest.approx(123.4e3, abs=2 * spectrum.bin_hz)
    # The smoothed test widens a strong line by half its 21-bin window.
    assert np.all(np.abs(spectrum.frequency_hz[spectrum.line_mask] - 123.4e3) < 12 * spectrum.bin_hz)
    # The tone carries 3/sqrt(2) LSB; noise plus rounding sqrt(1 + 1/12) LSB.
    assert spectrum.narrowband_rms_lsb == pytest.approx(3.0 / math.sqrt(2.0), rel=0.05)
    assert spectrum.broadband_rms_lsb == pytest.approx(math.sqrt(1.0 + 1.0 / 12.0), rel=0.05)
    assert spectrum.total_rms_lsb**2 == pytest.approx(spectrum.narrowband_rms_lsb**2 + spectrum.broadband_rms_lsb**2)
    assert np.std(spectrum.narrowband_dout) == pytest.approx(3.0 / math.sqrt(2.0), rel=0.05)


def test_code_spectrum_of_white_noise_finds_no_lines() -> None:
    codes = np.rint(2_000.0 + np.random.default_rng(2).normal(0.0, 1.0, 32_768))
    spectrum = analyze_code_spectrum(adc_measurement(codes))

    assert not np.any(spectrum.line_mask)
    assert spectrum.narrowband_rms_lsb == 0.0
    assert spectrum.broadband_rms_lsb == pytest.approx(np.std(codes), rel=0.02)


def test_code_spectrum_of_a_constant_code_has_no_floor() -> None:
    spectrum = analyze_code_spectrum(adc_measurement(np.full(1_024, 2_000)))

    assert not spectrum.spectrum_valid
    assert spectrum.total_rms_lsb == 0.0
    assert not np.any(spectrum.line_mask)
    assert math.isnan(spectrum.peak_to_floor)


def test_interferer_unfolds_aliases_at_three_rates_and_skips_stuck_captures() -> None:
    measurements = [
        adc_measurement(tone_codes(rate, tone_hz=8.15e6, count=16_384, seed=index), sample_rate_hz=rate, observed_adc=3)
        for index, rate in enumerate((2.0e6, 6.0e6, 10.0e6))
    ]
    stuck = adc_measurement(np.full(16_384, 2_000), sample_rate_hz=2.0e6, logic_phase_delay_symbols=1, observed_adc=3)
    measurements.append(stuck)
    spectra = [analyze_code_spectrum(measurement) for measurement in measurements]

    interferer = analyze_interferer(measurements, spectra=spectra)

    np.testing.assert_allclose(interferer.sample_rate_hz, [2.0e6, 6.0e6, 10.0e6])
    # 2, 6, and 10 MSPS fold 8.15 MHz to 150 kHz, 2.15 MHz, and 1.85 MHz.
    np.testing.assert_allclose(interferer.observed_peak_hz, [150e3, 2.15e6, 1.85e6], atol=2e3)
    assert interferer.frequency_hz == pytest.approx(8.15e6, abs=2e3)
    # The rates repeat every 30 MHz and mirror about 15 MHz.
    assert interferer.candidate_frequency_hz[-1] == pytest.approx(15e6, abs=1e3)
    assert interferer.excluded_capture_count == 1
    np.testing.assert_allclose(interferer.folded_frequency_hz[:, 0], 0.0)


def test_interferer_rejects_spectra_from_other_captures() -> None:
    measurement = adc_measurement(tone_codes(2.0e6, tone_hz=8.15e6, count=4_096), sample_rate_hz=2.0e6)
    other = analyze_code_spectrum(adc_measurement(tone_codes(6.0e6, tone_hz=8.15e6, count=4_096), sample_rate_hz=6.0e6))

    with pytest.raises(ValueError, match="one to one"):
        analyze_interferer([measurement], spectra=[other])


def test_physical_noise_readout_requires_valid_scope_and_fastrx_readbacks() -> None:
    good = {"scope_fastrx_comparison_valid": True, "scope_fastrx_bit_mismatches": 0, "fastrx_lost_count": 0}
    measurement = adc_measurement([100, 101, 100], observed_adc=0, readbacks=good)
    physical = replace(measurement, info=replace(measurement.info, backend="physical"))
    assert analyze_noise(physical).readout_valid
    for name, value in (("scope_fastrx_bit_mismatches", 2), ("fastrx_lost_count", 1)):
        bad = replace(physical, info=replace(physical.info, readbacks={**good, name: value}))
        assert not analyze_noise(bad).readout_valid


def test_operating_conditions_judge_constant_shifted_and_readout_rows() -> None:
    sequences = timing_sequences[:3]
    measurements = []
    for rate_index, sample_rate_hz in enumerate((1.0e6, 2.0e6)):
        for sequence_index, sequence in enumerate(sequences):
            dout = [1000, 1001, 1002, 1001] * 25
            if (rate_index, sequence_index) == (1, 1):
                dout = [1000] * 100
            if (rate_index, sequence_index) == (1, 2):
                dout = [1100, 1101, 1102, 1101] * 25
            base = adc_measurement(dout, sample_rate_hz=sample_rate_hz, observed_adc=3)
            measurements.append(
                replace(base, param=replace(base.param, tb=replace(base.param.tb, **sequence.as_tb_fields())))
            )
    noise = [analyze_noise(measurement) for measurement in measurements]
    result = analyze_operating_conditions(measurements, noise=list(reversed(noise)))

    assert (result.group, result.index) == (7, 3)
    assert result.reference_mean_dout == pytest.approx(1001.0)
    np.testing.assert_array_equal(result.constant, (False, False, False, False, True, False))
    np.testing.assert_array_equal(result.shifted, (False, False, False, False, False, True))
    np.testing.assert_array_equal(result.plausible, (True, True, True, True, False, False))
    with pytest.raises(ValueError, match="no noise result matches"):
        analyze_operating_conditions(measurements, noise=noise[:-1])


@pytest.mark.parametrize(
    ("samples", "sample_rate_hz", "input_frequency_hz", "message"),
    [
        ([1] * 7, 1_000.0, 10.0, "at least eight"),
        ([1] * 8, 0.0, 10.0, "sample_rate_hz"),
        ([1] * 8, 1_000.0, 500.0, "Nyquist"),
    ],
)
def test_dynamic_analysis_rejects_invalid_records(
    samples: list[int],
    sample_rate_hz: float,
    input_frequency_hz: float,
    message: str,
) -> None:
    msmt = adc_measurement(samples)
    msmt = replace(
        msmt,
        param=replace(
            msmt.param,
            tb=replace(
                msmt.param.tb,
                symbol_rate=sample_rate_hz * len(msmt.param.tb.seq_init_pattern),
                vin_diff=h.Vsin.Params(voff=0.0, vamp=0.5, freq=input_frequency_hz),
            ),
        ),
    )
    with pytest.raises(ValueError, match=message):
        analyze_dynamic(msmt)


def adc_timing_measurement() -> MeasAdc:
    """Seventeen known decisions and a next-cycle tail at 10 ps resolution."""
    base = adc_measurement([2048], internal=True)
    assert base.wave is not None
    assert isinstance(base, MeasAdc)
    time = np.arange(3631, dtype=np.float64) * 10e-12
    t = time / 1e-9
    signals = {name: np.zeros_like(t) for name in base.wave.v}

    def pulse(edges, width):
        return np.asarray([any(edge <= value < edge + width for edge in edges) for value in t], dtype=float) * 1.2

    starts = 1 + 2 * np.arange(17)
    signals.update(
        seq_init=pulse([0.2, 35], 0.5),
        seq_logic=pulse([0.4, *list(starts[:16] + 1), 35.2], 0.1),
        clk_comp=pulse([*starts, 36], 0.8),
        seq_comp=pulse([*starts, 36], 0.8),
    )
    bits = np.array([1, 1, *[index % 2 for index in range(15)]])
    signals["comp.latch_p"] = np.full_like(t, 1.2)
    signals["comp.latch_n"] = np.full_like(t, 1.2)
    sr = np.zeros_like(t)
    for decision, start in enumerate(starts):
        active = (t >= start + 0.25) & (t < start + 0.8)
        signals["comp.latch_p"][active] = bits[decision] * 1.2
        signals["comp.latch_n"][active] = (1 - bits[decision]) * 1.2
        sr[t >= start + 0.4] = bits[decision] * 1.2
        if decision == 16:
            continue
        for side, state in (("p", 1 - bits[decision]), ("n", bits[decision])):
            for diff in (False, True):
                suffix = "_diff" if diff else ""
                signals[f"dac_state_{side}{suffix}[{decision}]"] = np.where(t >= start + 1.1, state * 1.2, 0)
                target = bool(state) ^ (diff and bool(base.param.dac_diffcaps))
                signals[f"dac_botplate_{side}{suffix}[{decision}]"] = np.where(t >= start + 1.2, target * 1.2, 0)
    signals.update(
        comp_out_p=sr, comp_out_n=1.2 - sr, comp_out=sr, vdac_p=np.full_like(t, 0.7), vdac_n=np.full_like(t, 0.7)
    )
    return replace(
        base,
        wave=Wave(
            record_index=np.array([0]), time_s=time, v={name: values[None, :] for name, values in signals.items()}
        ),
    )


def test_adc_timing_closure_uses_typed_wave_records_and_preserves_codes(tmp_path) -> None:
    from flow.analysis.io import read_measurement, write_measurement

    measurement = adc_timing_measurement()
    path = tmp_path / "measurement.h5"
    write_measurement(path, measurement)
    loaded = read_measurement(path)
    assert isinstance(loaded, MeasAdc)
    before = loaded.bout.copy()
    result = analyze_timing_closure(loaded)
    assert isinstance(result, adc.AnalysisTimingClosure)
    assert np.all(result.passed)
    np.testing.assert_array_equal(result.decision_index, np.arange(17))
    assert result.required_logic_setup_s == result.required_cdac_setup_s == 200e-12
    assert result.sample_interval_s == pytest.approx(10e-12)
    np.testing.assert_allclose(result.logic_setup_s[np.r_[0, 2:16]], 0.595e-9, atol=11e-12)
    assert result.logic_setup_s[1] > 0.7e-9
    assert np.all(result.cdac_setup_s[:16] > 0.7e-9)
    # Consecutive equal decisions do not require a new SR transition.
    assert result.sr_stable_s[1] == pytest.approx(3e-9)
    assert result.logic_ready[-1] and not result.cdac_applicable[-1]
    assert np.isnan(result.cdac_setup_s[-1])
    np.testing.assert_array_equal(loaded.bout, before)


@pytest.mark.parametrize(
    "failure", ("wrong_sr", "late_sr", "unresolved", "late_internal", "ringing_cdac", "wrong_state", "missing_reset")
)
def test_adc_timing_closure_flags_failed_handoffs(failure) -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    time = measurement.wave.time_s
    signals = {name: value.copy() for name, value in measurement.wave.v.items()}
    if failure in ("wrong_sr", "late_sr"):
        stop = 2.01e-9 if failure == "wrong_sr" else 1.9e-9
        signals["comp_out_p"][0, time < stop] = 0
        signals["comp_out_n"][0, time < stop] = 1.2
    elif failure == "unresolved":
        active = (time >= 1e-9) & (time < 1.81e-9)
        signals["comp.latch_p"][0, active] = 0.61
        signals["comp.latch_n"][0, active] = 0.60
    elif failure == "late_internal":
        # The final tendency reverses after LOGIC; a first crossing would miss this.
        active = (time >= 1.25e-9) & (time < 2.15e-9)
        signals["clk_comp"][0, active] = 1.2
        signals["comp.latch_p"][0, active] = 0
        signals["comp.latch_n"][0, active] = 1.2
        final = (time >= 2.05e-9) & (time < 2.15e-9)
        signals["comp.latch_p"][0, final] = 1.2
        signals["comp.latch_n"][0, final] = 0
    elif failure == "ringing_cdac":
        signals["vdac_p"][0, (time >= 2.8e-9) & (time < 2.9e-9)] += 0.01
    elif failure == "wrong_state":
        signals["dac_state_n[0]"][:] = 0
    else:
        signals["clk_comp"][0, (time >= 1.8e-9) & (time < 3e-9)] = 1.2
        # Preserve the next rise while hiding only the internal reset with an initial-high record:
        # the absent pulse boundary is a malformed decision sequence, and is rejected explicitly.
        with pytest.raises(ValueError, match="COMP rises; expected"):
            analyze_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))
        return
    result = analyze_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))
    assert not result.passed[0]
    assert np.all(result.passed[1:])
    if failure == "wrong_sr":
        assert not result.sr_matches_at_logic[0]
    elif failure in ("late_sr", "late_internal"):
        assert result.logic_setup_s[0] < 200e-12
    elif failure == "unresolved":
        assert result.internal_final_diff_v[0] == pytest.approx(0.01)
        assert np.isnan(result.internal_stable_s[0])
    else:
        assert not result.cdac_ready[0]


def test_adc_timing_closure_reports_unknown_when_final_tail_is_missing() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    wave = measurement.wave
    assert wave is not None
    selected = wave.time_s <= 34e-9
    result = analyze_timing_closure(
        replace(
            measurement,
            wave=replace(
                wave, time_s=wave.time_s[selected], v={name: values[:, selected] for name, values in wave.v.items()}
            ),
        )
    )
    assert np.all(result.passed[:16])
    assert np.isnan(result.logic_setup_s[-1])
    assert not result.passed[-1]


def test_adc_timing_closure_requires_saved_internals() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    signals = dict(measurement.wave.v)
    del signals["comp.latch_n"]
    with pytest.raises(ValueError, match="comp.latch_n"):
        analyze_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))


def test_adc_timing_closure_preserves_saved_conversion_indices() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    result = analyze_timing_closure(
        replace(
            measurement,
            conversion_index=np.array([37]),
            wave=replace(measurement.wave, record_index=np.array([37])),
        )
    )
    np.testing.assert_array_equal(result.conversion_index, np.full(17, 37))
    assert np.all(result.passed)


def test_adc_timing_closure_marks_missing_logic_unknown_instead_of_guessing() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    signals = {name: values.copy() for name, values in measurement.wave.v.items()}
    signals["seq_logic"][0, (measurement.wave.time_s >= 1.9e-9) & (measurement.wave.time_s <= 2.2e-9)] = 0
    result = analyze_timing_closure(replace(measurement, wave=replace(measurement.wave, v=signals)))
    assert np.isnan(result.logic_rise_s[0])
    assert not result.passed[0]
    assert np.all(result.passed[1:])


def test_dynamic_sine_fit_recovers_signal_with_frequency_error() -> None:
    """The fit refines a programmed frequency that is off by 0.6%."""

    sample_rate = 1000.0
    time_s = np.arange(1000) / sample_rate
    samples = np.rint(2_000.0 + 1_500.0 * np.sin(2.0 * np.pi * 41.25 * time_s + 0.4))
    result = analyze_dynamic(adc_measurement(samples, sample_rate_hz=sample_rate, input_frequency_hz=41.0))
    assert result.fitted_frequency_hz == pytest.approx(41.25, abs=1e-4)
    assert result.amplitude_dout == pytest.approx(1_500.0, rel=1e-4)
    assert result.phase_rad == pytest.approx(0.4, abs=1e-3)
    assert result.offset_dout == pytest.approx(2_000.0, abs=0.05)
    # Only rounding to whole codes remains in the residual.
    assert result.residual_rms_dout == pytest.approx(1 / np.sqrt(12), rel=0.1)
    np.testing.assert_allclose(result.time_s, time_s)
    np.testing.assert_allclose(result.fitted_dout + result.residual_dout, samples)


def test_code_spectrum_decodes_bout_with_a_calibration() -> None:
    """A calibration replaces the stored DOUT with its decoded BOUT and names the decoding."""

    measurement = adc_ramp_measurement()
    nominal = analyze_ramp(measurement).weights.astype(np.float64)
    nominal *= 4095.0 / np.sum(nominal)
    calibrated = nominal.copy()
    calibrated[:2] *= (1.02, 0.97)
    calibrated *= 4095.0 / np.sum(calibrated)
    calibration = adc.AnalysisCalibration(
        group=7,
        index=0,
        dut=measurement.dut,
        method="calibration1",
        label="Synthetic calibrated BOUT",
        code_max=4095,
        nominal_weights=nominal,
        calibrated_weights=calibrated,
        measured_weight_mask=np.ones(17, dtype=np.bool_),
        training_sample_count=100,
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )

    plain = analyze_code_spectrum(measurement)
    decoded = analyze_code_spectrum(measurement, calibration=calibration)

    assert plain.decoding == "uncalibrated_dout"
    assert decoded.decoding == "calibration1"
    codes = _decode(measurement.bout, calibration, rounded=False)
    assert decoded.mean_dout == pytest.approx(float(np.mean(codes)))
    assert decoded.mean_dout != pytest.approx(plain.mean_dout)


def test_code_spectrum_integrates_to_the_code_noise_rms() -> None:
    rng = np.random.default_rng(0)
    codes = np.rint(2000.3 + rng.normal(0.0, 2.0, 65536)).astype(np.int64)
    spectrum = analyze_code_spectrum(adc_measurement(codes))

    assert spectrum.decoding == "uncalibrated_dout"
    # Welch with a Hann window integrates to the sample variance within a few percent.
    assert spectrum.total_rms_lsb == pytest.approx(np.std(codes), rel=0.03)
    # White noise: the median density sits near variance / (fs / 2).
    assert spectrum.white_floor_lsb2_per_hz == pytest.approx(np.var(codes) / (spectrum.sample_rate_hz / 2), rel=0.15)


# ---- an ADC other than FRIDA: a hypothetical 10-bit converter with 12 switched capacitors (13
# decisions) exercises every place where a decision count, capacitor count or code range must come
# from the measurement parameters; a literal FRIDA size fails here

CAPACITOR_WEIGHTS = (192, 128, 80, 48, 32, 16, 12, 8, 4, 2, 1, 1)


def small_adc() -> adc.Params:
    return adc.Params(adc_bits=10, cdac=CapArrayConfig(n_dac=9, n_extra=3, weights=CAPACITOR_WEIGHTS))


def small_scan_params(conversions: int, vin_diff) -> AdcScanParams:
    template = adc.TbParams()
    return AdcScanParams(
        tb=adc.TbParams(
            dut=small_adc(),
            conversions=conversions,
            symbol_rate=1.0e6 * len(template.seq_init_pattern),
            vin_cm=h.Vdc.Params(dc=0.6),
            vin_diff=vin_diff,
            dac_astate_p=(0, 1) * 6,
            dac_astate_n=(0, 1) * 6,
            dac_bstate_p=(0,) * 12,
            dac_bstate_n=(0,) * 12,
        ),
        board_id=1,
        observed_adc=5,
        active_adc_mask=tuple(int(index == 5) for index in reversed(range(16))),
    )


def small_measurement(bout: np.ndarray, vin_diff_v: np.ndarray, vin_diff) -> MeasAdc:
    weights = np.asarray([2 * weight for weight in CAPACITOR_WEIGHTS] + [1], dtype=np.int64)
    dout_raw = bout.astype(np.int64) @ weights
    params = small_scan_params(len(bout), vin_diff)
    return MeasAdc(
        group=params.board_id,
        index=params.observed_adc,
        dut=params.tb.dut,
        info=MeasInfo(backend="behavioral", timestamp_utc=datetime(2026, 10, 5, tzinfo=UTC)),
        param=params,
        conversion_index=np.arange(len(bout)),
        bout=bout,
        dout_raw=dout_raw,
        dout=np.rint(dout_raw * 1023 / np.sum(weights)).astype(np.int64),
        vin_diff_v=vin_diff_v,
        wave=None,
    )


def small_ramp(cycles: int = 8, samples_per_cycle: int = 2_048) -> MeasAdc:
    weights = np.asarray([2 * weight for weight in CAPACITOR_WEIGHTS] + [1], dtype=np.int64)
    remaining = np.rint(np.linspace(0.0, np.sum(weights), samples_per_cycle)).astype(np.int64)
    one_cycle = np.zeros((samples_per_cycle, len(weights)), dtype=np.uint8)
    for decision, weight in enumerate(weights):
        one_cycle[:, decision] = remaining >= weight
        remaining -= one_cycle[:, decision] * weight
    return small_measurement(
        np.tile(one_cycle, (cycles, 1)),
        np.tile(np.linspace(-1.0, 1.0, samples_per_cycle, endpoint=False), cycles),
        h.Vpwl.Params(wave=f"0 -1 {samples_per_cycle / 1.0e6:.12g} 1"),
    )


def test_small_adc_is_a_different_architecture() -> None:
    assert len(get_caparray_weights(small_adc().cdac)) == 12
    assert small_adc().adc_bits == 10


def test_ramp_code_density_and_calibration_use_the_measured_architecture() -> None:
    measurement = small_ramp()
    ramp = analyze_ramp(measurement)
    assert ramp.period_conversions == pytest.approx(2_048, rel=1e-6)
    assert len(ramp.code) == 1024 and len(ramp.weights) == 13
    density = analyze_code_density_nonlinearity(measurement, ramp=ramp)
    assert density.code[0] == 1 and density.code[-1] == 1022
    calibration = analyze_calibration2(measurement, ramp=ramp)
    assert calibration.calibrated_weights.shape == (13,)
    assert calibration.code_max == 1023
    assert np.sum(calibration.calibrated_weights) == pytest.approx(1023.0)
    recalibrated = analyze_ramp(measurement, calibration=calibration)
    assert recalibrated.decoding == "calibration2"
    assert len(recalibrated.code) == 1024 and len(recalibrated.weights) == 13


def test_static_noise_and_decision_paths_use_the_measured_architecture() -> None:
    rng = np.random.default_rng(5)
    bout = rng.integers(0, 2, size=(200, 13), dtype=np.uint8)
    measurement = small_measurement(bout, np.zeros(200), h.Vdc.Params(dc=0.0))
    assert analyze_code_distribution([measurement]).count.shape == (1, 1024)
    assert analyze_transfer([measurement]).sample_count.sum() == 200
    paths = analyze_decision_paths(measurement)
    assert paths.estimate_dout.shape == (200, 14)
    assert paths.estimate_dout[0, -1] == pytest.approx(measurement.dout[0], abs=0.5)
    noise = analyze_noise(measurement)
    assert noise.code_max == 1023
    assert noise.input_lsb_v == pytest.approx(1.2 / 1023)
    conditions = analyze_operating_conditions([measurement], noise=[noise])
    assert (conditions.group, conditions.index) == (1, 5)


def test_cdac_mismatch_and_calibration1_use_the_measured_capacitor_count() -> None:
    measurements = []
    transition_v = 3e-3
    for input_index, probability in enumerate((0.0, 0.5, 1.0)):
        vin_diff_v = transition_v + (input_index - 1) * 10e-3
        params = _build_cdac_params(
            adc_index=5,
            side="p",
            element=11,
            direction="0to1",
            dac_diffcaps=1,
            vin_diff_v=vin_diff_v,
            conversions=100,
            sweep_stage="fine",
        )
        small = small_scan_params(100, h.Vdc.Params(dc=vin_diff_v))
        params = replace(params, board_id=1, tb=replace(small.tb, dac_diffcaps=1, conversions=100))
        ones = round(100 * probability)
        measurements.append(
            MeasCdac(
                group=params.board_id,
                index=params.observed_adc,
                dut=params.tb.dut.cdac,
                info=MeasInfo(
                    backend="physical",
                    timestamp_utc=datetime(2026, 10, 5, tzinfo=UTC),
                    readbacks={"cdac_topplate_parasitic_weight": 0.0},
                ),
                param=params,
                trial_index=np.arange(100),
                dac_state_p=np.zeros((100, 12), dtype=np.uint8),
                dac_state_n=np.zeros((100, 12), dtype=np.uint8),
                vin_diff_v=np.full(100, vin_diff_v),
                decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
                wave=None,
            )
        )
    transition = analyze_cdac_transition(
        measurements, offset=comp.analyze_offset_noise([analyze_cdac_decisions(measurements)])
    )
    mismatch = analyze_cdac_cap_mismatch(
        measurements, transitions=[transition], comparator=comparator_offset(measurements[0], 0.0)
    )
    assert mismatch.effective_fraction.shape == (2, 12)
    assert mismatch.effective_fraction_by_direction[0, 11, 1] == pytest.approx(-transition_v / 1.2)

    tb = measurements[0].tb
    nominal = np.asarray(CAPACITOR_WEIGHTS, dtype=np.float64)
    by_direction = np.repeat(np.repeat(nominal[None, :, None], 2, axis=0), 2, axis=2)
    nan = np.full((2, 12), np.nan)
    cap_mismatch = AnalysisCdacCapMismatch(
        group=1,
        index=5,
        dut=tb.dut.cdac,
        main_fraction=nan,
        diff_fraction=nan,
        effective_fraction=nan,
        effective_fraction_by_direction=by_direction,
        direction_bias=np.full((2, 12, 2), np.nan),
    )
    fake = cast(
        MeasCdac,
        SimpleNamespace(tb=tb, identity=Identity(1, 5, tb.dut.cdac), trial_index=np.arange(3)),
    )
    calibration = analyze_calibration1((fake,), cap_mismatch=cap_mismatch)
    assert calibration.calibrated_weights.shape == (13,)
    assert calibration.code_max == 1023
    np.testing.assert_allclose(calibration.calibrated_weights, calibration.nominal_weights)


# ---- calibration 1, from mechanistic CDAC measurements


def test_calibration1_public_analysis_returns_common_weights() -> None:
    params = AdcScanParams(
        tb=adc.TbParams(),
        board_id=0,
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
    )
    nominal_cap_weight = 2.0 * np.asarray(get_caparray_weights(params.tb.dut.cdac), dtype=np.float64)
    element_count = len(nominal_cap_weight)
    measured = np.repeat((nominal_cap_weight / 2.0)[None, :, None], 2, axis=0)
    measured = np.repeat(measured, 2, axis=2)
    identity = Identity(0, 0, params.tb.dut.cdac)
    measurement = cast(
        MeasCdac,
        SimpleNamespace(param=params, tb=params.tb, identity=identity, trial_index=np.arange(100)),
    )

    def cap_mismatch(by_direction: np.ndarray) -> AnalysisCdacCapMismatch:
        nan = np.full((2, element_count), np.nan)
        return AnalysisCdacCapMismatch(
            group=0,
            index=0,
            dut=params.tb.dut.cdac,
            main_fraction=nan,
            diff_fraction=nan,
            effective_fraction=nan,
            effective_fraction_by_direction=by_direction,
            direction_bias=np.full((2, element_count, 2), np.nan),
        )

    result = analyze_calibration1((measurement,), cap_mismatch=cap_mismatch(measured))

    assert result.method == "calibration1"
    assert (result.group, result.index, result.dut) == (0, 0, params.tb.dut)
    np.testing.assert_allclose(result.calibrated_weights, result.nominal_weights)
    np.testing.assert_array_equal(result.measured_weight_mask, [True] * element_count + [False])
    assert result.training_sample_count == 100

    measured[0, 5, :] = np.nan
    hybrid = analyze_calibration1((measurement,), cap_mismatch=cap_mismatch(measured))
    assert not hybrid.measured_weight_mask[5]
    assert np.all(np.isfinite(hybrid.calibrated_weights))
    assert np.sum(hybrid.calibrated_weights) == pytest.approx(4095.0)

    other_channel = replace(cap_mismatch(measured), index=1)
    with pytest.raises(ValueError, match="does not match"):
        analyze_calibration1((measurement,), cap_mismatch=other_channel)


def test_calibration1_selects_p_and_n_directions_from_each_a_state() -> None:
    """A=0 uses the 0-to-1 movement and A=1 the 1-to-0 movement, independently per side."""

    a_p = (0, 1) * 8
    a_n = (0, 0, 1, 1) * 4
    params = AdcScanParams(
        tb=adc.TbParams(dac_astate_p=a_p, dac_astate_n=a_n),
        board_id=0,
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
    )
    nominal_cap_weight = np.asarray(get_caparray_weights(params.tb.dut.cdac), dtype=np.float64)
    by_direction = np.empty((2, 16, 2))
    # Selected movements are each nominal half-weight; unselected ones are
    # deliberately wrong or NaN so a wrong selection would be visible.
    for element in range(16):
        by_direction[0, element, 1 - a_p[element]] = nominal_cap_weight[element]
        by_direction[0, element, a_p[element]] = np.nan
        by_direction[1, element, 1 - a_n[element]] = nominal_cap_weight[element]
        by_direction[1, element, a_n[element]] = 100.0 * nominal_cap_weight[element]
    nan = np.full((2, 16), np.nan)
    cap_mismatch = AnalysisCdacCapMismatch(
        group=0,
        index=0,
        dut=params.tb.dut.cdac,
        main_fraction=nan,
        diff_fraction=nan,
        effective_fraction=nan,
        effective_fraction_by_direction=by_direction,
        direction_bias=np.full((2, 16, 2), np.nan),
    )
    measurement = cast(
        MeasCdac,
        SimpleNamespace(
            param=params,
            tb=params.tb,
            identity=Identity(0, 0, params.tb.dut.cdac),
            trial_index=np.arange(10),
        ),
    )

    result = analyze_calibration1((measurement,), cap_mismatch=cap_mismatch)

    assert np.all(result.measured_weight_mask[:16])
    np.testing.assert_allclose(result.calibrated_weights, result.nominal_weights)


# ---- calibration 2, the known-ramp BOUT weight regression

RAMP_CODE_MAX = 4095  # the ramp builders' twelve bits


def perturbed_ramp_measurement(true_weights: np.ndarray, *, cycles: int = 8, samples_per_cycle: int = 4_096):
    """Return a linear ramp whose BOUT words were decided with ``true_weights``.

    DOUT is still decoded with the nominal weights, as the hardware does, so
    the analysis must recover ``true_weights`` from the known ramp alone.
    """

    template = adc_ramp_measurement(cycles=cycles)
    nominal = template.nominal_bout_weights
    remaining = np.linspace(0.0, np.sum(true_weights), samples_per_cycle)
    one_cycle = np.zeros((samples_per_cycle, len(nominal)), dtype=np.uint8)
    for decision, weight in enumerate(true_weights):
        one_cycle[:, decision] = remaining >= weight
        remaining -= one_cycle[:, decision] * weight
    bout = np.tile(one_cycle, (cycles, 1))
    dout_raw = bout.astype(np.int64) @ nominal
    return replace(
        template,
        conversion_index=template.conversion_index,
        bout=bout,
        dout_raw=dout_raw,
        dout=np.rint(dout_raw * RAMP_CODE_MAX / np.sum(nominal)).astype(np.int64),
        vin_diff_v=template.vin_diff_v,
    )


def test_calibration2_public_analysis_returns_common_weights() -> None:
    measurement = adc_ramp_measurement(cycles=8)
    ramp = analyze_ramp(measurement)

    result = analyze_calibration2(measurement, ramp=ramp)

    assert result.method == "calibration2"
    assert (result.group, result.index, result.dut) == (7, 0, measurement.dut)
    assert result.calibrated_weights.shape == (17,)
    assert np.sum(result.calibrated_weights) == pytest.approx(RAMP_CODE_MAX)
    assert np.all(result.measured_weight_mask)
    assert result.training_sample_count > 0
    assert result.validation_sample_count > 0


def test_calibration2_recovers_known_perturbed_weights() -> None:
    nominal = adc_ramp_measurement().nominal_bout_weights.astype(np.float64)
    perturbation = np.asarray(
        [1.002, 0.998, 1.004, 0.997, 1.003, 0.996, 1.005, 0.995, 1.006, 0.994, 1.01, 0.99, 1.01, 0.98, 1.02, 0.97, 1.03]
    )
    true_weights = nominal * perturbation
    measurement = perturbed_ramp_measurement(true_weights)

    result = analyze_calibration2(measurement, ramp=analyze_ramp(measurement))

    expected = true_weights * RAMP_CODE_MAX / np.sum(true_weights)
    # The large weights dominate the fit; recover them to a fraction of one code.
    np.testing.assert_allclose(result.calibrated_weights[:8], expected[:8], atol=0.5)
    assert np.max(np.abs(result.calibrated_weights - expected)) < np.max(np.abs(result.nominal_weights - expected))


def test_validation_cycles_cannot_change_the_fit() -> None:
    measurement = adc_ramp_measurement(cycles=8)
    ramp = analyze_ramp(measurement)
    reference = analyze_calibration2(measurement, ramp=ramp)

    # Corrupt every odd (validation) cycle's decisions, keeping DOUT consistent.
    odd = (ramp.cycle_index % 2) == 1
    bout = measurement.bout.copy()
    bout[odd] = 1 - bout[odd]
    dout_raw = bout.astype(np.int64) @ measurement.nominal_bout_weights
    changed = replace(
        measurement,
        bout=bout,
        dout_raw=dout_raw,
        dout=np.rint(dout_raw * RAMP_CODE_MAX / np.sum(measurement.nominal_bout_weights)).astype(np.int64),
    )
    result = analyze_calibration2(changed, ramp=ramp)

    np.testing.assert_array_equal(result.calibrated_weights, reference.calibrated_weights)
    assert result.output_gain == reference.output_gain
    assert result.output_offset_lsb == reference.output_offset_lsb


# ---- calibration 3, from Hsu's slow-ramp thresholds

NOMINAL_WEIGHTS = np.asarray(
    [1536, 1024, 640, 384, 192, 128, 64, 48, 24, 20, 10, 8, 8, 4, 2, 2, 1],
    dtype=np.float64,
)


def _threshold_ramp_measurement(
    *,
    cycles: int = 40,
    samples_per_cycle: int = 16_384,
    noise_sigma_v: float = 40e-6,
) -> tuple[MeasAdc, np.ndarray, np.ndarray]:
    """Build a SAR whose Hsu branch thresholds have known directional steps."""

    rng = np.random.default_rng(20260813)
    one_cycle_vin_diff_v = np.linspace(-1.0, 1.0, samples_per_cycle, endpoint=False)
    vin_diff_v = np.tile(one_cycle_vin_diff_v, cycles)

    # Deliberately perturb the largest weights so an applied calibration has a
    # signal which is much larger than this synthetic comparator noise.  The
    # unequal up/down split also verifies that the analysis does not assume a
    # comparator decision always moves the same physical side of the CDAC.
    mismatch = np.asarray([1.04, 0.97, 1.02, 0.98, 1.01, 0.99, 1.01, 0.99, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    endpoint_weight_v = NOMINAL_WEIGHTS[:-1] * 250e-6 * mismatch
    down_step_v = endpoint_weight_v * np.linspace(0.47, 0.52, 16)
    up_step_v = endpoint_weight_v - down_step_v

    decisions = np.empty((len(vin_diff_v), 17), dtype=np.uint8)
    decision_level_v = np.zeros(len(vin_diff_v), dtype=np.float64)
    for decision_index in range(17):
        # Independent Gaussian decision noise is intentionally simpler than the
        # real capture.  The production analysis comments identify source drift
        # and conversion correlation which this numerical fixture cannot model.
        decision = vin_diff_v + rng.normal(0.0, noise_sigma_v, len(vin_diff_v)) >= decision_level_v
        decisions[:, decision_index] = decision
        if decision_index < 16:
            decision_level_v += np.where(
                decision,
                up_step_v[decision_index],
                -down_step_v[decision_index],
            )

    nominal_raw = decisions.astype(np.int64) @ NOMINAL_WEIGHTS.astype(np.int64)
    nominal_dout = np.rint(nominal_raw * 4095 / np.sum(NOMINAL_WEIGHTS)).astype(np.int64)
    base = adc_measurement(np.zeros(len(vin_diff_v), dtype=np.int64), observed_adc=0)
    assert isinstance(base, MeasAdc)
    params = AdcScanParams(
        tb=adc.TbParams(
            dut=base.param.tb.dut,
            conversions=len(vin_diff_v),
            symbol_rate=base.param.tb.symbol_rate,
            vin_cm=h.Vdc.Params(dc=0.6),
            vin_diff=h.Vpwl.Params(wave=f"0 -1 {samples_per_cycle / base.sample_rate_hz:.12g} 1"),
        ),
        board_id=7,
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
        campaign="adc_ramp",
    )
    return (
        replace(
            base,
            param=params,
            conversion_index=np.arange(len(vin_diff_v)),
            bout=decisions,
            dout_raw=nominal_raw,
            dout=nominal_dout,
            vin_diff_v=vin_diff_v,
        ),
        down_step_v,
        up_step_v,
    )


@pytest.fixture(scope="module")
def threshold_analysis():
    """Share the relatively expensive synthetic threshold extraction."""

    measurement, expected_down_step_v, expected_up_step_v = _threshold_ramp_measurement()
    return (
        analyze_calibration3(measurement, ramp=analyze_ramp(measurement)),
        expected_down_step_v,
        expected_up_step_v,
    )


def test_threshold_calibration_recovers_both_directional_movements(threshold_analysis) -> None:
    """Measured weights follow the known down-plus-up threshold movements without side assumptions."""

    result, expected_down_step_v, expected_up_step_v = threshold_analysis
    expected_endpoint_v = expected_down_step_v + expected_up_step_v

    assert (result.group, result.index) == (7, 0)
    assert result.method == "calibration3"
    measured = int(np.count_nonzero(result.measured_weight_mask))
    # The first four, deliberately perturbed steps resolve on this fixture.
    assert measured >= 4
    assert np.all(result.measured_weight_mask[:measured])
    # Within the measured prefix, weight ratios equal the endpoint-movement ratios.
    np.testing.assert_allclose(
        result.calibrated_weights[:measured] / result.calibrated_weights[0],
        expected_endpoint_v[:measured] / expected_endpoint_v[0],
        rtol=2e-3,
    )
    assert np.all(result.calibrated_weights > 0.0)
    assert np.sum(result.nominal_weights) == pytest.approx(4095.0)
    assert np.sum(result.calibrated_weights) == pytest.approx(4095.0)


def test_threshold_calibration_keeps_design_ratios_in_the_unmeasured_tail(threshold_analysis) -> None:
    """The terminal half-step is unobservable, so it and unresolved steps keep nominal ratios."""

    result, _, _ = threshold_analysis
    measured = int(np.count_nonzero(result.measured_weight_mask))
    tail = slice(measured, None)
    np.testing.assert_allclose(
        result.calibrated_weights[tail] / result.calibrated_weights[-1],
        result.nominal_weights[tail] / result.nominal_weights[-1],
    )


def test_threshold_calibration_uses_common_weight_plot(
    threshold_analysis,
    tmp_path,
) -> None:
    """Render calibration 3 through the method-independent plotting API."""

    result, _, _ = threshold_analysis
    plot_paths = plot_adc_calibration_weights(
        (result,),
        output_path=tmp_path / "direct_threshold_calibration",
    )
    assert tuple(path.suffix for path in plot_paths) == (".pdf",)
    assert plot_paths[0].is_file()
    assert plot_paths[0].stat().st_size > 0


# ---- the ENOB ladder: the campaign's ladder captures on a model of ideal blocks of known impairments


def _stub_model(table: Path, params: Params):
    """An ADC model of ideal blocks of known impairments, the array's ideal capacitances in an
    extraction's table, at a 1.2 V supply (no PDK)."""
    from flow.adc import model

    class Stub(model.Model):
        supply_v = 1.2

    main_f, diff_f = calc_ideal_capacitances(params.cdac)
    rows = (f"{i},{m * 1e15:.6f},{d * 1e15:.6f},{(m - d) * 1e15:.6f}\n" for i, (m, d) in enumerate(zip(main_f, diff_f)))
    table.write_text("stage,main_ff,diff_ff,effective_ff\n" + "".join(rows))
    load_f = float(np.sum(main_f) + np.sum(diff_f))
    return Stub(
        pdk="none",
        params=params,
        comp=SimpleNamespace(
            behavioral=lambda vin_cm_v: comp_model.Model.Behavioral(
                noise_v=100e-6, delay_table_v=(1e-6, 1e-3), delay_table_s=(2e-9, 0.6e-9)
            )
        ),
        # an on-resistance twice as high at mid-supply as at the rails: a tracking error that distorts
        samp=SimpleNamespace(
            behavioral=lambda load_f: samp_model.Model.Behavioral(
                noise_v=float(np.sqrt(2 * constants.k * 300 / load_f)),
                jitter_s=2e-12,
                ron_table_v=(0.2, 0.7, 1.2),
                # on the 12-bit array's 0.54 pF at its 204 aF unit, a time constant of 0.4-0.8 ns
                ron_table_ohm=(750.0, 1500.0, 750.0),
            )
        ),
        cdac=SimpleNamespace(
            draw=lambda unit_mismatch, rng: (main_f, diff_f),
            parasitic_f=0.0,
            main_f=main_f,
            diff_f=diff_f,
            load_f=load_f,
            table=table,
        ),
        drivers=tuple(SimpleNamespace(resistance_ohm=1.0, intrinsic_delay_s=20e-12, energy_j=0.0) for _ in main_f),
        settling=SimpleNamespace(tau_s=(0.35e-9,) * len(main_f), delay_s=(50e-12,) * len(main_f)),
    )


def _capture(model, declared):
    """The model's capture of one declared capture, its sources and settling as declared."""
    return model.capture(
        declared.tb,
        None,
        seed=declared.seed,
        noise_seed=declared.noise_seed,
        unit_mismatch=declared.unit_mismatch,
        quiet=declared.quiet,
        tau_scale=declared.tau_scale,
    )


@pytest.mark.parametrize(
    "cdac",
    [CapArrayConfig(n_dac=11, n_extra=0, redun_strat=RedunStrat.BINARY), CapArrayConfig()],
    ids=["binary", "msb_redist"],
)
def test_the_ladder_starts_at_quantization_and_ends_on_enob_bits(tmp_path: Path, cdac: CapArrayConfig) -> None:
    params = Params(adc_bits=12, cdac=cdac)
    model = _stub_model(tmp_path / "table.csv", params)
    plan = campaign(model.tb, model.full_scale_v, params.adc_bits)
    captures = {name: _capture(model, plan[name]) for name in LADDER_NAMES}
    result = _ladder(captures)
    assert result is not None and len(result.enob_bits) == len(LADDER)
    ladder = result.enob_bits
    # quantization alone reads the design resolution: the extracted weights' codes unrounded (whole
    # codes would quantize a second time) and the -0.5 dBFS sine's SNDR referred to full scale
    assert ladder[0] == pytest.approx(params.adc_bits, abs=0.02)
    # the sampler's input-dependent on-resistance distorts the held sine
    assert ladder[1] < ladder[0] - 0.5
    # every impairment on is the 10 MS/s sine as enob_bits decodes it (the extracted weights), and
    # the last step's sources and settling capture it again, decision for decision
    rate = captures["rate_10"]
    assert ladder[-1] == analyze_dynamic(rate, calibration=_extracted(rate)).spectral_enob_fs_bits
    _, _, quiet, tau_scale = LADDER[-1]
    again = _capture(model, replace(plan["rate_10"], quiet=quiet, tau_scale=tau_scale))
    np.testing.assert_array_equal(again.bout, rate.bout)
    repeated = _ladder({**captures, "rate_10": again})
    assert repeated is not None and repeated.enob_bits[-1] == ladder[-1]
    # without the ladder's captures (a SPICE campaign), no ladder
    assert _ladder({"rate_10": rate}) is None


@pytest.mark.parametrize("adc_bits", [10, 12])
def test_the_ladders_quantization_reads_the_design_resolution(tmp_path: Path, adc_bits: int) -> None:
    """Quantization alone (a binary array, as the sweep's binary instances) reads the design
    resolution: the ladder refers the -0.5 dBFS sine's SNDR to full scale, where at the sine's own
    amplitude it reads half a dB less."""
    params = Params(
        adc_bits=adc_bits, cdac=CapArrayConfig(n_dac=adc_bits - 1, n_extra=0, redun_strat=RedunStrat.BINARY)
    )
    model = _stub_model(tmp_path / "table.csv", params)
    plan = campaign(model.tb, model.full_scale_v, params.adc_bits)
    captures = {name: _capture(model, plan[name]) for name in LADDER_NAMES}
    ladder = _ladder(captures)
    assert ladder is not None
    assert ladder.enob_bits[0] == pytest.approx(adc_bits, abs=0.02)
    quantization = captures[LADDER_NAMES[0]]
    at_amplitude = analyze_dynamic(quantization, calibration=_extracted(quantization)).spectral_enob_bits
    assert at_amplitude == pytest.approx(adc_bits - 0.5 / 6.02, abs=0.02)
