"""The latch's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
a characterization's condition sweeps, over the supply, the data offset, the clock frequency and a
strike's charge (the record's plots), with setup, hold, f_max and the critical charge marked where
the figure shows them, a share of edges or strikes on an axis from 0 to 1. The viewer draws a
record's from its JSON, ``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

import math

import numpy as np

from flow.pipeline import Band, Marker, Plot, plot

from .params import UPSET_NODE, Style
from .types import AnalysisConstraint, AnalysisSr, AnalysisTiming, AnalysisUpset


def _delay_label(result: AnalysisTiming | AnalysisSr) -> str:
    """The axis label of a design's delays to q: a flip-flop's or divider's clock-to-Q, a
    transparent latch's D-to-Q (d arrives while it is open), an SR latch's propagation delay."""
    if isinstance(result, AnalysisSr):
        return "Delay (s)"
    return "Clock-to-Q delay (s)" if result.dut.flop else "D-to-Q delay (s)"


def _launch(result: AnalysisTiming | AnalysisSr, *, rising: bool) -> str:
    """What a design's delay to q rising (falling) runs from, for its figures' titles."""
    if isinstance(result, AnalysisSr):
        return "from s" if rising else "from r"
    return "from clk" if result.dut.flop else "from d, the latch open"


def _supply_over_nominal(supply: AnalysisTiming | AnalysisSr) -> list[float]:
    """Each run's supply over the nominal one, the middle of the sweep (90, 100, 110 %)."""
    return [float(value) for value in supply.vdd_v / np.median(supply.vdd_v)]


def _supply_condition(supply: AnalysisTiming | AnalysisSr) -> str:
    """The supply runs' clock period, or an SR latch's set and reset period, for the figures'
    titles: one set pulse and one reset pulse each period."""
    if isinstance(supply, AnalysisTiming):
        return f"{float(np.median(supply.clock_period_s)) * 1e9:.3g} ns clock"
    return f"one set and one reset every {float(np.median(supply.data_period_s)) * 1e9:.3g} ns"


def _constraint_markers(constraint: AnalysisConstraint) -> list[Marker]:
    """The setup and hold boundaries on the data offset axis: setup at its offset, hold at minus
    the hold time (d changing that long after the edge, or before it where negative)."""
    markers = []
    if math.isfinite(constraint.setup_s):
        markers.append(Marker(constraint.setup_s, "setup"))
    if math.isfinite(constraint.hold_s):
        markers.append(Marker(-constraint.hold_s, "hold"))
    return markers


def _period_condition(period: AnalysisTiming) -> str:
    """The period runs' stimulus, for the frequency figures' titles."""
    return "toggling" if period.dut.divider else "d half a period before each edge"


def _fmax_markers(period: AnalysisTiming) -> list[Marker]:
    """f_max on the clock frequency axis, where the period runs found one."""
    fmax = period.fmax_hz
    return [Marker(fmax, "f_max")] if math.isfinite(fmax) else []


def _captured_delays(timing: AnalysisTiming, delays: np.ndarray) -> list[float]:
    """The runs' delays where every edge captured, NaN where some did not: a median over the few
    edges a failing run captured is not the cell's delay at that clock or data offset."""
    return [
        float(delay) if captured == 1.0 else math.nan
        for delay, captured in zip(delays, timing.captured_fraction, strict=True)
    ]


def _upset_bands(upset: AnalysisUpset) -> list[Band]:
    """The charges between the largest recovered strike and the smallest flipping one, where the
    critical charge lies."""
    low, high = upset.critical_charge_c, upset.flip_charge_c
    return [Band(low, high, "critical charge")] if low > 0 and math.isfinite(high) else []


def _struck(upset: AnalysisUpset) -> str:
    """The struck node and its load, for the charge figures' titles."""
    node = UPSET_NODE[upset.dut.style]
    load = f"{upset.cload_f * 1e15:g} fF" if upset.dut.style is Style.CLOCKED else "unloaded"
    return f"strike into {node} ({load}), q holding a 1"


# [Baker] Fig. 10.9, p. 333: t_PLH, between the 50 % points (an SR latch's set delay)
# [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay (a flip-flop's, a divider's)
# not in the reference texts: a transparent latch's D-to-Q delay
@plot
def plot_delay_rise_supply(supply: AnalysisTiming | AnalysisSr) -> Plot:
    """The delay to q rising over the supply, relative to nominal."""
    return Plot(
        name="delay_rise_supply",
        title=f"Delay to q rising {_launch(supply, rising=True)} over the supply ({_supply_condition(supply)})",
        x_label="Supply over nominal",
        y_label=_delay_label(supply),
        x=_supply_over_nominal(supply),
        series={"delay": [float(value) for value in supply.delay_rise_s]},
    )


