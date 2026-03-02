"""
Plotting functions for FRIDA ADC characterization.

Provides:
- configure_matplotlib() - headless plotting setup
- save_plot() - save in PDF and PNG formats
- plot_inl_dnl() - INL/DNL vs code
- plot_histogram() - code histogram
- plot_transfer_function() - ADC transfer curve
- plot_fft_spectrum() - FFT with harmonic markers
- plot_waveforms() - generic waveform plotting
"""

import logging
import os
import sys
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np

# Lazy import matplotlib to avoid import-time side effects
_plt = None


def configure_matplotlib():
    """
    Configure matplotlib for headless plotting with LaTeX.

    Returns:
        matplotlib.pyplot module
    """
    global _plt

    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)

    os.environ["MPLBACKEND"] = "Agg"
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        import matplotlib  # type: ignore[import-not-found,import-untyped]

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore[import-not-found,import-untyped]

        _plt = plt
    finally:
        sys.stdout = old_stdout

    plt.rcParams.update(
        {
            "text.usetex": True,
            "font.family": "serif",
            "font.serif": ["Computer Modern Roman"],
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )
    return plt


def _get_plt():
    """Get pyplot, configuring if needed."""
    global _plt
    if _plt is None:
        configure_matplotlib()
    assert _plt is not None
    return _plt


def save_plot(fig, filename_base: str, output_dir: Path = Path("scratch")) -> list[str]:
    """
    Save plot in both PDF and PNG formats.

    Args:
        fig: Matplotlib figure
        filename_base: Base filename (without extension)
        output_dir: Output directory

    Returns:
        List of saved file paths
    """
    output_dir.mkdir(exist_ok=True)
    saved = []

    fig.tight_layout()
    for ext in ["pdf", "png"]:
        path = output_dir / f"{filename_base}.{ext}"
        try:
            fig.savefig(path, dpi=150 if ext == "png" else None)
            saved.append(str(path))
        except Exception as e:
            print(f"Warning: Could not save {path}: {e}")

    return saved


def plot_inl_dnl(
    result: dict[str, Any],
    title: str | None = None,
    save_path: str | None = None,
):
    """
    Plot INL and DNL vs code.

    Args:
        result: Dict from histogram_inl_dnl() with 'dnl', 'inl', 'first_code', 'last_code'
        title: Optional plot title
        save_path: Optional path to save (without extension)

    Returns:
        Matplotlib figure
    """
    plt = _get_plt()

    dnl = result["dnl"]
    inl = result["inl"]
    first = result.get("first_code", 0)
    last = result.get("last_code", len(dnl) - 1)

    codes = np.arange(first, last + 1)
    dnl_active = dnl[first : last + 1]
    inl_active = inl[first : last + 1]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    # DNL plot
    ax1.bar(codes, dnl_active, width=1.0, color="steelblue", alpha=0.7)
    ax1.axhline(y=0, color="black", linewidth=0.5)
    ax1.axhline(y=1, color="red", linewidth=0.5, linestyle="--", label=r"$\pm$1 LSB")
    ax1.axhline(y=-1, color="red", linewidth=0.5, linestyle="--")
    ax1.set_ylabel("DNL (LSB)")
    ax1.set_ylim(-2, 2)
    ax1.legend(loc="upper right")
    ax1.grid(True, alpha=0.3)

    # INL plot
    ax2.plot(codes, inl_active, color="steelblue", linewidth=1.0)
    ax2.axhline(y=0, color="black", linewidth=0.5)
    ax2.set_xlabel("Code")
    ax2.set_ylabel("INL (LSB)")
    ax2.grid(True, alpha=0.3)

    # Add stats annotation
    dnl_max = result.get("dnl_max", np.max(np.abs(dnl_active)))
    inl_max = result.get("inl_max", np.max(np.abs(inl_active)))
    ax1.text(
        0.02,
        0.95,
        f"DNL max: {dnl_max:.2f} LSB",
        transform=ax1.transAxes,
        verticalalignment="top",
        fontsize=9,
    )
    ax2.text(
        0.02,
        0.95,
        f"INL max: {inl_max:.2f} LSB",
        transform=ax2.transAxes,
        verticalalignment="top",
        fontsize=9,
    )

    if title:
        fig.suptitle(title)

    fig.tight_layout()

    if save_path:
        save_plot(fig, save_path)

    return fig


def plot_histogram(
    result: dict[str, Any],
    title: str | None = None,
    save_path: str | None = None,
):
    """
    Plot code histogram.

    Args:
        result: Dict from histogram_inl_dnl() with 'histogram', 'first_code', 'last_code'
        title: Optional plot title
        save_path: Optional path to save

    Returns:
        Matplotlib figure
    """
    plt = _get_plt()

    hist = result["histogram"]
    first = result.get("first_code", 0)
    last = result.get("last_code", len(hist) - 1)

    codes = np.arange(first, last + 1)
    hist_active = hist[first : last + 1]

    fig, ax = plt.subplots(figsize=(8, 4))

    ax.bar(codes, hist_active, width=1.0, color="steelblue", alpha=0.7)
    ax.set_xlabel("Code")
    ax.set_ylabel("Count")
    ax.grid(True, alpha=0.3, axis="y")

    # Mark missing codes
    missing = result.get("missing_codes", [])
    if missing:
        for m in missing:
            if first <= m <= last:
                ax.axvline(x=m, color="red", linewidth=0.5, alpha=0.5)

    # Add stats
    total = int(np.sum(hist_active))
    n_missing = len(missing)
    ax.text(
        0.98,
        0.95,
        f"Total samples: {total}\nMissing codes: {n_missing}",
        transform=ax.transAxes,
        verticalalignment="top",
        horizontalalignment="right",
        fontsize=9,
    )

    if title:
        ax.set_title(title)

    fig.tight_layout()

    if save_path:
        save_plot(fig, save_path)

    return fig


def plot_transfer_function(
    v_in: np.ndarray,
    codes: np.ndarray,
    v_estimated: np.ndarray | None = None,
    title: str | None = None,
    save_path: str | None = None,
):
    """
    Plot ADC transfer function.

    Args:
        v_in: Input voltage array
        codes: Output codes array
        v_estimated: Optional estimated voltage for comparison
        title: Optional plot title
        save_path: Optional path to save

    Returns:
        Matplotlib figure
    """
    plt = _get_plt()

    fig, ax = plt.subplots(figsize=(8, 6))

    # Sort by input voltage for cleaner plotting
    sort_idx = np.argsort(v_in)
    v_sorted = v_in[sort_idx]
    codes_sorted = codes[sort_idx]

    ax.plot(
        v_sorted * 1000, codes_sorted, ".", markersize=1, alpha=0.5, label="Measured"
    )

    # Ideal line
    v_min, v_max = v_sorted.min(), v_sorted.max()
    code_min, code_max = codes_sorted.min(), codes_sorted.max()
    ax.plot(
        [v_min * 1000, v_max * 1000],
        [code_min, code_max],
        "r--",
        linewidth=1,
        label="Ideal",
    )

    ax.set_xlabel("Input Voltage (mV)")
    ax.set_ylabel("Output Code")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)

    if title:
        ax.set_title(title)

    fig.tight_layout()

    if save_path:
        save_plot(fig, save_path)

    return fig


