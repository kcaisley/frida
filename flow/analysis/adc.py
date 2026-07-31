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
    AnalysisAdcDecisionPaths,
    AnalysisAdcDynamic,
    AnalysisAdcDynamicSweep,
    AnalysisAdcNoise,
    AnalysisAdcNoiseSweep,
    AnalysisAdcNonlin,
    AnalysisAdcPowerSweep,
    AnalysisAdcTransfer,
    MeasAdc,
)
from flow.cdac import get_cdac_weights

ADC_DYNAMIC_RESIDUAL_TAIL_LIMIT_DOUT = 24.0
ADC_DYNAMIC_GAUSSIAN_TAIL_FRACTION = 0.0027


def _pattern_repeat_rate_hz(msmt: MeasAdc) -> float:
    """Return the true sampling rate including sequencer idle padding."""

    return float(msmt.param.symbol_rate) / len(msmt.param.seq_init_pattern)


def _active_conversion_rate_hz(msmt: MeasAdc) -> float:
    """Return the nominal conversion rate excluding idle padding."""

    patterns = (
        msmt.param.seq_init_pattern,
        msmt.param.seq_samp_pattern,
        msmt.param.seq_comp_pattern,
        msmt.param.seq_logic_pattern,
    )
    active = [index for index in range(len(patterns[0])) if any(pattern[index] == "1" for pattern in patterns)]
    if not active:
        raise ValueError("ADC timing patterns contain no active symbols")
    return float(msmt.param.symbol_rate) / (active[-1] - active[0] + 1)


def _input_frequency_hz(msmt: MeasAdc) -> float:
    """Return the programmed sine frequency from the measurement parameters."""

    source = msmt.param.vin_diff
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
    msmt: MeasAdc,
    *,
    sample_rate_hz: float | None = None,
    input_frequency_hz: float | None = None,
    frequency_search_fraction: float = 0.02,
    maximum_harmonic_order: int = 5,
) -> AnalysisAdcDynamic:
    """Fit one sine acquisition and calculate time- and frequency-domain metrics."""

    measured_dout = np.asarray(msmt.daq.dout, dtype=np.float64)
    sample_rate_hz = _pattern_repeat_rate_hz(msmt) if sample_rate_hz is None else float(sample_rate_hz)
    input_frequency_hz = _input_frequency_hz(msmt) if input_frequency_hz is None else float(input_frequency_hz)
    adc_bits = msmt.param.dut.adc_bits
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
    source = msmt.param.vin_diff
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


def analyze_adc_transfer(measurements: Sequence[MeasAdc]) -> AnalysisAdcTransfer:
    """Calculate mean ADC output and dispersion versus differential input."""

    if not measurements:
        raise ValueError("ADC transfer analysis requires at least one measurement")
    inputs = np.concatenate([msmt.daq.vin_diff_v for msmt in measurements])
    dout = np.concatenate([msmt.daq.dout for msmt in measurements]).astype(np.float64)
    if not len(dout):
        raise ValueError("ADC transfer analysis requires at least one conversion")
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    return AnalysisAdcTransfer(
        vin_diff_v=unique_inputs,
        mean_dout=np.asarray([np.mean(dout[inverse == index]) for index in range(len(unique_inputs))]),
        std_dout=np.asarray([np.std(dout[inverse == index]) for index in range(len(unique_inputs))]),
        sample_count=np.bincount(inverse, minlength=len(unique_inputs)).astype(np.int64),
    )


