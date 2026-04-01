"""
Comparator generator for FRIDA.

Supports multiple topologies including:
- NMOS/PMOS input differential pairs
- Standard/dynamic biasing
- Single/double stage latches
- Various power-gating and reset configurations
"""

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import C, MosType, MosVth

from ..circuit.params import (
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    PreampBias,
)


@h.paramclass
class CompParams:
    """Comparator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=10 means 10×Wmin, e.g., 1.2µm for TSMC65)
    - l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for TSMC65)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    preamp_diffpair = h.Param(
        dtype=MosType,
        desc="Input diff pair type (NMOS or PMOS)",
        default=MosType.NMOS,
    )
    preamp_bias = h.Param(
        dtype=PreampBias, desc="Biasing type", default=PreampBias.STD_BIAS
    )
    comp_stages = h.Param(
        dtype=CompStages, desc="Comparator stages", default=CompStages.SINGLE_STAGE
    )
    latch_pwrgate_ctl = h.Param(
        dtype=LatchPwrgateCtl, desc="Powergate control", default=LatchPwrgateCtl.CLOCKED
    )
    latch_pwrgate_node = h.Param(
        dtype=LatchPwrgateNode,
        desc="Powergate position",
        default=LatchPwrgateNode.EXTERNAL,
    )
    latch_rst_extern_ctl = h.Param(
        dtype=LatchRstExternCtl,
        desc="External reset control",
        default=LatchRstExternCtl.CLOCKED,
    )
    latch_rst_intern_ctl = h.Param(
        dtype=LatchRstInternCtl,
        desc="Internal reset control",
        default=LatchRstInternCtl.CLOCKED,
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


def is_valid_comp_params(p: CompParams) -> bool:
    """Check if this topology combination is valid."""
    if p.comp_stages == CompStages.SINGLE_STAGE:
        # For single stage, latch params must be canonical
        return (
            p.latch_pwrgate_ctl == LatchPwrgateCtl.CLOCKED
            and p.latch_pwrgate_node == LatchPwrgateNode.EXTERNAL
            and p.latch_rst_extern_ctl == LatchRstExternCtl.CLOCKED
            and p.latch_rst_intern_ctl == LatchRstInternCtl.CLOCKED
        )
    elif p.comp_stages == CompStages.DOUBLE_STAGE:
        # External reset only valid if powergate is external
        if p.latch_pwrgate_node == LatchPwrgateNode.INTERNAL:
            return p.latch_rst_extern_ctl == LatchRstExternCtl.NO_RESET
        return True
    return False


@h.generator
def Comp(p: CompParams) -> h.Module:
    """
    Comparator generator.

    Generates Strong-ARM or two-stage comparators based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_comp_params(p):
        raise ValueError(f"Invalid comparator params: {p}")

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
        outp_int = h.Signal()
        outn_int = h.Signal()

    # Build preamp
    _build_preamp(Comp, p)

    # Build latch
    if p.comp_stages == CompStages.SINGLE_STAGE:
        _build_single_stage_latch(Comp, p)
        _build_output_buffers(Comp, p, Comp.outp_int, Comp.outn_int)
    elif p.comp_stages == CompStages.DOUBLE_STAGE:
        _build_double_stage_latch(Comp, p)
        _build_output_buffers(Comp, p, Comp.latch_p, Comp.latch_n)

    return Comp


def _build_preamp(mod, p: CompParams):
    """Build input differential pair and reset/precharge devices."""

    # These initial 7 values are derived from the preamp polarity, so that we can get invert the topology
    diff_type = p.preamp_diffpair
    reset_type = MosType.PMOS if p.preamp_diffpair == MosType.NMOS else MosType.NMOS
    tail_type = p.preamp_diffpair

    # The rail that we move toward during comparison
    on_rail = mod.vss if p.preamp_diffpair == MosType.NMOS else mod.vdd
    # The rail that we move toward during reset
    off_rail = mod.vdd if p.preamp_diffpair == MosType.NMOS else mod.vss

    # We use the main clock for the reset and tail devices
    on_clk = mod.clk if p.preamp_diffpair == MosType.NMOS else mod.clkb
    # An opposite polarity is only needed for a dynamic bias devices
    off_clk = mod.clkb if p.preamp_diffpair == MosType.NMOS else mod.clk

    # Differential pair
    mod.mdiff_p = h.Mos(
        tp=diff_type, vth=p.diffpair_vth, w=p.diffpair_w, l=p.diffpair_l
    )(d=mod.outn_int, g=mod.inp, s=mod.tail, b=on_rail)
    mod.mdiff_n = h.Mos(
        tp=diff_type, vth=p.diffpair_vth, w=p.diffpair_w, l=p.diffpair_l
    )(d=mod.outp_int, g=mod.inn, s=mod.tail, b=on_rail)

    # Tail current source
    if p.preamp_bias == PreampBias.STD_BIAS:
        mod.mtail = h.Mos(tp=tail_type, vth=p.tail_vth, w=p.tail_w, l=p.tail_l)(
            d=mod.tail, g=on_clk, s=on_rail, b=on_rail
        )
    elif p.preamp_bias == PreampBias.DYN_BIAS:
        mod.vcap = h.Signal()
        mod.mtail = h.Mos(tp=tail_type, vth=p.tail_vth, w=p.tail_w, l=p.tail_l)(
            d=mod.tail, g=on_clk, s=mod.vcap, b=on_rail
        )
        mod.mbias = h.Mos(tp=tail_type, vth=p.tail_vth, w=p.tail_w, l=p.tail_l)(
            d=mod.vcap, g=off_clk, s=on_rail, b=on_rail
        )
        mod.cbias = C(c=100 * f)(p=mod.vcap, n=on_rail)

    # Reset/precharge devices (minimum length = 1)
    # Precharge preamp outputs during reset phase.
    # For NMOS input: PMOS reset gate=clk → ON when clk=0, OFF when clk=1
    # For PMOS input: NMOS reset gate=clkb → ON when clkb=0, OFF when clkb=1
    mod.mrst_p = h.Mos(tp=reset_type, vth=p.rst_vth, w=p.rst_w, l=1)(
        d=mod.outn_int, g=on_clk, s=off_rail, b=off_rail
    )
    mod.mrst_n = h.Mos(tp=reset_type, vth=p.rst_vth, w=p.rst_w, l=1)(
        d=mod.outp_int, g=on_clk, s=off_rail, b=off_rail
    )


