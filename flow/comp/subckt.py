"""
Comparator generator for FRIDA.

Supports multiple topologies including:
- NMOS/PMOS input differential pairs
- Standard/dynamic biasing
- Single/double stage latches
- Various power-gating and reset configurations
"""

from enum import Enum, auto

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import C, MosType, MosVth


class Stages(Enum):
    SINGLE = auto()
    DOUBLE = auto()


class Bias(Enum):
    DYNAMIC = auto()
    SWITCHED = auto()


class State(Enum):
    CLOCK = auto()
    SIGNAL = auto()
    OMIT = auto()


@h.paramclass
class CompParams:
    """Comparator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=10 means 10×Wmin, e.g., 1.2µm for TSMC65)
    - l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for TSMC65)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    comp_stages = h.Param(dtype=Stages, desc="Comparator stages", default=Stages.SINGLE)

    preamp_diff_xtors = h.Param(
        dtype=MosType,
        desc="Input diff pair type (NMOS or PMOS)",
        default=MosType.NMOS,
    )
    preamp_bias = h.Param(dtype=Bias, desc="Biasing type", default=Bias.DYNAMIC)

    # Latch transistor pairs — each can be clocked, signaled, or omitted
    latch_outer_on_xtors = h.Param(
        dtype=State, desc="Outer on devices", default=State.OMIT
    )
    latch_inner_on_xtors = h.Param(
        dtype=State, desc="Inner on  devices", default=State.OMIT
    )
    latch_outer_init_xtors = h.Param(
        dtype=State, desc="Outer init devices", default=State.OMIT
    )
    latch_inner_init_xtors = h.Param(
        dtype=State, desc="Inner init devices", default=State.CLOCK
    )

    # Device sizing (multipliers of Wmin/Lmin)
    diffpair_w = h.Param(dtype=int, desc="Diff pair width multiplier", default=40)
    diffpair_l = h.Param(dtype=int, desc="Diff pair length multiplier", default=1)
    diffpair_vth = h.Param(dtype=MosVth, desc="Diff pair Vth", default=MosVth.LOW)

    tail_w = h.Param(dtype=int, desc="Tail width multiplier", default=20)
    tail_l = h.Param(dtype=int, desc="Tail length multiplier", default=2)
    tail_vth = h.Param(dtype=MosVth, desc="Tail Vth", default=MosVth.STD)

    rst_w = h.Param(dtype=int, desc="Reset device width multiplier", default=20)
    rst_vth = h.Param(dtype=MosVth, desc="Reset Vth", default=MosVth.LOW)

    latch_w = h.Param(dtype=int, desc="Latch device width multiplier", default=20)
    latch_vth = h.Param(dtype=MosVth, desc="Latch Vth", default=MosVth.LOW)


def is_valid_comp_params(param: CompParams) -> bool:
    """Check if this topology combination is valid.

    Inner init devices must always exist (CLOCK or SIGNAL, never OMIT).

    Single stage: Both kinds of on devices plus outer init devices must be OMIT.

    Double stage: at least one on device pair must exist, and at least
    one of the four device pairs must be signaled (not just clocked).
    """
    if param.latch_inner_init_xtors == State.OMIT:
        return False

    if param.comp_stages == Stages.SINGLE:
        return (
            param.latch_outer_on_xtors == State.OMIT
            and param.latch_inner_on_xtors == State.OMIT
            and param.latch_outer_init_xtors == State.OMIT
        )
    # outer_init requires outer_on (needs outerp/outern nodes)
    if (
        param.latch_outer_init_xtors != State.OMIT
        and param.latch_outer_on_xtors == State.OMIT
    ):
        return False

    if param.comp_stages == Stages.DOUBLE:
        has_on = (
            param.latch_outer_on_xtors != State.OMIT
            or param.latch_inner_on_xtors != State.OMIT
        )
        has_signal = State.SIGNAL in (
            param.latch_outer_on_xtors,
            param.latch_inner_on_xtors,
            param.latch_outer_init_xtors,
            param.latch_inner_init_xtors,
        )
        return has_on and has_signal
    return False


@h.generator
def Comp(param: CompParams) -> h.Module:
    """
    Comparator generator.

    Generates Strong-ARM or two-stage comparators based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_comp_params(param):
        raise ValueError(f"Invalid comparator params: {param}")

    @h.module
    class Comp:
        """Comparator module."""

        # IO ports
        inp = h.Input(desc="Positive input")
        inn = h.Input(desc="Negative input")
        outp = h.Output(desc="Positive output")
        outn = h.Output(desc="Negative output")
        clk = h.Input(desc="Clock")
        clkb = h.Input(desc="Clock complement")
        vdd = h.Inout(desc="Supply")
        vss = h.Inout(desc="Ground")

        # Internal signals
        tail = h.Signal()

        # Additional signals added by sub-builders:
        # Preamp: preamp_p, preamp_n — preamp output nodes
        #         cap_node (only if Bias.DYNAMIC)
        # Latch:  innerp, innern — cross-coupled inverter outputs

    # Build preamp
    _build_preamp(Comp, param)

    # Build latch
    _build_latch(Comp, param)

    # Build output buffers
    _build_output_buffers(Comp, param, Comp.innerp, Comp.innern)

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
    # preamp_n ─┤             ├─ preamp_p
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
    module.preamp_p = h.Signal()
    module.preamp_n = h.Signal()

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

    # Differential pair
    module.Mdiff_p = h.Mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=param.diffpair_l)(d=module.preamp_n, g=module.inp, s=module.tail, b=on_rail)
    module.Mdiff_n = h.Mos(tp=diff_type, vth=param.diffpair_vth, w=param.diffpair_w, l=param.diffpair_l)(d=module.preamp_p, g=module.inn, s=module.tail, b=on_rail)

    # Tail current source
    if param.preamp_bias == Bias.SWITCHED:
        module.Mtail = h.Mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(d=module.tail, g=on_clk, s=on_rail, b=on_rail)
    elif param.preamp_bias == Bias.DYNAMIC:
        # Source of tail device connects to a cap node that stores charge
        # during init (via mbias) and sources current during comparison
        module.cap_node = h.Signal()
        module.Mtail = h.Mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(d=module.tail, g=on_clk, s=module.cap_node, b=on_rail)
        module.Mbias = h.Mos(tp=tail_type, vth=param.tail_vth, w=param.tail_w, l=param.tail_l)(d=module.cap_node, g=off_clk, s=on_rail, b=on_rail)
        module.Cbias = C(c=100 * f)(p=module.cap_node, n=on_rail)

    # Reset/precharge devices (minimum length = 1)
    # Precharge preamp outputs during reset phase.
    # For NMOS input: PMOS reset gate=clk → ON when clk=0, OFF when clk=1
    # For PMOS input: NMOS reset gate=clkb → ON when clkb=0, OFF when clkb=1
    module.Mrst_p = h.Mos(tp=reset_type, vth=param.rst_vth, w=param.rst_w, l=1)(d=module.preamp_n, g=on_clk, s=init_rail, b=init_rail)
    module.Mrst_n = h.Mos(tp=reset_type, vth=param.rst_vth, w=param.rst_w, l=1)(d=module.preamp_p, g=on_clk, s=init_rail, b=init_rail)
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
    preamp_init_rail = (
        module.vdd if param.preamp_diff_xtors == MosType.NMOS else module.vss
    )

    # In a single stage, the late pre-charges to same rail as the preamp, in double stage it's opposite
    latch_init_rail = (
        preamp_init_rail
        if param.comp_stages == Stages.SINGLE
        else opposite[preamp_init_rail]
    )
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
    # innern                   innerp
    #  │                           │
    #  │                           │
    #  └─┐╷  innerp     innern  ╷┌─┘
    #    │├───               ───┤│
    #  ┌─┘╵                     ╵└─┐
    #  │                           │
    #  │                           │
    #  │                           │
    # ─┴─     latch_init_rail     ─┴─

    module.innerp = h.Signal()
    module.innern = h.Signal()

    module.Mcross_init_p = h.Mos(tp=latch_init_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.innerp, g=module.innern, s=latch_init_rail, b=latch_init_rail)
    module.Mcross_init_n = h.Mos(tp=latch_init_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.innern, g=module.innerp, s=latch_init_rail, b=latch_init_rail)

    # --- Minner_init: inner init (reset) devices ---
    # When signaled: gates driven by preamp outputs (cross-coupled)
    # When clocked: gates driven by latch_clk
    if param.latch_inner_init_xtors == State.SIGNAL:
        init_inner_gate_p = module.preamp_n
        init_inner_gate_n = module.preamp_p
    if param.latch_inner_init_xtors == State.CLOCK:
        init_inner_gate_p = latch_clk
        init_inner_gate_n = latch_clk

    module.Minner_init_p = h.Mos(tp=latch_init_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.innerp, g=init_inner_gate_p, s=latch_init_rail, b=latch_init_rail)
    module.Minner_init_n = h.Mos(tp=latch_init_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.innern, g=init_inner_gate_n, s=latch_init_rail, b=latch_init_rail)

    # --- Minner_on: inner on (current steering) devices ---
    # Only valid in double stage mode. Drains connect to innerp/innern,
    # sources introduce midp/midn nodes.
    if param.latch_inner_on_xtors != State.OMIT:
        module.midp = h.Signal()
        module.midn = h.Signal()

        if param.latch_inner_on_xtors == State.SIGNAL:
            inner_on_gate_p = module.preamp_p
            inner_on_gate_n = module.preamp_n
        elif param.latch_inner_on_xtors == State.CLOCK:
            inner_on_gate_p = latch_clk
            inner_on_gate_n = latch_clk

        module.Minner_on_p = h.Mos(tp=latch_on_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.innerp, g=inner_on_gate_p, s=module.midp, b=latch_on_rail)
        module.Minner_on_n = h.Mos(tp=latch_on_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.innern, g=inner_on_gate_n, s=module.midn, b=latch_on_rail)

    # --- Mcross_on: cross-coupled inverter pair, on side ---
    # Drains connect to midp/midn if inner_on devices exist, otherwise innerp/innern.
    # Sources connect to outerp/outern if outer_on devices exist, otherwise on_rail.
    cross_on_drain_p = (
        module.midp if param.latch_inner_on_xtors != State.OMIT else module.innerp
    )
    cross_on_drain_n = (
        module.midn if param.latch_inner_on_xtors != State.OMIT else module.innern
    )

    # If single stage, cross-coupled latch outer driven directly from preamp
    if param.comp_stages == Stages.SINGLE:
        cross_on_src_p = module.preamp_p
        cross_on_src_n = module.preamp_n
    # Double stage with outer on: intermediate node to outer devices
    elif param.latch_outer_on_xtors != State.OMIT:
        module.outerp = h.Signal()
        module.outern = h.Signal()
        cross_on_src_p = module.outerp
        cross_on_src_n = module.outern
    # Double stage without outer on: connect directly to on rail
    else:
        cross_on_src_p = latch_on_rail
        cross_on_src_n = latch_on_rail

    module.Mcross_on_p = h.Mos(tp=latch_on_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=cross_on_drain_p, g=module.innern, s=cross_on_src_p, b=latch_on_rail)
    module.Mcross_on_n = h.Mos(tp=latch_on_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=cross_on_drain_n, g=module.innerp, s=cross_on_src_n, b=latch_on_rail)

    # --- Mouter_on: outer on (currently steering) devices ---
    # Only available in double stage mode.
    if param.latch_outer_on_xtors != State.OMIT:
        if param.latch_outer_on_xtors == State.SIGNAL:
            outer_on_gate_p = module.preamp_p
            outer_on_gate_n = module.preamp_n
        elif param.latch_outer_on_xtors == State.CLOCK:
            outer_on_gate_p = latch_clk
            outer_on_gate_n = latch_clk

        module.Mouter_on_p = h.Mos(tp=latch_on_type, vth=param.latch_vth, w=param.latch_w, l=1)(
            d=module.outerp, g=outer_on_gate_p, s=latch_on_rail, b=latch_on_rail
        )
        module.Mouter_on_n = h.Mos(tp=latch_on_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.outern, g=outer_on_gate_n, s=latch_on_rail, b=latch_on_rail)

    # --- Mouter_init: outer init (reset) devices ---
    # Requires outer_on devices to exist (for outerp/outern nodes).
    if param.latch_outer_init_xtors != State.OMIT:
        if param.latch_outer_init_xtors == State.SIGNAL:
            outer_init_gate_p = module.preamp_p
            outer_init_gate_n = module.preamp_n
        elif param.latch_outer_init_xtors == State.CLOCK:
            outer_init_gate_p = latch_clk
            outer_init_gate_n = latch_clk

        module.Mouter_init_p = h.Mos(tp=latch_init_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.outerp, g=outer_init_gate_p, s=latch_init_rail, b=latch_init_rail)
        module.Mouter_init_n = h.Mos(tp=latch_init_type, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.outern, g=outer_init_gate_n, s=latch_init_rail, b=latch_init_rail)
# fmt: on


def _build_output_buffers(module, param: CompParams, innerp, innern):
    """Build output buffer inverters driven by latch nodes.

    TODO: Output polarity differs between single and double stage.
    Either add a second inverter stage for single stage so outp/outn
    init state is always both-low, or have downstream logic account
    for the polarity difference.
    """
    module.Mbuf_outp_top = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.outp, g=innern, s=module.vdd, b=module.vdd)
    module.Mbuf_outp_bot = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.outp, g=innern, s=module.vss, b=module.vss)
    module.Mbuf_outn_top = h.Mos(tp=MosType.PMOS, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.outn, g=innerp, s=module.vdd, b=module.vdd)
    module.Mbuf_outn_bot = h.Mos(tp=MosType.NMOS, vth=param.latch_vth, w=param.latch_w, l=1)(d=module.outn, g=innerp, s=module.vss, b=module.vss)
# fmt: on
