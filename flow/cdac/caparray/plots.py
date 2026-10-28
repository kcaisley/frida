"""Capacitor-array architecture comparisons: one panel per named array, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.cdac.caparray.analysis import AnalysisCaparrayTransfer, AnalysisCaparrayWeights


@mpl.rc_context(PLOT_STYLE)
def plot_caparray_weights(
    weights: Sequence[AnalysisCaparrayWeights],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the arrays' measured and design stage weights, C0 first, and their error."""

    if not weights or len(weights) != len(labels):
        raise ValueError("weight comparison requires one weight result and label per array")
    columns = min(2, len(weights))
    rows = (len(weights) + columns - 1) // columns
    error_limit = 1.1 * max(np.nanmax(np.abs(item.weight_error), initial=0.0) for item in weights) * 100 or 1.0
    fig, axes = plt.subplots(rows, columns, sharey=True, squeeze=False)
    for index, (weight, label) in enumerate(zip(weights, labels, strict=True)):
        ax = axes.flat[index]
        stage = np.arange(len(weight.design_weight))
        measured = weight.fraction * np.sum(weight.design_weight) / weight.total_fraction
        ax.bar(stage, weight.design_weight, color=NORD_BLUE, alpha=0.35, label="Design")
        ax.semilogy(stage, measured, "o", color=NORD_BLUE, markersize=3, label="Measured")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        error_ax = ax.twinx()
        error_ax.plot(stage, weight.weight_error * 100, "s--", color=NORD_RED, markersize=3)
        error_ax.set_ylim(-error_limit, error_limit)
        error_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(weights) - 1:
            error_ax.set_ylabel("Weight error (%)", color=NORD_RED)
        ax.set_title(f"{label}\n{len(stage)} stages, {weight.total_fraction:.3f} of the supply on the top plate")
        ax.set_xlabel("Stage (C0 first)")
        style_grid(ax)
    for ax in axes.flat[len(weights) :]:
        ax.set_visible(False)
    axes.flat[0].legend()
    fig.supylabel("Stage weight (unit capacitors)", color=NORD_BLUE)
    fig.suptitle("Capacitor-array stage weights")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_caparray_transfer(
    transfers: Sequence[AnalysisCaparrayTransfer],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the arrays' top plate over the packed code ramp against its design weight."""

    if not transfers or len(transfers) != len(labels):
        raise ValueError("transfer comparison requires one transfer result and label per array")
    columns = min(2, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharey=True, squeeze=False)
    for index, (transfer, label) in enumerate(zip(transfers, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(transfer.code, transfer.voltage_v * 1e3, "-", color=NORD_BLUE, linewidth=0.8, label="Top plate")
        ax.plot(
            transfer.code,
            (transfer.voltage_v[0] + (transfer.design_weight - transfer.design_weight[0]) * transfer.volts_per_unit)
            * 1e3,
            ":",
            color=NORD_DARK,
            label="Design weights",
        )
        ax.set_title(f"{label}\n{transfer.volts_per_unit * 1e6:.3g} µV per unit capacitor")
        ax.set_xlabel("Packed code")
        style_grid(ax)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    axes.flat[0].legend()
    fig.supylabel("Top plate (mV)")
    fig.suptitle("Capacitor-array transfer over the packed code ramp")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_caparray_error(
    transfers: Sequence[AnalysisCaparrayTransfer],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the arrays' top-plate error against their design weights over the code ramp."""

    if not transfers or len(transfers) != len(labels):
        raise ValueError("error comparison requires one transfer result and label per array")
    columns = min(2, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (transfer, label) in enumerate(zip(transfers, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(transfer.code, transfer.error_units, "-", color=NORD_RED, linewidth=0.8)
        ax.axhline(0.0, color=NORD_DARK, linewidth=0.6)
        ax.set_title(f"{label}\nlargest {np.nanmax(np.abs(transfer.error_units), initial=0.0):.3g} units")
        style_grid(ax)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    fig.supxlabel("Packed code")
    fig.supylabel("Error against the design weights (unit capacitors)")
    fig.suptitle("Capacitor-array error over the packed code ramp")
    return save_figure(fig, output_path)
