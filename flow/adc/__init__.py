"""
ADC generator module for FRIDA.

Exports:
- Adc: Full ADC generator (composes digital + analog)
- AdcParams: ADC parameters
- AdcDigital: ExternalModule for synthesized digital block
- get_adc_weights: Get capacitor weights for ADC configuration
- AdcTb: Testbench generator
- AdcTbParams: Testbench parameters
"""

from .subckt import (
    Adc,
    AdcDigital,
    AdcParams,
    get_adc_weights,
)
from .testbench import AdcTb, AdcTbParams, sim_input

__all__ = [
    "Adc",
    "AdcParams",
    "AdcDigital",
    "get_adc_weights",
    "AdcTb",
    "AdcTbParams",
    "sim_input",
]
