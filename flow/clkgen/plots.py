"""Clock conditioning architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import (
    NORD_BLUE,
    NORD_DARK,
    NORD_GREEN,
    NORD_ORANGE,
    NORD_RED,
    PLOT_STYLE,
    save_figure,
    style_grid,
)
from flow.clkgen.analysis import AnalysisClkgenTiming, MeasClkgen


@mpl.rc_context(PLOT_STYLE)
def plot_clkgen_supply(
    timings: Sequence[AnalysisClkgenTiming],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the clock functions over the supply: delay, and outp's high width and the output gaps."""

    if not timings or len(timings) != len(labels):
        raise ValueError("supply comparison requires one timing result and label per function")
    columns = min(3, len(timings))
    rows = (len(timings) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (timing, label) in enumerate(zip(timings, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(timing.vdd_v, timing.delay_s * 1e12, "o-", color=NORD_BLUE, markersize=3)
        ax.set_ylim(bottom=0.0)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        width_ax = ax.twinx()
        width_ax.plot(timing.vdd_v, timing.high_width_s * 1e12, "s-", color=NORD_RED, markersize=3, label="outp high")
        width_ax.plot(
            timing.vdd_v, timing.rise_gap_s * 1e12, "^--", color=NORD_ORANGE, markersize=3, label="outp to outn"
        )
        width_ax.plot(
            timing.vdd_v, timing.fall_gap_s * 1e12, "v:", color=NORD_ORANGE, markersize=3, label="outn to outp"
        )
        width_ax.axhline(0.0, color=NORD_DARK, linewidth=0.6)
        width_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(timings) - 1:
            width_ax.set_ylabel("Width and gaps (ps)", color=NORD_RED)
        if index == 0:
            width_ax.legend(loc="upper right", fontsize="small")
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(timings) :]:
        ax.set_visible(False)
    fig.supxlabel("Supply (V)")
    fig.supylabel("clk to outp delay (ps)", color=NORD_BLUE)
    fig.suptitle(f"Clock timing versus supply at a {timings[0].period_s[0] * 1e9:g} ns clock")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_clkgen_frequency(
    timings: Sequence[AnalysisClkgenTiming],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the clock functions over the clock frequency: outp's duty and the share of periods that pulse."""

    if not timings or len(timings) != len(labels):
        raise ValueError("frequency comparison requires one timing result and label per function")
    columns = min(3, len(timings))
    rows = (len(timings) + columns - 1) // columns
    energy_limit_fj = 1.1 * max(np.nanmax(item.energy_per_cycle_j) * 1e15 for item in timings)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (timing, label) in enumerate(zip(timings, labels, strict=True)):
        ax = axes.flat[index]
        frequency_ghz = 1e-9 / timing.period_s
        ax.semilogx(frequency_ghz, timing.duty_cycle, "o-", color=NORD_BLUE, markersize=3, label="outp duty")
        ax.semilogx(
            frequency_ghz, timing.pulse_fraction, "^--", color=NORD_GREEN, markersize=3, label="Periods pulsing"
        )
        ax.set_ylim(-0.05, 1.1)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        energy_ax = ax.twinx()
        energy_ax.semilogx(frequency_ghz, timing.energy_per_cycle_j * 1e15, "s-", color=NORD_RED, markersize=3)
        energy_ax.set_ylim(0.0, energy_limit_fj)
        energy_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(timings) - 1:
            energy_ax.set_ylabel("Energy per cycle (fJ)", color=NORD_RED)
        working = frequency_ghz[timing.pulse_fraction == 1.0]
        ax.set_title(f"{label}\npulses every period to {np.max(working):.3g} GHz" if len(working) else label)
        style_grid(ax)
    for ax in axes.flat[len(timings) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="center left", fontsize="small")
    fig.supxlabel("Clock frequency (GHz)")
    fig.supylabel("Share", color=NORD_BLUE)
    fig.suptitle(f"Clock functions versus frequency at {timings[0].vdd_v[0]:g} V")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_clkgen_waveforms(
    measurements: Sequence[MeasClkgen],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the clock functions' clk, en, outp and outn from the start through the enable."""

    if not measurements or len(measurements) != len(labels):
        raise ValueError("waveform comparison requires one measurement and label per function")
    fig, axes = plt.subplots(len(measurements), 1, sharex=True, squeeze=False)
    fig.set_size_inches(9.6, 1.9 * len(measurements) + 0.8)
    for ax, measurement, label in zip(axes.flat, measurements, labels, strict=True):
        wave = measurement.wave
        if wave is None:
            raise ValueError("waveform comparison requires waveform records")
        shown = wave.time_s <= 5 * float(measurement.param.period_s)
        time_ns = wave.time_s[shown] * 1e9
        vdd = float(measurement.param.vdd)
        # stacked lanes, one supply high each
        for lane, (name, color) in enumerate(
            (("clk", NORD_DARK), ("en", NORD_GREEN), ("outp", NORD_BLUE), ("outn", NORD_RED))
        ):
            ax.plot(time_ns, wave.v[name][0][shown] + 1.5 * vdd * (3 - lane), color=color, label=name)
        ax.set_yticks([1.5 * vdd * (3 - lane) + vdd / 2 for lane in range(4)], ["clk", "en", "outp", "outn"])
        ax.set_title(label)
        style_grid(ax)
    fig.supxlabel("Time (ns)")
    fig.suptitle("Clock functions through the enable")
    return save_figure(fig, output_path)
