"""The comparator's circuit: its nets (``Nets``) and its generator (``netlist``), the module
``Comp`` of the design ``Params``.

It builds NMOS or PMOS input pairs on a switched or dynamic (capacitor) tail, each latch of
``Latch`` (the StrongARM, the double tails and the triple tail), and a static output stage that
holds each decision.

Each sizing rule carries its source beside it (docs/references.md), the source's devices named as
this netlist's, and where it holds. The comments are written for an NMOS input pair (the reset rail
the supply, the evaluation rail ground); a PMOS pair mirrors every device and rail.
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.devices import Inverter, LogicCellParams, Nand2, Nor2, logic_pair
from flow.circuit.ports import module_from_ports
from flow.layout.devices.moscap.netlist import mos_cap
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import Border, EdgePin, Half, edge_pins, halves, place, row, rows

from .params import Bias, Latch, OutputStage, Params


@h.bundle
class Nets:
    inp, inn = h.Input(), h.Input()
    outp, outn = h.Output(), h.Output()
    clk, clkb = h.Clock(), h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)
    latch_p, latch_n = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))
    input_p_drain, input_n_drain = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """
    Comparator generator.

    Generates StrongARM, double-tail or triple-tail comparators with held differential
    decisions based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    Comp = module_from_ports("Comp", Nets.signals)
    # its inputs on its outline's top, mirror images of each other (flow.layout.pins)
    edge_pins(Comp, EdgePin(Comp.inp, Border.TOP, mirror=Comp.inn))
    Comp.tail = h.Signal()

    # Build preamp
    _build_preamp(Comp, param)

    # Build latch
    if param.latch is Latch.TRIPLE_TAIL:
        _build_triple_tail(Comp, param)
    else:
        _build_latch(Comp, param)

    # Hold each dynamic decision through comparator reset for the SAR update.
    if param.output_stage == OutputStage.STDCELLS:
        _build_output_stdcells(Comp, param, Comp.latch_p, Comp.latch_n)
    else:
        _build_output_srlatch(Comp, param, Comp.latch_p, Comp.latch_n)

    _place(Comp, param)
    return Comp


def _place(module: h.Module, param: Params) -> None:
    """The comparator's rows, top first, by its devices' roles, each row mirrored about the
    centre (a half's devices on its side): the tail capacitor, the input pair (its cascodes
    outside), the bias capacitor and its switch, the triple tail's ties, the reset and the latch (a
    StrongARM's latch above its reset), its init pair split cross-quad over two rows, the
    standard-cell output stage. The large devices are split in two, each half (``(name, index)``)
    in its own row. A device in no rule (the output stage drawn transistor by transistor) states
    nothing: ALIGN places the comparator on its own."""
    split = ("Mcap_tail", "Mcap_p", "Mcap_n", "Mcross_init_p", "Mcross_init_n")
    parts = {name: halves(module.instances[name]) for name in split if name in module.instances}
    reset = [["Mrst_p", "Mtail_reset", "Mrst_n"]]
    middle = [
        ["Mmid_cross_p", "Mtail2", "Mmid_cross_n"],
        ["Mmid_in_p", "Mmid_cross_init_p", "Mmid_cross_init_n", "Mmid_in_n"],
    ]
    on = [
        [
            "Mouter_on_p",
            "Mcross_on_p",
            "Minner_on_p",
            "Mtail3_p",
            "Mouter_on",
            "Mtail3_n",
            "Minner_on_n",
            "Mcross_on_n",
            "Mouter_on_n",
        ]
    ]
    order = [
        [("Mcap_tail", 0)],
        [("Mcap_tail", 1)],
        ["Mcas_p", "Mdiff_p", "Mtail", "Mdiff_n", "Mcas_n"],
        [("Mcap_p", 0), "Mbias", ("Mcap_n", 0)],
        [("Mcap_n", 1), ("Mcap_p", 1)],
        ["Mtie_bias"],
        ["Mtie"],
        *(on + reset if param.latch is Latch.STRONGARM else reset + middle + on),
        [
            "Mouter_init_p",
            "Minner_init_p",
            ("Mcross_init_p", 0),
            ("Mcross_init_n", 0),
            "Minner_init_n",
            "Mouter_init_n",
        ],
        [("Mcross_init_n", 1), ("Mcross_init_p", 1)],
        ["Xbuf2_outp", "Xbuf1_outp", "Xsr_p", "Xdecision_n", "Xdecision_p", "Xsr_n", "Xbuf1_outn", "Xbuf2_outn"],
    ]
    placed = rows(*(row(*(_entry(module, parts, name) for name in names)) for names in order))
    covered = {id(e.instance if isinstance(e, Half) else e) for r in placed.rows for e in r.instances}
    if all(id(instance) in covered for instance in module.instances.values()):
        place(module, placed)


