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
    """Clocked latch, flip-flop or divider timing at each measured point (one run each).

    The events are the capturing edges (a latch's falling, closing edge; a flip-flop's or divider's
    rising one) at clk's mid-supply crossings after the reset and half a clock period, each with an
    opening (rising) edge after it, and, but for a divider, a d crossing within a quarter period of
    ``data_offset_s`` before it; every other edge is passed over. Each event's launch is the later
    of d's crossing and the edge opening the path to q (a flip-flop's or divider's capturing edge, a
    latch's opening edge before it). q is read twice: at the launch (a divider's 0.05 T_CK before
    it, the edge before's sample instant) and at the sample instant, 0.05 T_CK before the next
    opening edge. An event is captured where q moves from the old value to the new one (d's value
    after its crossing; a divider's: the old one's complement), the old value at the first read,
    the new one at the sample instant, and q crossing mid-supply toward it in between; it is held
    where q at the sample instant is d's value before its crossing (a divider: q's value at the
    first read). A divider's old value is the one its edges set in turn, from q 0.05 T_CK before
    its first capturing edge after rst falls (after the run's start without reset), not q's own at
    the edge: a toggle later than the next edge is that edge's old value arriving late, not its
    capture. ``captured_fraction`` and ``held_fraction`` are the shares of the events (NaN without
    one); an event in neither moved q somewhere else, or not at all where it should have. Not in
    the reference texts: a capture so requires q settled within 0.95 T_CK of its edge (a
    flip-flop's or divider's), and a divider that once misses an edge stands out of phase, its later
    edges not captured either.

    ``delay_rise_s`` and ``delay_fall_s`` are medians over the captured events, from the launch to
    q's mid-supply crossing, q rising and falling: a flip-flop's or divider's clock-to-Q delay (a
    divider's negative where q crosses on the clock's ramp, before the clock does), a transparent
    latch's D-to-Q delay (d arrives while it is open). ``idd_a`` is the current from V_DD averaged
    from the first event to the last, ``idd_drivers_a`` the current CMOS drivers of the inputs on
    V_DD would draw over the same span: each input source's signed current integrated while its
    driver's pull-up would conduct, from the start of each rising ramp to the start of the next
    falling one, summed over the inputs and divided by the span.
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: V_DD, the supply voltage
    vdd_v: np.ndarray
    # [Razavi-ADC] Sec. 3.1.3, p. 24: T_CK, the clock period
    clock_period_s: np.ndarray
    # not in the reference texts: d's mid-supply crossing before the capturing edge, the swept
    # variable, positive where d crosses before the edge
    # [Baker] Fig. 13.25, p. 401: setup, d applied t_s before the clock edge
    data_offset_s: np.ndarray
    # [Baker] Fig. 10.9, p. 333: t_PLH and t_PHL, between the 50 % points
    # [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay (flip-flops and dividers)
    # not in the reference texts: a transparent latch's D-to-Q delay, from d's mid-supply crossing to
    # q's while the latch is open
    delay_rise_s: np.ndarray
    delay_fall_s: np.ndarray
    # not in the reference texts: the share of capturing edges that took (kept) the value, the
    # block's own pass or fail per edge
    captured_fraction: np.ndarray
    held_fraction: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: I_DD, the current drawn from V_DD
    # [Baker] Eq. (11.14), p. 355: the average current, the charge a period over the period
    idd_a: np.ndarray
    # [Baker] Eq. (11.14), p. 355: a CMOS driver draws from V_DD only the charge it supplies to its load
    idd_drivers_a: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        """The energy a clock cycle drawn from V_DD by the latch and by the inputs' drivers."""
        # [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, so a period's energy V_DD I_avg T
        return self.vdd_v * (self.idd_a + self.idd_drivers_a) * self.clock_period_s

    @property
    def fmax_hz(self) -> float:
        """The highest clock frequency below the first failing one, the runs taken from the slowest
        clock up (a run fails where not every event is captured): f_max lies at or above it and
        below the next frequency run, the one that failed (one step of the period grid above it);
        NaN where the slowest fails, the fastest run's where none fails (f_max at or above it)."""
        # [Razavi-PLL] Sec. 15.1, p. 453: f_max, the maximum allowable input frequency
        # not in the reference texts: f_max read as the top of the contiguous band of passing runs
        # counted from the slowest clock, so that a pass above a failure does not raise it, a lower
        # bound to within the grid's step
        order = np.argsort(self.clock_period_s)[::-1]
        frequency = 1 / self.clock_period_s[order]
        failing = np.flatnonzero(~(self.captured_fraction[order] == 1.0))
        if not len(failing):
            return float(frequency[-1])
        return float(frequency[failing[0] - 1]) if failing[0] > 0 else math.nan


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisConstraint(Analysis):
    """Setup and hold from a data offset sweep (``data_offset_s`` > 0: d crosses before the
    capturing edge).

    ``delay_rise_s`` and ``delay_fall_s`` are the delays at the largest offset, the reference.
    ``setup_s`` is where the contiguous run of passing offsets from the largest one down begins (an
    offset passes where every event is captured with both delays within 10 % of the reference),
    resolved between the grid's bracketing offsets: where the failing one captured too (its delay
    pushed out), the offset at which the pushed-out delay, linear between the two, reaches 1.1
    times the reference (the later of rising and falling); otherwise the passing offset, at most one
    grid step above the boundary. ``hold_s`` is minus the offset where the contiguous run of holding
    offsets from the most negative one up ends (every event held), the boundary to within one grid
    step and never below it. NaN where the sweep has no such boundary: setup where every offset
    passes or none does, hold where every offset holds or none does.
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: V_DD, the supply voltage
    vdd_v: float
    # [Razavi-ADC] Sec. 3.1.3, p. 24: T_CK, the clock period
    clock_period_s: float
    # [Baker] Fig. 10.9, p. 333: t_PLH and t_PHL, between the 50 % points
    delay_rise_s: float
    delay_fall_s: float
    # [Baker] Fig. 13.25, p. 401: setup time t_s, d applied t_s before the clock edge
    # not in the reference texts: setup at a 10 % delay pushout (standard-cell characterization)
    setup_s: float
    # [Baker] Fig. 13.26, p. 402: hold time t_h, how long d must stay after the clock edge
    hold_s: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSr(Analysis):
    """SR latch set and reset delays at each measured supply.

    ``delay_rise_s`` runs from the second active set edge to q rising, ``delay_fall_s`` from the
    second active reset edge to q falling, both at mid-supply, each NaN where q does not cross
    within the active pulse (a quarter of ``data_period_s``); ``idd_a`` averages the current from
    V_DD over one set and reset period (``data_period_s``) from that set edge, ``idd_drivers_a`` the
    current CMOS drivers of the inputs on V_DD would draw over it, their pull-ups' charge
    (``AnalysisTiming``).
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: V_DD, the supply voltage
    vdd_v: np.ndarray
    # not in the reference texts: the period of the bench's set and reset pulses, one each
    data_period_s: np.ndarray
    # [Baker] Fig. 10.9, p. 333: t_PLH and t_PHL, between the 50 % points
    delay_rise_s: np.ndarray
    delay_fall_s: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: I_DD, the current drawn from V_DD
    # [Baker] Eq. (11.14), p. 355: the average current, the charge a period over the period
    idd_a: np.ndarray
    # [Baker] Eq. (11.14), p. 355: a CMOS driver draws from V_DD only the charge it supplies to its load
    idd_drivers_a: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        """The energy a set and reset cycle drawn from V_DD by the latch and by the inputs' drivers."""
        # [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, so a period's energy V_DD I_avg T
        return self.vdd_v * (self.idd_a + self.idd_drivers_a) * self.data_period_s


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisUpset(Analysis):
    """Latch response to a strike at each charge (the upset bench): the strike into the storage
    node holding a 0 while q holds a 1 (sim.testbench).

    ``upset_fraction`` is 1 where q, holding a 1 before the strike, ends below mid-supply, else 0
    (one strike a run), NaN where q did not hold a 1 (the write failed: the run says nothing);
    ``dip_v`` is how far q falls after the strike, recovered or not (NaN where it held no 1).
    ``flip_charge_c`` is the smallest charge that flipped q (NaN where none did) and
    ``critical_charge_c`` the largest one below it that q recovered from (0 where the smallest
    flipped it; the largest strike where none did): the critical charge lies between the two.
    ``cload_f`` is the load on q and qb in the runs (on the struck node itself where that is qb).
    """

    # [Razavi-Analog] Sec. 6.7.1, p. 204: C_L, the load capacitance
    cload_f: float
    # not in the reference texts: a strike's charge, the integral of its double-exponential current
    charge_c: np.ndarray
    # not in the reference texts: 1 where the strike flipped the held 1, a share of one trial
    upset_fraction: np.ndarray
    # not in the reference texts: q's held level minus its lowest after the strike
    dip_v: np.ndarray

    @property
    def flip_charge_c(self) -> float:
        # not in the reference texts: the smallest strike that flipped q, the critical charge's upper bound
        flipped = self.charge_c[self.upset_fraction == 1.0]
        return float(np.min(flipped)) if len(flipped) else math.nan

    @property
    def critical_charge_c(self) -> float:
        # not in the reference texts: critical charge, the smallest charge on the storage node that
        # flips the stored state (single-event upset); here its lower bound, the largest strike
        # below the first flip that q recovered from
        valid = np.isfinite(self.upset_fraction)
        if not np.any(valid):
            return math.nan
        recovered = self.charge_c[valid & (self.upset_fraction == 0.0) & ~(self.charge_c >= self.flip_charge_c)]
        return float(np.max(recovered)) if len(recovered) else 0.0


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A latch's numbers (``analysis.metrics``): at the nominal supply the delays to q rising and
    falling and the energy per cycle; the slowest delay over the supply; a latch's or flip-flop's
    setup and hold; a flip-flop's or divider's highest clock frequency and its capture at a slow
    clock; a C2MOS or DICE latch's critical charge. NaN where a design has no such run.

    The timing conditions: ideal complementary clocks of zero skew, edges ramping 0 to 100 % in
    50 ps (40 ps 10 to 90 %), 2 fF on q and on qb, a 2 ns clock, d toggling every cycle and crossing
    mid-supply 0.5 ns before each capturing edge; an SR latch set and reset once each every 5.2 ns."""

    # [Baker] Fig. 10.9, p. 333: t_PLH, between the 50 % points
    delay_rise_s: float = metric(
        "Delay to q rising at the nominal supply: a flip-flop's or divider's from clk (clock-to-Q), a "
        "latch's from d while it is open (D-to-Q), an SR latch's from s; 2 ns clock, 50 ps (0-100 %) "
        "edges, 2 fF on q and qb",
        "lower",
    )
    # [Baker] Fig. 10.9, p. 333: t_PHL, between the 50 % points
    delay_fall_s: float = metric(
        "Delay to q falling at the nominal supply: a flip-flop's or divider's from clk (clock-to-Q), a "
        "latch's from d while it is open (D-to-Q), an SR latch's from r; 2 ns clock, 50 ps (0-100 %) "
        "edges, 2 fF on q and qb",
        "lower",
    )
    # [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, the energy a period V_DD I_avg T
    # [Pelgrom] Sec. 3.3.3, p. 86: d changing polarity every cycle, an activity of 1
    energy_per_cycle_j: float = metric(
        "Energy per 2 ns clock cycle at the nominal supply drawn from V_DD by the latch and by CMOS "
        "drivers of its inputs (V_DD times the charge each input's source delivers while its driver's "
        "pull-up would conduct, from each rising ramp to the next falling one), leakage included; "
        "d toggling every cycle, 2 fF on q and qb, 50 ps (0-100 %) edges (SR: one set and one reset in "
        "5.2 ns)",
        "lower",
    )
    # not in the reference texts: the worst of the rising and falling delays over the supply runs
    delay_max_supply_s: float = metric("Slowest delay to q over 90 to 110 % of the supply", "lower")
    # [Baker] Fig. 13.25, p. 401: setup time
    # not in the reference texts: setup at a 10 % delay pushout (standard-cell characterization)
    setup_s: float = metric(
        "Setup time: the data offset before the capturing edge from which every edge captures with "
        "both delays within 10 % of those with d 300 ps early; resolved between 10 ps grid points "
        "(to one step where the failing point does not capture); NaN where no offset fails or none "
        "passes",
        "lower",
    )
    # [Baker] Fig. 13.26, p. 402: hold time
    hold_s: float = metric(
        "Hold time: from how long after the capturing edge d may change with the old value kept at "
        "every edge (negative: before the edge); at most one 10 ps grid step above the true value; "
        "NaN where every offset holds or none does",
        "lower",
    )
    # [Razavi-PLL] Sec. 15.1, p. 453: f_max, the maximum allowable input frequency
    # not in the reference texts: its lower bound on the period grid, to within the grid's 10 % step
    fmax_hz: float = metric(
        "Highest clock frequency, from the slowest up to the first failure, at which every edge "
        "captures (a divider: toggles) with q settled within 0.95 of a period; a lower bound, f_max "
        "at or above it and below the next frequency run, 10 % above it (the fastest run, 34 GHz, "
        "where none fails); a flip-flop's d crossing mid-supply half a period before each rising "
        "edge; 3.68 ps (0-100 %) edges at every period",
        "higher",
    )
    # [Razavi-PLL] Sec. 15.2.2, p. 459: a dynamic latch loses its state at too slow a clock
    captured_1mhz_fraction: float = metric(
        "Share of the edges captured (a divider: toggled) at a 1 MHz clock, d half a period before each "
        "rising edge: a dynamic (TSPC) circuit's lower frequency bound checked at that clock",
        "higher",
    )
    # not in the reference texts: critical charge (single-event upset), its lower bound
    critical_charge_c: float = metric(
        "Critical charge, lower bound: the largest strike q recovers from below the smallest that "
        "flips it, within one 10 % step of the true value (the largest strike, 208 fC, where none "
        "flips); the strike into the node holding 0 while q holds 1 (C2MOS: qb, carrying 2 fF; DICE: "
        "x1, unloaded), the other nodes and the stored 0 not struck",
        "higher",
    )
    # not in the reference texts: the smallest flipping strike, the critical charge's upper bound
    flip_charge_c: float = metric(
        "Smallest strike that flips the held 1 (the critical charge's upper bound): NaN where no strike "
        "up to 208 fC does; the strike into the node holding 0 while q holds 1 (C2MOS: qb, carrying "
        "2 fF; DICE: x1, unloaded)",
        "higher",
    )