def _build_single_stage_latch(mod, p: CompParams):
    """Build Strong-ARM style single stage latch.

    The cross-coupled latch sits directly on the preamp output nodes
    (outp_int/outn_int). Output buffers are driven from these same nodes.
    """

    top_type = MosType.PMOS if p.preamp_diffpair == MosType.NMOS else MosType.NMOS
    bot_type = MosType.NMOS if p.preamp_diffpair == MosType.NMOS else MosType.PMOS

    top_rail = mod.vdd if p.preamp_diffpair == MosType.NMOS else mod.vss
    bot_rail = mod.vss if p.preamp_diffpair == MosType.NMOS else mod.vdd
    clk_off = mod.clkb if p.preamp_diffpair == MosType.NMOS else mod.clk

    # Cross-coupled top devices (minimum length = 1)
    mod.ma_p = h.Mos(tp=top_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outn_int, g=mod.outp_int, s=top_rail, b=top_rail
    )
    mod.ma_n = h.Mos(tp=top_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outp_int, g=mod.outn_int, s=top_rail, b=top_rail
    )

    # Cross-coupled bottom devices
    mod.mb_p = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outn_int, g=mod.outp_int, s=bot_rail, b=bot_rail
    )
    mod.mb_n = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outp_int, g=mod.outn_int, s=bot_rail, b=bot_rail
    )

    # Clocked reset
    mod.mlatch_rst_p = h.Mos(tp=top_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outn_int, g=clk_off, s=top_rail, b=top_rail
    )
    mod.mlatch_rst_n = h.Mos(tp=top_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outp_int, g=clk_off, s=top_rail, b=top_rail
    )


def _build_double_stage_latch(mod, p: CompParams):
    """Build two-stage latch with separate preamp and latch."""

    top_type = MosType.PMOS if p.preamp_diffpair == MosType.NMOS else MosType.NMOS
    bot_type = MosType.NMOS if p.preamp_diffpair == MosType.NMOS else MosType.PMOS

    top_rail = mod.vdd if p.preamp_diffpair == MosType.NMOS else mod.vss
    bot_rail = mod.vss if p.preamp_diffpair == MosType.NMOS else mod.vdd
    clk_off = mod.clkb if p.preamp_diffpair == MosType.NMOS else mod.clk

    # Internal latch nodes
    mod.latch_p = h.Signal()
    mod.latch_n = h.Signal()
    mod.latch_vdd = h.Signal()
    mod.latch_vss = h.Signal()

    # Core cross-coupled latch (minimum length = 1)
    mod.mla_p = h.Mos(tp=top_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=mod.latch_p, s=mod.latch_vdd, b=top_rail
    )
    mod.mla_n = h.Mos(tp=top_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=mod.latch_n, s=mod.latch_vdd, b=top_rail
    )
    mod.mlb_p = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=mod.latch_p, s=mod.latch_vss, b=bot_rail
    )
    mod.mlb_n = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=mod.latch_n, s=mod.latch_vss, b=bot_rail
    )

    # Preamp to latch connection
    mod.mconn_p = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=mod.outn_int, s=bot_rail, b=bot_rail
    )
    mod.mconn_n = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=mod.outp_int, s=bot_rail, b=bot_rail
    )

    # Latch power gating (clocked external)
    mod.mpg_vdd = h.Mos(tp=top_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_vdd, g=clk_off, s=top_rail, b=top_rail
    )
    mod.mpg_vss = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_vss,
        g=mod.vdd,
        s=bot_rail,
        b=bot_rail,  # Always on
    )

    # Internal reset
    mod.mrst_int_p = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=clk_off, s=mod.latch_vss, b=bot_rail
    )
    mod.mrst_int_n = h.Mos(tp=bot_type, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=clk_off, s=mod.latch_vss, b=bot_rail
    )


def _build_output_buffers(mod, p: CompParams, latch_p, latch_n):
    """Build output buffer inverters driven by latch nodes."""
    mod.mbuf_outp_top = h.Mos(tp=MosType.PMOS, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outp, g=latch_n, s=mod.vdd, b=mod.vdd
    )
    mod.mbuf_outp_bot = h.Mos(tp=MosType.NMOS, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outp, g=latch_n, s=mod.vss, b=mod.vss
    )
    mod.mbuf_outn_top = h.Mos(tp=MosType.PMOS, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outn, g=latch_p, s=mod.vdd, b=mod.vdd
    )
    mod.mbuf_outn_bot = h.Mos(tp=MosType.NMOS, vth=p.latch_vth, w=p.latch_w, l=1)(
        d=mod.outn, g=latch_p, s=mod.vss, b=mod.vss
    )