def _entry(module: h.Module, parts: dict[str, tuple[Half, ...]], name: str | tuple[str, int]):
    """A row's entry: the instance ``name`` of ``module``, or a split one's half ``(name, index)``;
    None where the comparator has no such device."""
    if isinstance(name, tuple):
        return parts[name[0]][name[1]] if name[0] in parts else None
    return module.instances.get(name)


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
    diff_type = param.input_pair
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
    # tie (a kit's rules may forbid a gate on a rail by metal alone, and an ESD event on the rail
    # would land on the gate oxide): a diode-connected device of the input pair's type biases the
    # gate of one of the other type, whose drain is the held net, as a library tie cell does.
    if param.latch is Latch.TRIPLE_TAIL:
        module.cas_p = h.Signal()
        module.cas_n = h.Signal()
        module.cas_gate, module.tie_bias = h.Signal(), h.Signal()
        diff_drain_p, diff_drain_n = module.cas_p, module.cas_n
        # not in the reference texts: the tie's size (frida's own). cas_gate carries the two
        # cascodes' gates alone, which their drains and sources (a supply's swing each decision)
        # push through the gate capacitances; Mtie returns that charge to the rail. It holds the
        # gate where its on-resistance times that capacitance is short against the drains' edges:
        # as wide as one cascode at the minimum length, a ratio that keeps the product whatever
        # the pair's width. Mtie_bias, the diode that biases its gate, carries no current: the
        # narrowest device of two fingers
        module.Mtie_bias = mos(tp=diff_type, vth=param.vth, w=2, l=1)(
            d=module.tie_bias, g=module.tie_bias, s=on_rail, b=on_rail
        )
        module.Mtie = mos(tp=reset_type, vth=param.vth, w=param.diffpair_w, l=1)(
            d=module.cas_gate, g=module.tie_bias, s=init_rail, b=init_rail
        )
        # not in the reference texts: the cascodes' size (frida's own): Mcas_p/n as wide as the
        # input pair, at the minimum length; holds for the triple tail, the one latch that
        # cascodes its pair
        module.Mcas_p = mos(tp=diff_type, vth=param.vth, w=param.diffpair_w, l=1)(
            d=module.input_p_drain, g=module.cas_gate, s=module.cas_p, b=on_rail
        )
        module.Mcas_n = mos(tp=diff_type, vth=param.vth, w=param.diffpair_w, l=1)(
            d=module.input_n_drain, g=module.cas_gate, s=module.cas_n, b=on_rail
        )
    else:
        diff_drain_p, diff_drain_n = module.input_p_drain, module.input_n_drain
    module.Mdiff_p = mos(tp=diff_type, vth=param.vth, w=param.diffpair_w, l=param.diffpair_l)(
        d=diff_drain_p, g=module.inp, s=module.tail, b=on_rail
    )
    module.Mdiff_n = mos(tp=diff_type, vth=param.vth, w=param.diffpair_w, l=param.diffpair_l)(
        d=diff_drain_n, g=module.inn, s=module.tail, b=on_rail
    )

    # Tail current source
    if param.bias == Bias.SWITCHED:
        # [Razavi-ADC] Sec. 5.8.3, Fig. 5.37, p. 94: the StrongArm's clocked tail device: Mtail
        # not in the reference texts: Mtail_reset, which takes the tail node to the reset rail
        # while Mtail is off (the source precharges P, Q, X and Y, not the tail node): every
        # decision then starts from the same state, none of the last one's left on the pair's
        # sources (what [Razavi-ADC] Sec. 7.1, p. 129 calls dynamic offset). As wide as Mtail at
        # the minimum length: it only has to charge the tail node within the reset
        module.Mtail = mos(tp=tail_type, vth=param.vth, w=param.tail_w, l=param.tail_l)(
            d=module.tail, g=on_clk, s=on_rail, b=on_rail
        )
        module.Mtail_reset = mos(tp=reset_type, vth=param.vth, w=param.tail_w, l=1)(
            d=module.tail, g=on_clk, s=init_rail, b=init_rail
        )
    elif param.bias == Bias.DYNAMIC:
        # Source of tail device connects to a cap node that stores charge
        # during init (via mbias) and sources current during comparison
        # [Bindra] Fig. 3(a), p. 2: the dynamic bias; its M3a: Mtail, its M3b: Mbias, its V_CAP:
        # cap_node
        # [Bindra] Sec. III, p. 4: M3a minimum-sized (here tail_w by tail_l: a family sets them,
        # runs.dynamic_bias)
        # not in the reference texts: Mbias as wide and as long as Mtail. It holds where Mbias
        # empties C_TAIL within the reset: its on-resistance times bias_c_ff well under
        # TbParams.reset_time_s
        module.cap_node = h.Signal()
        module.Mtail = mos(tp=tail_type, vth=param.vth, w=param.tail_w, l=param.tail_l)(
            d=module.tail, g=on_clk, s=module.cap_node, b=on_rail
        )
        module.Mbias = mos(tp=tail_type, vth=param.vth, w=param.tail_w, l=param.tail_l)(
            d=module.cap_node, g=off_clk, s=on_rail, b=on_rail
        )
        # [Bindra] Fig. 3(a), p. 2: C_TAIL, from V_CAP to ground: Mcap_tail, bias_c_ff of nominal
        # capacitance on cap_node
        # Ours differs twice: a MOS capacitor where the source's is a metal one (Sec. V, p. 7),
        # and against the reset rail, not the evaluation rail (the same capacitance to a supply:
        # of the reset's type, its gate on cap_node, in inversion while cap_node is at the
        # evaluation rail). It holds its value while cap_node, which rises by a few hundred mV in
        # a decision, stays more than a threshold from the reset rail
        module.Mcap_tail = mos_cap(param.bias_c_ff, tp=reset_type, vth=param.vth)(
            d=init_rail, g=module.cap_node, s=init_rail, b=init_rail
        )

    # [Bindra] Eq. (15), p. 6: the pair's input-referred noise power, inversely proportional to C_P
    # [Bindra] Eq. (1), p. 4: the integration time, proportional to C_P
    # C_P: everything on a drain node (input_p_drain, input_n_drain): Mcap_p/n, the part
    # preamp_c_ff adds, and the node's own (Mdiff's or Mcas's drain, Mrst's drain, the latch gates
    # on it), which the parameter does not count. Ours is a MOS capacitor of the input pair's
    # type against the evaluation rail (the source adds metal capacitors, Sec. V, p. 7): the
    # drains start at the reset rail, a supply away, and fall. It keeps its value only while the
    # drain is well above a threshold over the evaluation rail: the drains fall by at most C_TAIL /
    # (C_TAIL + 2 C_P) of the supply (Eq. (8), p. 5), so at the larger ratios the capacitance
    # falls off toward the end of a decision
    if param.bias == Bias.DYNAMIC:
        module.Mcap_p = mos_cap(param.preamp_c_ff, tp=diff_type, vth=param.vth)(
            d=on_rail, g=module.input_p_drain, s=on_rail, b=on_rail
        )
        module.Mcap_n = mos_cap(param.preamp_c_ff, tp=diff_type, vth=param.vth)(
            d=on_rail, g=module.input_n_drain, s=on_rail, b=on_rail
        )

    # Reset/precharge devices, rst_w by rst_l
    # Precharge preamp outputs during reset phase.
    # For NMOS input: PMOS reset gate=clk → ON when clk=0, OFF when clk=1
    # For PMOS input: NMOS reset gate=clkb → ON when clkb=1, OFF when clkb=0
    # [Razavi-ADC] Sec. 7.2, p. 130: the reset switches, sized to pull their nodes to V_DD within
    # the reset
    # S1-S4 (one width for the four, Fig. 7.4, p. 131): Mrst_p/n here and the latch's init devices
    # (Minner_init_p/n, Mouter_init_p/n: _build_latch), all rst_w by rst_l; the triple tail's
    # later stages size theirs by their latch (_build_triple_tail). Holds where each pulls its
    # node to the rail within TbParams.reset_time_s
    module.Mrst_p = mos(tp=reset_type, vth=param.vth, w=param.rst_w, l=param.rst_l)(
        d=module.input_p_drain, g=on_clk, s=init_rail, b=init_rail
    )
    module.Mrst_n = mos(tp=reset_type, vth=param.vth, w=param.rst_w, l=param.rst_l)(
        d=module.input_n_drain, g=on_clk, s=init_rail, b=init_rail
    )


