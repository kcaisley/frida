"""A block's figures (``python -m flow plot <block>``): figure specs (``flow.pipeline.Plot``) drawn
with matplotlib in the style of the analysis plots (``flow.analysis.plots``, ``render``), or written
as the JSON the viewer draws with Plotly; from a sweep run's records or from captures
(``figures``).

    paths = render(comp.plot_noise_cm(common_mode), Path("build/analysis/comp/noise_cm"))
"""

from __future__ import annotations

import inspect
import itertools
import json
import math
import typing
from collections.abc import Sequence
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from types import UnionType
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LogNorm
from matplotlib.figure import Figure
from matplotlib.ticker import FixedLocator, LogLocator, MaxNLocator, NullFormatter

from flow import pipeline
from flow.analysis.plots import CURVE_COLORS, DENSITY_COLOR_MAP, PLOT_STYLE, SPINE_COLOR, save_figure, style_grid
from flow.pipeline import Heatmap, Plot

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


def _members(hint: Any) -> tuple[type, ...]:
    """The classes ``hint`` names: itself, or a union's members (None left out)."""
    if isinstance(hint, UnionType) or typing.get_origin(hint) is typing.Union:
        return tuple(
            member for member in typing.get_args(hint) if isinstance(member, type) and member is not type(None)
        )
    return (hint,) if isinstance(hint, type) else ()


def _of(hint: Any) -> tuple[tuple[type, ...], bool]:
    """What a parameter takes: its classes, and whether a sequence of them (``Sequence[X]``)."""
    if typing.get_origin(hint) is Sequence:
        return _members(typing.get_args(hint)[0]), True
    return _members(hint), False


def _stages(block: str, kind: str) -> list[Any]:
    """The analyses (``kind`` "analysis") or figures ("plots") a block's figures from captures draw
    on: its own, then those of every block whose results they take or give (the ADC's: the
    comparator's and the DAC's), each module once."""

    modules, pending = [], [block]
    while pending:
        name = pending.pop(0)
        if name in modules:
            continue
        modules.append(name)
        for function in vars(import_module(f"flow.{name}.analysis")).values():
            if not inspect.isfunction(function) or pipeline.STAGE_FUNCTIONS.get(function) != "analysis":
                continue
            for hint in typing.get_type_hints(function).values():
                for member in (*_of(hint)[0], *_members(hint)):
                    owner = member.__module__.split(".")
                    if (
                        len(owner) == 3
                        and owner[0] == "flow"
                        and owner[2] == "types"
                        and owner[1] not in modules
                        and find_spec(f"flow.{owner[1]}.analysis") is not None
                    ):
                        pending.append(owner[1])
    found, names = [], set()
    for name in modules:
        for function_name, function in vars(import_module(f"flow.{name}.{kind}")).items():
            stage = "analysis" if kind == "analysis" else "plot"
            if (
                inspect.isfunction(function)
                and pipeline.STAGE_FUNCTIONS.get(function) == stage
                and function_name not in names
            ):
                names.add(function_name)
                found.append(function)
    return found


def _returns(function: Any) -> type:
    return typing.get_type_hints(function)["return"]


def _producers(analyses: Sequence[Any], wanted: type) -> list[Any]:
    """The analyses that give a ``wanted`` result: the first that gives it exactly, else each that
    gives one of its kinds (the ADC's three calibrations of ``AnalysisCalibration``)."""
    exact = [analysis for analysis in analyses if _returns(analysis) is wanted]
    return exact[:1] or [analysis for analysis in analyses if issubclass(_returns(analysis), wanted)]


def resolvable(block: str) -> dict[str, tuple[Any, type, bool]]:
    """The block's figures drawn from captures, by name: each ``plot_<name>`` of its ``plots.py``
    (or of the plots of a block whose results its analyses give: the ADC's of the DAC's mismatch)
    that takes one result, or a sequence of them, which a capture is or an analysis gives, with
    that result's type and whether it takes a sequence."""

    analyses = _stages(block, "analysis")
    found = {}
    for function in _stages(block, "plots"):
        hints = typing.get_type_hints(function)
        hints.pop("return", None)
        if len(hints) != 1:
            continue
        (kinds, many) = _of(next(iter(hints.values())))
        if len(kinds) == 1 and (
            _producers(analyses, kinds[0]) or getattr(kinds[0], "__module__", "").endswith(".types")
        ):
            found.setdefault(function.__name__.removeprefix("plot_"), (function, kinds[0], many))
    return found


def _stem(capture: Any) -> str:
    """A capture's name in its figures' names: its file's stem."""
    source = getattr(getattr(capture, "info", None), "source_path", None)
    return Path(source).stem if source else f"capture{id(capture):x}"


def _tag(*parts: str) -> str:
    """A figure's name from its parts, each once."""
    return "_".join(dict.fromkeys(part for part in parts if part))


