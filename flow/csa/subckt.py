"""
Charge-sensitive amplifier generator for FRIDA.

A pixel front end's preamplifier core: an input device, its
cascode and a current-source load of the other type, a cascoded common-source stage whose output
``out`` returns to the input through the feedback capacitor and one of three discharges.
Supports, with an NMOS or PMOS input device:
- Krummenacher feedback: a differential pair of the other type,
  its tail biased by ``vfb``, compares ``out`` with ``vref`` and feeds the input from one side and
  through a mirror of the input's type from the other; the mirror, its gate filtered by a MOS
  capacitor, holds the output's baseline near ``vref`` and follows the detector's slow leakage,
  while under signal the pair switches and returns the input at half the tail current (a time
  over threshold linear in the charge)
- Continuous feedback: one long device of the input's type across the
  capacitor, its gate biased by ``vfb``: a large resistance at rest, a constant current under
  signal
- Reset feedback: a switch of the input's type across the capacitor, closed
  while ``vfb`` turns it on

The feedback capacitor ``cf`` belongs to simulation: the row cells draw MOS only, and the
layout's netlist leaves it out. A source follower after ``out`` is the follower block.
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import C, MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.circuit.devices import mos as _mos
from flow.circuit.devices import write_netlist as _write_netlist


class Feedback(Enum):
    KRUMMENACHER = auto()  # a differential pair against vref, its tail current returning the input
    CONTINUOUS = auto()  # one long device across cf, its gate on vfb
    RESET = auto()  # a switch across cf, its gate on vfb


@h.paramclass
class CsaParams:
    """Charge-sensitive amplifier parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    input_xtors = h.Param(dtype=MosType, desc="Input device type (NMOS or PMOS)", default=MosType.NMOS)
    feedback = h.Param(dtype=Feedback, desc="Discharge across the feedback capacitor", default=Feedback.KRUMMENACHER)
    cf = h.Param(dtype=h.Prefixed, desc="Feedback capacitor, for simulation (0: none)", default=5 * f)

    # Device sizing (multipliers of Wmin/Lmin)
    in_w = h.Param(dtype=int, desc="Input device width multiplier", default=24)
    in_l = h.Param(dtype=int, desc="Input device length multiplier", default=2)
    cas_w = h.Param(dtype=int, desc="Cascode width multiplier", default=8)
    cas_l = h.Param(dtype=int, desc="Cascode length multiplier", default=2)
    load_w = h.Param(dtype=int, desc="Current-source load width multiplier", default=8)
    load_l = h.Param(dtype=int, desc="Current-source load length multiplier", default=8)
    fb_w = h.Param(dtype=int, desc="Feedback pair, long device or switch width multiplier", default=2)
    fb_l = h.Param(dtype=int, desc="Feedback device length multiplier", default=8)
    tail_w = h.Param(dtype=int, desc="Krummenacher tail and mirror width multiplier", default=2)
    tail_l = h.Param(dtype=int, desc="Krummenacher tail and mirror length multiplier", default=16)
    filter_w = h.Param(dtype=int, desc="Krummenacher mirror filter capacitor width multiplier", default=16)
    filter_l = h.Param(dtype=int, desc="Krummenacher mirror filter capacitor length multiplier", default=32)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_csa_params(param: CsaParams) -> bool:
    """Check if this amplifier is valid: every size positive, the capacitor not negative."""
    sizes = (param.in_w, param.in_l, param.cas_w, param.cas_l, param.load_w, param.load_l)
    sizes += (param.fb_w, param.fb_l, param.tail_w, param.tail_l, param.filter_w, param.filter_l)
    return min(sizes) > 0 and float(param.cf) >= 0


