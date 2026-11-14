"""The delay line and ring oscillator's analysis results (``flow.delay.analysis``), pure data: at
each measured point (a run over the supply or the control voltage), a ring's oscillation and a
delay line's propagation; and the record's metrics (``Metrics``).

Every current is the chain's own supply's (the testbench's ``vvdd``): the chain's stages, which
charge the stage loading each output too, without the bias generation; a ring's counts every
stage's input, while a delay line's leaves out its first stage's input charge, which the driving
stages supply."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric

from .params import Oscillation


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOscillation(Analysis):
    """Ring oscillation at each measured supply and control point.

    A differential ring is measured on its p chain alone: ``outp`` single-ended at mid-supply.
    ``oscillation`` says what ``outp`` did after the enable (``Oscillation``). Where it is timed,
    over the last ten whole cycles at most before the run's end (between its last rising crossings
    of mid-supply): ``oscillation_frequency_hz`` the cycles over their time, ``idd_a`` the supply
    current averaged over them, ``swing_v`` the output's peak to peak and ``duty_cycle`` its high
    time over the period there. A point not timed (too slow, or stopped) holds NaN.
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: the supply voltage V_DD
    vdd_v: np.ndarray
    # [Razavi-PLL] Sec. 1.6, p. 27: the control voltage
    vcont_v: np.ndarray
    # [Razavi-PLL] Sec. 3.1.1, p. 64: oscillation frequency, f0 = 1/T0 of the steady oscillation
    oscillation_frequency_hz: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: supply current of a ring, periodic in the ring's cycle
    idd_a: np.ndarray
    # [Razavi-PLL] Sec. 1.4.1, Fig. 1.14, p. 12: a ring regenerates to a rail-to-rail swing (the
    # notation's name, output swing: [Razavi-Analog] Sec. 9.1.1, p. 348). Here its peak to peak, with the overshoot past each rail (the driving stage's input
    # edge coupled through its gate-drain capacitance)
    swing_v: np.ndarray
    # [Razavi-PLL] Sec. 11.10, Fig. 11.29(a), p. 365: duty cycle, the high time over the period
    duty_cycle: np.ndarray
    # not in the reference texts: whether the output kept crossing mid-supply to the run's end, and
    # whether it made the cycles to be timed (the rule in Oscillation's members)
    oscillation: tuple[Oscillation, ...]

    @property
    def oscillating(self) -> np.ndarray:
        # not in the reference texts: the output crossed mid-supply to the run's end, timed or not
        return np.asarray([state is not Oscillation.STOPPED for state in self.oscillation], dtype=np.bool_)

    @property
    def average_power_w(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 3.3.2, p. 74: a ring's power P; [Baker] Eq. (11.15), p. 355: the average
        # power, the supply voltage times its average current
        return self.vdd_v * self.idd_a

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 3.3.2, p. 74: P = N f0 C_tot V_DD^2, so P / f0 is a cycle's energy
        return self.average_power_w / self.oscillation_frequency_hz

    @property
    def stage_delay_s(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 3.3.2, p. 74: f0 = 1 / (2 N T_D); [Razavi-Analog] Sec. 15.4.1, p. 633: a
        # differential ring's too, N its stages per chain. Derived with [Baker] Eq. (11.11), p. 354,
        # f_osc = 1 / (n (t_PHL + t_PLH)) for identical stages: here T_D is the mean over the loop's
        # unequal stages, the gated first stage and the output's (loaded by the first stage and the
        # load stages) among them
        return 1 / (2 * self.dut.stages * self.oscillation_frequency_hz)

    @property
    def kvco_hz_per_v(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 1.6, Fig. 1.33, pp. 27-28: K_VCO, the slope of the frequency over the
        # control (here in Hz/V); [Razavi-PLL] Fig. 3.27, p. 84: the tuning curve's local slope, at
        # each control point
        # not in the reference texts: the difference, over each run of consecutive timed points
        # alone: central inside it, second-order one-sided at its ends (first order in a run of two),
        # NaN at a point not timed and at a timed point with no timed neighbour
        frequency, control = self.oscillation_frequency_hz, self.vcont_v
        gain = np.full(len(frequency), np.nan)
        timed = np.flatnonzero(np.isfinite(frequency))
        for run in np.split(timed, np.flatnonzero(np.diff(timed) > 1) + 1):
            if len(run) >= 2:
                gain[run] = np.gradient(frequency[run], control[run], edge_order=2 if len(run) >= 3 else 1)
        return gain


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisPropagation(Analysis):
    """Delay line propagation at each measured supply and control point.

    A differential line is measured on its p chain alone: ``inp`` to ``outp``, single-ended at
    mid-supply. ``delay_rise_s`` and ``delay_fall_s`` run from the line's second rising (falling)
    input edge to the output edge it caused, both at mid-supply: counted from the settled start, the
    output edge of the same count (the k-th rising output edge of a non-inverting line answers its
    k-th rising input edge), so a delay of a period or more is still paired right. A delay is NaN
    where it is not positive or where the first edges' delay differs from the second's by more than a
    quarter of the input period (an edge lost or added between them shifts the count by a period).
    ``rise_time_s`` and ``fall_time_s`` are the 10-90 % transitions between the rails of the output
    edges the delays timed, NaN where the output turns back through mid-supply before completing
    one; ``idd_a`` averages two input periods (``clock_period_s`` each) from the second rising input
    edge. ``valid`` where every one of them was found.
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: the supply voltage V_DD
    vdd_v: np.ndarray
    # [Razavi-PLL] Sec. 1.6, p. 27: the control voltage
    vcont_v: np.ndarray
    # [Baker] Eq. (11.14), Fig. 11.13, p. 355: the period of the square input
    clock_period_s: np.ndarray
    # [Baker] Sec. 10.1.3, Fig. 10.9, p. 333: propagation delays t_PLH, t_PHL, by the output's edge
    delay_rise_s: np.ndarray
    delay_fall_s: np.ndarray
    # [Baker] Sec. 10.1.3, Fig. 10.9, p. 333; Eq. (2.26), p. 49: output rise and fall times, 10 to 90 %
    rise_time_s: np.ndarray
    fall_time_s: np.ndarray
    # [Baker] Eq. (11.14), p. 355: the average current drawn from the supply over input periods
    idd_a: np.ndarray
    # not in the reference texts: every delay, transition and the current found at this point
    valid: np.ndarray

    @property
    def average_power_w(self) -> np.ndarray:
        # [Razavi-PLL] Sec. 3.3.2, p. 74: power P; [Baker] Eq. (11.15), p. 355: the average power at
        # the input clock, V_DD I_avg = C_tot V_DD^2 f_clk
        return self.vdd_v * self.idd_a

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        # [Baker] Eq. (11.15), p. 355: the average power times the input clock's period
        return self.vdd_v * self.idd_a * self.clock_period_s

    @property
    def delay_s(self) -> np.ndarray:
        # [Baker] Sec. 10.1.3, Fig. 10.9, p. 333: the line's delay, the mean of t_PLH and t_PHL
        return (self.delay_rise_s + self.delay_fall_s) / 2

    @property
    def stage_delay_s(self) -> np.ndarray:
        # [Baker] Eq. (11.22), p. 360: a string's t_PHL + t_PLH, the sum of its stages'; the mean
        # stage delay (t_PLH + t_PHL) / (2 N), its output stage's among them
        return (self.delay_rise_s + self.delay_fall_s) / (2 * self.dut.stages)


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A chain's numbers (``analysis.metrics``) at the PDK's supply and the nominal control: a
    ring's frequency, swing and duty cycle, a delay line's delays and output transitions, either one's mean
    stage delay, power and energy per cycle, its slowest mean stage delay over the supply, and, with
    a control, its gain about the nominal control. NaN where a chain has no such number (a ring's
    for a delay line, a delay line's for a ring, a gain without a control), and the slowest stage
    delay NaN where a supply point was not timed or not valid. Power and energy are the chain's own
    supply's, the bias generation excluded. A differential chain's are its p chain's, single-ended."""

    # [Razavi-PLL] Sec. 3.1.1, p. 64: oscillation frequency
    oscillation_frequency_hz: float = metric("A ring's oscillation frequency", "higher")
    # [Razavi-PLL] Sec. 1.4.1, Fig. 1.14, p. 12: a ring's rail-to-rail swing (the notation's output
    # swing, [Razavi-Analog] Sec. 9.1.1, p. 348); here peak to peak, its overshoot past the rails
    # included
    swing_v: float = metric(
        "A ring's output swing, peak to peak: rail to rail plus the overshoot past each rail", "higher"
    )
    # [Razavi-PLL] Sec. 11.10, Fig. 11.29(a), p. 365: duty cycle, the high time over the period
    duty_cycle: float = metric("A ring's output duty cycle: its high time over the period", "none")
    # [Baker] Sec. 10.1.3, Fig. 10.9, p. 333: t_PLH, t_PHL
    delay_rise_s: float = metric("A delay line's delay to its rising output", "none")
    delay_fall_s: float = metric("A delay line's delay to its falling output", "none")
    # [Baker] Sec. 10.1.3, Fig. 10.9, p. 333; Eq. (2.26), p. 49: t_LH, t_HL, 10 to 90 %
    rise_time_s: float = metric("A delay line's output rise time, 10 to 90 %", "lower")
    fall_time_s: float = metric("A delay line's output fall time, 90 to 10 %", "lower")
    # [Razavi-PLL] Sec. 3.3.2, p. 74 (a ring: 1 / (2 N f0)); [Baker] Eq. (11.22), p. 360: a string's
    # t_PHL + t_PLH, the sum of its stages' (a line: (t_PLH + t_PHL) / (2 N))
    stage_delay_s: float = metric(
        "Mean delay per stage: a ring's 1 / (2 N f0), a delay line's (t_PLH + t_PHL) / (2 N)", "none"
    )
    # [Razavi-PLL] Sec. 3.3.2, p. 74: power P; [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg
    average_power_w: float = metric(
        "Average power from the chain's supply: a ring's own, a delay line's at the bench's input clock", "lower"
    )
    # [Razavi-PLL] Sec. 3.3.2, p. 74 (a ring: P / f0); [Baker] Eq. (11.15), p. 355 (a line: P T)
    energy_per_cycle_j: float = metric(
        "Energy per cycle from the chain's supply (a ring's own cycle, a delay line's input clock's)", "lower"
    )
    # [Razavi-PLL] Sec. 1.4.1, p. 12: a stage's delay falls as the supply rises; the sweep's slowest
    stage_delay_max_supply_s: float = metric(
        "Slowest mean delay per stage over the supply, the worst case at the typical corner and 25 C "
        "(NaN where a point was not timed or not valid)",
        "none",
    )
    # [Razavi-PLL] Sec. 1.6, Fig. 1.33, pp. 27-28: K_VCO, here in Hz/V
    kvco_hz_per_v: float = metric("A ring's gain: its frequency's slope over the control", "none")
    # [Razavi-PLL] Sec. 11.1, p. 346: K_DL, here as time per volt
    kdl_s_per_v: float = metric("A delay line's gain: its delay's slope over the control", "none")
