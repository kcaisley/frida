"""The sampling switch's circuit: its nets (``Nets``) and its generator (``netlist``), the module
``Samp`` of the design ``Params``.

An NMOS, PMOS or transmission-gate switch with configurable device sizing and threshold voltage,
half-size charge-injection dummies, and a bootstrapped NMOS gate ([Razavi-ADC] Fig. 3.41(b), p. 48). The generator uses h.Mos
primitives; the PDK's compile makes them its devices.
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.ports import module_from_ports
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import Border, EdgePin, edge_pins, halves, place, row, rows

from .params import Params, SwitchType


@h.bundle
class Nets:
    vin = h.Input(desc="Data input")
    vout = h.Output(desc="Data output")
    clk, clk_b = h.Clock(), h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


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
    # not in the reference texts: Mgate's gate (``gate_ctl``) follows Q while tracking (Mctl_n, its
    # gate on A; Mctl_on starts it as the clock rises) and sits at vdd while holding (Mctl_p), so
    # Mgate's |V_GS| stays about V_DD where a clocked gate would see P, up to two supplies, from 0 V
    if bootstrap:
        Samp.gate = h.Signal(desc="Boosted switch gate")
        Samp.boot_top, Samp.boot_bot, Samp.gate_ctl = h.Signal(), h.Signal(), h.Signal()
        Samp.gate_mid, Samp.gate_off = h.Signal(), h.Signal()
        aux = {"vth": param.mos_vth, "w": param.boot_w, "l": 1}
        # the bottom plate follows vin while tracking, its gate boosted with the switch's
        Samp.Mbot_in = mos(tp=MosType.NMOS, **aux)(d=Samp.boot_bot, g=Samp.gate, s=Samp.vin, b=Samp.vss)
        # bottom plate to vss during hold
        Samp.Mbot = mos(tp=MosType.NMOS, **aux)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        # gate pull-down during hold, under a cascode gated by vdd ([Razavi-ADC] Fig. 3.41(b), p. 48);
        # not in the reference texts: a second cascode above it, gated by the top plate, so that
        # neither carries more than about a supply while the gate sits up to two supplies high
        Samp.Mgate_top = mos(tp=MosType.NMOS, **aux)(d=Samp.gate, g=Samp.boot_top, s=Samp.gate_mid, b=Samp.vss)
        Samp.Mgate_cas = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_mid, g=Samp.vdd, s=Samp.gate_off, b=Samp.vss)
        Samp.Mgate_off = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_off, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        # top plate to the gate while tracking
        Samp.Mgate = mos(tp=MosType.PMOS, **aux)(d=Samp.gate, g=Samp.gate_ctl, s=Samp.boot_top, b=Samp.boot_top)
        # top plate to vdd while the gate is low (hold)
        Samp.Mpre = mos(tp=MosType.PMOS, **aux)(d=Samp.vdd, g=Samp.gate, s=Samp.boot_top, b=Samp.boot_top)
        # Mgate's gate: vdd in hold, the bottom plate while tracking
        Samp.Mctl_p = mos(tp=MosType.PMOS, **aux)(d=Samp.gate_ctl, g=Samp.clk, s=Samp.vdd, b=Samp.vdd)
        Samp.Mctl_n = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_ctl, g=Samp.gate, s=Samp.boot_bot, b=Samp.vss)
        Samp.Mctl_on = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_ctl, g=Samp.clk, s=Samp.boot_bot, b=Samp.vss)
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
            row(Samp.Mpre, Samp.Mgate, Samp.Mctl_p),
            row(Samp.Mcap),
            row(Samp.Mgate_top, Samp.Mgate_cas, Samp.Mgate_off, Samp.Mbot, Samp.Mctl_n, Samp.Mctl_on),
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
