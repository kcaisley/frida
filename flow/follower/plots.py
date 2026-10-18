"""Follower architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.follower.analysis import (
    AnalysisFollowerImpedance,
    AnalysisFollowerSlew,
    AnalysisFollowerTransfer,
    MeasFollowerStep,
)


@mpl.rc_context(PLOT_STYLE)
def plot_follower_transfer(
    transfers: Sequence[AnalysisFollowerTransfer],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the followers' DC transfer and small-signal gain over the input level."""

    if not transfers or len(transfers) != len(labels):
        raise ValueError("transfer comparison requires one transfer result and label per follower")
    columns = min(2, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (transfer, label) in enumerate(zip(transfers, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(transfer.vin_v, transfer.vin_v, ":", color=NORD_DARK, label="Input")
        ax.plot(transfer.vin_v, transfer.vout_v, "o-", color=NORD_BLUE, markersize=3, label="Output")
        ax.tick_params(axis="y", colors=NORD_BLUE)
        gain_ax = ax.twinx()
        gain_ax.plot(transfer.vin_v, transfer.gain_v_per_v, "s-", color=NORD_RED, markersize=3)
        gain_ax.set_ylim(0.0, 1.05)
        gain_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(transfers) - 1:
            gain_ax.set_ylabel("Small-signal gain (V/V)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper left")
    fig.supxlabel("Input (V)")
    fig.supylabel("Output (V)", color=NORD_BLUE)
    fig.suptitle("Follower transfer and small-signal gain versus input level")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_follower_bandwidth(
    transfers: Sequence[AnalysisFollowerTransfer],
    impedances: Sequence[AnalysisFollowerImpedance],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the followers' bandwidth and output impedance over the input level."""

    if not transfers or not len(transfers) == len(impedances) == len(labels):
        raise ValueError("bandwidth comparison requires one transfer, impedance, and label per follower")
    columns = min(2, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    impedances_ohm = np.concatenate([item.impedance_ohm for item in impedances])
    impedance_limits = (0.5 * np.nanmin(impedances_ohm), 2.0 * np.nanmax(impedances_ohm))
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (transfer, impedance, label) in enumerate(zip(transfers, impedances, labels, strict=True)):
        ax = axes.flat[index]
        # bandwidth only where the follower follows: a gain of at least half
        working = transfer.gain_v_per_v >= 0.5
        ax.semilogy(transfer.vin_v[working], transfer.bandwidth_hz[working], "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        impedance_ax = ax.twinx()
        impedance_ax.semilogy(impedance.vin_v, impedance.impedance_ohm, "s-", color=NORD_RED, markersize=3)
        impedance_ax.set_ylim(impedance_limits)
        impedance_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(transfers) - 1:
            impedance_ax.set_ylabel("Output impedance (Ω)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    fig.supxlabel("Input (V)")
    fig.supylabel("−3 dB bandwidth where gain ≥ 0.5 (Hz)", color=NORD_BLUE)
    fig.suptitle("Follower bandwidth and output impedance versus input level")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_follower_response(
    transfers: Sequence[AnalysisFollowerTransfer],
    impedances: Sequence[AnalysisFollowerImpedance],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the followers' gain and output impedance over frequency, at one input level each (their first)."""

    if not transfers or not len(transfers) == len(impedances) == len(labels):
        raise ValueError("response comparison requires one transfer, impedance, and label per follower")
    columns = min(2, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (transfer, impedance, label) in enumerate(zip(transfers, impedances, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogx(transfer.frequency_hz, transfer.response_db[0], "-", color=NORD_BLUE)
        ax.set_ylim(-40.0, 5.0)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        impedance_ax = ax.twinx()
        impedance_ax.loglog(impedance.frequency_hz, 10 ** (impedance.impedance_db_ohm[0] / 20), "--", color=NORD_RED)
        impedance_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(transfers) - 1:
            impedance_ax.set_ylabel("Output impedance (Ω)", color=NORD_RED)
        ax.set_title(f"{label} at {transfer.vin_v[0]:g} V")
        style_grid(ax)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Gain (dB)", color=NORD_BLUE)
    fig.suptitle("Follower gain and output impedance versus frequency")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_follower_psrr(
    transfers: Sequence[AnalysisFollowerTransfer],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the followers' supply rejection at the lowest frequency over the input level."""

    if not transfers or len(transfers) != len(labels):
        raise ValueError("PSRR comparison requires one transfer result and label per follower")
    columns = min(2, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (transfer, label) in enumerate(zip(transfers, labels, strict=True)):
        ax = axes.flat[index]
        # only where the follower follows: a gain of at least half
        working = transfer.gain_v_per_v >= 0.5
        ax.plot(transfer.vin_v[working], transfer.psrr_db[working], "o-", color=NORD_BLUE, markersize=3)
        ax.axhline(0.0, color=NORD_DARK, linewidth=0.8)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    fig.supxlabel("Input (V)")
    fig.supylabel("PSRR where gain ≥ 0.5 (dB)")
    fig.suptitle("Follower supply rejection versus input level")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_follower_slew(
    measurements: Sequence[MeasFollowerStep],
    slews: Sequence[AnalysisFollowerSlew],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the followers' large-signal step responses: input and output, slew rates in each title."""

    if not measurements or not len(measurements) == len(slews) == len(labels):
        raise ValueError("slew comparison requires one step record, slew result, and label per follower")
    columns = min(2, len(measurements))
    rows = (len(measurements) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, squeeze=False)
    for index, (measurement, slew, label) in enumerate(zip(measurements, slews, labels, strict=True)):
        ax = axes.flat[index]
        wave = measurement.wave
        if wave is None:
            raise ValueError("slew comparison requires waveform records")
        ax.plot(wave.time_s * 1e9, wave.v["vin"][0], ":", color=NORD_DARK, label="Input")
        ax.plot(wave.time_s * 1e9, wave.v["vout"][0], "-", color=NORD_BLUE, label="Output")
        ax.set_title(
            f"{label}\nslew +{slew.rise_slew_v_per_s[0] * 1e-9:.2g} / {slew.fall_slew_v_per_s[0] * 1e-9:.2g} V/ns"
        )
        style_grid(ax)
    for ax in axes.flat[len(measurements) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper right", fontsize="small")
    fig.supxlabel("Time (ns)")
    fig.supylabel("Voltage (V)")
    fig.suptitle("Follower step response at the nominal input")
    return save_figure(fig, output_path)
