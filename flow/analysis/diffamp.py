"""Differential-amplifier output-noise analysis."""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import welch

from flow.analysis.types import AnalysisDiffampNoise


def analyze_diffamp_noise(
    samples_v: np.ndarray,
    *,
    sample_interval_s: float,
    measurement_bandwidth_hz: float,
) -> AnalysisDiffampNoise:
    """Fit a Gaussian width and Welch-averaged one-sided noise density."""

    samples = np.asarray(samples_v, dtype=np.float64)
    if samples.ndim != 1 or len(samples) < 256:
        raise ValueError("diff-amp noise analysis requires at least 256 one-dimensional samples")
    if np.any(~np.isfinite(samples)):
        raise ValueError("diff-amp noise samples must be finite")
    if not math.isfinite(sample_interval_s) or sample_interval_s <= 0.0:
        raise ValueError("sample interval must be finite and positive")
    nyquist_hz = 0.5 / sample_interval_s
    if not math.isfinite(measurement_bandwidth_hz) or not 0.0 < measurement_bandwidth_hz <= nyquist_hz:
        raise ValueError("measurement bandwidth must be finite, positive, and no greater than Nyquist")

    mean_v = float(np.mean(samples))
    centered_v = samples - mean_v
    noise_rms_v = float(np.sqrt(np.mean(centered_v**2)))
    sample_rate_hz = 1.0 / sample_interval_s
    segment_length = min(262_144, len(centered_v))
    frequency_hz, power_spectral_density_v2_per_hz = welch(
        centered_v,
        fs=sample_rate_hz,
        window="hann",
        nperseg=segment_length,
        noverlap=segment_length // 2,
        detrend=False,
        return_onesided=True,
        scaling="density",
    )
    density = np.sqrt(np.maximum(power_spectral_density_v2_per_hz, 0.0))
    integrated_rms_v = float(np.sqrt(np.trapezoid(power_spectral_density_v2_per_hz, frequency_hz)))
    return AnalysisDiffampNoise(
        mean_v=mean_v,
        centered_v=centered_v,
        noise_rms_v=noise_rms_v,
        sample_rate_hz=sample_rate_hz,
        measurement_bandwidth_hz=measurement_bandwidth_hz,
        frequency_hz=frequency_hz,
        amplitude_spectral_density_v_per_sqrt_hz=density,
        integrated_fft_noise_rms_v=integrated_rms_v,
    )
