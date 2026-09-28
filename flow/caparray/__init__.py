"""
Capacitor DAC generator module for FRIDA.

Exports:
- CapArray: passive main/diff capacitor-array generator
- CapArrayConfig: CDAC parameters
- is_valid_caparray_config: Validate parameter combinations
- get_caparray_weights: Get capacitor weights for configuration
"""

from .subckt import (
    CapArray,
    CapArrayConfig,
    CapArrayParams,
    CapType,
    RedunStrat,
    SplitStrat,
    get_caparray_weights,
    is_valid_caparray_config,
    is_valid_caparray_params,
)

__all__ = [
    "CapArray",
    "CapArrayConfig",
    "CapArrayParams",
    "CapType",
    "RedunStrat",
    "SplitStrat",
    "get_caparray_weights",
    "is_valid_caparray_config",
    "is_valid_caparray_params",
]
