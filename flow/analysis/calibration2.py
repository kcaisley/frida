"""Calibration 2: known-stimulus regression of BOUT weights.

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
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import lsq_linear

from flow.analysis import calc
from flow.analysis.types import AnalysisAdcCalibration, AnalysisAdcRamp, MeasAdc, check_identity


def analyze_adc_calibration2(measurement: MeasAdc, *, ramp: AnalysisAdcRamp) -> AnalysisAdcCalibration:
    """Fit every BOUT coefficient from complete known-ramp cycles.

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
    # Candidate strengths from no prior to the mild 2% default, spaced roughly
    # by factors of five, cover the useful regularization range.
    candidates = (0.0, 0.0001, 0.001, 0.005, 0.02)

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
        unique_bout, inverse, word_count = np.unique(
            decisions[fit_mask], axis=0, return_inverse=True, return_counts=True
        )
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
            lsmr_tol="auto",
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

    return AnalysisAdcCalibration(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        method="calibration2",
        label="Known-ramp fitted weights",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=normalized_weights,
        measured_weight_mask=np.ones(decision_count, dtype=np.bool_),
        training_sample_count=int(np.count_nonzero(training)),
        validation_sample_count=int(np.count_nonzero(validation)),
        output_gain=output_gain,
        output_offset_lsb=output_intercept_lsb,
    )
