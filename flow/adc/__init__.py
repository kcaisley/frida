"""
ADC generator module for FRIDA.

Exports:
- Adc: Full ADC generator (composes digital + analog)
- AdcParams: ADC parameters (every combination they admit builds)
"""

from .subckt import (
    Adc,
    AdcParams,
)

__all__ = [
    "Adc",
    "AdcParams",
]
