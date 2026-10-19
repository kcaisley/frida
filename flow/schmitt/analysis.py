"""Typed Schmitt trigger measurements, results, and analyses.

A ``MeasSchmitt`` is one transient of the Schmitt trigger testbench: the slow triangle, or one
step up and back down. The figures are each a calculator function of ``flow.analysis.calc``: the
input where the output crosses mid-supply on the triangle's way up and down (``cross``,
``value``), whose difference is the hysteresis; each step edge's delay at mid-supply
(``delayMeasure``), the output's transitions (``riseTime``, ``fallTime``) and the supply energy
over the period (``integ``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.schmitt.sim import SchmittTbParams
from flow.schmitt.subckt import SchmittNets, SchmittParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasSchmitt(Meas):
    """Schmitt trigger transient: one record, all in ``wave``."""

    dut: SchmittParams
    param: SchmittTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSchmittTrip(Analysis):
    """Schmitt trigger trip points, one row per triangle (supply).

    ``rise_trip_v`` and ``fall_trip_v`` are the input where the output crosses mid-supply while
    the input rises and while it falls (NaN where it does not); ``inp_v`` and ``out_v`` hold each
    triangle's input and output.
    """

    vdd_v: np.ndarray
    rise_trip_v: np.ndarray
    fall_trip_v: np.ndarray
    inp_v: np.ndarray
    out_v: np.ndarray

    @property
    def hysteresis_v(self) -> np.ndarray:
        return self.rise_trip_v - self.fall_trip_v


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSchmittDelay(Analysis):
    """Schmitt trigger step timing at each step point.

    ``rise_delay_s`` runs from the input's rising mid-supply crossing to the output's (falling for
    the inverting trigger), ``fall_delay_s`` from its falling one; ``out_rise_time_s`` and
    ``out_fall_time_s`` are the output's 10–90 % transitions, ``energy_per_cycle_j`` the supply
    energy over the period.
    """

    vdd_v: np.ndarray
    rise_delay_s: np.ndarray
    fall_delay_s: np.ndarray
    out_rise_time_s: np.ndarray
    out_fall_time_s: np.ndarray
    energy_per_cycle_j: np.ndarray


def _output_edges(dut: SchmittParams) -> tuple[str, str]:
    """The output's edge on the input's rising and falling ones."""
    return ("rising", "falling") if dut.buffer else ("falling", "rising")


def analyze_schmitt_trip(measurements: Sequence[MeasSchmitt]) -> AnalysisSchmittTrip:
    """Measure the input where the output switches on the triangle's way up and down."""

    identity = measurement_identity(measurements)
    if any(item.param.step for item in measurements):
        raise ValueError("Schmitt trigger trip points require the triangle bench")
    on_rise, on_fall = _output_edges(identity.dut)
    rows, traces = [], []
    for measurement in sorted(measurements, key=lambda item: float(item.param.vdd)):
        wave, vdd = measurement.wave, float(measurement.param.vdd)
        if wave is None:
            raise ValueError("Schmitt trigger trip points require a waveform record")
        time_s, inp, out = wave.time_s, wave.v[SchmittNets.inp.name][0], wave.v[SchmittNets.out.name][0]
        # the input's peak splits the triangle's way up from its way down
        peak_s = calc.xmax(inp, time_s)
        up_s = calc.cross(out, time_s, vdd / 2, edge=on_rise)
        down_s = calc.cross(out, time_s, vdd / 2, edge=on_fall)
        up_s, down_s = up_s[up_s < peak_s], down_s[down_s > peak_s]
        rows.append(
            (
                vdd,
                calc.value(inp, time_s, float(up_s[0])) if len(up_s) else math.nan,
                calc.value(inp, time_s, float(down_s[0])) if len(down_s) else math.nan,
            )
        )
        traces.append((inp, out))
    vdd_v, rise, fall = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    length = min(len(inp) for inp, _ in traces)
    return AnalysisSchmittTrip(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        rise_trip_v=rise,
        fall_trip_v=fall,
        inp_v=np.asarray([inp[:length] for inp, _ in traces], dtype=np.float64),
        out_v=np.asarray([out[:length] for _, out in traces], dtype=np.float64),
    )


def analyze_schmitt_delay(measurements: Sequence[MeasSchmitt]) -> AnalysisSchmittDelay:
    """Measure each step edge's delay, the output's transitions and the energy per cycle."""

    identity = measurement_identity(measurements)
    if not all(item.param.step for item in measurements):
        raise ValueError("Schmitt trigger delays require the step bench")
    on_rise, on_fall = _output_edges(identity.dut)
    rows = []
    for measurement in measurements:
        wave, vdd = measurement.wave, float(measurement.param.vdd)
        if wave is None:
            raise ValueError("Schmitt trigger delays require a waveform record")
        time_s, inp, out = wave.time_s, wave.v[SchmittNets.inp.name][0], wave.v[SchmittNets.out.name][0]
        edges = {"value1": vdd / 2, "value2": vdd / 2}
        rows.append(
            (
                vdd,
                calc.delayMeasure(inp, out, time_s, edge1="rising", edge2=on_rise, **edges),
                calc.delayMeasure(inp, out, time_s, edge1="falling", edge2=on_fall, **edges),
                calc.riseTime(out, time_s, 0.0, vdd, occurrence=1),
                calc.fallTime(out, time_s, vdd, 0.0, occurrence=1),
                vdd * calc.integ(wave.i[SchmittNets.vdd.name][0], time_s),
            )
        )
    vdd_v, rise, fall, out_rise, out_fall, energy = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True)
    )
    return AnalysisSchmittDelay(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        rise_delay_s=rise,
        fall_delay_s=fall,
        out_rise_time_s=out_rise,
        out_fall_time_s=out_fall,
        energy_per_cycle_j=energy,
    )
