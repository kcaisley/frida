"""Plots of typed FRIDA measurements and analysis results."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from basil.HL.tektronix_oscilloscope import CapturedWaveform
from cycler import cycler
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.offsetbox import AnchoredOffsetbox, TextArea, VPacker
from matplotlib.patches import Patch
from matplotlib.ticker import AutoMinorLocator, NullLocator, StrMethodFormatter
from scipy.special import ndtr

from flow import comp
from flow.adc.sim import AdcSequence
from flow.analysis import calc
from flow.analysis.types import (
    AnalysisAdcComparatorEdgeEye,
    AnalysisAdcComparatorResponse,
    AnalysisAdcCompOutEdgeEye,
    AnalysisAdcScopeBits,
    AnalysisCdacCapMismatch,
    AnalysisScope,
    Meas,
    MeasAdc,
    MeasCdac,
    Wave,
)
from flow.scans.scope import ScopeConns, scope_wave

PLOT_PNGS = False
PLOT_SVGS = False
PLOT_PDFS = True
PNG_DPI = 500
INFO_BOX_FONT_SIZE = 7.0

# Nord presentation colors. The ordering gives all plots a stable semantic
# sequence instead of inheriting Matplotlib's version-dependent default cycle.
PLOT_FACE_COLOR = "white"
TEXT_COLOR = "black"
SPINE_COLOR = "#4C566A"
LEGEND_FACE_COLOR = "#ECEFF4"
GRID_MAJOR_COLOR = "#D8DEE9"
GRID_MINOR_COLOR = "#E5E9F0"
NORD_BLUE = "#5E81AC"
NORD_RED = "#BF616A"
NORD_GREEN = "#A3BE8C"
NORD_ORANGE = "#D08770"
NORD_PURPLE = "#B48EAD"
NORD_CYAN = "#88C0D0"
NORD_YELLOW = "#EBCB8B"
NORD_TEAL = "#8FBCBB"
NORD_LIGHT_BLUE = "#81A1C1"
NORD_DARK = "#4C566A"
# The scope's amplitude-spectral-density plots share this range in nV/√Hz (the
# ADC's input-referred code spectra are its spec, flow.adc.plots, on their own data).
SPECTRAL_DENSITY_LIMITS_NV = (1.0, 1.0e5)
# The per-decade RMS panels below them share this range in µV.
DECADE_RMS_LIMITS_UV = (0.1, 1.0e4)

CURVE_COLORS = (
    NORD_BLUE,
    NORD_ORANGE,
    NORD_GREEN,
    NORD_PURPLE,
    NORD_YELLOW,
    NORD_RED,
    NORD_CYAN,
    NORD_TEAL,
    NORD_LIGHT_BLUE,
    NORD_DARK,
)
SPECTRUM_COLOR_MAP = LinearSegmentedColormap.from_list(
    "nord_blue_orange_yellow",
    (NORD_BLUE, NORD_ORANGE, NORD_YELLOW),
)
DENSITY_COLOR_MAP = LinearSegmentedColormap.from_list(
    "nord_purple_orange_yellow",
    SPECTRUM_COLOR_MAP(np.linspace(0.2, 1.0, 256)),
)
PLOT_STYLE = mpl.RcParams(
    {
        "text.usetex": False,
        "mathtext.fontset": "cm",
        "font.family": "serif",
        "font.serif": ["Computer Modern Roman", "DejaVu Serif"],
        "font.size": 10.0,
        "figure.figsize": (9.6, 5.4),
        "figure.constrained_layout.use": True,
        "axes.titlesize": 12.0,
        "axes.titlecolor": TEXT_COLOR,
        "axes.titleweight": "normal",
        "axes.labelsize": 10.0,
        "axes.labelcolor": TEXT_COLOR,
        "axes.edgecolor": SPINE_COLOR,
        "axes.linewidth": 0.8,
        "axes.facecolor": PLOT_FACE_COLOR,
        "axes.grid": False,
        "axes.prop_cycle": cycler(color=CURVE_COLORS),
        "xtick.color": TEXT_COLOR,
        "xtick.direction": "in",
        "xtick.labelsize": 10.0,
        "xtick.major.size": 2.5,
        "xtick.minor.size": 1.5,
        "xtick.top": True,
        "ytick.color": TEXT_COLOR,
        "ytick.direction": "in",
        "ytick.labelsize": 10.0,
        "ytick.major.size": 2.5,
        "ytick.minor.size": 1.5,
        "ytick.right": True,
        "text.color": TEXT_COLOR,
        "figure.facecolor": PLOT_FACE_COLOR,
        "figure.titlesize": 12.0,
        "figure.titleweight": "normal",
        "savefig.facecolor": PLOT_FACE_COLOR,
        "savefig.dpi": PNG_DPI,
        "savefig.bbox": None,
        "legend.loc": "best",
        "legend.frameon": True,
        "legend.fancybox": True,
        "legend.facecolor": LEGEND_FACE_COLOR,
        "legend.edgecolor": SPINE_COLOR,
        "legend.framealpha": 0.9,
        "legend.labelcolor": TEXT_COLOR,
        "legend.linewidth": 0.8,
        "legend.borderpad": 0.4,
        "legend.borderaxespad": 0.5,
        "legend.fontsize": 10.0,
        "legend.title_fontsize": 10.0,
        "lines.linewidth": 1.0,
        "lines.markersize": 4.0,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def style_grid(ax: plt.Axes) -> None:
    """Apply the shared light grid."""

    # rcParams cannot give major and minor grid lines different appearances.
    # Retain explicitly selected minor-tick intervals, such as the 0.25 MSPS
    # measurement spacing. ``minorticks_on`` would replace them with an
    # AutoMinorLocator and produce misleading 0.20 MSPS tick marks.
    if isinstance(ax.xaxis.get_minor_locator(), NullLocator):
        ax.xaxis.set_minor_locator(AutoMinorLocator())
    if isinstance(ax.yaxis.get_minor_locator(), NullLocator):
        ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.set_axisbelow(True)
    ax.grid(
        True,
        which="major",
        color=GRID_MAJOR_COLOR,
        alpha=0.95,
        linewidth=0.8,
    )
    ax.grid(
        True,
        which="minor",
        color=GRID_MINOR_COLOR,
        alpha=1.0,
        linewidth=0.5,
    )


def style_info_box(
    ax: plt.Axes,
    lines: Sequence[str],
    *,
    location: str = "upper right",
    line_colors: Sequence[str] | None = None,
) -> None:
    """Add measurement setup using the same spacing and frame as a legend."""

    # Legend rcParams do not apply automatically to anchored offset boxes.
    if not lines:
        return
    if line_colors is not None and len(line_colors) != len(lines):
        raise ValueError("information-box line colors must match its lines")
    if line_colors is None:
        child = TextArea("\n".join(lines), textprops={"size": INFO_BOX_FONT_SIZE})
    else:
        child = VPacker(
            children=[
                TextArea(line, textprops={"color": color, "size": INFO_BOX_FONT_SIZE})
                for line, color in zip(lines, line_colors, strict=True)
            ],
            align="left",
            pad=0.0,
            sep=1.0,
        )
    box = AnchoredOffsetbox(
        loc=location,
        child=child,
        frameon=True,
        pad=mpl.rcParams["legend.borderpad"],
        borderpad=mpl.rcParams["legend.borderaxespad"],
    )
    box.patch.set_boxstyle(f"round,pad={mpl.rcParams['legend.borderpad']}")
    box.patch.set_facecolor(mpl.rcParams["legend.facecolor"])
    box.patch.set_edgecolor(mpl.rcParams["legend.edgecolor"])
    box.patch.set_alpha(mpl.rcParams["legend.framealpha"])
    box.patch.set_linewidth(mpl.rcParams["legend.linewidth"])
    ax.add_artist(box)


def style_measurement_group_text(msmt_list: Sequence[Meas | comp.AnalysisDecisions]) -> tuple[str, ...]:
    """Return only setup lines shared by every measurement in a group."""

    # rcParams cannot derive display text from typed measurement metadata.
    if not msmt_list:
        return ()
    shared = list(style_measurement_text(msmt_list[0]))
    for msmt in msmt_list[1:]:
        current = set(style_measurement_text(msmt))
        shared = [line for line in shared if line in current]
    adc_indices = sorted(
        {int(adc_index) for msmt in msmt_list if (adc_index := getattr(msmt.param, "observed_adc", None)) is not None}
    )
    shared = [line for line in shared if not line.startswith(("ADC: ", "ADCs: "))]
    if len(adc_indices) == 1:
        shared.insert(0, f"ADC: {adc_indices[0]:02d}")
    elif adc_indices:
        shared.insert(0, "ADCs: " + ", ".join(f"{adc_index:02d}" for adc_index in adc_indices))
    return tuple(shared)


def style_time_units(time_s: np.ndarray) -> tuple[float, str]:
    # rcParams cannot choose a readable unit from the plotted data extent.
    maximum = float(calc.ymax(np.abs(time_s)))
    if maximum < 1e-9:
        return 1e12, "ps"
    if maximum < 1e-6:
        return 1e9, "ns"
    if maximum < 1e-3:
        return 1e6, "µs"
    if maximum < 1.0:
        return 1e3, "ms"
    return 1.0, "s"


def style_ratio_limits(*ratios: np.ndarray) -> tuple[float, float]:
    """An axis around 1 wide enough for every finite ratio, so the worst points stay in view."""
    finite = np.concatenate([np.asarray(ratio, dtype=np.float64) for ratio in ratios])
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return 0.9, 1.1
    return min(0.9, float(np.min(finite)) - 0.05), max(1.1, float(np.max(finite)) + 0.05)


def save_figure(
    fig: plt.Figure,
    output_path: Path,
    *,
    pdf_metadata: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    output_path = Path(output_path)
    if output_path.suffix:
        raise ValueError("plot output_path must be a suffixless artifact stem")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    formats = tuple(
        output_format
        for output_format, enabled in (
            ("png", PLOT_PNGS),
            ("svg", PLOT_SVGS),
            ("pdf", PLOT_PDFS),
        )
        if enabled
    )
    if not formats:
        raise RuntimeError("at least one plot output format must be enabled")
    # Preserve figures that explicitly disable automatic layout. Matplotlib can
    # otherwise install the rcParam-selected constrained-layout engine after the
    # first backend renders, causing later formats to move manually positioned
    # axes underneath legends and colorbars.
    with mpl.rc_context({"figure.constrained_layout.use": False}):
        for output_format in formats:
            path = output_path.with_suffix(f".{output_format}")
            if output_format == "pdf" and pdf_metadata is not None:
                fig.savefig(path, metadata=dict(pdf_metadata))
            else:
                fig.savefig(path)
            paths.append(path)
    plt.close(fig)
    return tuple(paths)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_mismatch_nonlinearity(
    coefficients: Sequence[float],
    decodings: Mapping[str, Mapping[str, np.ndarray]],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot the worst DNL and INL and the missing codes of capacitor draws at each Pelgrom
    coefficient (A_C, the relative sigma of a 1-fF capacitor).

    ``decodings`` maps each decoding's label to its ``dnl``, ``inl`` and ``missing`` arrays of
    shape (coefficients, draws); each panel shows the median over the draws and their 5-95 % band.
    """

    fig, axes = plt.subplots(3, 1, sharex=True)
    percent = np.asarray(coefficients, dtype=np.float64) * 100
    for (label, stats), color in zip(decodings.items(), CURVE_COLORS, strict=False):
        for ax, key in zip(axes, ("dnl", "inl", "missing"), strict=True):
            values = np.asarray(stats[key], dtype=np.float64)
            low, median, high = np.percentile(values, (5, 50, 95), axis=1)
            ax.fill_between(percent, low, high, color=color, alpha=0.2, linewidth=0)
            ax.plot(percent, median, "o-", color=color, label=label)
    axes[0].axhline(0.5, color=SPINE_COLOR, linestyle="--", linewidth=0.8)
    axes[0].set_ylabel("Max |DNL| (LSB)")
    axes[1].set_ylabel("Max |INL| (LSB)")
    axes[2].set_ylabel("Missing codes")
    axes[2].set_xscale("log")
    axes[2].set_xlabel(r"Pelgrom coefficient $A_C$ (%$\cdot\sqrt{\mathrm{fF}}$)")
    for ax in axes:
        style_grid(ax)
    axes[0].legend()
    fig.suptitle("ADC nonlinearity over capacitor mismatch (median, 5-95 % of draws)")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_waveforms(
    wave: Wave,
    *,
    output_path: Path,
    title: str,
    signals: Mapping[str, str] | None = None,
    record: int = 0,
    time_origin_s: float = 0.0,
    setup_lines: Sequence[str] = (),
) -> tuple[Path, ...]:
    """Plot selected node voltages and supply currents of one waveform record.

    ``signals`` maps a voltage name, or ``i(<supply>)`` for a supply current,
    to its axis label; by default every voltage is plotted under its own name.
    Each signal gets its own stacked axis. Time is shown relative to
    ``time_origin_s``.
    """

    selected = signals if signals is not None else {name: name for name in wave.v}
    if not selected:
        raise ValueError("waveform plots show at least one signal")
    traces = [
        (wave.i[name[2:-1]], "A") if name.startswith("i(") and name.endswith(")") else (wave.v[name], "V")
        for name in selected
    ]
    time_s = wave.time_s - time_origin_s
    scale, unit = style_time_units(time_s)
    fig, axes = plt.subplots(len(selected), 1, sharex=True)
    axes = np.atleast_1d(axes)
    for ax, label, (values, signal_unit) in zip(axes, selected.values(), traces, strict=True):
        ax.plot(time_s * scale, values[record])
        # Horizontal labels stay readable for long net names and expressions.
        ax.set_ylabel(f"{label} ({signal_unit})", rotation=0, ha="right", va="center")
        style_grid(ax)
    axes[-1].set_xlabel(f"Time ({unit})")
    style_info_box(axes[0], tuple(setup_lines))
    fig.suptitle(title)
    return save_figure(fig, output_path)


