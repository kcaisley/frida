"""
Comparator generator for FRIDA.

Supports multiple topologies including:
- NMOS/PMOS input differential pairs
- Standard/dynamic biasing
- Single (StrongARM), double- and triple-tail latches
- Various power-gating and reset configurations
- Static transistor-level output decision storage
"""

from enum import Enum, auto
from importlib import import_module
from math import ceil
from pathlib import Path

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import C, MosType, MosVth
from pydantic import StrictInt

from flow.circuit.ports import module_from_ports


class Stages(Enum):
    SINGLE = auto()
    DOUBLE = auto()
    TRIPLE = auto()


class Bias(Enum):
    DYNAMIC = auto()
    SWITCHED = auto()


class State(Enum):
    CLOCK = auto()
    SIGNAL = auto()
    OMIT = auto()


class OutputStage(Enum):
    TRANSISTORS = auto()  # decision inverters, SR latch and buffers drawn transistor by transistor
    STDCELLS = auto()  # the same stage as generic logic cells, mapped to a library by the PDK


@h.paramclass
class CompParams:
    """Comparator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=10 means 10×Wmin, e.g., 1.2µm for a 65nm node)
    - l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for a 65nm node)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    comp_stages = h.Param(dtype=Stages, desc="Comparator stages", default=Stages.SINGLE)

    preamp_diff_xtors = h.Param(
        dtype=MosType,
        desc="Input diff pair type (NMOS or PMOS)",
        default=MosType.NMOS,
    )
    preamp_bias = h.Param(dtype=Bias, desc="Biasing type", default=Bias.SWITCHED)

    # Latch transistor pairs — each can be clocked, signaled, or omitted
    latch_outer_on_xtors = h.Param(dtype=State, desc="Outer on devices", default=State.OMIT)
    latch_inner_on_xtors = h.Param(dtype=State, desc="Inner on  devices", default=State.OMIT)
    latch_outer_init_xtors = h.Param(dtype=State, desc="Outer init devices", default=State.OMIT)
    latch_inner_init_xtors = h.Param(dtype=State, desc="Inner init devices", default=State.CLOCK)
    output_stage = h.Param(dtype=OutputStage, desc="Output stage implementation", default=OutputStage.TRANSISTORS)
    latch_tail_shared = h.Param(
        dtype=bool, desc="One clocked outer tail shared by both latch halves (double tail)", default=False
    )

    # Device sizing (multipliers of Wmin/Lmin)
    diffpair_w = h.Param(dtype=int, desc="Diff pair width multiplier", default=32)
    diffpair_l = h.Param(dtype=int, desc="Diff pair length multiplier", default=4)
    diffpair_vth = h.Param(dtype=MosVth, desc="Diff pair Vth", default=MosVth.LOW)

    tail_w = h.Param(dtype=int, desc="Tail width multiplier", default=4)
    tail_l = h.Param(dtype=int, desc="Tail length multiplier", default=16)
    tail_vth = h.Param(dtype=MosVth, desc="Tail Vth", default=MosVth.LOW)

    rst_w = h.Param(dtype=int, desc="Reset device width multiplier", default=8)
    rst_l = h.Param(dtype=int, desc="Reset device length multiplier", default=1)
    rst_vth = h.Param(dtype=MosVth, desc="Reset Vth", default=MosVth.LOW)

    latch_on_w = h.Param(dtype=int, desc="Latch evaluation-side width multiplier", default=4)
    latch_on_l = h.Param(dtype=int, desc="Latch evaluation-side length multiplier", default=1)
    latch_init_w = h.Param(dtype=int, desc="Latch precharge-side width multiplier", default=4)
    latch_init_l = h.Param(dtype=int, desc="Latch precharge-side length multiplier", default=1)
    latch_vth = h.Param(dtype=MosVth, desc="Latch Vth", default=MosVth.LOW)

    srlatch_n_w = h.Param(
        dtype=int,
        desc="Output SR-latch NMOS width multiplier",
        default=4,
    )
    srlatch_p_w = h.Param(
        dtype=int,
        desc="Output SR-latch PMOS width multiplier",
        default=8,
    )


def is_valid_comp_params(param: CompParams) -> bool:
    """Check if this topology combination is valid.

    Inner init devices must always exist (CLOCK or SIGNAL, never OMIT).

    Single stage: Both kinds of on devices plus outer init devices must be OMIT.

    Double stage: at least one on device pair must exist, and at least
    one of the four device pairs must be signaled (not just clocked). A shared
    tail is one clocked outer on device, so it excludes outer init devices.

    Triple stage (triple tail): its second and third stages are fixed, so the
    latch device options keep their defaults.
    """
    if param.srlatch_n_w <= 0 or param.srlatch_p_w <= 0:
        return False

    if param.latch_inner_init_xtors == State.OMIT:
        return False

    if param.latch_tail_shared and (
        param.comp_stages != Stages.DOUBLE
        or param.latch_outer_on_xtors != State.CLOCK
        or param.latch_outer_init_xtors != State.OMIT
    ):
        return False

    if param.comp_stages == Stages.TRIPLE:
        return (
            param.latch_inner_init_xtors == State.CLOCK
            and param.latch_outer_on_xtors == State.OMIT
            and param.latch_inner_on_xtors == State.OMIT
            and param.latch_outer_init_xtors == State.OMIT
        )

    if param.comp_stages == Stages.SINGLE:
        return (
            param.latch_outer_on_xtors == State.OMIT
            and param.latch_inner_on_xtors == State.OMIT
            and param.latch_outer_init_xtors == State.OMIT
        )
    # outer_init requires outer_on (needs outerp/outern nodes)
    if param.latch_outer_init_xtors != State.OMIT and param.latch_outer_on_xtors == State.OMIT:
        return False

    if param.comp_stages == Stages.DOUBLE:
        has_on = param.latch_outer_on_xtors != State.OMIT or param.latch_inner_on_xtors != State.OMIT
        has_signal = State.SIGNAL in (
            param.latch_outer_on_xtors,
            param.latch_inner_on_xtors,
            param.latch_outer_init_xtors,
            param.latch_inner_init_xtors,
        )
        return has_on and has_signal
    return False


# ==== Device fingers and generic logic cells ====


def _fingers(units: int, kind: str, nf: int | None = None) -> tuple[int, int | None]:
    """Total width and finger count for a device of ``units`` unit widths.

    The active PDK (``hdl21.pdk.default()``) may give ``MOS_FINGER_UNITS``, the widest finger
    its row cells fit per kind ("analog", "logic_n", "logic_p"), in its own unit widths. Then
    the device takes the fewest fingers that fit unless ``nf`` is given (analog devices: an
    even count, so both ends of the diffusion are one terminal, raised by up to three steps
    where that rounds closer), and every finger is the nearest whole number of units. Without those limits the device stays one finger at full size.
    ``MOS_FINGER_MIN_UNITS`` (optional) is the narrowest analog finger the PDK can contact: an even
    count that would go below it gives way to fewer fingers, and a narrower device is widened to it.
    """

    pdk = h.pdk.default()
    limits = getattr(pdk, "MOS_FINGER_UNITS", None)
    if not limits:
        return units, nf
    if kind == "analog":  # an analog device narrower than one contacted finger takes that finger
        units = max(units, getattr(pdk, "MOS_FINGER_MIN_UNITS", 1))
    rounded = lambda count: max(1, int(units / count + 0.5)) * count
    if nf is None:
        nf = ceil(units / limits[kind])
        if kind == "analog":
            # the fewest even finger counts that fit, the one closest to the requested width
            low = getattr(pdk, "MOS_FINGER_MIN_UNITS", 1)
            nf += nf % 2
            counts = [c for c in range(nf, nf + 8, 2) if rounded(c) // c >= low] or [max(1, units // low)]
            nf = min(counts, key=lambda count: (abs(rounded(count) - units), count))
    return rounded(nf), nf


# The PDK whose unit sizes analog devices keep physically in another PDK (write_netlist's
# ``constant_from``); None keeps them relative, in the active PDK's own units.
_CONSTANT_FROM = None


def _core_unit(pdk) -> tuple[float, float]:
    """A PDK's unit width and minimum length (m): its core devices', the shortest default size."""

    return min(((float(w), float(l)) for w, l in pdk.default_xtor_size.values()), key=lambda size: size[1])


def _mos(*, tp, vth, w, l):
    """An analog MOS, fingered to the active PDK's row cells.

    With ``_CONSTANT_FROM`` set, ``w`` and ``l`` are that PDK's units made physical: the width
    to the nearest whole unit of the active PDK, the length kept as drawn, except at one or two
    minimum lengths, which stay that multiple of the active PDK's minimum.
    """

    if _CONSTANT_FROM is not None:
        (w_ref, l_ref), (w_unit, _) = _core_unit(_CONSTANT_FROM), _core_unit(h.pdk.default())
        w = max(1, round(w * w_ref / w_unit))
        if l > 2:
            l = h.Prefixed.new(round(l * l_ref * 1e9), h.Prefix.NANO)
    w, nf = _fingers(w, "analog")
    return h.Mos(tp=tp, vth=vth, w=w, l=l, nf=nf)


def _logic_pair(n_units: int, p_units: int) -> tuple[tuple[int, int | None], tuple[int, int | None]]:
    """NMOS and PMOS sharing a gate in a logic cell: one finger count that fits both."""

    limits = getattr(h.pdk.default(), "MOS_FINGER_UNITS", None)
    nf = max(ceil(n_units / limits["logic_n"]), ceil(p_units / limits["logic_p"])) if limits else None
    return _fingers(n_units, "logic_n", nf), _fingers(p_units, "logic_p", nf)


@h.paramclass
class LogicCellParams:
    drive = h.Param(dtype=StrictInt, desc="Standard-cell drive strength", default=1)


@h.bundle
class InverterPorts:
    A = h.Input()
    Y = h.Output()
    VDD = h.Power(direction=h.PortDir.INOUT)
    VSS = h.Ground(direction=h.PortDir.INOUT)


@h.bundle
class Gate2Ports:
    A, B = h.Input(), h.Input()
    Y = h.Output()
    VDD = h.Power(direction=h.PortDir.INOUT)
    VSS = h.Ground(direction=h.PortDir.INOUT)


# PDK compile passes replace these with library cells (pdk/<tech>/stdcells.py).
Inverter, Nor2, Nand2 = (
    h.ExternalModule(
        domain="generic",
        name=name,
        paramtype=LogicCellParams,
        port_list=list(ports.signals.values()),
        desc=f"{name} standard cell; requires PDK compile substitution",
    )
    for name, ports in (("inverter", InverterPorts), ("nor2", Gate2Ports), ("nand2", Gate2Ports))
)


@h.bundle
class CompNets:
    inp, inn = h.Input(), h.Input()
    outp, outn = h.Output(), h.Output()
    clk, clkb = h.Clock(), h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)
    latch_p, latch_n = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))
    input_p_drain, input_n_drain = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))


@h.generator
def Comp(param: CompParams) -> h.Module:
    """
    Comparator generator.

    Generates StrongARM, double-tail or triple-tail comparators with held differential
    decisions based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_comp_params(param):
        raise ValueError(f"Invalid comparator params: {param}")

    Comp = module_from_ports("Comp", CompNets.signals)
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


