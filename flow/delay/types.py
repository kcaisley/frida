"""The delay line and ring oscillator's analysis results (``flow.delay.analysis``), pure data: at
each measured point (a run over the supply or the control voltage), a ring's oscillation and a
delay line's propagation; and the record's metrics (``Metrics``)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOscillation(Analysis):
    """Ring oscillation at each measured supply and control point.

    ``oscillation_frequency_hz`` counts rising ``outp`` crossings of mid-supply from the fifth after
    enable (up to ten cycles); ``idd_a`` is the supply current averaged over those cycles,
    ``swing_v`` the output's peak to peak and ``duty_cycle`` the share of the time it spends above
    mid-supply there. A point whose output made fewer than three cycles is not oscillating and
    holds NaN.
    """

    vdd_v: np.ndarray
    vcont_v: np.ndarray
    # [Razavi-PLL] Sec. 3.1.1, p. 64: oscillation frequency and period
    oscillation_frequency_hz: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: supply current of a ring
    idd_a: np.ndarray
    # [Razavi-Analog] Sec. 9.1.1, p. 348: output swing
    swing_v: np.ndarray
    # [Razavi-PLL] Sec. 11.10, p. 365: duty cycle
    duty_cycle: np.ndarray
    oscillating: np.ndarray

    @property
    def average_power_w(self) -> np.ndarray:
        # [Baker] Eq. (11.15), p. 355: average power from the supply
        return self.vdd_v * self.idd_a

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        # [Baker] Eq. (11.15), p. 355: the average power over the frequency
        return self.average_power_w / self.oscillation_frequency_hz

    @property
    def stage_delay_s(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 3.3.2, p. 74: a ring's frequency from its gate delay
        return 1 / (2 * self.dut.stages * self.oscillation_frequency_hz)

    @property
    def kvco_hz_per_v(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 1.6, p. 27: the gain of a VCO, the frequency's slope over the control
        return np.gradient(self.oscillation_frequency_hz, self.vcont_v)


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPropagation(Analysis):
    """Delay line propagation at each measured supply and control point.

    ``delay_rise_s`` and ``delay_fall_s`` run from the second ``inp`` edge that makes ``outp`` rise
    (fall) to that ``outp`` edge, both at mid-supply; ``rise_time_s`` and ``fall_time_s`` are the
    output's 10-90 % transitions; ``idd_a`` averages two input periods (``clock_period_s`` each)
    from the second rising input edge. ``valid`` where every one of them was found.
    """

    vdd_v: np.ndarray
    vcont_v: np.ndarray
    clock_period_s: np.ndarray
    # [Baker] Fig. 10.9, p. 333: propagation delays to the rising and the falling output
    delay_rise_s: np.ndarray
    delay_fall_s: np.ndarray
    # [Baker] Fig. 10.9, p. 333: output rise and fall times
    rise_time_s: np.ndarray
    fall_time_s: np.ndarray
    idd_a: np.ndarray
    valid: np.ndarray

    @property
    def average_power_w(self) -> np.ndarray:
        # [Baker] Eq. (11.15), p. 355: average power from the supply
        return self.vdd_v * self.idd_a

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        # [Baker] Eq. (11.15), p. 355: the average power times the input clock's period
        return self.vdd_v * self.idd_a * self.clock_period_s

    @property
    def delay_s(self) -> np.ndarray:
        """The line's delay, the mean of its two directions."""
        return (self.delay_rise_s + self.delay_fall_s) / 2

    @property
    def stage_delay_s(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 1.4.1, p. 12: gate delay
        return (self.delay_rise_s + self.delay_fall_s) / (2 * self.dut.stages)


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A chain's numbers (``analysis.metrics``) at the PDK's supply and the nominal control: a
    ring's frequency and swing, a delay line's delays and output transitions, either one's stage
    delay, power and energy per cycle, its slowest stage delay over the supply, and, with a
    control, its gain about the nominal control. NaN where a chain has no such number (a ring's
    for a delay line, a delay line's for a ring, a gain without a control)."""

    oscillation_frequency_hz: float = metric("A ring's oscillation frequency", "higher")
    swing_v: float = metric("A ring's output swing, peak to peak", "higher")
    delay_rise_s: float = metric("A delay line's delay to its rising output", "none")
    delay_fall_s: float = metric("A delay line's delay to its falling output", "none")
    rise_time_s: float = metric("A delay line's output rise time, 10 to 90 %", "lower")
    fall_time_s: float = metric("A delay line's output fall time, 90 to 10 %", "lower")
    stage_delay_s: float = metric("Delay per stage", "lower")
    average_power_w: float = metric("Average power from the supply", "lower")
    energy_per_cycle_j: float = metric("Energy per cycle (a ring's own, a delay line's input clock's)", "lower")
    stage_delay_max_supply_s: float = metric("Slowest delay per stage over the supply", "lower")
    kvco_hz_per_v: float = metric("A ring's gain: its frequency's slope over the control", "none")
    kdl_s_per_v: float = metric("A delay line's gain: its delay's slope over the control", "none")
