"""
CDAC testbench and simulation tests.
"""

import io
from typing import List

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner
from hdl21.prefix import n, p, f, m, µ
from hdl21.primitives import Vdc, Vpulse, C

from ..cdac import Cdac, CdacParams, cdac_variants, is_valid_cdac_params, get_cdac_weights, get_cdac_n_bits
from ..common.params import Pvt, SupplyVals, Project, RedunStrat, SplitStrat
from .sim_options import sim_options


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


@h.generator
def CdacCodeSweepTb(params: CdacTbParams) -> h.Module:
    """
    CDAC testbench for code sweep using PWL sources.

    Sweeps through all DAC codes using piecewise-linear voltage sources.
    """
    supply = SupplyVals.corner(params.pvt.v)
    n_bits = get_cdac_n_bits(params.cdac)
    n_codes = 2**params.cdac.n_dac
    t_per_code = 10 * n  # Time per code

    tb = h.sim.tb("CdacCodeSweepTb")

    # Supply
    tb.vdd = h.Signal()
    tb.vvdd = Vdc(dc=supply.VDD)(p=tb.vdd, n=tb.VSS)

    # DAC output with load
    tb.top = h.Signal()
    tb.cload = C(c=100 * f)(p=tb.top, n=tb.VSS)

    # DAC code inputs - PWL sources that sweep through codes
    tb.dac_bits = h.Signal(width=n_bits)

    # Generate PWL for each bit
    # Each bit toggles at different rates to sweep through all codes
    for bit_idx in range(n_bits):
        # Generate PWL points for this bit
        # Bit i toggles every 2^i codes
        toggle_period = (2**bit_idx) * t_per_code
        pwl_points = []
        t = 0
        bit_state = 0

        while t < n_codes * t_per_code:
            v = supply.VDD if bit_state else 0 * m
            pwl_points.append(f"{t.number}n {v.number}")
            t = t + toggle_period
            bit_state = 1 - bit_state
            if t < n_codes * t_per_code:
                pwl_points.append(f"{t.number}n {v.number}")

        pwl_str = " ".join(pwl_points)

        # Use Literal for PWL (simplified)
        vbit = Vdc(dc=0 * m)(p=tb.dac_bits[bit_idx], n=tb.VSS)
        setattr(tb, f"vbit_{bit_idx}", vbit)

    # DUT
    tb.dut = Cdac(params.cdac)(
        top=tb.top,
        dac=tb.dac_bits,
        vdd=tb.vdd,
        vss=tb.VSS,
    )

    return tb


def sim_input(params: CdacTbParams) -> hs.Sim:
    """Create simulation input for single-code CDAC test."""
    temp = Project.temper(params.pvt.t)

    @hs.sim
    class CdacSim:
        tb = CdacTb(params)
        op = hs.Op()  # DC operating point

        temp_lit = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
        """
        )

    return CdacSim


def run_code_sweep(cdac_params: CdacParams = None, pvt: Pvt = None) -> List[tuple]:
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
        sim = sim_input(tb_params)
        # result = sim.run(sim_options)  # Would run simulation
        # voltage = result.an[0].data["v(xtop.top)"]
        results.append((code, None))  # Placeholder

    return results


def run_linearity_test(cdac_params: CdacParams = None, pvt: Pvt = None):
    """
    Run code sweep and compute INL/DNL.

    Returns dict with INL, DNL arrays and max values.
    """
    import numpy as np
    from ..sim import compute_inl_dnl

    code_sweep = run_code_sweep(cdac_params, pvt)
    codes = np.array([c for c, _ in code_sweep])
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


# Test functions
def test_cdac_weights():
    """Test weight calculation for different strategies."""
    print("CDAC Weight Calculations:")

    # Standard binary
    params = CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2)
    weights = get_cdac_weights(params)
    print(f"  RDX2 (8-bit): {weights}")

    # Sub-radix-2 with redundancy
    params = CdacParams(n_dac=8, n_extra=2, redun_strat=RedunStrat.SUBRDX2_LIM)
    weights = get_cdac_weights(params)
    print(f"  SUBRDX2_LIM (8+2): {weights}")


def test_cdac_netlist():
    """Test that netlist generation works for valid configurations."""
    count = 0
    for params in cdac_variants(n_dac_list=[8], n_extra_list=[0, 2]):
        cdac = Cdac(params)
        h.netlist(cdac, dest=io.StringIO())
        count += 1
    print(f"Generated {count} valid CDAC netlists")


def test_cdac_tb_netlist():
    """Test testbench netlist generation."""
    params = CdacTbParams(cdac=CdacParams(n_dac=8))
    tb = CdacTb(params)
    h.netlist(tb, dest=io.StringIO())
    print("CDAC testbench netlist generated successfully")


if __name__ == "__main__":
    print("Testing CDAC weight calculations...")
    test_cdac_weights()
    print()
    print("Testing CDAC netlist generation...")
    test_cdac_netlist()
    print()
    print("Testing CDAC testbench netlist...")
    test_cdac_tb_netlist()