def _build_preamp(module, param: CompParams):
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

    # Differential pair. A triple tail cascodes it with devices gated by the reset
    # rail (always on), isolating the input pair from the precharged outputs.
    if param.comp_stages == Stages.TRIPLE:
        module.cas_p = h.Signal()
        module.cas_n = h.Signal()
        diff_drain_p, diff_drain_n = module.cas_p, module.cas_n
        module.Mcas_p = _mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=1)(
            d=module.input_p_drain, g=init_rail, s=module.cas_p, b=on_rail
        )
        module.Mcas_n = _mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=1)(
            d=module.input_n_drain, g=init_rail, s=module.cas_n, b=on_rail
        )
    else:
        diff_drain_p, diff_drain_n = module.input_p_drain, module.input_n_drain
    module.Mdiff_p = _mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=param.diffpair_l)(
        d=diff_drain_p, g=module.inp, s=module.tail, b=on_rail
    )
    module.Mdiff_n = _mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=param.diffpair_l)(
        d=diff_drain_n, g=module.inn, s=module.tail, b=on_rail
    )

    # Tail current source
    if param.preamp_bias == Bias.SWITCHED:
        module.Mtail = _mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(
            d=module.tail, g=on_clk, s=on_rail, b=on_rail
        )
        module.Mtail_reset = _mos(tp=reset_type, vth=param.tail_vth, w=param.tail_w, l=1)(
            d=module.tail, g=on_clk, s=init_rail, b=init_rail
        )
    elif param.preamp_bias == Bias.DYNAMIC:
        # Source of tail device connects to a cap node that stores charge
        # during init (via mbias) and sources current during comparison
        module.cap_node = h.Signal()
        module.Mtail = _mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(
            d=module.tail, g=on_clk, s=module.cap_node, b=on_rail
        )
        module.Mbias = _mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(
            d=module.cap_node, g=off_clk, s=on_rail, b=on_rail
        )
        module.Cbias = C(c=100 * f)(p=module.cap_node, n=on_rail)

    # Reset/precharge devices (minimum length = 1)
    # Precharge preamp outputs during reset phase.
    # For NMOS input: PMOS reset gate=clk → ON when clk=0, OFF when clk=1
    # For PMOS input: NMOS reset gate=clkb → ON when clkb=1, OFF when clkb=0
    module.Mrst_p = _mos(tp=reset_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.input_p_drain, g=on_clk, s=init_rail, b=init_rail
    )
    module.Mrst_n = _mos(tp=reset_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.input_n_drain, g=on_clk, s=init_rail, b=init_rail
    )


