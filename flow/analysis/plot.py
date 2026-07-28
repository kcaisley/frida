"""Rendering-only plots for normalized FRIDA results.

File parsing and numerical analysis intentionally live elsewhere.  Every
public plot accepts one :class:`PlotRequest` and returns :class:`PlotArtifacts`.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from flow.analysis.models import (
    AnalysisResult,
    DataTable,
    PlotArtifacts,
    PlotKind,
    PlotRequest,
    RunData,
)

PNG_FACE_COLOR = "white"
TEXT_COLOR = "#2E3440"
SPINE_COLOR = "#7B8794"
GRID_COLOR = "#D8DEE9"
LEGEND_FACE_COLOR = "#ECEFF4"
NORD_BLUE = "#5E81AC"
NORD_GREEN = "#A3BE8C"
NORD_RED = "#BF616A"
NORD_ORANGE = "#D08770"


def style_ax(ax: plt.Axes) -> None:
    """Apply the shared FRIDA axis style."""

    ax.set_facecolor(PNG_FACE_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)


def style_grid(ax: plt.Axes) -> None:
    """Apply the shared FRIDA grid style."""

    ax.grid(True, color=GRID_COLOR, linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)


def style_legend(ax: plt.Axes, **kwargs) -> None:
    """Apply the shared FRIDA legend style."""

    legend = ax.legend(facecolor=LEGEND_FACE_COLOR, edgecolor=SPINE_COLOR, **kwargs)
    if legend is not None:
        for text in legend.get_texts():
            text.set_color(TEXT_COLOR)


def format_frequency_hz(value: float) -> str:
    """Format one frequency with a compact SI prefix."""

    if abs(value) >= 1e9:
        return f"{value / 1e9:.4g} GHz"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.4g} kHz"
    return f"{value:.4g} Hz"


def _add_info_box(ax: plt.Axes, lines: tuple[str, ...]) -> None:
    if not lines:
        return
    ax.text(
        0.98,
        0.92,
        "\n".join(lines),
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=TEXT_COLOR,
        bbox={
            "boxstyle": "round",
            "facecolor": LEGEND_FACE_COLOR,
            "edgecolor": SPINE_COLOR,
            "alpha": 0.9,
        },
    )


def _save_figure(fig: plt.Figure, request: PlotRequest) -> PlotArtifacts:
    spec = request.spec
    formats = tuple(item.lower().lstrip(".") for item in spec.formats)
    if not formats:
        raise ValueError("plot formats must not be empty")
    supported = {"png", "pdf", "svg"}
    unsupported = sorted(set(formats).difference(supported))
    if unsupported:
        raise ValueError(f"unsupported plot formats: {', '.join(unsupported)}")
    base_path = spec.output_path.with_suffix("") if spec.output_path.suffix else spec.output_path
    base_path.parent.mkdir(parents=True, exist_ok=True)
    paths = tuple(base_path.with_suffix(f".{format_name}") for format_name in formats)
    for path in paths:
        if path.suffix == ".png":
            fig.savefig(path, facecolor=PNG_FACE_COLOR, dpi=250)
        else:
            fig.savefig(path, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    return PlotArtifacts(spec.name, paths)


def _run_input(request: PlotRequest) -> RunData:
    if len(request.spec.input_ids) != 1:
        raise ValueError(f"{request.spec.kind.value} plot requires exactly one run")
    input_id = request.spec.input_ids[0]
    for run in request.runs:
        if run.run_id == input_id:
            return run
    raise KeyError(f"plot request has no run {input_id!r}")


def _result_input(request: PlotRequest) -> AnalysisResult:
    if len(request.spec.input_ids) != 1:
        raise ValueError(f"{request.spec.kind.value} plot requires exactly one analysis result")
    input_id = request.spec.input_ids[0]
    for result in request.results:
        if result.name == input_id:
            return result
    raise KeyError(f"plot request has no result {input_id!r}")


def _table_from_run(run: RunData, name: str | None) -> DataTable:
    if name is not None:
        return run.table(name)
    if len(run.tables) != 1:
        raise ValueError(f"run {run.run_id!r} contains several tables; PlotSpec.table is required")
    return run.tables[0]


def _table_input(request: PlotRequest) -> DataTable:
    """Resolve one table from either a normalized run or analysis result."""

    if len(request.spec.input_ids) != 1:
        raise ValueError(f"{request.spec.kind.value} plot requires exactly one input")
    input_id = request.spec.input_ids[0]
    run_matches = [run for run in request.runs if run.run_id == input_id]
    result_matches = [result for result in request.results if result.name == input_id]
    if len(run_matches) + len(result_matches) != 1:
        raise KeyError(f"plot request must contain exactly one input named {input_id!r}")
    if run_matches:
        return _table_from_run(run_matches[0], request.spec.table)
    result = result_matches[0]
    if request.spec.table is not None:
        return result.table(request.spec.table)
    if len(result.tables) != 1:
        raise ValueError(
            f"analysis result {result.name!r} contains several tables; PlotSpec.table is required"
        )
    return result.tables[0]


def _time_scale(times_s: np.ndarray) -> tuple[float, str]:
    span = float(np.max(times_s) - np.min(times_s))
    magnitude = max(span, float(np.max(np.abs(times_s))))
    if magnitude < 1e-6:
        return 1e9, "ns"
    if magnitude < 1e-3:
        return 1e6, "µs"
    if magnitude < 1.0:
        return 1e3, "ms"
    return 1.0, "s"


def plot_time_domain(request: PlotRequest) -> PlotArtifacts:
    """Render one to four aligned time-domain columns."""

    spec = request.spec
    run = _run_input(request)
    table = _table_from_run(run, spec.table)
    x_name = spec.x_column or "time_s"
    y_names = spec.y_columns
    if not 1 <= len(y_names) <= 4:
        raise ValueError("time-domain plots require one to four y columns")
    times_s = np.asarray(table.column(x_name), dtype=np.float64)
    if len(times_s) < 2:
        raise ValueError("time-domain plot requires at least two samples")
    time_scale, time_unit = _time_scale(times_s)

    fig, axes_grid = plt.subplots(
        len(y_names),
        1,
        figsize=(8, max(2.8, 1.8 * len(y_names))),
        sharex=True,
        squeeze=False,
        facecolor=PNG_FACE_COLOR,
    )
    axes = axes_grid[:, 0]
    colors = (NORD_BLUE, NORD_GREEN, NORD_RED, NORD_ORANGE)
    if spec.title:
        axes[0].set_title(spec.title)
    for axis, name, color in zip(axes, y_names, colors[: len(y_names)], strict=True):
        values = np.asarray(table.column(name), dtype=np.float64)
        axis.plot(times_s * time_scale, values, color=color, linewidth=1.1)
        axis.set_ylabel(spec.labels.get(name, f"{name} ({table.unit(name)})".strip()))
        if spec.x_limit is not None:
            axis.set_xlim(*(np.asarray(spec.x_limit) * time_scale))
        if spec.y_limit is not None:
            axis.set_ylim(*spec.y_limit)
        _add_info_box(axis, spec.info_lines.get(name, ()))
        style_ax(axis)
        style_grid(axis)
    axes[-1].set_xlabel(spec.labels.get(x_name, f"Time ({time_unit})"))
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_frequency_domain(request: PlotRequest) -> PlotArtifacts:
    """Render spectra already calculated by the measurement layer."""

    spec = request.spec
    result = _result_input(request)
    table = result.table(spec.table or "spectrum")
    x_name = spec.x_column or "frequency_hz"
    y_names = spec.y_columns or tuple(name for name in table.column_names if name != x_name)
    if not 1 <= len(y_names) <= 4:
        raise ValueError("frequency-domain plots require one to four y columns")
    frequency_hz = np.asarray(table.column(x_name), dtype=np.float64)
    limit_hz = spec.x_limit[1] if spec.x_limit is not None else float(frequency_hz[-1])
    if limit_hz >= 1e9:
        scale, unit = 1e9, "GHz"
    elif limit_hz >= 1e6:
        scale, unit = 1e6, "MHz"
    elif limit_hz >= 1e3:
        scale, unit = 1e3, "kHz"
    else:
        scale, unit = 1.0, "Hz"

    fig, axes_grid = plt.subplots(
        len(y_names),
        1,
        figsize=(8, max(2.8, 1.8 * len(y_names))),
        sharex=True,
        squeeze=False,
        facecolor=PNG_FACE_COLOR,
    )
    axes = axes_grid[:, 0]
    colors = (NORD_BLUE, NORD_GREEN, NORD_RED, NORD_ORANGE)
    if spec.title:
        axes[0].set_title(spec.title)
    for axis, name, color in zip(axes, y_names, colors[: len(y_names)], strict=True):
        values = np.asarray(table.column(name), dtype=np.float64)
        if table.unit(name) not in {"dB", "dBFS"}:
            values = 20.0 * np.log10(np.maximum(values, np.finfo(float).tiny))
        axis.plot(frequency_hz / scale, values, color=color, linewidth=1.0)
        axis.set_ylabel(spec.labels.get(name, name))
        axis.set_xlim(0.0, limit_hz / scale)
        if spec.y_limit is not None:
            axis.set_ylim(*spec.y_limit)
        _add_info_box(axis, spec.info_lines.get(name, ()))
        style_ax(axis)
        style_grid(axis)
    axes[-1].set_xlabel(spec.labels.get(x_name, f"Frequency ({unit})"))
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_transfer(request: PlotRequest) -> PlotArtifacts:
    """Render individual ADC conversions and their mean transfer."""

    spec = request.spec
    result = _result_input(request)
    samples = result.table("samples")
    transfer = result.table("transfer")
    fig, axis = plt.subplots(figsize=(7, 5), facecolor=PNG_FACE_COLOR)
    axis.scatter(
        samples.column("vin_diff_v") * 1e3,
        samples.column("dout"),
        s=12,
        alpha=0.35,
        color=NORD_BLUE,
        label="individual conversions",
    )
    axis.plot(
        transfer.column("vin_diff_v") * 1e3,
        transfer.column("mean_code"),
        color=NORD_RED,
        linewidth=1.8,
        label="mean output",
    )
    axis.set_title(spec.title or "ADC transfer")
    axis.set_xlabel(spec.labels.get("vin_diff_v", "Differential input (mV)"))
    axis.set_ylabel(spec.labels.get("dout", "Output code"))
    if spec.x_limit is not None:
        axis.set_xlim(*spec.x_limit)
    if spec.y_limit is not None:
        axis.set_ylim(*spec.y_limit)
    style_ax(axis)
    style_grid(axis)
    style_legend(axis)
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_distribution(request: PlotRequest) -> PlotArtifacts:
    """Render a code or scalar histogram from an analysis result."""

    spec = request.spec
    result = _result_input(request)
    table_name = spec.table or (
        "distribution" if "distribution" in result.table_names else "histogram"
    )
    table = result.table(table_name)
    if table_name == "distribution":
        x, counts = table.column("code"), table.column("count")
        xlabel = spec.labels.get("code", "Output code")
    else:
        x, counts = table.column("bin_start"), table.column("count")
        xlabel = spec.labels.get("bin_start", "Value")
    fig, axis = plt.subplots(figsize=(8, 5), facecolor=PNG_FACE_COLOR)
    axis.bar(x, counts, width=1.0, color=NORD_BLUE, linewidth=0)
    axis.set_title(spec.title or "Distribution")
    axis.set_xlabel(xlabel)
    axis.set_ylabel(spec.labels.get("count", "Count"))
    if spec.x_limit is not None:
        axis.set_xlim(*spec.x_limit)
    if spec.y_limit is not None:
        axis.set_ylim(*spec.y_limit)
    _add_info_box(
        axis,
        tuple(
            f"{metric.name.replace('_', ' ').title()}: {metric.value:.5g} {metric.unit}".rstrip()
            for metric in result.metrics
        ),
    )
    style_ax(axis)
    style_grid(axis)
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_linearity(request: PlotRequest) -> PlotArtifacts:
    """Render DNL and INL from one linearity result."""

    spec = request.spec
    result = _result_input(request)
    table = result.table(spec.table or "linearity")
    codes = table.column("code")
    fig, (dnl_axis, inl_axis) = plt.subplots(
        2,
        1,
        figsize=(9, 7),
        sharex=True,
        facecolor=PNG_FACE_COLOR,
    )
    dnl_axis.bar(codes, table.column("dnl"), width=1.0, color=NORD_BLUE, linewidth=0)
    inl_axis.plot(codes, table.column("inl"), color=NORD_RED, linewidth=1.0)
    dnl_axis.axhline(0.0, color=SPINE_COLOR, linewidth=0.8)
    inl_axis.axhline(0.0, color=SPINE_COLOR, linewidth=0.8)
    dnl_axis.set_title(spec.title or "Differential and integral nonlinearity")
    dnl_axis.set_ylabel("DNL (LSB)")
    inl_axis.set_ylabel("INL (LSB)")
    inl_axis.set_xlabel("Output code")
    for axis in (dnl_axis, inl_axis):
        style_ax(axis)
        style_grid(axis)
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_decision_paths(request: PlotRequest) -> PlotArtifacts:
    """Render reconstructed SAR decision paths."""

    spec = request.spec
    result = _result_input(request)
    table = result.table("decision_paths")
    conversion_indices = np.unique(table.column("conversion_index"))
    fig, axis = plt.subplots(figsize=(10, 6), facecolor=PNG_FACE_COLOR)
    for conversion_index in conversion_indices:
        mask = table.column("conversion_index") == conversion_index
        axis.step(
            table.column("cycle")[mask],
            table.column("estimate_code")[mask],
            where="post",
            color=NORD_BLUE,
            linewidth=0.9,
            alpha=min(0.8, max(0.04, 10.0 / len(conversion_indices))),
        )
    axis.set_title(spec.title or "SAR decision paths")
    axis.set_xlabel("Decision cycle")
    axis.set_ylabel("Running output-code estimate")
    if spec.y_limit is not None:
        axis.set_ylim(*spec.y_limit)
    style_ax(axis)
    style_grid(axis)
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_adc_dynamic(request: PlotRequest) -> PlotArtifacts:
    """Render one ADC sine fit, residual, and FFT spectrum."""

    spec = request.spec
    result = _result_input(request)
    fit = result.table("fit")
    spectrum = result.table("spectrum")
    time_s = np.asarray(fit.column("time_s"), dtype=np.float64)
    maximum_samples = min(len(time_s), 5_000)
    scale, unit = _time_scale(time_s[:maximum_samples])

    fig, (fit_axis, residual_axis, spectrum_axis) = plt.subplots(
        3,
        1,
        figsize=(10, 9),
        height_ratios=(2, 1, 1.2),
        facecolor=PNG_FACE_COLOR,
    )
    fit_axis.plot(
        time_s[:maximum_samples] * scale,
        fit.column("measured_codes")[:maximum_samples],
        color=NORD_BLUE,
        linewidth=0.7,
        label="Measured ADC output",
    )
    fit_axis.plot(
        time_s[:maximum_samples] * scale,
        fit.column("fitted_codes")[:maximum_samples],
        color=NORD_RED,
        linewidth=1.1,
        label="Sine fit",
    )
    residual_axis.plot(
        time_s[:maximum_samples] * scale,
        fit.column("residual_codes")[:maximum_samples],
        color=NORD_GREEN,
        linewidth=0.7,
    )
    frequencies = spectrum.column("frequency_hz")[1:]
    amplitudes = spectrum.column("amplitude_dbfs")[1:]
    spectrum_axis.semilogx(frequencies, amplitudes, color=NORD_BLUE, linewidth=0.8)
    spectrum_axis.axvline(
        result.metric("fitted_frequency_hz"),
        color=NORD_RED,
        linestyle="--",
        linewidth=1.0,
    )
    fit_axis.set_title(spec.title or "ADC sine fit and residual")
    fit_axis.set_ylabel("ADC output code")
    residual_axis.set_xlabel(f"Time ({unit})")
    residual_axis.set_ylabel("Residual (LSB)")
    spectrum_axis.set_xlabel("Frequency (Hz)")
    spectrum_axis.set_ylabel("Amplitude (dBFS)")
    _add_info_box(
        fit_axis,
        (
            f"Samples: {int(result.metric('sample_count')):,}",
            f"Sample rate: {format_frequency_hz(result.metric('sample_rate_hz'))}",
            f"Input: {format_frequency_hz(result.metric('input_frequency_hz'))}",
            f"Residual: {result.metric('residual_rms_codes'):.3f} LSB RMS",
            f"Fit ENOB: {result.metric('enob_bits'):.3f} bits",
        ),
    )
    _add_info_box(
        spectrum_axis,
        (
            f"SNDR: {result.metric('spectral_sndr_db'):.2f} dB",
            f"SNR: {result.metric('spectral_snr_db'):.2f} dB",
            f"THD: {result.metric('spectral_thd_db'):.2f} dB",
            f"SFDR: {result.metric('spectral_sfdr_db'):.2f} dB",
            f"ENOB: {result.metric('spectral_enob_bits'):.3f} bits",
        ),
    )
    style_legend(fit_axis, loc="upper left")
    for axis in (fit_axis, residual_axis, spectrum_axis):
        style_ax(axis)
        style_grid(axis)
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_adc_dynamic_sweep(request: PlotRequest) -> PlotArtifacts:
    """Render ADC ENOB and SNDR versus frequency or conversion rate."""

    spec = request.spec
    result = _result_input(request)
    table = result.table("dynamic_sweep")
    x_name = spec.x_column or "input_frequency_hz"
    x = table.column(x_name)
    order = np.argsort(x)
    fig, (enob_axis, sndr_axis) = plt.subplots(
        2,
        1,
        figsize=(9, 7),
        sharex=True,
        facecolor=PNG_FACE_COLOR,
    )
    enob_axis.plot(
        x[order],
        table.column("spectral_enob_bits")[order],
        marker="o",
        color=NORD_BLUE,
    )
    sndr_axis.plot(
        x[order],
        table.column("spectral_sndr_db")[order],
        marker="o",
        color=NORD_RED,
    )
    enob_axis.set_title(spec.title or "ADC dynamic performance")
    enob_axis.set_ylabel("ENOB (bit)")
    sndr_axis.set_ylabel("SNDR (dB)")
    sndr_axis.set_xlabel(spec.labels.get(x_name, x_name.replace("_", " ").title()))
    if np.all(x > 0):
        enob_axis.set_xscale("log")
        sndr_axis.set_xscale("log")
    for axis in (enob_axis, sndr_axis):
        style_ax(axis)
        style_grid(axis)
    fig.tight_layout()
    return _save_figure(fig, request)


def plot_sweep(request: PlotRequest) -> PlotArtifacts:
    """Render one or more quantities against a shared sweep axis."""

    spec = request.spec
    table = _table_input(request)
    if spec.x_column is None:
        raise ValueError("sweep plots require PlotSpec.x_column")
    if not spec.y_columns:
        raise ValueError("sweep plots require at least one y column")

    x = np.asarray(table.column(spec.x_column), dtype=np.float64)
    group_values = (
        np.asarray(table.column(spec.group_column))
        if spec.group_column is not None
        else np.zeros(len(x), dtype=np.int8)
    )
    unique_groups = np.unique(group_values)
    colors = (
        "#4C566A",
        NORD_BLUE,
        NORD_GREEN,
        NORD_RED,
        NORD_ORANGE,
        "#B48EAD",
        "#88C0D0",
    )
    fig, axes_grid = plt.subplots(
        len(spec.y_columns),
        1,
        figsize=(8, max(3.4, 3.2 * len(spec.y_columns))),
        sharex=True,
        squeeze=False,
        facecolor=PNG_FACE_COLOR,
    )
    axes = axes_grid[:, 0]
    if spec.title:
        axes[0].set_title(spec.title)
    for axis, y_name in zip(axes, spec.y_columns, strict=True):
        y = np.asarray(table.column(y_name), dtype=np.float64)
        for group_index, group_value in enumerate(unique_groups):
            selected = group_values == group_value
            order = np.argsort(x[selected])
            label = None
            if spec.group_column is not None:
                label_key = f"{spec.group_column}:{group_value}"
                if label_key in spec.labels:
                    label = spec.labels[label_key]
                elif spec.group_column.endswith("_percent"):
                    label = f"{float(group_value):g}%"
                else:
                    label = str(group_value)
            axis.plot(
                x[selected][order],
                y[selected][order],
                marker="o",
                markersize=3.0,
                linewidth=0.75,
                color=colors[group_index % len(colors)],
                label=label,
            )
        axis.set_ylabel(spec.labels.get(y_name, y_name.replace("_", " ").title()))
        if spec.x_limit is not None:
            axis.set_xlim(*spec.x_limit)
        if spec.y_limit is not None:
            axis.set_ylim(*spec.y_limit)
        _add_info_box(axis, spec.info_lines.get(y_name, ()))
        style_ax(axis)
        style_grid(axis)
        if spec.group_column is not None:
            style_legend(axis, title=spec.legend_title)

    axes[-1].set_xlabel(
        spec.labels.get(spec.x_column, spec.x_column.replace("_", " ").title())
    )
    if spec.x_ticks:
        axes[-1].set_xticks(spec.x_ticks)
    if spec.secondary_x_reciprocal is not None:
        if spec.secondary_x_reciprocal <= 0.0:
            raise ValueError("secondary reciprocal-axis scale must be positive")
        primary = axes[-1]
        secondary = primary.twiny()
        secondary.set_xlim(primary.get_xlim())
        secondary.xaxis.set_ticks_position("bottom")
        secondary.xaxis.set_label_position("bottom")
        secondary.spines["bottom"].set_position(("outward", 42))
        secondary.spines["top"].set_visible(False)
        ticks = primary.get_xticks()
        visible_ticks = ticks[(ticks > 0.0) & (ticks >= primary.get_xlim()[0]) & (ticks <= primary.get_xlim()[1])]
        secondary.set_xticks(visible_ticks)
        secondary.set_xticklabels(
            [f"{spec.secondary_x_reciprocal / tick:.4g}" for tick in visible_ticks]
        )
        secondary.set_xlabel(spec.secondary_x_label or "Reciprocal sweep axis")
        style_ax(secondary)

    fig.tight_layout()
    return _save_figure(fig, request)


def render_plot(request: PlotRequest) -> PlotArtifacts:
    """Dispatch one rendering-only plot request."""

    handlers = {
        PlotKind.TIME_DOMAIN: plot_time_domain,
        PlotKind.FREQUENCY_DOMAIN: plot_frequency_domain,
        PlotKind.TRANSFER: plot_transfer,
        PlotKind.DISTRIBUTION: plot_distribution,
        PlotKind.LINEARITY: plot_linearity,
        PlotKind.DECISION_PATHS: plot_decision_paths,
        PlotKind.ADC_DYNAMIC: plot_adc_dynamic,
        PlotKind.ADC_DYNAMIC_SWEEP: plot_adc_dynamic_sweep,
        PlotKind.SWEEP: plot_sweep,
        PlotKind.MONTE_CARLO: plot_distribution,
    }
    try:
        handler = handlers[request.spec.kind]
    except KeyError:
        raise ValueError(f"unsupported plot kind {request.spec.kind.value!r}") from None
    return handler(request)
