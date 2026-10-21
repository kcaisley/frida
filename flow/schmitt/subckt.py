"""
Schmitt trigger generator for FRIDA.

A CMOS Schmitt trigger, as in a power-on reset or a logic input: an inverter whose NMOS and PMOS are each split
into a stack of two, with a feedback device from the output into each stack's middle node (an NMOS
to vdd, a PMOS to vss). While the output is high the NMOS feedback holds the lower stack's middle
up, so the input must rise further to pull the output down; while it is low the PMOS feedback
holds the upper stack's middle down. The feedback devices' strength against the stacks' sets the
hysteresis. Supports:
- The inverting trigger alone (6 devices)
- A buffer: the trigger and an output inverter (8 devices)
"""

from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


@h.paramclass
class SchmittParams:
    """Schmitt trigger parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=4 means 4×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    buffer = h.Param(dtype=bool, desc="An output inverter: out follows in", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    n_w = h.Param(dtype=int, desc="Stack and output NMOS width multiplier", default=4)
    p_w = h.Param(dtype=int, desc="Stack and output PMOS width multiplier", default=8)
    fb_n_w = h.Param(dtype=int, desc="NMOS feedback width multiplier", default=2)
    fb_p_w = h.Param(dtype=int, desc="PMOS feedback width multiplier", default=4)
    l = h.Param(dtype=int, desc="Length multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_schmitt_params(param: SchmittParams) -> bool:
    """Check if this trigger is valid: every size positive."""
    return min(param.n_w, param.p_w, param.fb_n_w, param.fb_p_w, param.l) > 0


@h.bundle
class SchmittNets:
    inp = h.Input(desc="Input")
    out = h.Output(desc="Output: in inverted, or with the buffer in itself")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Schmitt(param: SchmittParams) -> h.Module:
    """
    Schmitt trigger generator.

    Generates the six-device CMOS Schmitt trigger, inverting, or with an output inverter, every body
    on its rail.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_schmitt_params(param):
        raise ValueError(f"Invalid Schmitt trigger params: {param}")

    Schmitt = module_from_ports("Schmitt", SchmittNets.signals)
    vdd, vss, vth = Schmitt.vdd, Schmitt.vss, param.vth
    nmos = {"tp": MosType.NMOS, "vth": vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": vth, "w": param.p_w, "l": param.l}
    # the trigger's output: out itself, or the output inverter's input
    trig = Schmitt.add(h.Signal(name="trig", desc="The trigger's inverted output")) if param.buffer else Schmitt.out
    Schmitt.nmid, Schmitt.pmid = h.Signal(desc="NMOS stack's middle"), h.Signal(desc="PMOS stack's middle")
    Schmitt.Mn1 = _mos(**nmos)(d=Schmitt.nmid, g=Schmitt.inp, s=vss, b=vss)
    Schmitt.Mn2 = _mos(**nmos)(d=trig, g=Schmitt.inp, s=Schmitt.nmid, b=vss)
    Schmitt.Mp1 = _mos(**pmos)(d=Schmitt.pmid, g=Schmitt.inp, s=vdd, b=vdd)
    Schmitt.Mp2 = _mos(**pmos)(d=trig, g=Schmitt.inp, s=Schmitt.pmid, b=vdd)
    # the feedback: a high output holds the NMOS middle up, a low one the PMOS middle down
    Schmitt.Mnf = _mos(tp=MosType.NMOS, vth=vth, w=param.fb_n_w, l=param.l)(d=vdd, g=trig, s=Schmitt.nmid, b=vss)
    Schmitt.Mpf = _mos(tp=MosType.PMOS, vth=vth, w=param.fb_p_w, l=param.l)(d=vss, g=trig, s=Schmitt.pmid, b=vdd)
    if param.buffer:
        Schmitt.Mout_n = _mos(**nmos)(d=Schmitt.out, g=trig, s=vss, b=vss)
        Schmitt.Mout_p = _mos(**pmos)(d=Schmitt.out, g=trig, s=vdd, b=vdd)
    return Schmitt


def write_netlist(params: SchmittParams, path: Path, pdk) -> Path:
    """The trigger after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Schmitt, nets=SchmittNets)


# ==== Named triggers ====

CASES = {
    # inverting trigger
    "inv": SchmittParams(),
    # inverting trigger with stronger feedback: wider hysteresis
    "inv_wide": SchmittParams(fb_n_w=4, fb_p_w=8),
    # non-inverting buffer
    "buffer": SchmittParams(buffer=True),
}
