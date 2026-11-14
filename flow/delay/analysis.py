"""The delay line and ring oscillator's analyses: each from the runs' measurements
(``flow.pipeline.Meas``, their signals on Spectre's own time axis) of the shared testbench, one run
at each supply or control point, and the record's metrics.

A ring is measured by its period over ten cycles from the fifth rising output edge, the supply
current averaged over the same window (``analyze_oscillation``); a delay line by its 50 % delays
and 10-90 % output transitions (``analyze_propagation``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, measurement_identity

from .params import CONTROL_SWEEP, GAIN_POINTS, SUPPLY_SWEEP
from .subckt import Nets
from .types import AnalysisOscillation, AnalysisPropagation, Metrics


@analysis
def analyze_oscillation(measurements: Sequence[Meas]) -> AnalysisOscillation:
    """Measure ring frequency, supply current, output swing, and duty cycle at each point."""

    identity = measurement_identity(measurements)
    if not identity.dut.ring:
        raise ValueError("oscillation analysis requires a ring")
    rows = []
    for measurement in measurements:
        time_s = measurement.time_s
        if not len(time_s):
            raise ValueError("ring oscillation requires a transient")
        tb = measurement.tb
        vdd = float(tb.vdd)
        output = measurement.v[Nets.outp.name]
        rises = calc.cross(output, time_s, vdd / 2, edge="rising")
        rises = rises[rises > float(tb.enable_delay_s)]
        # the window: rise 5 to rise 15, shortened when a slow point made fewer cycles
        first = min(4, len(rises) // 3)
        last = min(first + 10, len(rises) - 1)
        if last - first < 3:
            rows.append((vdd, float(tb.vcont_v), math.nan, math.nan, math.nan, math.nan, False))
            continue
        start_s, stop_s = float(rises[first]), float(rises[last])
        window_v, window_s = calc.clip(output, time_s, start_s, stop_s)
        current, current_s = calc.clip(measurement.i[Nets.vdd.name], time_s, start_s, stop_s)
        rows.append(
            (
                vdd,
                float(tb.vcont_v),
                # [Razavi-PLL] Sec. 3.1.1, p. 64: oscillation frequency, the cycles over their time
                (last - first) / (stop_s - start_s),
                calc.average(current, current_s),
                calc.peakToPeak(window_v),
                # [Razavi-PLL] Sec. 11.10, p. 365: duty cycle, the time above mid-supply over the window
                calc.average((window_v > vdd / 2).astype(np.float64), window_s),
                True,
            )
        )
    vdd_v, vcont_v, frequency, current, swing, duty, oscillating = (np.asarray(column) for column in zip(*rows))
    return AnalysisOscillation(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v.astype(np.float64),
        vcont_v=vcont_v.astype(np.float64),
        oscillation_frequency_hz=frequency.astype(np.float64),
        idd_a=current.astype(np.float64),
        swing_v=swing.astype(np.float64),
        duty_cycle=duty.astype(np.float64),
        oscillating=oscillating.astype(np.bool_),
    )


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
        # [Baker] Fig. 10.9, p. 333: propagation delay between the 50 % points of input and output
        answer_rising, answer_falling = ("falling", "rising") if inverting else ("rising", "falling")
        trigger_s, _response_s, after_rising_s = calc.delay(
            source, output, time_s, vdd / 2, vdd / 2, response_edge=answer_rising, occurrence=2
        )
        _trigger_s, _response_s, after_falling_s = calc.delay(
            source,
            output,
            time_s,
            vdd / 2,
            vdd / 2,
            trigger_edge="falling",
            response_edge=answer_falling,
            occurrence=2,
        )
        # each delay by its output edge: an inverting chain's output rises after a falling input
        delay_rise_s, delay_fall_s = (
            (after_falling_s, after_rising_s) if inverting else (after_rising_s, after_falling_s)
        )
        # [Baker] Fig. 10.9, p. 333: output rise and fall times, 10 to 90 % of the supply
        rise_time_s = calc.riseTime(output, time_s, 0.0, vdd, occurrence=2)
        fall_time_s = calc.fallTime(output, time_s, vdd, 0.0, occurrence=2)
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
    the PDK's supply, a ring's frequency and swing or a delay line's delays and output transitions,
    and either one's stage delay, power and energy per cycle, and its slowest stage delay over the
    supply; from the control's runs (``control``: in ``CONTROL_SWEEP``'s order, a chain with a
    control), its gain between the points either side of the nominal control (``GAIN_POINTS``)."""

    at = SUPPLY_SWEEP.index(1.0)
    stage_delay = supply.stage_delay_s
    kvco_hz_per_v = kdl_s_per_v = math.nan
    if control is not None:
        low, high = (next(i for i, step in enumerate(CONTROL_SWEEP) if math.isclose(step, p)) for p in GAIN_POINTS)
        span = control.vcont_v[high] - control.vcont_v[low]
        if isinstance(control, AnalysisOscillation):
            # [Razavi-PLL] Sec. 1.6, p. 27: the gain of a VCO, here in Hz/V
            kvco_hz_per_v = float(
                (control.oscillation_frequency_hz[high] - control.oscillation_frequency_hz[low]) / span
            )
        else:
            # [Razavi-PLL] Sec. 11.1, p. 346: the gain of a variable-delay stage, here as time
            kdl_s_per_v = float((control.delay_s[high] - control.delay_s[low]) / span)
    shared = {
        "stage_delay_s": float(stage_delay[at]),
        "average_power_w": float(supply.average_power_w[at]),
        "energy_per_cycle_j": float(supply.energy_per_cycle_j[at]),
        "stage_delay_max_supply_s": float(np.nanmax(stage_delay)),
        "kvco_hz_per_v": kvco_hz_per_v,
        "kdl_s_per_v": kdl_s_per_v,
    }
    if isinstance(supply, AnalysisOscillation):
        return Metrics(
            oscillation_frequency_hz=float(supply.oscillation_frequency_hz[at]),
            swing_v=float(supply.swing_v[at]),
            **shared,
        )
    return Metrics(
        delay_rise_s=float(supply.delay_rise_s[at]),
        delay_fall_s=float(supply.delay_fall_s[at]),
        rise_time_s=float(supply.rise_time_s[at]),
        fall_time_s=float(supply.fall_time_s[at]),
        **shared,
    )
