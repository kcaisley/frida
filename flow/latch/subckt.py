"""The latch's circuit: its nets (``Nets``) and its generator (``netlist``), the module ``Latch``
of the design ``Params``.

- Static C2MOS latches: a clocked (tristate) inverter forward, an inverter (or a NOR with an
  asynchronous reset) to the output, and a weaker clocked inverter feeding the output back
- Master-slave flip-flops of two such latches, and divide-by-two flip-flops (qb fed back to d)
- True single-phase clock (TSPC) flip-flops and dividers: three dynamic stages on clk alone and
  an output inverter
- Dual interlocked storage cell (DICE) latches: four nodes, each driven up by one neighbour and
  down by the other and written by a clocked inverter of its own, so that an upset of any one
  node does not flip the stored bit
- Cross-coupled NAND or NOR SR latches

The generator uses h.Mos primitives; the PDK's compile makes them its devices.
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.ports import module_from_ports
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import place, row, rows

from .params import Params, Style


@h.bundle
class Nets:
    d = h.Input(desc="Data input")
    s, r = h.Input(desc="SR latch set"), h.Input(desc="SR latch reset")
    rst = h.Input(desc="Asynchronous reset, active high")
    clk, clkb = h.Clock(), h.Clock()
    q, qb = h.Output(), h.Output()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The latch: a static C2MOS latch, a master-slave or divide-by-two flip-flop of two, a TSPC
    flip-flop or divider, a DICE latch, or a cross-coupled NAND or NOR SR latch, as ``param.style``,
    ``param.flop`` and ``param.divider`` say."""
    Latch = module_from_ports("Latch", Nets.signals)

    if param.style is Style.TSPC:
        _build_tspc(Latch, param, Latch.qb if param.divider else Latch.d)
    elif param.style is Style.DICE:
        _build_dice(Latch, param)
    elif param.style is not Style.CLOCKED:
        _build_sr(Latch, param)
    elif not param.flop:
        # one latch, transparent while clk is high: qb is its inner node
        _build_latch(Latch, param, "", Latch.d, Latch.clk, Latch.clkb, Latch.qb, Latch.q)
    else:
        # [Razavi-PLL] Fig. 15.12, p. 460: master-slave flipflop of two C2MOS latches
        # [Razavi-PLL] Fig. 15.3, p. 455: divide-by-2 circuit of two latches in a negative-feedback loop
        # the master is transparent while clk is low, the slave while it is high: q takes d at
        # the rising edge. qb, the slave's inner node, is q's complement; a divider feeds it to d.
        Latch.m, Latch.mb = h.Signal(desc="Master output"), h.Signal(desc="Master inner node")
        d = Latch.qb if param.divider else Latch.d
        _build_latch(Latch, param, "_m", d, Latch.clkb, Latch.clk, Latch.mb, Latch.m)
        _build_latch(Latch, param, "_s", Latch.m, Latch.clk, Latch.clkb, Latch.qb, Latch.q)

    _place(Latch, param)
    return Latch


def _place(module: h.Module, param: Params) -> None:
    """The latch's rows for ALIGN, top first, each device by its name (one the design lacks left
    out): a PMOS row above an NMOS row, each clocked inverter's stack side by side, the feedback
    beside the forward stage, the output last; a flip-flop's master above its slave, the slave's
    NMOS row first; a DICE latch's writers above its interlocked storage devices; an SR latch's q
    gate left of its qb gate."""
    if param.style is Style.TSPC:
        order = [
            ["Mt1_p", "Mt1_pclk", "Mt2_pclk", "Mt3_p", "Mout_p"],
            ["Mt1_n", "Mt2_n", "Mt2_nclk", "Mt3_nclk", "Mt3_n", "Mout_n"],
        ]
    elif param.style is Style.DICE:
        writers = [f"Mw{index}_{{}}{clocked}" for index in (1, 2, 3, 4) for clocked in ("", "clk")]
        order = [
            ["Mdb_p", *(name.format("p") for name in writers), "Mout_q_p", "Mout_qb_p"],
            ["Mdb_n", *(name.format("n") for name in writers), "Mout_q_n", "Mout_qb_n"],
            [f"Mx{index}_n" for index in (1, 2, 3, 4)],
            [f"Mx{index}_p" for index in (1, 2, 3, 4)],
        ]
    elif param.style is not Style.CLOCKED:
        order = [
            ["Mq_p_in", "Mq_p_fb", "Mqb_p_fb", "Mqb_p_in"],
            ["Mq_n_in", "Mq_n_fb", "Mqb_n_fb", "Mqb_n_in"],
        ]
    else:
        order = []
        for name in ("_m", "_s") if param.flop else ("",):
            pmos = [f"Mfwd{name}_p", f"Mfwd{name}_pclk", f"Mfb{name}_pclk", f"Mfb{name}_p"]
            pmos += [f"Mrst{name}_p", f"Mout{name}_p"]
            nmos = [f"Mfwd{name}_n", f"Mfwd{name}_nclk", f"Mfb{name}_nclk", f"Mfb{name}_n"]
            nmos += [f"Mout{name}_n", f"Mrst{name}_n"]
            order += [nmos, pmos] if name == "_s" else [pmos, nmos]
    place(module, rows(*(row(*(module.instances.get(name) for name in names)) for names in order)), symmetric=False)


