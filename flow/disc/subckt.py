"""
Continuous-time discriminator generator for FRIDA.

The threshold comparator of the group's pixel front ends (FE65-P2 ``Comparator``, CCPD
``Comparator_cont``, DHPT ``Comparator_normal``; RD53B ``Comparator_hyst``): an unclocked two-stage
open-loop comparator, a differential pair into its load, then a second stage whose output turns
high while ``inp`` is above ``inn``. Supports, with an NMOS or PMOS input pair:
- A current-mirror load (FE65-P2 ``Comparator``): the diode on the ``inn`` side; the second stage a
  common-source device of the load's type driven from the ``inp`` side, against a current source of
  the input's type sharing the tail's bias ``vbias``
- Internal hysteresis (RD53B ``Comparator_hyst``; Allen and Holberg's comparator with internal
  hysteresis): both loads diode-connected, each in parallel with one of a cross-coupled pair
  stronger than the diodes, whose ratio sets how far past the threshold the pair must be driven to
  flip either way; the second stage a pair of the load's type on both sides into a mirror of the
  input's type, so that the output switches where the first stage flips
"""

from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


@h.paramclass
class DiscParams:
    """Discriminator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    input_xtors = h.Param(dtype=MosType, desc="Input pair device type (NMOS or PMOS)", default=MosType.NMOS)
    hysteresis = h.Param(dtype=bool, desc="Diode loads with a cross-coupled pair, for hysteresis", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    in_w = h.Param(dtype=int, desc="Input pair width multiplier", default=8)
    in_l = h.Param(dtype=int, desc="Input pair length multiplier", default=2)
    tail_w = h.Param(dtype=int, desc="Tail and output current source width multiplier", default=4)
    tail_l = h.Param(dtype=int, desc="Tail and output current source length multiplier", default=16)
    load_w = h.Param(dtype=int, desc="Load width multiplier", default=4)
    load_l = h.Param(dtype=int, desc="Load length multiplier", default=8)
    cross_w = h.Param(dtype=int, desc="Cross-coupled pair width multiplier (hysteresis)", default=6)
    cross_l = h.Param(dtype=int, desc="Cross-coupled pair length multiplier (hysteresis)", default=8)
    out_w = h.Param(dtype=int, desc="Second stage devices' width multiplier", default=4)
    out_l = h.Param(dtype=int, desc="Second stage devices' length multiplier", default=4)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_disc_params(param: DiscParams) -> bool:
    """Check if this discriminator is valid: every size positive."""
    sizes = (param.in_w, param.in_l, param.tail_w, param.tail_l, param.load_w, param.load_l)
    return min((*sizes, param.cross_w, param.cross_l, param.out_w, param.out_l)) > 0


@h.bundle
class DiscNets:
    inp = h.Input(desc="Signal input")
    inn = h.Input(desc="Threshold input")
    out = h.Output(desc="High while inp is above inn")
    vbias = h.Input(desc="Tail bias, and the output current source's without hysteresis")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Disc(param: DiscParams) -> h.Module:
    """
    Continuous-time discriminator generator.

    Generates a differential pair with a current-mirror load and a common-source second stage, or
    with a hysteresis load and a differential second stage, NMOS or PMOS input, every body on its
    rail.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_disc_params(param):
        raise ValueError(f"Invalid discriminator params: {param}")

    Disc = module_from_ports("Disc", DiscNets.signals)
    tp = param.input_xtors
    other = MosType.PMOS if tp == MosType.NMOS else MosType.NMOS
    # the input type's rail (its bodies, the tail's source), the other type's
    rail, far = (Disc.vss, Disc.vdd) if tp == MosType.NMOS else (Disc.vdd, Disc.vss)
    vth = param.vth

    # the pair: inp draws on node a, inn on node b
    Disc.tail = h.Signal(desc="The pair's sources")
    Disc.a, Disc.b = h.Signal(desc="The inp side's drain"), h.Signal(desc="The inn side's drain")
    pair, tail = {"vth": vth, "w": param.in_w, "l": param.in_l}, {"vth": vth, "w": param.tail_w, "l": param.tail_l}
    Disc.Minp = _mos(tp=tp, **pair)(d=Disc.a, g=Disc.inp, s=Disc.tail, b=rail)
    Disc.Minn = _mos(tp=tp, **pair)(d=Disc.b, g=Disc.inn, s=Disc.tail, b=rail)
    Disc.Mtail = _mos(tp=tp, **tail)(d=Disc.tail, g=Disc.vbias, s=rail, b=rail)

    load = {"vth": vth, "w": param.load_w, "l": param.load_l}
    second = {"vth": vth, "w": param.out_w, "l": param.out_l}
    if param.hysteresis:
        # each side's diode in parallel with a cross-coupled device: past the ratio of their
        # strengths, the side carrying more of the tail turns the other's load off and flips
        cross = {"vth": vth, "w": param.cross_w, "l": param.cross_l}
        Disc.Mload_a = _mos(tp=other, **load)(d=Disc.a, g=Disc.a, s=far, b=far)
        Disc.Mload_b = _mos(tp=other, **load)(d=Disc.b, g=Disc.b, s=far, b=far)
        Disc.Mcross_a = _mos(tp=other, **cross)(d=Disc.a, g=Disc.b, s=far, b=far)
        Disc.Mcross_b = _mos(tp=other, **cross)(d=Disc.b, g=Disc.a, s=far, b=far)
        # the second stage: the a side drives the output, the b side the mirror that opposes it
        Disc.c = h.Signal(desc="The second stage mirror's diode")
        Disc.Mout_a = _mos(tp=other, **second)(d=Disc.out, g=Disc.a, s=far, b=far)
        Disc.Mout_b = _mos(tp=other, **second)(d=Disc.c, g=Disc.b, s=far, b=far)
        Disc.Mmirror_d = _mos(tp=tp, **second)(d=Disc.c, g=Disc.c, s=rail, b=rail)
        Disc.Mmirror_o = _mos(tp=tp, **second)(d=Disc.out, g=Disc.c, s=rail, b=rail)
    else:
        # the mirror's diode on the inn side: inp above inn pulls node a toward the input's rail,
        # turning the load-type device on and out toward its rail (high for an NMOS input)
        Disc.Mload_a = _mos(tp=other, **load)(d=Disc.a, g=Disc.b, s=far, b=far)
        Disc.Mload_b = _mos(tp=other, **load)(d=Disc.b, g=Disc.b, s=far, b=far)
        Disc.Mout = _mos(tp=other, **second)(d=Disc.out, g=Disc.a, s=far, b=far)
        Disc.Msink = _mos(tp=tp, **tail)(d=Disc.out, g=Disc.vbias, s=rail, b=rail)
    return Disc


def write_netlist(params: DiscParams, path: Path, pdk) -> Path:
    """The discriminator after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Disc, nets=DiscNets)


# ==== Named discriminators ====

CASES = {
    # NMOS input pair, current-mirror load (FE65-P2 Comparator)
    "nmos": DiscParams(),
    # NMOS input pair, hysteresis load (RD53B Comparator_hyst)
    "nmos_hyst": DiscParams(hysteresis=True),
    # PMOS input pair, current-mirror load
    "pmos": DiscParams(input_xtors=MosType.PMOS),
    # PMOS input pair, hysteresis load
    "pmos_hyst": DiscParams(input_xtors=MosType.PMOS, hysteresis=True),
}
