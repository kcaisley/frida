"""
Simulation infrastructure for FRIDA HDL21.

Provides utilities for:
- Parameter sweeps (device types, sizing, PVT corners)
- Monte Carlo analysis
- Result extraction and post-processing
- Common testbench patterns
"""

from copy import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.pdk import Corner
from hdl21.prefix import f, m, n, p, µ
from hdl21.primitives import C, Vdc, Vpulse

from .common.params import Project, Pvt, SupplyVals

# Re-export HDL21 sim types for convenience
LinearSweep = hs.LinearSweep
LogSweep = hs.LogSweep
PointSweep = hs.PointSweep
MonteCarlo = hs.MonteCarlo
SweepAnalysis = hs.SweepAnalysis
Tran = hs.Tran
Dc = hs.Dc
Ac = hs.Ac
Op = hs.Op
Meas = hs.Meas
Save = hs.Save
SaveMode = hs.SaveMode


@dataclass
class SimConfig:
    """Configuration for a simulation run."""

    pvt: Pvt
    temp: int = None  # If None, derived from PVT

    def __post_init__(self):
        if self.temp is None:
            self.temp = Project.temper(self.pvt.t)


def create_tran_sim(
    tb: h.Module,
    tstop: h.Scalar,
    tstep: h.Scalar = None,
    pvt: Pvt = None,
    measurements: Dict[str, str] = None,
    monte_carlo: int = None,
) -> hs.Sim:
    """
    Create a transient simulation with optional Monte Carlo.

    Args:
        tb: Testbench module
        tstop: Stop time
        tstep: Time step (optional)
        pvt: PVT conditions
        measurements: Dict of measurement name -> expression
        monte_carlo: Number of Monte Carlo runs (None = no MC)

    Returns:
        hs.Sim object ready to run
    """
    if pvt is None:
        pvt = Pvt()

    config = SimConfig(pvt=pvt)

    @hs.sim
    class TranSim:
        tb_inst = tb

        # Base transient analysis
        tr = hs.Tran(tstop=tstop, tstep=tstep)

        # Temperature setting
        # Use _ for Literal (frozen dataclass, has no name field)
        _ = hs.Literal(
            f"""
            simulator lang=spice
            .temp {config.temp}
            simulator lang=spectre
        """
        )

    # Add measurements
    if measurements:
        for name, expr in measurements.items():
            TranSim.add(hs.Meas(analysis=TranSim.tr, expr=expr, name=name))

    # Wrap in Monte Carlo if requested
    if monte_carlo and monte_carlo > 1:
        mc = hs.MonteCarlo(inner=[TranSim.tr], npts=monte_carlo)
        TranSim.add(mc)

    return TranSim


def run_parameter_sweep(
    tb_generator: Callable,
    param_list: List[Any],
    sim_options,
    parallel: bool = True,
) -> List[hs.SimResult]:
    """
    Run simulations across a list of parameter configurations.

    This is for sweeping Python-level parameters (device types, sizing, etc.)
    that require different circuit topologies.

    Args:
        tb_generator: Function that takes params and returns (tb, sim) tuple
        param_list: List of parameter configurations
        sim_options: vlsirtools SimOptions
        parallel: Run simulations in parallel

    Returns:
        List of SimResult objects
    """
    sims = []
    for params in param_list:
        tb, sim = tb_generator(params)
        sims.append(sim)

    if parallel:
        return h.sim.run(sims, sim_options)
    else:
        return [sim.run(sim_options) for sim in sims]


def run_pvt_sweep(
    tb_generator: Callable,
    base_params: Any,
    corners: List[Corner] = None,
    temps: List[int] = None,
    sim_options=None,
) -> Dict[str, hs.SimResult]:
    """
    Run simulations across PVT corners.

    Args:
        tb_generator: Function that takes (params, pvt) and returns (tb, sim)
        base_params: Base parameter configuration
        corners: List of process corners (default: TYP, FAST, SLOW)
        temps: List of temperatures (default: -40, 25, 125)
        sim_options: vlsirtools SimOptions

    Returns:
        Dict mapping (corner, temp) string to SimResult
    """
    if corners is None:
        corners = [Corner.TYP, Corner.FAST, Corner.SLOW]
    if temps is None:
        temps = [-40, 25, 125]

    results = {}
    for corner in corners:
        for temp in temps:
            pvt = Pvt(p=corner, v=corner, t=corner)
            # Override temperature
            config = SimConfig(pvt=pvt, temp=temp)

            tb, sim = tb_generator(base_params, pvt)

            key = f"{corner.name}_{temp}C"
            result = sim.run(sim_options)
            results[key] = result

    return results


