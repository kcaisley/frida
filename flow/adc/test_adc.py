"""
ADC testbench and flow tests for FRIDA.
"""

import hdl21 as h
import hdl21.sim as hs
import pytest
from hdl21.prefix import f, m, n, p
from hdl21.primitives import Vdc

from ..cdac import CdacParams
from ..comp import CompParams
from ..flow import (
    Project,
    Pvt,
    SupplyVals,
    generate_staircase_pwl,
    get_param_axes,
    print_netlist_summary,
    pwl_to_spice_literal,
    run_netlist_variants,
    select_variants,
    wrap_monte_carlo,
)
from ..pdk import get_pdk
from ..samp import SampParams
from .adc import Adc, AdcParams, get_adc_weights


@h.paramclass
class AdcTbParams:
    """ADC testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    adc = h.Param(dtype=AdcParams, desc="ADC parameters", default=AdcParams())

    # Input voltage sweep (staircase PWL)
    v_start = h.Param(dtype=h.Scalar, desc="Starting input voltage", default=0 * m)
    v_stop = h.Param(dtype=h.Scalar, desc="Ending input voltage", default=1200 * m)
    v_step = h.Param(dtype=h.Scalar, desc="Voltage step size", default=1 * m)
    t_step = h.Param(dtype=h.Scalar, desc="Duration per step", default=200 * n)
    t_rise = h.Param(dtype=h.Scalar, desc="Rise time between steps", default=100 * p)

    # Common mode voltage
    vcm = h.Param(dtype=h.Scalar, desc="Common-mode voltage", default=600 * m)


@h.generator
def AdcTb(p: AdcTbParams) -> h.Module:
    """
    ADC testbench generator.

    Creates a testbench with:
    - Staircase PWL input for transfer function characterization
    - Supply sources
    """
    supplies = SupplyVals.corner(p.pvt.v)

    @h.module
    class AdcTb:
        vss = h.Port(desc="Ground")

        vdd_a = h.Signal(desc="Analog supply")
        vdd_d = h.Signal(desc="Digital supply")
        vin_p = h.Signal(desc="Input positive")
        vin_n = h.Signal(desc="Input negative")
        vcm = h.Signal(desc="Common mode")

        seq_init = h.Signal()
        seq_samp = h.Signal()
        seq_comp = h.Signal()
        seq_update = h.Signal()

        en_init = h.Signal()
        en_samp_p = h.Signal()
        en_samp_n = h.Signal()
        en_comp = h.Signal()
        en_update = h.Signal()

        dac_mode = h.Signal()
        dac_diffcaps = h.Signal()

        dac_astate_p = h.Signal(width=16)
        dac_bstate_p = h.Signal(width=16)
        dac_astate_n = h.Signal(width=16)
        dac_bstate_n = h.Signal(width=16)

        dac_state_p = h.Signal(width=16)
        dac_state_n = h.Signal(width=16)

    AdcTb.vvdd_a = Vdc(dc=supplies.VDD)(p=AdcTb.vdd_a, n=AdcTb.vss)
    AdcTb.vvdd_d = Vdc(dc=supplies.VDD)(p=AdcTb.vdd_d, n=AdcTb.vss)

    AdcTb.xadc = Adc(p.adc)(
        vin_p=AdcTb.vin_p,
        vin_n=AdcTb.vin_n,
        seq_init=AdcTb.seq_init,
        seq_samp=AdcTb.seq_samp,
        seq_comp=AdcTb.seq_comp,
        seq_update=AdcTb.seq_update,
        en_init=AdcTb.en_init,
        en_samp_p=AdcTb.en_samp_p,
        en_samp_n=AdcTb.en_samp_n,
        en_comp=AdcTb.en_comp,
        en_update=AdcTb.en_update,
        dac_mode=AdcTb.dac_mode,
        dac_diffcaps=AdcTb.dac_diffcaps,
        dac_astate_p=AdcTb.dac_astate_p,
        dac_bstate_p=AdcTb.dac_bstate_p,
        dac_astate_n=AdcTb.dac_astate_n,
        dac_bstate_n=AdcTb.dac_bstate_n,
        dac_state_p=AdcTb.dac_state_p,
        dac_state_n=AdcTb.dac_state_n,
        vdd_a=AdcTb.vdd_a,
        vss_a=AdcTb.vss,
        vdd_d=AdcTb.vdd_d,
        vss_d=AdcTb.vss,
    )

    return AdcTb


def sim_input(params: AdcTbParams) -> hs.Sim:
    """Create transient simulation with stepped input."""
    sim_temp = Project.temper(params.pvt.t)

    points = generate_staircase_pwl(
        v_start=float(params.v_start),
        v_stop=float(params.v_stop),
        v_step=float(params.v_step),
        t_step=float(params.t_step),
        t_rise=float(params.t_rise),
    )
    t_stop = points[-1][0] + float(params.t_step)

    vin_p = pwl_to_spice_literal("vinp", "xtop.vin_p", "xtop.vss", points)
    vin_n = pwl_to_spice_literal(
        "vinn",
        "xtop.vin_n",
        "xtop.vss",
        [(0.0, float(params.vcm)), (t_stop, float(params.vcm))],
    )

    @hs.sim
    class AdcSim:
        tb = AdcTb(params)
        tr = hs.Tran(tstop=t_stop, tstep=100 * p)
        temp = hs.Options(name="temp", value=sim_temp)

    AdcSim.add(hs.Literal(vin_p), hs.Literal(vin_n))

    return AdcSim


def test_adc_weights():
    """Test ADC weight calculation with SUBRDX2_OVLY strategy."""
    import numpy as np

    params = AdcParams()
    weights = get_adc_weights(params)

    assert len(weights) == 16
    assert weights.sum() == 2047
    assert weights[0] == 768

    expected = np.array([768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1])
    np.testing.assert_array_equal(weights, expected)


@pytest.mark.usefixtures("require_sim_for_flow")
def test_adc_flow(flow, mode, montecarlo, verbose, simulator, sim_options):
    """Run ADC flow: netlist, simulate, or measure."""
    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    n_cycles_list = [16]
    cdac_list = [
        CdacParams(n_dac=11, n_extra=5, unit_cap=1 * f),
        CdacParams(n_dac=11, n_extra=5, unit_cap=2 * f),
    ]
    samp_list = [SampParams()]
    comp_list = [CompParams()]

    variants: list[AdcParams] = []
    for n_cycles in n_cycles_list:
        for cdac in cdac_list:
            for samp in samp_list:
                for comp in comp_list:
                    variants.append(
                        AdcParams(
                            n_cycles=n_cycles,
                            cdac=cdac,
                            samp=samp,
                            comp=comp,
                        )
                    )

    variants = select_variants(variants, mode)

    def build_sim(adc_params: AdcParams):
        tb_params = AdcTbParams(adc=adc_params)
        tb = AdcTb(tb_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return tb, sim

    if flow == "netlist":
        wall_time = run_netlist_variants(
            "adc", variants, build_sim, pdk, outdir, simulator=simulator
        )
        if verbose:
            print_netlist_summary(
                block="adc",
                pdk_name=pdk.name,
                count=len(variants),
                param_axes=get_param_axes(variants),
                wall_time=wall_time,
                outdir=str(outdir),
            )
        return

    wall_time, sims = run_netlist_variants(
        "adc", variants, build_sim, pdk, outdir, return_sims=True, simulator=simulator
    )
    if verbose:
        print_netlist_summary(
            block="adc",
            pdk_name=pdk.name,
            count=len(variants),
            param_axes=get_param_axes(variants),
            wall_time=wall_time,
            outdir=str(outdir),
        )

    if flow == "simulate":
        h.sim.run(sims, sim_options)
    elif flow == "measure":
        pass
