"""The ADC's analyses: pure functions of its captures (``MeasAdc``, physical, behavioral or SPICE;
``MeasCdac``) and of earlier results, no file I/O, each returning its own result
(``flow.adc.types``). Their sizes (decisions, capacitors, codes, symbols a decision) come from the
capture's parameters, never from literals.

- A capture's conversions: its static transfer, endpoint and code-density linearity, a repeated
  ramp's transfer and linearity (``analyze_ramp``), the codes at static inputs, a fixed input's
  noise and the noise's spectrum, an interferer unfolded from several rates, the plausible
  operating conditions over sequence and rate and their maps (``analyze_sequence_map``: one ADC's,
  or a chip's together), the sequence its testbench programs (``analyze_sequencer``), a sine's
  dynamic performance, the decision paths and the supply power. Where an analysis takes a calibration, its weights decode the stored decisions
  in place of the stored codes (``_decode``).
- A simulation's internal waveforms: the held voltages after sampling, the CDAC's settling, one
  conversion's rail power, and the timing closure of every decision with its summary.
- The calibrations, each decision's weight: from the CDAC's S-curves (``analyze_calibration1``), a
  least-squares fit to a known ramp (``analyze_calibration2``) and Hsu's slow-ramp thresholds
  (``analyze_calibration3``).
- The campaign's studies: the output code's noise over the input (``analyze_input_noise``) and at a
  fixed input (``analyze_noise_rms``), Hsu's integrated error over the rate (``analyze_hsu``), the
  ENOB ladder (``analyze_ladder``), the energy over the input (``analyze_energy``) and the
  redundancy of a calibration's weights (``analyze_redundancy``); and the record's numbers
  (``metrics``).
- An array's capacitor mismatch: ``analyze_mismatch`` takes a behavioral capture to its array's
  mismatch as statistics rather than draws (``AnalysisMismatch``), from which ``_dnl_quantile``,
  ``_inl_quantile``, ``_missing_codes_quantile`` and ``_margin_over_sigma`` predict at a Pelgrom
  coefficient (``analyze_mismatch_prediction``: at Harpe's matching and over the coefficients the
  figures draw), and which drawn arrays check (``analyze_mismatch_draws``); the redundancy of a
  SAR's weights (``_redundancy_margins``, after Ogawa et al.) grades each stage's error tolerance.

Capacitor mismatch as statistics rather than draws: what a Pelgrom coefficient costs a capacitor
array's DNL, INL and codes, from its capacitances alone, to first order in the mismatch.

The converter samples on its top plates and switches monotonically. Decision k (k = 0 to n, the
first free) compares the input with the reference R_k; above it the n side's capacitor k rises and
the reference moves up by b_k, below it the p side's does and the reference moves down by a_k::

    R_0 = 0,  R_{k+1} = R_k + d_k b_k - (1 - d_k) a_k

A side's step is its capacitor's share of that side's load, a_k = V c_k / C_p, with c_k = main_k -
diff_k (the difference plate moves the other way; main_k + diff_k where it moves with the main
plate) and C_p every plate of the side and the top plate's other load. The LSB is
2 V sum(c) / C / 2^bits, so in LSB the step is s_k = c_k 2^bits / (2 sum(c)): the load cancels
from the nominal steps and only scales a side's gain.

Pelgrom's mismatch draws every plate independently, sigma_C = A sqrt(C 1 fF)
(``capdac.Model.draw``), so a side's step k varies by

    sigma_k = A sqrt((main_k + diff_k) 1 fF) 2^bits / (2 sum(c))   [LSB]

(both plates add their variance, whichever way they move) and the side's load C_p by the sum of
all of them, a gain common to the side's steps: a capacitor drawn large also loads its side more,
which takes back the share c_k / C_p of its own error from every step of that side. The code-level
statistics below keep that term; it lowers a binary array's MSB transition sigma by about a
fifth where the switched capacitance is a third of the load.

**Transitions and widths.** Every code edge is one comparator's threshold, R_k with the decisions
before it, T = sum_{j<k} (d_j b_j - (1 - d_j) a_j). A code's width (the input that converts to it,
what the ramp's code density measures) is, on each decision path ending on it, its upper threshold
less its lower. Two thresholds on one path at decisions k < m differ by the steps between them,

    w = sum_{k <= j < m} (d_j b_j - (1 - d_j) a_j),   sigma_w^2 = sum_{k <= j < m} sigma_j^2,

each step from the side its decision switched. In a binary array the code just above stage k's
transition ends at the last comparison, so sigma^2 = sigma_k^2 + sum_{j>k} sigma_j^2 over the
capacitors (b_k against the a_j after it; the code just below, a_k against the b_j); in a redundant
one the path after a transition need not run to the last comparison, so the next edge can come at
any later decision and the sum stops there, and a code can hold several paths whose widths add.
Rather than assume which, ``analyze_mismatch`` walks every decision path of the nominal array
(``calc_paths``: each comparator splits the input interval a path still holds at its threshold)
and takes each code's width as the sum of its paths', linear in every plate's error. A stage's
transition sigma is the largest of the codes whose width starts at its decision.

**Redundancy margin.** Stage k tolerates a wrong decision within q_k (Ogawa et al.,
``_redundancy_margins``): a wrong 1 there takes b_k, and the 0s after it give back
sum_{j>k} a_j, so q_k moves with exactly those steps' errors. Its sigma is theirs, and q_k / sigma
says how many sigma of mismatch would close the margin (a negative margin is a gap: missing codes).

**DNL and INL.** The code density's DNL is w_c / mean(w) - 1 over the codes between the clipped
ends, and its INL the endpoint-corrected sum (``calc.dnl``, ``calc.inl``); both are linear in the
widths, so to first order each code's DNL and INL are Gaussian, the nominal array's value (an
extraction's own error against the design weights) plus a sum of the plates' errors, with a
variance from the plates' Pelgrom variances. All of them scale with A.

**The worst DNL.** Codes whose widths sum the same steps from the same sides are one random
variable (every last-stage code of a binary array, say), so the worst |DNL| is a maximum over the
distinct widths, not over the codes. Its percentile is the independent maximum over them,
P(max <= x) = prod_g P(|DNL_g| <= x): by Sidak's inequality the true probability is at least that
for centred Gaussians, so the predicted percentile is an upper bound there. A DNL is never under
-1 (a code narrower than none is missing, not negative), so past 1 LSB only the wide side counts.

**The worst INL.** The per-code sigma says little about the worst code: the INL is a sum of
the stages' errors, and some code takes each with the sign that adds. A threshold is
T_c = sum_j d_j(c) gamma_j + (the steps after its own stage), gamma_j = a_j + b_j the stage's step
on both sides, which every code whose path decided 1 at j carries; the decoder expects W_j there.
The endpoint fit takes off the gain: e_j = gamma_j - W_j - W_j sum(gamma - W) / sum(W). As d_j is
0 or 1, max_c sum_j d_j e_j <= sum_j max(e_j, 0) and the minimum >= sum_j min(e_j, 0), with
equality where the codes take every decision pattern (a binary array); the full-scale code
decides 1 everywhere, so sum_j e_j = 0 and the worst |INL| is half of sum_j |e_j|. Each e_j is the
nominal array's own error (an extraction's) plus a Gaussian draw, so with the e_j taken
independent that is a sum of folded normals, whose percentile is a numerical convolution. A
redundant array's codes do not take every pattern, and its decoder rounds between output codes,
so half the nominal errors' sum differs from its nominal worst INL; the prediction is shifted by
that difference, to the nominal INL at A = 0.

**Missing codes.** A code is missing when its width is not positive, P = Phi(-w / sigma_w); the
codes of one distinct width go together, so the count is a sum of independent Bernoulli groups,
whose distribution is again a convolution.

Everything is first order in the mismatch, and checked against exact draws of the same paths
(``calc_drawn_linearity``; ``test_analysis``): on the extracted 10- to 14-bit arrays the worst
DNL and INL agree within about 5 % to 0.2 %·sqrt(fF) and the INL within about 10 % to 0.85 %. A
redundant array's worst DNL is overstated past about 0.4 %·sqrt(fF): its near-coincident
thresholds (different paths' a fraction of an LSB apart) then reorder, and a code's edge becomes
the nearer of several thresholds, which the one-threshold Gaussian lets move freely.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from functools import partial
from itertools import takewhile

import hdl21 as h
import numpy as np
from scipy.optimize import lsq_linear, minimize, minimize_scalar
from scipy.special import erfc, log_ndtr, ndtr

from flow import capdac, comp
from flow.analysis import calc
from flow.analysis.calc import calc_paths
from flow.analysis.types import MeasAdc, MeasCdac
from flow.pipeline import Identity, analysis, check_identity, measurement_identity

from .params import CDAC_SETTLING_TOLERANCE_V, LADDER, NOMINAL_RATE_HZ, PELGROM_AXIS, UNIT_MISMATCH
from .sim import AdcSequence
from .subckt import AdcNets, calc_side_capacitances
from .types import (
    AnalysisCalibration,
    AnalysisCalibration1,
    AnalysisCalibration2,
    AnalysisCalibration3,
    AnalysisCdacSettling,
    AnalysisCodeDensityNonlinearity,
    AnalysisCodeDistribution,
    AnalysisCodeSpectrum,
    AnalysisDecisionPaths,
    AnalysisDynamic,
    AnalysisEndpointNonlinearity,
    AnalysisEnergy,
    AnalysisHsu,
    AnalysisInputNoise,
    AnalysisInterferer,
    AnalysisLadder,
    AnalysisMismatch,
    AnalysisMismatchDraws,
    AnalysisMismatchPrediction,
    AnalysisNoise,
    AnalysisNoiseRms,
    AnalysisOperatingConditions,
    AnalysisPower,
    AnalysisPowerWaveform,
    AnalysisRamp,
    AnalysisRedundancy,
    AnalysisSamplingNoise,
    AnalysisSequenceMap,
    AnalysisSequencer,
    AnalysisTimingClosure,
    AnalysisTimingSummary,
    AnalysisTransfer,
)

# =============================================================================
# Static and dynamic conversion analyses
# =============================================================================


@analysis
def analyze_dynamic(measurement: MeasAdc, *, calibration: AnalysisCalibration | None = None) -> AnalysisDynamic:
    """Fit one sine acquisition and calculate time- and frequency-domain metrics.

    A calibration decodes the stored BOUT decisions to fractional codes in
    place of the stored nominal DOUT. They are not rounded: whole codes would
    quantize the converter's output a second time and cost about 0.5 bit. To
    grade whole N-bit codes, as an output word would carry them, analyze the
    measurement with its DOUT replaced by ``_decode(bout, calibration)``.
    """

    source = measurement.tb.vin_diff
    if not isinstance(source, h.Vsin.Params) or source.freq is None or source.vamp is None:
        raise ValueError("ADC dynamic analysis requires a sine vin_diff source with freq and vamp set")
    if calibration is not None:
        check_identity(calibration, measurement.identity, name="calibration")
    measured_dout = np.asarray(
        measurement.dout if calibration is None else _decode(measurement.bout, calibration, rounded=False),
        dtype=np.float64,
    )
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
    return AnalysisDynamic(
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


@analysis
def analyze_transfer(
    measurements: Sequence[MeasAdc],
    *,
    calibration: AnalysisCalibration | None = None,
) -> AnalysisTransfer:
    """Pool conversions by input and calculate transfer statistics.

    With a calibration, DOUT is decoded transiently from the stored BOUT.
    """

    identity = measurement_identity(measurements)
    if calibration is not None:
        check_identity(calibration, identity, name="calibration")
    inputs = np.concatenate([measurement.vin_diff_v for measurement in measurements])
    dout = np.concatenate(
        [
            measurement.dout if calibration is None else _decode(measurement.bout, calibration)
            for measurement in measurements
        ]
    ).astype(np.float64)
    if not len(dout):
        raise ValueError("ADC transfer analysis requires at least one conversion")
    unique_inputs, inverse = np.unique(inputs, return_inverse=True)
    return AnalysisTransfer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_diff_v=unique_inputs,
        mean_dout=np.asarray([calc.average(dout[inverse == index]) for index in range(len(unique_inputs))]),
        std_dout=np.asarray([calc.stddev(dout[inverse == index]) for index in range(len(unique_inputs))]),
        sample_count=np.bincount(inverse, minlength=len(unique_inputs)).astype(np.int64),
    )


@analysis
def analyze_endpoint_nonlinearity(
    measurement: MeasAdc,
    *,
    calibration: AnalysisCalibration | None = None,
) -> AnalysisEndpointNonlinearity:
    """Calculate endpoint INL and DNL from code transitions of a stepped input."""

    if calibration is not None:
        check_identity(calibration, measurement.identity, name="calibration")
    decoded_dout = np.asarray(
        measurement.dout if calibration is None else _decode(measurement.bout, calibration),
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
    return AnalysisEndpointNonlinearity(
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


@analysis
def analyze_code_density_nonlinearity(
    measurement: MeasAdc,
    *,
    ramp: AnalysisRamp | None = None,
    calibration: AnalysisCalibration | None = None,
) -> AnalysisCodeDensityNonlinearity:
    """Calculate code-density INL and DNL from a uniformly distributed input.

    With a ramp result, only its ``retained`` conversions (away from each
    wrap) are counted. The first and last codes are excluded because a finite
    ramp clips into them.
    """

    if calibration is not None:
        check_identity(calibration, measurement.identity, name="calibration")
    decoded_dout = measurement.dout if calibration is None else _decode(measurement.bout, calibration)
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
    return AnalysisCodeDensityNonlinearity(
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


@analysis
def analyze_ramp(
    measurement: MeasAdc,
    *,
    calibration: AnalysisCalibration | None = None,
) -> AnalysisRamp:
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
    decoded = nominal_decoded if calibration is None else _decode(measurement.bout, calibration)
    counts = np.bincount(decoded[retained], minlength=number_codes).astype(np.int64)
    # Clipped end codes stay in the histogram but not in linearity.
    active_counts = counts[1:code_max]
    ideal_count = calc.average(active_counts)
    dnl = calc.dnl(active_counts, ideal_count=ideal_count)
    transfer_sum = np.bincount(transfer_bin[retained], weights=decoded[retained], minlength=number_codes)
    return AnalysisRamp(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        decoding="uncalibrated_dout" if calibration is None else calibration.method,
        label="Ideal weights" if calibration is None else calibration.label,
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


@analysis
def analyze_code_distribution(
    measurements: Sequence[MeasAdc],
    *,
    calibration: AnalysisCalibration | None = None,
) -> AnalysisCodeDistribution:
    """Pool conversions by input and histogram their output codes."""

    identity = measurement_identity(measurements)
    if calibration is not None:
        check_identity(calibration, identity, name="calibration")
    inputs = np.concatenate([measurement.vin_diff_v for measurement in measurements])
    dout = np.concatenate(
        [
            measurement.dout if calibration is None else _decode(measurement.bout, calibration)
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
    return AnalysisCodeDistribution(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_diff_v=unique_inputs,
        code=np.arange(number_codes, dtype=np.int64),
        count=count,
    )


@analysis
def analyze_noise(measurement: MeasAdc) -> AnalysisNoise:
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
    return AnalysisNoise(
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


@analysis
def analyze_code_spectrum(
    measurement: MeasAdc,
    *,
    calibration: AnalysisCalibration | None = None,
) -> AnalysisCodeSpectrum:
    """Treat one fixed-input capture's output codes as a waveform sampled at the conversion rate.

    The Welch density of the mean-free codes separates periodic interference,
    which appears as lines (aliased into the first Nyquist zone), from the
    broadband floor of comparator, input, and quantization noise. A
    calibration decodes the stored BOUT decisions to fractional codes in place
    of the stored DOUT.
    """

    if calibration is not None:
        check_identity(calibration, measurement.identity, name="calibration")
    codes = np.asarray(
        measurement.dout if calibration is None else _decode(measurement.bout, calibration, rounded=False),
        dtype=np.float64,
    )
    if len(codes) < 4:
        raise ValueError("a code spectrum needs at least four conversions")
    mean_dout = calc.average(codes)
    centered = codes - mean_dout
    # 8192-conversion Hann segments: 244-Hz bins at 2 MSPS, enough to resolve a
    # line that wanders by a few kHz, with tens of averages per 100,000 codes.
    segment = min(len(codes), 8192)
    frequency_hz, psd = calc.psd(centered, sample_rate=measurement.sample_rate_hz, segment_length=segment)
    # The median ignores the few bins that interference lines occupy.
    floor = float(np.median(psd[1:]))
    # A white floor averaged over K half-overlapping segments scatters by about
    # 1/sqrt(K); ten times that above the floor is a line, not a fluctuation.
    # A wandering line spreads into a low hump, so the density smoothed over
    # 21 bins, which scatters sqrt(21) times less, is tested the same way.
    averages = max(1, 2 * len(codes) // segment - 1)
    smoothed = np.convolve(psd, np.ones(21) / 21.0, mode="same")
    line_mask = (
        (
            (psd > floor * (1.0 + 10.0 / math.sqrt(averages)))
            | (smoothed > floor * (1.0 + 10.0 / math.sqrt(21.0 * averages)))
        )
        & (frequency_hz > 0.0)
        & (floor > 0.0)
    )
    # Keep only the line frequencies of the whole record for its narrowband part.
    record_hz = np.fft.rfftfreq(len(codes), 1.0 / measurement.sample_rate_hz)
    keep = line_mask[np.clip(np.rint(record_hz / frequency_hz[1]).astype(np.int64), 0, len(psd) - 1)]
    narrowband = np.fft.irfft(np.where(keep, np.fft.rfft(centered), 0.0), len(codes))
    identity = measurement.identity
    return AnalysisCodeSpectrum(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        sequence=AdcSequence.from_tb_params(measurement.tb),
        symbol_rate_hz=float(measurement.tb.symbol_rate),
        decoding="uncalibrated_dout" if calibration is None else calibration.method,
        sample_rate_hz=measurement.sample_rate_hz,
        input_lsb_v=measurement.input_lsb_v,
        mean_dout=mean_dout,
        frequency_hz=frequency_hz,
        psd_lsb2_per_hz=psd,
        white_floor_lsb2_per_hz=floor,
        line_mask=line_mask,
        narrowband_dout=narrowband,
    )


@analysis
def analyze_interferer(
    measurements: Sequence[MeasAdc],
    *,
    spectra: Sequence[AnalysisCodeSpectrum],
) -> AnalysisInterferer:
    """Unfold one interferer's aliases at several conversion rates to its true frequency.

    Every candidate frequency is folded into each rate's first Nyquist zone
    and scored by the code spectra there, relative to their floors. Two rates
    or more are needed for the aliases to single out a candidate.
    """

    identity = measurement_identity(measurements)
    check_identity(spectra, identity, name="spectra")
    if sorted((m.sample_rate_hz, repr(AdcSequence.from_tb_params(m.tb))) for m in measurements) != sorted(
        (s.sample_rate_hz, repr(s.sequence)) for s in spectra
    ):
        raise ValueError("spectra must match the measurements' sequences and rates one to one")
    valid = [spectrum for spectrum in spectra if spectrum.spectrum_valid]
    if not valid:
        raise ValueError("interferer search needs at least one capture with a noise floor")
    rates = np.unique([spectrum.sample_rate_hz for spectrum in valid])
    # Aliases at all rates repeat with the rates' common period and mirror about
    # its half; when the rates share no short period, search ten times the
    # highest rate. The step matches the finest spectral bin.
    common_hz = math.lcm(*(round(rate) for rate in rates))
    span_hz = min(common_hz / 2.0, 10.0 * float(rates[-1]))
    step_hz = min(float(spectrum.frequency_hz[1]) for spectrum in valid)
    candidate_hz = np.arange(0.0, span_hz + step_hz, step_hz)
    score_db = np.zeros_like(candidate_hz)
    observed_hz = []
    for rate in rates:
        at_rate = [spectrum for spectrum in valid if spectrum.sample_rate_hz == rate]
        folded_hz = np.abs((candidate_hz + rate / 2.0) % rate - rate / 2.0)
        score_db += np.mean(
            [
                10.0
                * np.log10(
                    np.maximum(np.interp(folded_hz, spectrum.frequency_hz, spectrum.psd_lsb2_per_hz), 1e-30)
                    / spectrum.white_floor_lsb2_per_hz
                )
                for spectrum in at_rate
            ],
            axis=0,
        )
        observed_hz.append(float(np.median([spectrum.peak_frequency_hz for spectrum in at_rate])))
    return AnalysisInterferer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        sample_rate_hz=rates,
        observed_peak_hz=np.asarray(observed_hz),
        candidate_frequency_hz=candidate_hz,
        score_db=score_db,
        excluded_capture_count=len(spectra) - len(valid),
    )


@analysis
def analyze_operating_conditions(
    measurements: Sequence[MeasAdc],
    *,
    noise: Sequence[AnalysisNoise],
) -> AnalysisOperatingConditions:
    """Judge which sequence and symbol-rate settings of one ADC give plausible codes.

    Each measurement is matched to the noise result with the same sequence
    and symbol rate. The reference code is the median mean code over every
    sequence at the lowest symbol rate, where timing is most relaxed.
    """

    identity = measurement_identity(measurements)
    check_identity(noise, identity, name="noise")
    by_coordinates: dict[tuple[AdcSequence, float], AnalysisNoise] = {}
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
    return AnalysisOperatingConditions(
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


@analysis
def analyze_sequence_map(conditions: Sequence[AnalysisOperatingConditions]) -> AnalysisSequenceMap:
    """One ADC's operating conditions, or a chip's ADCs' (each ``analyze_operating_conditions``), as
    maps over sequence and symbol rate (``AnalysisSequenceMap``): a cell's ENOB is the median of the
    plausible ADCs' where at least three quarters of the ADCs are plausible there."""

    if not conditions:
        raise ValueError("a sequence map needs the operating conditions of at least one ADC")
    sequences = tuple(dict.fromkeys(sequence for result in conditions for sequence in result.sequence))
    rates = np.unique(np.concatenate([np.asarray(result.symbol_rate_hz, dtype=np.float64) for result in conditions]))
    column = {sequence: index for index, sequence in enumerate(sequences)}
    shape = (len(conditions), len(rates), len(sequences))
    enob, shift = np.full(shape, np.nan), np.full(shape, np.nan)
    plausible, measured = np.zeros(shape, dtype=np.bool_), np.zeros(shape, dtype=np.bool_)
    for adc, result in enumerate(conditions):
        for row, (sequence, rate) in enumerate(zip(result.sequence, result.symbol_rate_hz, strict=True)):
            cell = (adc, int(np.searchsorted(rates, rate)), column[sequence])
            enob[cell], shift[cell] = result.enob_bits[row], abs(result.mean_shift_dout[row])
            plausible[cell], measured[cell] = result.plausible[row], True
    least = math.ceil(0.75 * len(conditions))
    enob_bits, shift_dout = np.full(shape[1:], np.nan), np.full(shape[1:], np.nan)
    for row, col in np.ndindex(*shape[1:]):
        good = enob[plausible[:, row, col], row, col]
        if len(good) >= least:
            enob_bits[row, col] = float(np.median(good))
        if measured[:, row, col].any():
            shift_dout[row, col] = float(np.median(shift[measured[:, row, col], row, col]))
    identities = [result.identity for result in conditions]
    first = identities[0]
    return AnalysisSequenceMap(
        group=first.group if all(identity.group == first.group for identity in identities) else None,
        index=first.index if all(identity.index == first.index for identity in identities) else None,
        dut=first.dut if all(identity.dut == first.dut for identity in identities) else None,
        sequence=sequences,
        symbol_rate_hz=rates,
        adc_count=len(conditions),
        plausible_count=np.where(measured.any(axis=0), plausible.sum(axis=0), np.nan),
        enob_bits=enob_bits,
        shift_dout=shift_dout,
    )


