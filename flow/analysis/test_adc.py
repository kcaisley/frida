"""Software-only tests for typed ADC analyses."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime

import hdl21 as h
import numpy as np
import pytest

from flow.adc import AdcParams
from flow.analysis.adc import (
    analyze_adc_code_distribution,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise_sweep,
    analyze_adc_nonlinearity,
    analyze_adc_power_sweep,
    analyze_adc_ramp,
    analyze_adc_transfer,
    combine_adc_noise_comparison,
    decode_bout,
)
from flow.analysis.types import (
    AdcDaq,
    AdcExtWave,
    AdcIntWave,
    AnalysisAdcCalibration,
    InfoValue,
    MeasAdc,
    MeasAdcExt,
    MeasAdcInt,
    MeasInfo,
)
from flow.cdac import CdacParams
from flow.scans.params import AdcTbParams


def adc_measurement(
    dout,
    *,
    vin_diff_v: float | Sequence[float] | np.ndarray = 0.0,
    sample_rate_hz: float = 1.0e6,
    input_frequency_hz: float = 10.0e3,
    logic_phase_delay_symbols: float = 0.0,
    observed_adc: int | None = None,
    readbacks: Mapping[str, InfoValue] | None = None,
    internal: bool = False,
) -> MeasAdc:
    """Build one compact external or internal ADC measurement for numerical tests."""

    dout = np.asarray(dout, dtype=np.int64)
    vin_diff_array = np.asarray(vin_diff_v, dtype=np.float64)
    if vin_diff_array.ndim == 0:
        vin_diff_array = np.full(len(dout), vin_diff_array.item())
    template = AdcTbParams()
    measurement_selection = {}
    if observed_adc is not None:
        measurement_selection = {
            "board_id": "test_board",
            "observed_adc": observed_adc,
            "active_adc_mask": tuple(int(index == observed_adc) for index in reversed(range(16))),
        }
    param = AdcTbParams(
        conversions=len(dout),
        symbol_rate=sample_rate_hz * len(template.seq_init_pattern),
        vin_diff=h.Vsin.Params(voff=0.0, vamp=0.5, freq=input_frequency_hz),
        seq_logic_phase_delay_symbols=logic_phase_delay_symbols,
        **measurement_selection,
    )
    time_s = np.linspace(0.0, 1.0 / sample_rate_hz, 8)
    zeros = np.zeros((1, len(time_s)))
    daq = AdcDaq(
        conversion_index=np.arange(len(dout)),
        bout=np.zeros((len(dout), 17), dtype=np.uint8),
        dout_raw=dout,
        dout=dout,
        vin_diff_v=vin_diff_array,
    )
    if internal:
        return MeasAdcInt(
            info=MeasInfo(
                schema_version=1,
                measurement_type="MeasAdcInt",
                backend="spice",
                timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC),
                readbacks=dict(readbacks or {}),
            ),
            param=param,
            daq=daq,
            wave=AdcIntWave(
                conversion_index=np.asarray([0], dtype=np.int64),
                time_s=time_s,
                vin_diff_v=zeros,
                seq_comp_v=zeros,
                seq_logic_v=zeros,
                comp_out_v=zeros,
                vin_p_v=zeros,
                vin_n_v=zeros,
                seq_init_v=zeros,
                seq_samp_v=zeros,
                vdac_p_v=zeros,
                vdac_n_v=zeros,
                clk_samp_p_v=zeros,
                clk_samp_p_b_v=zeros,
                clk_samp_n_v=zeros,
                clk_samp_n_b_v=zeros,
                clk_comp_v=zeros,
                comp_out_p_v=zeros,
                comp_out_n_v=zeros,
                dac_state_p_15_v=zeros,
                dac_state_p_8_v=zeros,
                dac_state_p_0_v=zeros,
                dac_state_n_15_v=zeros,
                dac_state_n_8_v=zeros,
                dac_state_n_0_v=zeros,
                dac_botplate_p_15_v=zeros,
                dac_botplate_p_8_v=zeros,
                dac_botplate_p_0_v=zeros,
                dac_botplate_n_15_v=zeros,
                dac_botplate_n_8_v=zeros,
                dac_botplate_n_0_v=zeros,
                vdd_a_i=zeros,
                vdd_d_i=zeros,
                vdd_dac_i=zeros,
            ),
        )
    return MeasAdcExt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasAdcExt",
            backend="behavioral",
            timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC),
            readbacks=dict(readbacks or {}),
        ),
        param=param,
        daq=daq,
        wave=AdcExtWave(
            conversion_index=np.asarray([0], dtype=np.int64),
            time_s=time_s,
            vin_diff_v=zeros,
            seq_comp_v=zeros,
            seq_logic_v=zeros,
            comp_out_v=zeros,
        ),
    )


def adc_ramp_measurement(*, cycles: int = 4, observed_adc: int = 0) -> MeasAdcExt:
    """Build a repeated monotonic decision ramp with visible reset edges."""

    samples_per_cycle = 4_096
    rng = np.random.default_rng(20260812)
    one_cycle_bout = rng.integers(0, 2, size=(samples_per_cycle, 17), dtype=np.uint8)
    one_cycle_bout[0] = 0
    one_cycle_bout[-1] = 1
    nominal_weights = np.asarray(
        [2 * value for value in (768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1)] + [1]
    )
    order = np.argsort(one_cycle_bout @ nominal_weights, kind="stable")
    one_cycle_bout = one_cycle_bout[order]
    bout = np.tile(one_cycle_bout, (cycles, 1)).astype(np.uint8, copy=False)
    sample_count = len(bout)
    dout_raw = bout @ nominal_weights
    dout = np.rint(dout_raw * 4_095 / np.sum(nominal_weights)).astype(np.int64)
    vin_diff_v = np.tile(np.linspace(-1.0, 1.0, samples_per_cycle, endpoint=False), cycles)
    base = adc_measurement(np.zeros(sample_count, dtype=np.int64), observed_adc=observed_adc)
    assert isinstance(base, MeasAdcExt)
    params = AdcTbParams(
        dut=base.param.dut,
        conversions=sample_count,
        symbol_rate=base.param.symbol_rate,
        board_id="test_board",
        observed_adc=observed_adc,
        active_adc_mask=tuple(int(index == observed_adc) for index in reversed(range(16))),
        campaign="adc_ramp",
        vin_cm=h.Vdc.Params(dc=0.6),
        vin_diff=h.Vpwl.Params(wave="0 -1 0.001 1"),
    )
    return replace(
        base,
        param=params,
        daq=AdcDaq(
            conversion_index=np.arange(sample_count),
            bout=bout,
            dout_raw=dout_raw,
            dout=dout,
            vin_diff_v=vin_diff_v,
        ),
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
    result = analyze_adc_dynamic(msmt)

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
    """Count each ±24 LSB tail without deleting samples from the analysis."""

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

    result = analyze_adc_dynamic(msmt)
    assert result.residual_tail_limit_dout == 24.0
    assert result.expected_residual_tail_count == pytest.approx(len(samples) * 0.0027)
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
    result = analyze_adc_dynamic(
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


def test_transfer_noise_and_code_density_use_typed_adc_data() -> None:
    msmt = adc_measurement(
        [0, 0, 1, 2, 3, 3],
        vin_diff_v=[-0.1, -0.1, 0.0, 0.0, 0.1, 0.1],
    )
    transfer = analyze_adc_transfer([msmt])
    noise = analyze_adc_code_distribution([msmt])
    linearity = analyze_adc_nonlinearity(msmt, method="code_density", code_range=(1, 2))

    np.testing.assert_allclose(transfer.mean_dout, (0.0, 1.5, 3.0))
    np.testing.assert_array_equal(noise.count.sum(axis=0)[:4], (2, 1, 1, 2))
    assert linearity.ideal_count == 1.0
    assert linearity.missing_codes == 0
    np.testing.assert_allclose(linearity.dnl, (0.0, 0.0))


def test_ramp_analysis_infers_repeated_reset_frequency_and_phase() -> None:
    """Use reset timing instead of assuming the AWG and capture start together."""

    measurement = adc_ramp_measurement()
    analysis = analyze_adc_ramp(measurement)

    assert analysis.adc_index == 0
    assert analysis.sample_count == 4 * 4_096
    assert analysis.ramp_frequency_hz == pytest.approx(analysis.sample_rate_hz / 4_096)
    assert len(analysis.reset_conversion_index) == 3
    assert len(analysis.curves) == 1
    assert analysis.curves[0].decoding == "uncalibrated_dout"
    assert analysis.curves[0].label == "Uncalibrated DOUT"
    assert analysis.reset_excluded_sample_count == 3 * 8
    assert analysis.retained_sample_count == analysis.sample_count - analysis.reset_excluded_sample_count
    assert analysis.curves[0].count.sum() == analysis.retained_sample_count
    assert len(analysis.curves[0].transfer_vin_diff_v) == 4_096


def test_ramp_analysis_redecodes_with_common_calibration_weights() -> None:
    """Apply any calibration result to stored decisions without new HDF5."""

    measurement = adc_ramp_measurement()
    nominal = analyze_adc_ramp(measurement).curves[0].weights.astype(np.float64)
    nominal *= 4095.0 / np.sum(nominal)
    calibrated = nominal.copy()
    calibrated[:2] *= (1.02, 0.97)
    calibrated *= 4095.0 / np.sum(calibrated)
    calibration = AnalysisAdcCalibration(
        adc_index=0,
        method="calibration1",
        label="Synthetic calibrated BOUT",
        code_max=4095,
        nominal_weight=nominal,
        calibrated_weight=calibrated,
        weight_from_measurement=np.ones(17, dtype=np.bool_),
        training_sample_count=100,
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )

    analysis = analyze_adc_ramp(measurement, calibrations=(calibration,))

    assert [curve.decoding for curve in analysis.curves] == ["uncalibrated_dout", "calibration1"]
    assert [curve.label for curve in analysis.curves] == ["Uncalibrated DOUT", "Synthetic calibrated BOUT"]
    assert all(curve.count.sum() == analysis.retained_sample_count for curve in analysis.curves)
    assert not np.array_equal(analysis.curves[0].weights, analysis.curves[1].weights)
    assert analysis.curves[1].weights[0] == pytest.approx(calibrated[0])
    decoded = decode_bout(measurement.daq.bout, calibration)
    distribution = analyze_adc_code_distribution([measurement], calibration=calibration)
    nonlinearity = analyze_adc_nonlinearity(
        measurement,
        method="code_density",
        calibration=calibration,
    )
    assert distribution.count.sum() == len(decoded)
    assert nonlinearity.count is not None
    assert nonlinearity.count.sum() == np.count_nonzero((decoded >= 1) & (decoded <= 4094))
    with pytest.raises(ValueError, match="same ADC"):
        analyze_adc_ramp(measurement, calibrations=(replace(calibration, adc_index=1),))


def test_shared_adc_analyses_accept_internal_measurements() -> None:
    """Analyze simulated ADC data through the same public entry points."""

    static = adc_measurement(
        [0, 0, 1, 2, 3, 3],
        vin_diff_v=[-0.1, -0.1, 0.0, 0.0, 0.1, 0.1],
        internal=True,
    )
    assert isinstance(static, MeasAdcInt)
    assert analyze_adc_transfer([static]).sample_count.sum() == 6
    assert analyze_adc_code_distribution([static]).sample_count.sum() == 6
    assert (
        analyze_adc_nonlinearity(
            static,
            method="code_density",
            code_range=(1, 2),
        ).missing_codes
        == 0
    )

    sample_rate_hz = 100_000.0
    input_frequency_hz = 1_000.0
    time_s = np.arange(2_048) / sample_rate_hz
    dynamic = adc_measurement(
        np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s)),
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz,
        internal=True,
    )
    assert analyze_adc_dynamic(dynamic).sample_count == len(time_s)


def test_endpoint_linearity_interpolates_static_code_transitions() -> None:
    inputs = np.linspace(-0.6, 0.6, 129)
    ideal_codes = np.rint(np.linspace(0.0, 15.0, len(inputs)))
    ideal = analyze_adc_nonlinearity(
        adc_measurement(ideal_codes, vin_diff_v=inputs),
        method="endpoint",
    )
    assert ideal.endpoint_lsb_v == pytest.approx(0.08, abs=0.01)
    assert ideal.missing_codes == 0

    nonlinear_codes = np.rint(
        np.linspace(0.0, 15.0, len(inputs)) + 0.6 * np.sin(np.pi * np.linspace(0.0, 15.0, len(inputs)) / 15.0)
    )
    nonlinear = analyze_adc_nonlinearity(
        adc_measurement(nonlinear_codes, vin_diff_v=inputs),
        method="endpoint",
    )
    assert nonlinear.maximum_abs_inl > 0.05


def test_decision_paths_select_matching_output_codes() -> None:
    msmt = adc_measurement([5, 5, 3])
    bout = np.asarray(
        [
            [1, 0, 1] + [0] * 14,
            [1, 0, 1] + [0] * 14,
            [0, 1, 1] + [0] * 14,
        ],
        dtype=np.uint8,
    )
    object.__setattr__(msmt.daq, "bout", bout)
    paths = analyze_adc_decision_paths(msmt, selection="same_dout")

    assert paths.estimate_dout.shape == (2, 18)
    np.testing.assert_array_equal(paths.final_dout, (5, 5))


def test_decision_paths_normalize_redundant_raw_weights() -> None:
    """Keep the running estimate in nominal ADC LSB for non-4095 raw sums."""

    msmt = adc_measurement([4095])
    weights = (768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)
    object.__setattr__(
        msmt,
        "param",
        AdcTbParams(
            **(
                vars(msmt.param)
                | {
                    "dut": AdcParams(
                        adc_bits=12,
                        n_cycles=16,
                        cdac=CdacParams(n_dac=11, n_extra=5, weights=weights),
                    )
                }
            )
        ),
    )
    object.__setattr__(msmt.daq, "bout", np.ones((1, 17), dtype=np.uint8))

    paths = analyze_adc_decision_paths(msmt, selection="all")

    assert paths.estimate_dout[0, 0] == pytest.approx(2047.5)
    assert paths.estimate_dout[0, -1] == pytest.approx(4095.0)


def test_dynamic_sweep_retains_rate_frequency_and_logic_phase() -> None:
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
    sweep = analyze_adc_dynamic_sweep(measurements, frequency_search_fraction=0.0)
    np.testing.assert_allclose(sweep.input_frequency_hz, (1_000.0, 5_000.0))
    np.testing.assert_allclose(sweep.sample_rate_hz, (100_000.0, 100_000.0))
    np.testing.assert_array_equal(sweep.logic_phase_delay_symbols, (-1, 0))
    np.testing.assert_array_equal(sweep.observed_adc, (-1, -1))
    assert np.all(sweep.input_referred_noise_rms_v > 0)


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

    power = analyze_adc_power_sweep(measurements)

    np.testing.assert_array_equal(power.observed_adc, (0, 1))
    np.testing.assert_allclose(power.vdd_d_static_power_w, (24e-6, 12e-6))
    np.testing.assert_allclose(power.vdd_d_dynamic_power_w, (24e-6, 36e-6))
    np.testing.assert_allclose(power.total_static_power_w, (37.2e-6, 18.6e-6))
    np.testing.assert_allclose(power.total_dynamic_power_w, (37.2e-6, 55.8e-6))
    np.testing.assert_allclose(power.total_power_w, (74.4e-6, 74.4e-6))


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

    sweep = analyze_adc_noise_sweep([low, high])

    # The default pattern has 160 active symbols within a 256-symbol repeat.
    np.testing.assert_allclose(sweep.sample_rate_hz, [1.6e6, 3.2e6])
    np.testing.assert_allclose(sweep.comparator_time_percent, [12.5, 87.5])
    assert sweep.input_lsb_v == pytest.approx(1.2 / 4095)
    np.testing.assert_allclose(
        sweep.input_referred_noise_rms_v,
        sweep.std_dout * 1.2 / 4095,
    )
    assert np.all(np.isnan(sweep.pretrigger_vin_diff_mean_v))
    assert np.all(np.isnan(sweep.pretrigger_vin_diff_noise_rms_v))


def test_noise_sweep_extracts_pretrigger_input_noise() -> None:
    msmt = adc_measurement([100, 101, 100])
    time_s = np.asarray((-2.0, -1.0, 0.0, 1.0)) * 1e-9
    vin_diff_v = np.asarray(((-0.051, -0.049, -0.040, -0.060),))
    msmt = replace(
        msmt,
        wave=replace(
            msmt.wave,
            time_s=time_s,
            vin_diff_v=vin_diff_v,
            seq_comp_v=np.zeros_like(vin_diff_v),
            seq_logic_v=np.zeros_like(vin_diff_v),
            comp_out_v=np.zeros_like(vin_diff_v),
        ),
    )

    sweep = analyze_adc_noise_sweep([msmt])

    np.testing.assert_allclose(sweep.pretrigger_vin_diff_mean_v, [-0.05])
    np.testing.assert_allclose(sweep.pretrigger_vin_diff_noise_rms_v, [0.001])


def test_noise_comparison_combines_dc_dynamic_and_simulated_series() -> None:
    dc_noise = analyze_adc_noise_sweep(
        [
            adc_measurement([100, 101, 100], sample_rate_hz=2.0e6),
            adc_measurement([100, 102, 101], sample_rate_hz=1.0e6),
        ]
    )
    dc_noise_100mv = analyze_adc_noise_sweep(
        [
            adc_measurement([200, 201, 200], sample_rate_hz=1.0e6),
            adc_measurement([200, 202, 201], sample_rate_hz=2.0e6),
        ]
    )
    sample_rate_hz = 100_000.0
    input_frequency_hz = 1_000.0
    time_s = np.arange(2_048) / sample_rate_hz
    sine_dynamic = analyze_adc_dynamic_sweep(
        [
            adc_measurement(
                np.rint(2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s)),
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=input_frequency_hz,
            )
        ],
        frequency_search_fraction=0.0,
    )

    comparison = combine_adc_noise_comparison(
        (dc_noise, dc_noise_100mv),
        sine_dynamic,
        (dc_noise,),
    )

    assert len(comparison.sample_rate_hz) == 9
    np.testing.assert_array_equal(comparison.sample_rate_hz[:2], np.sort(dc_noise.sample_rate_hz))
    np.testing.assert_array_equal(comparison.sample_rate_hz[-2:], dc_noise.sample_rate_hz)
    assert comparison.input_lsb_v == dc_noise.input_lsb_v

    mismatched_lsb = replace(dc_noise, input_lsb_v=2.0 * dc_noise.input_lsb_v)
    with pytest.raises(ValueError, match="one nominal input LSB scale"):
        combine_adc_noise_comparison((dc_noise, mismatched_lsb), sine_dynamic)


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
        param=AdcTbParams(
            **(
                vars(msmt.param)
                | {
                    "symbol_rate": sample_rate_hz * len(msmt.param.seq_init_pattern),
                    "vin_diff": h.Vsin.Params(voff=0.0, vamp=0.5, freq=input_frequency_hz),
                }
            )
        ),
    )
    with pytest.raises(ValueError, match=message):
        analyze_adc_dynamic(msmt)
