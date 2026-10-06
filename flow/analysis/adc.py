"""Typed ADC analyses for physical, behavioral, and SPICE measurements.

Every public function follows the analysis contract in ``readme.md``: one
positional measurement input, keyword-only prior results, and one typed result.
Architecture sizes (decisions, capacitors, codes, symbols per decision) are
derived from the measurement parameters, never written as literals.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import hdl21 as h
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import erfc

from flow.adc.sequences import AdcSequence
from flow.adc.subckt import AdcNets
from flow.analysis import calc
from flow.analysis.types import (
    AnalysisAdcCalibration,
    AnalysisAdcCdacSettling,
    AnalysisAdcCodeDensityNonlinearity,
    AnalysisAdcCodeDistribution,
    AnalysisAdcComparatorEdgeEye,
    AnalysisAdcComparatorResponse,
    AnalysisAdcCompOutEdgeEye,
    AnalysisAdcDecisionPaths,
    AnalysisAdcDynamic,
    AnalysisAdcEndpointNonlinearity,
    AnalysisAdcNoise,
    AnalysisAdcOperatingConditions,
    AnalysisAdcPower,
    AnalysisAdcPowerWaveform,
    AnalysisAdcRamp,
    AnalysisAdcSamplingNoise,
    AnalysisAdcScopeBits,
    AnalysisAdcTimingClosure,
    AnalysisAdcTimingSummary,
    AnalysisAdcTransfer,
    Identity,
    MeasAdc,
    check_identity,
    measurement_identity,
)
from flow.comp.subckt import CompNets

# =============================================================================
# Scope and comparator-output analyses
# =============================================================================


def analyze_adc_comp_out_edge_eye(measurements: Sequence[MeasAdc]) -> AnalysisAdcCompOutEdgeEye:
    """Measure external comparator transitions and clock jitter from scope records.

    Every scope record of every measurement is one capture of one complete
    conversion. All measurements must share one sequence and symbol rate.
    """

    identity = measurement_identity(measurements)
    first = measurements[0]
    sequence = AdcSequence.from_tb_params(first.tb)
    symbol_rate_bps = float(first.tb.symbol_rate)
    if any(
        AdcSequence.from_tb_params(measurement.tb) != sequence or float(measurement.tb.symbol_rate) != symbol_rate_bps
        for measurement in measurements
    ):
        raise ValueError("comparator eye measurements must share one sequence and symbol rate")
    decisions = len(first.nominal_bout_weights)
    decision_period_s = first.symbols_per_decision / symbol_rate_bps

    time_s = None
    comp_records = []
    comp_out_records = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("comparator eye requires scope waveform records")
        if time_s is None:
            time_s = wave.time_s
        elif not np.array_equal(time_s, wave.time_s):
            raise ValueError("comparator eye scope records must share one time axis")
        comp_records.extend(wave.v["seq_comp"])
        comp_out_records.extend(wave.v["comp_out"])
    assert time_s is not None

    capture_count = len(comp_records)
    clock_edges_s = np.empty((capture_count, decisions))
    delays_s = np.full((capture_count, decisions), np.nan)
    jitter_s = np.empty((capture_count, decisions))
    unchanged = np.zeros(decisions, dtype=np.int64)
    multiple = np.zeros(decisions, dtype=np.int64)
    unsettled = np.zeros(decisions, dtype=np.int64)
    for capture_index, (comp_v, comp_out_v) in enumerate(zip(comp_records, comp_out_records, strict=True)):
        # Take logic levels from the 5th/95th percentiles, which ignore edge
        # overshoot, and require at least 50 mV of swing to call it a logic signal.
        comp_low, comp_high = np.percentile(comp_v, (5, 95))
        out_low, out_high = np.percentile(comp_out_v, (5, 95))
        if comp_high - comp_low < 0.05 or out_high - out_low < 0.05:
            raise ValueError(f"capture {capture_index} lacks a valid COMP or COMP_OUT swing")
        comp_level = float((comp_low + comp_high) / 2)
        out_level = float((out_low + out_high) / 2)
        clock_edges = calc.cross(comp_v, time_s, comp_level, edge="rising")
        clock_edges = clock_edges[clock_edges >= 0][:decisions]
        # Allow 20% of a decision period of edge jitter before rejecting the record.
        if len(clock_edges) != decisions or np.any(
            np.abs(np.diff(clock_edges) - decision_period_s) > 0.2 * decision_period_s
        ):
            raise ValueError(f"capture {capture_index} does not contain one complete {decisions}-decision conversion")
        clock_edges_s[capture_index] = clock_edges
        jitter_s[capture_index] = clock_edges - clock_edges[0] - np.arange(decisions) * decision_period_s
        rising_edges = calc.cross(comp_out_v, time_s, out_level, edge="rising")
        output_edges = calc.cross(comp_out_v, time_s, out_level, edge="either")
        for decision, clock_edge in enumerate(clock_edges):
            matching = output_edges[(output_edges >= clock_edge) & (output_edges < clock_edge + decision_period_s)]
            if len(matching) == 1:
                rising = bool(np.any(rising_edges == matching[0]))
                final_index = min(np.searchsorted(time_s, clock_edge + decision_period_s), len(time_s)) - 1
                final_valid = comp_out_v[final_index] >= out_level if rising else comp_out_v[final_index] <= out_level
                if final_valid:
                    delays_s[capture_index, decision] = matching[0] - clock_edge
                else:
                    unsettled[decision] += 1
            elif len(matching) == 0:
                unchanged[decision] += 1
            else:
                multiple[decision] += 1

    # Resample every capture at the scope spacing, aligned to its B0 COMP rise
    # and folded at every decision's COMP rise; NaN lies outside the record.
    sample_interval_s = float(np.median(np.diff(time_s)))
    aligned_time_s = np.arange(-0.2 * decision_period_s, decisions * decision_period_s, sample_interval_s)
    eye_phase = np.arange(-0.2, 1.0, sample_interval_s / decision_period_s)
    traces = (np.asarray(comp_records), np.asarray(comp_out_records))
    aligned = [
        np.asarray(
            [
                np.interp(edges[0] + aligned_time_s, time_s, row, left=np.nan, right=np.nan)
                for row, edges in zip(values, clock_edges_s, strict=True)
            ]
        )
        for values in traces
    ]
    folded = [
        np.asarray(
            [
                np.interp(edge + eye_phase * decision_period_s, time_s, row, left=np.nan, right=np.nan)
                for row, edges in zip(values, clock_edges_s, strict=True)
                for edge in edges
            ]
        )
        for values in traces
    ]
    return AnalysisAdcCompOutEdgeEye(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        aligned_time_s=aligned_time_s,
        aligned_comp_v=aligned[0],
        aligned_comp_out_v=aligned[1],
        eye_phase=eye_phase,
        eye_comp_v=folded[0],
        eye_comp_out_v=folded[1],
        clock_edges_s=clock_edges_s,
        delays_s=delays_s,
        jitter_s=jitter_s,
        unchanged=unchanged,
        multiple=multiple,
        unsettled=unsettled,
        decision_period_s=decision_period_s,
        conversion_rate_hz=symbol_rate_bps / sequence.conversion_symbols,
    )


def analyze_adc_scope_bits(measurement: MeasAdc) -> AnalysisAdcScopeBits:
    """Decode the scope in the middle of the delayed comparator decision.

    New captures record the characterized COMP-to-COMP_OUT link delay. Older
    files without that field retain their historical 7/8-period reference.
    This independent scope reference is not the physical FastRX sample instant.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("scope/FastRX comparison requires a captured scope waveform")
    tb = measurement.tb
    decisions = measurement.bout.shape[1]
    symbols_per_decision = measurement.symbols_per_decision
    time_s = wave.time_s
    comp_v = wave.v["seq_comp"][0]
    comp_out_v = wave.v["comp_out"][0]
    # Logic levels from the 1st/99th percentiles; at least 100 mV of swing is
    # required before a scope trace is treated as a logic signal.
    comp_low_v, comp_high_v = np.percentile(comp_v, (1.0, 99.0))
    comp_out_low_v, comp_out_high_v = np.percentile(comp_out_v, (1.0, 99.0))
    comp_threshold_v = float((comp_low_v + comp_high_v) / 2.0)
    comp_out_threshold_v = float((comp_out_low_v + comp_out_high_v) / 2.0)
    if comp_high_v - comp_low_v < 0.1:
        raise ValueError("scope COMP waveform does not have a valid logic swing")
    if comp_out_high_v - comp_out_low_v < 0.1:
        raise ValueError("scope COMP_OUT waveform does not have a valid logic swing")

    rising_edges_s = calc.cross(comp_v, time_s, comp_threshold_v, edge="rising")
    rising_edges_s = rising_edges_s[rising_edges_s >= 0.0]
    if len(rising_edges_s) < decisions:
        raise ValueError(f"scope contains only {len(rising_edges_s)} COMP rising edges; expected at least {decisions}")
    comp_edge_times_s = rising_edges_s[:decisions]
    decision_period_s = symbols_per_decision / float(tb.symbol_rate)
    link_delay_s = measurement.info.readbacks.get("scope_comp_out_delay_s")
    # Historical captures sample 7/8 of a decision period after the COMP edge.
    sample_offset_s = (7.0 / 8.0) * decision_period_s
    if link_delay_s is not None:
        link_delay_s = float(link_delay_s)
        if not math.isfinite(link_delay_s) or link_delay_s < 0:
            raise ValueError("scope comparator link delay must be finite and non-negative")
        # Sample mid-decision after the characterized link delay.
        sample_offset_s = link_delay_s + 0.5 * decision_period_s
    sample_times_s = comp_edge_times_s + sample_offset_s
    sample_values_v = calc.value(comp_out_v, time_s, sample_times_s, extrapolate=False)
    scope_bits = np.asarray(sample_values_v) > comp_out_threshold_v
    if measurement.info.readbacks.get("scope_comp_out_inverted") is True:
        scope_bits = ~scope_bits
    identity = measurement.identity
    return AnalysisAdcScopeBits(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        scope_bits=scope_bits,
        fastrx_bits=measurement.bout[measurement.conversion_index == wave.record_index[0]][0].astype(np.bool_),
        comp_threshold_v=comp_threshold_v,
        comp_out_threshold_v=comp_out_threshold_v,
        comp_edge_times_s=comp_edge_times_s,
        sample_times_s=sample_times_s,
        sample_values_v=np.asarray(sample_values_v),
    )


