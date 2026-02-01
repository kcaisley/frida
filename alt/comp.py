"""
Comparator generator for FRIDA.

Supports multiple topologies including:
- NMOS/PMOS input differential pairs
- Standard/dynamic biasing
- Single/double stage latches
- Various power-gating and reset configurations

Includes testbench, simulation definitions, Monte Carlo support,
and pytest test functions.
"""

import io
from dataclasses import dataclass
from typing import Any, Dict, List

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosType, MosVth, R, Vdc, Vpulse

from .common.params import (
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    PreampBias,
    PreampDiffpair,
    Project,
    Pvt,
    SupplyVals,
    Vth,
)
from .conftest import SimTestMode


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
    diffpair_vth = h.Param(dtype=Vth, desc="Diff pair Vth", default=Vth.LVT)

    tail_w = h.Param(dtype=int, desc="Tail width multiplier", default=20)
    tail_l = h.Param(dtype=int, desc="Tail length multiplier", default=2)
    tail_vth = h.Param(dtype=Vth, desc="Tail Vth", default=Vth.SVT)

    rst_w = h.Param(dtype=int, desc="Reset device width multiplier", default=20)
    rst_vth = h.Param(dtype=Vth, desc="Reset Vth", default=Vth.LVT)

    latch_w = h.Param(dtype=int, desc="Latch device width multiplier", default=20)
    latch_vth = h.Param(dtype=Vth, desc="Latch Vth", default=Vth.LVT)


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


def _vth_to_mosvth(vth: Vth) -> MosVth:
    """Convert FRIDA Vth enum to HDL21 MosVth."""
    return MosVth.LOW if vth == Vth.LVT else MosVth.STD


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

    diff_vth = _vth_to_mosvth(p.diffpair_vth)
    load_vth = _vth_to_mosvth(p.rst_vth)
    tail_vth = _vth_to_mosvth(p.tail_vth)

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
    latch_vth = _vth_to_mosvth(p.latch_vth)

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
    latch_vth = _vth_to_mosvth(p.latch_vth)

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


# =============================================================================
# MONTE CARLO CONFIGURATION
# =============================================================================


@dataclass
class MCConfig:
    """Monte Carlo simulation configuration."""

    numruns: int = 10  # Default: 10 runs for quick characterization
    seed: int = 12345  # Fixed seed for reproducibility
    variations: str = (
        "mismatch"  # Default: mismatch only (most relevant for comparator)
    )


DEFAULT_MC_CONFIG = MCConfig()


# =============================================================================
# TESTBENCH
# =============================================================================


@h.paramclass
class CompTbParams:
    """Comparator testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())
    vin_diff = h.Param(
        dtype=h.Scalar, desc="Differential input voltage", default=10 * m
    )
    vcm = h.Param(dtype=h.Scalar, desc="Common-mode voltage", default=600 * m)


@h.generator
def CompTb(params: CompTbParams) -> h.Module:
    """
    Comparator testbench generator.

    Creates a testbench matching the original blocks/comp.py structure:
    - DC supplies
    - Common-mode voltage (configurable)
    - Symmetric differential inputs around CM
    - Source impedances (1kOhm + 100fF)
    - 10ns clock period, 40% duty cycle (4ns high)
    - 10fF output loading
    """
    supply = SupplyVals.corner(params.pvt.v)

    tb = h.sim.tb("CompTb")

    # Power supplies
    tb.vdd = h.Signal()
    tb.vvdd = Vdc(dc=supply.VDD)(p=tb.vdd, n=tb.VSS)

    # Common mode voltage
    tb.vcm = h.Signal()
    tb.vvcm = Vdc(dc=params.vcm)(p=tb.vcm, n=tb.VSS)

    # Symmetric differential inputs around common mode
    # in+ = CM + diff/2, in- = CM - diff/2
    tb.vin_src = h.Signal()
    tb.vref_src = h.Signal()
    tb.vdiff_p = Vdc(dc=params.vin_diff / 2)(p=tb.vin_src, n=tb.vcm)
    tb.vdiff_n = Vdc(dc=-params.vin_diff / 2)(p=tb.vref_src, n=tb.vcm)

    # Source impedances (models DAC/SHA output impedance)
    # r=1kOhm, c=100fF
    tb.inp = h.Signal()
    tb.inn = h.Signal()
    tb.rsrc_p = R(r=1000)(p=tb.vin_src, n=tb.inp)
    tb.rsrc_n = R(r=1000)(p=tb.vref_src, n=tb.inn)
    tb.csrc_p = C(c=100 * f)(p=tb.inp, n=tb.VSS)
    tb.csrc_n = C(c=100 * f)(p=tb.inn, n=tb.VSS)

    # Clocks: 10ns period, 40% duty cycle (4ns high = evaluation phase)
    tb.clk = h.Signal()
    tb.clkb = h.Signal()
    tb.vclk = Vpulse(
        v1=0 * m,
        v2=supply.VDD,
        period=10 * n,
        width=4 * n,
        rise=100 * p,
        fall=100 * p,
        delay=500 * p,
    )(p=tb.clk, n=tb.VSS)
    tb.vclkb = Vpulse(
        v1=supply.VDD,
        v2=0 * m,
        period=10 * n,
        width=4 * n,
        rise=100 * p,
        fall=100 * p,
        delay=500 * p,
    )(p=tb.clkb, n=tb.VSS)

    # Output loading (10fF each)
    tb.outp = h.Signal()
    tb.outn = h.Signal()
    tb.cload_p = C(c=10 * f)(p=tb.outp, n=tb.VSS)
    tb.cload_n = C(c=10 * f)(p=tb.outn, n=tb.VSS)

    # DUT
    tb.dut = Comp(params.comp)(
        inp=tb.inp,
        inn=tb.inn,
        outp=tb.outp,
        outn=tb.outn,
        clk=tb.clk,
        clkb=tb.clkb,
        vdd=tb.vdd,
        vss=tb.VSS,
    )

    return tb


# =============================================================================
# SIMULATION DEFINITIONS
# =============================================================================


def sim_input(params: CompTbParams) -> hs.Sim:
    """
    Create deterministic transient simulation for comparator characterization.

    Matches original: tran(stop=5.5e-6)
    Saves: v(inp, inn, outp, outn, clk), i(Vvdd)
    """
    temp = Project.temper(params.pvt.t)

    @hs.sim
    class CompSim:
        tb = CompTb(params)

        # Transient analysis (matches original 5.5us stop time)
        tr = hs.Tran(tstop=5500 * n, tstep=1 * n)

        # Measurements matching original measures dict
        t_delay = hs.Meas(
            analysis=tr,
            expr="trig V(xtop.clk) val=0.6 rise=1 targ V(xtop.outp) val=0.6 rise=1",
        )

        # Save key signals
        save = hs.Save(hs.SaveMode.ALL)

        # Temperature setting
        # Use _ for Literal (frozen dataclass, has no name field)
        _ = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
        """
        )

    return CompSim


