"""Ring amplifier architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_RED, PLOT_STYLE, SPECTRUM_COLOR_MAP, save_figure, style_grid
from flow.ringamp.analysis import AnalysisRingampSettling, AnalysisRingampTransfer, MeasRingamp


@mpl.rc_context(PLOT_STYLE)
def plot_ringamp_transfer(
    transfers: Sequence[AnalysisRingampTransfer],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' open-loop transfer (solid) and supply current (dashed) at each dead-zone bias."""

    if not transfers or len(transfers) != len(labels):
        raise ValueError("transfer comparison requires one transfer result and label per amplifier")
    columns = min(2, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    current_limit_ua = 1.1 * max(np.nanmax(item.current_a, initial=0.0) * 1e6 for item in transfers)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (transfer, label) in enumerate(zip(transfers, labels, strict=True)):
        ax = axes.flat[index]
        current_ax = ax.twinx()
        for row, dead_zone_v in enumerate(transfer.dead_zone_v):
            color = SPECTRUM_COLOR_MAP(row / max(len(transfer.dead_zone_v) - 1, 1))
            ax.plot(transfer.input_v, transfer.output_v[row], "-", color=color, label=f"{dead_zone_v:g} V")
            current_ax.plot(transfer.input_v, transfer.current_a[row] * 1e6, "--", color=color)
        current_ax.set_ylim(0.0, current_limit_ua)
        if index % columns == columns - 1 or index == len(transfers) - 1:
            current_ax.set_ylabel("Supply current, dashed (µA)")
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    axes.flat[0].legend(title="Dead-zone drive", loc="center left", fontsize="small")
    fig.supxlabel("Input (V), rising ramp")
    fig.supylabel("Output (V)")
    fig.suptitle("Ring amplifier open-loop transfer and current")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ringamp_deadzone(
    settlings: Sequence[AnalysisRingampSettling],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers over the dead-zone bias: settling time and static error, and the quiescent current."""

    if not settlings or len(settlings) != len(labels):
        raise ValueError("dead-zone comparison requires one settling result and label per amplifier")
    columns = min(2, len(settlings))
    rows = (len(settlings) + columns - 1) // columns
    current_limit_ua = 1.1 * max(np.nanmax(item.quiescent_current_a, initial=0.0) * 1e6 for item in settlings)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (settling, label) in enumerate(zip(settlings, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogy(settling.dead_zone_v, np.abs(settling.gain_error) * 100, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        current_ax = ax.twinx()
        current_ax.plot(settling.dead_zone_v, settling.quiescent_current_a * 1e6, "s--", color=NORD_RED, markersize=3)
        current_ax.set_ylim(0.0, current_limit_ua)
        current_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(settlings) - 1:
            current_ax.set_ylabel("Quiescent current after settling (µA)", color=NORD_RED)
        # a settling time means something where the output reached the step: within half of it, stable
        settled = [
            f"{drive:g} V: {time * 1e9:.2g} ns"
            for drive, time, overshoot, error in zip(
                settling.dead_zone_v, settling.settling_time_s, settling.overshoot, settling.gain_error, strict=True
            )
            if np.isfinite(time) and overshoot < 1.0 and abs(error) < 0.5
        ]
        ax.set_title(f"{label}\nsettles to 1 % at " + ", ".join(settled) if settled else label, fontsize="small")
        style_grid(ax)
    for ax in axes.flat[len(settlings) :]:
        ax.set_visible(False)
    fig.supxlabel("Dead-zone drive (biasn above vss, biasp below vdd) (V)")
    fig.supylabel("Closed-loop step error |gain error| (%)", color=NORD_BLUE)
    fig.suptitle(f"Ring amplifier dead zone: accuracy against current, {settlings[0].step_v[0] * 1e3:g} mV step")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ringamp_step(
    settlings: Sequence[AnalysisRingampSettling],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers over the closed-loop step: static error and settling time."""

    if not settlings or len(settlings) != len(labels):
        raise ValueError("step comparison requires one settling result and label per amplifier")
    columns = min(2, len(settlings))
    rows = (len(settlings) + columns - 1) // columns
    settling_limit_ns = 1.1 * max(np.nanmax(item.settling_time_s, initial=0.0) * 1e9 for item in settlings)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (settling, label) in enumerate(zip(settlings, labels, strict=True)):
        ax = axes.flat[index]
        residual_mv = (settling.output_step_v + settling.step_v) * 1e3
        ax.plot(settling.step_v * 1e3, residual_mv, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        time_ax = ax.twinx()
        time_ax.plot(settling.step_v * 1e3, settling.settling_time_s * 1e9, "s--", color=NORD_RED, markersize=3)
        time_ax.set_ylim(0.0, settling_limit_ns)
        time_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(settlings) - 1:
            time_ax.set_ylabel("Settling to 1 % (ns)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(settlings) :]:
        ax.set_visible(False)
    fig.supxlabel("Input step (mV), ideal output its negative")
    fig.supylabel("Output error, settled (mV)", color=NORD_BLUE)
    fig.suptitle(f"Ring amplifier closed-loop step at {settlings[0].dead_zone_v[0]:g} V dead-zone drive")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ringamp_waveforms(
    measurements: Sequence[Sequence[MeasRingamp]],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' closed-loop output after each step, one panel per amplifier."""

    if not measurements or len(measurements) != len(labels):
        raise ValueError("waveform comparison requires one step sweep and label per amplifier")
    columns = min(2, len(measurements))
    rows = (len(measurements) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (sweep, label) in enumerate(zip(measurements, labels, strict=True)):
        ax = axes.flat[index]
        for row, measurement in enumerate(sweep):
            wave = measurement.wave
            if wave is None:
                raise ValueError("waveform comparison requires waveform records")
            step_s = float(measurement.param.step_delay_s)
            shown = wave.time_s >= step_s - 0.5e-9
            color = SPECTRUM_COLOR_MAP(row / max(len(sweep) - 1, 1))
            output = wave.v["out"][0][shown]
            ax.plot(
                (wave.time_s[shown] - step_s) * 1e9,
                (output - output[0]) * 1e3,
                color=color,
                label=f"{float(measurement.param.step_v) * 1e3:g} mV",
            )
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(measurements) :]:
        ax.set_visible(False)
    axes.flat[0].legend(title="Step", loc="upper right", fontsize="small")
    fig.supxlabel("Time after the step (ns)")
    fig.supylabel("Output change (mV)")
    fig.suptitle("Ring amplifier closed-loop step responses")
    return save_figure(fig, output_path)
