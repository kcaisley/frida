"""Typed CML measurements, results, and analyses.

A ``MeasCml`` is one transient of the shared CML testbench. Every figure is taken over the
record's second half, after the start-up: the single-ended swing (half the differential
peak-to-peak), the delay from the driving input's differential crossing to the output's, and
whether the output holds its function's value where that is defined, at a level the next gate can
use: the right sign and at least half the inputs' differential swing (``vhigh - vlow``). A
buffer's and an XOR's just before each input change (one at least a quarter clock period after
the last); a latch's a quarter period after each closing clock edge (it captured the data) and
at the next opening one (it held it); a divider's at each rising one, alternating with one
output crossing between them (it divides, rather than following the clock or ringing).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.cml.sim import CmlTbParams
from flow.cml.subckt import CmlNets, CmlParams, Function


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCml(Meas):
    """CML transient at one clock period and tail drive: one record, all in ``wave``."""

    dut: CmlParams
    param: CmlTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCmlSwitching(Analysis):
    """CML switching at each measured point, over each record's second half.

    ``delay_s`` is the median over output crossings of the time since the latest driving input
    crossing (the clock for a divider, the data for a buffer, either for a latch or an XOR);
    ``correct_fraction`` the share of checked instants where the output held its function's
    value at a usable level (1 when it works); ``swing_v`` half the differential peak-to-peak.
    """

    vdd_v: np.ndarray
    clock_period_s: np.ndarray
    tail_current_a: np.ndarray
    swing_v: np.ndarray
    output_cm_v: np.ndarray
    delay_s: np.ndarray
    correct_fraction: np.ndarray
    supply_current_a: np.ndarray

    @property
    def power_w(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a


def analyze_cml_switching(measurements: Sequence[MeasCml]) -> AnalysisCmlSwitching:
    """Measure swing, output common mode, delay, transition ratio, and supply current at each point."""

    identity = measurement_identity(measurements)
    function = identity.dut.function
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("CML switching requires a waveform record")
        time_s = wave.time_s
        start_s, stop_s = float(time_s[-1]) / 2, float(time_s[-1])
        differential = {
            name: calc.clip(wave.v[f"{name}p"][0] - wave.v[f"{name}n"][0], time_s, start_s, stop_s)
            for name in ("in", "clk", "out")
        }
        crossings = {name: calc.cross(value, axis, 0.0, edge="either") for name, (value, axis) in differential.items()}
        drivers = {
            Function.BUFFER: ("in",),
            Function.DIVIDER: ("clk",),
            Function.LATCH: ("in", "clk"),
            Function.XOR: ("in", "clk"),
        }[function]
        launches = np.sort(np.concatenate([crossings[name] for name in drivers]))
        delays = [
            float(crossing - launches[launches < crossing][-1])
            for crossing in crossings["out"]
            if np.any(launches < crossing)
        ]
        # the function's value at each checked instant, against the output there: its sign, and
        # at least half the inputs' swing (a sign alone passes any low-passed square wave)
        period = float(measurement.param.clock_period_s)
        level = (float(measurement.param.vhigh) - float(measurement.param.vlow)) / 2
        data, clock, output = (differential[name] for name in ("in", "clk", "out"))

        def holds(instant: float, value: bool) -> bool:
            out = calc.value(*output, instant)
            return bool((out > 0) == value and abs(out) >= level)

        checks = []
        if function in (Function.BUFFER, Function.XOR):
            for previous, event in pairwise(launches):
                # the inputs' value over the interval, the output's at its end
                if event - previous >= period / 4:
                    middle = (previous + event) / 2
                    value = calc.value(*data, middle) > 0
                    if function == Function.XOR:
                        value = value != (calc.value(*clock, middle) > 0)
                    checks.append(holds(event, value))
        elif function == Function.LATCH:
            closing = calc.cross(*clock, 0.0, edge="falling")
            opening = calc.cross(*clock, 0.0, edge="rising")
            for edge in closing[closing + period / 4 < stop_s]:
                if not np.any(np.abs(crossings["in"] - edge) < period / 8):
                    value = calc.value(*data, edge) > 0
                    # captured a quarter period on, still held as the latch opens again
                    reopen = opening[opening > edge]
                    held = holds(reopen[0], value) if len(reopen) else True
                    checks.append(holds(edge + period / 4, value) and held)
        else:
            rising = calc.cross(*clock, 0.0, edge="rising")
            for before, after in pairwise(rising):
                flips = np.count_nonzero((crossings["out"] > before) & (crossings["out"] <= after))
                state = calc.value(*output, before) > 0
                checks.append(bool(flips == 1 and holds(before, state) and holds(after, not state)))
        output_v, _output_s = output
        common = calc.clip((wave.v[CmlNets.outp.name][0] + wave.v[CmlNets.outn.name][0]) / 2, time_s, start_s, stop_s)
        current = calc.clip(wave.i[CmlNets.vdd.name][0], time_s, start_s, stop_s)
        rows.append(
            (
                float(measurement.param.vdd),
                float(measurement.param.clock_period_s),
                float(measurement.param.tail_current_a),
                calc.peakToPeak(output_v) / 2,
                calc.average(*common),
                float(np.median(delays)) if delays else math.nan,
                float(np.mean(checks)) if checks else math.nan,
                calc.average(*current),
            )
        )
    vdd_v, period_s, drive, swing, common_v, delay, correct, current_a = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisCmlSwitching(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        clock_period_s=period_s,
        tail_current_a=drive,
        swing_v=swing,
        output_cm_v=common_v,
        delay_s=delay,
        correct_fraction=correct,
        supply_current_a=current_a,
    )
