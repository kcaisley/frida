"""The delay line and ring oscillator's analyses: each from the runs' measurements
(``flow.pipeline.Meas``, their signals on Spectre's own time axis) of the shared testbench, one run
at each supply or control point, and the record's metrics.

A ring is measured over the last ten whole cycles at most before its run's end, its period, the
supply current, swing and duty cycle over that window, where its output still oscillates there
(``analyze_oscillation``); a delay line by its 50 % delays and the 10-90 % transitions of the output
edges they timed (``analyze_propagation``). A differential chain is measured on its p chain alone,
``outp`` (and a line's ``inp``) single-ended at mid-supply.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, measurement_identity

from .params import CONTROL_SWEEP, GAIN_POINTS, SUPPLY_SWEEP, Oscillation
from .subckt import Nets
from .types import AnalysisOscillation, AnalysisPropagation, Metrics


# [Razavi-PLL] Sec. 3.1.1, p. 64: a ring's oscillation period T0 = 1/f0, measured here with its supply
# current, swing and duty cycle
@analysis
def analyze_oscillation(measurements: Sequence[Meas]) -> AnalysisOscillation:
    """Measure ring frequency, supply current, output swing, and duty cycle at each point, over the
    last ten whole cycles at most before the run's end, where the output still oscillates there."""

    identity = measurement_identity(measurements)
    if not identity.dut.ring:
        raise ValueError("oscillation analysis requires a ring")
    rows = []
    for measurement in measurements:
        time_s = measurement.time_s
        if not len(time_s):
            raise ValueError("ring oscillation requires a transient")
        tb = measurement.tb
        vdd, end_s = float(tb.vdd), float(time_s[-1])
        output = measurement.v[Nets.outp.name]
        # not in the reference texts: the output's mid-supply crossings after the enable, the
        # calculator's cross at the threshold its frequency and dutyCycle take
        crossings = calc.cross(output, time_s, vdd / 2, edge="either")
        crossings = crossings[crossings > float(tb.enable_delay_s)]
        rises = calc.cross(output, time_s, vdd / 2, edge="rising")
        rises = rises[rises > float(tb.enable_delay_s)]
        # not in the reference texts: the window, the last ten whole cycles at most before the run's
        # end, from rise to rise ([Razavi-PLL] Example 3.5, p. 70 needs whole cycles, no more)
        first = max(0, len(rises) - 11)
        cycles = len(rises) - 1 - first
        period_s = (float(rises[-1]) - float(rises[first])) / cycles if cycles > 0 else math.nan
        if cycles >= 2:
            # [Razavi-PLL] Sec. 1.1, Fig. 1.1, p. 1: an oscillation that no mechanism sustains dies out
            # not in the reference texts: the rule that tells a ring still oscillating from one that
            # died, its last rise within two of its periods of the run's end
            state = Oscillation.TIMED if end_s - float(rises[-1]) <= 2 * period_s else Oscillation.STOPPED
        elif len(crossings) >= 2 and end_s - float(crossings[-1]) <= 2 * float(np.max(np.diff(crossings))):
            state = Oscillation.SLOW
        else:
            state = Oscillation.STOPPED
        if state is not Oscillation.TIMED:
            rows.append((vdd, float(tb.vcont_v), math.nan, math.nan, math.nan, math.nan, state))
            continue
        start_s, stop_s = float(rises[first]), float(rises[-1])
        window_v, _ = calc.clip(output, time_s, start_s, stop_s)
        current, current_s = calc.clip(measurement.i[Nets.vdd.name], time_s, start_s, stop_s)
        # [Razavi-PLL] Sec. 11.10, Fig. 11.29(a), p. 365: duty cycle, the high time over the period,
        # each of the window's cycles from its interpolated crossings (the calculator's dutyCycle, in
        # percent); a quarter period's margin keeps the window's first and last rise inside the clip
        margin_s = period_s / 4
        high_v, high_s = calc.clip(
            output, time_s, max(start_s - margin_s, float(time_s[0])), min(stop_s + margin_s, end_s)
        )
        duty = calc.dutyCycle(high_v, high_s, threshold=vdd / 2, output_type="average")
        assert isinstance(duty, float)
        rows.append(
            (
                vdd,
                float(tb.vcont_v),
                # [Razavi-PLL] Sec. 3.1.1, p. 64: oscillation frequency, the cycles over their time
                cycles / (stop_s - start_s),
                # [Razavi-PLL] Example 3.5, p. 70: I_DD is periodic in the ring's cycle, so its
                # average over whole cycles
                calc.average(current, current_s),
                # [Razavi-Analog] Sec. 9.1.1, p. 348: output swing; [Razavi-PLL] Sec. 1.4.1, p. 12: the
                # rail-to-rail swing a ring regenerates to; peak to peak, overshoot past the rails included
                calc.peakToPeak(window_v),
                duty / 100,
                state,
            )
        )
    vdd_v, vcont_v, frequency, current, swing, duty, states = zip(*rows, strict=True)
    return AnalysisOscillation(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=np.asarray(vdd_v, dtype=np.float64),
        vcont_v=np.asarray(vcont_v, dtype=np.float64),
        oscillation_frequency_hz=np.asarray(frequency, dtype=np.float64),
        idd_a=np.asarray(current, dtype=np.float64),
        swing_v=np.asarray(swing, dtype=np.float64),
        duty_cycle=np.asarray(duty, dtype=np.float64),
        oscillation=tuple(states),
    )


