"""
Sampler testbench and runner functions for FRIDA.
"""

from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosVth, Vdc, Vpulse

from ..circuit import (
    Project,
    Pvt,
    SupplyVals,
    get_param_axes,
    print_netlist_summary,
    run_netlist_variants,
    run_simulations,
    select_variants,
    wrap_monte_carlo,
)
from .subckt import Samp, SampParams, SwitchType


@h.paramclass
class SampTbParams:
    """Sampler testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    samp = h.Param(dtype=SampParams, desc="Sampler parameters", default=SampParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance", default=1 * f)


@h.generator
def SampTb(params: SampTbParams) -> h.Module:
    """
    Sampler testbench generator.

    Creates a testbench with:
    - DC supply voltage
    - Complementary clock pulses
    - DC input voltage
    - Load capacitor
    - DUT sampler instance
    """
    supply = SupplyVals.corner(params.pvt.v)

    @h.module
    class SampTb:
        """Sampler testbench module."""

        vss = h.Port(desc="Ground")

        # Supply
        vdd = h.Signal()

        # Clocks - complementary pulses
        clk = h.Signal()
        clk_b = h.Signal()

        # Input - mid-supply DC voltage
        din = h.Signal()

        # Output with load capacitor
        dout = h.Signal()

    SampTb.vvdd = Vdc(dc=supply.VDD)(p=SampTb.vdd, n=SampTb.vss)

    SampTb.vclk = Vpulse(
        v1=0 * m,
        v2=supply.VDD,
        period=100 * n,
        width=50 * n,
        rise=100 * p,
        fall=100 * p,
        delay=0 * n,
    )(p=SampTb.clk, n=SampTb.vss)
    SampTb.vclk_b = Vpulse(
        v1=supply.VDD,
        v2=0 * m,
        period=100 * n,
        width=50 * n,
        rise=100 * p,
        fall=100 * p,
        delay=0 * n,
    )(p=SampTb.clk_b, n=SampTb.vss)

    SampTb.vdin = Vdc(dc=supply.VDD / 2)(p=SampTb.din, n=SampTb.vss)
    SampTb.cload = C(c=params.cload)(p=SampTb.dout, n=SampTb.vss)

    SampTb.dut = Samp(params.samp)(
        din=SampTb.din,
        dout=SampTb.dout,
        clk=SampTb.clk,
        clk_b=SampTb.clk_b,
        vdd=SampTb.vdd,
        vss=SampTb.vss,
    )

    return SampTb


def sim_input(params: SampTbParams) -> hs.Sim:
    """Create simulation input for sampler characterization."""
    sim_temp = Project.temper(params.pvt.t)

    @hs.sim
    class SampSim:
        tb = SampTb(params)
        tr = hs.Tran(tstop=500 * n, tstep=100 * p)

        save_all = hs.Save(hs.SaveMode.ALL)
        save = hs.Save(["xtop.din", "xtop.dout"])

        temp = hs.Options(name="temp", value=sim_temp)

    return SampSim


def _build_variants():
    """Build the full sampler variant list."""
    return [
        SampParams(switch_type=st, mos_w=w, mos_l=l, mos_vth=vth)
        for st in SwitchType
        for vth in [MosVth.LOW, MosVth.STD]
        for w in [2, 5, 10, 20, 40]
        for l in [1]
    ]


def run_netlist(
    tech: str,
    mode: str,
    montecarlo: bool,
    fmt: str,
    outdir: Path,
    scope: str = "full",
    verbose: bool = False,
) -> None:
    """Run sampler netlist generation."""
    all_variants = _build_variants()
    variants = select_variants(all_variants, mode)

    def build_sim(samp_params: SampParams):
        tb_params = SampTbParams(samp=samp_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return SampTb(tb_params), sim

    def build_dut(samp_params: SampParams):
        return Samp(samp_params)

    wall_time = run_netlist_variants(
        "samp",
        variants,
        build_sim,
        outdir,
        simulator=fmt,
        fmt=fmt,
        scope=scope,
        build_dut=build_dut,
    )
    if verbose:
        print_netlist_summary(
            block="samp",
            pdk_name=tech,
            count=len(variants),
            total=len(all_variants),
            param_axes=get_param_axes(all_variants),
            wall_time=wall_time,
            outdir=str(outdir),
        )


def run_simulate(
    tech: str,
    mode: str,
    montecarlo: bool,
    simulator: str,
    sim_options,
    sim_server,
    outdir: Path,
    verbose: bool = False,
) -> None:
    """Run sampler simulation."""
    all_variants = _build_variants()
    variants = select_variants(all_variants, mode)

    def build_sim(samp_params: SampParams):
        tb_params = SampTbParams(samp=samp_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return SampTb(tb_params), sim

    wall_time, sims = run_netlist_variants(
        "samp",
        variants,
        build_sim,
        outdir,
        return_sims=True,
        simulator=simulator,
        scope="full",
    )
    if verbose:
        print_netlist_summary(
            block="samp",
            pdk_name=tech,
            count=len(variants),
            total=len(all_variants),
            param_axes=get_param_axes(all_variants),
            wall_time=wall_time,
            outdir=str(outdir),
        )
    run_simulations(sims, sim_options, sim_server=sim_server)
