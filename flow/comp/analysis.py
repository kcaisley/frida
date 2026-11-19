"""The comparator's analyses: from its testbench's measurements (``flow.pipeline.Meas``: every
saved signal on the simulator's own time axis, the run's ``TbParams``) and from bench captures, to
the numbers its characterization reports (``metrics``).

A simulation's trials are read from the testbench's schedule (``TbParams``: each decision's cycle
and input) by ``analyze_decisions``; a lab capture is its trials already. The offset, noise,
common-mode and S-curve analyses take those trials, for both. Waveforms are read by the
testbench's net names (``clk``, ``latch_p``, ``latch_n``, ``outp``, ``outn``, ``inp``, ``inn``;
supply current ``vdd``), each trial's on the raw time points of its own cycle: nothing is resampled.

The comparator inside a converter is read from the converter's captures, each as the comparator
sees it (``AnalysisConversions``: ``adc.analyze_conversions``), each decision at its clock's rise:
the bench's scope records of COMP and COMP_OUT (``analyze_scope_edges``), and a simulation's saved
internal nets (``analyze_edge_eye``, ``analyze_response``: ``clk_comp``, ``comp_out_p``,
``comp.latch_p``, ``comp.latch_n``, ``seq_init``). Their maps sample each record at the centre of
each time cell (``_share``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import log_ndtr
from scipy.stats import norm
from scipy.stats import t as student_t

from flow.analysis import calc
from flow.circuit import oppoint
from flow.pipeline import Meas, analysis, check_identity, measurement_identity

from .params import CHARGE_METER, CHARGE_METER_F, LARGE_V, SMALL_V, Validity
from .subckt import netlist
from .types import (
    AnalysisClockCheck,
    AnalysisCommonMode,
    AnalysisConversions,
    AnalysisDecisions,
    AnalysisDelay,
    AnalysisEdgeEye,
    AnalysisKickback,
    AnalysisMetastability,
    AnalysisOffsetNoise,
    AnalysisPower,
    AnalysisResponse,
    AnalysisSamplingNoise,
    AnalysisScopeEdges,
    AnalysisScurve,
    AnalysisStress,
    AnalysisTiming,
    Metrics,
)


@analysis
def analyze_decisions(meas: Meas) -> AnalysisDecisions:
    """Each trial of a simulation: its input from the testbench's schedule, its decision (the
    positive output above the negative) and whether the latch had decided (its nodes more than half
    the supply apart), both read just before the trial's evaluation ends."""

    tb = meas.param
    at_s = tb.decision_time_s
    # [Razavi-ADC] Sec. 5.8.5, p. 98: the RS latch holds the decision through the precharge
    out_p, out_n = (calc.value(meas.v[name], meas.time_s, at_s) for name in ("outp", "outn"))
    # The output stage holds the last decision while the regenerative latch is still undecided, so
    # a trial is resolved only where the latch's own nodes are half the supply apart by then.
    # [Razavi-ADC] Sec. 6.2.1, p. 109: a metastable state, the output short of its final value in
    # the time allowed (the book's 90 %; here the latch half the supply apart)
    resolved = None
    if "latch_p" in meas.v and "latch_n" in meas.v:
        latch = calc.value(meas.v["latch_p"], meas.time_s, at_s) - calc.value(meas.v["latch_n"], meas.time_s, at_s)
        resolved = np.abs(latch) > float(tb.vdd) / 2
    points = np.asarray(tb.points, dtype=np.float64)
    return AnalysisDecisions(
        group=meas.group,
        index=meas.index,
        dut=meas.dut,
        info=meas.info,
        param=tb,
        trial_index=np.arange(len(at_s), dtype=np.int64),
        vin_diff_v=points[tb.trial_point, 1],
        vin_cm_v=points[tb.trial_point, 0],
        decision=(out_p > out_n).astype(np.uint8),
        resolved=resolved,
    )


@analysis
def analyze_timing(meas: Meas, *, decisions: AnalysisDecisions) -> AnalysisTiming:
    """Each trial's clock-to-decision delay, to the latch's half swing and to the held outputs'
    crossing, and its settling, on the raw points of its own cycle.

    A trial is unresolved where its latch is still within 0.1 V of balance at the cycle's end, or
    where it was read undecided (``decisions.resolved``); an unresolved trial is timed nowhere
    downstream. The outputs' delay is NaN where they end the cycle as they were at the clock's rise
    (the decision of the trial before held).
    """

    identity = measurement_identity([meas])
    check_identity(decisions, identity, name="comparator decisions")
    tb = meas.param
    clock_to_decision, clock_to_output, settling, unresolved = [], [], [], []
    # each cycle up to the next one's start as the schedule computes it (the start plus a cycle may
    # round past it, and take in the next cycle's first point)
    ends_s = np.r_[tb.trial_start_s[1:], tb.stop_s]
    for trial, (start_s, end_s) in enumerate(zip(tb.trial_start_s, ends_s, strict=True)):
        window = slice(*np.searchsorted(meas.time_s, (start_s, end_s), side="left"))
        time_s = meas.time_s[window]
        clock = meas.v["clk"][window]
        # Settling is a property of the dynamic comparator core: the held output latch keeps the
        # previous decision through reset, so the outputs would often look resolved before the clock.
        difference = meas.v["latch_p"][window] - meas.v["latch_n"][window]
        response = np.abs(difference)
        # [Razavi-ADC] Sec. 7.3, p. 131: the comparator's speed, from the clock's rise at V_DD/2
        # until |V_X - V_Y| reaches a set level; both signals timed at the midpoint of their own swing
        trigger_s, _response_s, delay_s = calc.delay(
            clock,
            response,
            time_s,
            float((calc.ymin(clock) + calc.ymax(clock)) / 2.0),
            float(calc.ymax(response) / 2.0),
        )
        # a latch still within 0.1 V of balance at the cycle's end has not resolved
        is_unresolved = abs(difference[-1]) < 0.1 or (decisions.resolved is not None and not decisions.resolved[trial])
        settling_s = math.nan
        if math.isfinite(trigger_s) and not is_unresolved:
            evaluation_v, evaluation_s = calc.clip(difference, time_s, trigger_s, float(time_s[-1]))
            # [Razavi-ADC] Sec. 8.2.2, p. 150: settling time, the output inside an error band about
            # its final value (here 1 % of the final latch step)
            settled_at_s = calc.settlingTime(evaluation_v, evaluation_s, percent_of_step=1.0)
            settling_s = settled_at_s - trigger_s if math.isfinite(settled_at_s) else math.nan
        clock_to_decision.append(delay_s)
        clock_to_output.append(_output_delay(meas.v["outp"][window] - meas.v["outn"][window], time_s, trigger_s))
        settling.append(settling_s)
        unresolved.append(is_unresolved)
    return AnalysisTiming(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        trial_index=decisions.trial_index,
        clock_to_decision_s=np.asarray(clock_to_decision, dtype=np.float64),
        clock_to_output_s=np.asarray(clock_to_output, dtype=np.float64),
        settling_s=np.asarray(settling, dtype=np.float64),
        unresolved=np.asarray(unresolved, dtype=np.bool_),
    )


def _output_delay(output_v: np.ndarray, time_s: np.ndarray, trigger_s: float) -> float:
    """The time from ``trigger_s`` to the differential output's (``output_v``, on ``time_s``) last
    zero crossing after it, where the output ends on the other side of zero than at the trigger;
    NaN where it does not (the output held) or there is no trigger."""
    # [Razavi-ADC] Sec. 7.5, p. 134: the RS latch's delay, critical in some converters; [Baker]
    # Fig. 10.9, p. 333: a propagation delay, to the output's 50 % point (both outputs cross at
    # once where the differential output crosses zero)
    if not math.isfinite(trigger_s):
        return math.nan
    after, after_s = calc.clip(output_v, time_s, trigger_s, float(time_s[-1]))
    if len(after) < 2 or (after[0] > 0) == (after[-1] > 0):
        return math.nan
    crossings = calc.cross(after, after_s, 0.0, edge="either")
    return float(crossings[-1] - trigger_s) if len(crossings) else math.nan