@h.bundle
class CsaNets:
    inp = h.Input(desc="Charge input")
    out = h.Output(desc="Preamplifier output")
    vload = h.Input(desc="Current-source load bias")
    vcas = h.Input(desc="Cascode bias")
    vref = h.Input(desc="Krummenacher reference: the output's baseline")
    vfb = h.Input(desc="Feedback control: the Krummenacher tail's or the long device's bias, or the reset switch")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Csa(param: CsaParams) -> h.Module:
    """
    Charge-sensitive amplifier generator.

    Generates a cascoded common-source preamplifier with Krummenacher, continuous or reset
    feedback, NMOS or PMOS input, every body on its rail.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_csa_params(param):
        raise ValueError(f"Invalid charge-sensitive amplifier params: {param}")

    Csa = module_from_ports("Csa", CsaNets.signals)
    tp = param.input_xtors
    other = MosType.PMOS if tp == MosType.NMOS else MosType.NMOS
    # the input type's rail (its bodies), the other type's
    rail, far = (Csa.vss, Csa.vdd) if tp == MosType.NMOS else (Csa.vdd, Csa.vss)
    vth = param.vth

    # the preamplifier: input device, its cascode, the other type's current source as load
    Csa.x = h.Signal(desc="Input device drain, the cascode's source")
    Csa.Min = _mos(tp=tp, vth=vth, w=param.in_w, l=param.in_l)(d=Csa.x, g=Csa.inp, s=rail, b=rail)
    Csa.Mcas = _mos(tp=tp, vth=vth, w=param.cas_w, l=param.cas_l)(d=Csa.out, g=Csa.vcas, s=Csa.x, b=rail)
    Csa.Mload = _mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(d=Csa.out, g=Csa.vload, s=far, b=far)
    if float(param.cf) > 0:
        Csa.Cf = C(c=param.cf)(p=Csa.out, n=Csa.inp)

    if param.feedback == Feedback.KRUMMENACHER:
        # the pair of the other type, so its drain may sit at the input's level. out above vref
        # (NMOS input, after electrons): the vref side takes the whole tail into the input, while
        # the mirror, held by its filter, still draws half of it out: the input rises at half the
        # tail current until out is back at vref. The mirror alone follows the slow leakage.
        Csa.tail, Csa.mirror = h.Signal(desc="The pair's sources"), h.Signal(desc="The mirror's diode")
        pair, tail = {"vth": vth, "w": param.fb_w, "l": param.fb_l}, {"vth": vth, "w": param.tail_w, "l": param.tail_l}
        Csa.Mk_ref = _mos(tp=other, **pair)(d=Csa.inp, g=Csa.vref, s=Csa.tail, b=far)
        Csa.Mk_sig = _mos(tp=other, **pair)(d=Csa.mirror, g=Csa.out, s=Csa.tail, b=far)
        Csa.Mk_tail = _mos(tp=other, **tail)(d=Csa.tail, g=Csa.vfb, s=far, b=far)
        Csa.Mk_diode = _mos(tp=tp, **tail)(d=Csa.mirror, g=Csa.mirror, s=rail, b=rail)
        Csa.Mk_mirror = _mos(tp=tp, **tail)(d=Csa.inp, g=Csa.mirror, s=rail, b=rail)
        Csa.Mk_filter = _mos(tp=tp, vth=vth, w=param.filter_w, l=param.filter_l)(d=rail, g=Csa.mirror, s=rail, b=rail)
    else:
        # a long device (biased by vfb) or a switch (driven by vfb) across the capacitor
        Csa.Mfb = _mos(tp=tp, vth=vth, w=param.fb_w, l=param.fb_l)(d=Csa.inp, g=Csa.vfb, s=Csa.out, b=rail)
    return Csa


def write_netlist(params: CsaParams, path: Path, pdk) -> Path:
    """The amplifier after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.circuit.devices.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Csa, nets=CsaNets)


# ==== Named amplifiers ====

CASES = {
    # NMOS input, Krummenacher feedback
    "krum": CsaParams(),
    # PMOS input, Krummenacher feedback
    "krum_pmos": CsaParams(input_xtors=MosType.PMOS),
    # NMOS input, a long feedback device
    "continuous": CsaParams(feedback=Feedback.CONTINUOUS, fb_l=16),
    # NMOS input, a reset switch
    "reset": CsaParams(feedback=Feedback.RESET, fb_l=1),
}