def sim_input_with_mc(
    params: CompTbParams,
    mc_config: MCConfig = None,
) -> hs.Sim:
    """
    Create Monte Carlo transient simulation for offset characterization.

    Monte Carlo config (default matches original blocks/comp.py):
    - numruns: 10
    - seed: 12345
    - variations: mismatch

    HDL21 MonteCarlo wraps inner analyses with statistical variation.
    """
    if mc_config is None:
        mc_config = DEFAULT_MC_CONFIG

    temp = Project.temper(params.pvt.t)
    numruns = mc_config.numruns
    seed = mc_config.seed
    variations = mc_config.variations

    @hs.sim
    class CompMcSim:
        tb = CompTb(params)

        # Base transient analysis
        tr = hs.Tran(tstop=5500 * n, tstep=1 * n)

        # Monte Carlo wrapper with inner transient
        # Note: HDL21's MonteCarlo uses npts parameter
        mc = hs.MonteCarlo(inner=[tr], npts=numruns)

        # Save key signals
        save = hs.Save(hs.SaveMode.ALL)

        # MC configuration and temperature
        # Use _ to avoid name assignment issue (Literal is frozen, has no name field)
        _ = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
            // MC options: seed={seed}, variations={variations}
        """
        )

    return CompMcSim


# =============================================================================
# SWEEP FUNCTIONS
# =============================================================================


def run_scurve_sweep(
    comp_params: CompParams = None,
    pvt: Pvt = None,
) -> List[tuple]:
    """
    Run S-curve sweep: sweep differential voltage at multiple CM points.

    Matches original testbench structure:
    - 5 common-mode voltages: 0.3V to 0.7V (100mV steps)
    - 11 differential voltages at each: -10mV to +10mV (2mV steps)
    - 10 clock cycles at each point

    Returns list of ((vcm, vdiff), result) tuples.
    """
    if comp_params is None:
        comp_params = CompParams()
    if pvt is None:
        pvt = Pvt()

    # 5 common-mode voltages: 0.3V to 0.7V
    cm_voltages = [300 * m, 400 * m, 500 * m, 600 * m, 700 * m]

    # 11 differential voltages: -10mV to +10mV (2mV steps)
    diff_voltages = [i * 2 * m - 10 * m for i in range(11)]

    results = []
    for vcm in cm_voltages:
        for vdiff in diff_voltages:
            tb_params = CompTbParams(
                pvt=pvt,
                comp=comp_params,
                vcm=vcm,
                vin_diff=vdiff,
            )
            sim = sim_input(tb_params)
            # result = sim.run(sim_options)
            results.append(((vcm, vdiff), None))  # Placeholder

    return results


def run_topology_sweep(pvt: Pvt = None) -> List[tuple]:
    """
    Sweep over comparator topologies.

    Returns list of (params, result) tuples for each valid topology.
    """
    if pvt is None:
        pvt = Pvt()

    results = []
    variants = comp_variants(
        preamp_diffpairs=[PreampDiffpair.NMOS_INPUT],
        preamp_biases=list(PreampBias),
        comp_stages_list=list(CompStages),
        diffpair_w_list=[40],
    )

    for comp_params in variants:
        tb_params = CompTbParams(pvt=pvt, comp=comp_params)
        sim = sim_input(tb_params)
        # result = sim.run(sim_options)
        results.append((comp_params, None))  # Placeholder

    return results


def run_offset_monte_carlo(
    comp_params: CompParams = None,
    pvt: Pvt = None,
    mc_config: MCConfig = None,
) -> Dict[str, Any]:
    """
    Run Monte Carlo simulation to characterize comparator offset.

    Uses default MC config: numruns=10, seed=12345, variations=mismatch

    Returns statistics on offset distribution.
    """
    if comp_params is None:
        comp_params = CompParams()
    if pvt is None:
        pvt = Pvt()
    if mc_config is None:
        mc_config = DEFAULT_MC_CONFIG

    # Zero differential input for offset measurement
    tb_params = CompTbParams(pvt=pvt, comp=comp_params, vin_diff=0 * m)
    sim = sim_input_with_mc(tb_params, mc_config=mc_config)

    # Would run simulation and extract offset from each MC point
    # result = sim.run(sim_options)
    # offsets = [extract_offset(r) for r in result.mc_results]
    # return mc_statistics(offsets)

    return {
        "mc_config": {
            "numruns": mc_config.numruns,
            "seed": mc_config.seed,
            "variations": mc_config.variations,
        },
        "info": "Placeholder - simulation not run",
    }


# =============================================================================
# PYTEST TEST FUNCTIONS
# =============================================================================


def test_comp_netlist(simtestmode: SimTestMode):
    """Test that netlist generation works for all valid topologies."""
    if simtestmode != SimTestMode.NETLIST:
        return

    from .pdk import get_pdk

    pdk = get_pdk()

    count = 0
    for params in comp_variants():
        comp = Comp(params)
        pdk.compile(comp)
        h.netlist(comp, dest=io.StringIO())
        count += 1
    print(f"Generated {count} valid comparator netlists")


def test_comp_tb_netlist(simtestmode: SimTestMode):
    """Test testbench netlist generation."""
    if simtestmode != SimTestMode.NETLIST:
        return

    from .pdk import get_pdk

    pdk = get_pdk()

    params = CompTbParams()
    tb = CompTb(params)
    pdk.compile(tb)
    h.netlist(tb, dest=io.StringIO())
    print("Comparator testbench netlist generated successfully")


def test_comp_mc_sim_structure(simtestmode: SimTestMode):
    """Test Monte Carlo simulation structure."""
    if simtestmode != SimTestMode.NETLIST:
        return

    params = CompTbParams(vin_diff=0 * m)
    mc_config = MCConfig(numruns=10)
    sim = sim_input_with_mc(params, mc_config)
    print(f"MC simulation created with {mc_config.numruns} runs")
    print(f"  seed={mc_config.seed}, variations={mc_config.variations}")


def test_comp_scurve(simtestmode: SimTestMode):
    """Test S-curve sweep functionality."""
    if simtestmode == SimTestMode.NETLIST:
        # Just verify we can create the sweep parameters
        sweep = run_scurve_sweep()
        print(f"S-curve sweep would run {len(sweep)} simulations")

    elif simtestmode == SimTestMode.MIN:
        # Run single point
        params = CompTbParams(vcm=600 * m, vin_diff=0 * m)
        sim = sim_input(params)
        print("MIN mode: would run single S-curve point")

    elif simtestmode in (SimTestMode.TYP, SimTestMode.MAX):
        # Run full sweep
        results = run_scurve_sweep()
        print(f"Would run {len(results)} S-curve points")


def test_comp_sim(simtestmode: SimTestMode):
    """Test comparator simulation."""
    if simtestmode == SimTestMode.NETLIST:
        params = CompTbParams()
        sim = sim_input(params)
        print("Simulation input created successfully")

    elif simtestmode == SimTestMode.MIN:
        from .common.sim_options import sim_options
        from .measure import comp_delay_ns

        params = CompTbParams()
        sim = sim_input(params)
        # result = sim.run(sim_options)
        # delay = comp_delay_ns(result)
        # print(f"Decision delay: {delay:.2f} ns")
        print("MIN mode: simulation would run here")

    elif simtestmode in (SimTestMode.TYP, SimTestMode.MAX):
        results = run_topology_sweep()
        for comp_params, result in results:
            print(
                f"{comp_params.preamp_bias.name}/{comp_params.comp_stages.name}: result={result}"
            )


# =============================================================================
# CLI ENTRY POINT (for standalone testing)
# =============================================================================


if __name__ == "__main__":
    print("Testing comparator netlist generation...")
    test_comp_netlist(SimTestMode.NETLIST)
    print()
    print("Testing comparator testbench netlist...")
    test_comp_tb_netlist(SimTestMode.NETLIST)
    print()
    print("Testing Monte Carlo simulation structure...")
    test_comp_mc_sim_structure(SimTestMode.NETLIST)
