"""The sampler's figures, from results alone, drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from pathlib import Path

from flow import plot as figures

from . import plots
from .analysis import analyze_hold, analyze_track
from .params import SUPPLY_SWEEP, TbParams
from .test_analysis import rc_run


def test_every_figure_renders(tmp_path: Path) -> None:
    runs = [
        rc_run(TbParams(input_voltage=vin, vdd=1.2 * factor, periods=3))
        for vin, factor in zip((0.3, 0.45, 0.6, 0.75), SUPPLY_SWEEP, strict=True)
    ]
    track, hold = analyze_track(runs), analyze_hold(runs)
    drawn = [
        plots.plot_ron_vin(track),
        plots.plot_track_error_vin(track),
        plots.plot_pedestal_vin(hold),
        plots.plot_feedthrough_vin(hold),
        plots.plot_ron_supply(track),
        plots.plot_pedestal_supply(hold),
    ]
    assert len({plot.name for plot in drawn}) == 6 and all(len(plot.x) == 4 for plot in drawn)
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)
