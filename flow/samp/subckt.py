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
    #   (3.70), p. 50). Mpre's and Mgate's n-wells sit on P ([Razavi-ADC] Sec. 3.8.2, p. 48),
    #   which is the highest of their terminals but as holding starts: P then lands at V_b', below
    #   Mpre's drain on vdd by V_DD - V_b' (a tenth of the supply at most, BOOST_MIN) until Mpre
    #   has recharged it, and A stands a few tens of millivolts above P while the pull-down
    #   discharges it; both far under a junction's turn-on (junction_forward_max_v reports them).
    # Ours against the source, each not in the reference texts:
    #   - Mgate's gate (``gate_ctl``) is not the clock: it follows Q while tracking (the PMOS
    #     Mctl_on, gated by the complementary clock, down to Q or to about its threshold above 0 V,
    #     whichever is higher) and sits at vdd while holding (Mctl_p), so Mgate's |V_GS| stays
    #     within about V_DD where a clocked gate would see P, up to two supplies, from 0 V;
    #     Mctl_dummy, drain and source on gate_ctl, on the complementary clock (below).
    #   - Mbot_in is ``bot_l`` long, so that Q, rising from 0 V to vin, cannot pass the output
    #     the switch moves from the previous sample (flow.samp.params.BOTTOM_LIFT): A, which rides
    #     V_b' above Q, then stands no more than V_b' above an output the switch has yet to move
    #     (A - vout, MN's oxide at its output end). Q's slope may be the larger before it reaches
    #     the output; its level stays below.
    #   - a second cascode, Mgate_top, above M7, gated by P, so that neither carries more than a
    #     supply while A sits up to two supplies high (the source: V_DS7 about V_DD + V_TH7), and
    #     between the two a diode-connected device, Mgate_drop, with Mgate_pass (gated by vdd)
    #     across it. While tracking, Mgate_top's source (``gate_top``) creeps up to a subthreshold
    #     drop below P and M7's drain (``gate_mid``) to another below that; as the pull-down turns
    #     on, M7's source falls to a threshold below vdd before M7 conducts, and the two drops
    #     keep what M7 then has across it under a supply. Once gate_mid is a threshold below vdd
    #     Mgate_pass conducts past the diode, so that A is pulled to 0 V, not to a threshold above.
    #   - Mgate_off_dummy, drain and source on the pull-down's foot (``gate_off``), on the clock,
    #     against Mgate_off's clock edge, whose kick reaches A through the cascodes (below).
    #   - Mctl_cap, a capacitor between gate_ctl and Q, against Mctl_p's kick while the
    #     complementary clock lags (below).
    #   - Mpre is PRECHARGE_W helpers wide: it holds P at vdd while A charges from it.
    # Holds for: a design ``flow.samp.params.valid`` admits; clocks whose edges meet or whose
    #   complement lags by up to an edge; an input that moves no faster than a full-scale sine at
    #   the ADC's Nyquist frequency while holding. Every node held at a rail while holding is held
    #   through a channel: a clock edge moves it by the charge it couples over the node's
    #   capacitance, a moving input by C dV/dt times the channel's resistance. A pair that holds a
    #   whole supply while holding (Mcap between P and Q; Mpre, Mgate and Mgate_top against A;
    #   Mctl_p, Mctl_on and Mctl_cap against gate_ctl and Q) passes the supply by as much: inside
    #   the stress limit at the nominal supply, past it by that coupling at the highest, where the
    #   limit is the supply itself.
    if bootstrap:
        Samp.gate = h.Signal(desc="Boosted switch gate")
        Samp.boot_top, Samp.boot_bot, Samp.gate_ctl = h.Signal(), h.Signal(), h.Signal()
        Samp.gate_top, Samp.gate_mid, Samp.gate_off = h.Signal(), h.Signal(), h.Signal()
        aux = {"vth": param.mos_vth, "w": param.boot_w, "l": 1}
        # [Razavi-ADC] Sec. 3.7, p. 42: a dummy of half its switch's width, W_3 = 0.5 W_1, on the
        # opposite clock, takes the half of the channel charge its switch releases onto the node
        # Terms: the source's M1 Mctl_p (on clk), which releases its channel onto gate_ctl as
        #   tracking starts; its M3 Mctl_dummy (on clk_b), drain and source both on gate_ctl;
        #   W_3 = boot_w // 2.
        # Ours against the source: applied to a helper, not to the sampling switch. The node also
        #   carries Mctl_on's source, whose gate is on clk_b too: its overlap alone balances
        #   Mctl_p's, so with the dummy's two clk_b couples twice what clk does onto gate_ctl. As
        #   tracking starts that pulls gate_ctl a few millivolts down before Mctl_on conducts; as
        #   holding starts at an input near the supply (gate_ctl already near vdd) it lifts
        #   gate_ctl above vdd while clk is still falling, until Mctl_p has pulled it back.
        # Holds for: clock edges that meet; a helper at least two units wide.
        small = {"vth": param.mos_vth, "w": max(1, param.boot_w // 2), "l": 1}
        # the bottom plate follows vin while tracking, its gate boosted with the switch's
        Samp.Mbot_in = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.boot_w, l=param.bot_l)(
            d=Samp.boot_bot, g=Samp.gate, s=Samp.vin, b=Samp.vss
        )
        # bottom plate to vss during hold
        # not in the reference texts: no dummy on the bottom plate. A dummy against Mbot's turn-off
        # would be on clk, its gate-source pair V_DD - V_Q while tracking, past V_DD wherever Q is
        # below 0 V; and early in the track phase Q is: A charges from P, P droops, and the
        # floating Q (Mbot off, the long Mbot_in not yet lifting it) follows P below 0 V by more
        # than Mbot's kick
        # Terms: V_Q boot_bot; V_DD the dummy's gate (clk) while tracking; Mbot's kick its overlap
        #   and its channel's release onto Q as clk_b falls.
        # Holds for: every design; the cost is the kick itself, which passes Mcap's pair (P at vdd
        #   against Q) past the supply by its size as tracking starts.
        Samp.Mbot = mos(tp=MosType.NMOS, **aux)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        # gate pull-down during hold, under the cascodes
        Samp.Mgate_top = mos(tp=MosType.NMOS, **aux)(d=Samp.gate, g=Samp.boot_top, s=Samp.gate_top, b=Samp.vss)
        Samp.Mgate_drop = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_top, g=Samp.gate_top, s=Samp.gate_mid, b=Samp.vss)
        Samp.Mgate_pass = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_top, g=Samp.vdd, s=Samp.gate_mid, b=Samp.vss)
        Samp.Mgate_cas = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_mid, g=Samp.vdd, s=Samp.gate_off, b=Samp.vss)
        Samp.Mgate_off = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_off, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        # not in the reference texts: Mgate_off_dummy as wide as Mgate_off (boot_w), twice the
        # half width the dummy of [Razavi-ADC] Sec. 3.7, p. 42 has: its two overlaps on clk are
        # twice Mgate_off's one on clk_b, so that as tracking starts the foot is kicked above 0 V,
        # not below it
        # Terms: the source's M1 Mgate_off (on clk_b), its M3 Mgate_off_dummy (on clk), drain and
        #   source on gate_off; W_3 = W_1 = boot_w.
        # Ours against the source: Mgate_off's source is the rail, so its channel charge does not
        #   split in halves; the dummy over-compensates on purpose. It keeps the foot's kick off
        #   A, which reduces A's dip below 0 V as tracking starts but does not remove it: A also
        #   follows P through Mpre's channel (on while holding, its gate on A, its source on P)
        #   as Mbot's kick drags Q and P down (Mbot's note), and every pair that holds a supply
        #   against A (Mpre's and Mgate_top's gates, Mgate's drain) passes it by that dip.
        # Holds for: clock edges that meet.
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
        # not in the reference texts: Mctl_cap, gate on gate_ctl, drain and source on Q, boot_w by
        # 4 units, against Mctl_p's kick while the complementary clock lags (as one made from clk
        # through an inverter does): from clk's rise, which turns Mctl_p off, to clk_b's fall,
        # which turns Mctl_on on, gate_ctl floats, and Mctl_p's overlap and channel lift it by
        # Delta V = q / C_ctl above vdd, against Mctl_on's drain and Mgate's drain at 0 V. Mbot
        # holds Q at 0 V meanwhile, so Mctl_cap's gate, its channel inverted with a supply across
        # it, adds to C_ctl about what the node has of its own and halves Delta V. As tracking
        # starts Mctl_on joins its two plates, and it adds no charge to Q: the current Mctl_on
        # carries leaves gate_ctl and enters Q, C_ctl0 Delta V_ctl + C_Q0 Delta V_Q = 0 whatever the
        # capacitance between the two
        # Terms: C_ctl gate_ctl's capacitance (Mctl_p's, Mctl_on's and Mctl_dummy's junctions and
        #   overlaps, Mgate's gate) with Mctl_cap's gate; C_ctl0 and C_Q0 each node's capacitance to
        #   nodes that stay put; q the charge clk's rise moves through Mctl_p's gate-drain
        #   capacitance and its channel's release.
        # Ours against the source: [Razavi-ADC] Fig. 3.41(b), p. 48 drives M3's gate from the clock.
        # Holds for: a complement up to a clock edge late at the nominal supply, the lift then under
        #   the stress limit's margin over the supply, (SUPPLY_CORNER_MAX - 1) V_DD; at the highest
        #   supply there is no margin, and its runs take clock edges that meet. While tracking
        #   gate_ctl is within about a threshold of Q: Mctl_cap's channel is off then, and its two
        #   junctions on Q count in Q's capacitance (flow.samp.params._bottom_f).
        Samp.Mctl_cap = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.boot_w, l=4)(
            d=Samp.boot_bot, g=Samp.gate_ctl, s=Samp.boot_bot, b=Samp.vss
        )
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
                Samp.Mctl_cap,
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