# [Baker] Fig. 10.9, p. 333: t_PHL, between the 50 % points (an SR latch's reset delay)
# [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay (a flip-flop's, a divider's)
# not in the reference texts: a transparent latch's D-to-Q delay
@plot
def plot_delay_fall_supply(supply: AnalysisTiming | AnalysisSr) -> Plot:
    """The delay to q falling over the supply, relative to nominal."""
    return Plot(
        name="delay_fall_supply",
        title=f"Delay to q falling {_launch(supply, rising=False)} over the supply ({_supply_condition(supply)})",
        x_label="Supply over nominal",
        y_label=_delay_label(supply),
        x=_supply_over_nominal(supply),
        series={"delay": [float(value) for value in supply.delay_fall_s]},
    )


# [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, so a period's energy V_DD I_avg T
@plot
def plot_energy_supply(supply: AnalysisTiming | AnalysisSr) -> Plot:
    """The energy per cycle, the latch's and its inputs' drivers', over the supply."""
    cycle = "clock cycle" if isinstance(supply, AnalysisTiming) else "set and reset cycle"
    return Plot(
        name="energy_supply",
        title=f"Energy per {cycle} from V_DD, the inputs' drivers included, over the supply",
        x_label="Supply over nominal",
        y_label="Energy per cycle (J)",
        x=_supply_over_nominal(supply),
        series={"energy": [float(value) for value in supply.energy_per_cycle_j]},
    )


# [Baker] Fig. 13.25, p. 401: setup time
# [Baker] Fig. 13.26, p. 402: hold time
# not in the reference texts: setup at a 10 % delay pushout (standard-cell characterization)
@plot
def plot_delay_rise_offset(offset: AnalysisTiming, constraint: AnalysisConstraint) -> Plot:
    """The delay to q rising over the data offset before the capturing edge, at the offsets at which
    every edge captured (none drawn where some failed), setup and hold and the 10 % pushout bound
    marked."""
    return Plot(
        name="delay_rise_offset",
        title=f"Delay to q rising {_launch(offset, rising=True)} over the data offset before the capturing edge",
        x_label="Data offset (s)",
        y_label=_delay_label(offset),
        x=[float(value) for value in offset.data_offset_s],
        series={"delay": _captured_delays(offset, offset.delay_rise_s)},
        x_markers=_constraint_markers(constraint),
        y_markers=[Marker(1.1 * constraint.delay_rise_s, "10 % pushout")]
        if math.isfinite(constraint.delay_rise_s)
        else [],
    )


# [Baker] Fig. 13.25, p. 401: setup time
# [Baker] Fig. 13.26, p. 402: hold time
# not in the reference texts: setup at a 10 % delay pushout (standard-cell characterization)
@plot
def plot_delay_fall_offset(offset: AnalysisTiming, constraint: AnalysisConstraint) -> Plot:
    """The delay to q falling over the data offset before the capturing edge, at the offsets at which
    every edge captured (none drawn where some failed), setup and hold and the 10 % pushout bound
    marked."""
    return Plot(
        name="delay_fall_offset",
        title=f"Delay to q falling {_launch(offset, rising=False)} over the data offset before the capturing edge",
        x_label="Data offset (s)",
        y_label=_delay_label(offset),
        x=[float(value) for value in offset.data_offset_s],
        series={"delay": _captured_delays(offset, offset.delay_fall_s)},
        x_markers=_constraint_markers(constraint),
        y_markers=[Marker(1.1 * constraint.delay_fall_s, "10 % pushout")]
        if math.isfinite(constraint.delay_fall_s)
        else [],
    )


# [Baker] Fig. 13.25, p. 401: setup time, d applied t_s before the clock edge
# not in the reference texts: the share of capturing edges that took the new value
@plot
def plot_captured_offset(offset: AnalysisTiming, constraint: AnalysisConstraint) -> Plot:
    """The fraction of the capturing edges that took the new value over the data offset, setup and
    hold marked."""
    return Plot(
        name="captured_offset",
        title="Edges taking the new value over the data offset before the capturing edge",
        x_label="Data offset (s)",
        y_label="Fraction captured",
        x=[float(value) for value in offset.data_offset_s],
        series={"captured": [float(value) for value in offset.captured_fraction]},
        y_range=(0.0, 1.0),
        x_markers=_constraint_markers(constraint),
    )


