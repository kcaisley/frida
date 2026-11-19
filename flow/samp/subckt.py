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

from .params import PRECHARGE_W, Params, SwitchType


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

    # [Razavi-ADC] Fig. 3.41(b), p. 48: the bootstrapped NMOS switch
    # Terms: M1 MN; C_b Mcap, between P (``boot_top``) and Q (``boot_bot``); M2 Mbot_in (its gate on
    #   A, ``gate``); M3 Mgate; M4 Mbot; M5 Mpre; M6 Mgate_off; M7 Mgate_cas (its gate on vdd). In
    #   hold (clk low) Mpre charges P to vdd and Mbot pulls Q to vss, while Mgate_off under its
    #   cascodes holds A low. In track Mgate joins A to P and Mbot_in puts vin on Q, so A sits C_b's
    #   charge above vin: V_GS = V_b' whatever the input ([Razavi-ADC] Sec. 3.8.1, p. 43; Eq.
    #   (3.70), p. 50). Mpre's and Mgate's n-wells sit on P, never below their other terminals
    #   ([Razavi-ADC] Sec. 3.8.2, p. 48).
    # Ours against the source, each not in the reference texts:
    #   - Mgate's gate (``gate_ctl``) is not the clock: it follows Q while tracking (the PMOS
    #     Mctl_on, gated by the complementary clock, down to Q or to about its threshold above 0 V,
    #     whichever is higher) and sits at vdd while holding (Mctl_p), so Mgate's |V_GS| stays
    #     within about V_DD where a clocked gate would see P, up to two supplies, from 0 V;
    #     Mctl_dummy, drain and source on gate_ctl, on the complementary clock against Mctl_p's
    #     clock edge.
    #   - Mbot_in is ``bot_l`` long, so that Q, and A with it, rises from 0 V to vin no faster
    #     than the switch moves its output from the previous sample (flow.samp.params.BOTTOM_LIFT):
    #     A then stands no more than V_b' above an output the switch has yet to move (A - vout,
    #     MN's oxide at its output end).
    #   - a second cascode, Mgate_top, above M7, gated by P, so that neither carries more than a
    #     supply while A sits up to two supplies high (the source: V_DS7 about V_DD + V_TH7), and
    #     between the two a diode-connected device, Mgate_drop, with Mgate_pass (gated by vdd)
    #     across it. While tracking, Mgate_top's source (``gate_top``) creeps up to a subthreshold
    #     drop below P and M7's drain (``gate_mid``) to another below that; as the pull-down turns
    #     on, M7's source falls to a threshold below vdd before M7 conducts, and the two drops
    #     keep what M7 then has across it under a supply. Once gate_mid is a threshold below vdd
    #     Mgate_pass conducts past the diode, so that A is pulled to 0 V, not to a threshold above.
    #   - Mgate_off_dummy, drain and source on the pull-down's foot (``gate_off``), on the clock,
    #     against Mgate_off's clock edge, whose kick reaches A through the cascodes.
    #   - Mpre is PRECHARGE_W helpers wide: it holds P at vdd while A charges from it.
    # Holds for: a design ``flow.samp.params.valid`` admits; the input moving no faster while
    #   holding than a full-scale sine at the ADC's Nyquist frequency (a faster fall couples A
    #   below 0 V through MN's gate). No terminal pair then passes the highest supply by more than
    #   the coupling of a clock edge or of the moving input onto a node held at a rail.
    if bootstrap:
        Samp.gate = h.Signal(desc="Boosted switch gate")
        Samp.boot_top, Samp.boot_bot, Samp.gate_ctl = h.Signal(), h.Signal(), h.Signal()
        Samp.gate_top, Samp.gate_mid, Samp.gate_off = h.Signal(), h.Signal(), h.Signal()
        aux = {"vth": param.mos_vth, "w": param.boot_w, "l": 1}
        # not in the reference texts: Mctl_dummy half a helper wide, drain and source both on
        # gate_ctl: its two overlaps equal Mctl_p's one (the dummy of [Razavi-ADC] Sec. 3.7, p. 42,
        # on a helper's clock edge)
        # Terms: the source's M1 Mctl_p (on clk), its M3 Mctl_dummy (on clk_b); W_3 = boot_w // 2.
        # Holds for: clock edges that meet; a helper at least two units wide.
        small = {"vth": param.mos_vth, "w": max(1, param.boot_w // 2), "l": 1}
        # the bottom plate follows vin while tracking, its gate boosted with the switch's
        Samp.Mbot_in = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.boot_w, l=param.bot_l)(
            d=Samp.boot_bot, g=Samp.gate, s=Samp.vin, b=Samp.vss
        )
        # bottom plate to vss during hold
        Samp.Mbot = mos(tp=MosType.NMOS, **aux)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        # gate pull-down during hold, under the cascodes
        Samp.Mgate_top = mos(tp=MosType.NMOS, **aux)(d=Samp.gate, g=Samp.boot_top, s=Samp.gate_top, b=Samp.vss)
        Samp.Mgate_drop = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_top, g=Samp.gate_top, s=Samp.gate_mid, b=Samp.vss)
        Samp.Mgate_pass = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_top, g=Samp.vdd, s=Samp.gate_mid, b=Samp.vss)
        Samp.Mgate_cas = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_mid, g=Samp.vdd, s=Samp.gate_off, b=Samp.vss)
        Samp.Mgate_off = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_off, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        Samp.Mgate_off_dummy = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_off, g=Samp.clk, s=Samp.gate_off, b=Samp.vss)
        # top plate to the gate while tracking
        Samp.Mgate = mos(tp=MosType.PMOS, **aux)(d=Samp.gate, g=Samp.gate_ctl, s=Samp.boot_top, b=Samp.boot_top)
        # top plate to vdd while the gate is low (hold)
        Samp.Mpre = mos(tp=MosType.PMOS, vth=param.mos_vth, w=PRECHARGE_W * param.boot_w, l=1)(
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

    # [Razavi-ADC] Sec. 3.7, p. 42: a dummy of half the switch's width, W_3 = 0.5 W_1, clocked
    # opposite its switch, absorbs the charge the switch's channel releases at turn-off
    # Terms: M1 MN (MP), M3 MN_dummy (MP_dummy), drain and source on vout; W_1 mos_w, W_3 mos_w // 2.
    # Ours against the source: whole size units, so an odd mos_w's dummy is half a unit narrow.
    # Holds for: half the channel charge leaving through vout and clock edges that meet
    #   ([Razavi-ADC] Sec. 3.7, p. 43: neither can be relied on).
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
                Samp.Mgate_drop,
                Samp.Mgate_pass,
                Samp.Mgate_cas,
                Samp.Mgate_off,
                Samp.Mgate_off_dummy,
                Samp.Mbot,
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
