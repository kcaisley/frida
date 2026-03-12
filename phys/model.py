#!/usr/bin/env python3
import os

import numpy as np

os.environ.setdefault("MPLBACKEND", "Agg")
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ELEMENTARY_CHARGE_C = 1.602176634e-19
plt.rcParams.update(
    {
        "text.usetex": True,
        "text.latex.preamble": r"\usepackage{textcomp}",
        "font.family": "serif",
        "font.serif": ["Computer Modern Roman"],
    }
)


def hit_rate_per_pixel_per_second(fluence_m2_s: float, pixel_pitch_m: float) -> float:
    return fluence_m2_s * pixel_pitch_m**2


def max_counting_rate_per_pixel_per_second(enob_bits: float, window_s: float) -> float:
    return (2**enob_bits - 1) / window_s


def format_time_axis(value: float, _: object) -> str:
    if value >= 1e-3:
        return f"{value * 1e3:g} ms"
    if value >= 1e-6:
        return rf"{value * 1e6:g} \textmu s"
    return f"{value * 1e9:g} ns"


def format_rate_axis(value: float, _: object) -> str:
    for scale, prefix in ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if value >= scale:
            return f"{value / scale:g} {prefix}Hz"
    return f"{value:g} Hz"


def format_fluence_axis(value: float, _: object) -> str:
    for scale, unit in (
        (1e15, r"\mathrm{PHz}"),
        (1e12, r"\mathrm{THz}"),
        (1e9, r"\mathrm{GHz}"),
        (1e6, r"\mathrm{MHz}"),
        (1e3, r"\mathrm{kHz}"),
    ):
        if value >= scale:
            return rf"${value / scale:g}\,\frac{{{unit}}}{{\mathrm{{cm}}^2}}$"
    return rf"${value:g}\,\frac{{\mathrm{{Hz}}}}{{\mathrm{{cm}}^2}}$"


def fluence_to_current_density_pa_cm2(value: float) -> float:
    return value * ELEMENTARY_CHARGE_C * 1e12


def current_density_pa_cm2_to_fluence(value: float) -> float:
    return value / (ELEMENTARY_CHARGE_C * 1e12)


def format_current_density_axis(value: float, _: object) -> str:
    for scale, unit in (
        (1e12, r"\mathrm{A}"),
        (1e9, r"\mathrm{mA}"),
        (1e6, r"\mu\mathrm{A}"),
        (1e3, r"\mathrm{nA}"),
        (1, r"\mathrm{pA}"),
        (1e-3, r"\mathrm{fA}"),
    ):
        if value >= scale:
            return rf"${value / scale:g}\,\frac{{{unit}}}{{\mathrm{{cm}}^2}}$"
    return rf"${value * 1e3:g}\,\frac{{\mathrm{{fA}}}}{{\mathrm{{cm}}^2}}$"


