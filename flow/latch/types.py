"""The latch's analysis results (``flow.latch.analysis``) and its metrics, pure data: a clocked
latch's, flip-flop's or divider's timing at each measured point, its setup and hold from a data
offset sweep, an SR latch's delays, and a latch's response to a strike over its charge."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisTiming(Analysis):
    """Clocked latch, flip-flop or divider timing at each measured point.

    Every capturing edge after the reset is one event (a latch's falling edge, a flip-flop's or
    divider's rising one). ``captured_fraction`` counts events whose output took the new value
    (a divider: toggled), ``held_fraction`` those that kept the old one. ``clock_to_q_rise_s`` and
    ``clock_to_q_fall_s`` are medians over captured events, from the launching edge (the later of
    the data edge and the edge opening the path to q) to q's mid-supply crossing, rising and
    falling; ``idd_a`` the supply current averaged from the first event to the last.
    """

    vdd_v: np.ndarray
    clock_period_s: np.ndarray
    data_offset_s: np.ndarray
    clock_to_q_rise_s: np.ndarray
    clock_to_q_fall_s: np.ndarray
    captured_fraction: np.ndarray
    held_fraction: np.ndarray
    idd_a: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        return self.vdd_v * self.idd_a * self.clock_period_s


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisConstraint(Analysis):
    """Setup and hold from a data offset sweep.

    ``setup_s`` is the smallest offset from which every larger one captures with both delays
    within 10 % of those at the largest offset (``clock_to_q_rise_s``, ``clock_to_q_fall_s``);
    ``hold_s`` the smallest delay after the edge from which every later data change leaves the old
    value held. NaN where the sweep never met the condition.
    """

    vdd_v: float
    clock_period_s: float
    clock_to_q_rise_s: float
    clock_to_q_fall_s: float
    setup_s: float
    hold_s: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSr(Analysis):
    """SR latch set and reset delays at each measured supply.

    ``delay_rise_s`` runs from the second active set edge to q rising, ``delay_fall_s`` from the
    second active reset edge to q falling, both at mid-supply; ``idd_a`` averages the supply
    current over one set and reset period (``data_period_s``) from that set edge.
    """

    vdd_v: np.ndarray
    data_period_s: np.ndarray
    delay_rise_s: np.ndarray
    delay_fall_s: np.ndarray
    idd_a: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        return self.vdd_v * self.idd_a * self.data_period_s


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisUpset(Analysis):
    """Latch response to a strike at each charge (the upset bench).

    ``upset_fraction`` is 1 where q, holding a 1, ends below mid-supply, else 0 (one strike a
    run); ``dip_v`` is how far q falls after the strike, recovered or not; ``critical_charge_c``
    the smallest charge that flipped q (NaN where none did).
    """

    charge_c: np.ndarray
    upset_fraction: np.ndarray
    dip_v: np.ndarray

    @property
    def critical_charge_c(self) -> float:
        flipped = self.charge_c[self.upset_fraction > 0]
        return float(np.min(flipped)) if len(flipped) else math.nan


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A latch's numbers (``analysis.metrics``): at the nominal supply the delays to q rising and
    falling (a clocked design's from the launching edge, an SR latch's from set and reset) and the
    energy per cycle; the slowest delay over the supply; a latch's or flip-flop's setup and hold;
    a flip-flop's or divider's highest clock frequency; a C2MOS or DICE latch's critical charge.
    NaN where a design has no such run."""

    delay_rise_s: float = metric("Delay to q rising at the nominal supply", "lower")
    delay_fall_s: float = metric("Delay to q falling at the nominal supply", "lower")
    energy_per_cycle_j: float = metric("Supply energy per clock (SR: set and reset) cycle", "lower")
    delay_max_supply_s: float = metric("Slowest delay to q over the supply", "lower")
    setup_s: float = metric("Setup time at a 10 % delay pushout", "lower")
    hold_s: float = metric("Hold time", "lower")
    fmax_hz: float = metric("Highest clock frequency at which every edge captures", "higher")
    critical_charge_c: float = metric("Smallest charge on the storage node that flips a held 1", "higher")
