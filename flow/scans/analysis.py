"""Hardware-free numerical analyses for physical and simulated ADC results."""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal.windows import blackmanharris


@dataclass(frozen=True, slots=True)
class SineFitResult:
    """Four-parameter sine fit and dynamic ADC metrics for one continuous record."""

    sample_rate_hz: float
    input_frequency_hz: float
    fitted_frequency_hz: float
    sample_count: int
    adc_bits: int
    offset_codes: float
    amplitude_codes: float
    phase_rad: float
    amplitude_dbfs: float
    signal_rms_codes: float
    residual_rms_codes: float
    sinad_db: float
    enob_bits: float
    spectral_sndr_db: float
    spectral_snr_db: float
    spectral_thd_db: float
    spectral_sfdr_db: float
    spectral_enob_bits: float
    time_s: np.ndarray
    measured_codes: np.ndarray
    fitted_codes: np.ndarray
    residual_codes: np.ndarray
    spectrum_frequency_hz: np.ndarray
    spectrum_dbfs: np.ndarray


def analyze_adc_sine_fit(
    samples_or_csv: Sequence[float] | Path,
    sample_rate_hz: float,
    input_frequency_hz: float,
    *,
    adc_bits: int = 12,
    frequency_search_fraction: float = 0.02,
    maximum_harmonic_order: int = 5,
) -> SineFitResult:
    """Fit one ADC sine record and calculate time- and frequency-domain metrics.

    The fitted model is ``A*sin(2*pi*f*t) + B*cos(2*pi*f*t) + C``.
    For each candidate frequency, amplitude, phase, and offset are solved by
    linear least squares. A bounded scalar minimization supplies the fourth
    fitted parameter, frequency. Residual power therefore includes noise,
    harmonics, nonlinearity, and sampling error, as required for SINAD.

    ``samples_or_csv`` may be a sequence of normalized output codes or a typed
    scan CSV containing ``dout``. Legacy CSVs containing ``Dout`` are accepted.
    The record must be uniformly sampled without acquisition gaps.

    The frequency-domain calculation applies a four-term Blackman-Harris
    window, integrates the fundamental and aliased harmonic main lobes, and
    reports SNDR, SNR, THD, SFDR, and ENOB. ``maximum_harmonic_order`` controls
    which harmonic lobes are separated from noise for SNR and THD.
    """

    if isinstance(samples_or_csv, Path):
        with samples_or_csv.open(newline="") as input_file:
            reader = csv.DictReader(input_file)
            fieldnames = set(reader.fieldnames or ())
            if "dout" in fieldnames:
                code_field = "dout"
            elif "Dout" in fieldnames:
                code_field = "Dout"
            else:
                raise ValueError("ADC sine-fit CSV must contain a dout or Dout column")
            measured_codes = np.fromiter(
                (float(row[code_field]) for row in reader),
                dtype=np.float64,
            )
    else:
        measured_codes = np.asarray(samples_or_csv, dtype=np.float64)

    if measured_codes.ndim != 1:
        raise ValueError("ADC sine-fit samples must be one-dimensional")
    if measured_codes.size < 8:
        raise ValueError("ADC sine fit requires at least eight samples")
    if not np.all(np.isfinite(measured_codes)):
        raise ValueError("ADC sine-fit samples must all be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if not math.isfinite(input_frequency_hz) or input_frequency_hz <= 0 or input_frequency_hz >= sample_rate_hz / 2:
        raise ValueError("input_frequency_hz must be finite and between zero and Nyquist")
    if isinstance(adc_bits, bool) or not isinstance(adc_bits, int) or adc_bits <= 0:
        raise ValueError("adc_bits must be a positive integer")
    if not math.isfinite(frequency_search_fraction) or frequency_search_fraction < 0 or frequency_search_fraction >= 1:
        raise ValueError("frequency_search_fraction must be finite and in [0, 1)")
    if (
        isinstance(maximum_harmonic_order, bool)
        or not isinstance(maximum_harmonic_order, int)
        or maximum_harmonic_order < 2
    ):
        raise ValueError("maximum_harmonic_order must be an integer of at least two")

    time_s = np.arange(measured_codes.size, dtype=np.float64) / sample_rate_hz
    ones = np.ones(measured_codes.size, dtype=np.float64)

    def fit_at_frequency(frequency_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        phase = 2.0 * np.pi * frequency_hz * time_s
        sine = np.sin(phase)
        cosine = np.cos(phase)
        design = np.column_stack((sine, cosine, ones))
        coefficients, _residuals, _rank, _singular_values = np.linalg.lstsq(
            design,
            measured_codes,
            rcond=None,
        )
        fitted = design @ coefficients
        residual = measured_codes - fitted
        residual_power = float(np.mean(residual * residual))
        return coefficients, fitted, residual, residual_power

    if frequency_search_fraction:
        # Keep the bounded search inside one least-squares minimum. The
        # programmed/ read-back AWG frequency supplies the coarse estimate;
        # half a DFT bin is sufficient to refine it without crossing one of
        # the many adjacent minima present in a long record.
        maximum_frequency_offset_hz = min(
            input_frequency_hz * frequency_search_fraction,
            0.45 * sample_rate_hz / measured_codes.size,
        )
        lower_frequency_hz = max(
            np.nextafter(0.0, 1.0),
            input_frequency_hz - maximum_frequency_offset_hz,
        )
        upper_frequency_hz = min(
            np.nextafter(sample_rate_hz / 2.0, 0.0),
            input_frequency_hz + maximum_frequency_offset_hz,
        )
        frequency_fit = minimize_scalar(
            lambda frequency_hz: fit_at_frequency(float(frequency_hz))[3],
            bounds=(lower_frequency_hz, upper_frequency_hz),
            method="bounded",
            options={"xatol": max(1e-9, input_frequency_hz * 1e-10)},
        )
        if not frequency_fit.success:
            raise RuntimeError(f"ADC sine frequency fit failed: {frequency_fit.message}")
        fitted_frequency_hz = float(frequency_fit.x)
    else:
        fitted_frequency_hz = float(input_frequency_hz)

    coefficients, fitted_codes, residual_codes, residual_power = fit_at_frequency(fitted_frequency_hz)
    sine_coefficient, cosine_coefficient, offset_codes = (float(value) for value in coefficients)
    amplitude_codes = math.hypot(sine_coefficient, cosine_coefficient)
    phase_rad = math.atan2(cosine_coefficient, sine_coefficient)
    signal_rms_codes = amplitude_codes / math.sqrt(2.0)
    residual_rms_codes = math.sqrt(residual_power)
    if signal_rms_codes == 0:
        sinad_db = -math.inf
    elif residual_rms_codes == 0:
        sinad_db = math.inf
    else:
        sinad_db = 20.0 * math.log10(signal_rms_codes / residual_rms_codes)
    enob_bits = (sinad_db - 1.76) / 6.02

    full_scale_peak_codes = ((1 << adc_bits) - 1) / 2.0
    amplitude_dbfs = 20.0 * math.log10(amplitude_codes / full_scale_peak_codes) if amplitude_codes > 0 else -math.inf

    # Use a low-sidelobe window because the laboratory stimulus is
    # intentionally non-coherent with the ADC sample clock. Four bins on
    # either side of each tone contain the Blackman-Harris main lobe.
    window = blackmanharris(measured_codes.size, sym=False)
    windowed_codes = (measured_codes - offset_codes) * window
    spectrum = np.fft.rfft(windowed_codes)
    spectrum_frequency_hz = np.fft.rfftfreq(
        measured_codes.size,
        d=1.0 / sample_rate_hz,
    )
    spectrum_amplitude_codes = 2.0 * np.abs(spectrum) / float(np.sum(window))
    spectrum_amplitude_codes[0] *= 0.5
    if measured_codes.size % 2 == 0:
        spectrum_amplitude_codes[-1] *= 0.5
    spectrum_dbfs = 20.0 * np.log10(
        np.maximum(
            spectrum_amplitude_codes / full_scale_peak_codes,
            np.finfo(np.float64).tiny,
        )
    )

    spectral_power = np.abs(spectrum) ** 2
    if measured_codes.size % 2 == 0:
        spectral_power[1:-1] *= 2.0
    else:
        spectral_power[1:] *= 2.0
    spectral_power[0] = 0.0

    bin_width_hz = sample_rate_hz / measured_codes.size
    main_lobe_half_width_bins = 4

    def tone_bins(tone_frequency_hz: float) -> set[int]:
        center_bin = round(tone_frequency_hz / bin_width_hz)
        return set(
            range(
                max(1, center_bin - main_lobe_half_width_bins),
                min(
                    len(spectral_power),
                    center_bin + main_lobe_half_width_bins + 1,
                ),
            )
        )

    fundamental_bins = tone_bins(fitted_frequency_hz)
    harmonic_bins: set[int] = set()
    for harmonic_order in range(2, maximum_harmonic_order + 1):
        wrapped_frequency_hz = (harmonic_order * fitted_frequency_hz) % sample_rate_hz
        aliased_frequency_hz = min(
            wrapped_frequency_hz,
            sample_rate_hz - wrapped_frequency_hz,
        )
        harmonic_bins.update(tone_bins(aliased_frequency_hz) - fundamental_bins)

    signal_bins = fundamental_bins | harmonic_bins
    noise_bins = set(range(1, len(spectral_power))) - signal_bins
    fundamental_power = float(np.sum(spectral_power[list(fundamental_bins)]))
    harmonic_power = float(np.sum(spectral_power[list(harmonic_bins)]))
    noise_power = float(np.sum(spectral_power[list(noise_bins)]))
    distortion_and_noise_power = harmonic_power + noise_power

    if fundamental_power <= 0:
        spectral_sndr_db = -math.inf
        spectral_snr_db = -math.inf
    else:
        spectral_sndr_db = (
            10.0 * math.log10(fundamental_power / distortion_and_noise_power)
            if distortion_and_noise_power > 0
            else math.inf
        )
        spectral_snr_db = 10.0 * math.log10(fundamental_power / noise_power) if noise_power > 0 else math.inf
    if fundamental_power <= 0:
        spectral_thd_db = math.inf if harmonic_power > 0 else -math.inf
    else:
        spectral_thd_db = 10.0 * math.log10(harmonic_power / fundamental_power) if harmonic_power > 0 else -math.inf

    spur_candidates = np.array(
        sorted(set(range(1, len(spectral_power))) - fundamental_bins),
        dtype=int,
    )
    if fundamental_power > 0 and spur_candidates.size:
        spur_center_bin = int(spur_candidates[np.argmax(spectral_power[spur_candidates])])
        spur_bins = tone_bins(spectrum_frequency_hz[spur_center_bin]) - fundamental_bins
        spur_power = float(np.sum(spectral_power[list(spur_bins)]))
        spectral_sfdr_db = 10.0 * math.log10(fundamental_power / spur_power) if spur_power > 0 else math.inf
    else:
        spectral_sfdr_db = math.inf
    spectral_enob_bits = (spectral_sndr_db - 1.76) / 6.02

    return SineFitResult(
        sample_rate_hz=float(sample_rate_hz),
        input_frequency_hz=float(input_frequency_hz),
        fitted_frequency_hz=fitted_frequency_hz,
        sample_count=int(measured_codes.size),
        adc_bits=adc_bits,
        offset_codes=float(offset_codes),
        amplitude_codes=amplitude_codes,
        phase_rad=phase_rad,
        amplitude_dbfs=amplitude_dbfs,
        signal_rms_codes=signal_rms_codes,
        residual_rms_codes=residual_rms_codes,
        sinad_db=sinad_db,
        enob_bits=enob_bits,
        spectral_sndr_db=spectral_sndr_db,
        spectral_snr_db=spectral_snr_db,
        spectral_thd_db=spectral_thd_db,
        spectral_sfdr_db=spectral_sfdr_db,
        spectral_enob_bits=spectral_enob_bits,
        time_s=time_s,
        measured_codes=measured_codes,
        fitted_codes=fitted_codes,
        residual_codes=residual_codes,
        spectrum_frequency_hz=spectrum_frequency_hz,
        spectrum_dbfs=spectrum_dbfs,
    )