@analysis
def analyze_sequencer(measurement: MeasAdc) -> AnalysisSequencer:
    """A capture's sequence as its testbench programs it (``AdcSequence``: the sequencer's four rows),
    from INIT's rise, as levels a symbol: the timing the capture ran, a physical one or a simulated
    one alike."""

    sequence = AdcSequence.from_tb_params(measurement.tb).relative_to_init()
    rows = (sequence.init, sequence.samp, sequence.comp, sequence.logic)
    identity = measurement.identity
    return AnalysisSequencer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        symbol_rate_hz=float(measurement.tb.symbol_rate),
        high=np.asarray([[bit == "1" for bit in row] for row in rows], dtype=np.bool_),
    )


@analysis
def analyze_conversions(measurement: MeasAdc) -> comp.AnalysisConversions:
    """A capture as its comparator sees it (``comp.AnalysisConversions``), which the comparator's
    analyses of a converter take (``comp.analyze_scope_edges``, ``comp.analyze_edge_eye``,
    ``comp.analyze_response``): its records, its decisions and the spacing its sequence programs for
    them, its sequence and symbol rate, its conversion rate without idle symbols and its supplies;
    a physical capture or a simulated one alike."""

    tb = measurement.tb
    symbol_rate_hz = float(tb.symbol_rate)
    try:
        decision_period_s = measurement.symbols_per_decision / symbol_rate_hz
    except ValueError:
        # clock rises not evenly spaced: a simulation's analyses time each from its records
        decision_period_s = math.nan
    identity = measurement.identity
    return comp.AnalysisConversions(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        wave=measurement.wave,
        sequence=(tb.seq_init_pattern, tb.seq_samp_pattern, tb.seq_comp_pattern, tb.seq_logic_pattern),
        symbol_rate_hz=symbol_rate_hz,
        decisions=len(measurement.nominal_bout_weights),
        decision_period_s=decision_period_s,
        conversion_rate_hz=measurement.active_conversion_rate_hz,
        vdd_a_v=float(tb.vdd_a.dc),
        vdd_d_v=float(tb.vdd_d.dc),
    )