# =============================================================================
# Static and dynamic conversion analyses
# =============================================================================


def analyze_adc_dynamic(measurement: MeasAdc) -> AnalysisAdcDynamic:
    """Fit one sine acquisition and calculate time- and frequency-domain metrics."""

    source = measurement.tb.vin_diff
    if not isinstance(source, h.Vsin.Params) or source.freq is None or source.vamp is None:
        raise ValueError("ADC dynamic analysis requires a sine vin_diff source with freq and vamp set")
    measured_dout = np.asarray(measurement.dout, dtype=np.float64)
    sample_count = len(measured_dout)
    sample_rate_hz = measurement.sample_rate_hz
    input_frequency_hz = float(source.freq)
    adc_bits = measurement.dut.adc_bits
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if sample_count < 8:
        raise ValueError("sine fit requires at least eight samples")
    if not math.isfinite(input_frequency_hz) or not 0 < input_frequency_hz < sample_rate_hz / 2:
        raise ValueError("input frequency must be finite and between zero and Nyquist")

    # Least-squares fit of sine, cosine, and offset. The AWG and the ADC
    # sample clock are not locked, so refine the programmed frequency by up to
    # 2%, but by at most 0.45 FFT bins so the bounded search stays on the main
    # lobe, resolving it to 0.1 ppb (or 1 nHz for very slow inputs).
    time_s = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    ones = np.ones(sample_count, dtype=np.float64)
    maximum_offset_hz = min(input_frequency_hz * 0.02, 0.45 * sample_rate_hz / sample_count)
    search = minimize_scalar(
        lambda frequency_hz: float(
            np.sum(
                np.linalg.lstsq(
                    np.column_stack(
                        (np.sin(2 * np.pi * frequency_hz * time_s), np.cos(2 * np.pi * frequency_hz * time_s), ones)
                    ),
                    measured_dout,
                    rcond=None,
                )[1]
            )
        ),
        bounds=(
            max(np.nextafter(0.0, 1.0), input_frequency_hz - maximum_offset_hz),
            min(np.nextafter(sample_rate_hz / 2.0, 0.0), input_frequency_hz + maximum_offset_hz),
        ),
        method="bounded",
        options={"xatol": max(1e-9, input_frequency_hz * 1e-10)},
    )
    if not search.success:
        raise RuntimeError(f"sine frequency fit failed: {search.message}")
    fitted_frequency_hz = float(search.x)
    phase = 2.0 * np.pi * fitted_frequency_hz * time_s
    design = np.column_stack((np.sin(phase), np.cos(phase), ones))
    sine_coefficient, cosine_coefficient, offset_dout = (
        float(value) for value in np.linalg.lstsq(design, measured_dout, rcond=None)[0]
    )
    fitted_dout = design @ np.asarray((sine_coefficient, cosine_coefficient, offset_dout))
    residual_dout = measured_dout - fitted_dout
    residual_rms_dout = calc.rms(residual_dout)
    amplitude_dout = math.hypot(sine_coefficient, cosine_coefficient)
    full_scale_peak_dout = measurement.code_max / 2.0
    (
        spectral_sndr_db,
        spectral_snr_db,
        spectral_thd_db,
        spectral_sfdr_db,
        spectral_enob_bits,
        spectrum_frequency_hz,
        spectrum_dbfs,
    ) = calc.spectrumMeas(
        measured_dout,
        sample_rate=sample_rate_hz,
        fundamental_frequency=fitted_frequency_hz,
        offset=offset_dout,
        full_scale_peak=full_scale_peak_dout,
        # Count harmonics 2..5 as distortion, the conventional THD bandwidth.
        maximum_harmonic_order=5,
    )
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
    # Flag residuals beyond three fitted RMS deviations; a Gaussian residual
    # exceeds that two-sided limit with probability erfc(3/sqrt(2)) ~= 0.27%.
    tail_sigma = 3.0
    identity = measurement.identity
    return AnalysisAdcDynamic(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        sample_rate_hz=sample_rate_hz,
        active_conversion_rate_hz=measurement.active_conversion_rate_hz,
        logic_phase_delay_symbols=measurement.logic_phase_delay_symbols,
        input_frequency_hz=input_frequency_hz,
        fitted_frequency_hz=fitted_frequency_hz,
        adc_bits=adc_bits,
        offset_dout=offset_dout,
        amplitude_dout=amplitude_dout,
        phase_rad=math.atan2(cosine_coefficient, sine_coefficient),
        input_referred_noise_rms_v=input_referred_noise_rms_v,
        input_referred_residual_rms_v=input_referred_residual_rms_v,
        spectral_sndr_db=spectral_sndr_db,
        spectral_snr_db=spectral_snr_db,
        spectral_thd_db=spectral_thd_db,
        spectral_sfdr_db=spectral_sfdr_db,
        spectral_enob_bits=spectral_enob_bits,
        residual_tail_limit_dout=tail_sigma * residual_rms_dout,
        expected_residual_tail_count=sample_count * float(erfc(tail_sigma / math.sqrt(2.0))),
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
    """Pool conversions by input and calculate transfer statistics.

    With a calibration, DOUT is decoded transiently from the stored BOUT.
    """

    identity = measurement_identity(measurements)
    if calibration is not None:
        check_identity(calibration, identity, name="calibration")
    inputs = np.concatenate([measurement.vin_diff_v for measurement in measurements])
    dout = np.concatenate(
        [
            measurement.dout if calibration is None else calibration.decode_bout(measurement.bout)
            for measurement in measurements
        ]
    ).astype(np.float64)
    if not len(dout):
        raise ValueError("ADC transfer analysis requires at least one conversion")
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    return AnalysisAdcTransfer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_diff_v=unique_inputs,
        mean_dout=np.asarray([calc.average(dout[inverse == index]) for index in range(len(unique_inputs))]),
        std_dout=np.asarray([calc.stddev(dout[inverse == index]) for index in range(len(unique_inputs))]),
        sample_count=np.bincount(inverse, minlength=len(unique_inputs)).astype(np.int64),
    )


def analyze_adc_endpoint_nonlinearity(
    measurement: MeasAdc,
    *,
    calibration: AnalysisAdcCalibration | None = None,
) -> AnalysisAdcEndpointNonlinearity:
    """Calculate endpoint INL and DNL from code transitions of a stepped input."""

    if calibration is not None:
        check_identity(calibration, measurement.identity, name="calibration")
    decoded_dout = np.asarray(
        measurement.dout if calibration is None else calibration.decode_bout(measurement.bout),
        dtype=np.float64,
    )
    unique_inputs, inverse = np.unique(measurement.vin_diff_v, return_inverse=True)
    if len(unique_inputs) < 3:
        raise ValueError("endpoint nonlinearity requires at least three input points")
    mean_dout = np.asarray([calc.average(decoded_dout[inverse == index]) for index in range(len(unique_inputs))])
    direction = 1.0 if mean_dout[-1] >= mean_dout[0] else -1.0
    increasing = direction * mean_dout
    if np.any(np.diff(increasing) < 0):
        raise ValueError("code transition extraction requires a monotonic transfer")
    # A code transition is where the mean output crosses the half-code boundary.
    first = math.ceil(increasing[0] - 0.5)
    last = math.floor(increasing[-1] - 0.5)
    codes = np.arange(first, last + 1, dtype=np.int64)
    transitions = np.asarray([calc.cross(increasing, unique_inputs, float(code) + 0.5, occurrence=1) for code in codes])
    bracketed = np.isfinite(transitions)
    transition_code = np.asarray(direction * codes[bracketed], dtype=np.int64)
    transition_input = transitions[bracketed]
    if len(transition_input) < 2:
        raise ValueError("endpoint nonlinearity spans fewer than two code transitions")
    endpoint_lsb_v = float((transition_input[-1] - transition_input[0]) / (len(transition_input) - 1))
    dnl = calc.deriv(transition_input, np.arange(len(transition_input))) / endpoint_lsb_v - 1.0
    observed = set(np.rint(decoded_dout).astype(np.int64))
    active = range(int(calc.ymin(transition_code)), int(calc.ymax(transition_code)) + 2)
    identity = measurement.identity
    return AnalysisAdcEndpointNonlinearity(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        code=transition_code[1:],
        dnl=dnl,
        inl=calc.inl(dnl, endpoint_correct=False),
        transition_vin_diff_v=transition_input[1:],
        endpoint_lsb_v=endpoint_lsb_v,
        missing_codes=sum(code not in observed for code in active),
    )


