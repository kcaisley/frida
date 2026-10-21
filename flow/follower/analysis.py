"""Typed follower measurements, results, and analyses.

A ``MeasFollower`` is one operating point and AC response of the follower testbench, the output
per volt of input or, with the output test current, per ampere into the output (the output
impedance), and the output per volt of supply (Spectre's ``xf``). Its operating point (supply
current, output level) is in the run readbacks. A ``MeasFollowerStep`` is the transient of a large
input step up and back down, whose output gives the slew rates and settling. Every figure is a calculator function of ``flow.analysis.calc``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.follower.sim import FollowerTbParams
from flow.follower.subckt import FollowerNets, FollowerParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasFollower(Meas):
    """Follower AC response at one input level: one row per frequency."""

    dut: FollowerParams
    param: FollowerTbParams
    frequency_hz: np.ndarray
    magnitude: np.ndarray
    phase_deg: np.ndarray
    supply_gain_v_per_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasFollowerStep(Meas):
    """Follower transient of one input step up and back down: one record, all in ``wave``."""

    dut: FollowerParams
    param: FollowerTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisFollowerTransfer(Analysis):
    """Follower transfer at each input level.

    ``vout_v`` is the operating-point output, ``gain_v_per_v`` the response at the lowest
    frequency, ``bandwidth_hz`` where it has fallen 3 dB (``bandwidth``, NaN beyond the sweep),
    ``psrr_db`` that gain over the supply's to the output there, ``response_db`` the whole
    response, one row per point and one column per ``frequency_hz``.
    """

    vin_v: np.ndarray
    vout_v: np.ndarray
    gain_v_per_v: np.ndarray
    bandwidth_hz: np.ndarray
    psrr_db: np.ndarray
    supply_current_a: np.ndarray
    frequency_hz: np.ndarray
    response_db: np.ndarray

    @property
    def level_shift_v(self) -> np.ndarray:
        return self.vin_v - self.vout_v


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisFollowerImpedance(Analysis):
    """Follower output impedance at each input level: ``impedance_ohm`` at the lowest frequency,
    ``impedance_db_ohm`` (20 log10 of ohms) over ``frequency_hz``, one row per point."""

    vin_v: np.ndarray
    impedance_ohm: np.ndarray
    frequency_hz: np.ndarray
    impedance_db_ohm: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisFollowerSlew(Analysis):
    """Follower large-signal step response at each step point (the nominal input).

    ``low_v`` and ``high_v`` are the output's settled levels before the rising and falling input
    steps, ``rise_slew_v_per_s`` and ``fall_slew_v_per_s`` the output's 10–90 % slopes between them
    (``slewrate``; the fall's negative), ``rise_settling_s`` and ``fall_settling_s`` the time from
    each input edge until the output stays within 1 % of the step (``settlingTime``),
    ``rise_overshoot`` and ``fall_overshoot`` how far it passes the final level, a fraction of the
    step (``overshoot``), ``supply_current_a`` the average over the period. The edges are NaN where the
    output moves less than a tenth of the step.
    """

    vin_v: np.ndarray
    step_v: np.ndarray
    low_v: np.ndarray
    high_v: np.ndarray
    rise_slew_v_per_s: np.ndarray
    fall_slew_v_per_s: np.ndarray
    rise_settling_s: np.ndarray
    fall_settling_s: np.ndarray
    rise_overshoot: np.ndarray
    fall_overshoot: np.ndarray
    supply_current_a: np.ndarray


def analyze_follower_transfer(measurements: Sequence[MeasFollower]) -> AnalysisFollowerTransfer:
    """Measure output level, small-signal gain, bandwidth, PSRR, and supply current at each input level."""

    identity = measurement_identity(measurements)
    if any(item.param.output_test for item in measurements):
        raise ValueError("follower transfer requires the AC stimulus on the input")
    frequency_hz = measurements[0].frequency_hz
    if any(not np.array_equal(item.frequency_hz, frequency_hz) for item in measurements):
        raise ValueError("follower analysis requires one frequency sweep for every point")
    rows = []
    for measurement in measurements:
        readbacks = measurement.info.readbacks
        rows.append(
            (
                float(measurement.param.vin),
                float(readbacks["op_vout_v"]),
                float(measurement.magnitude[0]),
                calc.bandwidth(measurement.magnitude, frequency_hz, 3.0, "low"),
                float(calc.db20(measurement.magnitude[0]) - calc.db20(measurement.supply_gain_v_per_v[0])),
                float(readbacks["op_supply_current_a"]),
                calc.db20(measurement.magnitude),
            )
        )
    vin_v, vout_v, gain, bandwidth, psrr, current, response_db = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisFollowerTransfer(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=vin_v,
        vout_v=vout_v,
        gain_v_per_v=gain,
        bandwidth_hz=bandwidth,
        psrr_db=psrr,
        supply_current_a=current,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        response_db=response_db,
    )


def analyze_follower_impedance(measurements: Sequence[MeasFollower]) -> AnalysisFollowerImpedance:
    """Measure the output impedance at each input level from the output test current's response."""

    identity = measurement_identity(measurements)
    if not all(item.param.output_test for item in measurements):
        raise ValueError("follower impedance requires the AC stimulus on the output test current")
    frequency_hz = measurements[0].frequency_hz
    if any(not np.array_equal(item.frequency_hz, frequency_hz) for item in measurements):
        raise ValueError("follower analysis requires one frequency sweep for every point")
    return AnalysisFollowerImpedance(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=np.asarray([float(item.param.vin) for item in measurements], dtype=np.float64),
        impedance_ohm=np.asarray([float(item.magnitude[0]) for item in measurements], dtype=np.float64),
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        impedance_db_ohm=np.asarray([20 * np.log10(item.magnitude) for item in measurements], dtype=np.float64),
    )


def analyze_follower_slew(measurements: Sequence[MeasFollowerStep]) -> AnalysisFollowerSlew:
    """Measure the output's slew rates, settling and overshoot on the input's rising and falling steps."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        wave = measurement.wave
        if wave is None:
            raise ValueError("follower slew requires a waveform record")
        tb = measurement.param
        time_s, output = wave.time_s, wave.v[FollowerNets.vout.name][0]
        period, edge = float(tb.period_s), float(tb.transition_time_s)
        rise_s, fall_s = period / 4, 3 * period / 4
        # the settled levels: the output just before each input edge
        low = calc.average(*calc.clip(output, time_s, rise_s - period / 20, rise_s))
        high = calc.average(*calc.clip(output, time_s, fall_s - period / 20, fall_s))
        up_v, up_s = calc.clip(output, time_s, rise_s, fall_s)
        down_v, down_s = calc.clip(output, time_s, fall_s, float(time_s[-1]))
        # an output that moves less than a tenth of the step (stuck, or not following) has no edges
        if high - low > float(tb.step_v) / 10:
            rise_settled = calc.settlingTime(up_v, up_s, initial=low, final=high, percent_of_step=1.0)
            fall_settled = calc.settlingTime(down_v, down_s, initial=high, final=low, percent_of_step=1.0)
            edges = (
                calc.slewrate(up_v, up_s, low, high),
                calc.slewrate(down_v, down_s, high, low),
                rise_settled - rise_s - edge / 2,
                fall_settled - fall_s - edge / 2,
                max(calc.overshoot(up_v, up_s, low, high), 0.0) / 100,
                max(calc.overshoot(down_v, down_s, high, low), 0.0) / 100,
            )
        else:
            edges = (math.nan,) * 6
        rows.append(
            (float(tb.vin), float(tb.step_v), low, high, *edges, calc.average(wave.i[FollowerNets.vdd.name][0], time_s))
        )
    columns = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    vin_v, step_v, low_v, high_v, rise_slew, fall_slew, rise_settling, fall_settling, rise_over, fall_over, current = (
        columns
    )
    return AnalysisFollowerSlew(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_v=vin_v,
        step_v=step_v,
        low_v=low_v,
        high_v=high_v,
        rise_slew_v_per_s=rise_slew,
        fall_slew_v_per_s=fall_slew,
        rise_settling_s=rise_settling,
        fall_settling_s=fall_settling,
        rise_overshoot=rise_over,
        fall_overshoot=fall_over,
        supply_current_a=current,
    )
