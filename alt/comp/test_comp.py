"""
Comparator testbench and tests for FRIDA.

Includes testbench generator, simulation definitions, Monte Carlo support,
and pytest test functions.
"""

import io
from typing import Any

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, R, Vdc, Vpulse

from ..flow import (
    DEFAULT_MC_CONFIG,
    MCConfig,
    Project,
    Pvt,
    SimTestMode,
    SupplyVals,
    PreampBias,
    PreampDiffpair,
    CompStages,
    sim_options,
    write_sim_netlist,
)
from ..pdk import get_pdk
from .comp import Comp, CompParams, comp_variants, is_valid_comp_params


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
        mc_config = DEFAULT_MC_CONFIG

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
            sim = sim_input(tb_params)
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
        sim = sim_input(tb_params)
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

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    count = 0
    for params in comp_variants():
        comp = Comp(params)
        pdk.compile(comp)
        # Write netlist to scratch directory
        netlist_path = outdir / f"comp_{count}.sp"
        with open(netlist_path, "w") as f:
            h.netlist(comp, dest=f)
        count += 1
    print(f"Generated {count} comparator netlists in {outdir}/")


def test_comp_tb_netlist(simtestmode: SimTestMode):
    """Test testbench netlist generation."""
    if simtestmode != SimTestMode.NETLIST:
        return

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    params = CompTbParams()
    tb = CompTb(params)
    pdk.compile(tb)
    netlist_path = outdir / "comp_tb.sp"
    with open(netlist_path, "w") as f:
        h.netlist(tb, dest=f)
    print(f"Comparator testbench netlist: {netlist_path}")

    # Also write simulation netlist (same path as actual simulation)
    sim = sim_input(params)
    sim_netlist_path = outdir / "comp_tb.scs"
    write_sim_netlist(sim, sim_netlist_path, compact=True)
    print(f"Comparator simulation netlist: {sim_netlist_path}")


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
