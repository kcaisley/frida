"""
CDAC testbench and tests for FRIDA.

Includes testbench generator, simulation definitions, and pytest test functions.
"""

import hdl21 as h
import pytest
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, Vdc

from ..flow import (
    Project,
    Pvt,
    RedunStrat,
    FlowMode,
    SupplyVals,
    sim_options,
    write_sim_netlist,
    params_to_filename,
    params_to_tb_filename,
)
from ..pdk import get_pdk
from ..conftest import has_simulator, print_summary_if_verbose
from .cdac import (
    Cdac,
    CdacParams,
    cdac_variants,
    get_cdac_n_bits,
    get_cdac_weights,
    is_valid_cdac_params,
)


# =============================================================================
# TESTBENCH
# =============================================================================


@h.paramclass
class CdacTbParams:
    """CDAC testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    cdac = h.Param(dtype=CdacParams, desc="CDAC parameters", default=CdacParams())
    code = h.Param(dtype=int, desc="DAC code to apply", default=128)


@h.generator
def CdacTb(params: CdacTbParams) -> h.Module:
    """
    CDAC testbench generator.

    Creates a testbench with:
    - DC supply
    - DAC code inputs (static for single code test)
    - Load capacitor on output
    """
    supply = SupplyVals.corner(params.pvt.v)
    n_bits = get_cdac_n_bits(params.cdac)

    tb = h.sim.tb("CdacTb")

    # Supply
    tb.vdd = h.Signal()
    tb.vvdd = Vdc(dc=supply.VDD)(p=tb.vdd, n=tb.VSS)

    # DAC output with load
    tb.top = h.Signal()
    tb.cload = C(c=100 * f)(p=tb.top, n=tb.VSS)

    # DAC code inputs - generate bit values from code
    tb.dac_bits = h.Signal(width=n_bits)
    for i in range(n_bits):
        bit_val = supply.VDD if (params.code >> i) & 1 else 0 * m
        vbit = Vdc(dc=bit_val)(p=tb.dac_bits[i], n=tb.VSS)
        setattr(tb, f"vbit_{i}", vbit)

    # DUT
    tb.dut = Cdac(params.cdac)(
        top=tb.top,
        dac=tb.dac_bits,
        vdd=tb.vdd,
        vss=tb.VSS,
    )

    return tb


# =============================================================================
# SIMULATION DEFINITIONS
# =============================================================================


def sim_input(params: CdacTbParams) -> hs.Sim:
    """Create simulation input for single-code CDAC test."""
    sim_temp = Project.temper(params.pvt.t)

    @hs.sim
    class CdacSim:
        tb = CdacTb(params)
        op = hs.Op()  # DC operating point

        # Temperature setting using hs.Options
        temp = hs.Options(name="temp", value=sim_temp)

    return CdacSim


def sim_input_tran(params: CdacTbParams) -> hs.Sim:
    """Create transient simulation input for CDAC settling test."""
    sim_temp = Project.temper(params.pvt.t)

    @hs.sim
    class CdacTranSim:
        tb = CdacTb(params)
        tr = hs.Tran(tstop=100 * n, tstep=100 * p)

        # Save all signals
        save = hs.Save(hs.SaveMode.ALL)

        # Temperature setting using hs.Options
        temp = hs.Options(name="temp", value=sim_temp)

    return CdacTranSim


# =============================================================================
# SWEEP FUNCTIONS
# =============================================================================


def run_code_sweep(cdac_params: CdacParams = None, pvt: Pvt = None) -> list[tuple]:
    """
    Sweep through all DAC codes and measure output voltage.

    Returns list of (code, voltage) tuples.
    """
    if cdac_params is None:
        cdac_params = CdacParams(n_dac=8)
    if pvt is None:
        pvt = Pvt()

    n_codes = 2**cdac_params.n_dac
    results = []

    for code in range(n_codes):
        tb_params = CdacTbParams(pvt=pvt, cdac=cdac_params, code=code)
        # Simulation not executed - requires SPICE simulator with PDK
        sim = sim_input(tb_params)  # noqa: F841
        # result = sim.run(sim_options)
        # voltage = result.an[0].data["v(xtop.top)"]
        results.append((code, None))  # Placeholder

    return results


def run_linearity_test(cdac_params: CdacParams = None, pvt: Pvt = None):
    """
    Run code sweep and compute INL/DNL.

    Returns dict with INL, DNL arrays and max values.
    """
    code_sweep = run_code_sweep(cdac_params, pvt)
    # TODO: use codes array for INL/DNL computation
    codes = np.array([c for c, _ in code_sweep])  # noqa: F841
    # outputs = np.array([v for _, v in code_sweep])  # Would be real voltages

    # Placeholder - would compute real INL/DNL
    return {
        "inl_max": 0.5,
        "dnl_max": 0.3,
        "info": "Placeholder - simulation not run",
    }


def run_architecture_comparison(pvt: Pvt = None):
    """
    Compare different CDAC architectures.

    Sweeps through redundancy strategies and measures linearity.
    """
    if pvt is None:
        pvt = Pvt()

    results = {}

    for redun_strat in [RedunStrat.RDX2, RedunStrat.SUBRDX2_LIM]:
        n_extra = 0 if redun_strat == RedunStrat.RDX2 else 2

        params = CdacParams(
            n_dac=10,
            n_extra=n_extra,
            redun_strat=redun_strat,
        )

        if is_valid_cdac_params(params):
            weights = get_cdac_weights(params)
            linearity = run_linearity_test(params, pvt)
            results[redun_strat.name] = {
                "weights": weights,
                "linearity": linearity,
            }

    return results


# =============================================================================
# PYTEST TEST FUNCTIONS
# =============================================================================


def test_cdac_weights(flowmode: FlowMode):
    """Test weight calculation for different strategies."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    print("CDAC Weight Calculations:")

    # Standard binary
    params = CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2)
    weights = get_cdac_weights(params)
    print(f"  RDX2 (8-bit): {weights}")

    # Sub-radix-2 with redundancy
    params = CdacParams(n_dac=8, n_extra=2, redun_strat=RedunStrat.SUBRDX2_LIM)
    weights = get_cdac_weights(params)
    print(f"  SUBRDX2_LIM (8+2): {weights}")