def style_measurement_text(msmt: Meas | comp.AnalysisDecisions) -> tuple[str, ...]:
    """Format concise plot context persisted with one measurement."""

    tb = msmt.tb
    lines: tuple[str, ...] = ()
    adc_index = getattr(msmt.param, "observed_adc", None)
    if adc_index is not None:
        lines += (f"ADC: {adc_index:02d}",)
    elif msmt.info.backend != "physical" and isinstance(msmt, (MeasAdc, comp.AnalysisDecisions)):
        lines += ("Source: Sim" if msmt.info.backend == "behavioral" else f"Source: {msmt.info.backend.upper()}",)
    mismatch = msmt.info.readbacks.get("unit_mismatch") if msmt.info.readbacks else None
    if msmt.info.backend == "behavioral" and mismatch is not None:
        # Pelgrom coefficients from Tripathi (JSSC 2014) and Harpe's unit-length DAC.
        source = {0.0085: " (Tripathi)", 0.0010: " (Harpe)"}.get(round(float(mismatch), 6), "")
        lines += (
            f"Pelgrom mismatch: A = {float(mismatch) * 100:g} %·√fF{source}"
            if mismatch
            else "Capacitor mismatch: none",
        )
        if mismatch and msmt.group is not None:
            lines += (f"Mismatch draw: {msmt.group}",)
    board_id = getattr(msmt.param, "board_id", None)
    if board_id is not None:
        lines += (f"Board: {board_id:02d}",)
    for field_name, label in (("vin_cm", "Vcm"), ("vin_diff", "Vdiff")):
        dc_v = getattr(getattr(tb, field_name, None), "dc", None)
        if dc_v is not None:
            lines += (f"{label}: {float(dc_v) * 1e3:g} mV",)
    # A standalone block testbench has no SAR sequence or CDAC state.
    if not hasattr(tb, "seq_init_pattern"):
        return lines
    sequence = AdcSequence.from_tb_params(tb)
    if isinstance(msmt, MeasAdc):
        lines += (f"Conversion: {float(tb.symbol_rate) / sequence.conversion_symbols / 1e6:g} MSPS",)
    lines += (f"Repetition: {len(sequence.init) / float(tb.symbol_rate) * 1e9:g} ns",)
    init_p = int("".join(str(int(bit)) for bit in tb.dac_astate_p), 2)
    init_n = int("".join(str(int(bit)) for bit in tb.dac_astate_n), 2)
    if init_p == init_n:
        lines += (f"CDAC init: h'{init_p:04X}",)
    else:
        lines += (f"CDAC init: P h'{init_p:04X}, N h'{init_n:04X}",)
    return lines


