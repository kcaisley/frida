"""The thesis's figures: each described once (``Figure``: panels of traces, notes, legends and
ticks), then drawn twice from that description: by matplotlib into ``figures/<name>.pdf`` for the
printed thesis (the analysis plots' style, ``flow.analysis.plots``, in the thesis's Latin Modern),
and as the Plotly JSON the web edition draws (``figures/<name>.json``, read by the ``plotly``
shortcode in ``_extensions/plotly``), with the same colours, markers, ticks and labels, plus
hover text and links.

    uv run python docs/thesis/figures.py      # quarto's pre-render runs this
"""

from __future__ import annotations

import json
import math
import os
import sys
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # this checkout's flow and phys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, NullFormatter

from flow.analysis.plots import (
    CURVE_COLORS,
    GRID_MAJOR_COLOR,
    GRID_MINOR_COLOR,
    LEGEND_FACE_COLOR,
    PLOT_STYLE,
    SPINE_COLOR,
    TEXT_COLOR,
)
from phys import adc_survey, model

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
FONTS = HERE / "fonts"
FONT_STACK = ["Latin Modern Roman", "DejaVu Serif"]  # DejaVu for the few glyphs LM lacks (≤ ≥)
WEB_FONT = '"Latin Modern Roman", "DejaVu Serif", Georgia, serif'
TEXT_WIDTH_IN = 5.9  # the thesis's text block
FONT_PT = 9.0

# matplotlib's marker codes and the Plotly symbols drawn for them
SYMBOLS = {
    "o": "circle",
    "s": "square",
    "v": "triangle-down",
    "^": "triangle-up",
    "D": "diamond",
    "X": "x",
    "P": "cross",
    "h": "hexagon",
    "*": "star",
}
# a legend's corner in its panel, as matplotlib names it, and Plotly's anchors for it
CORNERS = {
    "upper left": (0.01, 0.99, "left", "top"),
    "upper right": (0.99, 0.99, "right", "top"),
    "lower left": (0.01, 0.01, "left", "bottom"),
    "lower right": (0.99, 0.01, "right", "bottom"),
}


@dataclass
class Axis:
    label: str
    log: bool = False
    limits: tuple[float, float] | None = None
    ticks: Sequence[tuple[float, str]] | None = None  # major ticks and their text; None: automatic


@dataclass
class Trace:
    name: str
    x: Sequence[float]
    y: Sequence[float]
    color: str | Sequence[str] = CURVE_COLORS[0]
    symbol: str | Sequence[str] = "o"  # matplotlib marker codes (SYMBOLS)
    lines: bool = False
    dash: bool = False
    size: float = 5.0
    edge: str = SPINE_COLOR
    edge_width: float = 0.45
    legend: int = 1  # 1 or 2: which legend lists it; 0: none
    hover: Sequence[str] | None = None
    links: Sequence[str] | None = None
    order: int = 3


@dataclass
class Note:
    x: float
    y: float
    text: str
    offset: tuple[float, float] = (0.0, 10.0)  # points, right and up
    align: str = "center"
    rotation: float = 0.0
    color: str = TEXT_COLOR
    axes_y: bool = False  # y in axes fraction (0 bottom, 1 top), not data
    box: bool = False  # a white backing, over busy data


@dataclass
class Panel:
    x: Axis
    y: Axis
    traces: list[Trace]
    notes: list[Note] = field(default_factory=list)
    title: str = ""
    legend: tuple[str, str] = ("", "upper left")  # title, corner
    legend2: tuple[str, str] | None = None


@dataclass
class Figure:
    name: str
    panels: list[Panel]
    height_in: float = 3.7
    share_y: bool = False


def decades(low: int, high: int, text=None) -> list[tuple[float, str]]:
    """Ticks at each power of ten from 10^low to 10^high, labelled by ``text`` (SI by default)."""
    return [(10.0**n, (text or si)(10.0**n)) for n in range(low, high + 1)]


def si(value: float) -> str:
    for exponent, prefix in ((9, "G"), (6, "M"), (3, "k"), (0, "")):
        if abs(value) >= 10**exponent:
            return f"{value / 10**exponent:g}{prefix}"
    return f"{value:g}"


def plain(value: float) -> str:
    return f"{value:g}"


# ---------------------------------------------------------------- matplotlib (the printed thesis)


