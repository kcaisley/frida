"""The comparator's circuit: its nets (``Nets``) and its generator (``netlist``), the module
``Comp`` of the design ``Params``.

It builds NMOS or PMOS input pairs on a switched or dynamic (capacitor) tail, single-stage
(StrongARM), double- and triple-tail latches with their on, init and reset devices clocked,
signaled or omitted, and a static output stage that holds each decision.
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.devices import Inverter, LogicCellParams, Nand2, Nor2, logic_pair, mos, mos_cap
from flow.circuit.ports import module_from_ports

from .params import Bias, OutputStage, Params, Stages, State, valid


@h.bundle
class Nets:
    inp, inn = h.Input(), h.Input()
    outp, outn = h.Output(), h.Output()
    clk, clkb = h.Clock(), h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)
    latch_p, latch_n = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))
    input_p_drain, input_n_drain = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))


@h.generator
def netlist(param: Params) -> h.Module:
    """
    Comparator generator.

    Generates StrongARM, double-tail or triple-tail comparators with held differential
    decisions based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not valid(param):
        raise ValueError(f"Invalid comparator params: {param}")

    Comp = module_from_ports("Comp", Nets.signals)
    Comp.tail = h.Signal()

    # Build preamp
    _build_preamp(Comp, param)

    # Build latch
    if param.comp_stages == Stages.TRIPLE:
        _build_triple_tail(Comp, param)
    else:
        _build_latch(Comp, param)

    # Hold each dynamic decision through comparator reset for the SAR update.
    if param.output_stage == OutputStage.STDCELLS:
        _build_output_stdcells(Comp, param, Comp.latch_p, Comp.latch_n)
    else:
        _build_output_srlatch(Comp, param, Comp.latch_p, Comp.latch_n)

    return Comp