def analyze_adc_code_density_nonlinearity(
    measurement: MeasAdc,
    *,
    ramp: AnalysisAdcRamp | None = None,
    calibration: AnalysisAdcCalibration | None = None,
) -> AnalysisAdcCodeDensityNonlinearity:
    """Calculate code-density INL and DNL from a uniformly distributed input.

    With a ramp result, only its ``retained`` conversions (away from each
    wrap) are counted. The first and last codes are excluded because a finite
    ramp clips into them.
    """

    if calibration is not None:
        check_identity(calibration, measurement.identity, name="calibration")
    decoded_dout = measurement.dout if calibration is None else calibration.decode_bout(measurement.bout)
    sample_count = len(decoded_dout)
    if ramp is not None:
        check_identity(ramp, measurement.identity, name="ramp")
        if ramp.sample_count != sample_count:
            raise ValueError("ramp analysis and measurement contain different conversion counts")
        decoded_dout = decoded_dout[ramp.retained]
    number_codes = measurement.code_max + 1
    valid = decoded_dout[(decoded_dout >= 0) & (decoded_dout < number_codes)]
    if not len(valid):
        raise ValueError(f"ADC measurement contains no codes in 0..{number_codes - 1}")
    counts = np.bincount(valid, minlength=number_codes)
    active_counts = counts[1 : number_codes - 1]
    ideal_count = calc.average(active_counts)
    dnl = calc.dnl(active_counts, ideal_count=ideal_count)
    identity = measurement.identity
    return AnalysisAdcCodeDensityNonlinearity(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        code=np.arange(1, number_codes - 1, dtype=np.int64),
        dnl=dnl,
        inl=calc.inl(dnl),
        count=active_counts,
        ideal_count=ideal_count,
        retained_sample_count=len(decoded_dout),
        sample_count=sample_count,
    )


def analyze_adc_ramp(
    measurement: MeasAdc,
    *,
    calibration: AnalysisAdcCalibration | None = None,
) -> AnalysisAdcRamp:
    """Recover the nominal or calibrated transfer and linearity of one repeated ramp.

    The PWL source and sample rate give the nominal ramp period in
    conversions. The AWG and FastRX are neither started together nor locked,
    so the wrap phase, and a ppm-level correction to the period, are fitted
    coherently to the sawtooth's fundamental in the nominal DOUT. No jump in
    DOUT needs to be detected. That phase maps each conversion back to the
    programmed input range, while the uniform code histogram supplies DNL and
    endpoint-corrected INL. Clipped end codes are excluded from linearity.
    A calibration decodes the same stored BOUT words; the phase always comes
    from the nominal DOUT, so every decoding of one capture uses the same
    retained conversions and the methods stay comparable.
    """

    tb = measurement.tb
    source = tb.vin_diff
    if not isinstance(source, h.Vpwl.Params):
        raise TypeError("ADC ramp analysis requires a PWL differential-input source")
    # The PWL source repeats after its last time point.
    if isinstance(source.wave, str):
        pwl_values = np.asarray([float(value) for value in source.wave.split()], dtype=np.float64)
        pwl_time_s, pwl_value_v = pwl_values[0::2], pwl_values[1::2]
    else:
        pwl_time_s = np.asarray([float(time) for time, _value in source.wave.points], dtype=np.float64)
        pwl_value_v = np.asarray([float(value) for _time, value in source.wave.points], dtype=np.float64)
    if len(pwl_time_s) < 2 or len(pwl_time_s) != len(pwl_value_v):
        raise ValueError("PWL wave must contain at least two time/value pairs")
    intended_input = np.asarray(measurement.vin_diff_v, dtype=np.float64)
    if intended_input.ndim != 1 or len(intended_input) < 2:
        raise ValueError("ADC ramp analysis requires at least two intended input samples")
    vin_diff_min_v = float(calc.ymin(intended_input))
    vin_diff_max_v = float(calc.ymax(intended_input))
    if not vin_diff_max_v > vin_diff_min_v:
        raise ValueError("ADC ramp input must span a nonzero differential range")

    nominal_weights_int = measurement.nominal_bout_weights
    nominal_weights = nominal_weights_int.astype(np.float64)
    code_max = measurement.code_max
    number_codes = code_max + 1
    if measurement.bout.shape[1] != len(nominal_weights):
        raise ValueError("ADC ramp decisions do not match the nominal CDAC weights")
    nominal_raw = np.asarray(measurement.bout, dtype=np.int64) @ nominal_weights_int
    if not np.array_equal(nominal_raw, measurement.dout_raw):
        raise ValueError("stored ramp DOUT_RAW does not match BOUT decoded with the configured design weights")
    expected_nominal_dout = np.rint(nominal_raw * code_max / np.sum(nominal_weights_int)).astype(np.int64)
    if not np.array_equal(expected_nominal_dout, measurement.dout):
        raise ValueError("stored ramp DOUT does not match normalized DOUT_RAW")
    nominal_decoded = np.asarray(measurement.dout, dtype=np.int64)
    if np.any((nominal_decoded < 0) | (nominal_decoded >= number_codes)):
        raise ValueError(f"ADC ramp contains output codes outside 0..{number_codes - 1}")

    identity = measurement.identity
    if calibration is not None:
        check_identity(calibration, identity, name="calibration")

    sample_rate_hz = measurement.sample_rate_hz
    nominal_period = float(pwl_time_s[-1] - pwl_time_s[0]) * sample_rate_hz
    sample_count = len(nominal_decoded)
    if not 1.0 < nominal_period <= sample_count / 2.0:
        raise ValueError("ADC ramp capture must contain at least two PWL periods")
    # A falling PWL ramp is fitted as a rising one on the negated output.
    oriented = (1.0 if pwl_value_v[-1] > pwl_value_v[0] else -1.0) * (nominal_decoded - calc.average(nominal_decoded))
    sample = np.arange(sample_count, dtype=np.float64)
    # Take the sawtooth's fundamental phase over each whole nominal period:
    # over exactly one period the DC term and every harmonic are orthogonal to
    # it, so a rising ramp wrapping at n0 gives arg = pi/2 - 2 pi n0 / P. The
    # unlocked AWG and FPGA clocks differ by ppm, which makes the phase drift
    # linearly from period to period; the regression slope corrects the period
    # and its intercept gives the first wrap.
    segment_count = int(sample_count // nominal_period)
    segment_phase = np.unwrap(
        [
            np.angle(np.sum(oriented[segment] * np.exp(-2j * np.pi * sample[segment] / nominal_period)))
            for start, stop in (
                (math.ceil(index * nominal_period), math.ceil((index + 1) * nominal_period))
                for index in range(segment_count)
            )
            for segment in (slice(start, stop),)
        ]
    )
    slope, intercept = np.polyfit(np.arange(segment_count, dtype=np.float64), segment_phase, 1)
    period_conversions = nominal_period * (1.0 - slope / (2.0 * np.pi))
    coarse_wrap = (np.pi / 2 - intercept) * nominal_period / (2.0 * np.pi)

    # A nonlinear or asymmetric transfer biases the fundamental's phase, so
    # refine the wrap by least squares against the full sawtooth shape of the
    # intended input: an offset and gain fit the output to the ramp position,
    # and the residual grows linearly with any misalignment of the wraps.
    # Search 2% of a period either side of the coarse wrap, far wider than the
    # phase bias of any monotonic transfer, and resolve it to 0.01 conversion.
    ones = np.ones(sample_count)
    refined = minimize_scalar(
        lambda wrap: float(
            np.sum(
                np.linalg.lstsq(
                    np.column_stack((ones, np.mod((sample - wrap) / period_conversions, 1.0))),
                    oriented,
                    rcond=None,
                )[1]
            )
        ),
        bounds=(coarse_wrap - 0.02 * period_conversions, coarse_wrap + 0.02 * period_conversions),
        method="bounded",
        options={"xatol": 0.01},
    )
    if not refined.success:
        raise RuntimeError(f"ramp phase fit failed: {refined.message}")
    first_wrap_conversion = float(np.mod(refined.x, period_conversions))
    conversion_phase = np.mod((sample - first_wrap_conversion) / period_conversions, 1.0)
    retained = np.ones(sample_count, dtype=bool)
    wraps = first_wrap_conversion + period_conversions * np.arange(
        math.ceil((sample_count - first_wrap_conversion) / period_conversions)
    )
    for wrap in np.ceil(wraps).astype(np.int64):
        # Drop one conversion before each fitted wrap, for phase uncertainty,
        # and eight after it, while the AWG flyback and input settle.
        retained[max(0, wrap - 1) : wrap + 8] = False
    if not np.any(retained):
        raise ValueError("ADC ramp retains no conversions after wrap exclusion")

    transfer_bin = np.minimum((conversion_phase * number_codes).astype(np.int64), code_max)
    transfer_sample_count = np.bincount(transfer_bin[retained], minlength=number_codes).astype(np.int64)
    populated = transfer_sample_count > 0
    transfer_vin_diff_v = vin_diff_min_v + (
        (np.arange(number_codes, dtype=np.float64) + 0.5) / number_codes * (vin_diff_max_v - vin_diff_min_v)
    )
    decoded = nominal_decoded if calibration is None else calibration.decode_bout(measurement.bout)
    counts = np.bincount(decoded[retained], minlength=number_codes).astype(np.int64)
    # Clipped end codes stay in the histogram but not in linearity.
    active_counts = counts[1:code_max]
    ideal_count = calc.average(active_counts)
    dnl = calc.dnl(active_counts, ideal_count=ideal_count)
    transfer_sum = np.bincount(transfer_bin[retained], weights=decoded[retained], minlength=number_codes)
    return AnalysisAdcRamp(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        decoding="uncalibrated_dout" if calibration is None else calibration.method,
        label="Uncalibrated DOUT" if calibration is None else calibration.label,
        weights=nominal_weights if calibration is None else calibration.calibrated_weights,
        sample_rate_hz=sample_rate_hz,
        period_conversions=period_conversions,
        first_wrap_conversion=first_wrap_conversion,
        retained=retained,
        vin_diff_min_v=vin_diff_min_v,
        vin_diff_max_v=vin_diff_max_v,
        transfer_vin_diff_v=transfer_vin_diff_v[populated],
        transfer_mean_dout=transfer_sum[populated] / transfer_sample_count[populated],
        transfer_sample_count=transfer_sample_count[populated],
        code=np.arange(number_codes, dtype=np.int64),
        count=counts,
        linearity_code=np.arange(1, code_max, dtype=np.int64),
        dnl=dnl,
        inl=calc.inl(dnl),
        ideal_count=ideal_count,
    )


def analyze_adc_code_distribution(
    measurements: Sequence[MeasAdc],
    *,
    calibration: AnalysisAdcCalibration | None = None,
) -> AnalysisAdcCodeDistribution:
    """Pool conversions by input and histogram their output codes."""

    identity = measurement_identity(measurements)
    if calibration is not None:
        check_identity(calibration, identity, name="calibration")
    inputs = np.concatenate([measurement.vin_diff_v for measurement in measurements])
    dout = np.concatenate(
        [
            measurement.dout if calibration is None else calibration.decode_bout(measurement.bout)
            for measurement in measurements
        ]
    )
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    number_codes = measurements[0].code_max + 1
    count = np.zeros((len(unique_inputs), number_codes), dtype=np.int64)
    for index in range(len(unique_inputs)):
        values = dout[inverse == index]
        valid = values[(values >= 0) & (values < number_codes)]
        if not len(valid):
            raise ValueError(f"input point {unique_inputs[index]:g} V has no valid ADC codes")
        count[index] = np.bincount(valid, minlength=number_codes)
    return AnalysisAdcCodeDistribution(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_diff_v=unique_inputs,
        code=np.arange(number_codes, dtype=np.int64),
        count=count,
    )


def analyze_adc_noise(measurement: MeasAdc) -> AnalysisAdcNoise:
    """Histogram one fixed-input capture and record its timing coordinates.

    The readout of a physical capture is valid only with a valid scope/FastRX
    comparison, no bit mismatches, and no lost FastRX frames.
    """

    tb = measurement.tb
    number_codes = measurement.code_max + 1
    dout = measurement.dout
    if np.any((dout < 0) | (dout >= number_codes)):
        raise ValueError("ADC noise capture contains output codes outside its resolution")
    wave = measurement.wave
    pretrigger = None if wave is None else wave.time_s < 0.0
    if wave is not None and "vin_diff" in wave.v and pretrigger is not None and np.any(pretrigger):
        quiet_input = wave.v["vin_diff"][:, pretrigger]
        pretrigger_mean_v = calc.average(quiet_input)
        pretrigger_noise_v = calc.rms([calc.stddev(record) for record in quiet_input])
    else:
        pretrigger_mean_v = math.nan
        pretrigger_noise_v = math.nan
    readbacks = measurement.info.readbacks
    readout_valid = measurement.info.backend != "physical" or (
        readbacks.get("scope_fastrx_comparison_valid") is True
        and int(readbacks.get("scope_fastrx_bit_mismatches", -1)) == 0
        and int(readbacks.get("fastrx_lost_count", -1)) == 0
    )
    identity = measurement.identity
    return AnalysisAdcNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        sequence=AdcSequence.from_tb_params(tb),
        symbol_rate_hz=float(tb.symbol_rate),
        sample_rate_hz=measurement.sample_rate_hz,
        active_conversion_rate_hz=measurement.active_conversion_rate_hz,
        logic_phase_delay_symbols=measurement.logic_phase_delay_symbols,
        comparator_time_percent=measurement.comparator_time_percent,
        input_lsb_v=float(tb.vdd_dac.dc) / (number_codes - 1),
        pretrigger_vin_diff_mean_v=pretrigger_mean_v,
        pretrigger_vin_diff_noise_rms_v=pretrigger_noise_v,
        bit_mismatches=int(readbacks.get("scope_fastrx_bit_mismatches", 0)),
        readout_valid=bool(readout_valid),
        code=np.arange(number_codes, dtype=np.int64),
        count=np.bincount(dout, minlength=number_codes),
    )


