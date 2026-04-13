#!/usr/bin/env python3
import os

import numpy as np

os.environ.setdefault("MPLBACKEND", "Agg")
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ELEMENTARY_CHARGE_C = 1.602176634e-19
PNG_FACE_COLOR = "white"
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


def max_rate(time_dead: float, allowed_overlap_fraction: float = 0.1) -> float:
    r"""Return the max Poisson arrival rate for a target overlap probability.

    Uses the non-paralyzable dead-time model.  After each
    accepted hit the front-end is insensitive for a fixed interval t_d.
    Hits arriving during that window are lost, but they do *not* extend
    the dead time — the detector recovers on schedule and is ready for
    the next event. In contrast, a paralyzable detector restarts the dead time
    on every arriving event, even during the insensitive window, which
    can cause the detector to lock up at very high rates. Some chips (e.g. IBEX)
    add instant retrigger on top of this.

    We model particle arrivals as a Poisson process with average rate μ (hits/s).
    Each hit occupies the front-end for a fixed dead time t_d.

    Let λ = μ * t_d be the expected number of arrivals in one dead-time window.
    The probability that a hit overlaps with a previous one (i.e., at least
    one other arrival falls within the dead-time window) is:

        P(overlap) = 1 - P(0 arrivals in window)
                   = 1 - e^(-λ)

    We want P(overlap) = allowed_overlap_fraction, so:

        1 - e^(-λ) = f
        e^(-λ) = 1 - f
        -λ = ln(1 - f)
        λ = -ln(1 - f)       [equivalently  ln(1/0.9) for f = 0.1]

    Since λ = μ * t_d, we solve for μ:

        μ = -ln(1 - f) / t_d     (non-paralyzable, Eq. 7)

    For comparison, the paralyzable model gives τ_p = f / ((1-f) * μ),
    which yields a slightly longer dead time for the same rate (Eq. 6).

    Reference: R. Ballabriga et al., "Photon Counting Detectors for X-ray
    Imaging with Emphasis on CT", IEEE Trans. Radiat. Plasma Med. Sci.,
    vol. 5, no. 4, pp. 422–440, 2021.
    """
    return -np.log1p(-allowed_overlap_fraction) / time_dead


def format_time_axis(value: float, _: object) -> str:
    if value >= 1e-3:
        return f"{value * 1e3:g} ms"
    if value >= 1e-6:
        return rf"{value * 1e6:g} \textmu s"
    return f"{value * 1e9:g} ns"


def format_rate_axis(value: float, _: object) -> str:
    for scale, prefix in ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if value >= scale:
            return f"{value / scale:g} {prefix}cps"
    return f"{value:g} cps"


def format_fluence_axis(value: float, _: object) -> str:
    for scale, unit in (
        (1e15, r"\mathrm{Pcps}"),
        (1e12, r"\mathrm{Tcps}"),
        (1e9, r"\mathrm{Gcps}"),
        (1e6, r"\mathrm{Mcps}"),
        (1e3, r"\mathrm{kcps}"),
    ):
        if value >= scale:
            return rf"${value / scale:g}\,\frac{{{unit}}}{{\mathrm{{mm}}^2}}$"
    return rf"${value:g}\,\frac{{\mathrm{{cps}}}}{{\mathrm{{mm}}^2}}$"


def amps_to_cps(current_a: float) -> float:
    """Convert a current in amps to a count rate in particles/s."""
    return current_a / ELEMENTARY_CHARGE_C


def cps_to_amps(rate_cps: float) -> float:
    """Convert a count rate in particles/s to a current in amps."""
    return rate_cps * ELEMENTARY_CHARGE_C


def fluence_to_current_density_pa_mm2(value: float) -> float:
    return value * ELEMENTARY_CHARGE_C * 1e12


def current_density_pa_mm2_to_fluence(value: float) -> float:
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
            return rf"${value / scale:g}\,\frac{{{unit}}}{{\mathrm{{mm}}^2}}$"
    return rf"${value * 1e3:g}\,\frac{{\mathrm{{fA}}}}{{\mathrm{{mm}}^2}}$"


# ---- shared axis styling ----
def _style_ax(ax: plt.Axes) -> None:
    ax.tick_params(colors="#2E3440")
    for spine in ax.spines.values():
        spine.set_color("#4C566A")
    ax.xaxis.label.set_color("#2E3440")
    ax.yaxis.label.set_color("#2E3440")
    ax.title.set_color("#2E3440")


