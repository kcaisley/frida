"""The charge-sensitive amplifier's circuit: its nets (``Nets``) and its generator (``netlist``), the
module ``Csa`` of the design ``Params``.

A pixel front end's preamplifier core: an input device, its cascode and a current-source load of
the other type, a cascoded common-source stage whose output ``out`` returns to the input through
the feedback capacitor and one of three discharges, with an NMOS or PMOS input device:

- Krummenacher feedback: a differential pair of the other type, its tail biased by ``vfb``,
  compares ``out`` with ``vref`` and feeds the input from one side and through a mirror of the
  input's type from the other; the mirror, its gate filtered by a MOS capacitor, holds the output's
  baseline near ``vref`` and follows the detector's slow leakage, while under signal the pair
  switches and returns the input at half the tail current (a time over threshold linear in the
  charge).
- Continuous feedback: one long device of the input's type across the capacitor, its gate biased
  by ``vfb``: a large resistance at rest, a constant current under signal.
- Reset feedback: a switch of the input's type across the capacitor, closed while ``vfb`` turns it
  on.

The feedback capacitor ``cf`` belongs to simulation: the row cells draw MOS only, and the layout
leaves it out (``params.layout_view``). A source follower after ``out`` is the follower block. The
generator uses h.Mos primitives; the PDK's compile makes them its devices.
"""

import hdl21 as h
from hdl21.primitives import C, MosType

from flow.circuit.ports import module_from_ports
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import place, row, rows

from .params import Feedback, Params


@h.bundle
class Nets:
    inp = h.Input(desc="Charge input")
    out = h.Output(desc="Preamplifier output")
    vload = h.Input(desc="Current-source load bias")
    vcas = h.Input(desc="Cascode bias")
    vref = h.Input(desc="Krummenacher reference: the output's baseline")
    vfb = h.Input(desc="Feedback control: the Krummenacher tail's or the long device's bias, or the reset switch")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The charge-sensitive amplifier: a cascoded common-source preamplifier with Krummenacher,
    continuous or reset feedback, NMOS or PMOS input, every body on its rail."""
    Csa = module_from_ports("Csa", Nets.signals)
    tp = param.input_xtors
    other = MosType.PMOS if tp == MosType.NMOS else MosType.NMOS
    # the input type's rail (its bodies), the other type's
    rail, far = (Csa.vss, Csa.vdd) if tp == MosType.NMOS else (Csa.vdd, Csa.vss)
    vth = param.vth

    # the preamplifier: input device, its cascode, the other type's current source as load
    Csa.x = h.Signal(desc="Input device drain, the cascode's source")
    Csa.Min = mos(tp=tp, vth=vth, w=param.in_w, l=param.in_l)(d=Csa.x, g=Csa.inp, s=rail, b=rail)
    Csa.Mcas = mos(tp=tp, vth=vth, w=param.cas_w, l=param.cas_l)(d=Csa.out, g=Csa.vcas, s=Csa.x, b=rail)
    Csa.Mload = mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(d=Csa.out, g=Csa.vload, s=far, b=far)
    if float(param.cf) > 0:
        Csa.Cf = C(c=param.cf)(p=Csa.out, n=Csa.inp)

    # where ALIGN puts each device (flow.layout.hdl21align), rows top first, the input type's rail
    # at the bottom for an NMOS input and at the top for a PMOS one: the Krummenacher's load beside
    # its tail, its pair, the cascode beside the mirror, the input device beside the mirror's
    # filter; the other feedbacks' load above the cascode, the input device and the feedback
    # device. The feedback capacitor, which the layout leaves out, is left to ALIGN.
    if param.feedback == Feedback.KRUMMENACHER:
        # the pair of the other type, so its drain may sit at the input's level. out above vref
        # (NMOS input, after electrons): the vref side takes the whole tail into the input, while
        # the mirror, held by its filter, still draws half of it out: the input rises at half the
        # tail current until out is back at vref. The mirror alone follows the slow leakage.
        Csa.tail, Csa.mirror = h.Signal(desc="The pair's sources"), h.Signal(desc="The mirror's diode")
        pair, tail = {"vth": vth, "w": param.fb_w, "l": param.fb_l}, {"vth": vth, "w": param.tail_w, "l": param.tail_l}
        Csa.Mk_ref = mos(tp=other, **pair)(d=Csa.inp, g=Csa.vref, s=Csa.tail, b=far)
        Csa.Mk_sig = mos(tp=other, **pair)(d=Csa.mirror, g=Csa.out, s=Csa.tail, b=far)
        Csa.Mk_tail = mos(tp=other, **tail)(d=Csa.tail, g=Csa.vfb, s=far, b=far)
        Csa.Mk_diode = mos(tp=tp, **tail)(d=Csa.mirror, g=Csa.mirror, s=rail, b=rail)
        Csa.Mk_mirror = mos(tp=tp, **tail)(d=Csa.inp, g=Csa.mirror, s=rail, b=rail)
        Csa.Mk_filter = mos(tp=tp, vth=vth, w=param.filter_w, l=param.filter_l)(d=rail, g=Csa.mirror, s=rail, b=rail)
        placed = [
            row(Csa.Mload, Csa.Mk_tail),
            row(Csa.Mk_ref, Csa.Mk_sig),
            row(Csa.Mcas, Csa.Mk_diode, Csa.Mk_mirror),
            row(Csa.Min, Csa.Mk_filter),
        ]
    else:
        # a long device (biased by vfb) or a switch (driven by vfb) across the capacitor
        Csa.Mfb = mos(tp=tp, vth=vth, w=param.fb_w, l=param.fb_l)(d=Csa.inp, g=Csa.vfb, s=Csa.out, b=rail)
        placed = [row(Csa.Mload), row(Csa.Mcas, Csa.Min, Csa.Mfb)]
    order = placed if tp == MosType.NMOS else placed[::-1]
    place(Csa, rows(*order), symmetric=False, auto=(Csa.Cf,) if float(param.cf) > 0 else ())
    return Csa
