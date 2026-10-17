"""Level shifter architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_GREEN, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.lvshift.analysis import AnalysisLvshiftSwitching, MeasLvShift


@mpl.rc_context(PLOT_STYLE)
def plot_lvshift_vddl(
    switchings: Sequence[AnalysisLvshiftSwitching],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the shifters over the input supply: rise and fall delay, and energy per cycle."""

    if not switchings or len(switchings) != len(labels):
        raise ValueError("input supply comparison requires one switching result and label per shifter")
    columns = min(3, len(switchings))
    rows = (len(switchings) + columns - 1) // columns
    energy_limit_fj = 1.1 * max(np.nanmax(item.energy_per_cycle_j, initial=0.0) * 1e15 for item in switchings)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (switching, label) in enumerate(zip(switchings, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogy(
            switching.vddl_v, switching.rise_delay_s * 1e12, "o-", color=NORD_BLUE, markersize=3, label="Rising"
        )
        ax.semilogy(
            switching.vddl_v, switching.fall_delay_s * 1e12, "^--", color=NORD_BLUE, markersize=3, label="Falling"
        )
        ax.tick_params(axis="y", colors=NORD_BLUE)
        energy_ax = ax.twinx()
        energy_ax.plot(switching.vddl_v, switching.energy_per_cycle_j * 1e15, "s-", color=NORD_RED, markersize=3)
        energy_ax.set_ylim(0.0, energy_limit_fj)
        energy_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(switchings) - 1:
            energy_ax.set_ylabel("Energy per input period (fJ)", color=NORD_RED)
        working = switching.vddl_v[switching.switched_fraction == 1.0]
        ax.set_title(f"{label}\nswitches from {np.min(working):g} V" if len(working) else label)
        style_grid(ax)
    for ax in axes.flat[len(switchings) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper right")
    fig.supxlabel("Input supply vddl (V)")
    fig.supylabel("Delay (ps)", color=NORD_BLUE)
    fig.suptitle(f"Level shifter delay and energy versus input supply, {switchings[0].vdd_v[0]:g} V out")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_lvshift_vdd(
    switchings: Sequence[AnalysisLvshiftSwitching],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the shifters over the output supply: rise and fall delay, and idle current."""

    if not switchings or len(switchings) != len(labels):
        raise ValueError("output supply comparison requires one switching result and label per shifter")
    columns = min(3, len(switchings))
    rows = (len(switchings) + columns - 1) // columns
    delay_limit_ps = 1.1 * max(
        np.nanmax(np.r_[item.rise_delay_s, item.fall_delay_s], initial=0.0) * 1e12 for item in switchings
    )
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (switching, label) in enumerate(zip(switchings, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(switching.vdd_v, switching.rise_delay_s * 1e12, "o-", color=NORD_BLUE, markersize=3, label="Rising")
        ax.plot(switching.vdd_v, switching.fall_delay_s * 1e12, "^--", color=NORD_BLUE, markersize=3, label="Falling")
        ax.set_ylim(0.0, delay_limit_ps)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        idle_ax = ax.twinx()
        idle_ax.plot(switching.vdd_v, switching.static_current_a * 1e9, "s-", color=NORD_RED, markersize=3)
        idle_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(switchings) - 1:
            idle_ax.set_ylabel("Idle vdd current (nA)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(switchings) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="lower left")
    fig.supxlabel("Output supply vdd (V)")
    fig.supylabel("Delay (ps)", color=NORD_BLUE)
    fig.suptitle(f"Level shifter delay and idle current versus output supply, {switchings[0].vddl_v[0]:g} V in")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_lvshift_waveforms(
    measurements: Sequence[MeasLvShift],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the shifters' input and outputs over the whole record."""

    if not measurements or len(measurements) != len(labels):
        raise ValueError("waveform comparison requires one measurement and label per shifter")
    fig, axes = plt.subplots(len(measurements), 1, sharex=True, squeeze=False)
    fig.set_size_inches(9.6, 1.9 * len(measurements) + 0.8)
    for ax, measurement, label in zip(axes.flat, measurements, labels, strict=True):
        wave = measurement.wave
        if wave is None:
            raise ValueError("waveform comparison requires waveform records")
        time_ns = wave.time_s * 1e9
        names = [("inp", NORD_GREEN), ("rst", NORD_DARK), ("outp", NORD_BLUE), ("outn", NORD_RED)]
        if measurement.dut.buffers:
            names.append(("bufp", NORD_BLUE))
        for name, color in names:
            ax.plot(time_ns, wave.v[name][0], color=color, label=name, linestyle=":" if name == "bufp" else "-")
        ax.set_title(f"{label} at vddl {float(measurement.param.vddl):g} V")
        ax.legend(loc="center right", fontsize="small", ncols=len(names))
        style_grid(ax)
    fig.supxlabel("Time (ns)")
    fig.supylabel("Voltage (V)")
    fig.suptitle("Level shifter waveforms")
    return save_figure(fig, output_path)
