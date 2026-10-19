"""Charge-sensitive amplifier comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import (
    NORD_BLUE,
    NORD_CYAN,
    NORD_DARK,
    NORD_GREEN,
    NORD_ORANGE,
    NORD_RED,
    PLOT_STYLE,
    save_figure,
    style_grid,
)
from flow.csa.analysis import AnalysisCsaNoise, AnalysisCsaPulse

CHARGE_COLORS = (NORD_CYAN, NORD_BLUE, NORD_GREEN, NORD_ORANGE, NORD_RED)


@mpl.rc_context(PLOT_STYLE)
def plot_csa_pulse(
    pulses: Sequence[AnalysisCsaPulse],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' responses to each injected charge: the output's excursion from its
    baseline from the injection on, the time-over-threshold level dotted; the smallest charge's
    gain and 10–90 % rise time in each title."""

    if not pulses or len(pulses) != len(labels):
        raise ValueError("pulse comparison requires one pulse result and label per amplifier")
    columns = min(2, len(pulses))
    rows = (len(pulses) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (pulse, label) in enumerate(zip(pulses, labels, strict=True)):
        ax = axes.flat[index]
        for row, charge in enumerate(pulse.charge_c):
            color = CHARGE_COLORS[row % len(CHARGE_COLORS)]
            ax.plot(pulse.time_s * 1e9, pulse.pulse_v[row] * 1e3, "-", color=color, label=f"{charge * 1e15:g} fC")
        ax.axhline(pulse.threshold_v[0] * 1e3, color=NORD_DARK, linestyle=":", linewidth=0.8)
        ax.set_title(f"{label}\n{pulse.gain_v_per_c[0] * 1e-12:.0f} mV/fC, rise {pulse.rise_time_s[0] * 1e9:.2g} ns")
        style_grid(ax)
    for ax in axes.flat[len(pulses) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper right", fontsize="small")
    fig.supxlabel("Time from injection (ns)")
    fig.supylabel("Output excursion from baseline (mV)")
    fig.suptitle("Amplifier response to an injected charge")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_csa_charge(
    pulses: Sequence[AnalysisCsaPulse],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' amplitude and time over threshold over the injected charge (none for
    an amplifier that holds it)."""

    if not pulses or len(pulses) != len(labels):
        raise ValueError("charge comparison requires one pulse result and label per amplifier")
    columns = min(2, len(pulses))
    rows = (len(pulses) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (pulse, label) in enumerate(zip(pulses, labels, strict=True)):
        ax = axes.flat[index]
        charge_fc = pulse.charge_c * 1e15
        ax.plot(charge_fc, pulse.amplitude_v * 1e3, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        tot_ax = ax.twinx()
        tot_ax.plot(charge_fc, pulse.tot_s * 1e9, "s-", color=NORD_RED, markersize=3)
        tot_ax.tick_params(axis="y", colors=NORD_RED)
        # an amplifier that holds the charge has no time over threshold
        tot_ax.set_visible(bool(np.any(np.isfinite(pulse.tot_s))))
        if index % columns == columns - 1 or index == len(pulses) - 1:
            tot_ax.set_ylabel("Time over threshold (ns)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(pulses) :]:
        ax.set_visible(False)
    fig.supxlabel("Injected charge (fC)")
    fig.supylabel("Amplitude (mV)", color=NORD_BLUE)
    fig.suptitle("Amplifier amplitude and time over threshold versus charge")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_csa_noise(
    noises: Sequence[AnalysisCsaNoise],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the amplifiers' output noise density, the rms noise and ENC in each title."""

    if not noises or len(noises) != len(labels):
        raise ValueError("noise comparison requires one noise result and label per amplifier")
    columns = min(2, len(noises))
    rows = (len(noises) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (noise, label) in enumerate(zip(noises, labels, strict=True)):
        ax = axes.flat[index]
        ax.loglog(noise.frequency_hz, noise.output_noise_v_rthz[0], "-", color=NORD_BLUE)
        ax.set_title(f"{label}\n{noise.noise_rms_v[0] * 1e3:.2g} mV rms, ENC {noise.enc_electrons[0]:.0f} e⁻")
        style_grid(ax)
    for ax in axes.flat[len(noises) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Output noise (V/√Hz)")
    fig.suptitle("Amplifier output noise without charge")
    return save_figure(fig, output_path)
