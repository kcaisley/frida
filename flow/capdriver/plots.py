"""Capacitor driver drive-band comparisons: one panel per band, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.capdriver.analysis import AnalysisCapdriverDrive


@mpl.rc_context(PLOT_STYLE)
def plot_capdriver_load(
    drives: Sequence[AnalysisCapdriverDrive],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the bands over the load: the state path's delays and the output's transitions, the
    fitted drive resistance in each title."""

    if not drives or len(drives) != len(labels):
        raise ValueError("load comparison requires one drive result and label per band")
    columns = min(3, len(drives))
    rows = (len(drives) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (drive, label) in enumerate(zip(drives, labels, strict=True)):
        ax = axes.flat[index]
        load_ff = drive.load_f * 1e15
        ax.loglog(load_ff, drive.state_rise_delay_s * 1e12, "o-", color=NORD_BLUE, markersize=3, label="Delay, rising")
        ax.loglog(
            load_ff, drive.state_fall_delay_s * 1e12, "o--", color=NORD_BLUE, markersize=3, label="Delay, falling"
        )
        ax.loglog(load_ff, drive.rise_time_s * 1e12, "s-", color=NORD_RED, markersize=3, label="10–90 %, rising")
        ax.loglog(load_ff, drive.fall_time_s * 1e12, "s--", color=NORD_RED, markersize=3, label="10–90 %, falling")
        rise_ohm, fall_ohm = drive.drive_resistance_ohm()
        ax.set_title(f"{label}\nR {rise_ohm * 1e-3:.2g} / {fall_ohm * 1e-3:.2g} kΩ")
        style_grid(ax)
    axes.flat[0].legend(loc="upper left", fontsize="small")
    for ax in axes.flat[len(drives) :]:
        ax.set_visible(False)
    fig.supxlabel("Load (fF)")
    fig.supylabel("Time (ps)")
    fig.suptitle(f"Driver delay and transitions versus load at {drives[0].vdd_v[0]:g} V")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_capdriver_supply(
    drives: Sequence[AnalysisCapdriverDrive],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the bands over the supply: the state path's rising delay and 1 % settling, the energy
    per cycle over C V² on the right."""

    if not drives or len(drives) != len(labels):
        raise ValueError("supply comparison requires one drive result and label per band")
    columns = min(3, len(drives))
    rows = (len(drives) + columns - 1) // columns
    energy_limit = 1.1 * max(np.nanmax(item.energy_per_cv2, initial=0.0) for item in drives)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (drive, label) in enumerate(zip(drives, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(drive.vdd_v, drive.state_rise_delay_s * 1e12, "o-", color=NORD_BLUE, markersize=3, label="Delay")
        ax.plot(
            drive.vdd_v, drive.rise_settling_s * 1e12, "o--", color=NORD_BLUE, markersize=3, label="Settling to 1 %"
        )
        ax.tick_params(axis="y", colors=NORD_BLUE)
        energy_ax = ax.twinx()
        energy_ax.plot(drive.vdd_v, drive.energy_per_cv2, "s-", color=NORD_RED, markersize=3)
        energy_ax.set_ylim(0.0, energy_limit)
        energy_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(drives) - 1:
            energy_ax.set_ylabel("Energy per cycle / C V²", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    axes.flat[0].set_ylim(bottom=0.0)
    axes.flat[0].legend(loc="upper right", fontsize="small")
    for ax in axes.flat[len(drives) :]:
        ax.set_visible(False)
    fig.supxlabel("Supply (V)")
    fig.supylabel("Rising state path (ps)", color=NORD_BLUE)
    fig.suptitle(f"Driver timing and energy versus supply into {drives[0].load_f[0] * 1e15:g} fF")
    return save_figure(fig, output_path)
