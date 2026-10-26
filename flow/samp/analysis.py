"""The sampler's analyses: each from a run's measurement (``flow.pipeline.Meas``, its signals on
Spectre's own time axis) of the testbench with a stepped input, and the record's metrics.

A run tracks while ``clk`` is high, and its input steps once per period in the middle of each hold
phase. Every figure is the median over the periods after the first (whose track phase starts from
an arbitrary held value). A track phase settles from the step: its time constant, the switch's
effective resistance into the load, and what is left at the end (``analyze_track``). A hold phase
shows the pedestal the opening switch leaves, the droop before the input steps, and how much of
that step feeds through (``analyze_hold``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, measurement_identity

from .params import NOMINAL_VIN, VIN_SWEEP
from .subckt import Nets
from .types import AnalysisHold, AnalysisTrack


@analysis
def analyze_track(measurements: Sequence[Meas]) -> AnalysisTrack:
    """Measure the track phases' time constant, on-resistance, bandwidth, and remaining error at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vdd, transition = float(tb.vdd), float(tb.clock_transition_time_s)
        time_s = measurement.time_s
        clock, data, output = (measurement.v[net.name] for net in (Nets.clk, Nets.din, Nets.dout))
        falls = calc.cross(clock, time_s, vdd / 2, edge="falling")
        constants, errors = [], []
        for start in calc.cross(clock, time_s, vdd / 2, edge="rising")[1:]:
            ends = falls[falls > start]
            if not len(ends):
                continue
            end = float(ends[0])
            level = calc.value(data, time_s, (start + end) / 2)
            error, error_s = calc.clip(np.abs(output - level), time_s, float(start), end)
            # the time constant of the exponential itself, from its 1/e to its 1/e^2 point: counted
            # from the clock edge it would also hold the edge and the switch's turning on (some
            # 40 ps, which reads as 40 ohm into 1 pF and hides a wide switch's resistance)
            first = calc.cross(error, error_s, float(error[0]) / math.e, edge="falling")
            second = calc.cross(error, error_s, float(error[0]) / math.e**2, edge="falling")
            constants.append(float(second[0]) - float(first[0]) if len(first) and len(second) else math.nan)
            errors.append(calc.value(output, time_s, end - transition) - level)
        tau = float(np.median(constants)) if constants else math.nan
        rows.append(
            (
                vdd,
                float(tb.input_voltage),
                tau,
                tau / float(tb.cload),
                1 / (2 * math.pi * tau),
                float(np.median(errors)) if errors else math.nan,
            )
        )
    vdd_v, vin_v, tau_s, resistance, bandwidth, error_v = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisTrack(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        time_constant_s=tau_s,
        on_resistance_ohm=resistance,
        bandwidth_hz=bandwidth,
        track_error_v=error_v,
    )


@analysis
def analyze_hold(measurements: Sequence[Meas]) -> AnalysisHold:
    """Measure the hold phases' pedestal, droop, and input feedthrough at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb = measurement.param
        vdd, transition = float(tb.vdd), float(tb.clock_transition_time_s)
        time_s = measurement.time_s
        clock, data, output = (measurement.v[net.name] for net in (Nets.clk, Nets.din, Nets.dout))
        rises = calc.cross(clock, time_s, vdd / 2, edge="rising")
        steps = calc.cross(data, time_s, float(tb.input_voltage), edge="either")
        pedestals, droops, feedthroughs = [], [], []
        for fall in calc.cross(clock, time_s, vdd / 2, edge="falling")[1:]:
            following, stepped = rises[rises > fall], steps[steps > fall]
            if not len(following) or not len(stepped) or stepped[0] > following[0]:
                continue
            step, release = float(stepped[0]), float(following[0])
            held_s, before_s, after_s = (fall + step) / 2, step - transition, release - transition
            held = calc.value(output, time_s, held_s)
            before = calc.value(output, time_s, before_s)
            pedestals.append(held - calc.value(output, time_s, fall - transition))
            droops.append((before - held) / (before_s - held_s))
            feedthroughs.append(
                (calc.value(output, time_s, after_s) - before)
                / (calc.value(data, time_s, after_s) - calc.value(data, time_s, before_s))
            )
        rows.append(
            (
                vdd,
                float(tb.input_voltage),
                *(float(np.median(values)) if values else math.nan for values in (pedestals, droops, feedthroughs)),
            )
        )
    vdd_v, vin_v, pedestal_v, droop, feedthrough = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisHold(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        pedestal_v=pedestal_v,
        droop_v_per_s=droop,
        feedthrough=feedthrough,
    )


def metrics(*, track: AnalysisTrack, hold: AnalysisHold, supply: AnalysisTrack) -> dict[str, float]:
    """The record's numbers: from the input level's runs (``track``, ``hold``: in ``VIN_SWEEP``'s
    order) the on-resistance, bandwidth, track error, pedestal, droop and feedthrough at mid-supply
    input, the largest on-resistance and pedestal where a point settled, the input range over which
    it settles; from the supply's (``supply``) the largest on-resistance."""

    nominal = VIN_SWEEP.index(NOMINAL_VIN)
    settled = np.isfinite(track.on_resistance_ohm)
    # each the largest magnitude where the point settled to a value
    largest = {
        name: float(finite.max()) if finite.size else math.nan
        for name, values in (
            ("ron", track.on_resistance_ohm),
            ("pedestal", hold.pedestal_v),
            ("supply", supply.on_resistance_ohm),
        )
        for finite in (np.abs(values[np.isfinite(values)]),)
    }
    feedthrough_db = 20 * np.log10(np.abs(hold.feedthrough))
    return {
        "ron_ohm": float(track.on_resistance_ohm[nominal]),
        "ron_max_ohm": largest["ron"],
        "input_range_v": float(np.ptp(track.vin_v[settled])) if settled.any() else 0.0,
        "bandwidth_hz": float(track.bandwidth_hz[nominal]),
        "track_error_v": float(track.track_error_v[nominal]),
        "pedestal_v": float(hold.pedestal_v[nominal]),
        "pedestal_max_v": largest["pedestal"],
        "droop_v_s": float(hold.droop_v_per_s[nominal]),
        "feedthrough_db": float(feedthrough_db[nominal]),
        "ron_max_supply_ohm": largest["supply"],
    }
