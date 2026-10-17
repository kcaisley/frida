"""Phase interpolator architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_GREEN, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.pi.analysis import AnalysisPiLinearity, AnalysisPiPhase, MeasPi


@mpl.rc_context(PLOT_STYLE)
def plot_pi_transfer(
    phases: Sequence[AnalysisPiPhase],
    linearities: Sequence[AnalysisPiLinearity],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the interpolators' output phase over the input spacing against their weights, and the INL."""

    if not phases or not len(phases) == len(linearities) == len(labels):
        raise ValueError("transfer comparison requires one phase result, linearity, and label per interpolator")
    columns = min(2, len(phases))
    rows = (len(phases) + columns - 1) // columns
    inl_limit = 1.1 * max(np.nanmax(np.abs(item.inl_deg)) for item in linearities)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (phase, linearity, label) in enumerate(zip(phases, linearities, labels, strict=True)):
        ax = axes.flat[index]
        intercept_deg = 360 * linearity.intrinsic_delay_s / linearity.period_s
        ax.plot(phase.spacing_deg, phase.output_phase_deg, "o-", color=NORD_BLUE, markersize=3, label="Output")
        ax.plot(
            phase.spacing_deg,
            intercept_deg + linearity.ideal_slope * phase.spacing_deg,
            ":",
            color=NORD_DARK,
            label=f"Weights ({linearity.ideal_slope:g} of the spacing)",
        )
        ax.axvspan(0.0, 90.0, color=NORD_DARK, alpha=0.06)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        inl_ax = ax.twinx()
        inl_ax.plot(phase.spacing_deg, linearity.inl_deg, "s--", color=NORD_RED, markersize=3)
        inl_ax.set_ylim(-inl_limit, inl_limit)
        inl_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(phases) - 1:
            inl_ax.set_ylabel("Deviation from the fit (°)", color=NORD_RED)
        ax.set_title(
            f"{label}\nslope {linearity.slope:.2f} (ideal {linearity.ideal_slope:g}), INL {linearity.max_inl_deg:.1f}° to 90°"
        )
        style_grid(ax)
    for ax in axes.flat[len(phases) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper left", fontsize="small")
    fig.supxlabel("Phase B behind phase A (°), the fitted range shaded")
    fig.supylabel("Output phase behind phase A (°)", color=NORD_BLUE)
    fig.suptitle(f"Interpolator transfer at a {phases[0].period_s[0] * 1e12:g} ps period")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_pi_frequency(
    phases: Sequence[AnalysisPiPhase],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the interpolators over the clock frequency at one spacing: output phase and swing."""

    if not phases or len(phases) != len(labels):
        raise ValueError("frequency comparison requires one phase result and label per interpolator")
    columns = min(2, len(phases))
    rows = (len(phases) + columns - 1) // columns
    swing_limit_mv = 1.1 * max(np.nanmax(item.swing_v) * 1e3 for item in phases)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (phase, label) in enumerate(zip(phases, labels, strict=True)):
        ax = axes.flat[index]
        frequency_ghz = 1e-9 / phase.period_s
        ax.semilogx(frequency_ghz, phase.output_phase_deg, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        swing_ax = ax.twinx()
        swing_ax.semilogx(frequency_ghz, phase.swing_v * 1e3, "s--", color=NORD_RED, markersize=3)
        swing_ax.set_ylim(0.0, swing_limit_mv)
        swing_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(phases) - 1:
            swing_ax.set_ylabel("Swing, half differential (mV)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(phases) :]:
        ax.set_visible(False)
    fig.supxlabel("Clock frequency (GHz)")
    fig.supylabel("Output phase behind phase A (°)", color=NORD_BLUE)
    fig.suptitle(f"Interpolator phase and swing versus frequency at {phases[0].spacing_deg[0]:g}° spacing")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_pi_waveforms(
    measurements: Sequence[MeasPi],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the interpolators' differential phases and output over their last two periods."""

    if not measurements or len(measurements) != len(labels):
        raise ValueError("waveform comparison requires one measurement and label per interpolator")
    columns = min(2, len(measurements))
    rows = (len(measurements) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (measurement, label) in enumerate(zip(measurements, labels, strict=True)):
        ax = axes.flat[index]
        wave = measurement.wave
        if wave is None:
            raise ValueError("waveform comparison requires waveform records")
        shown = wave.time_s >= wave.time_s[-1] - 2 * float(measurement.param.period_s)
        time_ps = (wave.time_s[shown] - wave.time_s[shown][0]) * 1e12
        for name, color, style in (("a", NORD_GREEN, ":"), ("b", NORD_DARK, "--"), ("out", NORD_BLUE, "-")):
            difference = wave.v[f"{name}p"][0][shown] - wave.v[f"{name}n"][0][shown]
            ax.plot(time_ps, difference * 1e3, style, color=color, label=name)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(measurements) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="lower right")
    fig.supxlabel("Time (ps)")
    fig.supylabel("Differential voltage (mV)")
    fig.suptitle(
        f"Interpolator waveforms at {float(measurements[0].param.spacing_deg):g}° spacing, "
        f"{float(measurements[0].param.period_s) * 1e12:g} ps period"
    )
    return save_figure(fig, output_path)
