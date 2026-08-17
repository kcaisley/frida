"""Typed ADC analyses for physical, behavioral, and SPICE measurements."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from typing import Literal

import hdl21 as h
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal.windows import blackmanharris

from flow.analysis.measure import find_code_transitions, histogram_inl_dnl
from flow.analysis.types import (
    AdcDecoding,
    AnalysisAdcCalibration,
    AnalysisAdcCodeDistribution,
    AnalysisAdcDecisionPaths,
    AnalysisAdcDynamic,
    AnalysisAdcDynamicSweep,
    AnalysisAdcNoiseSweep,
    AnalysisAdcNonlinearity,
    AnalysisAdcPowerSweep,
    AnalysisAdcRamp,
    AnalysisAdcRampCurve,
    AnalysisAdcTransfer,
    MeasAdc,
)
from flow.cdac import get_cdac_weights

ADC_DYNAMIC_RESIDUAL_TAIL_LIMIT_DOUT = 24.0
ADC_DYNAMIC_GAUSSIAN_TAIL_FRACTION = 0.0027
ADC_RAMP_RESET_EXCLUSION_CONVERSIONS = 8


def decode_bout(
    bout: np.ndarray,
    calibration: AnalysisAdcCalibration,
    *,
    rounded: bool = True,
) -> np.ndarray:
    """Apply one method-independent 17-weight digital calibration."""

    decisions = np.asarray(bout)
    if decisions.ndim != 2 or decisions.shape[1] != 17:
        raise ValueError("calibrated ADC decoding requires BOUT shape (samples, 17)")
    if np.any((decisions != 0) & (decisions != 1)):
        raise ValueError("calibrated ADC decoding requires binary BOUT values")
    fractional = np.asarray(
        decisions.astype(np.float64) @ calibration.calibrated_weight,
        dtype=np.float64,
    )
    fractional = np.clip(fractional, 0.0, float(calibration.code_max))
    if not rounded:
        return fractional
    return np.rint(fractional).astype(np.int64)


def _validate_calibration(measurement: MeasAdc, calibration: AnalysisAdcCalibration) -> None:
    adc_index = -1 if measurement.param.observed_adc is None else measurement.param.observed_adc
    code_max = (1 << measurement.param.dut.adc_bits) - 1
    if calibration.adc_index != adc_index:
        raise ValueError("calibration and measurement must refer to the same ADC")
    if calibration.code_max != code_max:
        raise ValueError("calibration and measurement must use the same output range")


def _pattern_repeat_rate_hz(measurement: MeasAdc) -> float:
    """Return the true sampling rate including sequencer idle padding."""

    return float(measurement.param.symbol_rate) / len(measurement.param.seq_init_pattern)


def _active_conversion_rate_hz(measurement: MeasAdc) -> float:
    """Return the nominal conversion rate excluding idle padding."""

    patterns = (
        measurement.param.seq_init_pattern,
        measurement.param.seq_samp_pattern,
        measurement.param.seq_comp_pattern,
        measurement.param.seq_logic_pattern,
    )
    active = [index for index in range(len(patterns[0])) if any(pattern[index] == "1" for pattern in patterns)]
    if not active:
        raise ValueError("ADC timing patterns contain no active symbols")
    return float(measurement.param.symbol_rate) / (active[-1] - active[0] + 1)


def _input_frequency_hz(measurement: MeasAdc) -> float:
    """Return the programmed sine frequency from the measurement parameters."""

    source = measurement.param.vin_diff
    if not isinstance(source, h.Vsin.Params) or source.freq is None:
        raise ValueError("ADC dynamic analysis requires a sine vin_diff source with freq set")
    return float(source.freq)


def _calculate_adc_spectrum(
    measured_dout: np.ndarray,
    *,
    sample_rate_hz: float,
    fitted_frequency_hz: float,
    offset_dout: float,
    full_scale_peak_dout: float,
    maximum_harmonic_order: int,
) -> tuple[float, float, float, float, float, np.ndarray, np.ndarray]:
    """Calculate windowed SNR, SNDR, THD, SFDR, ENOB, and spectrum."""

    window = blackmanharris(measured_dout.size, sym=False)
    spectrum = np.fft.rfft((measured_dout - offset_dout) * window)
    frequency_hz = np.fft.rfftfreq(measured_dout.size, d=1.0 / sample_rate_hz)
    amplitude_dout = 2.0 * np.abs(spectrum) / float(np.sum(window))
    amplitude_dout[0] *= 0.5
    if measured_dout.size % 2 == 0:
        amplitude_dout[-1] *= 0.5
    amplitude_dbfs = 20.0 * np.log10(
        np.maximum(
            amplitude_dout / full_scale_peak_dout,
            np.finfo(np.float64).tiny,
        )
    )

    spectral_power = np.abs(spectrum) ** 2
    if measured_dout.size % 2 == 0:
        spectral_power[1:-1] *= 2.0
    else:
        spectral_power[1:] *= 2.0
    spectral_power[0] = 0.0
    bin_width_hz = sample_rate_hz / measured_dout.size

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
        wrapped_hz = (harmonic_order * fitted_frequency_hz) % sample_rate_hz
        aliased_hz = min(wrapped_hz, sample_rate_hz - wrapped_hz)
        harmonic_bins.update(tone_bins(aliased_hz) - fundamental_bins)

    noise_bins = set(range(1, len(spectral_power))) - fundamental_bins - harmonic_bins
    fundamental_power = float(np.sum(spectral_power[list(fundamental_bins)]))
    harmonic_power = float(np.sum(spectral_power[list(harmonic_bins)]))
    noise_power = float(np.sum(spectral_power[list(noise_bins)]))
    noise_and_distortion = harmonic_power + noise_power
    if fundamental_power <= 0:
        sndr_db = -math.inf
        snr_db = -math.inf
        thd_db = math.inf if harmonic_power > 0 else -math.inf
    else:
        sndr_db = 10.0 * math.log10(fundamental_power / noise_and_distortion) if noise_and_distortion > 0 else math.inf
        snr_db = 10.0 * math.log10(fundamental_power / noise_power) if noise_power > 0 else math.inf
        thd_db = 10.0 * math.log10(harmonic_power / fundamental_power) if harmonic_power > 0 else -math.inf

    spur_candidates = np.asarray(
        sorted(set(range(1, len(spectral_power))) - fundamental_bins),
        dtype=np.int64,
    )
    if fundamental_power > 0 and spur_candidates.size:
        spur_center = int(spur_candidates[np.argmax(spectral_power[spur_candidates])])
        spur_bins = tone_bins(frequency_hz[spur_center]) - fundamental_bins
        spur_power = float(np.sum(spectral_power[list(spur_bins)]))
        sfdr_db = 10.0 * math.log10(fundamental_power / spur_power) if spur_power > 0 else math.inf
    else:
        sfdr_db = math.inf
    return (
        sndr_db,
        snr_db,
        thd_db,
        sfdr_db,
        (sndr_db - 1.76) / 6.02,
        frequency_hz,
        amplitude_dbfs,
    )


def analyze_adc_dynamic(
    measurement: MeasAdc,
    *,
    frequency_search_fraction: float = 0.02,
    maximum_harmonic_order: int = 5,
) -> AnalysisAdcDynamic:
    """Fit one sine acquisition and calculate time- and frequency-domain metrics."""

    measured_dout = np.asarray(measurement.daq.dout, dtype=np.float64)
    sample_rate_hz = _pattern_repeat_rate_hz(measurement)
    input_frequency_hz = _input_frequency_hz(measurement)
    adc_bits = measurement.param.dut.adc_bits
    if measured_dout.ndim != 1 or measured_dout.size < 8:
        raise ValueError("ADC sine fit requires at least eight one-dimensional samples")
    if not np.all(np.isfinite(measured_dout)):
        raise ValueError("ADC sine-fit samples must all be finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if not math.isfinite(input_frequency_hz) or input_frequency_hz <= 0 or input_frequency_hz >= sample_rate_hz / 2:
        raise ValueError("input_frequency_hz must be finite and between zero and Nyquist")
    if not math.isfinite(frequency_search_fraction) or not 0 <= frequency_search_fraction < 1:
        raise ValueError("frequency_search_fraction must be finite and in [0, 1)")
    if maximum_harmonic_order < 2:
        raise ValueError("maximum_harmonic_order must be at least two")
    time_s = np.arange(measured_dout.size, dtype=np.float64) / sample_rate_hz
    ones = np.ones(measured_dout.size, dtype=np.float64)

    def fit_at_frequency(frequency_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        phase = 2.0 * np.pi * frequency_hz * time_s
        design = np.column_stack((np.sin(phase), np.cos(phase), ones))
        coefficients = np.linalg.lstsq(design, measured_dout, rcond=None)[0]
        fitted = design @ coefficients
        residual = measured_dout - fitted
        return coefficients, fitted, residual, float(np.mean(residual * residual))

    if frequency_search_fraction:
        maximum_offset_hz = min(
            input_frequency_hz * frequency_search_fraction,
            0.45 * sample_rate_hz / measured_dout.size,
        )
        lower_hz = max(np.nextafter(0.0, 1.0), input_frequency_hz - maximum_offset_hz)
        upper_hz = min(
            np.nextafter(sample_rate_hz / 2.0, 0.0),
            input_frequency_hz + maximum_offset_hz,
        )
        frequency_fit = minimize_scalar(
            lambda frequency_hz: fit_at_frequency(float(frequency_hz))[3],
            bounds=(lower_hz, upper_hz),
            method="bounded",
            options={"xatol": max(1e-9, input_frequency_hz * 1e-10)},
        )
        if not frequency_fit.success:
            raise RuntimeError(f"ADC sine frequency fit failed: {frequency_fit.message}")
        fitted_frequency_hz = float(frequency_fit.x)
    else:
        fitted_frequency_hz = input_frequency_hz

    coefficients, fitted_dout, residual_dout, residual_power = fit_at_frequency(fitted_frequency_hz)
    absolute_residual_dout = np.abs(residual_dout)
    sine_coefficient, cosine_coefficient, offset_dout = (float(value) for value in coefficients)
    amplitude_dout = math.hypot(sine_coefficient, cosine_coefficient)
    phase_rad = math.atan2(cosine_coefficient, sine_coefficient)
    signal_rms_dout = amplitude_dout / math.sqrt(2.0)
    residual_rms_dout = math.sqrt(residual_power)
    if signal_rms_dout == 0:
        sinad_db = -math.inf
    elif residual_rms_dout == 0:
        sinad_db = math.inf
    else:
        sinad_db = 20.0 * math.log10(signal_rms_dout / residual_rms_dout)
    enob_bits = (sinad_db - 1.76) / 6.02
    full_scale_peak_dout = ((1 << adc_bits) - 1) / 2.0
    amplitude_dbfs = 20.0 * math.log10(amplitude_dout / full_scale_peak_dout) if amplitude_dout > 0 else -math.inf
    (
        spectral_sndr_db,
        spectral_snr_db,
        spectral_thd_db,
        spectral_sfdr_db,
        spectral_enob_bits,
        spectrum_frequency_hz,
        spectrum_dbfs,
    ) = _calculate_adc_spectrum(
        measured_dout,
        sample_rate_hz=sample_rate_hz,
        fitted_frequency_hz=fitted_frequency_hz,
        offset_dout=offset_dout,
        full_scale_peak_dout=full_scale_peak_dout,
        maximum_harmonic_order=maximum_harmonic_order,
    )
    source = measurement.param.vin_diff
    if not isinstance(source, h.Vsin.Params) or source.vamp is None:
        raise ValueError("ADC dynamic analysis requires a sine vin_diff source with vamp set")
    input_amplitude_v = abs(float(source.vamp))
    if input_amplitude_v > 0 and amplitude_dout > 0:
        gain_dout_per_v = amplitude_dout / input_amplitude_v
        input_referred_residual_rms_v = residual_rms_dout / gain_dout_per_v
        if math.isinf(spectral_snr_db) and spectral_snr_db > 0:
            input_referred_noise_rms_v = 0.0
        elif math.isinf(spectral_snr_db) and spectral_snr_db < 0:
            input_referred_noise_rms_v = math.inf
        else:
            input_referred_noise_rms_v = input_amplitude_v / math.sqrt(2.0) / 10.0 ** (spectral_snr_db / 20.0)
    else:
        input_referred_noise_rms_v = math.nan
        input_referred_residual_rms_v = math.nan
    return AnalysisAdcDynamic(
        sample_rate_hz=sample_rate_hz,
        input_frequency_hz=input_frequency_hz,
        fitted_frequency_hz=fitted_frequency_hz,
        sample_count=len(measured_dout),
        adc_bits=adc_bits,
        offset_dout=offset_dout,
        amplitude_dout=amplitude_dout,
        phase_rad=phase_rad,
        amplitude_dbfs=amplitude_dbfs,
        signal_rms_dout=signal_rms_dout,
        residual_rms_dout=residual_rms_dout,
        input_referred_noise_rms_v=input_referred_noise_rms_v,
        input_referred_residual_rms_v=input_referred_residual_rms_v,
        sinad_db=sinad_db,
        enob_bits=enob_bits,
        spectral_sndr_db=spectral_sndr_db,
        spectral_snr_db=spectral_snr_db,
        spectral_thd_db=spectral_thd_db,
        spectral_sfdr_db=spectral_sfdr_db,
        spectral_enob_bits=spectral_enob_bits,
        residual_tail_limit_dout=ADC_DYNAMIC_RESIDUAL_TAIL_LIMIT_DOUT,
        expected_residual_tail_count=len(residual_dout) * ADC_DYNAMIC_GAUSSIAN_TAIL_FRACTION,
        negative_residual_tail_count=int(np.count_nonzero(residual_dout < -ADC_DYNAMIC_RESIDUAL_TAIL_LIMIT_DOUT)),
        positive_residual_tail_count=int(np.count_nonzero(residual_dout > ADC_DYNAMIC_RESIDUAL_TAIL_LIMIT_DOUT)),
        maximum_abs_residual_dout=float(np.max(absolute_residual_dout)),
        time_s=time_s,
        measured_dout=measured_dout,
        fitted_dout=fitted_dout,
        residual_dout=residual_dout,
        spectrum_frequency_hz=spectrum_frequency_hz,
        spectrum_dbfs=spectrum_dbfs,
    )


def analyze_adc_transfer(
    measurements: Sequence[MeasAdc],
    *,
    calibration: AnalysisAdcCalibration | None = None,
) -> AnalysisAdcTransfer:
    """Calculate transfer statistics with optional calibrated BOUT decoding."""

    if not measurements:
        raise ValueError("ADC transfer analysis requires at least one measurement")
    if calibration is not None:
        for measurement in measurements:
            _validate_calibration(measurement, calibration)
    inputs = np.concatenate([measurement.daq.vin_diff_v for measurement in measurements])
    dout = np.concatenate(
        [
            measurement.daq.dout if calibration is None else decode_bout(measurement.daq.bout, calibration)
            for measurement in measurements
        ]
    ).astype(np.float64)
    if not len(dout):
        raise ValueError("ADC transfer analysis requires at least one conversion")
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    return AnalysisAdcTransfer(
        vin_diff_v=unique_inputs,
        mean_dout=np.asarray([np.mean(dout[inverse == index]) for index in range(len(unique_inputs))]),
        std_dout=np.asarray([np.std(dout[inverse == index]) for index in range(len(unique_inputs))]),
        sample_count=np.bincount(inverse, minlength=len(unique_inputs)).astype(np.int64),
    )


def _endpoint_nonlinearity(measurement: MeasAdc, decoded_dout: np.ndarray) -> AnalysisAdcNonlinearity:
    inputs = measurement.daq.vin_diff_v
    decoded_dout = np.asarray(decoded_dout, dtype=np.float64)
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    if len(unique_inputs) < 3:
        raise ValueError("endpoint nonlinearity requires at least three input points")
    mean_dout = np.asarray([np.mean(decoded_dout[inverse == index]) for index in range(len(unique_inputs))])
    transition_code, transition_input = find_code_transitions(unique_inputs, mean_dout)
    if len(transition_input) < 2:
        raise ValueError("endpoint nonlinearity spans fewer than two code transitions")
    endpoint_lsb_v = float((transition_input[-1] - transition_input[0]) / (len(transition_input) - 1))
    ideal = transition_input[0] + np.arange(len(transition_input)) * endpoint_lsb_v
    inl = (transition_input - ideal) / endpoint_lsb_v
    dnl = np.diff(transition_input) / endpoint_lsb_v - 1.0
    observed = set(np.rint(decoded_dout).astype(np.int64))
    active = range(int(np.min(transition_code)), int(np.max(transition_code)) + 2)
    return AnalysisAdcNonlinearity(
        method="endpoint",
        code=transition_code[1:],
        dnl=dnl,
        inl=inl[1:],
        count=None,
        transition_vin_diff_v=transition_input[1:],
        ideal_count=None,
        endpoint_lsb_v=endpoint_lsb_v,
        maximum_abs_dnl=float(np.max(np.abs(dnl))),
        maximum_abs_inl=float(np.max(np.abs(inl))),
        missing_codes=sum(code not in observed for code in active),
    )


def _code_density_nonlinearity(
    measurement: MeasAdc,
    decoded_dout: np.ndarray,
    *,
    code_range: tuple[int, int] | None,
) -> AnalysisAdcNonlinearity:
    number_codes = 1 << measurement.param.dut.adc_bits
    valid = decoded_dout[(decoded_dout >= 0) & (decoded_dout < number_codes)]
    if not len(valid):
        raise ValueError(f"ADC measurement contains no codes in 0..{number_codes - 1}")
    counts = np.bincount(valid, minlength=number_codes)
    first_code, last_code = code_range or (1, number_codes - 2)
    result = histogram_inl_dnl(counts, first_code=first_code, last_code=last_code)
    return AnalysisAdcNonlinearity(
        method="code_density",
        code=result["codes"],
        dnl=result["dnl"],
        inl=result["inl"],
        count=result["counts"],
        transition_vin_diff_v=None,
        ideal_count=result["ideal_count"],
        endpoint_lsb_v=None,
        maximum_abs_dnl=float(np.max(np.abs(result["dnl"]))),
        maximum_abs_inl=float(np.max(np.abs(result["inl"]))),
        missing_codes=result["missing_codes"],
    )


def analyze_adc_nonlinearity(
    measurement: MeasAdc,
    *,
    method: Literal["endpoint", "code_density"] = "endpoint",
    code_range: tuple[int, int] | None = None,
    calibration: AnalysisAdcCalibration | None = None,
) -> AnalysisAdcNonlinearity:
    """Calculate INL and DNL with optional calibrated BOUT decoding."""

    if calibration is not None:
        _validate_calibration(measurement, calibration)
    # Nominal DOUT is stored in the measurement. Calibrated DOUT is derived
    # transiently from the same stored BOUT decisions and the supplied weights.
    decoded_dout = measurement.daq.dout if calibration is None else decode_bout(measurement.daq.bout, calibration)
    if method == "endpoint":
        return _endpoint_nonlinearity(measurement, decoded_dout)
    if method == "code_density":
        return _code_density_nonlinearity(measurement, decoded_dout, code_range=code_range)
    raise ValueError("ADC nonlinearity method must be 'endpoint' or 'code_density'")


def analyze_adc_ramp(
    measurement: MeasAdc,
    *,
    calibrations: Sequence[AnalysisAdcCalibration] = (),
    code_range: tuple[int, int] | None = None,
) -> AnalysisAdcRamp:
    """Recover nominal and optionally calibrated curves from one repeated ramp.

    Each large negative output jump identifies a sawtooth reset.  A line fit to
    those repeated resets recovers the actual ramp period and acquisition phase
    without assuming the AWG and FastRX started together.  That phase maps each
    conversion back to the requested -1 V to +1 V input, while the uniform code
    histogram supplies DNL and endpoint-corrected INL. Clipped endpoint codes
    are excluded from linearity by default. Every supplied calibration is
    applied to the same stored BOUT words and analyzed on the same retained
    conversions, making all three methods directly comparable.
    """

    if not isinstance(measurement.param.vin_diff, h.Vpwl.Params):
        raise TypeError("ADC ramp analysis requires a PWL differential-input source")
    intended_input = np.asarray(measurement.daq.vin_diff_v, dtype=np.float64)
    if intended_input.ndim != 1 or len(intended_input) < 2:
        raise ValueError("ADC ramp analysis requires at least two intended input samples")
    vin_diff_min_v = float(np.min(intended_input))
    vin_diff_max_v = float(np.max(intended_input))
    if not vin_diff_max_v > vin_diff_min_v:
        raise ValueError("ADC ramp input must span a nonzero differential range")

    nominal_weights_int = np.asarray(
        [2 * value for value in get_cdac_weights(measurement.param.dut.cdac)] + [1],
        dtype=np.int64,
    )
    nominal_weights = nominal_weights_int.astype(np.float64)
    number_codes = 1 << measurement.param.dut.adc_bits
    code_max = number_codes - 1
    if measurement.daq.bout.shape[1] != len(nominal_weights):
        raise ValueError("ADC ramp decisions do not match the nominal CDAC weights")
    decisions_int = np.asarray(measurement.daq.bout, dtype=np.int64)
    nominal_raw = decisions_int @ nominal_weights_int
    if not np.array_equal(nominal_raw, measurement.daq.dout_raw):
        raise ValueError("stored ramp DOUT_RAW does not match BOUT decoded with the configured design weights")
    expected_nominal_dout = np.rint(nominal_raw * code_max / np.sum(nominal_weights_int)).astype(np.int64)
    if not np.array_equal(expected_nominal_dout, measurement.daq.dout):
        raise ValueError("stored ramp DOUT does not match normalized DOUT_RAW")
    nominal_decoded = np.asarray(measurement.daq.dout, dtype=np.int64)
    if np.any((nominal_decoded < 0) | (nominal_decoded >= number_codes)):
        raise ValueError(f"ADC ramp contains output codes outside 0..{number_codes - 1}")

    decodings: list[tuple[AdcDecoding, str, np.ndarray, np.ndarray]] = [
        ("uncalibrated_dout", "Uncalibrated DOUT", nominal_weights, nominal_decoded)
    ]
    adc_index = -1 if measurement.param.observed_adc is None else measurement.param.observed_adc
    observed_methods = set()
    for calibration in calibrations:
        if calibration.method in observed_methods:
            raise ValueError(f"duplicate ADC calibration method {calibration.method!r}")
        observed_methods.add(calibration.method)
        _validate_calibration(measurement, calibration)
        decodings.append(
            (
                calibration.method,
                calibration.label,
                calibration.calibrated_weight,
                decode_bout(measurement.daq.bout, calibration),
            )
        )

    reset_candidates = np.flatnonzero(np.diff(nominal_decoded) < -0.25 * code_max).astype(np.int64) + 1
    if len(reset_candidates):
        cluster_starts = np.concatenate(
            (
                np.asarray([0], dtype=np.int64),
                np.flatnonzero(np.diff(reset_candidates) > 64).astype(np.int64) + 1,
            )
        )
        reset_conversion_index = reset_candidates[cluster_starts]
    else:
        reset_conversion_index = reset_candidates
    if len(reset_conversion_index) < 2:
        raise ValueError("ADC ramp analysis requires at least two visible sawtooth resets")
    reset_number = np.arange(len(reset_conversion_index), dtype=np.float64)
    reset_design = np.column_stack((reset_number, np.ones(len(reset_number))))
    period_samples, first_reset_sample = np.linalg.lstsq(
        reset_design,
        reset_conversion_index.astype(np.float64),
        rcond=None,
    )[0]
    if not math.isfinite(period_samples) or period_samples <= 1.0:
        raise ValueError("inferred ADC ramp period is invalid")
    reset_residual_samples = reset_conversion_index - (period_samples * reset_number + first_reset_sample)
    if float(np.max(np.abs(reset_residual_samples))) > 2.0:
        raise ValueError("ADC ramp resets are not periodic within two conversions")
    sample_rate_hz = _pattern_repeat_rate_hz(measurement)
    ramp_frequency_hz = sample_rate_hz / period_samples
    ramp_phase_cycles = float(np.mod(-first_reset_sample / period_samples, 1.0))
    conversion_phase = np.mod(
        (np.arange(len(nominal_decoded), dtype=np.float64) - first_reset_sample) / period_samples,
        1.0,
    )
    retained = np.ones(len(nominal_decoded), dtype=bool)
    for reset_index in reset_conversion_index:
        retained[reset_index : reset_index + ADC_RAMP_RESET_EXCLUSION_CONVERSIONS] = False
    retained_sample_count = int(np.count_nonzero(retained))

    first_code, last_code = code_range or (1, number_codes - 2)
    transfer_bin = np.minimum((conversion_phase * number_codes).astype(np.int64), number_codes - 1)
    transfer_sample_count = np.bincount(transfer_bin[retained], minlength=number_codes).astype(np.int64)
    populated = transfer_sample_count > 0
    transfer_vin_diff_v = vin_diff_min_v + (
        (np.arange(number_codes, dtype=np.float64) + 0.5) / number_codes * (vin_diff_max_v - vin_diff_min_v)
    )
    curves = []
    for decoding, label, weights, decoded in decodings:
        counts = np.bincount(decoded[retained], minlength=number_codes).astype(np.int64)
        density = histogram_inl_dnl(counts, first_code=first_code, last_code=last_code)
        transfer_sum = np.bincount(transfer_bin[retained], weights=decoded[retained], minlength=number_codes)
        transfer_mean_dout = transfer_sum[populated] / transfer_sample_count[populated]
        transfer_difference = np.diff(transfer_mean_dout)
        maximum_transfer_reversal_dout = (
            max(0.0, float(-np.min(transfer_difference))) if len(transfer_difference) else 0.0
        )
        curves.append(
            AnalysisAdcRampCurve(
                decoding=decoding,
                label=label,
                weights=weights,
                transfer_vin_diff_v=transfer_vin_diff_v[populated],
                transfer_mean_dout=transfer_mean_dout,
                transfer_sample_count=transfer_sample_count[populated],
                code=np.arange(number_codes, dtype=np.int64),
                count=counts,
                linearity_code=density["codes"],
                dnl=density["dnl"],
                inl=density["inl"],
                ideal_count=density["ideal_count"],
                maximum_abs_dnl=float(np.max(np.abs(density["dnl"]))),
                maximum_abs_inl=float(np.max(np.abs(density["inl"]))),
                missing_codes=density["missing_codes"],
                maximum_transfer_reversal_dout=maximum_transfer_reversal_dout,
            )
        )
    return AnalysisAdcRamp(
        adc_index=adc_index,
        sample_count=len(nominal_decoded),
        retained_sample_count=retained_sample_count,
        reset_excluded_sample_count=len(nominal_decoded) - retained_sample_count,
        sample_rate_hz=sample_rate_hz,
        ramp_frequency_hz=ramp_frequency_hz,
        ramp_phase_cycles=ramp_phase_cycles,
        reset_conversion_index=reset_conversion_index,
        vin_diff_min_v=vin_diff_min_v,
        vin_diff_max_v=vin_diff_max_v,
        curves=tuple(curves),
    )


def analyze_adc_code_distribution(
    measurements: Sequence[MeasAdc],
    *,
    calibration: AnalysisAdcCalibration | None = None,
) -> AnalysisAdcCodeDistribution:
    """Calculate code histograms with optional calibrated BOUT decoding."""

    if not measurements:
        raise ValueError("ADC code-distribution analysis requires at least one measurement")
    adc_bits = measurements[0].param.dut.adc_bits
    if any(measurement.param.dut.adc_bits != adc_bits for measurement in measurements):
        raise ValueError("ADC code-distribution measurements must use one output resolution")
    if calibration is not None:
        for measurement in measurements:
            _validate_calibration(measurement, calibration)
    inputs = np.concatenate([measurement.daq.vin_diff_v for measurement in measurements])
    dout = np.concatenate(
        [
            measurement.daq.dout if calibration is None else decode_bout(measurement.daq.bout, calibration)
            for measurement in measurements
        ]
    )
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    number_codes = 1 << adc_bits
    count = np.zeros((len(unique_inputs), number_codes), dtype=np.int64)
    mean = np.empty(len(unique_inputs))
    std = np.empty(len(unique_inputs))
    minimum = np.empty(len(unique_inputs), dtype=np.int64)
    maximum = np.empty(len(unique_inputs), dtype=np.int64)
    sample_count = np.empty(len(unique_inputs), dtype=np.int64)
    for index in range(len(unique_inputs)):
        values = dout[inverse == index]
        valid = values[(values >= 0) & (values < number_codes)]
        if not len(valid):
            raise ValueError(f"input point {unique_inputs[index]:g} V has no valid ADC codes")
        count[index] = np.bincount(valid, minlength=number_codes)
        sample_count[index] = len(valid)
        mean[index] = np.mean(valid)
        std[index] = np.std(valid)
        minimum[index] = np.min(valid)
        maximum[index] = np.max(valid)
    return AnalysisAdcCodeDistribution(
        vin_diff_v=unique_inputs,
        sample_count=sample_count,
        mean_dout=mean,
        std_dout=std,
        minimum_dout=minimum,
        maximum_dout=maximum,
        code=np.arange(number_codes, dtype=np.int64),
        count=count,
    )


def analyze_adc_noise_sweep(
    measurements: Sequence[MeasAdc],
) -> AnalysisAdcNoiseSweep:
    """Combine fixed-input code variation across conversion timing settings."""

    if not measurements:
        raise ValueError("ADC noise sweep requires at least one measurement")
    adc_bits = measurements[0].param.dut.adc_bits
    if any(measurement.param.dut.adc_bits != adc_bits for measurement in measurements):
        raise ValueError("ADC noise sweep measurements must use one output resolution")
    number_codes = 1 << adc_bits
    input_lsb_values_v = np.asarray(
        [
            float(measurement.param.vdd_dac.dc) / ((1 << measurement.param.dut.adc_bits) - 1)
            for measurement in measurements
        ],
        dtype=np.float64,
    )
    if not np.allclose(
        input_lsb_values_v,
        input_lsb_values_v[0],
        rtol=1e-12,
        atol=0.0,
    ):
        raise ValueError(
            "ADC noise sweep requires one nominal input LSB scale; "
            "split measurements with different VDD_DAC or ADC resolution"
        )
    sample_rate_hz = []
    logic_phase = []
    comparator_percent = []
    mean_dout = []
    std_dout = []
    pretrigger_vin_diff_mean_v = []
    pretrigger_vin_diff_noise_rms_v = []
    minimum_dout = []
    maximum_dout = []
    bit_mismatches = []
    counts = []
    for measurement in measurements:
        phase = float(measurement.param.seq_logic_phase_delay_symbols) - float(
            measurement.param.seq_comp_phase_delay_symbols
        )
        sample_rate_hz.append(_active_conversion_rate_hz(measurement))
        logic_phase.append(phase)
        comparator_percent.append(50.0 + 12.5 * phase)
        mean_dout.append(float(np.mean(measurement.daq.dout)))
        std_dout.append(float(np.std(measurement.daq.dout)))
        pretrigger = measurement.wave.time_s < 0.0
        if np.any(pretrigger):
            quiet_input = measurement.wave.vin_diff_v[:, pretrigger]
            pretrigger_vin_diff_mean_v.append(float(np.mean(quiet_input)))
            pretrigger_vin_diff_noise_rms_v.append(
                float(np.sqrt(np.mean((quiet_input - np.mean(quiet_input, axis=1, keepdims=True)) ** 2)))
            )
        else:
            pretrigger_vin_diff_mean_v.append(float("nan"))
            pretrigger_vin_diff_noise_rms_v.append(float("nan"))
        minimum_dout.append(int(np.min(measurement.daq.dout)))
        maximum_dout.append(int(np.max(measurement.daq.dout)))
        bit_mismatches.append(int(measurement.info.readbacks.get("scope_fastrx_bit_mismatches", 0)))
        valid_dout = measurement.daq.dout[(measurement.daq.dout >= 0) & (measurement.daq.dout < number_codes)]
        if len(valid_dout) != len(measurement.daq.dout):
            raise ValueError("ADC noise sweep contains output codes outside its resolution")
        counts.append(np.bincount(valid_dout, minlength=number_codes))
    std_dout_array = np.asarray(std_dout)
    return AnalysisAdcNoiseSweep(
        sample_rate_hz=np.asarray(sample_rate_hz),
        logic_phase_delay_symbols=np.asarray(logic_phase),
        comparator_time_percent=np.asarray(comparator_percent),
        input_lsb_v=float(input_lsb_values_v[0]),
        input_referred_noise_rms_v=std_dout_array * input_lsb_values_v,
        pretrigger_vin_diff_mean_v=np.asarray(pretrigger_vin_diff_mean_v),
        pretrigger_vin_diff_noise_rms_v=np.asarray(pretrigger_vin_diff_noise_rms_v),
        mean_dout=np.asarray(mean_dout),
        std_dout=std_dout_array,
        minimum_dout=np.asarray(minimum_dout, dtype=np.int64),
        maximum_dout=np.asarray(maximum_dout, dtype=np.int64),
        bit_mismatches=np.asarray(bit_mismatches, dtype=np.int64),
        code=np.arange(number_codes, dtype=np.int64),
        count=np.asarray(counts, dtype=np.int64),
    )


def combine_adc_noise_comparison(
    dc_noise_sweeps: Sequence[AnalysisAdcNoiseSweep],
    sine_dynamic: AnalysisAdcDynamicSweep,
    simulated_noise_sweeps: Sequence[AnalysisAdcNoiseSweep] = (),
) -> AnalysisAdcNoiseSweep:
    """Combine stimulus, measured, dynamic, and simulated noise-rate series."""

    if not dc_noise_sweeps:
        raise ValueError("ADC noise comparison requires at least one DC-noise sweep")
    input_lsb_v = dc_noise_sweeps[0].input_lsb_v
    if any(
        not np.isclose(sweep.input_lsb_v, input_lsb_v, rtol=1e-12, atol=0.0)
        for sweep in (*dc_noise_sweeps, *simulated_noise_sweeps)
    ):
        raise ValueError("physical/SPICE comparison requires one nominal input LSB scale")

    stimulus = dc_noise_sweeps[0]
    stimulus_order = np.argsort(stimulus.sample_rate_hz)
    noise_parts = [
        stimulus.pretrigger_vin_diff_noise_rms_v[stimulus_order],
        *(sweep.input_referred_noise_rms_v for sweep in dc_noise_sweeps),
        sine_dynamic.input_referred_noise_rms_v,
        *(sweep.input_referred_noise_rms_v for sweep in simulated_noise_sweeps),
    ]
    rate_parts = [
        stimulus.sample_rate_hz[stimulus_order],
        *(sweep.sample_rate_hz for sweep in dc_noise_sweeps),
        sine_dynamic.active_conversion_rate_hz,
        *(sweep.sample_rate_hz for sweep in simulated_noise_sweeps),
    ]
    logic_parts = [
        stimulus.logic_phase_delay_symbols[stimulus_order],
        *(sweep.logic_phase_delay_symbols for sweep in dc_noise_sweeps),
        sine_dynamic.logic_phase_delay_symbols,
        *(sweep.logic_phase_delay_symbols for sweep in simulated_noise_sweeps),
    ]
    comparator_parts = [
        stimulus.comparator_time_percent[stimulus_order],
        *(sweep.comparator_time_percent for sweep in dc_noise_sweeps),
        50.0 + 12.5 * sine_dynamic.logic_phase_delay_symbols,
        *(sweep.comparator_time_percent for sweep in simulated_noise_sweeps),
    ]
    pretrigger_mean_parts = [
        stimulus.pretrigger_vin_diff_mean_v[stimulus_order],
        *(sweep.pretrigger_vin_diff_mean_v for sweep in dc_noise_sweeps),
        np.full(len(sine_dynamic.active_conversion_rate_hz), np.nan),
        *(sweep.pretrigger_vin_diff_mean_v for sweep in simulated_noise_sweeps),
    ]
    pretrigger_noise_parts = [
        stimulus.pretrigger_vin_diff_noise_rms_v[stimulus_order],
        *(sweep.pretrigger_vin_diff_noise_rms_v for sweep in dc_noise_sweeps),
        np.full(len(sine_dynamic.active_conversion_rate_hz), np.nan),
        *(sweep.pretrigger_vin_diff_noise_rms_v for sweep in simulated_noise_sweeps),
    ]
    compared_noise_v = np.concatenate(noise_parts)
    return AnalysisAdcNoiseSweep(
        sample_rate_hz=np.concatenate(rate_parts),
        logic_phase_delay_symbols=np.concatenate(logic_parts),
        comparator_time_percent=np.concatenate(comparator_parts),
        input_lsb_v=input_lsb_v,
        input_referred_noise_rms_v=compared_noise_v,
        pretrigger_vin_diff_mean_v=np.concatenate(pretrigger_mean_parts),
        pretrigger_vin_diff_noise_rms_v=np.concatenate(pretrigger_noise_parts),
        mean_dout=np.zeros(len(compared_noise_v)),
        std_dout=compared_noise_v / input_lsb_v,
        minimum_dout=np.zeros(len(compared_noise_v), dtype=np.int64),
        maximum_dout=np.zeros(len(compared_noise_v), dtype=np.int64),
        bit_mismatches=np.zeros(len(compared_noise_v), dtype=np.int64),
    )


def analyze_adc_decision_paths(
    measurement: MeasAdc,
    *,
    selection: Literal["single", "same_dout", "all"] = "single",
    row_index: int = 0,
    selected_dout: int | None = None,
) -> AnalysisAdcDecisionPaths:
    """Reconstruct running SAR estimates from captured comparator decisions."""

    cap_weights = get_cdac_weights(measurement.param.dut.cdac)
    weights = np.asarray([2 * weight for weight in cap_weights] + [1], dtype=np.float64)
    if measurement.daq.bout.shape[1] != len(weights):
        raise ValueError(
            f"ADC measurement has {measurement.daq.bout.shape[1]} decisions, "
            f"but its CDAC defines {len(weights)} weights"
        )
    indices = np.arange(len(measurement.daq.dout), dtype=np.int64)
    if selection == "single":
        if not 0 <= row_index < len(indices):
            raise IndexError("decision-path row_index is outside the acquisition")
        selected = np.asarray([row_index], dtype=np.int64)
    elif selection == "same_dout":
        if selected_dout is None:
            selected_dout = Counter(int(value) for value in measurement.daq.dout).most_common(1)[0][0]
        selected = np.flatnonzero(measurement.daq.dout == selected_dout)
    elif selection == "all":
        selected = indices
    else:
        raise ValueError("decision-path selection must be 'single', 'same_dout', or 'all'")

    normalized_code_max = (1 << measurement.param.dut.adc_bits) - 1
    raw_code_max = float(np.sum(weights))
    paths = np.empty((len(selected), len(weights) + 1), dtype=np.float64)
    paths[:, 0] = normalized_code_max / 2.0
    for row, conversion in enumerate(selected):
        decided = 0.0
        remaining = float(np.sum(weights))
        for cycle, (bit, weight) in enumerate(
            zip(measurement.daq.bout[conversion], weights, strict=True),
            start=1,
        ):
            decided += bit * weight
            remaining -= weight
            paths[row, cycle] = (decided + 0.5 * remaining) * normalized_code_max / raw_code_max
    return AnalysisAdcDecisionPaths(
        selection=selection,
        conversion_index=measurement.daq.conversion_index[selected],
        final_dout=measurement.daq.dout[selected],
        bout=measurement.daq.bout[selected],
        weights=weights,
        estimate_dout=paths,
    )


def analyze_adc_dynamic_sweep(
    measurements: Sequence[MeasAdc],
    *,
    frequency_search_fraction: float = 0.02,
    maximum_harmonic_order: int = 5,
) -> AnalysisAdcDynamicSweep:
    """Analyze and combine sine acquisitions into dynamic trend arrays."""

    results = [
        analyze_adc_dynamic(
            measurement,
            frequency_search_fraction=frequency_search_fraction,
            maximum_harmonic_order=maximum_harmonic_order,
        )
        for measurement in measurements
    ]
    return AnalysisAdcDynamicSweep(
        input_frequency_hz=np.asarray([result.input_frequency_hz for result in results]),
        sample_rate_hz=np.asarray([result.sample_rate_hz for result in results]),
        active_conversion_rate_hz=np.asarray([_active_conversion_rate_hz(measurement) for measurement in measurements]),
        observed_adc=np.asarray(
            [
                measurement.param.observed_adc if measurement.param.observed_adc is not None else -1
                for measurement in measurements
            ],
            dtype=np.int64,
        ),
        logic_phase_delay_symbols=np.asarray(
            [
                float(measurement.param.seq_logic_phase_delay_symbols)
                - float(measurement.param.seq_comp_phase_delay_symbols)
                for measurement in measurements
            ]
        ),
        input_referred_noise_rms_v=np.asarray([result.input_referred_noise_rms_v for result in results]),
        input_referred_residual_rms_v=np.asarray([result.input_referred_residual_rms_v for result in results]),
        spectral_enob_bits=np.asarray([result.spectral_enob_bits for result in results]),
        spectral_sndr_db=np.asarray([result.spectral_sndr_db for result in results]),
        spectral_snr_db=np.asarray([result.spectral_snr_db for result in results]),
        spectral_thd_db=np.asarray([result.spectral_thd_db for result in results]),
        spectral_sfdr_db=np.asarray([result.spectral_sfdr_db for result in results]),
        residual_tail_limit_dout=ADC_DYNAMIC_RESIDUAL_TAIL_LIMIT_DOUT,
        expected_residual_tail_count=np.asarray([result.expected_residual_tail_count for result in results]),
        negative_residual_tail_count=np.asarray(
            [result.negative_residual_tail_count for result in results],
            dtype=np.int64,
        ),
        positive_residual_tail_count=np.asarray(
            [result.positive_residual_tail_count for result in results],
            dtype=np.int64,
        ),
        maximum_abs_residual_dout=np.asarray([result.maximum_abs_residual_dout for result in results]),
    )


def analyze_adc_power_sweep(measurements: Sequence[MeasAdc]) -> AnalysisAdcPowerSweep:
    """Separate measured active power into static-baseline and incremental parts.

    New captures provide a configured-idle ``static_average_power_w`` for each
    rail. Older captures fall back to their supply-on voltage/current readback,
    which predates the active sequencer interval but is sufficient to analyze
    the existing physical campaign.
    """

    if not measurements:
        raise ValueError("ADC power sweep requires at least one measurement")
    rail_names = ("vdd_a", "vdd_d", "vdd_dac")
    static_power_by_rail: dict[str, list[float]] = {rail: [] for rail in rail_names}
    active_power_by_rail: dict[str, list[float]] = {rail: [] for rail in rail_names}
    observed_adc = []
    for measurement in measurements:
        if measurement.param.observed_adc is None:
            raise ValueError("ADC power sweep requires observed_adc in every measurement")
        observed_adc.append(measurement.param.observed_adc)
        for rail in rail_names:
            active_power_key = f"{rail}_active_average_power_w"
            if active_power_key not in measurement.info.readbacks:
                raise ValueError(f"ADC measurement is missing active-power readbacks for {rail}")
            active_power_by_rail[rail].append(float(measurement.info.readbacks[active_power_key]))

            static_power_key = f"{rail}_static_average_power_w"
            if static_power_key in measurement.info.readbacks:
                static_power_w = float(measurement.info.readbacks[static_power_key])
            else:
                voltage_key = f"{rail}_measured_voltage_v"
                current_key = f"{rail}_measured_current_a"
                if voltage_key not in measurement.info.readbacks or current_key not in measurement.info.readbacks:
                    raise ValueError(f"ADC measurement is missing static-power readbacks for {rail}")
                static_power_w = abs(
                    float(measurement.info.readbacks[voltage_key]) * float(measurement.info.readbacks[current_key])
                )
            static_power_by_rail[rail].append(static_power_w)

    vdd_a_active_power_w = np.asarray(active_power_by_rail["vdd_a"])
    vdd_d_active_power_w = np.asarray(active_power_by_rail["vdd_d"])
    vdd_dac_active_power_w = np.asarray(active_power_by_rail["vdd_dac"])
    # Independent slow SMU averages can differ by a few nanowatts. Cap a
    # baseline at its active reading rather than reporting negative added
    # dynamic power from measurement noise.
    vdd_a_static_power_w = np.minimum(np.asarray(static_power_by_rail["vdd_a"]), vdd_a_active_power_w)
    vdd_d_static_power_w = np.minimum(np.asarray(static_power_by_rail["vdd_d"]), vdd_d_active_power_w)
    vdd_dac_static_power_w = np.minimum(np.asarray(static_power_by_rail["vdd_dac"]), vdd_dac_active_power_w)
    vdd_a_dynamic_power_w = vdd_a_active_power_w - vdd_a_static_power_w
    vdd_d_dynamic_power_w = vdd_d_active_power_w - vdd_d_static_power_w
    vdd_dac_dynamic_power_w = vdd_dac_active_power_w - vdd_dac_static_power_w
    total_static_power_w = vdd_a_static_power_w + vdd_d_static_power_w + vdd_dac_static_power_w
    total_dynamic_power_w = vdd_a_dynamic_power_w + vdd_d_dynamic_power_w + vdd_dac_dynamic_power_w
    return AnalysisAdcPowerSweep(
        sample_rate_hz=np.asarray([_pattern_repeat_rate_hz(measurement) for measurement in measurements]),
        active_conversion_rate_hz=np.asarray([_active_conversion_rate_hz(measurement) for measurement in measurements]),
        observed_adc=np.asarray(observed_adc, dtype=np.int64),
        vdd_a_static_power_w=vdd_a_static_power_w,
        vdd_d_static_power_w=vdd_d_static_power_w,
        vdd_dac_static_power_w=vdd_dac_static_power_w,
        vdd_a_dynamic_power_w=vdd_a_dynamic_power_w,
        vdd_d_dynamic_power_w=vdd_d_dynamic_power_w,
        vdd_dac_dynamic_power_w=vdd_dac_dynamic_power_w,
        total_static_power_w=total_static_power_w,
        total_dynamic_power_w=total_dynamic_power_w,
        total_power_w=total_static_power_w + total_dynamic_power_w,
    )
