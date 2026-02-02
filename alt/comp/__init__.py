"""
Comparator generator module for FRIDA.

Exports:
- Comp: Comparator generator
- CompParams: Comparator parameters
- comp_variants: Generate parameter sweep variants
- is_valid_comp_params: Validate parameter combinations
- CompTb: Testbench generator
- CompTbParams: Testbench parameters
"""

from .comp import Comp, CompParams, comp_variants, is_valid_comp_params
from .test_comp import CompTb, CompTbParams, sim_input, sim_input_with_mc

__all__ = [
    "Comp",
    "CompParams",
    "comp_variants",
    "is_valid_comp_params",
    "CompTb",
    "CompTbParams",
    "sim_input",
    "sim_input_with_mc",
]