def _build_preamp(module, param: Params):
    """Build input differential pair and reset/precharge devices.
    Topology can be inverted to support N or P-type input devices.
    Also supports a 'dynamic' bias, as described in 2018 H. Bindra
    """

    #          ─┬─           ─┬─ preamp_on_rail
    #           │             │
    #           └─┐╷  clk  ╷┌─┘
    #             │├○──┴──○┤│
    #           ┌─┘╵       ╵└─┐
    #  input_p ─┤             ├─ input_n
    #        ╷┌─┘             └─┐╷
    #  inp ──┤│                 │├── inn
    #        ╵└─┐             ┌─┘╵
    #           └──────┬──────┘
    #               ╷┌─┘
    #         clk ──┤│
    #               ╵└─┐
    #                  │
    #                 ─┴─ preamp_init_rail

    # Preamp output nodes

    # Derived polarities from the preamp input type
    diff_type = param.preamp_diff_xtors
    reset_type = MosType.PMOS if diff_type == MosType.NMOS else MosType.NMOS
    tail_type = diff_type

    # The rail that we move toward during comparison
    on_rail = module.vss if diff_type == MosType.NMOS else module.vdd
    # The rail that we move toward during reset
    init_rail = module.vdd if diff_type == MosType.NMOS else module.vss
    # We use the main clock for the reset and tail devices
    on_clk = module.clk if diff_type == MosType.NMOS else module.clkb
    # Opposite polarity is only needed for dynamic bias devices
    off_clk = module.clkb if diff_type == MosType.NMOS else module.clk

    # Differential pair. A triple tail cascodes it with devices held on at the reset rail,
    # isolating the input pair from the precharged outputs. Their gates reach the rail through a
    # tie (a gate on a rail by metal alone breaks TPSC65's rules, and an ESD event on the rail
    # would land on the gate oxide): a diode-connected device of the input pair's type biases the
    # gate of one of the other type, whose drain is the held net, as a library tie cell does.
    if param.comp_stages == Stages.TRIPLE:
        module.cas_p = h.Signal()
        module.cas_n = h.Signal()
        module.cas_gate, module.tie_bias = h.Signal(), h.Signal()
        diff_drain_p, diff_drain_n = module.cas_p, module.cas_n
        module.Mtie_bias = mos(tp=diff_type, vth=param.diffpair_vth, w=1, l=1)(
            d=module.tie_bias, g=module.tie_bias, s=on_rail, b=on_rail
        )
        module.Mtie = mos(tp=reset_type, vth=param.diffpair_vth, w=1, l=1)(
            d=module.cas_gate, g=module.tie_bias, s=init_rail, b=init_rail
        )
        module.Mcas_p = mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=1)(
            d=module.input_p_drain, g=module.cas_gate, s=module.cas_p, b=on_rail
        )
        module.Mcas_n = mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=1)(
            d=module.input_n_drain, g=module.cas_gate, s=module.cas_n, b=on_rail
        )
    else:
        diff_drain_p, diff_drain_n = module.input_p_drain, module.input_n_drain
    module.Mdiff_p = mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=param.diffpair_l)(
        d=diff_drain_p, g=module.inp, s=module.tail, b=on_rail
    )
    module.Mdiff_n = mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=param.diffpair_l)(
        d=diff_drain_n, g=module.inn, s=module.tail, b=on_rail
    )

    # Tail current source
    if param.preamp_bias == Bias.SWITCHED:
        module.Mtail = mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(
            d=module.tail, g=on_clk, s=on_rail, b=on_rail
        )
        module.Mtail_reset = mos(tp=reset_type, vth=param.tail_vth, w=param.tail_w, l=1)(
            d=module.tail, g=on_clk, s=init_rail, b=init_rail
        )
    elif param.preamp_bias == Bias.DYNAMIC:
        # Source of tail device connects to a cap node that stores charge
        # during init (via mbias) and sources current during comparison
        module.cap_node = h.Signal()
        module.Mtail = mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(
            d=module.tail, g=on_clk, s=module.cap_node, b=on_rail
        )
        module.Mbias = mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(
            d=module.cap_node, g=off_clk, s=on_rail, b=on_rail
        )
        # the tail capacitor, a MOS capacitor of the reset's type against the reset rail: the cap
        # node starts at the evaluation rail, a supply away, and moves toward it by a few hundred mV
        module.Mcap_tail = mos_cap(param.bias_c_ff, tp=reset_type, vth=param.tail_vth)(
            d=init_rail, g=module.cap_node, s=init_rail, b=init_rail
        )

    # The input pair's load beyond its devices' own (C_P): more charge to move before the latch takes
    # over (a longer integration, more gain, less noise: kT/C). MOS capacitors of the input pair's
    # type against the evaluation rail: the drains start at the reset rail, a supply away, and fall.
    if param.preamp_c_ff:
        module.Mcap_p = mos_cap(param.preamp_c_ff, tp=diff_type, vth=param.diffpair_vth)(
            d=on_rail, g=module.input_p_drain, s=on_rail, b=on_rail
        )
        module.Mcap_n = mos_cap(param.preamp_c_ff, tp=diff_type, vth=param.diffpair_vth)(
            d=on_rail, g=module.input_n_drain, s=on_rail, b=on_rail
        )

    # Reset/precharge devices (minimum length = 1)
    # Precharge preamp outputs during reset phase.
    # For NMOS input: PMOS reset gate=clk → ON when clk=0, OFF when clk=1
    # For PMOS input: NMOS reset gate=clkb → ON when clkb=1, OFF when clkb=0
    module.Mrst_p = mos(tp=reset_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.input_p_drain, g=on_clk, s=init_rail, b=init_rail
    )
    module.Mrst_n = mos(tp=reset_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.input_n_drain, g=on_clk, s=init_rail, b=init_rail
    )


# fmt: on


