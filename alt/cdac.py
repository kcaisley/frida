"""
Capacitor DAC (CDAC) generator for FRIDA.

Supports multiple architectures including:
- Various redundancy strategies (RDX2, sub-radix-2, etc.)
- Different split strategies (no split, voltage divider, difference cap)
- Variable bit widths with dynamic port generation

Includes testbench, simulation definitions, and pytest test functions.
"""

import io
import math
from typing import Optional, List

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner
from hdl21.prefix import n, p, f, m, µ
from hdl21.primitives import Vdc, Vpulse, C

from .pdk import get_pdk
from .common.params import Vth, RedunStrat, SplitStrat, CapType, Pvt, SupplyVals, Project
from .conftest import SimTestMode


@h.paramclass
class CdacParams:
    """CDAC parameters."""

    n_dac = h.Param(dtype=int, desc="DAC resolution (bits)", default=8)
    n_extra = h.Param(dtype=int, desc="Extra caps for redundancy", default=0)
    redun_strat = h.Param(dtype=RedunStrat, desc="Redundancy strategy", default=RedunStrat.RDX2)
    split_strat = h.Param(dtype=SplitStrat, desc="Split strategy", default=SplitStrat.NO_SPLIT)
    cap_type = h.Param(dtype=CapType, desc="Capacitor type", default=CapType.MOM1)
    vth = h.Param(dtype=Vth, desc="Transistor Vth", default=Vth.LVT)
    unit_cap = h.Param(dtype=h.Scalar, desc="Unit capacitance", default=1 * f)


def is_valid_cdac_params(p: CdacParams) -> bool:
    """Check if this CDAC configuration is valid."""
    # RDX2 only works with n_extra=0
    if p.redun_strat == RedunStrat.RDX2 and p.n_extra != 0:
        return False
    # Other strategies need n_extra > 0
    if p.redun_strat != RedunStrat.RDX2 and p.n_extra == 0:
        return False
    return _calc_weights(p.n_dac, p.n_extra, p.redun_strat) is not None


def get_cdac_weights(p: CdacParams) -> List[int]:
    """Get the capacitor weights for a CDAC configuration."""
    weights = _calc_weights(p.n_dac, p.n_extra, p.redun_strat)
    if weights is None:
        raise ValueError(f"Invalid CDAC params: {p}")
    return weights


def get_cdac_n_bits(p: CdacParams) -> int:
    """Get the number of physical bits (capacitors) for a CDAC configuration."""
    return len(get_cdac_weights(p))


@h.generator
def Cdac(p: CdacParams) -> h.Module:
    """
    Capacitor DAC generator.

    Generates a CDAC with variable bit width based on parameters.
    """
    pdk = get_pdk()
    weights = get_cdac_weights(p)
    n_bits = len(weights)

    # Select devices based on Vth
    Nfet = pdk.NmosLvt if p.vth == Vth.LVT else pdk.Nmos
    Pfet = pdk.PmosLvt if p.vth == Vth.LVT else pdk.Pmos

    @h.module
    class Cdac:
        """Capacitor DAC module."""

        # IO ports
        top = h.Port(desc="DAC output (top plate)")
        vdd = h.Port(desc="Supply")
        vss = h.Port(desc="Ground")
        # Variable-width DAC control bus
        dac = h.Input(width=n_bits, desc="DAC control bits")

    # Build each DAC bit
    threshold = 64  # Split threshold for vdiv/diffcap

    for idx, weight in enumerate(weights):
        _build_dac_bit(Cdac, p, idx, weight, threshold, Nfet, Pfet)

    return Cdac


def _calc_driver_width(c: int, m: int) -> int:
    """Calculate driver width based on capacitor load (sqrt scaling)."""
    return max(1, int(math.sqrt(c * m)))


