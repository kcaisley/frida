"""
Comparator testbench and tests for FRIDA.

Includes testbench generator, simulation definitions, Monte Carlo support,
and pytest test functions.
"""

from typing import Any

import hdl21 as h
import pytest
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, R, Vdc, Vpulse

from ..flow import (
    MCConfig,
    Project,
    Pvt,
    FlowMode,
    SupplyVals,
    PreampBias,
    PreampDiffpair,
    CompStages,
    sim_options,
    write_sim_netlist,
    params_to_filename,
    params_to_tb_filename,
)
from ..pdk import get_pdk
from ..conftest import has_simulator, print_summary_if_verbose
from .comp import Comp, CompParams, comp_variants


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
    sim_temp = Project.temper(params.pvt.t)

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

        # Temperature setting using hs.Options
        temp = hs.Options(name="temp", value=sim_temp)

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
        mc_config = MCConfig()

    sim_temp = Project.temper(params.pvt.t)
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

        # Temperature setting using hs.Options
        temp = hs.Options(name="temp", value=sim_temp)

        # MC options as literal (Spectre-specific MC syntax)
        _ = hs.Literal(f"// MC options: seed={seed}, variations={variations}")

    return CompMcSim


# =============================================================================
# SWEEP FUNCTIONS
# =============================================================================


def run_scurve_sweep(
    comp_params: CompParams = None,
    pvt: Pvt = None,
) -> list[tuple]:
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
            # Simulation not executed - requires SPICE simulator with PDK
            sim = sim_input(tb_params)  # noqa: F841
            # result = sim.run(sim_options)
            results.append(((vcm, vdiff), None))  # Placeholder

    return results


def run_topology_sweep(pvt: Pvt = None) -> list[tuple]:
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
        # Simulation not executed - requires SPICE simulator with PDK
        sim = sim_input(tb_params)  # noqa: F841
        # result = sim.run(sim_options)
        results.append((comp_params, None))  # Placeholder

    return results


def run_offset_monte_carlo(
    comp_params: CompParams = None,
    pvt: Pvt = None,
    mc_config: MCConfig = None,
) -> dict[str, Any]:
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
        mc_config = MCConfig()

    # Zero differential input for offset measurement
    tb_params = CompTbParams(pvt=pvt, comp=comp_params, vin_diff=0 * m)
    # TODO: run MC simulation and extract offsets
    sim = sim_input_with_mc(tb_params, mc_config=mc_config)  # noqa: F841

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


def test_comp_netlist(flowmode: FlowMode, request):
    """Test that netlist generation works for all valid topologies."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()
    variants = list(comp_variants())

    for params in variants:
        comp = Comp(params)
        pdk.compile(comp)
        # Write netlist with consistent naming
        filename = params_to_filename("comp", params, pdk.name)
        netlist_path = outdir / filename
        with open(netlist_path, "w") as f:
            h.netlist(comp, dest=f)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="comp",
        count=len(variants),
        params_list=variants,
        wall_time=wall_time,
        outdir=outdir,
    )


def test_comp_tb_netlist(flowmode: FlowMode, request):
    """Test testbench netlist generation."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()

    params = CompTbParams()
    tb = CompTb(params)
    pdk.compile(tb)

    # Write testbench netlist with consistent naming
    tb_filename = params_to_tb_filename("comp", params, pdk.name, suffix=".sp")
    netlist_path = outdir / tb_filename
    with open(netlist_path, "w") as f:
        h.netlist(tb, dest=f)

    # Also write simulation netlist (same path as actual simulation)
    sim = sim_input(params)
    sim_filename = params_to_tb_filename("comp", params, pdk.name, suffix=".scs")
    sim_netlist_path = outdir / sim_filename
    write_sim_netlist(sim, sim_netlist_path, compact=True)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="comp_tb",
        count=2,  # .sp and .scs
        params_list=[params.comp],  # Use inner comp params for axes
        wall_time=wall_time,
        outdir=outdir,
    )


def test_comp_mc_sim_structure(flowmode: FlowMode):
    """Test Monte Carlo simulation structure."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    params = CompTbParams(vin_diff=0 * m)
    mc_config = MCConfig(numruns=10)
    # TODO: run MC simulation
    sim = sim_input_with_mc(params, mc_config)  # noqa: F841
    print(f"MC simulation created with {mc_config.numruns} runs")
    print(f"  seed={mc_config.seed}, variations={mc_config.variations}")


def test_comp_scurve(flowmode: FlowMode):
    """Test S-curve sweep functionality."""
    if flowmode == FlowMode.NETLIST:
        # Just verify we can create the sweep parameters
        sweep = run_scurve_sweep()
        print(f"S-curve sweep would run {len(sweep)} simulations")
        pytest.skip("Simulation requires --mode=min/typ/max")

    elif flowmode == FlowMode.MIN:
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
        # Run single point
        params = CompTbParams(vcm=600 * m, vin_diff=0 * m)
        # Simulation not executed - requires SPICE simulator with PDK
        sim = sim_input(params)  # noqa: F841
        print("MIN mode: would run single S-curve point")

    elif flowmode in (FlowMode.TYP, FlowMode.MAX):
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
        # Run full sweep
        results = run_scurve_sweep()
        print(f"Would run {len(results)} S-curve points")


def test_comp_sim(flowmode: FlowMode):
    """Test comparator simulation."""
    if flowmode == FlowMode.NETLIST:
        params = CompTbParams()
        sim = sim_input(params)
        assert sim is not None
        pytest.skip("Simulation requires --mode=min/typ/max")

    elif flowmode == FlowMode.MIN:
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
        params = CompTbParams()
        # Simulation not executed - requires SPICE simulator with PDK
        sim = sim_input(params)  # noqa: F841
        # result = sim.run(sim_options)
        # delay = comp_delay_ns(result)
        # print(f"Decision delay: {delay:.2f} ns")
        print("MIN mode: simulation would run here")

    elif flowmode in (FlowMode.TYP, FlowMode.MAX):
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
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
    test_comp_netlist(FlowMode.NETLIST)
    print()
    print("Testing comparator testbench netlist...")
    test_comp_tb_netlist(FlowMode.NETLIST)
    print()
    print("Testing Monte Carlo simulation structure...")
    test_comp_mc_sim_structure(FlowMode.NETLIST)
