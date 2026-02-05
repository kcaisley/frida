"""
Shared parameters, enums, and dataclasses for FRIDA HDL21 generators.
"""

from enum import Enum
from typing import ClassVar

import hdl21 as h
from hdl21.pdk import Corner
from hdl21.prefix import m
from pydantic.dataclasses import dataclass


class SimTestMode(Enum):
    """
    Simulation test mode controlling test execution depth.

    Schematic/Simulation stages:
        NETLIST: HDL21 netlist generation only (no simulator needed)
        MIN: One setting, one corner (quick sanity check)
        TYP: One corner, many settings (typical parameter sweep)
        MAX: Full PVT sweep (comprehensive characterization)

    Physical design stages (future):
        LAYOUT: gdsfactory layout generation
        DRC: KLayout DRC checks
        LVS: Layout vs Schematic
        PNR: OpenROAD place & route
    """

    # Schematic/Simulation stages
    NETLIST = "netlist"
    MIN = "min"
    TYP = "typ"
    MAX = "max"

    # Physical design stages (future)
    LAYOUT = "layout"
    DRC = "drc"
    LVS = "lvs"
    PNR = "pnr"


class SwitchType(Enum):
    """Sampling switch topology."""

    NMOS = "nmos"
    PMOS = "pmos"
    TGATE = "tgate"


# Comparator topology enums
class PreampDiffpair(Enum):
    NMOS_INPUT = "nmosinput"
    PMOS_INPUT = "pmosinput"


class PreampBias(Enum):
    STD_BIAS = "stdbias"
    DYN_BIAS = "dynbias"


class CompStages(Enum):
    SINGLE_STAGE = "singlestage"
    DOUBLE_STAGE = "doublestage"


class LatchPwrgateCtl(Enum):
    CLOCKED = "clocked"
    SIGNALLED = "signalled"


class LatchPwrgateNode(Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"


class LatchRstExternCtl(Enum):
    CLOCKED = "clocked"
    SIGNALLED = "signalled"
    NO_RESET = "noreset"


class LatchRstInternCtl(Enum):
    CLOCKED = "clocked"
    SIGNALLED = "signalled"


# CDAC topology enums
class RedunStrat(Enum):
    RDX2 = "rdx2"
    SUBRDX2 = "subrdx2"
    SUBRDX2_LIM = "subrdx2lim"
    SUBRDX2_RDST = "subrdx2rdst"
    RDX2_RPT = "rdx2rpt"
    SUBRDX2_OVLY = "subrdx2ovly"  # Sub-radix-2 with paired overlay


class SplitStrat(Enum):
    NO_SPLIT = "nosplit"
    VDIV_SPLIT = "vdivsplit"
    DIFFCAP_SPLIT = "diffcapsplit"


class CapType(Enum):
    MOM1 = "cap_mom1"
    MOM2 = "cap_mom2"
    MOM3 = "cap_mom3"


@h.paramclass
class Pvt:
    """Process, Voltage, and Temperature condition."""

    p = h.Param(dtype=Corner, desc="Process corner", default=Corner.TYP)
    v = h.Param(dtype=Corner, desc="Voltage corner", default=Corner.TYP)
    t = h.Param(dtype=Corner, desc="Temperature corner", default=Corner.TYP)

    def __repr__(self) -> str:
        return f"Pvt({self.p.name}, {self.v.name}, {self.t.name})"


@dataclass
class SupplyVals:
    """
    Supply voltage values mapped from corners to physical voltages.

    This class provides a technology-independent way to specify
    supply voltages. Each PDK can define its own voltage levels.
    """

    VDD: h.Prefixed

    # Default values for a generic 1.2V process
    # Override these class variables in PDK-specific subclasses
    VDD_VALS: ClassVar[list] = [1080 * m, 1200 * m, 1320 * m]  # -10%, nom, +10%

    @classmethod
    def corner(cls, corner: Corner) -> "SupplyVals":
        """Create SupplyVals from a voltage corner."""
        idx = {Corner.SLOW: 0, Corner.TYP: 1, Corner.FAST: 2}.get(corner)
        if idx is None:
            raise ValueError(f"Invalid corner: {corner}")
        return cls(VDD=cls.VDD_VALS[idx])


@dataclass
class Tsmc65SupplyVals(SupplyVals):
    """
    TSMC 65nm LP supply voltage values.

    Nominal VDD: 1.2V
    Corners: -10%, nominal, +10%
    """

    VDD_VALS: ClassVar[list] = [1080 * m, 1200 * m, 1320 * m]


@dataclass
class Tsmc28SupplyVals(SupplyVals):
    """
    TSMC 28nm HPC+ supply voltage values.

    Nominal VDD: 0.9V
    Corners: -10%, nominal, +10%
    """

    VDD_VALS: ClassVar[list] = [810 * m, 900 * m, 990 * m]


@dataclass
class Tower180SupplyVals(SupplyVals):
    """
    Tower 180nm supply voltage values.

    Nominal VDD: 1.8V
    Corners: -10%, nominal, +10%
    """

    VDD_VALS: ClassVar[list] = [1620 * m, 1800 * m, 1980 * m]


class Project:
    """Project-level settings for temperature mapping."""

    @staticmethod
    def temper(corner: Corner) -> int:
        """Map temperature corner to degrees Celsius."""
        vals = {Corner.SLOW: -40, Corner.TYP: 25, Corner.FAST: 125}
        return vals[corner]
