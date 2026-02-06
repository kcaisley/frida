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

from .adc import (
    Adc,
    AdcParams,
    AdcDigital,
    get_adc_weights,
)
from .test_adc import (
    AdcTb,
    AdcTbParams,
    run_transfer_function,
)

__all__ = [
    "Adc",
    "AdcParams",
    "AdcDigital",
    "get_adc_weights",
    "AdcTb",
    "AdcTbParams",
    "run_transfer_function",
]
