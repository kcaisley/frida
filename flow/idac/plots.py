"""Current source architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.idac.analysis import AnalysisIdacOutput, AnalysisIdacSteering


@mpl.rc_context(PLOT_STYLE)
def plot_idac_iv(
    outputs: Sequence[AnalysisIdacOutput],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the units' output characteristics at one bias each (their first): current and output resistance."""

    if not outputs or len(outputs) != len(labels):
        raise ValueError("I-V comparison requires one output result and label per unit")
    columns = min(2, len(outputs))
    rows = (len(outputs) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, squeeze=False)
    for index, (output, label) in enumerate(zip(outputs, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(output.vout_v, output.iv_current_a[0] * 1e6, "-", color=NORD_BLUE)
        for edge in (output.compliance_low_v[0], output.compliance_high_v[0]):
            ax.axvline(edge, color=NORD_DARK, linestyle=":")
        ax.set_ylim(bottom=0.0)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        resistance_ax = ax.twinx()
        resistance_ax.semilogy(output.vout_v, output.iv_resistance_ohm[0], "--", color=NORD_RED)
        resistance_ax.set_ylim(1e3, 1e9)
        resistance_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(outputs) - 1:
            resistance_ax.set_ylabel("Output resistance (Ω)", color=NORD_RED)
        ax.set_title(
            f"{label}\n{output.current_a[0] * 1e6:.3g} µA, {output.output_resistance_ohm[0] * 1e-3:.3g} kΩ, "
            f"5 % over {output.compliance_low_v[0]:.2f}–{output.compliance_high_v[0]:.2f} V"
        )
        style_grid(ax)
    for ax in axes.flat[len(outputs) :]:
        ax.set_visible(False)
    fig.supxlabel("Output voltage (V)")
    fig.supylabel("Output current (µA)", color=NORD_BLUE)
    fig.suptitle("Current source output characteristic at its nominal bias")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_idac_bias(
    outputs: Sequence[AnalysisIdacOutput],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the units over their bias (gate voltage or reference current): current and output resistance."""

    if not outputs or len(outputs) != len(labels):
        raise ValueError("bias comparison requires one output result and label per unit")
    columns = min(2, len(outputs))
    rows = (len(outputs) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, squeeze=False)
    for index, (output, label) in enumerate(zip(outputs, labels, strict=True)):
        ax = axes.flat[index]
        diode = bool(np.all(np.isfinite(output.iref_a)))
        bias = output.iref_a * 1e6 if diode else output.vbias_v
        ax.semilogy(bias, output.current_a * 1e6, "o-", color=NORD_BLUE, markersize=3)
        if diode:
            ax.set_xscale("log")
        ax.set_xlabel("Reference current (µA)" if diode else "Gate voltage vbias (V)")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        resistance_ax = ax.twinx()
        resistance_ax.semilogy(bias, output.output_resistance_ohm, "s-", color=NORD_RED, markersize=3)
        resistance_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(outputs) - 1:
            resistance_ax.set_ylabel("Output resistance (Ω)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(outputs) :]:
        ax.set_visible(False)
    fig.supylabel("Output current (µA)", color=NORD_BLUE)
    fig.suptitle(f"Current and output resistance versus bias at {outputs[0].vout_v[-1] / 2:g} V out")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_idac_steering(
    steerings: Sequence[AnalysisIdacSteering],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the switched units over their bias: on and off current, and current lost between the states."""

    if not steerings or len(steerings) != len(labels):
        raise ValueError("steering comparison requires one steering result and label per unit")
    columns = min(2, len(steerings))
    rows = (len(steerings) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (steering, label) in enumerate(zip(steerings, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogy(steering.vbias_v, steering.on_current_a, "o-", color=NORD_BLUE, markersize=3, label="On")
        ax.semilogy(steering.vbias_v, steering.off_current_a, "^--", color=NORD_BLUE, markersize=3, label="Off")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        change_ax = ax.twinx()
        change_ax.plot(steering.vbias_v, steering.total_change * 100, "s-", color=NORD_RED, markersize=3)
        change_ax.set_ylim(-105.0, 5.0)
        change_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(steerings) - 1:
            change_ax.set_ylabel("Output plus dump change, off to on (%)", color=NORD_RED)
        ax.set_title(f"{label}\non-off ratio {np.min(steering.on_off_ratio):.2g}–{np.max(steering.on_off_ratio):.2g}")
        style_grid(ax)
    for ax in axes.flat[len(steerings) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="lower right")
    fig.supxlabel("Gate voltage vbias (V)")
    fig.supylabel("Output current (A)", color=NORD_BLUE)
    fig.suptitle("Switched and steered units: on, off, and the current kept")
    return save_figure(fig, output_path)