@analysis
def analyze_delay(meas: Meas, *, decisions: AnalysisDecisions, timing: AnalysisTiming) -> AnalysisDelay:
    """The clock-to-decision delay at every input point, of its resolved trials that decided as the
    input's sign asks (a zero input's any): their median and their slowest, to the latch and to the
    held outputs (those that changed them); and how many resolved trials decided against the sign."""

    identity = measurement_identity([meas])
    check_identity([decisions, timing], identity, name="comparator decisions and timing")
    vin_cm_v, vin_diff_v = np.unique(decisions.vin_cm_v), np.unique(decisions.vin_diff_v)
    shape = (len(vin_cm_v), len(vin_diff_v))
    delay_s, slowest_s, output_s, output_slowest_s = (np.full(shape, np.nan) for _ in range(4))
    against = np.zeros(shape, dtype=np.int64)
    # a decision follows its input's sign: high for a positive input, low for a negative one
    follows = (decisions.vin_diff_v == 0) | ((np.asarray(decisions.decision) == 1) == (decisions.vin_diff_v > 0))
    for row, cm_v in enumerate(vin_cm_v):
        for column, diff_v in enumerate(vin_diff_v):
            at = np.isclose(decisions.vin_cm_v, cm_v) & np.isclose(decisions.vin_diff_v, diff_v) & ~timing.unresolved
            against[row, column] = int(np.count_nonzero(at & ~follows))
            # not in the reference texts: a point's delay the median of its resolved trials (each
            # a decision of [Razavi-ADC] Sec. 7.3, p. 131), its slowest their largest
            for times_s, median, slowest in (
                (timing.clock_to_decision_s, delay_s, slowest_s),
                (timing.clock_to_output_s, output_s, output_slowest_s),
            ):
                selected = times_s[at & follows]
                selected = selected[np.isfinite(selected)]
                if len(selected):
                    median[row, column] = float(np.median(selected))
                    slowest[row, column] = float(calc.ymax(selected))
    return AnalysisDelay(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=vin_cm_v,
        vin_diff_v=vin_diff_v,
        delay_s=delay_s,
        slowest_s=slowest_s,
        output_delay_s=output_s,
        output_slowest_s=output_slowest_s,
        against_sign=against,
    )


@analysis
def analyze_metastability(
    meas: Meas,
    *,
    delay: AnalysisDelay,
    decisions: AnalysisDecisions | None = None,
    timing: AnalysisTiming | None = None,
) -> AnalysisMetastability:
    """The delay at each positive input of the first common mode, to the latch and to the held
    outputs; the systematic offset and the regeneration time constant, fitted together to the
    resolved decisions (``decisions`` and ``timing``: each one but the run's first, which starts
    from the operating point; without them, the points' delays that followed their sign): the
    delay t_0 + tau ln(1 / |V - V_OS|) over the decisions within 3 mV of the offset (at least the
    three nearest), the offset between the largest input decided low and the smallest decided high
    (``_regeneration``); and the delays over the input less that offset, |V - V_OS| ascending, to
    the latch and to the held outputs (NaN where no decision there changed them); NaN with
    decisions of one value alone."""

    identity = measurement_identity([meas])
    check_identity(
        [delay, *(item for item in (decisions, timing) if item is not None)], identity, name="comparator delay"
    )
    positive = delay.vin_diff_v > 0
    input_v, delay_s = delay.vin_diff_v[positive], delay.delay_s[0][positive]
    output_s = None if delay.output_delay_s is None else delay.output_delay_s[0][positive]
    if decisions is not None and timing is not None:
        use = (
            np.isclose(decisions.vin_cm_v, delay.vin_cm_v[0])
            & ~timing.unresolved
            & np.isfinite(timing.clock_to_decision_s)
            & (decisions.trial_index > 0)
        )
        trial_v, high = decisions.vin_diff_v[use], np.asarray(decisions.decision)[use] == 1
        latch_s, toggled_s = timing.clock_to_decision_s[use], timing.clock_to_output_s[use]
    else:
        timed = np.isfinite(delay.delay_s[0]) & (delay.vin_diff_v != 0)
        trial_v, high = delay.vin_diff_v[timed], delay.vin_diff_v[timed] > 0
        latch_s = delay.delay_s[0][timed]
        toggled_s = np.full(len(trial_v), np.nan) if delay.output_delay_s is None else delay.output_delay_s[0][timed]
    tau_s, offset_v = _regeneration(trial_v, high, latch_s)
    effective_v = effective_s = effective_output_s = None
    if math.isfinite(offset_v):
        inputs_v = np.unique(trial_v)
        # each input's decisions: the median of their delays (of those that changed the outputs)
        at = [trial_v == value for value in inputs_v]
        latch = np.asarray([_median(latch_s[mask]) for mask in at])
        toggled = np.asarray([_median(toggled_s[mask]) for mask in at])
        order = np.argsort(np.abs(inputs_v - offset_v), kind="stable")
        effective_v, effective_s, effective_output_s = np.abs(inputs_v - offset_v)[order], latch[order], toggled[order]
    return AnalysisMetastability(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        input_v=input_v,
        delay_s=delay_s,
        regeneration_tau_s=tau_s,
        output_delay_s=output_s,
        offset_v=offset_v,
        effective_v=effective_v,
        effective_delay_s=effective_s,
        effective_output_s=effective_output_s,
        against_sign=None if delay.against_sign is None else int(delay.against_sign[0].sum()),
    )


def _regeneration(inputs_v: np.ndarray, high: np.ndarray, delay_s: np.ndarray) -> tuple[float, float]:
    """The regeneration time constant and the systematic offset of decisions at ``inputs_v``
    (``high`` where one decided high) taking ``delay_s``: the offset V_OS and t_0, tau of least
    squares of t_0 - tau ln|V - V_OS| over the decisions within 3 mV of V_OS (at least the three
    nearest; chosen again at each new V_OS until they stay), V_OS searched between the largest
    input decided low and the smallest decided high (where they overlap, between the two); NaN
    with decisions of one value alone or fewer than three."""
    # [Razavi-ADC] Sec. 5.1, p. 71: the offset, the input at which the comparator balances, so the
    # latch's initial imbalance is proportional to V - V_OS; Eq. (7.6), p. 136: an imbalance alpha
    # times smaller delays the regeneration by tau_reg ln(alpha); not in the reference texts: the
    # least-squares fit of both
    if not np.any(high) or np.all(high) or len(inputs_v) < 3:
        return math.nan, math.nan
    low_v, high_v = float(calc.ymax(inputs_v[~high])), float(calc.ymin(inputs_v[high]))
    bounds = (min(low_v, high_v), max(low_v, high_v))

    offset_v, near = (bounds[0] + bounds[1]) / 2, None
    for _ in range(10):
        distance = np.abs(inputs_v - offset_v)
        chosen = distance <= max(3e-3, float(np.sort(distance)[2]))
        if near is not None and np.array_equal(chosen, near):
            break
        near = chosen
        if len(np.unique(np.round(distance[near], 12))) < 2:
            return math.nan, math.nan
        # the least residual on a grid inside the bounds, then refined between its neighbours
        step = (bounds[1] - bounds[0]) / 400
        grid = bounds[0] + step * (np.arange(400) + 0.5)
        best = float(grid[int(np.argmin([_squares(inputs_v, delay_s, float(v), near)[0] for v in grid]))])
        found = minimize_scalar(
            _residual,
            bounds=(max(bounds[0], best - step), min(bounds[1], best + step)),
            method="bounded",
            args=(inputs_v, delay_s, near),
            options={"xatol": step * 1e-7},
        )
        offset_v = float(found.x)
    assert near is not None
    return _squares(inputs_v, delay_s, offset_v, near)[1], offset_v


def _squares(inputs_v: np.ndarray, delay_s: np.ndarray, offset_v: float, near: np.ndarray) -> tuple[float, float]:
    """The residual sum of squares of the line t_0 - tau ln|V - offset_v| through the ``near``
    decisions' delays, and its tau."""
    log_v = np.log(np.abs(inputs_v[near] - offset_v))
    design = np.stack([np.ones_like(log_v), log_v], axis=1)
    coefficients, *_ = np.linalg.lstsq(design, delay_s[near], rcond=None)
    return float(np.sum((design @ coefficients - delay_s[near]) ** 2)), -float(coefficients[1])


def _residual(offset_v: float, inputs_v: np.ndarray, delay_s: np.ndarray, near: np.ndarray) -> float:
    """``_squares``' residual at ``offset_v``, the argument a scalar search varies first."""
    return _squares(inputs_v, delay_s, float(offset_v), near)[0]


