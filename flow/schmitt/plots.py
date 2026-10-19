"""Schmitt trigger comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.schmitt.analysis import AnalysisSchmittDelay, AnalysisSchmittTrip


@mpl.rc_context(PLOT_STYLE)
def plot_schmitt_transfer(
    trips: Sequence[AnalysisSchmittTrip],
    delays: Sequence[AnalysisSchmittDelay],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the triggers' output over the triangle's input at the core supply (each trip
    result's last row), with the trip points, hysteresis and step delays in each title."""

    if not trips or not len(trips) == len(delays) == len(labels):
        raise ValueError("transfer comparison requires one trip result, delay result and label per trigger")
    columns = min(2, len(trips))
    rows = (len(trips) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (trip, delay, label) in enumerate(zip(trips, delays, labels, strict=True)):
        ax = axes.flat[index]
        row = int(np.argmin(np.abs(trip.vdd_v - delay.vdd_v[0])))
        ax.plot(trip.inp_v[row], trip.out_v[row], "-", color=NORD_BLUE)
        for level in (trip.rise_trip_v[row], trip.fall_trip_v[row]):
            ax.axvline(level, color=NORD_DARK, linestyle=":", linewidth=0.8)
        ax.set_title(
            f"{label}\nhysteresis {trip.hysteresis_v[row] * 1e3:.0f} mV, "
            f"delay {delay.rise_delay_s[0] * 1e12:.0f}/{delay.fall_delay_s[0] * 1e12:.0f} ps"
        )
        style_grid(ax)
    for ax in axes.flat[len(trips) :]:
        ax.set_visible(False)
    fig.supxlabel("Input (V)")
    fig.supylabel("Output (V)")
    fig.suptitle("Schmitt trigger transfer on a slow triangle")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_schmitt_supply(
    trips: Sequence[AnalysisSchmittTrip],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the triggers' rising and falling trip points over the supply, mid-supply dotted."""

    if not trips or len(trips) != len(labels):
        raise ValueError("supply comparison requires one trip result and label per trigger")
    columns = min(2, len(trips))
    rows = (len(trips) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (trip, label) in enumerate(zip(trips, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(trip.vdd_v, trip.rise_trip_v, "o-", color=NORD_RED, markersize=3, label="Input rising")
        ax.plot(trip.vdd_v, trip.fall_trip_v, "s-", color=NORD_BLUE, markersize=3, label="Input falling")
        ax.plot(trip.vdd_v, trip.vdd_v / 2, ":", color=NORD_DARK, label="Mid-supply")
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(trips) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper left", fontsize="small")
    fig.supxlabel("Supply (V)")
    fig.supylabel("Trip point (V)")
    fig.suptitle("Schmitt trigger trip points versus supply")
    return save_figure(fig, output_path)