def test_cdac_netlist(flowmode: FlowMode, request):
    """Test that netlist generation works for valid configurations."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()
    variants = list(cdac_variants(n_dac_list=[8], n_extra_list=[0, 2]))

    for params in variants:
        cdac = Cdac(params)
        pdk.compile(cdac)
        # Write netlist with consistent naming
        filename = params_to_filename("cdac", params, pdk.name)
        netlist_path = outdir / filename
        with open(netlist_path, "w") as f:
            h.netlist(cdac, dest=f)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="cdac",
        count=len(variants),
        params_list=variants,
        wall_time=wall_time,
        outdir=outdir,
    )


def test_cdac_tb_netlist(flowmode: FlowMode, request):
    """Test testbench netlist generation."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()

    params = CdacTbParams(cdac=CdacParams(n_dac=8))
    tb = CdacTb(params)
    pdk.compile(tb)

    # Write testbench netlist with consistent naming
    tb_filename = params_to_tb_filename("cdac", params, pdk.name, suffix=".sp")
    netlist_path = outdir / tb_filename
    with open(netlist_path, "w") as f:
        h.netlist(tb, dest=f)

    # Also write simulation netlist (same path as actual simulation)
    sim = sim_input(params)
    sim_filename = params_to_tb_filename("cdac", params, pdk.name, suffix=".scs")
    sim_netlist_path = outdir / sim_filename
    write_sim_netlist(sim, sim_netlist_path, compact=True)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="cdac_tb",
        count=2,  # .sp and .scs
        params_list=[params.cdac],  # Use inner cdac params for axes
        wall_time=wall_time,
        outdir=outdir,
    )


def test_cdac_variants(flowmode: FlowMode, request):
    """Test variant generation for different architectures."""
    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    import time

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    start = time.perf_counter()
    variants = cdac_variants()

    # Generate netlists for first 5 variants
    generated_variants = variants[:5]
    for params in generated_variants:
        cdac = Cdac(params)
        pdk.compile(cdac)
        # Write netlist with consistent naming
        filename = params_to_filename("cdac", params, pdk.name)
        netlist_path = outdir / filename
        with open(netlist_path, "w") as f:
            h.netlist(cdac, dest=f)

    wall_time = time.perf_counter() - start

    # Print summary table if verbose
    print_summary_if_verbose(
        request,
        block="cdac_variants",
        count=len(generated_variants),
        params_list=generated_variants,
        wall_time=wall_time,
        outdir=outdir,
    )


def test_cdac_sim(flowmode: FlowMode):
    """Test CDAC simulation."""
    if flowmode == FlowMode.NETLIST:
        # Just verify sim input can be created
        params = CdacTbParams(cdac=CdacParams(n_dac=8))
        sim = sim_input(params)
        assert sim is not None
        pytest.skip("Simulation requires --mode=min/typ/max")

    elif flowmode == FlowMode.MIN:
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
        # Run one quick simulation
        params = CdacTbParams(cdac=CdacParams(n_dac=8), code=128)
        # Simulation not executed - requires SPICE simulator with PDK
        sim = sim_input_tran(params)  # noqa: F841
        # result = sim.run(sim_options)
        # settling = cdac_settling_ns(result)
        # print(f"Settling time: {settling:.2f} ns")
        print("MIN mode: simulation would run here")

    elif flowmode in (FlowMode.TYP, FlowMode.MAX):
        if not has_simulator():
            pytest.skip("Simulation requires sim host (jupiter/juno/asiclab003)")
        # Run architecture comparison
        results = run_architecture_comparison()
        for arch, data in results.items():
            print(f"{arch}: weights={data['weights'][:3]}...")


# =============================================================================
# CLI ENTRY POINT (for standalone testing)
# =============================================================================


if __name__ == "__main__":
    print("Testing CDAC weight calculations...")
    test_cdac_weights(FlowMode.NETLIST)
    print()
    print("Testing CDAC netlist generation...")
    test_cdac_netlist(FlowMode.NETLIST)
    print()
    print("Testing CDAC testbench netlist...")
    test_cdac_tb_netlist(FlowMode.NETLIST)
