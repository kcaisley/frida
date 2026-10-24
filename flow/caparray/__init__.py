"""
Capacitor DAC generator module for FRIDA.

Exports:
- CapArray: passive main/diff capacitor-array generator
- CapArrayConfig: an array's DAC resolution, extra cycles, scheme and capacitance
- RedunStrat: the schemes (binary, MSB split, LSB split, MSB redistribution)
- is_valid_caparray_config: Validate parameter combinations
- get_caparray_weights: Get capacitor weights for configuration
"""

from .subckt import (
    CapArray,
    CapArrayConfig,
    CapArrayParams,
    RedunStrat,
    get_caparray_weights,
    is_valid_caparray_config,
    is_valid_caparray_params,
    switched_capacitance_f,
    total_capacitance_f,
    unit_capacitance_f,
)

__all__ = [
    "CapArray",
    "CapArrayConfig",
    "CapArrayParams",
    "RedunStrat",
    "get_caparray_weights",
    "is_valid_caparray_config",
    "is_valid_caparray_params",
    "switched_capacitance_f",
    "total_capacitance_f",
    "unit_capacitance_f",
]
