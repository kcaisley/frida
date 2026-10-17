"""Typed level shifter measurements, results, and analyses.

A ``MeasLvShift`` is one transient of the shared level shifter testbench. The figures follow
bag3_digital's level shifter benches, on the case's output (bufp for a buffered shifter, outp
otherwise): the delays from the input's crossing at half the low supply to the output's at half
vdd, the share of input edges the output followed, its levels, the energy per input period from
both supplies, and the idle supply current once the output has settled.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.lvshift.sim import LvShiftTbParams
from flow.lvshift.subckt import LvShiftNets, LvShiftParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasLvShift(Meas):
    """Level shifter transient at one pair of supplies: one record, all in ``wave``."""

    dut: LvShiftParams
    param: LvShiftTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisLvshiftSwitching(Analysis):
    """Level shifter switching at each pair of supplies.

    Delays are medians over the input edges the output followed within half a period;
    ``energy_per_cycle_j`` sums both supplies over one input period from the second rising
    input edge; ``static_current_a`` is vdd's larger average current over the last tenth of a
    half period before an input edge, the output settled high or low.
    """

    vdd_v: np.ndarray
    vddl_v: np.ndarray
    rise_delay_s: np.ndarray
    fall_delay_s: np.ndarray
    switched_fraction: np.ndarray
    output_high_v: np.ndarray
    output_low_v: np.ndarray
    energy_per_cycle_j: np.ndarray
    static_current_a: np.ndarray


def analyze_lvshift_switching(measurements: Sequence[MeasLvShift]) -> AnalysisLvshiftSwitching:
    """Measure delays, the edges followed, output levels, energy per cycle, and idle current at each point."""

    identity = measurement_identity(measurements)
    output_name = LvShiftNets.bufp.name if identity.dut.buffers else LvShiftNets.outp.name
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("level shifter analysis requires a waveform record")
        tb = measurement.param
        vdd, vddl, period = float(tb.vdd), float(tb.vddl), float(tb.period_s)
        time_s = wave.time_s
        source = wave.v[LvShiftNets.inp.name][0]
        output = wave.v[output_name][0]
        delays = {}
        for edge in ("rising", "falling"):
            launches = calc.cross(source, time_s, vddl / 2, edge=edge)
            responses = calc.cross(output, time_s, vdd / 2, edge=edge)
            delays[edge] = [
                float(responses[responses > launch][0] - launch)
                for launch in launches
                if np.any((responses > launch) & (responses < launch + period / 2))
            ]
            delays[edge, "launches"] = len(launches)
        launches = delays["rising", "launches"] + delays["falling", "launches"]
        followed = len(delays["rising"]) + len(delays["falling"])
        rises = calc.cross(source, time_s, vddl / 2, edge="rising")
        if len(rises) >= 2 and rises[1] + period <= time_s[-1]:
            start_s = float(rises[1])
            energy = 0.0
            for name, level in ((LvShiftNets.vdd.name, vdd), (LvShiftNets.vddl.name, vddl)):
                current, current_s = calc.clip(wave.i[name][0], time_s, start_s, start_s + period)
                energy += level * calc.average(current, current_s) * period
        else:
            energy = math.nan
        # idle: the last tenth of each half period, before the next input edge
        idle = [
            calc.average(*calc.clip(wave.i[LvShiftNets.vdd.name][0], time_s, edge - 0.05 * period, edge))
            for edge in calc.cross(source, time_s, vddl / 2, edge="either")
            if edge > period
        ]
        settled_v, _settled_s = calc.clip(output, time_s, period / 2, float(time_s[-1]))
        rows.append(
            (
                vdd,
                vddl,
                float(np.median(delays["rising"])) if delays["rising"] else math.nan,
                float(np.median(delays["falling"])) if delays["falling"] else math.nan,
                followed / launches if launches else math.nan,
                calc.ymax(settled_v),
                calc.ymin(settled_v),
                energy,
                max(idle) if idle else math.nan,
            )
        )
    vdd_v, vddl_v, rise, fall, followed_share, high, low, energy_j, idle_a = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisLvshiftSwitching(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vddl_v=vddl_v,
        rise_delay_s=rise,
        fall_delay_s=fall,
        switched_fraction=followed_share,
        output_high_v=high,
        output_low_v=low,
        energy_per_cycle_j=energy_j,
        static_current_a=idle_a,
    )
