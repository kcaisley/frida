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

__all__ = [
    "Adc",
    "AdcDigital",
    "AdcParams",
    "AdcTb",
    "AdcTbParams",
    "get_adc_weights",
    "sim_input",
]


def __getattr__(name: str):
    if name in {"AdcTb", "AdcTbParams", "sim_input"}:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.testbench"), name)
    raise AttributeError(name)
