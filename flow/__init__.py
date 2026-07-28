"""
FRIDA HDL21 - Analog circuit generators using HDL21/VLSIR.

This package provides HDL21-based generators for FRIDA analog blocks
with a PDK abstraction layer supporting multiple process nodes.

Each block module (comp/, samp/, cdac/) contains:
- Generator: @h.generator function creating the circuit
- Testbench: @h.generator for testbench + sim_input() for simulation
- Tests: test_* functions using pytest flow/mode flags
"""

# Generators and Testbenches - from per-block modules
from .cdac import (
    CapType,
    Cdac,
    CdacParams,
    CdacTb,
    CdacTbParams,
    RedunStrat,
    SplitStrat,
    get_cdac_n_bits,
    get_cdac_weights,
    is_valid_cdac_params,
)

# Common params and enums - from circuit module
from .circuit import (
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
    Project,
    # PVT and supply
    Pvt,
    Save,
    SaveMode,
    SimConfig,
    SupplyVals,
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
)
from .comp import Comp, CompParams, CompTb, CompTbParams, is_valid_comp_params
from .samp import Samp, SampParams, SampTb, SampTbParams, SwitchType

__all__ = [
    # Generators
    "Samp",
    "SampParams",
    "Comp",
    "CompParams",
    "is_valid_comp_params",
    "Cdac",
    "CdacParams",
    "is_valid_cdac_params",
    "get_cdac_weights",
    "get_cdac_n_bits",
    # Testbenches
    "SampTb",
    "SampTbParams",
    "CompTb",
    "CompTbParams",
    "CdacTb",
    "CdacTbParams",
    # Enums
    "SwitchType",
    "RedunStrat",
    "SplitStrat",
    "CapType",
    "Pvt",
    "SupplyVals",
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
    "extract_waveform",
    "compute_settling_time",
    "compute_delay",
    # Pytest
]