def _build_latch(module, param: Params):
    """Generate cross coupled latch connected to preamp.

    Supports either a single Strong-ARM style stage, or a
    double stage with two tails.
    """
    # This is a convenient
    opposite = {
        module.vdd: module.vss,
        module.vss: module.vdd,
        module.clk: module.clkb,
        module.clkb: module.clk,
    }

    # Input devices determine the opposite
    preamp_init_rail = module.vdd if param.preamp_diff_xtors == MosType.NMOS else module.vss

    # In a single stage, the late pre-charges to same rail as the preamp, in double stage it's opposite
    latch_init_rail = preamp_init_rail if param.comp_stages == Stages.SINGLE else opposite[preamp_init_rail]
    # And the rail when comparison is on, is then the opposite of the precharge init
    latch_on_rail = opposite[latch_init_rail]

    # The latch has at most 12 devices: 4 in the cross-coupled inverters,
    # plus inner/outer init and on current-steering devices.
    # In all architectures, init and on devices split cleanly along the
    # NMOS/PMOS division, so we only ever need a single polarity clock
    # for the latch itself.
    latch_init_type = MosType.NMOS if latch_init_rail == module.vss else MosType.PMOS
    latch_on_type = MosType.PMOS if latch_on_rail == module.vdd else MosType.NMOS
    latch_clk = module.clkb if latch_init_type == MosType.NMOS else module.clk

    # --- Mcross_init: cross-coupled inverter pair, init side (always present) ---
    #
    # (Mcross_on pair connects above)
    #
    # latch_n                   latch_p
    #  │                           │
    #  │                           │
    #  └─┐╷  latch_p     latch_n  ╷┌─┘
    #    │├───               ───┤│
    #  ┌─┘╵                     ╵└─┐
    #  │                           │
    #  │                           │
    #  │                           │
    # ─┴─     latch_init_rail     ─┴─

    module.Mcross_init_p = mos(
        tp=latch_init_type,
        vth=param.latch_vth,
        w=param.latch_init_w,
        l=param.latch_init_l,
    )(d=module.latch_p, g=module.latch_n, s=latch_init_rail, b=latch_init_rail)
    module.Mcross_init_n = mos(
        tp=latch_init_type,
        vth=param.latch_vth,
        w=param.latch_init_w,
        l=param.latch_init_l,
    )(d=module.latch_n, g=module.latch_p, s=latch_init_rail, b=latch_init_rail)

    # --- Minner_init: inner init (reset) devices ---
    # When signaled: gates driven by preamp outputs (cross-coupled)
    # When clocked: gates driven by latch_clk
    # Every signaled latch device takes the opposite input pair's drain (the drain
    # of the inp device drives the latch_p side): the first drain to move releases
    # its init device and turns on its on device together, and latch_p ends high
    # when inp > inn.
    if param.latch_inner_init_xtors == State.SIGNAL:
        init_inner_gate_p = module.input_p_drain
        init_inner_gate_n = module.input_n_drain
    if param.latch_inner_init_xtors == State.CLOCK:
        init_inner_gate_p = latch_clk
        init_inner_gate_n = latch_clk

    module.Minner_init_p = mos(tp=latch_init_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.latch_p, g=init_inner_gate_p, s=latch_init_rail, b=latch_init_rail
    )
    module.Minner_init_n = mos(tp=latch_init_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.latch_n, g=init_inner_gate_n, s=latch_init_rail, b=latch_init_rail
    )

    # --- Minner_on: inner on (current steering) devices ---
    # Only valid in double stage mode. Drains connect to latch_p/latch_n,
    # sources introduce midp/midn nodes.
    if param.latch_inner_on_xtors != State.OMIT:
        module.midp = h.Signal()
        module.midn = h.Signal()

        if param.latch_inner_on_xtors == State.SIGNAL:
            inner_on_gate_p = module.input_p_drain
            inner_on_gate_n = module.input_n_drain
        elif param.latch_inner_on_xtors == State.CLOCK:
            inner_on_gate_p = latch_clk
            inner_on_gate_n = latch_clk

        module.Minner_on_p = mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.latch_p, g=inner_on_gate_p, s=module.midp, b=latch_on_rail)
        module.Minner_on_n = mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.latch_n, g=inner_on_gate_n, s=module.midn, b=latch_on_rail)

    # --- Mcross_on: cross-coupled inverter pair, on side ---
    # Drains connect to midp/midn if inner_on devices exist, otherwise latch_p/latch_n.
    # Sources connect to outerp/outern if outer_on devices exist, otherwise on_rail.
    cross_on_drain_p = module.midp if param.latch_inner_on_xtors != State.OMIT else module.latch_p
    cross_on_drain_n = module.midn if param.latch_inner_on_xtors != State.OMIT else module.latch_n

    # If single stage, cross-coupled latch outer driven directly from preamp
    if param.comp_stages == Stages.SINGLE:
        cross_on_src_p = module.input_n_drain
        cross_on_src_n = module.input_p_drain
    # Double stage with outer on: intermediate node to outer devices
    elif param.latch_tail_shared:
        module.outer = h.Signal()
        cross_on_src_p = module.outer
        cross_on_src_n = module.outer
    elif param.latch_outer_on_xtors != State.OMIT:
        module.outerp = h.Signal()
        module.outern = h.Signal()
        cross_on_src_p = module.outerp
        cross_on_src_n = module.outern
    # Double stage without outer on: connect directly to on rail
    else:
        cross_on_src_p = latch_on_rail
        cross_on_src_n = latch_on_rail

    module.Mcross_on_p = mos(
        tp=latch_on_type,
        vth=param.latch_vth,
        w=param.latch_on_w,
        l=param.latch_on_l,
    )(d=cross_on_drain_p, g=module.latch_n, s=cross_on_src_p, b=latch_on_rail)
    module.Mcross_on_n = mos(
        tp=latch_on_type,
        vth=param.latch_vth,
        w=param.latch_on_w,
        l=param.latch_on_l,
    )(d=cross_on_drain_n, g=module.latch_p, s=cross_on_src_n, b=latch_on_rail)

    # --- Mouter_on: outer on (currently steering) devices ---
    # Only available in double stage mode. A shared tail is one device of the
    # pair's combined width feeding both halves.
    if param.latch_tail_shared:
        module.Mouter_on = mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=param.latch_tail_w or 2 * param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outer, g=latch_clk, s=latch_on_rail, b=latch_on_rail)
    elif param.latch_outer_on_xtors != State.OMIT:
        if param.latch_outer_on_xtors == State.SIGNAL:
            outer_on_gate_p = module.input_p_drain
            outer_on_gate_n = module.input_n_drain
        elif param.latch_outer_on_xtors == State.CLOCK:
            outer_on_gate_p = latch_clk
            outer_on_gate_n = latch_clk

        module.Mouter_on_p = mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outerp, g=outer_on_gate_p, s=latch_on_rail, b=latch_on_rail)
        module.Mouter_on_n = mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outern, g=outer_on_gate_n, s=latch_on_rail, b=latch_on_rail)

    # --- Mouter_init: outer init (reset) devices ---
    # Requires outer_on devices to exist (for outerp/outern nodes).
    if param.latch_outer_init_xtors != State.OMIT:
        if param.latch_outer_init_xtors == State.SIGNAL:
            outer_init_gate_p = module.input_p_drain
            outer_init_gate_n = module.input_n_drain
        elif param.latch_outer_init_xtors == State.CLOCK:
            outer_init_gate_p = latch_clk
            outer_init_gate_n = latch_clk

        module.Mouter_init_p = mos(
            tp=latch_init_type,
            vth=param.rst_vth,
            w=param.rst_w,
            l=param.rst_l,
        )(d=module.outerp, g=outer_init_gate_p, s=latch_init_rail, b=latch_init_rail)
        module.Mouter_init_n = mos(
            tp=latch_init_type,
            vth=param.rst_vth,
            w=param.rst_w,
            l=param.rst_l,
        )(d=module.outern, g=outer_init_gate_n, s=latch_init_rail, b=latch_init_rail)


