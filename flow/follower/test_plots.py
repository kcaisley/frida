"""The follower's figures, from results alone, drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from flow import plot as figures

from . import plots
from .analysis import analyze_impedance, analyze_transfer
from .params import SUPPLY_SWEEP, Stimulus
from .test_analysis import TB, single_pole


def test_every_figure_renders(tmp_path: Path) -> None:
    levels = [replace(TB, vin_v=vin, vdd=1.2 * factor) for vin, factor in zip((0.3, 0.6, 0.9), SUPPLY_SWEEP)]
    transfer = analyze_transfer([single_pole(tb, 0.8, 1e9 * (1 + tb.vin_v)) for tb in levels])
    impedance = analyze_impedance(
        [single_pole(replace(tb, stimulus=Stimulus.OUTPUT), 1000.0 / (1 + tb.vin_v), 2e9) for tb in levels]
    )
    over_level = [
        plots.plot_vout_vin(transfer),
        plots.plot_gain_vin(transfer),
        plots.plot_bandwidth_vin(transfer),
        plots.plot_zout_vin(impedance),
        plots.plot_psrr_vin(transfer),
        plots.plot_gain_supply(transfer),
        plots.plot_bandwidth_supply(transfer),
        plots.plot_psrr_supply(transfer),
    ]
    over_frequency = [plots.plot_gain_frequency(transfer), plots.plot_zout_frequency(impedance)]
    drawn = [*over_level, *over_frequency]
    assert len({plot.name for plot in drawn}) == 10
    assert all(len(plot.x) == len(SUPPLY_SWEEP) for plot in over_level)
    assert all(plot.x_log and len(plot.x) == 161 for plot in over_frequency)
    # the output impedance in ohms on a log axis
    assert over_frequency[1].y_log and over_frequency[1].series["output impedance"][0] > 700.0
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)