def run_monte_carlo(
    tb_generator: Callable,
    params: Any,
    n_runs: int,
    sim_options=None,
) -> hs.SimResult:
    """
    Run Monte Carlo simulation.

    Args:
        tb_generator: Function that takes params and returns (tb, sim)
        params: Parameter configuration
        n_runs: Number of Monte Carlo iterations
        sim_options: vlsirtools SimOptions

    Returns:
        SimResult with Monte Carlo data
    """
    tb, base_sim = tb_generator(params)

    # Get the transient analysis from the sim
    tran_analysis = None
    for attr in base_sim.attrs:
        if isinstance(attr, hs.Tran):
            tran_analysis = attr
            break

    if tran_analysis is None:
        raise ValueError("No transient analysis found in simulation")

    # Create Monte Carlo wrapper
    mc = hs.MonteCarlo(inner=[tran_analysis], npts=n_runs)
    base_sim.add(mc)

    return base_sim.run(sim_options)


# =============================================================================
# Result Extraction Utilities
# =============================================================================


def extract_waveform(
    result: hs.SimResult,
    signal: str,
    analysis_idx: int = 0,
) -> tuple:
    """
    Extract time and voltage waveform from simulation result.

    Args:
        result: SimResult object
        signal: Signal name (e.g., "v(out)" or "xtop.out")
        analysis_idx: Index of analysis (for multiple analyses)

    Returns:
        Tuple of (time_array, voltage_array)
    """
    data = result.an[analysis_idx].data
    time = data.get("time", data.get("TIME"))
    voltage = data.get(signal, data.get(f"v({signal})"))
    return time, voltage


def extract_measurement(
    result: hs.SimResult,
    meas_name: str,
) -> float:
    """
    Extract a measurement value from simulation result.

    Args:
        result: SimResult object
        meas_name: Measurement name

    Returns:
        Measurement value as float
    """
    try:
        return result.an[0].data.get(meas_name, float("nan"))
    except (IndexError, KeyError, AttributeError):
        return float("nan")


def compute_settling_time(
    time: np.ndarray,
    voltage: np.ndarray,
    final_value: float,
    tolerance: float = 0.01,
) -> float:
    """
    Compute settling time to within tolerance of final value.

    Args:
        time: Time array
        voltage: Voltage array
        final_value: Expected final value
        tolerance: Relative tolerance (default 1%)

    Returns:
        Settling time in same units as time array
    """
    threshold = final_value * tolerance
    settled = np.abs(voltage - final_value) < threshold

    # Find first time that stays settled
    for i in range(len(settled)):
        if np.all(settled[i:]):
            return time[i]

    return float("nan")


def compute_delay(
    time: np.ndarray,
    sig_in: np.ndarray,
    sig_out: np.ndarray,
    threshold: float = 0.5,
) -> float:
    """
    Compute propagation delay between input and output crossing threshold.

    Args:
        time: Time array
        sig_in: Input signal array
        sig_out: Output signal array
        threshold: Crossing threshold (normalized 0-1)

    Returns:
        Delay time
    """
    # Find input crossing
    in_max, in_min = np.max(sig_in), np.min(sig_in)
    in_thresh = in_min + threshold * (in_max - in_min)
    in_cross_idx = np.where(np.diff(np.sign(sig_in - in_thresh)))[0]

    # Find output crossing
    out_max, out_min = np.max(sig_out), np.min(sig_out)
    out_thresh = out_min + threshold * (out_max - out_min)
    out_cross_idx = np.where(np.diff(np.sign(sig_out - out_thresh)))[0]

    if len(in_cross_idx) == 0 or len(out_cross_idx) == 0:
        return float("nan")

    # First rising edge delay
    t_in = time[in_cross_idx[0]]
    t_out = time[out_cross_idx[0]]

    return t_out - t_in


def compute_inl_dnl(
    codes: np.ndarray,
    outputs: np.ndarray,
) -> Dict[str, Any]:
    """
    Compute INL and DNL from code sweep results.

    Args:
        codes: Array of DAC codes
        outputs: Array of corresponding output values

    Returns:
        Dict with 'inl', 'dnl', 'inl_max', 'dnl_max' arrays/values
    """
    n_codes = len(codes)

    # Ideal LSB from endpoint fit
    lsb_ideal = (outputs[-1] - outputs[0]) / (n_codes - 1)

    # DNL: difference from ideal step
    steps = np.diff(outputs)
    dnl = (steps / lsb_ideal) - 1

    # INL: cumulative deviation from ideal line
    ideal_line = outputs[0] + np.arange(n_codes) * lsb_ideal
    inl = (outputs - ideal_line) / lsb_ideal

    return {
        "dnl": dnl,
        "inl": inl,
        "dnl_max": np.max(np.abs(dnl)),
        "inl_max": np.max(np.abs(inl)),
        "lsb": lsb_ideal,
    }


# =============================================================================
# Monte Carlo Statistics
# =============================================================================


def mc_statistics(
    results: List[float],
) -> Dict[str, float]:
    """
    Compute statistics from Monte Carlo results.

    Args:
        results: List of scalar results from MC runs

    Returns:
        Dict with mean, std, min, max, 3sigma values
    """
    arr = np.array(results)
    return {
        "mean": np.mean(arr),
        "std": np.std(arr),
        "min": np.min(arr),
        "max": np.max(arr),
        "sigma3_low": np.mean(arr) - 3 * np.std(arr),
        "sigma3_high": np.mean(arr) + 3 * np.std(arr),
    }