def _build_latch(module, param: Params, name: str, d, on, off, inner, out):
    """One static C2MOS latch, transparent while ``on`` is high (``off`` its complement): a clocked
    inverter from ``d`` to ``inner``, an inverter (a NOR with rst) from ``inner`` to ``out``, and a
    weaker clocked inverter from ``out`` back to ``inner`` while it holds."""

    # [Razavi-PLL] Fig. 15.4(a), p. 455: static latch with single-ended data path (its clocked
    # paths transmission gates there, clocked inverters here)
    _build_clocked_inverter(module, param, f"Mfwd{name}", d, inner, on, off, param.n_w, param.p_w)
    _build_clocked_inverter(module, param, f"Mfb{name}", out, inner, off, on, param.fb_n_w, param.fb_p_w)
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    module.add(mos(**nmos)(d=out, g=inner, s=module.vss, b=module.vss), name=f"Mout{name}_n")
    if not param.reset:
        module.add(mos(**pmos)(d=out, g=inner, s=module.vdd, b=module.vdd), name=f"Mout{name}_p")
        return
    # NOR with rst: rst pulls out low and blocks the PMOS stack
    stack = module.add(h.Signal(name=f"out{name}_stack"))
    module.add(mos(**nmos)(d=out, g=module.rst, s=module.vss, b=module.vss), name=f"Mrst{name}_n")
    module.add(mos(**pmos)(d=stack, g=module.rst, s=module.vdd, b=module.vdd), name=f"Mrst{name}_p")
    module.add(mos(**pmos)(d=out, g=inner, s=stack, b=module.vdd), name=f"Mout{name}_p")


def _build_clocked_inverter(module, param: Params, name: str, inp, out, on, off, n_w: int, p_w: int):
    """A clocked (tristate) inverter from ``inp`` to ``out``, driving while ``on`` is high: the data
    devices on the rails, the clocked devices at the output (C2MOS)."""

    # [Razavi-PLL] Fig. 15.10, p. 459: C2MOS latch
    nmid = module.add(h.Signal(name=f"{name[1:]}_nmid"))
    pmid = module.add(h.Signal(name=f"{name[1:]}_pmid"))
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": p_w, "l": param.l}
    module.add(mos(**nmos)(d=nmid, g=inp, s=module.vss, b=module.vss), name=f"{name}_n")
    module.add(mos(**nmos)(d=out, g=on, s=nmid, b=module.vss), name=f"{name}_nclk")
    module.add(mos(**pmos)(d=pmid, g=inp, s=module.vdd, b=module.vdd), name=f"{name}_p")
    module.add(mos(**pmos)(d=out, g=off, s=pmid, b=module.vdd), name=f"{name}_pclk")


def _build_tspc(module, param: Params, d):
    """A positive-edge TSPC flip-flop: a p-latch from ``d`` to ``x`` open while clk is low, a
    precharged n-stage from ``x`` to ``y`` evaluating while clk is high, an n-latch from ``y`` to qb
    open while clk is high, and an inverter from qb to q. ``y`` and, while clk is low, qb hold their
    charge alone: the flip-flop is dynamic."""

    # [Razavi-PLL] Fig. 15.13(d), p. 461: TSPC flipflop (here with an output inverter after it)
    module.x, module.y = h.Signal(desc="First stage: d inverted while clk is low"), h.Signal(desc="Second stage")
    mids = [module.add(h.Signal(name=f"tspc{stage}_mid")) for stage in (1, 2, 3)]
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    vdd, vss, clk = module.vdd, module.vss, module.clk
    module.Mt1_p = mos(**pmos)(d=mids[0], g=d, s=vdd, b=vdd)
    module.Mt1_pclk = mos(**pmos)(d=module.x, g=clk, s=mids[0], b=vdd)
    module.Mt1_n = mos(**nmos)(d=module.x, g=d, s=vss, b=vss)
    module.Mt2_pclk = mos(**pmos)(d=module.y, g=clk, s=vdd, b=vdd)
    module.Mt2_n = mos(**nmos)(d=module.y, g=module.x, s=mids[1], b=vss)
    module.Mt2_nclk = mos(**nmos)(d=mids[1], g=clk, s=vss, b=vss)
    module.Mt3_p = mos(**pmos)(d=module.qb, g=module.y, s=vdd, b=vdd)
    module.Mt3_nclk = mos(**nmos)(d=module.qb, g=clk, s=mids[2], b=vss)
    module.Mt3_n = mos(**nmos)(d=mids[2], g=module.y, s=vss, b=vss)
    module.Mout_n = mos(**nmos)(d=module.q, g=module.qb, s=vss, b=vss)
    module.Mout_p = mos(**pmos)(d=module.q, g=module.qb, s=vdd, b=vdd)


