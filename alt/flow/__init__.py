"""
Shared test infrastructure for FRIDA HDL21 generators.

Provides:
- SimTestMode enum and pytest fixture for controlling test depth
- Simulation infrastructure (sim options, Monte Carlo config)
- Measurement functions for post-processing results
- Matplotlib plotting configuration
- Shared parameters (PVT, enums, supply values)
"""

# Pytest configuration
from .params import SimTestMode

# Parameters and enums
from .params import (
    # Basic enums
    SwitchType,
    # Comparator enums
    PreampDiffpair,
    PreampBias,
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    # CDAC enums
    RedunStrat,
    SplitStrat,
    CapType,
    # PVT and supply
    Pvt,
    SupplyVals,
    Tsmc65SupplyVals,
    Tsmc28SupplyVals,
    Tower180SupplyVals,
    Project,
)

# Simulation infrastructure
from .sim import (
    # Simulation options
    sim_options,
    get_sim_options,
    # Monte Carlo
    MCConfig,
    DEFAULT_MC_CONFIG,
    SimConfig,
    # Sweep types
    LinearSweep,
    LogSweep,
    PointSweep,
    # Analysis types
    MonteCarlo,
    SweepAnalysis,
    Tran,
    Dc,
    Ac,
    Op,
    Meas,
    Save,
    SaveMode,
    # Simulation helpers
    create_tran_sim,
    run_parameter_sweep,
    run_pvt_sweep,
    run_monte_carlo,
    # Result extraction
    extract_waveform,
    extract_measurement,
    compute_settling_time,
    compute_delay,
    # Netlist generation
    write_sim_netlist,
)

# Measurement functions
from .measure import (
    comp_offset_mV,
    comp_noise_sigma_mV,
    comp_delay_ns,
    comp_settling_ns,
    comp_power_uW,
    compute_inl_dnl,
    mc_statistics,
    samp_settling_ns,
    samp_charge_injection_mV,
    cdac_settling_ns,
)

# Plotting
from .plot import configure_matplotlib, save_plot

__all__ = [
    # Pytest
    "SimTestMode",
    # Enums
    "SwitchType",
    "PreampDiffpair",
    "PreampBias",
    "CompStages",
    "LatchPwrgateCtl",
    "LatchPwrgateNode",
    "LatchRstExternCtl",
    "LatchRstInternCtl",
    "RedunStrat",
    "SplitStrat",
    "CapType",
    # PVT and supply
    "Pvt",
    "SupplyVals",
    "Tsmc65SupplyVals",
    "Tsmc28SupplyVals",
    "Tower180SupplyVals",
    "Project",
    # Simulation options
    "sim_options",
    "get_sim_options",
    # Monte Carlo
    "MCConfig",
    "DEFAULT_MC_CONFIG",
    "SimConfig",
    # Sweep types
    "LinearSweep",
    "LogSweep",
    "PointSweep",
    # Analysis types
    "MonteCarlo",
    "SweepAnalysis",
    "Tran",
    "Dc",
    "Ac",
    "Op",
    "Meas",
    "Save",
    "SaveMode",
    # Simulation helpers
    "create_tran_sim",
    "run_parameter_sweep",
    "run_pvt_sweep",
    "run_monte_carlo",
    # Result extraction
    "extract_waveform",
    "extract_measurement",
    "compute_settling_time",
    "compute_delay",
    # Netlist generation
    "write_sim_netlist",
    # Measurement functions
    "comp_offset_mV",
    "comp_noise_sigma_mV",
    "comp_delay_ns",
    "comp_settling_ns",
    "comp_power_uW",
    "compute_inl_dnl",
    "mc_statistics",
    "samp_settling_ns",
    "samp_charge_injection_mV",
    "cdac_settling_ns",
    # Plotting
    "configure_matplotlib",
    "save_plot",
]
