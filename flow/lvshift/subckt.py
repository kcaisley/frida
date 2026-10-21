"""
Level shifter generator for FRIDA.

Supports a cross-coupled level shifter from a low supply (vddl) to vdd:
- An NMOS input pair, driven differentially or from an input inverter on vddl
- A cross-coupled PMOS pair on vdd, an optional reset pulling outp low, optional output inverters

Every PMOS body sits on vdd, the higher supply (the row cells' wells): the input inverter's
PMOS has its source on vddl and its body on vdd.
"""

from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


@h.paramclass
class LvShiftParams:
    """Level shifter parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    input_inverter = h.Param(dtype=bool, desc="inn from an inverter on vddl (single-ended input)", default=False)
    reset = h.Param(dtype=bool, desc="rst pulls outp low", default=False)
    buffers = h.Param(dtype=bool, desc="Output inverters on vdd (bufp, bufn)", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    in_w = h.Param(dtype=int, desc="Input pair width multiplier", default=8)
    cross_w = h.Param(dtype=int, desc="Cross-coupled PMOS width multiplier", default=2)
    cross_l = h.Param(dtype=int, desc="Cross-coupled PMOS length multiplier", default=2)
    inv_n_w = h.Param(dtype=int, desc="Inverter NMOS width multiplier", default=2)
    inv_p_w = h.Param(dtype=int, desc="Inverter PMOS width multiplier", default=4)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_lvshift_params(param: LvShiftParams) -> bool:
    """Check if this level shifter is valid: every size positive."""
    return min(param.in_w, param.cross_w, param.cross_l, param.inv_n_w, param.inv_p_w) > 0


@h.bundle
class LvShiftNets:
    inp, inn = h.Input(desc="Input (vddl levels)"), h.Input(desc="Input complement (vddl levels)")
    rst = h.Input(desc="Reset, active high: outp low")
    outp, outn = h.Output(desc="Output (vdd levels)"), h.Output()
    bufp, bufn = h.Output(desc="Buffered outp"), h.Output(desc="Buffered outn")
    vddl = h.Input(desc="The input's supply")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def LvShift(param: LvShiftParams) -> h.Module:
    """
    Level shifter generator.

    Generates cross-coupled level shifters from vddl to vdd with a differential or
    single-ended input, an optional reset and optional output inverters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_lvshift_params(param):
        raise ValueError(f"Invalid level shifter params: {param}")

    LvShift = module_from_ports("LvShift", LvShiftNets.signals)
    vth = param.vth
    nmos = lambda w, l=1: _mos(tp=MosType.NMOS, vth=vth, w=w, l=l)
    pmos = lambda w, l=1: _mos(tp=MosType.PMOS, vth=vth, w=w, l=l)

    if param.input_inverter:  # inn from inp on the low supply, its PMOS body on vdd
        LvShift.Minv_n = nmos(param.inv_n_w)(d=LvShift.inn, g=LvShift.inp, s=LvShift.vss, b=LvShift.vss)
        LvShift.Minv_p = pmos(param.inv_p_w)(d=LvShift.inn, g=LvShift.inp, s=LvShift.vddl, b=LvShift.vdd)
    # inp pulls outn low, which turns on the PMOS that pulls outp to vdd
    LvShift.Min_p = nmos(param.in_w)(d=LvShift.outn, g=LvShift.inp, s=LvShift.vss, b=LvShift.vss)
    LvShift.Min_n = nmos(param.in_w)(d=LvShift.outp, g=LvShift.inn, s=LvShift.vss, b=LvShift.vss)
    LvShift.Mcross_p = pmos(param.cross_w, param.cross_l)(d=LvShift.outp, g=LvShift.outn, s=LvShift.vdd, b=LvShift.vdd)
    LvShift.Mcross_n = pmos(param.cross_w, param.cross_l)(d=LvShift.outn, g=LvShift.outp, s=LvShift.vdd, b=LvShift.vdd)
    if param.reset:
        LvShift.Mrst = nmos(param.in_w)(d=LvShift.outp, g=LvShift.rst, s=LvShift.vss, b=LvShift.vss)
    if param.buffers:  # each output's inverter drives the other buffered output: bufp follows outp
        for out, buf, name in ((LvShift.outn, LvShift.bufp, "p"), (LvShift.outp, LvShift.bufn, "n")):
            LvShift.add(nmos(param.inv_n_w)(d=buf, g=out, s=LvShift.vss, b=LvShift.vss), name=f"Mbuf_{name}_n")
            LvShift.add(pmos(param.inv_p_w)(d=buf, g=out, s=LvShift.vdd, b=LvShift.vdd), name=f"Mbuf_{name}_p")
    return LvShift


def write_netlist(params: LvShiftParams, path: Path, pdk) -> Path:
    """The level shifter after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=LvShift, nets=LvShiftNets)


# ==== Named level shifters ====

CASES = {
    # cross-coupled core, differential input
    "core": LvShiftParams(),
    # with an input inverter on vddl and a reset
    "single_rst": LvShiftParams(input_inverter=True, reset=True),
    # with an input inverter and output inverters
    "buffered": LvShiftParams(input_inverter=True, buffers=True),
}
