"""
FRIDA HDL21 - Analog circuit generators using HDL21/VLSIR.

This package provides HDL21-based generators for FRIDA analog blocks
with a PDK abstraction layer supporting multiple process nodes.

Each block module (comp/, samp/, cdac/) contains:
- Generator: @h.generator function creating the circuit
- Testbench: @h.generator for testbench + sim_input() for simulation
- Tests: test_* functions using pytest flow/mode flags
"""

# Generators and Testbenches - from per-block modules
from .cdac import (
    CapType,
    Cdac,
    CdacParams,
    RedunStrat,
    SplitStrat,
    get_cdac_n_bits,
    get_cdac_weights,
    is_valid_cdac_params,
)

# Common circuit parameters
from .circuit import Pvt, PvtParams, supply_voltage
from .comp import Comp, CompParams, is_valid_comp_params
from .samp import Samp, SampParams, SwitchType

__all__ = [  # noqa: RUF022 - grouped by API domain
    # Generators
    "Samp",
    "SampParams",
    "Comp",
    "CompParams",
    "is_valid_comp_params",
    "Cdac",
    "CdacParams",
    "is_valid_cdac_params",
    "get_cdac_weights",
    "get_cdac_n_bits",
    # Testbenches
    "SampTb",
    "SampTbParams",
    "CompTb",
    "CompTbParams",
    "CdacTb",
    "CdacTbParams",
    # Enums
    "SwitchType",
    "RedunStrat",
    "SplitStrat",
    "CapType",
    "PvtParams",
    "Pvt",
    "supply_voltage",
]

_TESTBENCH_EXPORTS = {
    "CdacTb": ("flow.cdac.sim", "CdacTb"),
    "CdacTbParams": ("flow.cdac.sim", "CdacTbParams"),
    "CompTb": ("flow.comp.sim", "CompTb"),
    "CompTbParams": ("flow.comp.sim", "CompTbParams"),
    "SampTb": ("flow.samp.sim", "SampTb"),
    "SampTbParams": ("flow.samp.sim", "SampTbParams"),
}


def __getattr__(name: str):
    if name in _TESTBENCH_EXPORTS:
        from importlib import import_module

        module_name, attribute = _TESTBENCH_EXPORTS[name]
        return getattr(import_module(module_name), attribute)
    raise AttributeError(name)
