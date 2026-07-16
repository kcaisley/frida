"""Shared ADC scan plotting helpers.

Run the overlay plotter from /local/frida with:
    uv run python -m flow.scans.plot
"""

from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flow.circuit.measure import amplitude_spectrum

PNG_FACE_COLOR = "white"
TEXT_COLOR = "#2E3440"
SPINE_COLOR = "#4C566A"
LEGEND_FACE_COLOR = "#ECEFF4"
GRID_MAJOR_COLOR = "#D8DEE9"
GRID_MINOR_COLOR = "#E5E9F0"
NORD_RED = "#BF616A"
NORD_GREEN = "#A3BE8C"
NORD_BLUE = "#5E81AC"


@dataclass(frozen=True)
class SubplotSpec:
    """Caller-provided presentation details for one plotted signal."""

    ylabel: str
    info_lines: tuple[str, ...] = ()

plt.rcParams.update(
    {
        # phys/model.py uses external LaTeX with Computer Modern.  Keep the same
        # serif/mathtext look here without requiring a complete TeX install.
        "text.usetex": False,
        "mathtext.fontset": "cm",
        "font.family": "serif",
        "font.serif": ["Computer Modern Roman", "DejaVu Serif"],
    }
)

CSV_FIELDS = [
    "adc",
    "config_adc",
    "mux_bits",
    "selected_adc_cfg",
    "other_adc_cfg",
    "case_name",
    "nominal_sample_rate_hz",
    "sequencer_frequency_hz",
    "serializer_frequency_hz",
    "symbol_rate_bps",
    "si570_frequency_hz",
    "pll_divider_n",
    "rx_sen_start_word",
    "comp_idelay_taps",
    "alignment_ok",
    "sweep_index",
    "vin_set_v",
    "vin_read_v",
    "vdiff_v",
    "conversion_index",
    "raw_word",
    "id",
    "frame",
    "spi",
    "Bbits",
    "Dout",
    "Dout_raw",
]

V_START = 0.000
V_STOP = 1.200
VIN_N = 0.600
VDIFF_START = (V_START - VIN_N) * 1000
VDIFF_STOP = (V_STOP - VIN_N) * 1000

BEHAVIORAL_LABEL = "behavioral"
BEHAVIORAL_CSV = Path("build/behavioral_scan/adc_00.csv")
BEHAVIORAL_COLOR = NORD_RED

PEX_SPICE_BSS_LABEL = "PEX SPICE BSS"
PEX_SPICE_BSS_CSV = Path("build/adc_pex_bss/adc_00.csv")
PEX_SPICE_BSS_COLOR = NORD_GREEN

PEX_SPICE_MONOTONIC_LABEL = "PEX SPICE monotonic"
PEX_SPICE_MONOTONIC_CSV = Path("build/adc_pex_monotonic/adc_00.csv")
PEX_SPICE_MONOTONIC_COLOR = "#D08770"

MEASUREMENT_LABEL = "measurement"
MEASUREMENT_CSV = Path("build/basic_scan/adc_00.csv")
MEASUREMENT_COLOR = NORD_BLUE

OVERLAY_PLOT = Path("build/adc_compare/adc_00_transfer_overlay.png")

OVERLAY_SOURCES = [
    (BEHAVIORAL_LABEL, BEHAVIORAL_CSV, BEHAVIORAL_COLOR),
    (PEX_SPICE_BSS_LABEL, PEX_SPICE_BSS_CSV, PEX_SPICE_BSS_COLOR),
    # (PEX_SPICE_MONOTONIC_LABEL, PEX_SPICE_MONOTONIC_CSV, PEX_SPICE_MONOTONIC_COLOR),
    (MEASUREMENT_LABEL, MEASUREMENT_CSV, MEASUREMENT_COLOR),
]


def style_ax(ax: plt.Axes) -> None:
    """Apply the shared FRIDA presentation style from phys/model.py."""
    ax.tick_params(colors=TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)
    ax.set_facecolor(PNG_FACE_COLOR)


def style_grid(ax: plt.Axes) -> None:
    ax.minorticks_on()
    ax.xaxis.grid(True, which="major", color=GRID_MAJOR_COLOR, alpha=0.95, linewidth=0.8)
    ax.yaxis.grid(True, which="major", color=GRID_MAJOR_COLOR, alpha=0.95, linewidth=0.8)
    ax.xaxis.grid(True, which="minor", color=GRID_MINOR_COLOR, alpha=1.0, linewidth=0.5)
    ax.yaxis.grid(True, which="minor", color=GRID_MINOR_COLOR, alpha=1.0, linewidth=0.5)


def style_legend(ax: plt.Axes, **kwargs) -> None:
    legend = ax.legend(
        facecolor=LEGEND_FACE_COLOR,
        edgecolor=SPINE_COLOR,
        labelcolor=TEXT_COLOR,
        **kwargs,
    )
    if legend is not None and legend.get_title() is not None:
        legend.get_title().set_color(TEXT_COLOR)


def format_frequency_hz(value: float) -> str:
    if value >= 1e6:
        return f"{value / 1e6:.3f} MHz"
    if value >= 1e3:
        return f"{value / 1e3:.3f} kHz"
    return f"{value:.3f} Hz"


