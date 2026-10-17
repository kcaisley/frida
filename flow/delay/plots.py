"""Delay line and ring oscillator architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_ORANGE, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.delay.analysis import AnalysisDelayOscillation, AnalysisDelayPropagation


@mpl.rc_context(PLOT_STYLE)
def plot_delay_ring_supply(
    oscillations: Sequence[AnalysisDelayOscillation],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare rings over the supply: frequency and energy per cycle."""

    if not oscillations or len(oscillations) != len(labels):
        raise ValueError("ring supply comparison requires one oscillation result and label per ring")
    columns = min(2, len(oscillations))
    rows = (len(oscillations) + columns - 1) // columns
    energy_limit_fj = 1.1 * max(np.nanmax(item.energy_per_cycle_j) * 1e15 for item in oscillations)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (oscillation, label) in enumerate(zip(oscillations, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(oscillation.vdd_v, oscillation.frequency_hz * 1e-9, "o-", color=NORD_BLUE)
        ax.set_ylim(bottom=0.0)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        energy_ax = ax.twinx()
        energy_ax.plot(oscillation.vdd_v, oscillation.energy_per_cycle_j * 1e15, "s-", color=NORD_RED)
        energy_ax.set_ylim(0.0, energy_limit_fj)
        energy_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(oscillations) - 1:
            energy_ax.set_ylabel("Energy per cycle (fJ)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(oscillations) :]:
        ax.set_visible(False)
    fig.supxlabel("Supply (V)")
    fig.supylabel("Frequency (GHz)", color=NORD_BLUE)
    fig.suptitle("Ring frequency and energy per cycle versus supply")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_delay_ring_control(
    oscillations: Sequence[AnalysisDelayOscillation],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare rings over the control voltage: frequency and tuning gain."""

    if not oscillations or len(oscillations) != len(labels):
        raise ValueError("ring control comparison requires one oscillation result and label per ring")
    columns = min(2, len(oscillations))
    rows = (len(oscillations) + columns - 1) // columns
    gains = [np.gradient(item.frequency_hz, item.control_v) * 1e-9 for item in oscillations]
    gain_limit = 1.1 * max(np.nanmax(np.abs(gain)) for gain in gains)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (oscillation, gain, label) in enumerate(zip(oscillations, gains, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(oscillation.control_v, oscillation.frequency_hz * 1e-9, "o-", color=NORD_BLUE)
        ax.set_ylim(bottom=0.0)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        gain_ax = ax.twinx()
        gain_ax.plot(oscillation.control_v, gain, "s-", color=NORD_RED)
        gain_ax.set_ylim(-gain_limit, gain_limit)
        gain_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(oscillations) - 1:
            gain_ax.set_ylabel("Tuning gain (GHz/V)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(oscillations) :]:
        ax.set_visible(False)
    fig.supxlabel("Control voltage (V)")
    fig.supylabel("Frequency (GHz)", color=NORD_BLUE)
    fig.suptitle(f"Ring frequency and tuning gain versus control at {oscillations[0].vdd_v[0]:g} V")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_delay_line_supply(
    propagations: Sequence[AnalysisDelayPropagation],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare delay lines over the supply: rise and fall delay, and energy per input cycle."""

    if not propagations or len(propagations) != len(labels):
        raise ValueError("delay line supply comparison requires one propagation result and label per line")
    columns = min(3, len(propagations))
    rows = (len(propagations) + columns - 1) // columns
    energy_limit_fj = 1.1 * max(np.nanmax(item.energy_per_cycle_j) * 1e15 for item in propagations)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (propagation, label) in enumerate(zip(propagations, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(propagation.vdd_v, propagation.rise_delay_s * 1e12, "o-", color=NORD_BLUE, label="Rising input")
        ax.plot(propagation.vdd_v, propagation.fall_delay_s * 1e12, "^--", color=NORD_BLUE, label="Falling input")
        ax.set_ylim(bottom=0.0)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        energy_ax = ax.twinx()
        energy_ax.plot(propagation.vdd_v, propagation.energy_per_cycle_j * 1e15, "s-", color=NORD_RED)
        energy_ax.set_ylim(0.0, energy_limit_fj)
        energy_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(propagations) - 1:
            energy_ax.set_ylabel("Energy per input cycle (fJ)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(propagations) :]:
        ax.set_visible(False)
    axes.flat[0].legend()
    fig.supxlabel("Supply (V)")
    fig.supylabel("Input to output delay (ps)", color=NORD_BLUE)
    fig.suptitle("Delay line delay and energy versus supply")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_delay_line_control(
    propagations: Sequence[AnalysisDelayPropagation],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare delay lines over the control voltage: delay, and the output's 10–90 % transitions."""

    if not propagations or len(propagations) != len(labels):
        raise ValueError("delay line control comparison requires one propagation result and label per line")
    columns = min(3, len(propagations))
    rows = (len(propagations) + columns - 1) // columns
    transition_limit_ps = 1.1 * max(
        np.nanmax(np.r_[item.output_rise_s, item.output_fall_s]) * 1e12 for item in propagations
    )
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (propagation, label) in enumerate(zip(propagations, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(propagation.control_v, propagation.rise_delay_s * 1e12, "o-", color=NORD_BLUE, label="Rising input")
        ax.plot(propagation.control_v, propagation.fall_delay_s * 1e12, "^--", color=NORD_BLUE, label="Falling input")
        ax.set_yscale("log")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        transition_ax = ax.twinx()
        transition_ax.plot(propagation.control_v, propagation.output_rise_s * 1e12, "s-", color=NORD_RED)
        transition_ax.plot(propagation.control_v, propagation.output_fall_s * 1e12, "v--", color=NORD_ORANGE)
        transition_ax.set_ylim(0.0, transition_limit_ps)
        transition_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(propagations) - 1:
            transition_ax.set_ylabel("Output rise, fall 10–90 % (ps)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(propagations) :]:
        ax.set_visible(False)
    axes.flat[0].legend()
    fig.supxlabel("Control voltage (V)")
    fig.supylabel("Input to output delay (ps)", color=NORD_BLUE)
    fig.suptitle(f"Delay line delay and output transitions versus control at {propagations[0].vdd_v[0]:g} V")
    return save_figure(fig, output_path)
