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
from .samp import Samp, SampParams, SampTb, SampTbParams
from .comp import Comp, CompParams, is_valid_comp_params, CompTb, CompTbParams
from .cdac import (
    Cdac,
    CdacParams,
    is_valid_cdac_params,
    get_cdac_weights,
    get_cdac_n_bits,
    CdacTb,
    CdacTbParams,
)

# PDK
from .pdk import get_pdk, set_pdk, GenericPdk

# Common params and enums - from flow module
from .flow import (
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
    Project,
    # Simulation options
    sim_options,
    get_sim_options,
    # Monte Carlo
    MCConfig,
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
    # Result extraction
    extract_waveform,
    extract_measurement,
    compute_settling_time,
    compute_delay,
    # Measurement functions
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
    # Plotting
    configure_matplotlib,
    save_plot,
)

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
    # PDK
    "get_pdk",
    "set_pdk",
    "GenericPdk",
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
    "Meas",
    "Save",
    "SaveMode",
    # Simulation helpers
    "create_tran_sim",
    "run_parameter_sweep",
    "run_pvt_sweep",
    "extract_waveform",
    "extract_measurement",
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