# fmt: on


def _build_latch(module, param: Params):
    """The latch after the input pair, its cross-coupled pair and, by the latch (every one but the
    triple tail, ``_build_triple_tail``):

    - StrongARM: one stage, stacked on the input pair (its on pair's sources the pair's drains), its
      inner init devices clocked;
    - double tail (Schinkel): a second stage on the opposite rails, one clocked tail (the outer on
      device) under both halves, its inner init devices driven by the input pair's drains;
    - self-timed double tail: an outer on and an outer init device per half instead of the tail,
      all driven by the input pair's drains, as its inner init devices;
    - modified double tail (van Elzakker): no tail, inner on devices driven by the input pair's
      drains between the cross pair and the latch nodes, its inner init devices clocked;
    - self-timed modified double tail: the modified latch, its inner init devices driven by the
      input pair's drains.
    """
    latch = param.latch
    stacked = latch is Latch.STRONGARM
    shared_tail = latch is Latch.DOUBLE_TAIL
    self_timed_outer = latch is Latch.DOUBLE_TAIL_SELF_TIMED
    inner_on = latch in (Latch.DOUBLE_TAIL_MODIFIED, Latch.DOUBLE_TAIL_MODIFIED_SELF_TIMED)
    signaled_init = latch in (Latch.DOUBLE_TAIL, Latch.DOUBLE_TAIL_SELF_TIMED, Latch.DOUBLE_TAIL_MODIFIED_SELF_TIMED)
    # This is a convenient
    opposite = {
        module.vdd: module.vss,
        module.vss: module.vdd,
        module.clk: module.clkb,
        module.clkb: module.clk,
    }

    # Input devices determine the opposite
    preamp_init_rail = module.vdd if param.input_pair == MosType.NMOS else module.vss

    # In a single stage, the late pre-charges to same rail as the preamp, in double stage it's opposite
    latch_init_rail = preamp_init_rail if stacked else opposite[preamp_init_rail]
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

    # not in the reference texts: the latch's two sizes (no source gives a formula; [Razavi-ADC]
    # Sec. 7.2, p. 130 and Sec. 7.4, pp. 132-133 weigh the two pairs' widths against offset and
    # speed). latch_init_w by latch_init_l: the cross pair on the init rail (Mcross_init_p/n, the
    # source's M5-M6). latch_on_w by latch_on_l: the cross pair on the on side (Mcross_on_p/n, its
    # M3-M4) and every on device in series with it (Minner_on_p/n, Mouter_on_p/n), so that a stack
    # is one size. Holds for every latch but the triple tail's (_build_triple_tail)
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
        vth=param.vth,
        w=param.latch_init_w,
        l=param.latch_init_l,
    )(d=module.latch_p, g=module.latch_n, s=latch_init_rail, b=latch_init_rail)
    module.Mcross_init_n = mos(
        tp=latch_init_type,
        vth=param.vth,
        w=param.latch_init_w,
        l=param.latch_init_l,
    )(d=module.latch_n, g=module.latch_p, s=latch_init_rail, b=latch_init_rail)

    # --- Minner_init: inner init (reset) devices ---
    # Driven by the input pair's drains (signaled_init), else clocked by latch_clk.
    # Every signaled latch device takes the opposite input pair's drain (the drain
    # of the inp device drives the latch_p side): the first drain to move releases
    # its init device and turns on its on device together, and latch_p ends high
    # when inp > inn.
    # [Razavi-ADC] Eqs. (5.2)-(5.3), p. 72: the output high for a positive input
    # not in the reference texts: the wiring that gives it in every latch here: latch_p is the
    # side the inp device's drain (input_p_drain) acts on, and it ends high for inp > inn
    # (analysis.analyze_decisions reads the held outputs by it, outp high)
    if signaled_init:
        init_inner_gate_p = module.input_p_drain
        init_inner_gate_n = module.input_n_drain
    else:
        init_inner_gate_p = latch_clk
        init_inner_gate_n = latch_clk

    module.Minner_init_p = mos(tp=latch_init_type, vth=param.vth, w=param.rst_w, l=param.rst_l)(
        d=module.latch_p, g=init_inner_gate_p, s=latch_init_rail, b=latch_init_rail
    )
    module.Minner_init_n = mos(tp=latch_init_type, vth=param.vth, w=param.rst_w, l=param.rst_l)(
        d=module.latch_n, g=init_inner_gate_n, s=latch_init_rail, b=latch_init_rail
    )

    # --- Minner_on: inner on (current steering) devices, driven by the input pair's drains ---
    # The modified double tails' alone. Drains connect to latch_p/latch_n, sources introduce
    # midp/midn nodes.
    if inner_on:
        module.midp = h.Signal()
        module.midn = h.Signal()
        module.Minner_on_p = mos(
            tp=latch_on_type,
            vth=param.vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.latch_p, g=module.input_p_drain, s=module.midp, b=latch_on_rail)
        module.Minner_on_n = mos(
            tp=latch_on_type,
            vth=param.vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.latch_n, g=module.input_n_drain, s=module.midn, b=latch_on_rail)

    # --- Mcross_on: cross-coupled inverter pair, on side ---
    # Drains connect to midp/midn if inner_on devices exist, otherwise latch_p/latch_n.
    # Sources connect to the outer on devices' nodes where they exist, otherwise on_rail.
    cross_on_drain_p = module.midp if inner_on else module.latch_p
    cross_on_drain_n = module.midn if inner_on else module.latch_n

    # The StrongARM: its cross-coupled pair driven directly from the input pair (the on device
    # whose drain is latch_p sits on the inn device's drain: that drain falls later for inp > inn,
    # so latch_p is the node left high)
    if stacked:
        cross_on_src_p = module.input_n_drain
        cross_on_src_n = module.input_p_drain
    # The double tail: one node to the shared tail
    elif shared_tail:
        module.outer = h.Signal()
        cross_on_src_p = module.outer
        cross_on_src_n = module.outer
    # The self-timed double tail: a node to each half's outer devices
    elif self_timed_outer:
        module.outerp = h.Signal()
        module.outern = h.Signal()
        cross_on_src_p = module.outerp
        cross_on_src_n = module.outern
    # The modified double tails: directly to the on rail
    else:
        cross_on_src_p = latch_on_rail
        cross_on_src_n = latch_on_rail

    module.Mcross_on_p = mos(
        tp=latch_on_type,
        vth=param.vth,
        w=param.latch_on_w,
        l=param.latch_on_l,
    )(d=cross_on_drain_p, g=module.latch_n, s=cross_on_src_p, b=latch_on_rail)
    module.Mcross_on_n = mos(
        tp=latch_on_type,
        vth=param.vth,
        w=param.latch_on_w,
        l=param.latch_on_l,
    )(d=cross_on_drain_n, g=module.latch_p, s=cross_on_src_n, b=latch_on_rail)

    # --- Mouter_on: outer on (current steering) devices ---
    # The double tail's shared tail, one clocked device of the pair's combined width feeding both
    # halves; the self-timed double tail's one per half, driven by the input pair's drains.
    # [Schinkel] Sec. III, p. 91: a large current in the latching stage (a wide latch tail), a
    # small one in the input stage
    # Its M12: Mouter_on; its M9: Mtail (Fig. 2(a), p. 90).
    # not in the reference texts: the factor, Mouter_on twice latch_on_w (the two halves' on
    # devices together, at their length), where the source gives no ratio; the input tail is
    # tail_w by tail_l, free of it. Holds for Latch.DOUBLE_TAIL
    if shared_tail:
        module.Mouter_on = mos(
            tp=latch_on_type,
            vth=param.vth,
            w=2 * param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outer, g=latch_clk, s=latch_on_rail, b=latch_on_rail)
    elif self_timed_outer:
        module.Mouter_on_p = mos(
            tp=latch_on_type,
            vth=param.vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outerp, g=module.input_p_drain, s=latch_on_rail, b=latch_on_rail)
        module.Mouter_on_n = mos(
            tp=latch_on_type,
            vth=param.vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outern, g=module.input_n_drain, s=latch_on_rail, b=latch_on_rail)

        # --- Mouter_init: outer init (reset) devices on the outer on devices' nodes, driven by
        # the input pair's drains ---
        module.Mouter_init_p = mos(
            tp=latch_init_type,
            vth=param.vth,
            w=param.rst_w,
            l=param.rst_l,
        )(d=module.outerp, g=module.input_p_drain, s=latch_init_rail, b=latch_init_rail)
        module.Mouter_init_n = mos(
            tp=latch_init_type,
            vth=param.vth,
            w=param.rst_w,
            l=param.rst_l,
        )(d=module.outern, g=module.input_n_drain, s=latch_init_rail, b=latch_init_rail)