# fmt: on


def _build_triple_tail(module, param: Params):
    """Second and third stages of a triple-tail comparator.

    Stage two is a double tail's second stage without its init cross pair: a
    clocked tail feeds a cross-coupled pair of the reset polarity, whose nodes
    midp/midn are held at the evaluation rail by input devices gated by the
    input pair's drains. Stage three is a clocked-tail latch, precharged through
    devices gated by stage two: midp releases latch_n, so latch_p ends at the
    reset rail when inp > inn, as in a StrongARM.

    Stages one and three start on the same clock edge, so stage three must not
    regenerate before stage two decides: its precharge devices (4x reset width)
    outdrive its tail (the latch on width) while stage two holds them on.
    """

    diff_type = param.preamp_diff_xtors
    reset_type = MosType.PMOS if diff_type == MosType.NMOS else MosType.NMOS
    on_rail = module.vss if diff_type == MosType.NMOS else module.vdd
    init_rail = module.vdd if diff_type == MosType.NMOS else module.vss
    on_clk = module.clk if diff_type == MosType.NMOS else module.clkb
    off_clk = module.clkb if diff_type == MosType.NMOS else module.clk
    vth = param.latch_vth

    module.tail2 = h.Signal()
    module.midp = h.Signal()
    module.midn = h.Signal()
    module.Mtail2 = mos(tp=reset_type, vth=vth, w=param.latch_tail_w or 2 * param.latch_on_w, l=param.latch_on_l)(
        d=module.tail2, g=off_clk, s=init_rail, b=init_rail
    )
    module.Mmid_cross_p = mos(tp=reset_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midp, g=module.midn, s=module.tail2, b=init_rail
    )
    module.Mmid_cross_n = mos(tp=reset_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midn, g=module.midp, s=module.tail2, b=init_rail
    )
    module.Mmid_in_p = mos(tp=diff_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.midp, g=module.input_p_drain, s=on_rail, b=on_rail
    )
    module.Mmid_in_n = mos(tp=diff_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.midn, g=module.input_n_drain, s=on_rail, b=on_rail
    )

    module.tail3 = h.Signal()
    module.Mtail3 = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.tail3, g=on_clk, s=on_rail, b=on_rail
    )
    module.Mcross_on_p = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.latch_p, g=module.latch_n, s=module.tail3, b=on_rail
    )
    module.Mcross_on_n = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.latch_n, g=module.latch_p, s=module.tail3, b=on_rail
    )
    module.Mcross_init_p = mos(tp=reset_type, vth=vth, w=param.latch_init_w, l=param.latch_init_l)(
        d=module.latch_p, g=module.latch_n, s=init_rail, b=init_rail
    )
    module.Mcross_init_n = mos(tp=reset_type, vth=vth, w=param.latch_init_w, l=param.latch_init_l)(
        d=module.latch_n, g=module.latch_p, s=init_rail, b=init_rail
    )
    module.Minner_init_p = mos(tp=reset_type, vth=param.rst_vth, w=4 * param.rst_w, l=param.rst_l)(
        d=module.latch_p, g=module.midn, s=init_rail, b=init_rail
    )
    module.Minner_init_n = mos(tp=reset_type, vth=param.rst_vth, w=4 * param.rst_w, l=param.rst_l)(
        d=module.latch_n, g=module.midp, s=init_rail, b=init_rail
    )


