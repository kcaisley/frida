"""Sampler architecture comparisons: one panel per named switch, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.samp.analysis import AnalysisSampHold, AnalysisSampTrack, MeasSamp
from flow.samp.subckt import SampNets


@mpl.rc_context(PLOT_STYLE)
def plot_samp_resistance(
    tracks: Sequence[AnalysisSampTrack],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the switches' on-resistance and remaining track error over the input level."""

    if not tracks or len(tracks) != len(labels):
        raise ValueError("resistance comparison requires one tracking result and label per switch")
    columns = min(2, len(tracks))
    rows = (len(tracks) + columns - 1) // columns
    error_limit_mv = 1.1 * max(np.nanmax(np.abs(item.track_error_v), initial=0.0) for item in tracks) * 1e3 or 1.0
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (track, label) in enumerate(zip(tracks, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogy(track.vin_v, track.on_resistance_ohm, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        error_ax = ax.twinx()
        error_ax.plot(track.vin_v, track.track_error_v * 1e3, "s--", color=NORD_RED, markersize=3)
        error_ax.set_ylim(-error_limit_mv, error_limit_mv)
        error_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(tracks) - 1:
            error_ax.set_ylabel("Track error at the hold edge (mV)", color=NORD_RED)
        finite = track.on_resistance_ohm[np.isfinite(track.on_resistance_ohm)]
        ax.set_title(f"{label}\n{np.min(finite):.3g}–{np.max(finite):.3g} Ω" if len(finite) else label)
        style_grid(ax)
    for ax in axes.flat[len(tracks) :]:
        ax.set_visible(False)
    fig.supxlabel("Input level (V)")
    fig.supylabel("On-resistance into the load (Ω)", color=NORD_BLUE)
    fig.suptitle("Sampler on-resistance and track error versus input level")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_samp_hold(
    holds: Sequence[AnalysisSampHold],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the switches' pedestal and input feedthrough over the input level."""

    if not holds or len(holds) != len(labels):
        raise ValueError("hold comparison requires one hold result and label per switch")
    columns = min(2, len(holds))
    rows = (len(holds) + columns - 1) // columns
    feedthrough_limit = 1.1 * max(np.nanmax(np.abs(item.feedthrough), initial=0.0) for item in holds) * 1e3 or 1.0
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (hold, label) in enumerate(zip(holds, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(hold.vin_v, hold.pedestal_v * 1e3, "o-", color=NORD_BLUE, markersize=3)
        ax.axhline(0.0, color=NORD_DARK, linewidth=0.6)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        feedthrough_ax = ax.twinx()
        feedthrough_ax.plot(hold.vin_v, hold.feedthrough * 1e3, "s--", color=NORD_RED, markersize=3)
        feedthrough_ax.set_ylim(-feedthrough_limit, feedthrough_limit)
        feedthrough_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(holds) - 1:
            feedthrough_ax.set_ylabel("Input feedthrough while held (mV/V)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(holds) :]:
        ax.set_visible(False)
    fig.supxlabel("Input level (V)")
    fig.supylabel("Pedestal (mV)", color=NORD_BLUE)
    fig.suptitle("Sampler pedestal and feedthrough versus input level")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_samp_supply(
    tracks: Sequence[AnalysisSampTrack],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the switches' on-resistance and bandwidth over the supply, at mid-supply input."""

    if not tracks or len(tracks) != len(labels):
        raise ValueError("supply comparison requires one tracking result and label per switch")
    columns = min(2, len(tracks))
    rows = (len(tracks) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (track, label) in enumerate(zip(tracks, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogy(track.vdd_v, track.on_resistance_ohm, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        bandwidth_ax = ax.twinx()
        bandwidth_ax.semilogy(track.vdd_v, track.bandwidth_hz * 1e-6, "s--", color=NORD_RED, markersize=3)
        bandwidth_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(tracks) - 1:
            bandwidth_ax.set_ylabel("Tracking bandwidth (MHz)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(tracks) :]:
        ax.set_visible(False)
    fig.supxlabel("Supply (V)")
    fig.supylabel("On-resistance into the load (Ω)", color=NORD_BLUE)
    fig.suptitle("Sampler on-resistance and bandwidth versus supply, mid-supply input")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_samp_waveforms(
    measurements: Sequence[MeasSamp],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the switches' clock, input and output over their last two periods."""

    if not measurements or len(measurements) != len(labels):
        raise ValueError("waveform comparison requires one measurement and label per switch")
    columns = min(2, len(measurements))
    rows = (len(measurements) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (measurement, label) in enumerate(zip(measurements, labels, strict=True)):
        wave = measurement.wave
        if wave is None:
            raise ValueError("sampler waveforms require a waveform record")
        ax = axes.flat[index]
        start_s = float(wave.time_s[-1]) - 2 * float(measurement.param.clock_period_s)
        shown = wave.time_s >= start_s
        time_ns = (wave.time_s[shown] - start_s) * 1e9
        ax.plot(time_ns, wave.v[SampNets.clk.name][0][shown], ":", color=NORD_DARK, label="clk")
        ax.plot(time_ns, wave.v[SampNets.din.name][0][shown], "--", color=NORD_RED, label="din")
        ax.plot(time_ns, wave.v[SampNets.dout.name][0][shown], "-", color=NORD_BLUE, label="dout")
        ax.set_title(f"{label} at {float(measurement.param.input_voltage):g} V")
        style_grid(ax)
    for ax in axes.flat[len(measurements) :]:
        ax.set_visible(False)
    axes.flat[0].legend()
    fig.supxlabel("Time (ns)")
    fig.supylabel("Voltage (V)")
    fig.suptitle("Sampler waveforms, last two periods")
    return save_figure(fig, output_path)
