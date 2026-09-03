"""
Capacitor DAC generator module for FRIDA.

Exports:
- Cdac: CDAC generator
- CdacArray: passive main/diff capacitor-array generator
- CdacParams: CDAC parameters
- is_valid_cdac_params: Validate parameter combinations
- get_cdac_weights: Get capacitor weights for configuration
"""

from .subckt import (
    CapType,
    Cdac,
    CdacArray,
    CdacArrayParams,
    CdacParams,
    RedunStrat,
    SplitStrat,
    get_cdac_weights,
    is_valid_cdac_array_params,
    is_valid_cdac_params,
)

__all__ = [
    "CapType",
    "Cdac",
    "CdacArray",
    "CdacArrayParams",
    "CdacParams",
    "RedunStrat",
    "SplitStrat",
    "get_cdac_weights",
    "is_valid_cdac_array_params",
    "is_valid_cdac_params",
]
