"""Software-only tests for ADC result analysis; no hardware I/O is performed."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pytest

from flow.scans.analysis import analyze_adc_sine_fit


def test_four_parameter_sine_fit_recovers_signal_and_dynamic_metrics() -> None:
    """Recover a noisy sine's frequency, amplitude, offset, SINAD, and ENOB."""

    rng = np.random.default_rng(12345)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 20_000
    amplitude_codes = 1_500.0
    offset_codes = 2_040.0
    phase_rad = 0.37
    noise_rms_codes = 2.0
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = (
        offset_codes
        + amplitude_codes * np.sin(2.0 * np.pi * input_frequency_hz * time_s + phase_rad)
        + rng.normal(0.0, noise_rms_codes, sample_count)
    )

    result = analyze_adc_sine_fit(
        samples,
        sample_rate_hz,
        input_frequency_hz * (1.0 + 5e-6),
    )

    assert result.sample_count == sample_count
    assert result.fitted_frequency_hz == pytest.approx(input_frequency_hz, abs=0.02)
    assert result.amplitude_codes == pytest.approx(amplitude_codes, rel=2e-4)
    assert result.offset_codes == pytest.approx(offset_codes, abs=0.05)
    assert result.phase_rad == pytest.approx(phase_rad, abs=2e-4)
    assert result.residual_rms_codes == pytest.approx(noise_rms_codes, rel=0.03)
    assert result.sinad_db == pytest.approx(20.0 * math.log10(result.signal_rms_codes / result.residual_rms_codes))
    assert result.enob_bits == pytest.approx((result.sinad_db - 1.76) / 6.02)
    assert len(result.fitted_codes) == sample_count
    assert len(result.residual_codes) == sample_count


def test_sine_fit_reads_typed_adc_csv(tmp_path: Path) -> None:
    """Read the typed lowercase dout field and fit at a fixed frequency."""

    sample_rate_hz = 100_000.0
    input_frequency_hz = 1_000.0
    samples = 2_000.0 + 500.0 * np.sin(2.0 * np.pi * input_frequency_hz * np.arange(1_000) / sample_rate_hz)
    csv_path = tmp_path / "adc.csv"
    with csv_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("conversion_index", "dout"))
        writer.writerows(enumerate(samples))

    result = analyze_adc_sine_fit(
        csv_path,
        sample_rate_hz,
        input_frequency_hz,
        frequency_search_fraction=0.0,
    )

    assert result.sample_count == len(samples)
    assert result.fitted_frequency_hz == input_frequency_hz
    assert result.amplitude_codes == pytest.approx(500.0)
    assert result.offset_codes == pytest.approx(2_000.0)
    assert result.residual_rms_codes < 1e-9


def test_spectrum_separates_noise_and_harmonic_distortion() -> None:
    """Recover known SNR, THD, SFDR, SNDR, and spectral ENOB."""

    rng = np.random.default_rng(7)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 65_536
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = (
        2_048.0
        + 1_500.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s + 0.2)
        + 15.0 * np.sin(2.0 * np.pi * 2.0 * input_frequency_hz * time_s - 0.1)
        + rng.normal(0.0, 1.0, sample_count)
    )

    result = analyze_adc_sine_fit(
        samples,
        sample_rate_hz,
        input_frequency_hz,
    )

    assert result.spectral_snr_db == pytest.approx(60.51, abs=0.15)
    assert result.spectral_thd_db == pytest.approx(-40.0, abs=0.15)
    assert result.spectral_sfdr_db == pytest.approx(40.0, abs=0.15)
    assert result.spectral_sndr_db == pytest.approx(39.96, abs=0.15)
    assert result.spectral_enob_bits == pytest.approx((result.spectral_sndr_db - 1.76) / 6.02)
    assert result.spectral_sndr_db == pytest.approx(result.sinad_db, abs=0.15)


@pytest.mark.parametrize(
    ("samples", "sample_rate_hz", "input_frequency_hz", "message"),
    [
        ([1.0] * 7, 1_000.0, 10.0, "at least eight"),
        ([1.0] * 8, 0.0, 10.0, "sample_rate_hz"),
        ([1.0] * 8, 1_000.0, 500.0, "Nyquist"),
    ],
)
def test_sine_fit_rejects_invalid_records(
    samples: list[float],
    sample_rate_hz: float,
    input_frequency_hz: float,
    message: str,
) -> None:
    """Reject records which cannot define a physical sine fit."""

    with pytest.raises(ValueError, match=message):
        analyze_adc_sine_fit(samples, sample_rate_hz, input_frequency_hz)


def test_sine_fit_rejects_invalid_harmonic_order() -> None:
    """Require at least the second harmonic for spectral separation."""

    with pytest.raises(ValueError, match="maximum_harmonic_order"):
        analyze_adc_sine_fit(
            [1.0] * 8,
            1_000.0,
            10.0,
            maximum_harmonic_order=1,
        )
