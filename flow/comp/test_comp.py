"""
Comparator testbench and flow tests for FRIDA.
"""

import hdl21 as h
import pytest
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, R, Vdc, Vpulse

from ..flow import (
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
    get_param_axes,
    print_netlist_summary,
    pwl_to_spice_literal,
    run_netlist_variants,
    select_variants,
    sim_options,
    wrap_monte_carlo,
)
from ..pdk import get_pdk
from ..conftest import has_simulator
from .comp import Comp, CompParams, is_valid_comp_params


@h.paramclass
class CompTbParams:
    """Comparator testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())


@h.generator
def CompTb(params: CompTbParams) -> h.Module:
    """
    Comparator testbench generator.

    Creates a testbench with:
    - DC supplies
    - Symmetric differential inputs around CM (driven by sim PWL)
    - Source impedances (1kOhm + 100fF)
    - 10ns clock period, 40% duty cycle
    - 10fF output loading
    """
    supply = SupplyVals.corner(params.pvt.v)

    tb = h.sim.tb("CompTb")

    # Power supplies
    tb.vdd = h.Signal()
    tb.vvdd = Vdc(dc=supply.VDD)(p=tb.vdd, n=tb.VSS)

    # Differential input sources (driven by sim PWL)
    tb.vin_src = h.Signal()
    tb.vref_src = h.Signal()

    # Source impedances (models DAC/SHA output impedance)
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


def _build_pwl_points(
    values: list[h.Scalar],
    t_step: h.Scalar,
    t_rise: h.Scalar,
    t_delay: h.Scalar = 0 * n,
) -> tuple[list[tuple[float, float]], float]:
    points: list[tuple[float, float]] = []
    t = float(t_delay)
    step = float(t_step)
    rise = float(t_rise)

    for i, value in enumerate(values):
        points.append((t, float(value)))
        t += step
        if i < len(values) - 1:
            points.append((t, float(value)))
            t += rise

    return points, t


def sim_input(params: CompTbParams) -> hs.Sim:
    """Create transient simulation with stepped vcm/vdiff inputs."""
    sim_temp = Project.temper(params.pvt.t)

    # S-curve sweep definition
    cm_voltages = [300 * m, 400 * m, 500 * m, 600 * m, 700 * m]
    diff_voltages = [i * 2 * m - 10 * m for i in range(11)]

    vin_p_values: list[h.Scalar] = []
    vin_n_values: list[h.Scalar] = []

    for vcm in cm_voltages:
        for vdiff in diff_voltages:
            vin_p_values.append(vcm + vdiff / 2)
            vin_n_values.append(vcm - vdiff / 2)

    t_step = 200 * n
    t_rise = 100 * p
    points_p, t_stop = _build_pwl_points(vin_p_values, t_step, t_rise)
    points_n, _ = _build_pwl_points(vin_n_values, t_step, t_rise)

    pwl_p = pwl_to_spice_literal("vinp", "xtop.vin_src", "xtop.VSS", points_p)
    pwl_n = pwl_to_spice_literal("vinn", "xtop.vref_src", "xtop.VSS", points_n)

    @hs.sim
    class CompSim:
        tb = CompTb(params)
        tr = hs.Tran(tstop=t_stop, tstep=1 * n)

        t_delay = hs.Meas(
            analysis=tr,
            expr="trig V(xtop.clk) val=0.6 rise=1 targ V(xtop.outp) val=0.6 rise=1",
        )

        save = hs.Save(hs.SaveMode.ALL)
        temp = hs.Options(name="temp", value=sim_temp)

    CompSim.add(hs.Literal(pwl_p), hs.Literal(pwl_n))

    return CompSim


def test_comp_flow(flow, mode, montecarlo, verbose):
    """Run comparator flow: netlist, simulate, or measure."""
    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    preamp_diffpairs = list(PreampDiffpair)
    preamp_biases = list(PreampBias)
    comp_stages_list = list(CompStages)
    diffpair_w_list = [40, 80]

    variants: list[CompParams] = []

    for preamp_diffpair in preamp_diffpairs:
        for preamp_bias in preamp_biases:
            for comp_stages in comp_stages_list:
                for diffpair_w in diffpair_w_list:
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
                        if is_valid_comp_params(params):
                            variants.append(params)
                    else:
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

    variants = select_variants(variants, mode)

    def build_sim(comp_params: CompParams):
        tb_params = CompTbParams(comp=comp_params)
        tb = CompTb(tb_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return tb, sim

    if flow == "netlist":
        wall_time = run_netlist_variants("comp", variants, build_sim, pdk, outdir)
        if verbose:
            print_netlist_summary(
                block="comp",
                pdk_name=pdk.name,
                count=len(variants),
                param_axes=get_param_axes(variants),
                wall_time=wall_time,
                outdir=str(outdir),
            )
        return

    wall_time, sims = run_netlist_variants(
        "comp", variants, build_sim, pdk, outdir, return_sims=True
    )
    if verbose:
        print_netlist_summary(
            block="comp",
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
