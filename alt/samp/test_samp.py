"""
Sampler testbench and flow tests for FRIDA.
"""

import hdl21 as h
import pytest
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosVth, Vdc, Vpulse

from ..flow import (
    Project,
    Pvt,
    SupplyVals,
    SwitchType,
    get_param_axes,
    print_netlist_summary,
    run_netlist_variants,
    select_variants,
    sim_options,
    wrap_monte_carlo,
)
from ..pdk import get_pdk
from ..conftest import has_simulator
from .samp import Samp, SampParams


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

    tb = h.sim.tb("SampTb")

    # Supply
    tb.vdd = h.Signal()
    tb.vvdd = Vdc(dc=supply.VDD)(p=tb.vdd, n=tb.VSS)

    # Clocks - complementary pulses
    tb.clk = h.Signal()
    tb.clk_b = h.Signal()
    tb.vclk = Vpulse(
        v1=0 * m,
        v2=supply.VDD,
        period=100 * n,
        width=50 * n,
        rise=100 * p,
        fall=100 * p,
        delay=0 * n,
    )(p=tb.clk, n=tb.VSS)
    tb.vclk_b = Vpulse(
        v1=supply.VDD,
        v2=0 * m,
        period=100 * n,
        width=50 * n,
        rise=100 * p,
        fall=100 * p,
        delay=0 * n,
    )(p=tb.clk_b, n=tb.VSS)

    # Input - mid-supply DC voltage
    tb.din = h.Signal()
    tb.vdin = Vdc(dc=supply.VDD / 2)(p=tb.din, n=tb.VSS)

    # Output with load capacitor
    tb.dout = h.Signal()
    tb.cload = C(c=params.cload)(p=tb.dout, n=tb.VSS)

    # DUT
    tb.dut = Samp(params.samp)(
        din=tb.din,
        dout=tb.dout,
        clk=tb.clk,
        clk_b=tb.clk_b,
        vdd=tb.vdd,
        vss=tb.VSS,
    )

    return tb


def sim_input(params: SampTbParams) -> hs.Sim:
    """Create simulation input for sampler characterization."""
    sim_temp = Project.temper(params.pvt.t)

    @hs.sim
    class SampSim:
        tb = SampTb(params)
        tr = hs.Tran(tstop=500 * n, tstep=100 * p)

        t_settle = hs.Meas(
            analysis=tr,
            expr="when V(xtop.dout)=0.99*V(xtop.din) rise=1",
        )

        temp = hs.Options(name="temp", value=sim_temp)

    return SampSim


def test_samp_flow(flow, mode, montecarlo, verbose):
    """Run sampler flow: netlist, simulate, or measure."""
    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    switch_types = list(SwitchType)
    vth_list = [MosVth.LOW, MosVth.STD]
    w_list = [2, 5, 10, 20, 40]
    l_list = [1]

    variants = [
        SampParams(switch_type=st, w=w, l=l, vth=vth)
        for st in switch_types
        for vth in vth_list
        for w in w_list
        for l in l_list
    ]

    variants = select_variants(variants, mode)

    def build_sim(samp_params: SampParams):
        tb_params = SampTbParams(samp=samp_params)
        tb = SampTb(tb_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return tb, sim

    if flow == "netlist":
        wall_time = run_netlist_variants("samp", variants, build_sim, pdk, outdir)
        if verbose:
            print_netlist_summary(
                block="samp",
                pdk_name=pdk.name,
                count=len(variants),
                param_axes=get_param_axes(variants),
                wall_time=wall_time,
                outdir=str(outdir),
            )
        return

    wall_time, sims = run_netlist_variants(
        "samp", variants, build_sim, pdk, outdir, return_sims=True
    )
    if verbose:
        print_netlist_summary(
            block="samp",
            pdk_name=pdk.name,
            count=len(variants),
            param_axes=get_param_axes(variants),
            wall_time=wall_time,
            outdir=str(outdir),
        )

    if not has_simulator():
        pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")

    if flow == "simulate":
        h.sim.run(sims, sim_options)
    elif flow == "measure":
        pass