def _build_output_srlatch(module, param: Params, latch_p, latch_n):
    """Build a static CMOS SR latch and buffered differential outputs.

    The dynamic comparator nodes return to their common reset level after each
    evaluation. Input inverters turn their differential decision into either
    active-high or active-low set/reset pulses. A cross-coupled NOR or NAND
    latch, selected from the dynamic-node reset polarity, retains that decision
    until the next comparison. Two inverter stages isolate the latch from its
    output load while preserving the one-hot output polarity.
    """

    # every gate drives one NMOS and one PMOS: they share a finger count (logic cells)
    (n_w, n_nf), (p_w, p_nf) = logic_pair(param.srlatch_n_w, param.srlatch_p_w)
    (n_w2, n_nf2), (p_w2, p_nf2) = logic_pair(2 * param.srlatch_n_w, 2 * param.srlatch_p_w)

    # Convert the dynamic inner nodes into the former direct-buffer outputs.
    # During evaluation exactly one of these differential signals asserts.
    module.decision_p = h.Signal(desc="Dynamic positive decision")
    module.decision_n = h.Signal(desc="Dynamic negative decision")
    module.Mdecision_p_p = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
        d=module.decision_p, g=latch_n, s=module.vdd, b=module.vdd
    )
    module.Mdecision_p_n = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
        d=module.decision_p, g=latch_n, s=module.vss, b=module.vss
    )
    module.Mdecision_n_p = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
        d=module.decision_n, g=latch_p, s=module.vdd, b=module.vdd
    )
    module.Mdecision_n_n = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
        d=module.decision_n, g=latch_p, s=module.vss, b=module.vss
    )

    module.sr_p = h.Signal(desc="Held positive decision")
    module.sr_n = h.Signal(desc="Held negative decision")
    module.sr_p_stack = h.Signal()
    module.sr_n_stack = h.Signal()

    preamp_resets_high = param.preamp_diff_xtors == MosType.NMOS
    # The latch nodes reset with the preamp in a StrongARM and a triple tail's last
    # stage, and to the opposite rail in a double tail.
    inner_resets_high = preamp_resets_high if param.comp_stages != Stages.DOUBLE else not preamp_resets_high

    if inner_resets_high:
        # decision_p/n are low between comparisons. Cross-coupled NOR gates
        # accept their active-high assertion and retain the resulting state.
        module.Msr_p_p_decision = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p_stack, g=module.decision_n, s=module.vdd, b=module.vdd
        )
        module.Msr_p_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p, g=module.sr_n, s=module.sr_p_stack, b=module.vdd
        )
        module.Msr_p_n_decision = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p, g=module.decision_n, s=module.vss, b=module.vss
        )
        module.Msr_p_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p, g=module.sr_n, s=module.vss, b=module.vss
        )

        module.Msr_n_p_decision = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n_stack, g=module.decision_p, s=module.vdd, b=module.vdd
        )
        module.Msr_n_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n, g=module.sr_p, s=module.sr_n_stack, b=module.vdd
        )
        module.Msr_n_n_decision = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n, g=module.decision_p, s=module.vss, b=module.vss
        )
        module.Msr_n_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n, g=module.sr_p, s=module.vss, b=module.vss
        )
    else:
        # decision_p/n are high between comparisons. Cross-coupled NAND gates
        # accept their active-low assertion and retain the resulting state:
        # latch_p rising pulls decision_n low, which sets sr_p.
        module.Msr_p_p_decision = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p, g=module.decision_n, s=module.vdd, b=module.vdd
        )
        module.Msr_p_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p, g=module.sr_n, s=module.vdd, b=module.vdd
        )
        module.Msr_p_n_decision = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p, g=module.decision_n, s=module.sr_p_stack, b=module.vss
        )
        module.Msr_p_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p_stack, g=module.sr_n, s=module.vss, b=module.vss
        )

        module.Msr_n_p_decision = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n, g=module.decision_p, s=module.vdd, b=module.vdd
        )
        module.Msr_n_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n, g=module.sr_p, s=module.vdd, b=module.vdd
        )
        module.Msr_n_n_decision = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n, g=module.decision_p, s=module.sr_n_stack, b=module.vss
        )
        module.Msr_n_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n_stack, g=module.sr_p, s=module.vss, b=module.vss
        )

    # Two inverter stages buffer the static latch without changing polarity.
    module.outp_b = h.Signal()
    module.outn_b = h.Signal()
    module.Mbuf1_outp_p = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
        d=module.outp_b, g=module.sr_p, s=module.vdd, b=module.vdd
    )
    module.Mbuf1_outp_n = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
        d=module.outp_b, g=module.sr_p, s=module.vss, b=module.vss
    )
    module.Mbuf1_outn_p = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w, l=1, nf=p_nf)(
        d=module.outn_b, g=module.sr_n, s=module.vdd, b=module.vdd
    )
    module.Mbuf1_outn_n = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w, l=1, nf=n_nf)(
        d=module.outn_b, g=module.sr_n, s=module.vss, b=module.vss
    )
    module.Mbuf2_outp_p = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w2, l=1, nf=p_nf2)(
        d=module.outp, g=module.outp_b, s=module.vdd, b=module.vdd
    )
    module.Mbuf2_outp_n = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w2, l=1, nf=n_nf2)(
        d=module.outp, g=module.outp_b, s=module.vss, b=module.vss
    )
    module.Mbuf2_outn_p = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=p_w2, l=1, nf=p_nf2)(
        d=module.outn, g=module.outn_b, s=module.vdd, b=module.vdd
    )
    module.Mbuf2_outn_n = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=n_w2, l=1, nf=n_nf2)(
        d=module.outn, g=module.outn_b, s=module.vss, b=module.vss
    )


