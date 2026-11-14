"""The latch's analyses: each from runs' measurements (``flow.pipeline.Meas``, their signals on
Spectre's own time axis) of the latch testbench, and the record's metrics.

Timing as a sequential cell characterization takes it: delays at mid-supply, a capturing edge's
data either taken (q moved from the old value to the new one) or kept (q ends at the old one),
setup where the delay has grown by 10 % (the pushout), resolved between the offsets that bracket
it, hold where the old value is still kept (``analyze_timing``, ``analyze_constraint``); the
currents from the supply and from the inputs' drivers; an SR latch's set and reset delays
(``analyze_sr``). On the upset bench, a latch holding a 1 either keeps it after a strike's charge
on its storage node or flips; the critical charge lies between the largest strike it recovers from
and the smallest that flips it (``analyze_upset``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, check_identity, measurement_identity

from .params import CLOCKED_STYLES, Bench, Style
from .subckt import Nets
from .types import AnalysisConstraint, AnalysisSr, AnalysisTiming, AnalysisUpset, Metrics


def _drivers_current(measurement: Meas, start_s: float, stop_s: float) -> float:
    """The average current CMOS drivers of the inputs on V_DD would draw from ``start_s`` to
    ``stop_s``: each input source's signed current integrated over the spans in which its driver's
    pull-up conducts, from the start of each rising ramp (its mid-supply crossing less half the
    transition) to the start of the next falling one (from the run's start where the input starts
    high, to its end where it ends high), summed over the inputs and divided by the time. What the
    source takes back as the input falls, a driver's pull-down sinks to ground; ringing of zero mean
    on the source's current cancels in the signed integral."""
    tb = measurement.param
    vdd, half_ramp = float(tb.vdd), float(tb.transition_time_s) / 2
    time_s, charge_c = measurement.time_s, 0.0
    for net in (Nets.d, Nets.s, Nets.r, Nets.rst, Nets.clk, Nets.clkb):
        level = measurement.v[net.name]
        ons = calc.cross(level, time_s, vdd / 2, edge="rising") - half_ramp
        offs = calc.cross(level, time_s, vdd / 2, edge="falling") - half_ramp
        if level[0] > vdd / 2:
            ons = np.r_[time_s[0], ons]
        if len(offs) < len(ons):
            offs = np.r_[offs, time_s[-1]]
        for on_s, off_s in zip(ons, offs, strict=True):
            low, high = max(float(on_s), start_s), min(float(off_s), stop_s)
            if low < high:
                # [Baker] Eq. (11.14), p. 355: a CMOS driver draws current from V_DD only while its
                # PMOS is on, the charge it puts on its load
                charge_c += calc.integ(*calc.clip(measurement.i[net.name], time_s, low, high))
    return charge_c / (stop_s - start_s)


@analysis
def analyze_timing(measurements: Sequence[Meas]) -> AnalysisTiming:
    """Measure the delays to q, the captured and held events, and the currents at each point."""

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
        # a divider's capturing edges from rst's fall on (from the run's start without reset), and q
        # 0.05 T_CK before the first of them (where an edge before it would be sampled): each edge's
        # old value is the one the edges before it set in turn
        released = float(tb.reset_time_s) + float(tb.transition_time_s) / 2 if dut.reset else 0.0
        toggles = captures[captures > released]
        first = len(toggles) > 0 and bool(calc.value(output, time_s, float(toggles[0]) - 0.05 * period) > vdd / 2)
        rises, falls, captured, held, event_times = [], [], 0, 0, []
        for capture in captures[captures > float(tb.reset_time_s) + period / 2]:
            following = opens[opens > capture + period / 8]
            if not len(following):
                continue
            # q is read just before the next edge that opens its path again
            sample_s = float(following[0]) - 0.05 * period
            if dut.divider:
                # [Razavi-PLL] Fig. 15.3, p. 455: a divide-by-2, two latches in a negative-feedback
                # loop: q toggles at each capturing edge
                launch_s = capture
                # not in the reference texts: q at the previous edge's sample instant, 0.05 T_CK
                # before this one, must show the value that edge set, so that a toggle later than
                # that is late, not this edge's capture; a toggle on the clock's ramp, before its
                # mid-supply crossing, is this edge's
                onset_s = capture - 0.05 * period
                old = first != bool(np.searchsorted(toggles, capture) % 2)
                new = not old
            else:
                nearby = data_edges[np.abs(data_edges - (capture - offset)) < period / 4]
                if not len(nearby):
                    continue
                old = calc.value(data, time_s, capture - offset - period / 4) > vdd / 2
                new = calc.value(data, time_s, capture - offset + period / 4) > vdd / 2
                # a flip-flop launches at its capturing edge, even where d changes after it (inside its
                # aperture); a latch at d's crossing, or at the rising edge before it that opens it
                launch_s = capture if dut.flop else max(float(nearby[0]), float(opens[opens <= capture][-1]))
                onset_s = launch_s
            event_times.append(capture)
            before = calc.value(output, time_s, onset_s) > vdd / 2
            after = calc.value(output, time_s, sample_s) > vdd / 2
            # [Baker] Fig. 10.9, p. 333: t_PLH and t_PHL, between the 50 % points
            # [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay, a flip-flop's or divider's launch at its clock
            # [Baker] Fig. 13.20, p. 399: while the latch is open q follows d, so its launch is d's
            # crossing (the D-to-Q delay, not in the reference texts by that name)
            response = calc.cross(output, time_s, vdd / 2, edge="rising" if new else "falling")
            response = response[(response > onset_s) & (response < sample_s)]
            # not in the reference texts: captured where q moved from the old value to the new one,
            # held where it ends at the value d had before its edge
            if before != new and after == new and len(response):
                captured += 1
                (rises if new else falls).append(float(response[0]) - launch_s)
            elif after == before if dut.divider else after == old:
                held += 1
        if len(event_times) >= 2:
            start_s, stop_s = float(event_times[0]), float(event_times[-1])
            # [Baker] Eq. (11.14), p. 355: the average current, the charge a period over the period
            current, current_s = calc.clip(measurement.i[Nets.vdd.name], time_s, start_s, stop_s)
            idd_a, drivers_a = calc.average(current, current_s), _drivers_current(measurement, start_s, stop_s)
        else:
            idd_a = drivers_a = math.nan
        events = len(event_times)
        rows.append(
            (
                vdd,
                period,
                offset,
                float(np.median(rises)) if rises else math.nan,
                float(np.median(falls)) if falls else math.nan,
                captured / events if events else math.nan,
                held / events if events else math.nan,
                idd_a,
                drivers_a,
            )
        )
    vdd_v, period_s, offset_s, rise, fall, captured_fraction, held_fraction, current, drivers = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisTiming(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        clock_period_s=period_s,
        data_offset_s=offset_s,
        delay_rise_s=rise,
        delay_fall_s=fall,
        captured_fraction=captured_fraction,
        held_fraction=held_fraction,
        idd_a=current,
        idd_drivers_a=drivers,
    )


