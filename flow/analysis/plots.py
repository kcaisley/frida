"""Plots of typed FRIDA measurements and analysis results."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Literal, cast

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from basil.HL.tektronix_oscilloscope import CapturedWaveform
from cycler import cycler
from matplotlib.artist import Artist
from matplotlib.cm import ScalarMappable
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredOffsetbox, DrawingArea, HPacker, TextArea, VPacker
from matplotlib.patches import Patch
from matplotlib.ticker import AutoMinorLocator, MaxNLocator, MultipleLocator, NullLocator, StrMethodFormatter
from scipy.special import ndtr

from flow.adc.sequences import AdcSequence
from flow.analysis import calc
from flow.analysis.types import (
    Analysis,
    AnalysisAdcCalibration,
    AnalysisAdcCdacSettling,
    AnalysisAdcCodeDensityNonlinearity,
    AnalysisAdcCodeDistribution,
    AnalysisAdcComparatorEdgeEye,
    AnalysisAdcComparatorResponse,
    AnalysisAdcCompOutEdgeEye,
    AnalysisAdcDecisionPaths,
    AnalysisAdcDynamic,
    AnalysisAdcEndpointNonlinearity,
    AnalysisAdcNoise,
    AnalysisAdcOperatingConditions,
    AnalysisAdcPower,
    AnalysisAdcPowerWaveform,
    AnalysisAdcRamp,
    AnalysisAdcSamplingNoise,
    AnalysisAdcScopeBits,
    AnalysisAdcTransfer,
    AnalysisCdacCapMismatch,
    AnalysisCompCandidate,
    AnalysisCompCommonMode,
    AnalysisCompOffsetNoise,
    AnalysisCompPower,
    AnalysisCompTiming,
    AnalysisDiffampNoise,
    Meas,
    MeasAdc,
    MeasCdac,
    MeasComp,
    Wave,
)
from flow.scans.scope import scope_wave

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


def style_adc_code_dispersion_lsb(value: float, *, single_code: bool) -> str:
    """Format unresolved single-code dispersion as a one-LSB upper bound."""

    if single_code:
        return "<1.0"
    rounded = f"{value:.1f}"
    return f"{value:.2g}" if rounded == "0.0" else rounded


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


def style_instance_text(analysis: Analysis) -> tuple[str, ...]:
    """Name the ADC channel or Monte Carlo iteration a result belongs to."""

    return () if analysis.index is None else (f"ADC: {analysis.index:02d}",)


def style_measurement_group_text(msmt_list: Sequence[Meas]) -> tuple[str, ...]:
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
def plot_adc_redundancy(
    margins_percent: Sequence[float] | Mapping[str, Sequence[float]], *, output_path: Path
) -> tuple[Path, ...]:
    """Plot one SAR correction-margin sequence or compare several by name."""

    series: Mapping[str, Sequence[float]]
    if isinstance(margins_percent, Mapping):
        series = cast("Mapping[str, Sequence[float]]", margins_percent)
    else:
        series = {"Error tolerance": margins_percent}
    if not series:
        raise ValueError("at least one redundancy sequence is required")
    fig, ax = plt.subplots()
    for label, margins in series.items():
        ax.plot(np.arange(len(margins)), margins, "o-", label=label)
    ax.axhline(0.0, color=SPINE_COLOR)
    ax.set_xlabel("Conversion stage")
    ax.set_ylabel("Error tolerance (%)")
    stage_count = max(map(len, series.values()))
    ax.set_xticks(np.arange(0, stage_count, 1 if stage_count <= 12 else 2))
    if stage_count > 12:
        ax.xaxis.set_minor_locator(MultipleLocator(1))
    if len(series) > 1:
        ax.legend()
    style_grid(ax)
    fig.suptitle("SAR redundancy by conversion stage")
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
    Time is shown relative to ``time_origin_s``.
    """

    selected = signals if signals is not None else {name: name for name in wave.v}
    if not 1 <= len(selected) <= 4:
        raise ValueError("waveform plots show one to four signals")
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
        ax.set_ylabel(f"{label} ({signal_unit})")
        style_grid(ax)
    axes[-1].set_xlabel(f"Time ({unit})")
    style_info_box(axes[0], tuple(setup_lines))
    fig.suptitle(title)
    return save_figure(fig, output_path)


