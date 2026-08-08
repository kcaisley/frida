"""Plots of typed FRIDA measurements and analysis results."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from functools import wraps
from pathlib import Path
from typing import cast

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import AutoMinorLocator, NullLocator
from PIL import Image
from scipy.special import ndtr

from flow.analysis.types import (
    AnalysisAdcCodeDistribution,
    AnalysisAdcDecisionPaths,
    AnalysisAdcDynamic,
    AnalysisAdcDynamicSweep,
    AnalysisAdcNoiseSweep,
    AnalysisAdcNonlinearity,
    AnalysisAdcPowerSweep,
    AnalysisAdcTransfer,
    AnalysisCdacCapMismatch,
    AnalysisCompOffsetNoise,
    AnalysisCompPower,
    AnalysisCompTiming,
    MeasAdc,
    MeasCdacExt,
    MeasCompExt,
    MeasCompInt,
    Measurement,
)
from flow.scans.params import load_board_map

DEFAULT_FORMATS = ("png", "pdf", "svg")
PNG_DPI = 200
FULL_HD_FIGSIZE = (9.6, 5.4)
DETAILED_16_9_FIGSIZE = (16.0, 9.0)
COMMON_MODE_DISPLAY_MIN_V = 0.7
COMMON_MODE_DISPLAY_MAX_V = 1.2
COMPARATOR_INPUT_ERROR_MINIMUM_MV = 0.0
COMPARATOR_INPUT_ERROR_MAXIMUM_MV = 25.0

# Nord presentation colors. The ordering gives all plots a stable semantic
# sequence instead of inheriting Matplotlib's version-dependent default cycle.
PLOT_FACE_COLOR = "white"
TEXT_COLOR = "#2E3440"
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
SAMPLING_TRACK_COLORS = ("#B7C9DF", "#8FAAC9", NORD_BLUE, "#486C99", "#34547C")
SAMPLING_HOLD_COLORS = ("#E7B8BC", "#D78E96", NORD_RED, "#A64E58", "#873B47")
COMMON_MODE_COLOR_MAP = LinearSegmentedColormap.from_list(
    "common_mode_nord_blue_to_red",
    (NORD_BLUE, NORD_RED),
)
NORD_COLORS = (
    NORD_BLUE,
    NORD_RED,
    NORD_GREEN,
    NORD_ORANGE,
    NORD_PURPLE,
    NORD_CYAN,
    NORD_YELLOW,
    NORD_TEAL,
    NORD_LIGHT_BLUE,
    NORD_DARK,
)
TIMING_COLORS = {
    12.5: NORD_DARK,
    25.0: NORD_BLUE,
    37.5: NORD_GREEN,
    50.0: NORD_RED,
    62.5: NORD_ORANGE,
    75.0: NORD_PURPLE,
    87.5: NORD_CYAN,
}
PLOT_STYLE = {
    "text.usetex": False,
    "mathtext.fontset": "cm",
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman", "DejaVu Serif"],
    "font.size": 10.0,
    "axes.titlesize": 13.0,
    "axes.titleweight": "normal",
    "axes.labelsize": 11.0,
    "axes.labelcolor": TEXT_COLOR,
    "axes.edgecolor": SPINE_COLOR,
    "axes.linewidth": 0.8,
    "axes.facecolor": PLOT_FACE_COLOR,
    "axes.prop_cycle": plt.cycler(color=NORD_COLORS),
    "xtick.color": TEXT_COLOR,
    "xtick.labelsize": 9.0,
    "ytick.color": TEXT_COLOR,
    "ytick.labelsize": 9.0,
    "text.color": TEXT_COLOR,
    "figure.facecolor": PLOT_FACE_COLOR,
    "figure.titlesize": 13.0,
    "figure.titleweight": "normal",
    "savefig.facecolor": PLOT_FACE_COLOR,
    "savefig.dpi": PNG_DPI,
    "legend.facecolor": LEGEND_FACE_COLOR,
    "legend.edgecolor": SPINE_COLOR,
    "legend.framealpha": 0.9,
    "legend.fontsize": 9.0,
    "legend.title_fontsize": 9.0,
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
    positions = {
        "upper right": (0.98, 0.98, "right", "top"),
        "upper left": (0.02, 0.98, "left", "top"),
        "lower right": (0.98, 0.02, "right", "bottom"),
        "lower left": (0.02, 0.02, "left", "bottom"),
    }
    if location not in positions:
        raise ValueError(f"unknown info-box location {location!r}")
    x, y, horizontal, vertical = positions[location]
    ax.text(
        x,
        y,
        "\n".join(lines),
        transform=ax.transAxes,
        horizontalalignment=horizontal,
        verticalalignment=vertical,
        fontsize="small",
        color=TEXT_COLOR,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": LEGEND_FACE_COLOR,
            "edgecolor": SPINE_COLOR,
            "alpha": 0.9,
            "linewidth": 0.8,
        },
    )


def _save_figure(
    fig: plt.Figure,
    output_path: Path,
    formats: Sequence[str],
    *,
    exact_canvas: bool = False,
) -> tuple[Path, ...]:
    output_path = Path(output_path)
    if output_path.suffix:
        formats = (output_path.suffix.lstrip("."),)
        output_path = output_path.with_suffix("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.patch.set_facecolor(PLOT_FACE_COLOR)
    fig.tight_layout()
    paths = []
    bbox_inches = None if exact_canvas else "tight"
    for output_format in formats:
        path = output_path.with_suffix(f".{output_format}")
        if output_format.lower() == "png":
            fig.savefig(
                path,
                facecolor=PLOT_FACE_COLOR,
                dpi=PNG_DPI,
                bbox_inches=bbox_inches,
            )
        else:
            fig.savefig(
                path,
                facecolor=PLOT_FACE_COLOR,
                bbox_inches=bbox_inches,
            )
        paths.append(path)
    plt.close(fig)
    return tuple(paths)


def _measurement_lines(msmt: Measurement) -> tuple[str, ...]:
    lines = (
        f"Backend: {msmt.info.backend}",
        f"Datetime: {msmt.info.timestamp_utc.strftime('%Y-%m-%d %H:%M')}",
    )
    board_id = getattr(msmt.param, "board_id", None)
    observed_adc = getattr(msmt.param, "observed_adc", None)
    if board_id is not None:
        lines += (f"Board: {board_id}",)
    if observed_adc is not None:
        lines += (f"ADC: {observed_adc:02d}",)
    return lines


def _measurement_group_lines(measurements: Sequence[Measurement]) -> tuple[str, ...]:
    """Summarize the shared and swept context of several measurements."""

    if not measurements:
        raise ValueError("measurement plot requires at least one measurement")
    first = measurements[0]
    backends = sorted({msmt.info.backend for msmt in measurements})
    lines = (
        f"Backend: {', '.join(backends)}",
        f"Datetime: {first.info.timestamp_utc.strftime('%Y-%m-%d %H:%M')}",
    )
    board_ids = sorted(
        {str(board_id) for msmt in measurements if (board_id := getattr(msmt.param, "board_id", None)) is not None}
    )
    if board_ids:
        lines += (f"Board: {', '.join(board_ids)}",)
    observed_adcs = sorted(
        {
            int(observed_adc)
            for msmt in measurements
            if (observed_adc := getattr(msmt.param, "observed_adc", None)) is not None
        }
    )
    if observed_adcs:
        lines += (f"ADCs: {', '.join(f'{adc:02d}' for adc in observed_adcs)}",)
    return lines


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
def plot_measurement_waveforms(
    msmt: Measurement,
    *,
    record_index: int = 0,
    signal_names: Sequence[str] | None = None,
    info_lines: Sequence[str] = (),
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot selected dense waveform signals from one measurement record."""

    if msmt.wave is None:
        raise ValueError("measurement does not contain a commissioned waveform")
    record_ids = getattr(msmt.wave, "conversion_index", None)
    if record_ids is None:
        record_ids = msmt.wave.trial_index
    if not 0 <= record_index < len(cast(Sequence[int], record_ids)):
        raise IndexError("waveform record_index is outside the measurement")
    names = tuple(
        field_name
        for field_name in msmt.wave.__dataclass_fields__
        if field_name not in {"conversion_index", "trial_index", "time_s"}
    )
    if signal_names is not None:
        missing = sorted(set(signal_names).difference(names))
        if missing:
            raise ValueError(f"measurement has no waveform signals {missing}")
        names = tuple(signal_names)

    scale, unit = _time_scale(msmt.wave.time_s)
    fig, axes = plt.subplots(len(names), 1, sharex=True, figsize=(9.0, max(2.8, 2.1 * len(names))))
    axes = np.atleast_1d(axes)
    for ax, name in zip(axes, names, strict=True):
        ax.plot(msmt.wave.time_s * scale, getattr(msmt.wave, name)[record_index], linewidth=1.0)
        ax.set_ylabel(name)
        style_ax(ax)
        style_grid(ax)
    axes[-1].set_xlabel(f"Time ({unit})")
    _add_info_box(axes[0], (*info_lines, *_measurement_lines(msmt)))
    fig.suptitle(f"{type(msmt).__name__} waveform record {record_index}")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_transfer(
    measurements: Sequence[MeasAdc],
    analysis: AnalysisAdcTransfer,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot individual ADC conversions and the mean static transfer."""

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    inputs = np.concatenate([msmt.daq.vin_diff_v for msmt in measurements])
    dout = np.concatenate([msmt.daq.dout for msmt in measurements])
    ax.scatter(inputs * 1e3, dout, s=5, alpha=0.15, label="Conversions")
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
    _add_info_box(ax, _measurement_group_lines(measurements), location="lower right")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_nonlinearity(
    msmt: MeasAdc,
    analysis: AnalysisAdcNonlinearity,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot ADC DNL and INL from one typed nonlinearity result."""

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8.5, 6.2))
    axes[0].plot(analysis.code, analysis.dnl, linewidth=0.9)
    axes[0].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    axes[0].set_ylabel("DNL (LSB)")
    axes[1].plot(analysis.code, analysis.inl, linewidth=0.9)
    axes[1].axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
    axes[1].set_ylabel("INL (LSB)")
    axes[1].set_xlabel("Output code")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    _add_info_box(
        axes[0],
        (
            f"Method: {analysis.method}",
            f"max |DNL|: {analysis.maximum_abs_dnl:.3g} LSB",
            f"max |INL|: {analysis.maximum_abs_inl:.3g} LSB",
            f"Missing codes: {analysis.missing_codes}",
            *_measurement_lines(msmt),
        ),
    )
    fig.suptitle("ADC static nonlinearity")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_code_distribution(
    measurements: Sequence[MeasAdc],
    analysis: AnalysisAdcCodeDistribution,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot code histograms and standard deviation at static input points."""

    fig, axes = plt.subplots(2, 1, figsize=(8.5, 7.0))
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
    _add_info_box(axes[1], _measurement_group_lines(measurements), location="upper left")
    fig.suptitle("ADC output-code distribution")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_noise_sweep(
    measurements: Sequence[MeasAdc],
    analysis: AnalysisAdcNoiseSweep,
    *,
    output_path: Path,
    quadratic_guide: bool = False,
    series_labels: Sequence[str] | None = None,
    title: str = "ADC noise performance vs conversion rate",
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot noise, equivalent full-scale SNR, and ENOB on one rate panel.

    A quadratic guide is useful for comparing sparse SPICE sweeps with the
    densely measured physical trend. With exactly three rates it is an
    interpolation, not an independently validated predictive model.
    """

    if series_labels is not None and len(series_labels) != len(analysis.sample_rate_hz):
        raise ValueError("series_labels must contain one label per noise-sweep point")
    if not np.isfinite(analysis.input_lsb_v) or analysis.input_lsb_v <= 0.0:
        raise ValueError("noise-sweep plot requires a finite positive input LSB")

    # The SNR and ENOB axes use a full-scale sine whose peak-to-peak
    # range is the ADC input range represented by all output codes.
    adc_bits = measurements[0].param.dut.adc_bits
    full_scale_rms_lsb = ((1 << adc_bits) - 1) / (2.0 * np.sqrt(2.0))
    noise_rms_v = np.asarray(analysis.input_referred_noise_rms_v)
    if np.any(~np.isfinite(noise_rms_v)) or np.any(noise_rms_v < 0.0):
        raise ValueError("noise-sweep plot requires finite nonnegative input-referred noise")
    noise_rms_lsb = noise_rms_v / analysis.input_lsb_v

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    conversion_rate_msps = analysis.sample_rate_hz / 1e6
    if series_labels is None:
        labels = tuple(f"{value:g}%" for value in np.unique(analysis.comparator_time_percent))
        selections = tuple(
            analysis.comparator_time_percent == value for value in np.unique(analysis.comparator_time_percent)
        )
        colors = tuple(
            TIMING_COLORS.get(float(value), NORD_DARK) for value in np.unique(analysis.comparator_time_percent)
        )
    else:
        labels = tuple(dict.fromkeys(series_labels))
        label_values = np.asarray(series_labels)
        selections = tuple(label_values == label for label in labels)
        colors = tuple(NORD_COLORS[index % len(NORD_COLORS)] for index in range(len(labels)))

    for label, selected, color in zip(labels, selections, colors, strict=True):
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
        if quadratic_guide and len(np.unique(selected_rate)) >= 3:
            coefficients = np.polyfit(selected_rate, selected_noise_lsb, deg=2)
            fit_rate = np.linspace(float(selected_rate[0]), float(selected_rate[-1]), 200)
            fit_label = "Quadratic guide (3 points)" if len(selected_rate) == 3 else "Quadratic fit"
            ax.plot(
                fit_rate,
                np.polyval(coefficients, fit_rate),
                linestyle="--",
                linewidth=1.2,
                color=color,
                alpha=0.8,
                label=fit_label,
            )
    ax.set_xlabel("Active conversion rate (Msps)")
    ax.set_ylabel("Input-referred noise (LSB RMS)")
    ax.invert_yaxis()
    ax.set_ylim(10.25, -0.25)
    ax.set_yticks(np.arange(0.0, 11.0, 1.0))
    ax.set_xticks(np.arange(0.0, 11.0, 1.0))
    ax.set_xlim(0.0, 10.25)
    ax.set_xticks(np.arange(0.0, 10.251, 0.25), minor=True)
    ax.set_title(title)
    style_ax(ax)
    ax.tick_params(which="both", right=False)
    style_grid(ax)
    style_legend(
        ax,
        ncol=4 if series_labels is None else 1,
        title="COMP→LOGIC interval\n(as % of decision cycle)" if series_labels is None else None,
        loc="lower left" if series_labels is not None else "upper left",
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
    info_lines = _measurement_group_lines(measurements)
    vin_diff_dc = getattr(measurements[0].param.vin_diff, "dc", None)
    vin_cm_dc = getattr(measurements[0].param.vin_cm, "dc", None)
    if vin_diff_dc is not None and all(
        getattr(msmt.param.vin_diff, "dc", None) == vin_diff_dc for msmt in measurements
    ):
        info_lines += (f"Vdiff: {float(vin_diff_dc) * 1e3:g} mV DC",)
    if vin_cm_dc is not None and all(getattr(msmt.param.vin_cm, "dc", None) == vin_cm_dc for msmt in measurements):
        info_lines += (f"Vcm: {float(vin_cm_dc) * 1e3:g} mV",)
    _add_info_box(ax, info_lines, location="lower right")
    return _save_figure(fig, output_path, formats, exact_canvas=True)


@with_plot_style
def plot_adc_noise_distribution_sweep(
    measurements: Sequence[MeasAdc],
    analysis: AnalysisAdcNoiseSweep,
    *,
    output_path: Path,
    title: str | None = None,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot left-facing output-code histograms along the conversion-rate axis."""

    if analysis.code is None or analysis.count is None:
        raise ValueError("noise-distribution plot requires per-rate histogram counts")
    if analysis.count.shape != (len(analysis.sample_rate_hz), len(analysis.code)):
        raise ValueError("noise-distribution histogram dimensions do not match its rates and codes")
    observed_adcs = {msmt.param.observed_adc for msmt in measurements}
    if len(observed_adcs) != 1:
        raise ValueError("noise-distribution plot requires measurements from one ADC")

    order = np.argsort(analysis.sample_rate_hz)
    rates_msps = analysis.sample_rate_hz[order] / 1e6
    if len(np.unique(rates_msps)) != len(rates_msps):
        raise ValueError("noise-distribution plot requires one histogram per conversion rate")
    counts = analysis.count[order]
    populated = np.flatnonzero(np.any(counts > 0, axis=0))
    if not len(populated):
        raise ValueError("noise-distribution plot has no populated output codes")
    first_code = max(0, int(populated[0]) - 2)
    last_code = min(len(analysis.code) - 1, int(populated[-1]) + 2)
    codes = analysis.code[first_code : last_code + 1]
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
            facecolor=to_rgba(NORD_BLUE, 0.25),
            edgecolor=NORD_BLUE,
            linewidth=0.45,
        )
    mean = analysis.mean_dout[order]
    std = analysis.std_dout[order]
    if std[0] <= 0.0:
        raise ValueError("noise-distribution plot requires nonzero variation at its lowest rate")
    ax.plot(rates_msps, mean, color=NORD_RED, linewidth=1.2, marker="o", markersize=2.5, label="Mean")
    ax.plot(rates_msps, mean - std, color=NORD_ORANGE, linewidth=0.9, linestyle="--", label="Mean ±1σ")
    ax.plot(rates_msps, mean + std, color=NORD_ORANGE, linewidth=0.9, linestyle="--")
    ax.set_xlabel("Active conversion rate (Msps)")
    ax.set_ylabel("ADC output code (LSB)")
    ax.set_xticks(np.arange(0.0, 11.0, 1.0))
    ax.set_xticks(np.arange(0.0, 10.251, 0.25), minor=True)
    ax.set_xlim(0.0, 10.25)
    ax.set_ylim(mean[0] - 3.0 * std[0], mean[0] + 3.0 * std[0])
    adc_index = next(iter(observed_adcs))
    adc_label = "ADC" if adc_index is None else f"ADC{adc_index:02d}"
    ax.set_title(title or f"{adc_label} fixed-input output-code distributions")
    style_ax(ax)
    style_grid(ax)
    style_legend(ax, loc="upper left")
    _add_info_box(
        ax,
        (
            f"Global histogram scale: {histogram_scale:,} conversions",
            *_measurement_group_lines(measurements),
        ),
        location="upper right",
    )
    return _save_figure(fig, output_path, formats, exact_canvas=True)


@with_plot_style
def plot_adc_noise_violin_sweep(
    measurements: Sequence[MeasAdc],
    analysis: AnalysisAdcNoiseSweep,
    *,
    output_path: Path,
    title: str | None = None,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot KDE violins with exact per-LSB count boxes at each conversion rate."""

    if analysis.code is None or analysis.count is None:
        raise ValueError("noise-violin plot requires per-rate histogram counts")
    if len(measurements) != len(analysis.sample_rate_hz):
        raise ValueError("noise-violin measurements and analysis must have equal lengths")
    observed_adcs = {msmt.param.observed_adc for msmt in measurements}
    if len(observed_adcs) != 1:
        raise ValueError("noise-violin plot requires measurements from one ADC")

    order = np.argsort(analysis.sample_rate_hz)
    rates_msps = analysis.sample_rate_hz[order] / 1e6
    if len(np.unique(rates_msps)) != len(rates_msps):
        raise ValueError("noise-violin plot requires one distribution per conversion rate")
    distributions = [measurements[index].daq.dout for index in order]
    if any(len(np.unique(values)) < 2 for values in distributions):
        raise ValueError("noise-violin KDE requires at least two output codes at every rate")
    positions = np.arange(len(rates_msps), dtype=np.float64)

    fig, ax = plt.subplots(figsize=FULL_HD_FIGSIZE)
    parts = ax.violinplot(
        distributions,
        positions,
        points=60,
        widths=0.7,
        showmeans=True,
        showextrema=True,
        showmedians=False,
        bw_method=0.5,
    )
    for body in parts["bodies"]:
        body.set_facecolor(to_rgba(NORD_CYAN, 0.14))
        body.set_edgecolor("none")
        body.set_linewidth(0.0)
        body.set_alpha(1.0)
    for name, color, linewidth in (
        ("cmeans", NORD_RED, 1.2),
        ("cmins", NORD_DARK, 0.7),
        ("cmaxes", NORD_DARK, 0.7),
        ("cbars", NORD_DARK, 0.7),
    ):
        parts[name].set_color(color)
        parts[name].set_linewidth(linewidth)

    maximum_count = int(np.max(analysis.count))
    histogram_scale = int(np.ceil(maximum_count / 10_000.0) * 10_000)
    for position, histogram in zip(positions, analysis.count[order], strict=True):
        populated_codes = histogram > 0
        widths = 0.7 * histogram[populated_codes] / histogram_scale
        ax.barh(
            analysis.code[populated_codes],
            widths,
            left=position - widths / 2.0,
            height=0.88,
            facecolor=to_rgba(NORD_BLUE, 0.58),
            edgecolor=to_rgba(NORD_DARK, 0.9),
            linewidth=0.4,
            zorder=2,
        )

    integer_rates = np.flatnonzero(np.isclose(rates_msps, np.round(rates_msps)) & (rates_msps >= 1.0))
    ax.set_xticks(integer_rates)
    ax.set_xticklabels(tuple(f"{rates_msps[index]:g}" for index in integer_rates))
    ax.set_xticks(positions, minor=True)
    ax.set_xlim(-0.8, float(positions[-1]) + 0.8)
    low_rate_mean = analysis.mean_dout[order][0]
    low_rate_std = analysis.std_dout[order][0]
    if low_rate_std <= 0.0:
        raise ValueError("noise-violin plot requires nonzero variation at its lowest rate")
    ax.set_ylim(low_rate_mean - 3.0 * low_rate_std, low_rate_mean + 3.0 * low_rate_std)
    ax.set_xlabel("Active conversion rate (Msps)")
    ax.set_ylabel("ADC output code (LSB)")
    adc_index = next(iter(observed_adcs))
    adc_label = "ADC" if adc_index is None else f"ADC{adc_index:02d}"
    ax.set_title(title or f"{adc_label} fixed-input output-code violin distributions")
    style_ax(ax)
    style_grid(ax)
    style_legend(
        ax,
        handles=(
            Patch(facecolor=to_rgba(NORD_CYAN, 0.14), edgecolor="none", label="KDE (bandwidth 0.5)"),
            Patch(facecolor=to_rgba(NORD_BLUE, 0.58), edgecolor=NORD_DARK, label="Exact LSB counts"),
            Line2D((), (), color=NORD_RED, linewidth=1.2, label="Mean"),
            Line2D((), (), color=NORD_DARK, linewidth=0.7, label="Extrema"),
        ),
        loc="upper left",
        ncol=3,
    )
    _add_info_box(
        ax,
        (
            f"Global LSB-bin scale: {histogram_scale:,} conversions",
            *_measurement_group_lines(measurements),
        ),
        location="upper right",
    )
    return _save_figure(fig, output_path, formats, exact_canvas=True)


@with_plot_style
def plot_adc_dynamic(
    msmt: MeasAdc,
    analysis: AnalysisAdcDynamic,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot sine fit, residual, and spectrum for one dynamic acquisition."""

    time_scale, time_unit = _time_scale(analysis.time_s)
    fig, axes = plt.subplots(3, 1, figsize=(9.0, 9.0))
    axes[0].plot(analysis.time_s * time_scale, analysis.measured_dout, ".", markersize=2, label="Measured")
    axes[0].plot(analysis.time_s * time_scale, analysis.fitted_dout, linewidth=1.0, label="Sine fit")
    axes[0].set_xlabel(f"Time ({time_unit})")
    axes[0].set_ylabel("ADC output (LSB)")
    style_legend(axes[0])
    axes[1].plot(analysis.time_s * time_scale, analysis.residual_dout, linewidth=0.7)
    axes[1].set_xlabel(f"Time ({time_unit})")
    axes[1].set_ylabel("Residual (LSB)")
    positive = analysis.spectrum_frequency_hz > 0
    axes[2].semilogx(analysis.spectrum_frequency_hz[positive], analysis.spectrum_dbfs[positive], linewidth=0.8)
    axes[2].set_xlabel("Frequency (Hz)")
    axes[2].set_ylabel("Amplitude (dBFS)")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
    _add_info_box(
        axes[2],
        (
            f"Input: {format_frequency_hz(analysis.input_frequency_hz)}",
            f"Sample rate: {format_frequency_hz(analysis.sample_rate_hz)}",
            f"SNDR: {analysis.spectral_sndr_db:.2f} dB",
            f"SNR: {analysis.spectral_snr_db:.2f} dB",
            f"THD: {analysis.spectral_thd_db:.2f} dB",
            f"SFDR: {analysis.spectral_sfdr_db:.2f} dB",
            f"ENOB: {analysis.spectral_enob_bits:.2f} bit",
            f"Input noise: {analysis.input_referred_noise_rms_v * 1e3:.3f} mV RMS",
            *_measurement_lines(msmt),
        ),
        location="lower left",
    )
    fig.suptitle("ADC dynamic performance")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_dynamic_sweep(
    measurements: Sequence[MeasAdc],
    analysis: AnalysisAdcDynamicSweep,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot ENOB and SNDR versus input frequency for each conversion rate."""

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8.5, 7.0))
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
        style_legend(ax, title="Conversion rate")
    _add_info_box(axes[0], _measurement_group_lines(measurements), location="lower left")
    fig.suptitle("ADC dynamic performance sweep")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_power_sweep(
    measurements: Sequence[MeasAdc],
    analysis: AnalysisAdcPowerSweep,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot one six-component stacked static/dynamic power chart per ADC."""

    output_path = Path(output_path)
    paths = []
    rail_colors = (NORD_BLUE, NORD_RED, NORD_GREEN)
    for adc_index in np.unique(analysis.observed_adc):
        selected = analysis.observed_adc == adc_index
        order = np.argsort(analysis.active_conversion_rate_hz[selected])
        rate_msps = analysis.active_conversion_rate_hz[selected][order] / 1e6
        component_labels = (
            "VDD_A static",
            "VDD_D static",
            "VDD_DAC static",
            "VDD_A dynamic",
            "VDD_D dynamic",
            "VDD_DAC dynamic",
        )
        component_power_uw = tuple(
            values[selected][order] * 1e6
            for values in (
                analysis.vdd_a_static_power_w,
                analysis.vdd_d_static_power_w,
                analysis.vdd_dac_static_power_w,
                analysis.vdd_a_dynamic_power_w,
                analysis.vdd_d_dynamic_power_w,
                analysis.vdd_dac_dynamic_power_w,
            )
        )
        component_colors = (
            *rail_colors,
            *(to_rgba(color, 0.42) for color in rail_colors),
        )

        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        collections = ax.stackplot(
            rate_msps,
            *component_power_uw,
            labels=component_labels,
            colors=component_colors,
        )
        for collection, color in zip(collections, (*rail_colors, *rail_colors), strict=True):
            collection.set_edgecolor(color)
            collection.set_linewidth(0.7)
        total_power_uw = analysis.total_power_w[selected][order] * 1e6
        ax.plot(rate_msps, total_power_uw, color=TEXT_COLOR, linewidth=1.0)

        low_index = 0
        high_index = -1
        endpoint_lines = [f"{rate_msps[low_index]:g} → {rate_msps[high_index]:g} MSPS (µW)"]
        endpoint_lines.extend(
            f"{label}: {values[low_index]:.2f} → {values[high_index]:.2f}"
            for label, values in zip(component_labels, component_power_uw, strict=True)
        )
        endpoint_lines.append(f"Total: {total_power_uw[low_index]:.2f} → {total_power_uw[high_index]:.2f}")
        _add_info_box(ax, endpoint_lines, location="upper left")

        ax.set_ylabel("Measured supply power (µW)")
        ax.set_xlabel("Active conversion rate (MSPS)")
        ax.set_xlim(0.0, float(np.max(rate_msps)) + 0.25)
        if np.max(rate_msps) >= 1.0:
            ax.set_xticks(np.arange(1.0, np.floor(np.max(rate_msps)) + 1.0))
        ax.set_xticks(np.arange(0.0, float(np.max(rate_msps)) + 0.251, 0.25), minor=True)
        ax.set_ylim(0.0, max(float(np.max(total_power_uw)) * 1.25, 1.0))
        style_ax(ax)
        style_grid(ax)
        style_legend(ax, ncol=2, loc="upper right")
        adc_label = f"ADC{adc_index:02d}" if adc_index >= 0 else "ADC unspecified"
        ax.set_title(f"{adc_label} static and dynamic supply power")

        adc_output_path = output_path.with_name(f"{output_path.stem}_adc{adc_index:02d}{output_path.suffix}")
        paths.extend(_save_figure(fig, adc_output_path, formats))
    return tuple(paths)


@with_plot_style
def plot_adc_decision_paths(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot running SAR estimates for selected conversions."""

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    cycles = np.arange(analysis.estimate_dout.shape[1])
    for row, estimate in enumerate(analysis.estimate_dout):
        ax.plot(
            cycles,
            estimate,
            alpha=0.5,
            linewidth=0.8,
            color=NORD_BLUE,
            label="Running estimate" if row == 0 else None,
        )
        ax.axhline(
            analysis.final_dout[row],
            alpha=0.2,
            linewidth=0.5,
            color=NORD_GREEN,
            label="Final output" if row == 0 else None,
        )
    ax.set_xlabel("Decision cycle")
    ax.set_ylabel("Running estimate (LSB)")
    ax.set_title("ADC decision paths")
    style_ax(ax)
    ax.grid(False, which="both")
    style_legend(ax)
    _add_info_box(
        ax,
        (
            f"Selection: {analysis.selection}",
            f"Conversions: {len(analysis.conversion_index)}",
            f"Decisions: {len(analysis.weights)}",
            *_measurement_lines(msmt),
        ),
    )
    return _save_figure(fig, output_path, formats)


def _draw_adc_decision_path_density(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    paths: np.ndarray,
    normalization_max: int,
    fig: plt.Figure | None = None,
) -> plt.Figure:
    """Draw one cumulative decision-path-density frame."""

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
    nord_density = LinearSegmentedColormap.from_list(
        "nord_decision_density",
        (NORD_LIGHT_BLUE, NORD_ORANGE, NORD_YELLOW),
    )
    # Keep zero occupancy solid blue, but start every positive occupancy at a
    # visibly lighter Frost color. This distinction is especially important
    # after GIF palette quantization: sparse horizontal holds must not disappear
    # while their anti-aliased vertical connectors remain visible.
    nord_density.set_bad(NORD_BLUE, alpha=1.0)
    density_norm = LogNorm(vmin=1, vmax=max(2, normalization_max))

    if fig is None:
        fig = plt.figure(figsize=FULL_HD_FIGSIZE)
    else:
        fig.clear()
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
    colorbar.outline.set_edgecolor(SPINE_COLOR)
    colorbar.ax.yaxis.label.set_color(TEXT_COLOR)

    populated_min = int(np.floor(np.min(analysis.estimate_dout) + 0.5))
    populated_max = int(np.floor(np.max(analysis.estimate_dout) + 0.5))
    ax.set_xlim(-0.5, cycles[-1] + 0.5)
    ax.set_ylim(max(-0.5, populated_min - 8.5), min(normalized_code_max + 0.5, populated_max + 8.5))
    ax.set_xticks(cycles)
    ax.set_xticklabels(("Initial", *(str(cycle) for cycle in range(1, len(cycles)))))
    ax.set_xlabel("Decision cycle")
    ax.set_ylabel("Running estimate (LSB)")
    adc_index = msmt.param.observed_adc
    adc_label = "ADC" if adc_index is None else f"ADC{adc_index:02d}"
    input_dc = getattr(msmt.param.vin_diff, "dc", None)
    input_mv = float(input_dc) * 1e3 if input_dc is not None else None
    rate_hz = msmt.info.readbacks.get("active_conversion_rate_hz")
    details = []
    if input_mv is not None:
        details.append(f"{input_mv:g} mV DC")
    if isinstance(rate_hz, (int, float)):
        details.append(f"{float(rate_hz) / 1e6:g} Msps")
    suffix = f" ({', '.join(details)})" if details else ""
    ax.set_title(f"{adc_label} decision-path density{suffix}")
    style_ax(ax)
    ax.set_facecolor(NORD_BLUE)
    ax.grid(False, which="both")
    _add_info_box(
        ax,
        (
            f"Conversions: {len(paths):,}",
            *_measurement_lines(msmt),
        ),
        location="upper right",
    )
    return fig


@with_plot_style
def plot_adc_decision_path_density(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot how frequently conversions follow each running SAR trajectory."""

    if analysis.selection != "all":
        raise ValueError("decision-path density requires an analysis containing all conversions")
    if not len(analysis.estimate_dout):
        raise ValueError("decision-path density requires at least one conversion")
    fig = _draw_adc_decision_path_density(
        msmt,
        analysis,
        paths=analysis.estimate_dout,
        normalization_max=len(analysis.estimate_dout),
    )
    return _save_figure(fig, output_path, formats, exact_canvas=True)


@with_plot_style
def animate_adc_decision_path_density(
    msmt: MeasAdc,
    analysis: AnalysisAdcDecisionPaths,
    *,
    output_path: Path,
    frame_count: int = 24,
    fps: int = 4,
) -> tuple[Path, ...]:
    """Animate the cumulative population of the SAR decision-path density."""

    if analysis.selection != "all":
        raise ValueError("decision-path density requires an analysis containing all conversions")
    total_conversions = len(analysis.estimate_dout)
    if not total_conversions:
        raise ValueError("decision-path density requires at least one conversion")
    if frame_count < 2:
        raise ValueError("frame_count must be at least two")
    if fps <= 0:
        raise ValueError("fps must be positive")

    cumulative_counts = np.unique(
        np.rint(
            np.geomspace(
                1,
                total_conversions,
                num=frame_count,
            )
        ).astype(np.int64)
    )
    if cumulative_counts[-1] != total_conversions:
        cumulative_counts = np.append(cumulative_counts, total_conversions)

    path = Path(output_path).with_suffix(".gif")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=FULL_HD_FIGSIZE, dpi=PNG_DPI)
    frames = []
    for cumulative_count in cumulative_counts:
        _draw_adc_decision_path_density(
            msmt,
            analysis,
            paths=analysis.estimate_dout[:cumulative_count],
            normalization_max=total_conversions,
            fig=fig,
        )
        fig.tight_layout()
        fig.canvas.draw()
        frames.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba()).copy()).convert("RGB"))
    plt.close(fig)

    frame_duration_ms = round(1_000 / fps)
    durations_ms = [frame_duration_ms] * len(frames)
    durations_ms[-1] += 1_000
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=durations_ms,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return (path,)


@with_plot_style
def plot_comp_offset_noise(
    measurements: Sequence[MeasCompExt | MeasCompInt],
    analysis: AnalysisCompOffsetNoise,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot comparator decision probability versus differential input."""

    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    ax.plot(analysis.vin_diff_v * 1e3, analysis.decision_probability, marker="o")
    ax.axhline(0.5, color=SPINE_COLOR, linewidth=0.6)
    if np.isfinite(analysis.offset_v):
        ax.axvline(analysis.offset_v * 1e3, color=NORD_RED, linestyle="--", linewidth=0.8)
    ax.set_xlabel("Differential input (mV)")
    ax.set_ylabel("Decision probability")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Comparator offset and noise")
    style_ax(ax)
    style_grid(ax)
    _add_info_box(
        ax,
        (
            f"Offset: {analysis.offset_v * 1e3:.3g} mV",
            f"Input noise σ: {analysis.noise_sigma_v * 1e3:.3g} mV",
            f"Decision polarity: {'increasing' if analysis.decision_polarity > 0 else 'decreasing'}",
            f"Validity: {analysis.validity}",
            *_measurement_group_lines(measurements),
        ),
        location="lower right",
    )
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_comp_campaign(
    measurement_groups: Sequence[Sequence[MeasCompExt | MeasCompInt]],
    analyses: Sequence[AnalysisCompOffsetNoise],
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot one ADC's common-mode or complementary-CDAC sampling campaign."""

    if (
        not measurement_groups
        or len(measurement_groups) != len(analyses)
        or any(not group for group in measurement_groups)
    ):
        raise ValueError("comparator campaign plot requires aligned non-empty measurement groups and analyses")
    campaigns = {getattr(group[0].param, "campaign", "") for group in measurement_groups}
    adc_indices = {getattr(group[0].param, "observed_adc", None) for group in measurement_groups}
    if len(campaigns) != 1 or len(adc_indices) != 1:
        raise ValueError("comparator campaign plot requires one campaign and one ADC")
    campaign = next(iter(campaigns))
    adc_index = next(iter(adc_indices))
    if not isinstance(adc_index, int):
        raise TypeError("comparator campaign plot requires an observed ADC index")
    if campaign == "comp_sampling_noise":
        return _plot_comp_sampling_campaign(
            measurement_groups,
            analyses,
            adc_index=adc_index,
            output_path=output_path,
            formats=formats,
        )
    if campaign == "comp_common_mode":
        return _plot_comp_common_mode_campaign(
            measurement_groups,
            analyses,
            adc_index=adc_index,
            output_path=output_path,
            formats=formats,
        )
    raise ValueError(f"unsupported comparator campaign {campaign!r}")


def _plot_comp_sampling_campaign(
    measurement_groups: Sequence[Sequence[MeasCompExt | MeasCompInt]],
    analyses: Sequence[AnalysisCompOffsetNoise],
    *,
    adc_index: int,
    output_path: Path,
    formats: Sequence[str],
) -> tuple[Path, ...]:
    """Plot one ADC's matched track/ hold curves over VDAC coupling."""

    grouped_results = {
        (float(group[0].param.requested_dac_rail_percent), group[0].param.sampling_mode): (
            group,
            analysis,
        )
        for group, analysis in zip(measurement_groups, analyses, strict=True)
    }
    coupling_percentages = (0.0, 25.0, 50.0, 75.0, 100.0)
    expected_results = {
        (coupling_percent, mode) for coupling_percent in coupling_percentages for mode in ("track", "hold")
    }
    if set(grouped_results) != expected_results:
        raise ValueError("sampling-noise plot requires five matched track and hold coupling pairs")
    common_modes_v = {float(measurement.param.vin_cm.dc) for group in measurement_groups for measurement in group}
    if common_modes_v != {0.7}:
        raise ValueError("sampling-noise plot requires Vin_cm = 0.7 V")

    fig, (curve_ax, violin_ax) = plt.subplots(1, 2, figsize=DETAILED_16_9_FIGSIZE)
    mode_colors = {
        "track": SAMPLING_TRACK_COLORS,
        "hold": SAMPLING_HOLD_COLORS,
    }
    mode_offsets = {"track": -2.6, "hold": 2.6}
    for coupling_index, coupling_percent_p in enumerate(coupling_percentages):
        coupling_percent_n = 100.0 - coupling_percent_p
        for mode in ("track", "hold"):
            _group, analysis = grouped_results[(coupling_percent_p, mode)]
            threshold_mv = analysis.offset_v * 1e3
            noise_mv = analysis.noise_sigma_v * 1e3
            if not (
                analysis.validity == "valid" and np.isfinite(threshold_mv) and np.isfinite(noise_mv) and noise_mv > 0.0
            ):
                raise ValueError(
                    f"sampling-noise plot requires a valid {mode} fit at "
                    f"P/N = {coupling_percent_p:g}/{coupling_percent_n:g}%"
                )
            color = mode_colors[mode][coupling_index]
            curve_label = f"{mode.title()} P/N = {coupling_percent_p:g}/{coupling_percent_n:g}%"
            curve_ax.scatter(
                analysis.vin_diff_v * 1e3,
                analysis.decision_probability,
                s=9.0,
                color=color,
                alpha=0.32,
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
                alpha=0.60,
                linewidth=0.8,
                edgecolor=color,
            )
            violin_ax.plot(
                violin_center,
                threshold_mv,
                marker="o",
                markersize=3.5,
                color=color,
            )
            annotation_y_mv = max(
                COMPARATOR_INPUT_ERROR_MINIMUM_MV + 0.35,
                threshold_mv - 4.0 * noise_mv - 0.45,
            )
            violin_ax.text(
                violin_center,
                annotation_y_mv,
                f"μ={threshold_mv:.2f}\nσ={noise_mv:.2f}",
                horizontalalignment="center",
                verticalalignment="top",
                fontsize="xx-small",
                color=TEXT_COLOR,
            )

    curve_ax.axhline(0.5, color=SPINE_COLOR, linewidth=0.6)
    curve_ax.set_xlim(COMPARATOR_INPUT_ERROR_MINIMUM_MV, COMPARATOR_INPUT_ERROR_MAXIMUM_MV)
    curve_ax.set_xlabel("Differential input (mV)")
    curve_ax.set_ylabel("Decision probability")
    curve_ax.set_ylim(-0.02, 1.02)
    curve_ax.set_title("Comparator S-curves (CDF)")
    style_legend(curve_ax, loc="lower right", ncols=2)

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
            Patch(facecolor=NORD_BLUE, edgecolor=NORD_BLUE, alpha=0.60, label="Track"),
            Patch(facecolor=NORD_RED, edgecolor=NORD_RED, alpha=0.60, label="Hold"),
        ),
        loc="upper right",
    )

    for ax in (curve_ax, violin_ax):
        style_ax(ax)
        style_grid(ax)
    fig.suptitle(f"ADC{adc_index:02d} Threshold dispersion and input-referred noise vs VDAC coupling at Vin_cm = 0.7 V")
    return _save_figure(fig, output_path, formats, exact_canvas=True)


def _plot_comp_common_mode_campaign(
    measurement_groups: Sequence[Sequence[MeasCompExt | MeasCompInt]],
    analyses: Sequence[AnalysisCompOffsetNoise],
    *,
    adc_index: int,
    output_path: Path,
    formats: Sequence[str],
) -> tuple[Path, ...]:
    """Plot one ADC's comparator response over common-mode input."""

    selected_results = [
        (group, analysis)
        for group, analysis in zip(measurement_groups, analyses, strict=True)
        if COMMON_MODE_DISPLAY_MIN_V <= float(group[0].param.vin_cm.dc) <= COMMON_MODE_DISPLAY_MAX_V
    ]
    if not selected_results:
        raise ValueError("common-mode plot has no curves in the 0.7..1.2 V display range")

    selected_results.sort(key=lambda result: float(result[0][0].param.vin_cm.dc))
    fig, (curve_ax, violin_ax) = plt.subplots(1, 2, figsize=DETAILED_16_9_FIGSIZE)
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
            alpha=0.40,
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
                alpha=0.55,
                linewidth=0.8,
                edgecolor=color,
            )
            violin_ax.plot(common_mode_v, threshold_mv, marker="o", markersize=4.0, color=color)
            annotation_y_mv = max(
                COMPARATOR_INPUT_ERROR_MINIMUM_MV + 0.35,
                threshold_mv - 4.0 * noise_mv - 0.55,
            )
            annotation = f"μ={threshold_mv:.2f} mV\nσ={noise_mv:.2f} mV"
        else:
            curve_ax.plot(
                analysis.vin_diff_v * 1e3,
                analysis.decision_probability,
                linewidth=0.8,
                color=color,
                alpha=0.75,
                label=f"Vin_cm = {common_mode_v:.3g} V (fit invalid)",
                zorder=3,
            )
            annotation_y_mv = COMPARATOR_INPUT_ERROR_MINIMUM_MV + 0.35
            annotation = "fit invalid"
        violin_ax.text(
            common_mode_v,
            annotation_y_mv,
            annotation,
            horizontalalignment="center",
            verticalalignment="top",
            fontsize="x-small",
            color=TEXT_COLOR,
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
    fig.suptitle(f"ADC{adc_index:02d} Threshold dispersion and input-referred noise vs common mode")
    return _save_figure(fig, output_path, formats, exact_canvas=True)


def _expected_cdac_effective_fraction(
    measurements: Sequence[MeasCdacExt],
) -> np.ndarray:
    """Return flavor-aware normalized main-minus-diff PEX expectations."""

    if not measurements:
        raise ValueError("CDAC expectation requires measurements")
    params = measurements[0].param
    weights = np.asarray(params.dut.cdac.weights, dtype=np.float64)
    total_weights = 65.0 * np.ceil(weights / 64.0)
    recorded_parasitics = {
        float(measurement.info.readbacks["cdac_topplate_parasitic_weight"])
        for measurement in measurements
        if "cdac_topplate_parasitic_weight" in measurement.info.readbacks
    }
    if len(recorded_parasitics) > 1:
        raise ValueError("CDAC measurements contain inconsistent top-plate parasitic expectations")
    if recorded_parasitics:
        topplate_parasitic_weight = next(iter(recorded_parasitics))
    else:
        board_id = getattr(params, "board_id", None)
        adc_index = getattr(params, "observed_adc", None)
        if board_id is None or adc_index is None:
            topplate_parasitic_weight = 0.0
        else:
            board_map = load_board_map()
            board = board_map["boards"][board_id]
            flavor = board["adc_channels"][adc_index]
            topplate_parasitic_weight = float(
                board_map["adc_flavors"][flavor].get("cdac_topplate_parasitic_weight", 0.0)
            )
    if not np.isfinite(topplate_parasitic_weight) or topplate_parasitic_weight < 0.0:
        raise ValueError("CDAC top-plate parasitic expectation must be finite and non-negative")
    return weights / (np.sum(total_weights) + topplate_parasitic_weight)


@with_plot_style
def plot_cdac_cap_mismatch(
    measurements: Sequence[MeasCdacExt],
    analysis: AnalysisCdacCapMismatch,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot one ADC's normalized A-to-B main/diff weights and diagnostics."""

    if not measurements:
        raise ValueError("CDAC A-to-B plot requires measurements")
    elements = np.arange(1, analysis.effective_fraction.shape[1] + 1)
    expected_effective = _expected_cdac_effective_fraction(measurements)
    fig, axes_grid = plt.subplots(2, 3, figsize=DETAILED_16_9_FIGSIZE)
    axes = axes_grid.ravel()
    for side, label, color in ((0, "P", NORD_BLUE), (1, "N", NORD_RED)):
        axes[0].plot(
            elements,
            analysis.effective_fraction[side],
            "o-",
            color=color,
            label=f"{label} normal (diffcaps=1, main-diff)",
        )
        axes[1].plot(
            elements,
            analysis.effective_fraction[side] - expected_effective,
            "o-",
            color=color,
            label=f"{label} residual",
        )
        axes[3].plot(elements, analysis.main_fraction[side], "o-", color=color, label=f"{label} main")
        axes[3].plot(
            elements,
            analysis.diff_fraction[side],
            "s--",
            color=color,
            alpha=0.8,
            label=f"{label} diff",
        )
        axes[4].plot(
            elements,
            analysis.direction_bias[side, :, 0],
            marker="o",
            linestyle="-" if side == 0 else "--",
            color=color,
            label=f"{label} diffcaps=0 (main+diff)",
        )
        axes[4].plot(
            elements,
            analysis.direction_bias[side, :, 1],
            marker="s",
            linestyle="-" if side == 0 else "--",
            color=color,
            alpha=0.7,
            label=f"{label} diffcaps=1 (main-diff)",
        )
        axes[5].plot(
            elements,
            2.0 * analysis.diff_fraction[side],
            "o-",
            color=color,
            label=f"{label} (w_plus - w_minus)",
        )
    axes[0].plot(elements, expected_effective, "k--", linewidth=0.8, label="ideal/PEX expectation")
    axes[2].plot(
        elements,
        analysis.effective_fraction[0] - analysis.effective_fraction[1],
        "o-",
        color=NORD_PURPLE,
        label="P-N effective",
    )
    axes[0].set_ylabel("Normalized effective C/Ctotal_top")
    axes[1].set_ylabel("Effective residual from expectation")
    axes[2].set_ylabel("Normalized asymmetry / bias")
    axes[3].set_ylabel("Normalized component C/Ctotal_top")
    axes[4].set_ylabel("Switching-direction half-difference")
    axes[5].set_ylabel("Diffcap separation")
    for ax in axes:
        ax.set_xlabel("Element in C16-to-C1 order")
        ax.set_xticks(elements)
        style_ax(ax)
        style_grid(ax)
        style_legend(ax)
    fig.suptitle(f"ADC{analysis.adc_index:02d} A-to-B CDAC capacitance")
    return _save_figure(fig, output_path, formats, exact_canvas=True)


@with_plot_style
def plot_cdac_cap_mismatch_comparison(
    measurement_groups: Sequence[Sequence[MeasCdacExt]],
    analyses: Sequence[AnalysisCdacCapMismatch],
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Compare normalized A-to-B CDAC extraction across ADC00–ADC03."""

    if len(measurement_groups) != 4 or len(analyses) != 4 or any(not group for group in measurement_groups):
        raise ValueError("CDAC comparison requires four aligned non-empty measurement groups and analyses")
    if {analysis.adc_index for analysis in analyses} != {0, 1, 2, 3}:
        raise ValueError("CDAC comparison requires exactly ADC00 through ADC03")
    if any(
        getattr(group[0].param, "observed_adc", None) != analysis.adc_index
        for group, analysis in zip(measurement_groups, analyses, strict=True)
    ):
        raise ValueError("CDAC comparison measurement groups do not match their analyses")

    fig, axes_grid = plt.subplots(2, 2, figsize=DETAILED_16_9_FIGSIZE)
    axes = axes_grid.ravel()
    aligned = sorted(zip(measurement_groups, analyses, strict=True), key=lambda item: item[1].adc_index)
    element_counts = {analysis.effective_fraction.shape[1] for analysis in analyses}
    if len(element_counts) != 1:
        raise ValueError("CDAC comparison requires matching element counts")
    elements = np.arange(1, next(iter(element_counts)) + 1)
    for group, analysis in aligned:
        expected = _expected_cdac_effective_fraction(group)
        effective_mean = (analysis.effective_fraction[0] + analysis.effective_fraction[1]) / 2.0
        diffcap_separation_mean = analysis.diff_fraction[0] + analysis.diff_fraction[1]
        label = f"ADC{analysis.adc_index:02d}"
        color = NORD_COLORS[analysis.adc_index]
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

    axes[0].set_ylabel("Mean P/N effective fraction")
    axes[1].set_ylabel("Residual from ideal/PEX expectation")
    axes[2].set_ylabel("P-N effective asymmetry")
    axes[3].set_ylabel("Mean P/N diffcap separation")
    for ax in axes:
        ax.axhline(0.0, color=SPINE_COLOR, linewidth=0.6)
        ax.set_xlabel("Element in C16-to-C1 order")
        ax.set_xticks(elements)
        style_ax(ax)
        style_grid(ax)
        style_legend(ax)
    fig.suptitle("ADC00–ADC03 A-to-B CDAC comparison")
    return _save_figure(fig, output_path, formats, exact_canvas=True)


@with_plot_style
def plot_comp_timing(
    measurements: Sequence[MeasCompInt],
    analysis: AnalysisCompTiming,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot comparator delay, settling time, and unresolved outcomes."""

    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.5))
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
    _add_info_box(axes[0], _measurement_group_lines(measurements))
    fig.suptitle("Comparator timing")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_comp_power(
    measurements: Sequence[MeasCompInt],
    analysis: AnalysisCompPower,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot comparator average power per measurement."""

    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    labels = [str(index) for index in analysis.source_index]
    ax.bar(labels, analysis.average_power_w * 1e6)
    ax.set_ylabel("Average power (µW)")
    ax.set_xlabel("Measurement index")
    style_ax(ax)
    style_grid(ax)
    _add_info_box(ax, _measurement_group_lines(measurements))
    fig.suptitle("Comparator power")
    return _save_figure(fig, output_path, formats)
