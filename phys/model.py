import os
from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from flow.analysis.plots import (
    CURVE_COLORS,
    PLOT_STYLE,
    SPINE_COLOR,
    TEXT_COLOR,
    save_figure,
    style_grid,
)

ROOT = Path(__file__).resolve().parents[1]
ELEMENTARY_CHARGE_C = 1.602176634e-19


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


def style_time_axis_text(value: float, _: object) -> str:
    # rcParams cannot format domain-specific engineering units.
    if value >= 1e-3:
        return f"{value * 1e3:g} ms"
    if value >= 1e-6:
        return f"{value * 1e6:g} µs"
    return f"{value * 1e9:g} ns"


def style_rate_axis_text(value: float, _: object) -> str:
    # rcParams cannot format domain-specific engineering units.
    for scale, prefix in ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if value >= scale:
            return f"{value / scale:g} {prefix}cps"
    return f"{value:g} cps"


def style_fluence_axis_text(value: float, _: object) -> str:
    # rcParams cannot format domain-specific engineering units.
    for scale, unit in (
        (1e15, "Pcps"),
        (1e12, "Tcps"),
        (1e9, "Gcps"),
        (1e6, "Mcps"),
        (1e3, "kcps"),
    ):
        if value >= scale:
            return f"{value / scale:g} {unit}/mm²"
    return f"{value:g} cps/mm²"


def amps_to_cps(current_a: float) -> float:
    """Convert a current in amps to a count rate in particles/s."""
    return current_a / ELEMENTARY_CHARGE_C


def cps_to_amps(rate_cps: float) -> float:
    """Convert a count rate in particles/s to a current in amps."""
    return rate_cps * ELEMENTARY_CHARGE_C


def fluence_to_current_density_pa_mm2(value: npt.ArrayLike) -> np.ndarray:
    return np.asarray(value) * ELEMENTARY_CHARGE_C * 1e12


def current_density_pa_mm2_to_fluence(value: npt.ArrayLike) -> np.ndarray:
    return np.asarray(value) / (ELEMENTARY_CHARGE_C * 1e12)


def style_current_density_axis_text(value: float, _: object) -> str:
    # rcParams cannot format domain-specific engineering units.
    for scale, unit in (
        (1e12, "A"),
        (1e9, "mA"),
        (1e6, "µA"),
        (1e3, "nA"),
        (1, "pA"),
        (1e-3, "fA"),
    ):
        if value >= scale:
            return f"{value / scale:g} {unit}/mm²"
    return f"{value * 1e3:g} fA/mm²"