def draw_pdf(figure: Figure, path: Path) -> Path:
    for font in sorted(FONTS.glob("LM-*.ttf")):
        font_manager.fontManager.addfont(str(font))
    style = {
        **PLOT_STYLE,
        "font.family": FONT_STACK,
        "mathtext.fontset": "cm",
        "font.size": FONT_PT,
        "axes.labelsize": FONT_PT,
        "axes.titlesize": FONT_PT + 1,
        "xtick.labelsize": FONT_PT,
        "ytick.labelsize": FONT_PT,
        "legend.fontsize": FONT_PT - 1,
        "legend.title_fontsize": FONT_PT - 1,
        "figure.figsize": (TEXT_WIDTH_IN, figure.height_in),
    }
    with mpl.rc_context(style):
        fig, axes = plt.subplots(1, len(figure.panels), sharey=figure.share_y, squeeze=False)
        for panel, ax in zip(figure.panels, axes[0], strict=True):
            _panel_pdf(ax, panel)
        fig.savefig(path, metadata={"CreationDate": None, "Creator": "docs/thesis/figures.py"})
        plt.close(fig)
    return path


def _panel_pdf(ax, panel: Panel) -> None:
    handles: dict[int, list] = {1: [], 2: []}
    for trace in panel.traces:
        colors = _each(trace.color, len(trace.x))
        symbols = _each(trace.symbol, len(trace.x))
        if trace.lines:
            ax.plot(trace.x, trace.y, "--" if trace.dash else "-", color=colors[0], linewidth=1.2, zorder=trace.order)
        elif len(trace.x):
            for symbol in dict.fromkeys(symbols):
                pick = [i for i, s in enumerate(symbols) if s == symbol]
                ax.scatter(
                    [trace.x[i] for i in pick],
                    [trace.y[i] for i in pick],
                    s=trace.size**2,
                    marker=symbol,
                    c=[colors[i] for i in pick],
                    edgecolors=trace.edge,
                    linewidths=trace.edge_width,
                    zorder=trace.order,
                    clip_on=False,
                )
        if trace.legend:
            handles[trace.legend].append(
                Line2D(
                    [0],
                    [0],
                    color=_first(trace.color) if trace.lines else "none",
                    linestyle=("--" if trace.dash else "-") if trace.lines else "none",
                    marker=None if trace.lines else (trace.symbol if isinstance(trace.symbol, str) else "o"),
                    markerfacecolor=_first(trace.color),
                    markeredgecolor=trace.edge,
                    markeredgewidth=0.6,
                    markersize=5,
                    linewidth=1.8,
                    label=trace.name,
                )
            )
    for note in panel.notes:
        ax.annotate(
            note.text,
            (note.x, note.y),
            xycoords=ax.get_xaxis_transform() if note.axes_y else "data",
            xytext=note.offset,
            textcoords="offset points",
            ha=note.align,
            va="bottom" if note.offset[1] >= 0 else "top",
            rotation=note.rotation,
            color=note.color,
            fontsize=FONT_PT - 1,
            bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.85} if note.box else None,
            zorder=8,
        )
    for axis, spec in ((ax.xaxis, panel.x), (ax.yaxis, panel.y)):
        if spec.log:
            (ax.set_xscale if axis is ax.xaxis else ax.set_yscale)("log")
        if spec.limits:
            (ax.set_xlim if axis is ax.xaxis else ax.set_ylim)(*spec.limits)
        if spec.ticks:
            axis.set_major_locator(FixedLocator([value for value, _ in spec.ticks]))
            axis.set_ticklabels([_tick(text, web=False) for _, text in spec.ticks])
            if spec.log:
                axis.set_minor_locator(FixedLocator(_minor_ticks(spec)))
                axis.set_minor_formatter(NullFormatter())
    ax.set_xlabel(panel.x.label)
    if panel.y.label:
        ax.set_ylabel(panel.y.label)
    if panel.title:
        ax.set_title(panel.title)
    ax.set_axisbelow(True)
    ax.grid(True, which="major", color=GRID_MAJOR_COLOR, linewidth=0.8)
    ax.grid(True, which="minor", color=GRID_MINOR_COLOR, linewidth=0.5)
    first = None
    for number, spec in ((1, panel.legend), (2, panel.legend2)):
        if spec is None or not handles[number]:
            continue
        title, corner = spec
        legend = ax.legend(handles=handles[number], title=title or None, loc=corner)
        if number == 1:
            first = legend
    if first is not None and panel.legend2 is not None and handles[2]:
        ax.add_artist(first)


def _each(value, count: int) -> list:
    return [value] * count if isinstance(value, str) else list(value)


