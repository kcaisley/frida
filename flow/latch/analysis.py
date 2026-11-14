"""The latch's analyses: each from runs' measurements (``flow.pipeline.Meas``, their signals on
Spectre's own time axis) of the latch testbench, and the record's metrics.

Timing as a sequential cell characterization takes it: delays at mid-supply, a capturing edge's
data either taken (the new value) or not (the old one), setup where the delay has grown by 10 %
(the pushout), hold where the old value is still held (``analyze_timing``,
``analyze_constraint``); an SR latch's set and reset delays (``analyze_sr``). On the upset bench, a
latch holding a 1 either keeps it after a strike's charge on its storage node or flips; the
smallest charge that flips it is its critical charge (``analyze_upset``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, check_identity, measurement_identity

from .params import CLOCKED_STYLES, SUPPLY_SWEEP, Bench, Style
from .subckt import Nets
from .types import AnalysisConstraint, AnalysisSr, AnalysisTiming, AnalysisUpset, Metrics


@analysis
def analyze_timing(measurements: Sequence[Meas]) -> AnalysisTiming:
    """Measure clock-to-q delays, captured and held events, and supply current at each point."""

    identity = measurement_identity(measurements)
    dut = identity.dut
    if dut.style not in CLOCKED_STYLES:
        raise ValueError("latch timing requires a clocked latch, flip-flop, or divider")
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vdd, period, offset = float(tb.vdd), float(tb.clock_period_s), float(tb.data_offset_s)
        time_s = measurement.time_s
        clock, data, output = (measurement.v[net.name] for net in (Nets.clk, Nets.d, Nets.q))
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
            # [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay
            response = calc.cross(output, time_s, vdd / 2, edge="rising" if new else "falling")
            response = response[(response > launch_s) & (response < sample_s)]
            if len(response):
                (rises if new else falls).append(float(response[0]) - launch_s)
        if len(event_times) >= 2:
            current, current_s = calc.clip(
                measurement.i[Nets.vdd.name], time_s, float(event_times[0]), float(event_times[-1])
            )
            idd_a = calc.average(current, current_s)
        else:
            idd_a = math.nan
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
                idd_a,
            )
        )
    vdd_v, period_s, offset_s, rise, fall, captured_fraction, held_fraction, current = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisTiming(
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
        idd_a=current,
    )


@analysis
def analyze_constraint(measurements: Sequence[Meas], *, timing: AnalysisTiming) -> AnalysisConstraint:
    """Find setup (a 10 % delay pushout) and hold from a data offset sweep at one supply and period."""

    identity = measurement_identity(measurements)
    check_identity(timing, identity, name="timing")
    if len(set(timing.vdd_v)) != 1 or len(set(timing.clock_period_s)) != 1 or len(set(timing.data_offset_s)) < 3:
        raise ValueError("setup and hold require a data offset sweep at one supply and clock period")
    order = np.argsort(timing.data_offset_s)
    offsets = timing.data_offset_s[order]
    rise, fall = timing.clock_to_q_rise_s[order], timing.clock_to_q_fall_s[order]
    # [Baker] Fig. 13.25, p. 401: D FF setup time
    # not in the reference texts: setup taken where the delay to q has grown by 10 % over its value
    # with the data early (the pushout criterion of standard-cell timing characterization)
    passing = (timing.captured_fraction[order] == 1.0) & (rise <= 1.1 * rise[-1]) & (fall <= 1.1 * fall[-1])
    # [Baker] Fig. 13.26, p. 402: D FF hold time
    holding = timing.held_fraction[order] == 1.0
    # the contiguous runs from the largest offset down, and from the most negative one up
    failing_setup = np.flatnonzero(~passing)
    setup_index = failing_setup[-1] + 1 if len(failing_setup) else 0
    failing_hold = np.flatnonzero(~holding)
    hold_index = failing_hold[0] - 1 if len(failing_hold) else len(offsets) - 1
    return AnalysisConstraint(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=float(timing.vdd_v[0]),
        clock_period_s=float(timing.clock_period_s[0]),
        clock_to_q_rise_s=float(rise[-1]),
        clock_to_q_fall_s=float(fall[-1]),
        setup_s=float(offsets[setup_index]) if setup_index < len(offsets) else math.nan,
        hold_s=-float(offsets[hold_index]) if hold_index >= 0 else math.nan,
    )


@analysis
def analyze_sr(measurements: Sequence[Meas]) -> AnalysisSr:
    """Measure SR latch set and reset delays and supply current at each supply."""

    identity = measurement_identity(measurements)
    if identity.dut.style in CLOCKED_STYLES:
        raise ValueError("SR analysis requires a NAND or NOR SR latch")
    # a NAND latch sets and resets on falling (active-low) inputs, a NOR latch on rising ones
    active = "falling" if identity.dut.style is Style.SR_NAND else "rising"
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vdd, period = float(tb.vdd), float(tb.data_period_s)
        time_s = measurement.time_s
        output = measurement.v[Nets.q.name]
        # [Baker] Fig. 10.9, p. 333: propagation delays, to the output rising and falling
        set_s, _response, delay_rise = calc.delay(
            measurement.v[Nets.s.name], output, time_s, vdd / 2, vdd / 2, trigger_edge=active, occurrence=2
        )
        _trigger, _response, delay_fall = calc.delay(
            measurement.v[Nets.r.name],
            output,
            time_s,
            vdd / 2,
            vdd / 2,
            trigger_edge=active,
            response_edge="falling",
            occurrence=2,
        )
        if math.isfinite(set_s) and set_s + period <= float(time_s[-1]):
            current, current_s = calc.clip(measurement.i[Nets.vdd.name], time_s, set_s, set_s + period)
            idd_a = calc.average(current, current_s)
        else:
            idd_a = math.nan
        rows.append((vdd, period, delay_rise, delay_fall, idd_a))
    vdd_v, period_s, delay_rise_s, delay_fall_s, current = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisSr(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        data_period_s=period_s,
        delay_rise_s=delay_rise_s,
        delay_fall_s=delay_fall_s,
        idd_a=current,
    )


@analysis
def analyze_upset(measurements: Sequence[Meas]) -> AnalysisUpset:
    """Measure whether a strike flips the held 1 and how far q dips, at each charge."""

    identity = measurement_identity(measurements)
    if not all(item.param.bench is Bench.UPSET for item in measurements):
        raise ValueError("latch upset requires the upset bench")
    rows = []
    for measurement in sorted(measurements, key=lambda item: float(item.param.charge_c)):
        tb = measurement.param
        time_s, output, vdd = measurement.time_s, measurement.v[Nets.q.name], float(tb.vdd)
        strike_s, end_s = float(tb.upset_time_s), float(time_s[-1])
        held = calc.value(output, time_s, strike_s - 0.1e-9)
        # q at the end, a strike time after the strike: recovered, or flipped
        final = calc.average(*calc.clip(output, time_s, end_s - 0.1e-9, end_s))
        rows.append(
            (
                float(tb.charge_c),
                float(held > vdd / 2 > final),
                held - calc.ymin(calc.clip(output, time_s, strike_s, end_s)[0]),
            )
        )
    charge, upset, dip = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    return AnalysisUpset(
        group=identity.group, index=identity.index, dut=identity.dut, charge_c=charge, upset_fraction=upset, dip_v=dip
    )


def metrics(
    *,
    supply: AnalysisTiming | AnalysisSr,
    constraint: AnalysisConstraint | None = None,
    period: AnalysisTiming | None = None,
    upset: AnalysisUpset | None = None,
) -> Metrics:
    """The record's numbers: from the supply's runs (``supply``, in ``SUPPLY_SWEEP``'s order: a
    clocked design's timing or an SR latch's delays) the delays to q rising and falling and the
    energy per cycle at the nominal supply, and the slowest delay over the supply; a latch's or
    flip-flop's setup and hold (``constraint``); from a flip-flop's or divider's runs over the clock
    period (``period``) the highest frequency at which every edge captures; a struck latch's
    critical charge (``upset``). NaN where a design has no such run."""

    nominal = SUPPLY_SWEEP.index(1.0)
    rise, fall = (
        (supply.clock_to_q_rise_s, supply.clock_to_q_fall_s)
        if isinstance(supply, AnalysisTiming)
        else (supply.delay_rise_s, supply.delay_fall_s)
    )
    fmax_hz = math.nan
    if period is not None:
        # [Razavi-PLL] Sec. 15.1, p. 453: maximum allowable input frequency, f_max
        frequency = 1 / period.clock_period_s
        working = frequency[period.captured_fraction == 1.0]
        fmax_hz = float(np.max(working)) if len(working) else math.nan
    return Metrics(
        delay_rise_s=float(rise[nominal]),
        delay_fall_s=float(fall[nominal]),
        energy_per_cycle_j=float(supply.energy_per_cycle_j[nominal]),
        delay_max_supply_s=float(np.nanmax([rise, fall])),
        setup_s=constraint.setup_s if constraint is not None else math.nan,
        hold_s=constraint.hold_s if constraint is not None else math.nan,
        fmax_hz=fmax_hz,
        critical_charge_c=upset.critical_charge_c if upset is not None else math.nan,
    )