def analyze_adc_operating_conditions(
    measurements: Sequence[MeasAdc],
    *,
    noise: Sequence[AnalysisAdcNoise],
) -> AnalysisAdcOperatingConditions:
    """Judge which sequence and symbol-rate settings of one ADC give plausible codes.

    Each measurement is matched to the noise result with the same sequence
    and symbol rate. The reference code is the median mean code over every
    sequence at the lowest symbol rate, where timing is most relaxed.
    """

    identity = measurement_identity(measurements)
    check_identity(noise, identity, name="noise")
    by_coordinates: dict[tuple[AdcSequence, float], AnalysisAdcNoise] = {}
    for result in noise:
        key = (result.sequence, result.symbol_rate_hz)
        if key in by_coordinates:
            raise ValueError("noise results contain a duplicate sequence and symbol rate")
        by_coordinates[key] = result
    rows = []
    for measurement in measurements:
        key = (AdcSequence.from_tb_params(measurement.tb), float(measurement.tb.symbol_rate))
        if key not in by_coordinates:
            raise ValueError("no noise result matches a measurement's sequence and symbol rate")
        rows.append(by_coordinates[key])
    if len({(row.sequence, row.symbol_rate_hz) for row in rows}) != len(rows):
        raise ValueError("operating-condition measurements repeat a sequence and symbol rate")

    symbol_rate_hz = np.asarray([row.symbol_rate_hz for row in rows])
    mean_dout = np.asarray([row.mean_dout for row in rows])
    std_dout = np.asarray([row.std_dout for row in rows])
    slowest = symbol_rate_hz == calc.ymin(symbol_rate_hz)
    reference_mean_dout = float(np.median(mean_dout[slowest]))
    # A setting is shifted when its mean leaves the reference by more than
    # five times the median code noise at the slowest rate, but never less
    # than four codes, so a noise-free capture is not flagged for a code step.
    shift_limit_dout = max(4.0, 5.0 * float(np.median(std_dout[slowest])))
    # Constant output: one code, a 99.5% modal code, or under 0.1 code of
    # dispersion means the noise is below what the code variance resolves.
    constant = np.asarray(
        [row.distinct_code_count <= 1 or row.modal_fraction >= 0.995 or row.std_dout < 0.1 for row in rows]
    )
    mean_shift_dout = mean_dout - reference_mean_dout
    return AnalysisAdcOperatingConditions(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        sequence=tuple(row.sequence for row in rows),
        symbol_rate_hz=symbol_rate_hz,
        enob_bits=np.asarray([row.enob_bits for row in rows]),
        mean_shift_dout=mean_shift_dout,
        reference_mean_dout=reference_mean_dout,
        shift_limit_dout=shift_limit_dout,
        constant=constant,
        shifted=np.abs(mean_shift_dout) > shift_limit_dout,
        readout_valid=np.asarray([row.readout_valid for row in rows]),
    )


def analyze_adc_decision_paths(measurement: MeasAdc) -> AnalysisAdcDecisionPaths:
    """Reconstruct running SAR estimates from every captured decision record."""

    weights = measurement.nominal_bout_weights.astype(np.float64)
    bout = np.asarray(measurement.bout)
    if bout.shape[1] != len(weights):
        raise ValueError(f"ADC measurement has {bout.shape[1]} decisions, but its CDAC defines {len(weights)} weights")
    normalized_code_max = measurement.code_max
    raw_code_max = float(np.sum(weights))
    decided = np.cumsum(bout * weights, axis=1)
    remaining = raw_code_max - np.cumsum(weights)
    paths = np.empty((len(bout), len(weights) + 1), dtype=np.float64)
    # Before any decision the estimate is mid-scale; afterwards each undecided
    # weight contributes half its value.
    paths[:, 0] = normalized_code_max / 2.0
    paths[:, 1:] = (decided + 0.5 * remaining) * normalized_code_max / raw_code_max
    identity = measurement.identity
    return AnalysisAdcDecisionPaths(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        conversion_index=measurement.conversion_index,
        final_dout=measurement.dout,
        bout=bout,
        weights=weights,
        estimate_dout=paths,
    )


