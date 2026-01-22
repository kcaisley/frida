"""Utilities for loading and plotting analysis results."""

import datetime
from pathlib import Path
import importlib.util
import logging
import sys
import numpy as np
import matplotlib.pyplot as plt

from flow.common import setup_logging


def load_analysis(pkl_file):
    """
    Load analysis file and return dict of all variables.

    Usage:
        data = load_analysis('results_analysis.pkl')
        locals().update(data)
    """
    import pickle

    with open(pkl_file, "rb") as f:
        return pickle.load(f)


def load_analysis_vars(pkl_file, globals_dict=None, locals_dict=None):
    """
    Load analysis and inject variables into namespace.

    Usage:
        load_analysis_vars('results_analysis.pkl', globals(), locals())
    """
    data = load_analysis(pkl_file)
    if locals_dict is not None:
        locals_dict.update(data)
    if globals_dict is not None:
        globals_dict.update(data)
    return data


def load_analysis_module(analysis_file):
    """Load analysis module from file path."""
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    spec = importlib.util.spec_from_file_location("analysis", analysis_file)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load analysis module from {analysis_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["analysis"] = module
    spec.loader.exec_module(module)
    return module


def configure_fonts_for_pdf():
    """Configure LaTeX fonts for PDF output"""
    plt.rcParams.update(
        {
            "text.usetex": True,  # Use LaTeX for text rendering
            "font.family": "serif",  # Use serif (LaTeX default)
            "font.serif": ["Computer Modern Roman"],  # LaTeX default font
            "font.size": 11,  # Base font size
            "axes.titlesize": 12,  # Title font size
            "axes.labelsize": 11,  # Axis label font size
            "xtick.labelsize": 10,  # X-tick label size
            "ytick.labelsize": 10,  # Y-tick label size
            "legend.fontsize": 10,  # Legend font size
        }
    )


def configure_fonts_for_svg():
    """Configure sans-serif fonts for SVG output"""
    plt.rcParams.update(
        {
            "text.usetex": False,  # Disable LaTeX for SVG
            "font.family": "sans-serif",  # Use sans-serif
            "font.sans-serif": [
                "DejaVu Sans",
                "Arial",
                "Helvetica",
            ],  # Default sans-serif fonts
            "font.size": 11,  # Base font size
            "axes.titlesize": 12,  # Title font size
            "axes.labelsize": 11,  # Axis label font size
            "xtick.labelsize": 10,  # X-tick label size
            "ytick.labelsize": 10,  # Y-tick label size
            "legend.fontsize": 10,  # Legend font size
        }
    )


def save_plot(filename_base):
    """
    Save plot in both PDF and SVG formats with appropriate font settings.

    Args:
        filename_base: Base filename without extension (e.g., 'build/figure_name')
    """
    # Save PDF version with LaTeX fonts
    configure_fonts_for_pdf()
    plt.tight_layout()
    plt.savefig(f"{filename_base}.pdf")

    # Save SVG version with sans-serif fonts
    configure_fonts_for_svg()
    plt.tight_layout()
    plt.savefig(f"{filename_base}.svg")


# Initialize with PDF configuration as default
configure_fonts_for_pdf()


def plot_dnl_histogram_legacy(
    dout_rounded, dnl_hist, code_counts, dnl_rms, title="DNL Code Density"
):
    """
    Plot DNL using histogram/code density (legacy spice.py style).

    Creates a 2x2 subplot with width ratios [1, 2]:
    - Left: horizontal bar chart of DNL per code
    - Right: transfer function and error plots

    Parameters:
        dout_rounded: numpy array of rounded output codes
        dnl_hist: numpy array of DNL values per code (from calculate_dnl_histogram)
        code_counts: dict mapping code -> count
        dnl_rms: RMS DNL value
        title: plot title

    Returns:
        fig, axes: matplotlib figure and axes objects
    """
    fig, axes = plt.subplots(
        2, 2, figsize=(12, 8), gridspec_kw={"width_ratios": [1, 2]}
    )
    fig.suptitle(title)

    axes = axes.flatten()

    # Plot 1: Horizontal bar chart of DNL per code (legacy style)
    ax = axes[0]
    codes = sorted(code_counts.keys())
    dnl_by_code = []
    for code in codes:
        idx = list(code_counts.keys()).index(code)
        dnl_by_code.append(dnl_hist[idx])

    ax.barh(codes, dnl_by_code, label=f"DNL (RMS = {dnl_rms:.4f})")
    ax.axvline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_ylabel("Output Code")
    ax.set_xlabel("DNL [LSB]")
    ax.set_title("DNL per Code")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Plot 2: Transfer function (shares y-axis with plot 1)
    ax = axes[1]
    ax.plot(range(len(dout_rounded)), dout_rounded, "b-", linewidth=0.5)
    ax.sharey(axes[0])
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Output Code")
    ax.set_title("Transfer Function")
    ax.grid(True, alpha=0.3)

    # Plot 3: Turn off (legacy style)
    axes[2].axis("off")

    # Plot 4: Error plot (shares x-axis with plot 2)
    ax = axes[3]
    # Calculate error from linear fit
    sample_idx = np.arange(len(dout_rounded))
    coeffs = np.polyfit(sample_idx, dout_rounded, 1)
    dout_linear = np.polyval(coeffs, sample_idx)
    error = dout_rounded - dout_linear

    ax.plot(sample_idx, error, "r-", linewidth=0.5, label="Error")
    ax.sharex(axes[1])
    ax.axhline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Error [LSB]")
    ax.set_title("Linearity Error")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig, axes


def plot_inl_dnl(
    vin,
    dout_analog,
    inl,
    dnl,
    inl_rms,
    inl_max,
    dnl_rms,
    dnl_max,
    title="ADC/DAC Linearity",
):
    """
    Plot INL and DNL analysis results.

    Parameters:
        vin: numpy array of input voltages
        dout_analog: numpy array of reconstructed analog output
        inl: numpy array of INL values
        dnl: numpy array of DNL values (length = len(vin) - 1)
        inl_rms: RMS INL value
        inl_max: worst-case INL value
        dnl_rms: RMS DNL value
        dnl_max: worst-case DNL value
        title: plot title

    Returns:
        fig, axes: matplotlib figure and axes objects
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(title)

    # Plot 1: Transfer function (Dout vs Vin)
    ax = axes[0, 0]
    ax.plot(vin, dout_analog, "b-", linewidth=1, label="Actual")
    ax.set_xlabel("Input Voltage [V]")
    ax.set_ylabel("Output Code [V or LSB]")
    ax.set_title("Transfer Function")
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Plot 2: INL vs Vin
    ax = axes[0, 1]
    ax.plot(vin, inl, "r-", linewidth=1)
    ax.axhline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Input Voltage [V]")
    ax.set_ylabel("INL [LSB]")
    ax.set_title(f"INL (RMS={inl_rms:.4f}, Max={inl_max:.4f})")
    ax.grid(True, alpha=0.3)

    # Plot 3: DNL histogram
    ax = axes[1, 0]
    ax.hist(dnl, bins=50, edgecolor="black", alpha=0.7)
    ax.axvline(0, color="r", linestyle="--", linewidth=1, label="Ideal")
    ax.set_xlabel("DNL [LSB]")
    ax.set_ylabel("Count")
    ax.set_title(f"DNL Histogram (RMS={dnl_rms:.4f}, Max={dnl_max:.4f})")
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Plot 4: DNL vs Code
    ax = axes[1, 1]
    ax.plot(dnl, "g-", linewidth=1)
    ax.axhline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Code Index")
    ax.set_ylabel("DNL [LSB]")
    ax.set_title("DNL vs Code")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig, axes


def plot_dnl_histogram_legacy_compare(datasets, labels, title="DNL Comparison"):
    """
    Compare DNL histograms from multiple datasets (legacy spice.py style).

    Parameters:
        datasets: list of dicts, each containing:
            {'dout_rounded', 'dnl_hist', 'code_counts', 'dnl_rms'}
        labels: list of strings for legend labels
        title: plot title

    Returns:
        fig, axes: matplotlib figure and axes objects
    """
    fig, axes = plt.subplots(
        2, 2, figsize=(12, 8), gridspec_kw={"width_ratios": [1, 2]}
    )
    fig.suptitle(title)

    axes = axes.flatten()
    colors = plt.cm.tab10(range(len(datasets)))

    # Plot 1: Horizontal bar chart of DNL per code (overlaid)
    ax = axes[0]
    for i, (data, label, color) in enumerate(zip(datasets, labels, colors)):
        codes = sorted(data["code_counts"].keys())
        dnl_by_code = []
        for code in codes:
            idx = list(data["code_counts"].keys()).index(code)
            dnl_by_code.append(data["dnl_hist"][idx])

        ax.barh(
            codes,
            dnl_by_code,
            alpha=0.6,
            color=color,
            label=f"{label} (RMS={data['dnl_rms']:.4f})",
        )

    ax.axvline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_ylabel("Output Code")
    ax.set_xlabel("DNL [LSB]")
    ax.set_title("DNL per Code")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Plot 2: Transfer functions (shares y-axis with plot 1)
    ax = axes[1]
    for i, (data, label, color) in enumerate(zip(datasets, labels, colors)):
        ax.plot(
            range(len(data["dout_rounded"])),
            data["dout_rounded"],
            color=color,
            linewidth=0.5,
            label=label,
            alpha=0.7,
        )
    ax.sharey(axes[0])
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Output Code")
    ax.set_title("Transfer Functions")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Plot 3: Turn off (legacy style)
    axes[2].axis("off")

    # Plot 4: Error plots (shares x-axis with plot 2)
    ax = axes[3]
    for i, (data, label, color) in enumerate(zip(datasets, labels, colors)):
        dout_rounded = data["dout_rounded"]
        sample_idx = np.arange(len(dout_rounded))
        coeffs = np.polyfit(sample_idx, dout_rounded, 1)
        dout_linear = np.polyval(coeffs, sample_idx)
        error = dout_rounded - dout_linear

        ax.plot(sample_idx, error, color=color, linewidth=0.5, label=label, alpha=0.7)

    ax.sharex(axes[1])
    ax.axhline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Error [LSB]")
    ax.set_title("Linearity Error")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig, axes


def plot_inl_dnl_compare(datasets, labels, title="ADC/DAC Linearity Comparison"):
    """
    Compare INL and DNL from multiple datasets on the same plots.

    Parameters:
        datasets: list of dicts, each containing:
            {'vin', 'dout_analog', 'inl', 'dnl', 'inl_rms', 'inl_max', 'dnl_rms', 'dnl_max'}
        labels: list of strings for legend labels
        title: plot title

    Returns:
        fig, axes: matplotlib figure and axes objects
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(title)

    colors = plt.cm.tab10(range(len(datasets)))

    # Plot 1: Transfer functions
    ax = axes[0, 0]
    for i, (data, label) in enumerate(zip(datasets, labels)):
        ax.plot(
            data["vin"],
            data["dout_analog"],
            color=colors[i],
            linewidth=1,
            label=label,
            alpha=0.7,
        )
    ax.set_xlabel("Input Voltage [V]")
    ax.set_ylabel("Output Code [V or LSB]")
    ax.set_title("Transfer Function")
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Plot 2: INL comparison
    ax = axes[0, 1]
    for i, (data, label) in enumerate(zip(datasets, labels)):
        ax.plot(
            data["vin"],
            data["inl"],
            color=colors[i],
            linewidth=1,
            label=f"{label} (RMS={data['inl_rms']:.4f})",
            alpha=0.7,
        )
    ax.axhline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Input Voltage [V]")
    ax.set_ylabel("INL [LSB]")
    ax.set_title("INL Comparison")
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Plot 3: DNL comparison (histogram overlay)
    ax = axes[1, 0]
    for i, (data, label) in enumerate(zip(datasets, labels)):
        ax.hist(
            data["dnl"],
            bins=30,
            alpha=0.5,
            label=label,
            color=colors[i],
            edgecolor="black",
        )
    ax.axvline(0, color="r", linestyle="--", linewidth=1)
    ax.set_xlabel("DNL [LSB]")
    ax.set_ylabel("Count")
    ax.set_title("DNL Histogram")
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Plot 4: DNL vs Code comparison
    ax = axes[1, 1]
    for i, (data, label) in enumerate(zip(datasets, labels)):
        ax.plot(
            data["dnl"],
            color=colors[i],
            linewidth=1,
            label=f"{label} (RMS={data['dnl_rms']:.4f})",
            alpha=0.7,
        )
    ax.axhline(0, color="k", linestyle="--", linewidth=0.5)
    ax.set_xlabel("Code Index")
    ax.set_ylabel("DNL [LSB]")
    ax.set_title("DNL vs Code")
    ax.grid(True, alpha=0.3)
    ax.legend()

    plt.tight_layout()
    return fig, axes


def plot_code_density(dout_codes, bins="auto", title="Code Density"):
    """
    Plot histogram showing code density (useful for DNL visualization).

    Parameters:
        dout_codes: numpy array of output codes (integers or rounded values)
        bins: number of bins or 'auto'
        title: plot title

    Returns:
        fig, ax: matplotlib figure and axis objects
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    counts, edges, patches = ax.hist(
        dout_codes, bins=bins, edgecolor="black", alpha=0.7
    )

    # Calculate average count and mark deviations
    avg_count = np.mean(counts)
    ax.axhline(
        avg_count,
        color="r",
        linestyle="--",
        linewidth=1,
        label=f"Average ({avg_count:.1f})",
    )

    ax.set_xlabel("Output Code")
    ax.set_ylabel("Count")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()

    plt.tight_layout()
    return fig, ax


def main():
    """Main entry point for plotting."""
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Generate plots from measurement results"
    )
    parser.add_argument(
        "analysis_file",
        type=Path,
        help="Path to analysis.py script (e.g., blocks/comp.py)",
    )
    parser.add_argument(
        "meas_dir", type=Path, help="Directory containing .pkl measurement files"
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Output directory for plots (default: same as meas_dir)",
    )
    args = parser.parse_args()

    # Setup logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cell_name = args.analysis_file.stem
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"plot_{cell_name}_{timestamp}.log"
    logger = setup_logging(log_file)

    logger.info("=" * 70)
    logger.info("Plot Generation")
    logger.info("=" * 70)
    logger.info(f"Analysis file: {args.analysis_file}")
    logger.info(f"Meas dir:      {args.meas_dir}")
    logger.info(f"Log file:      {log_file}")
    logger.info("=" * 70)

    # Load analysis module
    analysis_module = load_analysis_module(args.analysis_file)

    # Check if plot() function exists
    if not hasattr(analysis_module, "plot"):
        logger.warning(f"{args.analysis_file} does not have a plot() function")
        logger.info("No plots generated.")
        return 0

    # Set output directory
    outdir = args.outdir if args.outdir else args.meas_dir
    outdir.mkdir(parents=True, exist_ok=True)

    # Store outdir in sys for access by plot functions
    sys._plot_outdir = str(outdir)

    # Call the plot function
    analysis_module.plot(str(args.meas_dir), str(outdir))

    logger.info(f"\nPlots saved to: {outdir}")
    logger.info("=" * 70)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())


# ========================================================================
# Analytic Plot Functions - from src/analytic.py
# ========================================================================


def plot_qnoise_vs_bits(Nbits_range, Vrefs, outdir="build", filename="qnoise"):
    """
    Plot quantization noise vs number of bits for different reference voltages.

    Args:
        Nbits_range: List of bit resolutions to plot
        Vrefs: List of reference voltages
        outdir: Output directory
        filename: Output filename (without extension)
    """
    from flow.measure import analyze_qnoise

    labels = [f"Vref = {v} V" for v in Vrefs]

    plt.figure()
    for Vref_val, label in zip(Vrefs, labels):
        Vqnoise_vals = [analyze_qnoise(Vref_val, n)[0] * 1e6 for n in Nbits_range]  # µV
        plt.plot(Nbits_range, Vqnoise_vals, label=label)
        # Annotate y-values at N=10 and N=12
        y10 = analyze_qnoise(Vref_val, 10)[0] * 1e6
        y12 = analyze_qnoise(Vref_val, 12)[0] * 1e6
        plt.annotate(
            f"{y10:.1f} µV", xy=(10, y10), xytext=(5, -3), textcoords="offset points"
        )
        plt.annotate(
            f"{y12:.1f} µV", xy=(12, y12), xytext=(5, -3), textcoords="offset points"
        )
        plt.plot(
            [10, 12],
            [y10, y12],
            "o",
            markersize=4,
            color=plt.gca().lines[-1].get_color(),
            label="_nolegend_",
        )

    plt.xlabel(r"Number of Bits ($N_{\mathrm{bits}}$)")
    plt.ylabel(r"Quantization Noise RMS ($\mu$V)")
    plt.title(r"$\sigma_{V_{\mathrm{qnoise}}}$ vs. Bit Resolution")
    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.legend()
    plt.yscale("log")
    save_plot(f"{outdir}/{filename}")
    plt.close()


def plot_sampnoise_vs_capacitance(Ctot_range, outdir="build", filename="sampnoise"):
    """
    Plot sampling noise vs total capacitance.

    Args:
        Ctot_range: Array of capacitance values (F)
        outdir: Output directory
        filename: Output filename (without extension)
    """
    from flow.measure import analyze_sampnoise

    Vsampnoise_vals = [analyze_sampnoise(C) * 1e6 for C in Ctot_range]  # µV

    plt.figure()
    annotate_Cs = [200e-15, 500e-15, 1e-12, 2e-12, 4e-12]  # 200fF, 500fF, 1pF, 2pF, 4pF
    plt.plot(Ctot_range * 1e15, Vsampnoise_vals)
    for C in annotate_Cs:
        x = C * 1e15  # fF
        y = analyze_sampnoise(C) * 1e6  # µV
        plt.plot(x, y, "o", color=plt.gca().lines[-1].get_color(), label="_nolegend_")
        plt.annotate(
            f"{y:.1f} µV", xy=(x, y), xytext=(5, -3), textcoords="offset points"
        )

    plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
    plt.ylabel(r"Sampling Noise RMS ($\mu$V)")
    plt.title(r"$\sigma_{V_{\mathrm{samp}}}$ vs. Total Capacitance")
    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.xscale("log")
    plt.yscale("log")
    save_plot(f"{outdir}/{filename}")
    plt.close()


def plot_enob_vs_capacitance(
    Ctot_range, Vrefs, Nbits, outdir="build", filename_prefix="enob_vs_Ctot"
):
    """
    Plot ENOB vs capacitance for different reference voltages.

    Args:
        Ctot_range: Array of capacitance values (F)
        Vrefs: List of reference voltages
        Nbits: Number of bits
        outdir: Output directory
        filename_prefix: Output filename prefix
    """
    from flow.measure import analyze_enob_from_vref_Ctot_Nbits

    labels = [f"Vref = {v} V" for v in Vrefs]

    plt.figure()
    for Vref_val, label in zip(Vrefs, labels):
        enob_vals = [
            analyze_enob_from_vref_Ctot_Nbits(Vref_val, C, Nbits) for C in Ctot_range
        ]
        plt.plot(Ctot_range * 1e15, enob_vals, label=label)
        # Annotate ENOB at specific capacitances
        for C_annot in [200e-15, 500e-15, 1e-12, 2e-12]:
            x = C_annot * 1e15  # fF
            y = analyze_enob_from_vref_Ctot_Nbits(Vref_val, C_annot, Nbits)
            plt.plot(
                x, y, "o", color=plt.gca().lines[-1].get_color(), label="_nolegend_"
            )
            plt.annotate(
                f"{y:.2f}", xy=(x, y), xytext=(5, -3), textcoords="offset points"
            )

    plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
    plt.ylabel(r"ENOB (reduced by sampling noise)")
    plt.title(
        rf"Degradation of ENOB vs. Sampling Capacitance ($N_{{\mathrm{{bits}}}}={Nbits}$)"
    )
    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.xscale("log")
    plt.legend()
    save_plot(f"{outdir}/{filename_prefix}_{Nbits}bit")
    plt.close()


def plot_midcode_bounds_vs_capacitance(
    Ctot_range, Nbits, Acap, outdir="build", filename_prefix="expected_mismatch"
):
    """
    Plot 3-sigma and 4-sigma mid-code bounds vs capacitance.

    Args:
        Ctot_range: Array of capacitance values (F)
        Nbits: Number of bits
        Acap: Mismatch coefficient
        outdir: Output directory
        filename_prefix: Output filename prefix
    """
    from flow.measure import analyze_midcode_sigma_bounds

    bounds_1sigma = []
    bounds_3sigma = []
    bounds_4sigma = []

    for cap in Ctot_range:
        b1, b3, b4, Cu, sigmaCu = analyze_midcode_sigma_bounds(cap, Nbits, Acap)
        bounds_1sigma.append(b1)
        bounds_3sigma.append(b3)
        bounds_4sigma.append(b4)

    plt.figure()
    plt.plot(Ctot_range * 1e15, bounds_1sigma, label=r"1$\sigma$ Bound")
    plt.plot(Ctot_range * 1e15, bounds_3sigma, label=r"3$\sigma$ Bound")
    plt.plot(Ctot_range * 1e15, bounds_4sigma, label=r"4$\sigma$ Bound")

    plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
    plt.ylabel(r"Max DNL [LSB] (expected at mid-code)")
    plt.title(
        rf"1$\sigma$, 3$\sigma$, and 4$\sigma$ Mid-code LSB vs. $C_{{\mathrm{{tot}}}}$ ($N_{{\mathrm{{bits}}}}={Nbits}$)"
    )
    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.xscale("log")
    plt.legend()
    save_plot(f"{outdir}/{filename_prefix}_{Nbits}bit")
    plt.close()


def plot_mismatch_dnl_noise_vs_capacitance(
    Ctot_range, Nbits, Acap, Vref, outdir="build", filename_prefix="mismatch_dnl_noise"
):
    """
    Plot mismatch DNL noise vs capacitance.

    Args:
        Ctot_range: Array of capacitance values (F)
        Nbits: Number of bits
        Acap: Mismatch coefficient
        Vref: Reference voltage
        outdir: Output directory
        filename_prefix: Output filename prefix
    """
    from flow.measure import analyze_mismatch_dnl_noise

    dnl_noise_1sigma = []
    dnl_noise_3sigma = []
    dnl_noise_4sigma = []
    for cap in Ctot_range:
        d1, d3, d4 = analyze_mismatch_dnl_noise(cap, Nbits, Acap, Vref)
        dnl_noise_1sigma.append(d1 * 1e6)
        dnl_noise_3sigma.append(d3 * 1e6)
        dnl_noise_4sigma.append(d4 * 1e6)

    plt.figure()
    plt.plot(Ctot_range * 1e15, dnl_noise_1sigma, label=r"1$\sigma$ DNL Noise")
    plt.plot(Ctot_range * 1e15, dnl_noise_3sigma, label=r"3$\sigma$ DNL Noise")
    plt.plot(Ctot_range * 1e15, dnl_noise_4sigma, label=r"4$\sigma$ DNL Noise")
    plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
    plt.ylabel(r"Mismatch DNL Noise [$\mu$V]")
    plt.title(
        rf"Mismatch DNL Noise vs. $C_{{\mathrm{{tot}}}}$ ($N_{{\mathrm{{bits}}}}={Nbits}$)"
    )
    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.xscale("log")
    plt.legend()
    save_plot(f"{outdir}/{filename_prefix}_{Nbits}bit")
    plt.close()


def plot_enob_comparison(
    Ctot_range, Vref, Nbits, Acap, outdir="build", filename_prefix="enob_vs_Ctot"
):
    """
    Plot ENOB comparison: sampling noise vs mismatch noise.

    Args:
        Ctot_range: Array of capacitance values (F)
        Vref: Reference voltage
        Nbits: Number of bits
        Acap: Mismatch coefficient
        outdir: Output directory
        filename_prefix: Output filename prefix
    """
    from flow.measure import (
        analyze_enob_from_vref_Ctot_Nbits,
        analyze_enob_from_mismatch,
    )

    enob_vals_sampnoise = []
    for Ctot in Ctot_range:
        enob = analyze_enob_from_vref_Ctot_Nbits(Vref, Ctot, Nbits)
        enob_vals_sampnoise.append(enob)

    enob_vals_mismatchdnl_noise = []
    for Ctot in Ctot_range:
        enob = analyze_enob_from_mismatch(Ctot, Nbits, Acap, Vref)
        enob_vals_mismatchdnl_noise.append(enob)

    plt.figure()
    plt.plot(Ctot_range * 1e15, enob_vals_sampnoise, label="ENOB due to Sampling noise")
    plt.plot(
        Ctot_range * 1e15,
        enob_vals_mismatchdnl_noise,
        label="ENOB due to Mismatch DNL noise",
    )

    plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
    plt.ylabel(r"ENOB")
    plt.title(rf"ENOB vs. $C_{{\mathrm{{tot}}}}$: from Sampling or Mismatch DNL Noise")

    plt.annotate(
        rf"$N_{{\mathrm{{bits}}}}={Nbits}$"
        "\n"
        rf"$V_{{\mathrm{{ref}}}}={Vref}$ V"
        "\n"
        rf"$A_{{C}}={Acap}$",
        xy=(1, 0),
        xycoords="axes fraction",
        va="top",
        xytext=(-60, 75),
        textcoords="offset points",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.7),
    )

    plt.grid(True, which="both", ls="--", alpha=0.5)
    plt.xscale("log")
    plt.legend(loc="lower right", bbox_to_anchor=(1, 0), frameon=True)
    save_plot(f"{outdir}/{filename_prefix}_{Nbits}bit_compare")
    plt.close()
