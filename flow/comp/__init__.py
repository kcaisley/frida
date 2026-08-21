"""
Comparator generator module for FRIDA.

Exports:
- Comp: Comparator generator
- CompParams: Comparator parameters
- is_valid_comp_params: Validate parameter combinations
"""

from .subckt import Comp, CompParams, is_valid_comp_params

__all__ = [
    "Comp",
    "CompParams",
    "is_valid_comp_params",
]