def plot_hit_rate_vs_fluence() -> None:
    """Figure 1: per-pixel hit rate vs fluence."""
    fluences_mm2_s = np.logspace(6, 11, 400)
    fluences_m2_s = fluences_mm2_s * 1e6
    pitches_m = [100e-6, 75e-6, 50e-6, 30e-6, 15e-6, 10e-6]
    colors = ["#5E81AC", "#81A1C1", "#88C0D0", "#8FBCBB", "#A3BE8C", "#EBCB8B"]

    fig, ax = plt.subplots(figsize=(7, 5), facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    ax.set_facecolor(PNG_FACE_COLOR)
    for pitch_m, color in zip(pitches_m, colors, strict=True):
        rates = [hit_rate_per_pixel_per_second(f, pitch_m) for f in fluences_m2_s]
        ax.plot(
            fluences_mm2_s,
            rates,
            label=rf"{pitch_m * 1e6:g} \textmu m",
            color=color,
            linewidth=2,
        )

    # ---- beam-source markers along bottom axis ----
    _PH, _EL = "#B48EAD", "#BF616A"
    _photon = [
        ("PETRA III", 1e10),
        ("PETRA IV", 1.5e10),
        ("ESRF-EBS", 1e11),
        ("EuXFEL CW", 1.2e11),
    ]
    _electron = [
        ("ELSA", 4e6),
        ("Talos F200", 1.4e7),
        ("Spectra", 6.2e7),
        ("F200X", 9.4e7),
        ("Themis", 1.2e8),
    ]
    _xax = ax.get_xaxis_transform()
    for n, f in _photon:
        ax.plot(
            f,
            0.03,
            "s",
            transform=_xax,
            color=_PH,
            markersize=7,
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=5,
            clip_on=False,
        )
        ax.text(f, 0.06, n, transform=_xax, fontsize=6, color=_PH, rotation=90, va="bottom", ha="center", clip_on=False)
    for n, f in _electron:
        ax.plot(
            f,
            0.03,
            "o",
            transform=_xax,
            color=_EL,
            markersize=7,
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=5,
            clip_on=False,
        )
        ax.text(f, 0.06, n, transform=_xax, fontsize=6, color=_EL, rotation=90, va="bottom", ha="center", clip_on=False)
    _src_h = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=_PH, markersize=7, label="Photon source"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=_EL, markersize=7, label="Electron source"),
    ]

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(1e4, 1e9)
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
        functions=(fluence_to_current_density_pa_mm2, current_density_pa_mm2_to_fluence),
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

    ax.set_xlabel(r"Incident particle fluence $\left[\frac{\mathrm{cps}}{\mathrm{mm}^2}\right]$")
    ax.set_ylabel(r"Resulting hit rate per pixel $\left[\mathrm{cps}\right]$")
    ax.set_title("Per-pixel hit rate vs fluence")
    ax.minorticks_on()
    ax.xaxis.grid(True, which="major", color="#D8DEE9", alpha=0.95, linewidth=0.8)
    ax.yaxis.grid(True, which="major", color="#D8DEE9", alpha=0.95, linewidth=0.8)
    ax.xaxis.grid(True, which="minor", color="#E5E9F0", alpha=1.0, linewidth=0.5)
    ax.yaxis.grid(True, which="minor", color="#E5E9F0", alpha=1.0, linewidth=0.5)

    _ph, _pl = ax.get_legend_handles_labels()
    ax.legend(
        handles=_ph + _src_h,
        labels=_pl + ["Photon source", "Electron source"],
        title="Pixel pitch / Sources",
        facecolor="#ECEFF4",
        edgecolor="#4C566A",
        labelcolor="#2E3440",
    )
    ax.text(
        0.98,
        0.97,
        r"Assuming 100\% efficiency, no charge sharing,"
        "\n"
        r"and a 1\,cm$^2$ beam spot for source markers",
        transform=ax.transAxes,
        color="#2E3440",
        fontsize=8,
        ha="right",
        va="top",
        bbox={"facecolor": "#ECEFF4", "edgecolor": "#4C566A", "alpha": 0.9},
    )
    _style_ax(ax)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.22)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(RESULTS_DIR / "hit_rate_vs_fluence.png", dpi=200, facecolor=PNG_FACE_COLOR)
    fig.savefig(RESULTS_DIR / "hit_rate_vs_fluence.pdf", transparent=True)


