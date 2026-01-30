"""
Common parameters and utilities for FRIDA HDL21 generators.
"""

from .params import (
    # Basic enums
    SwitchType,
    Vth,
    # Comparator enums
    PreampDiffpair,
    PreampBias,
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    # CDAC enums
    RedunStrat,
    SplitStrat,
    CapType,
    # PVT and supply
    Pvt,
    SupplyVals,
    Project,
)

from .sim_options import sim_options, get_sim_options

__all__ = [
    "SwitchType",
    "Vth",
    "PreampDiffpair",
    "PreampBias",
    "CompStages",
    "LatchPwrgateCtl",
    "LatchPwrgateNode",
    "LatchRstExternCtl",
    "LatchRstInternCtl",
    "RedunStrat",
    "SplitStrat",
    "CapType",
    "Pvt",
    "SupplyVals",
    "Project",
    "sim_options",
    "get_sim_options",
]