@mpl.rc_context(PLOT_STYLE)
def plot_adc_comparator_edge_eye(
    analysis: AnalysisAdcComparatorEdgeEye,
    *,
    output_path: Path,
    context: str | None = None,
) -> tuple[Path, ...]:
    """Overlay every saved conversion and every COMP-aligned decision window."""

    signal_names = ("Comparator clock", "SR-latch P", "XC-latch |P−N|")
    period_ns = analysis.decision_period_s * 1e9
    edge_ns = analysis.decision_edge_s * 1e9
    decisions = len(edge_ns)
    records = analysis.aligned_v.shape[1]
    full_time_ns = analysis.aligned_time_s * 1e9
    eye_time_ns = analysis.eye_phase * period_ns
    full_segments = [[np.column_stack((full_time_ns, row)) for row in rows] for rows in analysis.aligned_v]
    decision_segments = [[np.column_stack((eye_time_ns, row)) for row in rows] for rows in analysis.eye_v]
    supply = analysis.supply_v
    output_path = Path(output_path)
    paths = []
    for suffix, segments_by_signal in (("timing", full_segments), ("decision_eye", decision_segments)):
        fig, ax = plt.subplots(figsize=(14, 5.5))
        handles = [ax.plot([], [], label=name)[0] for name in signal_names]
        for handle, segments in zip(handles, segments_by_signal, strict=True):
            ax.add_collection(
                LineCollection(segments, colors=(handle.get_color(),), alpha=0.7, linewidths=1.0, rasterized=True)
            )
        if suffix == "timing":
            decision_axis = ax.secondary_xaxis("top")
            decision_axis.set_xticks(edge_ns, labels=[f"B{decision}" for decision in range(decisions)])
            ax.set_xlim(-0.2 * period_ns, edge_ns[-1] + period_ns)
            ax.set_xlabel("Time from B0 comparator clock rise (ns)")
            title = f"PEX comparator waveforms: {records} conversions overlaid"
        else:
            ax.set_xlim(-0.1 * period_ns, 1.1 * period_ns)
            ax.set_xlabel("Time from each comparator clock rise (ns)")
            title = f"PEX comparator decision eye: {records} conversions × {decisions} decisions"
        ax.set_title(f"{title}\n{context}" if context else title)
        ax.set_ylim(-0.1 * supply, 1.1 * supply)
        ax.set_ylabel("Voltage (V); XC trace is |P−N|")
        style_grid(ax)
        fig.legend(handles=handles, loc="outside lower center", ncol=len(handles))
        metadata = (
            {"Title": title, "Subject": context.replace("\n", "; "), "Keywords": "PEX simulation"} if context else None
        )
        paths.extend(save_figure(fig, output_path.with_name(f"{output_path.name}_{suffix}"), pdf_metadata=metadata))
    return tuple(paths)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_comparator_response(
    analysis: AnalysisAdcComparatorResponse,
    *,
    output_path: Path,
    context: str | None = None,
) -> tuple[Path, ...]:
    """Plot XC rail validity and positive SR output histograms at each decision, B0 first."""

    decisions = int(np.max(analysis.decision_index)) + 1
    internal = [analysis.internal_response_s[analysis.decision_index == decision] for decision in range(decisions)]
    output = [analysis.sr_response_s[analysis.decision_index == decision] for decision in range(decisions)]
    fig, ax = plt.subplots(figsize=(12, 6))
    series = (internal, output)
    labels = ("XC-latch |P−N| (both rails valid)", "SR-latch P (single-ended rail valid)")
    populated = [
        scaled for stages in series for values in stages if len(scaled := np.asarray(values)[np.isfinite(values)] * 1e9)
    ]
    if not populated:
        raise ValueError("no valid comparator response times to plot")
    all_values = np.concatenate(populated)
    lower, upper = float(all_values.min()), float(all_values.max())
    if lower == upper:
        lower -= 0.05
        upper += 0.05
    bins = np.linspace(lower, upper, 49)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    bin_height = float(bins[1] - bins[0]) * 0.95
    peak_fraction = max(calc.ymax(np.histogram(values, bins=bins)[0]) / len(values) for values in populated)
    for stages, label in zip(series, labels, strict=True):
        positions = []
        widths = []
        left_edges = []
        median_x = []
        median_y = []
        for decision, values in enumerate(stages):
            values = np.asarray(values)
            scaled = values[np.isfinite(values)] * 1e9
            if not len(scaled):
                continue
            counts, _ = np.histogram(scaled, bins=bins)
            occupied = counts > 0
            positions.extend(bin_centers[occupied])
            widths.extend(0.58 * counts[occupied] / len(scaled) / peak_fraction)
            left_edges.extend(np.full(np.count_nonzero(occupied), decision))
            median_x.append(decision)
            median_y.append(np.median(scaled))
        bars = ax.barh(positions, widths, height=bin_height, left=left_edges, alpha=0.5, label=label)
        if bars.patches:
            ax.plot(median_x, median_y, linestyle="none", marker="_", color=bars.patches[0].get_facecolor())
    ax.set_xlim(-0.7, decisions - 0.3)
    ax.set_xticks(range(decisions))
    ax.set_xlabel("ADC decision step (bar width: fraction of transitions per bin)")
    ax.set_ylabel("Time from COMP rise to midpoint response (ns)")
    title = f"ADC comparator response at {analysis.conversion_rate_hz / 1e6:.3g} MSPS (PEX simulation, 50% VDD)"
    ax.set_title(f"{title}\n{context}" if context else title)
    ax.legend()
    if not np.any(np.isfinite(analysis.internal_response_s)):
        ax.text(
            0.99,
            0.97,
            "No XC output reached both rail thresholds before COMP reset",
            transform=ax.transAxes,
            ha="right",
            va="top",
        )
    style_grid(ax)
    output_path = Path(output_path)
    metadata = (
        {"Title": title, "Subject": context.replace("\n", "; "), "Keywords": "PEX simulation"} if context else None
    )
    return save_figure(fig, output_path, pdf_metadata=metadata)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_comp_out_edge_eye(
    analysis: AnalysisAdcCompOutEdgeEye,
    *,
    output_path: Path,
    context: str | None = None,
) -> tuple[Path, ...]:
    """Render external comparator timing from a completed scope analysis."""

    decision_period_s = analysis.decision_period_s
    decisions = analysis.decision_count
    delays_by_decision = [analysis.delays_s[:, decision] for decision in range(decisions)]
    period_ns = decision_period_s * 1e9
    traces = (analysis.aligned_comp_v, analysis.aligned_comp_out_v)
    timing_segments = [[np.column_stack((analysis.aligned_time_s * 1e9, row)) for row in rows] for rows in traces]
    decision_segments = [
        [np.column_stack((analysis.eye_phase * period_ns, row)) for row in rows]
        for rows in (analysis.eye_comp_v, analysis.eye_comp_out_v)
    ]
    voltage_low = float(min(np.nanmin(rows) for rows in traces))
    voltage_high = float(max(np.nanmax(rows) for rows in traces))
    captures = len(analysis.clock_edges_s)

    output_path = Path(output_path)
    voltage_margin = 0.05 * (voltage_high - voltage_low)
    overlay_alpha = 0.35
    metadata = {"Subject": context.replace("\n", "; "), "Keywords": "Oscilloscope measurement"} if context else None
    eye_fig, eye_ax = plt.subplots(figsize=(14, 5.5))
    eye_handles = [eye_ax.plot([], [], label=name)[0] for name in ("Scope COMP", "Scope COMP_OUT")]
    for handle, segments in zip(eye_handles, decision_segments, strict=True):
        eye_ax.add_collection(
            LineCollection(segments, colors=(handle.get_color(),), alpha=overlay_alpha, linewidths=0.6, rasterized=True)
        )
    eye_ax.set_xlim(-0.2 * period_ns, period_ns)
    eye_ax.set_ylim(voltage_low - voltage_margin, voltage_high + voltage_margin)
    eye_ax.set_xlabel("Time from each scope COMP rise (ns)")
    eye_ax.set_ylabel("Voltage at scope (V)")
    eye_title = f"Measured comparator decision eye: {captures} captures × {decisions} decisions"
    eye_ax.set_title(f"{eye_title}\n{context}" if context else eye_title)
    style_grid(eye_ax)
    eye_fig.legend(handles=eye_handles, loc="outside lower center", ncol=len(eye_handles))
    eye_paths = save_figure(
        eye_fig,
        output_path.with_name(output_path.name + "_decision_eye"),
        pdf_metadata={**metadata, "Title": eye_title} if metadata else None,
    )

    timing_fig, timing_ax = plt.subplots(figsize=(14, 5.5))
    timing_handles = [timing_ax.plot([], [], label=name)[0] for name in ("Scope COMP", "Scope COMP_OUT")]
    for handle, segments in zip(timing_handles, timing_segments, strict=True):
        timing_ax.add_collection(
            LineCollection(segments, colors=(handle.get_color(),), alpha=overlay_alpha, linewidths=0.6, rasterized=True)
        )
    decision_axis = timing_ax.secondary_xaxis("top")
    decision_axis.set_xticks(
        np.arange(decisions) * period_ns,
        labels=[f"B{decision}" for decision in range(decisions)],
    )
    timing_ax.set_xlim(-0.2 * period_ns, decisions * period_ns)
    timing_ax.set_ylim(voltage_low - voltage_margin, voltage_high + voltage_margin)
    timing_ax.set_xlabel("Time from B0 scope COMP rise (ns)")
    timing_ax.set_ylabel("Voltage at scope (V)")
    timing_title = f"Measured comparator waveforms: {captures} captures overlaid"
    timing_ax.set_title(f"{timing_title}\n{context}" if context else timing_title)
    style_grid(timing_ax)
    timing_fig.legend(handles=timing_handles, loc="outside lower center", ncol=len(timing_handles))
    timing_paths = save_figure(
        timing_fig,
        output_path.with_name(output_path.name + "_timing"),
        pdf_metadata={**metadata, "Title": timing_title} if metadata else None,
    )

    response_fig, response_ax = plt.subplots(figsize=(12, 6))
    populated = [
        scaled for values in delays_by_decision if len(scaled := np.asarray(values)[np.isfinite(values)] * 1e9)
    ]
    all_values_ns = np.concatenate(populated)
    lower, upper = float(all_values_ns.min()), float(all_values_ns.max())
    if lower == upper:
        lower -= 0.05
        upper += 0.05
    bins = np.linspace(lower, upper, 49)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    bin_height = float(bins[1] - bins[0]) * 0.95
    peak_fraction = max(calc.ymax(np.histogram(values, bins=bins)[0]) / len(values) for values in populated)
    positions = []
    widths = []
    left_edges = []
    median_x = []
    median_y = []
    for decision, values in enumerate(delays_by_decision):
        scaled = np.asarray(values) * 1e9
        if not len(scaled):
            continue
        counts, _ = np.histogram(scaled, bins=bins)
        occupied = counts > 0
        positions.extend(bin_centers[occupied])
        widths.extend(0.39 * counts[occupied] / len(scaled) / peak_fraction)
        left_edges.extend(np.full(np.count_nonzero(occupied), decision))
        median_x.append(decision)
        median_y.append(np.median(scaled))
    bars = response_ax.barh(positions, widths, height=bin_height, left=left_edges, alpha=0.68, label="Scope COMP_OUT")
    if bars.patches:
        response_ax.plot(median_x, median_y, linestyle="none", marker="_", color=bars.patches[0].get_facecolor())
    response_ax.set_xlim(-0.7, decisions - 0.3)
    response_ax.set_xticks(range(decisions))
    response_ax.set_xlabel("ADC decision step (bar width: fraction of transitions per bin)")
    response_title = f"ADC COMP_OUT response at {analysis.conversion_rate_hz / 1e6:g} MSPS (50% swing, measured)"
    response_ax.set_title(f"{response_title}\n{context}" if context else response_title)
    response_ax.set_ylabel("Time from COMP rise to 50% swing (ns)")
    style_grid(response_ax)
    response_paths = save_figure(
        response_fig,
        output_path.with_name(output_path.name + "_response_histogram"),
        pdf_metadata={**metadata, "Title": response_title} if metadata else None,
    )
    return (*eye_paths, *timing_paths, *response_paths)


