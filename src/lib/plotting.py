"""Plotting utilities for waveform visualization."""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict


def configure_fonts_for_pdf():
    """Configure fonts for PDF output (from analytic.py style)."""
    plt.rcParams.update({
        "text.usetex": False,  # Disable LaTeX for compatibility
        "font.family": "serif",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
    })


def get_scale_and_unit(data: np.ndarray, trace_name: str) -> tuple:
    """
    Determine appropriate scale factor and unit for trace data.

    Args:
        data: Array of values
        trace_name: Name of trace (to detect if voltage or current)

    Returns:
        Tuple of (scale_factor, unit_string)
    """
    # Detect if current or voltage
    is_current = trace_name.lower().startswith('i(')
    base_unit = 'A' if is_current else 'V'

    # Find max absolute value
    max_val = np.max(np.abs(data))

    if max_val == 0:
        return 1.0, base_unit

    # Auto-scale based on magnitude
    if base_unit == 'V':
        if max_val >= 1.0:
            return 1.0, 'V'
        elif max_val >= 1e-3:
            return 1e3, 'mV'
        elif max_val >= 1e-6:
            return 1e6, 'µV'
        else:
            return 1e9, 'nV'
    else:  # Current
        if max_val >= 1.0:
            return 1.0, 'A'
        elif max_val >= 1e-3:
            return 1e3, 'mA'
        elif max_val >= 1e-6:
            return 1e6, 'µA'
        elif max_val >= 1e-9:
            return 1e9, 'nA'
        else:
            return 1e12, 'pA'


def get_time_scale_and_unit(time: np.ndarray) -> tuple:
    """
    Determine appropriate scale factor and unit for time data.

    Args:
        time: Time array in seconds

    Returns:
        Tuple of (scale_factor, unit_string)
    """
    max_time = np.max(np.abs(time))

    if max_time == 0:
        return 1.0, 's'

    # Auto-scale time: s, ms, µs, ns, ps
    if max_time >= 1.0:
        return 1.0, 's'
    elif max_time >= 1e-3:
        return 1e3, 'ms'
    elif max_time >= 1e-6:
        return 1e6, 'µs'
    elif max_time >= 1e-9:
        return 1e9, 'ns'
    else:
        return 1e12, 'ps'


def should_plot_trace(trace_name: str) -> bool:
    """
    Determine if a trace should be plotted.

    Filters out:
    - Power supply traces (vdd*, vss*)
    - Time axis (shouldn't be in traces, but just in case)

    Args:
        trace_name: Name of the trace

    Returns:
        True if trace should be plotted, False otherwise
    """
    name_lower = trace_name.lower()

    # Filter out power supplies
    if name_lower.startswith('v(vdd') or name_lower.startswith('v(vss'):
        return False

    # Filter out time (shouldn't happen, but be safe)
    if name_lower == 'time':
        return False

    return True


def plot_all_traces(pdf_file: Path, time: np.ndarray, traces: Dict[str, np.ndarray]):
    """
    Plot all traces with auto-scaled axes to PDF.

    Args:
        pdf_file: Output PDF file path
        time: Time array
        traces: Dictionary of trace_name -> data_array
    """
    pdf_file.parent.mkdir(parents=True, exist_ok=True)

    # Configure PDF style
    configure_fonts_for_pdf()

    # Filter traces to plot
    filtered_traces = {name: data for name, data in traces.items() if should_plot_trace(name)}

    if not filtered_traces:
        print(f"    Warning: No traces to plot after filtering")
        return

    # Determine time scale
    time_scale, time_unit = get_time_scale_and_unit(time)
    time_scaled = time * time_scale

    # Create subplots - one per trace
    n_traces = len(filtered_traces)
    fig, axes = plt.subplots(n_traces, 1, figsize=(10, 2 * n_traces), sharex=True)

    # Handle single trace case
    if n_traces == 1:
        axes = [axes]

    # Plot each trace
    for ax, (name, data) in zip(axes, filtered_traces.items()):
        # Auto-scale data
        scale, unit = get_scale_and_unit(data, name)
        data_scaled = data * scale

        # Plot
        ax.plot(time_scaled, data_scaled)
        ax.set_ylabel(f'{name} [{unit}]')
        ax.grid(True, which="both", ls="--", alpha=0.5)

    # Set x-axis label on bottom plot only
    axes[-1].set_xlabel(f'Time [{time_unit}]')

    plt.tight_layout()
    plt.savefig(pdf_file)
    plt.close()
