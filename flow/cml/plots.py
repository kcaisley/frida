"""CML architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_GREEN, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.cml.analysis import AnalysisCmlSwitching, MeasCml


@mpl.rc_context(PLOT_STYLE)
def plot_cml_frequency(
    switchings: Sequence[AnalysisCmlSwitching],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the gates over the clock frequency: swing and delay, failing points hollow."""

    if not switchings or len(switchings) != len(labels):
        raise ValueError("frequency comparison requires one switching result and label per gate")
    columns = min(3, len(switchings))
    rows = (len(switchings) + columns - 1) // columns
    delay_limit_ps = 1.1 * max(np.nanmax(item.delay_s) * 1e12 for item in switchings)
    swing_limit_mv = 1.1 * max(np.nanmax(item.swing_v) * 1e3 for item in switchings)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (switching, label) in enumerate(zip(switchings, labels, strict=True)):
        ax = axes.flat[index]
        frequency_ghz = 1e-9 / switching.clock_period_s
        working = switching.correct_fraction == 1.0
        ax.semilogx(frequency_ghz, switching.swing_v * 1e3, "-", color=NORD_BLUE)
        ax.semilogx(frequency_ghz[working], switching.swing_v[working] * 1e3, "o", color=NORD_BLUE, markersize=4)
        ax.semilogx(
            frequency_ghz[~working], switching.swing_v[~working] * 1e3, "o", mfc="none", color=NORD_BLUE, markersize=4
        )
        ax.set_ylim(0.0, swing_limit_mv)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        delay_ax = ax.twinx()
        delay_ax.semilogx(frequency_ghz, switching.delay_s * 1e12, "s--", color=NORD_RED, markersize=3)
        delay_ax.set_ylim(0.0, delay_limit_ps)
        delay_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(switchings) - 1:
            delay_ax.set_ylabel("Delay (ps)", color=NORD_RED)
        fastest = frequency_ghz[working]
        ax.set_title(f"{label}\nworks to {np.max(fastest):.3g} GHz" if len(fastest) else label)
        style_grid(ax)
    for ax in axes.flat[len(switchings) :]:
        ax.set_visible(False)
    fig.supxlabel("Clock frequency (GHz), data at 1/2.6 of it")
    fig.supylabel("Single-ended swing (mV)", color=NORD_BLUE)
    fig.suptitle("CML swing and delay versus frequency (hollow: wrong output)")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_cml_tail(
    switchings: Sequence[AnalysisCmlSwitching],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the gates over the tail's gate drive: swing and supply current, failing points hollow."""

    if not switchings or len(switchings) != len(labels):
        raise ValueError("tail comparison requires one switching result and label per gate")
    columns = min(3, len(switchings))
    rows = (len(switchings) + columns - 1) // columns
    current_limit_ua = 1.1 * max(np.nanmax(item.supply_current_a) * 1e6 for item in switchings)
    swing_limit_mv = 1.1 * max(np.nanmax(item.swing_v) * 1e3 for item in switchings)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (switching, label) in enumerate(zip(switchings, labels, strict=True)):
        ax = axes.flat[index]
        working = switching.correct_fraction == 1.0
        ax.plot(switching.tail_drive_v, switching.swing_v * 1e3, "-", color=NORD_BLUE)
        ax.plot(switching.tail_drive_v[working], switching.swing_v[working] * 1e3, "o", color=NORD_BLUE, markersize=4)
        ax.plot(
            switching.tail_drive_v[~working],
            switching.swing_v[~working] * 1e3,
            "o",
            mfc="none",
            color=NORD_BLUE,
            markersize=4,
        )
        ax.set_ylim(0.0, swing_limit_mv)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        current_ax = ax.twinx()
        current_ax.plot(switching.tail_drive_v, switching.supply_current_a * 1e6, "s--", color=NORD_RED, markersize=3)
        current_ax.set_ylim(0.0, current_limit_ua)
        current_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(switchings) - 1:
            current_ax.set_ylabel("Supply current (µA)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(switchings) :]:
        ax.set_visible(False)
    fig.supxlabel("Tail gate drive from its rail (V)")
    fig.supylabel("Single-ended swing (mV)", color=NORD_BLUE)
    fig.suptitle(
        f"CML swing and current versus tail bias at {1e-9 / switchings[0].clock_period_s[0]:g} GHz (hollow: wrong output)"
    )
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_cml_waveforms(
    measurements: Sequence[MeasCml],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the gates' differential input, clock and output over their last four clock periods."""

    if not measurements or len(measurements) != len(labels):
        raise ValueError("waveform comparison requires one measurement and label per gate")
    columns = min(3, len(measurements))
    rows = (len(measurements) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharey=True, squeeze=False)
    for index, (measurement, label) in enumerate(zip(measurements, labels, strict=True)):
        ax = axes.flat[index]
        wave = measurement.wave
        if wave is None:
            raise ValueError("waveform comparison requires waveform records")
        period = float(measurement.param.clock_period_s)
        shown = wave.time_s >= wave.time_s[-1] - 4 * period
        time_ps = (wave.time_s[shown] - wave.time_s[shown][0]) * 1e12
        for name, color, style in (("in", NORD_GREEN, ":"), ("clk", NORD_DARK, "--"), ("out", NORD_BLUE, "-")):
            difference = wave.v[f"{name}p"][0][shown] - wave.v[f"{name}n"][0][shown]
            ax.plot(time_ps, difference * 1e3, style, color=color, label=name)
        ax.set_title(label)
        ax.set_xlabel("Time (ps)")
        style_grid(ax)
    for ax in axes.flat[len(measurements) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="lower right")
    fig.supylabel("Differential voltage (mV)")
    fig.suptitle(f"CML waveforms at a {float(measurements[0].param.clock_period_s) * 1e12:g} ps clock")
    return save_figure(fig, output_path)