@mpl.rc_context(PLOT_STYLE)
def plot_hit_rate_vs_fluence(*, output_path: Path) -> tuple[Path, ...]:
    """Figure 1: per-pixel hit rate vs fluence."""
    fluences_mm2_s = np.logspace(6, 11, 400)
    fluences_m2_s = fluences_mm2_s * 1e6
    pitches_m = [100e-6, 75e-6, 50e-6, 30e-6, 15e-6, 10e-6]
    colors = CURVE_COLORS[: len(pitches_m)]

    fig, ax = plt.subplots()
    for pitch_m, color in zip(pitches_m, colors, strict=True):
        rates = [hit_rate_per_pixel_per_second(f, pitch_m) for f in fluences_m2_s]
        ax.plot(
            fluences_mm2_s,
            rates,
            label=f"{pitch_m * 1e6:g} µm",
            color=color,
        )

    # ---- beam-source markers along bottom axis ----
    photon_color, electron_color = CURVE_COLORS[3], CURVE_COLORS[5]
    _photon = [
        ("PETRA III", 1e10, -4),
        ("PETRA IV", 1.5e10, 4),
        ("ESRF-EBS", 1e11, -8),
        ("EuXFEL CW", 1.2e11, 8),
    ]
    _electron = [
        ("ELSA", 4e6, 0),
        ("Talos F200", 1.4e7, 0),
        ("Spectra", 6.2e7, -5),
        ("F200X", 9.4e7, 0),
        ("Themis", 1.2e8, 5),
    ]
    _xax = ax.get_xaxis_transform()
    for n, f, text_offset in _photon:
        ax.plot(
            f,
            0.03,
            "s",
            transform=_xax,
            color=photon_color,
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=5,
            clip_on=False,
        )
        ax.annotate(
            n,
            (f, 0.06),
            xycoords=_xax,
            xytext=(text_offset, 0),
            textcoords="offset points",
            color=photon_color,
            rotation=90,
            va="bottom",
            ha="center",
            clip_on=False,
        )
    for n, f, text_offset in _electron:
        ax.plot(
            f,
            0.03,
            "o",
            transform=_xax,
            color=electron_color,
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=5,
            clip_on=False,
        )
        ax.annotate(
            n,
            (f, 0.06),
            xycoords=_xax,
            xytext=(text_offset, 0),
            textcoords="offset points",
            color=electron_color,
            rotation=90,
            va="bottom",
            ha="center",
            clip_on=False,
        )
    _src_h = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=photon_color, label="Photon source"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=electron_color, label="Electron source"),
    ]

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(1e4, 1e9)
    ax.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10))))
    ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10))))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.xaxis.set_major_formatter(FuncFormatter(style_fluence_axis_text))
    ax.yaxis.set_major_formatter(FuncFormatter(style_rate_axis_text))

    bottom2 = ax.secondary_xaxis(
        "bottom",
        functions=(fluence_to_current_density_pa_mm2, current_density_pa_mm2_to_fluence),
    )
    bottom2.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    bottom2.xaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10))))
    bottom2.xaxis.set_minor_formatter(NullFormatter())
    bottom2.spines["bottom"].set_position(("outward", 38))
    bottom2.xaxis.set_major_formatter(FuncFormatter(style_current_density_axis_text))
    bottom2.tick_params(colors=TEXT_COLOR)
    bottom2.spines["bottom"].set_color(SPINE_COLOR)
    bottom2.xaxis.label.set_color(TEXT_COLOR)
    bottom2.set_xlabel("Equivalent beam current density")

    ax.set_xlabel("Incident particle fluence (cps/mm²)")
    ax.set_ylabel("Resulting hit rate per pixel (cps)")
    ax.set_title("Per-pixel hit rate vs fluence")
    style_grid(ax)

    _ph, _pl = ax.get_legend_handles_labels()
    ax.legend(
        handles=_ph + _src_h,
        labels=_pl + ["Photon source", "Electron source"],
        title="Pixel pitch / Sources",
    )
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_max_counting_rate_vs_window(*, output_path: Path) -> tuple[Path, ...]:
    """Figure 2: two subplots — integrating (frame time) and discriminating (dead time)."""
    fig, (ax_int, ax_disc) = plt.subplots(
        1,
        2,
        sharey=True,
    )

    # ---- Left: integrating frame-time curves (5 µs – 100 µs) ----
    frame_windows = np.linspace(5e-6, 100e-6, 200)
    enobs = [12, 10, 8, 6, 4]
    colors = CURVE_COLORS[: len(enobs)]

    for enob, color in zip(enobs, colors, strict=True):
        rates = [max_counting_rate_per_pixel_per_second(enob, w) for w in frame_windows]
        ax_int.plot(frame_windows, rates, label=rf"{enob}-bit", color=color)

    ax_int.set_yscale("log")
    ax_int.set_ylim(1e4, 1e9)
    ax_int.xaxis.set_major_formatter(FuncFormatter(style_time_axis_text))
    ax_int.yaxis.set_major_formatter(FuncFormatter(style_rate_axis_text))
    ax_int.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax_int.yaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10))))
    ax_int.yaxis.set_minor_formatter(NullFormatter())
    ax_int.set_xlabel("Frame time")
    ax_int.set_ylabel("Max hit counting rate per pixel (cps)")
    ax_int.set_title("Integrating (frame-based)")
    style_grid(ax_int)
    ax_int.legend(title="ADC bit depth")

    # ---- Right: discriminating dead-time curve (10 ns – 400 ns) ----
    dead_ns = np.linspace(10, 400, 200)
    dead_s = dead_ns * 1e-9
    loss_rates = [max_rate(w) for w in dead_s]

    ax_disc.plot(dead_ns, loss_rates, "--", color=CURVE_COLORS[0], label="10% pile-up limit")

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
    annotation_positions = {
        "MPX4": ((-8, 8), "right"),
        "TPX4": ((8, -2), "left"),
        "IBEX": ((-8, 8), "right"),
        "PIL3": ((8, -2), "left"),
    }
    for n, td_ns, r in _discrim:
        ax_disc.plot(
            td_ns,
            r,
            "o",
            color=CURVE_COLORS[1],
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=5,
        )
        text_offset, horizontal_alignment = annotation_positions.get(n, ((5, 4), "left"))
        ax_disc.annotate(
            n,
            (td_ns, r),
            color=TEXT_COLOR,
            textcoords="offset points",
            xytext=text_offset,
            horizontalalignment=horizontal_alignment,
        )

    ax_disc.set_yscale("log")
    ax_disc.set_ylim(1e4, 1e9)
    ax_disc.set_xlabel("Front-end dead time (ns)")
    ax_disc.set_title("Discriminating (counting)")
    ax_disc.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=100))
    ax_disc.yaxis.set_minor_locator(LogLocator(base=10.0, subs=tuple(range(2, 10))))
    ax_disc.yaxis.set_minor_formatter(NullFormatter())
    style_grid(ax_disc)
    ax_disc.legend()

    fig.suptitle("Max pixel count rate: integrating vs discriminating detectors")
    return save_figure(fig, output_path)


def main() -> int:
    output_dir = ROOT / "build" / "detector_model" / datetime.now().astimezone().strftime("%Y%m%d_%H%M")
    plot_hit_rate_vs_fluence(output_path=output_dir / "hit_rate_vs_fluence")
    plot_max_counting_rate_vs_window(output_path=output_dir / "max_counting_rate_vs_window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