@analysis
def analyze_clock_check(
    meas: Sequence[Meas],
    *,
    decisions: Sequence[AnalysisDecisions],
    metastability: Sequence[AnalysisMetastability],
) -> AnalysisClockCheck:
    """Whether the comparator decides within the clock of the first run: its noise-free decisions
    over the input (each input after its negative), against the same at the second run's longer
    clock (``decisions`` and ``metastability`` of each, in order)."""

    identity = measurement_identity(meas)
    check_identity([*decisions, *metastability], identity, name="comparator decisions and metastability")
    (at, longer), (at_delay, longer_delay) = decisions, metastability
    evaluation_s = float(meas[0].param.evaluation_time_s)
    unresolved = 0 if at.resolved is None else int(np.count_nonzero(~at.resolved))
    # the decisions from 0.3 mV up (the first starts from the operating point, and a systematic
    # offset of 0.1 mV leaves either at the latch's threshold)
    match = bool(np.array_equal(at.decision[2:], longer.decision[2:]))
    with np.errstate(invalid="ignore", divide="ignore"):
        change = np.abs(at_delay.delay_s / longer_delay.delay_s - 1)
    delay_change = float(np.nanmax(change)) if np.any(np.isfinite(change)) else math.nan
    # 10 uV from the offset, the delay nearest the offset extrapolated by the regeneration time
    # constant: a fifth of the quietest noise the grid asks for
    # [Razavi-ADC] Eq. (7.7), p. 136: the delay at an input 10^n smaller, n tau_reg ln 10 later
    nearest_v, nearest_s = math.nan, math.nan
    if at_delay.effective_v is not None and at_delay.effective_delay_s is not None:
        timed = np.flatnonzero(np.isfinite(at_delay.effective_delay_s) & (at_delay.effective_v > 0))
        if len(timed):
            nearest_v, nearest_s = float(at_delay.effective_v[timed[0]]), float(at_delay.effective_delay_s[timed[0]])
    resolved_10uv_s = float(nearest_s + at_delay.regeneration_tau_s * math.log(nearest_v / 10e-6))
    # not in the reference texts: every decision resolved, the same decisions and the delays within
    # 10 % at twice the clock, and 10 uV within the evaluation (the verdict's tests)
    reasons = []
    if unresolved:
        reasons.append(f"{unresolved} of its {len(at.decision)} decisions unresolved")
    if not match:
        reasons.append("decisions other than at the longer clock")
    # neither the reset nor the evaluation may shape a delay by more than 10 % (of the inputs both
    # clocks timed: a decision against its input's sign has no delay)
    if not np.all(change[np.isfinite(change)] <= 0.10):
        reasons.append(f"delays up to {delay_change:.0%} off the longer clock's")
    if not resolved_10uv_s <= evaluation_s:
        reasons.append(f"10 uV decided after {resolved_10uv_s * 1e9:.1f} ns")
    return AnalysisClockCheck(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        evaluation_s=evaluation_s,
        unresolved_count=unresolved,
        decisions_match=match,
        delay_change=delay_change,
        resolved_10uv_s=resolved_10uv_s,
        decides_in_time=not reasons,
        reasons=tuple(reasons),
    )


@analysis
def analyze_kickback(meas: Meas) -> AnalysisKickback:
    """The inputs' largest excursion over the first decision's cycle from their values at its
    start; and the difference's error as each later decision's clock edges begin (the comparator's
    own clk leaving 1 % of the supply as it rises, its clkb 99 % as it falls, whichever first:
    behind its drivers, and before the edges kick the inputs themselves) against its programmed
    input, the largest (what the decisions before leave for it; NaN in a run of one decision)."""

    # [Razavi-ADC] Sec. 5.7.4, p. 88: kickback noise, the input currents a comparator's switching
    # draws and the error voltage they leave at its input; Sec. 7.8, p. 137: its common-mode and
    # differential components, and when it happens deciding whether it does harm
    identity = measurement_identity([meas])
    tb = meas.param
    window = slice(*np.searchsorted(meas.time_s, (0.0, tb.cycle_s), side="left"))
    inp, inn = meas.v["inp"][window], meas.v["inn"][window]
    residual_v = math.nan
    if len(tb.trial_point) > 1:
        starts_s = tb.trial_start_s[1:]
        # each later decision's first edge of each clock after its cycle began, the earlier of them
        edges = [calc.cross(meas.v["clk"], meas.time_s, 0.01 * float(tb.vdd), edge="rising")]
        if "clkb" in meas.v:
            edges.append(calc.cross(meas.v["clkb"], meas.time_s, 0.99 * float(tb.vdd), edge="falling"))
        firsts = [np.r_[found, np.inf][np.searchsorted(found, starts_s)] for found in edges]
        rise_s = np.minimum.reduce(firsts)
        read = np.isfinite(rise_s)
        rise_s = rise_s[read]
        programmed_v = np.asarray(tb.points, dtype=np.float64)[tb.trial_point[1:][read], 1]
        read_v = calc.value(meas.v["inp"] - meas.v["inn"], meas.time_s, rise_s) - programmed_v
        residual_v = float(calc.ymax(np.abs(read_v))) if len(read_v) else math.nan
    return AnalysisKickback(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        kickback_v=float(max(calc.ymax(np.abs(inp - inp[0])), calc.ymax(np.abs(inn - inn[0])))),
        kickback_diff_v=float(calc.ymax(np.abs((inp - inn) - (inp[0] - inn[0])))),
        residual_diff_v=residual_v,
    )


@analysis
def analyze_power(meas: Sequence[Meas], *, decisions: Sequence[AnalysisDecisions] | None = None) -> AnalysisPower:
    """Each run's energy per decision: the supply's charge over each decision's cycle, read off the
    testbench's charge meter (``params.CHARGE_METER``: integrated by the simulator, exact at any
    output step) at the cycle's ends, at the supply's voltage, averaged over the settled decisions,
    those that follow one of the same magnitude: at the same input (the held outputs unchanged), or
    at its negative (the outputs toggling); the run's first starts from the operating point, and a
    decision after another input carries that change. With each run's ``decisions``, over those
    that changed the held outputs instead (a decision other than the one before it), the run's
    first left out. The power that is over a cycle; and each input's own energy (the inputs of every
    run, ascending: NaN where a run has none counted)."""

    # [Baker] Eq. (11.14), p. 355: the supply's average current, the charge a cycle over its period;
    # Eq. (11.15), p. 355: the power, V_DD times it (a decision's energy V_DD times its charge)
    identity = measurement_identity(meas)
    if decisions is not None:
        check_identity(list(decisions), identity, name="comparator decisions")
    supply_v = np.asarray([float(run.param.vdd) for run in meas])
    inputs_v = np.unique(np.concatenate([np.asarray(run.param.points, dtype=np.float64)[:, 1] for run in meas]))
    energy_j, point_energy_j = [], np.full((len(meas), len(inputs_v)), np.nan)
    for row, (run, vdd) in enumerate(zip(meas, supply_v, strict=True)):
        tb = run.param
        charge_c = run.v[CHARGE_METER] * CHARGE_METER_F
        start, end = (calc.value(charge_c, run.time_s, tb.trial_start_s + offset) for offset in (0.0, tb.cycle_s))
        trial_v = np.asarray(tb.points, dtype=np.float64)[tb.trial_point, 1]
        steady = np.flatnonzero(np.isclose(np.abs(trial_v[1:]), np.abs(trial_v[:-1]), rtol=1e-9, atol=1e-15)) + 1
        if decisions is not None:
            decided = np.asarray(decisions[row].decision)
            steady = np.flatnonzero(decided[1:] != decided[:-1]) + 1
        energy_j.append(float(vdd * np.mean((end - start)[steady])) if len(steady) else math.nan)
        for column, value in enumerate(inputs_v):
            at = steady[np.isclose(trial_v[steady], value, rtol=1e-9, atol=1e-15)]
            if len(at):
                point_energy_j[row, column] = float(vdd * np.mean((end - start)[at]))
    energy = np.asarray(energy_j)
    return AnalysisPower(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        supply_v=supply_v,
        average_power_w=energy / np.asarray([run.param.cycle_s for run in meas]),
        energy_per_decision_j=energy,
        vin_diff_v=inputs_v,
        point_energy_j=point_energy_j,
    )


