"""
FRIDA HDL21 - Analog circuit generators using HDL21/VLSIR.

This package provides HDL21-based generators for FRIDA analog blocks
with a PDK abstraction layer supporting multiple process nodes.

Each block file (samp.py, comp.py, cdac.py) contains:
- Generator: @h.generator function creating the circuit
- Testbench: @h.generator for testbench + sim_input() for simulation
- Tests: test_* functions using pytest's simtestmode fixture
"""

# Generators and Testbenches
from .samp import Samp, SampParams, samp_variants, SampTb, SampTbParams
from .comp import (
    Comp, CompParams, comp_variants, is_valid_comp_params,
    CompTb, CompTbParams, MCConfig, DEFAULT_MC_CONFIG,
)
from .cdac import (
    Cdac, CdacParams, cdac_variants, is_valid_cdac_params, get_cdac_weights, get_cdac_n_bits,
    CdacTb, CdacTbParams,
)

# PDK
from .pdk import get_pdk, set_pdk, GenericPdk

# Common params and enums
from .common.params import (
    SwitchType,
    Vth,
    PreampDiffpair,
    PreampBias,
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    RedunStrat,
    SplitStrat,
    CapType,
    Pvt,
    SupplyVals,
    Project,
)

# Simulation options
from .common.sim_options import sim_options, get_sim_options

# Simulation infrastructure
from .sim import (
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
    SimConfig,
    create_tran_sim,
    run_parameter_sweep,
    run_pvt_sweep,
    run_monte_carlo,
    # Result extraction (some moved to measure.py)
    extract_waveform,
    extract_measurement,
    compute_settling_time,
    compute_delay,
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

# Pytest fixture
from .conftest import SimTestMode

__all__ = [
    # Generators
    "Samp",
    "SampParams",
    "samp_variants",
    "Comp",
    "CompParams",
    "comp_variants",
    "is_valid_comp_params",
    "Cdac",
    "CdacParams",
    "cdac_variants",
    "is_valid_cdac_params",
    "get_cdac_weights",
    "get_cdac_n_bits",
    # Testbenches
    "SampTb",
    "SampTbParams",
    "CompTb",
    "CompTbParams",
    "MCConfig",
    "DEFAULT_MC_CONFIG",
    "CdacTb",
    "CdacTbParams",
    # PDK
    "get_pdk",
    "set_pdk",
    "GenericPdk",
    # Enums
    "SwitchType",
    "Vth",
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
    # Simulation infrastructure
    "LinearSweep",
    "LogSweep",
    "PointSweep",
    "MonteCarlo",
    "SweepAnalysis",
    "Tran",
    "Dc",
    "Ac",
    "Op",
    "Meas",
    "Save",
    "SaveMode",
    "SimConfig",
    "create_tran_sim",
    "run_parameter_sweep",
    "run_pvt_sweep",
    "run_monte_carlo",
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
    # Pytest
    "SimTestMode",
]