def add_code_density_info_inset(
    ax: plt.Axes,
    adc_cfg: dict,
    *,
    average_per_code: float,
    missing_codes: int,
) -> None:
    seq_base_freq_hz = float(adc_cfg["seq_base_freq_hz"])
    conversion_steps = int(adc_cfg["conversion_steps"])
    sample_rate_hz = seq_base_freq_hz / conversion_steps
    text = "\n".join(
        (
            f"Samples: {int(adc_cfg['num_samples']):,}",
            f"Input: {adc_cfg['input_ramp']}",
            f"$f_s$: {format_frequency_hz(sample_rate_hz)}",
            f"$D_{{init}}$: {adc_cfg['dac_init_state']}",
            f"Diff caps: {'enabled' if adc_cfg['dac_diffcaps'] else 'disabled'}",
            f"Average/code: {average_per_code:.1f}",
            f"Missing codes: {missing_codes}",
        )
    )
    ax.text(
        0.98,
        0.95,
        text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=TEXT_COLOR,
        bbox={"boxstyle": "round", "facecolor": LEGEND_FACE_COLOR, "edgecolor": SPINE_COLOR, "alpha": 0.9},
    )


def write_scope_csv(
    csv_path: Path,
    waveforms,
    track_names: dict[int, str],
) -> Path:
    """Write aligned scope waveforms to a CSV with voltage and raw-code columns."""
    channels = tuple(track_names)
    if not channels:
        raise ValueError("at least one scope track is required")
    if len(set(track_names.values())) != len(track_names):
        raise ValueError(f"scope track names must be unique, got {tuple(track_names.values())}")

    missing_channels = sorted(set(channels).difference(waveforms))
    if missing_channels:
        raise ValueError(f"scope did not return waveforms for channels {missing_channels}")

    reference_x_scale = waveforms[channels[0]].x_scale
    if reference_x_scale.unit.lower() not in {"s", "sec", "seconds"}:
        raise ValueError(f"expected scope time axis in seconds, got {reference_x_scale.unit!r}")

    sample_counts: dict[int, int] = {}
    for channel in channels:
        waveform = waveforms[channel]
        if waveform.x_scale != reference_x_scale:
            raise ValueError(
                f"scope channel {channel} has horizontal scale {waveform.x_scale}, expected {reference_x_scale}"
            )
        if len(waveform.data) != len(waveform.raw_data):
            raise ValueError(
                f"scope channel {channel} has {len(waveform.data)} voltage samples "
                f"but {len(waveform.raw_data)} raw samples"
            )
        sample_counts[channel] = len(waveform.raw_data)

    if len(set(sample_counts.values())) != 1:
        raise ValueError(f"scope channels have different sample counts: {sample_counts}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "time_s",
                *[f"{track_names[channel]}_v" for channel in channels],
                *[f"{track_names[channel]}_raw" for channel in channels],
            ]
        )
        for index in range(next(iter(sample_counts.values()))):
            writer.writerow(
                [
                    reference_x_scale.offset + index * reference_x_scale.slope,
                    *[waveforms[channel].data[index] for channel in channels],
                    *[waveforms[channel].raw_data[index] for channel in channels],
                ]
            )

    print(f"Saved scope waveform CSV: {csv_path}")
    return csv_path


def _add_info_box(ax, lines: tuple[str, ...]) -> None:
    """Add a consistently styled information box to one plot axis."""
    ax.text(
        0.98,
        0.88,
        "\n".join(lines),
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=TEXT_COLOR,
        bbox={"boxstyle": "round", "facecolor": LEGEND_FACE_COLOR, "edgecolor": SPINE_COLOR, "alpha": 0.9},
    )


def _validate_subplots(subplots: dict[str, SubplotSpec]) -> None:
    """Validate caller-supplied signal selection and presentation details."""
    if not 1 <= len(subplots) <= 4:
        raise ValueError(f"expected one to four subplots, got {len(subplots)}")
    empty_labels = [signal for signal, spec in subplots.items() if not spec.ylabel]
    if empty_labels:
        raise ValueError(f"subplot labels must not be empty: {', '.join(empty_labels)}")


def _add_subplot_info(axes, subplots: dict[str, SubplotSpec]) -> None:
    """Place each supplied information block on its corresponding subplot."""
    for ax, spec in zip(axes, subplots.values(), strict=True):
        if spec.info_lines:
            _add_info_box(ax, spec.info_lines)


