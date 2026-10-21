"""
Current source and current-steering DAC unit generator for FRIDA.

Supports, with an NMOS (sinking) or PMOS (sourcing) current source:
- Any number of parallel units on one bias, optionally cascoded
- Always on, switched to the output by en, or steered between the output (en) and a dump (enb)
- A diode-connected reference that sets the bias from a current into vbias (a bias mirror)
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


class Switch(Enum):
    NONE = auto()  # the current flows to the output
    SINGLE = auto()  # a switch gated by en to the output
    STEER = auto()  # en switches it to the output, enb to the dump


@h.paramclass
class IdacParams:
    """Current source unit parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=4 means 4×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    source_xtors = h.Param(dtype=MosType, desc="Current source type: NMOS sinks, PMOS sources", default=MosType.NMOS)
    units = h.Param(dtype=int, desc="Parallel units (a thermometer segment's weight)", default=1)
    cascode = h.Param(dtype=bool, desc="A cascode on each unit (gate vcas)", default=False)
    switch = h.Param(dtype=Switch, desc="Output switching", default=Switch.SINGLE)
    diode = h.Param(dtype=bool, desc="A diode-connected reference on vbias", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    src_w = h.Param(dtype=int, desc="Current source width multiplier", default=8)
    src_l = h.Param(dtype=int, desc="Current source length multiplier", default=8)
    cas_w = h.Param(dtype=int, desc="Cascode width multiplier", default=8)
    cas_l = h.Param(dtype=int, desc="Cascode length multiplier", default=2)
    sw_w = h.Param(dtype=int, desc="Switch width multiplier", default=4)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_idac_params(param: IdacParams) -> bool:
    """Check if this unit is valid: at least one unit, every size positive."""
    return min(param.units, param.src_w, param.src_l, param.cas_w, param.cas_l, param.sw_w) > 0


@h.bundle
class IdacNets:
    out = h.Output(desc="Unit output current")
    dump = h.Output(desc="Steered-off current (Switch.STEER)")
    en, enb = h.Input(desc="Output switch enable"), h.Input(desc="Dump switch enable")
    vbias = h.Input(desc="Current source gate (the reference's drain with a diode)")
    vcas = h.Input(desc="Cascode gate")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Idac(param: IdacParams) -> h.Module:
    """
    Current source unit generator.

    Generates parallel, optionally cascoded NMOS or PMOS current sources, always on, switched
    or steered, with an optional diode-connected reference.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_idac_params(param):
        raise ValueError(f"Invalid current source params: {param}")

    Idac = module_from_ports("Idac", IdacNets.signals)
    tp, vth = param.source_xtors, param.vth
    rail = Idac.vss if tp == MosType.NMOS else Idac.vdd
    # a PMOS source's switches take the complements: low turns a PMOS on
    on, off = (Idac.en, Idac.enb) if tp == MosType.NMOS else (Idac.enb, Idac.en)

    if param.diode:
        Idac.Mref = _mos(tp=tp, vth=vth, w=param.src_w, l=param.src_l)(d=Idac.vbias, g=Idac.vbias, s=rail, b=rail)
    for k in range(param.units):
        node = Idac.out if param.switch == Switch.NONE and not param.cascode else Idac.add(h.Signal(name=f"src{k}"))
        Idac.add(
            _mos(tp=tp, vth=vth, w=param.src_w, l=param.src_l)(d=node, g=Idac.vbias, s=rail, b=rail), name=f"Msrc{k}"
        )
        if param.cascode:
            top = Idac.out if param.switch == Switch.NONE else Idac.add(h.Signal(name=f"cas{k}"))
            Idac.add(
                _mos(tp=tp, vth=vth, w=param.cas_w, l=param.cas_l)(d=top, g=Idac.vcas, s=node, b=rail), name=f"Mcas{k}"
            )
            node = top
        if param.switch != Switch.NONE:
            Idac.add(_mos(tp=tp, vth=vth, w=param.sw_w, l=1)(d=Idac.out, g=on, s=node, b=rail), name=f"Msw{k}")
        if param.switch == Switch.STEER:
            Idac.add(_mos(tp=tp, vth=vth, w=param.sw_w, l=1)(d=Idac.dump, g=off, s=node, b=rail), name=f"Mdump{k}")
    return Idac


def write_netlist(params: IdacParams, path: Path, pdk) -> Path:
    """The unit after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Idac, nets=IdacNets)


# ==== Named units ====

CASES = {
    # switched NMOS unit (Usb2Phy NmosIdac's unit), two of them
    "nmos_switched": IdacParams(units=2),
    # cascoded PMOS unit steered between the output and the dump (Usb2Phy PmosIdacUnit)
    "pmos_steer_cas": IdacParams(source_xtors=MosType.PMOS, cascode=True, switch=Switch.STEER),
    # four NMOS units steered between two outputs (Usb2Phy cmlpi IdacUnit, I/Q steering)
    "nmos_steer": IdacParams(units=4, switch=Switch.STEER),
    # PMOS bias mirror: a diode reference and two cascoded always-on units (Usb2Phy PmosBiasDist)
    "pmos_mirror": IdacParams(source_xtors=MosType.PMOS, units=2, cascode=True, switch=Switch.NONE, diode=True),
}
