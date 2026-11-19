"""The sampling switch's circuit: its nets (``Nets``) and its generator (``netlist``), the module
``Samp`` of the design ``Params``.

An NMOS, PMOS or transmission-gate switch with configurable device sizing and threshold voltage,
half-size charge-injection dummies, and a bootstrapped NMOS gate ([Razavi-ADC] Fig. 3.41(b), p. 48). The generator uses h.Mos
primitives; the PDK's compile makes them its devices.
"""

import math

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.ports import module_from_ports
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import Border, EdgePin, edge_pins, halves, place, row, rows

from .params import BOTTOM_LIFT, Params, SwitchType


@h.bundle
class Nets:
    vin = h.Input(desc="Data input")
    vout = h.Output(desc="Data output")
    clk, clk_b = h.Clock(), h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


def _bottom_length(param: Params) -> int:
    """The bootstrap's bottom-plate switch's (Mbot_in's) length in units of the minimum, at the
    helpers' width: the shortest whose resistance over the switch's, times the boost capacitor's
    area, reaches ``BOTTOM_LIFT``."""
    return max(1, math.ceil(BOTTOM_LIFT * param.boot_w * param.mos_l / (param.mos_w * param.cap_w * param.cap_l)))


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The sampling switch: an NMOS, a PMOS or both (a transmission gate) between ``vin`` and
    ``vout``, tracking while ``clk`` is high; a bootstrap drives the NMOS gate from its boosted node,
    half-size dummies on ``vout`` absorb the charge their switch's channel releases at turn-off."""
    Samp = module_from_ports("Samp", Nets.signals)
    # its ports on its outline (flow.layout.pins): the input at the top, the output on the side
    # that faces the comparator
    edge_pins(Samp, EdgePin(Samp.vin, Border.TOP), EdgePin(Samp.vout, Border.RIGHT))
    bootstrap = param.switch_type is SwitchType.BOOTSTRAP
    nmos = param.switch_type in (SwitchType.NMOS, SwitchType.TGATE, SwitchType.BOOTSTRAP)
    pmos = param.switch_type in (SwitchType.PMOS, SwitchType.TGATE)

    # The bootstrapped NMOS switch, [Razavi-ADC] Fig. 3.41(b), p. 48: the boost capacitor (Mcap, C_b)
    # between ``boot_top`` (P) and ``boot_bot`` (Q). In hold (clk low) Mpre (M5) charges P to vdd and
    # Mbot (M4) pulls Q to vss, while Mgate_off (M6) under the cascode Mgate_cas (M7, its gate on
    # vdd) holds ``gate`` (A) low. In track Mgate (M3) joins A to P and Mbot_in (M2, its gate on A)
    # puts vin on Q, so A sits C_b's charge above vin: V_GS = V_b' whatever the input
    # ([Razavi-ADC] Sec. 3.8.1, p. 43; Eq. (3.70), p. 50). Mpre's and Mgate's n-wells sit on P, which
    # is never below their other terminals ([Razavi-ADC] Sec. 3.8.2, p. 48).
    # not in the reference texts: Mgate's gate (``gate_ctl``) follows Q while tracking (the PMOS
    # Mctl_on, gated by the complementary clock, down to Q or to about its threshold above 0 V,
    # whichever is higher) and sits at vdd while holding (Mctl_p), so Mgate's |V_GS| stays within
    # about V_DD where a clocked gate would see P, up to two supplies, from 0 V.
    # not in the reference texts: Mbot_in long (``_bottom_length``), so that Q, and A with it, rises
    # from 0 V to vin no faster than the switch moves its output from the previous sample: A then
    # never stands much more than V_b' above an output the switch has yet to move (A - vout, MN's
    # oxide at its output end); its resistance over the switch's, times the boost capacitor's area
    # (Q's capacitance, the capacitor's bottom plate to the substrate), at least ``BOTTOM_LIFT``.
    # not in the reference texts: the edges' coupling and charge sharing held within a few
    # millivolts of the highest supply where the boost capacitor is large against the helpers
    # (a switch 16 units wide or wider; an 8-unit switch's bottom plate dips further below 0 V as
    # tracking ends): Mpre eight times the helpers' width holds P at vdd while A
    # charges from it, and dummies (drain and source joined) whose clock edge pushes against a
    # node's own kick: on Q (Mbot_dummy, on Mbot's clock, against the charge Mgate's gate brings Q
    # as tracking begins), on Mgate's gate (Mctl_dummy, opposite Mctl_p) and on the pull-down's foot
    # (Mgate_off_dummy, opposite Mgate_off, whose kick reaches A through the cascodes)
    if bootstrap:
        Samp.gate = h.Signal(desc="Boosted switch gate")
        Samp.boot_top, Samp.boot_bot, Samp.gate_ctl = h.Signal(), h.Signal(), h.Signal()
        Samp.gate_mid, Samp.gate_off = h.Signal(), h.Signal()
        aux = {"vth": param.mos_vth, "w": param.boot_w, "l": 1}
        small = {"vth": param.mos_vth, "w": max(1, param.boot_w // 2), "l": 1}
        # the bottom plate follows vin while tracking, its gate boosted with the switch's
        Samp.Mbot_in = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.boot_w, l=_bottom_length(param))(
            d=Samp.boot_bot, g=Samp.gate, s=Samp.vin, b=Samp.vss
        )
        # bottom plate to vss during hold
        Samp.Mbot = mos(tp=MosType.NMOS, **aux)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        Samp.Mbot_dummy = mos(tp=MosType.NMOS, **small)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.boot_bot, b=Samp.vss)
        # gate pull-down during hold, under a cascode gated by vdd ([Razavi-ADC] Fig. 3.41(b), p. 48);
        # not in the reference texts: a second cascode above it, gated by the top plate, so that
        # neither carries more than about a supply while the gate sits up to two supplies high
        Samp.Mgate_top = mos(tp=MosType.NMOS, **aux)(d=Samp.gate, g=Samp.boot_top, s=Samp.gate_mid, b=Samp.vss)
        Samp.Mgate_cas = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_mid, g=Samp.vdd, s=Samp.gate_off, b=Samp.vss)
        Samp.Mgate_off = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_off, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        Samp.Mgate_off_dummy = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_off, g=Samp.clk, s=Samp.gate_off, b=Samp.vss)
        # top plate to the gate while tracking
        Samp.Mgate = mos(tp=MosType.PMOS, **aux)(d=Samp.gate, g=Samp.gate_ctl, s=Samp.boot_top, b=Samp.boot_top)
        # top plate to vdd while the gate is low (hold)
        Samp.Mpre = mos(tp=MosType.PMOS, vth=param.mos_vth, w=8 * param.boot_w, l=1)(
            d=Samp.vdd, g=Samp.gate, s=Samp.boot_top, b=Samp.boot_top
        )
        # Mgate's gate: vdd in hold, the bottom plate (or a threshold above 0 V) while tracking
        Samp.Mctl_p = mos(tp=MosType.PMOS, **aux)(d=Samp.gate_ctl, g=Samp.clk, s=Samp.vdd, b=Samp.vdd)
        Samp.Mctl_on = mos(tp=MosType.PMOS, **aux)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.gate_ctl, b=Samp.vdd)
        Samp.Mctl_dummy = mos(tp=MosType.PMOS, **small)(d=Samp.gate_ctl, g=Samp.clk_b, s=Samp.gate_ctl, b=Samp.vdd)
        # the boost capacitor: an NMOS whose channel (drain and source on the bottom plate) faces its gate
        Samp.Mcap = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.cap_w, l=param.cap_l)(
            d=Samp.boot_bot, g=Samp.boot_top, s=Samp.boot_bot, b=Samp.vss
        )
    if nmos:
        Samp.MN = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.vout, g=Samp.gate if bootstrap else Samp.clk, s=Samp.vin, b=Samp.vss
        )
    if pmos:
        Samp.MP = mos(tp=MosType.PMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.vout, g=Samp.clk_b, s=Samp.vin, b=Samp.vdd
        )

    # Half-size dummies with drain and source on vout absorb the charge their switch's channel
    # releases at turn-off: each is clocked opposite its switch ([Razavi-ADC] Sec. 3.7, p. 42: a
    # dummy of half the switch's width)
    if param.dummy:
        half = param.mos_w // 2
        if nmos:
            Samp.MN_dummy = mos(tp=MosType.NMOS, vth=param.mos_vth, w=half, l=param.mos_l)(
                d=Samp.vout, g=Samp.clk_b, s=Samp.vout, b=Samp.vss
            )
        if pmos:
            Samp.MP_dummy = mos(tp=MosType.PMOS, vth=param.mos_vth, w=half, l=param.mos_l)(
                d=Samp.vout, g=Samp.clk, s=Samp.vout, b=Samp.vdd
            )

    # where ALIGN puts each device (flow.layout.hdl21align), rows top first, for the structures
    # FRIDA lays out (the others ALIGN places on its own): the bootstrap's boost above its switch,
    # a transmission gate's PMOS above its NMOS (each beside its dummy), an NMOS switch in two halves
    plain, tgate = not param.dummy, param.switch_type is SwitchType.TGATE
    if bootstrap and plain:
        placed = rows(
            row(Samp.Mpre, Samp.Mgate, Samp.Mctl_p, Samp.Mctl_on, Samp.Mctl_dummy),
            row(Samp.Mcap),
            row(
                Samp.Mgate_top,
                Samp.Mgate_cas,
                Samp.Mgate_off,
                Samp.Mgate_off_dummy,
                Samp.Mbot,
                Samp.Mbot_dummy,
            ),
            row(Samp.MN, Samp.Mbot_in),
        )
    elif tgate:
        placed = rows(row(Samp.MP, getattr(Samp, "MP_dummy", None)), row(Samp.MN, getattr(Samp, "MN_dummy", None)))
    elif param.switch_type is SwitchType.NMOS and plain:
        first, second = halves(Samp.MN)
        placed = rows(row(first), row(second))
    else:
        return Samp
    place(Samp, placed, symmetric=False)
    return Samp
