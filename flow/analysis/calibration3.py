"""Calibration 3: slow-ramp SAR decision-threshold extraction.

This implements the foreground digital calibration described as Algorithm I
in Section 4.2 of Albert Hsu's 2013 dissertation.  It uses a known, slow ramp
and the stored 17-bit BOUT decision word; it does not require a change to the
ADC scan or to the fabricated converter.  For decision ``k`` it estimates the
50% crossing after an all-zero prefix and after an all-one prefix.  Adjacent
crossings give the two directional analog movements, and their sum is the
effective coefficient multiplying BOUT[k].

The current physical ramp is noisy enough that its smallest threshold
separations are not all trustworthy.  This module intentionally keeps that
limitation visible: every threshold and step carries a statistical uncertainty,
and only a contiguous, validation-selected prefix of measured weights can be
used.  Remaining weights retain their design ratios.  Comments below identify
places where comparator noise, source noise, drift, or correlated samples can
make the reported uncertainty optimistic.  A quieter calibration capture can
use the same analysis without changing its data format.
"""

from __future__ import annotations

import math

import hdl21 as h
import numpy as np
from scipy.optimize import minimize
from scipy.special import log_ndtr, ndtr

from flow.analysis.adc import ADC_RAMP_RESET_EXCLUSION_CONVERSIONS
from flow.analysis.measure import histogram_inl_dnl
from flow.analysis.types import AnalysisAdcCalibration, AnalysisAdcRamp, MeasAdc
from flow.cdac import get_cdac_weights

THRESHOLD_BIN_COUNT = 16_384
STEP_RESOLUTION_SIGMA = 3.0


def _probit_negative_log_likelihood(
    parameters: np.ndarray,
    centers_v: np.ndarray,
    one_count: np.ndarray,
    trials: np.ndarray,
) -> float:
    """Return the stable binned Bernoulli objective for one probit fit."""

    threshold_v, log_sigma_v = (float(value) for value in parameters)
    sigma_v = math.exp(log_sigma_v)
    z = (centers_v - threshold_v) / sigma_v
    # log_ndtr remains finite in the saturated tails where direct log(Phi)
    # would underflow. Those tails matter because each Hsu prefix contains
    # many deterministic decisions far from its transition.
    return -float(np.sum(one_count * log_ndtr(z) + (trials - one_count) * log_ndtr(-z)))


