"""Tests for calibration 2, the known-ramp BOUT weight regression."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from flow.analysis.adc import analyze_adc_ramp
from flow.analysis.calibration2 import analyze_adc_calibration2
from flow.analysis.test_adc import adc_ramp_measurement

CODE_MAX = 4095


def perturbed_ramp_measurement(true_weights: np.ndarray, *, cycles: int = 8, samples_per_cycle: int = 4_096):
    """Return a linear ramp whose BOUT words were decided with ``true_weights``.

    DOUT is still decoded with the nominal weights, as the hardware does, so
    the analysis must recover ``true_weights`` from the known ramp alone.
    """

    template = adc_ramp_measurement(cycles=cycles)
    nominal = template.nominal_bout_weights
    remaining = np.linspace(0.0, np.sum(true_weights), samples_per_cycle)
    one_cycle = np.zeros((samples_per_cycle, len(nominal)), dtype=np.uint8)
    for decision, weight in enumerate(true_weights):
        one_cycle[:, decision] = remaining >= weight
        remaining -= one_cycle[:, decision] * weight
    bout = np.tile(one_cycle, (cycles, 1))
    dout_raw = bout.astype(np.int64) @ nominal
    return replace(
        template,
        conversion_index=template.conversion_index,
        bout=bout,
        dout_raw=dout_raw,
        dout=np.rint(dout_raw * CODE_MAX / np.sum(nominal)).astype(np.int64),
        vin_diff_v=template.vin_diff_v,
    )


def test_calibration2_public_analysis_returns_common_weights() -> None:
    measurement = adc_ramp_measurement(cycles=8)
    ramp = analyze_adc_ramp(measurement)

    result = analyze_adc_calibration2(measurement, ramp=ramp)

    assert result.method == "calibration2"
    assert (result.group, result.index, result.dut) == (7, 0, measurement.dut)
    assert result.calibrated_weights.shape == (17,)
    assert np.sum(result.calibrated_weights) == pytest.approx(CODE_MAX)
    assert np.all(result.measured_weight_mask)
    assert result.training_sample_count > 0
    assert result.validation_sample_count > 0


def test_calibration2_recovers_known_perturbed_weights() -> None:
    nominal = adc_ramp_measurement().nominal_bout_weights.astype(np.float64)
    perturbation = np.asarray(
        [1.002, 0.998, 1.004, 0.997, 1.003, 0.996, 1.005, 0.995, 1.006, 0.994, 1.01, 0.99, 1.01, 0.98, 1.02, 0.97, 1.03]
    )
    true_weights = nominal * perturbation
    measurement = perturbed_ramp_measurement(true_weights)

    result = analyze_adc_calibration2(measurement, ramp=analyze_adc_ramp(measurement))

    expected = true_weights * CODE_MAX / np.sum(true_weights)
    # The large weights dominate the fit; recover them to a fraction of one code.
    np.testing.assert_allclose(result.calibrated_weights[:8], expected[:8], atol=0.5)
    assert np.max(np.abs(result.calibrated_weights - expected)) < np.max(np.abs(result.nominal_weights - expected))


def test_validation_cycles_cannot_change_the_fit() -> None:
    measurement = adc_ramp_measurement(cycles=8)
    ramp = analyze_adc_ramp(measurement)
    reference = analyze_adc_calibration2(measurement, ramp=ramp)

    # Corrupt every odd (validation) cycle's decisions, keeping DOUT consistent.
    odd = (ramp.cycle_index % 2) == 1
    bout = measurement.bout.copy()
    bout[odd] = 1 - bout[odd]
    dout_raw = bout.astype(np.int64) @ measurement.nominal_bout_weights
    changed = replace(
        measurement,
        bout=bout,
        dout_raw=dout_raw,
        dout=np.rint(dout_raw * CODE_MAX / np.sum(measurement.nominal_bout_weights)).astype(np.int64),
    )
    result = analyze_adc_calibration2(changed, ramp=ramp)

    np.testing.assert_array_equal(result.calibrated_weights, reference.calibrated_weights)
    assert result.output_gain == reference.output_gain
    assert result.output_offset_lsb == reference.output_offset_lsb
