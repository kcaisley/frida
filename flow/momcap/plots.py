"""FMOM capacitor comparisons: the styles' length and spacing fits, and their scaling across PDKs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import CURVE_COLORS, PLOT_STYLE, save_figure, style_grid
from flow.momcap.analysis import AnalysisMomcapFit


@mpl.rc_context(PLOT_STYLE)
def plot_momcap_fit(
    fits: Sequence[AnalysisMomcapFit],
    *,
    title: str,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the styles' extracted capacitance against plate length at the minimum spacing, one
    panel per style, one curve per stacked-metal count, each with its model; the model's relative
    error at every extracted spacing below."""

    if not fits:
        raise ValueError("the fit comparison requires at least one fit")
    styles = list(dict.fromkeys(fit.dut.style for fit in fits))
    fig, axes = plt.subplots(2, len(styles), sharex=True, squeeze=False, height_ratios=(3, 1))
    for column, style in enumerate(styles):
        ax, error_ax = axes[0, column], axes[1, column]
        for fit in (item for item in fits if item.dut.style == style):
            color = CURVE_COLORS[(fit.dut.layers - 1) % len(CURVE_COLORS)]
            closest = fit.space_nm == fit.min_space_nm
            order = np.argsort(fit.length_um[closest])
            span = np.linspace(0.0, float(np.max(fit.length_um)), 50)
            ax.plot(
                fit.length_um[closest][order], fit.capacitance_f[closest][order] * 1e15, "o", color=color, markersize=3
            )
            ax.plot(
                span,
                (fit.slope_f_per_um * span + fit.gamma_f) * 1e15,
                "-",
                color=color,
                linewidth=0.8,
                label=f"{fit.dut.layers} layer{'s' if fit.dut.layers > 1 else ''}: "
                f"{fit.slope_f_per_um * 1e15:.3f} L + {fit.gamma_f * 1e15:.3f}",
            )
            error_ax.plot(fit.length_um, fit.fit_error * 100, "o", color=color, markersize=2)
        ax.set_title(style.name.lower())
        ax.legend(title="C (fF), L (µm), minimum s")
        error_ax.set_xlabel("Plate length (µm)")
        for item in (ax, error_ax):
            style_grid(item)
    axes[0, 0].set_ylabel("Plate-to-plate C (fF)")
    axes[1, 0].set_ylabel("Model error (%)")
    fig.suptitle(title)
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_momcap_spacing(
    fits: Sequence[AnalysisMomcapFit],
    *,
    title: str,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the styles' capacitance per plate length against plate spacing: one panel per style,
    one curve per stacked-metal count, each spacing's own length fit as a point and the model,
    alpha / s + beta, as the line."""

    if not fits:
        raise ValueError("the spacing comparison requires at least one fit")
    styles = list(dict.fromkeys(fit.dut.style for fit in fits))
    fig, axes = plt.subplots(1, len(styles), sharey=True, squeeze=False)
    for column, style in enumerate(styles):
        ax = axes[0, column]
        for fit in (item for item in fits if item.dut.style == style):
            color = CURVE_COLORS[(fit.dut.layers - 1) % len(CURVE_COLORS)]
            span = np.linspace(float(fit.spacings_nm[0]) * 0.8, float(fit.spacings_nm[-1]) * 1.1, 50)
            ax.plot(fit.spacings_nm, fit.spacing_slopes_f_per_um * 1e15, "o", color=color, markersize=3)
            ax.plot(
                span,
                (fit.alpha_f_nm_per_um / span + fit.beta_f_per_um) * 1e15,
                "-",
                color=color,
                linewidth=0.8,
                label=f"{fit.dut.layers} layer{'s' if fit.dut.layers > 1 else ''}: "
                f"{fit.alpha_f_nm_per_um * 1e15:.1f} / s + {fit.beta_f_per_um * 1e15:.3f}",
            )
        ax.set_title(style.name.lower())
        ax.set_xlabel("Plate spacing s (nm)")
        ax.legend(title="C / L (fF/µm), s (nm)")
        style_grid(ax)
    axes[0, 0].set_ylim(bottom=0.0)
    axes[0, 0].set_ylabel("Plate-to-plate C per length (fF/µm)")
    fig.suptitle(title)
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_momcap_scaling(
    fits: Sequence[AnalysisMomcapFit],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the fits' capacitance per plate length across PDKs: one panel per style, one curve
    per stacked-metal count, the PDKs (``labels``, one per fit, in order along the x axis)."""

    if not fits or len(fits) != len(labels):
        raise ValueError("the scaling comparison requires one label per fit")
    order = list(dict.fromkeys(labels))
    styles = list(dict.fromkeys(fit.dut.style for fit in fits))
    fig, axes = plt.subplots(1, len(styles), sharey=True, squeeze=False)
    for column, style in enumerate(styles):
        ax = axes[0, column]
        for layers in sorted({fit.dut.layers for fit in fits}):
            points = [
                (order.index(label), fit.slope_f_per_um * 1e15)
                for fit, label in zip(fits, labels, strict=True)
                if fit.dut.style == style and fit.dut.layers == layers
            ]
            if points:
                x, y = zip(*sorted(points), strict=True)
                ax.plot(x, y, "o-", color=CURVE_COLORS[(layers - 1) % len(CURVE_COLORS)], label=f"{layers} layers")
        ax.set_xticks(range(len(order)), order)
        ax.set_title(style.name.lower())
        style_grid(ax)
    axes[0, 0].set_ylim(bottom=0.0)
    axes[0, 0].set_ylabel("Plate-to-plate C per length (fF/µm)")
    axes[0, 0].legend()
    fig.suptitle("FMOM capacitance per length across PDKs, at minimum width and spacing")
    return save_figure(fig, output_path)
