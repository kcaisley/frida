"""The latch's figures, from results alone, drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np

from flow import plot as figures
from flow.pipeline import Band, Marker, Plot

from . import plots, runs
from .analysis import analyze_constraint, analyze_sr, analyze_timing, analyze_upset
from .params import SUPPLY_SWEEP, Params
from .test_analysis import approx, flop_run, sr_run, timing_result, upset_run
from .types import AnalysisConstraint, AnalysisSr, AnalysisUpset


def test_every_figure_renders(tmp_path: Path) -> None:
    supply = analyze_timing([flop_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
    sweep = [flop_run(round(value * 1e-12, 15)) for value in range(-100, 201, 50)]
    offset = analyze_timing(sweep)
    constraint = analyze_constraint(sweep, timing=offset)
    period = analyze_timing(
        [
            flop_run(value / 2, clock_period_s=value, transition_time_s=3.75e-12, reset_time_s=1e-9, cycles=12)
            for value in (1e-9, 500e-12, 300e-12)
        ]
    )
    upset = analyze_upset([upset_run(charge * 1e-15, 20e-15) for charge in (5, 20, 50)])
    drawn = [
        plots.plot_delay_rise_supply(supply),
        plots.plot_delay_fall_supply(supply),
        plots.plot_energy_supply(supply),
        plots.plot_delay_rise_offset(offset, constraint),
        plots.plot_delay_fall_offset(offset, constraint),
        plots.plot_captured_offset(offset, constraint),
        plots.plot_held_offset(offset, constraint),
        plots.plot_captured_frequency(period),
        plots.plot_delay_rise_frequency(period),
        plots.plot_delay_fall_frequency(period),
        plots.plot_dip_charge(upset),
        plots.plot_upset_charge(upset),
    ]
    assert len({plot.name for plot in drawn}) == 12
    # one curve a figure, a value at each point of its sweep
    assert all(len(plot.series) == 1 and len(next(iter(plot.series.values()))) == len(plot.x) for plot in drawn)
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)


def test_the_supply_figures_name_what_the_delay_runs_from() -> None:
    """A flip-flop's delays run from its clock (clock-to-Q), a latch's from d while it is open
    (D-to-Q), an SR latch's from set and reset; one label a design in every figure."""
    clocked = analyze_timing([flop_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
    sr = analyze_sr([sr_run(1.2 * factor) for factor in SUPPLY_SWEEP])
    assert plots.plot_delay_rise_supply(clocked).title == "Delay to q rising from clk over the supply (2 ns clock)"
    assert (
        plots.plot_delay_fall_supply(sr).title
        == "Delay to q falling from r over the supply (one set and one reset every 5.2 ns)"
    )
    # the condition is the runs' own period: a 1 ns clock, a set and a reset every 4 ns
    faster = replace(clocked, clock_period_s=np.full(3, 1e-9))
    assert plots.plot_delay_fall_supply(faster).title == "Delay to q falling from clk over the supply (1 ns clock)"
    slower = replace(sr, data_period_s=np.full(3, 4e-9))
    assert plots.plot_delay_rise_supply(slower).title.endswith("(one set and one reset every 4 ns)")
    assert plots.plot_energy_supply(sr).title.startswith("Energy per set and reset cycle from V_DD")
    assert plots.plot_delay_rise_supply(clocked).y_label == "Clock-to-Q delay (s)"
    assert plots.plot_delay_rise_supply(sr).y_label == "Delay (s)"
    latch = replace(timing_result(), dut=Params())
    assert plots.plot_delay_fall_supply(latch).y_label == "D-to-Q delay (s)"
    assert plots.plot_delay_fall_supply(latch).title.startswith("Delay to q falling from d, the latch open")


# Each figure's spec from synthetic results of known arrays: the quantity, its SI unit and scale on
# each axis as the notation names them, and the one curve equal to the result's array.
def assert_axes(
    drawn: Plot, *, name: str, x_label: str, y_label: str, x_log: bool, x, series: str, y, y_log: bool = False
) -> None:
    assert (drawn.name, drawn.x_label, drawn.y_label) == (name, x_label, y_label)
    assert (drawn.x_log, drawn.y_log) == (x_log, y_log)
    assert drawn.x == approx(list(x)) and list(drawn.series) == [series]
    assert drawn.series[series] == approx(list(y), nan_ok=True)


def test_the_supply_figures_spec() -> None:
    """Over the supply, its fraction of nominal (each run's V_DD over the middle one's), whatever
    order the runs come in."""
    clocked = timing_result(delay_fall_s=np.array([55e-12, math.nan, 36e-12]))
    sr = AnalysisSr(
        group=None,
        index=None,
        dut=runs.sr_nor(),
        vdd_v=1.2 * np.asarray(SUPPLY_SWEEP),
        data_period_s=np.full(3, 5.2e-9),
        delay_rise_s=np.array([30e-12, 25e-12, 21e-12]),
        delay_fall_s=np.array([33e-12, 27e-12, 23e-12]),
        idd_a=np.array([4e-6, 5e-6, 6e-6]),
        idd_drivers_a=np.array([1e-6, 1e-6, 1e-6]),
    )
    reordered = replace(
        clocked,
        vdd_v=clocked.vdd_v[::-1],
        delay_rise_s=clocked.delay_rise_s[::-1],
        delay_fall_s=clocked.delay_fall_s[::-1],
        idd_a=clocked.idd_a[::-1],
    )
    for supply, label, period in (
        (clocked, "Clock-to-Q delay (s)", clocked.clock_period_s),
        (reordered, "Clock-to-Q delay (s)", reordered.clock_period_s),
        (sr, "Delay (s)", sr.data_period_s),
    ):
        relative = supply.vdd_v / 1.2
        common = {"x_label": "Supply over nominal", "x_log": False, "x": relative}
        assert_axes(
            plots.plot_delay_rise_supply(supply),
            name="delay_rise_supply",
            y_label=label,
            series="delay",
            y=supply.delay_rise_s,
            **common,
        )
        assert_axes(
            plots.plot_delay_fall_supply(supply),
            name="delay_fall_supply",
            y_label=label,
            series="delay",
            y=supply.delay_fall_s,
            **common,
        )
        # [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, so a cycle's energy V_DD I_avg T, the
        # latch's own current and its inputs' drivers'
        energy = supply.vdd_v * (supply.idd_a + supply.idd_drivers_a) * period
        assert_axes(
            plots.plot_energy_supply(supply),
            name="energy_supply",
            y_label="Energy per cycle (J)",
            series="energy",
            y=energy,
            **common,
        )


def test_the_offset_figures_spec() -> None:
    """Over the data offset, setup and hold marked at their offsets (hold at minus the hold time)
    and the delay figures' 10 % pushout bound at 1.1 times the reference delay; the delays only
    where every edge captured (at -50 ps half the edges captured, late: their median, 90 and 96 ps,
    is drawn as no point; at -100 ps none did)."""
    offsets = np.array([-100e-12, -50e-12, 0.0, 50e-12, 100e-12])
    offset = timing_result(
        vdd_v=np.full(5, 1.2),
        clock_period_s=np.full(5, 2e-9),
        data_offset_s=offsets,
        delay_rise_s=np.array([math.nan, 90e-12, 60e-12, 42e-12, 40e-12]),
        delay_fall_s=np.array([math.nan, 96e-12, 66e-12, 46e-12, 44e-12]),
        captured_fraction=np.array([0.0, 0.5, 1.0, 1.0, 1.0]),
        held_fraction=np.array([1.0, 0.5, 0.0, 0.0, 0.0]),
        idd_a=np.full(5, 6e-6),
        idd_drivers_a=np.zeros(5),
    )
    drawn_rise, drawn_fall = ([math.nan, math.nan, *delay[2:]] for delay in (offset.delay_rise_s, offset.delay_fall_s))
    constraint = AnalysisConstraint(
        group=None,
        index=None,
        dut=runs.flop_rst(),
        vdd_v=1.2,
        clock_period_s=2e-9,
        delay_rise_s=40e-12,
        delay_fall_s=44e-12,
        setup_s=30e-12,
        hold_s=50e-12,
    )
    common = {"x_label": "Data offset (s)", "x_log": False, "x": offsets}
    for drawn, name, y_label, series, y in (
        (
            plots.plot_delay_rise_offset(offset, constraint),
            "delay_rise_offset",
            "Clock-to-Q delay (s)",
            "delay",
            drawn_rise,
        ),
        (
            plots.plot_delay_fall_offset(offset, constraint),
            "delay_fall_offset",
            "Clock-to-Q delay (s)",
            "delay",
            drawn_fall,
        ),
        (
            plots.plot_captured_offset(offset, constraint),
            "captured_offset",
            "Fraction captured",
            "captured",
            offset.captured_fraction,
        ),
        (plots.plot_held_offset(offset, constraint), "held_offset", "Fraction held", "held", offset.held_fraction),
    ):
        assert_axes(drawn, name=name, y_label=y_label, series=series, y=y, **common)
        assert drawn.x_markers == [Marker(30e-12, "setup"), Marker(-50e-12, "hold")]
    assert plots.plot_delay_rise_offset(offset, constraint).y_markers == [Marker(1.1 * 40e-12, "10 % pushout")]
    assert plots.plot_delay_fall_offset(offset, constraint).y_markers == [Marker(1.1 * 44e-12, "10 % pushout")]
    # a share's axis spans 0 to 1 whatever its points (here 0 to 1 already), a delay's its data
    assert plots.plot_captured_offset(offset, constraint).y_range == (0.0, 1.0)
    assert plots.plot_held_offset(offset, constraint).y_range == (0.0, 1.0)
    assert plots.plot_delay_rise_offset(offset, constraint).y_range is None
    # no boundary in the sweep: no marker
    open_ended = replace(constraint, setup_s=math.nan, hold_s=math.nan)
    assert plots.plot_captured_offset(offset, open_ended).x_markers == []


def test_the_frequency_figures_spec() -> None:
    """Over f_CK = 1 / T_CK, on a log axis, f_max marked on each: the top of the band that works from
    the slowest clock up; the delays only where every edge captured (the 5 GHz run captured half its
    edges: its median over them is drawn as no point)."""
    periods = np.array([1e-9, 500e-12, 200e-12])
    period = timing_result(
        vdd_v=np.full(3, 1.2),
        clock_period_s=periods,
        data_offset_s=periods / 2,
        captured_fraction=np.array([1.0, 1.0, 0.5]),
        held_fraction=np.array([0.0, 0.0, 0.5]),
    )
    common = {"x_label": "Clock frequency (Hz)", "x_log": True, "x": [1e9, 2e9, 5e9]}
    for drawn, name, y_label, series, y in (
        (plots.plot_captured_frequency(period), "captured_frequency", "Fraction captured", "captured", [1.0, 1.0, 0.5]),
        (
            plots.plot_delay_rise_frequency(period),
            "delay_rise_frequency",
            "Clock-to-Q delay (s)",
            "delay",
            [*period.delay_rise_s[:2], math.nan],
        ),
        (
            plots.plot_delay_fall_frequency(period),
            "delay_fall_frequency",
            "Clock-to-Q delay (s)",
            "delay",
            [*period.delay_fall_s[:2], math.nan],
        ),
    ):
        assert_axes(drawn, name=name, y_label=y_label, series=series, y=y, **common)
    assert all(math.isfinite(delay) for delay in period.delay_rise_s)
    for drawn in (plots.plot_captured_frequency(period), plots.plot_delay_rise_frequency(period)):
        assert drawn.x_markers == [Marker(approx(2e9), "f_max")]
    assert plots.plot_delay_fall_frequency(period).x_markers == [Marker(approx(2e9), "f_max")]
    # the titles name the stimulus alone, short enough not to be clipped
    assert plots.plot_delay_rise_frequency(period).title == (
        "Delay to q rising from clk over the clock frequency (d half a period before each edge)"
    )
    # the share spans 0 to 1 though its points lie from 0.5 to 1
    assert plots.plot_captured_frequency(period).y_range == (0.0, 1.0)
    assert plots.plot_delay_rise_frequency(period).y_range is None
    assert "(toggling" in plots.plot_captured_frequency(replace(period, dut=runs.div2())).title


def test_the_charge_figures_spec() -> None:
    """Over the strike's charge, on log axes (the dip's too), the critical charge's interval shaded,
    the struck node and its load named."""
    upset = AnalysisUpset(
        group=None,
        index=None,
        dut=Params(),
        cload_f=2e-15,
        charge_c=np.array([1e-15, 5e-15, 10e-15]),
        upset_fraction=np.array([0.0, 1.0, 1.0]),
        dip_v=np.array([0.17, 1.2, 1.2]),
    )
    common = {"x_label": "Strike charge (C)", "x_log": True, "x": upset.charge_c}
    assert_axes(
        plots.plot_dip_charge(upset),
        name="dip_charge",
        y_label="Output dip (V)",
        series="dip",
        y=upset.dip_v,
        y_log=True,
        **common,
    )
    assert_axes(
        plots.plot_upset_charge(upset),
        name="upset_charge",
        y_label="Fraction upset",
        series="upset",
        y=upset.upset_fraction,
        **common,
    )
    for drawn in (plots.plot_dip_charge(upset), plots.plot_upset_charge(upset)):
        assert drawn.x_bands == [Band(1e-15, 5e-15, "critical charge")]
        assert "strike into qb (2 fF)" in drawn.title
    assert plots.plot_upset_charge(upset).y_range == (0.0, 1.0) and plots.plot_dip_charge(upset).y_range is None
    dice = replace(upset, dut=runs.latch_dice())
    assert "strike into x1 (unloaded)" in plots.plot_upset_charge(dice).title
    # no flip on the grid: nothing shaded
    immune = replace(upset, upset_fraction=np.zeros(3))
    assert plots.plot_upset_charge(immune).x_bands == []