@analysis
def analyze_stress(meas: Sequence[Meas]) -> AnalysisStress:
    """Every transistor of the comparator over runs at the supply's corners that saved its values
    (``TbParams.device_values``), the nominal supply's among them: its junctions' forward bias and
    its terminal pairs' voltages at each run's operating point and over its transient
    (``flow.circuit.oppoint.stress``), against the nominal supply times the largest corner."""

    identity = measurement_identity(meas)
    nominal_v = float(np.median([float(run.param.vdd) for run in meas]))
    devices = oppoint.mos_devices(netlist(meas[0].param.params))
    found = oppoint.stress([*meas, *(run.sweeps["opdc"] for run in meas)], devices, nominal_v=nominal_v)
    # [Razavi-Analog] Sec. 15.4.2, p. 641: a junction forward-biased by 300 mV conducts negligibly
    forward_v, forward_device = max(
        (float(calc.ymax(values)), device)
        for device, by_junction in found.junction_v.items()
        for values in by_junction.values()
    )
    # not in the reference texts: the largest |voltage| across a terminal pair, against the nominal
    # supply times the largest supply corner (flow.circuit.oppoint)
    terminal_v, terminal_device, terminal_pair = max(
        (float(calc.ymax(values)), device, pair.name.lower())
        for device, by_pair in found.terminal_v.items()
        for pair, values in by_pair.items()
    )
    return AnalysisStress(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        forward_v=forward_v,
        forward_device=forward_device,
        terminal_v=terminal_v,
        terminal_device=terminal_device,
        terminal_pair=terminal_pair,
        limit_v=nominal_v * oppoint.SUPPLY_CORNER_MAX,
        overstressed=tuple(sorted(found.overstressed)),
        forward=tuple(sorted(found.forward)),
    )


@analysis
def analyze_scurve(decisions: Sequence[AnalysisDecisions]) -> AnalysisScurve:
    """Per input, over every trial: the decision probability (the share of the resolved decisions
    high) and the fraction unresolved."""

    # [Razavi-ADC] Eq. (6.62), p. 117: the decisions' shares at a constant input under noise
    identity = measurement_identity(decisions)
    # inputs rounded to 1 pV, finer than any programmed step
    vin_diff_v = np.round(np.concatenate([item.vin_diff_v for item in decisions]), decimals=12)
    decision = np.concatenate([np.asarray(item.decision, dtype=np.float64) for item in decisions])
    unresolved = np.concatenate(
        [
            np.zeros(len(item.decision), dtype=np.bool_) if item.resolved is None else ~np.asarray(item.resolved)
            for item in decisions
        ]
    )
    inputs = np.unique(vin_diff_v)
    probability, undecided = [], []
    for value in inputs:
        at = vin_diff_v == value
        decided = at & ~unresolved
        probability.append(calc.average(decision[decided]) if np.any(decided) else math.nan)
        undecided.append(calc.average(unresolved[at]))
    return AnalysisScurve(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_diff_v=inputs,
        probability=np.asarray(probability),
        unresolved_fraction=np.asarray(undecided),
        total_unresolved_fraction=calc.average(unresolved),
    )


@analysis
def analyze_offset_noise(decisions: Sequence[AnalysisDecisions]) -> AnalysisOffsetNoise:
    """Pool decision sweeps at one input common mode and fit offset and input noise.

    The same S-curve fit locates a CDAC switching curve's transition, from its trials
    (``capdac.analyze_decisions``). Trials a simulation marks unresolved (the
    latch still undecided when the decision was read: the output holds the previous one) are left
    out; where more than 1 % of them are, the comparator is too slow for its clock and the fit is
    ``unresolved``.

    The offset and noise of a valid curve are the Gaussian of most likelihood given every point's
    decisions (``_probit_fit``), searched from the monotonic curve's 50 % and 16 %/84 % crossings.
    It needs two points or more inside the transition (a share strictly between 0 and 1): with
    fewer the inputs are too far apart there to measure its width, and the curve is
    ``Validity.UNDERSAMPLED``, its offset the 50 % crossing and its noise NaN.
    """

    identity = measurement_identity(decisions)
    # Compare common modes at 1 µV resolution, finer than any programmed step.
    common_modes = np.unique(np.round(np.concatenate([item.vin_cm_v for item in decisions]), decimals=6))
    if len(common_modes) != 1:
        raise ValueError("comparator offset/noise analysis requires measurements at one input common mode")

    # Round inputs to 1 pV so repeated programmed values pool exactly.
    vin_diff_v = np.round(np.concatenate([item.vin_diff_v for item in decisions]), decimals=12)
    decision = np.concatenate([item.decision for item in decisions])
    resolved = np.concatenate(
        [
            np.ones(len(item.decision), dtype=np.bool_) if item.resolved is None else np.asarray(item.resolved)
            for item in decisions
        ]
    )
    unresolved_fraction = 1.0 - float(np.mean(resolved))
    # more than 1 % undecided: the comparator is too slow for its clock, and its curve is kept as read
    if unresolved_fraction <= 0.01:
        vin_diff_v, decision = vin_diff_v[resolved], decision[resolved]
    unique_input, inverse = np.unique(vin_diff_v, return_inverse=True)
    if len(unique_input) < 3:
        raise ValueError("comparator offset/noise analysis requires at least three inputs")
    count = np.bincount(inverse, minlength=len(unique_input)).astype(np.int64)
    decision_count = np.bincount(inverse, weights=np.asarray(decision, dtype=np.float64), minlength=len(unique_input))
    probability = decision_count / count
    trend = float(np.dot(unique_input - calc.average(unique_input), probability - calc.average(probability)))
    decision_polarity: Literal[-1, 1] = 1 if trend >= 0.0 else -1

    # Adjacent-point reversals are tested across the complete curve. Use
    # Bonferroni-adjusted 95% Wilson bounds so a long 100 µV grid does not
    # acquire an almost-certain false failure from repeated pairwise tests.
    # not in the reference texts: Wilson score intervals, Bonferroni-adjusted, and a between-batch
    # Student t interval, to call a reversal significant
    comparison_count = max(len(unique_input) - 1, 1)
    z_monotonic = float(norm.ppf(1.0 - 0.05 / (2.0 * comparison_count)))
    denominator = 1.0 + z_monotonic**2 / count
    interval_center = (probability + z_monotonic**2 / (2.0 * count)) / denominator
    interval_half_width = (
        z_monotonic
        * np.sqrt(probability * (1.0 - probability) / count + z_monotonic**2 / (4.0 * count**2))
        / denominator
    )
    lower_probability = interval_center - interval_half_width
    upper_probability = interval_center + interval_half_width

    # A physical fine point is deliberately acquired in host-side batches.
    # Trials inside one sequencer burst share the same analog state, so their
    # Bernoulli outcomes are not independent. Keep the simultaneous Wilson
    # interval as the minimum uncertainty, but widen it with the between-batch
    # 95% interval whenever the persisted batching metadata permits an exact
    # reconstruction. A nonzero host interval additionally exposes slow drift;
    # zero-interval transport batches still expose within-capture correlation.
    # Simulations and legacy/unbatched captures retain Wilson-only behavior.
    batch_probabilities: list[list[float]] = [[] for _ in unique_input]
    for item in decisions:
        batch_count = int(item.info.readbacks.get("capture_batch_count", 1))
        batch_trials = int(item.info.readbacks.get("capture_batch_trials", 0))
        point_inputs = np.round(item.vin_diff_v, decimals=12)
        point_decisions = np.asarray(item.decision)
        if (
            batch_count < 2
            or batch_trials < 1
            or batch_count * batch_trials != len(point_decisions)
            or len(np.unique(point_inputs)) != 1
        ):
            continue
        input_index = int(np.searchsorted(unique_input, point_inputs[0]))
        batch_probabilities[input_index].extend(
            np.mean(point_decisions.reshape(batch_count, batch_trials), axis=1).tolist()
        )
    for input_index, point_batches in enumerate(batch_probabilities):
        if len(point_batches) < 2:
            continue
        batch_array = np.asarray(point_batches, dtype=np.float64)
        cluster_half_width = float(
            student_t.ppf(0.975, len(batch_array) - 1)
            * calc.stddev(batch_array, sample=True)
            / np.sqrt(len(batch_array))
        )
        lower_probability[input_index] = min(
            lower_probability[input_index], max(0.0, probability[input_index] - cluster_half_width)
        )
        upper_probability[input_index] = max(
            upper_probability[input_index], min(1.0, probability[input_index] + cluster_half_width)
        )
    if decision_polarity > 0:
        oriented_probability, oriented_lower, oriented_upper = probability, lower_probability, upper_probability
    else:
        oriented_probability = 1.0 - probability
        oriented_lower = 1.0 - upper_probability
        oriented_upper = 1.0 - lower_probability

    significant_reversal = np.any(
        (oriented_probability[:-1] > oriented_probability[1:]) & (oriented_lower[:-1] > oriented_upper[1:])
    )
    fitted_probability = np.maximum.accumulate(oriented_probability)

    # Measure the first rising contact of the 16%, 50%, and 84% points: the
    # Gaussian mean and +-1 sigma. Endpoint-only contacts remain unbracketed.
    # [Razavi-ADC] Eq. (6.63), p. 118: the input-referred noise, the sigma of the Gaussian whose
    # cumulative area gives the decisions' shares (Phi(-1) = 15.87 % at a sigma's input); [Pelgrom]
    # Practical Hint 12.1, Fig. 12.8, p. 607: the decisions' cumulative Gaussian about the trip level
    p16 = calc.cross(fitted_probability, unique_input, 0.158655, occurrence=1)
    # [Razavi-ADC] Sec. 5.1, p. 71: the input-referred offset, the input at which the circuit
    # balances (the curve's 50 % point)
    p50 = calc.cross(fitted_probability, unique_input, 0.5, occurrence=1)
    p84 = calc.cross(fitted_probability, unique_input, 0.841345, occurrence=1)
    noise_sigma_v = abs(p84 - p16) / 2.0 if math.isfinite(p16) and math.isfinite(p84) else math.nan
    inside = int(np.count_nonzero((oriented_probability > 0.0) & (oriented_probability < 1.0)))
    validity: Validity
    if unresolved_fraction > 0.01:
        validity = Validity.UNRESOLVED
        p50 = math.nan
        noise_sigma_v = math.nan
    elif significant_reversal:
        validity = Validity.NON_MONOTONIC
        p50 = math.nan
        noise_sigma_v = math.nan
    elif not all(math.isfinite(value) for value in (p16, p50, p84)):
        validity = Validity.UNBRACKETED
    elif inside < 2:
        validity = Validity.UNDERSAMPLED
        noise_sigma_v = math.nan
    else:
        validity = Validity.VALID
        high = decision_count if decision_polarity > 0 else count - decision_count
        p50, noise_sigma_v = _probit_fit(unique_input, high, count, mean=p50, sigma=noise_sigma_v)
    return AnalysisOffsetNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=float(common_modes[0]),
        vin_diff_v=unique_input,
        decision_probability=probability,
        trial_count=count,
        offset_v=p50,
        noise_sigma_v=noise_sigma_v,
        decision_polarity=decision_polarity,
        validity=validity,
    )


