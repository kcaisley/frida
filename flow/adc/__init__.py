"""
ADC generator module for FRIDA.

Exports:
- Params: ADC parameters (every combination they admit builds)
- TbParams: the parameters of one generated testbench
- Adc: Full ADC generator (composes digital + analog)
"""

from .params import Params, TbParams
from .subckt import Adc

__all__ = [
    "Adc",
    "Params",
    "TbParams",
]
