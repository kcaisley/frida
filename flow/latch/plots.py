"""Latch, flip-flop, divider and SR latch architecture comparisons: one panel per named case."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_ORANGE, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.latch.analysis import AnalysisLatchConstraint, AnalysisLatchSr, AnalysisLatchTiming


@mpl.rc_context(PLOT_STYLE)
def plot_latch_setup_hold(
    timings: Sequence[AnalysisLatchTiming],
    constraints: Sequence[AnalysisLatchConstraint],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare setup and hold: clock-to-q and the captured and held fractions versus data offset."""

    if not timings or not len(timings) == len(constraints) == len(labels):
        raise ValueError("setup and hold comparison requires one timing, constraint, and label per case")
    columns = min(3, len(timings))
    rows = (len(timings) + columns - 1) // columns
    delay_limit_ps = 1.1 * max(
        np.nanmax(np.r_[item.clock_to_q_rise_s, item.clock_to_q_fall_s], initial=0.0) * 1e12 for item in timings
    )
    # the window around every case's aperture, from 100 ps before the earliest hold edge
    edges_ps = [value * 1e12 for item in constraints for value in (item.setup_s, -item.hold_s) if np.isfinite(value)]
    window_ps = (min(edges_ps) - 100.0, max(edges_ps) + 150.0) if edges_ps else (None, None)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (timing, constraint, label) in enumerate(zip(timings, constraints, labels, strict=True)):
        ax = axes.flat[index]
        offset_ps = timing.data_offset_s * 1e12
        ax.plot(offset_ps, timing.clock_to_q_rise_s * 1e12, "o-", color=NORD_BLUE, markersize=3, label="q rising")
        ax.plot(offset_ps, timing.clock_to_q_fall_s * 1e12, "^--", color=NORD_BLUE, markersize=3, label="q falling")
        ax.set_ylim(0.0, delay_limit_ps)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        fraction_ax = ax.twinx()
        fraction_ax.plot(offset_ps, timing.captured_fraction, "-", color=NORD_RED, label="New value")
        fraction_ax.plot(offset_ps, timing.held_fraction, "--", color=NORD_ORANGE, label="Old value")
        fraction_ax.set_ylim(-0.05, 1.05)
        fraction_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(timings) - 1:
            fraction_ax.set_ylabel("Fraction of edges", color=NORD_RED)
        for value in (constraint.setup_s, -constraint.hold_s):
            if np.isfinite(value):
                ax.axvline(value * 1e12, color=NORD_DARK, linestyle=":")
        ax.set_xlim(window_ps)
        ax.set_title(f"{label}\nsetup {constraint.setup_s * 1e12:.0f} ps, hold {constraint.hold_s * 1e12:.0f} ps")
        style_grid(ax)
    for ax in axes.flat[len(timings) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="lower right")
    fraction_ax.legend(loc="center right")
    fig.supxlabel("Data edge before the capturing clock edge (ps)")
    fig.supylabel("Launch to q delay (ps)", color=NORD_BLUE)
    fig.suptitle(f"Setup and hold at {timings[0].vdd_v[0]:g} V, {timings[0].clock_period_s[0] * 1e9:g} ns clock")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_latch_supply(
    timings: Sequence[AnalysisLatchTiming],
    srs: Sequence[AnalysisLatchSr],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare every case over the supply: its rise and fall delay, and energy per cycle.

    ``labels`` name the clocked cases first, then the SR latches.
    """

    if not timings and not srs or len(labels) != len(timings) + len(srs):
        raise ValueError("supply comparison requires one label per clocked case and SR latch")
    panels = [
        (item.vdd_v, item.clock_to_q_rise_s, item.clock_to_q_fall_s, item.energy_per_cycle_j, "Clock to q")
        for item in timings
    ] + [(item.vdd_v, item.set_delay_s, item.reset_delay_s, item.energy_per_cycle_j, "Set, reset") for item in srs]
    columns = min(3, len(panels))
    rows = (len(panels) + columns - 1) // columns
    energy_limit_fj = 1.1 * max(np.nanmax(energy, initial=0.0) * 1e15 for *_delays, energy, _kind in panels)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, ((vdd_v, rise, fall, energy, kind), label) in enumerate(zip(panels, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(vdd_v, rise * 1e12, "o-", color=NORD_BLUE, label=f"{kind}: q rising")
        ax.plot(vdd_v, fall * 1e12, "^--", color=NORD_BLUE, label=f"{kind}: q falling")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        if index in (0, len(timings)):
            ax.legend(loc="upper right", fontsize="small")
        energy_ax = ax.twinx()
        energy_ax.plot(vdd_v, energy * 1e15, "s-", color=NORD_RED)
        energy_ax.set_ylim(0.0, energy_limit_fj)
        energy_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(panels) - 1:
            energy_ax.set_ylabel("Energy per cycle (fJ)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    # the shared limit, once every panel has drawn: one panel's would cut the others' data
    axes.flat[0].set_ylim(bottom=0.0)
    for ax in axes.flat[len(panels) :]:
        ax.set_visible(False)
    fig.supxlabel("Supply (V)")
    fig.supylabel("Delay (ps)", color=NORD_BLUE)
    fig.suptitle("Latch delay and energy per cycle versus supply")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_latch_frequency(
    timings: Sequence[AnalysisLatchTiming],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare flip-flops and dividers over the clock frequency: clock-to-q and the edges that capture."""

    if not timings or len(timings) != len(labels):
        raise ValueError("frequency comparison requires one timing result and label per case")
    columns = min(3, len(timings))
    rows = (len(timings) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (timing, label) in enumerate(zip(timings, labels, strict=True)):
        ax = axes.flat[index]
        frequency_ghz = 1e-9 / timing.clock_period_s
        ax.plot(frequency_ghz, timing.clock_to_q_rise_s * 1e12, "o-", color=NORD_BLUE, label="q rising")
        ax.plot(frequency_ghz, timing.clock_to_q_fall_s * 1e12, "^--", color=NORD_BLUE, label="q falling")
        ax.set_xscale("log")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        fraction_ax = ax.twinx()
        fraction_ax.plot(frequency_ghz, timing.captured_fraction, "s-", color=NORD_RED)
        fraction_ax.set_ylim(-0.05, 1.05)
        fraction_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(timings) - 1:
            fraction_ax.set_ylabel("Edges capturing the new value", color=NORD_RED)
        working = frequency_ghz[timing.captured_fraction == 1.0]
        ax.set_title(f"{label}: up to {np.max(working):.3g} GHz" if len(working) else label)
        style_grid(ax)
    # the shared limit, once every panel has drawn: one panel's would cut the others' data
    axes.flat[0].set_ylim(bottom=0.0)
    for ax in axes.flat[len(timings) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper left")
    fig.supxlabel("Clock frequency (GHz)")
    fig.supylabel("Clock to q delay (ps)", color=NORD_BLUE)
    fig.suptitle(f"Flip-flop and divider speed at {timings[0].vdd_v[0]:g} V")
    return save_figure(fig, output_path)
