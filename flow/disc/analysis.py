"""Typed discriminator measurements, results, and analyses.

A ``MeasDisc`` is one transient of the discriminator testbench: the slow triangle across the
threshold, or one step from below it to an overdrive above it and back. The figures are each a calculator function of
``flow.analysis.calc``: the input where the output crosses mid-supply on the triangle's way up and
down (``cross``, ``value``), whose mean is the offset and whose difference the hysteresis; each
step edge's delay from the input's threshold crossing to the output's mid-supply crossing
(``delayMeasure``), whose rise over the overdrive is the timewalk; the output's transitions
(``riseTime``, ``fallTime``) and the supply current (``average``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.disc.sim import DiscTbParams
from flow.disc.subckt import DiscNets, DiscParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasDisc(Meas):
    """Discriminator transient: one record, all in ``wave``."""

    dut: DiscParams
    param: DiscTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDiscTrip(Analysis):
    """Discriminator trip points, one row per triangle.

    ``rise_trip_v`` and ``fall_trip_v`` are the input, less the threshold, where the output crosses
    mid-supply on the way up and down (NaN where it does not); a crossing lags the input by the
    delay, which at the triangle's slope moves each trip point outward by that much. ``inp_v`` and
    ``out_v`` hold each triangle's input, less the threshold, and output.
    """

    threshold_v: np.ndarray
    rise_trip_v: np.ndarray
    fall_trip_v: np.ndarray
    inp_v: np.ndarray
    out_v: np.ndarray

    @property
    def offset_v(self) -> np.ndarray:
        return (self.rise_trip_v + self.fall_trip_v) / 2

    @property
    def hysteresis_v(self) -> np.ndarray:
        return self.rise_trip_v - self.fall_trip_v


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDiscDelay(Analysis):
    """Discriminator timing at each step overdrive.

    ``rise_delay_s`` runs from the input's rising crossing of the threshold to the output's rising
    crossing of mid-supply, ``fall_delay_s`` likewise for the falling edges (NaN where the output
    does not switch); ``rise_time_s`` and ``fall_time_s`` are the output's 10–90 % transitions,
    ``supply_current_a`` the average over the period.
    """

    overdrive_v: np.ndarray
    rise_delay_s: np.ndarray
    fall_delay_s: np.ndarray
    rise_time_s: np.ndarray
    fall_time_s: np.ndarray
    supply_current_a: np.ndarray

    @property
    def timewalk_s(self) -> np.ndarray:
        """Each rising delay over that at the largest overdrive."""
        return self.rise_delay_s - self.rise_delay_s[np.argmax(self.overdrive_v)]


def analyze_disc_trip(measurements: Sequence[MeasDisc]) -> AnalysisDiscTrip:
    """Measure the input where the output switches on the triangle's way up and down."""

    identity = measurement_identity(measurements)
    if any(float(item.param.overdrive_v) for item in measurements):
        raise ValueError("discriminator trip points require the triangle bench")
    rows, traces = [], []
    for measurement in measurements:
        wave, tb = measurement.wave, measurement.param
        if wave is None:
            raise ValueError("discriminator trip points require a waveform record")
        time_s, threshold = wave.time_s, float(tb.threshold_v)
        inp, out = wave.v[DiscNets.inp.name][0] - threshold, wave.v[DiscNets.out.name][0]
        mid = float(tb.vdd) / 2
        rise_s = calc.cross(out, time_s, mid, edge="rising", occurrence=1)
        fall_s = calc.cross(out, time_s, mid, edge="falling", occurrence=1)
        rows.append(
            (
                threshold,
                calc.value(inp, time_s, rise_s) if math.isfinite(rise_s) else math.nan,
                calc.value(inp, time_s, fall_s) if math.isfinite(fall_s) else math.nan,
            )
        )
        traces.append((inp, out))
    threshold, rise, fall = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    length = min(len(inp) for inp, _ in traces)
    return AnalysisDiscTrip(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        threshold_v=threshold,
        rise_trip_v=rise,
        fall_trip_v=fall,
        inp_v=np.asarray([inp[:length] for inp, _ in traces], dtype=np.float64),
        out_v=np.asarray([out[:length] for _, out in traces], dtype=np.float64),
    )


def analyze_disc_delay(measurements: Sequence[MeasDisc]) -> AnalysisDiscDelay:
    """Measure each step edge's delay, the output's transitions and the supply current at each overdrive."""

    identity = measurement_identity(measurements)
    if not all(float(item.param.overdrive_v) for item in measurements):
        raise ValueError("discriminator delays require the step bench")
    rows = []
    for measurement in sorted(measurements, key=lambda item: float(item.param.overdrive_v)):
        wave, tb = measurement.wave, measurement.param
        if wave is None:
            raise ValueError("discriminator delays require a waveform record")
        time_s, threshold, vdd = wave.time_s, float(tb.threshold_v), float(tb.vdd)
        inp, out = wave.v[DiscNets.inp.name][0], wave.v[DiscNets.out.name][0]
        edges = {"value1": threshold, "value2": vdd / 2}
        rows.append(
            (
                float(tb.overdrive_v),
                calc.delayMeasure(inp, out, time_s, edge1="rising", edge2="rising", **edges),
                calc.delayMeasure(inp, out, time_s, edge1="falling", edge2="falling", **edges),
                calc.riseTime(out, time_s, 0.0, vdd, occurrence=1),
                calc.fallTime(out, time_s, vdd, 0.0, occurrence=1),
                calc.average(wave.i[DiscNets.vdd.name][0], time_s),
            )
        )
    overdrive, rise_delay, fall_delay, rise_time, fall_time, current = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True)
    )
    return AnalysisDiscDelay(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        overdrive_v=overdrive,
        rise_delay_s=rise_delay,
        fall_delay_s=fall_delay,
        rise_time_s=rise_time,
        fall_time_s=fall_time,
        supply_current_a=current,
    )
