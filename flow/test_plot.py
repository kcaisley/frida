"""A figure spec drawn with matplotlib (``flow.plot.render``) on the axes the viewer draws it on."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

import flow.analysis.plots as analysis_plots
from flow.pipeline import Plot
from flow.plot import render, scaled


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