@mpl.rc_context(PLOT_STYLE)
def plot_serdes_output_word_grid(
    captures_by_case: Mapping[tuple[int, int], Sequence[Mapping[int, CapturedWaveform]]],
    *,
    output_channel: int,
    output_path: Path,
) -> tuple[Path, ...]:
    """Show 1..7-of-8 serializer words at three baud rates over their full period."""

    rates_mbd = (320, 960, 1600)
    high_counts = range(1, 8)
    if set(captures_by_case) != {(rate, high) for rate in rates_mbd for high in high_counts}:
        raise ValueError("word grid requires 1..7-of-8 captures at 320, 960, and 1600 MBd")
    output_path = Path(output_path)
    fig = plt.figure(figsize=(18, 9))
    grid = fig.add_gridspec(4, 7, height_ratios=(0.35, 1, 1, 1))
    axes = np.empty((3, 7), dtype=object)
    for column, high_symbols in enumerate(high_counts):
        icon_ax = fig.add_subplot(grid[0, column])
        icon_ax.plot(
            (-0.2, 0, 0, high_symbols, high_symbols, 8.2),
            (0, 0, 1, 1, 0, 0),
        )
        icon_ax.set_xlim(-0.2, 8.2)
        icon_ax.set_ylim(-0.2, 1.2)
        icon_ax.set_axis_off()
        icon_ax.set_title(f"{high_symbols} of 8", fontsize=10)
        for row, rate_mbd in enumerate(rates_mbd):
            shared = axes[0, 0] if row or column else None
            ax = fig.add_subplot(grid[row + 1, column], sharex=shared, sharey=shared)
            axes[row, column] = ax
            captures = captures_by_case[(rate_mbd, high_symbols)]
            if not captures:
                raise ValueError(f"{rate_mbd} MBd, {high_symbols} of 8 has no captures")
            unit_interval_s = 1.0 / (rate_mbd * 1e6)
            segments = []
            for capture_index, capture in enumerate(captures):
                wave = scope_wave(capture, ScopeConns(**{f"ch{output_channel}": "seq_comp"}))
                time_s = wave.time_s
                voltage_v = wave.v["seq_comp"][0]
                low_v, high_v = np.percentile(voltage_v, (5, 95))
                if high_v - low_v < 0.05:
                    raise ValueError(f"{rate_mbd} MBd, {high_symbols} of 8 capture {capture_index} has no swing")
                rises = calc.cross(voltage_v, time_s, float((low_v + high_v) / 2), edge="rising")
                if not len(rises):
                    raise ValueError(f"{rate_mbd} MBd, {high_symbols} of 8 capture {capture_index} has no rise")
                origin_s = calc.xmin(np.abs(rises), rises)
                # Skip the trigger word after idle and the final idle word.
                word_origins = origin_s + 8 * np.arange(1, 30) * unit_interval_s
                # Keep complete words only, in symbol positions from each word origin.
                segments.extend(
                    np.column_stack(((time_s[selected] - origin) / unit_interval_s, voltage_v[selected]))
                    for origin in word_origins
                    if time_s[0] <= origin - 0.2 * unit_interval_s
                    and origin + 8.2 * unit_interval_s <= time_s[-1]
                    and np.any(
                        selected := (time_s >= origin - 0.2 * unit_interval_s)
                        & (time_s <= origin + 8.2 * unit_interval_s)
                    )
                )
            if not segments:
                raise ValueError(f"{rate_mbd} MBd, {high_symbols} of 8 has no complete words")
            handle = ax.plot([], [])[0]
            ax.add_collection(
                LineCollection(segments, colors=(handle.get_color(),), alpha=0.45, linewidths=0.6, rasterized=True)
            )
            ax.set_xlim(-0.2, 8.2)
            ax.set_ylim(-0.85, 0.85)
            ax.set_xticks(range(9))
            ax.set_yticks((-0.5, 0.0, 0.5))
            ax.tick_params(labelbottom=row == 2, labelleft=column == 0)
            if row == 2:
                ax.set_xlabel("Symbol position")
            if column == 0:
                ax.set_ylabel(f"{rate_mbd} MBd\nOutput (V)")
            style_grid(ax)
            ax.minorticks_off()
            ax.grid(False, which="minor")
    fig.suptitle("FPGA sequencer and serializer output: eight-symbol words")
    metadata = {
        "Title": "FPGA sequencer and serializer output: eight-symbol words",
        "Subject": "1..7 high symbols of 8; 320, 960, 1600 MBd; oscilloscope measurement",
        "Keywords": "Oscilloscope measurement",
    }
    return save_figure(fig, output_path, pdf_metadata=metadata)


