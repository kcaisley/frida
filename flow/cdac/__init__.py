"""
Capacitor DAC generator module for FRIDA.

Exports:
- Cdac: CDAC generator
- CdacParams: CDAC parameters
- is_valid_cdac_params: Validate parameter combinations
- get_cdac_weights: Get capacitor weights for configuration
- get_cdac_n_bits: Get number of physical bits
- CdacTb: Testbench generator
- CdacTbParams: Testbench parameters
"""

from .subckt import (
    CapType,
    Cdac,
    CdacParams,
    RedunStrat,
    SplitStrat,
    get_cdac_n_bits,
    get_cdac_weights,
    is_valid_cdac_params,
)

__all__ = [
    "CapType",
    "Cdac",
    "CdacParams",
    "CdacTb",
    "CdacTbParams",
    "RedunStrat",
    "SplitStrat",
    "get_cdac_n_bits",
    "get_cdac_weights",
    "is_valid_cdac_params",
    "sim_input",
]


def __getattr__(name: str):
    if name in {"CdacTb", "CdacTbParams", "sim_input"}:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.testbench"), name)
    raise AttributeError(name)