def plot_fft_spectrum(
    codes: np.ndarray,
    fs: float,
    fin: float | None = None,
    n_harmonics: int = 5,
    title: str | None = None,
    save_path: str | None = None,
):
    """
    Plot FFT spectrum with harmonic markers.

    Args:
        codes: ADC output codes
        fs: Sampling frequency (Hz)
        fin: Input frequency (Hz) for harmonic markers
        n_harmonics: Number of harmonics to mark
        title: Optional plot title
        save_path: Optional path to save

    Returns:
        Matplotlib figure
    """
    plt = _get_plt()

    n = len(codes)
    codes_ac = codes - np.mean(codes)

    # Window and FFT
    win = np.hanning(n)
    fft_out = np.fft.rfft(codes_ac * win)
    pwr_db = 20 * np.log10(np.abs(fft_out) + 1e-20)
    freq = np.fft.rfftfreq(n, 1 / fs)

    # Normalize to max
    pwr_db -= np.max(pwr_db)

    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(freq / 1e6, pwr_db, linewidth=0.5, color="steelblue")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Power (dB)")
    ax.set_ylim(-120, 10)
    ax.grid(True, alpha=0.3)

    # Mark harmonics if fin provided
    if fin is not None:
        colors = ["green", "red", "orange", "purple", "brown"]
        for h in range(1, n_harmonics + 1):
            hf = h * fin
            if hf < fs / 2:
                color = colors[(h - 1) % len(colors)]
                ax.axvline(
                    x=hf / 1e6,
                    color=color,
                    linewidth=1,
                    linestyle="--",
                    alpha=0.7,
                    label=f"H{h}" if h > 1 else "Fund",
                )
        ax.legend(loc="upper right", fontsize=8)

    if title:
        ax.set_title(title)

    fig.tight_layout()

    if save_path:
        save_plot(fig, save_path)

    return fig