@mpl.rc_context(PLOT_STYLE)
def plot_serdes_symbol_eye_grid(
    captures_by_rate: Mapping[int, Sequence[Mapping[int, CapturedWaveform]]],
    *,
    marker_channel: int,
    output_channel: int,
    pattern: str,
    output_path: Path,
) -> tuple[Path, ...]:
    """Fold a complete 256-bit serializer pattern into three symbol eyes."""

    rates_mbd = (320, 960, 1600)
    if set(captures_by_rate) != set(rates_mbd) or len(pattern) != 256 or set(pattern) != {"0", "1"}:
        raise ValueError("symbol eye requires three rates and one binary 256-bit pattern")
    words = {(pattern + pattern)[index : index + 8] for index in range(256)}
    if len(words) != 254 or words & {"00000000", "11111111"}:
        raise ValueError("symbol eye pattern must contain every nonconstant eight-bit word")
    anchor_bit = next(
        index for index in range(256) if pattern[index - 1] == "0" and pattern[index : index + 4] == "1111"
    )
    output_path = Path(output_path)
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, sharey=True)
    for ax, rate_mbd in zip(axes, rates_mbd, strict=True):
        captures = captures_by_rate[rate_mbd]
        if not captures:
            raise ValueError(f"{rate_mbd} MBd has no captures")
        unit_interval_s = 1.0 / (rate_mbd * 1e6)
        phases = []
        voltages = []
        eyes = []
        folded_symbols = 0
        for capture_index, capture in enumerate(captures):
            wave = scope_wave(
                capture, ScopeConns(**{f"ch{marker_channel}": "seq_init", f"ch{output_channel}": "seq_comp"})
            )
            time_s = wave.time_s
            marker_v, output_v = wave.v["seq_init"][0], wave.v["seq_comp"][0]
            marker_low, marker_high = np.percentile(marker_v, (0.1, 99.9))
            output_low, output_high = np.percentile(output_v, (5, 95))
            if marker_high - marker_low < 0.05 or output_high - output_low < 0.05:
                raise ValueError(f"{rate_mbd} MBd capture {capture_index} lacks a valid swing")
            marker_edges = calc.cross(marker_v, time_s, float((marker_low + marker_high) / 2), edge="rising")
            output_edges = calc.cross(output_v, time_s, float((output_low + output_high) / 2), edge="rising")
            if not len(marker_edges) or not len(output_edges):
                raise ValueError(f"{rate_mbd} MBd capture {capture_index} lacks a trigger or output rise")
            marker_origin_s = calc.xmin(np.abs(marker_edges), marker_edges)
            anchor_expected_s = marker_origin_s + anchor_bit * unit_interval_s
            anchor_edge_s = calc.xmin(np.abs(output_edges - anchor_expected_s), output_edges)
            if abs(anchor_edge_s - anchor_expected_s) > unit_interval_s:
                raise ValueError(f"{rate_mbd} MBd capture {capture_index} cannot align the output word")
            output_origin_s = anchor_edge_s - anchor_bit * unit_interval_s
            start_s = output_origin_s - 0.5 * unit_interval_s
            stop_s = start_s + (len(pattern) + 1) * unit_interval_s
            eye = calc.eyeDiagram(
                output_v, start_s, stop_s, 2 * unit_interval_s, axis=time_s, trigger_period=unit_interval_s
            )
            separators = np.flatnonzero(np.isnan(eye[:, 0]))
            # The acquisition edges and final trigger can leave incomplete windows.
            for first, last in zip(np.r_[0, separators + 1], np.r_[separators, len(eye)], strict=True):
                trace = eye[first:last]
                if (
                    not len(trace)
                    or not np.isclose(trace[0, 0], 0, atol=1e-9 * unit_interval_s, rtol=0)
                    or not np.isclose(trace[-1, 0], 2 * unit_interval_s, atol=1e-9 * unit_interval_s, rtol=0)
                ):
                    continue
                eyes.append(trace)
                phases.append(trace[:, 0] / unit_interval_s - 0.5)
                voltages.append(trace[:, 1])
                folded_symbols += 1
        if not eyes:
            raise ValueError(f"{rate_mbd} MBd captures contain no complete symbol eyes")
        folded = np.vstack([part for eye in eyes for part in (eye, np.full((1, 2), np.nan))][:-1])
        samples = np.concatenate(voltages)
        low_v, high_v = np.percentile(samples, (5, 95))
        opening_v = calc.eyeHeightAtXY(folded, unit_interval_s, float((low_v + high_v) / 2))
        ax.hist2d(
            np.concatenate(phases),
            samples,
            bins=(140, 160),
            range=((-0.5, 1.5), (-0.8, 0.8)),
            weights=np.full(sum(map(len, phases)), 1 / folded_symbols),
            norm=LogNorm(vmin=1 / folded_symbols),
            cmap=DENSITY_COLOR_MAP,
        )
        ax.set_xlim(-0.5, 1.5)
        ax.set_ylim(-0.8, 0.8)
        ax.set_ylabel(f"{rate_mbd} MBd\nOutput (V)")
        ax.set_title(f"{folded_symbols:,} symbols; geometric center eye height: {opening_v * 1e3:.0f} mV")
        style_grid(ax)
        ax.minorticks_off()
        ax.grid(False, which="minor")
    axes[-1].set_xlabel("Time from symbol boundary (UI)")
    fig.suptitle("FPGA sequencer and serializer output: all 254 nonconstant eight-bit contexts")
    metadata = {
        "Title": "FPGA sequencer and serializer output: all 254 nonconstant eight-bit contexts",
        "Subject": "256-bit pattern excluding constant words; 320, 960, 1600 MBd; oscilloscope measurement",
        "Keywords": "Oscilloscope measurement",
    }
    return save_figure(fig, output_path, pdf_metadata=metadata)