@analysis
def analyze_switching(measurement: MeasCdac) -> capdac.AnalysisSwitching:
    """A capture of one point of a CDAC stage's switching curve as the CDAC sees it
    (``capdac.AnalysisSwitching``), which its lab analyses take (``capdac.analyze_decisions``,
    ``analyze_transition``, ``analyze_cap_mismatch``): the stage that switches and how, the trials
    (the common mode from the testbench where the DAQ did not record it), the reference, the array's
    stages and the design's expectation of each stage's effective fraction (the capture's,
    ``MeasCdac.expected_effective_fraction``), and the design of the comparator that decided."""

    params = measurement.param
    tb = measurement.tb
    stages = len(capdac.Model.weights(params.tb.dut.cdac))
    expected = np.asarray(measurement.expected_effective_fraction, dtype=np.float64)
    identity = measurement.identity
    return capdac.AnalysisSwitching(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        info=measurement.info,
        param=params,
        campaign=params.campaign,
        side=params.cdac_side,
        stage=params.cdac_element,
        direction=params.cdac_direction,
        diffcaps=int(params.tb.dac_diffcaps),
        trial_index=np.asarray(measurement.trial_index),
        vin_diff_v=np.asarray(measurement.vin_diff_v, dtype=np.float64),
        vin_cm_v=np.full(len(measurement.decision), float(tb.vin_cm.dc))
        if measurement.vin_cm_v is None
        else np.asarray(measurement.vin_cm_v, dtype=np.float64),
        decision=np.asarray(measurement.decision),
        vdd_dac_v=float(tb.vdd_dac.dc),
        stages=stages,
        # an array without weights of its own (a behavioral one) has no expectation: NaN a stage
        expected_fraction=np.broadcast_to(expected, (stages,)).copy(),
        comparator=params.tb.dut.comp,
    )


