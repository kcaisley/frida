"""
Sampling Switch generator for FRIDA.

Supports NMOS, PMOS, and transmission gate topologies
with configurable device sizing and threshold voltage.

Note: Generators use h.Mos primitives with MosType/MosVth parameters.
Call pdk.compile(module) after generation to convert to PDK-specific devices.
"""

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from ..flow.params import SwitchType


@h.paramclass
class SampParams:
    """Sampling switch parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=10 means 10×Wmin, e.g., 1.2µm for TSMC65)
    - l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for TSMC65)

    This approach allows the same design to be portable across PDKs.
    """

    switch_type = h.Param(
        dtype=SwitchType, desc="Switch topology", default=SwitchType.NMOS
    )
    w = h.Param(dtype=int, desc="Width multiplier (× Wmin)", default=10)
    l = h.Param(dtype=int, desc="Length multiplier (× Lmin)", default=1)
    vth = h.Param(dtype=MosVth, desc="Threshold voltage flavor", default=MosVth.LOW)


@h.generator
def Samp(p: SampParams) -> h.Module:
    """
    Sampling switch generator.

    Generates NMOS, PMOS, or transmission gate switches
    based on the switch_type parameter.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    mosvth = p.vth

    @h.module
    class Samp:
        """Sampling switch module."""

        # IO ports
        din = h.Input(desc="Data input")
        dout = h.Output(desc="Data output")
        clk = h.Input(desc="Clock (active high)")
        clk_b = h.Input(desc="Clock complement (active low)")
        vdd = h.Port(desc="Supply")
        vss = h.Port(desc="Ground")

    # Instantiate devices based on switch type
    if p.switch_type == SwitchType.NMOS:
        Samp.mn = h.Mos(tp=MosType.NMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss
        )

    elif p.switch_type == SwitchType.PMOS:
        Samp.mp = h.Mos(tp=MosType.PMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    elif p.switch_type == SwitchType.TGATE:
        Samp.mn = h.Mos(tp=MosType.NMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss
        )
        Samp.mp = h.Mos(tp=MosType.PMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    return Samp


def samp_variants(
    w_list: list = None,
    l_list: list = None,
    switch_types: list = None,
    vth_list: list = None,
) -> list:
    """
    Generate a list of SampParams for parameter sweeps.

    Args:
        w_list: List of width multipliers (default: [5, 10, 20, 40])
        l_list: List of length multipliers (default: [1, 2])
        switch_types: List of SwitchType values (default: all)
        vth_list: List of Vth values (default: all)

    Returns:
        List of SampParams instances
    """
    if w_list is None:
        w_list = [5, 10, 20, 40]
    if l_list is None:
        l_list = [1, 2]
    if switch_types is None:
        switch_types = list(SwitchType)
    if vth_list is None:
        vth_list = [MosVth.LOW, MosVth.STD]

    return [
        SampParams(switch_type=st, w=w, l=l, vth=vth)
        for st in switch_types
        for w in w_list
        for l in l_list
        for vth in vth_list
    ]