def plot_hit_rate_vs_fluence() -> None:
    # Sweep 1 MHz to 1 THz per square centimeter, then convert immediately to
    # per square meter for the SI-based rate calculation.
    fluences_cm2_s = np.logspace(6, 12, 400)
    fluences_m2_s = fluences_cm2_s * 1e4
    pitches_m = [100e-6, 75e-6, 50e-6, 30e-6, 15e-6, 10e-6]
    colors = ["#5E81AC", "#81A1C1", "#88C0D0", "#8FBCBB", "#A3BE8C", "#EBCB8B"]

    fig, ax = plt.subplots(figsize=(7, 5))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    for pitch_m, color in zip(pitches_m, colors, strict=True):
        rates = [
            hit_rate_per_pixel_per_second(fluence, pitch_m) for fluence in fluences_m2_s
        ]
        ax.plot(
            fluences_cm2_s,
            rates,
            label=rf"{pitch_m * 1e6:g} \textmu m",
            color=color,
            linewidth=2,
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=np.arange(2.0, 10.0)))
    ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=np.arange(2.0, 10.0)))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.xaxis.set_major_formatter(FuncFormatter(format_fluence_axis))
    ax.yaxis.set_major_formatter(FuncFormatter(format_rate_axis))
    bottom2 = ax.secondary_xaxis(
        "bottom",
        functions=(
            fluence_to_current_density_pa_cm2,
            current_density_pa_cm2_to_fluence,
        ),
    )
    bottom2.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    bottom2.xaxis.set_minor_locator(LogLocator(base=10.0, subs=np.arange(2.0, 10.0)))
    bottom2.xaxis.set_minor_formatter(NullFormatter())
    bottom2.spines["bottom"].set_position(("outward", 38))
    bottom2.xaxis.set_major_formatter(FuncFormatter(format_current_density_axis))
    bottom2.tick_params(colors="#2E3440")
    bottom2.spines["bottom"].set_color("#4C566A")
    bottom2.xaxis.label.set_color("#2E3440")
    bottom2.set_xlabel(r"Equivalent beam current density")
    ax.set_xlabel(
        r"Incident particle fluence $\left[\frac{\mathrm{count}}{\mathrm{cm}^2 \cdot \mathrm{s}}\right]$"
    )
    ax.set_ylabel(r"Hit rate per pixel $\left[\frac{\mathrm{hits}}{\mathrm{s}}\right]$")
    ax.set_title("Per-pixel hit rate vs fluence")
    ax.minorticks_on()
    ax.xaxis.grid(True, which="major", color="#D8DEE9", alpha=0.95, linewidth=0.8)
    ax.yaxis.grid(True, which="major", color="#D8DEE9", alpha=0.95, linewidth=0.8)
    ax.xaxis.grid(True, which="minor", color="#E5E9F0", alpha=1.0, linewidth=0.5)
    ax.yaxis.grid(True, which="minor", color="#E5E9F0", alpha=1.0, linewidth=0.5)
    ax.legend(
        title="Pixel pitch",
        facecolor="#ECEFF4",
        edgecolor="#4C566A",
        labelcolor="#2E3440",
    )
    ax.text(
        0.98,
        0.03,
        r"Assuming 100\% efficiency and no charge sharing",
        transform=ax.transAxes,
        color="#2E3440",
        fontsize=9,
        ha="right",
        bbox={"facecolor": "#ECEFF4", "edgecolor": "#4C566A", "alpha": 0.9},
    )
    ax.tick_params(colors="#2E3440")
    for spine in ax.spines.values():
        spine.set_color("#4C566A")
    ax.xaxis.label.set_color("#2E3440")
    ax.yaxis.label.set_color("#2E3440")
    ax.title.set_color("#2E3440")
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.22)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(RESULTS_DIR / "hit_rate_vs_fluence.png", dpi=200, transparent=True)
    fig.savefig(RESULTS_DIR / "hit_rate_vs_fluence.pdf", transparent=True)


def plot_max_counting_rate_vs_window() -> None:
    windows = np.logspace(-8, -3, 400)
    enobs = [12, 10, 8, 6, 4, 1]
    colors = ["#5E81AC", "#81A1C1", "#88C0D0", "#8FBCBB", "#A3BE8C", "#EBCB8B"]

    fig, ax = plt.subplots(figsize=(7, 5))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    for enob, color in zip(enobs, colors, strict=True):
        rates = [
            max_counting_rate_per_pixel_per_second(enob, window) for window in windows
        ]
        ax.plot(windows, rates, label=rf"{enob}-bit", color=color, linewidth=2)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(format_time_axis))
    ax.yaxis.set_major_formatter(FuncFormatter(format_rate_axis))
    ax.set_xlabel("Measurement window (frame time / dead time)")
    ax.set_ylabel(r"Max counting rate per pixel")
    ax.set_title(r"Max counting rate vs measurement window")
    ax.grid(True, which="both", color="#D8DEE9", alpha=0.9)
    ax.legend(
        title="ENOB", facecolor="#ECEFF4", edgecolor="#4C566A", labelcolor="#2E3440"
    )
    ax.tick_params(colors="#2E3440")
    for spine in ax.spines.values():
        spine.set_color("#4C566A")
    ax.xaxis.label.set_color("#2E3440")
    ax.yaxis.label.set_color("#2E3440")
    ax.title.set_color("#2E3440")
    fig.tight_layout()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        RESULTS_DIR / "max_counting_rate_vs_window.png", dpi=200, transparent=True
    )
    fig.savefig(RESULTS_DIR / "max_counting_rate_vs_window.pdf", transparent=True)


def main() -> int:
    plot_hit_rate_vs_fluence()
    plot_max_counting_rate_vs_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