@mpl.rc_context(PLOT_STYLE)
def plot_spectrum(
    scopes: Sequence[AnalysisScope],
    *,
    output_path: Path,
    title: str,
    signals: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Overlay the amplitude spectral densities of selected traces of one or more scope captures.

    ``signals`` maps a trace name to its legend label; by default every trace
    of the first capture is drawn for every capture. Traces are grouped by
    signal, then capture. Each legend entry gives the capture's sample rate,
    sample count, and bandwidth, its name, and the trace label when several
    traces are drawn. In the color of each
    capture's first trace, a labeled dotted line marks its -3 dB acquisition
    bandwidth and a labeled dashed line its Nyquist frequency. A lower panel
    steps each trace's integrated RMS across every decade up to that bandwidth,
    with an inset of each trace's total over that band.
    """

    if not scopes:
        raise ValueError("spectrum plots show at least one scope capture")
    selected = signals if signals is not None else {name: name for name in scopes[0].spectrum_v_per_sqrt_hz}
    fig, (ax, ax_decade) = plt.subplots(2, 1, sharex=True, height_ratios=(3.0, 1.0))
    # Group traces by signal, then capture, so each signal's captures sit
    # together in the legend; each capture's markers take its first color.
    capture_colors = {}
    decade_rows = []
    for name, label in selected.items():
        for index, scope in enumerate(scopes):
            positive = scope.spectrum_frequency_hz > 0.0
            capture = (
                f"{scope.sample_rate_hz / 1e6:g} MS/s, {len(scope.wave.time_s) / 1e6:g} Msamples, "
                f"{scope.bandwidth_hz / 1e6:g} MHz BW, {scope.name}"
            )
            (line,) = ax.loglog(
                scope.spectrum_frequency_hz[positive],
                scope.spectrum_v_per_sqrt_hz[name][positive] * 1e9,
                label=capture if len(selected) == 1 else f"{capture}, {label}",
            )
            capture_colors.setdefault(index, line.get_color())
            decade_rows.append((line.get_color(), scope, name))
    # Dotted at the -3 dB acquisition bandwidth, dashed at the Nyquist frequency.
    for index, scope in enumerate(scopes):
        for frequency_hz, linestyle, marker_label, side in (
            (scope.bandwidth_hz, ":", r"$f_\mathrm{BW}$", "right"),
            (scope.sample_rate_hz / 2.0, "--", r"$f_\mathrm{N}$", "left"),
        ):
            ax.axvline(frequency_hz, color=capture_colors[index], linestyle=linestyle)
            ax.text(
                frequency_hz,
                0.98,
                marker_label,
                transform=ax.get_xaxis_transform(),
                rotation=90,
                ha=side,
                va="top",
                fontsize=mpl.rcParams["legend.fontsize"],
                bbox={"boxstyle": "round,pad=0.2", "facecolor": LEGEND_FACE_COLOR, "edgecolor": capture_colors[index]},
            )
    # Below: each trace's RMS in every decade up to the acquisition bandwidth,
    # drawn as a step across the band in the trace's color.
    for color, scope, name in decade_rows:
        ax_decade.stairs(scope.decade_rms_v[name] * 1e6, scope.decade_edges_hz, color=color, baseline=None)
    # Log steps keep small decades visible next to a dominant one; plain labels.
    ax_decade.set_yscale("log")
    ax_decade.yaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
    ax_decade.yaxis.set_minor_formatter(StrMethodFormatter(""))
    ax_decade.set_ylim(*DECADE_RMS_LIMITS_UV)
    ax_decade.set_ylabel("Integrated RMS noise\n(µV/decade)")
    # Inset: each trace's total from its lowest bin to the acquisition bandwidth.
    style_info_box(
        ax_decade,
        (
            "In-band total",
            *(f"{scope.band_rms_v[name] * 1e6:.1f} µV RMS" for _color, scope, name in decade_rows),
        ),
        location="lower right",
        line_colors=(mpl.rcParams["text.color"], *(color for color, _scope, _name in decade_rows)),
    )
    ax_decade.set_xlabel("Frequency (Hz)")
    style_grid(ax_decade)
    ax.set_ylabel("Amplitude spectral density (nV/√Hz)")
    ax.set_ylim(*SPECTRAL_DENSITY_LIMITS_NV)
    ax.legend()
    style_grid(ax)
    fig.suptitle(title)
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_histogram(
    scope: AnalysisScope,
    *,
    output_path: Path,
    title: str,
    signals: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Plot the sample distributions of selected scope traces about their means.

    ``signals`` maps a trace name to its legend label; by default every trace
    is drawn. Each histogram is overlaid with a Gaussian of the trace's AC RMS.
    """

    selected = signals if signals is not None else {name: name for name in scope.wave.v}
    if not selected:
        raise ValueError("histogram plots show at least one signal")
    fig, ax = plt.subplots()
    for name, label in selected.items():
        centered_uv = (scope.wave.v[name][0] - scope.mean_v[name]) * 1e6
        sigma_uv = scope.ac_rms_v[name] * 1e6
        x_uv = np.linspace(centered_uv.min(), centered_uv.max(), 1001)
        # The Gaussian takes the next cycle color; its histogram reuses it.
        (gaussian,) = ax.plot(
            x_uv,
            np.exp(-0.5 * (x_uv / sigma_uv) ** 2) / (sigma_uv * np.sqrt(2.0 * np.pi)),
            linestyle=":",
            label=f"{label} Gaussian",
        )
        ax.hist(
            centered_uv,
            bins=120,
            density=True,
            histtype="step",
            color=gaussian.get_color(),
            label=f"{label} (σ = {sigma_uv:.1f} µV)",
        )
    ax.set_xlabel("Deviation from mean (µV)")
    ax.set_ylabel("Density (µV⁻¹)")
    ax.legend(loc="upper left")
    style_grid(ax)
    fig.suptitle(title)
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_fastrx_scope_comparison(
    msmt: MeasAdc,
    analysis: AnalysisAdcScopeBits,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot CH2--CH4 and aligned Scope/FastRX decision streams."""

    wave = msmt.wave
    if wave is None:
        raise ValueError("scope/FastRX comparison plot requires a captured scope waveform")
    params = msmt.param.tb
    decision_period_s = 8.0 / float(params.symbol_rate)
    edge_times_s = analysis.comp_edge_times_s
    sample_times_s = analysis.sample_times_s
    decision_end_times_s = np.concatenate((edge_times_s[1:], [edge_times_s[-1] + decision_period_s]))
    decision_widths_s = decision_end_times_s - edge_times_s

    time_s = wave.time_s
    scale, unit = style_time_units(time_s)
    scaled_time = time_s * scale
    scaled_edges = edge_times_s * scale
    scaled_ends = decision_end_times_s * scale
    scaled_widths = decision_widths_s * scale
    scaled_samples = sample_times_s * scale
    display_start_s = max(float(time_s[0]), float(edge_times_s[0] - 4.0 * decision_period_s))
    display_end_s = min(float(time_s[-1]), float(decision_end_times_s[-1]))

    fig, axes = plt.subplots(
        4,
        1,
        sharex=True,
        gridspec_kw={"height_ratios": (1.0, 1.0, 1.35, 1.25)},
    )
    waveform_rows = (
        ("COMP", wave.v["seq_comp"][0]),
        ("LOGIC", wave.v["seq_logic"][0]),
        ("COMP_OUT", wave.v["comp_out"][0]),
    )
    for ax, (label, values), color in zip(axes[:3], waveform_rows, CURVE_COLORS, strict=False):
        ax.plot(scaled_time, values, color=color)
        for edge in scaled_edges:
            ax.axvline(edge, color=SPINE_COLOR, alpha=0.18)
        ax.set_ylabel(f"{label} (V)")
        style_grid(ax)

    axes[2].scatter(
        scaled_samples,
        analysis.sample_values_v,
        marker="o",
        color=CURVE_COLORS[3],
        edgecolor=PLOT_FACE_COLOR,
        linewidth=0.5,
        zorder=5,
        label="Scope decode sample",
    )
    axes[2].legend()

    scope_values = analysis.scope_bits.astype(np.uint8)
    fastrx_values = analysis.fastrx_bits.astype(np.uint8)
    mismatches = analysis.mismatch_mask
    decision_ax = axes[3]
    for decision_index, (start, end, width) in enumerate(zip(scaled_edges, scaled_ends, scaled_widths, strict=True)):
        for y, values in ((1.0, scope_values), (0.0, fastrx_values)):
            bit = int(values[decision_index])
            decision_ax.barh(
                y,
                width,
                left=start,
                height=0.56,
                align="center",
                color=NORD_GREEN if bit else NORD_BLUE,
                edgecolor=NORD_RED if mismatches[decision_index] else PLOT_FACE_COLOR,
                linewidth=1.5 if mismatches[decision_index] else 0.8,
            )
            decision_ax.text(
                start + width / 2.0,
                y,
                str(bit),
                ha="center",
                va="center",
                fontweight="bold",
            )
    decision_ax.set_yticks((1.0, 0.0), labels=("Scope decode", "FastRX decode"))
    decision_ax.set_ylim(-0.6, 1.6)
    decision_ax.set_ylabel("Decision stream")
    decision_ax.set_xlabel(f"Time ({unit})")
    decision_ax.set_title("Decoded decision streams")
    style_grid(decision_ax)

    axes[0].set_xlim(display_start_s * scale, display_end_s * scale)
    setup_lines = (
        *(line for line in style_measurement_text(msmt) if line.startswith("ADC:")),
        f"Symbol rate: {float(params.symbol_rate) / 1e6:g} MBd",
        f"Sequence: {len(params.seq_comp_pattern)} symbols",
    )
    style_info_box(axes[0], setup_lines)
    fig.suptitle("ADC scope and FastRX decision comparison")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_offset_noise(
    msmt_list: Sequence[comp.AnalysisDecisions],
    analysis: comp.AnalysisOffsetNoise,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot comparator decision probability versus differential input."""

    fig, ax = plt.subplots()
    ax.plot(
        analysis.vin_diff_v * 1e3,
        analysis.decision_probability,
        marker="o",
        color=CURVE_COLORS[0],
        label="Measured decisions",
    )
    ax.axhline(0.5, color=SPINE_COLOR)
    if np.isfinite(analysis.offset_v):
        ax.axvline(
            analysis.offset_v * 1e3,
            color=CURVE_COLORS[1],
            linestyle="--",
            label="50% threshold",
        )
    ax.set_xlabel("Differential input (mV)")
    ax.set_ylabel("Decision probability")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Comparator offset and input-referred noise")
    style_grid(ax)
    ax.legend()
    style_info_box(ax, style_measurement_group_text(msmt_list), location="lower right")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_sampling_campaign(
    msmt_list2d: Sequence[Sequence[comp.AnalysisDecisions]],
    analysis_list: Sequence[comp.AnalysisOffsetNoise],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one ADC's matched track/ hold curves over VDAC coupling."""

    # Show 0-25 mV by default, widened so that every swept input stays visible.
    swept_mv = np.concatenate([analysis.vin_diff_v for analysis in analysis_list]) * 1e3
    input_error_minimum_mv = min(0.0, float(calc.ymin(swept_mv)))
    input_error_maximum_mv = max(25.0, float(calc.ymax(swept_mv)))
    grouped_results = {
        (float(group[0].param.requested_dac_rail_percent), group[0].param.sampling_mode): (
            group,
            analysis,
        )
        for group, analysis in zip(msmt_list2d, analysis_list, strict=True)
    }
    coupling_percentages = (0.0, 25.0, 50.0, 75.0, 100.0)
    fig, (curve_ax, violin_ax) = plt.subplots(1, 2)
    coupling_colors = tuple(
        SPECTRUM_COLOR_MAP(index / (len(coupling_percentages) - 1)) for index in range(len(coupling_percentages))
    )
    mode_offsets = {"track": -2.6, "hold": 2.6}
    mode_linestyles = {"track": "-", "hold": "--"}
    mode_markers = {"track": "o", "hold": "s"}
    mode_hatches = {"track": None, "hold": "///"}
    for coupling_index, coupling_percent_p in enumerate(coupling_percentages):
        coupling_percent_n = 100.0 - coupling_percent_p
        for mode in ("track", "hold"):
            _group, analysis = grouped_results[(coupling_percent_p, mode)]
            threshold_mv = analysis.offset_v * 1e3
            noise_mv = analysis.noise_sigma_v * 1e3
            color = coupling_colors[coupling_index]
            curve_label = f"P/N = {coupling_percent_p:g}/{coupling_percent_n:g}%" if mode == "track" else None
            curve_ax.scatter(
                analysis.vin_diff_v * 1e3,
                analysis.decision_probability,
                color=color,
                marker=mode_markers[mode],
                edgecolors="none",
                zorder=2,
            )
            fit_input_v = np.linspace(
                float(calc.ymin(analysis.vin_diff_v)),
                float(calc.ymax(analysis.vin_diff_v)),
                1001,
            )
            fit_probability = ndtr(
                analysis.decision_polarity * (fit_input_v - analysis.offset_v) / analysis.noise_sigma_v
            )
            curve_ax.plot(
                fit_input_v * 1e3,
                fit_probability,
                color=color,
                linestyle=mode_linestyles[mode],
                label=curve_label,
                zorder=3,
            )

            distribution_mv = np.linspace(
                threshold_mv - 4.0 * noise_mv,
                threshold_mv + 4.0 * noise_mv,
                401,
            )
            density = np.exp(-0.5 * ((distribution_mv - threshold_mv) / noise_mv) ** 2)
            violin_center = coupling_percent_p + mode_offsets[mode]
            violin_half_width = 2.15 * density
            violin_ax.fill_betweenx(
                distribution_mv,
                violin_center - violin_half_width,
                violin_center + violin_half_width,
                color=color,
                linewidth=0.8,
                edgecolor=color,
                hatch=mode_hatches[mode],
            )
            violin_ax.plot(
                violin_center,
                threshold_mv,
                marker=mode_markers[mode],
                color=color,
            )

    curve_ax.axhline(0.5, color=SPINE_COLOR)
    curve_ax.set_xlim(input_error_minimum_mv, input_error_maximum_mv)
    curve_ax.set_xlabel("Differential input (mV)")
    curve_ax.set_ylabel("Decision probability")
    curve_ax.set_ylim(-0.02, 1.02)
    curve_ax.set_title("Comparator S-curves (CDF)")
    curve_ax.legend(title="VDAC coupling")

    violin_ax.set_xlim(-8.0, 108.0)
    violin_ax.set_ylim(input_error_minimum_mv, input_error_maximum_mv)
    violin_ax.set_xticks(
        coupling_percentages,
        [f"{value:g}/{100.0 - value:g}" for value in coupling_percentages],
    )
    violin_ax.set_xlabel("VDAC coupling (P/N % of VDD_DAC)")
    violin_ax.set_ylabel("Input error (mV)")
    violin_ax.set_title("Gaussian fit of μ (threshold) and σ (noise)")
    violin_ax.legend(
        handles=(
            Patch(facecolor=LEGEND_FACE_COLOR, edgecolor=SPINE_COLOR, label="Track"),
            Patch(facecolor=LEGEND_FACE_COLOR, edgecolor=SPINE_COLOR, hatch="///", label="Hold"),
        ),
    )

    for ax in (curve_ax, violin_ax):
        style_grid(ax)
    style_info_box(
        curve_ax,
        style_measurement_group_text(tuple(msmt for group in msmt_list2d for msmt in group)),
    )
    fig.suptitle("Comparator threshold and input-referred noise versus VDAC coupling")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_common_mode_campaign(
    msmt_list: Sequence[comp.AnalysisDecisions],
    offsets: Sequence[comp.AnalysisOffsetNoise],
    common_mode: comp.AnalysisCommonMode,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one ADC's comparator response over every measured common-mode input."""

    ordered = sorted(offsets, key=lambda analysis: analysis.vin_cm_v)
    if not np.allclose([analysis.vin_cm_v for analysis in ordered], common_mode.vin_cm_v):
        raise ValueError("comparator offsets must align with the common-mode result")
    common_modes_v = [analysis.vin_cm_v for analysis in ordered]
    swept_mv = np.concatenate([analysis.vin_diff_v for analysis in ordered]) * 1e3
    # Show 0-25 mV by default, widened so that every swept input stays visible.
    input_error_minimum_mv = min(0.0, float(calc.ymin(swept_mv)))
    input_error_maximum_mv = max(25.0, float(calc.ymax(swept_mv)))
    common_mode_span_v = max(common_modes_v) - min(common_modes_v)
    fig, (curve_ax, violin_ax) = plt.subplots(1, 2)
    for analysis, validity in zip(ordered, common_mode.validity, strict=True):
        common_mode_v = analysis.vin_cm_v
        threshold_mv = analysis.offset_v * 1e3
        noise_mv = analysis.noise_sigma_v * 1e3
        gradient_position = (common_mode_v - min(common_modes_v)) / common_mode_span_v if common_mode_span_v else 0.0
        color = SPECTRUM_COLOR_MAP(float(gradient_position))

        curve_ax.scatter(
            analysis.vin_diff_v * 1e3,
            analysis.decision_probability,
            color=color,
            edgecolors="none",
            zorder=2,
        )

        valid_fit = validity == "valid" and np.isfinite(threshold_mv) and np.isfinite(noise_mv) and noise_mv > 0.0
        if valid_fit:
            fit_input_v = np.linspace(
                float(calc.ymin(analysis.vin_diff_v)),
                float(calc.ymax(analysis.vin_diff_v)),
                1001,
            )
            fit_probability = ndtr(
                analysis.decision_polarity * (fit_input_v - analysis.offset_v) / analysis.noise_sigma_v
            )
            curve_ax.plot(
                fit_input_v * 1e3,
                fit_probability,
                color=color,
                label=f"Vin_cm = {common_mode_v:.3g} V",
                zorder=3,
            )
            distribution_mv = np.linspace(
                threshold_mv - 4.0 * noise_mv,
                threshold_mv + 4.0 * noise_mv,
                401,
            )
            density = np.exp(-0.5 * ((distribution_mv - threshold_mv) / noise_mv) ** 2)
            violin_half_width_v = 0.035 * density
            violin_ax.fill_betweenx(
                distribution_mv,
                common_mode_v - violin_half_width_v,
                common_mode_v + violin_half_width_v,
                color=color,
                linewidth=0.8,
                edgecolor=color,
            )
            violin_ax.plot(common_mode_v, threshold_mv, marker="o", color=color)
        else:
            curve_ax.plot(
                analysis.vin_diff_v * 1e3,
                analysis.decision_probability,
                color=color,
                label=f"Vin_cm = {common_mode_v:.3g} V ({validity})",
                zorder=3,
            )

    curve_ax.axhline(0.5, color=SPINE_COLOR)
    curve_ax.set_xlim(input_error_minimum_mv, input_error_maximum_mv)
    curve_ax.set_ylim(-0.02, 1.02)
    curve_ax.set_xlabel("Differential input (mV)")
    curve_ax.set_ylabel("Decision probability")
    curve_ax.set_title("Comparator S-curve (CDF)")
    curve_ax.legend(loc="lower right")

    violin_ax.set_xlim(
        min(common_modes_v) - 0.05,
        max(common_modes_v) + 0.05,
    )
    violin_ax.set_ylim(input_error_minimum_mv, input_error_maximum_mv)
    violin_ax.set_xticks(common_modes_v, [f"{value:.1f}" for value in common_modes_v])
    violin_ax.set_xlabel("Common-mode input (V)")
    violin_ax.set_ylabel("Input error (mV)")
    violin_ax.set_title("Gaussian fit of μ (threshold) and σ (noise)")

    for ax in (curve_ax, violin_ax):
        style_grid(ax)
    style_info_box(curve_ax, style_measurement_group_text(msmt_list))
    fig.suptitle("Comparator threshold and input-referred noise versus common mode")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_cdac_cap_mismatch(
    msmt_list: Sequence[MeasCdac],
    analysis: AnalysisCdacCapMismatch,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one ADC's normalized A-to-B main/diff weights and diagnostics."""

    stages = np.arange(analysis.effective_fraction.shape[1])
    expected_effective = msmt_list[0].expected_effective_fraction
    if any(not np.array_equal(msmt.expected_effective_fraction, expected_effective) for msmt in msmt_list):
        raise ValueError("CDAC measurements contain inconsistent ideal/PEX expectations")
    fig, axes_grid = plt.subplots(2, 3, sharex=True)
    axes = axes_grid.ravel()
    for side, label, color in ((0, "P", CURVE_COLORS[0]), (1, "N", CURVE_COLORS[1])):
        axes[0].plot(
            stages,
            analysis.effective_fraction[side],
            "o-",
            color=color,
            label=label,
        )
        axes[1].plot(
            stages,
            analysis.effective_fraction[side] - expected_effective,
            "o-",
            color=color,
            label=label,
        )
        axes[3].plot(stages, analysis.main_fraction[side], "o-", color=color, label=f"{label} main")
        axes[3].plot(
            stages,
            analysis.diff_fraction[side],
            "s--",
            color=color,
            label=f"{label} diff",
        )
        axes[4].plot(
            stages,
            analysis.direction_bias[side, :, 0],
            marker="o",
            linestyle="-" if side == 0 else "--",
            color=color,
            label=f"{label}, main+diff",
        )
        axes[4].plot(
            stages,
            analysis.direction_bias[side, :, 1],
            marker="s",
            linestyle="-" if side == 0 else "--",
            color=color,
            label=f"{label}, main−diff",
        )
        axes[5].plot(
            stages,
            2.0 * analysis.diff_fraction[side],
            "o-",
            color=color,
            label=label,
        )
    axes[0].plot(stages, expected_effective, "k--", label="Ideal/PEX")
    axes[2].plot(
        stages,
        analysis.effective_fraction[0] - analysis.effective_fraction[1],
        "o-",
        color=NORD_PURPLE,
        label="P−N",
    )
    panel_titles = (
        "Effective fraction",
        "Residual from ideal/PEX",
        "P−N effective asymmetry",
        "Main and differential fractions",
        "Switching-direction bias",
        "Differential-capacitor separation",
    )
    ylabels = ("C/Ctotal", "Residual", "P−N", "C/Ctotal", "Half-difference", "Separation")
    tick_positions = stages[::3]
    tick_labels = tuple(f"C{stage}" for stage in tick_positions)
    for ax, title, ylabel in zip(axes, panel_titles, ylabels, strict=True):
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(tick_positions, tick_labels)
        style_grid(ax)
        ax.legend()
    style_info_box(axes[2], style_measurement_group_text(msmt_list), location="lower right")
    fig.supxlabel("Conversion stage")
    fig.suptitle("A-to-B CDAC capacitance")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_cdac_cap_mismatch_comparison(
    msmt_list2d: Sequence[Sequence[MeasCdac]],
    analysis_list: Sequence[AnalysisCdacCapMismatch],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare normalized A-to-B CDAC extraction across ADC channels."""

    fig, axes_grid = plt.subplots(2, 2, sharex=True)
    axes = axes_grid.ravel()
    aligned = sorted(zip(msmt_list2d, analysis_list, strict=True), key=lambda item: item[1].index or 0)
    stages = np.arange(analysis_list[0].effective_fraction.shape[1])
    for group, analysis in aligned:
        expected = group[0].expected_effective_fraction
        effective_mean = (analysis.effective_fraction[0] + analysis.effective_fraction[1]) / 2.0
        diffcap_separation_mean = analysis.diff_fraction[0] + analysis.diff_fraction[1]
        label = f"ADC{analysis.index:02d}" if analysis.index is not None else "Nominal"
        color = CURVE_COLORS[(analysis.index or 0) % len(CURVE_COLORS)]
        axes[0].plot(stages, effective_mean, "o-", color=color, label=label)
        axes[1].plot(stages, effective_mean - expected, "o-", color=color, label=label)
        axes[2].plot(
            stages,
            analysis.effective_fraction[0] - analysis.effective_fraction[1],
            "o-",
            color=color,
            label=label,
        )
        axes[3].plot(stages, diffcap_separation_mean, "o-", color=color, label=label)

    panel_titles = (
        "Mean P/N effective fraction",
        "Residual from ideal/PEX",
        "P−N effective asymmetry",
        "Mean P/N diffcap separation",
    )
    ylabels = ("Fraction", "Residual", "Asymmetry", "Separation")
    tick_positions = stages[::3]
    tick_labels = tuple(f"C{stage}" for stage in tick_positions)
    for ax, title, ylabel in zip(axes, panel_titles, ylabels, strict=True):
        ax.axhline(0.0, color=SPINE_COLOR)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks(tick_positions, tick_labels)
        style_grid(ax)
    axes[0].legend()
    style_info_box(
        axes[3],
        style_measurement_group_text(tuple(msmt for group in msmt_list2d for msmt in group)),
        location="lower right",
    )
    fig.supxlabel("Conversion stage")
    fig.suptitle("A-to-B CDAC comparison")
    return save_figure(fig, output_path)
