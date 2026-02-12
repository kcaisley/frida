"""
Simulation infrastructure for FRIDA HDL21.

Provides utilities for:
- Parameter sweeps (device types, sizing, PVT corners)
- Monte Carlo analysis
- Result extraction and post-processing
- Common testbench patterns
"""

from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Callable, Union

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.pdk import Corner
from hdl21.sim import to_proto
from vlsirtools.netlist import NetlistOptions
from vlsirtools.netlist.spectre import SpectreNetlister
from vlsirtools.netlist.spice import NgspiceNetlister, XyceNetlister
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from .params import Project, Pvt

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
Save = hs.Save
SaveMode = hs.SaveMode


# =============================================================================
# SIMULATION OPTIONS
# =============================================================================


# Default simulation options for Spectre
sim_options = SimOptions(
    rundir=Path("./scratch"),
    fmt=ResultFormat.SIM_DATA,
    simulator=SupportedSimulators.SPECTRE,
)


def get_sim_options(
    rundir: Path = None,
    simulator: SupportedSimulators = SupportedSimulators.SPECTRE,
) -> SimOptions:
    """
    Create simulation options with custom settings.

    Args:
        rundir: Directory for simulation files (None for temp dir)
        simulator: Simulator to use (SPECTRE, NGSPICE, etc.)

    Returns:
        SimOptions instance
    """
    return SimOptions(
        rundir=rundir,
        fmt=ResultFormat.SIM_DATA,
        simulator=simulator,
    )


# =============================================================================
# MONTE CARLO CONFIGURATION
# =============================================================================


@dataclass
class MCConfig:
    """Monte Carlo simulation configuration."""

    numruns: int = 10  # Fixed: 10 runs for manageability
    seed: int = 12345  # Fixed seed for reproducibility
    variations: str = "mismatch"  # Mismatch only (most relevant)


# =============================================================================
# SIMULATION CONFIGURATION
# =============================================================================


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
    save_signals: list[str] | None = None,
) -> hs.Sim:
    """
    Create a transient simulation.

    Args:
        tb: Testbench module
        tstop: Stop time
        tstep: Time step (optional)
        pvt: PVT conditions
        save_signals: List of signals to save (optional, in addition to save-all)
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

        # Temperature setting using hs.Options
        temp = hs.Options(name="temp", value=config.temp)

        # Always save all signals, plus any explicit list
        save_all = hs.Save(hs.SaveMode.ALL)

        # Save selected signals for waveform post-processing
        if save_signals:
            save = hs.Save(save_signals)

    return TranSim


def run_parameter_sweep(
    tb_generator: Callable,
    param_list: list[Any],
    sim_options,
    parallel: bool = True,
) -> list[hs.SimResult]:
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
    corners: list[Corner] = None,
    temps: list[int] = None,
    sim_options=None,
) -> dict[str, hs.SimResult]:
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
            # NOTE: temp is captured in pvt.t for tb_generator to use

            tb, sim = tb_generator(base_params, pvt)

            key = f"{corner.name}_{temp}C"
            result = sim.run(sim_options)
            results[key] = result

    return results


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


# =============================================================================
# NETLIST GENERATION
# =============================================================================


def write_sim_netlist(
    sim_class,
    dest: Union[str, Path, IO],
    compact: bool = True,
    simulator: SupportedSimulators = SupportedSimulators.SPECTRE,
) -> None:
    """
    Write simulation netlist to dest.

    Uses the same code path as actual Spectre simulation,
    ensuring NETLIST mode outputs match simulation inputs exactly.

    Args:
        sim_class: HDL21 Sim class (decorated with @hs.sim)
        dest: Output path or file-like object
        compact: Use compact instance formatting (default True)
        simulator: Target simulator/netlist dialect
    """
    proto = to_proto(sim_class)
    opts = NetlistOptions(compact=compact)

    netlister_cls = {
        SupportedSimulators.SPECTRE: SpectreNetlister,
        SupportedSimulators.NGSPICE: NgspiceNetlister,
        SupportedSimulators.XYCE: XyceNetlister,
    }[simulator]

    if isinstance(dest, (str, Path)):
        with open(dest, "w") as f:
            netlister = netlister_cls(dest=f, opts=opts)
            netlister.write_sim_input(proto)
    else:
        netlister = netlister_cls(dest=dest, opts=opts)
        netlister.write_sim_input(proto)