def _fit_probit_threshold(
    vin_diff_v: np.ndarray,
    decision: np.ndarray,
    *,
    vin_diff_min_v: float,
    vin_diff_max_v: float,
) -> tuple[float, float, float, int]:
    """Fit one decision probability and return p50, noise sigma, and p50 SE.

    Binning is lossless for the Bernoulli likelihood apart from replacing each
    narrow bin's inputs by its center, and turns the four-million-sample capture
    into a small optimization problem.  The probit width is an *effective*
    input-referred noise: it combines comparator noise, input-source noise,
    aperture uncertainty, and any threshold motion during the ramp.

    The Fisher standard error assumes independent trials and a stationary
    threshold.  Consecutive conversions and repeated cycles in the real setup
    can be correlated, so this error can be too small when slow drift or source
    noise dominates.  It is useful as a resolution warning, not a promise that
    the extracted sub-millivolt weights are physically reproducible.
    """

    vin_diff_v = np.asarray(vin_diff_v, dtype=np.float64)
    decision = np.asarray(decision, dtype=np.uint8)
    if vin_diff_v.ndim != 1 or decision.ndim != 1 or len(vin_diff_v) != len(decision):
        raise ValueError("threshold inputs and decisions must be aligned one-dimensional arrays")
    if len(vin_diff_v) < 64:
        raise ValueError("threshold fit requires at least 64 branch trials")
    if np.any((decision != 0) & (decision != 1)):
        raise ValueError("threshold decisions must be binary")
    zeros = int(np.count_nonzero(decision == 0))
    ones = len(decision) - zeros
    if min(zeros, ones) < 8:
        raise ValueError("threshold fit is not bracketed by at least eight decisions of each state")

    input_span_v = vin_diff_max_v - vin_diff_min_v
    if not math.isfinite(input_span_v) or input_span_v <= 0.0:
        raise ValueError("threshold fit requires a finite, nonzero input span")
    # Keep the voltage resolution fixed instead of reducing it for rare late
    # branches.  Empty bins cost little, while coarsening a rare branch would
    # create exactly the false precision/ bias we are trying to expose for the
    # smallest capacitor steps.
    number_bins = THRESHOLD_BIN_COUNT
    scaled = (vin_diff_v - vin_diff_min_v) * number_bins / input_span_v
    bin_index = np.floor(scaled).astype(np.int64)
    bin_index = np.clip(bin_index, 0, number_bins - 1)
    trials = np.bincount(bin_index, minlength=number_bins).astype(np.float64)
    one_count = np.bincount(bin_index, weights=decision, minlength=number_bins).astype(np.float64)
    occupied = trials > 0.0
    trials = trials[occupied]
    one_count = one_count[occupied]
    bin_width_v = input_span_v / number_bins
    centers_v = vin_diff_min_v + (np.flatnonzero(occupied) + 0.5) * bin_width_v

    # Seed the threshold at the split which minimizes binary classification
    # errors.  This is more robust than a cumulative probability envelope: one
    # rare noisy "1" far below the transition would permanently contaminate an
    # increasing envelope, which matters precisely when a future quiet capture
    # makes the transition narrower than one voltage bin.
    zero_count = trials - one_count
    split_error = np.cumsum(one_count) + np.sum(zero_count) - np.cumsum(zero_count)
    threshold_seed_v = float(centers_v[int(np.argmin(split_error))])
    sigma_seed_v = max(input_span_v / 1000.0, 2.0 * bin_width_v)
    minimum_sigma_v = max(bin_width_v / 32.0, np.finfo(np.float64).eps)
    maximum_sigma_v = input_span_v / 2.0

    fit = minimize(
        _probit_negative_log_likelihood,
        np.asarray([threshold_seed_v, math.log(sigma_seed_v)]),
        args=(centers_v, one_count, trials),
        method="L-BFGS-B",
        bounds=(
            (vin_diff_min_v, vin_diff_max_v),
            (math.log(minimum_sigma_v), math.log(maximum_sigma_v)),
        ),
    )
    if not fit.success or not np.all(np.isfinite(fit.x)):
        # Very sharp, almost deterministic synthetic transitions occasionally
        # defeat the L-BFGS line search at its sigma bound.  Powell is slower but
        # derivative-free and provides a reliable fallback for that quiet-data
        # regime; ordinary noisy physical fits remain on the fast path above.
        fit = minimize(
            _probit_negative_log_likelihood,
            np.asarray([threshold_seed_v, math.log(sigma_seed_v)]),
            args=(centers_v, one_count, trials),
            method="Powell",
            bounds=(
                (vin_diff_min_v, vin_diff_max_v),
                (math.log(minimum_sigma_v), math.log(maximum_sigma_v)),
            ),
            # SciPy's default two-parameter Powell budget is 2,000 objective
            # evaluations.  Near-deterministic transitions can need slightly
            # more on some CPU/libm combinations, so keep the fallback bounded
            # but large enough to converge reproducibly in CI.
            options={"xtol": 1e-12, "ftol": 1e-12, "maxfev": 10_000},
        )
    if not fit.success or not np.all(np.isfinite(fit.x)):
        raise RuntimeError(f"ADC threshold probit fit failed: {fit.message}")
    threshold_v = float(fit.x[0])
    sigma_v = math.exp(float(fit.x[1]))

    # Expected Fisher information for parameters (threshold, log(sigma)).
    # The inverse is numerically more stable than differentiating the optimizer
    # objective a second time, especially for nearly deterministic large bits.
    z = (centers_v - threshold_v) / sigma_v
    probability = np.clip(ndtr(z), 1e-12, 1.0 - 1e-12)
    normal_density = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    derivative_threshold = -normal_density / sigma_v
    derivative_log_sigma = -normal_density * z
    information_weight = trials / (probability * (1.0 - probability))
    information = np.asarray(
        [
            [
                np.sum(information_weight * derivative_threshold * derivative_threshold),
                np.sum(information_weight * derivative_threshold * derivative_log_sigma),
            ],
            [
                np.sum(information_weight * derivative_threshold * derivative_log_sigma),
                np.sum(information_weight * derivative_log_sigma * derivative_log_sigma),
            ],
        ],
        dtype=np.float64,
    )
    covariance = np.linalg.pinv(information, rcond=1e-14)
    threshold_std_v = math.sqrt(max(0.0, float(covariance[0, 0])))
    return threshold_v, sigma_v, threshold_std_v, len(vin_diff_v)