# =============================================================================
# Internal-waveform analyses
# =============================================================================


def analyze_adc_sampling_noise(measurement: MeasAdc) -> AnalysisAdcSamplingNoise:
    """Sample P/N voltages exactly 1 ns after the first SEQ_SAMP falling edge.

    Interpolate saved samples at that instant for every conversion, including
    cases where COMP has already fired. Retain the DC offset in the result;
    the spread can include comparator activity and is not isolated kT/C noise.
    Equal window bounds record an instantaneous observation, not an average.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    threshold = 0.5 * float(measurement.tb.vdd_d.dc)
    starts, stops, held_p, held_n, inputs = [], [], [], [], []
    for row in range(len(wave.record_index)):
        sample_time = (
            calc.cross(wave.v[AdcNets.seq_samp.name][row], wave.time_s, threshold, edge="falling", occurrence=1) + 1e-9
        )
        if not math.isfinite(sample_time):
            raise ValueError("sampling noise requires a SAMP falling edge")
        input_trace = wave.v[AdcNets.vin_p.name][row] - wave.v[AdcNets.vin_n.name][row]
        # A 1 nV peak-to-peak bound distinguishes a DC input from numerical noise.
        if calc.peakToPeak(input_trace) > 1e-9:
            raise ValueError("sampling noise analysis requires a fixed differential input")
        starts.append(sample_time)
        stops.append(sample_time)
        held_p.append(calc.value(wave.v[AdcNets.vdac_p.name][row], wave.time_s, sample_time, extrapolate=False))
        held_n.append(calc.value(wave.v[AdcNets.vdac_n.name][row], wave.time_s, sample_time, extrapolate=False))
        inputs.append(calc.value(input_trace, wave.time_s, sample_time, extrapolate=False))
    if calc.peakToPeak(inputs) > 1e-9:
        raise ValueError("sampling noise analysis requires the same input across conversions")
    identity = measurement.identity
    return AnalysisAdcSamplingNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        conversion_index=wave.record_index,
        window_start_s=np.asarray(starts),
        window_stop_s=np.asarray(stops),
        held_p_v=np.asarray(held_p),
        held_n_v=np.asarray(held_n),
        input_diff_v=np.asarray(inputs),
    )


def analyze_adc_cdac_settling(measurement: MeasAdc) -> AnalysisAdcCdacSettling:
    """Align the first, middle, and last CDAC stages and measure final-value settling."""

    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    time_s = wave.time_s
    threshold_v = 0.5 * float(measurement.tb.vdd_d.dc)
    capacitors = len(measurement.nominal_bout_weights) - 1
    decisions = capacitors + 1
    stage_cycles = tuple((stage, stage) for stage in dict.fromkeys((0, (capacitors - 1) // 2, capacitors - 1)))
    # A 1 mV band is well below one LSB of the CDAC reference.
    settling_tolerance_v = 1e-3
    cycle_windows = []
    for record_index, conversion_index in enumerate(wave.record_index):
        comp_rising_s = np.asarray(
            calc.cross(wave.v[AdcNets.clk_comp.name][record_index], time_s, threshold_v, edge="rising")
        )
        comp_falling_s = np.asarray(
            calc.cross(wave.v[AdcNets.clk_comp.name][record_index], time_s, threshold_v, edge="falling")
        )
        logic_rising_s = np.asarray(
            calc.cross(wave.v[AdcNets.seq_logic.name][record_index], time_s, threshold_v, edge="rising")
        )
        period_s = len(measurement.tb.seq_init_pattern) / float(measurement.tb.symbol_rate)
        comp_rising_s = comp_rising_s[comp_rising_s < period_s]
        comp_falling_s = comp_falling_s[comp_falling_s < period_s]
        logic_rising_s = logic_rising_s[logic_rising_s < period_s]
        if len(comp_rising_s) != decisions or len(logic_rising_s) < capacitors:
            raise ValueError(
                f"ADC CDAC settling requires {decisions} internal COMP pulses and {capacitors} following LOGIC edges"
            )
        comp_stops_s = []
        for cycle, rising_s in enumerate(comp_rising_s):
            next_rising_s = comp_rising_s[cycle + 1] if cycle < capacitors else time_s[-1]
            falling_s = comp_falling_s[(comp_falling_s > rising_s) & (comp_falling_s <= next_rising_s)]
            if len(falling_s) == 1:
                comp_stops_s.append(float(falling_s[0]))
            elif (
                cycle == capacitors
                and not len(falling_s)
                and wave.v[AdcNets.clk_comp.name][record_index, -1] >= threshold_v
                and wave.v[AdcNets.seq_comp.name][record_index, -1] >= threshold_v
            ):
                # Back-to-back records end during the final comparison.
                # Show only saved samples; do not invent its later reset edge.
                comp_stops_s.append(float(time_s[-1]))
            else:
                raise ValueError(f"ADC comparator cycle {cycle} does not have one reset edge")
        for stage_index, cycle_index in stage_cycles:
            start_s = float(comp_rising_s[cycle_index])
            next_comp_s = float(comp_rising_s[cycle_index + 1])
            following_logic_s = logic_rising_s[(logic_rising_s > start_s) & (logic_rising_s < next_comp_s)]
            if len(following_logic_s) != 1:
                raise ValueError(f"ADC CDAC stage C{stage_index} does not have one complete update interval")
            cycle_windows.append(
                (
                    record_index,
                    int(conversion_index),
                    stage_index,
                    cycle_index,
                    start_s,
                    float(following_logic_s[0]),
                    next_comp_s,
                    comp_stops_s[cycle_index + 1],
                )
            )

    waveform_sample_interval_s = np.median(np.diff(time_s))
    decision_period_s = min(
        next_comp_s - start_s
        for _record, _conversion, _bit, _cycle, start_s, _logic_s, next_comp_s, _stop_s in cycle_windows
    )
    # Show 5% of a decision period before each COMP edge for context.
    margin_samples = max(1, int(np.rint(0.05 * decision_period_s / waveform_sample_interval_s)))
    displayed_stop_s = min(
        min(stop_s + margin_samples * waveform_sample_interval_s, time_s[-1]) - start_s
        for _record, _conversion, _bit, _cycle, start_s, _logic_s, _next_comp_s, stop_s in cycle_windows
    )
    stop_samples = int(np.floor(displayed_stop_s / waveform_sample_interval_s))
    relative_time_s = np.arange(-margin_samples, stop_samples + 1, dtype=np.float64) * waveform_sample_interval_s

    stage_indices = []
    cycle_indices = []
    conversion_indices = []
    aligned: dict[str, list[np.ndarray]] = {
        name: []
        for name in (
            "clk_comp_v",
            "comp_out_p_v",
            "comp_out_n_v",
            "seq_logic_v",
            "dac_state_p_v",
            "dac_state_n_v",
            "dac_botplate_p_v",
            "dac_botplate_n_v",
            "vdac_p_settling_error_v",
            "vdac_n_settling_error_v",
        )
    }
    static_vdac_p_v = []
    static_vdac_n_v = []
    vdac_p_settling_s = []
    vdac_n_settling_s = []
    internal_names = tuple(
        name
        for name in ("comp_latch_p_v", "comp_latch_n_v")
        if name.replace("comp_", "comp.", 1).removesuffix("_v") in wave.v
    )
    aligned.update({name: [] for name in internal_names})
    for (
        record_index,
        conversion_index,
        stage_index,
        cycle_index,
        start_s,
        logic_s,
        next_comp_s,
        _stop_s,
    ) in cycle_windows:
        sample_time_s = start_s + relative_time_s
        # Use the quiet tail after the CDAC update (75% to 95% of the way to
        # the next comparator edge) as the per-trace static settling reference.
        settling_reference = (time_s >= logic_s + 0.75 * (next_comp_s - logic_s)) & (
            time_s <= logic_s + 0.95 * (next_comp_s - logic_s)
        )
        if np.count_nonzero(settling_reference) < 2:
            raise ValueError(f"ADC CDAC stage C{stage_index} has fewer than two settled-reference samples")
        p_static_v = np.median(wave.v[AdcNets.vdac_p.name][record_index, settling_reference])
        n_static_v = np.median(wave.v[AdcNets.vdac_n.name][record_index, settling_reference])
        evaluation_stop_s = logic_s + 0.95 * (next_comp_s - logic_s)
        for side, static_v, durations in (
            ("p", p_static_v, vdac_p_settling_s),
            ("n", n_static_v, vdac_n_settling_s),
        ):
            evaluation_v, evaluation_s = calc.clip(
                wave.v[f"vdac_{side}"][record_index], time_s, logic_s, evaluation_stop_s
            )
            settled_at_s = calc.settlingTime(
                evaluation_v, evaluation_s, final=float(static_v), absolute_tolerance=settling_tolerance_v
            )
            durations.append(settled_at_s - logic_s if math.isfinite(settled_at_s) else math.nan)
        stage_indices.append(stage_index)
        cycle_indices.append(cycle_index)
        conversion_indices.append(conversion_index)
        static_vdac_p_v.append(p_static_v)
        static_vdac_n_v.append(n_static_v)
        for name in ("clk_comp_v", "comp_out_p_v", "comp_out_n_v", "seq_logic_v"):
            aligned[name].append(calc.value(wave.v[name.removesuffix("_v")][record_index], time_s, sample_time_s))
        for name in internal_names:
            aligned[name].append(
                calc.value(
                    wave.v[name.replace("comp_", "comp.", 1).removesuffix("_v")][record_index],
                    time_s,
                    sample_time_s,
                )
            )
        for side in ("p", "n"):
            for signal in ("dac_state", "dac_botplate"):
                aligned[f"{signal}_{side}_v"].append(
                    calc.value(wave.v[f"{signal}_{side}[{stage_index}]"][record_index], time_s, sample_time_s)
                )
        aligned["vdac_p_settling_error_v"].append(
            calc.value(wave.v[AdcNets.vdac_p.name][record_index], time_s, sample_time_s) - p_static_v
        )
        aligned["vdac_n_settling_error_v"].append(
            calc.value(wave.v[AdcNets.vdac_n.name][record_index], time_s, sample_time_s) - n_static_v
        )

    identity = measurement.identity
    return AnalysisAdcCdacSettling(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        active_conversion_rate_hz=measurement.active_conversion_rate_hz,
        stage_index=np.asarray(stage_indices),
        cycle_index=np.asarray(cycle_indices),
        conversion_index=np.asarray(conversion_indices),
        time_s=relative_time_s,
        **{name: np.asarray(values) for name, values in aligned.items()},
        static_vdac_p_v=np.asarray(static_vdac_p_v),
        static_vdac_n_v=np.asarray(static_vdac_n_v),
        vdac_p_settling_s=np.asarray(vdac_p_settling_s),
        vdac_n_settling_s=np.asarray(vdac_n_settling_s),
    )


# =============================================================================
# Power analyses
# =============================================================================


def analyze_adc_power(measurement: MeasAdc) -> AnalysisAdcPower:
    """Separate one capture's active power into static-baseline and incremental parts.

    New captures provide a configured-idle ``static_average_power_w`` for each
    rail. Older captures fall back to their supply-on voltage/current readback,
    which predates the active sequencer interval but is sufficient to analyze
    the existing physical campaign. SPICE measurements average active power
    from the first SEQ_INIT edge through one conversion period. Static power
    is the signed, time-weighted mean over the settled idle tail between that
    conversion and the next SEQ_INIT edge (or the end of the waveform).
    """

    tb = measurement.tb
    rail_names = ("vdd_a", "vdd_d", "vdd_dac")
    readbacks = measurement.info.readbacks
    spice_static_indices = None
    spice_active = None
    # Only a simulation records supply currents; a physical capture reports SMU readbacks.
    wave = measurement.wave if measurement.wave is not None and measurement.wave.i else None
    if wave is not None:
        waveform_time_s = wave.time_s
        init_rising_s = calc.cross(
            wave.v[AdcNets.seq_init.name][0],
            waveform_time_s,
            0.5 * float(tb.vdd_d.dc),
            edge="rising",
            initial_high=True,
        )
        if not len(init_rising_s):
            raise ValueError("SPICE ADC power measurement contains no SEQ_INIT rising edge")
        active_start_s = float(init_rising_s[0])
        active_stop_s = active_start_s + 1.0 / measurement.active_conversion_rate_hz
        if active_stop_s >= waveform_time_s[-1]:
            raise ValueError("SPICE ADC waveform does not contain one complete active conversion interval")
        spice_active = (active_start_s, active_stop_s)
        later_init_times_s = init_rising_s[init_rising_s > active_stop_s]
        idle_stop_s = float(later_init_times_s[0]) if len(later_init_times_s) else float(waveform_time_s[-1])
        idle_duration_s = idle_stop_s - active_stop_s
        if idle_duration_s <= 0.0:
            raise ValueError("SPICE ADC waveform contains no idle interval after its active conversion")
        # Exclude switching at the conversion boundary and any transition
        # into the next record. The relative guard also keeps compact test
        # records usable while production records receive a full 1 ns.
        idle_guard_s = min(1.0e-9, idle_duration_s / 10.0)
        spice_static_indices = np.flatnonzero(
            (waveform_time_s >= active_stop_s + idle_guard_s) & (waveform_time_s <= idle_stop_s - idle_guard_s)
        )
        if len(spice_static_indices) < 2:
            raise ValueError("SPICE ADC power measurement requires at least two settled-idle samples")
    static_w = []
    active_w = []
    for rail in rail_names:
        if wave is not None:
            assert spice_active is not None
            current_a, time_s = calc.clip(wave.i[rail][0], wave.time_s, *spice_active)
            active_power_w = float(getattr(tb, rail).dc) * calc.average(current_a, time_s)
        else:
            active_power_key = f"{rail}_active_average_power_w"
            if active_power_key not in readbacks:
                raise ValueError(f"ADC measurement is missing active-power readbacks for {rail}")
            active_power_w = float(readbacks[active_power_key])

        static_power_key = f"{rail}_static_average_power_w"
        if static_power_key in readbacks:
            static_power_w = float(readbacks[static_power_key])
        elif wave is not None:
            assert spice_static_indices is not None
            baseline_time_s = wave.time_s[spice_static_indices]
            baseline_current_a = wave.i[rail][0, spice_static_indices]
            static_power_w = float(getattr(tb, rail).dc) * calc.average(baseline_current_a, baseline_time_s)
        else:
            voltage_key = f"{rail}_measured_voltage_v"
            current_key = f"{rail}_measured_current_a"
            if voltage_key not in readbacks or current_key not in readbacks:
                raise ValueError(f"ADC measurement is missing static-power readbacks for {rail}")
            static_power_w = abs(float(readbacks[voltage_key]) * float(readbacks[current_key]))
        # Independent slow SMU averages can differ by a few nanowatts. Cap a
        # baseline at its active reading rather than reporting negative added
        # dynamic power from measurement noise.
        static_w.append(min(static_power_w, active_power_w))
        active_w.append(active_power_w)
    identity = measurement.identity
    return AnalysisAdcPower(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        sample_rate_hz=measurement.sample_rate_hz,
        active_conversion_rate_hz=measurement.active_conversion_rate_hz,
        vdd_a_static_power_w=static_w[0],
        vdd_d_static_power_w=static_w[1],
        vdd_dac_static_power_w=static_w[2],
        vdd_a_dynamic_power_w=active_w[0] - static_w[0],
        vdd_d_dynamic_power_w=active_w[1] - static_w[1],
        vdd_dac_dynamic_power_w=active_w[2] - static_w[2],
    )


def analyze_adc_power_waveform(measurement: MeasAdc, *, power: AnalysisAdcPower) -> AnalysisAdcPowerWaveform:
    """Select and align one simulated conversion for detailed power plotting.

    ``power`` supplies the static and active rail averages of the same capture.
    """

    check_identity(power, measurement.identity, name="power")
    static_w = (power.vdd_a_static_power_w, power.vdd_d_static_power_w, power.vdd_dac_static_power_w)
    active_w = (
        power.vdd_a_static_power_w + power.vdd_a_dynamic_power_w,
        power.vdd_d_static_power_w + power.vdd_d_dynamic_power_w,
        power.vdd_dac_static_power_w + power.vdd_dac_dynamic_power_w,
    )
    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    time_s = wave.time_s
    threshold_v = 0.5 * float(measurement.tb.vdd_d.dc)
    active_start_s = calc.cross(
        wave.v[AdcNets.seq_init.name][0],
        time_s,
        threshold_v,
        edge="rising",
        initial_high=True,
        occurrence=1,
    )
    if not math.isfinite(active_start_s):
        raise ValueError("ADC power waveform contains no SEQ_INIT rising edge")
    active_duration_s = 1.0 / measurement.active_conversion_rate_hz
    active_stop_s = active_start_s + active_duration_s
    # Show 2% of the conversion either side of it for context.
    margin_s = 0.02 * active_duration_s
    displayed = (time_s >= active_start_s - margin_s) & (time_s <= active_stop_s + margin_s)
    if np.count_nonzero(displayed) < 2:
        raise ValueError("ADC power waveform contains fewer than two displayed samples")

    rail_power_w = [
        wave.i[rail][0][displayed] * float(getattr(measurement.tb, rail).dc) for rail in ("vdd_a", "vdd_d", "vdd_dac")
    ]
    identity = measurement.identity
    return AnalysisAdcPowerWaveform(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        active_conversion_rate_hz=measurement.active_conversion_rate_hz,
        time_s=time_s[displayed] - active_start_s,
        rail_power_w=np.asarray(rail_power_w),
        static_power_w=np.asarray(static_w),
        active_power_w=np.asarray(active_w),
        timing_high=np.asarray(
            [
                values[0, displayed] > threshold_v
                for values in (
                    wave.v[AdcNets.seq_init.name],
                    wave.v[AdcNets.seq_samp.name],
                    wave.v[AdcNets.seq_comp.name],
                    wave.v[AdcNets.seq_logic.name],
                )
            ],
            dtype=np.bool_,
        ),
    )


# =============================================================================
# Comparator response and timing closure
# =============================================================================


def analyze_adc_comparator_edge_eye(measurement: MeasAdc) -> AnalysisAdcComparatorEdgeEye:
    """Align every saved conversion at its B0 COMP rise and fold it at every decision.

    The three traces are the comparator clock, the positive SR-latch output,
    and the XC-latch magnitude ``|P-N|``. Aligned records span from 0.2
    decision periods before B0 to one period after the final decision; folded
    windows span -0.1..1.1 periods around each COMP rise. Both are resampled at
    the saved waveform spacing, with NaN outside a record.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    required = {"seq_init", "clk_comp", "comp.latch_p", "comp.latch_n", "comp_out_p"}
    if missing := required - wave.v.keys():
        raise ValueError(f"ADC edge eye requires saved canonical nets: {sorted(missing)}")
    time = wave.time_s
    threshold = float(measurement.tb.vdd_d.dc) / 2
    decisions = len(measurement.nominal_bout_weights)
    traces = (
        wave.v["clk_comp"],
        wave.v["comp_out_p"],
        np.abs(wave.v["comp.latch_p"] - wave.v["comp.latch_n"]),
    )
    record_edges = []
    for record in range(len(wave.record_index)):
        init_edges = calc.cross(wave.v["seq_init"][record], time, threshold, edge="rising", initial_high=True)
        if not len(init_edges):
            raise ValueError(f"conversion {record} has no INIT rise")
        stop = init_edges[1] if len(init_edges) > 1 else time[-1]
        clock_edges = calc.cross(wave.v["clk_comp"][record], time, threshold, edge="rising")
        clock_edges = clock_edges[(clock_edges >= init_edges[0]) & (clock_edges < stop)]
        if len(clock_edges) != decisions:
            raise ValueError(f"conversion {record} has {len(clock_edges)} COMP rises; expected {decisions}")
        record_edges.append(clock_edges)
    record_edges = np.asarray(record_edges)
    period_s = float(np.median(np.diff(record_edges, axis=1)))
    decision_edge_s = np.median(record_edges - record_edges[:, :1], axis=0)
    sample_interval_s = float(np.median(np.diff(time)))
    aligned_time_s = np.arange(-0.2 * period_s, decision_edge_s[-1] + period_s, sample_interval_s)
    eye_phase = np.arange(-0.1, 1.1, sample_interval_s / period_s)
    identity = measurement.identity
    return AnalysisAdcComparatorEdgeEye(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        decision_period_s=period_s,
        decision_edge_s=decision_edge_s,
        supply_v=max(float(measurement.tb.vdd_a.dc), float(measurement.tb.vdd_d.dc)),
        aligned_time_s=aligned_time_s,
        aligned_v=np.asarray(
            [
                [
                    np.interp(edges[0] + aligned_time_s, time, row, left=np.nan, right=np.nan)
                    for row, edges in zip(values, record_edges, strict=True)
                ]
                for values in traces
            ]
        ),
        eye_phase=eye_phase,
        eye_v=np.asarray(
            [
                [
                    np.interp(edge + eye_phase * period_s, time, row, left=np.nan, right=np.nan)
                    for row, edges in zip(values, record_edges, strict=True)
                    for edge in edges
                ]
                for values in traces
            ]
        ),
    )


