"""
Comparator generator module for FRIDA.

Exports:
- Comp: Comparator generator
- CompParams: Comparator parameters
- is_valid_comp_params: Validate parameter combinations
- CompTb: Testbench generator
- CompTbParams: Testbench parameters
"""

from .subckt import Comp, CompParams, is_valid_comp_params
from .testbench import CompTb, CompTbParams, sim_input

__all__ = [
    "Comp",
    "CompParams",
    "is_valid_comp_params",
    "CompTb",
    "CompTbParams",
    "sim_input",
]