# fmt: on


def _build_triple_tail(module, param: Params):
    """Second and third stages of a triple-tail comparator (frida's own: no source has it).

    Stage two is a clocked-tail latch on the opposite rails: a cross-coupled pair of the reset
    polarity under a clocked tail, a cross-coupled init pair of the input polarity, and input
    devices gated by the input pair's drains that hold its nodes midp/midn at the evaluation rail
    until the drains fall. It regenerates to the rails: the node of the drain that falls first
    (midp for inp > inn) ends at the reset rail, the other at the evaluation rail.

    Stage three is a latch stage two starts: its precharge devices and its two tail devices are
    gated by midp/midn, so it stays precharged, drawing nothing, until stage two has decided; then
    the high mid node turns its tail on and releases one latch node (midp releases latch_n, so
    latch_p ends at the reset rail when inp > inn, as in a StrongARM), while the low mid node keeps
    the other precharged. No clocked device of stage three: nothing regenerates before stage two,
    and no current flows once it has decided.
    """

    diff_type = param.input_pair
    reset_type = MosType.PMOS if diff_type == MosType.NMOS else MosType.NMOS
    on_rail = module.vss if diff_type == MosType.NMOS else module.vdd
    init_rail = module.vdd if diff_type == MosType.NMOS else module.vss
    off_clk = module.clkb if diff_type == MosType.NMOS else module.clk
    vth = param.vth

    module.tail2 = h.Signal()
    module.midp = h.Signal()
    module.midn = h.Signal()
    # not in the reference texts: stage two's sizes (frida's own), every device of it latch_on_w by
    # latch_on_l but its tail, Mtail2, twice as wide (the two halves' cross devices together, as
    # the double tail's shared tail: _build_latch). The input devices (Mmid_in_p/n, gated by the
    # input pair's drains) hold midp/midn near the evaluation rail against the cross pair
    # (Mmid_cross_p/n) and the tail while the drains are high; the init cross pair
    # (Mmid_cross_init_p/n) takes the losing node to the evaluation rail, so that stage three's
    # precharge device on it stays fully on. One size for the three pairs makes both a matter of
    # the two device types' strengths alone, whatever the widths: one input device against the
    # stack of a cross device and the tail, and the level at which the stage splits. With an NMOS
    # input pair the input devices are the stronger type; a PMOS pair's hold with less margin
    module.Mtail2 = mos(tp=reset_type, vth=vth, w=2 * param.latch_on_w, l=param.latch_on_l)(
        d=module.tail2, g=off_clk, s=init_rail, b=init_rail
    )
    module.Mmid_cross_p = mos(tp=reset_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midp, g=module.midn, s=module.tail2, b=init_rail
    )
    module.Mmid_cross_n = mos(tp=reset_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midn, g=module.midp, s=module.tail2, b=init_rail
    )
    module.Mmid_cross_init_p = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midp, g=module.midn, s=on_rail, b=on_rail
    )
    module.Mmid_cross_init_n = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midn, g=module.midp, s=on_rail, b=on_rail
    )
    module.Mmid_in_p = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midp, g=module.input_p_drain, s=on_rail, b=on_rail
    )
    module.Mmid_in_n = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midn, g=module.input_n_drain, s=on_rail, b=on_rail
    )

    # not in the reference texts: stage three's sizes (frida's own), every device of it but the
    # init cross pair (Mcross_init_p/n, latch_init_w by latch_init_l as every latch's) latch_on_w
    # by latch_on_l: the cross pair (Mcross_on_p/n), the two tail devices (Mtail3_p on midp,
    # Mtail3_n on midn: one conducts once stage two has decided) and the precharge devices
    # (Minner_init_p on midn, Minner_init_n on midp). While the mid nodes rise together, before
    # they split, both tails conduct a little against both precharge devices: one size for the
    # two, and for stage two, keeps their currents in one ratio whatever the widths, so the latch
    # nodes stay near the reset rail, above the decision inverters' threshold, until stage two
    # has decided. Holds for the strengths of a kit's two device types, not for widths chosen
    # apart
    module.tail3 = h.Signal()
    module.Mtail3_p = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.tail3, g=module.midp, s=on_rail, b=on_rail
    )
    module.Mtail3_n = mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.tail3, g=module.midn, s=on_rail, b=on_rail
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
    module.Minner_init_p = mos(tp=reset_type, vth=param.vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.latch_p, g=module.midn, s=init_rail, b=init_rail
    )
    module.Minner_init_n = mos(tp=reset_type, vth=param.vth, w=param.latch_on_w, l=param.latch_on_l)(
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
    # [Baker] Eq. (11.17), p. 359: a buffer's stages, each A times the one before
    # A = 2: the second buffer (Mbuf2_*) twice the first and every other gate of the stage
    # (srlatch_n_w, srlatch_p_w: the decision inverters, the SR latch, the first buffers). C_load:
    # the output's load, TbParams.output_load_f in the bench. The PMOS-to-NMOS ratio is Params'
    # (its defaults W_P = 2 W_N). Holds for the transistor view alone: the cells' drives are set
    # apart (_build_output_stdcells)
    (n_w, n_nf), (p_w, p_nf) = logic_pair(param.srlatch_n_w, param.srlatch_p_w)
    (n_w2, n_nf2), (p_w2, p_nf2) = logic_pair(2 * param.srlatch_n_w, 2 * param.srlatch_p_w)

    # Convert the dynamic inner nodes into the former direct-buffer outputs.
    # During evaluation exactly one of these differential signals asserts.
    module.decision_p = h.Signal(desc="Dynamic positive decision")
    module.decision_n = h.Signal(desc="Dynamic negative decision")
    module.Mdecision_p_p = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
        d=module.decision_p, g=latch_n, s=module.vdd, b=module.vdd
    )
    module.Mdecision_p_n = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
        d=module.decision_p, g=latch_n, s=module.vss, b=module.vss
    )
    module.Mdecision_n_p = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
        d=module.decision_n, g=latch_p, s=module.vdd, b=module.vdd
    )
    module.Mdecision_n_n = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
        d=module.decision_n, g=latch_p, s=module.vss, b=module.vss
    )

    module.sr_p = h.Signal(desc="Held positive decision")
    module.sr_n = h.Signal(desc="Held negative decision")
    module.sr_p_stack = h.Signal()
    module.sr_n_stack = h.Signal()

    preamp_resets_high = param.input_pair == MosType.NMOS
    # The latch nodes reset with the preamp in a StrongARM and a triple tail's last
    # stage, and to the opposite rail in a double tail.
    # [Razavi-ADC] Sec. 5.8.5, p. 98: the RS latch that holds the decision through the precharge
    # not in the reference texts: its gate by the latch nodes' reset level: where they reset high
    # the decision inverters idle low and cross-coupled NORs take their active-high pulse; where
    # they reset low, NANDs take the active-low one. The side whose pulse comes changes first and
    # the other a gate delay later: the two held outputs do not cross together
    double = param.latch not in (Latch.STRONGARM, Latch.TRIPLE_TAIL)
    inner_resets_high = not preamp_resets_high if double else preamp_resets_high

    if inner_resets_high:
        # decision_p/n are low between comparisons. Cross-coupled NOR gates
        # accept their active-high assertion and retain the resulting state.
        module.Msr_p_p_decision = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p_stack, g=module.decision_n, s=module.vdd, b=module.vdd
        )
        module.Msr_p_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p, g=module.sr_n, s=module.sr_p_stack, b=module.vdd
        )
        module.Msr_p_n_decision = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p, g=module.decision_n, s=module.vss, b=module.vss
        )
        module.Msr_p_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p, g=module.sr_n, s=module.vss, b=module.vss
        )

        module.Msr_n_p_decision = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n_stack, g=module.decision_p, s=module.vdd, b=module.vdd
        )
        module.Msr_n_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n, g=module.sr_p, s=module.sr_n_stack, b=module.vdd
        )
        module.Msr_n_n_decision = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n, g=module.decision_p, s=module.vss, b=module.vss
        )
        module.Msr_n_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n, g=module.sr_p, s=module.vss, b=module.vss
        )
    else:
        # decision_p/n are high between comparisons. Cross-coupled NAND gates
        # accept their active-low assertion and retain the resulting state:
        # latch_p rising pulls decision_n low, which sets sr_p.
        module.Msr_p_p_decision = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p, g=module.decision_n, s=module.vdd, b=module.vdd
        )
        module.Msr_p_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_p, g=module.sr_n, s=module.vdd, b=module.vdd
        )
        module.Msr_p_n_decision = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p, g=module.decision_n, s=module.sr_p_stack, b=module.vss
        )
        module.Msr_p_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_p_stack, g=module.sr_n, s=module.vss, b=module.vss
        )

        module.Msr_n_p_decision = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n, g=module.decision_p, s=module.vdd, b=module.vdd
        )
        module.Msr_n_p_feedback = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
            d=module.sr_n, g=module.sr_p, s=module.vdd, b=module.vdd
        )
        module.Msr_n_n_decision = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n, g=module.decision_p, s=module.sr_n_stack, b=module.vss
        )
        module.Msr_n_n_feedback = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
            d=module.sr_n_stack, g=module.sr_p, s=module.vss, b=module.vss
        )

    # Two inverter stages buffer the static latch without changing polarity.
    module.outp_b = h.Signal()
    module.outn_b = h.Signal()
    module.Mbuf1_outp_p = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
        d=module.outp_b, g=module.sr_p, s=module.vdd, b=module.vdd
    )
    module.Mbuf1_outp_n = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
        d=module.outp_b, g=module.sr_p, s=module.vss, b=module.vss
    )
    module.Mbuf1_outn_p = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=1, nf=p_nf)(
        d=module.outn_b, g=module.sr_n, s=module.vdd, b=module.vdd
    )
    module.Mbuf1_outn_n = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=1, nf=n_nf)(
        d=module.outn_b, g=module.sr_n, s=module.vss, b=module.vss
    )
    module.Mbuf2_outp_p = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w2, l=1, nf=p_nf2)(
        d=module.outp, g=module.outp_b, s=module.vdd, b=module.vdd
    )
    module.Mbuf2_outp_n = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w2, l=1, nf=n_nf2)(
        d=module.outp, g=module.outp_b, s=module.vss, b=module.vss
    )
    module.Mbuf2_outn_p = h.Mos(tp=MosType.PMOS, vth=param.vth, w=p_w2, l=1, nf=p_nf2)(
        d=module.outn, g=module.outn_b, s=module.vdd, b=module.vdd
    )
    module.Mbuf2_outn_n = h.Mos(tp=MosType.NMOS, vth=param.vth, w=n_w2, l=1, nf=n_nf2)(
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
    preamp_resets_high = param.input_pair == MosType.NMOS
    # the latch nodes reset with the preamp but in a double tail; the gate by their reset level,
    # as _build_output_srlatch picks it
    double = param.latch not in (Latch.STRONGARM, Latch.TRIPLE_TAIL)
    inner_resets_high = not preamp_resets_high if double else preamp_resets_high
    # not in the reference texts: the cells' drives, fixed (frida's own): 1 for the decision
    # inverters on the latch nodes (the least load a library cell puts there), 2 for a NOR (its
    # stacked PMOS) and 1 for a NAND, then 4 and 8 for the two buffers, a taper of 2 ([Baker]
    # Eq. (11.17), p. 359). They are not derived from srlatch_n_w and srlatch_p_w: this view and
    # the transistor view are one circuit only where those widths are what the cells draw
    # (params.OutputStage)
    gate, drive = (Nor2, 2) if inner_resets_high else (Nand2, 1)
    module.Xsr_p = gate(LogicCellParams(drive=drive))(A=module.decision_n, B=module.sr_n, Y=module.sr_p, **supplies)
    module.Xsr_n = gate(LogicCellParams(drive=drive))(A=module.decision_p, B=module.sr_p, Y=module.sr_n, **supplies)
    module.Xbuf1_outp = Inverter(LogicCellParams(drive=4))(A=module.sr_p, Y=module.outp_b, **supplies)
    module.Xbuf1_outn = Inverter(LogicCellParams(drive=4))(A=module.sr_n, Y=module.outn_b, **supplies)
    module.Xbuf2_outp = Inverter(LogicCellParams(drive=8))(A=module.outp_b, Y=module.outp, **supplies)
    module.Xbuf2_outn = Inverter(LogicCellParams(drive=8))(A=module.outn_b, Y=module.outn, **supplies)