# fmt: on


def _build_latch(module, param: CompParams):
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

    module.Mcross_init_p = _mos(
        tp=latch_init_type,
        vth=param.latch_vth,
        w=param.latch_init_w,
        l=param.latch_init_l,
    )(d=module.latch_p, g=module.latch_n, s=latch_init_rail, b=latch_init_rail)
    module.Mcross_init_n = _mos(
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

    module.Minner_init_p = _mos(tp=latch_init_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.latch_p, g=init_inner_gate_p, s=latch_init_rail, b=latch_init_rail
    )
    module.Minner_init_n = _mos(tp=latch_init_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
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

        module.Minner_on_p = _mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.latch_p, g=inner_on_gate_p, s=module.midp, b=latch_on_rail)
        module.Minner_on_n = _mos(
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

    module.Mcross_on_p = _mos(
        tp=latch_on_type,
        vth=param.latch_vth,
        w=param.latch_on_w,
        l=param.latch_on_l,
    )(d=cross_on_drain_p, g=module.latch_n, s=cross_on_src_p, b=latch_on_rail)
    module.Mcross_on_n = _mos(
        tp=latch_on_type,
        vth=param.latch_vth,
        w=param.latch_on_w,
        l=param.latch_on_l,
    )(d=cross_on_drain_n, g=module.latch_p, s=cross_on_src_n, b=latch_on_rail)

    # --- Mouter_on: outer on (currently steering) devices ---
    # Only available in double stage mode. A shared tail is one device of the
    # pair's combined width feeding both halves.
    if param.latch_tail_shared:
        module.Mouter_on = _mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=2 * param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outer, g=latch_clk, s=latch_on_rail, b=latch_on_rail)
    elif param.latch_outer_on_xtors != State.OMIT:
        if param.latch_outer_on_xtors == State.SIGNAL:
            outer_on_gate_p = module.input_p_drain
            outer_on_gate_n = module.input_n_drain
        elif param.latch_outer_on_xtors == State.CLOCK:
            outer_on_gate_p = latch_clk
            outer_on_gate_n = latch_clk

        module.Mouter_on_p = _mos(
            tp=latch_on_type,
            vth=param.latch_vth,
            w=param.latch_on_w,
            l=param.latch_on_l,
        )(d=module.outerp, g=outer_on_gate_p, s=latch_on_rail, b=latch_on_rail)
        module.Mouter_on_n = _mos(
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

        module.Mouter_init_p = _mos(
            tp=latch_init_type,
            vth=param.rst_vth,
            w=param.rst_w,
            l=param.rst_l,
        )(d=module.outerp, g=outer_init_gate_p, s=latch_init_rail, b=latch_init_rail)
        module.Mouter_init_n = _mos(
            tp=latch_init_type,
            vth=param.rst_vth,
            w=param.rst_w,
            l=param.rst_l,
        )(d=module.outern, g=outer_init_gate_n, s=latch_init_rail, b=latch_init_rail)


# fmt: on


def _build_triple_tail(module, param: CompParams):
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
    module.Mtail2 = _mos(tp=reset_type, vth=vth, w=2 * param.latch_on_w, l=param.latch_on_l)(
        d=module.tail2, g=off_clk, s=init_rail, b=init_rail
    )
    module.Mmid_cross_p = _mos(tp=reset_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midp, g=module.midn, s=module.tail2, b=init_rail
    )
    module.Mmid_cross_n = _mos(tp=reset_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.midn, g=module.midp, s=module.tail2, b=init_rail
    )
    module.Mmid_in_p = _mos(tp=diff_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.midp, g=module.input_p_drain, s=on_rail, b=on_rail
    )
    module.Mmid_in_n = _mos(tp=diff_type, vth=param.rst_vth, w=param.rst_w, l=param.rst_l)(
        d=module.midn, g=module.input_n_drain, s=on_rail, b=on_rail
    )

    module.tail3 = h.Signal()
    module.Mtail3 = _mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.tail3, g=on_clk, s=on_rail, b=on_rail
    )
    module.Mcross_on_p = _mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.latch_p, g=module.latch_n, s=module.tail3, b=on_rail
    )
    module.Mcross_on_n = _mos(tp=diff_type, vth=vth, w=param.latch_on_w, l=param.latch_on_l)(
        d=module.latch_n, g=module.latch_p, s=module.tail3, b=on_rail
    )
    module.Mcross_init_p = _mos(tp=reset_type, vth=vth, w=param.latch_init_w, l=param.latch_init_l)(
        d=module.latch_p, g=module.latch_n, s=init_rail, b=init_rail
    )
    module.Mcross_init_n = _mos(tp=reset_type, vth=vth, w=param.latch_init_w, l=param.latch_init_l)(
        d=module.latch_n, g=module.latch_p, s=init_rail, b=init_rail
    )
    module.Minner_init_p = _mos(tp=reset_type, vth=param.rst_vth, w=4 * param.rst_w, l=param.rst_l)(
        d=module.latch_p, g=module.midn, s=init_rail, b=init_rail
    )
    module.Minner_init_n = _mos(tp=reset_type, vth=param.rst_vth, w=4 * param.rst_w, l=param.rst_l)(
        d=module.latch_n, g=module.midp, s=init_rail, b=init_rail
    )


