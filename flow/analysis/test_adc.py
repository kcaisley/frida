"""Software-only tests for typed ADC analyses."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import hdl21 as h
import numpy as np
import pytest

from flow.analysis.adc import (
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise,
    analyze_adc_noise_sweep,
    analyze_adc_nonlin,
    analyze_adc_power_sweep,
    analyze_adc_transfer,
)
from flow.analysis.types import AdcDaq, AdcExtWave, InfoValue, MeasAdcExt, MeasInfo
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
) -> MeasAdcExt:
    """Build one compact external ADC measurement for numerical tests."""

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
    return MeasAdcExt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasAdcExt",
            backend="behavioral",
            timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC),
            readbacks=dict(readbacks or {}),
        ),
        param=param,
        daq=AdcDaq(
            conversion_index=np.arange(len(dout)),
            bout=np.zeros((len(dout), 17), dtype=np.uint8),
            dout_raw=dout,
            dout=dout,
            vin_diff_v=vin_diff_array,
        ),
        wave=AdcExtWave(
            conversion_index=np.asarray([0], dtype=np.int64),
            time_s=time_s,
            vin_diff_v=zeros,
            seq_comp_v=zeros,
            seq_logic_v=zeros,
            comp_out_v=zeros,
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
    noise = analyze_adc_noise([msmt])
    linearity = analyze_adc_nonlin(msmt, method="code_density", code_range=(1, 2))

    np.testing.assert_allclose(transfer.mean_dout, (0.0, 1.5, 3.0))
    np.testing.assert_array_equal(noise.count.sum(axis=0)[:4], (2, 1, 1, 2))
    assert linearity.ideal_count == 1.0
    assert linearity.missing_codes == 0
    np.testing.assert_allclose(linearity.dnl, (0.0, 0.0))


def test_endpoint_linearity_interpolates_static_code_transitions() -> None:
    inputs = np.linspace(-0.6, 0.6, 129)
    ideal_codes = np.rint(np.linspace(0.0, 15.0, len(inputs)))
    ideal = analyze_adc_nonlin(
        adc_measurement(ideal_codes, vin_diff_v=inputs),
        method="endpoint",
    )
    assert ideal.endpoint_lsb_v == pytest.approx(0.08, abs=0.01)
    assert ideal.missing_codes == 0

    nonlinear_codes = np.rint(
        np.linspace(0.0, 15.0, len(inputs)) + 0.6 * np.sin(np.pi * np.linspace(0.0, 15.0, len(inputs)) / 15.0)
    )
    nonlinear = analyze_adc_nonlin(
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
    with pytest.raises(ValueError, match=message):
        analyze_adc_dynamic(
            msmt,
            sample_rate_hz=sample_rate_hz,
            input_frequency_hz=input_frequency_hz,
        )
