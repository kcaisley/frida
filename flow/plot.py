"""A block's figures (``python -m flow plot <block>``): figure specs (``flow.pipeline.Plot``) drawn
with matplotlib in the style of the analysis plots (``flow.analysis.plots``, ``render``), or written
as the JSON the viewer draws with Plotly; from a sweep run's records or from captures
(``figures``).

    paths = render(comp.plot_noise_cm(common_mode), Path("build/analysis/comp/noise_cm"))
"""

from __future__ import annotations

import inspect
import json
import math
import typing
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LogNorm
from matplotlib.figure import Figure
from matplotlib.ticker import FixedLocator, LogLocator, MaxNLocator, NullFormatter

from flow.analysis.plots import CURVE_COLORS, DENSITY_COLOR_MAP, PLOT_STYLE, SPINE_COLOR, save_figure, style_grid
from flow.pipeline import Analysis, Heatmap, Plot

# the units an axis label ends in that take an SI prefix, as the viewer scales them (detail.js)
SCALABLE = ("s", "V", "A", "J", "W", "F", "Hz", "Ω", "C", "V/C", "V/√Hz")
PREFIXES = {-18: "a", -15: "f", -12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T"}


def scaled(label: str, values: Sequence[float]) -> tuple[str, float]:
    """An axis's label with the SI prefix that brings its largest finite magnitude into [1, 1000),
    and the factor its values take (the viewer's ``unitScale``)."""
    unit = label[label.rfind("(") + 1 : -1] if label.endswith(")") and "(" in label else ""
    finite = [abs(value) for value in values if value is not None and math.isfinite(value) and value]
    if unit not in SCALABLE or not finite:
        return label, 1.0
    exponent = max(-18, min(12, math.floor(math.log10(max(finite)) / 3) * 3))
    return f"{label[: label.rfind('(')]}({PREFIXES[exponent]}{unit})", 10.0**-exponent


def render(plot: Plot, output_path: Path) -> tuple[Path, ...]:
    """``plot`` drawn into ``output_path`` (a stem; each enabled format of ``save_figure``): its
    heatmap under everything, in the density colours beside its colour bar (by decade where it
    asks); each series over x (NaN or None where a point failed: a gap), a few points marked and a
    long series (over 100 points: a spectrum, a code axis, a waveform) a plain line, as the viewer
    draws them, the histogram's as step outlines, the decision paths as step lines weighted by how
    many records took each; its bands shaded behind the curves and its markers dashed over them, in
    the spine's grey, each labelled at the plot's edge; log axes ticked as the viewer ticks them,
    categories on either axis (each ticked by its name, nothing between) and whole-number ticks
    where the spec asks."""

    if plot.figure is not None:
        raise ValueError(f"{plot.name} is a drawn figure ({plot.figure}), not a spec to render")
    with mpl.rc_context(PLOT_STYLE):
        fig, ax = plt.subplots()
        series = {
            label: np.asarray([math.nan if value is None else value for value in values], dtype=np.float64)
            for label, values in plot.series.items()
        }
        paths = [np.asarray(path["y"], dtype=np.float64) for path in plot.paths]
        heatmap = plot.heatmap
        # the SI prefixes from the values drawn (a map's cell edges among them), not the markers
        x_values = [*plot.x, *(heatmap.x if heatmap else ())]
        y_values = [*(v for y in (*series.values(), *paths) for v in y.tolist()), *(heatmap.y if heatmap else ())]
        x_label, x_factor = (plot.x_label, 1.0) if plot.x_labels is not None else scaled(plot.x_label, x_values)
        y_label, y_factor = (plot.y_label, 1.0) if plot.y_labels is not None else scaled(plot.y_label, y_values)
        x = np.asarray(plot.x, dtype=np.float64) * x_factor
        if heatmap is not None:
            _heatmap(fig, ax, heatmap, x_factor, y_factor)
        heaviest = max((path["count"] for path in plot.paths), default=1)
        for path, y in zip(plot.paths, paths, strict=True):
            ax.step(
                x[: len(y)],
                y * y_factor,
                where="post",
                color=SPINE_COLOR,
                alpha=0.15 + 0.85 * path["count"] / heaviest,
                linewidth=0.5 + 1.5 * path["count"] / heaviest,
            )
        dense = len(x) > 100
        for index, (label, y) in enumerate(series.items()):
            color = CURVE_COLORS[index % len(CURVE_COLORS)]
            if plot.histogram:
                ax.step(x, y * y_factor, where="mid", color=color, label=label)
            else:
                ax.plot(x, y * y_factor, marker=None if dense else "o", color=color, label=label)
        # the data's x (a map's cell edges among them), where a band's label stays inside the plot
        x_drawn = np.asarray([*plot.x, *(heatmap.x if heatmap else ())], dtype=np.float64) * x_factor
        x_drawn = x_drawn[np.isfinite(x_drawn) & ((x_drawn > 0) if plot.x_log else True)]
        x_extent = (float(x_drawn.min()), float(x_drawn.max())) if x_drawn.size else (math.nan, math.nan)
        _guides(ax, plot, x_factor, y_factor, x_extent)
        ax.set_xscale("log" if plot.x_log else "linear")
        ax.set_yscale("log" if plot.y_log else "linear")
        for axis, log, names in ((ax.xaxis, plot.x_log, plot.x_labels), (ax.yaxis, plot.y_log, plot.y_labels)):
            if log and names is None:
                _log_ticks(axis)
        if plot.x_labels is not None:
            # angled where they would collide, each name ending at its tick
            angled = {"rotation": 45, "ha": "right", "rotation_mode": "anchor"} if len(plot.x_labels) > 6 else {}
            ax.set_xticks(range(len(plot.x_labels)), plot.x_labels, **angled)
        if plot.y_labels is not None:
            ax.set_yticks(range(len(plot.y_labels)), plot.y_labels)
        for axis, ticks, labels in (
            (ax.xaxis, plot.x_ticks, plot.x_labels),
            (ax.yaxis, plot.y_ticks, plot.y_labels),
        ):
            if labels is not None:
                # categories: each ticked by its name, nothing between (style_grid keeps a set locator)
                axis.set_minor_locator(FixedLocator([]))
            elif ticks in ("integer", "code", "step"):
                axis.set_major_locator(MaxNLocator(integer=True))
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(plot.title)
        style_grid(ax)
        if len(plot.series) > 1:
            ax.legend(title=plot.legend_title)
        return save_figure(fig, Path(output_path))


def _heatmap(fig: Figure, ax: Axes, heatmap: Heatmap, x_factor: float, y_factor: float) -> None:
    """``heatmap`` on its cells' edges in the density colours, its colour bar beside the plot (by
    decade on a log scale, its label's SI prefix from the values), an empty cell (NaN or None, on a
    log scale one at or under 0 as well) the paper."""
    z = np.asarray([[math.nan if value is None else value for value in row] for row in heatmap.z], dtype=np.float64)
    label, factor = scaled(heatmap.label, z.ravel().tolist())
    z = z * factor
    if heatmap.log:
        with np.errstate(invalid="ignore"):
            z[~(z > 0)] = math.nan
    mesh = ax.pcolormesh(
        np.asarray(heatmap.x, dtype=np.float64) * x_factor,
        np.asarray(heatmap.y, dtype=np.float64) * y_factor,
        np.ma.masked_invalid(z),
        cmap=DENSITY_COLOR_MAP,
        norm=LogNorm() if heatmap.log and np.isfinite(z).any() else None,
        shading="flat",
        rasterized=True,
    )
    fig.colorbar(mesh, ax=ax, label=label)


def _guides(ax: Axes, plot: Plot, x_factor: float, y_factor: float, x_extent: tuple[float, float]) -> None:
    """``plot``'s bands shaded behind its curves (over the grid, under a map) and its markers dashed
    over them, in the spine's grey, each labelled at the plot's edge: a band's at its top (at its
    outer edge where it lies at the end of the data's x, ``x_extent``), an x marker's along it at
    the top, a y marker's over it at the right. One with no place on its axis (not a number, or not
    positive on a log axis) is left out."""
    # x in data and y in the axes' height (a label at its top), or the other way round (at its right)
    along_x, along_y = ax.get_xaxis_transform(), ax.get_yaxis_transform()
    for band in plot.x_bands:
        low, high = _place(band.low, x_factor, plot.x_log), _place(band.high, x_factor, plot.x_log)
        if math.isnan(low) or math.isnan(high):
            continue
        ax.axvspan(low, high, color=SPINE_COLOR, alpha=0.15, linewidth=0, zorder=0.8)
        if band.label:
            side = _band_side(low, high, x_extent, plot.x_log)
            at = {"left": low, "right": high}.get(side, math.sqrt(low * high) if plot.x_log else (low + high) / 2)
            ax.text(at, 0.98, band.label, transform=along_x, ha=side, va="top", color=SPINE_COLOR, size="small")
    for marker in plot.x_markers:
        at = _place(marker.at, x_factor, plot.x_log)
        if math.isnan(at):
            continue
        ax.axvline(at, color=SPINE_COLOR, linestyle="--", linewidth=0.8, zorder=2.5)
        if marker.label:
            ax.text(
                at,
                0.98,
                marker.label,
                transform=along_x,
                rotation=90,
                ha="right",
                va="top",
                color=SPINE_COLOR,
                size="small",
            )
    for marker in plot.y_markers:
        at = _place(marker.at, y_factor, plot.y_log)
        if math.isnan(at):
            continue
        ax.axhline(at, color=SPINE_COLOR, linestyle="--", linewidth=0.8, zorder=2.5)
        if marker.label:
            ax.text(0.99, at, marker.label, transform=along_y, ha="right", va="bottom", color=SPINE_COLOR, size="small")


def _band_side(low: float, high: float, extent: tuple[float, float], log: bool) -> str:
    """Where a band's label sits along it (detail.js ``bandSide``): at its outer edge and inside it
    ("left", "right") where the band's middle lies in the first or last fifth of the data's x (a
    centred label there would run off the plot), "center" otherwise."""
    first, last = (math.log10(value) if log else value for value in extent)
    middle = (math.log10(low * high) / 2) if log else (low + high) / 2
    if not last - first > 0:
        return "center"
    share = (middle - first) / (last - first)
    return "right" if share >= 0.8 else "left" if share <= 0.2 else "center"


def _log_ticks(axis) -> None:
    """A log axis ticked over its view as the viewer ticks one (paper.js ``fitAxis``): under 0.8
    decades linear steps of 1, 2 or 5 times a power of ten, each labelled in full; to 2.5 decades
    1, 2 and 5 of each decade; beyond, the decades (every second or more past 7), plainly where they
    all read so (0.001 to 10000) and as powers of ten otherwise; the digits between ticked, unlabelled."""
    low, high = sorted(axis.get_view_interval())
    if not (low > 0 and high > low):
        return
    decades = math.log10(high / low)
    if decades < 0.8:
        step = _nice((high - low) / 5)
        ticks = [k * step for k in range(math.ceil(low / step), math.floor(high / step) + 1)]
        labels = [f"{tick:.6g}" for tick in ticks]
    elif decades <= 2.5:
        ticks = [
            float(f"{mantissa * 10.0**exponent:.6g}")
            for exponent in range(math.floor(math.log10(low)), math.ceil(math.log10(high)) + 1)
            for mantissa in (1, 2, 5)
        ]
        ticks = [tick for tick in ticks if low <= tick <= high]
        labels = [_log_label(tick) for tick in ticks]
    else:
        every = 1 if decades <= 7 else math.ceil(decades / 7)
        first, last = math.ceil(math.log10(low) - 1e-9), math.floor(math.log10(high) + 1e-9)
        exponents = [e for e in range(math.ceil(first / every) * every, last + 1, every)]
        plain = first >= -3 and last <= 4
        ticks = [10.0**exponent for exponent in exponents]
        labels = [_log_label(10.0**e) if plain or e in (0, 1) else f"$10^{{{e}}}$" for e in exponents]
    axis.set_major_locator(FixedLocator(ticks))
    axis.set_ticklabels(labels)
    axis.set_minor_locator(LogLocator(base=10, subs=tuple(range(1, 10)), numticks=100))
    axis.set_minor_formatter(NullFormatter())


def _nice(rough: float) -> float:
    """The smallest 1, 2 or 5 times a power of ten at least ``rough`` (paper.js ``niceStep``)."""
    power = 10.0 ** math.floor(math.log10(rough))
    return next(m * power for m in (1, 2, 5, 10) if m * power >= rough * (1 - 1e-9))


def _log_label(value: float) -> str:
    """A positive tick as the viewer labels it (paper.js ``logLabel``): plain from 0.001 to 99999,
    a mantissa times a power of ten beyond."""
    exponent = math.floor(math.log10(value) + 1e-9)
    if -3 <= exponent <= 4:
        return f"{value:.6g}"
    mantissa = float(f"{value / 10.0**exponent:.3g}")
    return f"$10^{{{exponent}}}$" if mantissa == 1 else f"${mantissa:g}{{\\times}}10^{{{exponent}}}$"


def _place(value: float | None, factor: float, log: bool) -> float:
    """A marker's or a band edge's place on its axis, in the axis's prefixed unit: NaN where it has
    none (not a number, or not positive on a log axis)."""
    if value is None or not math.isfinite(value) or (log and value <= 0):
        return math.nan
    return value * factor


def _finite(value):
    """A spec's JSON as the viewer reads it: NaN (a failed point) as null."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    return value


def resolvable(block: str) -> dict[str, tuple[Any, ...]]:
    """The block's figures drawn from captures, by name: each ``plot_<name>`` of its ``plots.py`` that
    takes one result, with the analysis of its ``analysis.py`` that gives that result from a
    sequence of captures, and the captures' type."""

    analyses = import_module(f"flow.{block}.analysis")
    plots = import_module(f"flow.{block}.plots")
    found = {}
    for name, function in vars(plots).items():
        if not name.startswith("plot_") or not inspect.isfunction(function):
            continue
        hints = typing.get_type_hints(function)
        hints.pop("return", None)
        if len(hints) != 1:
            continue
        (result,) = hints.values()
        for analysis in vars(analyses).values():
            if not inspect.isfunction(analysis) or not analysis.__name__.startswith("analyze_"):
                continue
            needs = typing.get_type_hints(analysis)
            given = needs.pop("return", None)
            parameters = [
                p for p in inspect.signature(analysis).parameters.values() if p.kind is p.POSITIONAL_OR_KEYWORD
            ]
            if given is not result or len(needs) != 1 or len(parameters) != 1:
                continue
            (sequence,) = needs.values()
            if typing.get_origin(sequence) is Sequence and issubclass(typing.get_args(sequence)[0], Analysis):
                found[name.removeprefix("plot_")] = (function, analysis, typing.get_args(sequence)[0])
    return found


def figures(
    block: str,
    sources: Sequence[Path],
    names: Sequence[str] = (),
    *,
    backend: str = "matplotlib",
    pdks: Sequence[str] = (),
    instances: Sequence[str] = (),
    out_dir: Path | None = None,
) -> list[Path]:
    """The block's figures from ``sources`` into ``out_dir`` (a fresh ``build/analysis/<block>/``
    run): from a sweep run (its records' plots, those ``names``, of the instances ``pdks`` and
    ``instances`` pick by label or digest), or from captures (each figure of ``resolvable``, or
    those ``names``, of each board and channel's captures). ``backend`` "matplotlib" draws them,
    "web" writes each spec as the JSON the viewer draws (a record's plots it shows already)."""

    from flow import new_run
    from flow.analysis.io import read_analysis

    written: list[Path] = []
    made: list[Path] = [out_dir] if out_dir else []

    def emit(plot: Plot, stem: Path) -> None:
        # the run directory made with the first figure
        if not made:
            made.append(new_run("analysis", block))
        stem = made[0] / stem
        if backend == "web":
            stem.parent.mkdir(parents=True, exist_ok=True)
            path = stem.with_suffix(".json")
            path.write_text(json.dumps(_finite(plot.to_json())))
            written.append(path)
        else:
            written.extend(render(plot, stem))

    records = sorted(path for source in sources for path in Path(source).glob("*/*/instance.json"))
    if records:
        for path in records:
            record = json.loads(path.read_text())
            if (pdks and record["pdk"] not in pdks) or (
                instances and not {record.get("label"), path.parent.name} & set(instances)
            ):
                continue
            for detail in record["details"]:
                if not names or detail["name"] in names:
                    emit(Plot.from_json(detail), Path(record["pdk"], path.parent.name, detail["name"]))
        return written

    available = resolvable(block)
    unknown = set(names) - set(available)
    if unknown:
        raise LookupError(f"no figure {sorted(unknown)} of {block} from captures: {', '.join(available)}")
    captures = [read_analysis(path) for source in sources for path in sorted(Path(source).rglob("*.h5"))]
    if not captures:
        raise FileNotFoundError(f"no sweep run's records and no captures in {', '.join(map(str, sources))}")
    channels: dict[tuple[Any, ...], list[Any]] = {}
    for capture in captures:
        channels.setdefault((capture.group, capture.index), []).append(capture)
    for name in names or available:
        plot, analysis, kind = available[name]
        for (group, index), channel in channels.items():
            if not all(isinstance(capture, kind) for capture in channel):
                continue
            try:
                result = analysis(channel)
            except ValueError as error:
                if names:
                    raise
                print(f"{name}: not from the captures of board {group}, channel {index}: {error}")
                continue
            emit(plot(result), Path(f"{name}_board{group}_channel{index}"))
    return written
