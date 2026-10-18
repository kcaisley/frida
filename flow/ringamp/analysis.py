"""Typed ring amplifier measurements, results, and analyses.

A ``MeasRingamp`` is one transient of the shared ring amplifier testbench, open loop (a slow
triangle on the input) or closed loop (a step through the input capacitor, a gain of -1). Open
loop: the transfer curve and supply current on the rising ramp, the trip point and gain, and the
trip's shift on the falling ramp. Closed loop, after BAG's settling measurement: the output step
against the ideal, the time to settle within 1 % of it, the overshoot, and the supply current
once settled (the dead zone's purpose) against the charge spent settling.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.ringamp.sim import RingampTbParams
from flow.ringamp.subckt import RingampNets, RingampParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasRingamp(Meas):
    """Ring amplifier transient at one dead-zone bias and step: one record, all in ``wave``."""

    dut: RingampParams
    param: RingampTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisRingampTransfer(Analysis):
    """Open-loop transfer at each dead-zone bias (``dead_zone_v``, biasn's drive above vss).

    ``trip_v`` is the input where the output crosses mid-supply on the rising ramp,
    ``hysteresis_v`` the falling ramp's trip minus it, ``gain_v_per_v`` the steepest slope;
    ``output_v`` and ``current_a`` hold the rising ramp's transfer and supply current, one row per
    bias, over ``input_v``.
    """

    dead_zone_v: np.ndarray
    trip_v: np.ndarray
    hysteresis_v: np.ndarray
    gain_v_per_v: np.ndarray
    current_at_trip_a: np.ndarray
    peak_current_a: np.ndarray
    input_v: np.ndarray
    output_v: np.ndarray
    current_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisRingampSettling(Analysis):
    """Closed-loop settling at each dead-zone bias and step.

    ``output_step_v`` is the output's change from before the step to the record's last
    nanosecond, ``gain_error`` its deviation from -cin/cfb times the step; ``settling_time_s``
    from the step to staying within 1 % of that change; ``overshoot`` the excursion beyond the
    final value, relative to the change; ``settling_charge_c`` the supply charge above the
    quiescent current from the step on.
    """

    dead_zone_v: np.ndarray
    step_v: np.ndarray
    output_step_v: np.ndarray
    gain_error: np.ndarray
    settling_time_s: np.ndarray
    overshoot: np.ndarray
    quiescent_current_a: np.ndarray
    settling_charge_c: np.ndarray


def analyze_ringamp_transfer(measurements: Sequence[MeasRingamp]) -> AnalysisRingampTransfer:
    """Measure the open-loop transfer, trip point, hysteresis, gain, and supply current at each bias."""

    identity = measurement_identity(measurements)
    if any(item.param.closed_loop for item in measurements):
        raise ValueError("ring amplifier transfer requires open-loop records")
    tb = measurements[0].param
    input_v = np.linspace(float(tb.vcm) - float(tb.vstep), float(tb.vcm) + float(tb.vstep), 121)
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("ring amplifier transfer requires a waveform record")
        tb = measurement.param
        vdd, period = float(tb.vdd), float(tb.period_s)
        time_s = wave.time_s
        source, output = wave.v[RingampNets.inp.name][0], wave.v[RingampNets.out.name][0]
        current = wave.i[RingampNets.vdd.name][0]
        # the rising ramp runs one period from half a period, the falling one the next period
        rising = (time_s > period / 2) & (time_s < 1.5 * period)
        falling = (time_s > 1.5 * period) & (time_s < 2.5 * period)
        # a dead zone wider than the input range never turns the output stage on: no trip
        trip_up_s = calc.cross(output[rising], time_s[rising], vdd / 2, edge="falling", occurrence=1)
        trip_down_s = calc.cross(output[falling], time_s[falling], vdd / 2, edge="rising", occurrence=1)
        trip_up = calc.value(source[rising], time_s[rising], trip_up_s) if math.isfinite(trip_up_s) else math.nan
        trip_down = (
            calc.value(source[falling], time_s[falling], trip_down_s) if math.isfinite(trip_down_s) else math.nan
        )
        transfer = calc.value(output[rising], source[rising], input_v)
        drawn = calc.value(current[rising], source[rising], input_v)
        rows.append(
            (
                float(tb.biasn),
                trip_up,
                trip_down - trip_up,
                calc.ymax(np.abs(np.gradient(transfer, input_v))),
                calc.value(drawn, input_v, trip_up) if math.isfinite(trip_up) else math.nan,
                calc.ymax(drawn),
                transfer,
                drawn,
            )
        )
    dead_zone, trip, hysteresis, gain, trip_current, peak, output_v, current_a = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisRingampTransfer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        dead_zone_v=dead_zone,
        trip_v=trip,
        hysteresis_v=hysteresis,
        gain_v_per_v=gain,
        current_at_trip_a=trip_current,
        peak_current_a=peak,
        input_v=input_v,
        output_v=output_v,
        current_a=current_a,
    )


def analyze_ringamp_settling(measurements: Sequence[MeasRingamp]) -> AnalysisRingampSettling:
    """Measure the closed-loop output step, gain error, settling time, overshoot, and currents at each point."""

    identity = measurement_identity(measurements)
    if not all(item.param.closed_loop for item in measurements):
        raise ValueError("ring amplifier settling requires closed-loop records")
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("ring amplifier settling requires a waveform record")
        tb = measurement.param
        time_s = wave.time_s
        output, current = wave.v[RingampNets.out.name][0], wave.i[RingampNets.vdd.name][0]
        step_s = float(tb.step_delay_s) + float(tb.transition_time_s) / 2
        stop_s = float(time_s[-1])
        initial = calc.average(*calc.clip(output, time_s, step_s - 0.5e-9, step_s))
        final = calc.average(*calc.clip(output, time_s, stop_s - 1e-9, stop_s))
        change = final - initial
        ideal = -float(tb.step_v) * float(tb.cin) / float(tb.cfb)
        after_v, after_s = calc.clip(output, time_s, step_s, stop_s)
        settled_s = calc.settlingTime(after_v, after_s, initial=initial, final=final, percent_of_step=1.0)
        quiescent = calc.average(*calc.clip(current, time_s, stop_s - 1e-9, stop_s))
        drawn, drawn_s = calc.clip(current, time_s, step_s, stop_s)
        rows.append(
            (
                float(tb.biasn),
                float(tb.step_v),
                change,
                change / ideal - 1,
                settled_s - step_s if math.isfinite(settled_s) else math.nan,
                max(calc.overshoot(after_v, after_s, initial, final), 0.0) / 100 if change else math.nan,
                quiescent,
                calc.integ(drawn - quiescent, drawn_s),
            )
        )
    dead_zone, step, change_v, error, settling, overshoot, quiescent_a, charge = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisRingampSettling(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        dead_zone_v=dead_zone,
        step_v=step,
        output_step_v=change_v,
        gain_error=error,
        settling_time_s=settling,
        overshoot=overshoot,
        quiescent_current_a=quiescent_a,
        settling_charge_c=charge,
    )