@analysis
def analyze_decision_paths(measurement: MeasAdc) -> AnalysisDecisionPaths:
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
    return AnalysisDecisionPaths(
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


@analysis
def analyze_sampling_noise(measurement: MeasAdc) -> AnalysisSamplingNoise:
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
    return AnalysisSamplingNoise(
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


@analysis
def analyze_cdac_settling(measurement: MeasAdc) -> AnalysisCdacSettling:
    """Align the first, middle, and last CDAC stages and measure final-value settling."""

    wave = measurement.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    time_s = wave.time_s
    threshold_v = 0.5 * float(measurement.tb.vdd_d.dc)
    capacitors = len(measurement.nominal_bout_weights) - 1
    decisions = capacitors + 1
    stage_cycles = tuple((stage, stage) for stage in dict.fromkeys((0, (capacitors - 1) // 2, capacitors - 1)))
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
                evaluation_v, evaluation_s, final=float(static_v), absolute_tolerance=CDAC_SETTLING_TOLERANCE_V
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
    return AnalysisCdacSettling(
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


@analysis
def analyze_power(measurement: MeasAdc) -> AnalysisPower:
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
    return AnalysisPower(
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


@analysis
def analyze_power_waveform(measurement: MeasAdc, *, power: AnalysisPower) -> AnalysisPowerWaveform:
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
    return AnalysisPowerWaveform(
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
# Timing closure
# =============================================================================


@analysis
def analyze_timing_closure(measurement: MeasAdc) -> AnalysisTimingClosure:
    """Check internal resolution -> held SR decision -> SAR/CDAC using /wave.

    Internal tendency is latch_p - latch_n just before the observed comparator
    reset. Resolution must persist until reset, and the correct rail-valid SR
    pair must persist through LOGIC. Repeated decisions need no SR transition.
    Every decision that switches a capacitor also requires the expected SAR
    state and driven bottom plates, plus top-plate settling, before the next
    observed comparator rise. Bottom-plate targets follow the programmed
    main/diff inversion (the generated ADC's is wired in, so a run of it is at
    dac_diffcaps 1); an array of unit capacitors has no difference plates, and
    none is saved, so its main plates alone are checked. Top-plate references
    are the final saved values before the next COMP, not a DC-accuracy
    guarantee. Only observed samples are used; this does not modify or
    re-decode DAQ codes.
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
    # an array of unit capacitors has no difference plates to save: its main plates alone
    differences = params.dut.cdac.weight_impl is not capdac.WeightImpl.UNIT_CAPS
    buses = (
        AdcNets.dac_state_p,
        AdcNets.dac_state_n,
        AdcNets.dac_state_p_diff,
        AdcNets.dac_state_n_diff,
        AdcNets.dac_botplate_p,
        AdcNets.dac_botplate_n,
        *((AdcNets.dac_botplate_p_diff, AdcNets.dac_botplate_n_diff) if differences else ()),
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
        | {f"comp.{net.name}" for net in (comp.Nets.latch_p, comp.Nets.latch_n)}
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
        internal = signals[f"comp.{comp.Nets.latch_p.name}"] - signals[f"comp.{comp.Nets.latch_n.name}"]
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
                        if diff and not differences:
                            continue
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
    return AnalysisTimingClosure(
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


@analysis
def analyze_timing_summary(
    measurement: MeasAdc,
    *,
    closure: AnalysisTimingClosure,
) -> AnalysisTimingSummary:
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
    return AnalysisTimingSummary(
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


# =============================================================================
# The campaign's studies: its noise, Hsu's integrated error, the ENOB ladder, energy, redundancy
# =============================================================================


@analysis
def analyze_input_noise(measurements: Sequence[MeasAdc]) -> AnalysisInputNoise:
    """The output code's noise over the input: the DC levels (V, differential) of a staircase capture
    (the record's, ``INPUT_NOISE_LEVELS`` of them) or of a lab study's DC steps (a capture each), and
    the output code's standard deviation at each (LSB)."""

    identity = measurement_identity(measurements)
    vin_v = np.concatenate([np.asarray(measurement.vin_diff_v, dtype=np.float64) for measurement in measurements])
    dout = np.concatenate([np.asarray(measurement.dout, dtype=np.float64) for measurement in measurements])
    levels = np.unique(np.round(vin_v, 9))
    sigma = np.array([np.std(dout[np.isclose(vin_v, level, rtol=0.0, atol=1e-9)]) for level in levels])
    return AnalysisInputNoise(
        group=identity.group, index=identity.index, dut=identity.dut, level_v=levels, sigma_lsb=sigma
    )


@analysis
def analyze_hsu(measurements: Sequence[MeasAdc]) -> AnalysisHsu:
    """Hsu's study: at each rate the integrated error sum_k |code_k - reference_k| (LSB) over every
    code centre, the codes decoded with the design weights. ``measurements`` are the ramps through
    every code centre at the array's own settling, one a rate, then their references at ideal timing
    in the same order (the same inputs at the same rate); each ramp's first conversion, a dummy a
    code below, is left out."""

    identity = measurement_identity(measurements)
    count = len(measurements) // 2
    captures, references = measurements[:count], measurements[count:]
    if len(measurements) != 2 * count or any(
        capture.sample_rate_hz != reference.sample_rate_hz
        for capture, reference in zip(captures, references, strict=True)
    ):
        raise ValueError("the Hsu study takes each rate's ramp and then its reference at the same rate")
    errors = np.empty(count)
    for index, (capture, reference) in enumerate(zip(captures, references, strict=True)):
        codes = np.asarray(capture.dout, dtype=np.int64)[1:]
        ideal = np.asarray(reference.dout, dtype=np.int64)[1:]
        errors[index] = float(np.sum(np.abs(codes - ideal)))
    rates = np.asarray([capture.sample_rate_hz for capture in captures])
    # the fastest rate before the integrated error first passes a code in 1024 (Hsu's zero, less the
    # rare metastable decision at a code centre), counting up from the slowest; NaN where even the
    # slowest does
    tolerance = max(1.0, len(references[0].dout) / 1024)
    failing = np.flatnonzero(errors > tolerance)
    fastest = rates[-1] if not len(failing) else rates[failing[0] - 1] if failing[0] else math.nan
    return AnalysisHsu(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        rate_hz=rates,
        integrated_error_lsb=errors,
        error_free_rate_hz=float(fastest),
    )


@analysis
def analyze_noise_rms(measurement: MeasAdc) -> AnalysisNoiseRms:
    """A fixed-input capture's output-code noise: its codes' standard deviation (LSB)."""

    identity = measurement.identity
    return AnalysisNoiseRms(
        group=identity.group, index=identity.index, dut=identity.dut, rms_lsb=float(np.std(measurement.dout))
    )


@analysis
def analyze_ladder(dynamics: Sequence[AnalysisDynamic]) -> AnalysisLadder:
    """The ENOB ladder (``LADDER``) from its steps' sines, quantization alone first (``LADDER_NAMES``'
    captures, each decoded as the record's ``enob_bits`` is): each step's spectral ENOB referred to
    full scale."""

    identity = measurement_identity(dynamics)
    if len(dynamics) != len(LADDER):
        raise ValueError(f"the ENOB ladder takes one sine a step, {len(LADDER)}, not {len(dynamics)}")
    return AnalysisLadder(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        enob_bits=np.asarray([dynamic.spectral_enob_fs_bits for dynamic in dynamics]),
    )


@analysis
def analyze_energy(measurements: Sequence[MeasAdc], *, power: Sequence[AnalysisPower]) -> AnalysisEnergy:
    """The energy a conversion takes over the input: each DC capture's input (V, differential: its
    conversions' mean) and each rail's energy per conversion from the capture's power (``power``, one
    a capture), its dynamic power at the active rate and its static power at the sample rate."""

    identity = measurement_identity(measurements)
    if len(power) != len(measurements):
        raise ValueError("the energy over the input takes one power result a capture")
    for measurement, result in zip(measurements, power, strict=True):
        check_identity(result, measurement.identity, name="power")
    energy = {
        rail: np.asarray(
            [
                getattr(result, f"{rail}_dynamic_power_w") / result.active_conversion_rate_hz
                + getattr(result, f"{rail}_static_power_w") / result.sample_rate_hz
                for result in power
            ]
        )
        for rail in ("vdd_a", "vdd_d", "vdd_dac")
    }
    return AnalysisEnergy(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_diff_v=np.asarray([float(np.mean(measurement.vin_diff_v)) for measurement in measurements]),
        vdd_a_energy_j=energy["vdd_a"],
        vdd_d_energy_j=energy["vdd_d"],
        vdd_dac_energy_j=energy["vdd_dac"],
    )


@analysis
def analyze_redundancy(calibration: AnalysisCalibration) -> AnalysisRedundancy:
    """Each stage's error tolerance (``_redundancy_margins``, after Ogawa et al.) with the design
    weights and with ``calibration``'s."""

    return AnalysisRedundancy(
        group=calibration.group,
        index=calibration.index,
        dut=calibration.dut,
        design_pct=_redundancy_margins(calibration.nominal_weights),
        calibrated_pct=_redundancy_margins(calibration.calibrated_weights),
    )


# =============================================================================
# Calibrations: each decision's weight, the decoder's
# =============================================================================


@analysis
def analyze_calibration1(
    measurements: Sequence[MeasCdac],
    *,
    cap_mismatch: capdac.AnalysisCapMismatch,
) -> AnalysisCalibration1:
    """Extract normalized BOUT weights from physical CDAC S-curves.

    The SAR logic initializes each P/N element from its programmed A-state and,
    for decision bit ``B``, selects the endpoint ``P_final = 1 - B`` and
    ``N_final = B``.  A-state therefore selects the physical switching direction,
    while B selects which endpoint is reached: an element starting at A=0 moves
    0-to-1 and one starting at A=1 moves 1-to-0, on each side independently. For
    equal or unequal P/N A-states, the distance between the ``B=0`` and ``B=1``
    endpoints is the sum of the direction-selected P and N movement magnitudes.

    Each capacitor's weight comes from the direction selected by its
    programmed P/N A-state in ``cap_mismatch``, which already references
    every step to the comparator offset. The terminal decision is a digital
    half-step, not a separately switched capacitor; its scale is inferred by
    projecting the measured movements onto their nominal design weights. This
    is the one coefficient marked as not directly measured in the result.
    The result applies to the whole ADC, so its DUT parameters are the ADC's.
    """

    identity = measurement_identity(measurements)
    check_identity(cap_mismatch, identity, name="CDAC cap mismatch")
    tb = measurements[0].tb
    # Every switched capacitor contributes twice its unit weight (both CDAC
    # sides move), and the terminal comparison adds one unit.
    nominal_bout_weight = np.asarray([2 * weight for weight in capdac.Model.weights(tb.dut.cdac)] + [1], float)
    nominal_cap_weight = nominal_bout_weight[:-1]
    initial_p = np.asarray(tb.dac_astate_p, dtype=np.int64)
    initial_n = np.asarray(tb.dac_astate_n, dtype=np.int64)
    measured = np.asarray(cap_mismatch.effective_fraction_by_direction, dtype=np.float64)
    if (
        initial_p.shape != (len(nominal_cap_weight),)
        or initial_n.shape != initial_p.shape
        or np.any((initial_p != 0) & (initial_p != 1))
        or np.any((initial_n != 0) & (initial_n != 1))
    ):
        raise ValueError("P/N A-states must contain one zero or one per capacitor")
    if measured.shape != (2, len(nominal_cap_weight), 2):
        raise ValueError("CDAC direction results must hold two sides, every capacitor, and two directions")
    # Direction index 0 is 1-to-0 and 1 is 0-to-1: A=0 selects index 1 and
    # A=1 selects index 0, independently for P (side 0) and N (side 1).
    element = np.arange(len(nominal_cap_weight))
    p_movement = measured[0, element, 1 - initial_p]
    n_movement = measured[1, element, 1 - initial_n]
    measured_cap_weight = p_movement + n_movement
    resolved = np.isfinite(p_movement) & np.isfinite(n_movement) & (p_movement > 0.0) & (n_movement > 0.0)
    if not np.any(resolved):
        raise ValueError("calibration 1 has no resolved direction-selected CDAC weights")
    # A failed or non-physical S-curve fit must not silently become a negative
    # backend coefficient. Fit one volts-per-design-unit scale from the valid
    # elements, retain each valid measured endpoint separation, and preserve
    # nominal ratios for unresolved elements. The result mask makes the
    # fallback visible to plots.
    measured_scale = float(
        np.dot(nominal_cap_weight[resolved], measured_cap_weight[resolved])
        / np.dot(nominal_cap_weight[resolved], nominal_cap_weight[resolved])
    )
    hybrid_cap_weight = nominal_cap_weight * measured_scale
    hybrid_cap_weight[resolved] = measured_cap_weight[resolved]
    terminal_weight = nominal_bout_weight[-1] * measured_scale
    code_max = (1 << tb.dut.adc_bits) - 1
    nominal_weight = nominal_bout_weight * code_max / np.sum(nominal_bout_weight)
    calibrated_weight = np.concatenate((hybrid_cap_weight, [terminal_weight]))
    calibrated_weight *= code_max / np.sum(calibrated_weight)
    return AnalysisCalibration1(
        group=identity.group,
        index=identity.index,
        dut=tb.dut,
        method="calibration1",
        label="Cal. 1: CDAC S-curve capacitor measurement",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=calibrated_weight,
        measured_weight_mask=np.concatenate((resolved, [False])),
        training_sample_count=sum(len(measurement.trial_index) for measurement in measurements),
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )


@analysis
def analyze_calibration2(measurement: MeasAdc, *, ramp: AnalysisRamp) -> AnalysisCalibration2:
    """Fit every BOUT coefficient from complete known-ramp cycles.

    This method leaves the analog ADC unchanged and uses the stored BOUT word to
    produce a corrected digital output. The extraction is reference assisted: the
    repeated ADC ramp supplies a known ideal code. Once the weights have been
    extracted, applying them is purely a digital backend or offline operation.
    Complete even-numbered cycles are used for fitting and complete odd-numbered
    cycles are reserved for validation. The ridge strength is dimensionless:
    ``0.02`` adds a prior penalty equivalent to roughly two percent of one
    observation per fitted weight. It is deliberately mild and is selected on an
    inner split of the training cycles before the final fit.

    A code-density lookup table is no alternative: a monotone, onto code-to-code
    table has to be the identity and therefore cannot correct INL while
    preserving every output code.

    The ramp phase supplies the ideal fractional code. Only the ramp's
    ``retained`` conversions in complete cycles are used, and endpoint-clipped
    conversions are excluded because their BOUT word no longer identifies
    where the input lies beyond the ADC range.

    The minimized training objective is

    ``sum((ideal - intercept - BOUT @ weight)**2)``
    ``+ ridge_strength * N_train / decisions * sum((weight - nominal)**2)``

    with nonnegative weights. Duplicate training words are compressed to
    weighted means before solving; this is algebraically equivalent for the
    fitted parameters. The ridge strength is chosen on an inner split of the
    even training cycles, so odd validation cycles never influence the fit.
    The fitted weights are normalized to the code range; ``output_gain`` and
    ``output_offset_lsb`` keep the global affine fit separately, so removing
    them does not needlessly collapse codes in the normalized output.
    """

    identity = measurement.identity
    check_identity(ramp, identity, name="ramp")
    if ramp.sample_count != len(measurement.bout):
        raise ValueError("calibration 2 requires the ramp analysis of this capture")
    code_max = measurement.code_max
    decisions = np.asarray(measurement.bout, dtype=np.float64)
    decision_count = decisions.shape[1]
    ideal_dout = ramp.conversion_phase * code_max
    cycle_index = ramp.cycle_index
    retained = ramp.retained & ramp.complete_cycle & (measurement.dout > 0) & (measurement.dout < code_max)
    nominal_weight = measurement.nominal_bout_weights.astype(np.float64)
    nominal_weight *= code_max / np.sum(nominal_weight)

    training = retained & (cycle_index % 2 == 0)
    validation = retained & (cycle_index % 2 != 0)
    if not np.any(training) or not np.any(validation):
        raise ValueError("calibration 2 requires retained samples from even training and odd validation cycles")
    # Renumber the even training cycles consecutively and split them again.
    even_cycles = np.unique(cycle_index[training])
    if len(even_cycles) < 2:
        raise ValueError("ridge selection requires at least two retained training cycles")
    inner_cycle = np.searchsorted(even_cycles, cycle_index)
    inner_training = training & (inner_cycle % 2 == 0)
    inner_validation = training & (inner_cycle % 2 != 0)
    # Candidate strengths from a vanishing prior to the mild 2% default, spaced
    # roughly by factors of five, cover the useful regularization range. Never
    # quite zero: a noise-free ramp repeats its BOUT words exactly, so with
    # redundant decisions the fit is rank-deficient and only the prior picks
    # the weights nearest the design's among the many that fit.
    candidates = (1e-6, 0.0001, 0.001, 0.005, 0.02)

    # Fit every candidate on the inner split, then refit all even cycles with
    # the strength whose inner validation error was lowest.
    inner_validation_rmse: list[float] = []
    normalized_weights = nominal_weight
    output_gain = 1.0
    output_intercept_lsb = 0.0
    for stage in range(len(candidates) + 1):
        if stage < len(candidates):
            fit_mask, score_mask, ridge_strength = inner_training, inner_validation, candidates[stage]
        else:
            best = min(range(len(candidates)), key=lambda index: (inner_validation_rmse[index], candidates[index]))
            fit_mask, score_mask, ridge_strength = training, validation, candidates[best]
        # each decision word as one integer, its first decision the most significant bit: the words
        # sort as np.unique(axis=0) sorts the rows, an order of magnitude faster than sorting rows
        bit_value = 1 << np.arange(decision_count - 1, -1, -1, dtype=np.int64)
        word_key = decisions[fit_mask].astype(np.int64) @ bit_value
        unique_key, inverse, word_count = np.unique(word_key, return_inverse=True, return_counts=True)
        unique_bout = ((unique_key[:, None] & bit_value) != 0).astype(np.float64)
        word_target = np.bincount(np.ravel(inverse), weights=ideal_dout[fit_mask]) / word_count
        sqrt_count = np.sqrt(word_count.astype(np.float64))
        design = np.column_stack((np.ones(len(unique_bout)), unique_bout)) * sqrt_count[:, None]
        target = word_target * sqrt_count
        ridge_penalty_scale = ridge_strength * np.count_nonzero(fit_mask) / decision_count
        if ridge_penalty_scale:
            prior_design = np.zeros((decision_count, decision_count + 1))
            prior_design[:, 1:] = np.eye(decision_count) * math.sqrt(ridge_penalty_scale)
            design = np.vstack((design, prior_design))
            target = np.concatenate((target, math.sqrt(ridge_penalty_scale) * nominal_weight))
        solution = lsq_linear(
            design,
            target,
            # The intercept is free; effective weights cannot be negative.
            bounds=(np.r_[-np.inf, np.zeros(decision_count)], np.full(decision_count + 1, np.inf)),
            # an exact active-set solve: with a noise-free ramp the trust-region one never converges
            method="bvls",
        )
        if not solution.success:
            raise RuntimeError(f"empirical BOUT calibration failed: {solution.message}")
        fitted_sum = float(np.sum(solution.x[1:]))
        if not math.isfinite(fitted_sum) or fitted_sum <= 0.0:
            raise RuntimeError("empirical BOUT calibration produced no positive weight sum")
        normalized_weights = solution.x[1:] * code_max / fitted_sum
        output_gain = fitted_sum / code_max
        output_intercept_lsb = float(solution.x[0])
        residual = output_intercept_lsb + output_gain * (decisions @ normalized_weights) - ideal_dout
        inner_validation_rmse.append(calc.rms(residual[score_mask]))

    return AnalysisCalibration2(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        method="calibration2",
        label="Cal. 2: least-squares fit to a known ramp",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=normalized_weights,
        measured_weight_mask=np.ones(decision_count, dtype=np.bool_),
        training_sample_count=int(np.count_nonzero(training)),
        validation_sample_count=int(np.count_nonzero(validation)),
        output_gain=output_gain,
        output_offset_lsb=output_intercept_lsb,
    )


@analysis
def analyze_calibration3(measurement: MeasAdc, *, ramp: AnalysisRamp) -> AnalysisCalibration3:
    """Extract Hsu prefix thresholds and validate a conservative BOUT decoder.

    This implements the foreground digital calibration described as Algorithm I
    in Section 4.2 of Albert Hsu's 2013 dissertation.  It uses a known, slow ramp
    and the stored BOUT decision word; it does not require a change to the
    ADC scan or to the fabricated converter.  For decision ``k`` it estimates the
    50% crossing after an all-zero prefix and after an all-one prefix.  Adjacent
    crossings give the two directional analog movements, and their sum is the
    effective coefficient multiplying BOUT[k].

    The current physical ramp is noisy enough that its smallest threshold
    separations are not all trustworthy.  This analysis intentionally keeps that
    limitation visible: every threshold and step carries a statistical uncertainty,
    and only a contiguous, validation-selected prefix of measured weights can be
    used.  Remaining weights retain their design ratios.  Comments below identify
    places where comparator noise, source noise, drift, or correlated samples can
    make the reported uncertainty optimistic.  A quieter calibration capture can
    use the same analysis without changing its data format.

    Complete even-numbered ramp cycles are the calibration set.  They are split
    again: one half extracts thresholds and the other chooses how many leading
    measured weights actually improve code-density INL.  Complete odd cycles
    are untouched until the final reported comparison, preventing selection on
    the result being reported.

    The selected prefix is intentionally contiguous.  A noisy small step does
    not justify trusting still-smaller later steps merely because one happened
    to fit well.  This is especially important in the present capture, where
    late all-zero/all-one paths have few minority decisions and the input and
    comparator noise are comparable to the physical step size.

    Each threshold is a binned probit fit. Binning is lossless for the
    Bernoulli likelihood apart from replacing each narrow bin's inputs by its
    center, and turns the four-million-sample capture into a small
    optimization problem. The probit width is an *effective* input-referred
    noise: it combines comparator noise, input-source noise, aperture
    uncertainty, and any threshold motion during the ramp. Its Fisher standard
    error assumes independent trials and a stationary threshold; consecutive
    conversions and repeated cycles in the real setup can be correlated, so
    that error is a resolution warning, not a promise that sub-millivolt
    weights are physically reproducible.
    """

    if not isinstance(measurement.tb.vin_diff, h.Vpwl.Params):
        raise TypeError("ADC threshold calibration requires a PWL differential-input source")
    identity = measurement.identity
    check_identity(ramp, identity, name="ramp")
    if ramp.sample_count != len(measurement.bout):
        raise ValueError("calibration 3 requires the ramp analysis of this capture")
    decisions = np.asarray(measurement.bout, dtype=np.uint8)
    decision_count = decisions.shape[1]
    vin_diff_min_v, vin_diff_max_v = ramp.vin_diff_min_v, ramp.vin_diff_max_v
    input_span_v = vin_diff_max_v - vin_diff_min_v
    inferred_vin_diff_v = vin_diff_min_v + ramp.conversion_phase * input_span_v
    cycle_index = ramp.cycle_index
    retained = ramp.retained & ramp.complete_cycle
    training = retained & (cycle_index % 2 == 0)
    validation = retained & (cycle_index % 2 != 0)
    inner_fit = training & (cycle_index % 4 == 0)
    inner_score = training & (cycle_index % 4 == 2)
    # Each split needs enough trials for the probit fits (64 per branch).
    if min(np.count_nonzero(inner_fit), np.count_nonzero(inner_score), np.count_nonzero(validation)) < 64:
        raise ValueError("threshold calibration requires multiple complete ramp cycles for train/validation splitting")
    code_max = measurement.code_max
    nominal_weight = measurement.nominal_bout_weights.astype(np.float64)
    nominal_weight *= code_max / np.sum(nominal_weight)
    # Keep the voltage resolution fixed instead of reducing it for rare late
    # branches.  Empty bins cost little, while coarsening a rare branch would
    # create exactly the false precision/ bias we are trying to expose for the
    # smallest capacitor steps. 16,384 bins resolve the ramp span to well
    # below one code of any converter resolution analyzed here.
    number_bins = 16_384
    bin_width_v = input_span_v / number_bins
    bin_index = np.clip(
        np.floor((inferred_vin_diff_v - vin_diff_min_v) * number_bins / input_span_v).astype(np.int64),
        0,
        number_bins - 1,
    )
    sigma_bounds = (math.log(max(bin_width_v / 32.0, np.finfo(np.float64).eps)), math.log(input_span_v / 2.0))

    # Stage 0 extracts thresholds on the inner fit cycles and selects how many
    # leading measured weights to trust by scoring INL on the inner score
    # cycles; the usable resolution is chosen only inside the even-cycle
    # training set. Stage 1 refits the already-selected model on every even
    # cycle. Odd cycles remain held out.
    selected_measured_step_count = 0
    calibrated_weight = nominal_weight
    for stage, extraction_mask in enumerate((inner_fit, training)):
        # Row 0 is the all-zero prefix ("down") and row 1 the all-one prefix ("up").
        threshold_v = np.empty((2, decision_count))
        threshold_std_v = np.empty((2, decision_count))
        for decision_index in range(decision_count):
            for branch in (0, 1):
                if decision_index == 0 and branch == 1:
                    # Both paths are the empty prefix at the first comparison.
                    # Fit it once so optimizer tolerance cannot create a
                    # fictitious difference between the two copies.
                    threshold_v[1, 0], threshold_std_v[1, 0] = threshold_v[0, 0], threshold_std_v[0, 0]
                    continue
                selected = extraction_mask & np.all(decisions[:, :decision_index] == branch, axis=1)
                decision = decisions[selected, decision_index]
                ones = int(np.count_nonzero(decision))
                if len(decision) < 64:
                    raise ValueError("threshold fit requires at least 64 branch trials")
                # Eight decisions of each state bracket the transition.
                if min(ones, len(decision) - ones) < 8:
                    raise ValueError("threshold fit is not bracketed by at least eight decisions of each state")
                trials = np.bincount(bin_index[selected], minlength=number_bins).astype(np.float64)
                one_count = np.bincount(bin_index[selected], weights=decision, minlength=number_bins)
                occupied = trials > 0.0
                trials, one_count = trials[occupied], one_count[occupied]
                centers_v = vin_diff_min_v + (np.flatnonzero(occupied) + 0.5) * bin_width_v

                # Seed the threshold at the split which minimizes binary
                # classification errors.  This is more robust than a cumulative
                # probability envelope: one rare noisy "1" far below the
                # transition would permanently contaminate an increasing
                # envelope, which matters precisely when a future quiet capture
                # makes the transition narrower than one voltage bin.
                zero_count = trials - one_count
                split_error = np.cumsum(one_count) + np.sum(zero_count) - np.cumsum(zero_count)
                seed = np.asarray(
                    [calc.xmin(split_error, centers_v), math.log(max(input_span_v / 1000.0, 2.0 * bin_width_v))]
                )
                # Very sharp, almost deterministic synthetic transitions
                # occasionally defeat the L-BFGS line search at its sigma bound.
                # Powell is slower but derivative-free and provides a reliable
                # fallback for that quiet-data regime; SciPy's default Powell
                # budget of 2,000 evaluations is raised to 10,000 so it
                # converges reproducibly in CI.
                fit = None
                for method, options in (
                    ("L-BFGS-B", None),
                    ("Powell", {"xtol": 1e-12, "ftol": 1e-12, "maxfev": 10_000}),
                ):
                    fit = minimize(
                        # Binned Bernoulli negative log-likelihood. log_ndtr
                        # stays finite in the saturated tails where log(Phi)
                        # would underflow; those tails matter because each Hsu
                        # prefix holds many deterministic decisions far from its
                        # transition.
                        lambda parameters, centers_v=centers_v, one_count=one_count, trials=trials: (
                            -float(
                                np.sum(
                                    one_count * log_ndtr((centers_v - parameters[0]) / math.exp(parameters[1]))
                                    + (trials - one_count)
                                    * log_ndtr((parameters[0] - centers_v) / math.exp(parameters[1]))
                                )
                            )
                        ),
                        seed,
                        method=method,
                        bounds=((vin_diff_min_v, vin_diff_max_v), sigma_bounds),
                        options=options,
                    )
                    if fit.success and np.all(np.isfinite(fit.x)):
                        break
                assert fit is not None
                if not fit.success or not np.all(np.isfinite(fit.x)):
                    raise RuntimeError(f"ADC threshold probit fit failed: {fit.message}")
                fitted_threshold_v = float(fit.x[0])
                sigma_v = math.exp(float(fit.x[1]))

                # Expected Fisher information for (threshold, log(sigma)). The
                # inverse is numerically more stable than differentiating the
                # optimizer objective a second time, especially for nearly
                # deterministic large bits.
                z = (centers_v - fitted_threshold_v) / sigma_v
                probability = np.clip(ndtr(z), 1e-12, 1.0 - 1e-12)
                normal_density = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
                derivatives = np.stack((-normal_density / sigma_v, -normal_density * z))
                information = (derivatives * (trials / (probability * (1.0 - probability)))) @ derivatives.T
                threshold_v[branch, decision_index] = fitted_threshold_v
                threshold_std_v[branch, decision_index] = math.sqrt(
                    max(0.0, float(np.linalg.pinv(information, rcond=1e-14)[0, 0]))
                )

        # Adjacent fits reuse many of the same ramp conversions.  Treating their
        # errors as independent is conservative for positively correlated p50
        # estimates but can still miss cycle-to-cycle drift.  A future quieter
        # scan with many independent ramp repetitions could replace this
        # approximation with a cycle bootstrap without changing the result type.
        down_step_v = threshold_v[0, :-1] - threshold_v[0, 1:]
        up_step_v = threshold_v[1, 1:] - threshold_v[1, :-1]
        down_step_std_v = np.hypot(threshold_std_v[0, :-1], threshold_std_v[0, 1:])
        up_step_std_v = np.hypot(threshold_std_v[1, :-1], threshold_std_v[1, 1:])
        endpoint_weight_v = down_step_v + up_step_v
        endpoint_weight_std_v = np.hypot(down_step_std_v, up_step_std_v)
        # A step is resolved when it exceeds three standard errors, a 99.7%
        # one-sided confidence that the movement is real and positive.
        step_resolved = (
            (down_step_v > 3.0 * down_step_std_v)
            & (up_step_v > 3.0 * up_step_std_v)
            & (endpoint_weight_v > 3.0 * endpoint_weight_std_v)
        )
        unresolved = np.flatnonzero(~step_resolved)
        contiguous_resolved = int(unresolved[0]) if len(unresolved) else len(step_resolved)

        if stage == 0:
            candidates = tuple(range(contiguous_resolved + 1))
        else:
            candidates = (min(selected_measured_step_count, contiguous_resolved),)
        candidate_maximum_abs_inl = []
        for measured_step_count in candidates:
            # Combine the measured prefix with a nominal tail on one analog
            # scale. Algorithm I supplies one fewer analog movement than BOUT
            # decisions: n thresholds have n - 1 adjacent separations. The
            # terminal half-step is therefore not separately observable here.
            # It, and every unresolved small step, retain their design ratios on
            # the volts-per-unit scale set by the measured prefix.
            analog_weight = nominal_weight.copy()
            if measured_step_count:
                nominal_prefix = nominal_weight[:measured_step_count]
                measured_prefix = endpoint_weight_v[:measured_step_count]
                analog_weight *= float(np.dot(nominal_prefix, measured_prefix) / np.dot(nominal_prefix, nominal_prefix))
                analog_weight[:measured_step_count] = measured_prefix
            if np.any(~np.isfinite(analog_weight)) or np.any(analog_weight <= 0.0):
                raise ValueError("calibrated decision weights must be finite and positive")
            calibrated_weight = analog_weight * code_max / np.sum(analog_weight)
            if stage == 0:
                decoded = np.rint(decisions[inner_score].astype(np.float64) @ calibrated_weight).astype(np.int64)
                counts = np.bincount(np.clip(decoded, 0, code_max), minlength=code_max + 1)
                candidate_maximum_abs_inl.append(calc.ymax(np.abs(calc.inl(calc.dnl(counts[1:code_max])))))
        selected_measured_step_count = int(np.argmin(candidate_maximum_abs_inl)) if stage == 0 else candidates[0]

    measured = np.zeros(decision_count, dtype=np.bool_)
    measured[:selected_measured_step_count] = True
    return AnalysisCalibration3(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        method="calibration3",
        label="Cal. 3: Hsu (2013) slow-ramp thresholds",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=calibrated_weight,
        measured_weight_mask=measured,
        training_sample_count=int(np.count_nonzero(training)),
        validation_sample_count=int(np.count_nonzero(validation)),
        output_gain=1.0,
        output_offset_lsb=0.0,
    )


def _decode(bout: np.ndarray, calibration: AnalysisCalibration, *, rounded: bool = True) -> np.ndarray:
    """Stored BOUT decisions decoded with ``calibration``'s weights, clipped to its code range.

    The stored DAQ codes are never replaced; calibrated codes exist only in the analysis that
    requests them. ``rounded`` gives whole codes, what an N-bit output word would carry and what
    the histogram analyses count. ``rounded=False`` keeps the fractional codes the dynamic and
    code-spectrum analyses take: rounding them would quantize the converter's output a second
    time, about 0.5 bit of ENOB.
    """

    decisions = np.asarray(bout)
    if decisions.ndim != 2 or decisions.shape[1] != len(calibration.calibrated_weights):
        raise ValueError("calibrated ADC decoding requires one BOUT column per calibrated weight")
    if np.any((decisions != 0) & (decisions != 1)):
        raise ValueError("calibrated ADC decoding requires binary BOUT values")
    fractional = np.clip(
        decisions.astype(np.float64) @ calibration.calibrated_weights, 0.0, float(calibration.code_max)
    )
    return fractional if not rounded else np.rint(fractional).astype(np.int64)


# =============================================================================
# Capacitor mismatch as statistics (the module's docstring)
# =============================================================================


@analysis
def analyze_mismatch(meas: MeasAdc) -> AnalysisMismatch:
    """The predicted mismatch statistics of a behavioral capture's array: its nominal capacitances
    (a capture without a draw), top-plate load, design weights and code range."""
    cdac = meas.param.cdac
    main_f, diff_f = calc_side_capacitances(cdac, meas.tb, "p")
    statistics = _mismatch_statistics(
        main_f,
        diff_f,
        cdac.parasitic_f,
        meas.nominal_bout_weights,
        meas.code_max,
        diffcaps=bool(meas.tb.dac_diffcaps),
    )
    return AnalysisMismatch(group=meas.group, index=meas.index, dut=meas.dut, **statistics)


@analysis
def analyze_mismatch_prediction(mismatch: AnalysisMismatch) -> AnalysisMismatchPrediction:
    """What an array's mismatch statistics predict at Harpe's matching (``UNIT_MISMATCH``): each
    stage's weight sigma, the DNL sigma at its transition and its margin over its sigma; and over the
    Pelgrom coefficients ``PELGROM_AXIS``, the worst DNL's and INL's 95th percentiles, decoded with
    the design weights."""

    return AnalysisMismatchPrediction(
        group=mismatch.group,
        index=mismatch.index,
        dut=mismatch.dut,
        unit_mismatch=UNIT_MISMATCH,
        weight_sigma_lsb=UNIT_MISMATCH * mismatch.weight_sigma,
        transition_sigma_lsb=UNIT_MISMATCH * mismatch.transition_sigma,
        margin_over_sigma=_margin_over_sigma(mismatch, UNIT_MISMATCH),
        coefficient=PELGROM_AXIS,
        dnl_p95_lsb=np.asarray([_dnl_quantile(mismatch, coefficient) for coefficient in PELGROM_AXIS]),
        inl_p95_lsb=np.asarray([_inl_quantile(mismatch, coefficient) for coefficient in PELGROM_AXIS]),
    )


@analysis
def analyze_mismatch_draws(measurements: Sequence[MeasAdc], *, ramps: Sequence[AnalysisRamp]) -> AnalysisMismatchDraws:
    """The Monte Carlo check of the predicted mismatch: the drawn arrays' ramps (behavioral captures,
    each its draw's, at its Pelgrom coefficient: the ``unit_mismatch`` readback) and their ramp
    analyses decoded with the design weights (``ramps``, one a capture), each one's worst |DNL| and
    |INL| and missing codes by coefficient and draw. The draws are each their own instance (a seed
    each), the result their design's."""

    if len(ramps) != len(measurements) or not measurements:
        raise ValueError("the mismatch draws take one ramp analysis a capture, at least one")
    for measurement, ramp in zip(measurements, ramps, strict=True):
        check_identity(ramp, measurement.identity, name="ramp")
    dut = measurements[0].dut
    if any(measurement.dut != dut for measurement in measurements):
        raise ValueError("the mismatch draws are of one design")
    rows: dict[float, list[tuple[float, float, float]]] = {}
    for measurement, ramp in zip(measurements, ramps, strict=True):
        coefficient = float(measurement.info.readbacks["unit_mismatch"])
        rows.setdefault(coefficient, []).append((ramp.maximum_abs_dnl, ramp.maximum_abs_inl, float(ramp.missing_codes)))
    coefficients = np.asarray(sorted(rows))
    columns = [np.asarray([[draw[column] for draw in rows[c]] for c in coefficients]) for column in range(3)]
    return AnalysisMismatchDraws(
        group=None,
        index=None,
        dut=dut,
        coefficient=coefficients,
        dnl_lsb=columns[0],
        inl_lsb=columns[1],
        missing_codes=columns[2],
    )


def _mismatch_statistics(
    main_f, diff_f, parasitic_f: float, weights, code_max: int, *, diffcaps: bool = True
) -> dict[str, np.ndarray]:
    """One side's mismatch statistics at a Pelgrom coefficient of 1 (``AnalysisMismatch``'s
    fields), from its nominal main and difference capacitances (C0 first), the top plate's other
    load, the decoder's weights (one a decision) and the output's largest code."""
    main, diff = np.asarray(main_f, dtype=np.float64), np.asarray(diff_f, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    stages = len(main)
    sign = -1.0 if diffcaps else 1.0
    switched = main + sign * diff
    load = float(np.sum(main) + np.sum(diff) + parasitic_f)
    lsb_per_farad = (code_max + 1) / (2 * float(np.sum(switched)))
    steps = switched * lsb_per_farad
    paths = calc_paths(steps, steps, weights, code_max)

    # each path's edges as sums of the p (a) and n (b) steps before their decision
    active = (paths.code > 0) & (paths.code < code_max)
    decided = paths.decisions[active, :stages].astype(np.int64)
    before = np.arange(stages)

    if np.any((paths.lower_stage[active] < 0) | (paths.upper_stage[active] < 0)):
        raise ValueError("a code between the ends has an unbounded path")
    a_low, b_low = _edge(decided, before, paths.lower_stage[active])
    a_high, b_high = _edge(decided, before, paths.upper_stage[active])
    codes = paths.code[active] - 1
    count = code_max - 1
    a_width = np.zeros((count, stages), dtype=np.int64)
    b_width = np.zeros((count, stages), dtype=np.int64)
    np.add.at(a_width, codes, a_high - a_low)
    np.add.at(b_width, codes, b_high - b_low)
    width = (a_width + b_width) @ steps

    # chained to the plates: a side's step error is lsb_per_farad (dc_k - c_k dC / load), the
    # plates (main and difference, p and n) independent with sigma sqrt(C 1 fF) at A = 1
    plate_sigma = np.sqrt(np.concatenate((main, diff)) * 1e-15)
    plates = partial(
        _plate_rows, switched=switched, load=load, lsb_per_farad=lsb_per_farad, sign=sign, plate_sigma=plate_sigma
    )
    width_rows = np.hstack((plates(a_width), plates(b_width)))
    mean_width = float(np.mean(width))
    dnl_rows = (width_rows - np.outer(width / mean_width, np.mean(width_rows, axis=0))) / mean_width
    dnl_mean = width / mean_width - 1.0
    inl_rows = np.vstack((np.zeros(dnl_rows.shape[1]), np.cumsum(dnl_rows[:-1], axis=0)))
    inl_rows -= np.outer(np.linspace(0.0, 1.0, count), inl_rows[-1])
    dnl_sigma = np.sqrt(np.sum(dnl_rows**2, axis=1))
    inl_sigma = np.sqrt(np.sum(inl_rows**2, axis=1))

    # the distinct widths: codes summing the same steps from the same sides
    _, group, sizes = np.unique(np.hstack((a_width, b_width)), axis=0, return_inverse=True, return_counts=True)
    group = group.ravel()
    groups = len(sizes)
    width_sigma = np.sqrt(np.sum(width_rows**2, axis=1))

    # each stage's transitions: the codes whose outer edges its decision sets
    first = np.r_[True, codes[1:] != codes[:-1]]
    last = np.r_[codes[1:] != codes[:-1], True]
    lower_edge = np.full(count, -1)
    upper_edge = np.full(count, -1)
    lower_edge[codes[first]] = paths.lower_stage[active][first]
    upper_edge[codes[last]] = paths.upper_stage[active][last]
    # a code's width spans the steps from its earlier edge's decision to its later one's: it is
    # that earlier stage's transition
    span_from = np.minimum(lower_edge, upper_edge)
    transition_sigma = np.array(
        [float(np.max(dnl_sigma[span_from == k])) if np.any(span_from == k) else math.nan for k in range(stages)]
    )

    weight_sigma = lsb_per_farad * np.sqrt((main + diff) * 1e-15)
    remaining = np.cumsum(weights[::-1])[::-1]
    # Ogawa's margin is in the decoder's weights, a step's half: in output LSB
    margin_lsb = (_redundancy_margins(weights) / 100 * remaining)[:stages] / 2 * code_max / np.sum(weights)
    # a wrong 1 at stage k (its n step taken) is undone by 0s after it (p steps): the margin is
    # sum_{j>k} a_j - b_k (and the mirror), its error that of those steps
    later = np.triu(np.ones((stages, stages), dtype=np.int64), 1)
    margin_rows = np.hstack((plates(later), plates(-np.eye(stages, dtype=np.int64))))
    margin_sigma = np.sqrt(np.sum(margin_rows**2, axis=1))

    # each stage's step on both sides, less its share of the endpoint gain: its error against the
    # decoder's weight (the nominal array's own) and its sigma
    identity = np.eye(stages, dtype=np.int64)
    gamma_rows = np.hstack((plates(identity), plates(identity)))
    decoder = weights[:stages] * code_max / np.sum(weights)
    share = decoder / np.sum(decoder)
    gamma_rows = gamma_rows - np.outer(share, np.sum(gamma_rows, axis=0))
    gamma_error = 2 * steps / mean_width - decoder
    gamma_error = gamma_error - share * np.sum(gamma_error)
    inl_mean = calc.inl(dnl_mean)
    return {
        "weight_sigma": weight_sigma,
        "transition_sigma": transition_sigma,
        "margin_lsb": margin_lsb,
        "margin_sigma": margin_sigma,
        "gamma_error": gamma_error,
        "gamma_sigma": np.sqrt(np.sum(gamma_rows**2, axis=1)),
        "dnl_mean": dnl_mean,
        "dnl_sigma": dnl_sigma,
        "inl_mean": inl_mean,
        "inl_sigma": inl_sigma,
        "width_mean": _by_group(width, group, groups) / mean_width,
        "width_sigma": _by_group(width_sigma, group, groups) / mean_width,
        "width_dnl_sigma": _by_group(dnl_sigma, group, groups),
        "width_codes": sizes,
    }


def _edge(decided: np.ndarray, before: np.ndarray, stage: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each path's edge at its decision ``stage`` as the p (a) and n (b) steps before it, a step's
    count each (``decided``: each path's decisions, ``before``: the stages)."""
    mask = before[None, :] < stage[:, None]
    return -(1 - decided) * mask, decided * mask


def _plate_rows(
    rows: np.ndarray, *, switched: np.ndarray, load: float, lsb_per_farad: float, sign: float, plate_sigma: np.ndarray
) -> np.ndarray:
    """Sums of a side's steps (``rows``, a count a step) as their errors in every plate's draw at a
    Pelgrom coefficient of 1 (LSB): a step's own plates, less its share of the side's load (a plate
    drawn large loads its side more)."""
    share = (rows @ switched / load)[:, None]
    return lsb_per_farad * np.hstack((rows - share, sign * rows - share)) * plate_sigma


def _by_group(values: np.ndarray, group: np.ndarray, groups: int) -> np.ndarray:
    """The largest of ``values`` in each of the ``groups`` groups (``group``: each value's)."""
    out = np.full(groups, -np.inf)
    np.maximum.at(out, group, values)
    return out


def _dnl_quantile(mismatch: AnalysisMismatch, unit_mismatch: float, quantile: float = 0.95) -> float:
    """The worst |DNL|'s ``quantile`` (LSB) at ``unit_mismatch``: the independent maximum over the
    distinct widths, an upper bound by Sidak's inequality where the nominal array has no error of its
    own."""
    return _independent_maximum_quantile(
        mismatch.width_mean - 1.0, unit_mismatch * mismatch.width_dnl_sigma, quantile, -1.0
    )


def _inl_quantile(mismatch: AnalysisMismatch, unit_mismatch: float, quantile: float = 0.95) -> float:
    """The worst |INL|'s ``quantile`` (LSB) at ``unit_mismatch``: half the sum of the stages'
    gain-corrected step errors' magnitudes, nominal and drawn (folded normals; exact for a binary
    array, an upper bound for the weights' part of any), less what that sum overstates the nominal
    array's own worst INL by (its codes need not take every decision pattern)."""
    weights = _sum_of_folded_normals_quantile(
        mismatch.gamma_error / 2, unit_mismatch * mismatch.gamma_sigma / 2, quantile
    )
    return weights + float(np.max(np.abs(mismatch.inl_mean))) - float(np.sum(np.abs(mismatch.gamma_error))) / 2


def _missing_codes(mismatch: AnalysisMismatch, unit_mismatch: float) -> np.ndarray:
    """The distribution of the missing-code count: P(count = m) for m = 0, 1, ..., each
    distinct width missing (not positive) with Phi(-w / sigma), the widths independent."""
    sigma = unit_mismatch * mismatch.width_sigma
    with np.errstate(divide="ignore", invalid="ignore"):
        missing = np.where(sigma > 0, ndtr(-mismatch.width_mean / sigma), (mismatch.width_mean <= 0).astype(float))
    distribution = np.ones(1)
    for probability, codes in zip(missing, mismatch.width_codes, strict=True):
        if probability < 1e-12:
            continue
        grown = np.zeros(len(distribution) + codes)
        grown[: len(distribution)] += (1.0 - probability) * distribution
        grown[codes:] += probability * distribution
        distribution = grown
    return distribution


def _missing_codes_quantile(mismatch: AnalysisMismatch, unit_mismatch: float, quantile: float = 0.95) -> float:
    """The missing-code count's ``quantile``."""
    return float(np.searchsorted(np.cumsum(_missing_codes(mismatch, unit_mismatch)), quantile))


def _missing_codes_expected(mismatch: AnalysisMismatch, unit_mismatch: float) -> float:
    """The expected number of missing codes."""
    distribution = _missing_codes(mismatch, unit_mismatch)
    return float(np.arange(len(distribution)) @ distribution)


def _margin_over_sigma(mismatch: AnalysisMismatch, unit_mismatch: float) -> np.ndarray:
    """Each stage's redundancy margin over its own sigma at ``unit_mismatch``."""
    return mismatch.margin_lsb / (unit_mismatch * mismatch.margin_sigma)


def _sum_of_folded_normals_quantile(means, scales, quantile: float, points: int = 1 << 14) -> float:
    """The ``quantile`` of sum_j |x_j| with independent x_j ~ N(means_j, scales_j^2): each folded
    normal as its probability over a common grid, convolved (FFT), each cut 8 scales past its mean."""
    means = np.abs(np.asarray(means, dtype=np.float64))
    scales = np.asarray(scales, dtype=np.float64)
    fixed = float(np.sum(means[scales <= 0]))
    means, scales = means[scales > 0], scales[scales > 0]
    if not len(scales):
        return fixed
    edges = np.linspace(0.0, float(np.sum(means + 8.0 * scales)), points + 1)
    spectrum = np.ones(points // 2 + 1, dtype=np.complex128)
    for mean, scale in zip(means, scales, strict=True):
        # P(|x| < e) = Phi((e - m) / s) - Phi((-e - m) / s), each bin's mass at its left edge
        spectrum *= np.fft.rfft(np.diff(ndtr((edges - mean) / scale) - ndtr((-edges - mean) / scale)), n=points)
    cumulative = np.cumsum(np.clip(np.fft.irfft(spectrum, n=points), 0.0, None))
    index = int(np.searchsorted(cumulative, quantile * cumulative[-1]))
    # half a bin a term above the left edges
    return fixed + float(edges[min(index, points - 1)] + 0.5 * (edges[1] - edges[0]) * len(scales))


def _independent_maximum_quantile(mean: np.ndarray, sigma: np.ndarray, quantile: float, least: float) -> float:
    """The ``quantile`` of max_g |x_g| with independent x_g ~ N(mean_g, sigma_g^2) (zero sigma: the
    mean alone), each x_g held at ``least`` from below (a DNL is never under -1: a code narrower than
    none is missing), by bisection of prod_g P(|x_g| <= x)."""
    mean, sigma = np.asarray(mean, dtype=np.float64), np.asarray(sigma, dtype=np.float64)
    floor = float(np.max(np.abs(mean)))
    random = sigma > 0
    if not np.any(random):
        return floor
    mean, sigma = mean[random], sigma[random]
    low, high = floor, floor + 10.0 * float(np.max(sigma)) + 10.0 * float(np.max(np.abs(mean)))
    target = math.log(quantile)
    for _ in range(80):
        middle = 0.5 * (low + high)
        low, high = (middle, high) if _log_probability(middle, mean, sigma, least) < target else (low, middle)
    return high


def _log_probability(x: float, mean: np.ndarray, sigma: np.ndarray, least: float) -> float:
    """log prod_g P(|x_g| <= x) of independent x_g ~ N(mean_g, sigma_g^2), each held at ``least``
    from below."""
    below = ndtr((-x - mean) / sigma) if x < -least else 0.0
    return float(np.sum(np.log(np.clip(ndtr((x - mean) / sigma) - below, 1e-300, 1.0))))


def _redundancy_margins(weights) -> np.ndarray:
    """Return each SAR stage's error tolerance as a percentage of the residue range left at it.

    T. Ogawa, H. Kobayashi, Y. Takahashi, N. Takai, M. Hotta, H. San, T. Matsuura, A. Abe,
    K. Yagi and T. Mori, "SAR ADC Algorithm with Redundancy and Digital Error Correction," IEICE
    Trans. Fundamentals, vol. E93-A, no. 2, pp. 415-423, Feb. 2010, doi:10.1587/transfun.E93.A.415.

    Their Eq. (5) defines the redundancy of step k as q(k) = -p(k+1) + 1 + sum_{i=k+2}^{M} p(i),
    and Proposition 1 shows that a wrong decision at step k still gives the right output code
    when |Vin - Vref(k)| < q(k). They count from 1: p(1) is the initial mid-scale reference, p(k+1)
    the step that decision k sets, and the +1 the last comparison's LSB. Here everything counts
    from 0: the M weights w_0 (C0, the first decision's) to w_{M-1} (the last decision's), w_k the
    step that decision k sets (+-w_k, as the CDAC switches). Their q(k+1) is then::

        q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1}

    returned as 100 * q_k / sum_{j=k}^{M-1} w_j. Binary weights give 0 at every stage; a positive
    value is the dynamic error (comparator noise or metastability, incomplete DAC settling,
    reference ripple) that stage tolerates; a negative one an error band the later stages cannot
    recover. The last stage's is 0: nothing after it corrects it. The tolerance is a worst-case
    bound per stage, and every stage may err within its own at once. Static weight errors
    (capacitor mismatch) are not tolerated: they need the decoder's weights calibrated.
    """
    values = np.asarray(weights, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("expected at least two finite, positive SAR weights in conversion order")
    remaining = np.cumsum(values[::-1])[::-1]
    # q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1} (Ogawa et al. Eq. 5, counted from 0). Until
    # 2026-10-21 this was (sum_{j=k+1}^{M-1} w_j - w_k) / sum_{j=k}^{M-1} w_j for k < M-1: without
    # the w_{M-1} term every stage read w_{M-1} low, so binary weights went negative toward the LSB
    return (remaining - 2 * values + values[-1]) / remaining * 100


# =============================================================================
# The record's numbers
# =============================================================================


def metrics(
    *,
    dynamics: Sequence[AnalysisDynamic],
    powers: Sequence[AnalysisPower],
    fins: Sequence[AnalysisDynamic],
    ramp: AnalysisRamp,
    extracted: AnalysisRamp,
    calibrated: AnalysisRamp,
    noise: AnalysisNoiseRms,
    input_noise: AnalysisInputNoise,
    hsu: AnalysisHsu,
    redundancy: AnalysisRedundancy,
    mismatch: AnalysisMismatch,
    noise_sampling: AnalysisNoiseRms | None = None,
    noise_comparator: AnalysisNoiseRms | None = None,
    calibration3: AnalysisCalibration3 | None = None,
    drawn_design: AnalysisDynamic | None = None,
    drawn_extracted: AnalysisDynamic | None = None,
    drawn_calibrated: AnalysisDynamic | None = None,
    ladder: AnalysisLadder | None = None,
    draws: AnalysisMismatchDraws | None = None,
) -> dict[str, float]:
    """The record's numbers from its campaign's results: the sines over the rate (``dynamics``,
    slowest first, the extracted weights' codes) and their power, the nominal rate's sines over the
    input frequency (``fins``, lowest first), the check ramp decoded with the design weights, the
    extracted weights and the calibration that grades it best (``calibrated``), the noise capture's
    output-code noise (with one source alone, where the campaign has it), the noise over the input,
    Hsu's study, the redundancy of the extracted weights, the array's predicted mismatch; whether
    calibration 3 fitted (``calibration3``), the nominal rate's sine on the CDAC's SPICE draw decoded
    with the design weights, the nominal extraction's and the best calibration's, the ENOB ladder and
    the Monte Carlo's check of the mismatch, where the campaign holds them. Every ENOB is the
    spectral one referred to full scale (an ideal N-bit quantizer reads N); the SNDR is the test
    sine's own, at -0.5 dBFS."""

    dynamic, power = next(
        (d, p) for d, p in zip(dynamics, powers, strict=True) if round(d.sample_rate_hz) == round(NOMINAL_RATE_HZ)
    )
    power_w = sum(
        getattr(power, f"{rail}_{kind}_power_w")
        for rail in ("vdd_a", "vdd_d", "vdd_dac")
        for kind in ("static", "dynamic")
    )
    sigma_lsb = input_noise.sigma_lsb
    # the redundant stages' margins over their sigma (the others have none to lose)
    margins = _margin_over_sigma(mismatch, UNIT_MISMATCH)[np.abs(mismatch.margin_lsb) > 1e-9]
    values = {
        "enob_bits": dynamic.spectral_enob_fs_bits,
        "sndr_db": dynamic.spectral_sndr_db,
        "sfdr_db": dynamic.spectral_sfdr_db,
        "enob_nyquist_bits": fins[-1].spectral_enob_fs_bits,
        "enob_low_fin_bits": fins[0].spectral_enob_fs_bits,
        "inl_max_lsb": ramp.maximum_abs_inl,
        "dnl_max_lsb": ramp.maximum_abs_dnl,
        "inl_max_extracted_lsb": extracted.maximum_abs_inl,
        "inl_max_calibrated_lsb": calibrated.maximum_abs_inl,
        "dnl_max_calibrated_lsb": calibrated.maximum_abs_dnl,
        "missing_codes": float(ramp.missing_codes),
        "power_w": power_w,
        "energy_per_conversion_j": power_w / dynamic.sample_rate_hz,
        "fom_walden_j": power_w / (2**dynamic.spectral_enob_fs_bits * dynamic.sample_rate_hz),
        "fom_schreier_db": dynamic.spectral_sndr_db + 10 * math.log10(dynamic.sample_rate_hz / 2 / power_w),
        "noise_rms_lsb": noise.rms_lsb,
        # each noise source alone (the noise capture with only it on), where the campaign has them
        **{
            f"noise_{source}_rms_lsb": result.rms_lsb
            for source, result in (("sampling", noise_sampling), ("comparator", noise_comparator))
            if result is not None
        },
        # the output-code noise at the input's ends and at mid-scale
        "noise_input_edge_lsb": float(max(sigma_lsb[0], sigma_lsb[-1])),
        "noise_input_mid_lsb": float(sigma_lsb[len(sigma_lsb) // 2]),
        # Hsu's study at the array's own settling: the fastest error-free rate, and the error at 10 MS/s
        "error_free_rate_max_hz": float(hsu.error_free_rate_hz),
        "integrated_error_nominal_lsb": float(
            hsu.integrated_error_lsb[np.flatnonzero(hsu.rate_hz == NOMINAL_RATE_HZ)[0]]
        ),
        # the fastest rate before the ENOB first falls a bit below the slowest rate's: past it the
        # comparator or the DAC runs out of time (the sampler's distortion slopes off more gently)
        "rate_max_hz": list(
            takewhile(lambda d: d.spectral_enob_fs_bits >= dynamics[0].spectral_enob_fs_bits - 1.0, dynamics)
        )[-1].sample_rate_hz,
        "redundancy_first_pct": float(redundancy.design_pct[0]),
        "redundancy_first_extracted_pct": float(redundancy.calibrated_pct[0]),
        "calibration3_fitted": float(calibration3 is not None),
        # the calibration the calibrated metrics use
        "calibration_best": float(calibrated.decoding.removeprefix("calibration")),
        # the nominal rate's sine on the CDAC's SPICE draw the ramps calibrate on, decoded with the
        # design weights (as it comes), the nominal extraction's (its systematic error calibrated,
        # not the draw's) and the best calibration learned from the drawn training ramp
        **{
            f"enob_drawn_{name}_bits": result.spectral_enob_fs_bits
            for name, result in (
                ("design", drawn_design),
                ("extracted", drawn_extracted),
                ("calibrated", drawn_calibrated),
            )
            if result is not None
        },
        # predicted at Harpe's matching (0.10 %·sqrt(fF)), decoded with the design weights: the
        # array's own layout error and the mismatch's 95th percentile; the largest DNL and INL sigma
        # of any code; the smallest margin of a redundant stage over its sigma (NaN without one)
        "mismatch_dnl_p95_lsb": _dnl_quantile(mismatch, UNIT_MISMATCH),
        "mismatch_inl_p95_lsb": _inl_quantile(mismatch, UNIT_MISMATCH),
        "mismatch_missing_codes_p95": _missing_codes_quantile(mismatch, UNIT_MISMATCH),
        "dnl_sigma_max_lsb": UNIT_MISMATCH * float(np.max(mismatch.dnl_sigma)),
        "inl_sigma_max_lsb": UNIT_MISMATCH * float(np.max(mismatch.inl_sigma)),
        "min_margin_over_sigma": float(np.min(margins)) if len(margins) else math.nan,
    }
    # the ladder's first step, and what each impairment after it costs where it is added (the
    # losses add up to the quantization's ENOB less enob_bits)
    if ladder is not None:
        enob = ladder.enob_bits
        values["enob_quantization_bits"] = float(enob[0])
        for (key, _, _, _), before, after in zip(LADDER[1:], enob[:-1], enob[1:], strict=True):
            values[f"enob_loss_{key}_bits"] = float(before - after)
    # the Monte Carlo's check, where the campaign drew it: its 95th percentiles at Harpe's matching
    if draws is not None:
        index = int(np.argmin(np.abs(draws.coefficient - UNIT_MISMATCH)))
        for drawn, column in (
            (draws.dnl_lsb, "dnl_p95_lsb"),
            (draws.inl_lsb, "inl_p95_lsb"),
            (draws.missing_codes, "missing_codes_p95"),
        ):
            values[f"mismatch_mc_{column}"] = float(np.percentile(drawn[index], 95))
    return values
