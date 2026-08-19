"""Plots of typed FRIDA measurements and analysis results."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from functools import wraps
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize
from matplotlib.offsetbox import AnchoredText
from matplotlib.patches import Patch
from matplotlib.ticker import AutoMinorLocator, NullLocator
from scipy.special import ndtr

from flow.analysis.types import (
    AnalysisAdcCalibration,
    AnalysisAdcCodeDistribution,
    AnalysisAdcDecisionPaths,
    AnalysisAdcDynamic,
    AnalysisAdcDynamicSweep,
    AnalysisAdcNoiseSweep,
    AnalysisAdcNonlinearity,
    AnalysisAdcPowerSweep,
    AnalysisAdcPowerWaveform,
    AnalysisAdcRamp,
    AnalysisAdcScopeBits,
    AnalysisAdcTransfer,
    AnalysisCdacCapMismatch,
    AnalysisCompCandidateSweep,
    AnalysisCompOffsetNoise,
    AnalysisCompPower,
    AnalysisCompTiming,
    AnalysisDiffampNoise,
    AnalysisWaveforms,
    MeasAdc,
    MeasAdcExt,
    MeasAdcInt,
    MeasCdacExt,
    MeasCompExt,
    MeasCompInt,
    Measurement,
)

PLOT_PNGS = True
PLOT_SVGS = False
PLOT_PDFS = True
PNG_DPI = 500
FULL_HD_FIGSIZE = (9.6, 5.4)
COMMON_MODE_DISPLAY_MIN_V = 0.7
COMMON_MODE_DISPLAY_MAX_V = 1.2
COMPARATOR_INPUT_ERROR_MINIMUM_MV = 0.0
COMPARATOR_INPUT_ERROR_MAXIMUM_MV = 25.0

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
COMMON_MODE_COLOR_MAP = SPECTRUM_COLOR_MAP
COMP_SETTLING_COLOR_MAP = SPECTRUM_COLOR_MAP
RAIL_COLORS = {
    "vdd_a": CURVE_COLORS[0],
    "vdd_d": CURVE_COLORS[1],
    "vdd_dac": CURVE_COLORS[2],
}
PLOT_STYLE: dict[Any, Any] = {
    "text.usetex": False,
    "mathtext.fontset": "cm",
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman", "DejaVu Serif"],
    "font.size": 11.0,
    "axes.titlesize": 13.0,
    "axes.titleweight": "normal",
    "axes.labelsize": 11.0,
    "axes.labelcolor": TEXT_COLOR,
    "axes.edgecolor": SPINE_COLOR,
    "axes.linewidth": 0.8,
    "axes.facecolor": PLOT_FACE_COLOR,
    "axes.prop_cycle": plt.cycler(color=CURVE_COLORS),
    "xtick.color": TEXT_COLOR,
    "xtick.labelsize": 11.0,
    "ytick.color": TEXT_COLOR,
    "ytick.labelsize": 11.0,
    "text.color": TEXT_COLOR,
    "figure.facecolor": PLOT_FACE_COLOR,
    "figure.titlesize": 13.0,
    "figure.titleweight": "normal",
    "savefig.facecolor": PLOT_FACE_COLOR,
    "savefig.dpi": PNG_DPI,
    "legend.facecolor": LEGEND_FACE_COLOR,
    "legend.edgecolor": SPINE_COLOR,
    "legend.framealpha": 0.9,
    "legend.fontsize": 11.0,
    "legend.title_fontsize": 11.0,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
}


def apply_plot_style() -> None:
    """Install the shared FRIDA Computer Modern and Nord presentation style.

    Computer Modern math and a serif text fallback reproduce the LaTeX-like
    historical plots without requiring every label and metadata value to be
    escaped for an external LaTeX process.
    """

    plt.rcParams.update(PLOT_STYLE)


def with_plot_style[**PlotParameters, PlotReturn](
    function: Callable[PlotParameters, PlotReturn],
) -> Callable[PlotParameters, PlotReturn]:
    """Run one complete plot renderer inside the shared FRIDA style context."""

    @wraps(function)
    def styled(
        *args: PlotParameters.args,
        **kwargs: PlotParameters.kwargs,
    ) -> PlotReturn:
        with plt.rc_context(PLOT_STYLE):
            return function(*args, **kwargs)

    return styled


def style_ax(ax: plt.Axes) -> None:
    """Apply the shared FRIDA axis style."""

    ax.tick_params(
        direction="in",
        which="both",
        top=True,
        right=True,
        colors=TEXT_COLOR,
    )
    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)
        spine.set_linewidth(0.8)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)
    ax.set_facecolor(PLOT_FACE_COLOR)


def style_grid(ax: plt.Axes) -> None:
    """Apply the shared light grid."""

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


def style_legend(ax: plt.Axes, **kwargs) -> None:
    """Create one consistently styled legend."""

    legend = ax.legend(
        frameon=True,
        facecolor=LEGEND_FACE_COLOR,
        edgecolor=SPINE_COLOR,
        labelcolor=TEXT_COLOR,
        framealpha=0.9,
        **kwargs,
    )
    if legend is not None:
        legend.get_frame().set_linewidth(0.8)
        if legend.get_title() is not None:
            legend.get_title().set_color(TEXT_COLOR)


def format_frequency_hz(value: float) -> str:
    """Format one frequency with a compact SI prefix."""

    for scale, suffix in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if abs(value) >= scale:
            return f"{value / scale:g} {suffix}"
    return f"{value:g} Hz"


def _add_info_box(ax: plt.Axes, lines: Sequence[str], *, location: str = "upper right") -> None:
    """Add measurement setup using the same spacing and frame as a legend."""

    if not lines:
        return
    box = AnchoredText(
        "\n".join(lines),
        loc=location,
        prop={"color": TEXT_COLOR, "size": 11.0},
        frameon=True,
        pad=0.4,
        borderpad=0.5,
    )
    box.patch.set_boxstyle("round,pad=0.4")
    box.patch.set_facecolor(LEGEND_FACE_COLOR)
    box.patch.set_edgecolor(SPINE_COLOR)
    box.patch.set_alpha(0.9)
    box.patch.set_linewidth(0.8)
    ax.add_artist(box)


def _save_figure(
    fig: plt.Figure,
    output_path: Path,
) -> tuple[Path, ...]:
    output_path = Path(output_path)
    if output_path.suffix:
        raise ValueError("plot output_path must be a suffixless artifact stem")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.patch.set_facecolor(PLOT_FACE_COLOR)
    fig.tight_layout()
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
    for output_format in formats:
        path = output_path.with_suffix(f".{output_format}")
        if output_format.lower() == "png":
            fig.savefig(
                path,
                facecolor=PLOT_FACE_COLOR,
                dpi=PNG_DPI,
                bbox_inches=None,
            )
        else:
            fig.savefig(
                path,
                facecolor=PLOT_FACE_COLOR,
                bbox_inches=None,
            )
        paths.append(path)
    plt.close(fig)
    return tuple(paths)


def _measurement_setup_lines(msmt: Measurement) -> tuple[str, ...]:
    """Return concise physical setup that is not normally present in titles."""

    lines: tuple[str, ...] = ()
    adc_index = getattr(msmt.param, "observed_adc", None)
    if adc_index is not None:
        lines += (f"ADC: {adc_index:02d}",)
    elif msmt.info.backend != "physical" and isinstance(msmt, (MeasAdcExt, MeasAdcInt)):
        lines += (f"Source: {msmt.info.backend.upper()}",)
    board_id = getattr(msmt.param, "board_id", None)
    if board_id is not None:
        lines += (f"Board: {board_id}",)
    for field_name, label in (("vin_cm", "Vcm"), ("vin_diff", "Vdiff")):
        source = getattr(msmt.param, field_name, None)
        dc_v = getattr(source, "dc", None)
        if dc_v is not None:
            lines += (f"{label}: {float(dc_v) * 1e3:g} mV",)
    input_source = getattr(msmt.param, "vin_diff", None)
    input_frequency_hz = getattr(input_source, "freq", None)
    if input_frequency_hz is not None:
        lines += (f"Input: {format_frequency_hz(float(input_frequency_hz))}",)
    active_rate_hz = msmt.info.readbacks.get("active_conversion_rate_hz")
    if isinstance(active_rate_hz, (int, float)):
        lines += (f"Rate: {float(active_rate_hz) / 1e6:g} MSPS",)
    return lines


def _measurement_group_setup_lines(msmt_list: Sequence[Measurement]) -> tuple[str, ...]:
    """Return only setup lines shared by every measurement in a group."""

    if not msmt_list:
        return ()
    shared = list(_measurement_setup_lines(msmt_list[0]))
    for msmt in msmt_list[1:]:
        current = set(_measurement_setup_lines(msmt))
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


def _time_scale(time_s: np.ndarray) -> tuple[float, str]:
    maximum = float(np.max(np.abs(time_s)))
    if maximum < 1e-9:
        return 1e12, "ps"
    if maximum < 1e-6:
        return 1e9, "ns"
    if maximum < 1e-3:
        return 1e6, "µs"
    if maximum < 1.0:
        return 1e3, "ms"
    return 1.0, "s"


@with_plot_style
def plot_waveforms(
    analysis: AnalysisWaveforms,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one completed typed waveform analysis."""

    scale, unit = _time_scale(analysis.time_s)
    fig, axes = plt.subplots(
        len(analysis.signal_names),
        1,
        sharex=True,
        figsize=FULL_HD_FIGSIZE,
    )
    axes = np.atleast_1d(axes)
    for ax, name, signal_unit, values in zip(
        axes,
        analysis.signal_names,
        analysis.signal_units,
        analysis.signal_values,
        strict=True,
    ):
        ax.plot(analysis.time_s * scale, values, linewidth=1.0)
        suffix = f" ({signal_unit})" if signal_unit else ""
        ax.set_ylabel(f"{name}{suffix}")
        style_ax(ax)
        style_grid(ax)
    axes[-1].set_xlabel(f"Time ({unit})")
    _add_info_box(axes[0], analysis.setup_lines)
    fig.suptitle(analysis.title)
    return _save_figure(fig, output_path)