# fmt: on


def _build_output_stdcells(module, param: Params, latch_p, latch_n):
    """The output stage of ``_build_output_srlatch`` as generic logic cells: decision inverters,
    an SR latch of two NOR2 (latch nodes reset high) or NAND2 gates, and two inverting buffers."""

    module.decision_p, module.decision_n = h.Signal(), h.Signal()
    module.sr_p, module.sr_n = h.Signal(), h.Signal()
    module.outp_b, module.outn_b = h.Signal(), h.Signal()
    supplies = {"VDD": module.vdd, "VSS": module.vss}
    module.Xdecision_p = Inverter(LogicCellParams(drive=1))(A=latch_n, Y=module.decision_p, **supplies)
    module.Xdecision_n = Inverter(LogicCellParams(drive=1))(A=latch_p, Y=module.decision_n, **supplies)
    preamp_resets_high = param.preamp_diff_xtors == MosType.NMOS
    inner_resets_high = preamp_resets_high if param.comp_stages != Stages.DOUBLE else not preamp_resets_high
    gate, drive = (Nor2, 2) if inner_resets_high else (Nand2, 1)
    module.Xsr_p = gate(LogicCellParams(drive=drive))(A=module.decision_n, B=module.sr_n, Y=module.sr_p, **supplies)
    module.Xsr_n = gate(LogicCellParams(drive=drive))(A=module.decision_p, B=module.sr_p, Y=module.sr_n, **supplies)
    module.Xbuf1_outp = Inverter(LogicCellParams(drive=4))(A=module.sr_p, Y=module.outp_b, **supplies)
    module.Xbuf1_outn = Inverter(LogicCellParams(drive=4))(A=module.sr_n, Y=module.outn_b, **supplies)
    module.Xbuf2_outp = Inverter(LogicCellParams(drive=8))(A=module.outp_b, Y=module.outp, **supplies)
    module.Xbuf2_outn = Inverter(LogicCellParams(drive=8))(A=module.outn_b, Y=module.outn, **supplies)
