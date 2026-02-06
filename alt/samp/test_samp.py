"""
Sampler testbench and tests for FRIDA.

Includes testbench generator, simulation definitions, and pytest test functions.
"""

import hdl21 as h
import pytest
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosVth, Vdc, Vpulse

from ..flow import (
    Project,
    Pvt,
    FlowMode,
    SupplyVals,
    SwitchType,
    sim_options,
    write_sim_netlist,
    params_to_filename,
    params_to_tb_filename,
)
from ..pdk import get_pdk
from ..conftest import has_simulator, print_summary_if_verbose
from .samp import Samp, SampParams, samp_variants


# =============================================================================
# TESTBENCH
# =============================================================================


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
    # Get supply voltage from PVT corner
    supply = SupplyVals.corner(params.pvt.v)

    # Create testbench module
    tb = h.sim.tb("SampTb")

    # Supply
    tb.vdd = h.Signal()
    tb.vvdd = Vdc(dc=supply.VDD)(p=tb.vdd, n=tb.VSS)

    # Clocks - complementary pulses
    tb.clk = h.Signal()
    tb.clk_b = h.Signal()

    # Clock high when sampling (first half of period)
    tb.vclk = Vpulse(
        v1=0 * m,
        v2=supply.VDD,
        period=100 * n,
        width=50 * n,
        rise=100 * p,
        fall=100 * p,
        delay=0 * n,
    )(p=tb.clk, n=tb.VSS)

    # Complementary clock
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


# =============================================================================
# SIMULATION DEFINITIONS
# =============================================================================


def sim_input(params: SampTbParams) -> hs.Sim:
    """
    Create simulation input for sampler characterization.

    Includes transient analysis and measurements for:
    - On-resistance (Ron)
    - Settling time
    - Charge injection
    """
    # Get temperature from PVT
    sim_temp = Project.temper(params.pvt.t)

    @hs.sim
    class SampSim:
        # Testbench
        tb = SampTb(params)

        # Transient analysis
        tr = hs.Tran(tstop=500 * n, tstep=100 * p)

        # Measurements
        # Settling time: when output reaches 99% of final value
        t_settle = hs.Meas(
            analysis=tr,
            expr="when V(xtop.dout)=0.99*V(xtop.din) rise=1",
        )

        # Temperature setting using hs.Options
        temp = hs.Options(name="temp", value=sim_temp)

    return SampSim


# =============================================================================
# SWEEP FUNCTIONS
# =============================================================================


def run_switch_type_sweep(pvt: Pvt = None) -> list[tuple]:
    """
    Sweep over switch types at given PVT conditions.

    Returns list of (switch_type, vth, settling_time) tuples.
    """
    if pvt is None:
        pvt = Pvt()

    results = []
    for switch_type in SwitchType:
        for vth in [MosVth.LOW, MosVth.STD]:
            samp_params = SampParams(switch_type=switch_type, w=10, l=1, vth=vth)
            tb_params = SampTbParams(pvt=pvt, samp=samp_params)
            # Simulation not executed - requires SPICE simulator with PDK
            sim = sim_input(tb_params)  # noqa: F841
            # result = sim.run(sim_options)
            # settling = samp_settling_ns(result)
            results.append((switch_type, vth, None))  # Placeholder

    return results


def run_width_sweep(
    pvt: Pvt = None,
    switch_type: SwitchType = SwitchType.NMOS,
) -> list[tuple]:
    """
    Sweep over device widths for a given switch type.

    Returns list of (width, settling_time) tuples.
    """
    if pvt is None:
        pvt = Pvt()

    width_list = [2, 5, 10, 20, 40]
    results = []

    for width in width_list:
        samp_params = SampParams(switch_type=switch_type, w=width, l=1)
        tb_params = SampTbParams(pvt=pvt, samp=samp_params)
        # Simulation not executed - requires SPICE simulator with PDK
        sim = sim_input(tb_params)  # noqa: F841
        # result = sim.run(sim_options)
        results.append((width, None))  # Placeholder

    return results