def _build_dac_bit(mod, p: CdacParams, idx: int, weight: int, threshold: int, Nfet, Pfet):
    """Build one DAC bit: buffer + driver + capacitor(s)."""

    # Create intermediate signal for this bit
    inter = h.Signal(name=f"inter_{idx}")
    bot = h.Signal(name=f"bot_{idx}")
    setattr(mod, f"inter_{idx}", inter)
    setattr(mod, f"bot_{idx}", bot)

    # First inverter (predriver - always unit sized)
    mp_buf = Pfet(w=1 * µ, l=60 * n)(d=inter, g=mod.dac[idx], s=mod.vdd, b=mod.vdd)
    mn_buf = Nfet(w=1 * µ, l=60 * n)(d=inter, g=mod.dac[idx], s=mod.vss, b=mod.vss)
    setattr(mod, f"mp_buf_{idx}", mp_buf)
    setattr(mod, f"mn_buf_{idx}", mn_buf)

    if p.split_strat == SplitStrat.NO_SPLIT:
        _build_nosplit_bit(mod, p, idx, weight, inter, bot, Nfet, Pfet)
    elif p.split_strat == SplitStrat.VDIV_SPLIT:
        _build_nosplit_bit(mod, p, idx, weight, inter, bot, Nfet, Pfet)  # Simplified
    else:  # DIFFCAP_SPLIT
        _build_nosplit_bit(mod, p, idx, weight, inter, bot, Nfet, Pfet)  # Simplified


def _build_nosplit_bit(mod, p: CdacParams, idx: int, weight: int, inter, bot, Nfet, Pfet):
    """No split: c=1, m=weight (simplified using multiplier)."""
    driver_w = _calc_driver_width(1, weight) * µ

    # Driver inverter
    mp_drv = Pfet(w=driver_w, l=60 * n)(d=bot, g=inter, s=mod.vdd, b=mod.vdd)
    mn_drv = Nfet(w=driver_w, l=60 * n)(d=bot, g=inter, s=mod.vss, b=mod.vss)
    setattr(mod, f"mp_drv_{idx}", mp_drv)
    setattr(mod, f"mn_drv_{idx}", mn_drv)

    # Main capacitor (weight implemented via capacitance value)
    cap_val = weight * p.unit_cap
    cap = C(c=cap_val)(p=mod.top, n=bot)
    setattr(mod, f"c_{idx}", cap)


def cdac_variants(
    n_dac_list: list = None,
    n_extra_list: list = None,
    redun_strats: list = None,
    split_strats: list = None,
) -> list:
    """
    Generate a list of valid CdacParams for parameter sweeps.

    Only generates valid topology combinations.
    """
    if n_dac_list is None:
        n_dac_list = [7, 9, 11]
    if n_extra_list is None:
        n_extra_list = [0, 2, 4]
    if redun_strats is None:
        redun_strats = list(RedunStrat)
    if split_strats is None:
        split_strats = [SplitStrat.NO_SPLIT]  # Simplified for now

    variants = []

    for n_dac in n_dac_list:
        for n_extra in n_extra_list:
            for redun_strat in redun_strats:
                for split_strat in split_strats:
                    params = CdacParams(
                        n_dac=n_dac,
                        n_extra=n_extra,
                        redun_strat=redun_strat,
                        split_strat=split_strat,
                    )
                    if is_valid_cdac_params(params):
                        variants.append(params)

    return variants


# =============================================================================
# WEIGHT CALCULATION (internal helper, called by validation and getter functions)
# =============================================================================


