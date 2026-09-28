"""
ADC generator module for FRIDA.

Exports:
- Adc: Full ADC generator (composes digital + analog)
- AdcParams: ADC parameters
- is_valid_adc_params: Validate parameter combinations
"""

from .subckt import (
    Adc,
    AdcParams,
    is_valid_adc_params,
)

__all__ = [
    "Adc",
    "AdcParams",
    "is_valid_adc_params",
]
