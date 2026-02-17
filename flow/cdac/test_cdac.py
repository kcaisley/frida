"""
CDAC testbench and flow tests for FRIDA.
"""

import hdl21 as h
import hdl21.sim as hs
import pytest
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosVth, Vdc, Vpwl

from ..flow import (
    CapType,
    Project,
    Pvt,
    RedunStrat,
    SplitStrat,
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
from .cdac import (
    Cdac,
    CdacParams,
    get_cdac_n_bits,
    get_cdac_weights,
    is_valid_cdac_params,
)


@h.paramclass
class CdacTbParams:
    """CDAC testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    cdac = h.Param(dtype=CdacParams, desc="CDAC parameters", default=CdacParams())


@h.generator
def CdacTb(params: CdacTbParams) -> h.Module:
    """
    CDAC testbench generator.

    Creates a testbench with:
    - DC supply
    - DAC code inputs (driven by sim PWL)
    - Load capacitor on output
    """
    supply = SupplyVals.corner(params.pvt.v)
    n_bits = get_cdac_n_bits(params.cdac)

    @h.module
    class CdacTb:
        """CDAC testbench module."""

        vss = h.Port(desc="Ground")

        # Supply
        vdd = h.Signal()

        # DAC output with load
        top = h.Signal()

        # DAC code inputs (driven by sim PWL)
        dac_bits = h.Signal(width=n_bits)

    CdacTb.vvdd = Vdc(dc=supply.VDD)(p=CdacTb.vdd, n=CdacTb.vss)
    CdacTb.cload = C(c=100 * f)(p=CdacTb.top, n=CdacTb.vss)

    CdacTb.dut = Cdac(params.cdac)(
        top=CdacTb.top,
        dac=CdacTb.dac_bits,
        vdd=CdacTb.vdd,
        vss=CdacTb.vss,
    )

    n_codes = 2**params.cdac.n_dac
    codes = list(range(n_codes))
    bit_values: list[list[h.Scalar]] = [[] for _ in range(n_bits)]
    for code in codes:
        for bit in range(n_bits):
            bit_is_set = (code >> bit) & 1
            bit_values[bit].append(supply.VDD if bit_is_set else 0 * m)

    t_step = 200 * n
    t_rise = 100 * p
    for bit in range(n_bits):
        points, _ = _build_pwl_points(bit_values[bit], t_step, t_rise)
        wave = pwl_points_to_wave(points)
        setattr(
            CdacTb,
            f"vdac_{bit}",
            Vpwl(wave=wave)(p=CdacTb.dac_bits[bit], n=CdacTb.vss),
        )

    return CdacTb


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


def sim_input(params: CdacTbParams) -> hs.Sim:
    """Create transient simulation with stepped DAC codes."""
    sim_temp = Project.temper(params.pvt.t)

    n_codes = 2**params.cdac.n_dac

    t_step = 200 * n
    t_rise = 100 * p
    t_stop = n_codes * t_step + (n_codes - 1) * t_rise

    @hs.sim
    class CdacSim:
        tb = CdacTb(params)
        tr = hs.Tran(tstop=t_stop, tstep=100 * p)
        save = hs.Save(hs.SaveMode.ALL)
        temp = hs.Options(name="temp", value=sim_temp)

    return CdacSim


def test_cdac_weights():
    """Test weight calculation for different strategies."""
    print("CDAC Weight Calculations:")

    params = CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2)
    weights = get_cdac_weights(params)
    print(f"  RDX2 (8-bit): {weights}")

    params = CdacParams(n_dac=8, n_extra=2, redun_strat=RedunStrat.SUBRDX2_LIM)
    weights = get_cdac_weights(params)
    print(f"  SUBRDX2_LIM (8+2): {weights}")


@pytest.mark.usefixtures("require_sim_for_flow")
def test_cdac_flow(
    flow,
    mode,
    montecarlo,
    verbose,
    simulator,
    netlist_fmt,
    sim_options,
    sim_server,
):
    """Run CDAC flow: netlist, simulate, or measure."""
    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    n_dac_list = [7, 9, 11]
    n_extra_list = [0, 2, 4]
    redun_strats = list(RedunStrat)
    split_strats = list(SplitStrat)
    cap_types = list(CapType)
    vth_list = [MosVth.LOW, MosVth.STD]
    unit_caps = [1 * f]

    variants: list[CdacParams] = []

    for n_dac in n_dac_list:
        for n_extra in n_extra_list:
            for redun_strat in redun_strats:
                for split_strat in split_strats:
                    for cap_type in cap_types:
                        for vth in vth_list:
                            for unit_cap in unit_caps:
                                params = CdacParams(
                                    n_dac=n_dac,
                                    n_extra=n_extra,
                                    redun_strat=redun_strat,
                                    split_strat=split_strat,
                                    cap_type=cap_type,
                                    vth=vth,
                                    unit_cap=unit_cap,
                                )
                                if is_valid_cdac_params(params):
                                    variants.append(params)

    variants = select_variants(variants, mode)

    def build_sim(cdac_params: CdacParams):
        tb_params = CdacTbParams(cdac=cdac_params)
        tb = CdacTb(tb_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return tb, sim

    def build_dut(cdac_params: CdacParams):
        return Cdac(cdac_params)

    if flow == "netlist":
        wall_time = run_netlist_variants(
            "cdac",
            variants,
            build_sim,
            pdk,
            outdir,
            simulator=simulator,
            netlist_fmt=netlist_fmt,
            build_dut=build_dut,
        )
        if verbose:
            print_netlist_summary(
                block="cdac",
                pdk_name=pdk.name,
                count=len(variants),
                param_axes=get_param_axes(variants),
                wall_time=wall_time,
                outdir=str(outdir),
            )
        return

    wall_time, sims = run_netlist_variants(
        "cdac", variants, build_sim, pdk, outdir, return_sims=True, simulator=simulator
    )
    if verbose:
        print_netlist_summary(
            block="cdac",
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
