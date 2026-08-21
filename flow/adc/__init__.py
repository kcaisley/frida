"""
ADC generator module for FRIDA.

Exports:
- Adc: Full ADC generator (composes digital + analog)
- AdcParams: ADC parameters
- AdcDigital: ExternalModule for synthesized digital block
"""

from .subckt import (
    Adc,
    AdcDigital,
    AdcParams,
)

__all__ = [
    "Adc",
    "AdcDigital",
    "AdcParams",
]
