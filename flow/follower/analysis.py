"""Typed follower measurements, results, and analyses.

A ``MeasFollower`` is one operating point and AC response of the follower testbench, the output
per volt of input or, with the output test current, per ampere into the output (the output
impedance). Its operating point (supply current, output level) is in the run readbacks.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.follower.sim import FollowerTbParams
from flow.follower.subckt import FollowerParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasFollower(Meas):
    """Follower AC response at one input level: one row per frequency."""

    dut: FollowerParams
    param: FollowerTbParams
    frequency_hz: np.ndarray
    magnitude: np.ndarray
    phase_deg: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisFollowerTransfer(Analysis):
    """Follower transfer at each input level.

    ``vout_v`` is the operating-point output, ``gain_v_per_v`` the response at the lowest
    frequency, ``bandwidth_hz`` where it has fallen 3 dB (log-interpolated, NaN beyond the sweep),
    ``response_db`` the whole response, one row per point and one column per ``frequency_hz``.
    """

    vin_v: np.ndarray
    vout_v: np.ndarray
    gain_v_per_v: np.ndarray
    bandwidth_hz: np.ndarray
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


def analyze_follower_transfer(measurements: Sequence[MeasFollower]) -> AnalysisFollowerTransfer:
    """Measure output level, small-signal gain, bandwidth, and supply current at each input level."""

    identity = measurement_identity(measurements)
    if any(item.param.output_test for item in measurements):
        raise ValueError("follower transfer requires the AC stimulus on the input")
    frequency_hz = measurements[0].frequency_hz
    if any(not np.array_equal(item.frequency_hz, frequency_hz) for item in measurements):
        raise ValueError("follower analysis requires one frequency sweep for every point")
    rows = []
    for measurement in measurements:
        response_db = 20 * np.log10(measurement.magnitude)
        corner = calc.cross(response_db, np.log10(frequency_hz), response_db[0] - 3.0, edge="falling", occurrence=1)
        readbacks = measurement.info.readbacks
        rows.append(
            (
                float(measurement.param.vin),
                float(readbacks["op_vout_v"]),
                float(measurement.magnitude[0]),
                10**corner if math.isfinite(corner) else math.nan,
                float(readbacks["op_supply_current_a"]),
                response_db,
            )
        )
    vin_v, vout_v, gain, bandwidth, current, response_db = (
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