def plot_max_counting_rate_vs_window() -> None:
    """Figure 2: two subplots — integrating (frame time) and discriminating (dead time)."""
    fig, (ax_int, ax_disc) = plt.subplots(
        1,
        2,
        figsize=(12, 5),
        facecolor=PNG_FACE_COLOR,
        sharey=True,
    )
    fig.patch.set_facecolor(PNG_FACE_COLOR)

    # ---- Left: integrating frame-time curves (5 µs – 100 µs) ----
    frame_windows = np.linspace(5e-6, 100e-6, 200)
    enobs = [12, 10, 8, 6, 4]
    colors = ["#5E81AC", "#81A1C1", "#88C0D0", "#8FBCBB", "#A3BE8C"]

    ax_int.set_facecolor(PNG_FACE_COLOR)
    for enob, color in zip(enobs, colors, strict=True):
        rates = [max_counting_rate_per_pixel_per_second(enob, w) for w in frame_windows]
        ax_int.plot(frame_windows, rates, label=rf"{enob}-bit", color=color, linewidth=2)

    ax_int.set_yscale("log")
    ax_int.set_ylim(1e4, 1e9)
    ax_int.xaxis.set_major_formatter(FuncFormatter(format_time_axis))
    ax_int.yaxis.set_major_formatter(FuncFormatter(format_rate_axis))
    ax_int.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax_int.yaxis.set_minor_locator(LogLocator(base=10.0, subs=np.arange(2.0, 10.0)))
    ax_int.yaxis.set_minor_formatter(NullFormatter())
    ax_int.set_xlabel(r"Frame time")
    ax_int.set_ylabel(r"Max hit counting rate per pixel $\left[\mathrm{cps}\right]$")
    ax_int.set_title("Integrating (frame-based)")
    ax_int.grid(True, which="major", color="#D8DEE9", alpha=0.9)
    ax_int.grid(True, which="minor", axis="y", color="#E5E9F0", alpha=0.7)
    ax_int.legend(
        title="ADC bit depth",
        loc="upper right",
        facecolor="#ECEFF4",
        edgecolor="#4C566A",
        labelcolor="#2E3440",
    )
    _style_ax(ax_int)

    # ---- Right: discriminating dead-time curve (10 ns – 400 ns) ----
    dead_ns = np.linspace(10, 400, 200)
    dead_s = dead_ns * 1e-9
    loss_rates = [max_rate(w) for w in dead_s]

    ax_disc.set_facecolor(PNG_FACE_COLOR)
    ax_disc.plot(dead_ns, loss_rates, "--", color="#BF616A", linewidth=2, label=r"10\% pile-up limit")

    # Discriminating detector markers
    _discrim = [  # (label, dead_time_ns, reported_rate_cps)
        ("SPHIRD", 8.3, 12e6),
        ("KITE", 23, 31e6),
        ("MPX4", 36, 2.9e6),
        ("TPX4", 50, 2.1e6),
        ("IBEX", 100, 1.1e6),
        ("PIL3", 125, 0.89e6),
        ("EIGER", 238, 0.47e6),
        ("MPX3", 400, 0.25e6),
    ]
    for n, td_ns, r in _discrim:
        ax_disc.plot(
            td_ns, r, "o", color="#BF616A", markersize=7, markeredgecolor="white", markeredgewidth=0.5, zorder=5
        )
        ax_disc.annotate(n, (td_ns, r), fontsize=7, color="#2E3440", textcoords="offset points", xytext=(5, 4))

    ax_disc.set_yscale("log")
    ax_disc.set_ylim(1e4, 1e9)
    ax_disc.set_xlabel(r"Front-end dead time [ns]")
    ax_disc.set_title(r"Discriminating (counting)")
    ax_disc.grid(True, which="major", color="#D8DEE9", alpha=0.9)
    ax_disc.grid(True, which="minor", axis="y", color="#E5E9F0", alpha=0.7)
    ax_disc.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax_disc.yaxis.set_minor_locator(LogLocator(base=10.0, subs=np.arange(2.0, 10.0)))
    ax_disc.yaxis.set_minor_formatter(NullFormatter())
    ax_disc.legend(
        loc="upper right",
        facecolor="#ECEFF4",
        edgecolor="#4C566A",
        labelcolor="#2E3440",
    )
    _style_ax(ax_disc)

    fig.suptitle(
        "Max pixel count rate: integrating vs discriminating detectors",
        color="#2E3440",
        fontsize=12,
    )
    fig.tight_layout()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        RESULTS_DIR / "max_counting_rate_vs_window.png",
        dpi=200,
        facecolor=PNG_FACE_COLOR,
    )
    fig.savefig(RESULTS_DIR / "max_counting_rate_vs_window.pdf", transparent=True)


def main() -> int:
    plot_hit_rate_vs_fluence()
    plot_max_counting_rate_vs_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
