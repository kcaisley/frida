"""Discriminator comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.disc.analysis import AnalysisDiscDelay, AnalysisDiscTrip


@mpl.rc_context(PLOT_STYLE)
def plot_disc_transfer(
    trips: Sequence[AnalysisDiscTrip],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the discriminators' output over the triangle's input, up and back down, with the
    offset and hysteresis in each title."""

    if not trips or len(trips) != len(labels):
        raise ValueError("transfer comparison requires one trip result and label per discriminator")
    columns = min(2, len(trips))
    rows = (len(trips) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, squeeze=False)
    for index, (trip, label) in enumerate(zip(trips, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(trip.inp_v[0] * 1e3, trip.out_v[0], "-", color=NORD_BLUE)
        for level in (trip.rise_trip_v[0], trip.fall_trip_v[0]):
            ax.axvline(level * 1e3, color=NORD_DARK, linestyle=":", linewidth=0.8)
        ax.set_title(f"{label}\noffset {trip.offset_v[0] * 1e3:.2g} mV, hysteresis {trip.hysteresis_v[0] * 1e3:.2g} mV")
        style_grid(ax)
    for ax in axes.flat[len(trips) :]:
        ax.set_visible(False)
    fig.supxlabel("Input less threshold (mV)")
    fig.supylabel("Output (V)")
    fig.suptitle("Discriminator transfer on a slow triangle")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_disc_delay(
    delays: Sequence[AnalysisDiscDelay],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the discriminators' rising and falling delay over the overdrive, the timewalk from
    the smallest overdrive that fires to the largest in each title."""

    if not delays or len(delays) != len(labels):
        raise ValueError("delay comparison requires one delay result and label per discriminator")
    columns = min(2, len(delays))
    rows = (len(delays) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (delay, label) in enumerate(zip(delays, labels, strict=True)):
        ax = axes.flat[index]
        overdrive_mv = delay.overdrive_v * 1e3
        ax.loglog(overdrive_mv, delay.rise_delay_s * 1e9, "o-", color=NORD_BLUE, markersize=3, label="Rising")
        ax.loglog(overdrive_mv, delay.fall_delay_s * 1e9, "s-", color=NORD_RED, markersize=3, label="Falling")
        fired = np.isfinite(delay.timewalk_s)
        timewalk = delay.timewalk_s[fired][0] if np.any(fired) else np.nan
        smallest = overdrive_mv[fired][0] if np.any(fired) else np.nan
        ax.set_title(f"{label}\ntimewalk {timewalk * 1e9:.3g} ns from {smallest:g} mV")
        style_grid(ax)
    for ax in axes.flat[len(delays) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper right", fontsize="small")
    fig.supxlabel("Overdrive (mV)")
    fig.supylabel("Delay from the threshold crossing (ns)")
    fig.suptitle("Discriminator delay versus overdrive")
    return save_figure(fig, output_path)
