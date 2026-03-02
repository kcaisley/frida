"""Smoke tests for the ADC generator."""

import numpy as np

from .subckt import Adc, AdcParams, get_adc_weights


def test_adc():
    """Verify ADC generator produces a valid module."""
    m = Adc(AdcParams())
    assert m is not None


def test_adc_weights():
    """Test ADC weight calculation with SUBRDX2_OVLY strategy."""
    params = AdcParams()
    weights = get_adc_weights(params)

    assert len(weights) == 16
    assert weights.sum() == 2047
    assert weights[0] == 768

    expected = np.array([768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1])
    np.testing.assert_array_equal(weights, expected)
