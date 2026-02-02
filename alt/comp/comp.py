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

from ..flow.params import (
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    PreampBias,
    PreampDiffpair,
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
        dtype=PreampDiffpair,
        desc="Input diff pair type",
        default=PreampDiffpair.NMOS_INPUT,
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
    else:  # DOUBLE_STAGE
        # External reset only valid if powergate is external
        if p.latch_pwrgate_node == LatchPwrgateNode.INTERNAL:
            return p.latch_rst_extern_ctl == LatchRstExternCtl.NO_RESET
        return True


@h.generator
def Comp(p: CompParams) -> h.Module:
    """
    Comparator generator.

    Generates Strong-ARM or two-stage comparators based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    is_nmos_input = p.preamp_diffpair == PreampDiffpair.NMOS_INPUT

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
        vdd = h.Port(desc="Supply")
        vss = h.Port(desc="Ground")

        # Internal signals
        tail = h.Signal()
        outp_int = h.Signal()
        outn_int = h.Signal()

    # Build preamp
    _build_preamp(Comp, p, is_nmos_input)

    # Build latch
    if p.comp_stages == CompStages.SINGLE_STAGE:
        _build_single_stage_latch(Comp, p, is_nmos_input)
    else:
        _build_double_stage_latch(Comp, p, is_nmos_input)

    return Comp


def _build_preamp(mod, p: CompParams, is_nmos_input: bool):
    """Build input differential pair and load devices."""
    # Determine device types and polarities
    diff_type = MosType.NMOS if is_nmos_input else MosType.PMOS
    load_type = MosType.PMOS if is_nmos_input else MosType.NMOS
    tail_type = MosType.NMOS if is_nmos_input else MosType.PMOS

    diff_vth = p.diffpair_vth
    load_vth = p.rst_vth
    tail_vth = p.tail_vth

    diff_rail = mod.vss if is_nmos_input else mod.vdd
    load_rail = mod.vdd if is_nmos_input else mod.vss
    clk_on = mod.clk if is_nmos_input else mod.clkb
    clk_off = mod.clkb if is_nmos_input else mod.clk

    # Differential pair
    mod.mdiff_p = h.Mos(tp=diff_type, vth=diff_vth, w=p.diffpair_w, l=p.diffpair_l)(
        d=mod.outn_int, g=mod.inp, s=mod.tail, b=diff_rail
    )
    mod.mdiff_n = h.Mos(tp=diff_type, vth=diff_vth, w=p.diffpair_w, l=p.diffpair_l)(
        d=mod.outp_int, g=mod.inn, s=mod.tail, b=diff_rail
    )

    # Tail current source
    if p.preamp_bias == PreampBias.STD_BIAS:
        mod.mtail = h.Mos(tp=tail_type, vth=tail_vth, w=p.tail_w, l=p.tail_l)(
            d=mod.tail, g=clk_on, s=diff_rail, b=diff_rail
        )
    else:  # DYN_BIAS
        mod.vcap = h.Signal()
        mod.mtail = h.Mos(tp=tail_type, vth=tail_vth, w=p.tail_w, l=p.tail_l)(
            d=mod.tail, g=clk_on, s=mod.vcap, b=diff_rail
        )
        mod.mbias = h.Mos(tp=tail_type, vth=tail_vth, w=p.tail_w, l=p.tail_l)(
            d=mod.vcap, g=clk_on, s=diff_rail, b=diff_rail
        )
        mod.cbias = C(c=1 * f)(p=mod.vcap, n=load_rail)

    # Load/reset devices (use minimum length = 1)
    mod.mrst_p = h.Mos(tp=load_type, vth=load_vth, w=p.rst_w, l=1)(
        d=mod.outn_int, g=clk_off, s=load_rail, b=load_rail
    )
    mod.mrst_n = h.Mos(tp=load_type, vth=load_vth, w=p.rst_w, l=1)(
        d=mod.outp_int, g=clk_off, s=load_rail, b=load_rail
    )


def _build_single_stage_latch(mod, p: CompParams, is_nmos_input: bool):
    """Build Strong-ARM style single stage latch."""
    top_type = MosType.PMOS if is_nmos_input else MosType.NMOS
    bot_type = MosType.NMOS if is_nmos_input else MosType.PMOS
    latch_vth = p.latch_vth

    top_rail = mod.vdd if is_nmos_input else mod.vss
    bot_rail = mod.vss if is_nmos_input else mod.vdd
    clk_off = mod.clkb if is_nmos_input else mod.clk

    # Connect internal outputs to final outputs
    mod.outp_conn = h.Signal()
    mod.outn_conn = h.Signal()

    # Cross-coupled top devices (use minimum length = 1)
    mod.ma_p = h.Mos(tp=top_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outn_int, g=mod.outp_int, s=top_rail, b=top_rail
    )
    mod.ma_n = h.Mos(tp=top_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outp_int, g=mod.outn_int, s=top_rail, b=top_rail
    )

    # Cross-coupled bottom devices
    mod.mb_p = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outn_int, g=mod.outp_int, s=bot_rail, b=bot_rail
    )
    mod.mb_n = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outp_int, g=mod.outn_int, s=bot_rail, b=bot_rail
    )

    # Clocked reset
    mod.mlatch_rst_p = h.Mos(tp=top_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outn_int, g=clk_off, s=top_rail, b=top_rail
    )
    mod.mlatch_rst_n = h.Mos(tp=top_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outp_int, g=clk_off, s=top_rail, b=top_rail
    )

    # Output buffer inverters
    mod.mbuf_outp_top = h.Mos(tp=MosType.PMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outp, g=mod.outn_int, s=mod.vdd, b=mod.vdd
    )
    mod.mbuf_outp_bot = h.Mos(tp=MosType.NMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outp, g=mod.outn_int, s=mod.vss, b=mod.vss
    )
    mod.mbuf_outn_top = h.Mos(tp=MosType.PMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outn, g=mod.outp_int, s=mod.vdd, b=mod.vdd
    )
    mod.mbuf_outn_bot = h.Mos(tp=MosType.NMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outn, g=mod.outp_int, s=mod.vss, b=mod.vss
    )


def _build_double_stage_latch(mod, p: CompParams, is_nmos_input: bool):
    """Build two-stage latch with separate preamp and latch."""
    top_type = MosType.PMOS if is_nmos_input else MosType.NMOS
    bot_type = MosType.NMOS if is_nmos_input else MosType.PMOS
    latch_vth = p.latch_vth

    top_rail = mod.vdd if is_nmos_input else mod.vss
    bot_rail = mod.vss if is_nmos_input else mod.vdd

    # Internal latch nodes
    mod.latch_p = h.Signal()
    mod.latch_n = h.Signal()
    mod.latch_vdd = h.Signal()
    mod.latch_vss = h.Signal()

    # Core cross-coupled latch (use minimum length = 1)
    mod.mla_p = h.Mos(tp=top_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=mod.latch_p, s=mod.latch_vdd, b=top_rail
    )
    mod.mla_n = h.Mos(tp=top_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=mod.latch_n, s=mod.latch_vdd, b=top_rail
    )
    mod.mlb_p = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=mod.latch_p, s=mod.latch_vss, b=bot_rail
    )
    mod.mlb_n = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=mod.latch_n, s=mod.latch_vss, b=bot_rail
    )

    # Preamp to latch connection
    mod.mconn_p = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=mod.outn_int, s=bot_rail, b=bot_rail
    )
    mod.mconn_n = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=mod.outp_int, s=bot_rail, b=bot_rail
    )

    # Powergate - simplified version (clocked external)
    clk_off = mod.clkb if is_nmos_input else mod.clk
    mod.mpg_vdd = h.Mos(tp=top_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_vdd, g=clk_off, s=top_rail, b=top_rail
    )
    mod.mpg_vss = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_vss,
        g=mod.vdd,
        s=bot_rail,
        b=bot_rail,  # Always on
    )

    # Internal reset
    mod.mrst_int_p = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_n, g=clk_off, s=mod.latch_vss, b=bot_rail
    )
    mod.mrst_int_n = h.Mos(tp=bot_type, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.latch_p, g=clk_off, s=mod.latch_vss, b=bot_rail
    )

    # Output buffers
    mod.mbuf_outp_top = h.Mos(tp=MosType.PMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outp, g=mod.latch_n, s=mod.vdd, b=mod.vdd
    )
    mod.mbuf_outp_bot = h.Mos(tp=MosType.NMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outp, g=mod.latch_n, s=mod.vss, b=mod.vss
    )
    mod.mbuf_outn_top = h.Mos(tp=MosType.PMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outn, g=mod.latch_p, s=mod.vdd, b=mod.vdd
    )
    mod.mbuf_outn_bot = h.Mos(tp=MosType.NMOS, vth=latch_vth, w=p.latch_w, l=1)(
        d=mod.outn, g=mod.latch_p, s=mod.vss, b=mod.vss
    )


def comp_variants(
    preamp_diffpairs: list = None,
    preamp_biases: list = None,
    comp_stages_list: list = None,
    diffpair_w_list: list = None,
) -> list:
    """
    Generate a list of valid CompParams for parameter sweeps.

    Only generates valid topology combinations.

    Args:
        diffpair_w_list: List of diff pair width multipliers (default: [40, 80])
    """
    if preamp_diffpairs is None:
        preamp_diffpairs = list(PreampDiffpair)
    if preamp_biases is None:
        preamp_biases = list(PreampBias)
    if comp_stages_list is None:
        comp_stages_list = list(CompStages)
    if diffpair_w_list is None:
        diffpair_w_list = [40, 80]

    variants = []

    for preamp_diffpair in preamp_diffpairs:
        for preamp_bias in preamp_biases:
            for comp_stages in comp_stages_list:
                for diffpair_w in diffpair_w_list:
                    # Use canonical latch params for single stage
                    if comp_stages == CompStages.SINGLE_STAGE:
                        params = CompParams(
                            preamp_diffpair=preamp_diffpair,
                            preamp_bias=preamp_bias,
                            comp_stages=comp_stages,
                            latch_pwrgate_ctl=LatchPwrgateCtl.CLOCKED,
                            latch_pwrgate_node=LatchPwrgateNode.EXTERNAL,
                            latch_rst_extern_ctl=LatchRstExternCtl.CLOCKED,
                            latch_rst_intern_ctl=LatchRstInternCtl.CLOCKED,
                            diffpair_w=diffpair_w,
                        )
                        variants.append(params)
                    else:
                        # Double stage - generate a few key combinations
                        for latch_pwrgate_node in LatchPwrgateNode:
                            if latch_pwrgate_node == LatchPwrgateNode.INTERNAL:
                                rst_extern = LatchRstExternCtl.NO_RESET
                            else:
                                rst_extern = LatchRstExternCtl.CLOCKED

                            params = CompParams(
                                preamp_diffpair=preamp_diffpair,
                                preamp_bias=preamp_bias,
                                comp_stages=comp_stages,
                                latch_pwrgate_ctl=LatchPwrgateCtl.CLOCKED,
                                latch_pwrgate_node=latch_pwrgate_node,
                                latch_rst_extern_ctl=rst_extern,
                                latch_rst_intern_ctl=LatchRstInternCtl.CLOCKED,
                                diffpair_w=diffpair_w,
                            )
                            if is_valid_comp_params(params):
                                variants.append(params)

    return variants