def _build_dice(module, param: Params):
    """A DICE latch, transparent while clk is high: storage nodes x1 to x4, each pulled up by a
    PMOS on the node before it and down by an NMOS on the node after it, so x1 and x3 hold one
    value and x2 and x4 the other. Each node is written by a clocked
    inverter of its own, from d (x1, x3) or its complement (x2, x4): a struck node driven past a
    rail can open only its own writer's clocked device, whose inner node leads nowhere else, where
    write gates sharing d or its complement would carry the strike to the node's partner. q and qb
    are x1 and x2 inverted."""

    # not in the reference texts: the dual interlocked storage cell, four nodes each held by its two
    # neighbours so that one upset node is restored (Calin, Nicolaidis and Velazco)
    nodes = [module.add(h.Signal(name=f"x{index}", desc="DICE storage node")) for index in (1, 2, 3, 4)]
    module.db = h.Signal(desc="d inverted")
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    store_n = {"tp": MosType.NMOS, "vth": param.vth, "w": param.fb_n_w, "l": param.l}
    store_p = {"tp": MosType.PMOS, "vth": param.vth, "w": param.fb_p_w, "l": param.l}
    vdd, vss = module.vdd, module.vss
    for index, node in enumerate(nodes, start=1):
        before, after = nodes[(index - 2) % 4], nodes[index % 4]
        module.add(mos(**store_p)(d=node, g=before, s=vdd, b=vdd), name=f"Mx{index}_p")
        module.add(mos(**store_n)(d=node, g=after, s=vss, b=vss), name=f"Mx{index}_n")
        source = module.db if index % 2 == 0 else module.d
        _build_clocked_inverter(
            module, param, f"Mw{index}", source, node, module.clk, module.clkb, param.n_w, param.p_w
        )
    module.Mdb_n = mos(**nmos)(d=module.db, g=module.d, s=vss, b=vss)
    module.Mdb_p = mos(**pmos)(d=module.db, g=module.d, s=vdd, b=vdd)
    for out, node in ((module.q, nodes[0]), (module.qb, nodes[1])):
        module.add(mos(**nmos)(d=out, g=node, s=vss, b=vss), name=f"Mout_{out.name}_n")
        module.add(mos(**pmos)(d=out, g=node, s=vdd, b=vdd), name=f"Mout_{out.name}_p")


def _build_sr(module, param: Params):
    """Cross-coupled NAND (active-low s, r) or NOR (active-high s, r) gates: s sets q, r resets it."""

    # [Baker] Fig. 13.13, p. 395: set-reset latch made using NAND gates
    # [Baker] Fig. 13.14, p. 396: set-reset latch made using NOR gates
    nand = param.style is Style.SR_NAND
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    # an active-low s on q's NAND pulls q high; an active-high s pulls its NOR output low, so in a
    # NOR latch s drives qb's gate and r q's
    first, second = (module.s, module.r) if nand else (module.r, module.s)
    for out, inp, other in ((module.q, first, module.qb), (module.qb, second, module.q)):
        side = out.name
        stack = module.add(h.Signal(name=f"{side}_stack"))
        if nand:  # the NMOS in series, the PMOS in parallel
            module.add(mos(**nmos)(d=out, g=inp, s=stack, b=module.vss), name=f"M{side}_n_in")
            module.add(mos(**nmos)(d=stack, g=other, s=module.vss, b=module.vss), name=f"M{side}_n_fb")
            module.add(mos(**pmos)(d=out, g=inp, s=module.vdd, b=module.vdd), name=f"M{side}_p_in")
            module.add(mos(**pmos)(d=out, g=other, s=module.vdd, b=module.vdd), name=f"M{side}_p_fb")
        else:  # the PMOS in series, the NMOS in parallel
            module.add(mos(**pmos)(d=out, g=inp, s=stack, b=module.vdd), name=f"M{side}_p_in")
            module.add(mos(**pmos)(d=stack, g=other, s=module.vdd, b=module.vdd), name=f"M{side}_p_fb")
            module.add(mos(**nmos)(d=out, g=inp, s=module.vss, b=module.vss), name=f"M{side}_n_in")
            module.add(mos(**nmos)(d=out, g=other, s=module.vss, b=module.vss), name=f"M{side}_n_fb")
