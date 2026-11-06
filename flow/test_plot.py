"""A figure spec drawn with matplotlib (``flow.plot.render``) on the axes the viewer draws it on: its
curves, its map (``Heatmap``), markers and bands (``Marker``, ``Band``), in the colours the viewer
draws them in, and the spec read back from its JSON."""

from __future__ import annotations

import json
import math
import re
from dataclasses import fields
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import LogNorm, to_rgb
from matplotlib.figure import Figure

import flow.analysis.plots as analysis_plots
import flow.plot
from flow.analysis.plots import DENSITY_COLOR_MAP, SPINE_COLOR
from flow.pipeline import Band, Heatmap, Marker, Plot
from flow.plot import figures, render, scaled
from flow.sweep.runner import write_record


def drawn(plot: Plot, monkeypatch: pytest.MonkeyPatch) -> Figure:
    """``plot`` as ``render`` draws it, the figure kept (closed to pyplot) instead of saved."""
    kept: list[Figure] = []
    monkeypatch.setattr(flow.plot, "save_figure", lambda fig, _path: kept.append(fig) or ())
    render(plot, Path("unsaved"))
    plt.close(kept[0])
    return kept[0]


def a_map(**overlays) -> Plot:
    """Counts over time (s) and an output code, by decade: a cell empty and a cell 0."""
    return Plot(
        name="map",
        title="Conversions through each code",
        x_label="Time (s)",
        y_label="Output code",
        x=[],
        series={},
        heatmap=Heatmap(
            x=[0.0, 1e-9, 2e-9, 3e-9],
            y=[9.5, 10.5, 11.5],
            z=[[1.0, 10.0, math.nan], [100.0, 0.0, 1000.0]],
            label="Conversions",
            log=True,
        ),
        y_ticks="code",
        **overlays,
    )


def test_an_axis_takes_the_viewers_si_prefix() -> None:
    assert scaled("Input common mode (V)", [0.45, 0.75]) == ("Input common mode (mV)", 1e3)
    assert scaled("Clock-to-decision delay (s)", [5e-10, math.nan, None]) == ("Clock-to-decision delay (ps)", 1e12)
    assert scaled("Supply over nominal", [0.9, 1.2]) == ("Supply over nominal", 1.0)
    assert scaled("Energy (J)", [math.nan]) == ("Energy (J)", 1.0)


def test_a_spec_renders_with_gaps_where_a_point_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    monkeypatch.setattr(analysis_plots, "PLOT_PDFS", False)
    plot = Plot(
        name="noise_cm",
        title="Input-referred noise over the common mode",
        x_label="Input common mode (V)",
        y_label="Input-referred noise (V)",
        x=[0.45, 0.55, 0.65],
        series={"noise": [1.4e-4, None, 1.6e-4], "other": [1e-4, 1.1e-4, math.nan]},
        legend_title="Instance",
    )
    (path,) = render(plot, tmp_path / "noise_cm")
    assert path.suffix == ".png" and path.stat().st_size > 0
    with pytest.raises(ValueError, match="drawn figure"):
        render(Plot(name="f", title="", x_label="", y_label="", x=[], series={}, figure="build/x.svg"), tmp_path / "f")


def test_a_map_under_its_markers_and_bands(monkeypatch: pytest.MonkeyPatch) -> None:
    plot = a_map(
        x_markers=[Marker(1.5e-9, "Sampling"), Marker(math.nan, "Nowhere")],
        y_markers=[Marker(10.0, "Input")],
        x_bands=[Band(2e-9, 2.5e-9, "Settling")],
    )
    ax, bar = drawn(plot, monkeypatch).axes
    # the map on its cells' edges, the x axis prefixed from them (ns), by decade: the empty cell and
    # the one at 0 left out
    (mesh,) = ax.collections
    assert isinstance(mesh.norm, LogNorm) and mesh.cmap.name == DENSITY_COLOR_MAP.name
    assert np.ma.getmaskarray(mesh.get_array()).tolist() == [[False, False, True], [False, True, False]]
    assert ax.get_xlabel() == "Time (ns)" and bar.get_ylabel() == "Conversions"
    assert ax.get_xlim() == pytest.approx((0.0, 3.0)) and ax.get_ylim() == pytest.approx((9.5, 11.5))
    # the markers dashed in the spine's grey at their places in the axes' units, one not a number left
    # out; the band shaded behind the curves; each labelled
    lines = [([float(x) for x in line.get_xdata()], [float(y) for y in line.get_ydata()]) for line in ax.lines]
    assert lines == [(pytest.approx([1.5, 1.5]), [0, 1]), ([0, 1], pytest.approx([10.0, 10.0]))]
    assert all(line.get_color() == SPINE_COLOR and line.get_linestyle() == "--" for line in ax.lines)
    (band,) = ax.patches
    assert (band.get_x(), band.get_width()) == pytest.approx((2.0, 0.5)) and band.get_zorder() < mesh.get_zorder()
    assert sorted(text.get_text() for text in ax.texts) == ["Input", "Sampling", "Settling"]