def _ids(value: Any) -> Any:
    """A value's identity as an analysis's input: a sequence's, its items'."""
    return tuple(map(id, value)) if isinstance(value, list) else id(value)


def _gathered(analyses: Sequence[Any], kind: type, composer: _Composer) -> list[Any]:
    """The results a board's channels gather for a figure of ``kind`` (an ADC's operating
    conditions, for a chip's sequence map): where its analysis takes, and needs nothing but, a
    sequence of results the channel's captures make once (an analysis of a sequence of them), the
    channel's; none otherwise."""
    producers = _producers(analyses, kind)
    if len(producers) != 1:
        return []
    parameters = list(inspect.signature(producers[0]).parameters.values())
    if any(parameter.default is inspect.Parameter.empty for parameter in parameters[1:]):
        return []
    kinds, many = _of(typing.get_type_hints(producers[0])[parameters[0].name])
    if not many or len(kinds) != 1 or any(isinstance(item, kinds[0]) for item in composer.channel):
        return []
    inner = _producers(analyses, kinds[0])
    if not inner or not all(
        _of(typing.get_type_hints(producer)[next(iter(inspect.signature(producer).parameters))])[1]
        for producer in inner
    ):
        return []
    return [value for value, _parts in composer.values(kinds[0], [], split=False)]


class _Composer:
    """A channel's results by type, each made from its captures as the block's analyses chain them
    (``figures``): a capture of that kind, or the analysis that gives it, its input and its priors
    made the same way; each analysis call kept, so a result is made once, and each that failed
    (``ValueError``, or ``KeyError`` for a wave a capture has not: not of these captures) noted."""

    def __init__(self, analyses: Sequence[Any], channel: Sequence[Any], priors: bool) -> None:
        self.analyses, self.channel, self.priors = analyses, list(channel), priors
        self.made: dict[tuple[Any, ...], Any] = {}
        self.making: list[tuple[Any, Any]] = []
        self.failures: dict[str, None] = {}

    def values(self, hint: Any, inputs: Sequence[Any], *, split: bool) -> list[tuple[Any, tuple[str, ...]]]:
        """Each value a parameter annotated ``hint`` takes for an analysis of ``inputs``, with what
        names it among several: captures of its kind (the analysis's own where they are of it,
        else the channel's), one each (each its file's name) or all as a sequence; else what its
        analysis makes (each analysis's name where several give one of its kinds), one capture at a
        time or once, a sequence made one capture at a time taken one sweep at a time (its name)
        where ``split`` and its captures name their sweep (``MeasAdc.sweep``)."""

        return self.made_of(*_of(hint), inputs, split=split)

    def made_of(
        self, kinds: tuple[type, ...], many: bool, inputs: Sequence[Any], *, split: bool
    ) -> list[tuple[Any, tuple[str, ...]]]:
        """``values`` of a parameter of ``kinds`` (a sequence of them where ``many``)."""
        captured = [item for item in inputs if isinstance(item, kinds)] or [
            item for item in self.channel if isinstance(item, kinds)
        ]
        if captured:
            return [(captured, ())] if many else [(item, (_stem(item),)) for item in captured]
        # a result made of these inputs while it is being made (a cycle of priors): none
        making = (kinds[0] if kinds else None, _ids(list(inputs)))
        if len(kinds) != 1 or making in self.making:
            return []
        self.making.append(making)
        producers = _producers(self.analyses, kinds[0])
        try:
            produced = [
                (value, (producer.__name__.removeprefix("analyze_"),) * (len(producers) > 1) + parts, source)
                for producer in producers
                for value, parts, source in self.results(producer, inputs)
            ]
        finally:
            self.making.pop()
        if not many:
            return [(value, parts) for value, parts, _source in produced]
        if not produced or produced[0][2] is None:
            return [([value], parts) for value, parts, _source in produced]
        sweeps: dict[tuple[str, ...], list[Any]] = {}
        for value, parts, source in produced:
            key = (*parts[: len(producers) > 1], getattr(source, "sweep", "") if split else "")
            sweeps.setdefault(key, []).append(value)
        return [(values, key) for key, values in sweeps.items()]

    def results(self, analysis: Any, inputs: Sequence[Any]) -> list[tuple[Any, tuple[str, ...], Any]]:
        """``analysis`` over the values its input takes (``values``), each with its required priors
        (made from that input, one value each) and its optional ones (None; with ``priors``, at the
        top, each the captures make instead): the results, what names each and the capture each was
        made of (None for one of several)."""

        parameters = list(inspect.signature(analysis).parameters.values())
        hints = typing.get_type_hints(analysis)
        primary, rest = parameters[0], parameters[1:]
        # the figure's own analysis: its optional priors taken where ``priors`` asks
        top = len(self.making) == 1
        produced = []
        for value, parts in self.values(hints[primary.name], inputs, split=True):
            given = value if isinstance(value, list) else [value]
            choices: list[list[tuple[str, Any, tuple[str, ...]]]] = []
            for parameter in rest:
                optional = parameter.default is None
                if optional and not (self.priors and top):
                    continue
                candidates = self.values(hints[parameter.name], given, split=False)
                if not optional and len(candidates) != 1:
                    break
                choices.append([(parameter.name, item, item_parts) for item, item_parts in candidates])
            else:
                for combination in itertools.product(*choices):
                    keywords = {name: item for name, item, _parts in combination}
                    key = (analysis, _ids(value), *((name, _ids(item)) for name, item in keywords.items()))
                    if key not in self.made:
                        try:
                            self.made[key] = analysis(value, **keywords)
                        except (ValueError, KeyError) as error:
                            # not of these captures (a capture without the run, or the waves, it takes)
                            self.made[key] = None
                            self.failures[f"{analysis.__name__}: {error!s}"] = None
                    if self.made[key] is not None:
                        names = (*parts, *(part for _name, _item, item_parts in combination for part in item_parts))
                        produced.append((self.made[key], names, None if isinstance(value, list) else value))
        return produced


