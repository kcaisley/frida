"""Calibration 2: known-stimulus regression of FRIDA BOUT weights.

This method leaves the analog ADC unchanged and uses the stored 17-bit BOUT
word to produce a corrected digital output. The extraction is reference
assisted: the repeated ADC ramp supplies a known ideal code. Once the weights
have been extracted, applying them is purely a digital backend or offline
operation. Complete even-numbered cycles are used for fitting and complete
odd-numbered cycles are reserved for validation. The default ridge strength is
dimensionless: ``0.02`` adds a prior penalty equivalent to roughly two percent
of one observation per fitted weight. It is deliberately mild and is selected
on an inner split of the training cycles before production use.

The code-density helper similarly requires a known-uniform training stimulus.
It returns a fractional mapping.  Rounding that mapping to twelve bits can
collapse adjacent outputs: a monotone, onto 12-bit-to-12-bit LUT has to be the
identity and therefore cannot correct INL while preserving every output code.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import lsq_linear

from flow.analysis.adc import ADC_RAMP_RESET_EXCLUSION_CONVERSIONS
from flow.analysis.types import AnalysisAdcCalibration, AnalysisAdcRamp, MeasAdc, MeasAdcExt

type FloatArray = NDArray[np.float64]
type IntArray = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]

ADC_BOUT_BITS = 17
ADC_NUMBER_CODES = 4096
ADC_CODE_MAX = ADC_NUMBER_CODES - 1
DEFAULT_RIDGE_STRENGTH = 0.02
RIDGE_STRENGTH_CANDIDATES = (0.0, 0.0001, 0.001, 0.005, 0.02)
FRIDA_NOMINAL_BOUT_WEIGHTS = (
    1536.0,
    1024.0,
    640.0,
    384.0,
    192.0,
    128.0,
    64.0,
    48.0,
    24.0,
    20.0,
    10.0,
    8.0,
    8.0,
    4.0,
    2.0,
    2.0,
    1.0,
)


def analyze(
    measurement: MeasAdc,
    ramp: AnalysisAdcRamp,
    *,
    ridge_strength: float | None = None,
) -> AnalysisAdcCalibration:
    """Fit all 17 BOUT coefficients from complete known-ramp cycles.

    Ramp phase supplies the ideal fractional code. Complete even cycles train
    the weights and complete odd cycles remain untouched validation data.
    Endpoint-clipped conversions are excluded from fitting because their BOUT
    word no longer identifies where the input lies beyond the ADC range.
    """

    params = measurement.param.tb if isinstance(measurement, MeasAdcExt) else measurement.param
    adc_index = (
        -1
        if not isinstance(measurement, MeasAdcExt) or measurement.param.observed_adc is None
        else measurement.param.observed_adc
    )
    if ramp.adc_index != adc_index or ramp.sample_count != len(measurement.daq.bout):
        raise ValueError("calibration 2 requires the matching ADC ramp analysis")
    sample = np.arange(ramp.sample_count, dtype=np.float64)
    reset_number = np.arange(len(ramp.reset_conversion_index), dtype=np.float64)
    period_samples, first_reset_sample = np.linalg.lstsq(
        np.column_stack((reset_number, np.ones(len(reset_number)))),
        ramp.reset_conversion_index.astype(np.float64),
        rcond=None,
    )[0]
    phase = np.mod((sample - first_reset_sample) / period_samples, 1.0)
    code_max = (1 << params.dut.adc_bits) - 1
    ideal_dout = phase * code_max
    cycle_index = np.floor((sample - first_reset_sample) / period_samples).astype(np.int64)
    retained = (cycle_index >= 0) & (cycle_index < len(ramp.reset_conversion_index) - 1)
    for reset_index in ramp.reset_conversion_index:
        retained[max(0, reset_index - 1) : reset_index + ADC_RAMP_RESET_EXCLUSION_CONVERSIONS] = False
    retained &= (measurement.daq.dout > 0) & (measurement.daq.dout < code_max)

    nominal_weight = np.asarray(ramp.curves[0].weights, dtype=np.float64)
    nominal_weight *= code_max / np.sum(nominal_weight)
    if ridge_strength is None:
        ridge_strength = select_empirical_ridge_strength(
            measurement.daq.bout,
            ideal_dout,
            cycle_index,
            retained,
            nominal_weights=nominal_weight,
            code_max=code_max,
        )
    fit = fit_empirical_bout_calibration(
        measurement.daq.bout,
        ideal_dout,
        cycle_index,
        retained,
        nominal_weights=nominal_weight,
        ridge_strength=ridge_strength,
        code_max=code_max,
    )
    return AnalysisAdcCalibration(
        adc_index=adc_index,
        method="calibration2",
        label="Known-ramp fitted weights",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=fit.normalized_weights,
        measured_weight_mask=np.ones(ADC_BOUT_BITS, dtype=np.bool_),
        training_sample_count=fit.diagnostics.training_sample_count,
        validation_sample_count=fit.diagnostics.validation_sample_count,
        output_gain=fit.output_gain,
        output_offset_lsb=fit.output_intercept_lsb,
    )


@dataclass(frozen=True, slots=True)
class AdcCalibrationDiagnostics:
    """Fit quality from cycle-disjoint training and validation samples."""

    training_cycles: IntArray
    validation_cycles: IntArray
    training_sample_count: int
    validation_sample_count: int
    unique_training_word_count: int
    ridge_strength: float
    ridge_penalty_scale: float
    design_rank: int
    design_condition: float
    solver_cost: float
    training_rmse_lsb: float
    validation_rmse_lsb: float
    training_maximum_abs_error_lsb: float
    validation_maximum_abs_error_lsb: float


@dataclass(frozen=True, slots=True)
class AdcCalibrationResult:
    """One constrained BOUT calibration evaluated over all supplied samples.

    ``normalized_weights`` sum to ``code_max`` and define the reported
    full-scale-normalized calibrated output.  ``output_gain`` and
    ``output_intercept_lsb`` separately preserve the global affine fit made on
    training cycles only:

    ``ideal_prediction = output_intercept_lsb + output_gain * fractional_dout``.

    Keeping gain and offset separate prevents their removal from needlessly
    collapsing codes in the normalized 12-bit output.
    """

    normalized_weights: FloatArray
    output_gain: float
    output_intercept_lsb: float
    fractional_dout: FloatArray
    rounded_dout: IntArray
    training_mask: BoolArray
    validation_mask: BoolArray
    diagnostics: AdcCalibrationDiagnostics


@dataclass(frozen=True, slots=True)
class AdcCodeDensityCdfLut:
    """Fractional code mapping learned from a known-uniform training input."""

    count: IntArray
    fractional_mapping: FloatArray
    first_code: int
    last_code: int

    def decode(self, raw_dout: Sequence[int] | IntArray) -> FloatArray:
        """Apply the fractional mapping without prematurely rounding it."""

        raw = np.asarray(raw_dout)
        if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.integer):
            raise ValueError("raw DOUT must be a one-dimensional integer array")
        raw = np.asarray(raw, dtype=np.int64)
        if np.any((raw < 0) | (raw >= len(self.fractional_mapping))):
            raise ValueError(f"raw DOUT must fit within 0..{len(self.fractional_mapping) - 1}")
        return np.asarray(self.fractional_mapping[raw], dtype=np.float64)


def _aligned_calibration_inputs(
    bout: Sequence[Sequence[int]] | NDArray[np.integer],
    ideal_dout: Sequence[float] | FloatArray,
    cycle_index: Sequence[int] | IntArray,
    retained: Sequence[bool] | BoolArray,
) -> tuple[NDArray[np.uint8], FloatArray, IntArray, BoolArray]:
    """Normalize and validate the arrays shared by the empirical fit."""

    decisions = np.asarray(bout)
    target = np.asarray(ideal_dout, dtype=np.float64)
    cycles_input = np.asarray(cycle_index)
    keep_input = np.asarray(retained)
    if decisions.ndim != 2 or decisions.shape[1] != ADC_BOUT_BITS:
        raise ValueError(f"BOUT must have shape (samples, {ADC_BOUT_BITS})")
    if np.any((decisions != 0) & (decisions != 1)):
        raise ValueError("BOUT must contain only zero and one")
    if target.ndim != 1 or not np.all(np.isfinite(target)):
        raise ValueError("ideal DOUT must be a finite one-dimensional array")
    if cycles_input.ndim != 1 or not np.issubdtype(cycles_input.dtype, np.integer):
        raise ValueError("cycle index must be a one-dimensional integer array")
    if keep_input.ndim != 1 or not np.issubdtype(keep_input.dtype, np.bool_):
        raise ValueError("retained must be a one-dimensional boolean mask")
    lengths = {len(decisions), len(target), len(cycles_input), len(keep_input)}
    if len(lengths) != 1:
        raise ValueError("BOUT, ideal DOUT, cycle index, and retained mask must be aligned")
    return (
        np.asarray(decisions, dtype=np.uint8),
        target,
        np.asarray(cycles_input, dtype=np.int64),
        np.asarray(keep_input, dtype=np.bool_),
    )


def _cycle_disjoint_masks(cycle_index: IntArray, retained: BoolArray) -> tuple[BoolArray, BoolArray]:
    """Assign every retained even cycle to training and every odd cycle to validation."""

    training = retained & ((cycle_index % 2) == 0)
    validation = retained & ((cycle_index % 2) != 0)
    if not np.any(training):
        raise ValueError("empirical calibration requires retained samples from an even training cycle")
    if not np.any(validation):
        raise ValueError("empirical calibration requires retained samples from an odd validation cycle")
    return training, validation


def fit_empirical_bout_calibration(
    bout: Sequence[Sequence[int]] | NDArray[np.integer],
    ideal_dout: Sequence[float] | FloatArray,
    cycle_index: Sequence[int] | IntArray,
    retained: Sequence[bool] | BoolArray,
    *,
    nominal_weights: Sequence[float] | FloatArray = FRIDA_NOMINAL_BOUT_WEIGHTS,
    ridge_strength: float = DEFAULT_RIDGE_STRENGTH,
    code_max: int = ADC_CODE_MAX,
) -> AdcCalibrationResult:
    """Fit nonnegative effective BOUT weights without validation-cycle leakage.

    The minimized training objective is

    ``sum((ideal - intercept - BOUT @ weight)**2)``
    ``+ ridge_strength * N_train / 17 * sum((weight - nominal)**2)``.

    Duplicate training words are compressed to weighted means before solving;
    this is algebraically equivalent for the fitted parameters.  Validation
    targets are used only after the solver and global affine decomposition have
    been fixed from training data.
    """

    decisions, target, cycles, keep = _aligned_calibration_inputs(bout, ideal_dout, cycle_index, retained)
    if not isinstance(code_max, int) or code_max <= 0:
        raise ValueError("code maximum must be a positive integer")
    if not math.isfinite(ridge_strength) or ridge_strength < 0.0:
        raise ValueError("ridge strength must be finite and nonnegative")
    prior = np.asarray(nominal_weights, dtype=np.float64)
    if prior.shape != (ADC_BOUT_BITS,) or not np.all(np.isfinite(prior)) or np.any(prior < 0.0):
        raise ValueError(f"nominal weights must contain {ADC_BOUT_BITS} finite nonnegative values")
    if float(np.sum(prior)) <= 0.0:
        raise ValueError("nominal weights must have a positive sum")
    prior = prior * code_max / np.sum(prior)

    training, validation = _cycle_disjoint_masks(cycles, keep)
    training_bout = decisions[training]
    training_target = target[training]

    unique_bout, inverse, word_count = np.unique(
        training_bout,
        axis=0,
        return_inverse=True,
        return_counts=True,
    )
    word_target = np.bincount(inverse, weights=training_target) / word_count
    sqrt_count = np.sqrt(word_count.astype(np.float64))
    design = np.column_stack((np.ones(len(unique_bout)), unique_bout.astype(np.float64)))
    weighted_design = design * sqrt_count[:, None]
    weighted_target = word_target * sqrt_count

    ridge_penalty_scale = ridge_strength * len(training_target) / ADC_BOUT_BITS
    if ridge_penalty_scale:
        prior_design = np.zeros((ADC_BOUT_BITS, ADC_BOUT_BITS + 1), dtype=np.float64)
        prior_design[:, 1:] = np.eye(ADC_BOUT_BITS) * math.sqrt(ridge_penalty_scale)
        weighted_design = np.vstack((weighted_design, prior_design))
        weighted_target = np.concatenate((weighted_target, math.sqrt(ridge_penalty_scale) * prior))

    lower_bound = np.concatenate(([-np.inf], np.zeros(ADC_BOUT_BITS)))
    upper_bound = np.full(ADC_BOUT_BITS + 1, np.inf)
    fit = lsq_linear(
        weighted_design,
        weighted_target,
        bounds=(lower_bound, upper_bound),
        lsmr_tol="auto",
    )
    if not fit.success:
        raise RuntimeError(f"empirical BOUT calibration failed: {fit.message}")
    fitted_weights = np.asarray(fit.x[1:], dtype=np.float64)
    fitted_sum = float(np.sum(fitted_weights))
    if not math.isfinite(fitted_sum) or fitted_sum <= 0.0:
        raise RuntimeError("empirical BOUT calibration produced no positive weight sum")

    normalized_weights = fitted_weights * code_max / fitted_sum
    output_gain = fitted_sum / code_max
    output_intercept_lsb = float(fit.x[0])
    fractional_dout = decisions @ normalized_weights
    rounded_dout = np.clip(np.rint(fractional_dout), 0, code_max).astype(np.int64)

    ideal_prediction = output_intercept_lsb + output_gain * fractional_dout
    residual = ideal_prediction - target
    training_error = residual[training]
    validation_error = residual[validation]
    centered_bout = unique_bout.astype(np.float64) - np.average(
        unique_bout,
        axis=0,
        weights=word_count,
    )
    weighted_centered_bout = centered_bout * sqrt_count[:, None]
    singular_values = np.linalg.svd(weighted_centered_bout, compute_uv=False)
    design_rank = int(np.linalg.matrix_rank(weighted_centered_bout))
    design_condition = (
        float(singular_values[0] / singular_values[-1])
        if design_rank == ADC_BOUT_BITS and singular_values[-1] > 0.0
        else math.inf
    )
    diagnostics = AdcCalibrationDiagnostics(
        training_cycles=np.unique(cycles[training]),
        validation_cycles=np.unique(cycles[validation]),
        training_sample_count=len(training_error),
        validation_sample_count=len(validation_error),
        unique_training_word_count=len(unique_bout),
        ridge_strength=ridge_strength,
        ridge_penalty_scale=ridge_penalty_scale,
        design_rank=design_rank,
        design_condition=design_condition,
        solver_cost=float(fit.cost),
        training_rmse_lsb=float(np.sqrt(np.mean(np.square(training_error)))),
        validation_rmse_lsb=float(np.sqrt(np.mean(np.square(validation_error)))),
        training_maximum_abs_error_lsb=float(np.max(np.abs(training_error))),
        validation_maximum_abs_error_lsb=float(np.max(np.abs(validation_error))),
    )
    return AdcCalibrationResult(
        normalized_weights=normalized_weights,
        output_gain=output_gain,
        output_intercept_lsb=output_intercept_lsb,
        fractional_dout=np.asarray(fractional_dout, dtype=np.float64),
        rounded_dout=rounded_dout,
        training_mask=training,
        validation_mask=validation,
        diagnostics=diagnostics,
    )


def select_empirical_ridge_strength(
    bout: Sequence[Sequence[int]] | NDArray[np.integer],
    ideal_dout: Sequence[float] | FloatArray,
    cycle_index: Sequence[int] | IntArray,
    retained: Sequence[bool] | BoolArray,
    *,
    candidates: Sequence[float] = RIDGE_STRENGTH_CANDIDATES,
    nominal_weights: Sequence[float] | FloatArray = FRIDA_NOMINAL_BOUT_WEIGHTS,
    code_max: int = ADC_CODE_MAX,
) -> float:
    """Choose ridge strength using an inner split of outer training cycles.

    The outer even cycles are renumbered consecutively and split again. Outer
    odd validation cycles never enter this selection.
    """

    decisions, target, cycles, keep = _aligned_calibration_inputs(bout, ideal_dout, cycle_index, retained)
    outer_training = keep & ((cycles % 2) == 0)
    even_cycles = np.unique(cycles[outer_training])
    if len(even_cycles) < 2:
        raise ValueError("ridge selection requires at least two retained outer training cycles")
    inner_cycle = np.full(len(cycles), -1, dtype=np.int64)
    for inner_index, cycle in enumerate(even_cycles):
        inner_cycle[cycles == cycle] = inner_index
    strengths = tuple(float(candidate) for candidate in candidates)
    if not strengths:
        raise ValueError("ridge selection requires at least one candidate")
    results = [
        fit_empirical_bout_calibration(
            decisions,
            target,
            inner_cycle,
            outer_training,
            nominal_weights=nominal_weights,
            ridge_strength=strength,
            code_max=code_max,
        )
        for strength in strengths
    ]
    best = min(
        zip(strengths, results, strict=True),
        key=lambda item: (item[1].diagnostics.validation_rmse_lsb, item[0]),
    )
    return best[0]


def fit_code_density_cdf_lut(
    raw_dout: Sequence[int] | IntArray,
    training_mask: Sequence[bool] | BoolArray,
    *,
    number_codes: int = ADC_NUMBER_CODES,
    first_code: int = 1,
    last_code: int | None = None,
) -> AdcCodeDensityCdfLut:
    """Fit a fractional CDF LUT from known-uniform training samples only.

    The midpoint of each code's empirical probability mass is mapped to the
    corresponding ideal code-center coordinate.  With exactly uniform counts,
    the active part of the LUT is therefore the identity.  Endpoint codes are
    excluded by default because a finite ramp generally clips into them.
    """

    raw_input = np.asarray(raw_dout)
    mask_input = np.asarray(training_mask)
    if raw_input.ndim != 1 or not np.issubdtype(raw_input.dtype, np.integer):
        raise ValueError("raw DOUT must be a one-dimensional integer array")
    if mask_input.ndim != 1 or not np.issubdtype(mask_input.dtype, np.bool_):
        raise ValueError("training mask must be a one-dimensional boolean array")
    if len(raw_input) != len(mask_input):
        raise ValueError("raw DOUT and training mask must be aligned")
    if not isinstance(number_codes, int) or number_codes < 3:
        raise ValueError("number of codes must be an integer of at least three")
    raw = np.asarray(raw_input, dtype=np.int64)
    mask = np.asarray(mask_input, dtype=np.bool_)
    if not np.any(mask):
        raise ValueError("code-density LUT requires at least one training sample")
    if np.any((raw < 0) | (raw >= number_codes)):
        raise ValueError(f"raw DOUT must fit within 0..{number_codes - 1}")
    last_code = number_codes - 2 if last_code is None else last_code
    if not 0 <= first_code <= last_code < number_codes:
        raise ValueError(f"active code range must fit within 0..{number_codes - 1}")

    count = np.bincount(raw[mask], minlength=number_codes).astype(np.int64)
    active_count = count[first_code : last_code + 1]
    total = int(np.sum(active_count))
    if total <= 0:
        raise ValueError("code-density LUT active range contains no training samples")
    cumulative_midpoint = np.cumsum(active_count, dtype=np.float64) - 0.5 * active_count
    active_code_count = last_code - first_code + 1
    mapping = np.arange(number_codes, dtype=np.float64)
    mapping[first_code : last_code + 1] = first_code - 0.5 + active_code_count * cumulative_midpoint / total
    return AdcCodeDensityCdfLut(
        count=count,
        fractional_mapping=mapping,
        first_code=first_code,
        last_code=last_code,
    )
