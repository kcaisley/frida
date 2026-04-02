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
    Cdac,
    CdacParams,
    CdacTb,
    CdacTbParams,
    get_cdac_n_bits,
    get_cdac_weights,
    is_valid_cdac_params,
)

# Common params and enums - from circuit module
from .circuit import (
    Ac,
    CapType,
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
    # CDAC enums
    RedunStrat,
    Save,
    SaveMode,
    SimConfig,
    SplitStrat,
    SupplyVals,
    SweepAnalysis,
    # Basic enums
    SwitchType,
    Tran,
    cdac_settling_ns,
    comp_delay_ns,
    comp_noise_sigma_mV,
    # Measurement functions
    comp_offset_mV,
    comp_power_uW,
    comp_settling_ns,
    compute_delay,
    compute_inl_dnl,
    compute_settling_time,
    # Plotting
    configure_matplotlib,
    # Simulation helpers
    create_tran_sim,
    # Result extraction
    extract_waveform,
    get_sim_options,
    mc_statistics,
    run_parameter_sweep,
    run_pvt_sweep,
    run_simulations,
    samp_charge_injection_mV,
    samp_settling_ns,
    save_plot,
    # Simulation options
    sim_options,
)
from .comp import Comp, CompParams, CompTb, CompTbParams, is_valid_comp_params
from .samp import Samp, SampParams, SampTb, SampTbParams

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
    # Pytest
]
