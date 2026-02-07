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

from .cdac import (
    Cdac,
    CdacParams,
    get_cdac_n_bits,
    get_cdac_weights,
    is_valid_cdac_params,
)
from .test_cdac import CdacTb, CdacTbParams, sim_input

__all__ = [
    "Cdac",
    "CdacParams",
    "is_valid_cdac_params",
    "get_cdac_weights",
    "get_cdac_n_bits",
    "CdacTb",
    "CdacTbParams",
    "sim_input",
]
