"""A block's figures (``python -m flow plot <block>``): figure specs (``flow.pipeline.Plot``) drawn
with matplotlib in the style of the analysis plots (``flow.analysis.plots``, ``render``), or written
as the JSON the viewer draws with Plotly; from a sweep run's records or from captures
(``figures``).

    paths = render(comp.plot_noise_cm(offsets), Path("build/analysis/comp/noise_cm"))
"""

from __future__ import annotations

import dataclasses
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
from matplotlib.ticker import MaxNLocator

from flow.analysis.plots import CURVE_COLORS, PLOT_STYLE, SPINE_COLOR, save_figure, style_grid
from flow.pipeline import Analysis, Plot

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
    """``plot`` drawn into ``output_path`` (a stem; each enabled format of ``save_figure``): each
    series over x (NaN or None where a point failed: a gap), the histogram's as step outlines, the
    decision paths as step lines weighted by how many records took each, log axes, categories and
    whole-number ticks where the spec asks."""

    if plot.figure is not None:
        raise ValueError(f"{plot.name} is a drawn figure ({plot.figure}), not a spec to render")
    with mpl.rc_context(PLOT_STYLE):
        fig, ax = plt.subplots()
        series = {
            label: np.asarray([math.nan if value is None else value for value in values], dtype=np.float64)
            for label, values in plot.series.items()
        }
        paths = [np.asarray(path["y"], dtype=np.float64) for path in plot.paths]
        x_label, x_factor = (plot.x_label, 1.0) if plot.x_labels is not None else scaled(plot.x_label, plot.x)
        y_label, y_factor = scaled(plot.y_label, [v for y in (*series.values(), *paths) for v in y.tolist()])
        x = np.asarray(plot.x, dtype=np.float64) * x_factor
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
        for index, (label, y) in enumerate(series.items()):
            color = CURVE_COLORS[index % len(CURVE_COLORS)]
            if plot.histogram:
                ax.step(x, y * y_factor, where="mid", color=color, label=label)
            else:
                ax.plot(x, y * y_factor, marker="o", color=color, label=label)
        ax.set_xscale("log" if plot.x_log else "linear")
        ax.set_yscale("log" if plot.y_log else "linear")
        if plot.x_labels is not None:
            ax.set_xticks(range(len(plot.x_labels)), plot.x_labels, rotation=45 if len(plot.x_labels) > 6 else 0)
        for axis, ticks in ((ax.xaxis, plot.x_ticks if plot.x_labels is None else None), (ax.yaxis, plot.y_ticks)):
            if ticks in ("integer", "code", "step"):
                axis.set_major_locator(MaxNLocator(integer=True))
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(plot.title)
        style_grid(ax)
        if len(plot.series) > 1:
            ax.legend(title=plot.legend_title)
        return save_figure(fig, Path(output_path))


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
            path.write_text(json.dumps(_finite(dataclasses.asdict(plot))))
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
                    emit(Plot(**detail), Path(record["pdk"], path.parent.name, detail["name"]))
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