def plot_time_domain_csv(
    csv_path: Path,
    subplots: dict[str, SubplotSpec],
    *,
    png_path: Path | None = None,
    title: str | None = None,
) -> tuple[Path, ...]:
    """Plot one to four time-domain signals from a CSV.

    The CSV must contain a ``time_s`` column plus each column named in
    ``subplots``. Mapping order determines subplot order; labels and annotations
    come entirely from ``subplots``. The active region is detected automatically.
    """
    _validate_subplots(subplots)
    signal_names = tuple(subplots)

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        required_columns = {"time_s", *signal_names}
        missing_columns = sorted(required_columns.difference(reader.fieldnames or ()))
        if missing_columns:
            raise ValueError(f"{csv_path} is missing required columns: {', '.join(missing_columns)}")
        rows = list(reader)

    if len(rows) < 2:
        raise ValueError(f"{csv_path} must contain at least two waveform samples")

    time_ns = [float(row["time_s"]) * 1e9 for row in rows]
    signals = {signal: [float(row[signal]) for row in rows] for signal in signal_names}

    active_indices: list[int] = []
    edge_count = max(1, len(rows) // 20)
    for signal in signal_names:
        values = signals[signal]
        span = max(values) - min(values)
        if span <= 1e-3:
            continue
        baseline_samples = sorted(values[:edge_count] + values[-edge_count:])
        baseline = baseline_samples[len(baseline_samples) // 2]
        threshold = 0.15 * span
        active_indices.extend(index for index, value in enumerate(values) if abs(value - baseline) > threshold)

    if active_indices:
        start = time_ns[min(active_indices)]
        stop = time_ns[max(active_indices)]
        active_span = stop - start
        pad = 0.05 * active_span if active_span else 0.01 * (time_ns[-1] - time_ns[0])
        xlim = (start - pad, stop + pad)
    else:
        xlim = (time_ns[0], time_ns[-1])

    use_microseconds = max(abs(xlim[0]), abs(xlim[1]), xlim[1] - xlim[0]) >= 1_000.0
    time_divisor = 1_000.0 if use_microseconds else 1.0
    time_unit = "µs" if use_microseconds else "ns"
    plot_times = [time / time_divisor for time in time_ns]
    plot_xlim = tuple(limit / time_divisor for limit in xlim)

    colors = (NORD_BLUE, NORD_GREEN, NORD_RED, "#D08770")
    fig, axes_grid = plt.subplots(
        len(signal_names),
        1,
        figsize=(8, max(2.8, 1.6 * len(signal_names))),
        sharex=True,
        squeeze=False,
    )
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    axes = axes_grid[:, 0]
    if title:
        axes[0].set_title(title, color=TEXT_COLOR, pad=6)

    for ax, signal, spec, color in zip(
        axes, signal_names, subplots.values(), colors[: len(signal_names)], strict=True
    ):
        ax.plot(plot_times, signals[signal], color=color, linewidth=1.2)
        ax.set_ylabel(spec.ylabel)
        ax.set_xlim(*plot_xlim)
        style_ax(ax)
        style_grid(ax)
    _add_subplot_info(axes, subplots)

    axes[-1].set_xlabel(f"Time ({time_unit})")
    bottom_margin = min(0.2, 0.5 / fig.get_figheight())
    fig.subplots_adjust(left=0.13, right=0.985, bottom=bottom_margin, top=0.93, hspace=0.18)

    png_path = png_path or csv_path.with_suffix(".png")
    if png_path.suffix.lower() != ".png":
        raise ValueError(f"png_path must have a .png suffix, got {png_path}")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    plot_paths = (png_path, png_path.with_suffix(".pdf"), png_path.with_suffix(".svg"))
    for plot_path in plot_paths:
        save_kwargs = {"facecolor": PNG_FACE_COLOR}
        if plot_path.suffix == ".png":
            save_kwargs["dpi"] = 200
        fig.savefig(plot_path, **save_kwargs)
    plt.close(fig)
    return plot_paths


def plot_frequency_domain_csv(
    csv_path: Path,
    subplots: dict[str, SubplotSpec],
    *,
    png_path: Path | None = None,
    title: str | None = None,
    max_frequency_hz: float | None = None,
) -> tuple[Path, ...]:
    """Plot one-sided FFT amplitude spectra for time-domain CSV signals."""
    _validate_subplots(subplots)
    signal_names = tuple(subplots)

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        required_columns = {"time_s", *signal_names}
        missing_columns = sorted(required_columns.difference(reader.fieldnames or ()))
        if missing_columns:
            raise ValueError(f"{csv_path} is missing required columns: {', '.join(missing_columns)}")
        rows = list(reader)

    if len(rows) < 3:
        raise ValueError(f"{csv_path} must contain at least three waveform samples")
    times_s = np.asarray([float(row["time_s"]) for row in rows])
    sample_intervals_s = np.diff(times_s)
    sample_interval_s = float(np.median(sample_intervals_s))
    if not np.allclose(sample_intervals_s, sample_interval_s, rtol=1e-6, atol=1e-18):
        raise ValueError(f"{csv_path} does not have a uniformly sampled time axis")

    spectra = {}
    frequencies_hz = None
    for signal_name in signal_names:
        signal = np.asarray([float(row[signal_name]) for row in rows])
        frequencies_hz, amplitudes = amplitude_spectrum(signal, sample_interval_s)
        spectra[signal_name] = 20.0 * np.log10(np.maximum(amplitudes, 1e-12))
    assert frequencies_hz is not None

    frequency_limit_hz = frequencies_hz[-1]
    if max_frequency_hz is not None:
        if max_frequency_hz <= 0:
            raise ValueError(f"max_frequency_hz must be positive, got {max_frequency_hz}")
        frequency_limit_hz = min(frequency_limit_hz, max_frequency_hz)
    if frequency_limit_hz >= 1e9:
        frequency_scale, frequency_unit = 1e9, "GHz"
    elif frequency_limit_hz >= 1e6:
        frequency_scale, frequency_unit = 1e6, "MHz"
    elif frequency_limit_hz >= 1e3:
        frequency_scale, frequency_unit = 1e3, "kHz"
    else:
        frequency_scale, frequency_unit = 1.0, "Hz"
    plot_frequencies = frequencies_hz / frequency_scale
    plot_limit = frequency_limit_hz / frequency_scale

    colors = (NORD_BLUE, NORD_GREEN, NORD_RED, "#D08770")
    fig, axes_grid = plt.subplots(
        len(signal_names),
        1,
        figsize=(8, max(2.8, 1.6 * len(signal_names))),
        sharex=True,
        squeeze=False,
    )
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    axes = axes_grid[:, 0]
    if title:
        axes[0].set_title(title, color=TEXT_COLOR, pad=6)
    for ax, signal, spec, color in zip(
        axes, signal_names, subplots.values(), colors[: len(signal_names)], strict=True
    ):
        ax.plot(plot_frequencies, spectra[signal], color=color, linewidth=1.2)
        ax.set_ylabel(spec.ylabel)
        ax.set_xlim(0.0, plot_limit)
        ax.set_ylim(-140.0, max(5.0, float(np.max(spectra[signal])) + 5.0))
        style_ax(ax)
        style_grid(ax)
    _add_subplot_info(axes, subplots)
    axes[-1].set_xlabel(f"Frequency ({frequency_unit})")
    bottom_margin = min(0.2, 0.5 / fig.get_figheight())
    fig.subplots_adjust(left=0.15, right=0.985, bottom=bottom_margin, top=0.93, hspace=0.18)

    png_path = png_path or csv_path.with_name(f"{csv_path.stem}_spectrum.png")
    if png_path.suffix.lower() != ".png":
        raise ValueError(f"png_path must have a .png suffix, got {png_path}")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    plot_paths = (png_path, png_path.with_suffix(".pdf"), png_path.with_suffix(".svg"))
    for plot_path in plot_paths:
        save_kwargs = {"facecolor": PNG_FACE_COLOR}
        if plot_path.suffix == ".png":
            save_kwargs["dpi"] = 200
        fig.savefig(plot_path, **save_kwargs)
    plt.close(fig)
    return plot_paths


def load_adc_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_adc_csv(adc_index: int, rows: list[dict], outdir: Path, csv_path: Path | None = None) -> Path:
    """Write one ADC's captured conversion data before plotting it."""
    csv_path = csv_path or outdir / f"adc_{adc_index:02d}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"ADC {adc_index:02d}: saved data to {csv_path}")
    return csv_path


def row_vdiff_v(row: dict) -> float:
    """Return Vinp - Vinn in volts for a scan row."""
    if row.get("vdiff_v") not in (None, ""):
        return float(row["vdiff_v"])
    return float(row["vin_set_v"]) - VIN_N


def transfer_points(rows: list[dict]) -> tuple[list[float], list[float]]:
    """Return mean Dout versus Vinp - Vinn, sorted by differential input."""
    groups: dict[float, list[int]] = defaultdict(list)
    for row in rows:
        groups[row_vdiff_v(row)].append(int(row["Dout"]))

    xs = sorted(groups)
    ys = [sum(groups[x]) / len(groups[x]) for x in xs]
    return [x * 1000 for x in xs], ys


def filter_decision_path_rows(
    rows: list[dict],
    mode: str,
    *,
    row_index: int = 0,
    dout: int | None = None,
) -> tuple[list[dict], str]:
    """Select rows for decision-path plots without changing plotting logic.

    Modes:
    - ``single``: one conversion, selected by row_index.
    - ``same_dout``: all conversions with one final Dout; defaults to the most common Dout.
    - ``all``: every conversion in the file.
    """
    if mode == "single":
        if not rows:
            return [], "single_empty"
        row = rows[row_index]
        return [row], f"single_row{row_index:04d}_dout{int(row['Dout'])}"

    if mode == "same_dout":
        selected_dout = dout
        if selected_dout is None:
            counts = Counter(int(row["Dout"]) for row in rows)
            if not counts:
                return [], "same_dout_empty"
            selected_dout = counts.most_common(1)[0][0]
        return [row for row in rows if int(row["Dout"]) == selected_dout], f"same_dout{selected_dout}"

    if mode == "all":
        return rows, "all"

    raise ValueError(f"unknown decision-path filter mode {mode!r}; expected 'single', 'same_dout', or 'all'")


def decision_path_from_bbits(bbits: str, code_weights: list[int], *, initial_estimate: float = 2047.0) -> list[float]:
    """Return the running 12-bit code estimate as each B16..B0 decision is revealed."""
    bits = [int(bit) for bit in bbits.strip()]
    if len(bits) != len(code_weights):
        raise ValueError(f"Bbits has {len(bits)} bits, expected {len(code_weights)}")

    decided = 0.0
    path = [initial_estimate]
    for bit_index, bit in enumerate(bits):
        decided += code_weights[bit_index] * bit
        undecided = sum(code_weights[bit_index + 1 :])
        path.append(decided + 0.5 * undecided)

    return path


def plot_decision_paths(
    adc_cfg: dict,
    rows_or_csv: list[dict] | Path,
    outdir: Path,
    *,
    code_weights: list[int] | None = None,
    filter_mode: str = "all",
    filter_row_index: int = 0,
    filter_dout: int | None = None,
    code_center: int | None = None,
    code_half_span: int = 0,
    max_paths: int | None = None,
    show_markers: bool = False,
    show_decision_labels: bool | None = None,
    show_reference_lines: bool = True,
    show_mean_path: bool = False,
    plot_suffix: str = "",
) -> Path:
    """Plot running SAR decision paths reconstructed directly from saved Bbits strings."""
    adc_index = int(adc_cfg["adc_index"])
    artifact_stem = adc_cfg.get("artifact_stem", f"adc{adc_index:02d}_dinit{adc_cfg['dac_init_state']}")
    setup = adc_cfg.get("setup", "")
    setup_suffix = f"_{setup}" if setup else ""
    rows = load_adc_csv(rows_or_csv) if isinstance(rows_or_csv, Path) else rows_or_csv
    selected_rows, filter_label = filter_decision_path_rows(
        rows,
        filter_mode,
        row_index=filter_row_index,
        dout=filter_dout,
    )
    code_weights = code_weights or adc_cfg["code_weights"]
    outdir.mkdir(parents=True, exist_ok=True)

    filtered_rows = []
    for row in selected_rows:
        if code_center is not None and abs(int(row["Dout"]) - code_center) > code_half_span:
            continue
        filtered_rows.append(row)
        if max_paths is not None and len(filtered_rows) >= max_paths:
            break
    selected_rows = filtered_rows

    window_suffix = f"_dout{code_center}pm{code_half_span}" if code_center is not None else ""
    suffix = f"_{plot_suffix or filter_label}" if plot_suffix or filter_label else ""
    plot_path = outdir / f"{artifact_stem}_decision_paths{setup_suffix}{window_suffix}{suffix}.png"

    paths = [decision_path_from_bbits(row["Bbits"], code_weights) for row in selected_rows]
    cycles = list(range(len(code_weights) + 1))
    if show_decision_labels is None:
        show_decision_labels = len(paths) == 1

    fig, ax = plt.subplots(figsize=(13, 6.5), facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    if paths:
        alpha = min(0.8, max(0.025, 12 / len(paths)))
        for row, path in zip(selected_rows, paths, strict=True):
            color = NORD_RED if row["Bbits"].strip()[0] == "1" else NORD_BLUE
            ax.step(cycles, path, where="post", color=color, linewidth=1.0, alpha=alpha)
            if show_markers:
                ax.scatter(cycles, path, color=color, s=18, alpha=alpha, zorder=3)
            if show_decision_labels:
                for cycle, bit in enumerate(row["Bbits"].strip(), start=1):
                    ax.text(cycle - 0.5, path[cycle - 1], bit, ha="center", va="bottom", fontsize=7, color=TEXT_COLOR)

        if show_mean_path and len(paths) > 1:
            mean_path = [sum(path[cycle] for path in paths) / len(paths) for cycle in cycles]
            ax.step(cycles, mean_path, where="post", color=NORD_GREEN, linewidth=2.0, label="mean path")

        if show_reference_lines:
            ax.axhline(2047, color=SPINE_COLOR, linestyle="--", linewidth=1.0, alpha=0.7, label="midscale start")
            if len(paths) == 1:
                ax.axhline(
                    int(selected_rows[0]["Dout"]),
                    color=NORD_RED,
                    linestyle=":",
                    linewidth=1.5,
                    alpha=0.9,
                    label="final CSV Dout",
                )

    ax.set_title(f"ADC{adc_index:02d} SAR Decision Paths from 17-bit Bout")
    ax.set_xlabel("Decision cycle")
    ax.set_ylabel("Running 12-bit Dout estimate")
    ax.set_xlim(0, len(code_weights))
    ax.set_xticks(cycles)
    if paths:
        y_values = [value for path in paths for value in path]
        y_span = max(y_values) - min(y_values)
        margin = 0.05 * y_span if y_span else 1.0
        ax.set_ylim(min(y_values) - margin, max(y_values) + margin)
    style_grid(ax)
    style_ax(ax)

    if paths:
        first_row = selected_rows[0]
        input_mv = round(float(first_row["vin_set_v"]) * 1000) if first_row.get("vin_set_v") else "n/a"
        info = "\n".join(
            (
                f"Conversions: {len(paths):,}",
                f"Input: {input_mv} mV fixed",
                f"$D_{{init}}$: {adc_cfg.get('dac_init_state', 'n/a')}",
                f"Dout range: {min(int(row['Dout']) for row in selected_rows)}–{max(int(row['Dout']) for row in selected_rows)}",
            )
        )
        ax.text(
            0.98,
            0.96,
            info,
            transform=ax.transAxes,
            ha="right",
            va="top",
            color=TEXT_COLOR,
            bbox={"boxstyle": "round", "facecolor": LEGEND_FACE_COLOR, "edgecolor": SPINE_COLOR, "alpha": 0.9},
        )
    if show_reference_lines or show_mean_path:
        style_legend(ax, loc="lower right")

    fig.tight_layout()
    fig.savefig(plot_path, dpi=250, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved decision-path plot to {plot_path}")
    return plot_path


def plot_adc_transfer(adc_cfg: dict, rows_or_csv: list[dict] | Path, outdir: Path) -> Path:
    """Create one transfer plot per ADC from already-saved conversion rows."""
    adc_index = int(adc_cfg["adc_index"])
    artifact_stem = adc_cfg.get("artifact_stem", f"adc{adc_index:02d}_dinit{adc_cfg['dac_init_state']}")
    setup = adc_cfg.get("setup", "")
    setup_suffix = f"_{setup}" if setup else ""
    rows = load_adc_csv(rows_or_csv) if isinstance(rows_or_csv, Path) else rows_or_csv
    outdir.mkdir(parents=True, exist_ok=True)
    plot_path = outdir / f"{artifact_stem}_transfer{setup_suffix}.png"
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    vdiff_mv = [row_vdiff_v(row) * 1000 for row in rows]
    codes = [int(row["Dout"]) for row in rows]

    fig, ax = plt.subplots(figsize=(7, 5), facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    if codes:
        ax.scatter(vdiff_mv, codes, s=14, alpha=0.45, color=NORD_BLUE, label="individual conversions")
        mean_x, mean_y = transfer_points(rows)
        ax.plot(mean_x, mean_y, color=NORD_BLUE, linewidth=2, alpha=0.9)
        style_legend(ax)
    ax.set_title(f"FRIDA ADC {adc_index:02d} voltage sweep")
    ax.set_xlabel("Differential input Vinp - Vinn (mV)")
    ax.set_ylabel("Effective output code")
    ax.set_xlim(VDIFF_START, VDIFF_STOP)
    ax.set_ylim(0, 4095)
    style_grid(ax)
    style_ax(ax)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=200, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved transfer plot to {plot_path}")
    return plot_path


def plot_code_histogram(adc_cfg: dict, rows_or_csv: list[dict] | Path, outdir: Path) -> list[Path]:
    """Plot one 1-code-bin histogram per fixed input voltage."""
    adc_index = int(adc_cfg["adc_index"])
    artifact_stem = adc_cfg.get("artifact_stem", f"adc{adc_index:02d}_dinit{adc_cfg['dac_init_state']}")
    setup = adc_cfg.get("setup", "")
    rows = load_adc_csv(rows_or_csv) if isinstance(rows_or_csv, Path) else rows_or_csv
    outdir.mkdir(parents=True, exist_ok=True)

    rows_by_vinp: dict[float, list[dict]] = defaultdict(list)
    for row in rows:
        rows_by_vinp[float(row["vin_set_v"])].append(row)

    plot_paths = []
    for vinp_v, vinp_rows in sorted(rows_by_vinp.items()):
        vinp_mv = round(vinp_v * 1000)
        plot_path = (
            outdir / f"{artifact_stem}_noise_{setup}_vinp_{vinp_mv:04d}mV.png"
            if setup
            else outdir / f"{artifact_stem}_noise_vinp_{vinp_mv:04d}mV.png"
        )
        codes = [int(row["Dout"]) for row in vinp_rows]

        fig, ax = plt.subplots(figsize=(7, 5), facecolor=PNG_FACE_COLOR)
        fig.patch.set_facecolor(PNG_FACE_COLOR)
        if codes:
            code_min = min(codes)
            code_max = max(codes)
            bins = [code - 0.5 for code in range(code_min, code_max + 2)]
            ax.hist(codes, bins=bins, alpha=0.65, color=NORD_BLUE, edgecolor="white")

            mean = sum(codes) / len(codes)
            variance = sum((code - mean) ** 2 for code in codes) / len(codes)
            sigma = math.sqrt(variance)
            sorted_codes = sorted(codes)
            p01 = sorted_codes[round(0.01 * (len(sorted_codes) - 1))]
            p99 = sorted_codes[round(0.99 * (len(sorted_codes) - 1))]
            seq_base_freq_hz = float(adc_cfg["seq_base_freq_hz"])
            conversion_steps = int(adc_cfg["conversion_steps"])
            sample_rate_hz = seq_base_freq_hz / conversion_steps
            stats = "\n".join(
                (
                    f"Samples: {len(codes):,}",
                    f"Input: {vinp_mv} mV fixed",
                    f"$f_s$: {format_frequency_hz(sample_rate_hz)}",
                    f"$D_{{init}}$: {adc_cfg['dac_init_state']}",
                    f"Diff caps: {'enabled' if adc_cfg['dac_diffcaps'] else 'disabled'}",
                    f"Mean: {mean:.2f} codes",
                    f"σ all: {sigma:.2f} codes",
                    f"P1–P99 range: {p99 - p01} codes ({p01}–{p99})",
                    f"Range: {max(codes) - min(codes)} codes ({min(codes)}–{max(codes)})",
                )
            )
            ax.text(
                0.98,
                0.95,
                stats,
                transform=ax.transAxes,
                ha="right",
                va="top",
                color=TEXT_COLOR,
                bbox={"boxstyle": "round", "facecolor": LEGEND_FACE_COLOR, "edgecolor": SPINE_COLOR, "alpha": 0.9},
            )

            ax.set_xlim(code_min - 1, code_max + 1)
        else:
            ax.text(0.5, 0.5, "No decoded codes", transform=ax.transAxes, ha="center", va="center")

        vdiff_mv = sum(row_vdiff_v(row) for row in vinp_rows) / len(vinp_rows) * 1000
        ax.set_title(
            f"Fixed-Input Noise Histogram (ADC Channel {adc_index:02d}, Vinp={vinp_mv} mV, Vdiff={vdiff_mv:.1f} mV)"
        )
        ax.set_xlabel("Output code (Dout)")
        ax.set_ylabel("Conversions per 1-code bin")
        style_ax(ax)
        fig.tight_layout()
        fig.savefig(plot_path, dpi=200, facecolor=PNG_FACE_COLOR)
        plt.close(fig)
        print(f"ADC {adc_index:02d}: saved histogram plot to {plot_path}")
        plot_paths.append(plot_path)

    return plot_paths


def plot_noise_histogram_grid(adc_runs: list[tuple[dict, Path]], outdir: Path) -> Path:
    """Plot fixed-input noise histograms for ADC00..ADC15 in a 4x4 grid."""
    outdir.mkdir(parents=True, exist_ok=True)
    setup = adc_runs[0][0].get("setup", "setup") if adc_runs else "setup"
    dinit = adc_runs[0][0].get("dac_init_state", "dinit") if adc_runs else "dinit"
    rate_label = adc_runs[0][0].get("rate_label", "") if adc_runs else ""
    rate_suffix = f"_{rate_label}" if rate_label else ""
    plot_path = outdir / f"adc_noise_histograms_4x4_dinit{dinit}{rate_suffix}_noise_{setup}.png"
    runs_by_adc = {int(adc_cfg["adc_index"]): (adc_cfg, csv_path) for adc_cfg, csv_path in adc_runs}
    x_center = 2048
    x_half_span = 32
    x_min = x_center - x_half_span
    x_max = x_center + x_half_span
    bins = [code - 0.5 for code in range(x_min, x_max + 2)]

    first_cfg, first_csv = adc_runs[0]
    first_rows = load_adc_csv(first_csv)
    first_vinp_mv = round(float(first_rows[0]["vin_set_v"]) * 1000) if first_rows else 0
    seq_base_freq_hz = float(first_cfg["seq_base_freq_hz"])
    conversion_steps = int(first_cfg["conversion_steps"])
    sample_rate_hz = seq_base_freq_hz / conversion_steps

    fig, axes = plt.subplots(4, 4, figsize=(18, 12), sharex=True, sharey=True, facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    max_count = 0
    for adc_index, ax in enumerate(axes.flat):
        if adc_index not in runs_by_adc:
            ax.text(0.5, 0.5, "missing", transform=ax.transAxes, ha="center", va="center", color=TEXT_COLOR)
            ax.set_title(f"ADC{adc_index:02d}")
            style_ax(ax)
            continue

        _, csv_path = runs_by_adc[adc_index]
        rows = load_adc_csv(csv_path)
        codes = [int(row["Dout"]) for row in rows]
        if codes:
            counts, _, _ = ax.hist(codes, bins=bins, alpha=0.75, color=NORD_BLUE, edgecolor="white")
            max_count = max(max_count, int(max(counts, default=0)))
            mean = sum(codes) / len(codes)
            sigma = math.sqrt(sum((code - mean) ** 2 for code in codes) / len(codes))
            stats = f"μ={mean:.1f}\nσ={sigma:.1f}\nrange={max(codes) - min(codes)}"
            ax.text(
                0.96,
                0.92,
                stats,
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=8,
                color=TEXT_COLOR,
                bbox={"boxstyle": "round", "facecolor": LEGEND_FACE_COLOR, "edgecolor": SPINE_COLOR, "alpha": 0.85},
            )
        else:
            ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center", va="center", color=TEXT_COLOR)

        ax.set_title(f"ADC{adc_index:02d}")
        ax.set_xlim(x_min, x_max)
        style_ax(ax)

    for ax in axes[-1, :]:
        ax.set_xlabel("Output code")
    for ax in axes[:, 0]:
        ax.set_ylabel("Count")
    if max_count:
        for ax in axes.flat:
            ax.set_ylim(0, max_count * 1.15)

    info = "\n".join(
        (
            f"Samples/ADC: {len(first_rows):,}",
            f"Input: {first_vinp_mv} mV fixed",
            f"$f_s$: {format_frequency_hz(sample_rate_hz)}",
            f"$D_{{init}}$: {first_cfg['dac_init_state']}",
        )
    )
    fig.text(
        0.985,
        0.965,
        info,
        ha="right",
        va="top",
        color=TEXT_COLOR,
        bbox={"boxstyle": "round", "facecolor": LEGEND_FACE_COLOR, "edgecolor": SPINE_COLOR, "alpha": 0.9},
    )
    fig.suptitle("Fixed-Input Noise Histograms (ADC Channels 00–15)", color=TEXT_COLOR)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(plot_path, dpi=400, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"saved 4x4 noise histogram plot to {plot_path}")
    return plot_path


def count_output_codes(rows_or_csv: list[dict] | Path, num_codes: int = 4096) -> tuple[list[int], int]:
    """Count Dout occurrences without loading large CSV files into memory."""
    counts = [0] * num_codes
    total = 0
    if isinstance(rows_or_csv, Path):
        with rows_or_csv.open(newline="") as f:
            for row in csv.DictReader(f):
                code = int(row["Dout"])
                if 0 <= code < num_codes:
                    counts[code] += 1
                    total += 1
    else:
        for row in rows_or_csv:
            code = int(row["Dout"])
            if 0 <= code < num_codes:
                counts[code] += 1
                total += 1
    return counts, total


def analyze_code_density(
    rows_or_csv: list[dict] | Path,
    num_codes: int = 4096,
    code_range: tuple[int, int] = (1, 4094),
) -> dict:
    """Estimate DNL/INL from output-code density under a uniform ramp/triangle input.

    DNL is computed as count[k] / mean_count - 1 over the trusted code range.
    INL is the cumulative sum of DNL with an endpoint line removed. The default
    range omits only the clipped endpoint bins, codes 0 and 4095.
    """
    counts, total = count_output_codes(rows_or_csv, num_codes=num_codes)
    first_code, last_code = code_range
    if not 0 <= first_code <= last_code < num_codes:
        raise ValueError(f"code_range must fit within 0..{num_codes - 1}, got {code_range}")
    codes = list(range(first_code, last_code + 1))
    active_counts = [counts[code] for code in codes]
    ideal_count = sum(active_counts) / len(active_counts) if active_counts else 0.0
    dnl = [(count / ideal_count - 1.0) if ideal_count else 0.0 for count in active_counts]

    raw_inl = []
    cumulative = 0.0
    for value in dnl:
        raw_inl.append(cumulative)
        cumulative += value

    if len(raw_inl) > 1:
        endpoint_slope = (raw_inl[-1] - raw_inl[0]) / (len(raw_inl) - 1)
        inl = [value - (raw_inl[0] + endpoint_slope * index) for index, value in enumerate(raw_inl)]
    else:
        inl = raw_inl

    return {
        "codes": codes,
        "counts": counts,
        "active_counts": active_counts,
        "total": total,
        "ideal_count": ideal_count,
        "dnl": dnl,
        "inl": inl,
        "first_code": first_code,
        "last_code": last_code,
        "missing_codes": sum(1 for count in active_counts if count == 0),
    }


def plot_code_distribution(adc_cfg: dict, rows_or_csv: list[dict] | Path, outdir: Path) -> Path:
    """Plot output-code counts for all captured samples, ignoring input voltage metadata."""
    adc_index = int(adc_cfg["adc_index"])
    artifact_stem = adc_cfg.get("artifact_stem", f"adc{adc_index:02d}_dinit{adc_cfg['dac_init_state']}")
    setup = adc_cfg.get("setup", "")
    setup_suffix = f"_{setup}" if setup else ""
    outdir.mkdir(parents=True, exist_ok=True)
    plot_path = outdir / f"{artifact_stem}_density{setup_suffix}.png"

    counts, total = count_output_codes(rows_or_csv)
    codes = list(range(len(counts)))
    nonzero_counts = [count for count in counts if count]
    first_code, last_code = adc_cfg.get("code_range", (1, len(counts) - 2))
    active_counts = counts[first_code : last_code + 1]
    average_per_code = sum(active_counts) / len(active_counts)
    missing_codes = sum(1 for count in active_counts if count == 0)

    fig, ax = plt.subplots(figsize=(10, 5), facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    if nonzero_counts:
        ax.bar(codes, counts, width=1.0, color=NORD_BLUE, linewidth=0, align="center")
        ax.set_xlim(-1, 4096)
        ax.set_ylim(0, 2 * average_per_code)
        ax.set_title(f"Code Density (ADC Channel {adc_index:02d})")
        add_code_density_info_inset(
            ax,
            adc_cfg,
            average_per_code=average_per_code,
            missing_codes=missing_codes,
        )
    else:
        ax.text(0.5, 0.5, "No decoded codes", transform=ax.transAxes, ha="center", va="center")

    ax.set_xlabel("Output code (Dout)")
    ax.set_ylabel("Conversions / code")
    style_ax(ax)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=600, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved code distribution plot to {plot_path}")
    return plot_path


def plot_code_density_linearity(adc_cfg: dict, rows_or_csv: list[dict] | Path, outdir: Path) -> Path:
    """Plot DNL and INL from output-code density under a uniform ramp/triangle input."""
    adc_index = int(adc_cfg["adc_index"])
    artifact_stem = adc_cfg.get("artifact_stem", f"adc{adc_index:02d}_dinit{adc_cfg['dac_init_state']}")
    setup = adc_cfg.get("setup", "")
    setup_suffix = f"_{setup}" if setup else ""
    code_range = adc_cfg.get("code_range", (1, 4094))
    outdir.mkdir(parents=True, exist_ok=True)
    plot_path = outdir / f"{artifact_stem}_nonlin{setup_suffix}.png"
    analysis = analyze_code_density(rows_or_csv, code_range=code_range)
    codes = analysis["codes"]
    dnl = analysis["dnl"]
    inl = analysis["inl"]
    ideal_count = analysis["ideal_count"]
    missing_codes = analysis["missing_codes"]

    fig, (ax_dnl, ax_inl) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    if codes:
        ax_dnl.bar(codes, dnl, width=1.0, color=NORD_BLUE, linewidth=0, align="center")
        ax_inl.plot(codes, inl, color=NORD_RED, linewidth=1.0)
        ax_dnl.axhline(0, color=SPINE_COLOR, linewidth=0.8)
        ax_inl.axhline(0, color=SPINE_COLOR, linewidth=0.8)
        ax_dnl.set_xlim(codes[0] - 1, codes[-1] + 1)
        ax_dnl.set_title(f"Differential Nonlinearity (DNL, ADC Channel {adc_index:02d}, Codes {codes[0]}-{codes[-1]})")
        add_code_density_info_inset(
            ax_dnl,
            adc_cfg,
            average_per_code=ideal_count,
            missing_codes=missing_codes,
        )
        ax_inl.set_title("Integral Nonlinearity (INL)")
        print(
            f"ADC {adc_index:02d}: code-density stats: ideal={ideal_count:.2f}/code, "
            f"DNL=[{min(dnl):.2f}, {max(dnl):.2f}] LSB, INL=[{min(inl):.2f}, {max(inl):.2f}] LSB"
        )
    else:
        ax_dnl.text(0.5, 0.5, "No decoded codes", transform=ax_dnl.transAxes, ha="center", va="center")
        ax_inl.set_visible(False)

    lsb_uv = 1.2 / 4096 * 1e6
    ax_dnl.set_ylabel(f"DNL (LSB = {lsb_uv:.0f} µV)")
    ax_inl.set_xlabel(r"Output code ($D_{out}$)")
    ax_inl.set_ylabel(f"INL (LSB = {lsb_uv:.0f} µV)")
    for ax in (ax_dnl, ax_inl):
        style_grid(ax)
        style_ax(ax)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=600, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved DNL/INL plot to {plot_path}")
    return plot_path


def plot_adc_overlay(sources: list[tuple[str, Path, str]], out_path: Path = OVERLAY_PLOT) -> Path:
    """Overlay transfer curves from multiple scan_adc.py-style ADC CSV files."""
    fig, ax = plt.subplots(figsize=(7, 5), facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    plotted = 0

    for label, path, color in sources:
        if not path.exists():
            print(f"warning: skipping {label}; missing CSV {path}")
            continue

        rows = load_adc_csv(path)
        if not rows:
            print(f"warning: skipping {label}; empty CSV {path}")
            continue

        x_mv, y_code = transfer_points(rows)
        ax.plot(
            x_mv,
            y_code,
            marker="o",
            markersize=3,
            markeredgecolor="white",
            markeredgewidth=0.5,
            linewidth=2,
            color=color,
            label=label,
        )
        plotted += 1

    ax.set_title("FRIDA ADC transfer comparison")
    ax.set_xlabel("Differential input Vinp - Vinn (mV)")
    ax.set_ylabel("Effective output code")
    ax.set_xlim(VDIFF_START, VDIFF_STOP)
    ax.set_ylim(0, 4095)
    style_grid(ax)
    style_ax(ax)
    if plotted:
        style_legend(ax, title="Characterization method")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"saved overlay plot to {out_path}")
    return out_path
