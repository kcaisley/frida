"""
Shared test infrastructure for FRIDA HDL21 generators.

Provides:
- Simulation infrastructure (sim options, Monte Carlo config)
- Measurement functions for post-processing results
- Matplotlib plotting configuration
- Shared parameters (PVT, enums, supply values)
"""

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
    Save,
    SaveMode,
    # Simulation helpers
    create_tran_sim,
    run_parameter_sweep,
    run_pvt_sweep,
    # Result extraction
    extract_waveform,
    compute_settling_time,
    compute_delay,
    # Netlist generation
    write_sim_netlist,
)

# Measurement functions
from .measure import (
    # Simulation extraction
    sim_get_time,
    sim_get_waveform,
    sim_get_waveforms,
    sim_sample_at_edges,
    # Waveform utilities
    find_crossings,
    # Analog preprocessing
    diff_to_single,
    quantize_to_bits,
    # Digital processing
    redundant_bits_to_code,
    code_to_voltage,
    # Core measurements (numpy arrays)
    measure_settling,
    measure_delay,
    measure_average_power,
    measure_offset_crossing,
    measure_charge_injection,
    # Static linearity
    histogram_inl_dnl,
    endpoint_inl_dnl,
    find_code_transitions,
    compute_static_error,
    # Dynamic performance
    compute_enob_fft,
    # Monte Carlo
    mc_statistics,
    # Legacy API (backward compatibility)
    comp_offset_mV,
    comp_noise_sigma_mV,
    comp_delay_ns,
    comp_settling_ns,
    comp_power_uW,
    compute_inl_dnl,
    samp_settling_ns,
    samp_charge_injection_mV,
    cdac_settling_ns,
)

# Plotting
from .plot import (
    configure_matplotlib,
    save_plot,
    plot_inl_dnl,
    plot_histogram,
    plot_transfer_function,
    plot_fft_spectrum,
    plot_waveforms,
    plot_enob_vs_frequency,
    plot_monte_carlo_histogram,
)

# Netlist utilities
from .netlist import (
    generate_staircase_pwl,
    pwl_to_spice_literal,
    params_to_filename,
    get_param_axes,
    print_netlist_summary,
    run_netlist_variants,
    select_variants,
    wrap_monte_carlo,
)

__all__ = [
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
    "run_parameter_sweep",
    "run_pvt_sweep",
    # Result extraction
    "extract_waveform",
    "compute_settling_time",
    "compute_delay",
    # Netlist generation
    "write_sim_netlist",
    # Simulation extraction
    "sim_get_time",
    "sim_get_waveform",
    "sim_get_waveforms",
    "sim_sample_at_edges",
    # Waveform utilities
    "find_crossings",
    # Analog preprocessing
    "diff_to_single",
    "quantize_to_bits",
    # Digital processing
    "redundant_bits_to_code",
    "code_to_voltage",
    # Core measurements
    "measure_settling",
    "measure_delay",
    "measure_average_power",
    "measure_offset_crossing",
    "measure_charge_injection",
    # Static linearity
    "histogram_inl_dnl",
    "endpoint_inl_dnl",
    "find_code_transitions",
    "compute_static_error",
    # Dynamic performance
    "compute_enob_fft",
    # Monte Carlo
    "mc_statistics",
    # Legacy measurement API
    "comp_offset_mV",
    "comp_noise_sigma_mV",
    "comp_delay_ns",
    "comp_settling_ns",
    "comp_power_uW",
    "compute_inl_dnl",
    "samp_settling_ns",
    "samp_charge_injection_mV",
    "cdac_settling_ns",
    # Plotting
    "configure_matplotlib",
    "save_plot",
    "plot_inl_dnl",
    "plot_histogram",
    "plot_transfer_function",
    "plot_fft_spectrum",
    "plot_waveforms",
    "plot_enob_vs_frequency",
    "plot_monte_carlo_histogram",
    # Netlist utilities
    "params_to_filename",
    "get_param_axes",
    "print_netlist_summary",
    "generate_staircase_pwl",
    "pwl_to_spice_literal",
    "run_netlist_variants",
    "select_variants",
    "wrap_monte_carlo",
]
