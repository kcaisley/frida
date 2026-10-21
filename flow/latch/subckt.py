"""
Latch, flip-flop, divider and SR latch generator for FRIDA.

Supports:
- Static C2MOS latches: a clocked (tristate) inverter forward, an inverter (or a NOR with an
  asynchronous reset) to the output, and a weaker clocked inverter feeding the output back
- Master-slave flip-flops of two such latches, and divide-by-two flip-flops (qb fed back to d)
- True single-phase clock (TSPC) flip-flops and dividers: three dynamic stages on clk alone and
  an output inverter (dmc65 ``DIV2_SeTSPC``)
- Dual interlocked storage cell (DICE) latches: four nodes, each driven up by one neighbour and
  down by the other and written by a clocked inverter of its own, so that an upset of any one
  node does not flip the stored bit (FE-I4 ``SEU_latch``, helena ``latch9_dice``)
- Cross-coupled NAND or NOR SR latches
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


class Style(Enum):
    CLOCKED = auto()  # static C2MOS latch, transparent while clk is high
    TSPC = auto()  # true single-phase clock flip-flop, dynamic: clk alone, no reset
    DICE = auto()  # dual interlocked storage cell latch, transparent while clk is high
    SR_NAND = auto()  # cross-coupled NAND gates: active-low s and r
    SR_NOR = auto()  # cross-coupled NOR gates: active-high s and r


# the styles a clock drives: latches, flip-flops and dividers
CLOCKED_STYLES = (Style.CLOCKED, Style.TSPC, Style.DICE)


@h.paramclass
class LatchParams:
    """Latch parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=4 means 4×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    style = h.Param(dtype=Style, desc="Latch style", default=Style.CLOCKED)
    flop = h.Param(dtype=bool, desc="Master-slave flip-flop on the rising clk edge", default=False)
    divider = h.Param(dtype=bool, desc="Divide by two: the flip-flop's qb drives its d", default=False)
    reset = h.Param(dtype=bool, desc="Asynchronous active-high reset to q low", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    n_w = h.Param(dtype=int, desc="Forward, write and output NMOS width multiplier", default=4)
    p_w = h.Param(dtype=int, desc="Forward, write and output PMOS width multiplier", default=8)
    fb_n_w = h.Param(dtype=int, desc="Feedback (DICE: storage) NMOS width multiplier", default=2)
    fb_p_w = h.Param(dtype=int, desc="Feedback (DICE: storage) PMOS width multiplier", default=4)
    l = h.Param(dtype=int, desc="Length multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_latch_params(param: LatchParams) -> bool:
    """Check if this latch is valid.

    A divider is a flip-flop. An SR latch has no clock, so no flip-flop, divider or reset. A TSPC
    circuit is a flip-flop without reset, a DICE one a latch without reset. Every size is positive.
    """
    if min(param.n_w, param.p_w, param.fb_n_w, param.fb_p_w, param.l) <= 0:
        return False
    if param.divider and not param.flop:
        return False
    if param.style == Style.TSPC:
        return param.flop and not param.reset
    if param.style == Style.DICE:
        return not (param.flop or param.reset)
    return param.style == Style.CLOCKED or not (param.flop or param.divider or param.reset)


@h.bundle
class LatchNets:
    d = h.Input(desc="Data input")
    s, r = h.Input(desc="SR latch set"), h.Input(desc="SR latch reset")
    rst = h.Input(desc="Asynchronous reset, active high")
    clk, clkb = h.Clock(), h.Clock()
    q, qb = h.Output(), h.Output()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Latch(param: LatchParams) -> h.Module:
    """
    Latch generator.

    Generates static C2MOS latches, master-slave and divide-by-two flip-flops, TSPC flip-flops
    and dividers, DICE latches, or cross-coupled NAND and NOR SR latches based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_latch_params(param):
        raise ValueError(f"Invalid latch params: {param}")

    Latch = module_from_ports("Latch", LatchNets.signals)

    if param.style == Style.TSPC:
        _build_tspc(Latch, param, Latch.qb if param.divider else Latch.d)
    elif param.style == Style.DICE:
        _build_dice(Latch, param)
    elif param.style != Style.CLOCKED:
        _build_sr(Latch, param)
    elif not param.flop:
        # one latch, transparent while clk is high: qb is its inner node
        _build_latch(Latch, param, "", Latch.d, Latch.clk, Latch.clkb, Latch.qb, Latch.q)
    else:
        # the master is transparent while clk is low, the slave while it is high: q takes d at
        # the rising edge. qb, the slave's inner node, is q's complement; a divider feeds it to d.
        Latch.m, Latch.mb = h.Signal(desc="Master output"), h.Signal(desc="Master inner node")
        d = Latch.qb if param.divider else Latch.d
        _build_latch(Latch, param, "_m", d, Latch.clkb, Latch.clk, Latch.mb, Latch.m)
        _build_latch(Latch, param, "_s", Latch.m, Latch.clk, Latch.clkb, Latch.qb, Latch.q)

    return Latch


def _build_latch(module, param: LatchParams, name: str, d, on, off, inner, out):
    """One static C2MOS latch, transparent while ``on`` is high (``off`` its complement): a clocked
    inverter from ``d`` to ``inner``, an inverter (a NOR with rst) from ``inner`` to ``out``, and a
    weaker clocked inverter from ``out`` back to ``inner`` while it holds."""

    _build_clocked_inverter(module, param, f"Mfwd{name}", d, inner, on, off, param.n_w, param.p_w)
    _build_clocked_inverter(module, param, f"Mfb{name}", out, inner, off, on, param.fb_n_w, param.fb_p_w)
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    module.add(_mos(**nmos)(d=out, g=inner, s=module.vss, b=module.vss), name=f"Mout{name}_n")
    if not param.reset:
        module.add(_mos(**pmos)(d=out, g=inner, s=module.vdd, b=module.vdd), name=f"Mout{name}_p")
        return
    # NOR with rst: rst pulls out low and blocks the PMOS stack
    stack = module.add(h.Signal(name=f"out{name}_stack"))
    module.add(_mos(**nmos)(d=out, g=module.rst, s=module.vss, b=module.vss), name=f"Mrst{name}_n")
    module.add(_mos(**pmos)(d=stack, g=module.rst, s=module.vdd, b=module.vdd), name=f"Mrst{name}_p")
    module.add(_mos(**pmos)(d=out, g=inner, s=stack, b=module.vdd), name=f"Mout{name}_p")


def _build_clocked_inverter(module, param: LatchParams, name: str, inp, out, on, off, n_w: int, p_w: int):
    """A clocked (tristate) inverter from ``inp`` to ``out``, driving while ``on`` is high: the data
    devices on the rails, the clocked devices at the output (C2MOS)."""

    nmid = module.add(h.Signal(name=f"{name[1:]}_nmid"))
    pmid = module.add(h.Signal(name=f"{name[1:]}_pmid"))
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": p_w, "l": param.l}
    module.add(_mos(**nmos)(d=nmid, g=inp, s=module.vss, b=module.vss), name=f"{name}_n")
    module.add(_mos(**nmos)(d=out, g=on, s=nmid, b=module.vss), name=f"{name}_nclk")
    module.add(_mos(**pmos)(d=pmid, g=inp, s=module.vdd, b=module.vdd), name=f"{name}_p")
    module.add(_mos(**pmos)(d=out, g=off, s=pmid, b=module.vdd), name=f"{name}_pclk")


def _build_tspc(module, param: LatchParams, d):
    """A positive-edge TSPC flip-flop (Yuan and Svensson): a p-latch from ``d`` to ``x`` open while
    clk is low, a precharged n-stage from ``x`` to ``y`` evaluating while clk is high, an n-latch
    from ``y`` to qb open while clk is high, and an inverter from qb to q. ``y`` and, while clk is
    low, qb hold their charge alone: the flip-flop is dynamic."""

    module.x, module.y = h.Signal(desc="First stage: d inverted while clk is low"), h.Signal(desc="Second stage")
    mids = [module.add(h.Signal(name=f"tspc{stage}_mid")) for stage in (1, 2, 3)]
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    vdd, vss, clk = module.vdd, module.vss, module.clk
    module.Mt1_p = _mos(**pmos)(d=mids[0], g=d, s=vdd, b=vdd)
    module.Mt1_pclk = _mos(**pmos)(d=module.x, g=clk, s=mids[0], b=vdd)
    module.Mt1_n = _mos(**nmos)(d=module.x, g=d, s=vss, b=vss)
    module.Mt2_pclk = _mos(**pmos)(d=module.y, g=clk, s=vdd, b=vdd)
    module.Mt2_n = _mos(**nmos)(d=module.y, g=module.x, s=mids[1], b=vss)
    module.Mt2_nclk = _mos(**nmos)(d=mids[1], g=clk, s=vss, b=vss)
    module.Mt3_p = _mos(**pmos)(d=module.qb, g=module.y, s=vdd, b=vdd)
    module.Mt3_nclk = _mos(**nmos)(d=module.qb, g=clk, s=mids[2], b=vss)
    module.Mt3_n = _mos(**nmos)(d=mids[2], g=module.y, s=vss, b=vss)
    module.Mout_n = _mos(**nmos)(d=module.q, g=module.qb, s=vss, b=vss)
    module.Mout_p = _mos(**pmos)(d=module.q, g=module.qb, s=vdd, b=vdd)


def _build_dice(module, param: LatchParams):
    """A DICE latch (Calin, Nicolaidis and Velazco), transparent while clk is high: storage nodes
    x1 to x4, each pulled up by a PMOS on the node before it and down by an NMOS on the node after
    it, so x1 and x3 hold one value and x2 and x4 the other. Each node is written by a clocked
    inverter of its own, from d (x1, x3) or its complement (x2, x4): a struck node driven past a
    rail can open only its own writer's clocked device, whose inner node leads nowhere else, where
    write gates sharing d or its complement would carry the strike to the node's partner. q and qb
    are x1 and x2 inverted."""

    nodes = [module.add(h.Signal(name=f"x{index}", desc="DICE storage node")) for index in (1, 2, 3, 4)]
    module.db = h.Signal(desc="d inverted")
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    store_n = {"tp": MosType.NMOS, "vth": param.vth, "w": param.fb_n_w, "l": param.l}
    store_p = {"tp": MosType.PMOS, "vth": param.vth, "w": param.fb_p_w, "l": param.l}
    vdd, vss = module.vdd, module.vss
    for index, node in enumerate(nodes, start=1):
        before, after = nodes[(index - 2) % 4], nodes[index % 4]
        module.add(_mos(**store_p)(d=node, g=before, s=vdd, b=vdd), name=f"Mx{index}_p")
        module.add(_mos(**store_n)(d=node, g=after, s=vss, b=vss), name=f"Mx{index}_n")
        source = module.db if index % 2 == 0 else module.d
        _build_clocked_inverter(
            module, param, f"Mw{index}", source, node, module.clk, module.clkb, param.n_w, param.p_w
        )
    module.Mdb_n = _mos(**nmos)(d=module.db, g=module.d, s=vss, b=vss)
    module.Mdb_p = _mos(**pmos)(d=module.db, g=module.d, s=vdd, b=vdd)
    for out, node in ((module.q, nodes[0]), (module.qb, nodes[1])):
        module.add(_mos(**nmos)(d=out, g=node, s=vss, b=vss), name=f"Mout_{out.name}_n")
        module.add(_mos(**pmos)(d=out, g=node, s=vdd, b=vdd), name=f"Mout_{out.name}_p")


def _build_sr(module, param: LatchParams):
    """Cross-coupled NAND (active-low s, r) or NOR (active-high s, r) gates: s sets q, r resets it."""

    nand = param.style == Style.SR_NAND
    nmos = {"tp": MosType.NMOS, "vth": param.vth, "w": param.n_w, "l": param.l}
    pmos = {"tp": MosType.PMOS, "vth": param.vth, "w": param.p_w, "l": param.l}
    # an active-low s on q's NAND pulls q high; an active-high s pulls its NOR output low, so in a
    # NOR latch s drives qb's gate and r q's
    first, second = (module.s, module.r) if nand else (module.r, module.s)
    for out, inp, other in ((module.q, first, module.qb), (module.qb, second, module.q)):
        side = out.name
        stack = module.add(h.Signal(name=f"{side}_stack"))
        if nand:  # the NMOS in series, the PMOS in parallel
            module.add(_mos(**nmos)(d=out, g=inp, s=stack, b=module.vss), name=f"M{side}_n_in")
            module.add(_mos(**nmos)(d=stack, g=other, s=module.vss, b=module.vss), name=f"M{side}_n_fb")
            module.add(_mos(**pmos)(d=out, g=inp, s=module.vdd, b=module.vdd), name=f"M{side}_p_in")
            module.add(_mos(**pmos)(d=out, g=other, s=module.vdd, b=module.vdd), name=f"M{side}_p_fb")
        else:  # the PMOS in series, the NMOS in parallel
            module.add(_mos(**pmos)(d=out, g=inp, s=stack, b=module.vdd), name=f"M{side}_p_in")
            module.add(_mos(**pmos)(d=stack, g=other, s=module.vdd, b=module.vdd), name=f"M{side}_p_fb")
            module.add(_mos(**nmos)(d=out, g=inp, s=module.vss, b=module.vss), name=f"M{side}_n_in")
            module.add(_mos(**nmos)(d=out, g=other, s=module.vss, b=module.vss), name=f"M{side}_n_fb")


def write_netlist(params: LatchParams, path: Path, pdk) -> Path:
    """The latch after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Latch, nets=LatchNets)


# ==== Named latches ====

CASES = {
    # static C2MOS latch (bag3_digital latch, BAG clk_retime_latch)
    "latch": LatchParams(),
    # latch with asynchronous reset (bag3_digital rst_latch)
    "latch_rst": LatchParams(reset=True),
    # master-slave flip-flop with reset (bag3_digital rst_flop, ciccreator DFRNQNX1)
    "flop_rst": LatchParams(flop=True, reset=True),
    # divide-by-two flip-flop with reset (bag3_digital div2, BAG vco_cnter_div)
    "div2": LatchParams(flop=True, divider=True, reset=True),
    # TSPC flip-flop (Yuan and Svensson)
    "flop_tspc": LatchParams(style=Style.TSPC, flop=True),
    # TSPC divide-by-two (dmc65 DIV2_SeTSPC)
    "div2_tspc": LatchParams(style=Style.TSPC, flop=True, divider=True),
    # DICE latch, upset-immune to one node (FE-I4 SEU_latch, helena latch9_dice)
    "latch_dice": LatchParams(style=Style.DICE),
    # NAND SR latch (BAG sr_nand)
    "sr_nand": LatchParams(style=Style.SR_NAND),
    # NOR SR latch (bag3_digital sr_latch_symmetric_core, the comparator's held output)
    "sr_nor": LatchParams(style=Style.SR_NOR),
}
