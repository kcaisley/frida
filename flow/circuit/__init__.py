"""
Shared circuit infrastructure for FRIDA HDL21 generators.

Provides:
- Simulation infrastructure (sim options, Monte Carlo config)
- Measurement functions for post-processing results
- Matplotlib plotting configuration
- Shared parameters (PVT, enums, supply values)
- Netlist generation utilities
"""

# Parameters and enums
# Measurement functions
from .measure import (
    cdac_settling_ns,
    code_to_voltage,
    comp_delay_ns,
    comp_noise_sigma_mV,
    # Legacy API (backward compatibility)
    comp_offset_mV,
    comp_power_uW,
    comp_settling_ns,
    # Dynamic performance
    compute_enob_fft,
    compute_inl_dnl,
    compute_static_error,
    # Analog preprocessing
    diff_to_single,
    endpoint_inl_dnl,
    find_code_transitions,
    # Waveform utilities
    find_crossings,
    # Static linearity
    histogram_inl_dnl,
    # Monte Carlo
    mc_statistics,
    measure_average_power,
    measure_charge_injection,
    measure_delay,
    measure_offset_crossing,
    # Core measurements (numpy arrays)
    measure_settling,
    quantize_to_bits,
    # Digital processing
    redundant_bits_to_code,
    samp_charge_injection_mV,
    samp_settling_ns,
    # Simulation extraction
    sim_get_time,
    sim_get_waveform,
    sim_get_waveforms,
    sim_sample_at_edges,
)

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
    CapType,
    CompStages,
    LatchPwrgateCtl,
    LatchPwrgateNode,
    LatchRstExternCtl,
    LatchRstInternCtl,
    PreampBias,
    Project,
    # PVT and supply
    Pvt,
    # CDAC enums
    RedunStrat,
    SplitStrat,
    SupplyVals,
    # Basic enums
    SwitchType,
    Tower180SupplyVals,
    Tsmc28SupplyVals,
    Tsmc65SupplyVals,
)

# Plotting
from .plot import (
    configure_matplotlib,
    plot_enob_vs_frequency,
    plot_fft_spectrum,
    plot_histogram,
    plot_inl_dnl,
    plot_monte_carlo_histogram,
    plot_transfer_function,
    plot_waveforms,
    save_plot,
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
    "SwitchType",
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
    "run_simulations",
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
    "pwl_points_to_wave",
    "pwl_to_spice_literal",
    "run_netlist_variants",
    "select_variants",
    "wrap_monte_carlo",
]
