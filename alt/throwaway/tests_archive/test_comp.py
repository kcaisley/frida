"""
Comparator testbench and simulation tests.

Matches the original blocks/comp.py testbench structure:
- 5 common-mode voltages: 0.3V to 0.7V
- 11 differential voltages: -10mV to +10mV (2mV steps)
- 10 clock cycles at each point
- Source impedances: 1kΩ + 100fF
- 10ns clock period, 40% duty cycle

Monte Carlo configuration (default):
- numruns: 10 (for quick characterization)
- seed: 12345 (fixed for reproducibility)
- variations: mismatch (most relevant for comparator)
"""

import io
from typing import List, Dict, Any
from dataclasses import dataclass

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner
from hdl21.prefix import n, p, f, m, µ
from hdl21.primitives import Vdc, Vpulse, C, R

from ..comp import Comp, CompParams, comp_variants, is_valid_comp_params
from ..common.params import (
    Pvt,
    SupplyVals,
    Project,
    PreampDiffpair,
    PreampBias,
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    Vth,
)
from .sim_options import sim_options


# =============================================================================
# Monte Carlo Configuration (matches original blocks/comp.py)
# =============================================================================

@dataclass
class MCConfig:
    """Monte Carlo simulation configuration."""
    numruns: int = 10          # Default: 10 runs for quick characterization
    seed: int = 12345          # Fixed seed for reproducibility
    variations: str = "mismatch"  # Default: mismatch only (most relevant for comparator)


DEFAULT_MC_CONFIG = MCConfig()


# =============================================================================
# Testbench Parameters
# =============================================================================

@h.paramclass
class CompTbParams:
    """Comparator testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())
    vin_diff = h.Param(dtype=h.Scalar, desc="Differential input voltage", default=10 * m)
    vcm = h.Param(dtype=h.Scalar, desc="Common-mode voltage", default=600 * m)


# =============================================================================
# Testbench Generator
# =============================================================================

@h.generator
def CompTb(params: CompTbParams) -> h.Module:
    """
    Comparator testbench generator.

    Creates a testbench matching the original blocks/comp.py structure:
    - DC supplies
    - Common-mode voltage (configurable)
    - Symmetric differential inputs around CM
    - Source impedances (1kΩ + 100fF)
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
    # r=1kΩ, c=100fF
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
# Simulation Definitions
# =============================================================================

def sim_input(params: CompTbParams) -> hs.Sim:
    """
    Create deterministic transient simulation for comparator characterization.

    Matches original: tran(stop=5.5e-6)
    Saves: v(inp, inn, outp, outn, clk), i(Vvdd)
    """
    temp = Project.temper(params.pvt.t)

    @hs.sim
    class CompSim:
        tb = CompTb(params)

        # Transient analysis (matches original 5.5µs stop time)
        tr = hs.Tran(tstop=5500 * n, tstep=1 * n)

        # Measurements matching original measures dict
        t_delay = hs.Meas(
            analysis=tr,
            expr="trig V(xtop.clk) val=0.6 rise=1 targ V(xtop.outp) val=0.6 rise=1",
        )

        # Save key signals
        _ = hs.Save(hs.SaveMode.ALL)

        # Temperature setting
        temp_lit = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
        """
        )

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

    temp = Project.temper(params.pvt.t)

    @hs.sim
    class CompMcSim:
        tb = CompTb(params)

        # Base transient analysis
        tr = hs.Tran(tstop=5500 * n, tstep=1 * n)

        # Monte Carlo wrapper
        # Note: HDL21's MonteCarlo uses npts parameter
        # Spectre-specific options (seed, variations) go in Literal
        mc = hs.MonteCarlo(inner=[tr], npts=mc_config.numruns)

        # Save key signals
        _ = hs.Save(hs.SaveMode.ALL)

        # MC configuration and temperature
        mc_lit = hs.Literal(
            f"""
            simulator lang=spice
            .temp {temp}
            simulator lang=spectre
            // MC options: seed={mc_config.seed}, variations={mc_config.variations}
        """
        )

    return CompMcSim


# =============================================================================
# Sweep Functions
# =============================================================================

def run_scurve_sweep(
    comp_params: CompParams = None,
    pvt: Pvt = None,
) -> List[tuple]:
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
            # result = sim.run(sim_options)  # Would run simulation
            results.append(((vcm, vdiff), None))  # Placeholder

    return results


def run_topology_sweep(pvt: Pvt = None) -> List[tuple]:
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
        diffpair_w_list=[4 * µ],
    )

    for comp_params in variants:
        tb_params = CompTbParams(pvt=pvt, comp=comp_params)
        sim = sim_input(tb_params)
        # result = sim.run(sim_options)  # Would run simulation
        results.append((comp_params, None))  # Placeholder

    return results


def run_offset_monte_carlo(
    comp_params: CompParams = None,
    pvt: Pvt = None,
    mc_config: MCConfig = None,
) -> Dict[str, Any]:
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
# Measure Extraction Functions (matching original measures dict)
# =============================================================================

def extract_offset_mV(result: hs.SimResult) -> float:
    """
    Extract input-referred offset from S-curve data.

    Offset = differential voltage where P(out+ > out-) = 50%
    """
    # Would analyze simulation result to find offset
    return float("nan")


def extract_noise_sigma_mV(result: hs.SimResult) -> float:
    """
    Extract input-referred noise sigma from S-curve width.

    Noise sigma is derived from the slope of the S-curve at the transition.
    """
    return float("nan")


def extract_delay_ns(result: hs.SimResult) -> float:
    """
    Extract decision delay from simulation result.

    Delay = time from clock edge to output crossing VDD/2
    """
    try:
        return result.an[0].data.get("t_delay", float("nan"))
    except (IndexError, KeyError, AttributeError):
        return float("nan")


def extract_settling_ns(result: hs.SimResult, tolerance: float = 0.01) -> float:
    """
    Extract settling time from simulation result.

    Settling = time for output to reach within tolerance of final value
    """
    return float("nan")


def extract_power_uW(result: hs.SimResult) -> float:
    """
    Extract average power consumption.

    Power = average(V(vdd) * I(Vvdd)) during simulation
    """
    return float("nan")


# =============================================================================
# Test Functions
# =============================================================================

def test_comp_netlist():
    """Test that netlist generation works for all valid topologies."""
    count = 0
    for params in comp_variants():
        comp = Comp(params)
        h.netlist(comp, dest=io.StringIO())
        count += 1
    print(f"Generated {count} valid comparator netlists")


def test_comp_tb_netlist():
    """Test testbench netlist generation."""
    params = CompTbParams()
    tb = CompTb(params)
    h.netlist(tb, dest=io.StringIO())
    print("Comparator testbench netlist generated successfully")


def test_mc_sim_structure():
    """Test Monte Carlo simulation structure."""
    params = CompTbParams(vin_diff=0 * m)
    mc_config = MCConfig(numruns=10)
    sim = sim_input_with_mc(params, mc_config)
    print(f"MC simulation created with {mc_config.numruns} runs")
    print(f"  seed={mc_config.seed}, variations={mc_config.variations}")


if __name__ == "__main__":
    print("Testing comparator netlist generation...")
    test_comp_netlist()
    print()
    print("Testing comparator testbench netlist...")
    test_comp_tb_netlist()
    print()
    print("Testing Monte Carlo simulation structure...")
    test_mc_sim_structure()