# =============================================================================
# PYTEST TEST FUNCTIONS
# =============================================================================


def test_samp_netlist(flowmode: FlowMode, request):
    """Test sampler netlist generation for all topologies."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()
    variants = []

    for switch_type in SwitchType:
        for vth in [MosVth.LOW, MosVth.STD]:
            params = SampParams(switch_type=switch_type, vth=vth)
            variants.append(params)
            samp = Samp(params)
            pdk.compile(samp)
            # Write netlist with consistent naming
            filename = params_to_filename("samp", params, pdk.name)
            netlist_path = outdir / filename
            with open(netlist_path, "w") as f:
                h.netlist(samp, dest=f)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="samp",
        count=len(variants),
        params_list=variants,
        wall_time=wall_time,
        outdir=outdir,
    )


def test_samp_tb_netlist(flowmode: FlowMode, request):
    """Test testbench netlist generation."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()

    params = SampTbParams()
    tb = SampTb(params)
    pdk.compile(tb)

    # Write testbench netlist with consistent naming
    tb_filename = params_to_tb_filename("samp", params, pdk.name, suffix=".sp")
    netlist_path = outdir / tb_filename
    with open(netlist_path, "w") as f:
        h.netlist(tb, dest=f)

    # Also write simulation netlist (same path as actual simulation)
    sim = sim_input(params)
    sim_filename = params_to_tb_filename("samp", params, pdk.name, suffix=".scs")
    sim_netlist_path = outdir / sim_filename
    write_sim_netlist(sim, sim_netlist_path, compact=True)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="samp_tb",
        count=2,  # .sp and .scs
        params_list=[params.samp],  # Use inner samp params for axes
        wall_time=wall_time,
        outdir=outdir,
    )


def test_samp_variants(flowmode: FlowMode, request):
    """Test variant generation."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()
    variants = samp_variants()

    # Generate netlists for first 5 variants
    generated_variants = variants[:5]
    for params in generated_variants:
        samp = Samp(params)
        pdk.compile(samp)
        # Write netlist with consistent naming
        filename = params_to_filename("samp", params, pdk.name)
        netlist_path = outdir / filename
        with open(netlist_path, "w") as f:
            h.netlist(samp, dest=f)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="samp_variants",
        count=len(generated_variants),
        params_list=generated_variants,
        wall_time=wall_time,
        outdir=outdir,
    )


def test_samp_sim(flowmode: FlowMode):
    """Test sampler simulation."""
    if flowmode == FlowMode.NETLIST:
        # Just verify sim input can be created
        params = SampTbParams()
        sim = sim_input(params)
        assert sim is not None
        pytest.skip("Simulation requires --mode=min/typ/max")

    elif flowmode == FlowMode.MIN:
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
        # Run one quick simulation
        params = SampTbParams(samp=SampParams(switch_type=SwitchType.TGATE))
        # TODO: run simulation and measure settling
        sim = sim_input(params)  # noqa: F841
        # result = sim.run(sim_options)
        # settling = samp_settling_ns(result)
        # print(f"Settling time: {settling:.2f} ns")
        print("MIN mode: simulation would run here")

    elif flowmode in (FlowMode.TYP, FlowMode.MAX):
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
        # Run parameter sweep
        results = run_switch_type_sweep()
        for switch_type, vth, settling in results:
            print(f"{switch_type.name}/{vth.name}: settling={settling}")


# =============================================================================
# CLI ENTRY POINT (for standalone testing)
# =============================================================================


if __name__ == "__main__":
    print("Testing netlist generation...")
    test_samp_netlist(FlowMode.NETLIST)
    print()
    print("Testing testbench netlist...")
    test_samp_tb_netlist(FlowMode.NETLIST)
    print()
    print("Testing variant generation...")
    test_samp_variants(FlowMode.NETLIST)
