"""OTA architecture comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import NORD_BLUE, NORD_DARK, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.ota.analysis import AnalysisOtaAc, AnalysisOtaDistortion, AnalysisOtaNoise, AnalysisOtaSlew, MeasOtaTran


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
        margin = f", GM {response.gain_margin_db[0]:.0f} dB" if np.isfinite(response.gain_margin_db[0]) else ""
        ax.set_title(
            f"{label}\n{response.dc_gain_db[0]:.1f} dB, {response.ugbw_hz[0] * 1e-9:.2g} GHz, "
            f"PM {response.phase_margin_deg[0]:.0f}°{margin}"
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
    ugbw_limit_ghz = 1.1 * max(np.nanmax(item.ugbw_hz, initial=0.0) * 1e-9 for item in responses)
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
    power_limit_uw = 1.1 * max(np.nanmax(item.power_w, initial=0.0) * 1e6 for item in responses)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (response, label) in enumerate(zip(responses, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(response.vdd_v, response.ugbw_hz * 1e-9, "o-", color=NORD_BLUE)
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
    # the shared limit, once every panel has drawn: one panel's would cut the others' data
    axes.flat[0].set_ylim(bottom=0.0)
    for ax in axes.flat[len(responses) :]:
        ax.set_visible(False)
    fig.supxlabel("Supply (V)")
    fig.supylabel("Unity-gain bandwidth (GHz)", color=NORD_BLUE)
    fig.suptitle("Bandwidth and power versus supply, common modes at mid-supply")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ota_rejection(
    responses: Sequence[AnalysisOtaAc],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' supply and common-mode rejection at outp over frequency, at one point each (their first)."""

    if not responses or len(responses) != len(labels):
        raise ValueError("rejection comparison requires one AC result and label per amplifier")
    columns = min(3, len(responses))
    rows = (len(responses) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (response, label) in enumerate(zip(responses, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogx(response.frequency_hz, response.psrr_db[0], "-", color=NORD_BLUE, label="PSRR")
        ax.semilogx(response.frequency_hz, response.cmrr_db[0], "--", color=NORD_RED, label="CMRR")
        ax.axhline(0.0, color=NORD_DARK, linewidth=0.8)
        ax.set_title(f"{label}\nPSRR {response.low_psrr_db[0]:.0f} dB, CMRR {response.low_cmrr_db[0]:.0f} dB")
        style_grid(ax)
    axes.flat[0].legend(loc="lower left")
    for ax in axes.flat[len(responses) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Rejection at outp (dB)")
    fig.suptitle(
        f"Supply and common-mode rejection at {responses[0].vdd_v[0]:g} V, input common mode {responses[0].vcm_v[0]:g} V"
    )
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ota_noise(
    noises: Sequence[AnalysisOtaNoise],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' input-referred noise over the input common mode: the spot density, and its RMS to the unity-gain bandwidth."""

    if not noises or len(noises) != len(labels):
        raise ValueError("noise comparison requires one noise result and label per amplifier")
    columns = min(3, len(noises))
    rows = (len(noises) + columns - 1) // columns
    integrated_limit_uv = 1.1 * max(np.nanmax(item.integrated_noise_v, initial=0.0) * 1e6 for item in noises)
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (noise, label) in enumerate(zip(noises, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogy(noise.vcm_v, noise.spot_noise_v_rthz * 1e9, "o-", color=NORD_BLUE)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        integrated_ax = ax.twinx()
        integrated_ax.plot(noise.vcm_v, noise.integrated_noise_v * 1e6, "s-", color=NORD_RED)
        integrated_ax.set_ylim(0.0, integrated_limit_uv)
        integrated_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(noises) - 1:
            integrated_ax.set_ylabel("RMS to the unity-gain bandwidth (µV)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(noises) :]:
        ax.set_visible(False)
    fig.supxlabel("Input common mode (V)")
    fig.supylabel(f"Input noise at {noises[0].spot_frequency_hz * 1e-6:.3g} MHz (nV/√Hz)", color=NORD_BLUE)
    fig.suptitle(f"Input-referred noise versus input common mode at {noises[0].vdd_v[0]:g} V")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ota_slew(
    measurements: Sequence[MeasOtaTran],
    slews: Sequence[AnalysisOtaSlew],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the OTAs' unity-gain step responses: input and output, slew rates in each title."""

    if not measurements or not len(measurements) == len(slews) == len(labels):
        raise ValueError("slew comparison requires one step record, slew result, and label per OTA")
    columns = min(2, len(measurements))
    rows = (len(measurements) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, squeeze=False)
    for index, (measurement, slew, label) in enumerate(zip(measurements, slews, labels, strict=True)):
        ax = axes.flat[index]
        wave = measurement.wave
        if wave is None:
            raise ValueError("slew comparison requires waveform records")
        ax.plot(wave.time_s * 1e9, wave.v["inp"][0], ":", color=NORD_DARK, label="Input")
        ax.plot(wave.time_s * 1e9, wave.v["outp"][0], "-", color=NORD_BLUE, label="Output")
        ax.set_title(
            f"{label}\nslew +{slew.rise_slew_v_per_s[0] * 1e-9:.2g} / {slew.fall_slew_v_per_s[0] * 1e-9:.2g} V/ns"
        )
        style_grid(ax)
    for ax in axes.flat[len(measurements) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper right", fontsize="small")
    fig.supxlabel("Time (ns)")
    fig.supylabel("Voltage (V)")
    fig.suptitle("OTA unity-gain step response at mid-supply")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_ota_distortion(
    distortions: Sequence[AnalysisOtaDistortion],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the OTAs' unity-gain output spectra on a sine, THD and SNDR in each title."""

    if not distortions or len(distortions) != len(labels):
        raise ValueError("distortion comparison requires one distortion result and label per OTA")
    columns = min(2, len(distortions))
    rows = (len(distortions) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (distortion, label) in enumerate(zip(distortions, labels, strict=True)):
        ax = axes.flat[index]
        ax.semilogx(distortion.frequency_hz[1:], distortion.spectrum_dbfs[0][1:], "-", color=NORD_BLUE)
        ax.set_ylim(-140.0, 10.0)
        ax.set_title(f"{label}\nTHD {distortion.thd_db[0]:.1f} dB, SNDR {distortion.sndr_db[0]:.1f} dB")
        style_grid(ax)
    for ax in axes.flat[len(distortions) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Output relative to the input amplitude (dB)")
    fig.suptitle(f"OTA unity-gain output spectrum, {distortions[0].sine_hz[0] * 1e-6:g} MHz sine")
    return save_figure(fig, output_path)
