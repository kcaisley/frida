"""
Shared circuit infrastructure for FRIDA HDL21 generators.

Provides simulation, parameter, and netlist infrastructure. Numerical
post-processing lives in :mod:`flow.analysis`.
"""

# Parameters and enums
# Netlist utilities
from .netlist import (
    generate_staircase_pwl,
    get_param_axes,
    params_to_filename,
    print_netlist_summary,
    pwl_points_to_wave,
    pwl_to_spice_literal,
    run_netlist_variants,
    select_variants,
    wrap_monte_carlo,
)
from .params import (
    Project,
    # PVT and supply
    Pvt,
    SupplyVals,
    Tower180SupplyVals,
    Tsmc28SupplyVals,
    Tsmc65SupplyVals,
)

# Simulation infrastructure
from .sim import (
    Ac,
    Dc,
    # Sweep types
    LinearSweep,
    LogSweep,
    # Monte Carlo
    MCConfig,
    # Analysis types
    MonteCarlo,
    Op,
    PointSweep,
    Save,
    SaveMode,
    SimConfig,
    SweepAnalysis,
    Tran,
    compute_delay,
    compute_settling_time,
    # Simulation helpers
    create_tran_sim,
    # Result extraction
    extract_waveform,
    get_sim_options,
    run_parameter_sweep,
    run_pvt_sweep,
    run_simulations,
    # Simulation options
    sim_options,
    # Netlist generation
    write_sim_netlist,
)

__all__ = [
    # Enums
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
    "Save",
    "SaveMode",
    # Simulation helpers
    "create_tran_sim",
    "run_simulations",
    "run_parameter_sweep",
    "run_pvt_sweep",
    # Result extraction
    "extract_waveform",
    "compute_settling_time",
    "compute_delay",
    # Netlist generation
    "write_sim_netlist",
    # Netlist utilities
    "params_to_filename",
    "get_param_axes",
    "print_netlist_summary",
    "generate_staircase_pwl",
    "pwl_points_to_wave",
    "pwl_to_spice_literal",
    "run_netlist_variants",
    "select_variants",
    "wrap_monte_carlo",
]
