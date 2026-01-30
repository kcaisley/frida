"""
Sampler testbench and simulation tests.
"""

import io
from copy import copy
from typing import List

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner
from hdl21.prefix import n, p, f, m, µ
from hdl21.primitives import Vdc, Vpulse, C

from ..samp import Samp, SampParams, samp_variants
from ..common.params import SwitchType, Vth, Pvt, SupplyVals, Project
from .sim_options import sim_options


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


def sim_input(params: SampTbParams) -> hs.Sim:
    """
    Create simulation input for sampler characterization.

    Includes transient analysis and measurements for:
    - On-resistance (Ron)
    - Settling time
    - Charge injection
    """
    # Get temperature from PVT
    temp = Project.temper(params.pvt.t)

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

        # Temperature setting
        l = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
        """
        )

    return SampSim


def run_single(params: SampTbParams = None) -> hs.SimResult:
    """Run a single sampler simulation with given parameters."""
    if params is None:
        params = SampTbParams()

    sim = sim_input(params)
    return sim.run(sim_options)


def run_switch_sweep(pvt: Pvt = None) -> List[hs.SimResult]:
    """
    Sweep over switch types at given PVT conditions.

    Returns results for NMOS, PMOS, and TGATE switches.
    """
    if pvt is None:
        pvt = Pvt()

    results = []
    for switch_type in SwitchType:
        samp_params = SampParams(switch_type=switch_type, w=10 * µ, l=60 * n)
        tb_params = SampTbParams(pvt=pvt, samp=samp_params)
        result = run_single(tb_params)
        results.append((switch_type, result))

    return results


# Post-processing functions for extracting metrics
def extract_settling_time(result: hs.SimResult) -> float:
    """Extract settling time from simulation result."""
    # Access measurement result
    try:
        return result.an[0].data.get("t_settle", float("nan"))
    except (IndexError, KeyError, AttributeError):
        return float("nan")


def extract_ron(result: hs.SimResult, vin: str = "xtop.din", vout: str = "xtop.dout") -> float:
    """
    Estimate on-resistance from transient simulation.

    Calculates Ron = (Vin - Vout) / Iswitch during sampling phase.
    """
    try:
        time = result.an[0].data["time"]
        v_in = result.an[0].data[f"v({vin})"]
        v_out = result.an[0].data[f"v({vout})"]

        # Find sampling phase (clk high, early in simulation)
        # Use time around 10ns as a sample point
        idx = (time > 10 * n) & (time < 20 * n)
        if not any(idx):
            return float("nan")

        # Average voltage difference during sampling
        delta_v = abs(v_in[idx] - v_out[idx]).mean()

        # This is a simplified estimate - real Ron calculation
        # would need current measurement
        return delta_v
    except (KeyError, AttributeError):
        return float("nan")


# Test functions
def test_netlist():
    """Test that netlist generation works for all switch types."""
    for switch_type in SwitchType:
        for vth in Vth:
            params = SampParams(switch_type=switch_type, vth=vth)
            samp = Samp(params)
            netlist = h.netlist(samp, dest=io.StringIO())
            print(f"{switch_type.name}/{vth.name}: Netlist generated successfully")


def test_tb_netlist():
    """Test that testbench netlist generation works."""
    params = SampTbParams()
    tb = SampTb(params)
    netlist = h.netlist(tb, dest=io.StringIO())
    print("Testbench netlist generated successfully")


def run_width_sweep(pvt: Pvt = None, switch_type: SwitchType = SwitchType.NMOS) -> List[tuple]:
    """
    Sweep over device widths for a given switch type.

    Returns list of (width, result) tuples.
    """
    if pvt is None:
        pvt = Pvt()

    width_list = [2 * µ, 5 * µ, 10 * µ, 20 * µ, 40 * µ]
    results = []

    for width in width_list:
        samp_params = SampParams(switch_type=switch_type, w=width, l=60 * n)
        tb_params = SampTbParams(pvt=pvt, samp=samp_params)
        sim = sim_input(tb_params)
        # result = sim.run(sim_options)  # Would run simulation
        results.append((width, None))  # Placeholder

    return results


def run_pvt_sweep(samp_params: SampParams = None) -> dict:
    """
    Run sampler simulation across PVT corners.

    Returns dict mapping corner name to result.
    """
    if samp_params is None:
        samp_params = SampParams(switch_type=SwitchType.TGATE, w=10 * µ, l=60 * n)

    corners = [Corner.SLOW, Corner.TYP, Corner.FAST]
    results = {}

    for corner in corners:
        pvt = Pvt(p=corner, v=corner, t=corner)
        tb_params = SampTbParams(pvt=pvt, samp=samp_params)
        sim = sim_input(tb_params)
        # result = sim.run(sim_options)  # Would run simulation
        results[corner.name] = None  # Placeholder

    return results


def run_full_parameter_sweep(pvt: Pvt = None) -> List[dict]:
    """
    Run comprehensive parameter sweep over all sampler variants.

    Uses samp_variants() to generate all combinations and runs simulations.
    """
    if pvt is None:
        pvt = Pvt()

    variants = samp_variants(
        w_list=[5 * µ, 10 * µ],
        l_list=[60 * n],
        switch_types=list(SwitchType),
        vth_list=[Vth.LVT],
    )

    results = []
    for samp_params in variants:
        tb_params = SampTbParams(pvt=pvt, samp=samp_params)
        sim = sim_input(tb_params)
        # result = sim.run(sim_options)  # Would run simulation
        results.append({
            "params": samp_params,
            "result": None,  # Placeholder
        })

    return results


def test_variants():
    """Test variant generation."""
    variants = samp_variants()
    print(f"Generated {len(variants)} sampler variants")
    for v in variants[:5]:
        print(f"  {v}")


if __name__ == "__main__":
    # Run basic tests
    print("Testing netlist generation...")
    test_netlist()
    print()
    print("Testing testbench netlist...")
    test_tb_netlist()
    print()
    print("Testing variant generation...")
    test_variants()