def _endpoint_nonlin(msmt: MeasAdc) -> AnalysisAdcNonlin:
    inputs = msmt.daq.vin_diff_v
    dout = msmt.daq.dout.astype(np.float64)
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    if len(unique_inputs) < 3:
        raise ValueError("endpoint nonlinearity requires at least three input points")
    mean_dout = np.asarray([np.mean(dout[inverse == index]) for index in range(len(unique_inputs))])
    transition_code, transition_input = find_code_transitions(unique_inputs, mean_dout)
    if len(transition_input) < 2:
        raise ValueError("endpoint nonlinearity spans fewer than two code transitions")
    endpoint_lsb_v = float((transition_input[-1] - transition_input[0]) / (len(transition_input) - 1))
    ideal = transition_input[0] + np.arange(len(transition_input)) * endpoint_lsb_v
    inl = (transition_input - ideal) / endpoint_lsb_v
    dnl = np.diff(transition_input) / endpoint_lsb_v - 1.0
    observed = set(np.rint(dout).astype(np.int64))
    active = range(int(np.min(transition_code)), int(np.max(transition_code)) + 2)
    return AnalysisAdcNonlin(
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


def _code_density_nonlin(
    msmt: MeasAdc,
    *,
    code_range: tuple[int, int] | None,
) -> AnalysisAdcNonlin:
    number_codes = 1 << msmt.param.dut.adc_bits
    valid = msmt.daq.dout[(msmt.daq.dout >= 0) & (msmt.daq.dout < number_codes)]
    if not len(valid):
        raise ValueError(f"ADC measurement contains no codes in 0..{number_codes - 1}")
    counts = np.bincount(valid, minlength=number_codes)
    first_code, last_code = code_range or (1, number_codes - 2)
    result = histogram_inl_dnl(counts, first_code=first_code, last_code=last_code)
    return AnalysisAdcNonlin(
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


def analyze_adc_nonlin(
    msmt: MeasAdc,
    *,
    method: Literal["endpoint", "code_density"] = "endpoint",
    code_range: tuple[int, int] | None = None,
) -> AnalysisAdcNonlin:
    """Calculate endpoint or code-density ADC INL and DNL."""

    if method == "endpoint":
        return _endpoint_nonlin(msmt)
    if method == "code_density":
        return _code_density_nonlin(msmt, code_range=code_range)
    raise ValueError("ADC nonlinearity method must be 'endpoint' or 'code_density'")


def analyze_adc_noise(measurements: Sequence[MeasAdc]) -> AnalysisAdcNoise:
    """Calculate code statistics and one histogram per static input point."""

    if not measurements:
        raise ValueError("ADC noise analysis requires at least one measurement")
    adc_bits = measurements[0].param.dut.adc_bits
    if any(msmt.param.dut.adc_bits != adc_bits for msmt in measurements):
        raise ValueError("ADC noise measurements must use one output resolution")
    inputs = np.concatenate([msmt.daq.vin_diff_v for msmt in measurements])
    dout = np.concatenate([msmt.daq.dout for msmt in measurements])
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
    return AnalysisAdcNoise(
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
    input_lsb_values_v = np.asarray(
        [float(msmt.param.vdd_dac.dc) / ((1 << msmt.param.dut.adc_bits) - 1) for msmt in measurements],
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
    minimum_dout = []
    maximum_dout = []
    bit_mismatches = []
    for msmt in measurements:
        phase = float(msmt.param.seq_logic_phase_delay_symbols) - float(msmt.param.seq_comp_phase_delay_symbols)
        sample_rate_hz.append(_active_conversion_rate_hz(msmt))
        logic_phase.append(phase)
        comparator_percent.append(50.0 + 12.5 * phase)
        mean_dout.append(float(np.mean(msmt.daq.dout)))
        std_dout.append(float(np.std(msmt.daq.dout)))
        minimum_dout.append(int(np.min(msmt.daq.dout)))
        maximum_dout.append(int(np.max(msmt.daq.dout)))
        bit_mismatches.append(int(msmt.info.readbacks.get("scope_fastrx_bit_mismatches", 0)))
    std_dout_array = np.asarray(std_dout)
    return AnalysisAdcNoiseSweep(
        sample_rate_hz=np.asarray(sample_rate_hz),
        logic_phase_delay_symbols=np.asarray(logic_phase),
        comparator_time_percent=np.asarray(comparator_percent),
        input_lsb_v=float(input_lsb_values_v[0]),
        input_referred_noise_rms_v=std_dout_array * input_lsb_values_v,
        mean_dout=np.asarray(mean_dout),
        std_dout=std_dout_array,
        minimum_dout=np.asarray(minimum_dout, dtype=np.int64),
        maximum_dout=np.asarray(maximum_dout, dtype=np.int64),
        bit_mismatches=np.asarray(bit_mismatches, dtype=np.int64),
    )


def analyze_adc_decision_paths(
    msmt: MeasAdc,
    *,
    selection: Literal["single", "same_dout", "all"] = "single",
    row_index: int = 0,
    selected_dout: int | None = None,
) -> AnalysisAdcDecisionPaths:
    """Reconstruct running SAR estimates from captured comparator decisions."""

    cap_weights = get_cdac_weights(msmt.param.dut.cdac)
    weights = np.asarray([2 * weight for weight in cap_weights] + [1], dtype=np.float64)
    if msmt.daq.bout.shape[1] != len(weights):
        raise ValueError(
            f"ADC measurement has {msmt.daq.bout.shape[1]} decisions, but its CDAC defines {len(weights)} weights"
        )
    indices = np.arange(len(msmt.daq.dout), dtype=np.int64)
    if selection == "single":
        if not 0 <= row_index < len(indices):
            raise IndexError("decision-path row_index is outside the acquisition")
        selected = np.asarray([row_index], dtype=np.int64)
    elif selection == "same_dout":
        if selected_dout is None:
            selected_dout = Counter(int(value) for value in msmt.daq.dout).most_common(1)[0][0]
        selected = np.flatnonzero(msmt.daq.dout == selected_dout)
    elif selection == "all":
        selected = indices
    else:
        raise ValueError("decision-path selection must be 'single', 'same_dout', or 'all'")

    initial_estimate = ((1 << msmt.param.dut.adc_bits) - 1) / 2.0
    paths = np.empty((len(selected), len(weights) + 1), dtype=np.float64)
    paths[:, 0] = initial_estimate
    for row, conversion in enumerate(selected):
        decided = 0.0
        remaining = float(np.sum(weights))
        for cycle, (bit, weight) in enumerate(
            zip(msmt.daq.bout[conversion], weights, strict=True),
            start=1,
        ):
            decided += bit * weight
            remaining -= weight
            paths[row, cycle] = decided + 0.5 * remaining
    return AnalysisAdcDecisionPaths(
        selection=selection,
        conversion_index=msmt.daq.conversion_index[selected],
        final_dout=msmt.daq.dout[selected],
        bout=msmt.daq.bout[selected],
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
            msmt,
            frequency_search_fraction=frequency_search_fraction,
            maximum_harmonic_order=maximum_harmonic_order,
        )
        for msmt in measurements
    ]
    return AnalysisAdcDynamicSweep(
        input_frequency_hz=np.asarray([result.input_frequency_hz for result in results]),
        sample_rate_hz=np.asarray([result.sample_rate_hz for result in results]),
        active_conversion_rate_hz=np.asarray([_active_conversion_rate_hz(msmt) for msmt in measurements]),
        observed_adc=np.asarray(
            [msmt.param.observed_adc if msmt.param.observed_adc is not None else -1 for msmt in measurements],
            dtype=np.int64,
        ),
        logic_phase_delay_symbols=np.asarray(
            [
                float(msmt.param.seq_logic_phase_delay_symbols) - float(msmt.param.seq_comp_phase_delay_symbols)
                for msmt in measurements
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
    for msmt in measurements:
        if msmt.param.observed_adc is None:
            raise ValueError("ADC power sweep requires observed_adc in every measurement")
        observed_adc.append(msmt.param.observed_adc)
        for rail in rail_names:
            active_power_key = f"{rail}_active_average_power_w"
            if active_power_key not in msmt.info.readbacks:
                raise ValueError(f"ADC measurement is missing active-power readbacks for {rail}")
            active_power_by_rail[rail].append(float(msmt.info.readbacks[active_power_key]))

            static_power_key = f"{rail}_static_average_power_w"
            if static_power_key in msmt.info.readbacks:
                static_power_w = float(msmt.info.readbacks[static_power_key])
            else:
                voltage_key = f"{rail}_measured_voltage_v"
                current_key = f"{rail}_measured_current_a"
                if voltage_key not in msmt.info.readbacks or current_key not in msmt.info.readbacks:
                    raise ValueError(f"ADC measurement is missing static-power readbacks for {rail}")
                static_power_w = abs(float(msmt.info.readbacks[voltage_key]) * float(msmt.info.readbacks[current_key]))
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
        sample_rate_hz=np.asarray([_pattern_repeat_rate_hz(msmt) for msmt in measurements]),
        active_conversion_rate_hz=np.asarray([_active_conversion_rate_hz(msmt) for msmt in measurements]),
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
