"""
ADC generator module for FRIDA.

Exports:
- Adc: Full ADC generator (composes digital + analog)
- AdcParams: ADC parameters
- Frida1AdcDigital: fabricated digital block with its explicit legacy boundary
"""

from .subckt import (
    Adc,
    AdcParams,
    Frida1AdcDigital,
)

__all__ = [
    "Adc",
    "AdcParams",
    "Frida1AdcDigital",
]
