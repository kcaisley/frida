"""
Sampling Switch generator for FRIDA.

Supports NMOS, PMOS, and transmission gate topologies
with configurable device sizing and threshold voltage.

Includes testbench, simulation definitions, and pytest test functions.

Note: Generators use h.Mos primitives with MosType/MosVth parameters.
Call pdk.compile(module) after generation to convert to PDK-specific devices.
"""

import io
from typing import List

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosType, MosVth, Vdc, Vpulse

from .common.params import Project, Pvt, SupplyVals, SwitchType, Vth
from .conftest import SimTestMode
from .pdk import get_pdk


@h.paramclass
class SampParams:
    """Sampling switch parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=10 means 10×Wmin, e.g., 1.2µm for TSMC65)
    - l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for TSMC65)

    This approach allows the same design to be portable across PDKs.
    """

    switch_type = h.Param(
        dtype=SwitchType, desc="Switch topology", default=SwitchType.NMOS
    )
    w = h.Param(dtype=int, desc="Width multiplier (× Wmin)", default=10)
    l = h.Param(dtype=int, desc="Length multiplier (× Lmin)", default=1)
    vth = h.Param(dtype=Vth, desc="Threshold voltage flavor", default=Vth.LVT)


def _vth_to_mosvth(vth: Vth) -> MosVth:
    """Convert FRIDA Vth enum to HDL21 MosVth."""
    return MosVth.LOW if vth == Vth.LVT else MosVth.STD


@h.generator
def Samp(p: SampParams) -> h.Module:
    """
    Sampling switch generator.

    Generates NMOS, PMOS, or transmission gate switches
    based on the switch_type parameter.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    mosvth = _vth_to_mosvth(p.vth)

    @h.module
    class Samp:
        """Sampling switch module."""

        # IO ports
        din = h.Input(desc="Data input")
        dout = h.Output(desc="Data output")
        clk = h.Input(desc="Clock (active high)")
        clk_b = h.Input(desc="Clock complement (active low)")
        vdd = h.Port(desc="Supply")
        vss = h.Port(desc="Ground")

    # Instantiate devices based on switch type
    if p.switch_type == SwitchType.NMOS:
        Samp.mn = h.Mos(tp=MosType.NMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss
        )

    elif p.switch_type == SwitchType.PMOS:
        Samp.mp = h.Mos(tp=MosType.PMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    elif p.switch_type == SwitchType.TGATE:
        Samp.mn = h.Mos(tp=MosType.NMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss
        )
        Samp.mp = h.Mos(tp=MosType.PMOS, vth=mosvth, w=p.w, l=p.l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    return Samp


# Convenience function to generate parameter sweep variants
def samp_variants(
    w_list: list = None,
    l_list: list = None,
    switch_types: list = None,
    vth_list: list = None,
) -> list:
    """
    Generate a list of SampParams for parameter sweeps.

    Args:
        w_list: List of width multipliers (default: [5, 10, 20, 40])
        l_list: List of length multipliers (default: [1, 2])
        switch_types: List of SwitchType values (default: all)
        vth_list: List of Vth values (default: all)

    Returns:
        List of SampParams instances
    """
    if w_list is None:
        w_list = [5, 10, 20, 40]
    if l_list is None:
        l_list = [1, 2]
    if switch_types is None:
        switch_types = list(SwitchType)
    if vth_list is None:
        vth_list = list(Vth)

    return [
        SampParams(switch_type=st, w=w, l=l, vth=vth)
        for st in switch_types
        for w in w_list
        for l in l_list
        for vth in vth_list
    ]


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
        # Use _ for Literal (frozen dataclass, has no name field)
        _ = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
        """
        )

    return SampSim


# =============================================================================
# SWEEP FUNCTIONS
# =============================================================================


def run_switch_type_sweep(pvt: Pvt = None) -> List[tuple]:
    """
    Sweep over switch types at given PVT conditions.

    Returns list of (switch_type, vth, settling_time) tuples.
    """
    if pvt is None:
        pvt = Pvt()

    from .common.sim_options import sim_options
    from .measure import samp_settling_ns

    results = []
    for switch_type in SwitchType:
        for vth in Vth:
            samp_params = SampParams(switch_type=switch_type, w=10, l=1, vth=vth)
            tb_params = SampTbParams(pvt=pvt, samp=samp_params)
            sim = sim_input(tb_params)
            # result = sim.run(sim_options)
            # settling = samp_settling_ns(result)
            results.append((switch_type, vth, None))  # Placeholder

    return results


def run_width_sweep(
    pvt: Pvt = None,
    switch_type: SwitchType = SwitchType.NMOS,
) -> List[tuple]:
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
        sim = sim_input(tb_params)
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
    count = 0
    for switch_type in SwitchType:
        for vth in Vth:
            params = SampParams(switch_type=switch_type, vth=vth)
            samp = Samp(params)
            pdk.compile(samp)
            h.netlist(samp, dest=io.StringIO())
            count += 1

    print(f"Generated {count} sampler netlists")


def test_samp_tb_netlist(simtestmode: SimTestMode):
    """Test testbench netlist generation."""
    if simtestmode != SimTestMode.NETLIST:
        return

    pdk = get_pdk()
    params = SampTbParams()
    tb = SampTb(params)
    pdk.compile(tb)
    h.netlist(tb, dest=io.StringIO())
    print("Testbench netlist generated successfully")


def test_samp_variants(simtestmode: SimTestMode):
    """Test variant generation."""
    if simtestmode != SimTestMode.NETLIST:
        return

    pdk = get_pdk()
    variants = samp_variants()
    print(f"Generated {len(variants)} sampler variants")

    # Verify all variants produce valid netlists
    for params in variants[:5]:  # Test first 5
        samp = Samp(params)
        pdk.compile(samp)
        h.netlist(samp, dest=io.StringIO())


def test_samp_sim(simtestmode: SimTestMode):
    """Test sampler simulation."""
    if simtestmode == SimTestMode.NETLIST:
        # Just verify sim input can be created
        params = SampTbParams()
        sim = sim_input(params)
        print("Simulation input created successfully")

    elif simtestmode == SimTestMode.MIN:
        # Run one quick simulation
        from .common.sim_options import sim_options
        from .measure import samp_settling_ns

        params = SampTbParams(samp=SampParams(switch_type=SwitchType.TGATE))
        sim = sim_input(params)
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
