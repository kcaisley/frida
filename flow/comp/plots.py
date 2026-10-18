"""Comparator plots: the generated-candidate sweep, and the topology comparisons of the
characterization, one panel per topology with shared axes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

from flow.analysis import calc
from flow.analysis.plots import (
    CURVE_COLORS,
    NORD_BLUE,
    NORD_RED,
    PLOT_STYLE,
    SPECTRUM_COLOR_MAP,
    SPINE_COLOR,
    TEXT_COLOR,
    save_figure,
    style_grid,
    style_info_box,
    style_measurement_group_text,
)
from flow.analysis.types import AnalysisCompCommonMode, MeasComp
from flow.comp.analysis import AnalysisCompCandidate, AnalysisCompDelay, AnalysisCompPower, AnalysisCompTiming


@mpl.rc_context(PLOT_STYLE)
def plot_comp_timing(
    msmt_list: Sequence[MeasComp],
    analysis: AnalysisCompTiming,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot comparator delay, settling time, and unresolved outcomes."""

    fig, axes = plt.subplots(2, 1)
    axes[0].plot(analysis.trial_index, analysis.clock_to_decision_s * 1e9, "o", label="Clock to decision")
    axes[0].plot(analysis.trial_index, analysis.settling_s * 1e9, "o", label="Settling")
    axes[0].set_ylabel("Time (ns)")
    axes[0].legend()
    axes[1].step(analysis.trial_index, analysis.unresolved, where="mid")
    axes[1].set_ylabel("Unresolved")
    axes[1].set_xlabel("Trial index")
    axes[1].set_yticks((0, 1))
    for ax in axes:
        style_grid(ax)
    style_info_box(axes[1], style_measurement_group_text(msmt_list), location="lower right")
    fig.suptitle("Comparator timing")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_power(
    msmt_list: Sequence[MeasComp],
    analysis: AnalysisCompPower,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot comparator average power per measurement."""

    fig, ax = plt.subplots()
    labels = [str(index) for index in analysis.source_index]
    ax.bar(labels, analysis.average_power_w * 1e6)
    ax.set_ylabel("Average power (µW)")
    ax.set_xlabel("Measurement index")
    style_grid(ax)
    style_info_box(ax, style_measurement_group_text(msmt_list))
    fig.suptitle("Comparator power")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_candidate_sweep(
    msmt_list: Sequence[MeasComp],
    candidates: Sequence[AnalysisCompCandidate],
    *,
    highlights: Mapping[str, str] | None = None,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot candidate noise, power, and settling on one area-ordered axis.

    ``highlights`` marks candidates by ID with a labeled line.
    """

    # Order candidates by summed MOS W*L; geometry and ID break ties reproducibly.
    ordered = sorted(
        candidates,
        key=lambda candidate: (candidate.total_active_area_units, candidate.geometry_signature, candidate.candidate_id),
    )
    analysis = {
        name: np.asarray([getattr(candidate, name) for candidate in ordered])
        for name in ("size_profile", "total_active_area_um2", "noise_sigma_v", "average_power_w", "maximum_settling_s")
    }
    candidate_count = len(candidates)
    position = np.arange(candidate_count)
    colors = {
        "half": CURVE_COLORS[0],
        "double": CURVE_COLORS[1],
        "fabricated": CURVE_COLORS[2],
    }
    fig, axes = plt.subplots(3, 1, sharex=True)
    metrics = (
        (analysis["noise_sigma_v"] * 1e3, "Noise σ (mV)", "linear"),
        (analysis["average_power_w"] * 1e6, "Power (µW)", "log"),
        (analysis["maximum_settling_s"] * 1e9, "Settling (ns)", "linear"),
    )
    for ax, (values, ylabel, scale) in zip(axes, metrics, strict=True):
        for profile in ("half", "double", "fabricated"):
            selected = analysis["size_profile"] == profile
            if not np.any(selected):
                continue
            ax.scatter(
                position[selected],
                values[selected],
                marker="o" if profile != "fabricated" else "*",
                color=colors[profile],
                label={"half": "0.5× FRIDA widths", "double": "2× FRIDA widths", "fabricated": "FRIDA baseline"}[
                    profile
                ],
                zorder=4 if profile == "fabricated" else 2,
            )
        ax.set_ylabel(ylabel)
        ax.set_yscale(scale)
        style_grid(ax)

    baseline = np.flatnonzero(analysis["size_profile"] == "fabricated")
    for ax in axes:
        ax.axvline(baseline[0], color=CURVE_COLORS[2], linestyle="--")
    ordered_ids = [candidate.candidate_id for candidate in ordered]
    for candidate_id, label in (highlights or {}).items():
        index = ordered_ids.index(candidate_id)
        for ax in axes:
            ax.axvline(index, color=NORD_RED, linestyle="--", label=label)
    axes[0].legend(ncols=4 if highlights else 3)

    tick_count = min(12, candidate_count)
    tick_positions = np.unique(np.rint(np.linspace(0, candidate_count - 1, tick_count)).astype(int))
    axes[-1].set_xticks(tick_positions)
    axes[-1].set_xticklabels(
        tuple(f"{index}\n{analysis['total_active_area_um2'][index]:.2f}" for index in tick_positions)
    )
    axes[-1].set_xlabel("Area-ordered candidate index\n(total instantiated MOS Σ(W×L) in µm²)")
    axes[-1].set_xlim(-2, candidate_count + 1)
    style_info_box(axes[2], style_measurement_group_text(msmt_list), location="lower right")
    fig.suptitle("Comparator candidate noise, power, and settling")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_noise_power_tradeoff(
    candidates: Sequence[AnalysisCompCandidate],
    *,
    highlights: Mapping[str, str] | None = None,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot candidate noise against power, colored by settling.

    Candidates with unresolved trials or an invalid S-curve fit have no
    meaningful settling color; those with finite noise and power are shown
    as gray crosses. ``highlights`` rings and labels candidates by ID.
    """

    analysis = {
        name: np.asarray([getattr(candidate, name) for candidate in candidates])
        for name in (
            "size_profile",
            "validity",
            "noise_sigma_v",
            "average_power_w",
            "maximum_settling_s",
            "unresolved_fraction",
        )
    }
    noise_mv = analysis["noise_sigma_v"] * 1e3
    power_uw = analysis["average_power_w"] * 1e6
    settling_ns = analysis["maximum_settling_s"] * 1e9
    valid_scurve = analysis["validity"] == "valid"
    finite_positive = (
        np.isfinite(noise_mv)
        & np.isfinite(power_uw)
        & np.isfinite(settling_ns)
        & (noise_mv > 0.0)
        & (power_uw > 0.0)
        & (settling_ns > 0.0)
    )
    resolved = analysis["unresolved_fraction"] == 0.0
    selected = valid_scurve & finite_positive & resolved
    other = ~selected & np.isfinite(noise_mv) & np.isfinite(power_uw) & (power_uw > 0.0)
    selected_settling_ns = settling_ns[selected]
    color_min = float(calc.ymin(selected_settling_ns))
    color_max = float(calc.ymax(selected_settling_ns))
    if np.isclose(color_min, color_max):
        color_max = color_min + 1.0
    color_norm = Normalize(vmin=color_min, vmax=color_max)
    profiles = analysis["size_profile"]

    fig, ax = plt.subplots()
    mappable = ScalarMappable(norm=color_norm, cmap=SPECTRUM_COLOR_MAP)
    for profile, marker, label in (
        ("half", "o", "0.5× FRIDA widths"),
        ("double", "s", "2× FRIDA widths"),
    ):
        profile_selected = selected & (profiles == profile)
        if not np.any(profile_selected):
            continue
        ax.scatter(
            noise_mv[profile_selected],
            power_uw[profile_selected],
            c=settling_ns[profile_selected],
            cmap=SPECTRUM_COLOR_MAP,
            norm=color_norm,
            marker=marker,
            edgecolors=SPINE_COLOR,
            linewidths=0.35,
            label=label,
            zorder=2,
        )
    if np.any(other):
        ax.scatter(
            noise_mv[other],
            power_uw[other],
            marker="x",
            color=SPINE_COLOR,
            label="Unresolved trials or invalid S-curve",
            zorder=1,
        )
    baseline = np.flatnonzero(profiles == "fabricated")
    baseline_index = int(baseline[0])
    ax.scatter(
        noise_mv[baseline_index],
        power_uw[baseline_index],
        marker="*",
        color=CURVE_COLORS[2],
        edgecolors=TEXT_COLOR,
        linewidths=0.7,
        label="FRIDA65A fabricated baseline",
        zorder=5,
    )
    ax.annotate(
        "FRIDA65A",
        (noise_mv[baseline_index], power_uw[baseline_index]),
        xytext=(8, 7),
        textcoords="offset points",
    )
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    for candidate_id, label in (highlights or {}).items():
        index = candidate_ids.index(candidate_id)
        ax.scatter(
            noise_mv[index],
            power_uw[index],
            s=160,
            facecolors="none",
            edgecolors=NORD_RED,
            linewidths=1.5,
            zorder=6,
        )
        ax.annotate(label, (noise_mv[index], power_uw[index]), xytext=(10, -14), textcoords="offset points")

    colorbar = fig.colorbar(mappable, ax=ax, pad=0.02)
    colorbar.set_label("Worst settling time (ns)")

    ax.set_yscale("log")
    ax.set_xlabel("Input-referred noise σ (mV)")
    ax.set_ylabel("Average power (µW)")
    style_grid(ax)
    ax.legend()
    fig.suptitle("Comparator noise–power trade-off")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_delay(
    delays: Sequence[AnalysisCompDelay],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the topologies' clock-to-decision delay versus differential input, one curve per common mode."""

    if not delays or len(delays) != len(labels):
        raise ValueError("delay comparison requires one delay result and label per topology")
    columns = min(3, len(delays))
    rows = (len(delays) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (delay, label) in enumerate(zip(delays, labels, strict=True)):
        ax = axes.flat[index]
        for row, vin_cm_v in enumerate(delay.vin_cm_v):
            ax.plot(
                delay.vin_diff_v * 1e3,
                delay.delay_s[row] * 1e12,
                "o-",
                color=SPECTRUM_COLOR_MAP(row / max(len(delay.vin_cm_v) - 1, 1)),
                markersize=3,
                label=f"{vin_cm_v * 1e3:g} mV",
            )
        ax.set_xscale("log")
        ax.set_title(label)
        style_grid(ax)
    # the shared limit, once every panel has drawn: one panel's would cut the others' data
    axes.flat[0].set_ylim(bottom=0.0)
    for ax in axes.flat[len(delays) :]:
        ax.set_visible(False)
    axes.flat[0].legend(title="Common mode")
    fig.supxlabel("Differential input (mV)")
    fig.supylabel("Clock-to-decision delay (ps)")
    fig.suptitle("Comparator delay versus input")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_common_mode(
    delays: Sequence[AnalysisCompDelay],
    common_modes: Sequence[AnalysisCompCommonMode],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the topologies' input-referred noise and smallest-input delay versus common mode."""

    if not delays or not len(delays) == len(common_modes) == len(labels):
        raise ValueError("common-mode comparison requires one delay, common-mode result and label per topology")
    columns = min(3, len(delays))
    rows = (len(delays) + columns - 1) // columns
    # only valid S-curve fits are drawn; every panel shares one noise and one delay scale
    noise_mv = [
        np.where(np.asarray(item.validity) == "valid", item.noise_sigma_v * 1e3, np.nan) for item in common_modes
    ]
    noise_limit_mv = 1.1 * max(np.nanmax(values, initial=0.0) for values in noise_mv) or 1.0
    delay_ps = [item.delay_s[:, 0] * 1e12 for item in delays]
    delay_limit_ps = 1.1 * max(np.nanmax(values, initial=0.0) for values in delay_ps) or 1.0
    fig, axes = plt.subplots(rows, columns, sharex=True, squeeze=False)
    for index, (delay, common_mode, noise, smallest, label) in enumerate(
        zip(delays, common_modes, noise_mv, delay_ps, labels, strict=True)
    ):
        ax = axes.flat[index]
        ax.plot(common_mode.vin_cm_v * 1e3, noise, "o-", color=NORD_BLUE, markersize=3)
        ax.set_ylim(0.0, noise_limit_mv)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        delay_ax = ax.twinx()
        delay_ax.plot(delay.vin_cm_v * 1e3, smallest, "s--", color=NORD_RED, markersize=3)
        delay_ax.set_ylim(0.0, delay_limit_ps)
        delay_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(delays) - 1:
            delay_ax.set_ylabel(f"Delay at {delay.vin_diff_v[0] * 1e3:g} mV (ps)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(delays) :]:
        ax.set_visible(False)
    fig.supxlabel("Common mode (mV)")
    fig.supylabel("Input-referred noise σ (mV)", color=NORD_BLUE)
    fig.suptitle("Comparator noise and delay versus common mode")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_energy(
    powers: Sequence[AnalysisCompPower],
    common_modes: Sequence[AnalysisCompCommonMode],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the topologies' energy per decision and systematic offset versus common mode.

    Each power result holds one entry per S-curve, in the order of its common-mode result.
    """

    if not powers or not len(powers) == len(common_modes) == len(labels):
        raise ValueError("energy comparison requires one power, common-mode result and label per topology")
    if any(
        len(power.energy_per_decision_j) != len(item.vin_cm_v) for power, item in zip(powers, common_modes, strict=True)
    ):
        raise ValueError("energy comparison requires one power entry per common mode")
    columns = min(3, len(powers))
    rows = (len(powers) + columns - 1) // columns
    offsets_mv = [np.where(np.asarray(item.validity) == "valid", item.offset_v * 1e3, np.nan) for item in common_modes]
    offset_limit_mv = 1.1 * max(np.nanmax(np.abs(values), initial=0.0) for values in offsets_mv) or 1.0
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (power, common_mode, offset, label) in enumerate(
        zip(powers, common_modes, offsets_mv, labels, strict=True)
    ):
        ax = axes.flat[index]
        ax.plot(common_mode.vin_cm_v * 1e3, power.energy_per_decision_j * 1e15, "o-", color=NORD_BLUE, markersize=3)
        ax.tick_params(axis="y", colors=NORD_BLUE)
        offset_ax = ax.twinx()
        offset_ax.plot(common_mode.vin_cm_v * 1e3, offset, "s--", color=NORD_RED, markersize=3)
        offset_ax.set_ylim(-offset_limit_mv, offset_limit_mv)
        offset_ax.tick_params(axis="y", colors=NORD_RED)
        if index % columns == columns - 1 or index == len(powers) - 1:
            offset_ax.set_ylabel("Systematic offset (mV)", color=NORD_RED)
        ax.set_title(label)
        style_grid(ax)
    # the shared limit, once every panel has drawn: one panel's would cut the others' data
    axes.flat[0].set_ylim(bottom=0.0)
    for ax in axes.flat[len(powers) :]:
        ax.set_visible(False)
    fig.supxlabel("Common mode (mV)")
    fig.supylabel("Energy per decision (fJ)", color=NORD_BLUE)
    fig.suptitle("Comparator energy and offset versus common mode")
    return save_figure(fig, output_path)
