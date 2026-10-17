"""OTA architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.ota.analysis import AnalysisOtaAc


@mpl.rc_context(PLOT_STYLE)
def plot_ota_bode(
    responses: Sequence[AnalysisOtaAc],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' open-loop gain and phase at one point each (their first)."""

    if not responses or len(responses) != len(labels):
        raise ValueError("Bode comparison requires one AC result and label per amplifier")
    columns = min(3, len(responses))
    rows = (len(responses) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (response, label) in enumerate(zip(responses, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogx(response.frequency_hz, response.gain_db[0], "-", color=NORD_BLUE)
        ax.axhline(0.0, color=NORD_DARK, linewidth=0.8)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        phase_ax = ax.twinx()
        phase_ax.semilogx(response.frequency_hz, response.phase_deg[0] - response.phase_deg[0][0], "--", color=NORD_RED)
        phase_ax.set_ylim(-360.0, 30.0)
        phase_ax.set_yticks(np.arange(-360, 1, 90))
        phase_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(responses) - 1:
            phase_ax.set_ylabel("Phase (°)", color=NORD_RED)
        ax.set_title(
            f"{label}\n{response.dc_gain_db[0]:.1f} dB, {response.ugbw_hz[0] * 1e-9:.2g} GHz, "
            f"PM {response.phase_margin_deg[0]:.0f}°"
        )
        style_grid(ax)
    for ax in axes.flat[len(responses) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Differential gain (dB)", color=NORD_BLUE)
    fig.suptitle(f"Open-loop response at {responses[0].vdd_v[0]:g} V, input common mode {responses[0].vcm_v[0]:g} V")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ota_common_mode(
    responses: Sequence[AnalysisOtaAc],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the input common-mode ranges: DC gain and unity-gain bandwidth versus input common mode."""

    if not responses or len(responses) != len(labels):
        raise ValueError("common-mode comparison requires one AC result and label per amplifier")
    columns = min(3, len(responses))
    rows = (len(responses) + columns - 1) // columns
    ugbw_limit_ghz = 1.1 * max(np.nanmax(item.ugbw_hz) * 1e-9 for item in responses)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (response, label) in enumerate(zip(responses, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(response.vcm_v, response.dc_gain_db, "o-", color=NORD_BLUE)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        ugbw_ax = ax.twinx()
        ugbw_ax.plot(response.vcm_v, response.ugbw_hz * 1e-9, "s-", color=NORD_RED)
        ugbw_ax.set_ylim(0.0, ugbw_limit_ghz)
        ugbw_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(responses) - 1:
            ugbw_ax.set_ylabel("Unity-gain bandwidth (GHz)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(responses) :]:
        ax.set_visible(False)
    fig.supxlabel("Input common mode (V)")
    fig.supylabel("DC gain (dB)", color=NORD_BLUE)
    fig.suptitle(f"Gain and bandwidth versus input common mode at {responses[0].vdd_v[0]:g} V")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ota_supply(
    responses: Sequence[AnalysisOtaAc],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers over the supply: unity-gain bandwidth and power, phase margin in the title."""

    if not responses or len(responses) != len(labels):
        raise ValueError("supply comparison requires one AC result and label per amplifier")
    columns = min(3, len(responses))
    rows = (len(responses) + columns - 1) // columns
    power_limit_uw = 1.1 * max(np.nanmax(item.power_w) * 1e6 for item in responses)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (response, label) in enumerate(zip(responses, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(response.vdd_v, response.ugbw_hz * 1e-9, "o-", color=NORD_BLUE)
        ax.set_ylim(bottom=0.0)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        power_ax = ax.twinx()
        power_ax.plot(response.vdd_v, response.power_w * 1e6, "s-", color=NORD_RED)
        power_ax.set_ylim(0.0, power_limit_uw)
        power_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(responses) - 1:
            power_ax.set_ylabel("Power (µW)", color=NORD_RED)
        margins = response.phase_margin_deg[np.isfinite(response.phase_margin_deg)]
        ax.set_title(f"{label}\nPM {np.min(margins):.0f}–{np.max(margins):.0f}°" if len(margins) else label)
        style_grid(ax)
    for ax in axes.flat[len(responses) :]:
        ax.set_visible(False)
    fig.supxlabel("Supply (V)")
    fig.supylabel("Unity-gain bandwidth (GHz)", color=NORD_BLUE)
    fig.suptitle("Bandwidth and power versus supply, common modes at mid-supply")
    return save_figure(fig, output_path)