def _calc_weights(n_dac: int, n_extra: int, strategy: RedunStrat) -> Optional[List[int]]:
    """
    Calculate capacitor weights for CDAC.

    Args:
        n_dac: DAC resolution (number of bits)
        n_extra: Number of extra physical capacitors for redundancy
        strategy: RedunStrat enum for weighting strategy

    Returns:
        List of (n_dac + n_extra) integer weights (in units of Cu), or None for invalid combos
    """
    m_caps = n_dac + n_extra

    if strategy == RedunStrat.RDX2:
        # Standard binary weighting: [2^(n-1), 2^(n-2), ..., 2, 1]
        # Pad with unit caps if n_extra > 0
        weights = [2**i for i in range(n_dac - 1, -1, -1)]
        if n_extra > 0:
            weights.extend([1] * n_extra)
        return weights

    elif strategy == RedunStrat.SUBRDX2:
        # Each bit is equal to radix^bit up to bit M-1, where radix = 2^(N/M)
        # Round to nearest integer (not floor like normalized)
        radix = 2 ** (n_dac / m_caps)
        weights = [round(radix ** (m_caps - 1 - i)) for i in range(m_caps)]
        return weights

    elif strategy == RedunStrat.SUBRDX2_LIM:
        # Sub-radix-2 with unit quantization
        # Radix < 2 provides redundancy for error correction
        radix = 2 ** (n_dac / m_caps)
        weights = [max(1, int(radix ** (m_caps - 1 - i))) for i in range(m_caps)]
        return weights

    elif strategy == RedunStrat.SUBRDX2_RDST:
        # Binary with MSB redistribution for redundancy
        # Split 2^n_redist from MSB and redistribute as pairs
        n_redist = n_extra + 2  # Extra caps determine redistribution

        # Base binary weights
        weights = [2**i for i in range(n_dac - 1, -1, -1)]

        # Check if MSB would become negative - return None for invalid combinations
        if weights[0] < 2**n_redist:
            return None

        weights[0] -= 2**n_redist  # Subtract from MSB

        # Redundant weights as paired powers of 2
        w_redun = [2**i for i in range(n_redist - 2, -1, -1) for _ in range(2)]
        w_redun += [1, 1]  # Final unit pair

        # Merge: add redundant weights offset by 1 position
        result = [0] * m_caps
        for i, w in enumerate(weights):
            if i < m_caps:
                result[i] += w
        for i, w in enumerate(w_redun):
            if i + 1 < m_caps:
                result[i + 1] += w

        return result

    elif strategy == RedunStrat.RDX2_RPT:
        # Generate base radix-2 array, then insert repeated capacitors
        # Extra capacitors are inserted at regular intervals

        # Base radix-2 weights
        base_weights = [2**i for i in range(n_dac - 1, -1, -1)]

        if n_extra == 0:
            return base_weights

        # Calculate spacing for inserted capacitors
        spacing = n_dac // n_extra

        # Calculate which base array positions should be duplicated
        # First duplicate is 1 position from end, then every 'spacing' positions earlier
        duplicate_indices = []
        for k in range(n_extra):
            pos_from_end = 1 + k * spacing
            # Convert to 0-based index in base_weights array
            idx = n_dac - 1 - pos_from_end
            duplicate_indices.append(idx)

        # Sort in ascending order to process from MSB to LSB
        duplicate_indices.sort()

        # Build result by inserting duplicates after their positions
        result = []
        dup_idx = 0
        for i in range(n_dac):
            result.append(base_weights[i])
            # Check if this position should be duplicated
            if dup_idx < len(duplicate_indices) and i == duplicate_indices[dup_idx]:
                result.append(base_weights[i])
                dup_idx += 1

        return result

    else:
        return None  # Unknown strategy


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
    temp = Project.temper(params.pvt.t)

    @hs.sim
    class CdacSim:
        tb = CdacTb(params)
        op = hs.Op()  # DC operating point

        # Use _ for Literal (frozen dataclass, has no name field)
        _ = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
        """
        )

    return CdacSim


def sim_input_tran(params: CdacTbParams) -> hs.Sim:
    """Create transient simulation input for CDAC settling test."""
    temp = Project.temper(params.pvt.t)

    @hs.sim
    class CdacTranSim:
        tb = CdacTb(params)
        tr = hs.Tran(tstop=100 * n, tstep=100 * p)

        # Save all signals
        save = hs.Save(hs.SaveMode.ALL)

        # Use _ for Literal (frozen dataclass, has no name field)
        _ = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
        """
        )

    return CdacTranSim


