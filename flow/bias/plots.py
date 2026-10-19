"""Cascode bias comparisons: one panel per named case, shared axes."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.plots import (
    NORD_BLUE,
    NORD_DARK,
    NORD_RED,
    PLOT_STYLE,
    save_figure,
    style_grid,
    style_ratio_limits,
)
from flow.bias.analysis import AnalysisBiasMirror


@mpl.rc_context(PLOT_STYLE)
def plot_bias_mirror(
    mirrors: Sequence[AnalysisBiasMirror],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the test mirrors' current over their output voltage, relative to the reference, at
    each case's nominal reference (its point nearest 10 µA), the compliance limits dotted."""

    if not mirrors or len(mirrors) != len(labels):
        raise ValueError("mirror comparison requires one mirror result and label per generator")
    columns = min(2, len(mirrors))
    rows = (len(mirrors) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    nominal = [int(np.argmin(np.abs(np.log(mirror.iref_a / 10e-6)))) for mirror in mirrors]
    # the panels share one axis: high enough for every panel's characteristics, and above 1
    _, top = style_ratio_limits(
        *(
            curve[row]
            for mirror, row in zip(mirrors, nominal, strict=True)
            for curve in (mirror.n_iv_ratio, mirror.p_iv_ratio)
        )
    )
    for index, (mirror, label, row) in enumerate(zip(mirrors, labels, nominal, strict=True)):
        ax = axes.flat[index]
        ax.plot(mirror.vout_v[row], mirror.n_iv_ratio[row], "-", color=NORD_BLUE, label="NMOS mirror")
        ax.plot(mirror.vout_v[row], mirror.p_iv_ratio[row], "-", color=NORD_RED, label="PMOS mirror")
        for level, color in ((mirror.n_compliance_v[row], NORD_BLUE), (mirror.p_compliance_v[row], NORD_RED)):
            ax.axvline(level, color=color, linestyle=":", linewidth=0.8)
        ax.axhline(1.0, color=NORD_DARK, linewidth=0.6)
        ax.set_ylim(0.0, top)
        ax.set_title(
            f"{label}\nat {mirror.iref_a[row] * 1e6:g} µA: {mirror.n_ratio[row]:.3f} / {mirror.p_ratio[row]:.3f}"
        )
        style_grid(ax)
    for ax in axes.flat[len(mirrors) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="lower center", fontsize="small")
    fig.supxlabel("Mirror output (V)")
    fig.supylabel("Output current over the reference")
    fig.suptitle("Cascoded test mirrors on the generated gates")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_bias_reference(
    mirrors: Sequence[AnalysisBiasMirror],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the mirror devices' headroom and the mirrors' current ratio over the reference."""

    if not mirrors or len(mirrors) != len(labels):
        raise ValueError("reference comparison requires one mirror result and label per generator")
    columns = min(2, len(mirrors))
    rows = (len(mirrors) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    for index, (mirror, label) in enumerate(zip(mirrors, labels, strict=True)):
        ax = axes.flat[index]
        iref_ua = mirror.iref_a * 1e6
        ax.semilogx(iref_ua, mirror.n_headroom_v * 1e3, "o-", color=NORD_BLUE, markersize=3, label="NMOS headroom")
        ax.semilogx(iref_ua, mirror.p_headroom_v * 1e3, "s-", color=NORD_RED, markersize=3, label="PMOS headroom")
        ax.tick_params(axis="y", colors=NORD_DARK)
        ratio_ax = ax.twinx()
        ratio_ax.semilogx(iref_ua, mirror.n_ratio, "o:", color=NORD_BLUE, markersize=3)
        ratio_ax.semilogx(iref_ua, mirror.p_ratio, "s:", color=NORD_RED, markersize=3)
        ratio_ax.set_ylim(*style_ratio_limits(mirror.n_ratio, mirror.p_ratio))
        if index % columns == columns - 1 or index == len(mirrors) - 1:
            ratio_ax.set_ylabel("Current over the reference (dotted)")
        ax.set_title(label)
        style_grid(ax)
    for ax in axes.flat[len(mirrors) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="upper left", fontsize="small")
    fig.supxlabel("Reference current (µA)")
    fig.supylabel("Mirror device drain-source voltage (mV)")
    fig.suptitle("Cascode bias headroom and accuracy versus reference current")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_bias_supply(
    mirrors: Sequence[AnalysisBiasMirror],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the mirrors' current ratio and the mirror devices' headroom over the supply."""

    if not mirrors or len(mirrors) != len(labels):
        raise ValueError("supply comparison requires one mirror result and label per generator")
    columns = min(2, len(mirrors))
    rows = (len(mirrors) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    # the panels share one axis: wide enough for every panel's ratios
    limits = style_ratio_limits(*(ratio for mirror in mirrors for ratio in (mirror.n_ratio, mirror.p_ratio)))
    for index, (mirror, label) in enumerate(zip(mirrors, labels, strict=True)):
        ax = axes.flat[index]
        ax.plot(mirror.vdd_v, mirror.n_ratio, "o-", color=NORD_BLUE, markersize=3, label="NMOS mirror")
        ax.plot(mirror.vdd_v, mirror.p_ratio, "s-", color=NORD_RED, markersize=3, label="PMOS mirror")
        ax.set_ylim(*limits)
        head_ax = ax.twinx()
        head_ax.plot(mirror.vdd_v, mirror.n_headroom_v * 1e3, "o:", color=NORD_BLUE, markersize=3)
        head_ax.plot(mirror.vdd_v, mirror.p_headroom_v * 1e3, "s:", color=NORD_RED, markersize=3)
        if index % columns == columns - 1 or index == len(mirrors) - 1:
            head_ax.set_ylabel("Mirror device drain-source voltage (mV, dotted)")
        ax.set_title(f"{label}\nat {mirror.iref_a[0] * 1e6:g} µA")
        style_grid(ax)
    for ax in axes.flat[len(mirrors) :]:
        ax.set_visible(False)
    axes.flat[0].legend(loc="lower right", fontsize="small")
    fig.supxlabel("Supply (V)")
    fig.supylabel("Output current over the reference")
    fig.suptitle("Cascode bias accuracy and headroom versus supply")
    return save_figure(fig, output_path)
