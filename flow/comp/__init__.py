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

__all__ = [
    "Comp",
    "CompParams",
    "CompTb",
    "CompTbParams",
    "is_valid_comp_params",
    "sim_input",
]


def __getattr__(name: str):
    if name in {"CompTb", "CompTbParams", "sim_input"}:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.sim"), name)
    raise AttributeError(name)