def _probit_fit(
    axis: np.ndarray, successes: np.ndarray, trials: np.ndarray, *, mean: float, sigma: float
) -> tuple[float, float]:
    """The Gaussian cumulative curve of most likelihood through binomial counts: ``successes`` of
    ``trials`` at each ``axis`` point, P = Phi((x - mean) / sigma); its mean and sigma, searched
    from ``mean`` and ``sigma``."""
    # not in the reference texts: the Gaussian of most likelihood through the binomial counts (the
    # probit model's maximum-likelihood fit), searched by Nelder-Mead in the mean and log sigma
    x, k, n = (np.asarray(values, dtype=np.float64) for values in (axis, successes, trials))
    steps = minimize(
        lambda step: (
            -float(
                np.sum(
                    k * log_ndtr((x - mean - step[0] * sigma) / (sigma * math.exp(step[1])))
                    + (n - k) * log_ndtr(-(x - mean - step[0] * sigma) / (sigma * math.exp(step[1])))
                )
            )
        ),
        np.zeros(2),
        method="Nelder-Mead",
        options={"xatol": 1e-6, "fatol": 1e-9},
    ).x
    return mean + float(steps[0]) * sigma, sigma * math.exp(float(steps[1]))


@analysis
def analyze_common_mode(decisions: Sequence[AnalysisDecisions]) -> AnalysisCommonMode:
    """Fit each common mode's decisions (``analyze_offset_noise``) and classify each, distinguishing
    stuck outputs from unbracketed curves.

    Each item of ``decisions`` is at one common mode (a capture's point, a run's S-curve). An
    unbracketed curve is relabeled stuck only when it is pinned and the offset of the nearest common
    mode on either side whose offset is located (valid, or undersampled) lies inside its swept input
    range, so the transition should have been observed.
    """

    identity = measurement_identity(decisions)
    groups: dict[float, list[AnalysisDecisions]] = {}
    for item in decisions:
        # Compare common modes at 1 µV resolution, finer than any programmed step.
        modes = np.unique(np.round(item.vin_cm_v, decimals=6))
        if len(modes) != 1:
            raise ValueError("each item of a common-mode analysis must be at one common mode")
        groups.setdefault(float(modes[0]), []).append(item)
    ordered = [analyze_offset_noise(groups[mode]) for mode in sorted(groups)]
    common_modes = np.asarray([result.vin_cm_v for result in ordered])

    # the curves whose offset is located (a valid fit, or a transition too narrow for its inputs)
    valid = np.asarray(
        [result.validity in (Validity.VALID, Validity.UNDERSAMPLED) for result in ordered], dtype=np.bool_
    )
    validity: list[Validity] = []
    for result in ordered:
        label = Validity(result.validity)
        # not in the reference texts: stuck-low/stuck-high, a curve pinned outside 0.1-0.9 where a
        # neighbour's offset lies in its span (0.1/0.9 well outside a bracketed S-curve's noise)
        probability = result.decision_probability
        pinned = (
            Validity.STUCK_LOW
            if np.all(probability <= 0.10)
            else Validity.STUCK_HIGH
            if np.all(probability >= 0.90)
            else None
        )
        if result.validity == Validity.UNBRACKETED and pinned is not None:
            lower = np.flatnonzero((common_modes < result.vin_cm_v) & valid)
            upper = np.flatnonzero((common_modes > result.vin_cm_v) & valid)
            neighbors = [int(lower[-1])] if len(lower) else []
            neighbors += [int(upper[0])] if len(upper) else []
            minimum_v = float(calc.ymin(result.vin_diff_v))
            maximum_v = float(calc.ymax(result.vin_diff_v))
            if any(minimum_v <= ordered[neighbor].offset_v <= maximum_v for neighbor in neighbors):
                label = pinned
        validity.append(label)
    width = max(len(result.vin_diff_v) for result in ordered)
    return AnalysisCommonMode(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=common_modes,
        offset_v=np.asarray([result.offset_v for result in ordered]),
        noise_sigma_v=np.asarray([result.noise_sigma_v for result in ordered]),
        decision_polarity=np.asarray([result.decision_polarity for result in ordered], dtype=np.int64),
        validity=tuple(validity),
        vin_diff_v=np.asarray(
            [
                np.pad(result.vin_diff_v, (0, width - len(result.vin_diff_v)), constant_values=np.nan)
                for result in ordered
            ]
        ),
        decision_probability=np.asarray(
            [
                np.pad(result.decision_probability, (0, width - len(result.vin_diff_v)), constant_values=np.nan)
                for result in ordered
            ]
        ),
        trial_count=np.asarray(
            [np.pad(result.trial_count, (0, width - len(result.vin_diff_v))) for result in ordered], dtype=np.int64
        ),
    )


@analysis
def analyze_sampling_noise(decisions: Sequence[AnalysisDecisions]) -> AnalysisSamplingNoise:
    """Fit each curve of one ADC's captures over the DAC's coupling to its inputs: a curve is one
    P-side coupling (the scan's ``requested_dac_rail_percent``) in one sampling mode, fitted as
    ``analyze_offset_noise`` fits it. Where captures of several runs hold the same curve, the newest
    run's replace the others' (a correction run re-measures whole curves)."""

    # not in the reference texts: a curve per DAC coupling and sampling mode of the converter's
    # captures, each fitted as [Razavi-ADC] Eq. (6.63), p. 118 defines the noise
    identity = measurement_identity(decisions)
    curves: dict[tuple[float, str], list[AnalysisDecisions]] = {}
    for item in decisions:
        key = (float(item.param.requested_dac_rail_percent or 0.0), str(item.param.sampling_mode))
        curves.setdefault(key, []).append(item)
    fits = []
    for key in sorted(curves):
        # each run by its folder, as the scan wrote it (a timestamp)
        run = {id(item): item.info.source_path.parent.name if item.info.source_path else "" for item in curves[key]}
        newest = max(run.values())
        fits.append((key, analyze_offset_noise([item for item in curves[key] if run[id(item)] == newest])))
    width = max(len(fit.vin_diff_v) for _key, fit in fits)
    return AnalysisSamplingNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        coupling_percent=np.asarray([coupling for (coupling, _mode), _fit in fits]),
        sampling_mode=tuple(mode for (_coupling, mode), _fit in fits),
        offset_v=np.asarray([fit.offset_v for _key, fit in fits]),
        noise_sigma_v=np.asarray([fit.noise_sigma_v for _key, fit in fits]),
        decision_polarity=np.asarray([fit.decision_polarity for _key, fit in fits], dtype=np.int64),
        validity=tuple(fit.validity for _key, fit in fits),
        vin_diff_v=np.asarray(
            [np.pad(fit.vin_diff_v, (0, width - len(fit.vin_diff_v)), constant_values=np.nan) for _key, fit in fits]
        ),
        decision_probability=np.asarray(
            [
                np.pad(fit.decision_probability, (0, width - len(fit.vin_diff_v)), constant_values=np.nan)
                for _key, fit in fits
            ]
        ),
        trial_count=np.asarray(
            [np.pad(fit.trial_count, (0, width - len(fit.vin_diff_v))) for _key, fit in fits], dtype=np.int64
        ),
    )