def _minor_ticks(spec: Axis) -> list[float]:
    """A log axis's minor ticks, 2–9 in each decade around its major ticks."""
    low, high = spec.ticks[0][0], spec.ticks[-1][0]
    decades_ = range(math.floor(math.log10(low)) - 1, math.ceil(math.log10(high)) + 1)
    return [m * 10.0**n for n in decades_ for m in range(2, 10)]


def _first(value):
    return value if isinstance(value, str) else value[0]


def _tick(text: str, web: bool) -> str:
    """A tick's text: ``10^n`` as mathtext for matplotlib, a superscript for Plotly."""
    if not text.startswith("10^"):
        return text
    return f"10<sup>{text[3:]}</sup>" if web else f"$10^{{{text[3:]}}}$"


# ---------------------------------------------------------------- Plotly (the web edition)


def plotly_spec(figure: Figure) -> dict:
    count = len(figure.panels)
    gap = 0.06
    width = (1.0 - gap * (count - 1)) / count
    data, layout = (
        [],
        {
            "font": {"family": WEB_FONT, "size": 14, "color": TEXT_COLOR},
            "paper_bgcolor": "white",
            "plot_bgcolor": "white",
            "margin": {"l": 64, "r": 16, "t": 28 if any(p.title for p in figure.panels) else 10, "b": 52},
            "hovermode": "closest",
            "hoverlabel": {
                "font": {"family": WEB_FONT, "size": 13},
                "bgcolor": "white",
                "bordercolor": SPINE_COLOR,
                "align": "left",
            },
            "annotations": [],
            "height": round(figure.height_in / TEXT_WIDTH_IN * 760),
        },
    )
    for index, panel in enumerate(figure.panels):
        n = "" if index == 0 else str(index + 1)
        left = index * (width + gap)
        layout[f"xaxis{n}"] = _axis(panel.x, (left, left + width), f"y{n}")
        y_axis = _axis(panel.y, (0, 1), f"x{n}")
        if figure.share_y and index:
            y_axis["matches"] = "y"
            y_axis["showticklabels"] = False
        layout[f"yaxis{n}"] = y_axis
        legends = {}
        for number, spec in ((1, panel.legend), (2, panel.legend2)):
            if spec is None:
                continue
            key = "legend" if number == 1 and index == 0 else f"legend{index * 2 + number}"
            x, y, xanchor, yanchor = CORNERS[spec[1]]
            layout[key] = {
                "x": left + x * width,
                "y": y,
                "xanchor": xanchor,
                "yanchor": yanchor,
                "bgcolor": "rgba(236,239,244,0.9)",
                "bordercolor": SPINE_COLOR,
                "borderwidth": 0.8,
                "font": {"size": 12},
                "title": {"text": spec[0], "font": {"size": 12}},
                "itemclick": "toggle" if number == 1 else False,
                "itemdoubleclick": "toggleothers" if number == 1 else False,
            }
            legends[number] = key
        if panel.title:
            layout["annotations"].append(
                {
                    "text": panel.title,
                    "xref": "paper",
                    "yref": "paper",
                    "x": left + width / 2,
                    "y": 1.0,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "showarrow": False,
                    "font": {"size": 15},
                }
            )
        for trace in panel.traces:
            data.append(_trace(trace, n, legends))
            if trace.legend and not trace.lines and not isinstance(trace.symbol, str):
                # listed by a plain dot that toggles the whole group
                data[-1]["showlegend"] = False
                data[-1]["legendgroup"] = trace.name
                data.append(
                    {
                        "type": "scatter",
                        "mode": "markers",
                        "name": trace.name,
                        "x": [None],
                        "y": [None],
                        "xaxis": f"x{n}",
                        "yaxis": f"y{n}",
                        "legend": legends.get(trace.legend, "legend"),
                        "legendgroup": trace.name,
                        "marker": {
                            "color": _first(trace.color),
                            "symbol": "circle",
                            "size": 8,
                            "line": {"color": trace.edge, "width": 0.7},
                        },
                        "hoverinfo": "skip",
                    }
                )
        for note in panel.notes:
            layout["annotations"].append(
                {
                    "text": note.text.replace("\n", "<br>"),
                    "x": math.log10(note.x) if panel.x.log else note.x,
                    "y": note.y if note.axes_y else (math.log10(note.y) if panel.y.log else note.y),
                    "xref": f"x{n}",
                    "yref": f"y{n} domain" if note.axes_y else f"y{n}",
                    "xshift": note.offset[0] * 1.4,
                    "yshift": note.offset[1] * 1.4,
                    "xanchor": {"center": "center", "left": "left", "right": "right"}[note.align],
                    "yanchor": "bottom" if note.offset[1] >= 0 else "top",
                    "textangle": -note.rotation,
                    "showarrow": False,
                    "font": {"size": 12, "color": note.color},
                    **({"bgcolor": "rgba(255,255,255,0.85)"} if note.box else {}),
                }
            )
    return {
        "data": data,
        "layout": layout,
        "config": {"responsive": True, "displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
    }


def _axis(spec: Axis, domain: tuple[float, float], anchor: str) -> dict:
    axis = {
        "title": {"text": spec.label, "standoff": 6},
        "type": "log" if spec.log else "linear",
        "domain": list(domain),
        "anchor": anchor,
        "showline": True,
        "mirror": "ticks",
        "linecolor": SPINE_COLOR,
        "linewidth": 0.8,
        "ticks": "inside",
        "ticklen": 4,
        "tickcolor": SPINE_COLOR,
        "gridcolor": GRID_MAJOR_COLOR,
        "zeroline": False,
    }
    if spec.log:
        # explicit, as matplotlib draws them: Plotly's own minor step beside fixed ticks is linear
        axis["minor"] = {"ticks": "inside", "ticklen": 2, "showgrid": True, "gridcolor": GRID_MINOR_COLOR}
        if spec.ticks:
            axis["minor"]["tickvals"] = _minor_ticks(spec)
    if spec.limits:
        axis["range"] = [math.log10(v) for v in spec.limits] if spec.log else list(spec.limits)
    if spec.ticks:
        axis["tickvals"] = [value for value, _ in spec.ticks]
        axis["ticktext"] = [_tick(text, web=True) for _, text in spec.ticks]
    return axis


def _trace(trace: Trace, n: str, legends: dict[int, str]) -> dict:
    colors = _each(trace.color, len(trace.x))
    symbols = [SYMBOLS[s] for s in _each(trace.symbol, len(trace.x))]
    out = {
        "type": "scatter",
        "name": trace.name,
        # a legend-only trace holds one empty point: Plotly drops the legends of a trace with none
        "x": list(trace.x) or [None],
        "y": list(trace.y) or [None],
        "xaxis": f"x{n}",
        "yaxis": f"y{n}",
        "showlegend": bool(trace.legend),
        "cliponaxis": False,
    }
    if trace.legend:
        out["legend"] = legends.get(trace.legend, "legend")
    if trace.lines:
        out["mode"] = "lines"
        out["line"] = {"color": colors[0], "width": 2, "dash": "dash" if trace.dash else "solid"}
    else:
        out["mode"] = "markers"
        out["marker"] = {
            "color": colors if len(set(colors)) > 1 else _first(trace.color),
            "symbol": symbols if len(set(symbols)) > 1 else SYMBOLS[_first(trace.symbol)],
            "size": trace.size * 1.6,
            "line": {"color": trace.edge, "width": trace.edge_width * 1.6},
        }
    if trace.hover is not None:
        out["text"] = list(trace.hover)
        out["hovertemplate"] = "%{text}<extra></extra>"
    else:
        out["hoverinfo"] = "skip" if not trace.lines else "x+y+name"
    if trace.links is not None:
        out["customdata"] = list(trace.links)
    return out


# ---------------------------------------------------------------- the figures


def hit_rate() -> Figure:
    """Per-pixel hit rate against incident fluence, for pixel pitches from 100 µm to 10 µm."""
    fluence = np.logspace(6, 11, 120)
    pitches_um = (100, 75, 50, 30, 15, 10)
    traces = [
        Trace(
            f"{pitch} µm",
            fluence.tolist(),
            [model.hit_rate_per_pixel_per_second(f * 1e6, pitch * 1e-6) for f in fluence],
            color=CURVE_COLORS[i],
            lines=True,
        )
        for i, pitch in enumerate(pitches_um)
    ]
    notes = []
    for sources, color, symbol, kind in (
        (model.photon_sources, CURVE_COLORS[3], "s", "Photon source"),
        (model.electron_sources, CURVE_COLORS[5], "o", "Electron source"),
    ):
        traces.append(
            Trace(
                kind,
                [f for _, f, _ in sources],
                [1.35e4] * len(sources),
                color=color,
                symbol=symbol,
                edge="white",
                size=6,
                hover=[
                    f"<b>{name}</b><br>{f:.2g} cps/mm² ≈ {float(model.fluence_to_current_density_pa_mm2(f)):.3g} pA/mm²"
                    for name, f, _ in sources
                ],
                order=5,
            )
        )
        notes += [Note(f, 1.9e4, name, offset=(offset, 4), rotation=90, color=color) for name, f, offset in sources]
    return Figure(
        "hit_rate_vs_fluence",
        [
            Panel(
                Axis(
                    "Incident particle fluence (cps/mm²)", log=True, limits=(1e6, 2.5e11), ticks=decades(6, 11, _power)
                ),
                Axis("Hit rate per pixel (cps)", log=True, limits=(1e4, 1e9), ticks=decades(4, 9)),
                traces,
                notes,
                legend=("Pixel pitch / source", "upper left"),
            )
        ],
        height_in=3.6,
    )


def _power(value: float) -> str:
    return f"10^{round(math.log10(value))}"


def counting_rate() -> Figure:
    """The highest hit rate per pixel an integrating pixel can count (its ADC's levels per frame)
    and a counting pixel can count (10 % pile-up for its dead time), with reported chips."""
    frame_us = np.linspace(5, 100, 96)
    integrating = [
        Trace(
            f"{bits}-bit",
            frame_us.tolist(),
            [model.max_counting_rate_per_pixel_per_second(bits, t * 1e-6) for t in frame_us],
            color=CURVE_COLORS[i],
            lines=True,
        )
        for i, bits in enumerate((12, 10, 8, 6, 4))
    ]
    dead_ns = np.linspace(5, 400, 120)
    counting = [
        Trace(
            "10 % pile-up limit",
            dead_ns.tolist(),
            [float(model.max_rate(t * 1e-9)) for t in dead_ns],
            lines=True,
            dash=True,
        ),
        Trace(
            "Reported chips",
            [t for _, t, _ in model.counting_chips],
            [r for _, _, r in model.counting_chips],
            color=CURVE_COLORS[1],
            edge="white",
            size=6,
            hover=[
                f"<b>{name}</b><br>dead time {t:g} ns<br>{r / 1e6:.3g} Mcps per pixel"
                for name, t, r in model.counting_chips
            ],
            legend=0,
        ),
    ]
    # each chip's label: offset in points and alignment (the cluster near 50 ns placed by hand)
    places = {
        "SPHIRD": ((6, -3), "left"),
        "MPX4": ((-4, -12), "right"),
        "IBEX": ((-4, -12), "right"),
        "MPX3": ((-4, 6), "right"),
    }
    notes = [
        Note(t, r, name, offset=places.get(name, ((6, 3), "left"))[0], align=places.get(name, ((6, 3), "left"))[1])
        for name, t, r in model.counting_chips
    ]
    rate = Axis("Max hit rate per pixel (cps)", log=True, limits=(1e4, 1e9), ticks=decades(4, 9))
    return Figure(
        "counting_rate_limits",
        [
            Panel(
                Axis("Frame time (µs)"),
                rate,
                integrating,
                title="Integrating (frame-based)",
                legend=("ADC resolution", "upper right"),
            ),
            Panel(
                Axis("Front-end dead time (ns)"),
                Axis("", log=True, limits=(1e4, 1e9), ticks=decades(4, 9)),
                counting,
                notes,
                title="Discriminating (counting)",
                legend=("", "upper right"),
            ),
        ],
        height_in=3.4,
        share_y=True,
    )


def _authors(text: str) -> str:
    names = [name.strip() for name in text.split(",") if name.strip()]
    return ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")


def survey(
    name: str,
    x_axis: Axis,
    y_axis: Axis,
    x_of,
    y_of,
    target: tuple[float, float],
    legends=("upper left", "lower right"),
) -> Figure:
    """Survey designs (``phys.adc_survey``'s cuts) coloured by process node, marked by architecture,
    with the FRIDA design goal; each design's paper on hover, its DOI on click."""
    points = adc_survey.load_filtered_points()
    traces = []
    for category, color in adc_survey.TECHNOLOGY_COLORS.items():
        chosen = [p for p in points if adc_survey.technology_category(p.technology_nm) == category]
        if not chosen:
            continue
        traces.append(
            Trace(
                category,
                [x_of(p) for p in chosen],
                [y_of(p) for p in chosen],
                color=color,
                symbol=[adc_survey.ARCHITECTURE_MARKERS[p.architecture_family] for p in chosen],
                hover=[_survey_hover(p) for p in chosen],
                links=[f"https://doi.org/{p.doi}" if p.doi else "" for p in chosen],
            )
        )
    for family, marker in adc_survey.ARCHITECTURE_MARKERS.items():
        if any(p.architecture_family == family for p in points):
            traces.append(Trace(family, [], [], color=LEGEND_FACE_COLOR, symbol=marker, legend=2))
    goal_color = adc_survey.TECHNOLOGY_COLORS[adc_survey.technology_category(adc_survey.FRIDA_TARGET_TECHNOLOGY_NM)]
    traces.append(
        Trace(
            "FRIDA design goal",
            [target[0]],
            [target[1]],
            color=goal_color,
            size=11,
            edge=TEXT_COLOR,
            edge_width=1.2,
            legend=0,
            order=7,
            hover=[
                (
                    "<b>FRIDA design goal</b><br>"
                    f"{adc_survey.FRIDA_TARGET_DESIGN_BITS}-bit SAR, {adc_survey.FRIDA_TARGET_TECHNOLOGY_NM:g} nm<br>"
                    f"ENOB {adc_survey.FRIDA_TARGET_ENOB:g} at {adc_survey.FRIDA_TARGET_SAMPLING_RATE_HZ / 1e6:g} MS/s, "
                    f"{adc_survey.FRIDA_TARGET_POWER_W * 1e6:g} µW, {adc_survey.FRIDA_TARGET_AREA_UM2:g} µm²"
                )
            ],
        )
    )
    return Figure(
        name,
        [
            Panel(
                x_axis,
                y_axis,
                traces,
                [Note(*target, "Design goal", offset=(0, 9), box=True)],
                legend=("Process node", legends[1]),
                legend2=("Architecture", legends[0]),
            )
        ],
        height_in=4.0,
    )


def _survey_hover(p: adc_survey.AdcSurveyPoint) -> str:
    title = "<br>".join(textwrap.wrap(p.title, 64)) or "(untitled)"
    return (
        f"<b>{title}</b><br>{_authors(p.authors)}<br>"
        f"{p.conference} {p.year}, paper {p.paper_id} · {p.architecture} · {p.technology_nm:g} nm<br>"
        f"ENOB {p.enob:.1f} · {p.nyquist_rate_hz / 1e6:.3g} MS/s · {p.power_w * 1e6:.3g} µW<br>"
        f"{p.conversion_energy_pj:.3g} pJ/conv · FoM<sub>W</sub> {p.walden_fom_fj:.3g} fJ/step · {p.area_mm2 * 1e6:.3g} µm²"
    )


def figures() -> list[Figure]:
    s = adc_survey
    enob = Axis("Effective number of bits (ENOB)", limits=(5.6, 16.4), ticks=[(v, f"{v}") for v in range(6, 17, 2)])
    area = Axis("ADC area (µm²)", log=True, limits=(2e2, 3e5), ticks=decades(3, 5, plain))
    return [
        hit_rate(),
        counting_rate(),
        survey(
            "survey_enob_vs_rate",
            Axis("Nyquist conversion rate (MS/s)", log=True, ticks=decades(-1, 4, plain)),
            enob,
            lambda p: p.nyquist_rate_hz / 1e6,
            lambda p: p.enob,
            (s.FRIDA_TARGET_SAMPLING_RATE_HZ / 1e6, s.FRIDA_TARGET_ENOB),
        ),
        survey(
            "survey_enob_vs_energy",
            Axis("Energy per conversion (pJ)", log=True, ticks=decades(-1, 3, plain)),
            enob,
            lambda p: p.conversion_energy_pj,
            lambda p: p.enob,
            (s.FRIDA_TARGET_CONVERSION_ENERGY_PJ, s.FRIDA_TARGET_ENOB),
            legends=("upper left", "lower right"),
        ),
        survey(
            "survey_fomw_vs_area",
            area,
            Axis("Walden FoM (fJ/conversion-step)", log=True, ticks=decades(-1, 3, plain)),
            lambda p: p.area_mm2 * 1e6,
            lambda p: p.walden_fom_fj,
            (s.FRIDA_TARGET_AREA_UM2, s.FRIDA_TARGET_WALDEN_FOM_FJ),
            legends=("upper left", "upper right"),
        ),
    ]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for figure in figures():
        draw_pdf(figure, OUT / f"{figure.name}.pdf")
        (OUT / f"{figure.name}.json").write_text(json.dumps(plotly_spec(figure), ensure_ascii=False))
        print(OUT / figure.name)


if __name__ == "__main__":
    main()