def _transition(output: np.ndarray, time_s: np.ndarray, middle_s: float, vdd: float, *, rising: bool) -> float:
    """The 10-90 % transition (90-10 % falling) of the output edge that crosses mid-supply at
    ``middle_s``: from the edge's last crossing of its start level before ``middle_s`` to its first
    crossing of its end level after it. The start crossing must follow the previous opposite edge
    (the output's last mid-supply crossing the other way before ``middle_s``): NaN where the output
    did not return past the start level since then, or where it turns back through mid-supply before
    reaching the end level."""
    if not math.isfinite(middle_s):
        return math.nan
    toward, back = ("rising", "falling") if rising else ("falling", "rising")
    start_v, end_v = (0.1 * vdd, 0.9 * vdd) if rising else (0.9 * vdd, 0.1 * vdd)
    starts = calc.cross(output, time_s, start_v, edge=toward)
    ends = calc.cross(output, time_s, end_v, edge=toward)
    turns = calc.cross(output, time_s, vdd / 2, edge=back)
    previous = turns[turns < middle_s]
    after_s = float(previous[-1]) if len(previous) else -math.inf
    starts = starts[(starts > after_s) & (starts <= middle_s)]
    ends, turns = ends[ends >= middle_s], turns[turns > middle_s]
    if not (len(starts) and len(ends)) or (len(turns) and turns[0] < ends[0]):
        return math.nan
    return float(ends[0] - starts[-1])


# [Baker] Sec. 10.1.3, Fig. 10.9, p. 333: a gate's delays t_PLH, t_PHL and output transitions t_LH,
# t_HL, measured here on the line with its supply current
@analysis
def analyze_propagation(measurements: Sequence[Meas]) -> AnalysisPropagation:
    """Measure delay line rise and fall delay, output transitions, and supply current at each point."""

    identity = measurement_identity(measurements)
    if identity.dut.ring:
        raise ValueError("propagation analysis requires a delay line, not a ring")
    # an odd chain inverts: its output answers a rising input with a falling edge
    inverting = identity.dut.stages % 2 == 1
    rows = []
    for measurement in measurements:
        time_s = measurement.time_s
        if not len(time_s):
            raise ValueError("delay line propagation requires a transient")
        tb = measurement.tb
        vdd = float(tb.vdd)
        source = measurement.v[Nets.inp.name]
        output = measurement.v[Nets.outp.name]
        # [Baker] Sec. 10.1.3, Fig. 10.9, p. 333: propagation delay between the 50 % points of input
        # and output, from the second rising (falling) input edge to the output edge it caused:
        # counted from the settled start, the output's second edge of the answering sense (the
        # calculator's delayMeasure, each crossing by its count), so a delay of a period or more is
        # paired with its own input edge
        answer = {"rising": "falling", "falling": "rising"} if inverting else {"rising": "rising", "falling": "falling"}
        level = {"value1": vdd / 2, "value2": vdd / 2}
        after_s = {}
        for sense, answering in answer.items():
            first_s, second_s = (
                calc.delayMeasure(source, output, time_s, edge1=sense, edge2=answering, nth1=nth, nth2=nth, **level)
                for nth in (1, 2)
            )
            # not in the reference texts: the pairing's check. An output edge lost or added between
            # the first and second input edges shifts the count by a period, so the first edges'
            # delay must agree with the second's to a quarter period; a delay that is not positive
            # paired an edge the input did not cause
            paired = second_s > 0 and abs(second_s - first_s) <= float(tb.clock_period_s) / 4
            after_s[sense] = second_s if paired else math.nan
        trigger_s = calc.cross(source, time_s, vdd / 2, edge="rising", occurrence=2)
        # each delay by its output edge: an inverting chain's output rises after a falling input
        cause = {"rise": "falling", "fall": "rising"} if inverting else {"rise": "rising", "fall": "falling"}
        delay_rise_s, delay_fall_s = after_s[cause["rise"]], after_s[cause["fall"]]
        # [Baker] Sec. 10.1.3, Fig. 10.9, p. 333; Eq. (2.26), p. 49: the output's rise and fall times,
        # 10 to 90 % of the swing between the rails (a CMOS output's V_OL and V_OH), each of the output
        # edge its delay timed (t_LH with t_PLH): the edge that crosses mid-supply its delay after its
        # input edge
        rise_time_s, fall_time_s = (
            _transition(
                output,
                time_s,
                calc.cross(source, time_s, vdd / 2, edge=cause[edge], occurrence=2) + delay_s,
                vdd,
                rising=edge == "rise",
            )
            for edge, delay_s in (("rise", delay_rise_s), ("fall", delay_fall_s))
        )
        # [Baker] Eq. (11.14), p. 355: the average current over whole input periods, two from the
        # second rising input edge
        stop_s = trigger_s + 2 * float(tb.clock_period_s)
        if math.isfinite(trigger_s) and stop_s <= float(time_s[-1]):
            current, current_s = calc.clip(measurement.i[Nets.vdd.name], time_s, trigger_s, stop_s)
            idd_a = calc.average(current, current_s)
        else:
            idd_a = math.nan
        timings = (delay_rise_s, delay_fall_s, rise_time_s, fall_time_s, idd_a)
        rows.append(
            (vdd, float(tb.vcont_v), float(tb.clock_period_s), *timings, all(math.isfinite(value) for value in timings))
        )
    vdd_v, vcont_v, period, delay_rise, delay_fall, rise_time, fall_time, current, valid = (
        np.asarray(column) for column in zip(*rows)
    )
    return AnalysisPropagation(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v.astype(np.float64),
        vcont_v=vcont_v.astype(np.float64),
        clock_period_s=period.astype(np.float64),
        delay_rise_s=delay_rise.astype(np.float64),
        delay_fall_s=delay_fall.astype(np.float64),
        rise_time_s=rise_time.astype(np.float64),
        fall_time_s=fall_time.astype(np.float64),
        idd_a=current.astype(np.float64),
        valid=valid.astype(np.bool_),
    )