def _pushout_offset(offsets: np.ndarray, delays: np.ndarray, reference: float, index: int) -> float:
    """The offset between ``offsets[index - 1]`` (failing) and ``offsets[index]`` (passing) at which
    the delay, linear between the two, reaches 1.1 times ``reference``; the passing offset where
    either delay is not finite; -inf where the failing offset's delay is within the bound already
    (the other direction failed there), so that this direction drops out of the caller's max."""
    low, high = float(delays[index - 1]), float(delays[index])
    bound = 1.1 * reference
    if not (math.isfinite(low) and math.isfinite(high)):
        return float(offsets[index])
    if low <= bound:
        return -math.inf
    return float(offsets[index] - (offsets[index] - offsets[index - 1]) * (bound - high) / (low - high))


@analysis
def analyze_constraint(measurements: Sequence[Meas], *, timing: AnalysisTiming) -> AnalysisConstraint:
    """Find setup (a 10 % delay pushout) and hold from a data offset sweep at one supply and period."""

    identity = measurement_identity(measurements)
    check_identity(timing, identity, name="timing")
    if len(set(timing.vdd_v)) != 1 or len(set(timing.clock_period_s)) != 1 or len(set(timing.data_offset_s)) < 3:
        raise ValueError("setup and hold require a data offset sweep at one supply and clock period")
    order = np.argsort(timing.data_offset_s)
    offsets = timing.data_offset_s[order]
    rise, fall = timing.delay_rise_s[order], timing.delay_fall_s[order]
    captures = timing.captured_fraction[order] == 1.0
    # [Baker] Fig. 13.25, p. 401: D FF setup time
    # not in the reference texts: setup taken where the delay to q has grown by 10 % over its value
    # with the data early (the pushout criterion of standard-cell timing characterization)
    passing = captures & (rise <= 1.1 * rise[-1]) & (fall <= 1.1 * fall[-1])
    # [Baker] Fig. 13.26, p. 402: D FF hold time
    # [Baker] Sec. 13.3, p. 401: a negative hold time, d removed before the clock edge
    holding = timing.held_fraction[order] == 1.0
    # the contiguous runs from the largest offset down, and from the most negative one up
    failing_setup = np.flatnonzero(~passing)
    setup_s = math.nan
    if len(failing_setup) and failing_setup[-1] + 1 < len(offsets):
        index = int(failing_setup[-1]) + 1
        setup_s = float(offsets[index])
        if captures[index - 1]:
            # the failing offset captured with its delay pushed out: the 1.1x crossing between the two
            crossings = (_pushout_offset(offsets, delays, float(delays[-1]), index) for delays in (rise, fall))
            setup_s = max(float(offsets[index - 1]), max(crossings))
            setup_s = min(setup_s, float(offsets[index]))
    failing_hold = np.flatnonzero(~holding)
    hold_s = math.nan
    if len(failing_hold) and failing_hold[0] > 0:
        hold_s = 0.0 - float(offsets[failing_hold[0] - 1])
    return AnalysisConstraint(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=float(timing.vdd_v[0]),
        clock_period_s=float(timing.clock_period_s[0]),
        delay_rise_s=float(rise[-1]),
        delay_fall_s=float(fall[-1]),
        setup_s=setup_s,
        hold_s=hold_s,
    )


