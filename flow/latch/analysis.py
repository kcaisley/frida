"""Typed latch, flip-flop, divider and SR latch measurements, results, and analyses.

A ``MeasLatch`` is one transient of the shared latch testbench. Timing follows BAG's sequential
characterization: delays at mid-supply, a capturing edge's data either taken (the new value) or
not (the old one), setup where the delay has grown by 10 % (the liberty pushout), hold where the
old value is still held.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, check_identity, measurement_identity
from flow.latch.sim import LatchTbParams
from flow.latch.subckt import LatchNets, LatchParams, Style


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasLatch(Meas):
    """Latch transient at one supply, clock period and data offset: one record, all in ``wave``."""

    dut: LatchParams
    param: LatchTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisLatchTiming(Analysis):
    """Clocked latch, flip-flop or divider timing at each measured point.

    Every capturing edge after the reset is one event (a latch's falling edge, a flip-flop's or
    divider's rising one). ``captured_fraction`` counts events whose output took the new value
    (a divider: toggled), ``held_fraction`` those that kept the old one. Delays are medians over
    captured events, from the launching edge (the later of the data edge and the edge opening
    the path to q) to q's mid-supply crossing.
    """

    vdd_v: np.ndarray
    clock_period_s: np.ndarray
    data_offset_s: np.ndarray
    clock_to_q_rise_s: np.ndarray
    clock_to_q_fall_s: np.ndarray
    captured_fraction: np.ndarray
    held_fraction: np.ndarray
    supply_current_a: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a * self.clock_period_s


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisLatchConstraint(Analysis):
    """Setup and hold from a data offset sweep.

    ``setup_s`` is the smallest offset from which every larger one captures with both delays
    within 10 % of those at the largest offset; ``hold_s`` the smallest delay after the edge
    from which every later data change leaves the old value held. NaN where the sweep never met
    the condition.
    """

    vdd_v: float
    clock_period_s: float
    reference_rise_s: float
    reference_fall_s: float
    setup_s: float
    hold_s: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisLatchSr(Analysis):
    """SR latch set and reset delays at each measured supply.

    ``set_delay_s`` runs from the second active set edge to q rising, ``reset_delay_s`` from
    the second active reset edge to q falling, both at mid-supply; ``supply_current_a``
    averages one set and reset period from that set edge.
    """

    vdd_v: np.ndarray
    data_period_s: np.ndarray
    set_delay_s: np.ndarray
    reset_delay_s: np.ndarray
    supply_current_a: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a * self.data_period_s


def analyze_latch_timing(measurements: Sequence[MeasLatch]) -> AnalysisLatchTiming:
    """Measure clock-to-q delays, captured and held events, and supply current at each point."""

    identity = measurement_identity(measurements)
    dut = identity.dut
    if dut.style != Style.CLOCKED:
        raise ValueError("latch timing requires a clocked latch, flip-flop, or divider")
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("latch timing requires a waveform record")
        tb = measurement.param
        vdd, period, offset = float(tb.vdd), float(tb.clock_period_s), float(tb.data_offset_s)
        time_s = wave.time_s
        clock = wave.v[LatchNets.clk.name][0]
        data = wave.v[LatchNets.d.name][0]
        output = wave.v[LatchNets.q.name][0]
        opens = calc.cross(clock, time_s, vdd / 2, edge="rising")
        captures = opens if dut.flop else calc.cross(clock, time_s, vdd / 2, edge="falling")
        data_edges = calc.cross(data, time_s, vdd / 2, edge="either")
        rises, falls, captured, held, event_times = [], [], 0, 0, []
        for capture in captures[captures > float(tb.reset_time_s) + period / 2]:
            following = opens[opens > capture + period / 8]
            if not len(following):
                continue
            # q is read just before the next edge that opens its path again
            sample_s = float(following[0]) - 0.05 * period
            before = calc.value(output, time_s, capture - 0.05 * period) > vdd / 2
            after = calc.value(output, time_s, sample_s) > vdd / 2
            if dut.divider:
                launch_s, new = capture, not before
            else:
                nearby = data_edges[np.abs(data_edges - (capture - offset)) < period / 4]
                if not len(nearby):
                    continue
                new = calc.value(data, time_s, capture - offset + period / 4) > vdd / 2
                # a flip-flop's path opens at the capturing edge, a latch's at the rising edge before it
                opening = capture if dut.flop else float(opens[opens <= capture][-1])
                launch_s = max(float(nearby[0]), opening)
            event_times.append(capture)
            if after != new:
                held += 1
                continue
            captured += 1
            response = calc.cross(output, time_s, vdd / 2, edge="rising" if new else "falling")
            response = response[(response > launch_s) & (response < sample_s)]
            if len(response):
                (rises if new else falls).append(float(response[0]) - launch_s)
        if len(event_times) >= 2:
            current, current_s = calc.clip(
                wave.i[LatchNets.vdd.name][0], time_s, float(event_times[0]), float(event_times[-1])
            )
            supply_current_a = calc.average(current, current_s)
        else:
            supply_current_a = math.nan
        events = max(len(event_times), 1)
        rows.append(
            (
                vdd,
                period,
                offset,
                float(np.median(rises)) if rises else math.nan,
                float(np.median(falls)) if falls else math.nan,
                captured / events,
                held / events,
                supply_current_a,
            )
        )
    vdd_v, period_s, offset_s, rise, fall, captured_fraction, held_fraction, current = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisLatchTiming(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        clock_period_s=period_s,
        data_offset_s=offset_s,
        clock_to_q_rise_s=rise,
        clock_to_q_fall_s=fall,
        captured_fraction=captured_fraction,
        held_fraction=held_fraction,
        supply_current_a=current,
    )


def analyze_latch_constraint(
    measurements: Sequence[MeasLatch], *, timing: AnalysisLatchTiming
) -> AnalysisLatchConstraint:
    """Find setup (a 10 % delay pushout) and hold from a data offset sweep at one supply and period."""

    identity = measurement_identity(measurements)
    check_identity(timing, identity, name="timing")
    if len(set(timing.vdd_v)) != 1 or len(set(timing.clock_period_s)) != 1 or len(set(timing.data_offset_s)) < 3:
        raise ValueError("setup and hold require a data offset sweep at one supply and clock period")
    order = np.argsort(timing.data_offset_s)
    offsets = timing.data_offset_s[order]
    rise, fall = timing.clock_to_q_rise_s[order], timing.clock_to_q_fall_s[order]
    passing = (timing.captured_fraction[order] == 1.0) & (rise <= 1.1 * rise[-1]) & (fall <= 1.1 * fall[-1])
    holding = timing.held_fraction[order] == 1.0
    # the contiguous runs from the largest offset down, and from the most negative one up
    failing_setup = np.flatnonzero(~passing)
    setup_index = failing_setup[-1] + 1 if len(failing_setup) else 0
    failing_hold = np.flatnonzero(~holding)
    hold_index = failing_hold[0] - 1 if len(failing_hold) else len(offsets) - 1
    return AnalysisLatchConstraint(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=float(timing.vdd_v[0]),
        clock_period_s=float(timing.clock_period_s[0]),
        reference_rise_s=float(rise[-1]),
        reference_fall_s=float(fall[-1]),
        setup_s=float(offsets[setup_index]) if setup_index < len(offsets) else math.nan,
        hold_s=-float(offsets[hold_index]) if hold_index >= 0 else math.nan,
    )


def analyze_latch_sr(measurements: Sequence[MeasLatch]) -> AnalysisLatchSr:
    """Measure SR latch set and reset delays and supply current at each supply."""

    identity = measurement_identity(measurements)
    if identity.dut.style == Style.CLOCKED:
        raise ValueError("SR analysis requires a NAND or NOR SR latch")
    # a NAND latch sets and resets on falling (active-low) inputs, a NOR latch on rising ones
    active = "falling" if identity.dut.style == Style.SR_NAND else "rising"
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("SR analysis requires a waveform record")
        tb = measurement.param
        vdd, period = float(tb.vdd), float(tb.data_period_s)
        time_s = wave.time_s
        output = wave.v[LatchNets.q.name][0]
        set_s, _response, set_delay = calc.delay(
            wave.v[LatchNets.s.name][0], output, time_s, vdd / 2, vdd / 2, trigger_edge=active, occurrence=2
        )
        _trigger, _response, reset_delay = calc.delay(
            wave.v[LatchNets.r.name][0],
            output,
            time_s,
            vdd / 2,
            vdd / 2,
            trigger_edge=active,
            response_edge="falling",
            occurrence=2,
        )
        if math.isfinite(set_s) and set_s + period <= float(time_s[-1]):
            current, current_s = calc.clip(wave.i[LatchNets.vdd.name][0], time_s, set_s, set_s + period)
            supply_current_a = calc.average(current, current_s)
        else:
            supply_current_a = math.nan
        rows.append((vdd, period, set_delay, reset_delay, supply_current_a))
    vdd_v, period_s, set_delay_s, reset_delay_s, current = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisLatchSr(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        data_period_s=period_s,
        set_delay_s=set_delay_s,
        reset_delay_s=reset_delay_s,
        supply_current_a=current,
    )