def plot_waveforms(
    time: np.ndarray,
    waveforms: dict[str, np.ndarray],
    title: str | None = None,
    ylabel: str = "Voltage (V)",
    save_path: str | None = None,
):
    """
    Plot multiple waveforms on the same axes.

    Args:
        time: Time array
        waveforms: Dict mapping label -> waveform array
        title: Optional plot title
        ylabel: Y-axis label
        save_path: Optional path to save

    Returns:
        Matplotlib figure
    """
    plt = _get_plt()

    fig, ax = plt.subplots(figsize=(10, 4))

    # Determine time unit
    t_max = time.max()
    if t_max < 1e-6:
        t_scale, t_unit = 1e9, "ns"
    elif t_max < 1e-3:
        t_scale, t_unit = 1e6, r"$\mu$s"
    elif t_max < 1:
        t_scale, t_unit = 1e3, "ms"
    else:
        t_scale, t_unit = 1, "s"

    for label, wf in waveforms.items():
        ax.plot(time * t_scale, wf, label=label, linewidth=0.8)

    ax.set_xlabel(f"Time ({t_unit})")
    ax.set_ylabel(ylabel)
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)

    if title:
        ax.set_title(title)

    fig.tight_layout()

    if save_path:
        save_plot(fig, save_path)

    return fig


def plot_enob_vs_frequency(
    frequencies: np.ndarray,
    enob_values: np.ndarray,
    nominal_bits: int | None = None,
    title: str | None = None,
    save_path: str | None = None,
):
    """
    Plot ENOB vs input frequency.

    Args:
        frequencies: Input frequencies (Hz)
        enob_values: ENOB values
        nominal_bits: Nominal resolution for reference line
        title: Optional plot title
        save_path: Optional path to save

    Returns:
        Matplotlib figure
    """
    plt = _get_plt()

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.semilogx(frequencies / 1e6, enob_values, "o-", color="steelblue", markersize=6)

    if nominal_bits is not None:
        ax.axhline(
            y=nominal_bits,
            color="red",
            linestyle="--",
            linewidth=1,
            label=f"{nominal_bits}-bit",
        )

    ax.set_xlabel("Input Frequency (MHz)")
    ax.set_ylabel("ENOB (bits)")
    ax.grid(True, alpha=0.3, which="both")

    if nominal_bits is not None:
        ax.legend(loc="lower left")

    if title:
        ax.set_title(title)

    fig.tight_layout()

    if save_path:
        save_plot(fig, save_path)

    return fig


def plot_monte_carlo_histogram(
    values: np.ndarray,
    xlabel: str,
    title: str | None = None,
    n_bins: int = 30,
    save_path: str | None = None,
):
    """
    Plot Monte Carlo result histogram with statistics.

    Args:
        values: Array of MC results
        xlabel: X-axis label
        title: Optional plot title
        n_bins: Number of histogram bins
        save_path: Optional path to save

    Returns:
        Matplotlib figure
    """
    plt = _get_plt()

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.hist(values, bins=n_bins, color="steelblue", alpha=0.7, edgecolor="black")

    mean = np.mean(values)
    std = np.std(values)

    ax.axvline(x=mean, color="red", linewidth=2, label=f"Mean: {mean:.3g}")
    ax.axvline(x=mean - 3 * std, color="orange", linewidth=1, linestyle="--")
    ax.axvline(
        x=mean + 3 * std,
        color="orange",
        linewidth=1,
        linestyle="--",
        label=f"3$\\sigma$: {3 * std:.3g}",
    )

    ax.set_xlabel(xlabel)
    ax.set_ylabel("Count")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3, axis="y")

    # Stats annotation
    ax.text(
        0.02,
        0.95,
        f"N = {len(values)}\n$\\mu$ = {mean:.3g}\n$\\sigma$ = {std:.3g}",
        transform=ax.transAxes,
        verticalalignment="top",
        fontsize=9,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )

    if title:
        ax.set_title(title)

    fig.tight_layout()

    if save_path:
        save_plot(fig, save_path)

    return fig