@analysis
def analyze_sr(measurements: Sequence[Meas]) -> AnalysisSr:
    """Measure SR latch set and reset delays and the currents at each supply."""

    identity = measurement_identity(measurements)
    if identity.dut.style in CLOCKED_STYLES:
        raise ValueError("SR analysis requires a NAND or NOR SR latch")
    # [Baker] Fig. 13.13, p. 395: a NAND latch's inputs are active low
    # [Baker] Fig. 13.14, p. 396: a NOR latch's inputs are active high
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
        # q answers within the active pulse, a quarter period, or the set or reset did not move it
        delay_rise, delay_fall = (delay if delay <= period / 4 else math.nan for delay in (delay_rise, delay_fall))
        if math.isfinite(set_s) and set_s + period <= float(time_s[-1]):
            # [Baker] Eq. (11.14), p. 355: the average current, the charge a period over the period
            current, current_s = calc.clip(measurement.i[Nets.vdd.name], time_s, set_s, set_s + period)
            idd_a, drivers_a = calc.average(current, current_s), _drivers_current(measurement, set_s, set_s + period)
        else:
            idd_a = drivers_a = math.nan
        rows.append((vdd, period, delay_rise, delay_fall, idd_a, drivers_a))
    vdd_v, period_s, delay_rise_s, delay_fall_s, current, drivers = (
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
        idd_drivers_a=drivers,
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
        # not in the reference texts: a flip where q, holding a 1, ends below mid-supply; q's dip,
        # its held level minus its lowest after the strike; neither where q held no 1
        wrote = held > vdd / 2
        rows.append(
            (
                float(tb.charge_c),
                float(final < vdd / 2) if wrote else math.nan,
                held - calc.ymin(calc.clip(output, time_s, strike_s, end_s)[0]) if wrote else math.nan,
            )
        )
    charge, upset, dip = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    loads = {float(item.param.cload_f) for item in measurements}
    if len(loads) != 1:
        raise ValueError("latch upset requires one load on q and qb")
    return AnalysisUpset(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        cload_f=loads.pop(),
        charge_c=charge,
        upset_fraction=upset,
        dip_v=dip,
    )


def metrics(
    *,
    supply: AnalysisTiming | AnalysisSr,
    constraint: AnalysisConstraint | None = None,
    period: AnalysisTiming | None = None,
    slow: AnalysisTiming | None = None,
    upset: AnalysisUpset | None = None,
) -> Metrics:
    """The record's numbers: from the supply's runs (``supply``, in any order: a clocked design's
    timing or an SR latch's delays) the delays to q rising and falling and the energy per cycle at
    the nominal supply (the run whose supply is the sweep's median), and the slowest delay over the
    supply; a latch's or
    flip-flop's setup and hold (``constraint``); from a flip-flop's or divider's runs over the clock
    period (``period``) the highest frequency up to which every edge captures, and from its run at a
    slow clock (``slow``) the share of edges captured there; a struck latch's critical charge and
    the smallest strike that flips it (``upset``). NaN where a design has no such run."""

    # the supply sweep is symmetric about nominal (SUPPLY_SWEEP): nominal is its median
    at_nominal = np.flatnonzero(np.isclose(supply.vdd_v / np.median(supply.vdd_v), 1.0))
    if not len(at_nominal):
        raise ValueError("latch metrics require a run at the nominal supply, the sweep's median")
    nominal = int(at_nominal[0])
    delays = np.asarray([supply.delay_rise_s, supply.delay_fall_s])
    return Metrics(
        delay_rise_s=float(supply.delay_rise_s[nominal]),
        delay_fall_s=float(supply.delay_fall_s[nominal]),
        energy_per_cycle_j=float(supply.energy_per_cycle_j[nominal]),
        # not in the reference texts: the worst of the rising and falling delays over the supply
        delay_max_supply_s=float(np.nanmax(delays)) if np.any(np.isfinite(delays)) else math.nan,
        setup_s=constraint.setup_s if constraint is not None else math.nan,
        hold_s=constraint.hold_s if constraint is not None else math.nan,
        # [Razavi-PLL] Sec. 15.1, p. 453: maximum allowable input frequency, f_max
        fmax_hz=period.fmax_hz if period is not None else math.nan,
        # [Razavi-PLL] Sec. 15.2.2, p. 459: a dynamic latch's stored charge leaks away, so it fails below
        # some clock frequency
        captured_1mhz_fraction=float(slow.captured_fraction[0]) if slow is not None else math.nan,
        critical_charge_c=upset.critical_charge_c if upset is not None else math.nan,
        flip_charge_c=upset.flip_charge_c if upset is not None else math.nan,
    )
