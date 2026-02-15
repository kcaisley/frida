"""
Comparator testbench and flow tests for FRIDA.
"""

import hdl21 as h
import hdl21.sim as hs
import pytest
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, R, Vdc, Vpulse, Vpwl

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
    pwl_points_to_wave,
    run_netlist_variants,
    run_simulations,
    select_variants,
    wrap_monte_carlo,
)
from ..pdk import get_pdk
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

    @h.module
    class CompTb:
        """Comparator testbench module."""

        vss = h.Port(desc="Ground")

        # Power supplies
        vdd = h.Signal()

        # Differential input sources (driven by sim PWL)
        vin_p_src = h.Signal()
        vin_n_src = h.Signal()

        # Source impedances (models DAC/SHA output impedance)
        in_p = h.Signal()
        in_n = h.Signal()

        # Clocks
        clk = h.Signal()
        clk_b = h.Signal()

        # Outputs
        out_p = h.Signal()
        out_n = h.Signal()

    CompTb.vvdd = Vdc(dc=supply.VDD)(p=CompTb.vdd, n=CompTb.vss)

    CompTb.rsrc_p = R(r=1000)(p=CompTb.vin_p_src, n=CompTb.in_p)
    CompTb.rsrc_n = R(r=1000)(p=CompTb.vin_n_src, n=CompTb.in_n)
    CompTb.csrc_p = C(c=100 * f)(p=CompTb.in_p, n=CompTb.vss)
    CompTb.csrc_n = C(c=100 * f)(p=CompTb.in_n, n=CompTb.vss)

    # Clocks: 10ns period, 40% duty cycle (4ns high = evaluation phase)
    CompTb.vclk = Vpulse(
        v1=0 * m,
        v2=supply.VDD,
        period=10 * n,
        width=4 * n,
        rise=100 * p,
        fall=100 * p,
        delay=500 * p,
    )(p=CompTb.clk, n=CompTb.vss)
    CompTb.vclkb = Vpulse(
        v1=supply.VDD,
        v2=0 * m,
        period=10 * n,
        width=4 * n,
        rise=100 * p,
        fall=100 * p,
        delay=500 * p,
    )(p=CompTb.clk_b, n=CompTb.vss)

    # Output loading (10fF each)
    CompTb.cload_p = C(c=10 * f)(p=CompTb.out_p, n=CompTb.vss)
    CompTb.cload_n = C(c=10 * f)(p=CompTb.out_n, n=CompTb.vss)

    # DUT
    CompTb.dut = Comp(params.comp)(
        inp=CompTb.in_p,
        inn=CompTb.in_n,
        outp=CompTb.out_p,
        outn=CompTb.out_n,
        clk=CompTb.clk,
        clkb=CompTb.clk_b,
        vdd=CompTb.vdd,
        vss=CompTb.vss,
    )

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
    points_p, _ = _build_pwl_points(vin_p_values, t_step, t_rise)
    points_n, _ = _build_pwl_points(vin_n_values, t_step, t_rise)
    CompTb.vvin_p = Vpwl(wave=pwl_points_to_wave(points_p))(
        p=CompTb.vin_p_src, n=CompTb.vss
    )
    CompTb.vvin_n = Vpwl(wave=pwl_points_to_wave(points_n))(
        p=CompTb.vin_n_src, n=CompTb.vss
    )

    return CompTb


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

    t_step = 200 * n
    t_rise = 100 * p
    n_points = len(cm_voltages) * len(diff_voltages)
    t_stop = n_points * t_step + (n_points - 1) * t_rise

    @hs.sim
    class CompSim:
        tb = CompTb(params)
        tr = hs.Tran(tstop=t_stop, tstep=1 * n)

        save_all = hs.Save(hs.SaveMode.ALL)
        save = hs.Save(["xtop.clk", "xtop.out_p"])
        temp = hs.Options(name="temp", value=sim_temp)

    return CompSim


@pytest.mark.usefixtures("require_sim_for_flow")
def test_comp_flow(flow, mode, montecarlo, verbose, simulator, sim_options, sim_server):
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
        wall_time = run_netlist_variants(
            "comp", variants, build_sim, pdk, outdir, simulator=simulator
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
        return

    wall_time, sims = run_netlist_variants(
        "comp", variants, build_sim, pdk, outdir, return_sims=True, simulator=simulator
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

    if flow == "simulate":
        run_simulations(sims, sim_options, sim_server=sim_server)
    elif flow == "measure":
        pass
