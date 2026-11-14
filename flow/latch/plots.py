"""The latch's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
a characterization's condition sweeps, over the supply, the data offset, the clock frequency and a
strike's charge (the record's plots). The viewer draws a record's from its JSON,
``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

import numpy as np

from flow.pipeline import Plot, plot

from .params import SUPPLY_SWEEP
from .types import AnalysisSr, AnalysisTiming, AnalysisUpset


def _delays(supply: AnalysisTiming | AnalysisSr) -> tuple[np.ndarray, np.ndarray, str]:
    """The delays to q rising and falling of a clocked design's or an SR latch's runs, and the
    condition their figures' titles name."""
    if isinstance(supply, AnalysisTiming):
        clock = f"{float(supply.clock_period_s[0]) * 1e9:g} ns clock"
        return supply.clock_to_q_rise_s, supply.clock_to_q_fall_s, clock
    return supply.delay_rise_s, supply.delay_fall_s, "set and reset"


def _cycle(supply: AnalysisTiming | AnalysisSr) -> str:
    """The cycle a design's energy is counted over."""
    return "clock cycle" if isinstance(supply, AnalysisTiming) else "set and reset cycle"


@plot
def plot_delay_rise_supply(supply: AnalysisTiming | AnalysisSr) -> Plot:
    """The delay to q rising over the supply (``SUPPLY_SWEEP``)."""
    rise, _fall, condition = _delays(supply)
    return Plot(
        name="delay_rise_supply",
        title=f"Delay to q rising over the supply ({condition})",
        x_label="Supply over nominal",
        y_label="Delay (s)",
        x=list(SUPPLY_SWEEP),
        series={"delay": [float(value) for value in rise]},
    )


@plot
def plot_delay_fall_supply(supply: AnalysisTiming | AnalysisSr) -> Plot:
    """The delay to q falling over the supply (``SUPPLY_SWEEP``)."""
    _rise, fall, condition = _delays(supply)
    return Plot(
        name="delay_fall_supply",
        title=f"Delay to q falling over the supply ({condition})",
        x_label="Supply over nominal",
        y_label="Delay (s)",
        x=list(SUPPLY_SWEEP),
        series={"delay": [float(value) for value in fall]},
    )


@plot
def plot_energy_supply(supply: AnalysisTiming | AnalysisSr) -> Plot:
    """The supply energy per cycle over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="energy_supply",
        title=f"Energy per {_cycle(supply)} over the supply",
        x_label="Supply over nominal",
        y_label="Energy per cycle (J)",
        x=list(SUPPLY_SWEEP),
        series={"energy": [float(value) for value in supply.energy_per_cycle_j]},
    )


@plot
def plot_clock_to_q_rise_offset(offset: AnalysisTiming) -> Plot:
    """The delay to q rising over the data offset before the capturing edge."""
    return Plot(
        name="clock_to_q_rise_offset",
        title="Delay to q rising over the data offset before the capturing edge (setup and hold)",
        x_label="Data offset (s)",
        y_label="Clock-to-Q delay (s)",
        x=[float(value) for value in offset.data_offset_s],
        series={"delay": [float(value) for value in offset.clock_to_q_rise_s]},
    )


@plot
def plot_clock_to_q_fall_offset(offset: AnalysisTiming) -> Plot:
    """The delay to q falling over the data offset before the capturing edge."""
    return Plot(
        name="clock_to_q_fall_offset",
        title="Delay to q falling over the data offset before the capturing edge (setup and hold)",
        x_label="Data offset (s)",
        y_label="Clock-to-Q delay (s)",
        x=[float(value) for value in offset.data_offset_s],
        series={"delay": [float(value) for value in offset.clock_to_q_fall_s]},
    )


@plot
def plot_captured_offset(offset: AnalysisTiming) -> Plot:
    """The fraction of the capturing edges that took the new value, over the data offset."""
    return Plot(
        name="captured_offset",
        title="Edges taking the new value over the data offset before the capturing edge",
        x_label="Data offset (s)",
        y_label="Fraction captured",
        x=[float(value) for value in offset.data_offset_s],
        series={"captured": [float(value) for value in offset.captured_fraction]},
    )


@plot
def plot_held_offset(offset: AnalysisTiming) -> Plot:
    """The fraction of the capturing edges that kept the old value, over the data offset."""
    return Plot(
        name="held_offset",
        title="Edges keeping the old value over the data offset before the capturing edge",
        x_label="Data offset (s)",
        y_label="Fraction held",
        x=[float(value) for value in offset.data_offset_s],
        series={"held": [float(value) for value in offset.held_fraction]},
    )


@plot
def plot_captured_frequency(period: AnalysisTiming) -> Plot:
    """The fraction of the edges captured (a divider's: toggling) over the clock frequency."""
    return Plot(
        name="captured_frequency",
        title="Edges captured over the clock frequency" + (" (toggling)" if period.dut.divider else ""),
        x_label="Clock frequency (Hz)",
        y_label="Fraction captured",
        x=[float(value) for value in 1 / period.clock_period_s],
        series={"captured": [float(value) for value in period.captured_fraction]},
        x_log=True,
    )


@plot
def plot_clock_to_q_rise_frequency(period: AnalysisTiming) -> Plot:
    """The delay to q rising over the clock frequency."""
    return Plot(
        name="clock_to_q_rise_frequency",
        title="Delay to q rising over the clock frequency",
        x_label="Clock frequency (Hz)",
        y_label="Clock-to-Q delay (s)",
        x=[float(value) for value in 1 / period.clock_period_s],
        series={"delay": [float(value) for value in period.clock_to_q_rise_s]},
        x_log=True,
    )


@plot
def plot_clock_to_q_fall_frequency(period: AnalysisTiming) -> Plot:
    """The delay to q falling over the clock frequency."""
    return Plot(
        name="clock_to_q_fall_frequency",
        title="Delay to q falling over the clock frequency",
        x_label="Clock frequency (Hz)",
        y_label="Clock-to-Q delay (s)",
        x=[float(value) for value in 1 / period.clock_period_s],
        series={"delay": [float(value) for value in period.clock_to_q_fall_s]},
        x_log=True,
    )


@plot
def plot_dip_charge(upset: AnalysisUpset) -> Plot:
    """How far q dips after a strike on the storage node, over the strike's charge."""
    return Plot(
        name="dip_charge",
        title="q's dip after a strike on the storage node (holding a 1)",
        x_label="Injected charge (C)",
        y_label="Output dip (V)",
        x=[float(value) for value in upset.charge_c],
        series={"dip": [float(value) for value in upset.dip_v]},
        x_log=True,
    )


@plot
def plot_upset_charge(upset: AnalysisUpset) -> Plot:
    """Whether a strike flips the held 1, over the strike's charge."""
    return Plot(
        name="upset_charge",
        title="Whether a strike flips the held 1",
        x_label="Injected charge (C)",
        y_label="Fraction upset",
        x=[float(value) for value in upset.charge_c],
        series={"upset": [float(value) for value in upset.upset_fraction]},
        x_log=True,
    )
