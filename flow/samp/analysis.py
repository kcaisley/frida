"""Typed sampler measurements, results, and analyses.

A ``MeasSamp`` is one transient of the sampler testbench with a stepped input: it tracks while
``clk`` is high, and the input steps once per period in the middle of each hold phase. Every
figure is the median over the periods after the first (whose track phase starts from an arbitrary
held value). A track phase settles from the step: its time constant, the switch's effective
resistance into the load, and what is left at the end. A hold phase shows the pedestal the opening
switch leaves, the droop before the input steps, and how much of that step feeds through.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.samp.sim import SampTbParams
from flow.samp.subckt import SampNets, SampParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasSamp(Meas):
    """Sampler trials: one row per trial; the observations are all in ``wave``."""

    dut: SampParams
    param: SampTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSampTrack(Analysis):
    """Sampler tracking at each measured point.

    ``time_constant_s`` is the time from the track phase's clock edge until the output's error
    to the input falls to 1/e of its start; ``on_resistance_ohm`` that over the load
    capacitance (the switch's own capacitance adds to it, so it bounds the resistance from
    above); ``bandwidth_hz`` 1/(2 pi tau); ``track_error_v`` the output minus the input as the
    clock starts to fall. NaN where the output never settles that far.
    """

    vdd_v: np.ndarray
    vin_v: np.ndarray
    time_constant_s: np.ndarray
    on_resistance_ohm: np.ndarray
    bandwidth_hz: np.ndarray
    track_error_v: np.ndarray


def analyze_samp_track(measurements: Sequence[MeasSamp]) -> AnalysisSampTrack:
    """Measure the track phases' time constant, on-resistance, bandwidth, and remaining error at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("sampler tracking requires a waveform record")
        tb = measurement.param
        vdd, transition = float(tb.vdd), float(tb.clock_transition_time_s)
        time_s = wave.time_s
        clock, data, output = (wave.v[net.name][0] for net in (SampNets.clk, SampNets.din, SampNets.dout))
        falls = calc.cross(clock, time_s, vdd / 2, edge="falling")
        constants, errors = [], []
        for start in calc.cross(clock, time_s, vdd / 2, edge="rising")[1:]:
            ends = falls[falls > start]
            if not len(ends):
                continue
            end = float(ends[0])
            level = calc.value(data, time_s, (start + end) / 2)
            error, error_s = calc.clip(np.abs(output - level), time_s, float(start), end)
            settled = calc.cross(error, error_s, float(error[0]) / math.e, edge="falling")
            constants.append(float(settled[0]) - float(start) if len(settled) else math.nan)
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
    return AnalysisSampTrack(
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


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSampHold(Analysis):
    """Sampler holding at each measured point.

    ``pedestal_v`` is the held output halfway to the input step minus the output just before
    the clock falls (the charge the opening switch dumps, and its clock feedthrough);
    ``droop_v_per_s`` the held output's slope from there to the step; ``feedthrough`` the held
    output's change over the input's step while the switch is off (V/V).
    """

    vdd_v: np.ndarray
    vin_v: np.ndarray
    pedestal_v: np.ndarray
    droop_v_per_s: np.ndarray
    feedthrough: np.ndarray


def analyze_samp_hold(measurements: Sequence[MeasSamp]) -> AnalysisSampHold:
    """Measure the hold phases' pedestal, droop, and input feedthrough at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("sampler hold requires a waveform record")
        tb = measurement.param
        vdd, transition = float(tb.vdd), float(tb.clock_transition_time_s)
        time_s = wave.time_s
        clock, data, output = (wave.v[net.name][0] for net in (SampNets.clk, SampNets.din, SampNets.dout))
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
    return AnalysisSampHold(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_v=vin_v,
        pedestal_v=pedestal_v,
        droop_v_per_s=droop,
        feedthrough=feedthrough,
    )