def style_measurement_text(msmt: Meas) -> tuple[str, ...]:
    """Format concise plot context persisted with one measurement."""

    tb = msmt.tb
    lines: tuple[str, ...] = ()
    adc_index = getattr(msmt.param, "observed_adc", None)
    if adc_index is not None:
        lines += (f"ADC: {adc_index:02d}",)
    elif msmt.info.backend != "physical" and isinstance(msmt, MeasAdc):
        lines += (f"Source: {msmt.info.backend.upper()}",)
    board_id = getattr(msmt.param, "board_id", None)
    if board_id is not None:
        lines += (f"Board: {board_id:02d}",)
    for field_name, label in (("vin_cm", "Vcm"), ("vin_diff", "Vdiff")):
        dc_v = getattr(getattr(tb, field_name, None), "dc", None)
        if dc_v is not None:
            lines += (f"{label}: {float(dc_v) * 1e3:g} mV",)
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
    """Plot XC rail validity and positive SR output histograms at B0..B16."""

    internal = [analysis.internal_response_s[analysis.decision_index == decision] for decision in range(17)]
    output = [analysis.sr_response_s[analysis.decision_index == decision] for decision in range(17)]
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
    ax.set_xlim(-0.7, 16.7)
    ax.set_xticks(range(17))
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
                wave = scope_wave(capture, {output_channel: "SERDES output"})
                time_s = wave.time_s
                voltage_v = wave.v["SERDES output"][0]
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
            wave = scope_wave(capture, {marker_channel: "INIT marker", output_channel: "SERDES output"})
            time_s = wave.time_s
            marker_v, output_v = wave.v["INIT marker"][0], wave.v["SERDES output"][0]
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
def plot_diffamp_noise(
    analysis: AnalysisDiffampNoise,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot differential-amplifier noise distribution and spectrum."""

    centered_mv = analysis.centered_v * 1e3
    noise_rms_mv = analysis.noise_rms_v * 1e3
    gaussian_x_mv = np.linspace(-5.0 * noise_rms_mv, 5.0 * noise_rms_mv, 1001)
    gaussian_density_per_mv = np.exp(-0.5 * (gaussian_x_mv / noise_rms_mv) ** 2) / (noise_rms_mv * np.sqrt(2.0 * np.pi))
    fig, (histogram_ax, spectrum_ax) = plt.subplots(2, 1)
    histogram_ax.hist(
        centered_mv,
        bins=120,
        density=True,
        color=NORD_BLUE,
        edgecolor=PLOT_FACE_COLOR,
        linewidth=0.35,
        label="Measured samples",
    )
    histogram_ax.plot(
        gaussian_x_mv,
        gaussian_density_per_mv,
        color=CURVE_COLORS[1],
        linestyle=":",
        label=(f"Gaussian fit (raw µ = {analysis.mean_v * 1e3:.3f} mV subtracted; σ = {noise_rms_mv:.3f} mV)"),
    )
    histogram_ax.set_xlabel("Differential output noise about its mean (mV)")
    histogram_ax.set_ylabel("Density (mV⁻¹)")
    histogram_ax.legend()

    positive = analysis.spectrum_frequency_hz > 0.0
    spectrum_ax.loglog(
        analysis.spectrum_frequency_hz[positive],
        analysis.spectrum_amplitude_density_v_per_sqrt_hz[positive] * 1e6,
        color=NORD_BLUE,
        label=f"Measured spectrum (integrated RMS = {analysis.integrated_fft_noise_rms_v * 1e3:.3f} mV)",
    )
    spectrum_ax.axvline(
        analysis.measurement_bandwidth_hz,
        color=CURVE_COLORS[1],
        linestyle=":",
        label=f"Measurement bandwidth = {analysis.measurement_bandwidth_hz / 1e6:g} MHz",
    )
    spectrum_ax.set_xlabel("Frequency (Hz)")
    spectrum_ax.set_ylabel("ASD (µV/√Hz)")
    spectrum_ax.legend()
    for ax in (histogram_ax, spectrum_ax):
        style_grid(ax)
    fig.suptitle("Differential-amplifier output noise")
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
def plot_adc_transfer(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcTransfer,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot individual ADC conversions and the mean static transfer."""

    fig, ax = plt.subplots()
    inputs = np.concatenate([msmt.vin_diff_v for msmt in msmt_list])
    dout = np.concatenate([msmt.dout for msmt in msmt_list])
    ax.scatter(inputs * 1e3, dout, label="Conversions")
    ax.errorbar(
        analysis.vin_diff_v * 1e3,
        analysis.mean_dout,
        yerr=analysis.std_dout,
        marker="o",
        capsize=2,
        label="Mean ± 1σ",
    )
    ax.set_xlabel("Differential input (mV)")
    ax.set_ylabel("ADC output (LSB)")
    ax.set_title("ADC static transfer")
    style_grid(ax)
    ax.legend()
    style_info_box(ax, style_measurement_group_text(msmt_list), location="lower right")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_ramp_transfer(
    analyses: Sequence[AnalysisAdcRamp],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot the phase-reconstructed ramp transfer of every decoding of one capture."""

    analysis = analyses[0]
    fig, ax = plt.subplots()
    for curve in analyses:
        ax.plot(
            curve.transfer_vin_diff_v * 1e3,
            curve.transfer_mean_dout,
            label=curve.label,
        )
    ax.set_xlabel("Inferred differential input (mV)")
    ax.set_ylabel("Mean ADC output (LSB)")
    ax.set_title("ADC ramp transfer")
    style_grid(ax)
    ax.legend()
    style_info_box(
        ax,
        (
            *style_instance_text(analysis),
            f"Sample rate: {analysis.sample_rate_hz / 1e6:.6g} MS/s",
            f"Ramp: {analysis.ramp_frequency_hz:.6g} Hz",
        ),
        location="lower right",
    )
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_ramp_histogram(
    analyses: Sequence[AnalysisAdcRamp],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot overlaid code-density histograms of every decoding of one capture."""

    analysis = analyses[0]
    fig, ax = plt.subplots()
    number_bins = 128
    first_code = int(analysis.code[0]) + 1
    last_code = int(analysis.code[-1])
    bin_edges = np.linspace(first_code, last_code, number_bins + 1, dtype=np.int64)
    bin_edges = np.unique(bin_edges)
    for curve, color in zip(analyses, CURVE_COLORS, strict=False):
        average_count = np.asarray([calc.average(curve.count[lower:upper]) for lower, upper in pairwise(bin_edges)])
        ax.stairs(
            average_count,
            bin_edges,
            baseline=0.0,
            fill=False,
            color=color,
            label=curve.label,
        )
    ax.set_xlabel("Output code")
    ax.set_ylabel("Mean samples per code in bin")
    ax.set_title("ADC ramp code density")
    style_grid(ax)
    ax.legend(ncols=2)
    style_info_box(
        ax,
        (
            *style_instance_text(analysis),
            f"Ramp: {analysis.ramp_frequency_hz:.6g} Hz",
        ),
        location="lower right",
    )
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_ramp_weights(
    nominal: AnalysisAdcRamp,
    measured: AnalysisAdcRamp,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare nominal and direction-matched physical decision weights."""

    analysis = nominal
    code_max = len(nominal.code) - 1
    nominal_weights = nominal.weights * code_max / np.sum(nominal.weights)
    measured_weights = measured.weights * code_max / np.sum(measured.weights)
    stages = np.arange(len(nominal_weights) - 1)
    relative_error_percent = 100.0 * (measured_weights[:-1] / nominal_weights[:-1] - 1.0)

    fig, axes = plt.subplots(
        2,
        1,
        sharex=True,
        gridspec_kw={"height_ratios": (2.0, 1.0)},
    )
    axes[0].plot(stages, nominal_weights[:-1], "o-", color=NORD_DARK, label="Ideal")
    axes[0].plot(
        stages,
        measured_weights[:-1],
        "o-",
        color=NORD_BLUE,
        label="Direction-matched measured",
    )
    axes[0].set_yscale("log", base=2)
    axes[0].set_ylabel("Decision weight (LSB)")
    axes[0].legend()
    axes[1].axhline(0.0, color=SPINE_COLOR)
    axes[1].bar(stages, relative_error_percent, color=NORD_BLUE, width=0.7)
    axes[1].set_ylabel("Error (%)")
    axes[1].set_xlabel("Conversion stage")
    axes[1].set_xticks(stages)
    axes[1].set_xticklabels([f"C{stage}" for stage in stages])
    for ax in axes:
        style_grid(ax)
    style_info_box(axes[1], style_instance_text(analysis), location="lower right")
    fig.suptitle("Ideal and extracted ADC decision weights")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_calibration_weights(
    analysis_list: Sequence[AnalysisAdcCalibration],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare any calibration methods against one shared ideal weight set."""

    nominal = analysis_list[0].nominal_weights

    decision = np.arange(len(nominal))
    labels = [f"B{stage}\nC{stage}" for stage in range(len(nominal) - 1)] + [f"B{len(nominal) - 1}\nterminal"]
    fig, axes = plt.subplots(
        2,
        1,
        sharex=True,
        gridspec_kw={"height_ratios": (2.0, 1.0)},
    )
    axes[0].plot(decision, nominal, "o-", color=NORD_DARK, label="Ideal")
    axes[1].axhline(0.0, color=SPINE_COLOR)
    for calibration, color in zip(analysis_list, CURVE_COLORS, strict=False):
        axes[0].plot(
            decision,
            calibration.calibrated_weights,
            "o-",
            color=color,
            label=calibration.label,
        )
        error_percent = 100.0 * (calibration.calibrated_weights / nominal - 1.0)
        axes[1].plot(
            decision,
            error_percent,
            "o-",
            color=color,
            label=calibration.label,
        )
        inferred = ~calibration.measured_weight_mask
        if np.any(inferred):
            axes[0].scatter(
                decision[inferred],
                calibration.calibrated_weights[inferred],
                marker="x",
                color=color,
                zorder=5,
            )
    axes[0].set_yscale("log", base=2)
    axes[0].set_ylabel("BOUT weight (LSB)")
    axes[0].set_title("Ideal and calibrated digital weights")
    axes[1].set_ylabel("Difference from ideal (%)")
    axes[1].set_xlabel("BOUT decision coefficient")
    axes[1].set_xticks(decision)
    axes[1].set_xticklabels(labels)
    axes[0].legend(ncols=2)
    for ax in axes:
        style_grid(ax)
    style_info_box(axes[1], style_instance_text(analysis_list[0]))
    fig.suptitle("ADC digital calibration weights")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_static_nonlinearity(
    msmt: MeasAdc,
    analysis: AnalysisAdcEndpointNonlinearity | AnalysisAdcCodeDensityNonlinearity,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot static ADC DNL and INL from one completed analysis."""

    fig, axes = plt.subplots(2, 1, sharex=True)
    axes[0].plot(analysis.code, analysis.dnl)
    axes[1].plot(analysis.code, analysis.inl)
    axes[0].axhline(0.0, color=SPINE_COLOR)
    axes[0].set_ylabel("DNL (LSB)")
    axes[1].axhline(0.0, color=SPINE_COLOR)
    axes[1].set_ylabel("INL (LSB)")
    axes[1].set_xlabel("Output code")
    for ax in axes:
        style_grid(ax)
    style_info_box(axes[0], style_measurement_text(msmt))
    method = "endpoint" if isinstance(analysis, AnalysisAdcEndpointNonlinearity) else "code-density"
    fig.suptitle(f"ADC {method} nonlinearity")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_ramp_nonlinearity(
    analyses: Sequence[AnalysisAdcRamp],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot overlaid ramp DNL and INL of every decoding of one capture."""

    analysis = analyses[0]
    fig, axes = plt.subplots(2, 1, sharex=True)
    for curve in analyses:
        axes[0].plot(curve.linearity_code, curve.dnl, label=curve.label)
        axes[1].plot(curve.linearity_code, curve.inl, label=curve.label)
    axes[0].axhline(0.0, color=SPINE_COLOR)
    axes[0].set_ylabel("DNL (LSB)")
    axes[1].axhline(0.0, color=SPINE_COLOR)
    axes[1].set_ylabel("INL (LSB)")
    axes[1].set_xlabel("Output code")
    for ax in axes:
        style_grid(ax)
    axes[0].legend()
    style_info_box(
        axes[1],
        (*style_instance_text(analysis), f"Ramp: {analysis.ramp_frequency_hz:.6g} Hz"),
    )
    fig.suptitle("ADC ramp nonlinearity")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_sampling_noise(
    analyses: Sequence[AnalysisAdcSamplingNoise],
    *,
    labels: Sequence[str],
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare mean-centered held voltages using common microvolt bins and axes."""

    if not analyses or len(analyses) != len(labels):
        raise ValueError("sampling noise requires one label per analysis")
    errors_uv = [(item.held_diff_v - calc.average(item.held_diff_v)) * 1e6 for item in analyses]
    limit_uv = max(25.0, np.ceil(max(calc.ymax(np.abs(values)) for values in errors_uv) / 25.0) * 25.0)
    bins_uv = np.arange(-limit_uv, limit_uv + 25.0, 25.0)
    columns = min(4, len(analyses))
    rows = (len(analyses) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, sharex=True, sharey=True, squeeze=False)
    if rows > 2:
        fig.set_size_inches(9.6, 2.7 * rows)
    for index, (analysis, label, error_uv) in enumerate(zip(analyses, labels, errors_uv, strict=True)):
        ax = axes.flat[index]
        ax.hist(
            error_uv,
            bins=bins_uv,
            weights=np.full(len(error_uv), 1.0 / len(error_uv)),
            color=CURVE_COLORS[index % len(CURVE_COLORS)],
            edgecolor=SPINE_COLOR,
            linewidth=0.4,
            alpha=0.85,
        )
        ax.set_title(label, fontsize=9)
        ax.set_xlim(-limit_uv, limit_uv)
        ax.xaxis.set_major_locator(MaxNLocator(5))
        if index + columns >= len(analyses):
            ax.tick_params(labelbottom=True)
        style_grid(ax)
        style_info_box(ax, (f"SD = {analysis.sigma_v * 1e6:.1f} µV", f"N = {len(error_uv)}"))
    for ax in axes.flat[len(analyses) :]:
        ax.set_visible(False)
    fig.supxlabel("VDAC_P − VDAC_N, relative to each design's mean (µV)")
    fig.supylabel("Fraction of conversions per 25 µV bin")
    fig.suptitle("Sampling-level variation · 1 ns after SAMP falls")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_code_distribution(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcCodeDistribution,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot code histograms and standard deviation at static input points."""

    fig, axes = plt.subplots(2, 1)
    for index, vin_diff_v in enumerate(analysis.vin_diff_v):
        active = analysis.count[index] > 0
        axes[0].step(
            analysis.code[active],
            analysis.count[index, active],
            where="mid",
            label=f"{vin_diff_v * 1e3:g} mV",
        )
    axes[0].set_xlabel("Output code")
    axes[0].set_ylabel("Count")
    axes[0].legend(ncols=2)
    axes[1].plot(analysis.vin_diff_v * 1e3, analysis.std_dout, marker="o")
    axes[1].set_xlabel("Differential input (mV)")
    axes[1].set_ylabel("Standard deviation (LSB)")
    for ax in axes:
        style_grid(ax)
    style_info_box(axes[1], style_measurement_group_text(msmt_list))
    fig.suptitle("ADC output-code distribution")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_noise_sweep(
    msmt_list: Sequence[MeasAdc],
    analyses: Sequence[AnalysisAdcNoise],
    *,
    output_path: Path,
    rate_axis: Literal["active", "sampling"] = "active",
    series_labels: Sequence[str] = (),
) -> tuple[Path, ...]:
    """Plot noise, equivalent full-scale SNR, and ENOB on one rate panel.

    Each result is one point. Points are grouped into series by
    ``series_labels`` when given, otherwise by COMP-to-LOGIC timing.
    """

    if not analyses:
        raise ValueError("noise sweep requires at least one result")
    input_lsb_v = analyses[0].input_lsb_v
    if any(not np.isclose(analysis.input_lsb_v, input_lsb_v, rtol=1e-12, atol=0.0) for analysis in analyses):
        raise ValueError("noise sweep results must share one nominal input LSB")
    # The SNR and ENOB axes use a full-scale sine whose peak-to-peak
    # range is the ADC input range represented by all output codes.
    full_scale_rms_lsb = analyses[0].code_max / (2.0 * np.sqrt(2.0))
    noise_rms_lsb = np.asarray([analysis.input_referred_noise_rms_v for analysis in analyses]) / input_lsb_v
    noise_valid = np.asarray([analysis.noise_valid for analysis in analyses])
    rates = np.asarray(
        [
            analysis.sample_rate_hz if rate_axis == "sampling" else analysis.active_conversion_rate_hz
            for analysis in analyses
        ]
    )
    comparator_time_percent = np.asarray([analysis.comparator_time_percent for analysis in analyses])

    fig, ax = plt.subplots(layout="none")
    conversion_rate_msps = rates / 1e6
    if series_labels:
        if len(series_labels) != len(rates):
            raise ValueError("sequence labels must align with noise points")
        labels = tuple(dict.fromkeys(series_labels))
        selections = tuple(np.asarray(series_labels) == label for label in labels)
    else:
        timing_values = np.unique(comparator_time_percent)
        labels = tuple(f"{value:g}%" for value in timing_values)
        selections = tuple(comparator_time_percent == value for value in timing_values)
    colors = tuple(CURVE_COLORS[index % len(CURVE_COLORS)] for index in range(len(labels)))

    for label, selected, color in zip(labels, selections, colors, strict=True):
        # A constant code has no finite noise estimate; it has no point to draw.
        selected = selected & noise_valid
        if not np.any(selected):
            continue
        order = np.argsort(conversion_rate_msps[selected])
        ax.plot(
            conversion_rate_msps[selected][order],
            noise_rms_lsb[selected][order],
            marker="o",
            color=color,
            label=label,
        )
    ax.set_xlabel("Repetition rate (MHz)" if rate_axis == "sampling" else "Conversion rate (MSPS)")
    ax.set_ylabel("Input-referred noise (LSB RMS)")
    ax.invert_yaxis()
    visible_noise = noise_rms_lsb[noise_valid]
    ax.set_ylim(max(9.0, float(calc.ymax(visible_noise)) * 1.05) if len(visible_noise) else 9.0, 0.0)
    rate_limit_msps = max(10.25, float(calc.ymax(conversion_rate_msps)) + 0.25)
    ax.set_xticks(np.arange(0.0, np.floor(rate_limit_msps) + 1.0, 1.0))
    ax.set_xlim(0.0, rate_limit_msps)
    ax.set_xticks(np.arange(0.0, rate_limit_msps + 0.001, 0.25), minor=True)
    ax.set_title(
        "ADC noise performance vs repetition rate"
        if rate_axis == "sampling"
        else "ADC noise performance vs conversion rate"
    )
    ax.tick_params(which="both", right=False)
    style_grid(ax)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(
            ncols=4,
            loc="lower center",
            bbox_to_anchor=(0.5, 1.06),
            fontsize=8,
            title="Sequence" if series_labels else "COMP→LOGIC interval\n(as % of decision cycle)",
        )
    noise_mv_axis = ax.secondary_yaxis(
        "left",
        functions=(
            lambda noise_lsb: np.asarray(noise_lsb) * input_lsb_v * 1e3,
            lambda noise_mv: np.asarray(noise_mv) / (input_lsb_v * 1e3),
        ),
    )
    noise_mv_axis.spines["left"].set_position(("outward", 58))
    noise_mv_axis.set_ylabel("Input-referred noise (mV RMS)")
    noise_mv_axis.tick_params(which="both", left=True, right=False)

    enob_axis = ax.secondary_yaxis(
        "right",
        functions=(
            lambda noise_lsb: (
                (
                    20.0
                    * (
                        np.log10(full_scale_rms_lsb)
                        - np.log10(np.maximum(np.asarray(noise_lsb), np.finfo(np.float64).tiny))
                    )
                    - 1.76
                )
                / 6.02
            ),
            lambda enob_bits: full_scale_rms_lsb * np.power(10.0, -(6.02 * np.asarray(enob_bits) + 1.76) / 20.0),
        ),
    )
    enob_axis.set_ylabel("Noise-equivalent ENOB (bit)")
    enob_ticks = np.arange(-2.0, 17.0)
    enob_noise = full_scale_rms_lsb * np.power(10.0, -(6.02 * enob_ticks + 1.76) / 20.0)
    noise_limit = max(ax.get_ylim())
    enob_axis.set_yticks(enob_ticks[(enob_noise >= 0.07 * noise_limit) & (enob_noise <= noise_limit)])
    enob_axis.tick_params(which="both", left=False, right=True)

    snr_axis = ax.secondary_yaxis(
        "right",
        functions=(
            lambda noise_lsb: (
                20.0
                * (
                    np.log10(full_scale_rms_lsb)
                    - np.log10(np.maximum(np.asarray(noise_lsb), np.finfo(np.float64).tiny))
                )
            ),
            lambda snr_db: full_scale_rms_lsb * np.power(10.0, -np.asarray(snr_db) / 20.0),
        ),
    )
    snr_axis.spines["right"].set_position(("outward", 58))
    snr_axis.set_ylabel("SNR (dB)")
    snr_ticks = np.arange(-10.0, 101.0, 5.0)
    snr_noise = full_scale_rms_lsb * np.power(10.0, -snr_ticks / 20.0)
    snr_axis.set_yticks(snr_ticks[(snr_noise >= 0.07 * noise_limit) & (snr_noise <= noise_limit)])
    snr_axis.tick_params(which="both", left=False, right=True)

    decision_time_axis = ax.twiny()
    decision_time_axis.set_xlim(ax.get_xlim())
    decision_time_axis.xaxis.set_ticks_position("bottom")
    decision_time_axis.xaxis.set_label_position("bottom")
    decision_time_axis.spines["bottom"].set_position(("outward", 38))
    decision_time_axis.spines["top"].set_visible(False)
    decision_time_axis.set_xlabel("Repetition interval (ns)" if rate_axis == "sampling" else "Conversion interval (ns)")
    labeled_rates_msps = np.arange(1.0, np.floor(rate_limit_msps) + 1.0)
    decision_cycle_ns = 1000.0 / labeled_rates_msps
    decision_time_axis.set_xticks(labeled_rates_msps)
    decision_time_axis.set_xticklabels(tuple(f"{interval:.3g}" for interval in decision_cycle_ns))
    decision_time_axis.tick_params(
        which="both",
        top=False,
        bottom=True,
    )
    # Reserve space for both outer noise axes and the second bottom time axis.
    fig.subplots_adjust(left=0.20, right=0.80, bottom=0.23, top=0.72)
    style_info_box(ax, style_measurement_group_text(msmt_list), location="lower left")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_noise_distribution_sweep(
    msmt_list: Sequence[MeasAdc],
    analyses: Sequence[AnalysisAdcNoise],
    *,
    output_path: Path,
    rate_axis: Literal["active", "sampling"] = "active",
) -> tuple[Path, ...]:
    """Plot left-facing output-code histograms along the conversion-rate axis."""

    code = analyses[0].code
    if any(not np.array_equal(analysis.code, code) for analysis in analyses):
        raise ValueError("noise distributions must share one output-code range")
    rates = np.asarray(
        [
            analysis.sample_rate_hz if rate_axis == "sampling" else analysis.active_conversion_rate_hz
            for analysis in analyses
        ]
    )
    order = np.argsort(rates)
    rates_msps = rates[order] / 1e6
    counts = np.asarray([analysis.count for analysis in analyses])[order]
    populated = np.flatnonzero(np.any(counts > 0, axis=0))
    first_code = max(0, int(populated[0]) - 2)
    last_code = min(len(code) - 1, int(populated[-1]) + 2)
    codes = code[first_code : last_code + 1]
    visible_counts = counts[:, first_code : last_code + 1]

    fig, ax = plt.subplots()
    maximum_count = int(calc.ymax(visible_counts))
    histogram_scale = int(np.ceil(maximum_count / 10_000.0) * 10_000)
    if len(np.unique(rates_msps)) == 1:
        maximum_width_msps = 0.2
    else:
        maximum_width_msps = min(0.2, 0.8 * float(calc.ymin(np.diff(np.unique(rates_msps)))))
    for rate_msps, histogram in zip(rates_msps, visible_counts, strict=True):
        populated_codes = histogram > 0
        widths = maximum_width_msps * histogram[populated_codes] / histogram_scale
        ax.barh(
            codes[populated_codes],
            widths,
            left=rate_msps - widths / 2.0,
            height=1.0,
            facecolor=NORD_BLUE,
            edgecolor=NORD_BLUE,
            linewidth=0.45,
        )
    mean = np.asarray([analysis.mean_dout for analysis in analyses])[order]
    std = np.asarray([analysis.std_dout for analysis in analyses])[order]
    ax.plot(rates_msps, mean, color=CURVE_COLORS[1], marker="o", label="Mean")
    ax.plot(
        rates_msps,
        mean - std,
        color=CURVE_COLORS[2],
        linestyle="--",
        label="Mean ±1σ",
    )
    ax.plot(rates_msps, mean + std, color=CURVE_COLORS[2], linestyle="--")
    ax.set_xlabel("Repetition rate (MHz)" if rate_axis == "sampling" else "Conversion rate (MSPS)")
    ax.set_ylabel("ADC output code (LSB)")
    rate_limit_msps = max(10.25, float(calc.ymax(rates_msps)) + 0.25)
    ax.set_xticks(np.arange(0.0, np.floor(rate_limit_msps) + 1.0, 1.0))
    ax.set_xticks(np.arange(0.0, rate_limit_msps + 0.001, 0.25), minor=True)
    ax.set_xlim(0.0, rate_limit_msps)
    ax.set_ylim(float(codes[0]) - 0.5, float(codes[-1]) + 0.5)
    ax.set_title("ADC fixed-input output-code distributions")
    style_grid(ax)
    ax.legend()
    style_info_box(ax, style_measurement_group_text(msmt_list), location="lower left")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_sequence_enob(
    conditions: AnalysisAdcOperatingConditions,
    *,
    sequences: Sequence[AdcSequence],
    adc_label: str,
    output_path: Path,
) -> tuple[Path, ...]:
    """Show fixed-input noise-equivalent ENOB and code shifts across catalogue recipes."""

    symbol_rates_hz = tuple(sorted({float(rate) for rate in conditions.symbol_rate_hz}))
    # Arrange the rows as (sequence, rate) grids; every row must have a place.
    rate_index = {rate: index for index, rate in enumerate(symbol_rates_hz)}
    shape = (len(sequences), len(symbol_rates_hz))
    enob_bits = np.full(shape, np.nan)
    mean_shift_lsb = np.full(shape, np.nan)
    reliable = np.zeros(shape, dtype=bool)
    for row, (sequence, rate) in enumerate(zip(conditions.sequence, conditions.symbol_rate_hz, strict=True)):
        if sequence not in sequences or float(rate) not in rate_index:
            raise ValueError("operating-condition row has no place in the plotted sequence catalogue")
        key = (sequences.index(sequence), rate_index[float(rate)])
        enob_bits[key] = conditions.enob_bits[row]
        mean_shift_lsb[key] = conditions.mean_shift_dout[row]
        reliable[key] = conditions.plausible[row]
    sequence_index = np.arange(1, len(sequences) + 1)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(12.0, 7.0))
    finite_enob = enob_bits[np.isfinite(enob_bits)]
    constant_marker_y = max(12.0, float(calc.ymax(finite_enob)) + 0.5) if len(finite_enob) else 12.0
    for rate_index, symbol_rate_hz in enumerate(symbol_rates_hz):
        baud_mbd = symbol_rate_hz / 1e6
        nominal_msps = symbol_rate_hz / len(sequences[0].init) / 1e6
        good = reliable[:, rate_index] & np.isfinite(enob_bits[:, rate_index])
        (line,) = axes[0].plot(
            sequence_index,
            np.where(good, enob_bits[:, rate_index], np.nan),
            marker="o",
            label=f"{baud_mbd:g} MBd ({nominal_msps:g} MSPS nominal)",
        )
        suspect = ~good
        axes[0].plot(
            sequence_index[suspect],
            np.where(
                np.isfinite(enob_bits[suspect, rate_index]),
                enob_bits[suspect, rate_index],
                constant_marker_y,
            ),
            marker="x",
            linestyle="none",
            color=line.get_color(),
        )
        axes[1].plot(sequence_index, mean_shift_lsb[:, rate_index], marker="o", label=f"{baud_mbd:g} MBd")
    axes[0].set_ylabel("Noise-equivalent ENOB (bit)")
    axes[0].legend(ncols=3)
    axes[1].axhspan(-conditions.shift_limit_dout, conditions.shift_limit_dout, color=SPINE_COLOR, alpha=0.15)
    axes[1].set_yscale("symlog", linthresh=1.0)
    axes[1].set_ylabel(f"Mean code − {symbol_rates_hz[0] / 1e6:g} MBd reference (LSB)")
    axes[1].set_xlabel("Catalogue sequence index (flow/adc/sequences.py)")
    axes[1].set_xlim(0.5, len(sequence_index) + 0.5)
    axes[1].xaxis.set_major_locator(MultipleLocator(5))
    axes[1].xaxis.set_minor_locator(MultipleLocator(1))
    for ax in axes:
        style_grid(ax)
    fig.suptitle(f"{adc_label} · fixed input · × suspect (top ×: constant code)")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_sequence_chip_overview(
    conditions: Sequence[AnalysisAdcOperatingConditions],
    *,
    sequences: Sequence[AdcSequence],
    title: str,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare the median noise-equivalent ENOB and plausible ADC count by recipe."""

    if not conditions or len({result.index for result in conditions}) != len(conditions):
        raise ValueError("chip sequence overview requires one result per ADC")
    symbol_rates_hz = tuple(sorted({float(rate) for result in conditions for rate in result.symbol_rate_hz}))
    # Arrange every ADC's rows as (ADC, sequence, rate) grids; every row must have a place.
    rate_index = {rate: index for index, rate in enumerate(symbol_rates_hz)}
    shape = (len(conditions), len(sequences), len(symbol_rates_hz))
    enob_bits = np.full(shape, np.nan)
    plausible = np.zeros(shape, dtype=bool)
    for adc_position, result in enumerate(conditions):
        for row, (sequence, rate) in enumerate(zip(result.sequence, result.symbol_rate_hz, strict=True)):
            if sequence not in sequences or float(rate) not in rate_index:
                raise ValueError("operating-condition row has no place in the plotted sequence catalogue")
            key = (adc_position, sequences.index(sequence), rate_index[float(rate)])
            enob_bits[key] = result.enob_bits[row]
            plausible[key] = result.plausible[row]
    adc_count = len(conditions)
    # A median is shown only where at least three quarters of the ADCs are plausible.
    minimum_plausible = math.ceil(0.75 * adc_count)
    sequence_index = np.arange(1, len(sequences) + 1)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(12.0, 7.0))
    for rate_index, symbol_rate_hz in enumerate(symbol_rates_hz):
        medians = np.full(len(sequences), np.nan)
        for index in range(len(sequences)):
            selected = enob_bits[plausible[:, index, rate_index], index, rate_index]
            if len(selected) >= minimum_plausible:
                medians[index] = np.median(selected)
        axes[0].plot(sequence_index, medians, marker="o", label=f"{symbol_rate_hz / 1e6:g} MBd")
        axes[1].plot(sequence_index, np.sum(plausible[:, :, rate_index], axis=0), marker="o")
    axes[0].set_ylabel(f"Median ENOB with ≥{minimum_plausible} plausible ADCs (bit)")
    axes[0].legend(ncols=3)
    axes[1].set_ylabel(f"Plausible ADCs of {adc_count}")
    axes[1].set_ylim(-0.5, adc_count + 0.5)
    axes[1].set_xlabel("Catalogue sequence index (flow/adc/sequences.py)")
    axes[1].set_xlim(0.5, len(sequence_index) + 0.5)
    axes[1].xaxis.set_major_locator(MultipleLocator(5))
    axes[1].xaxis.set_minor_locator(MultipleLocator(1))
    for ax in axes:
        style_grid(ax)
    fig.suptitle(title)
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_noise_distribution_grid(
    msmt_list: Sequence[MeasAdc],
    analyses: Sequence[AnalysisAdcNoise],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot rate-indexed code densities for every ADC channel in one grid."""

    groups_by_adc: dict[int, list[AnalysisAdcNoise]] = {}
    for analysis in analyses:
        if analysis.index is None:
            raise ValueError("ADC noise-distribution grid requires results of observed ADC channels")
        groups_by_adc.setdefault(analysis.index, []).append(analysis)
    if not groups_by_adc:
        raise ValueError("ADC noise-distribution grid requires at least one result")
    adc_indices = sorted(groups_by_adc)

    means = np.asarray([analysis.mean_dout for analysis in analyses])
    populated_codes = np.concatenate([analysis.code[analysis.count > 0] for analysis in analyses])
    # Center a span of at least 90 codes on the data, widened to show every populated code.
    y_span_lsb = max(90.0, float(calc.ymax(populated_codes) - calc.ymin(populated_codes)) + 10.0)
    y_center_lsb = 5.0 * np.round((float(calc.ymin(populated_codes)) + float(calc.ymax(populated_codes))) / 10.0)
    y_limits = (y_center_lsb - y_span_lsb / 2.0, y_center_lsb + y_span_lsb / 2.0)
    shared_setup_lines = style_measurement_group_text(msmt_list)
    cdac_setup_lines = tuple(line for line in shared_setup_lines if line.startswith("CDAC init: "))
    shared_setup_lines = tuple(
        line for line in shared_setup_lines if not line.startswith(("ADC: ", "ADCs: ", "CDAC init: "))
    )
    campaign_sample_counts = np.unique([analysis.sample_count for analysis in analyses])
    if len(campaign_sample_counts) == 1:
        sample_count_text = f"{int(campaign_sample_counts[0]):.3g}"
    else:
        sample_count_text = f"{int(calc.ymin(campaign_sample_counts)):.3g}-{int(calc.ymax(campaign_sample_counts)):.3g}"
    system_info_lines = (
        f"ADCs: {adc_indices[0]:02d}-{adc_indices[-1]:02d}",
        *shared_setup_lines,
        *cdac_setup_lines,
        f"N: {sample_count_text}",
    )
    system_info_text = "\n".join(system_info_lines)
    maximum_sample_count = max(analysis.sample_count for analysis in analyses)
    density_norm = LogNorm(vmin=1, vmax=max(2, maximum_sample_count))
    maximum_rate_msps = max(analysis.active_conversion_rate_hz for analysis in analyses) / 1e6
    maximum_width_msps = 2.0

    columns = math.ceil(math.sqrt(len(adc_indices)))
    rows = math.ceil(len(adc_indices) / columns)
    fig, axes = plt.subplots(
        rows,
        columns,
        sharex=True,
        sharey=True,
        layout="none",
        squeeze=False,
    )
    fig.subplots_adjust(left=0.075, right=0.79, bottom=0.105, top=0.94, wspace=0.05, hspace=0.05)
    fig.suptitle("Code density vs sampling rate for fixed input", y=0.985)
    for ax in axes.flat[len(adc_indices) :]:
        ax.set_visible(False)
    for adc_index, ax in zip(adc_indices, axes.flat, strict=False):
        group = sorted(groups_by_adc[adc_index], key=lambda analysis: analysis.active_conversion_rate_hz)
        rates_msps = np.asarray([analysis.active_conversion_rate_hz for analysis in group]) / 1e6
        counts = np.asarray([analysis.count for analysis in group])
        means = np.asarray([analysis.mean_dout for analysis in group])
        standard_deviations = np.asarray([analysis.std_dout for analysis in group])
        sample_counts = np.asarray([analysis.sample_count for analysis in group])
        code = group[0].code
        mean_curve_x = []
        standard_deviation_curve_x = []
        for rate_msps, histogram, sample_count, mean, standard_deviation in zip(
            rates_msps,
            counts,
            sample_counts,
            means,
            standard_deviations,
            strict=True,
        ):
            populated = histogram > 0
            fractions = histogram[populated] / sample_count
            peak_fraction_per_lsb = float(calc.ymax(fractions))
            widths = maximum_width_msps * fractions / peak_fraction_per_lsb
            ax.barh(
                code[populated],
                widths,
                left=rate_msps - widths,
                height=1.0,
                color=DENSITY_COLOR_MAP(density_norm(histogram[populated])),
                edgecolor="none",
                rasterized=True,
                zorder=2,
            )
            if standard_deviation > 0.0:
                fit_code = np.linspace(*y_limits, 501)
                fit_fraction_per_lsb = np.exp(-0.5 * ((fit_code - mean) / standard_deviation) ** 2) / (
                    standard_deviation * np.sqrt(2.0 * np.pi)
                )
                fit_fraction_per_lsb = np.minimum(fit_fraction_per_lsb, peak_fraction_per_lsb)
                fit_x = rate_msps - maximum_width_msps * fit_fraction_per_lsb / peak_fraction_per_lsb
                ax.plot(fit_x, fit_code, color=TEXT_COLOR, linestyle=":", zorder=3)
                gaussian_peak = 1.0 / (standard_deviation * np.sqrt(2.0 * np.pi))
                mean_curve_x.append(
                    rate_msps - maximum_width_msps * min(gaussian_peak, peak_fraction_per_lsb) / peak_fraction_per_lsb
                )
                standard_deviation_curve_x.append(
                    rate_msps
                    - maximum_width_msps
                    * min(gaussian_peak * np.exp(-0.5), peak_fraction_per_lsb)
                    / peak_fraction_per_lsb
                )
            else:
                ax.plot(
                    (rate_msps, rate_msps),
                    y_limits,
                    color=TEXT_COLOR,
                    linestyle=":",
                    zorder=3,
                )
                ax.plot(
                    (rate_msps, rate_msps - maximum_width_msps),
                    (mean, mean),
                    color=TEXT_COLOR,
                    linestyle=":",
                    zorder=3,
                )
                mean_curve_x.append(rate_msps - maximum_width_msps)
                standard_deviation_curve_x.append(rate_msps - maximum_width_msps)

        ax.plot(
            standard_deviation_curve_x,
            means - standard_deviations,
            color=NORD_GREEN,
            linestyle=":",
            zorder=4,
        )
        ax.plot(
            standard_deviation_curve_x,
            means + standard_deviations,
            color=NORD_GREEN,
            linestyle=":",
            zorder=4,
        )
        ax.plot(mean_curve_x, means, color=NORD_ORANGE, linestyle=":", zorder=5)
        summary_location = "lower left" if calc.average(means) > calc.average(y_limits) else "upper left"
        dispersion_range_text = (
            "σ:"
            f"{style_adc_code_dispersion_lsb(float(standard_deviations[0]), single_code=np.count_nonzero(counts[0]) == 1)}→"
            f"{style_adc_code_dispersion_lsb(float(standard_deviations[-1]), single_code=np.count_nonzero(counts[-1]) == 1)} LSB"
        )
        style_info_box(
            ax,
            (
                f"ADC:{adc_index:02d}",
                f"μ:{means[0]:.0f}→{means[-1]:.0f}",
                dispersion_range_text,
            ),
            location=summary_location,
            line_colors=(TEXT_COLOR, NORD_ORANGE, NORD_GREEN),
        )
        ax.set_facecolor(NORD_LIGHT_BLUE)
        ax.set_xlim(-0.25, max(10.5, maximum_rate_msps + 0.5))
        ax.set_ylim(*y_limits)
        if maximum_rate_msps <= 10.5:
            ax.set_xticks((2.0, 6.0, 10.0))
        ax.yaxis.set_major_locator(MultipleLocator(25.0))

    colorbar_ax = fig.add_axes((0.84, 0.10, 0.02, 0.45))
    colorbar = fig.colorbar(
        ScalarMappable(norm=density_norm, cmap=DENSITY_COLOR_MAP),
        cax=colorbar_ax,
    )
    colorbar.set_label("Conversions per code")
    legend_rows: list[Artist] = []
    for label, color in (
        ("Gaussian fit", TEXT_COLOR),
        ("Average (μ)", NORD_ORANGE),
        ("Dispersion (σ)", NORD_GREEN),
    ):
        handle = DrawingArea(22.0, 10.0)
        handle.add_artist(Line2D((0.0, 22.0), (5.0, 5.0), color=color, linestyle=":"))
        legend_rows.append(
            HPacker(
                children=[TextArea(label, textprops={"size": mpl.rcParams["legend.fontsize"]}), handle],
                align="center",
                pad=0.0,
                sep=5.0,
            )
        )
    legend_box = AnchoredOffsetbox(
        loc="upper left",
        bbox_to_anchor=(0.80, 0.92),
        bbox_transform=fig.transFigure,
        child=VPacker(
            children=[
                VPacker(children=legend_rows, align="left", pad=0.0, sep=2.0),
                TextArea(
                    system_info_text,
                    textprops={"multialignment": "left", "size": mpl.rcParams["legend.fontsize"]},
                ),
            ],
            align="left",
            pad=0.0,
            sep=6.0,
        ),
        frameon=True,
        pad=mpl.rcParams["legend.borderpad"],
        borderpad=mpl.rcParams["legend.borderaxespad"],
    )
    legend_box.patch.set_boxstyle(f"round,pad={mpl.rcParams['legend.borderpad']}")
    legend_box.patch.set_facecolor(mpl.rcParams["legend.facecolor"])
    legend_box.patch.set_edgecolor(mpl.rcParams["legend.edgecolor"])
    legend_box.patch.set_alpha(mpl.rcParams["legend.framealpha"])
    legend_box.patch.set_linewidth(mpl.rcParams["legend.linewidth"])
    fig.add_artist(legend_box)
    fig.supxlabel("Conversion rate (MSPS)")
    fig.supylabel("Output code (LSB)", x=0.01)
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_dynamic(
    msmt: MeasAdc,
    analysis: AnalysisAdcDynamic,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot sine fit, residual, and spectrum for one dynamic acquisition."""

    time_scale, time_unit = style_time_units(analysis.time_s)
    fig, axes = plt.subplots(3, 1)
    axes[0].plot(analysis.time_s * time_scale, analysis.measured_dout, label="Measured")
    axes[0].plot(analysis.time_s * time_scale, analysis.fitted_dout, label="Sine fit")
    axes[0].set_xlabel(f"Time ({time_unit})")
    axes[0].set_ylabel("ADC output (LSB)")
    axes[0].legend()
    axes[1].plot(analysis.time_s * time_scale, analysis.residual_dout)
    axes[1].set_xlabel(f"Time ({time_unit})")
    axes[1].set_ylabel("Residual (LSB)")
    positive = analysis.spectrum_frequency_hz > 0
    axes[2].semilogx(
        analysis.spectrum_frequency_hz[positive],
        analysis.spectrum_dbfs[positive],
        label=f"SNDR {analysis.spectral_sndr_db:.2f} dB; ENOB {analysis.spectral_enob_bits:.2f} bit",
    )
    axes[2].set_xlabel("Frequency (Hz)")
    axes[2].set_ylabel("Amplitude (dBFS)")
    for ax in axes:
        style_grid(ax)
    axes[2].legend()
    style_info_box(axes[1], style_measurement_text(msmt), location="lower right")
    fig.suptitle("ADC dynamic performance")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_dynamic_sweep(
    msmt_list: Sequence[MeasAdc],
    analyses: Sequence[AnalysisAdcDynamic],
    *,
    output_path: Path,
    x_axis: Literal["input_frequency", "sample_rate"] = "input_frequency",
) -> tuple[Path, ...]:
    """Plot ENOB and SNDR versus input frequency for each conversion rate."""

    sample_rate_hz = np.asarray([analysis.sample_rate_hz for analysis in analyses])
    input_frequency_hz = np.asarray([analysis.input_frequency_hz for analysis in analyses])
    enob_bits = np.asarray([analysis.spectral_enob_bits for analysis in analyses])
    sndr_db = np.asarray([analysis.spectral_sndr_db for analysis in analyses])
    fig, axes = plt.subplots(2, 1, sharex=True)
    if x_axis == "sample_rate":
        order = np.argsort(sample_rate_hz)
        axes[0].plot(sample_rate_hz[order] / 1e6, enob_bits[order], marker="o", label="Spectral")
        axes[1].plot(sample_rate_hz[order] / 1e6, sndr_db[order], marker="o", label="Spectral")
    else:
        for rate_hz in np.unique(sample_rate_hz):
            selected = sample_rate_hz == rate_hz
            order = np.argsort(input_frequency_hz[selected])
            frequency = input_frequency_hz[selected][order]
            # The largest SI prefix that keeps the rate at or above one, e.g. "10 MHz".
            label = next(
                f"{rate_hz / scale:g} {suffix}"
                for scale, suffix in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz"), (1.0, "Hz"))
                if abs(rate_hz) >= scale or scale == 1.0
            )
            axes[0].semilogx(frequency, enob_bits[selected][order], marker="o", label=label)
            axes[1].semilogx(frequency, sndr_db[selected][order], marker="o", label=label)
    axes[0].set_ylabel("ENOB (bit)")
    axes[1].set_ylabel("SNDR (dB)")
    axes[1].set_xlabel("Repetition rate (MHz)" if x_axis == "sample_rate" else "Input frequency (Hz)")
    for ax in axes:
        style_grid(ax)
    axes[0].legend(title=None if x_axis == "sample_rate" else "Conversion rate")
    style_info_box(axes[1], style_measurement_group_text(msmt_list), location="lower right")
    fig.suptitle("ADC dynamic performance sweep")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_power_sweep(
    msmt_list: Sequence[MeasAdc],
    analyses: Sequence[AnalysisAdcPower],
    *,
    output_path: Path,
    rate_axis: Literal["active", "sampling"] = "active",
) -> tuple[Path, ...]:
    """Plot one source's static and dynamic rail power versus rate."""

    rates = np.asarray(
        [
            analysis.sample_rate_hz if rate_axis == "sampling" else analysis.active_conversion_rate_hz
            for analysis in analyses
        ]
    )
    order = np.argsort(rates)
    rate_msps = rates[order] / 1e6
    component_labels = (
        "Digital static",
        "DAC static",
        "Analog static",
        "Digital dynamic",
        "DAC dynamic",
        "Analog dynamic",
    )
    component_power_uw = tuple(
        np.asarray([getattr(analysis, name) for analysis in analyses])[order] * 1e6
        for name in (
            "vdd_d_static_power_w",
            "vdd_dac_static_power_w",
            "vdd_a_static_power_w",
            "vdd_d_dynamic_power_w",
            "vdd_dac_dynamic_power_w",
            "vdd_a_dynamic_power_w",
        )
    )
    analog_color, digital_color, dac_color = CURVE_COLORS[:3]
    component_colors = (
        digital_color,
        dac_color,
        analog_color,
        digital_color,
        dac_color,
        analog_color,
    )
    fig, ax = plt.subplots()
    collections = ax.stackplot(
        rate_msps,
        *component_power_uw,
        labels=component_labels,
        colors=component_colors,
    )
    for index, (collection, color) in enumerate(zip(collections, component_colors, strict=True)):
        collection.set_edgecolor(color)
        collection.set_linewidth(0.7)
        if index >= 3:
            collection.set_hatch("///")
    total_power_uw = np.asarray([analysis.total_power_w for analysis in analyses])[order] * 1e6
    ax.plot(rate_msps, total_power_uw, color=TEXT_COLOR)
    ax.set_ylabel("Supply power (µW)")
    ax.set_xlabel("Repetition rate (MHz)" if rate_axis == "sampling" else "Conversion rate (MSPS)")
    ax.set_xlim(0.0, float(calc.ymax(rate_msps)) + 0.25)
    if calc.ymax(rate_msps) >= 1.0:
        ax.set_xticks(np.arange(1.0, np.floor(calc.ymax(rate_msps)) + 1.0))
    ax.set_xticks(np.arange(0.0, float(calc.ymax(rate_msps)) + 0.251, 0.25), minor=True)
    ax.set_ylim(0.0, max(float(calc.ymax(total_power_uw)) * 1.25, 1.0))
    style_grid(ax)
    ax.legend()
    style_info_box(ax, style_measurement_group_text(msmt_list), location="lower right")
    ax.set_title("ADC static and dynamic supply power")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_cdac_settling(
    msmt: MeasAdc,
    analysis: AnalysisAdcCdacSettling,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot CDAC-update intervals, with saved regenerative nodes dotted."""

    time_scale, time_unit = style_time_units(analysis.time_s)
    fig, axes = plt.subplots(
        3,
        3,
        sharex="col",
        sharey="row",
        gridspec_kw={"height_ratios": (1.0, 1.0, 1.25)},
    )
    scaled_time = analysis.time_s * time_scale
    stage_cycles = tuple(dict.fromkeys(zip(analysis.stage_index, analysis.cycle_index, strict=True)))
    for column, (stage_index, cycle_index) in enumerate(stage_cycles):
        selected = analysis.stage_index == stage_index
        if not np.any(selected):
            raise ValueError(f"ADC CDAC settling plot is missing saved stage C{stage_index}")
        comparator_ax, drive_ax, settling_ax = axes[:, column]
        comparator_ax.plot(scaled_time, analysis.clk_comp_v[selected][0], color=NORD_DARK)
        for values in analysis.comp_out_p_v[selected]:
            comparator_ax.plot(scaled_time, values, color=NORD_BLUE, alpha=0.35)
        for values in analysis.comp_out_n_v[selected]:
            comparator_ax.plot(scaled_time, values, color=NORD_ORANGE, alpha=0.35)
        for name, color in (("comp_latch_p_v", NORD_BLUE), ("comp_latch_n_v", NORD_ORANGE)):
            if (internal := getattr(analysis, name)) is not None:
                for values in internal[selected]:
                    comparator_ax.plot(scaled_time, values, color=color, linestyle=":", alpha=0.35)

        drive_ax.plot(scaled_time, analysis.seq_logic_v[selected][0], color=NORD_DARK)
        for values in analysis.dac_state_p_v[selected]:
            drive_ax.plot(scaled_time, values, color=NORD_BLUE, linestyle="--", alpha=0.35)
        for values in analysis.dac_state_n_v[selected]:
            drive_ax.plot(scaled_time, values, color=NORD_ORANGE, linestyle="--", alpha=0.35)
        for values in analysis.dac_botplate_p_v[selected]:
            drive_ax.plot(scaled_time, values, color=NORD_BLUE, alpha=0.35)
        for values in analysis.dac_botplate_n_v[selected]:
            drive_ax.plot(scaled_time, values, color=NORD_ORANGE, alpha=0.35)

        for values in analysis.vdac_p_settling_error_v[selected]:
            settling_ax.plot(scaled_time, values * 1e3, color=NORD_BLUE, alpha=0.35)
        for values in analysis.vdac_n_settling_error_v[selected]:
            settling_ax.plot(scaled_time, values * 1e3, color=NORD_ORANGE, alpha=0.35)
        settling_ax.axhline(0.0, color=NORD_DARK, linestyle="--")
        settling_ax.set_ylim(-25.0, 25.0)
        settling_ax.set_xlabel(f"Time ({time_unit})")
        comparator_ax.set_title(f"C{int(stage_index)} (cycle {int(cycle_index)})")
        for ax in (comparator_ax, drive_ax, settling_ax):
            ax.set_xlim(float(scaled_time[0]), float(scaled_time[-1]))
            style_grid(ax)

    digital_limit_v = float(msmt.param.vdd_d.dc)
    axes[0, 0].set_ylim(-0.08 * digital_limit_v, 1.08 * digital_limit_v)
    axes[1, 0].set_ylim(-0.08 * digital_limit_v, 1.08 * digital_limit_v)
    axes[0, 0].set_ylabel("Comparator (V)")
    axes[1, 0].set_ylabel("CDAC drive (V)")
    axes[2, 0].set_ylabel("VDAC residual (mV)")
    axes[0, 0].legend(
        handles=(
            Line2D((), (), color=NORD_DARK, label="clk_comp"),
            Line2D((), (), color=NORD_BLUE, label="out_p"),
            Line2D((), (), color=NORD_ORANGE, label="out_n"),
            *(
                Line2D((), (), color=color, linestyle=":", label=label)
                for name, color, label in (
                    ("comp_latch_p_v", NORD_BLUE, "internal_p"),
                    ("comp_latch_n_v", NORD_ORANGE, "internal_n"),
                )
                if getattr(analysis, name) is not None
            ),
        ),
        loc="lower left",
        ncols=2,
        fontsize=INFO_BOX_FONT_SIZE,
    )
    axes[1, 0].legend(
        handles=(
            Line2D((), (), color=NORD_DARK, label="clk_logic"),
            Line2D((), (), color=NORD_BLUE, linestyle="--", label="state_p"),
            Line2D((), (), color=NORD_ORANGE, linestyle="--", label="state_n"),
            Line2D((), (), color=NORD_BLUE, label="bot_p"),
            Line2D((), (), color=NORD_ORANGE, label="bot_n"),
        ),
        loc="lower left",
        ncols=1,
        fontsize=INFO_BOX_FONT_SIZE,
    )
    axes[2, 0].legend(
        handles=(
            Line2D((), (), color=NORD_BLUE, label="top_p"),
            Line2D((), (), color=NORD_ORANGE, label="top_n"),
        ),
        loc="lower left",
        ncols=1,
        fontsize=INFO_BOX_FONT_SIZE,
    )
    flavor = (
        msmt.param.pex_cell.removeprefix("adc_").replace("_", " ").replace("layer", "-layer").replace("radix", "radix-")
    )
    setup_lines = [
        f"PEX: {flavor}",
        *style_measurement_text(msmt),
        f"Conversions: {len(np.unique(analysis.conversion_index))}",
    ]
    style_info_box(axes[0, -1], setup_lines, location="upper right")
    fig.suptitle("CDAC settling through representative SAR decisions")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_power_waveform(
    analysis: AnalysisAdcPowerWaveform,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot instantaneous rail power and sequencer timing for one conversion."""

    scale, unit = style_time_units(np.asarray((0.0, analysis.active_duration_s)))
    scaled_time = analysis.time_s * scale
    linear_threshold_uw = 1.0
    power_limit_uw = 2.0e3
    first_tick_decade = int(np.ceil(np.log10(linear_threshold_uw)))
    last_tick_decade = int(np.floor(np.log10(power_limit_uw)))
    positive_ticks = 10.0 ** np.arange(first_tick_decade, last_tick_decade + 1)
    power_ticks = np.concatenate((-positive_ticks[::-1], np.asarray([0.0]), positive_ticks))
    fig, axes = plt.subplots(
        4,
        1,
        sharex=True,
        gridspec_kw={"height_ratios": (1.0, 1.0, 1.0, 0.8)},
    )
    rail_labels = ("Analog", "Digital", "DAC")
    rail_power_w = (analysis.analog_power_w, analysis.digital_power_w, analysis.dac_power_w)
    for index, (ax, label, power_w, color) in enumerate(
        zip(axes[:3], rail_labels, rail_power_w, CURVE_COLORS[:3], strict=True)
    ):
        instantaneous_power_uw = power_w * 1e6
        static_power_uw = analysis.static_power_w[index] * 1e6
        active_power_uw = analysis.active_power_w[index] * 1e6
        ax.plot(scaled_time, instantaneous_power_uw, color=color, label="Instantaneous")
        ax.axhline(static_power_uw, color=NORD_DARK, linestyle=":", label="Static average")
        ax.axhline(active_power_uw, color=NORD_ORANGE, linestyle="--", label="Active average")
        ax.set_ylabel(f"{label} (µW)")
        ax.set_yscale("symlog", linthresh=linear_threshold_uw, linscale=0.6)
        ax.set_yticks(power_ticks)
        ax.set_ylim(-power_limit_uw, power_limit_uw)
        style_grid(ax)
        ax.legend(ncols=3)

    timing_ax = axes[3]
    timing_labels = ("INIT", "SAMP", "COMP", "LOGIC")
    timing_states = (analysis.init_high, analysis.samp_high, analysis.comp_high, analysis.logic_high)
    for row, (label, high, color) in enumerate(zip(timing_labels, timing_states, CURVE_COLORS, strict=False)):
        timing_ax.step(scaled_time, row + 0.72 * high, where="post", color=color)
    timing_ax.set_yticks(np.arange(len(timing_labels)) + 0.36, labels=timing_labels)
    timing_ax.set_ylim(-0.15, len(timing_labels) - 0.05)
    timing_ax.set_ylabel("Sequencer")
    timing_ax.set_xlabel(f"Time ({unit})")
    display_duration_scaled = analysis.active_duration_s * scale
    display_margin_scaled = 0.02 * display_duration_scaled
    timing_ax.set_xlim(-display_margin_scaled, display_duration_scaled + display_margin_scaled)
    timing_ax.set_xticks(np.linspace(0.0, display_duration_scaled, 6))
    style_grid(timing_ax)

    setup_lines = [
        *style_instance_text(analysis),
        f"Conversion: {analysis.active_conversion_rate_hz / 1e6:g} MSPS",
    ]
    style_info_box(axes[0], setup_lines)
    fig.suptitle("ADC instantaneous supply power")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_decision_paths(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    output_path: Path,
    selection: Literal["single", "same_dout", "all"] = "single",
    row_index: int = 0,
    selected_dout: int | None = None,
) -> tuple[Path, ...]:
    """Plot running SAR estimates for one conversion, one final code, or all of them.

    ``same_dout`` defaults to the most common final code.
    """

    if selection == "single":
        if not 0 <= row_index < len(analysis.final_dout):
            raise IndexError("decision-path row_index is outside the acquisition")
        rows = np.asarray([row_index])
    elif selection == "same_dout":
        if selected_dout is None:
            codes, counts = np.unique(analysis.final_dout, return_counts=True)
            selected_dout = int(codes[np.argmax(counts)])
        rows = np.flatnonzero(analysis.final_dout == selected_dout)
    else:
        rows = np.arange(len(analysis.final_dout))
    fig, ax = plt.subplots()
    cycles = np.arange(analysis.estimate_dout.shape[1])
    for position, row in enumerate(rows):
        ax.plot(
            cycles,
            analysis.estimate_dout[row],
            color=CURVE_COLORS[0],
            label="Running estimate" if position == 0 else None,
        )
        ax.axhline(
            analysis.final_dout[row],
            color=CURVE_COLORS[1],
            label="Final output" if position == 0 else None,
        )
    ax.set_xlabel("Decision cycle")
    ax.set_xticks(cycles)
    ax.set_xticklabels(("Init", *(f"B{decision}" for decision in range(len(cycles) - 1))))
    ax.set_ylabel("Running estimate (LSB)")
    ax.set_title("ADC decision paths")
    ax.legend()
    style_info_box(ax, style_measurement_text(msmt), location="lower right")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_adc_decision_path_density(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot how frequently conversions follow each running SAR trajectory."""

    params = msmt.tb
    paths = analysis.estimate_dout
    cycles = np.arange(analysis.estimate_dout.shape[1], dtype=np.float64)
    substeps_per_decision = 8
    cycle_step = 1.0 / substeps_per_decision
    horizontal_bins = len(cycles) * substeps_per_decision
    cycle_edges = np.arange(horizontal_bins + 1, dtype=np.float64) * cycle_step
    fine_cycles = cycle_edges[:-1] + cycle_step / 2.0
    normalized_code_max = (1 << params.dut.adc_bits) - 1
    code_edges = np.arange(-0.5, normalized_code_max + 1.5, 1.0)
    count = np.zeros((len(cycle_edges) - 1, len(code_edges) - 1), dtype=np.float64)
    for first_row in range(0, len(paths), 10_000):
        path_chunk = paths[first_row : first_row + 10_000]
        # A SAR estimate is a discrete state, not a continuously changing
        # voltage. Hold each estimate through its decision interval and jump
        # to the next value exactly at the following integer cycle.
        held = np.repeat(path_chunk, substeps_per_decision, axis=1)
        path_count, _, _ = calc.histogram2D(
            np.broadcast_to(fine_cycles, held.shape).ravel(),
            held.ravel(),
            bins=(cycle_edges, code_edges),
        )
        count += path_count

    # Reserve a narrow gutter between decision-state boxes. Each transition is
    # one filled vertical track spanning the gutter and the outside edges of
    # its source and destination code cells.
    transition_gutter_width = 0.10
    transition_half_gutter = transition_gutter_width / 2.0
    transition_tracks = []
    transition_occupancies = []
    for cycle in range(1, len(cycles)):
        transitions, occupancies = np.unique(
            paths[:, (cycle - 1, cycle)],
            axis=0,
            return_counts=True,
        )
        changed = transitions[:, 0] != transitions[:, 1]
        transitions = transitions[changed]
        occupancies = occupancies[changed]
        order = np.argsort(occupancies)
        for transition, occupancy in zip(transitions[order], occupancies[order], strict=True):
            source_code, destination_code = (float(code) for code in transition)
            source_box_code = np.floor(source_code + 0.5)
            destination_box_code = np.floor(destination_code + 0.5)
            lower_edge = min(source_box_code, destination_box_code) - 0.5
            upper_edge = max(source_box_code, destination_box_code) + 0.5
            transition_tracks.append(
                (
                    (float(cycle) - transition_half_gutter, lower_edge),
                    (float(cycle) + transition_half_gutter, lower_edge),
                    (float(cycle) + transition_half_gutter, upper_edge),
                    (float(cycle) - transition_half_gutter, upper_edge),
                )
            )
            transition_occupancies.append(float(occupancy))

    state_count = count[::substeps_per_decision]
    box_vertices = []
    box_occupancies = []
    for cycle, cycle_count in enumerate(state_count):
        for code in np.flatnonzero(cycle_count):
            box_vertices.append(
                (
                    (float(cycle) + transition_half_gutter, float(code) - 0.5),
                    (float(cycle + 1) - transition_half_gutter, float(code) - 0.5),
                    (float(cycle + 1) - transition_half_gutter, float(code) + 0.5),
                    (float(cycle) + transition_half_gutter, float(code) + 0.5),
                )
            )
            box_occupancies.append(float(cycle_count[code]))

    density_norm = LogNorm(vmin=1, vmax=max(2, len(paths)))

    final_mean_code = int(np.rint(calc.average(analysis.final_dout)))
    populated_min = int(np.floor(calc.ymin(analysis.estimate_dout) + 0.5))
    populated_max = int(np.floor(calc.ymax(analysis.estimate_dout) + 0.5))
    # Keep rare final-code branches visible outside the usual 51-LSB zoom.
    y_limits = (
        (
            max(-0.5, populated_min - 8.5),
            min(normalized_code_max + 0.5, populated_max + 8.5),
        ),
        (
            max(-0.5, min(final_mean_code - 25.5, float(calc.ymin(paths[:, -1])) - 2.5)),
            min(normalized_code_max + 0.5, max(final_mean_code + 25.5, float(calc.ymax(paths[:, -1])) + 2.5)),
        ),
    )

    fig, all_axes = plt.subplots(
        1,
        4,
        layout="constrained",
        gridspec_kw={"width_ratios": (1.0, 1.0, 0.30, 0.035), "wspace": 0.03},
    )
    axes = all_axes[:2]
    for panel_index, (ax, panel_title, y_limit) in enumerate(
        zip(
            axes,
            ("Full trajectory", "Final trajectory"),
            y_limits,
            strict=True,
        )
    ):
        boxes = PolyCollection(
            box_vertices,
            array=np.asarray(box_occupancies),
            cmap=DENSITY_COLOR_MAP,
            norm=density_norm,
            edgecolors="none",
            antialiaseds=False,
            rasterized=True,
            zorder=2,
        )
        ax.add_collection(boxes)
        if transition_tracks:
            connectors = PolyCollection(
                transition_tracks,
                array=np.asarray(transition_occupancies),
                cmap=DENSITY_COLOR_MAP,
                norm=density_norm,
                edgecolors="none",
                antialiaseds=False,
                rasterized=True,
                zorder=2,
            )
            ax.add_collection(connectors)
        ax.set_xlim(0.0, float(len(cycles) + 1))
        ax.set_ylim(*y_limit)
        labeled_cycles = cycles[::2].copy()
        if labeled_cycles[-1] != cycles[-1]:
            labeled_cycles[-1] = cycles[-1]
        ax.set_xticks(labeled_cycles)
        ax.set_xticklabels(("Init", *(f"B{int(cycle - 1)}" for cycle in labeled_cycles[1:])))
        ax.set_xticks(cycles, minor=True)
        ax.set_xlabel("Decision cycle")
        if panel_index == 0:
            ax.set_ylabel("Successive approximation code (LSB)")
        ax.set_title(panel_title)
        ax.set_facecolor(NORD_LIGHT_BLUE)
        if panel_index:
            ax.yaxis.set_minor_locator(MultipleLocator(1.0))

    histogram_ax = all_axes[2]
    sample_count = len(paths)
    final_count = state_count[-1]
    populated_final_codes = np.flatnonzero(final_count)
    populated_final_count = final_count[populated_final_codes]
    histogram_ax.barh(
        populated_final_codes,
        populated_final_count / sample_count,
        height=1.0,
        color=DENSITY_COLOR_MAP(density_norm(populated_final_count)),
        edgecolor="none",
        rasterized=True,
        zorder=2,
    )
    final_mean = calc.average(paths[:, -1])
    final_std = calc.stddev(paths[:, -1])
    if final_std > 0.0:
        fit_code = np.linspace(*y_limits[1], 501)
        fit_fraction_per_lsb = np.exp(-0.5 * ((fit_code - final_mean) / final_std) ** 2) / (
            final_std * np.sqrt(2.0 * np.pi)
        )
        histogram_ax.plot(
            fit_fraction_per_lsb,
            fit_code,
            color=TEXT_COLOR,
            zorder=3,
        )
    histogram_ax.set_ylim(*y_limits[1])
    histogram_ax.set_xlim(left=0.0)
    histogram_ax.set_title("Code density")
    histogram_ax.set_xlabel("Count / N")
    histogram_ax.set_yticks([])
    histogram_ax.xaxis.set_major_locator(MaxNLocator(nbins=2, integer=True))
    histogram_ax.xaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
    histogram_ax.set_facecolor(NORD_LIGHT_BLUE)
    style_info_box(
        histogram_ax,
        (
            f"μ: {final_mean:.0f}",
            f"σ: {style_adc_code_dispersion_lsb(final_std, single_code=len(populated_final_codes) == 1)} LSB",
        ),
    )

    colorbar = fig.colorbar(ScalarMappable(norm=density_norm, cmap=DENSITY_COLOR_MAP), cax=all_axes[3])
    colorbar.set_label("Conversions per path")
    style_info_box(axes[0], (*style_measurement_text(msmt), f"N: {sample_count}"))
    fig.suptitle("ADC decision-path density")
    return save_figure(fig, output_path)


@mpl.rc_context(PLOT_STYLE)
def plot_comp_offset_noise(
    msmt_list: Sequence[MeasComp],
    analysis: AnalysisCompOffsetNoise,
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
    msmt_list2d: Sequence[Sequence[MeasComp]],
    analysis_list: Sequence[AnalysisCompOffsetNoise],
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
    msmt_list: Sequence[MeasComp],
    offsets: Sequence[AnalysisCompOffsetNoise],
    common_mode: AnalysisCompCommonMode,
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
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot candidate noise, power, and settling on one area-ordered axis."""

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
    axes[0].legend(ncols=3)

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
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot candidate noise against power, colored by settling.

    Candidates with unresolved trials or an invalid S-curve fit have no
    meaningful settling color; those with finite noise and power are shown
    as gray crosses.
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

    colorbar = fig.colorbar(mappable, ax=ax, pad=0.02)
    colorbar.set_label("Worst settling time (ns)")

    ax.set_yscale("log")
    ax.set_xlabel("Input-referred noise σ (mV)")
    ax.set_ylabel("Average power (µW)")
    style_grid(ax)
    ax.legend()
    fig.suptitle("Comparator noise–power trade-off")
    return save_figure(fig, output_path)
