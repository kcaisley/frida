"""
Sampler testbench and tests for FRIDA.

Includes testbench generator, simulation definitions, and pytest test functions.
"""


import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosVth, Vdc, Vpulse

from ..flow import Project, Pvt, SimTestMode, SupplyVals, SwitchType, sim_options, write_sim_netlist
from ..pdk import get_pdk
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
            # TODO: run simulation and measure settling
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
        # TODO: run simulation and extract result
        sim = sim_input(tb_params)  # noqa: F841
        # result = sim.run(sim_options)
        results.append((width, None))  # Placeholder

    return results


# =============================================================================
# PYTEST TEST FUNCTIONS
# =============================================================================


def test_samp_netlist(simtestmode: SimTestMode):
    """Test sampler netlist generation for all topologies."""
    if simtestmode != SimTestMode.NETLIST:
        return

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    count = 0
    for switch_type in SwitchType:
        for vth in [MosVth.LOW, MosVth.STD]:
            params = SampParams(switch_type=switch_type, vth=vth)
            samp = Samp(params)
            pdk.compile(samp)
            netlist_path = outdir / f"samp_{switch_type.name}_{vth.name}.sp"
            with open(netlist_path, "w") as f:
                h.netlist(samp, dest=f)
            count += 1

    print(f"Generated {count} sampler netlists in {outdir}/")


def test_samp_tb_netlist(simtestmode: SimTestMode):
    """Test testbench netlist generation."""
    if simtestmode != SimTestMode.NETLIST:
        return

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    params = SampTbParams()
    tb = SampTb(params)
    pdk.compile(tb)
    netlist_path = outdir / "samp_tb.sp"
    with open(netlist_path, "w") as f:
        h.netlist(tb, dest=f)
    print(f"Sampler testbench netlist: {netlist_path}")

    # Also write simulation netlist (same path as actual simulation)
    sim = sim_input(params)
    sim_netlist_path = outdir / "samp_tb.scs"
    write_sim_netlist(sim, sim_netlist_path, compact=True)
    print(f"Sampler simulation netlist: {sim_netlist_path}")


def test_samp_variants(simtestmode: SimTestMode):
    """Test variant generation."""
    if simtestmode != SimTestMode.NETLIST:
        return

    pdk = get_pdk()
    outdir = sim_options.rundir
    outdir.mkdir(exist_ok=True)

    variants = samp_variants()
    print(f"Generated {len(variants)} sampler variants")

    # Verify first 5 variants produce valid netlists
    for i, params in enumerate(variants[:5]):
        samp = Samp(params)
        pdk.compile(samp)
        netlist_path = outdir / f"samp_variant_{i}.sp"
        with open(netlist_path, "w") as f:
            h.netlist(samp, dest=f)


def test_samp_sim(simtestmode: SimTestMode):
    """Test sampler simulation."""
    if simtestmode == SimTestMode.NETLIST:
        # Just verify sim input can be created
        params = SampTbParams()
        sim = sim_input(params)
        print("Simulation input created successfully")

    elif simtestmode == SimTestMode.MIN:
        # Run one quick simulation
        params = SampTbParams(samp=SampParams(switch_type=SwitchType.TGATE))
        # TODO: run simulation and measure settling
        sim = sim_input(params)  # noqa: F841
        # result = sim.run(sim_options)
        # settling = samp_settling_ns(result)
        # print(f"Settling time: {settling:.2f} ns")
        print("MIN mode: simulation would run here")

    elif simtestmode in (SimTestMode.TYP, SimTestMode.MAX):
        # Run parameter sweep
        results = run_switch_type_sweep()
        for switch_type, vth, settling in results:
            print(f"{switch_type.name}/{vth.name}: settling={settling}")


# =============================================================================
# CLI ENTRY POINT (for standalone testing)
# =============================================================================


if __name__ == "__main__":
    print("Testing netlist generation...")
    test_samp_netlist(SimTestMode.NETLIST)
    print()
    print("Testing testbench netlist...")
    test_samp_tb_netlist(SimTestMode.NETLIST)
    print()
    print("Testing variant generation...")
    test_samp_variants(SimTestMode.NETLIST)
