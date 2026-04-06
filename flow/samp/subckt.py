"""
Sampling Switch generator for FRIDA.

Supports NMOS, PMOS, and transmission gate topologies
with configurable device sizing and threshold voltage.

Note: Generators use h.Mos primitives with MosType/MosVth parameters.
Call pdk.compile(module) after generation to convert to PDK-specific devices.
"""

from enum import Enum, auto

import hdl21 as h
from hdl21.primitives import MosType, MosVth


class SwitchType(Enum):
    """Sampling switch topology."""

    NMOS = auto()
    PMOS = auto()
    TGATE = auto()


@h.paramclass
class SampParams:
    """Sampling switch parameters.

    Device sizing uses multiplier-based scaling:
    - mos_w: Width multiplier (w=10 means 10×Wmin, e.g., 1.2µm for a 65nm node)
    - mos_l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for a 65nm node)

    This approach allows the same design to be portable across PDKs.
    """

    switch_type = h.Param(dtype=SwitchType, desc="Switch topology", default=SwitchType.NMOS)
    mos_w = h.Param(dtype=int, desc="Width multiplier (× Wmin)", default=10)
    mos_l = h.Param(dtype=int, desc="Length multiplier (× Lmin)", default=1)
    mos_vth = h.Param(dtype=MosVth, desc="Threshold voltage flavor", default=MosVth.LOW)


@h.generator
def Samp(param: SampParams) -> h.Module:
    """
    Sampling switch generator.

    Generates NMOS, PMOS, or transmission gate switches
    based on the switch_type parameter.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """

    @h.module
    class Samp:
        """Sampling switch module."""

        # IO ports
        din = h.Input(desc="Data input")
        dout = h.Output(desc="Data output")
        clk = h.Input(desc="Clock (active high)")
        clk_b = h.Input(desc="Clock complement (active low)")
        vdd = h.Inout(desc="Supply")
        vss = h.Inout(desc="Ground")

    # Instantiate devices based on switch type
    if param.switch_type == SwitchType.NMOS:
        Samp.MN = h.Mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss
        )

    elif param.switch_type == SwitchType.PMOS:
        Samp.MP = h.Mos(tp=MosType.PMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    elif param.switch_type == SwitchType.TGATE:
        Samp.MN = h.Mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss
        )
        Samp.MP = h.Mos(tp=MosType.PMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    return Samp