def analyze_adc_comparator_response(measurement: MeasAdc) -> AnalysisAdcComparatorResponse:
    """Measure midpoint-valid XC and single-ended SR timing after COMP rise.

    One XC node must fall below 50% of VDD and the other remain above 50%
    before COMP reset. The positive buffered SR output must enter the matching
    half-rail band before the next COMP rise. Both must remain valid through
    the end of their windows. Already-held SR states are counted separately.
    """

    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    required = {"seq_init", "seq_logic", "clk_comp", "comp.latch_p", "comp.latch_n", "comp_out_p"}
    if missing := required - wave.v.keys():
        raise ValueError(f"ADC comparator response requires saved canonical nets: {sorted(missing)}")
    time = wave.time_s
    analog_supply = float(measurement.tb.vdd_a.dc)
    digital_supply = float(measurement.tb.vdd_d.dc)
    decisions = len(measurement.nominal_bout_weights)
    rows = []
    for record, conversion in enumerate(wave.record_index):
        signals = {name: values[record] for name, values in wave.v.items() if name in required}
        # One conversion starts at the record's INIT rise and holds one COMP rise per decision.
        init_edges = calc.cross(signals["seq_init"], time, digital_supply / 2, edge="rising", initial_high=True)
        comp_edges = calc.cross(signals["clk_comp"], time, digital_supply / 2, edge="rising")
        if not len(init_edges):
            raise ValueError(f"record {record} has no INIT rise")
        stop = init_edges[1] if len(init_edges) > 1 else time[-1]
        comp_indices = np.flatnonzero((comp_edges >= init_edges[0]) & (comp_edges < stop))
        if len(comp_indices) != decisions:
            raise ValueError(f"record {record} has {len(comp_indices)} COMP rises; expected {decisions}")
        following = np.r_[comp_edges, np.nan][comp_indices + 1]
        resets = calc.cross(signals["clk_comp"], time, digital_supply / 2, edge="falling")
        latch_p, latch_n = signals["comp.latch_p"], signals["comp.latch_n"]
        sr_p = signals["comp_out_p"]
        for decision, (start, next_comp) in enumerate(zip(comp_edges[comp_indices], following, strict=True)):
            stop = next_comp if np.isfinite(next_comp) else time[-1]
            reset_edges = resets[(resets > start) & (resets < stop)]
            reset = float(reset_edges[0]) if len(reset_edges) == 1 else math.nan
            evaluation = (time >= start) & (time < reset)
            internal_delay = math.nan
            sr_delay = math.nan
            held = False
            if np.any(evaluation):
                last = np.flatnonzero(evaluation)[-1]
                final_p = float(latch_p[last])
                final_n = float(latch_n[last])
                midpoint = 0.5 * analog_supply
                if final_p != final_n:
                    target = 1 if final_p > final_n else -1
                    high, low = (latch_p, latch_n) if target > 0 else (latch_n, latch_p)
                    valid = (high[evaluation] >= midpoint) & (low[evaluation] <= midpoint)
                    stable = calc.settlingTime(valid, time[evaluation])
                    if np.isfinite(stable):
                        internal_delay = max(0.0, stable - start)
                    # Time the observed SR state even if the XC pair did not
                    # settle across the midpoint before COMP reset.
                    output = (time >= start) & (time < stop)
                    valid = sr_p[output] >= midpoint if target > 0 else sr_p[output] <= midpoint
                    stable = calc.settlingTime(valid, time[output])
                    if np.isfinite(stable):
                        held = bool(np.all(valid))
                        if not held:
                            sr_delay = max(0.0, stable - start)
            rows.append((int(conversion), decision, internal_delay, sr_delay, held))
    identity = measurement.identity
    return AnalysisAdcComparatorResponse(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        conversion_index=np.asarray([row[0] for row in rows]),
        decision_index=np.asarray([row[1] for row in rows]),
        internal_response_s=np.asarray([row[2] for row in rows]),
        sr_response_s=np.asarray([row[3] for row in rows]),
        sr_held=np.asarray([row[4] for row in rows]),
        sample_interval_s=float(calc.ymax(np.diff(time))),
        conversion_rate_hz=measurement.active_conversion_rate_hz,
    )