def metrics(
    *,
    supply: AnalysisOscillation | AnalysisPropagation,
    control: AnalysisOscillation | AnalysisPropagation | None = None,
) -> Metrics:
    """The record's numbers: from the supply's runs (``supply``: in ``SUPPLY_SWEEP``'s order), at
    the PDK's supply, a ring's frequency, swing and duty cycle or a delay line's delays and output
    transitions, and either one's stage delay, power and energy per cycle, and its slowest stage
    delay over the supply; from the control's runs (``control``: in ``CONTROL_SWEEP``'s order, a chain with a
    control), its gain between the points either side of the nominal control (``GAIN_POINTS``)."""

    at = SUPPLY_SWEEP.index(1.0)
    stage_delay = supply.stage_delay_s
    kvco_hz_per_v = kdl_s_per_v = math.nan
    if control is not None:
        low, high = (next(i for i, step in enumerate(CONTROL_SWEEP) if math.isclose(step, p)) for p in GAIN_POINTS)
        span = control.vcont_v[high] - control.vcont_v[low]
        if isinstance(control, AnalysisOscillation):
            # [Razavi-PLL] Sec. 1.6, Fig. 1.33, pp. 27-28: K_VCO, the slope between two control
            # points, here in Hz/V
            # not in the reference texts: the points, 7/12 and 9/12 of the supply (a central difference)
            kvco_hz_per_v = float(
                (control.oscillation_frequency_hz[high] - control.oscillation_frequency_hz[low]) / span
            )
        else:
            # [Razavi-PLL] Sec. 11.1, p. 346: K_DL, the gain of a variable-delay stage, here as time per
            # volt (2 pi / T_CK of it in radians), of the line's mean delay
            kdl_s_per_v = float((control.delay_s[high] - control.delay_s[low]) / span)
    shared = {
        "stage_delay_s": float(stage_delay[at]),
        "average_power_w": float(supply.average_power_w[at]),
        "energy_per_cycle_j": float(supply.energy_per_cycle_j[at]),
        # [Razavi-PLL] Sec. 1.4.1, p. 12: a stage's delay falls as V_DD rises; the slowest over the
        # supply, NaN where a point was not timed or (a line) not valid: a failed point has no finite
        # worst case
        "stage_delay_max_supply_s": float(
            np.max(
                stage_delay if isinstance(supply, AnalysisOscillation) else np.where(supply.valid, stage_delay, np.nan)
            )
        ),
        "kvco_hz_per_v": kvco_hz_per_v,
        "kdl_s_per_v": kdl_s_per_v,
    }
    if isinstance(supply, AnalysisOscillation):
        return Metrics(
            oscillation_frequency_hz=float(supply.oscillation_frequency_hz[at]),
            swing_v=float(supply.swing_v[at]),
            duty_cycle=float(supply.duty_cycle[at]),
            **shared,
        )
    return Metrics(
        delay_rise_s=float(supply.delay_rise_s[at]),
        delay_fall_s=float(supply.delay_fall_s[at]),
        rise_time_s=float(supply.rise_time_s[at]),
        fall_time_s=float(supply.fall_time_s[at]),
        **shared,
    )