@analysis
def analyze_scope_edges(conversions: Sequence[AnalysisConversions]) -> AnalysisScopeEdges:
    """The comparator's output edges in a converter's scope records (the bench's: ``seq_comp``,
    COMP, and ``comp_out``, COMP_OUT): each decision's COMP rise, COMP_OUT's crossing after it and
    the rise's jitter, COMP_OUT's maps folded per decision and over the conversion, where COMP is
    high, and each decision's delays as a map.

    Every scope record of every capture is one capture of one complete conversion; the captures
    share one sequence and symbol rate, whose clock rises are evenly spaced.
    """

    # [Baker] Fig. 10.9, p. 333: propagation delay, between the 50 % points of input and output;
    # [Razavi-PLL] Sec. 2.2.5, p. 52: absolute jitter, an edge's departure from a noiseless clock of
    # the same period; Fig. 2.14, p. 42: an eye diagram, the cycles superimposed against a clock
    identity = measurement_identity(conversions)
    first = conversions[0]
    if any(item.sequence != first.sequence or item.symbol_rate_hz != first.symbol_rate_hz for item in conversions):
        raise ValueError("comparator eye measurements must share one sequence and symbol rate")
    decisions = first.decisions
    decision_period_s = first.decision_period_s
    if not math.isfinite(decision_period_s):
        raise ValueError(f"sequence must contain {decisions} equally spaced COMP rising edges")

    time_s = None
    comp_records = []
    comp_out_records = []
    for item in conversions:
        wave = item.wave
        if wave is None:
            raise ValueError("comparator eye requires scope waveform records")
        if time_s is None:
            time_s = wave.time_s
        elif not np.array_equal(time_s, wave.time_s):
            raise ValueError("comparator eye scope records must share one time axis")
        comp_records.extend(wave.v["seq_comp"])
        comp_out_records.extend(wave.v["comp_out"])
    assert time_s is not None

    capture_count = len(comp_records)
    clock_edges_s = np.empty((capture_count, decisions))
    clock_falls_s = np.empty((capture_count, decisions))
    delays_s = np.full((capture_count, decisions), np.nan)
    jitter_s = np.empty((capture_count, decisions))
    unchanged = np.zeros(decisions, dtype=np.int64)
    multiple = np.zeros(decisions, dtype=np.int64)
    unsettled = np.zeros(decisions, dtype=np.int64)
    for capture_index, (comp_v, comp_out_v) in enumerate(zip(comp_records, comp_out_records, strict=True)):
        # Take logic levels from the 5th/95th percentiles, which ignore edge
        # overshoot, and require at least 50 mV of swing to call it a logic signal.
        comp_low, comp_high = np.percentile(comp_v, (5, 95))
        out_low, out_high = np.percentile(comp_out_v, (5, 95))
        if comp_high - comp_low < 0.05 or out_high - out_low < 0.05:
            raise ValueError(f"capture {capture_index} lacks a valid COMP or COMP_OUT swing")
        comp_level = float((comp_low + comp_high) / 2)
        out_level = float((out_low + out_high) / 2)
        clock_edges = calc.cross(comp_v, time_s, comp_level, edge="rising")
        clock_edges = clock_edges[clock_edges >= 0][:decisions]
        # Allow 20% of a decision period of edge jitter before rejecting the record.
        if len(clock_edges) != decisions or np.any(
            np.abs(np.diff(clock_edges) - decision_period_s) > 0.2 * decision_period_s
        ):
            raise ValueError(f"capture {capture_index} does not contain one complete {decisions}-decision conversion")
        clock_edges_s[capture_index] = clock_edges
        clock_falls_s[capture_index] = _falls(
            clock_edges, calc.cross(comp_v, time_s, comp_level, edge="falling"), decision_period_s
        )
        jitter_s[capture_index] = clock_edges - clock_edges[0] - np.arange(decisions) * decision_period_s
        rising_edges = calc.cross(comp_out_v, time_s, out_level, edge="rising")
        output_edges = calc.cross(comp_out_v, time_s, out_level, edge="either")
        for decision, clock_edge in enumerate(clock_edges):
            matching = output_edges[(output_edges >= clock_edge) & (output_edges < clock_edge + decision_period_s)]
            if len(matching) == 1:
                rising = bool(np.any(rising_edges == matching[0]))
                final_index = min(np.searchsorted(time_s, clock_edge + decision_period_s), len(time_s)) - 1
                final_valid = comp_out_v[final_index] >= out_level if rising else comp_out_v[final_index] <= out_level
                if final_valid:
                    delays_s[capture_index, decision] = matching[0] - clock_edge
                else:
                    unsettled[decision] += 1
            elif len(matching) == 0:
                unchanged[decision] += 1
            else:
                multiple[decision] += 1

    # COMP_OUT's maps over its range and a twentieth of it either side: every decision folded at
    # its COMP rise, 0.2 periods before it to a period after, in 96 cells, and every record from
    # its B0 rise over the conversion, 32 cells a period
    records = np.asarray(comp_out_records)
    low, high = float(np.min(records)), float(np.max(records))
    voltage_v = np.linspace(low - 0.05 * (high - low), high + 0.05 * (high - low), 65)
    eye_time_s = np.linspace(-0.2 * decision_period_s, decision_period_s, 97)
    timing_time_s = np.linspace(-0.2 * decision_period_s, decisions * decision_period_s, 32 * decisions + 7)
    return AnalysisScopeEdges(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        clock_edges_s=clock_edges_s,
        delays_s=delays_s,
        jitter_s=jitter_s,
        unchanged=unchanged,
        multiple=multiple,
        unsettled=unsettled,
        decision_period_s=decision_period_s,
        conversion_rate_hz=first.conversion_rate_hz,
        voltage_v=voltage_v,
        eye_time_s=eye_time_s,
        eye_share=_share(_folded(records, time_s, clock_edges_s, eye_time_s), voltage_v),
        timing_time_s=timing_time_s,
        timing_share=_share(_folded(records, time_s, clock_edges_s[:, :1], timing_time_s), voltage_v),
        clock_high_s=_median(clock_falls_s - clock_edges_s),
        rise_s=np.asarray([_median(column) for column in (clock_edges_s - clock_edges_s[:, :1]).T]),
        fall_s=np.asarray([_median(column) for column in (clock_falls_s - clock_edges_s[:, :1]).T]),
        **_per_decision("response", np.tile(np.arange(decisions), capture_count), delays_s.ravel(), decisions),
    )