def analyze_adc_timing_closure(measurement: MeasAdc) -> AnalysisAdcTimingClosure:
    """Check internal resolution -> held SR decision -> SAR/CDAC using /wave.

    Internal tendency is latch_p - latch_n just before the observed comparator
    reset. Resolution must persist until reset, and the correct rail-valid SR
    pair must persist through LOGIC. Repeated decisions need no SR transition.
    Every decision that switches a capacitor also requires the expected SAR
    state and driven bottom plates, plus top-plate settling, before the next
    observed comparator rise. Bottom-plate targets follow the programmed
    main/diff inversion; top-plate references are the final saved values
    before the next COMP, not a DC-accuracy guarantee. Only observed samples
    are used; this does not modify or re-decode DAQ codes.
    """

    # Setup margins of 200 ps cover the standard-cell flip-flop setup time
    # with clock-skew allowance; they are requirements of the logic library,
    # not of the converter architecture.
    required_logic_setup_s = 200e-12
    required_cdac_setup_s = 200e-12
    # The latch has resolved once its outputs differ by 0.3 V, a quarter of
    # the supply; the CDAC has settled within 1 mV, below one reference LSB.
    internal_differential_v = 0.3
    cdac_tolerance_v = 1e-3
    wave, params = measurement.wave, measurement.tb
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    time = wave.time_s
    analog_supply = float(params.vdd_a.dc)
    digital_supply = float(params.vdd_d.dc)
    dac_supply = float(params.vdd_dac.dc)
    capacitors = len(measurement.nominal_bout_weights) - 1
    buses = (
        AdcNets.dac_state_p,
        AdcNets.dac_state_n,
        AdcNets.dac_state_p_diff,
        AdcNets.dac_state_n_diff,
        AdcNets.dac_botplate_p,
        AdcNets.dac_botplate_n,
        AdcNets.dac_botplate_p_diff,
        AdcNets.dac_botplate_n_diff,
    )
    required = (
        {
            net.name
            for net in (
                AdcNets.seq_init,
                AdcNets.seq_logic,
                AdcNets.clk_comp,
                AdcNets.comp_out_p,
                AdcNets.comp_out_n,
                AdcNets.vdac_p,
                AdcNets.vdac_n,
            )
        }
        | {f"comp.{net.name}" for net in (CompNets.latch_p, CompNets.latch_n)}
        | {f"{net.name}[{stage}]" for net in buses for stage in range(capacitors)}
    )
    if missing := required - wave.v.keys():
        raise ValueError(f"ADC timing analysis requires saved canonical nets: {sorted(missing)}")
    rows = []
    for record, conversion in enumerate(wave.record_index):
        signals = {name: values[record] for name, values in wave.v.items()}
        # One conversion starts at the record's INIT rise and holds one COMP rise per decision.
        threshold_v = digital_supply / 2
        init_edges = calc.cross(signals[AdcNets.seq_init.name], time, threshold_v, edge="rising", initial_high=True)
        comp_edges = calc.cross(signals[AdcNets.clk_comp.name], time, threshold_v, edge="rising")
        logic_edges = calc.cross(signals[AdcNets.seq_logic.name], time, threshold_v, edge="rising", initial_high=True)
        if not len(init_edges):
            raise ValueError(f"record {record} has no INIT rise")
        conversion_stop = init_edges[1] if len(init_edges) > 1 else time[-1]
        comp_indices = np.flatnonzero((comp_edges >= init_edges[0]) & (comp_edges < conversion_stop))
        if len(comp_indices) != capacitors + 1:
            raise ValueError(f"record {record} has {len(comp_indices)} COMP rises; expected {capacitors + 1}")
        following = np.r_[comp_edges, np.nan][comp_indices + 1]
        # The unique LOGIC rise between a COMP rise and the next; NaN when missing or ambiguous.
        # The final decision's LOGIC observation belongs to the next INIT, before its B0.
        logic = []
        for decision, (start, next_comp) in enumerate(zip(comp_edges[comp_indices], following, strict=True)):
            updates = logic_edges[
                (logic_edges > start) & ((logic_edges < next_comp) if np.isfinite(next_comp) else True)
            ]
            when = updates[0] if len(updates) == 1 else math.nan
            if decision == capacitors and not conversion_stop <= when < (
                next_comp if np.isfinite(next_comp) else np.inf
            ):
                when = math.nan
            logic.append(when)
        resets = calc.cross(signals[AdcNets.clk_comp.name], time, threshold_v, edge="falling")
        internal = signals[f"comp.{CompNets.latch_p.name}"] - signals[f"comp.{CompNets.latch_n.name}"]
        sr_p, sr_n = signals[AdcNets.comp_out_p.name], signals[AdcNets.comp_out_n.name]
        for decision, (start, logic_time, next_comp) in enumerate(
            zip(comp_edges[comp_indices], logic, following, strict=True)
        ):
            stop = next_comp if np.isfinite(next_comp) else time[-1]
            reset_edges = resets[(resets > start) & (resets < stop)]
            reset = float(reset_edges[0]) if len(reset_edges) == 1 else math.nan
            evaluation = (time >= start) & (time < reset)
            final_diff = float(internal[evaluation][-1]) if np.any(evaluation) else math.nan
            target = 1 if final_diff > 0 else -1
            internal_stable = calc.settlingTime(
                target * internal[evaluation] >= internal_differential_v, time[evaluation]
            )
            high, low = (sr_p, sr_n) if target > 0 else (sr_n, sr_p)
            # Rail-valid logic levels: above 70% or below 30% of the supply.
            sr_valid = (high >= 0.7 * analog_supply) & (low <= 0.3 * analog_supply)
            # Include interpolated values at LOGIC: a transition straddling that
            # edge must not be certified from the preceding saved sample alone.
            before_logic = (time >= start) & (time < logic_time)
            sr_matches = bool(
                np.isfinite(final_diff)
                and final_diff != 0
                and np.isfinite(logic_time)
                and calc.value(high, time, logic_time) >= 0.7 * analog_supply
                and calc.value(low, time, logic_time) <= 0.3 * analog_supply
            )
            sr_stable = calc.settlingTime(
                np.r_[sr_valid[before_logic], sr_matches], np.r_[time[before_logic], logic_time]
            )
            cdac_stable = math.nan
            if decision < capacitors and np.isfinite(next_comp) and np.isfinite(logic_time):
                update = (time >= logic_time) & (time < next_comp)
                settled = np.ones(np.count_nonzero(update), dtype=bool)
                for net in (AdcNets.vdac_p, AdcNets.vdac_n):
                    values = signals[net.name][update]
                    if len(values):
                        settled &= np.abs(values - values[-1]) <= cdac_tolerance_v
                for side, positive in (("p", target < 0), ("n", target > 0)):
                    state = positive if params.dac_mode else getattr(params, f"dac_bstate_{side}")[decision]
                    for diff in (False, True):
                        suffix = "_diff" if diff else ""
                        state_net = getattr(AdcNets, f"dac_state_{side}{suffix}")
                        values = signals[f"{state_net.name}[{decision}]"][update]
                        settled &= values >= 0.7 * digital_supply if state else values <= 0.3 * digital_supply
                        bottom_net = getattr(AdcNets, f"dac_botplate_{side}{suffix}")
                        values = signals[f"{bottom_net.name}[{decision}]"][update]
                        bottom_target = (bool(state) ^ (diff and bool(params.dac_diffcaps))) * dac_supply
                        settled &= np.abs(values - bottom_target) <= cdac_tolerance_v
                cdac_stable = calc.settlingTime(settled, time[update])
            rows.append(
                (
                    int(conversion),
                    decision,
                    start,
                    reset,
                    logic_time,
                    next_comp,
                    final_diff,
                    internal_stable,
                    sr_stable,
                    sr_matches,
                    cdac_stable,
                )
            )
    identity = measurement.identity
    return AnalysisAdcTimingClosure(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        **{
            name: np.asarray(values)
            for name, values in zip(
                (
                    "conversion_index",
                    "decision_index",
                    "comp_rise_s",
                    "comp_reset_s",
                    "logic_rise_s",
                    "next_comp_s",
                    "internal_final_diff_v",
                    "internal_stable_s",
                    "sr_stable_s",
                    "sr_matches_at_logic",
                    "cdac_stable_s",
                ),
                zip(*rows, strict=True),
                strict=True,
            )
        },
        capacitor_count=capacitors,
        required_logic_setup_s=required_logic_setup_s,
        required_cdac_setup_s=required_cdac_setup_s,
        internal_differential_v=internal_differential_v,
        cdac_tolerance_v=cdac_tolerance_v,
        sample_interval_s=float(calc.ymax(np.diff(time))),
    )


