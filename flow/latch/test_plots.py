"""The latch's figures, from results alone, drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from pathlib import Path

from flow import plot as figures

from . import plots
from .analysis import analyze_sr, analyze_timing, analyze_upset
from .params import SUPPLY_SWEEP
from .test_analysis import flop_run, sr_run, upset_run


def test_every_figure_renders(tmp_path: Path) -> None:
    supply = analyze_timing([flop_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
    offset = analyze_timing([flop_run(round(value * 1e-12, 15)) for value in range(-100, 201, 50)])
    period = analyze_timing(
        [
            flop_run(value / 4, clock_period_s=value, transition_time_s=value / 8, reset_time_s=1e-9, cycles=12)
            for value in (1e-9, 500e-12, 300e-12)
        ]
    )
    upset = analyze_upset([upset_run(charge * 1e-15, 20e-15) for charge in (5, 20, 50)])
    drawn = [
        plots.plot_delay_rise_supply(supply),
        plots.plot_delay_fall_supply(supply),
        plots.plot_energy_supply(supply),
        plots.plot_clock_to_q_rise_offset(offset),
        plots.plot_clock_to_q_fall_offset(offset),
        plots.plot_captured_offset(offset),
        plots.plot_held_offset(offset),
        plots.plot_captured_frequency(period),
        plots.plot_clock_to_q_rise_frequency(period),
        plots.plot_clock_to_q_fall_frequency(period),
        plots.plot_dip_charge(upset),
        plots.plot_upset_charge(upset),
    ]
    assert len({plot.name for plot in drawn}) == 12
    # one curve a figure, a value at each point of its sweep
    assert all(len(plot.series) == 1 and len(next(iter(plot.series.values()))) == len(plot.x) for plot in drawn)
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)


def test_the_supply_figures_name_what_the_delay_runs_from() -> None:
    """A clocked design's delays run from its clock, an SR latch's from set and reset."""
    clocked = analyze_timing([flop_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
    sr = analyze_sr([sr_run(1.2 * factor) for factor in SUPPLY_SWEEP])
    assert plots.plot_delay_rise_supply(clocked).title == "Delay to q rising over the supply (2 ns clock)"
    assert plots.plot_delay_fall_supply(sr).title == "Delay to q falling over the supply (set and reset)"
    assert plots.plot_energy_supply(sr).title == "Energy per set and reset cycle over the supply"
    assert plots.plot_delay_rise_supply(sr).x == list(SUPPLY_SWEEP)
