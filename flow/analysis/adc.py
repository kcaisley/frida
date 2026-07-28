"""Hardware-free numerical analyses for normalized ADC results."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal.windows import blackmanharris

from flow.analysis.models import (
    AdcSettings,
    AnalysisKind,
    AnalysisRequest,
    AnalysisResult,
    AnalysisSpec,
    DataColumn,
    DataTable,
    Metric,
)


@dataclass(frozen=True, slots=True)
class _SineFitData:
    """Internal four-parameter sine fit and dynamic ADC calculations."""

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


@dataclass(frozen=True, slots=True)
class _SpectrumData:
    """Internal FFT arrays and ADC dynamic metrics."""

    sndr_db: float
    snr_db: float
    thd_db: float
    sfdr_db: float
    enob_bits: float
    frequency_hz: np.ndarray
    amplitude_dbfs: np.ndarray


def _calculate_adc_spectrum(
    measured_codes: np.ndarray,
    *,
    sample_rate_hz: float,
    fitted_frequency_hz: float,
    offset_codes: float,
    full_scale_peak_codes: float,
    maximum_harmonic_order: int,
) -> _SpectrumData:
    """Calculate windowed ADC SNR, SNDR, THD, SFDR, ENOB, and spectrum."""

    window = blackmanharris(measured_codes.size, sym=False)
    spectrum = np.fft.rfft((measured_codes - offset_codes) * window)
    frequency_hz = np.fft.rfftfreq(
        measured_codes.size,
        d=1.0 / sample_rate_hz,
    )
    amplitude_codes = 2.0 * np.abs(spectrum) / float(np.sum(window))
    amplitude_codes[0] *= 0.5
    if measured_codes.size % 2 == 0:
        amplitude_codes[-1] *= 0.5
    amplitude_dbfs = 20.0 * np.log10(
        np.maximum(
            amplitude_codes / full_scale_peak_codes,
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

    def tone_bins(tone_frequency_hz: float) -> set[int]:
        center_bin = round(tone_frequency_hz / bin_width_hz)
        return set(
            range(
                max(1, center_bin - 4),
                min(len(spectral_power), center_bin + 5),
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

    noise_bins = (
        set(range(1, len(spectral_power)))
        - fundamental_bins
        - harmonic_bins
    )
    fundamental_power = float(np.sum(spectral_power[list(fundamental_bins)]))
    harmonic_power = float(np.sum(spectral_power[list(harmonic_bins)]))
    noise_power = float(np.sum(spectral_power[list(noise_bins)]))
    distortion_and_noise_power = harmonic_power + noise_power
    if fundamental_power <= 0:
        sndr_db = -math.inf
        snr_db = -math.inf
        thd_db = math.inf if harmonic_power > 0 else -math.inf
    else:
        sndr_db = (
            10.0 * math.log10(fundamental_power / distortion_and_noise_power)
            if distortion_and_noise_power > 0
            else math.inf
        )
        snr_db = (
            10.0 * math.log10(fundamental_power / noise_power)
            if noise_power > 0
            else math.inf
        )
        thd_db = (
            10.0 * math.log10(harmonic_power / fundamental_power)
            if harmonic_power > 0
            else -math.inf
        )

    spur_candidates = np.asarray(
        sorted(set(range(1, len(spectral_power))) - fundamental_bins),
        dtype=np.int64,
    )
    if fundamental_power > 0 and spur_candidates.size:
        spur_center_bin = int(
            spur_candidates[np.argmax(spectral_power[spur_candidates])]
        )
        spur_bins = tone_bins(frequency_hz[spur_center_bin]) - fundamental_bins
        spur_power = float(np.sum(spectral_power[list(spur_bins)]))
        sfdr_db = (
            10.0 * math.log10(fundamental_power / spur_power)
            if spur_power > 0
            else math.inf
        )
    else:
        sfdr_db = math.inf
    return _SpectrumData(
        sndr_db=sndr_db,
        snr_db=snr_db,
        thd_db=thd_db,
        sfdr_db=sfdr_db,
        enob_bits=(sndr_db - 1.76) / 6.02,
        frequency_hz=frequency_hz,
        amplitude_dbfs=amplitude_dbfs,
    )


def _fit_adc_sine(
    samples: Sequence[float] | np.ndarray,
    sample_rate_hz: float,
    input_frequency_hz: float,
    *,
    adc_bits: int = 12,
    frequency_search_fraction: float = 0.02,
    maximum_harmonic_order: int = 5,
) -> _SineFitData:
    """Fit one ADC sine record and calculate time- and frequency-domain metrics.

    The fitted model is ``A*sin(2*pi*f*t) + B*cos(2*pi*f*t) + C``.
    For each candidate frequency, amplitude, phase, and offset are solved by
    linear least squares. A bounded scalar minimization supplies the fourth
    fitted parameter, frequency. Residual power therefore includes noise,
    harmonics, nonlinearity, and sampling error, as required for SINAD.

    The record must be uniformly sampled without acquisition gaps.

    The frequency-domain calculation applies a four-term Blackman-Harris
    window, integrates the fundamental and aliased harmonic main lobes, and
    reports SNDR, SNR, THD, SFDR, and ENOB. ``maximum_harmonic_order`` controls
    which harmonic lobes are separated from noise for SNR and THD.
    """

    measured_codes = np.asarray(samples, dtype=np.float64)

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
    # intentionally non-coherent with the ADC sample clock.
    spectral = _calculate_adc_spectrum(
        measured_codes,
        sample_rate_hz=sample_rate_hz,
        fitted_frequency_hz=fitted_frequency_hz,
        offset_codes=offset_codes,
        full_scale_peak_codes=full_scale_peak_codes,
        maximum_harmonic_order=maximum_harmonic_order,
    )

    return _SineFitData(
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
        spectral_sndr_db=spectral.sndr_db,
        spectral_snr_db=spectral.snr_db,
        spectral_thd_db=spectral.thd_db,
        spectral_sfdr_db=spectral.sfdr_db,
        spectral_enob_bits=spectral.enob_bits,
        time_s=time_s,
        measured_codes=measured_codes,
        fitted_codes=fitted_codes,
        residual_codes=residual_codes,
        spectrum_frequency_hz=spectral.frequency_hz,
        spectrum_dbfs=spectral.amplitude_dbfs,
    )


def _adc_settings(request: AnalysisRequest) -> AdcSettings:
    settings = request.spec.settings
    if not isinstance(settings, AdcSettings):
        raise TypeError(f"{request.spec.kind.value} analysis requires AdcSettings")
    if isinstance(settings.adc_bits, bool) or not isinstance(settings.adc_bits, int) or settings.adc_bits <= 0:
        raise ValueError("adc_bits must be a positive integer")
    return settings


def _run_by_id(request: AnalysisRequest, run_id: str):
    for run in request.runs:
        if run.run_id == run_id:
            return run
    raise KeyError(f"analysis request has no run {run_id!r}")


def _column_from_run(run, name: str) -> np.ndarray:
    matches = [table.column(name) for table in run.tables if name in table.column_names]
    if not matches:
        raise KeyError(
            f"run {run.run_id!r} has no column {name!r}; "
            f"available: {tuple(column for table in run.tables for column in table.column_names)}"
        )
    if len(matches) > 1:
        raise KeyError(f"run {run.run_id!r} contains ambiguous column {name!r}")
    return matches[0]


def _parameter_value(parameters, names: tuple[str, ...]):
    """Find one scalar in a nested backend-neutral parameter snapshot."""

    if isinstance(parameters, Mapping):
        for name in names:
            if name in parameters and isinstance(parameters[name], (int, float)):
                return float(parameters[name])
        for value in parameters.values():
            found = _parameter_value(value, names)
            if found is not None:
                return found
    elif isinstance(parameters, list):
        for value in parameters:
            found = _parameter_value(value, names)
            if found is not None:
                return found
    return None


def _metadata_item(metadata, name: str):
    """Find one scalar string or number in nested result metadata."""

    if isinstance(metadata, Mapping):
        if name in metadata and isinstance(metadata[name], (int, float, str)):
            return metadata[name]
        for value in metadata.values():
            found = _metadata_item(value, name)
            if found is not None:
                return found
    elif isinstance(metadata, list):
        for value in metadata:
            found = _metadata_item(value, name)
            if found is not None:
                return found
    return None


def _codes_and_inputs(
    request: AnalysisRequest,
    settings: AdcSettings,
) -> tuple[np.ndarray, np.ndarray]:
    code_parts = []
    input_parts = []
    for input_id in request.spec.input_ids:
        run = _run_by_id(request, input_id)
        codes = np.asarray(_column_from_run(run, settings.code_column), dtype=np.float64)
        try:
            inputs = np.asarray(_column_from_run(run, settings.input_column), dtype=np.float64)
        except KeyError:
            input_value = _parameter_value(
                run.parameters,
                (settings.input_column, "vin_diff_v", "vdiff_v"),
            )
            if input_value is None:
                raise ValueError(
                    f"run {run.run_id!r} has neither column {settings.input_column!r} "
                    "nor a scalar differential-input parameter"
                ) from None
            inputs = np.full(codes.size, input_value, dtype=np.float64)
        if len(inputs) != len(codes):
            raise ValueError(f"run {run.run_id!r} input and code columns are not aligned")
        code_parts.append(codes)
        input_parts.append(inputs)
    return np.concatenate(code_parts), np.concatenate(input_parts)


def analyze_adc_dynamic(request: AnalysisRequest) -> AnalysisResult:
    """Fit and spectrally analyze one normalized ADC sine acquisition."""

    settings = _adc_settings(request)
    if len(request.spec.input_ids) != 1:
        raise ValueError("ADC dynamic analysis requires exactly one input run")
    if settings.sample_rate_hz is None or settings.input_frequency_hz is None:
        raise ValueError("ADC dynamic analysis requires sample_rate_hz and input_frequency_hz")
    run = _run_by_id(request, request.spec.input_ids[0])
    measured_codes = _column_from_run(run, settings.code_column)
    fit = _fit_adc_sine(
        measured_codes,
        settings.sample_rate_hz,
        settings.input_frequency_hz,
        adc_bits=settings.adc_bits,
        frequency_search_fraction=settings.frequency_search_fraction,
        maximum_harmonic_order=settings.maximum_harmonic_order,
    )

    return AnalysisResult(
        name=request.spec.name,
        kind=AnalysisKind.ADC_DYNAMIC,
        source_ids=request.spec.input_ids,
        metrics=(
            Metric("sample_rate_hz", fit.sample_rate_hz, "Hz"),
            Metric("input_frequency_hz", fit.input_frequency_hz, "Hz"),
            Metric("fitted_frequency_hz", fit.fitted_frequency_hz, "Hz"),
            Metric("sample_count", fit.sample_count),
            Metric("adc_bits", fit.adc_bits, "bit"),
            Metric("offset_codes", fit.offset_codes, "LSB"),
            Metric("amplitude_codes", fit.amplitude_codes, "LSB"),
            Metric("phase_rad", fit.phase_rad, "rad"),
            Metric("amplitude_dbfs", fit.amplitude_dbfs, "dBFS"),
            Metric("signal_rms_codes", fit.signal_rms_codes, "LSB"),
            Metric("residual_rms_codes", fit.residual_rms_codes, "LSB"),
            Metric("sinad_db", fit.sinad_db, "dB"),
            Metric("enob_bits", fit.enob_bits, "bit"),
            Metric("spectral_sndr_db", fit.spectral_sndr_db, "dB"),
            Metric("spectral_snr_db", fit.spectral_snr_db, "dB"),
            Metric("spectral_thd_db", fit.spectral_thd_db, "dB"),
            Metric("spectral_sfdr_db", fit.spectral_sfdr_db, "dB"),
            Metric("spectral_enob_bits", fit.spectral_enob_bits, "bit"),
        ),
        tables=(
            DataTable(
                "fit",
                (
                    DataColumn("time_s", fit.time_s, "s"),
                    DataColumn("measured_codes", fit.measured_codes, "LSB"),
                    DataColumn("fitted_codes", fit.fitted_codes, "LSB"),
                    DataColumn("residual_codes", fit.residual_codes, "LSB"),
                ),
            ),
            DataTable(
                "spectrum",
                (
                    DataColumn("frequency_hz", fit.spectrum_frequency_hz, "Hz"),
                    DataColumn("amplitude_dbfs", fit.spectrum_dbfs, "dBFS"),
                ),
            ),
        ),
        metadata={
            "adc_bits": settings.adc_bits,
            "run_parameters": dict(run.parameters),
        },
    )


def analyze_adc_transfer(request: AnalysisRequest) -> AnalysisResult:
    """Calculate individual and mean ADC output codes versus input."""

    settings = _adc_settings(request)
    codes, inputs = _codes_and_inputs(request, settings)
    if not len(codes):
        raise ValueError("ADC transfer analysis requires at least one conversion")
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    mean_codes = np.asarray(
        [np.mean(codes[inverse == index]) for index in range(len(unique_inputs))],
        dtype=np.float64,
    )
    std_codes = np.asarray(
        [np.std(codes[inverse == index]) for index in range(len(unique_inputs))],
        dtype=np.float64,
    )
    counts = np.bincount(inverse, minlength=len(unique_inputs)).astype(np.int64)
    return AnalysisResult(
        name=request.spec.name,
        kind=AnalysisKind.ADC_TRANSFER,
        source_ids=request.spec.input_ids,
        metrics=(
            Metric("sample_count", len(codes)),
            Metric("input_points", len(unique_inputs)),
            Metric("minimum_code", float(np.min(codes)), "LSB"),
            Metric("maximum_code", float(np.max(codes)), "LSB"),
        ),
        tables=(
            DataTable(
                "samples",
                (
                    DataColumn("vin_diff_v", inputs, "V"),
                    DataColumn("dout", codes, "LSB"),
                ),
            ),
            DataTable(
                "transfer",
                (
                    DataColumn("vin_diff_v", unique_inputs, "V"),
                    DataColumn("mean_code", mean_codes, "LSB"),
                    DataColumn("std_code", std_codes, "LSB"),
                    DataColumn("sample_count", counts),
                ),
            ),
        ),
    )


def analyze_adc_endpoint_linearity(request: AnalysisRequest) -> AnalysisResult:
    """Calculate endpoint INL and DNL from a stepped static transfer."""

    settings = _adc_settings(request)
    codes, inputs = _codes_and_inputs(request, settings)
    if len(codes) < 3:
        raise ValueError("ADC endpoint linearity requires at least three conversions")
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    if len(unique_inputs) < 3:
        raise ValueError("ADC endpoint linearity requires at least three input points")
    mean_codes = np.asarray(
        [np.mean(codes[inverse == index]) for index in range(len(unique_inputs))],
        dtype=np.float64,
    )
    direction = 1.0 if mean_codes[-1] >= mean_codes[0] else -1.0
    increasing_codes = direction * mean_codes
    if np.any(np.diff(increasing_codes) < 0.0):
        raise ValueError("ADC endpoint linearity requires a monotonic mean transfer")

    first_transition = math.ceil(increasing_codes[0] - 0.5)
    last_transition = math.floor(increasing_codes[-1] - 0.5)
    if settings.code_range is not None:
        if direction > 0:
            range_start, range_stop = settings.code_range
        else:
            range_start, range_stop = (
                -settings.code_range[1],
                -settings.code_range[0],
            )
        first_transition = max(first_transition, range_start)
        last_transition = min(last_transition, range_stop)
    transition_codes = np.arange(
        first_transition,
        last_transition + 1,
        dtype=np.int64,
    )
    if len(transition_codes) < 2:
        raise ValueError("ADC endpoint linearity spans fewer than two code transitions")

    transition_inputs = np.interp(
        transition_codes + 0.5,
        increasing_codes,
        unique_inputs,
    )
    ideal_lsb_v = float(
        (transition_inputs[-1] - transition_inputs[0])
        / (len(transition_inputs) - 1)
    )
    if not math.isfinite(ideal_lsb_v) or ideal_lsb_v <= 0.0:
        raise ValueError("ADC endpoint linearity has a non-positive endpoint LSB")
    ideal_transitions = transition_inputs[0] + np.arange(len(transition_inputs)) * ideal_lsb_v
    transition_inl = (transition_inputs - ideal_transitions) / ideal_lsb_v
    dnl = np.diff(transition_inputs) / ideal_lsb_v - 1.0

    output_transition_codes = np.asarray(direction * transition_codes, dtype=np.int64)
    observed_codes = set(np.asarray(np.rint(codes), dtype=np.int64))
    active_codes = range(
        int(np.min(output_transition_codes)),
        int(np.max(output_transition_codes)) + 2,
    )
    missing_codes = sum(code not in observed_codes for code in active_codes)
    endpoint_gain_codes_per_v = (
        mean_codes[-1] - mean_codes[0]
    ) / (unique_inputs[-1] - unique_inputs[0])
    endpoint_offset_codes = mean_codes[0] - endpoint_gain_codes_per_v * unique_inputs[0]

    return AnalysisResult(
        name=request.spec.name,
        kind=AnalysisKind.ADC_ENDPOINT_LINEARITY,
        source_ids=request.spec.input_ids,
        metrics=(
            Metric("sample_count", len(codes)),
            Metric("input_points", len(unique_inputs)),
            Metric("endpoint_lsb_v", ideal_lsb_v, "V"),
            Metric("endpoint_gain_codes_per_v", endpoint_gain_codes_per_v, "LSB/V"),
            Metric("endpoint_offset_codes", endpoint_offset_codes, "LSB"),
            Metric("maximum_abs_dnl", float(np.max(np.abs(dnl))), "LSB"),
            Metric("maximum_abs_inl", float(np.max(np.abs(transition_inl))), "LSB"),
            Metric("rms_inl", float(np.sqrt(np.mean(transition_inl**2))), "LSB"),
            Metric("missing_codes", missing_codes),
        ),
        tables=(
            DataTable(
                "transfer",
                (
                    DataColumn("vin_diff_v", unique_inputs, "V"),
                    DataColumn("mean_code", mean_codes, "LSB"),
                ),
            ),
            DataTable(
                "transitions",
                (
                    DataColumn("code", output_transition_codes, "LSB"),
                    DataColumn("vin_diff_v", transition_inputs, "V"),
                    DataColumn("inl", transition_inl, "LSB"),
                ),
            ),
            DataTable(
                "linearity",
                (
                    DataColumn("code", output_transition_codes[1:], "LSB"),
                    DataColumn("dnl", dnl, "LSB"),
                    DataColumn("inl", transition_inl[1:], "LSB"),
                ),
            ),
        ),
        metadata={
            "first_transition_code": int(output_transition_codes[0]),
            "last_transition_code": int(output_transition_codes[-1]),
        },
    )


def analyze_adc_distribution(request: AnalysisRequest) -> AnalysisResult:
    """Calculate an ADC output-code histogram and summary statistics."""

    settings = _adc_settings(request)
    code_parts = [
        np.asarray(
            _column_from_run(_run_by_id(request, input_id), settings.code_column),
            dtype=np.int64,
        )
        for input_id in request.spec.input_ids
    ]
    codes = np.concatenate(code_parts)
    if not len(codes):
        raise ValueError("ADC distribution analysis requires at least one conversion")
    number_codes = 1 << settings.adc_bits
    valid = codes[(codes >= 0) & (codes < number_codes)]
    if not len(valid):
        raise ValueError(f"ADC distribution contains no codes in 0..{number_codes - 1}")
    counts = np.bincount(valid, minlength=number_codes)
    return AnalysisResult(
        name=request.spec.name,
        kind=AnalysisKind.ADC_DISTRIBUTION,
        source_ids=request.spec.input_ids,
        metrics=(
            Metric("sample_count", len(valid)),
            Metric("mean_code", float(np.mean(valid)), "LSB"),
            Metric("std_code", float(np.std(valid)), "LSB"),
            Metric("minimum_code", int(np.min(valid)), "LSB"),
            Metric("maximum_code", int(np.max(valid)), "LSB"),
            Metric("p01_code", float(np.percentile(valid, 1)), "LSB"),
            Metric("p99_code", float(np.percentile(valid, 99)), "LSB"),
        ),
        tables=(
            DataTable(
                "distribution",
                (
                    DataColumn("code", np.arange(number_codes, dtype=np.int64), "LSB"),
                    DataColumn("count", counts),
                ),
            ),
        ),
    )


def analyze_adc_code_density(request: AnalysisRequest) -> AnalysisResult:
    """Calculate code-density DNL and endpoint-corrected INL."""

    settings = _adc_settings(request)
    distribution = analyze_adc_distribution(
        AnalysisRequest(
            spec=AnalysisSpec(
                name=f"{request.spec.name}_distribution",
                kind=AnalysisKind.ADC_DISTRIBUTION,
                input_ids=request.spec.input_ids,
                settings=settings,
            ),
            runs=request.runs,
        )
    )
    distribution_table = distribution.table("distribution")
    all_codes = np.asarray(distribution_table.column("code"), dtype=np.int64)
    all_counts = np.asarray(distribution_table.column("count"), dtype=np.int64)
    number_codes = 1 << settings.adc_bits
    first_code, last_code = settings.code_range or (1, number_codes - 2)
    if not 0 <= first_code <= last_code < number_codes:
        raise ValueError(f"code_range must fit within 0..{number_codes - 1}")
    codes = all_codes[first_code : last_code + 1]
    counts = all_counts[first_code : last_code + 1]
    ideal_count = float(np.mean(counts))
    dnl = counts / ideal_count - 1.0 if ideal_count else np.zeros_like(counts, dtype=float)
    raw_inl = np.concatenate(([0.0], np.cumsum(dnl[:-1], dtype=np.float64)))
    if len(raw_inl) > 1:
        endpoint = np.linspace(raw_inl[0], raw_inl[-1], len(raw_inl))
        inl = raw_inl - endpoint
    else:
        inl = raw_inl
    return AnalysisResult(
        name=request.spec.name,
        kind=AnalysisKind.ADC_CODE_DENSITY,
        source_ids=request.spec.input_ids,
        metrics=(
            Metric("sample_count", distribution.metric("sample_count")),
            Metric("ideal_count", ideal_count),
            Metric("missing_codes", int(np.count_nonzero(counts == 0))),
            Metric("minimum_dnl", float(np.min(dnl)), "LSB"),
            Metric("maximum_dnl", float(np.max(dnl)), "LSB"),
            Metric("minimum_inl", float(np.min(inl)), "LSB"),
            Metric("maximum_inl", float(np.max(inl)), "LSB"),
        ),
        tables=(
            DataTable(
                "linearity",
                (
                    DataColumn("code", codes, "LSB"),
                    DataColumn("count", counts),
                    DataColumn("dnl", dnl, "LSB"),
                    DataColumn("inl", inl, "LSB"),
                ),
            ),
        ),
        metadata={"first_code": first_code, "last_code": last_code},
    )


def _decision_path(bits: str, weights: np.ndarray, initial_estimate: float) -> np.ndarray:
    bit_values = np.asarray([int(bit) for bit in bits.strip()], dtype=np.int8)
    if len(bit_values) != len(weights):
        raise ValueError(f"Bout has {len(bit_values)} bits, expected {len(weights)}")
    path = np.empty(len(weights) + 1, dtype=np.float64)
    path[0] = initial_estimate
    decided = 0.0
    remaining = float(np.sum(weights))
    for index, (bit, weight) in enumerate(zip(bit_values, weights, strict=True), start=1):
        decided += bit * weight
        remaining -= weight
        path[index] = decided + 0.5 * remaining
    return path


def analyze_adc_decision_paths(request: AnalysisRequest) -> AnalysisResult:
    """Reconstruct running SAR estimates from captured comparator decisions."""

    settings = _adc_settings(request)
    if not settings.code_weights:
        raise ValueError("decision-path analysis requires code_weights")
    weights = np.asarray(settings.code_weights, dtype=np.float64)
    initial_estimate = (
        settings.initial_estimate
        if settings.initial_estimate is not None
        else ((1 << settings.adc_bits) - 1) / 2.0
    )
    bits = np.concatenate(
        [
            np.asarray(
                _column_from_run(_run_by_id(request, input_id), settings.bits_column),
                dtype=np.str_,
            )
            for input_id in request.spec.input_ids
        ]
    )
    codes = np.concatenate(
        [
            np.asarray(
                _column_from_run(_run_by_id(request, input_id), settings.code_column),
                dtype=np.int64,
            )
            for input_id in request.spec.input_ids
        ]
    )
    indices = np.arange(len(bits), dtype=np.int64)
    if settings.selection == "single":
        if not 0 <= settings.row_index < len(bits):
            raise IndexError("decision-path row_index is outside the acquisition")
        selected = np.asarray([settings.row_index], dtype=np.int64)
    elif settings.selection == "same_code":
        selected_code = settings.selected_code
        if selected_code is None:
            selected_code = Counter(int(code) for code in codes).most_common(1)[0][0]
        selected = np.flatnonzero(codes == selected_code)
    elif settings.selection == "all":
        selected = indices
    else:
        raise ValueError("decision-path selection must be 'single', 'same_code', or 'all'")

    paths = np.vstack([_decision_path(bits[index], weights, initial_estimate) for index in selected])
    cycle_count = paths.shape[1]
    return AnalysisResult(
        name=request.spec.name,
        kind=AnalysisKind.ADC_DECISION_PATHS,
        source_ids=request.spec.input_ids,
        metrics=(
            Metric("path_count", len(selected)),
            Metric("decision_count", len(weights)),
        ),
        tables=(
            DataTable(
                "decision_paths",
                (
                    DataColumn("conversion_index", np.repeat(selected, cycle_count)),
                    DataColumn("cycle", np.tile(np.arange(cycle_count), len(selected))),
                    DataColumn("estimate_code", paths.reshape(-1), "LSB"),
                    DataColumn("final_code", np.repeat(codes[selected], cycle_count), "LSB"),
                ),
            ),
        ),
        metadata={"selection": settings.selection},
    )


def analyze_adc_dynamic_sweep(request: AnalysisRequest) -> AnalysisResult:
    """Combine ADC dynamic results into a reusable trend table."""

    settings = _adc_settings(request)
    dynamic_results = [
        result
        for input_id in request.spec.input_ids
        for result in request.results
        if result.name == input_id
    ]
    if len(dynamic_results) != len(request.spec.input_ids) or any(
        result.kind is not AnalysisKind.ADC_DYNAMIC for result in dynamic_results
    ):
        raise ValueError("dynamic sweep inputs must all be ADC dynamic results")
    columns = [
        DataColumn(
            "input_frequency_hz",
            np.asarray([result.metric("input_frequency_hz") for result in dynamic_results]),
            "Hz",
        ),
        DataColumn(
            "sample_rate_hz",
            np.asarray([result.metric("sample_rate_hz") for result in dynamic_results]),
            "Hz",
        ),
        DataColumn(
            "spectral_enob_bits",
            np.asarray([result.metric("spectral_enob_bits") for result in dynamic_results]),
            "bit",
        ),
        DataColumn(
            "spectral_sndr_db",
            np.asarray([result.metric("spectral_sndr_db") for result in dynamic_results]),
            "dB",
        ),
        DataColumn(
            "spectral_snr_db",
            np.asarray([result.metric("spectral_snr_db") for result in dynamic_results]),
            "dB",
        ),
        DataColumn(
            "spectral_thd_db",
            np.asarray([result.metric("spectral_thd_db") for result in dynamic_results]),
            "dB",
        ),
    ]
    existing_columns = {column.name for column in columns}
    for name in (settings.sweep_axis, settings.sweep_group):
        if name is None or name in existing_columns:
            continue
        values = [_metadata_item(result.metadata, name) for result in dynamic_results]
        if any(value is None for value in values):
            raise ValueError(f"dynamic sweep metadata does not contain {name!r} for every result")
        columns.append(DataColumn(name, np.asarray(values)))
        existing_columns.add(name)
    return AnalysisResult(
        name=request.spec.name,
        kind=AnalysisKind.ADC_DYNAMIC_SWEEP,
        source_ids=request.spec.input_ids,
        metrics=(Metric("point_count", len(dynamic_results)),),
        tables=(
            DataTable(
                "dynamic_sweep",
                tuple(columns),
            ),
        ),
        metadata={
            "sweep_axis": settings.sweep_axis,
            "sweep_group": settings.sweep_group,
        },
    )


def analyze_adc(request: AnalysisRequest) -> AnalysisResult:
    """Dispatch one typed ADC analysis request."""

    handlers = {
        AnalysisKind.ADC_TRANSFER: analyze_adc_transfer,
        AnalysisKind.ADC_ENDPOINT_LINEARITY: analyze_adc_endpoint_linearity,
        AnalysisKind.ADC_DISTRIBUTION: analyze_adc_distribution,
        AnalysisKind.ADC_CODE_DENSITY: analyze_adc_code_density,
        AnalysisKind.ADC_DECISION_PATHS: analyze_adc_decision_paths,
        AnalysisKind.ADC_DYNAMIC: analyze_adc_dynamic,
        AnalysisKind.ADC_DYNAMIC_SWEEP: analyze_adc_dynamic_sweep,
    }
    try:
        handler = handlers[request.spec.kind]
    except KeyError:
        raise ValueError(f"{request.spec.kind.value!r} is not an ADC analysis") from None
    return handler(request)