def analyze_adc_timing_summary(
    measurement: MeasAdc,
    *,
    closure: AnalysisAdcTimingClosure,
) -> AnalysisAdcTimingSummary:
    """Summarize setup and comparator-reset margins of one simulated case."""

    check_identity(closure, measurement.identity, name="timing closure")
    if measurement.wave is None:
        raise ValueError("this analysis requires waveform records")
    if not np.array_equal(np.unique(closure.conversion_index), np.unique(measurement.wave.record_index)):
        raise ValueError("timing closure does not cover the measurement's waveform records")
    ordinary = closure.cdac_applicable
    reset_gap_s = closure.next_comp_s[ordinary] - closure.comp_reset_s[ordinary]
    observed_gap = np.isfinite(reset_gap_s) & (reset_gap_s > 0)
    internal_margin_s = closure.comp_reset_s - closure.internal_stable_s
    logic_setup_s = closure.logic_setup_s[np.isfinite(closure.logic_setup_s)]
    cdac_setup_s = closure.cdac_setup_s[ordinary]
    cdac_setup_s = cdac_setup_s[np.isfinite(cdac_setup_s)]
    identity: Identity = measurement.identity
    return AnalysisAdcTimingSummary(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        sequence=AdcSequence.from_tb_params(measurement.tb),
        symbol_rate_hz=float(measurement.tb.symbol_rate),
        decisions=len(closure.decision_index),
        cdac_decisions=int(np.count_nonzero(ordinary)),
        reset_edges_observed=int(np.count_nonzero(np.isfinite(closure.comp_reset_s))),
        ordinary_reset_gaps_observed=int(np.count_nonzero(observed_gap)),
        minimum_reset_gap_s=float(calc.ymin(reset_gap_s[observed_gap])) if np.any(observed_gap) else math.nan,
        resolved_before_reset=int(np.count_nonzero(np.isfinite(internal_margin_s) & (internal_margin_s >= 0))),
        sr_matches_at_logic=int(np.count_nonzero(closure.sr_matches_at_logic)),
        logic_ready=int(np.count_nonzero(closure.logic_ready)),
        cdac_ready=int(np.count_nonzero(closure.cdac_ready)),
        timing_passed=int(np.count_nonzero(closure.passed)),
        minimum_logic_setup_s=float(calc.ymin(logic_setup_s)) if len(logic_setup_s) else math.nan,
        minimum_cdac_setup_s=float(calc.ymin(cdac_setup_s)) if len(cdac_setup_s) else math.nan,
    )