@analysis
def analyze_edge_eye(conversions: AnalysisConversions) -> AnalysisEdgeEye:
    """A simulated converter's comparator over each saved conversion, each from its record's INIT
    rise with one clock rise a decision: its SR latch's positive output and its regenerative
    latch's |P - N| as maps, folded at every decision's clock rise (-0.1 to 1.1 periods) and over
    the conversion from B0's (0.2 periods before it to a period after the last), in the supply's
    range; where the clock is high."""

    # [Razavi-PLL] Fig. 2.14, p. 42: an eye diagram, the cycles superimposed against an ideal clock
    wave = conversions.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    required = {"seq_init", "clk_comp", "comp.latch_p", "comp.latch_n", "comp_out_p"}
    if missing := required - wave.v.keys():
        raise ValueError(f"ADC edge eye requires saved canonical nets: {sorted(missing)}")
    time = wave.time_s
    threshold = conversions.vdd_d_v / 2
    decisions = conversions.decisions
    record_edges = []
    record_falls = []
    for record in range(len(wave.record_index)):
        init_edges = calc.cross(wave.v["seq_init"][record], time, threshold, edge="rising", initial_high=True)
        if not len(init_edges):
            raise ValueError(f"conversion {record} has no INIT rise")
        stop = init_edges[1] if len(init_edges) > 1 else time[-1]
        clock_edges = calc.cross(wave.v["clk_comp"][record], time, threshold, edge="rising")
        clock_edges = clock_edges[(clock_edges >= init_edges[0]) & (clock_edges < stop)]
        if len(clock_edges) != decisions:
            raise ValueError(f"conversion {record} has {len(clock_edges)} COMP rises; expected {decisions}")
        record_edges.append(clock_edges)
        record_falls.append(calc.cross(wave.v["clk_comp"][record], time, threshold, edge="falling"))
    record_edges = np.asarray(record_edges)
    period_s = float(np.median(np.diff(record_edges, axis=1)))
    decision_edge_s = np.median(record_edges - record_edges[:, :1], axis=0)
    falls_s = np.asarray(
        [_falls(edges, falls, period_s) for edges, falls in zip(record_edges, record_falls, strict=True)]
    )
    supply_v = max(conversions.vdd_a_v, conversions.vdd_d_v)
    # each map in 64 cells of the supply's range and a tenth of it either side; the eye in 96
    # cells, the conversion in 32 a period
    voltage_v = np.linspace(-0.1 * supply_v, 1.1 * supply_v, 65)
    eye_time_s = np.linspace(-0.1 * period_s, 1.1 * period_s, 97)
    span_s = float(decision_edge_s[-1]) + 1.2 * period_s
    timing_time_s = np.linspace(
        -0.2 * period_s, float(decision_edge_s[-1]) + period_s, round(32 * span_s / period_s) + 1
    )
    traces = {
        "sr": wave.v["comp_out_p"],
        "xc": np.abs(wave.v["comp.latch_p"] - wave.v["comp.latch_n"]),
    }
    identity = conversions.identity
    return AnalysisEdgeEye(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        decision_period_s=period_s,
        decision_edge_s=decision_edge_s,
        fall_s=np.asarray([_median(column) for column in (falls_s - record_edges[:, :1]).T]),
        clock_high_s=_median(falls_s - record_edges),
        supply_v=supply_v,
        records=len(record_edges),
        voltage_v=voltage_v,
        eye_time_s=eye_time_s,
        timing_time_s=timing_time_s,
        **{
            f"{name}_eye": _share(_folded(values, time, record_edges, eye_time_s), voltage_v)
            for name, values in traces.items()
        },
        **{
            f"{name}_timing": _share(_folded(values, time, record_edges[:, :1], timing_time_s), voltage_v)
            for name, values in traces.items()
        },
    )


@analysis
def analyze_response(conversions: AnalysisConversions) -> AnalysisResponse:
    """A simulated converter's comparator, each decision's midpoint-valid XC and single-ended SR
    response after its clock's rise; both as maps over the decisions.

    One XC node must fall below 50% of VDD and the other remain above 50% before COMP reset. The
    positive buffered SR output must enter the matching half-rail band before the next COMP rise.
    Both must remain valid through the end of their windows. Already-held SR states are counted
    separately.
    """

    # [Razavi-ADC] Sec. 7.3, p. 131: the comparator's speed, clock to its latch's nodes split; Sec.
    # 7.5, p. 134: the RS latch's delay; [Baker] Fig. 10.9, p. 333: to the output's 50 % point
    wave = conversions.wave
    if wave is None:
        raise ValueError("this analysis requires waveform records")
    required = {"seq_init", "seq_logic", "clk_comp", "comp.latch_p", "comp.latch_n", "comp_out_p"}
    if missing := required - wave.v.keys():
        raise ValueError(f"ADC comparator response requires saved canonical nets: {sorted(missing)}")
    time = wave.time_s
    analog_supply = conversions.vdd_a_v
    digital_supply = conversions.vdd_d_v
    decisions = conversions.decisions
    rows = []
    for record, conversion in enumerate(wave.record_index):
        signals = {name: values[record] for name, values in wave.v.items() if name in required}
        # One conversion starts at the record's INIT rise and holds one COMP rise per decision.
        init_edges = calc.cross(signals["seq_init"], time, digital_supply / 2, edge="rising", initial_high=True)
        comp_edges = calc.cross(signals["clk_comp"], time, digital_supply / 2, edge="rising")
        if not len(init_edges):
            raise ValueError(f"record {record} has no INIT rise")
        stop = init_edges[1] if len(init_edges) > 1 else time[-1]
        comp_indices = np.flatnonzero((comp_edges >= init_edges[0]) & (comp_edges < stop))
        if len(comp_indices) != decisions:
            raise ValueError(f"record {record} has {len(comp_indices)} COMP rises; expected {decisions}")
        following = np.r_[comp_edges, np.nan][comp_indices + 1]
        resets = calc.cross(signals["clk_comp"], time, digital_supply / 2, edge="falling")
        latch_p, latch_n = signals["comp.latch_p"], signals["comp.latch_n"]
        sr_p = signals["comp_out_p"]
        for decision, (start, next_comp) in enumerate(zip(comp_edges[comp_indices], following, strict=True)):
            stop = next_comp if np.isfinite(next_comp) else time[-1]
            reset_edges = resets[(resets > start) & (resets < stop)]
            reset = float(reset_edges[0]) if len(reset_edges) == 1 else math.nan
            evaluation = (time >= start) & (time < reset)
            internal_delay = math.nan
            sr_delay = math.nan
            held = False
            if np.any(evaluation):
                last = np.flatnonzero(evaluation)[-1]
                final_p = float(latch_p[last])
                final_n = float(latch_n[last])
                midpoint = 0.5 * analog_supply
                if final_p != final_n:
                    target = 1 if final_p > final_n else -1
                    high, low = (latch_p, latch_n) if target > 0 else (latch_n, latch_p)
                    valid = (high[evaluation] >= midpoint) & (low[evaluation] <= midpoint)
                    stable = calc.settlingTime(valid, time[evaluation])
                    if np.isfinite(stable):
                        internal_delay = max(0.0, stable - start)
                    # Time the observed SR state even if the XC pair did not
                    # settle across the midpoint before COMP reset.
                    output = (time >= start) & (time < stop)
                    valid = sr_p[output] >= midpoint if target > 0 else sr_p[output] <= midpoint
                    stable = calc.settlingTime(valid, time[output])
                    if np.isfinite(stable):
                        held = bool(np.all(valid))
                        if not held:
                            sr_delay = max(0.0, stable - start)
            rows.append((int(conversion), decision, internal_delay, sr_delay, held))
    decision_index = np.asarray([row[1] for row in rows])
    internal_response_s = np.asarray([row[2] for row in rows])
    sr_response_s = np.asarray([row[3] for row in rows])
    identity = conversions.identity
    return AnalysisResponse(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        conversion_index=np.asarray([row[0] for row in rows]),
        decision_index=decision_index,
        internal_response_s=internal_response_s,
        sr_response_s=sr_response_s,
        sr_held=np.asarray([row[4] for row in rows]),
        sample_interval_s=float(calc.ymax(np.diff(time))),
        conversion_rate_hz=conversions.conversion_rate_hz,
        **_per_decision("xc", decision_index, internal_response_s, decisions),
        **_per_decision("sr", decision_index, sr_response_s, decisions),
    )


def _falls(rises: np.ndarray, falls: np.ndarray, period_s: float) -> np.ndarray:
    """Each of ``rises``' fall: the first of the ascending ``falls`` after it, NaN where none comes
    within ``period_s``."""
    found = np.r_[falls, np.nan][np.searchsorted(falls, rises, side="right")]
    return np.where(found - rises < period_s, found, np.nan)