@with_plot_style
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
    fig, (histogram_ax, spectrum_ax) = plt.subplots(2, 1, figsize=FULL_HD_FIGSIZE)
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
        linewidth=1.8,
        label=(f"Gaussian fit (raw µ = {analysis.mean_v * 1e3:.3f} mV subtracted; σ = {noise_rms_mv:.3f} mV)"),
    )
    histogram_ax.set_xlabel("Differential output noise about its mean (mV)")
    histogram_ax.set_ylabel("Density (mV⁻¹)")
    style_legend(histogram_ax)

    positive = analysis.frequency_hz > 0.0
    spectrum_ax.loglog(
        analysis.frequency_hz[positive],
        analysis.amplitude_spectral_density_v_per_sqrt_hz[positive] * 1e6,
        color=NORD_BLUE,
        linewidth=1.0,
        label=f"Measured spectrum (integrated RMS = {analysis.integrated_fft_noise_rms_v * 1e3:.3f} mV)",
    )
    spectrum_ax.axvline(
        analysis.measurement_bandwidth_hz,
        color=CURVE_COLORS[1],
        linestyle=":",
        linewidth=1.4,
        label=f"Measurement bandwidth = {analysis.measurement_bandwidth_hz / 1e6:g} MHz",
    )
    spectrum_ax.set_xlabel("Frequency (Hz)")
    spectrum_ax.set_ylabel("ASD (µV/√Hz)")
    style_legend(spectrum_ax)
    for ax in (histogram_ax, spectrum_ax):
        style_ax(ax)
        style_grid(ax)
    fig.suptitle("Differential-amplifier output noise")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_fastrx_scope_comparison(
    msmt: MeasAdcExt,
    analysis: AnalysisAdcScopeBits,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot CH2--CH4 and aligned Scope/FastRX decision streams."""

    decision_period_s = 8.0 / float(msmt.param.symbol_rate)
    edge_times_s = analysis.comp_edge_times_s
    sample_times_s = analysis.sample_times_s
    decision_end_times_s = np.concatenate((edge_times_s[1:], [edge_times_s[-1] + decision_period_s]))
    decision_widths_s = decision_end_times_s - edge_times_s

    time_s = msmt.wave.time_s
    scale, unit = _time_scale(time_s)
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
        figsize=FULL_HD_FIGSIZE,
        gridspec_kw={"height_ratios": (1.0, 1.0, 1.35, 1.25)},
    )
    waveform_rows = (
        ("COMP", msmt.wave.seq_comp_v[0]),
        ("LOGIC", msmt.wave.seq_logic_v[0]),
        ("COMP_OUT", msmt.wave.comp_out_v[0]),
    )
    for ax, (label, values), color in zip(axes[:3], waveform_rows, CURVE_COLORS, strict=False):
        ax.plot(scaled_time, values, color=color, linewidth=1.0)
        for edge in scaled_edges:
            ax.axvline(edge, color=SPINE_COLOR, alpha=0.18, linewidth=0.6)
        ax.set_ylabel(f"{label} (V)")
        style_ax(ax)
        style_grid(ax)

    axes[2].scatter(
        scaled_samples,
        analysis.sample_values_v,
        marker="o",
        s=22,
        color=CURVE_COLORS[3],
        edgecolor=PLOT_FACE_COLOR,
        linewidth=0.5,
        zorder=5,
        label="Scope decode sample",
    )
    style_legend(axes[2])

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
                color=TEXT_COLOR,
                fontweight="bold",
            )
    decision_ax.set_yticks((1.0, 0.0), labels=("Scope decode", "FastRX decode"))
    decision_ax.set_ylim(-0.6, 1.6)
    decision_ax.set_ylabel("Decision stream")
    decision_ax.set_xlabel(f"Time ({unit})")
    decision_ax.set_title("Decoded decision streams")
    style_ax(decision_ax)
    style_grid(decision_ax)

    axes[0].set_xlim(display_start_s * scale, display_end_s * scale)
    setup_lines = (
        *(line for line in _measurement_setup_lines(msmt) if line.startswith("ADC:")),
        f"Symbol rate: {float(msmt.param.symbol_rate) / 1e6:g} MBd",
        (
            "COMP→LOGIC: "
            f"{float(msmt.param.seq_logic_phase_delay_symbols) - float(msmt.param.seq_comp_phase_delay_symbols):+g} symbols"
        ),
    )
    _add_info_box(axes[0], setup_lines)
    fig.suptitle("ADC scope and FastRX decision comparison")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_transfer(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcTransfer,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot individual ADC conversions and the mean static transfer."""

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    inputs = np.concatenate([msmt.daq.vin_diff_v for msmt in msmt_list])
    dout = np.concatenate([msmt.daq.dout for msmt in msmt_list])
    ax.scatter(inputs * 1e3, dout, s=2, label="Conversions")
    ax.errorbar(
        analysis.vin_diff_v * 1e3,
        analysis.mean_dout,
        yerr=analysis.std_dout,
        marker="o",
        markersize=3,
        linewidth=1.2,
        capsize=2,
        label="Mean ± 1σ",
    )
    ax.set_xlabel("Differential input (mV)")
    ax.set_ylabel("ADC output (LSB)")
    ax.set_title("ADC static transfer")
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    _add_info_box(ax, _measurement_group_setup_lines(msmt_list), location="lower right")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_ramp_transfer(
    analysis: AnalysisAdcRamp,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot the phase-reconstructed ramp transfer for every decoded curve."""

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    for curve in analysis.curves:
        ax.plot(
            curve.transfer_vin_diff_v * 1e3,
            curve.transfer_mean_dout,
            linewidth=1.0,
            label=curve.label,
        )
    ax.set_xlabel("Inferred differential input (mV)")
    ax.set_ylabel("Mean ADC output (LSB)")
    ax.set_title("ADC ramp transfer")
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    _add_info_box(
        ax,
        (
            f"ADC: {analysis.adc_index:02d}",
            f"Sample rate: {analysis.sample_rate_hz / 1e6:.6g} MS/s",
            f"Ramp: {analysis.ramp_frequency_hz:.6g} Hz",
        ),
        location="lower right",
    )
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_ramp_histogram(
    analysis: AnalysisAdcRamp,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot overlaid code-density histograms from completed ramp analyses."""

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    number_bins = 128
    first_code = int(analysis.curves[0].code[0]) + 1
    last_code = int(analysis.curves[0].code[-1])
    bin_edges = np.linspace(first_code, last_code, number_bins + 1, dtype=np.int64)
    bin_edges = np.unique(bin_edges)
    for curve, color in zip(analysis.curves, CURVE_COLORS, strict=False):
        average_count = np.asarray([np.mean(curve.count[lower:upper]) for lower, upper in pairwise(bin_edges)])
        ax.stairs(
            average_count,
            bin_edges,
            baseline=0.0,
            fill=False,
            linewidth=1.0,
            color=color,
            label=curve.label,
        )
    ax.set_xlabel("Output code")
    ax.set_ylabel("Mean samples per code in bin")
    ax.set_title("ADC ramp code density")
    style_ax(ax)
    style_grid(ax)
    style_legend(ax, ncol=2)
    _add_info_box(
        ax,
        (
            f"ADC: {analysis.adc_index:02d}",
            f"Ramp: {analysis.ramp_frequency_hz:.6g} Hz",
        ),
        location="lower right",
    )
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_ramp_weights(
    analysis: AnalysisAdcRamp,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare nominal and direction-matched physical decision weights."""

    nominal, measured = analysis.curves[:2]
    code_max = len(nominal.code) - 1
    nominal_weights = nominal.weights * code_max / np.sum(nominal.weights)
    measured_weights = measured.weights * code_max / np.sum(measured.weights)
    elements = np.arange(16, 0, -1)
    relative_error_percent = 100.0 * (measured_weights[:-1] / nominal_weights[:-1] - 1.0)

    fig, axes = plt.subplots(
        2,
        1,
        sharex=True,
        figsize=FULL_HD_FIGSIZE,
        gridspec_kw={"height_ratios": (2.0, 1.0)},
    )
    axes[0].plot(elements, nominal_weights[:-1], "o-", color=NORD_DARK, label="Ideal")
    axes[0].plot(
        elements,
        measured_weights[:-1],
        "o-",
        color=NORD_BLUE,
        label="Direction-matched measured",
    )
    axes[0].set_yscale("log", base=2)
    axes[0].set_ylabel("Decision weight (LSB)")
    style_legend(axes[0])
    axes[1].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    axes[1].bar(elements, relative_error_percent, color=NORD_BLUE, width=0.7)
    axes[1].set_ylabel("Error (%)")
    axes[1].set_xlabel("Physical capacitor element")
    axes[1].set_xticks(elements)
    axes[1].set_xticklabels([f"C{element:02d}" for element in elements])
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    _add_info_box(axes[1], (f"ADC: {analysis.adc_index:02d}",), location="lower right")
    fig.suptitle("Ideal and extracted ADC decision weights")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_calibration_weights(
    analysis_list: Sequence[AnalysisAdcCalibration],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare any calibration methods against one shared ideal weight set."""

    nominal = analysis_list[0].nominal_weight

    decision = np.arange(17)
    labels = [f"C{element:02d}" for element in range(16, 0, -1)] + ["Term."]
    fig, axes = plt.subplots(
        2,
        1,
        sharex=True,
        figsize=FULL_HD_FIGSIZE,
        gridspec_kw={"height_ratios": (2.0, 1.0)},
    )
    axes[0].plot(decision, nominal, "o-", color=NORD_DARK, linewidth=1.2, label="Ideal")
    axes[1].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    for calibration, color in zip(analysis_list, CURVE_COLORS, strict=False):
        axes[0].plot(
            decision,
            calibration.calibrated_weight,
            "o-",
            color=color,
            linewidth=1.1,
            markersize=3.5,
            label=calibration.label,
        )
        error_percent = 100.0 * (calibration.calibrated_weight / nominal - 1.0)
        axes[1].plot(
            decision,
            error_percent,
            "o-",
            color=color,
            linewidth=1.1,
            markersize=3.5,
            label=calibration.label,
        )
        inferred = ~calibration.weight_from_measurement
        if np.any(inferred):
            axes[0].scatter(
                decision[inferred],
                calibration.calibrated_weight[inferred],
                marker="x",
                s=30,
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
    style_legend(axes[0], ncol=2)
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    _add_info_box(axes[1], (f"ADC: {analysis_list[0].adc_index:02d}",))
    fig.suptitle("ADC digital calibration weights")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_static_nonlinearity(
    msmt: MeasAdc,
    analysis: AnalysisAdcNonlinearity,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot static ADC DNL and INL from one completed analysis."""

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=FULL_HD_FIGSIZE)
    axes[0].plot(analysis.code, analysis.dnl, linewidth=0.9)
    axes[1].plot(analysis.code, analysis.inl, linewidth=0.9)
    axes[0].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    axes[0].set_ylabel("DNL (LSB)")
    axes[1].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    axes[1].set_ylabel("INL (LSB)")
    axes[1].set_xlabel("Output code")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    _add_info_box(axes[0], _measurement_setup_lines(msmt))
    fig.suptitle(f"ADC {analysis.method.replace('_', '-')} nonlinearity")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_ramp_nonlinearity(
    analysis: AnalysisAdcRamp,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot overlaid ramp DNL and INL for every completed decoding."""

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=FULL_HD_FIGSIZE)
    for curve in analysis.curves:
        axes[0].plot(curve.linearity_code, curve.dnl, linewidth=0.9, label=curve.label)
        axes[1].plot(curve.linearity_code, curve.inl, linewidth=0.9, label=curve.label)
    axes[0].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    axes[0].set_ylabel("DNL (LSB)")
    axes[1].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    axes[1].set_ylabel("INL (LSB)")
    axes[1].set_xlabel("Output code")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    style_legend(axes[0])
    _add_info_box(
        axes[1],
        (f"ADC: {analysis.adc_index:02d}", f"Ramp: {analysis.ramp_frequency_hz:.6g} Hz"),
    )
    fig.suptitle("ADC ramp nonlinearity")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_code_distribution(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcCodeDistribution,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot code histograms and standard deviation at static input points."""

    fig, axes = plt.subplots(2, 1, figsize=FULL_HD_FIGSIZE)
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
    style_legend(axes[0], ncol=2)
    axes[1].plot(analysis.vin_diff_v * 1e3, analysis.std_dout, marker="o")
    axes[1].set_xlabel("Differential input (mV)")
    axes[1].set_ylabel("Standard deviation (LSB)")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    _add_info_box(axes[1], _measurement_group_setup_lines(msmt_list))
    fig.suptitle("ADC output-code distribution")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_noise_sweep(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcNoiseSweep,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot noise, equivalent full-scale SNR, and ENOB on one rate panel."""

    # The SNR and ENOB axes use a full-scale sine whose peak-to-peak
    # range is the ADC input range represented by all output codes.
    adc_bits = msmt_list[0].param.dut.adc_bits
    full_scale_rms_lsb = ((1 << adc_bits) - 1) / (2.0 * np.sqrt(2.0))
    noise_rms_v = np.asarray(analysis.input_referred_noise_rms_v)
    noise_rms_lsb = noise_rms_v / analysis.input_lsb_v

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    conversion_rate_msps = analysis.sample_rate_hz / 1e6
    if not analysis.series_labels:
        timing_values = np.unique(analysis.comparator_time_percent)
        labels = tuple(f"{value:g}%" for value in timing_values)
        selections = tuple(analysis.comparator_time_percent == value for value in timing_values)
        colors = tuple(CURVE_COLORS[index % len(CURVE_COLORS)] for index in range(len(labels)))
    else:
        labels = tuple(dict.fromkeys(analysis.series_labels))
        label_values = np.asarray(analysis.series_labels)
        selections = tuple(label_values == label for label in labels)
        colors = tuple(CURVE_COLORS[index % len(CURVE_COLORS)] for index in range(len(labels)))

    for label, selected, color in zip(labels, selections, colors, strict=True):
        selected = selected & analysis.noise_valid
        if not np.any(selected):
            continue
        order = np.argsort(conversion_rate_msps[selected])
        selected_rate = conversion_rate_msps[selected][order]
        selected_noise_lsb = noise_rms_lsb[selected][order]
        if label == "Input stimulus noise":
            ax.hlines(
                float(np.mean(selected_noise_lsb)),
                float(selected_rate[0]),
                float(selected_rate[-1]),
                color=color,
                linestyle=":",
                linewidth=1.4,
                label=label,
            )
        else:
            ax.plot(
                selected_rate,
                selected_noise_lsb,
                marker="o",
                markersize=3,
                linewidth=0.8,
                color=color,
                label=label,
            )
    ax.set_xlabel("Active conversion rate (Msps)")
    ax.set_ylabel("Input-referred noise (LSB RMS)")
    ax.invert_yaxis()
    ax.set_ylim(9.0, 0.0)
    ax.set_yticks(np.arange(0.0, 10.0, 1.0))
    ax.set_xticks(np.arange(0.0, 11.0, 1.0))
    ax.set_xlim(0.0, 10.25)
    ax.set_xticks(np.arange(0.0, 10.251, 0.25), minor=True)
    ax.set_title("ADC noise performance vs conversion rate")
    style_ax(ax)
    ax.tick_params(which="both", right=False)
    style_grid(ax)
    if ax.get_legend_handles_labels()[0]:
        style_legend(
            ax,
            ncol=4 if not analysis.series_labels else 1,
            title="COMP→LOGIC interval\n(as % of decision cycle)" if not analysis.series_labels else None,
        )
    noise_mv_axis = ax.secondary_yaxis(
        "left",
        functions=(
            lambda noise_lsb: np.asarray(noise_lsb) * analysis.input_lsb_v * 1e3,
            lambda noise_mv: np.asarray(noise_mv) / (analysis.input_lsb_v * 1e3),
        ),
    )
    noise_mv_axis.spines["left"].set_position(("outward", 58))
    noise_mv_axis.spines["left"].set_color(SPINE_COLOR)
    noise_mv_axis.set_ylabel("Input-referred noise (mV RMS)")
    noise_mv_axis.tick_params(direction="in", which="both", left=True, right=False, colors=TEXT_COLOR)
    noise_mv_axis.yaxis.label.set_color(TEXT_COLOR)

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
    enob_axis.spines["right"].set_color(SPINE_COLOR)
    enob_axis.set_ylabel("ENOB (bit)")
    enob_axis.set_yticks(np.arange(7.0, 13.0, 1.0))
    enob_axis.tick_params(direction="in", which="both", left=False, right=True, colors=TEXT_COLOR)
    enob_axis.yaxis.label.set_color(TEXT_COLOR)

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
    snr_axis.spines["right"].set_color(SPINE_COLOR)
    snr_axis.set_ylabel("SNR (dB)")
    snr_axis.set_yticks(np.arange(45.0, 71.0, 5.0))
    snr_axis.tick_params(direction="in", which="both", left=False, right=True, colors=TEXT_COLOR)
    snr_axis.yaxis.label.set_color(TEXT_COLOR)

    decision_time_axis = ax.twiny()
    decision_time_axis.set_xlim(ax.get_xlim())
    decision_time_axis.xaxis.set_ticks_position("bottom")
    decision_time_axis.xaxis.set_label_position("bottom")
    decision_time_axis.spines["bottom"].set_position(("outward", 38))
    decision_time_axis.spines["bottom"].set_color(SPINE_COLOR)
    decision_time_axis.spines["top"].set_visible(False)
    decision_time_axis.set_xlabel("Time per decision cycle (ns)")
    labeled_rates_msps = np.arange(1.0, 11.0)
    decision_cycle_ns = 50.0 / labeled_rates_msps
    decision_time_axis.set_xticks(labeled_rates_msps)
    decision_time_axis.set_xticklabels(tuple(f"{interval:.3g}" for interval in decision_cycle_ns))
    decision_time_axis.tick_params(
        direction="in",
        which="both",
        top=False,
        bottom=True,
        colors=TEXT_COLOR,
    )
    decision_time_axis.xaxis.label.set_color(TEXT_COLOR)
    _add_info_box(ax, _measurement_group_setup_lines(msmt_list), location="lower right")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_noise_distribution_sweep(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcNoiseSweep,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot left-facing output-code histograms along the conversion-rate axis."""

    code = cast(np.ndarray, analysis.code)
    count = cast(np.ndarray, analysis.count)
    order = np.argsort(analysis.sample_rate_hz)
    rates_msps = analysis.sample_rate_hz[order] / 1e6
    counts = count[order]
    populated = np.flatnonzero(np.any(counts > 0, axis=0))
    first_code = max(0, int(populated[0]) - 2)
    last_code = min(len(code) - 1, int(populated[-1]) + 2)
    codes = code[first_code : last_code + 1]
    visible_counts = counts[:, first_code : last_code + 1]

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    maximum_count = int(np.max(visible_counts))
    histogram_scale = int(np.ceil(maximum_count / 10_000.0) * 10_000)
    if len(rates_msps) == 1:
        maximum_width_msps = 0.2
    else:
        maximum_width_msps = 0.8 * float(np.min(np.diff(rates_msps)))
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
    mean = analysis.mean_dout[order]
    std = analysis.std_dout[order]
    ax.plot(rates_msps, mean, color=CURVE_COLORS[1], linewidth=1.2, marker="o", markersize=2.5, label="Mean")
    ax.plot(
        rates_msps,
        mean - std,
        color=CURVE_COLORS[2],
        linewidth=0.9,
        linestyle="--",
        label="Mean ±1σ",
    )
    ax.plot(rates_msps, mean + std, color=CURVE_COLORS[2], linewidth=0.9, linestyle="--")
    ax.set_xlabel("Active conversion rate (Msps)")
    ax.set_ylabel("ADC output code (LSB)")
    ax.set_xticks(np.arange(0.0, 11.0, 1.0))
    ax.set_xticks(np.arange(0.0, 10.251, 0.25), minor=True)
    ax.set_xlim(0.0, 10.25)
    ax.set_ylim(mean[0] - 3.0 * std[0], mean[0] + 3.0 * std[0])
    ax.set_title("ADC fixed-input output-code distributions")
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    _add_info_box(ax, _measurement_group_setup_lines(msmt_list), location="lower right")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_dynamic(
    msmt: MeasAdc,
    analysis: AnalysisAdcDynamic,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot sine fit, residual, and spectrum for one dynamic acquisition."""

    time_scale, time_unit = _time_scale(analysis.time_s)
    fig, axes = plt.subplots(3, 1, figsize=FULL_HD_FIGSIZE)
    axes[0].plot(analysis.time_s * time_scale, analysis.measured_dout, ".", markersize=2, label="Measured")
    axes[0].plot(analysis.time_s * time_scale, analysis.fitted_dout, linewidth=1.0, label="Sine fit")
    axes[0].set_xlabel(f"Time ({time_unit})")
    axes[0].set_ylabel("ADC output (LSB)")
    style_legend(axes[0])
    axes[1].plot(analysis.time_s * time_scale, analysis.residual_dout, linewidth=0.7)
    axes[1].set_xlabel(f"Time ({time_unit})")
    axes[1].set_ylabel("Residual (LSB)")
    positive = analysis.spectrum_frequency_hz > 0
    axes[2].semilogx(
        analysis.spectrum_frequency_hz[positive],
        analysis.spectrum_dbfs[positive],
        linewidth=0.8,
        label=f"SNDR {analysis.spectral_sndr_db:.2f} dB; ENOB {analysis.spectral_enob_bits:.2f} bit",
    )
    axes[2].set_xlabel("Frequency (Hz)")
    axes[2].set_ylabel("Amplitude (dBFS)")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    style_legend(axes[2])
    _add_info_box(axes[1], _measurement_setup_lines(msmt), location="lower right")
    fig.suptitle("ADC dynamic performance")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_dynamic_sweep(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcDynamicSweep,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot ENOB and SNDR versus input frequency for each conversion rate."""

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=FULL_HD_FIGSIZE)
    groups = np.unique(analysis.sample_rate_hz)
    for sample_rate_hz in groups:
        selected = analysis.sample_rate_hz == sample_rate_hz
        order = np.argsort(analysis.input_frequency_hz[selected])
        frequency = analysis.input_frequency_hz[selected][order]
        label = format_frequency_hz(sample_rate_hz)
        axes[0].semilogx(frequency, analysis.spectral_enob_bits[selected][order], marker="o", label=label)
        axes[1].semilogx(frequency, analysis.spectral_sndr_db[selected][order], marker="o", label=label)
    axes[0].set_ylabel("ENOB (bit)")
    axes[1].set_ylabel("SNDR (dB)")
    axes[1].set_xlabel("Input frequency (Hz)")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    style_legend(axes[0], title="Conversion rate")
    _add_info_box(axes[1], _measurement_group_setup_lines(msmt_list), location="lower right")
    fig.suptitle("ADC dynamic performance sweep")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_power_sweep(
    msmt_list: Sequence[MeasAdc],
    analysis: AnalysisAdcPowerSweep,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one source's static and dynamic rail power versus rate."""

    order = np.argsort(analysis.active_conversion_rate_hz)
    rate_msps = analysis.active_conversion_rate_hz[order] / 1e6
    component_labels = (
        "Digital static",
        "DAC static",
        "Analog static",
        "Digital dynamic",
        "DAC dynamic",
        "Analog dynamic",
    )
    component_power_uw = tuple(
        values[order] * 1e6
        for values in (
            analysis.vdd_d_static_power_w,
            analysis.vdd_dac_static_power_w,
            analysis.vdd_a_static_power_w,
            analysis.vdd_d_dynamic_power_w,
            analysis.vdd_dac_dynamic_power_w,
            analysis.vdd_a_dynamic_power_w,
        )
    )
    rail_colors = (RAIL_COLORS["vdd_d"], RAIL_COLORS["vdd_dac"], RAIL_COLORS["vdd_a"])
    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    collections = ax.stackplot(
        rate_msps,
        *component_power_uw,
        labels=component_labels,
        colors=(*rail_colors, *rail_colors),
    )
    for index, (collection, color) in enumerate(zip(collections, (*rail_colors, *rail_colors), strict=True)):
        collection.set_edgecolor(color)
        collection.set_linewidth(0.7)
        if index >= 3:
            collection.set_hatch("///")
    total_power_uw = analysis.total_power_w[order] * 1e6
    ax.plot(rate_msps, total_power_uw, color=TEXT_COLOR, linewidth=1.0)
    ax.set_ylabel("Supply power (µW)")
    ax.set_xlabel("Active conversion rate (MSPS)")
    ax.set_xlim(0.0, float(np.max(rate_msps)) + 0.25)
    if np.max(rate_msps) >= 1.0:
        ax.set_xticks(np.arange(1.0, np.floor(np.max(rate_msps)) + 1.0))
    ax.set_xticks(np.arange(0.0, float(np.max(rate_msps)) + 0.251, 0.25), minor=True)
    ax.set_ylim(0.0, max(float(np.max(total_power_uw)) * 1.25, 1.0))
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    _add_info_box(ax, _measurement_group_setup_lines(msmt_list), location="lower right")
    ax.set_title("ADC static and dynamic supply power")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_power_waveform(
    analysis: AnalysisAdcPowerWaveform,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot instantaneous rail power and sequencer timing for one conversion."""

    scale, unit = _time_scale(np.asarray((0.0, analysis.active_duration_s)))
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
        figsize=FULL_HD_FIGSIZE,
        gridspec_kw={"height_ratios": (1.0, 1.0, 1.0, 0.8)},
    )
    rail_labels = ("Analog", "Digital", "DAC")
    rail_names = ("vdd_a", "vdd_d", "vdd_dac")
    for index, (ax, label, rail) in enumerate(zip(axes[:3], rail_labels, rail_names, strict=True)):
        instantaneous_power_uw = analysis.rail_power_w[index] * 1e6
        static_power_uw = analysis.static_power_w[index] * 1e6
        active_power_uw = analysis.active_power_w[index] * 1e6
        color = RAIL_COLORS[rail]
        ax.plot(scaled_time, instantaneous_power_uw, color=color, linewidth=0.9, label="Instantaneous")
        ax.axhline(static_power_uw, color=NORD_DARK, linestyle=":", linewidth=1.0, label="Static average")
        ax.axhline(active_power_uw, color=NORD_ORANGE, linestyle="--", linewidth=1.0, label="Active average")
        ax.set_ylabel(f"{label} (µW)")
        ax.set_yscale("symlog", linthresh=linear_threshold_uw, linscale=0.6)
        ax.set_yticks(power_ticks)
        ax.set_ylim(-power_limit_uw, power_limit_uw)
        style_ax(ax)
        style_grid(ax)
        style_legend(ax, ncol=3)

    timing_ax = axes[3]
    timing_labels = ("INIT", "SAMP", "COMP", "LOGIC")
    for row, (label, high, color) in enumerate(zip(timing_labels, analysis.timing_high, CURVE_COLORS, strict=False)):
        timing_ax.step(scaled_time, row + 0.72 * high, where="post", color=color, linewidth=0.9)
    timing_ax.set_yticks(np.arange(len(timing_labels)) + 0.36, labels=timing_labels)
    timing_ax.set_ylim(-0.15, len(timing_labels) - 0.05)
    timing_ax.set_ylabel("Sequencer")
    timing_ax.set_xlabel(f"Time ({unit})")
    display_duration_scaled = analysis.active_duration_s * scale
    display_margin_scaled = 0.02 * display_duration_scaled
    timing_ax.set_xlim(-display_margin_scaled, display_duration_scaled + display_margin_scaled)
    timing_ax.set_xticks(np.linspace(0.0, display_duration_scaled, 6))
    style_ax(timing_ax)
    style_grid(timing_ax)

    setup_lines = [f"Source: {analysis.backend.upper()}"]
    if analysis.adc_index >= 0:
        setup_lines.append(f"ADC: {analysis.adc_index:02d}")
    setup_lines.append(f"Rate: {analysis.active_conversion_rate_hz / 1e6:g} MSPS")
    _add_info_box(axes[0], setup_lines)
    fig.suptitle("ADC instantaneous supply power")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_decision_paths(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot running SAR estimates for selected conversions."""

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    cycles = np.arange(analysis.estimate_dout.shape[1])
    for row, estimate in enumerate(analysis.estimate_dout):
        ax.plot(
            cycles,
            estimate,
            linewidth=0.8,
            color=CURVE_COLORS[0],
            label="Running estimate" if row == 0 else None,
        )
        ax.axhline(
            analysis.final_dout[row],
            linewidth=0.5,
            color=CURVE_COLORS[1],
            label="Final output" if row == 0 else None,
        )
    ax.set_xlabel("Decision cycle")
    ax.set_ylabel("Running estimate (LSB)")
    ax.set_title("ADC decision paths")
    style_ax(ax)
    ax.grid(False, which="both")
    style_legend(ax)
    _add_info_box(ax, _measurement_setup_lines(msmt), location="lower right")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_adc_decision_path_density(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot how frequently conversions follow each running SAR trajectory."""

    paths = analysis.estimate_dout
    cycles = np.arange(analysis.estimate_dout.shape[1], dtype=np.float64)
    substeps_per_decision = 8
    cycle_step = 1.0 / substeps_per_decision
    horizontal_bins = (len(cycles) - 1) * substeps_per_decision + 1
    cycle_edges = np.arange(horizontal_bins + 1, dtype=np.float64) * cycle_step
    fine_cycles = cycle_edges[:-1] + cycle_step / 2.0
    normalized_code_max = (1 << msmt.param.dut.adc_bits) - 1
    code_edges = np.arange(-0.5, normalized_code_max + 1.5, 1.0)
    count = np.zeros((len(cycle_edges) - 1, len(code_edges) - 1), dtype=np.float64)
    for first_row in range(0, len(paths), 10_000):
        path_chunk = paths[first_row : first_row + 10_000]
        # A SAR estimate is a discrete state, not a continuously changing
        # voltage. Hold each estimate through its decision interval and jump
        # to the next value exactly at the following integer cycle.
        held = np.repeat(path_chunk[:, :-1], substeps_per_decision, axis=1)
        held = np.concatenate((held, path_chunk[:, -1, None]), axis=1)
        path_count, _, _ = np.histogram2d(
            np.broadcast_to(fine_cycles, held.shape).ravel(),
            held.ravel(),
            bins=(cycle_edges, code_edges),
        )
        count += path_count

    # Draw transitions independently from the rectangular density cells. This
    # keeps each connector thin and places its endpoints exactly at the two
    # held estimates, without consuming or overlapping a fractional-cycle bin.
    transition_segments = []
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
            transition_segments.append(
                (
                    (float(cycle), float(transition[0])),
                    (float(cycle), float(transition[1])),
                )
            )
            transition_occupancies.append(float(occupancy))

    populated_count = np.ma.masked_equal(count.T, 0.0)
    nord_density = SPECTRUM_COLOR_MAP.copy()
    nord_density.set_bad(NORD_BLUE, alpha=1.0)
    density_norm = LogNorm(vmin=1, vmax=max(2, len(paths)))

    fig = plt.figure(figsize=FULL_HD_FIGSIZE)
    ax = fig.subplots()
    ax.set_facecolor(NORD_BLUE)
    mesh = ax.pcolormesh(
        cycle_edges,
        code_edges,
        populated_count,
        cmap=nord_density,
        norm=density_norm,
        shading="flat",
        rasterized=True,
    )
    if transition_segments:
        connectors = LineCollection(
            transition_segments,
            cmap=nord_density,
            norm=density_norm,
            linewidths=0.65,
            capstyle="butt",
            rasterized=True,
            zorder=3,
        )
        connectors.set_array(np.asarray(transition_occupancies))
        ax.add_collection(connectors)
    colorbar = fig.colorbar(mesh, ax=ax, pad=0.02)
    colorbar.set_label("Conversions per path")
    colorbar.ax.tick_params(colors=TEXT_COLOR)
    cast(Patch, colorbar.outline).set_edgecolor(SPINE_COLOR)
    colorbar.ax.yaxis.label.set_color(TEXT_COLOR)

    populated_min = int(np.floor(np.min(analysis.estimate_dout) + 0.5))
    populated_max = int(np.floor(np.max(analysis.estimate_dout) + 0.5))
    ax.set_xlim(-0.5, cycles[-1] + 0.5)
    ax.set_ylim(max(-0.5, populated_min - 8.5), min(normalized_code_max + 0.5, populated_max + 8.5))
    ax.set_xticks(cycles)
    ax.set_xticklabels(("Initial", *(str(cycle) for cycle in range(1, len(cycles)))))
    ax.set_xlabel("Decision cycle")
    ax.set_ylabel("Running estimate (LSB)")
    ax.set_title("ADC decision-path density")
    style_ax(ax)
    ax.set_facecolor(NORD_BLUE)
    ax.grid(False, which="both")
    _add_info_box(ax, _measurement_setup_lines(msmt))
    return _save_figure(fig, output_path)


@with_plot_style
def plot_comp_offset_noise(
    msmt_list: Sequence[MeasCompExt | MeasCompInt],
    analysis: AnalysisCompOffsetNoise,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot comparator decision probability versus differential input."""

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    ax.plot(
        analysis.vin_diff_v * 1e3,
        analysis.decision_probability,
        marker="o",
        color=CURVE_COLORS[0],
        label="Measured decisions",
    )
    ax.axhline(0.5, color=SPINE_COLOR, linewidth=0.6)
    if np.isfinite(analysis.offset_v):
        ax.axvline(
            analysis.offset_v * 1e3,
            color=CURVE_COLORS[1],
            linestyle="--",
            linewidth=0.8,
            label="50% threshold",
        )
    ax.set_xlabel("Differential input (mV)")
    ax.set_ylabel("Decision probability")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Comparator offset and input-referred noise")
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    _add_info_box(ax, _measurement_group_setup_lines(msmt_list), location="lower right")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_comp_sampling_campaign(
    msmt_list2d: Sequence[Sequence[MeasCompExt | MeasCompInt]],
    analysis_list: Sequence[AnalysisCompOffsetNoise],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one ADC's matched track/ hold curves over VDAC coupling."""

    grouped_results = {
        (float(group[0].param.requested_dac_rail_percent), group[0].param.sampling_mode): (
            group,
            analysis,
        )
        for group, analysis in zip(msmt_list2d, analysis_list, strict=True)
    }
    coupling_percentages = (0.0, 25.0, 50.0, 75.0, 100.0)
    fig, (curve_ax, violin_ax) = plt.subplots(1, 2, figsize=FULL_HD_FIGSIZE)
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
                s=9.0,
                color=color,
                marker=mode_markers[mode],
                edgecolors="none",
                zorder=2,
            )
            fit_input_v = np.linspace(
                float(np.min(analysis.vin_diff_v)),
                float(np.max(analysis.vin_diff_v)),
                1001,
            )
            fit_probability = ndtr(
                analysis.decision_polarity * (fit_input_v - analysis.offset_v) / analysis.noise_sigma_v
            )
            curve_ax.plot(
                fit_input_v * 1e3,
                fit_probability,
                linewidth=2.0,
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
                markersize=3.5,
                color=color,
            )

    curve_ax.axhline(0.5, color=SPINE_COLOR, linewidth=0.6)
    curve_ax.set_xlim(COMPARATOR_INPUT_ERROR_MINIMUM_MV, COMPARATOR_INPUT_ERROR_MAXIMUM_MV)
    curve_ax.set_xlabel("Differential input (mV)")
    curve_ax.set_ylabel("Decision probability")
    curve_ax.set_ylim(-0.02, 1.02)
    curve_ax.set_title("Comparator S-curves (CDF)")
    style_legend(curve_ax, title="VDAC coupling")

    violin_ax.set_xlim(-8.0, 108.0)
    violin_ax.set_ylim(COMPARATOR_INPUT_ERROR_MINIMUM_MV, COMPARATOR_INPUT_ERROR_MAXIMUM_MV)
    violin_ax.set_xticks(
        coupling_percentages,
        [f"{value:g}/{100.0 - value:g}" for value in coupling_percentages],
    )
    violin_ax.set_xlabel("VDAC coupling (P/N % of VDD_DAC)")
    violin_ax.set_ylabel("Input error (mV)")
    violin_ax.set_title("Gaussian fit of μ (threshold) and σ (noise)")
    style_legend(
        violin_ax,
        handles=(
            Patch(facecolor=LEGEND_FACE_COLOR, edgecolor=SPINE_COLOR, label="Track"),
            Patch(facecolor=LEGEND_FACE_COLOR, edgecolor=SPINE_COLOR, hatch="///", label="Hold"),
        ),
    )

    for ax in (curve_ax, violin_ax):
        style_ax(ax)
        style_grid(ax)
    _add_info_box(
        curve_ax,
        _measurement_group_setup_lines(tuple(msmt for group in msmt_list2d for msmt in group)),
    )
    fig.suptitle("Comparator threshold and input-referred noise versus VDAC coupling")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_comp_common_mode_campaign(
    msmt_list2d: Sequence[Sequence[MeasCompExt | MeasCompInt]],
    analysis_list: Sequence[AnalysisCompOffsetNoise],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one ADC's comparator response over common-mode input."""

    selected_results = [
        (group, analysis)
        for group, analysis in zip(msmt_list2d, analysis_list, strict=True)
        if COMMON_MODE_DISPLAY_MIN_V <= float(group[0].param.vin_cm.dc) <= COMMON_MODE_DISPLAY_MAX_V
    ]
    selected_results.sort(key=lambda result: float(result[0][0].param.vin_cm.dc))
    fig, (curve_ax, violin_ax) = plt.subplots(1, 2, figsize=FULL_HD_FIGSIZE)
    common_modes_v = []
    for group, analysis in selected_results:
        common_mode_v = float(group[0].param.vin_cm.dc)
        threshold_mv = analysis.offset_v * 1e3
        noise_mv = analysis.noise_sigma_v * 1e3
        gradient_position = (common_mode_v - COMMON_MODE_DISPLAY_MIN_V) / (
            COMMON_MODE_DISPLAY_MAX_V - COMMON_MODE_DISPLAY_MIN_V
        )
        color = COMMON_MODE_COLOR_MAP(float(np.clip(gradient_position, 0.0, 1.0)))
        common_modes_v.append(common_mode_v)

        curve_ax.scatter(
            analysis.vin_diff_v * 1e3,
            analysis.decision_probability,
            s=9.0,
            color=color,
            edgecolors="none",
            zorder=2,
        )

        valid_fit = (
            analysis.validity == "valid" and np.isfinite(threshold_mv) and np.isfinite(noise_mv) and noise_mv > 0.0
        )
        if valid_fit:
            fit_input_v = np.linspace(
                float(np.min(analysis.vin_diff_v)),
                float(np.max(analysis.vin_diff_v)),
                1001,
            )
            fit_probability = ndtr(
                analysis.decision_polarity * (fit_input_v - analysis.offset_v) / analysis.noise_sigma_v
            )
            curve_ax.plot(
                fit_input_v * 1e3,
                fit_probability,
                linewidth=2.0,
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
            violin_ax.plot(common_mode_v, threshold_mv, marker="o", markersize=4.0, color=color)
        else:
            curve_ax.plot(
                analysis.vin_diff_v * 1e3,
                analysis.decision_probability,
                linewidth=0.8,
                color=color,
                label=f"Vin_cm = {common_mode_v:.3g} V (fit invalid)",
                zorder=3,
            )

    curve_ax.axhline(0.5, color=SPINE_COLOR, linewidth=0.6)
    curve_ax.set_xlim(COMPARATOR_INPUT_ERROR_MINIMUM_MV, COMPARATOR_INPUT_ERROR_MAXIMUM_MV)
    curve_ax.set_ylim(-0.02, 1.02)
    curve_ax.set_xlabel("Differential input (mV)")
    curve_ax.set_ylabel("Decision probability")
    curve_ax.set_title("Comparator S-curve (CDF)")
    style_legend(curve_ax, loc="lower right")

    violin_ax.set_xlim(
        min(common_modes_v) - 0.05,
        max(common_modes_v) + 0.05,
    )
    violin_ax.set_ylim(COMPARATOR_INPUT_ERROR_MINIMUM_MV, COMPARATOR_INPUT_ERROR_MAXIMUM_MV)
    violin_ax.set_xticks(common_modes_v, [f"{value:.1f}" for value in common_modes_v])
    violin_ax.set_xlabel("Common-mode input (V)")
    violin_ax.set_ylabel("Input error (mV)")
    violin_ax.set_title("Gaussian fit of μ (threshold) and σ (noise)")

    for ax in (curve_ax, violin_ax):
        style_ax(ax)
        style_grid(ax)
    _add_info_box(
        curve_ax,
        _measurement_group_setup_lines(tuple(msmt for group in msmt_list2d for msmt in group)),
    )
    fig.suptitle("Comparator threshold and input-referred noise versus common mode")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_cdac_cap_mismatch(
    msmt_list: Sequence[MeasCdacExt],
    analysis: AnalysisCdacCapMismatch,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot one ADC's normalized A-to-B main/diff weights and diagnostics."""

    elements = np.arange(1, analysis.effective_fraction.shape[1] + 1)
    expected_effective = analysis.expected_effective_fraction
    fig, axes_grid = plt.subplots(2, 3, sharex=True, figsize=FULL_HD_FIGSIZE)
    axes = axes_grid.ravel()
    for side, label, color in ((0, "P", CURVE_COLORS[0]), (1, "N", CURVE_COLORS[1])):
        axes[0].plot(
            elements,
            analysis.effective_fraction[side],
            "o-",
            color=color,
            label=label,
        )
        axes[1].plot(
            elements,
            analysis.effective_fraction[side] - expected_effective,
            "o-",
            color=color,
            label=label,
        )
        axes[3].plot(elements, analysis.main_fraction[side], "o-", color=color, label=f"{label} main")
        axes[3].plot(
            elements,
            analysis.diff_fraction[side],
            "s--",
            color=color,
            label=f"{label} diff",
        )
        axes[4].plot(
            elements,
            analysis.direction_bias[side, :, 0],
            marker="o",
            linestyle="-" if side == 0 else "--",
            color=color,
            label=f"{label}, main+diff",
        )
        axes[4].plot(
            elements,
            analysis.direction_bias[side, :, 1],
            marker="s",
            linestyle="-" if side == 0 else "--",
            color=color,
            label=f"{label}, main−diff",
        )
        axes[5].plot(
            elements,
            2.0 * analysis.diff_fraction[side],
            "o-",
            color=color,
            label=label,
        )
    axes[0].plot(elements, expected_effective, "k--", linewidth=0.8, label="Ideal/PEX")
    axes[2].plot(
        elements,
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
    tick_positions = (1, 4, 7, 10, 13, 16)
    tick_labels = ("C16", "C13", "C10", "C07", "C04", "C01")
    for ax, title, ylabel in zip(axes, panel_titles, ylabels, strict=True):
        ax.set_title(title, fontsize=11.0)
        ax.set_ylabel(ylabel)
        ax.set_xticks(tick_positions, tick_labels)
        style_ax(ax)
        style_grid(ax)
        style_legend(ax)
    _add_info_box(axes[2], _measurement_group_setup_lines(msmt_list), location="lower right")
    fig.supxlabel("Physical capacitor element")
    fig.suptitle("A-to-B CDAC capacitance")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_cdac_cap_mismatch_comparison(
    msmt_list2d: Sequence[Sequence[MeasCdacExt]],
    analysis_list: Sequence[AnalysisCdacCapMismatch],
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Compare normalized A-to-B CDAC extraction across ADC00–ADC03."""

    fig, axes_grid = plt.subplots(2, 2, sharex=True, figsize=FULL_HD_FIGSIZE)
    axes = axes_grid.ravel()
    aligned = sorted(zip(msmt_list2d, analysis_list, strict=True), key=lambda item: item[1].adc_index)
    elements = np.arange(1, analysis_list[0].effective_fraction.shape[1] + 1)
    for group, analysis in aligned:
        expected = analysis.expected_effective_fraction
        effective_mean = (analysis.effective_fraction[0] + analysis.effective_fraction[1]) / 2.0
        diffcap_separation_mean = analysis.diff_fraction[0] + analysis.diff_fraction[1]
        label = f"ADC{analysis.adc_index:02d}"
        color = CURVE_COLORS[analysis.adc_index]
        axes[0].plot(elements, effective_mean, "o-", color=color, label=label)
        axes[1].plot(elements, effective_mean - expected, "o-", color=color, label=label)
        axes[2].plot(
            elements,
            analysis.effective_fraction[0] - analysis.effective_fraction[1],
            "o-",
            color=color,
            label=label,
        )
        axes[3].plot(elements, diffcap_separation_mean, "o-", color=color, label=label)

    panel_titles = (
        "Mean P/N effective fraction",
        "Residual from ideal/PEX",
        "P−N effective asymmetry",
        "Mean P/N diffcap separation",
    )
    ylabels = ("Fraction", "Residual", "Asymmetry", "Separation")
    tick_positions = (1, 4, 7, 10, 13, 16)
    tick_labels = ("C16", "C13", "C10", "C07", "C04", "C01")
    for ax, title, ylabel in zip(axes, panel_titles, ylabels, strict=True):
        ax.axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
        ax.set_title(title, fontsize=11.0)
        ax.set_ylabel(ylabel)
        ax.set_xticks(tick_positions, tick_labels)
        style_ax(ax)
        style_grid(ax)
    style_legend(axes[0])
    _add_info_box(
        axes[3],
        _measurement_group_setup_lines(tuple(msmt for group in msmt_list2d for msmt in group)),
        location="lower right",
    )
    fig.supxlabel("Physical capacitor element")
    fig.suptitle("A-to-B CDAC comparison")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_comp_timing(
    msmt_list: Sequence[MeasCompInt],
    analysis: AnalysisCompTiming,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot comparator delay, settling time, and unresolved outcomes."""

    fig, axes = plt.subplots(2, 1, figsize=FULL_HD_FIGSIZE)
    axes[0].plot(analysis.trial_index, analysis.clock_to_decision_s * 1e9, "o", label="Clock to decision")
    axes[0].plot(analysis.trial_index, analysis.settling_s * 1e9, "o", label="Settling")
    axes[0].set_ylabel("Time (ns)")
    style_legend(axes[0])
    axes[1].step(analysis.trial_index, analysis.unresolved, where="mid")
    axes[1].set_ylabel("Unresolved")
    axes[1].set_xlabel("Trial index")
    axes[1].set_yticks((0, 1))
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    _add_info_box(axes[1], _measurement_group_setup_lines(msmt_list), location="lower right")
    fig.suptitle("Comparator timing")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_comp_power(
    msmt_list: Sequence[MeasCompInt],
    analysis: AnalysisCompPower,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot comparator average power per measurement."""

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    labels = [str(index) for index in analysis.source_index]
    ax.bar(labels, analysis.average_power_w * 1e6)
    ax.set_ylabel("Average power (µW)")
    ax.set_xlabel("Measurement index")
    style_ax(ax)
    style_grid(ax)
    _add_info_box(ax, _measurement_group_setup_lines(msmt_list))
    fig.suptitle("Comparator power")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_comp_candidate_sweep(
    msmt_list: Sequence[MeasCompInt],
    analysis: AnalysisCompCandidateSweep,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot candidate noise, power, and settling on one area-ordered axis."""

    candidate_count = len(analysis.candidate_id)
    position = np.arange(candidate_count)
    colors = {
        "half": CURVE_COLORS[0],
        "double": CURVE_COLORS[1],
        "fabricated": CURVE_COLORS[2],
    }
    fig, axes = plt.subplots(3, 1, sharex=True, figsize=FULL_HD_FIGSIZE)
    metrics = (
        (analysis.noise_sigma_v * 1e3, "Noise σ (mV)", "linear"),
        (analysis.average_power_w * 1e6, "Power (µW)", "log"),
        (analysis.maximum_settling_s * 1e9, "Settling (ns)", "linear"),
    )
    for ax, (values, ylabel, scale) in zip(axes, metrics, strict=True):
        for profile in ("half", "double", "fabricated"):
            selected = np.asarray(analysis.size_profile) == profile
            if not np.any(selected):
                continue
            ax.scatter(
                position[selected],
                values[selected],
                s=14 if profile != "fabricated" else 52,
                marker="o" if profile != "fabricated" else "*",
                color=colors[profile],
                label={"half": "0.5× FRIDA widths", "double": "2× FRIDA widths", "fabricated": "FRIDA baseline"}[
                    profile
                ],
                zorder=4 if profile == "fabricated" else 2,
            )
        ax.set_ylabel(ylabel)
        ax.set_yscale(scale)
        style_ax(ax)
        style_grid(ax)

    baseline = np.flatnonzero(np.asarray(analysis.size_profile) == "fabricated")
    for ax in axes:
        ax.axvline(baseline[0], color=CURVE_COLORS[2], linestyle="--", linewidth=0.8)
    style_legend(axes[0], ncol=3)

    tick_count = min(12, candidate_count)
    tick_positions = np.unique(np.rint(np.linspace(0, candidate_count - 1, tick_count)).astype(int))
    axes[-1].set_xticks(tick_positions)
    axes[-1].set_xticklabels(tuple(f"{index}\n{analysis.total_active_area_um2[index]:.2f}" for index in tick_positions))
    axes[-1].set_xlabel("Area-ordered candidate index\n(total instantiated MOS Σ(W×L) in µm²)")
    axes[-1].set_xlim(-2, candidate_count + 1)
    _add_info_box(axes[2], _measurement_group_setup_lines(msmt_list), location="lower right")
    fig.suptitle("Comparator candidate noise, power, and settling")
    return _save_figure(fig, output_path)


@with_plot_style
def plot_comp_noise_power_tradeoff(
    analysis: AnalysisCompCandidateSweep,
    *,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot valid, resolved candidate noise against power, colored by settling."""

    noise_mv = analysis.noise_sigma_v * 1e3
    power_uw = analysis.average_power_w * 1e6
    settling_ns = analysis.maximum_settling_s * 1e9
    valid_scurve = np.asarray(analysis.validity) == "valid"
    finite_positive = (
        np.isfinite(noise_mv)
        & np.isfinite(power_uw)
        & np.isfinite(settling_ns)
        & (noise_mv > 0.0)
        & (power_uw > 0.0)
        & (settling_ns > 0.0)
    )
    resolved = analysis.unresolved_fraction == 0.0
    selected = valid_scurve & finite_positive & resolved
    selected_settling_ns = settling_ns[selected]
    color_min = float(np.min(selected_settling_ns))
    color_max = float(np.max(selected_settling_ns))
    if np.isclose(color_min, color_max):
        color_max = color_min + 1.0
    color_norm = Normalize(vmin=color_min, vmax=color_max)
    profiles = np.asarray(analysis.size_profile)

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    mappable = ScalarMappable(norm=color_norm, cmap=COMP_SETTLING_COLOR_MAP)
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
            cmap=COMP_SETTLING_COLOR_MAP,
            norm=color_norm,
            marker=marker,
            s=30,
            edgecolors=SPINE_COLOR,
            linewidths=0.35,
            label=label,
            zorder=2,
        )
    baseline = np.flatnonzero(profiles == "fabricated")
    baseline_index = int(baseline[0])
    ax.scatter(
        noise_mv[baseline_index],
        power_uw[baseline_index],
        marker="*",
        s=180,
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
        color=TEXT_COLOR,
    )

    colorbar = fig.colorbar(mappable, ax=ax, pad=0.02)
    colorbar.set_label("Worst settling time (ns)")
    colorbar.ax.tick_params(colors=TEXT_COLOR)
    cast(Patch, colorbar.outline).set_edgecolor(SPINE_COLOR)
    colorbar.ax.yaxis.label.set_color(TEXT_COLOR)

    ax.set_yscale("log")
    ax.set_xlabel("Input-referred noise σ (mV)")
    ax.set_ylabel("Average power (µW)")
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    fig.suptitle("Comparator noise–power trade-off")
    return _save_figure(fig, output_path)