def _build_output_srlatch(module, param: CompParams, latch_p, latch_n):
    """Build a static CMOS SR latch and buffered differential outputs.

    The dynamic comparator nodes return to their common reset level after each
    evaluation. Input inverters turn their differential decision into either
    active-high or active-low set/reset pulses. A cross-coupled NOR or NAND
    latch, selected from the dynamic-node reset polarity, retains that decision
    until the next comparison. Two inverter stages isolate the latch from its
    output load while preserving the one-hot output polarity.
    """

    # every gate drives one NMOS and one PMOS: they share a finger count (logic cells)
    (n_w, n_nf), (p_w, p_nf) = _logic_pair(param.srlatch_n_w, param.srlatch_p_w)
    (n_w2, n_nf2), (p_w2, p_nf2) = _logic_pair(2 * param.srlatch_n_w, 2 * param.srlatch_p_w)

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


def _build_output_stdcells(module, param: CompParams, latch_p, latch_n):
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


# ==== Named sizings, the topology sweep and netlists ====

FRIDA1 = CompParams(
    diffpair_w=37,
    tail_w=5,
    rst_w=8,
    latch_on_w=25,
    latch_init_w=33,
    srlatch_n_w=4,
    srlatch_p_w=8,
    diffpair_l=5,
    tail_l=13,
    rst_l=1,
    latch_on_l=6,
    latch_init_l=17,
    preamp_diff_xtors=MosType.NMOS,
    preamp_bias=Bias.SWITCHED,
    comp_stages=Stages.SINGLE,
    latch_inner_init_xtors=State.CLOCK,
)  # the fabricated FRIDA-1 comparator: single stage, NMOS input, switched tail
SIZE_PROFILES = {
    "half": {
        "diffpair_w": 19,
        "tail_w": 3,
        "rst_w": 4,
        "latch_on_w": 13,
        "latch_init_w": 17,
        "srlatch_n_w": 2,
        "srlatch_p_w": 4,
    },
    "double": {
        "diffpair_w": 74,
        "tail_w": 10,
        "rst_w": 16,
        "latch_on_w": 50,
        "latch_init_w": 66,
        "srlatch_n_w": 8,
        "srlatch_p_w": 16,
    },
}
LENGTHS = {"diffpair_l": 5, "tail_l": 13, "rst_l": 1, "latch_on_l": 6, "latch_init_l": 17}


