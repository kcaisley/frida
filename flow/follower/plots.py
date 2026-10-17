"""Follower architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.follower.analysis import AnalysisFollowerImpedance, AnalysisFollowerTransfer


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