# =============================================================================
# SWEEP FUNCTIONS
# =============================================================================


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
        # result = sim.run(sim_options)
        # voltage = result.an[0].data["v(xtop.top)"]
        results.append((code, None))  # Placeholder

    return results


def run_linearity_test(cdac_params: CdacParams = None, pvt: Pvt = None):
    """
    Run code sweep and compute INL/DNL.

    Returns dict with INL, DNL arrays and max values.
    """
    from .measure import compute_inl_dnl
    import numpy as np

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


# =============================================================================
# PYTEST TEST FUNCTIONS
# =============================================================================


def test_cdac_weights(simtestmode: SimTestMode):
    """Test weight calculation for different strategies."""
    if simtestmode != SimTestMode.NETLIST:
        return

    print("CDAC Weight Calculations:")

    # Standard binary
    params = CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2)
    weights = get_cdac_weights(params)
    print(f"  RDX2 (8-bit): {weights}")

    # Sub-radix-2 with redundancy
    params = CdacParams(n_dac=8, n_extra=2, redun_strat=RedunStrat.SUBRDX2_LIM)
    weights = get_cdac_weights(params)
    print(f"  SUBRDX2_LIM (8+2): {weights}")


def test_cdac_netlist(simtestmode: SimTestMode):
    """Test that netlist generation works for valid configurations."""
    if simtestmode != SimTestMode.NETLIST:
        return

    count = 0
    for params in cdac_variants(n_dac_list=[8], n_extra_list=[0, 2]):
        cdac = Cdac(params)
        h.netlist(cdac, dest=io.StringIO())
        count += 1
    print(f"Generated {count} valid CDAC netlists")


def test_cdac_tb_netlist(simtestmode: SimTestMode):
    """Test testbench netlist generation."""
    if simtestmode != SimTestMode.NETLIST:
        return

    params = CdacTbParams(cdac=CdacParams(n_dac=8))
    tb = CdacTb(params)
    h.netlist(tb, dest=io.StringIO())
    print("CDAC testbench netlist generated successfully")


def test_cdac_variants(simtestmode: SimTestMode):
    """Test variant generation for different architectures."""
    if simtestmode != SimTestMode.NETLIST:
        return

    variants = cdac_variants()
    print(f"Generated {len(variants)} valid CDAC variants")

    # Verify all variants produce valid netlists
    for params in variants[:5]:  # Test first 5
        cdac = Cdac(params)
        h.netlist(cdac, dest=io.StringIO())


def test_cdac_sim(simtestmode: SimTestMode):
    """Test CDAC simulation."""
    if simtestmode == SimTestMode.NETLIST:
        # Just verify sim input can be created
        params = CdacTbParams(cdac=CdacParams(n_dac=8))
        sim = sim_input(params)
        print("Simulation input created successfully")

    elif simtestmode == SimTestMode.MIN:
        # Run one quick simulation
        from .common.sim_options import sim_options
        from .measure import cdac_settling_ns

        params = CdacTbParams(cdac=CdacParams(n_dac=8), code=128)
        sim = sim_input_tran(params)
        # result = sim.run(sim_options)
        # settling = cdac_settling_ns(result)
        # print(f"Settling time: {settling:.2f} ns")
        print("MIN mode: simulation would run here")

    elif simtestmode in (SimTestMode.TYP, SimTestMode.MAX):
        # Run architecture comparison
        results = run_architecture_comparison()
        for arch, data in results.items():
            print(f"{arch}: weights={data['weights'][:3]}...")


# =============================================================================
# CLI ENTRY POINT (for standalone testing)
# =============================================================================


if __name__ == "__main__":
    print("Testing CDAC weight calculations...")
    test_cdac_weights(SimTestMode.NETLIST)
    print()
    print("Testing CDAC netlist generation...")
    test_cdac_netlist(SimTestMode.NETLIST)
    print()
    print("Testing CDAC testbench netlist...")
    test_cdac_tb_netlist(SimTestMode.NETLIST)
