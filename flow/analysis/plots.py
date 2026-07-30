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

from flow.analysis.types import (
    AnalysisAdcDecisionPaths,
    AnalysisAdcDynamic,
    AnalysisAdcDynamicSweep,
    AnalysisAdcNoise,
    AnalysisAdcNoiseSweep,
    AnalysisAdcNonlin,
    AnalysisAdcPowerSweep,
    AnalysisAdcTransfer,
    AnalysisCompOffsetNoise,
    AnalysisCompPower,
    AnalysisCompTiming,
    MeasAdcExt,
    MeasCompExt,
    MeasCompInt,
    Measurement,
)

DEFAULT_FORMATS = ("png", "pdf", "svg")
PNG_DPI = 200

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
NORD_DARK = "#4C566A"
NORD_COLORS = (
    NORD_BLUE,
    NORD_RED,
    NORD_GREEN,
    NORD_ORANGE,
    NORD_PURPLE,
    NORD_CYAN,
    NORD_YELLOW,
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

    ax.minorticks_on()
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
) -> tuple[Path, ...]:
    output_path = Path(output_path)
    if output_path.suffix:
        formats = (output_path.suffix.lstrip("."),)
        output_path = output_path.with_suffix("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.patch.set_facecolor(PLOT_FACE_COLOR)
    fig.tight_layout()
    paths = []
    for output_format in formats:
        path = output_path.with_suffix(f".{output_format}")
        if output_format.lower() == "png":
            fig.savefig(
                path,
                bbox_inches="tight",
                facecolor=PLOT_FACE_COLOR,
                dpi=PNG_DPI,
            )
        else:
            fig.savefig(
                path,
                bbox_inches="tight",
                facecolor=PLOT_FACE_COLOR,
            )
        paths.append(path)
    plt.close(fig)
    return tuple(paths)


def _measurement_lines(msmt: Measurement) -> tuple[str, ...]:
    lines = (
        f"Backend: {msmt.info.backend}",
        f"Recorded: {msmt.info.timestamp_utc.strftime('%Y-%m-%d %H:%M')}",
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
        f"Recorded: {first.info.timestamp_utc.strftime('%Y-%m-%d %H:%M')}",
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
    measurements: Sequence[MeasAdcExt],
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
def plot_adc_nonlin(
    msmt: MeasAdcExt,
    analysis: AnalysisAdcNonlin,
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
def plot_adc_noise(
    measurements: Sequence[MeasAdcExt],
    analysis: AnalysisAdcNoise,
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
    fig.suptitle("ADC output noise")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_noise_sweep(
    measurements: Sequence[MeasAdcExt],
    analysis: AnalysisAdcNoiseSweep,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot decision variation versus conversion rate and timing allocation."""

    fig, ax = plt.subplots(figsize=(9.0, 5.5))
    conversion_rate_msps = analysis.sample_rate_hz / 1e6
    for comparator_percent in np.unique(analysis.comparator_time_percent):
        selected = analysis.comparator_time_percent == comparator_percent
        order = np.argsort(conversion_rate_msps[selected])
        ax.plot(
            conversion_rate_msps[selected][order],
            analysis.std_dout[selected][order],
            marker="o",
            markersize=3,
            linewidth=0.8,
            color=TIMING_COLORS.get(float(comparator_percent), NORD_DARK),
            label=f"{comparator_percent:g}%",
        )
    ax.set_xlabel("Active conversion rate (MSPS)")
    ax.set_ylabel("Input-referred noise RMS (LSB)")
    ax.set_ylim(0.0, 10.0)
    ax.set_xticks(np.arange(1.0, 11.0))
    ax.set_title("Decision variation in LSB vs conversion rate")
    style_ax(ax)
    style_grid(ax)
    style_legend(
        ax,
        ncol=4,
        title="COMP→LOGIC interval\n(as % of decision cycle)",
        loc="lower left",
    )
    secondary = ax.twiny()
    secondary.set_xlim(ax.get_xlim())
    secondary.xaxis.set_ticks_position("bottom")
    secondary.xaxis.set_label_position("bottom")
    secondary.spines["bottom"].set_position(("outward", 38))
    secondary.spines["bottom"].set_color(SPINE_COLOR)
    secondary.spines["top"].set_visible(False)
    secondary.set_xlabel("Time per decision cycle (ns)")
    labeled_rates_msps = np.arange(1.0, 11.0)
    decision_cycle_ns = 50.0 / labeled_rates_msps
    secondary.set_xticks(labeled_rates_msps)
    secondary.set_xticklabels(tuple(f"{interval:.3g}" for interval in decision_cycle_ns))
    secondary.tick_params(
        direction="in",
        which="both",
        top=False,
        bottom=True,
        colors=TEXT_COLOR,
    )
    secondary.xaxis.label.set_color(TEXT_COLOR)
    secondary_y = ax.secondary_yaxis(
        "right",
        functions=(
            lambda noise_lsb: noise_lsb * analysis.input_lsb_v * 1e3,
            lambda noise_mv: noise_mv / (analysis.input_lsb_v * 1e3),
        ),
    )
    secondary_y.set_ylabel("Input-referred noise RMS (mV)")
    secondary_y.tick_params(
        direction="in",
        which="both",
        colors=TEXT_COLOR,
    )
    secondary_y.spines["right"].set_color(SPINE_COLOR)
    secondary_y.yaxis.label.set_color(TEXT_COLOR)
    _add_info_box(ax, _measurement_group_lines(measurements), location="upper left")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_dynamic(
    msmt: MeasAdcExt,
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
    measurements: Sequence[MeasAdcExt],
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
def plot_adc_dynamic_rate_sweep(
    measurements: Sequence[MeasAdcExt],
    analysis: AnalysisAdcDynamicSweep,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot SNDR/ENOB and input-referred noise on one rate-sweep panel."""

    if not measurements:
        raise ValueError("ADC dynamic rate plot requires at least one measurement")
    input_amplitudes_v = []
    for msmt in measurements:
        amplitude_v = getattr(msmt.param.vin_diff, "vamp", None)
        if amplitude_v is None:
            raise ValueError("ADC dynamic rate plot requires sine inputs with amplitude set")
        input_amplitudes_v.append(abs(float(amplitude_v)))
    if not np.allclose(input_amplitudes_v, input_amplitudes_v[0], rtol=1e-12, atol=0.0):
        raise ValueError("one input-referred-noise axis requires equal sine amplitudes")
    input_rms_mv = input_amplitudes_v[0] * 1e3 / np.sqrt(2.0)

    fig, ax = plt.subplots(figsize=(9.0, 5.5))
    for adc_position, adc_index in enumerate(np.unique(analysis.observed_adc)):
        selected = analysis.observed_adc == adc_index
        order = np.argsort(analysis.active_conversion_rate_hz[selected])
        rate_msps = analysis.active_conversion_rate_hz[selected][order] / 1e6
        label = f"ADC{adc_index:02d}" if adc_index >= 0 else "ADC unspecified"
        color = NORD_COLORS[adc_position % len(NORD_COLORS)]
        ax.plot(
            rate_msps,
            analysis.spectral_sndr_db[selected][order],
            marker="o",
            color=color,
            label=label,
        )

    ax.set_xlabel("Active conversion rate (MSPS)")
    ax.set_ylabel("SNDR (dB)")
    ax.set_xticks(np.arange(0.0, 11.0, 1.0))
    ax.set_xlim(0.0, 10.25)
    style_ax(ax)
    style_grid(ax)
    ax.set_xticks(np.arange(0.0, 10.251, 0.25), minor=True)

    enob_axis = ax.secondary_yaxis(
        "left",
        functions=(
            lambda sndr_db: (sndr_db - 1.76) / 6.02,
            lambda enob_bits: 6.02 * enob_bits + 1.76,
        ),
    )
    enob_axis.spines["left"].set_position(("outward", 48))
    enob_axis.spines["left"].set_color(SPINE_COLOR)
    enob_axis.set_ylabel("ENOB (bit)")
    enob_axis.tick_params(
        direction="in",
        which="both",
        left=True,
        right=False,
        colors=TEXT_COLOR,
    )
    enob_axis.yaxis.label.set_color(TEXT_COLOR)

    noise_axis = ax.secondary_yaxis(
        "left",
        functions=(
            lambda sndr_db: input_rms_mv * np.power(10.0, -np.asarray(sndr_db) / 20.0),
            lambda noise_mv: (
                20.0 * (np.log10(input_rms_mv) - np.log10(np.maximum(np.asarray(noise_mv), np.finfo(np.float64).tiny)))
            ),
        ),
    )
    noise_axis.spines["left"].set_position(("outward", 96))
    noise_axis.spines["left"].set_color(SPINE_COLOR)
    noise_axis.set_ylabel("Input-referred noise (mV RMS)")
    noise_axis.tick_params(
        direction="in",
        which="both",
        left=True,
        right=False,
        colors=TEXT_COLOR,
    )
    noise_axis.yaxis.label.set_color(TEXT_COLOR)

    decision_time_axis = ax.twiny()
    decision_time_axis.set_xlim(ax.get_xlim())
    decision_time_axis.xaxis.set_ticks_position("bottom")
    decision_time_axis.xaxis.set_label_position("bottom")
    decision_time_axis.spines["bottom"].set_position(("outward", 38))
    decision_time_axis.spines["bottom"].set_color(SPINE_COLOR)
    decision_time_axis.spines["top"].set_visible(False)
    decision_time_axis.set_xlabel("Time per decision cycle (ns)")
    labeled_rates_msps = np.arange(1.0, 11.0)
    decision_time_axis.set_xticks(labeled_rates_msps)
    decision_time_axis.set_xticklabels(tuple(f"{50.0 / rate:.3g}" for rate in labeled_rates_msps))
    decision_time_axis.tick_params(
        direction="in",
        which="both",
        top=False,
        bottom=True,
        colors=TEXT_COLOR,
    )
    decision_time_axis.xaxis.label.set_color(TEXT_COLOR)

    style_legend(ax, ncol=2, loc="upper right")
    _add_info_box(
        ax,
        (
            f"Input: {2.0 * input_amplitudes_v[0] * 1e3:g} mVpp sine",
            *_measurement_group_lines(measurements),
        ),
        location="lower left",
    )
    ax.set_title("ADC dynamic performance vs conversion rate")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_power_sweep(
    measurements: Sequence[MeasAdcExt],
    analysis: AnalysisAdcPowerSweep,
    *,
    output_path: Path,
    formats: Sequence[str] = DEFAULT_FORMATS,
) -> tuple[Path, ...]:
    """Plot active ADC total and per-rail power versus conversion rate."""

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8.5, 7.0))
    rail_powers = (
        ("VDD_A", analysis.vdd_a_power_w, NORD_BLUE),
        ("VDD_D", analysis.vdd_d_power_w, NORD_RED),
        ("VDD_DAC", analysis.vdd_dac_power_w, NORD_GREEN),
    )
    line_styles = ("-", "--", ":", "-.")
    for adc_position, adc_index in enumerate(np.unique(analysis.observed_adc)):
        selected = analysis.observed_adc == adc_index
        order = np.argsort(analysis.active_conversion_rate_hz[selected])
        rate_msps = analysis.active_conversion_rate_hz[selected][order] / 1e6
        adc_label = f"ADC{adc_index:02d}" if adc_index >= 0 else "ADC unspecified"
        axes[0].plot(
            rate_msps,
            analysis.total_power_w[selected][order] * 1e6,
            marker="o",
            color=NORD_COLORS[adc_position % len(NORD_COLORS)],
            label=adc_label,
        )
        for rail, power_w, color in rail_powers:
            axes[1].plot(
                rate_msps,
                power_w[selected][order] * 1e6,
                marker="o",
                color=color,
                linestyle=line_styles[adc_position % len(line_styles)],
                label=f"{adc_label} {rail}",
            )
    axes[0].set_ylabel("Total measured power (µW)")
    axes[1].set_ylabel("Measured rail power (µW)")
    axes[1].set_xlabel("Active conversion rate (MSPS)")
    for ax in axes:
        style_ax(ax)
        style_grid(ax)
        style_legend(ax)
    _add_info_box(axes[0], _measurement_group_lines(measurements), location="upper left")
    fig.suptitle("ADC active-conversion power")
    return _save_figure(fig, output_path, formats)


@with_plot_style
def plot_adc_decision_paths(
    msmt: MeasAdcExt,
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
    style_grid(ax)
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
            *_measurement_group_lines(measurements),
        ),
        location="lower right",
    )
    return _save_figure(fig, output_path, formats)


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
