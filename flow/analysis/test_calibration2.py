"""Tests for calibration 2 from cycle-disjoint known-stimulus fitting."""

from __future__ import annotations

import numpy as np
import pytest

from flow.analysis.adc import analyze_adc_ramp
from flow.analysis.calibration2 import (
    ADC_CODE_MAX,
    FRIDA_NOMINAL_BOUT_WEIGHTS,
    analyze,
    fit_code_density_cdf_lut,
    fit_empirical_bout_calibration,
    select_empirical_ridge_strength,
)
from flow.analysis.test_adc import adc_ramp_measurement


def synthetic_calibration_data():
    """Build repeatable noisy decision words with known effective weights."""

    rng = np.random.default_rng(20260812)
    samples_per_cycle = 2_000
    cycle_index = np.repeat(np.arange(12, dtype=np.int64), samples_per_cycle)
    bout = rng.integers(0, 2, size=(len(cycle_index), 17), dtype=np.uint8)
    nominal = np.asarray(FRIDA_NOMINAL_BOUT_WEIGHTS)
    perturbation = np.asarray(
        [1.002, 0.998, 1.004, 0.997, 1.003, 0.996, 1.005, 0.995, 1.006, 0.994, 1.01, 0.99, 1.01, 0.98, 1.02, 0.97, 1.03]
    )
    true_weights = nominal * perturbation
    true_weights *= ADC_CODE_MAX / np.sum(true_weights)
    ideal_dout = 2.75 + 0.998 * (bout @ true_weights) + rng.normal(0.0, 0.05, len(cycle_index))
    retained = np.ones(len(cycle_index), dtype=np.bool_)
    retained[::101] = False
    return bout, ideal_dout, cycle_index, retained, true_weights


def test_empirical_calibration_recovers_synthetic_weights() -> None:
    bout, ideal_dout, cycle_index, retained, true_weights = synthetic_calibration_data()

    result = fit_empirical_bout_calibration(bout, ideal_dout, cycle_index, retained)

    np.testing.assert_allclose(result.normalized_weights, true_weights, atol=0.025)
    assert result.output_gain == pytest.approx(0.998, abs=2.0e-5)
    assert result.output_intercept_lsb == pytest.approx(2.75, abs=0.03)
    assert result.diagnostics.validation_rmse_lsb < 0.06
    assert result.diagnostics.design_rank == 17
    assert np.isfinite(result.diagnostics.design_condition)


def test_empirical_calibration_splits_complete_cycles_and_enforces_weights() -> None:
    bout, ideal_dout, cycle_index, retained, _ = synthetic_calibration_data()

    result = fit_empirical_bout_calibration(bout, ideal_dout, cycle_index, retained)

    np.testing.assert_array_equal(result.training_mask, retained & ((cycle_index % 2) == 0))
    np.testing.assert_array_equal(result.validation_mask, retained & ((cycle_index % 2) == 1))
    np.testing.assert_array_equal(result.diagnostics.training_cycles, np.arange(0, 12, 2))
    np.testing.assert_array_equal(result.diagnostics.validation_cycles, np.arange(1, 12, 2))
    assert not np.any(result.training_mask & result.validation_mask)
    assert np.all(result.normalized_weights >= 0.0)
    assert np.sum(result.normalized_weights) == pytest.approx(ADC_CODE_MAX, abs=1.0e-10)
    assert result.fractional_dout.shape == ideal_dout.shape
    assert result.rounded_dout.dtype == np.int64
    assert np.all((result.rounded_dout >= 0) & (result.rounded_dout <= ADC_CODE_MAX))


def test_validation_targets_cannot_change_training_fit() -> None:
    bout, ideal_dout, cycle_index, retained, _ = synthetic_calibration_data()
    changed_validation = ideal_dout.copy()
    changed_validation[(cycle_index % 2) == 1] += 1_000.0

    reference = fit_empirical_bout_calibration(bout, ideal_dout, cycle_index, retained)
    changed = fit_empirical_bout_calibration(bout, changed_validation, cycle_index, retained)

    np.testing.assert_array_equal(changed.normalized_weights, reference.normalized_weights)
    assert changed.output_gain == reference.output_gain
    assert changed.output_intercept_lsb == reference.output_intercept_lsb
    np.testing.assert_array_equal(changed.fractional_dout, reference.fractional_dout)
    assert changed.diagnostics.validation_rmse_lsb > 900.0


