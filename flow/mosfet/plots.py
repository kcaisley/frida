"""MOSFET characterization comparisons: one panel per device, one curve per length."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import CURVE_COLORS, NORD_BLUE, NORD_RED, PLOT_STYLE, save_figure, style_grid
from flow.mosfet.analysis import (
    AnalysisMosfetMismatch,
    AnalysisMosfetNoise,
    AnalysisMosfetOutput,
    AnalysisMosfetTrannoise,
    AnalysisMosfetTransfer,
)


@mpl.rc_context(PLOT_STYLE)
def plot_mosfet_transfer(
    transfers: Sequence[Sequence[AnalysisMosfetTransfer]],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Each device's Id-Vgs on a log scale, saturated (solid) and linear (dashed), one curve per length."""

    if not transfers or len(transfers) != len(labels):
        raise ValueError("transfer comparison requires one list of lengths and one label per device")
    columns = min(3, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (lengths, label) in enumerate(zip(transfers, labels, strict=True)):
        ax = axes.flat[index]
        for color, transfer in zip(CURVE_COLORS, lengths, strict=False):
            name = f"L {transfer.l_m * 1e9:.0f} nm"
            ax.semilogy(transfer.vgs_v, np.maximum(transfer.id_sat_a, 1e-15), "-", color=color, label=name)
            ax.semilogy(transfer.vgs_v, np.maximum(transfer.id_lin_a, 1e-15), "--", color=color, linewidth=0.8)
        ax.set_title(label)
        style_grid(ax)
    axes.flat[0].legend(fontsize=8)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    fig.supxlabel("|Vgs| (V)")
    fig.supylabel("|Id| (A): saturated solid, linear dashed")
    fig.suptitle("MOSFET transfer characteristic")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_mosfet_gm_id(
    transfers: Sequence[Sequence[AnalysisMosfetTransfer]],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Each device's gm/Id over its current density Id/W in saturation, one curve per length."""

    if not transfers or len(transfers) != len(labels):
        raise ValueError("gm/Id comparison requires one list of lengths and one label per device")
    columns = min(3, len(transfers))
    rows = (len(transfers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (lengths, label) in enumerate(zip(transfers, labels, strict=True)):
        ax = axes.flat[index]
        for color, transfer in zip(CURVE_COLORS, lengths, strict=False):
            shown = transfer.current_density_a_m > 1e-6
            ax.semilogx(
                transfer.current_density_a_m[shown],
                transfer.gm_over_id[shown],
                "-",
                color=color,
                label=f"L {transfer.l_m * 1e9:.0f} nm",
            )
        ax.set_title(label)
        style_grid(ax)
    axes.flat[0].set_ylim(bottom=0.0)
    axes.flat[0].legend(fontsize=8)
    for ax in axes.flat[len(transfers) :]:
        ax.set_visible(False)
    fig.supxlabel("Id/W (A/m)")
    fig.supylabel("gm/Id (1/V)")
    fig.suptitle("MOSFET gm/Id versus current density, saturated")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_mosfet_output(
    outputs: Sequence[AnalysisMosfetOutput],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Each device's Id-Vds family at one length, a curve per gate voltage."""

    if not outputs or len(outputs) != len(labels):
        raise ValueError("output comparison requires one result and label per device")
    columns = min(3, len(outputs))
    rows = (len(outputs) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, squeeze=False)
    for index, (output, label) in enumerate(zip(outputs, labels, strict=True)):
        ax = axes.flat[index]
        for color, vgs, curve in zip(CURVE_COLORS, output.family_vgs_v, output.id_family_a.T, strict=False):
            ax.plot(output.vds_v, curve * 1e6, "-", color=color, label=f"|Vgs| {vgs:.2f} V")
        ax.axvline(output.bias_vds_v, color=NORD_RED, linewidth=0.6, linestyle=":")
        ax.set_title(label)
        ax.set_ylim(bottom=0.0)
        style_grid(ax)
    axes.flat[0].legend(fontsize=8)
    for ax in axes.flat[len(outputs) :]:
        ax.set_visible(False)
    fig.supxlabel("|Vds| (V)")
    fig.supylabel("|Id| (uA)")
    fig.suptitle("MOSFET output characteristic (dotted: the bias's |Vds|)")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_mosfet_noise(
    noises: Sequence[Sequence[AnalysisMosfetNoise]],
    *,
    lengths_m: Sequence[Sequence[float]],
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Each device's gate-referred noise density at the bias, one curve per length."""

    if not noises or not len(noises) == len(lengths_m) == len(labels):
        raise ValueError("noise comparison requires one list of lengths, their sizes and one label per device")
    columns = min(3, len(noises))
    rows = (len(noises) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (lengths, sizes, label) in enumerate(zip(noises, lengths_m, labels, strict=True)):
        ax = axes.flat[index]
        for color, noise, length in zip(CURVE_COLORS, lengths, sizes, strict=False):
            ax.loglog(noise.frequency_hz, noise.gate_noise_v_rthz, "-", color=color, label=f"L {length * 1e9:.0f} nm")
        ax.set_title(label)
        style_grid(ax)
    axes.flat[0].legend(fontsize=8)
    for ax in axes.flat[len(noises) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Gate-referred noise (V/√Hz)")
    fig.suptitle("MOSFET noise at the bias")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_mosfet_trannoise(
    trannoises: Sequence[AnalysisMosfetTrannoise],
    *,
    noises: Sequence[AnalysisMosfetNoise],
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Each device's drain-current noise density from its transient-noise record against the small-signal analysis's."""

    if not trannoises or not len(trannoises) == len(noises) == len(labels):
        raise ValueError("transient noise comparison requires one result, its noise analysis and a label per device")
    columns = min(3, len(trannoises))
    rows = (len(trannoises) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, squeeze=False)
    for index, (trannoise, noise, label) in enumerate(zip(trannoises, noises, labels, strict=True)):
        ax = axes.flat[index]
        ax.loglog(trannoise.frequency_hz, trannoise.drain_noise_a_rthz, "-", color=NORD_BLUE, label="transient")
        ax.loglog(noise.frequency_hz, noise.drain_noise_a_rthz, "--", color=NORD_RED, label="small signal")
        ax.set_xlim(trannoise.frequency_hz[0], trannoise.frequency_hz[-1])
        ax.set_title(label)
        style_grid(ax)
    axes.flat[0].legend(fontsize=8)
    for ax in axes.flat[len(trannoises) :]:
        ax.set_visible(False)
    fig.supxlabel("Frequency (Hz)")
    fig.supylabel("Drain current noise (A/√Hz)")
    fig.suptitle("MOSFET transient noise against small-signal noise")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_mosfet_mismatch(
    mismatches: Sequence[Sequence[AnalysisMosfetMismatch]],
    *,
    transfers: Sequence[Sequence[AnalysisMosfetTransfer]],
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """The Pelgrom plot: each device's gate-referred mismatch over 1/sqrt(W L), its lengths a series."""

    if not mismatches or not len(mismatches) == len(transfers) == len(labels):
        raise ValueError("mismatch comparison requires one list of lengths, their transfers and a label per device")
    fig, ax = plt.subplots()
    for color, lengths, sizes, label in zip(CURVE_COLORS, mismatches, transfers, labels, strict=False):
        area = np.array([transfer.w_m * transfer.l_m for transfer in sizes]) * 1e12
        sigma = np.array([mismatch.sigma_vgs_v for mismatch in lengths]) * 1e3
        avt = np.median([mismatch.avt_v_m for mismatch in lengths]) * 1e9
        ax.plot(1 / np.sqrt(area), sigma, "o-", color=color, markersize=4, label=f"{label}: {avt:.2f} mV um")
    ax.set_xlim(left=0.0)
    ax.set_ylim(bottom=0.0)
    ax.set_xlabel("1/sqrt(W L) (1/um)")
    ax.set_ylabel("sigma(Vgs) (mV)")
    ax.legend(fontsize=8, title="device: median A_VT")
    style_grid(ax)
    fig.suptitle("MOSFET mismatch at the bias (Monte Carlo)")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_mosfet_simulators(
    spectre: Sequence[AnalysisMosfetTransfer],
    *,
    ngspice: Sequence[AnalysisMosfetTransfer],
    noise_spectre: Sequence[AnalysisMosfetNoise],
    noise_ngspice: Sequence[AnalysisMosfetNoise],
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Spectre against ngspice for each device at one length: Id-Vgs and gate-referred noise."""

    if not spectre or not len(spectre) == len(ngspice) == len(noise_spectre) == len(noise_ngspice) == len(labels):
        raise ValueError("simulator comparison requires both simulators' results and a label per device")
    fig, axes = plt.subplots(2, len(spectre), squeeze=False, sharey="row")
    for index, label in enumerate(labels):
        transfer_ax, noise_ax = axes[0, index], axes[1, index]
        for result, noise, style, name in (
            (spectre[index], noise_spectre[index], "-", "Spectre"),
            (ngspice[index], noise_ngspice[index], "--", "ngspice"),
        ):
            color = NORD_BLUE if name == "Spectre" else NORD_RED
            transfer_ax.semilogy(result.vgs_v, np.maximum(result.id_sat_a, 1e-15), style, color=color, label=name)
            noise_ax.loglog(noise.frequency_hz, noise.gate_noise_v_rthz, style, color=color)
        transfer_ax.set_title(label)
        transfer_ax.set_xlabel("|Vgs| (V)")
        noise_ax.set_xlabel("Frequency (Hz)")
        style_grid(transfer_ax)
        style_grid(noise_ax)
    axes[0, 0].set_ylabel("|Id| saturated (A)")
    axes[1, 0].set_ylabel("Gate-referred noise (V/√Hz)")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("MOSFET in Spectre and ngspice")
    return save_figure(fig, output_path)