# [Baker] Fig. 13.26, p. 402: hold time
# [Baker] Sec. 13.3, p. 401: a negative hold time, d removed before the clock edge
# not in the reference texts: the share of capturing edges that kept the old value
@plot
def plot_held_offset(offset: AnalysisTiming, constraint: AnalysisConstraint) -> Plot:
    """The fraction of the capturing edges that kept the old value over the data offset, setup and
    hold marked."""
    return Plot(
        name="held_offset",
        title="Edges keeping the old value over the data offset before the capturing edge",
        x_label="Data offset (s)",
        y_label="Fraction held",
        x=[float(value) for value in offset.data_offset_s],
        series={"held": [float(value) for value in offset.held_fraction]},
        y_range=(0.0, 1.0),
        x_markers=_constraint_markers(constraint),
    )


# [Razavi-PLL] Sec. 15.1, p. 453: f_max, the maximum allowable input frequency
# not in the reference texts: the share of edges captured (a divider's: toggled)
@plot
def plot_captured_frequency(period: AnalysisTiming) -> Plot:
    """The fraction of the edges captured (a divider's: toggling) over the clock frequency, f_max
    marked."""
    return Plot(
        name="captured_frequency",
        title=f"Edges captured over the clock frequency ({_period_condition(period)})",
        x_label="Clock frequency (Hz)",
        y_label="Fraction captured",
        x=[float(value) for value in 1 / period.clock_period_s],
        series={"captured": [float(value) for value in period.captured_fraction]},
        y_range=(0.0, 1.0),
        x_log=True,
        x_markers=_fmax_markers(period),
    )


# [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay
# [Razavi-PLL] Sec. 15.1, p. 453: f_max, the maximum allowable input frequency
@plot
def plot_delay_rise_frequency(period: AnalysisTiming) -> Plot:
    """The clock-to-Q delay to q rising over the clock frequency, at the runs in which every edge
    captured (none drawn where some failed), f_max marked."""
    return Plot(
        name="delay_rise_frequency",
        title=f"Delay to q rising from clk over the clock frequency ({_period_condition(period)})",
        x_label="Clock frequency (Hz)",
        y_label=_delay_label(period),
        x=[float(value) for value in 1 / period.clock_period_s],
        series={"delay": _captured_delays(period, period.delay_rise_s)},
        x_log=True,
        x_markers=_fmax_markers(period),
    )


# [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay
# [Razavi-PLL] Sec. 15.1, p. 453: f_max, the maximum allowable input frequency
@plot
def plot_delay_fall_frequency(period: AnalysisTiming) -> Plot:
    """The clock-to-Q delay to q falling over the clock frequency, at the runs in which every edge
    captured (none drawn where some failed), f_max marked."""
    return Plot(
        name="delay_fall_frequency",
        title=f"Delay to q falling from clk over the clock frequency ({_period_condition(period)})",
        x_label="Clock frequency (Hz)",
        y_label=_delay_label(period),
        x=[float(value) for value in 1 / period.clock_period_s],
        series={"delay": _captured_delays(period, period.delay_fall_s)},
        x_log=True,
        x_markers=_fmax_markers(period),
    )


# not in the reference texts: q's dip after a strike, its held level minus its lowest after it
@plot
def plot_dip_charge(upset: AnalysisUpset) -> Plot:
    """How far q dips after a strike on the storage node, over the strike's charge (log, so that
    the recovering strikes' small dips show beside the flips), the critical charge shaded."""
    return Plot(
        name="dip_charge",
        title=f"q's dip after a strike ({_struck(upset)})",
        x_label="Strike charge (C)",
        y_label="Output dip (V)",
        x=[float(value) for value in upset.charge_c],
        series={"dip": [float(value) for value in upset.dip_v]},
        x_log=True,
        y_log=True,
        x_bands=_upset_bands(upset),
    )


# not in the reference texts: whether a strike flips the held 1 (one trial a charge), and the
# critical charge, the smallest charge on the storage node that flips the stored state
@plot
def plot_upset_charge(upset: AnalysisUpset) -> Plot:
    """Whether a strike flips the held 1, one strike a charge, over the strike's charge, the
    critical charge shaded."""
    return Plot(
        name="upset_charge",
        title=f"Whether a strike flips the held 1 ({_struck(upset)})",
        x_label="Strike charge (C)",
        y_label="Fraction upset",
        x=[float(value) for value in upset.charge_c],
        series={"upset": [float(value) for value in upset.upset_fraction]},
        y_range=(0.0, 1.0),
        x_log=True,
        x_bands=_upset_bands(upset),
    )
