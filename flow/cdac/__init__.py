"""
Capacitor DAC generator module for FRIDA.

Exports:
- Cdac: CDAC generator
- CdacParams: CDAC parameters
- is_valid_cdac_params: Validate parameter combinations
- get_cdac_weights: Get capacitor weights for configuration
"""

from .subckt import (
    CapType,
    Cdac,
    CdacParams,
    RedunStrat,
    SplitStrat,
    get_cdac_weights,
    is_valid_cdac_params,
)

__all__ = [
    "CapType",
    "Cdac",
    "CdacParams",
    "RedunStrat",
    "SplitStrat",
    "get_cdac_weights",
    "is_valid_cdac_params",
]