def test_code_density_cdf_lut_is_fractional_and_uses_training_only() -> None:
    count = np.arange(1, 17, dtype=np.int64)
    raw_dout = np.repeat(np.arange(16, dtype=np.int64), count)
    training = np.ones(len(raw_dout), dtype=np.bool_)
    training[-count[-1] :] = False

    lut = fit_code_density_cdf_lut(
        raw_dout,
        training,
        number_codes=16,
        first_code=1,
        last_code=14,
    )

    assert lut.count[-1] == 0
    assert lut.fractional_mapping[0] == 0.0
    assert lut.fractional_mapping[-1] == 15.0
    assert np.all(np.diff(lut.fractional_mapping[1:15]) > 0.0)
    assert np.any(lut.fractional_mapping[1:15] % 1.0 != 0.0)
    np.testing.assert_array_equal(
        lut.decode(np.asarray([0, 7, 15], dtype=np.int64)),
        lut.fractional_mapping[[0, 7, 15]],
    )


def test_uniform_cdf_is_identity_and_integer_lossless_lut_cannot_correct() -> None:
    raw_dout = np.tile(np.arange(16, dtype=np.int64), 20)
    training = np.ones(len(raw_dout), dtype=np.bool_)
    lut = fit_code_density_cdf_lut(
        raw_dout,
        training,
        number_codes=16,
        first_code=0,
        last_code=15,
    )

    np.testing.assert_allclose(lut.fractional_mapping, np.arange(16), atol=1.0e-12)

    # For a monotone 16-entry integer LUT to contain all 16 outputs, its 15
    # successive steps must each be at least one and sum to only 15.  Hence
    # every step is exactly one and the LUT is necessarily the identity.
    lossless_monotone_lut = np.sort(np.random.default_rng(1).permutation(16))
    assert len(np.unique(lossless_monotone_lut)) == 16
    assert np.all(np.diff(lossless_monotone_lut) >= 1)
    np.testing.assert_array_equal(lossless_monotone_lut, np.arange(16))


def test_calibration2_public_analysis_returns_common_weights() -> None:
    measurement = adc_ramp_measurement(cycles=8)
    ramp = analyze_adc_ramp(measurement)

    result = analyze(measurement, ramp, ridge_strength=0.02)

    assert result.method == "calibration2"
    assert result.adc_index == 0
    assert result.calibrated_weights.shape == (17,)
    assert np.sum(result.calibrated_weights) == pytest.approx(ADC_CODE_MAX)
    assert np.all(result.measured_weight_mask)
    assert result.training_sample_count > 0
    assert result.validation_sample_count > 0


def test_clipped_endpoint_paths_must_be_removed_before_empirical_fit() -> None:
    bout, ideal_dout, cycle_index, retained, _ = synthetic_calibration_data()
    bout[:200] = 0
    ideal_dout[:200] = np.linspace(-1_000.0, 0.0, 200)
    active_transfer = np.ones(len(retained), dtype=np.bool_)
    active_transfer[:200] = False

    reference = fit_empirical_bout_calibration(
        bout[200:],
        ideal_dout[200:],
        cycle_index[200:],
        retained[200:],
    )
    filtered = fit_empirical_bout_calibration(
        bout,
        ideal_dout,
        cycle_index,
        retained & active_transfer,
    )

    np.testing.assert_array_equal(filtered.normalized_weights, reference.normalized_weights)
    assert filtered.output_gain == reference.output_gain
    assert filtered.output_intercept_lsb == reference.output_intercept_lsb


def test_ridge_selection_never_reads_outer_validation_cycles() -> None:
    bout, ideal_dout, cycle_index, retained, _ = synthetic_calibration_data()
    changed_validation = ideal_dout.copy()
    changed_validation[(cycle_index % 2) == 1] += 1_000.0

    reference = select_empirical_ridge_strength(
        bout,
        ideal_dout,
        cycle_index,
        retained,
        candidates=(0.0, 0.001, 0.02),
    )
    changed = select_empirical_ridge_strength(
        bout,
        changed_validation,
        cycle_index,
        retained,
        candidates=(0.0, 0.001, 0.02),
    )

    assert changed == reference