def figures(
    block: str,
    sources: Sequence[Path],
    names: Sequence[str] = (),
    *,
    backend: str = "matplotlib",
    pdks: Sequence[str] = (),
    instances: Sequence[str] = (),
    out_dir: Path | None = None,
    priors: bool = False,
) -> list[Path]:
    """The block's figures from ``sources`` into ``out_dir`` (a fresh ``build/analysis/<block>/``
    run): from a sweep run (its records' plots, those ``names``, of the instances ``pdks`` and
    ``instances`` pick by label or digest), or from captures (each figure of ``resolvable``, or
    those ``names``, of each board and channel's captures). ``backend`` "matplotlib" draws them,
    "web" writes each spec as the JSON the viewer draws (a record's plots it shows already).

    From captures (directories of them, each HDF5 file beneath, or files): a channel's captures
    (one board's ``group`` and ``index``) make each figure's result as the block's analyses chain
    them: a capture of its kind, or the analysis that gives it (of the block's, then of the blocks
    whose results they take), whose input is made the same way: a capture each where it takes one
    (a figure each), all of its kind where it takes a sequence; a sequence an analysis makes one
    capture at a time is taken one sweep at a time where the captures name their sweep (an ADC's:
    its input, common mode and sequence, ``MeasAdc.sweep``, so a sweep over the rate is one curve);
    its required priors are made the same way from its own input, its optional ones left out (with
    ``priors``, each the captures make taken instead: a ramp decoded by each calibration). A result
    several analyses give (each of its kinds) is drawn for each. An analysis of the results one
    channel's captures make once (an ADC's operating conditions) is drawn for each channel and for
    every channel of a board together (``_board<g>``). A figure's name ends in what it is of where
    there are several: the capture, the sweep, the analysis or the prior."""

    from flow import new_run
    from flow.analysis.io import read_capture, read_channel

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
    paths = [
        path
        for source in sources
        for path in ([Path(source)] if Path(source).is_file() else sorted(Path(source).rglob("*.h5")))
    ]
    if not paths:
        raise FileNotFoundError(f"no sweep run's records and no captures in {', '.join(map(str, sources))}")
    # the captures read one channel at a time, in the order given (a later run's after an earlier one's)
    channels: dict[tuple[Any, ...], list[Path]] = {}
    for path in paths:
        channels.setdefault(read_channel(path), []).append(path)
    analyses = _stages(block, "analysis")
    drawn = dict.fromkeys(names or available, 0)
    failures: dict[str, list[str]] = {}
    boards: dict[tuple[str, Any], list[Any]] = {}
    for (group, index), channel_paths in channels.items():
        composer = _Composer(analyses, [read_capture(path) for path in channel_paths], priors)
        for name in drawn:
            plot, kind, many = available[name]
            noted = len(composer.failures)
            for value, parts in composer.made_of((kind,), many, [], split=True):
                emit(plot(value), Path(_tag(f"{name}_board{group}_channel{index}", *parts)))
                drawn[name] += 1
            if not many:
                boards.setdefault((name, group), []).append(_gathered(analyses, kind, composer))
            failures.setdefault(name, []).extend(
                f"board {group}, channel {index}: {failure}" for failure in list(composer.failures)[noted:]
            )
    for (name, group), gathered in boards.items():
        if sum(map(bool, gathered)) > 1:
            plot, kind, _many = available[name]
            (analysis,) = _producers(analyses, kind)
            emit(plot(analysis([result for channel in gathered for result in channel])), Path(f"{name}_board{group}"))
    for name, count in drawn.items():
        for failure in failures.get(name, []):
            print(f"{name}: not from the captures of {failure}")
        if names and not count:
            raise ValueError(f"no figure {name} of {block} from these captures: {'; '.join(failures.get(name, []))}")
    return written