def _extract_prefix_thresholds(
    decisions: np.ndarray,
    inferred_vin_diff_v: np.ndarray,
    retained: np.ndarray,
    *,
    vin_diff_min_v: float,
    vin_diff_max_v: float,
) -> dict[str, np.ndarray]:
    """Extract every all-zero and all-one prefix threshold from BOUT."""

    number_decisions = decisions.shape[1]
    down_threshold_v = np.empty(number_decisions, dtype=np.float64)
    up_threshold_v = np.empty(number_decisions, dtype=np.float64)
    down_threshold_std_v = np.empty(number_decisions, dtype=np.float64)
    up_threshold_std_v = np.empty(number_decisions, dtype=np.float64)
    down_noise_sigma_v = np.empty(number_decisions, dtype=np.float64)
    up_noise_sigma_v = np.empty(number_decisions, dtype=np.float64)
    down_trial_count = np.empty(number_decisions, dtype=np.int64)
    up_trial_count = np.empty(number_decisions, dtype=np.int64)

    for decision_index in range(number_decisions):
        if decision_index == 0:
            # Both paths are the empty prefix at the first comparison.  Fit it
            # once so numerical optimizer tolerance cannot create a fictitious
            # difference between the two copies.
            threshold = _fit_probit_threshold(
                inferred_vin_diff_v[retained],
                decisions[retained, decision_index],
                vin_diff_min_v=vin_diff_min_v,
                vin_diff_max_v=vin_diff_max_v,
            )
            down_threshold_v[0] = up_threshold_v[0] = threshold[0]
            down_noise_sigma_v[0] = up_noise_sigma_v[0] = threshold[1]
            down_threshold_std_v[0] = up_threshold_std_v[0] = threshold[2]
            down_trial_count[0] = up_trial_count[0] = threshold[3]
            continue

        prefix = decisions[:, :decision_index]
        down_branch = retained & np.all(prefix == 0, axis=1)
        up_branch = retained & np.all(prefix == 1, axis=1)
        down = _fit_probit_threshold(
            inferred_vin_diff_v[down_branch],
            decisions[down_branch, decision_index],
            vin_diff_min_v=vin_diff_min_v,
            vin_diff_max_v=vin_diff_max_v,
        )
        up = _fit_probit_threshold(
            inferred_vin_diff_v[up_branch],
            decisions[up_branch, decision_index],
            vin_diff_min_v=vin_diff_min_v,
            vin_diff_max_v=vin_diff_max_v,
        )
        down_threshold_v[decision_index], down_noise_sigma_v[decision_index] = down[:2]
        down_threshold_std_v[decision_index], down_trial_count[decision_index] = down[2:]
        up_threshold_v[decision_index], up_noise_sigma_v[decision_index] = up[:2]
        up_threshold_std_v[decision_index], up_trial_count[decision_index] = up[2:]

    # Adjacent fits reuse many of the same ramp conversions.  Treating their
    # errors as independent is conservative for positively correlated p50
    # estimates but can still miss cycle-to-cycle drift.  A future quieter scan
    # with many independent ramp repetitions could replace this approximation
    # with a cycle bootstrap without changing the public result type.
    down_step_v = down_threshold_v[:-1] - down_threshold_v[1:]
    up_step_v = up_threshold_v[1:] - up_threshold_v[:-1]
    down_step_std_v = np.hypot(down_threshold_std_v[:-1], down_threshold_std_v[1:])
    up_step_std_v = np.hypot(up_threshold_std_v[:-1], up_threshold_std_v[1:])
    endpoint_weight_v = down_step_v + up_step_v
    endpoint_weight_std_v = np.hypot(down_step_std_v, up_step_std_v)
    step_resolved = (
        (down_step_v > STEP_RESOLUTION_SIGMA * down_step_std_v)
        & (up_step_v > STEP_RESOLUTION_SIGMA * up_step_std_v)
        & (endpoint_weight_v > STEP_RESOLUTION_SIGMA * endpoint_weight_std_v)
    )
    return {
        "down_threshold_v": down_threshold_v,
        "up_threshold_v": up_threshold_v,
        "down_threshold_std_v": down_threshold_std_v,
        "up_threshold_std_v": up_threshold_std_v,
        "down_noise_sigma_v": down_noise_sigma_v,
        "up_noise_sigma_v": up_noise_sigma_v,
        "down_trial_count": down_trial_count,
        "up_trial_count": up_trial_count,
        "down_step_v": down_step_v,
        "up_step_v": up_step_v,
        "down_step_std_v": down_step_std_v,
        "up_step_std_v": up_step_std_v,
        "endpoint_weight_v": endpoint_weight_v,
        "endpoint_weight_std_v": endpoint_weight_std_v,
        "step_resolved": step_resolved,
    }