def topologies() -> list[dict[str, Enum]]:
    """The 148 valid single- and double-stage topologies of the size sweep, in sweep order."""

    found = []
    for diff_type in (MosType.NMOS, MosType.PMOS):
        for bias in Bias:
            for stages in (Stages.SINGLE, Stages.DOUBLE):  # the latch-device sweep space
                for inner_on in State:
                    for outer_on in State:
                        for inner_init in (State.CLOCK, State.SIGNAL):
                            for outer_init in (State.OMIT, State.CLOCK, State.SIGNAL):
                                topology = {
                                    "comp_stages": stages,
                                    "preamp_diff_xtors": diff_type,
                                    "preamp_bias": bias,
                                    "latch_inner_on_xtors": inner_on,
                                    "latch_outer_on_xtors": outer_on,
                                    "latch_inner_init_xtors": inner_init,
                                    "latch_outer_init_xtors": outer_init,
                                }
                                if is_valid_comp_params(CompParams(**topology, **SIZE_PROFILES["half"], **LENGTHS)):
                                    found.append(topology)
    return found


def write_netlist(params: CompParams, path: Path, pdk, constant_from=None, *, generator=Comp, nets=CompNets) -> Path:
    """The comparator after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``.

    Elaborated with ``pdk`` active, so every device is fingered to its row cells and sized in
    whole unit widths; simulation compiles the same way. MOS lines give the total width and
    the finger count (``w`` is the total, as in the foundry models); logic cells are written as
    their library cells. ``constant_from`` (a PDK) keeps the analog devices at that PDK's
    physical widths and lengths (``_mos``) instead of the same unit counts. ``generator`` and
    ``nets`` write another block built from the same devices (its generator and port bundle).
    """

    global _CONSTANT_FROM
    path = Path(path)
    manager = import_module("hdl21.pdk.pdk")._mgr  # hdl21 offers no public way back to "no default set"
    previous = manager.default
    h.pdk.set_default(pdk)
    _CONSTANT_FROM = constant_from
    try:
        generator.Cache.reset()
        module = generator(params)
        h.pdk.compile(module, pdk)
    finally:
        generator.Cache.reset()
        manager.default = previous
        _CONSTANT_FROM = None
    nm = lambda value: round(float(value) * 1e9)
    ports = [name for name, net in nets.signals.items() if net.vis == h.Visibility.PORT]
    lines = [f".subckt {path.stem} {' '.join(ports)}"]
    for name, inst in module.instances.items():
        conns = {port: sig.name for port, sig in inst.conns.items()}
        call = inst.of
        if isinstance(call, h.PrimitiveCall) and call.prim is C:
            lines.append(f"{name} {conns['p']} {conns['n']} {float(call.params.c) * 1e15:g}f")
        elif isinstance(call, h.ExternalModuleCall):
            q = call.params
            # the PDK's name for the finger count; none where m carries the fingers (LF150, w per finger)
            fingers = next((f" {k}={int(getattr(q, k))}" for k in ("nf", "ng") if hasattr(q, k)), "")
            lines.append(
                f"{name} {conns['d']} {conns['g']} {conns['s']} {conns['b']} {call.module.name} "
                f"w={nm(q.w)}n l={nm(q.l)}n{fingers} m={int(q.m)}"
            )
        else:  # a logic cell's wrapper around one library cell
            (cell,) = call.instances.values()
            outer = {port.name: conns[port.name] for port in call.ports.values()}
            pins = [outer[sig.name] for sig in (cell.conns[p.name] for p in cell.of.module.port_list)]
            lines.append(f"{name} {' '.join(pins)} {cell.of.module.name}")
    lines.append(f".ends {path.stem}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> None:
    """Write a comparator netlist: FRIDA-1 or a size-sweep case, either output stage."""

    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("case", help="frida1, or a sweep case <topology index>_<half|double>, e.g. 40_half")
    parser.add_argument("output", type=Path, help="SPICE file to write (its stem names the subcircuit)")
    parser.add_argument("--output-stage", choices=("transistors", "stdcells"), default="transistors")
    parser.add_argument("--pdk", default="tsmc65")
    parser.add_argument("--constant-from", help="keep the analog devices at this PDK's physical sizes, e.g. tsmc65")
    args = parser.parse_args()
    if args.case == "frida1":
        params = FRIDA1
    else:
        index, profile = args.case.split("_")
        params = CompParams(**topologies()[int(index)], **SIZE_PROFILES[profile], **LENGTHS)
    params = CompParams(**{**params.__dict__, "output_stage": OutputStage[args.output_stage.upper()]})
    pdk, reference = (
        __import__(f"pdk.{name}.hdl21", fromlist=["pdk_logic"]).pdk_logic if name else None
        for name in (args.pdk, args.constant_from)
    )
    print(write_netlist(params, args.output, pdk, reference))


if __name__ == "__main__":
    main()
