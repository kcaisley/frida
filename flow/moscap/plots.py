"""MOS capacitor architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.moscap.analysis import AnalysisMoscapCv


@mpl.rc_context(PLOT_STYLE)
def plot_moscap_cv(
    cvs: Sequence[AnalysisMoscapCv],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the capacitors' C-V curves and leakage over their bias."""

    if not cvs or len(cvs) != len(labels):
        raise ValueError("C-V comparison requires one result and label per capacitor")
    columns = min(2, len(cvs))
    rows = (len(cvs) + columns - 1) // columns
    # a model without gate leakage gives none to draw
    leakage_a = np.abs(np.concatenate([item.leakage_a for item in cvs]))
    leaking = leakage_a[leakage_a > 0]
    leakage_limits = (max(np.min(leaking), 1e-15), 2.0 * np.max(leaking)) if leaking.size else (1e-15, 1e-12)
    fig, axes = plt.subplots(rows, columns, sharey=True, squeeze=False)
    for index, (cv, label) in enumerate(zip(cvs, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(cv.bias_v, cv.capacitance_f * 1e15, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        leakage_ax = ax.twinx()
        leakage_ax.set_yscale("log")
        if np.any(cv.leakage_a != 0):
            leakage_ax.plot(cv.bias_v, np.abs(cv.leakage_a), "s-", color=NORD_RED, markersize=3)
        else:
            leakage_ax.text(
                0.5,
                0.5,
                "no gate leakage in the model",
                transform=ax.transAxes,
                ha="center",
                va="center",
                color=NORD_RED,
            )
        leakage_ax.set_ylim(leakage_limits)
        leakage_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(cvs) - 1:
            leakage_ax.set_ylabel("|Leakage| (A)", color=NORD_RED)
        ax.set_title(label)
        ax.set_xlabel("Supply (V)" if cv.dut.mode.name == "DECAP" else "Gate plate over channel plate (V)")
        style_grid(ax)
    # the shared limit, once every panel has drawn: one panel's would cut the others' data
    axes.flat[0].set_ylim(bottom=0.0)
    for ax in axes.flat[len(cvs) :]:
        ax.set_visible(False)
    fig.supylabel(f"Capacitance at {cvs[0].frequency_hz[0] * 1e-6:g} MHz (fF)", color=NORD_BLUE)
    fig.suptitle("MOS capacitor C-V and leakage")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_moscap_frequency(
    cvs: Sequence[AnalysisMoscapCv],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the capacitors' capacitance and quality factor over frequency, at one bias each (their first)."""

    if not cvs or len(cvs) != len(labels):
        raise ValueError("frequency comparison requires one result and label per capacitor")
    columns = min(2, len(cvs))
    rows = (len(cvs) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (cv, label) in enumerate(zip(cvs, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogx(cv.frequency_hz, cv.capacitance_spectrum_f[0] * 1e15, "-", color=NORD_BLUE)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        quality_ax = ax.twinx()
        quality_ax.loglog(cv.frequency_hz, cv.quality_spectrum[0], "--", color=NORD_RED)
        quality_ax.axhline(1.0, color=NORD_RED, linewidth=0.6, linestyle=":")
        quality_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(cvs) - 1:
            quality_ax.set_ylabel("Quality factor", color=NORD_RED)
        ax.set_title(f"{label} at {cv.bias_v[0]:g} V")
        style_grid(ax)
    # the shared limit, once every panel has drawn: one panel's would cut the others' data
    axes.flat[0].set_ylim(bottom=0.0)
    for ax in axes.flat[len(cvs) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Capacitance (fF)", color=NORD_BLUE)
    fig.suptitle("MOS capacitor capacitance and quality factor versus frequency")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_moscap_quality(
    cvs: Sequence[AnalysisMoscapCv],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the capacitors' quality factor and series resistance near 1 GHz over their bias."""

    if not cvs or len(cvs) != len(labels):
        raise ValueError("quality comparison requires one result and label per capacitor")
    columns = min(2, len(cvs))
    rows = (len(cvs) + columns - 1) // columns
    # a model without AC loss gives no series resistance at all
    resistance_limit = 1.1 * max(np.nanmax(item.series_resistance_ohm, initial=0.0) for item in cvs) or 1.0
    fig, axes = plt.subplots(rows, columns, sharey=True, squeeze=False)
    for index, (cv, label) in enumerate(zip(cvs, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogy(cv.bias_v, cv.quality, "o-", color=NORD_BLUE, markersize=3)
        if not np.any(np.isfinite(cv.quality)):
            ax.text(0.5, 0.5, "no AC loss in the model", transform=ax.transAxes, ha="center", va="center")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        resistance_ax = ax.twinx()
        resistance_ax.plot(cv.bias_v, cv.series_resistance_ohm, "s-", color=NORD_RED, markersize=3)
        resistance_ax.set_ylim(0.0, resistance_limit)
        resistance_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(cvs) - 1:
            resistance_ax.set_ylabel("Series resistance (Ω)", color=NORD_RED)
        ax.set_title(label)
        ax.set_xlabel("Supply (V)" if cv.dut.mode.name == "DECAP" else "Gate plate over channel plate (V)")
        style_grid(ax)
    for ax in axes.flat[len(cvs) :]:
        ax.set_visible(False)
    fig.supylabel(f"Quality factor at {cvs[0].loss_frequency_hz * 1e-9:g} GHz", color=NORD_BLUE)
    fig.suptitle("MOS capacitor loss versus bias")
    return save_figure(fig, output_path)