def _contiguous_resolved_count(step_resolved: np.ndarray) -> int:
    unresolved = np.flatnonzero(~step_resolved)
    return int(unresolved[0]) if len(unresolved) else len(step_resolved)


def _hybrid_weights(
    nominal_weight: np.ndarray,
    endpoint_weight_v: np.ndarray,
    measured_step_count: int,
    *,
    code_max: int,
) -> np.ndarray:
    """Combine an extracted prefix with a nominal tail on one analog scale."""

    if measured_step_count == 0:
        analog_weight = nominal_weight.copy()
    else:
        nominal_prefix = nominal_weight[:measured_step_count]
        measured_prefix = endpoint_weight_v[:measured_step_count]
        volts_per_nominal_unit = float(np.dot(nominal_prefix, measured_prefix) / np.dot(nominal_prefix, nominal_prefix))
        # Algorithm I supplies one fewer analog movement than BOUT decisions:
        # seventeen thresholds have sixteen adjacent separations.  The final
        # terminal half-step is therefore not separately observable here.  It,
        # and every unresolved small step, retain their design ratios on the
        # volts-per-unit scale set by the measured prefix.
        analog_weight = nominal_weight * volts_per_nominal_unit
        analog_weight[:measured_step_count] = measured_prefix
    if np.any(~np.isfinite(analog_weight)) or np.any(analog_weight <= 0.0):
        raise ValueError("calibrated decision weights must be finite and positive")
    return analog_weight * code_max / np.sum(analog_weight)


def _code_density(
    decisions: np.ndarray,
    retained: np.ndarray,
    weights: np.ndarray,
    *,
    code_max: int,
) -> dict[str, np.ndarray | float | int]:
    decoded = np.rint(decisions[retained].astype(np.float64) @ weights).astype(np.int64)
    decoded = np.clip(decoded, 0, code_max)
    counts = np.bincount(decoded, minlength=code_max + 1)
    return histogram_inl_dnl(counts, first_code=1, last_code=code_max - 1)


