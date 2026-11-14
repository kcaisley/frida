"""The chain's figures, from results alone, drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from pathlib import Path

from flow import plot as figures

from . import plots, runs
from .analysis import analyze_oscillation, analyze_propagation
from .params import CONTROL_SWEEP, SUPPLY_SWEEP, TbParams
from .test_analysis import line_run, ring_run


def test_every_figure_renders(tmp_path: Path) -> None:
    ring, line = runs.ring5_starved(), runs.chain4_starved()
    supplies = [round(1.2 * factor, 4) for factor in SUPPLY_SWEEP]
    controls = [round(1.2 * step, 4) for step in CONTROL_SWEEP]
    ring_supply = analyze_oscillation([ring_run(TbParams(params=ring, vdd=vdd), vdd * 1e9) for vdd in supplies])
    ring_control = analyze_oscillation([ring_run(TbParams(params=ring, vcont_v=v), v * 2e9) for v in controls])
    line_supply = analyze_propagation([line_run(TbParams(params=line, vdd=vdd), 50e-12 / vdd) for vdd in supplies])
    line_control = analyze_propagation([line_run(TbParams(params=line, vcont_v=v), 50e-12 / v) for v in controls])
    over_supply = [
        plots.plot_oscillation_frequency_supply(ring_supply),
        plots.plot_delay_rise_supply(line_supply),
        plots.plot_delay_fall_supply(line_supply),
        plots.plot_stage_delay_supply(ring_supply),
        plots.plot_stage_delay_supply(line_supply),
        plots.plot_energy_supply(ring_supply),
        plots.plot_energy_supply(line_supply),
    ]
    over_control = [
        plots.plot_oscillation_frequency_control(ring_control),
        plots.plot_kvco_control(ring_control),
        plots.plot_delay_rise_control(line_control),
        plots.plot_delay_fall_control(line_control),
        plots.plot_rise_time_control(line_control),
        plots.plot_fall_time_control(line_control),
        plots.plot_energy_control(ring_control),
        plots.plot_energy_control(line_control),
    ]
    assert all(plot.x == list(SUPPLY_SWEEP) for plot in over_supply)
    assert all(plot.x == controls for plot in over_control)
    drawn = [*over_supply, *over_control]
    # every figure of the module is drawn here, each under its own name
    defined = {name.removeprefix("plot_") for name in vars(plots) if name.startswith("plot_")}
    assert {plot.name for plot in drawn} == defined
    for plot in drawn:
        (values,) = plot.series.values()
        assert len(values) == len(plot.x)
        paths = figures.render(plot, tmp_path / f"{plot.name}_{len(list(tmp_path.iterdir()))}")
        assert paths and all(path.exists() for path in paths)