def _median(values: np.ndarray) -> float:
    """The median of the finite ``values``, NaN where there are none."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    return float(np.median(finite)) if len(finite) else math.nan


def _folded(records: np.ndarray, time_s: np.ndarray, origins_s: np.ndarray, edges_s: np.ndarray) -> np.ndarray:
    """Each record (a row of ``records`` on ``time_s``) at the centre of each time cell (``edges_s``,
    from an origin) from each of its origins (a row of ``origins_s`` each): a row an origin, in
    order, NaN outside its record."""
    centres_s = (edges_s[:-1] + edges_s[1:]) / 2
    return np.asarray(
        [
            np.interp(origin + centres_s, time_s, row, left=np.nan, right=np.nan)
            for row, origins in zip(records, origins_s, strict=True)
            for origin in origins
        ]
    )


def _share(traces: np.ndarray, voltage_v: np.ndarray) -> np.ndarray:
    """Each column of ``traces`` (a row a trace, a column a time cell) counted in the voltage's
    cells (``voltage_v``: their edges, ``calc.histogram2D``): a row a voltage cell, each cell's share
    of the traces, NaN where none passes it."""
    columns = traces.shape[1]
    column = np.broadcast_to(np.arange(columns, dtype=np.float64), traces.shape)
    inside = np.isfinite(traces)
    counts, _, _ = calc.histogram2D(column[inside], traces[inside], bins=(np.arange(columns + 1) - 0.5, voltage_v))
    share = counts.T / len(traces)
    return np.where(share > 0, share, np.nan)


def _per_decision(name: str, decision: np.ndarray, times_s: np.ndarray, decisions: int) -> dict[str, np.ndarray]:
    """Each decision's ``times_s`` over 48 cells across every finite one (0.05 ns either side of a
    single value; none where none is finite), by ``name``: the cells' edges (``<name>_s``), each
    cell's share of its decision's finite times (``<name>_share``: a row a cell, a column a
    decision, NaN where none) and each decision's median (``<name>_median_s``)."""
    finite = np.isfinite(times_s)
    by_decision = [times_s[finite & (decision == index)] for index in range(decisions)]
    median_s = np.asarray([_median(values) for values in by_decision])
    if not np.any(finite):
        return {f"{name}_s": np.zeros(0), f"{name}_share": np.zeros((0, decisions)), f"{name}_median_s": median_s}
    lower, upper = float(np.min(times_s[finite])), float(np.max(times_s[finite]))
    if lower == upper:
        lower, upper = lower - 0.05e-9, upper + 0.05e-9
    edges_s = np.linspace(lower, upper, 49)
    share = np.full((48, decisions), np.nan)
    for index, values in enumerate(by_decision):
        if len(values):
            counts, _ = np.histogram(values, bins=edges_s)
            share[:, index] = np.where(counts > 0, counts / len(values), np.nan)
    return {f"{name}_s": edges_s, f"{name}_share": share, f"{name}_median_s": median_s}


def metrics(
    *,
    small: AnalysisDelay,
    large: AnalysisDelay,
    metastability: AnalysisMetastability,
    power: AnalysisPower,
    kickback: AnalysisKickback,
    supply: Sequence[AnalysisDelay],
    clock: AnalysisClockCheck | None = None,
    common_mode: AnalysisCommonMode | None = None,
    nominal: AnalysisOffsetNoise | None = None,
    scurve: AnalysisScurve | None = None,
    outputs: AnalysisMetastability | None = None,
    toggle: AnalysisPower | None = None,
    recovery: AnalysisDelay | None = None,
    slow: AnalysisDelay | None = None,
    common_mode_delay: Sequence[AnalysisDelay] | None = None,
    converter: AnalysisDelay | None = None,
    converter_power: AnalysisPower | None = None,
    stress: AnalysisStress | None = None,
) -> Metrics:
    """The scalar metrics of a characterization: the delay at the small and large inputs (the
    slowest of their decisions that follow the input's sign) and their energy (``power``: the
    small run's, then the large's), the 0.1 mV delay and the regeneration time constant, kickback,
    the slowest small-input delay over the supply (NaN where one did not resolve) and whether it
    decides within the clock (``clock``); where their runs ran, the delays to the held outputs at
    0.5 and 100 mV from the offset (``outputs``) and the energy where they toggle (``toggle``: its
    +0.5 mV input's),
    the kickback's error left for the next decisions, the delay at 0.5 mV after a full-scale input
    (``recovery``), at the slow corner (``slow``), the slowest over the common mode (``small`` and
    ``common_mode_delay``), on the converter's clocks and its energy there (``converter``,
    ``converter_power``), the delay runs' decisions against their input's sign (those of the delay
    curves, ``metastability`` and ``outputs``, where they counted them), and the devices'
    largest forward bias and terminal voltage (``stress``); where the S-curves ran, the nominal
    common mode's noise and offset (NaN unless valid), the fraction of its decisions unresolved,
    and the largest valid noise over the common mode (``common_mode``: only from more than one
    common mode)."""

    valid = (
        []
        if common_mode is None
        else [
            float(noise)
            for noise, validity in zip(common_mode.noise_sigma_v, common_mode.validity, strict=True)
            if validity == Validity.VALID
        ]
    )
    over_common_mode = common_mode is not None and len(common_mode.vin_cm_v) > 1
    measured = nominal is not None
    against = [delay.against_sign for delay in (small, large, *supply, *([recovery] if recovery else []))]
    # the delay curves' runs, where they counted theirs
    curves = [run.against_sign for run in (metastability, outputs) if run is not None and run.against_sign is not None]
    return Metrics(
        delay_0p5mv_s=float(np.nanmax(_slowest(small))),
        delay_100mv_s=float(np.nanmax(_slowest(large))),
        delay_0p1mv_s=float(metastability.delay_s[0]),
        regeneration_tau_s=metastability.regeneration_tau_s,
        energy_0p5mv_j=float(power.energy_per_decision_j[0]),
        energy_100mv_j=float(power.energy_per_decision_j[1]),
        kickback_v=kickback.kickback_v,
        kickback_diff_v=kickback.kickback_diff_v,
        delay_max_supply_s=float(np.max([_slowest(delay)[0, 0] for delay in supply])),
        decides_in_time=clock.decides_in_time if clock is not None else None,
        noise_v=(nominal.noise_sigma_v if nominal.validity == Validity.VALID else math.nan) if measured else None,
        offset_v=(
            (nominal.offset_v if nominal.validity in (Validity.VALID, Validity.UNDERSAMPLED) else math.nan)
            if measured
            else None
        ),
        unresolved_fraction=scurve.total_unresolved_fraction if scurve is not None else None,
        noise_max_v=max(valid, default=math.nan) if over_common_mode else None,
        delay_out_0p5mv_s=_from_offset(outputs, SMALL_V) if outputs is not None else None,
        delay_out_100mv_s=_from_offset(outputs, LARGE_V) if outputs is not None else None,
        energy_toggle_0p5mv_j=_at(toggle.vin_diff_v, toggle.point_energy_j, SMALL_V) if toggle is not None else None,
        kickback_residual_diff_v=kickback.residual_diff_v if math.isfinite(kickback.residual_diff_v) else None,
        delay_recovery_0p5mv_s=_at(recovery.vin_diff_v, _slowest(recovery), SMALL_V) if recovery is not None else None,
        decisions_against_sign=None
        if any(count is None for count in against)
        else sum(int(np.asarray(count).sum()) for count in against) + sum(curves),
        delay_slow_0p5mv_s=float(np.nanmax(_slowest(slow))) if slow is not None else None,
        delay_max_cm_s=(
            float(np.max([_slowest(delay)[0, 0] for delay in (small, *common_mode_delay)]))
            if common_mode_delay
            else None
        ),
        delay_converter_0p5mv_s=float(np.nanmax(_slowest(converter))) if converter is not None else None,
        energy_converter_0p5mv_j=(
            float(converter_power.energy_per_decision_j[0]) if converter_power is not None else None
        ),
        forward_bias_max_v=stress.forward_v if stress is not None else None,
        terminal_max_v=stress.terminal_v if stress is not None else None,
    )


def _from_offset(outputs: AnalysisMetastability, input_v: float) -> float:
    """The delay to the held outputs at ``input_v`` from the offset: interpolated over the log of
    the input less the offset between the decisions that changed the outputs, beyond the nearest
    one grown by the regeneration time constant, beyond the farthest NaN; NaN without them."""
    if outputs.effective_v is None or outputs.effective_output_s is None:
        return math.nan
    timed = np.isfinite(outputs.effective_output_s) & (outputs.effective_v > 0)
    inputs_v, delays_s = outputs.effective_v[timed], outputs.effective_output_s[timed]
    if not len(inputs_v) or input_v > inputs_v[-1] * (1 + 1e-6):
        return math.nan
    if input_v < inputs_v[0]:
        # [Razavi-ADC] Eq. (7.6), p. 136: an input alpha times smaller, tau_reg ln(alpha) later
        return float(delays_s[0] + outputs.regeneration_tau_s * math.log(inputs_v[0] / input_v))
    return float(np.interp(math.log(input_v), np.log(inputs_v), delays_s))


def _slowest(delay: AnalysisDelay) -> np.ndarray:
    """Each point's slowest decision that follows its input's sign (the median where the delay was
    given without its trials)."""
    return delay.delay_s if delay.slowest_s is None else delay.slowest_s


def _at(inputs_v: np.ndarray | None, values: np.ndarray | None, input_v: float) -> float | None:
    """The value at ``input_v`` of ``values`` over ``inputs_v`` (a row of them: the first), NaN
    where it was not measured there; None where nothing was given."""
    if inputs_v is None or values is None:
        return None
    found = np.flatnonzero(np.isclose(inputs_v, input_v, rtol=1e-9, atol=1e-15))
    return float(np.atleast_2d(values)[0][found[0]]) if len(found) else math.nan