def analyze(measurement: MeasAdc, ramp: AnalysisAdcRamp) -> AnalysisAdcCalibration:
    """Extract Hsu prefix thresholds and validate a conservative BOUT decoder.

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
    """

    if not isinstance(measurement.param.vin_diff, h.Vpwl.Params):
        raise TypeError("ADC threshold calibration requires a PWL differential-input source")
    adc_index = -1 if measurement.param.observed_adc is None else measurement.param.observed_adc
    if ramp.adc_index != adc_index or ramp.sample_count != len(measurement.daq.bout):
        raise ValueError("calibration 3 requires the matching ADC ramp analysis")
    decisions = np.asarray(measurement.daq.bout, dtype=np.uint8)
    if decisions.ndim != 2 or decisions.shape[1] != 17:
        raise ValueError("ADC threshold calibration requires stored 17-bit BOUT decisions")

    sample = np.arange(ramp.sample_count, dtype=np.float64)
    reset_number = np.arange(len(ramp.reset_conversion_index), dtype=np.float64)
    period_samples, first_reset_sample = np.linalg.lstsq(
        np.column_stack((reset_number, np.ones(len(reset_number)))),
        ramp.reset_conversion_index.astype(np.float64),
        rcond=None,
    )[0]
    phase = np.mod((sample - first_reset_sample) / period_samples, 1.0)
    inferred_vin_diff_v = ramp.vin_diff_min_v + phase * (ramp.vin_diff_max_v - ramp.vin_diff_min_v)
    cycle_index = np.floor((sample - first_reset_sample) / period_samples).astype(np.int64)

    retained = (cycle_index >= 0) & (cycle_index < len(ramp.reset_conversion_index) - 1)
    for reset_index in ramp.reset_conversion_index:
        retained[max(0, reset_index - 1) : reset_index + ADC_RAMP_RESET_EXCLUSION_CONVERSIONS] = False
    training = retained & (cycle_index % 2 == 0)
    validation = retained & (cycle_index % 2 != 0)
    inner_fit = training & (cycle_index % 4 == 0)
    inner_score = training & (cycle_index % 4 == 2)
    if min(np.count_nonzero(inner_fit), np.count_nonzero(inner_score), np.count_nonzero(validation)) < 64:
        raise ValueError("threshold calibration requires multiple complete ramp cycles for train/validation splitting")

    nominal_weight = np.asarray(
        [2 * value for value in get_cdac_weights(measurement.param.dut.cdac)] + [1],
        dtype=np.float64,
    )
    code_max = (1 << measurement.param.dut.adc_bits) - 1
    nominal_weight *= code_max / np.sum(nominal_weight)

    # Select the usable resolution only inside the even-cycle training set.
    # This guards against the tempting but invalid practice of looking at the
    # odd-cycle INL and then choosing the cutoff which makes it look best.
    selection_extraction = _extract_prefix_thresholds(
        decisions,
        inferred_vin_diff_v,
        inner_fit,
        vin_diff_min_v=ramp.vin_diff_min_v,
        vin_diff_max_v=ramp.vin_diff_max_v,
    )
    maximum_candidate = _contiguous_resolved_count(selection_extraction["step_resolved"])
    candidate_measured_step_count = np.arange(maximum_candidate + 1, dtype=np.int64)
    candidate_maximum_abs_inl = np.empty(len(candidate_measured_step_count), dtype=np.float64)
    for index, measured_step_count in enumerate(candidate_measured_step_count):
        candidate_weight = _hybrid_weights(
            nominal_weight,
            selection_extraction["endpoint_weight_v"],
            int(measured_step_count),
            code_max=code_max,
        )
        candidate_density = _code_density(
            decisions,
            inner_score,
            candidate_weight,
            code_max=code_max,
        )
        candidate_maximum_abs_inl[index] = float(np.max(np.abs(candidate_density["inl"])))
    selected_index = min(
        range(len(candidate_measured_step_count)),
        key=lambda index: (candidate_maximum_abs_inl[index], candidate_measured_step_count[index]),
    )
    selected_measured_step_count = int(candidate_measured_step_count[selected_index])

    # Refit the already-selected model on every even calibration cycle.  Odd
    # cycles remain held out and are used only below for final metrics.
    extraction = _extract_prefix_thresholds(
        decisions,
        inferred_vin_diff_v,
        training,
        vin_diff_min_v=ramp.vin_diff_min_v,
        vin_diff_max_v=ramp.vin_diff_max_v,
    )
    selected_measured_step_count = min(
        selected_measured_step_count,
        _contiguous_resolved_count(extraction["step_resolved"]),
    )
    calibrated_weight = _hybrid_weights(
        nominal_weight,
        extraction["endpoint_weight_v"],
        selected_measured_step_count,
        code_max=code_max,
    )
    measured = np.zeros(decisions.shape[1], dtype=np.bool_)
    measured[:selected_measured_step_count] = True
    return AnalysisAdcCalibration(
        adc_index=adc_index,
        method="calibration3",
        label="Slow-ramp threshold weights",
        code_max=code_max,
        nominal_weight=nominal_weight,
        calibrated_weight=calibrated_weight,
        weight_from_measurement=measured,
        training_sample_count=int(np.count_nonzero(training)),
        validation_sample_count=int(np.count_nonzero(validation)),
        output_gain=1.0,
        output_offset_lsb=0.0,
    )