def test_markers_and_bands_on_a_log_axis(monkeypatch: pytest.MonkeyPatch) -> None:
    plot = Plot(
        name="spectrum",
        title="Noise density",
        x_label="Frequency (Hz)",
        y_label="Noise density (V/√Hz)",
        x=[1e3, 1e4, 1e5],
        series={"Total": [3e-7, 1e-7, 5e-8]},
        x_log=True,
        y_log=True,
        x_markers=[Marker(0.0, "DC"), Marker(2e4, "Corner")],
        y_markers=[Marker(4e-8, "Floor")],
        x_bands=[Band(1e3, 1e5, "Two decades")],
    )
    ax = drawn(plot, monkeypatch).axes[0]
    # in kHz and nV/√Hz; 0 has no place on a log axis; the band's label at its middle on the axis
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("Frequency (kHz)", "Noise density (nV/√Hz)")
    assert [line.get_xdata()[0] for line in ax.lines[1:]] == pytest.approx([20.0, 0.0])
    assert ax.lines[-1].get_ydata()[0] == pytest.approx(40.0)
    labels = {text.get_text(): text.get_position()[0] for text in ax.texts}
    assert labels == {"Two decades": pytest.approx(10.0), "Corner": pytest.approx(20.0), "Floor": pytest.approx(0.99)}


def test_a_heatmap_holds_a_row_of_values_for_each_row_of_cells() -> None:
    with pytest.raises(ValueError, match="holds 2 rows of 3 values"):
        Heatmap(x=[0.0, 1.0, 2.0, 3.0], y=[0.0, 1.0, 2.0], z=[[1.0, 2.0, 3.0]], label="Conversions")


def test_a_spec_reads_back_from_its_json() -> None:
    # without markers, bands or a map: its JSON is its fields as they were, none of theirs
    bare = Plot("noise", "Noise", "Input (V)", "Noise (V)", [0.1, 0.2], {"Noise": [1e-4, 2e-4]})
    overlays = {"x_markers", "y_markers", "x_bands", "heatmap"}
    assert set(bare.to_json()) == {field.name for field in fields(Plot)} - overlays
    assert Plot.from_json(json.loads(json.dumps(bare.to_json()))) == bare
    full = Plot(
        "map",
        "Map",
        "Time (s)",
        "Output code",
        [],
        {},
        heatmap=Heatmap(x=[0.0, 1.0], y=[0.0, 1.0, 2.0], z=[[3.0], [4.0]], label="Conversions", log=True),
        x_markers=[Marker(0.5, "Centre")],
        y_markers=[Marker(1.0)],
        x_bands=[Band(0.2, 0.4, "Window")],
    )
    spec = json.loads(json.dumps(full.to_json()))
    assert spec["heatmap"]["z"] == [[3.0], [4.0]] and spec["y_markers"] == [{"at": 1.0, "label": ""}]
    assert Plot.from_json(spec) == full


def test_a_records_map_draws_from_its_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    monkeypatch.setattr(analysis_plots, "PLOT_PDFS", False)
    # a sweep run's record as the runner writes it: NaN, the empty cell, as null
    plot = a_map(x_markers=[Marker(1.5e-9, "Sampling")], x_bands=[Band(2e-9, 2.5e-9)])
    record = tmp_path / "run/tsmc65/abc/instance.json"
    record.parent.mkdir(parents=True)
    write_record(record, {"pdk": "tsmc65", "label": None, "details": [plot.to_json()]})
    (png,) = figures("sample", [tmp_path / "run"], out_dir=tmp_path / "png")
    assert png.name == "map.png" and png.stat().st_size > 0
    (spec,) = figures("sample", [tmp_path / "run"], backend="web", out_dir=tmp_path / "web")
    written = json.loads(spec.read_text())
    assert written["heatmap"]["z"][0][2] is None and written["x_bands"] == [{"low": 2e-9, "high": 2.5e-9, "label": ""}]


def test_the_viewer_maps_in_the_renderers_colours() -> None:
    """paper.js's DENSITY (the viewer's colorscale) is the renderer's DENSITY_COLOR_MAP: each stop
    its colour, and the colour map linear between them (within two levels of 255)."""
    paper = Path(__file__).parent / "web/static/js/paper.js"
    found = re.search(r"export const DENSITY = (\[.*?\]);", paper.read_text(), re.DOTALL)
    assert found
    stops = json.loads(re.sub(r",(\s*\])", r"\1", found.group(1)))
    positions = np.array([position for position, _ in stops])
    colours = np.array([to_rgb(colour) for _, colour in stops])
    assert positions[0] == 0 and positions[-1] == 1
    for position in np.linspace(0, 1, 101):
        between = [np.interp(position, positions, colours[:, channel]) for channel in range(3)]
        assert np.abs(np.array(DENSITY_COLOR_MAP(position)[:3]) - between).max() < 2 / 255
