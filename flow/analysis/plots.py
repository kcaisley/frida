"""Plots of typed FRIDA measurements and analysis results, with matplotlib: the lab figures no
block's spec draws yet (the CDAC's, the scope's traces, spectra and histograms, the ADC's mismatch
nonlinearity; the comparator's are its specs, ``flow.comp.plots``, the serializer's eyes and the
scope's decode against FastRX's the sequencer's, ``flow.seqgen.plots``), and the plot style the specs
are drawn in (``flow.plot.render``: PLOT_STYLE, the colours, ``style_grid``, ``save_figure``)."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from cycler import cycler
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.offsetbox import AnchoredOffsetbox, TextArea, VPacker
from matplotlib.ticker import AutoMinorLocator, NullLocator, StrMethodFormatter

from flow import comp
from flow.adc.sim import AdcSequence
from flow.analysis import calc
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
    AnalysisScope,
    Meas,
    MeasAdc,
    MeasCdac,
    Wave,
)

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
