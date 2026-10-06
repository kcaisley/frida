"""Calibration 3: slow-ramp SAR decision-threshold extraction.

This implements the foreground digital calibration described as Algorithm I
in Section 4.2 of Albert Hsu's 2013 dissertation.  It uses a known, slow ramp
and the stored BOUT decision word; it does not require a change to the
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

from flow.analysis import calc
from flow.analysis.types import AnalysisAdcCalibration, AnalysisAdcRamp, MeasAdc, check_identity


def analyze_adc_calibration3(measurement: MeasAdc, *, ramp: AnalysisAdcRamp) -> AnalysisAdcCalibration:
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
    return AnalysisAdcCalibration(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        method="calibration3",
        label="Slow-ramp threshold weights",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=calibrated_weight,
        measured_weight_mask=measured,
        training_sample_count=int(np.count_nonzero(training)),
        validation_sample_count=int(np.count_nonzero(validation)),
        output_gain=1.0,
        output_offset_lsb=0.0,
    )
