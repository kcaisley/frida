"""Shared ADC scan plotting helpers.

Run the overlay plotter from /local/frida with:
    uv run python -m flow.scans.plot
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PNG_FACE_COLOR = "white"
TEXT_COLOR = "#2E3440"
SPINE_COLOR = "#4C566A"
LEGEND_FACE_COLOR = "#ECEFF4"
GRID_MAJOR_COLOR = "#D8DEE9"
GRID_MINOR_COLOR = "#E5E9F0"
NORD_RED = "#BF616A"
NORD_GREEN = "#A3BE8C"
NORD_BLUE = "#5E81AC"

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
    "sweep_index",
    "vin_set_v",
    "vin_read_v",
    "vdiff_v",
    "conversion_index",
    "raw_word0",
    "raw_word1",
    "id0",
    "id1",
    "frame0",
    "frame1",
    "spi0",
    "spi1",
    "Bbits",
    "Dout",
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


def plot_adc_transfer(
    adc_index: int,
    rows: list[dict],
    outdir: Path,
    *,
    title: str | None = None,
    label: str = "conversions",
    color: str | None = None,
    xlim: tuple[float, float] = (VDIFF_START, VDIFF_STOP),
) -> Path:
    """Create one transfer plot per ADC from already-saved conversion rows."""
    outdir.mkdir(parents=True, exist_ok=True)
    plot_path = outdir / f"adc_{adc_index:02d}_transfer.png"
    vdiff_mv = [row_vdiff_v(row) * 1000 for row in rows]
    codes = [int(row["Dout"]) for row in rows]

    fig, ax = plt.subplots(figsize=(7, 5), facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    if codes:
        ax.scatter(vdiff_mv, codes, s=14, alpha=0.45, color=color, label=label)
        mean_x, mean_y = transfer_points(rows)
        ax.plot(mean_x, mean_y, color=color, linewidth=2, alpha=0.9)
        style_legend(ax)
    ax.set_title(title or f"FRIDA ADC {adc_index:02d} voltage sweep")
    ax.set_xlabel("Differential input Vinp - Vinn (mV)")
    ax.set_ylabel("Effective output code")
    ax.set_xlim(*xlim)
    ax.set_ylim(0, 4095)
    style_grid(ax)
    style_ax(ax)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=200, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved transfer plot to {plot_path}")
    return plot_path


def plot_code_histogram(adc_index: int, rows: list[dict], outdir: Path) -> Path:
    """Plot a 1-code-bin histogram for repeated conversions at one input voltage."""
    outdir.mkdir(parents=True, exist_ok=True)
    plot_path = outdir / f"adc_{adc_index:02d}_histogram.png"
    codes = [int(row["Dout"]) for row in rows]

    fig, ax = plt.subplots(figsize=(7, 5), facecolor=PNG_FACE_COLOR)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    if codes:
        code_min = min(codes)
        code_max = max(codes)
        bins = [code - 0.5 for code in range(code_min, code_max + 2)]
        ax.hist(codes, bins=bins, alpha=0.65, color=NORD_BLUE, edgecolor="white", label="output code counts")

        mean = sum(codes) / len(codes)
        variance = sum((code - mean) ** 2 for code in codes) / len(codes)
        sigma = math.sqrt(variance)
        stats = f"N = {len(codes)}\nμ = {mean:.2f} codes\nσ = {sigma:.2f} codes"
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
        style_legend(ax)
    else:
        ax.text(0.5, 0.5, "No decoded codes", transform=ax.transAxes, ha="center", va="center")

    if rows:
        vdiff_mv = sum(row_vdiff_v(row) for row in rows) / len(rows) * 1000
        ax.set_title(f"FRIDA ADC {adc_index:02d} output-code histogram at Vdiff={vdiff_mv:.1f} mV")
    else:
        ax.set_title(f"FRIDA ADC {adc_index:02d} output-code histogram")
    ax.set_xlabel("Output code (Dout)")
    ax.set_ylabel("Conversions per 1-code bin")
    style_grid(ax)
    style_ax(ax)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=200, facecolor=PNG_FACE_COLOR)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved histogram plot to {plot_path}")
    return plot_path


def plot_adc_overlay(sources: list[tuple[str, Path, str]], out_path: Path = OVERLAY_PLOT) -> Path:
    """Overlay transfer curves from multiple basic.py-style ADC CSV files."""
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


def main() -> None:
    plot_adc_overlay(OVERLAY_SOURCES, OVERLAY_PLOT)


if __name__ == "__main__":
    main()
