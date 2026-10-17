"""Typed delay line and ring oscillator measurements, results, and analyses.

A ``MeasDelay`` is one transient of the shared delay testbench at one supply and control
voltage. A ring is measured like Usb2Phy's ``IloRingFreqTb`` (the period over ten cycles from
the fifth rising output edge, the supply current averaged over the same window); a delay line
like BAG's combinational delay benches (50 % delays and 10–90 % output transitions).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.delay.sim import DelayTbParams
from flow.delay.subckt import DelayNets, DelayParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasDelay(Meas):
    """Delay line or ring transient at one supply and control point: one record, all in ``wave``."""

    dut: DelayParams
    param: DelayTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDelayOscillation(Analysis):
    """Ring oscillation at each measured supply and control point.

    ``frequency_hz`` counts rising ``outp`` crossings of mid-supply from the fifth after enable
    (up to ten cycles); ``supply_current_a`` is the average over those cycles. A point whose
    output made fewer than three cycles is not oscillating and holds NaN.
    """

    vdd_v: np.ndarray
    control_v: np.ndarray
    frequency_hz: np.ndarray
    supply_current_a: np.ndarray
    swing_v: np.ndarray
    duty_cycle: np.ndarray
    oscillating: np.ndarray

    @property
    def power_w(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        return self.power_w / self.frequency_hz


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDelayPropagation(Analysis):
    """Delay line propagation at each measured supply and control point.

    ``rise_delay_s`` and ``fall_delay_s`` run from the second rising and falling ``inp`` edge
    to the following ``outp`` edge, both at mid-supply; ``output_rise_s`` and
    ``output_fall_s`` are that output's 10–90 % transitions; ``supply_current_a`` averages
    two input periods from the second rising edge.
    """

    vdd_v: np.ndarray
    control_v: np.ndarray
    period_s: np.ndarray
    rise_delay_s: np.ndarray
    fall_delay_s: np.ndarray
    output_rise_s: np.ndarray
    output_fall_s: np.ndarray
    supply_current_a: np.ndarray
    valid: np.ndarray

    @property
    def energy_per_cycle_j(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a * self.period_s


def analyze_delay_oscillation(measurements: Sequence[MeasDelay]) -> AnalysisDelayOscillation:
    """Measure ring frequency, supply current, output swing, and duty cycle at each point."""

    identity = measurement_identity(measurements)
    if not identity.dut.ring:
        raise ValueError("oscillation analysis requires a ring")
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("ring oscillation requires a waveform record")
        tb = measurement.param
        vdd = float(tb.vdd)
        output = wave.v[DelayNets.outp.name][0]
        rises = calc.cross(output, wave.time_s, vdd / 2, edge="rising")
        rises = rises[rises > float(tb.enable_delay_s)]
        # Usb2Phy's window: rise 5 to rise 15, shortened when a slow point made fewer cycles
        first = min(4, len(rises) // 3)
        last = min(first + 10, len(rises) - 1)
        if last - first < 3:
            rows.append((vdd, float(tb.control_v), math.nan, math.nan, math.nan, math.nan, False))
            continue
        start_s, stop_s = float(rises[first]), float(rises[last])
        window_v, window_s = calc.clip(output, wave.time_s, start_s, stop_s)
        current, current_s = calc.clip(wave.i[DelayNets.vdd.name][0], wave.time_s, start_s, stop_s)
        rows.append(
            (
                vdd,
                float(tb.control_v),
                (last - first) / (stop_s - start_s),
                calc.average(current, current_s),
                calc.peakToPeak(window_v),
                calc.average((window_v > vdd / 2).astype(np.float64), window_s),
                True,
            )
        )
    vdd_v, control_v, frequency, current, swing, duty, oscillating = (np.asarray(column) for column in zip(*rows))
    return AnalysisDelayOscillation(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v.astype(np.float64),
        control_v=control_v.astype(np.float64),
        frequency_hz=frequency.astype(np.float64),
        supply_current_a=current.astype(np.float64),
        swing_v=swing.astype(np.float64),
        duty_cycle=duty.astype(np.float64),
        oscillating=oscillating.astype(np.bool_),
    )


def analyze_delay_propagation(measurements: Sequence[MeasDelay]) -> AnalysisDelayPropagation:
    """Measure delay line rise and fall delay, output transitions, and supply current at each point."""

    identity = measurement_identity(measurements)
    if identity.dut.ring:
        raise ValueError("propagation analysis requires a delay line, not a ring")
    # an odd chain inverts: its output answers a rising input with a falling edge
    inverting = identity.dut.stages % 2 == 1
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("delay line propagation requires a waveform record")
        tb = measurement.param
        vdd = float(tb.vdd)
        source = wave.v[DelayNets.inp.name][0]
        output = wave.v[DelayNets.outp.name][0]
        rise_edge, fall_edge = ("falling", "rising") if inverting else ("rising", "falling")
        trigger_s, _response_s, rise_delay_s = calc.delay(
            source, output, wave.time_s, vdd / 2, vdd / 2, response_edge=rise_edge, occurrence=2
        )
        _trigger_s, _response_s, fall_delay_s = calc.delay(
            source,
            output,
            wave.time_s,
            vdd / 2,
            vdd / 2,
            trigger_edge="falling",
            response_edge=fall_edge,
            occurrence=2,
        )
        output_rise_s = calc.riseTime(output, wave.time_s, 0.0, vdd, occurrence=2)
        output_fall_s = calc.fallTime(output, wave.time_s, vdd, 0.0, occurrence=2)
        stop_s = trigger_s + 2 * float(tb.period_s)
        if math.isfinite(trigger_s) and stop_s <= float(wave.time_s[-1]):
            current, current_s = calc.clip(wave.i[DelayNets.vdd.name][0], wave.time_s, trigger_s, stop_s)
            supply_current_a = calc.average(current, current_s)
        else:
            supply_current_a = math.nan
        timings = (rise_delay_s, fall_delay_s, output_rise_s, output_fall_s, supply_current_a)
        rows.append(
            (vdd, float(tb.control_v), float(tb.period_s), *timings, all(math.isfinite(value) for value in timings))
        )
    vdd_v, control_v, period, rise, fall, output_rise, output_fall, current, valid = (
        np.asarray(column) for column in zip(*rows)
    )
    return AnalysisDelayPropagation(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v.astype(np.float64),
        control_v=control_v.astype(np.float64),
        period_s=period.astype(np.float64),
        rise_delay_s=rise.astype(np.float64),
        fall_delay_s=fall.astype(np.float64),
        output_rise_s=output_rise.astype(np.float64),
        output_fall_s=output_fall.astype(np.float64),
        supply_current_a=current.astype(np.float64),
        valid=valid.astype(np.bool_),
    )
