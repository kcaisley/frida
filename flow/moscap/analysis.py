"""Typed MOS capacitor measurements, results, and analyses.

A ``MeasMosCap`` is one operating point and AC response of the MOS capacitor testbench: the
admittance the stimulated source drives, per frequency. Its operating-point current, the
leakage, is in the run readbacks. Capacitance is the susceptance over 2 pi f, the quality
factor susceptance over conductance, the series resistance the real part of the impedance.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.moscap.sim import MosCapTbParams
from flow.moscap.subckt import Mode, MosCapParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasMosCap(Meas):
    """MOS capacitor admittance at one bias: one row per frequency."""

    dut: MosCapParams
    param: MosCapTbParams
    frequency_hz: np.ndarray
    conductance_s: np.ndarray
    susceptance_s: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMoscapCv(Analysis):
    """MOS capacitor capacitance, loss and leakage at each bias.

    ``bias_v`` is a decap's supply, or a two-net capacitor's gate plate over its channel plate.
    ``capacitance_f`` is at the lowest frequency; ``quality`` and ``series_resistance_ohm`` at
    the sweep frequency nearest 1 GHz (``loss_frequency_hz``); ``corner_hz`` where the quality
    factor first falls to 1 (NaN within the sweep). A model without AC loss gives no conductance:
    an infinite quality factor, no series resistance, no corner. ``capacitance_spectrum_f`` and
    ``quality_spectrum`` hold every frequency, one row per bias.
    """

    bias_v: np.ndarray
    capacitance_f: np.ndarray
    quality: np.ndarray
    series_resistance_ohm: np.ndarray
    corner_hz: np.ndarray
    leakage_a: np.ndarray
    loss_frequency_hz: float
    frequency_hz: np.ndarray
    capacitance_spectrum_f: np.ndarray
    quality_spectrum: np.ndarray


def analyze_moscap_cv(measurements: Sequence[MeasMosCap]) -> AnalysisMoscapCv:
    """Measure capacitance, quality factor, series resistance, quality corner, and leakage at each bias."""

    identity = measurement_identity(measurements)
    frequency_hz = measurements[0].frequency_hz
    if any(not np.array_equal(item.frequency_hz, frequency_hz) for item in measurements):
        raise ValueError("MOS capacitor analysis requires one frequency sweep for every point")
    decap = identity.dut.mode == Mode.DECAP
    loss_index = int(np.argmin(np.abs(np.log10(frequency_hz) - 9.0)))
    rows = []
    for measurement in measurements:
        tb = measurement.param
        capacitance = measurement.susceptance_s / (2 * np.pi * frequency_hz)
        quality = np.divide(
            measurement.susceptance_s,
            measurement.conductance_s,
            out=np.full_like(measurement.susceptance_s, np.inf),
            where=measurement.conductance_s != 0,
        )
        impedance = 1 / (measurement.conductance_s + 1j * measurement.susceptance_s)
        corner = (
            calc.cross(np.log10(quality), np.log10(frequency_hz), 0.0, edge="falling", occurrence=1)
            if np.all(np.isfinite(quality))
            else math.nan
        )
        rows.append(
            (
                float(tb.vdd) if decap else float(tb.vtop) - float(tb.vbot),
                float(capacitance[0]),
                float(quality[loss_index]),
                float(np.real(impedance[loss_index])),
                10**corner if math.isfinite(corner) else math.nan,
                float(measurement.info.readbacks["op_leakage_a"]),
                capacitance,
                quality,
            )
        )
    bias_v, capacitance_f, quality, resistance, corner_hz, leakage, spectrum, quality_spectrum = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
    return AnalysisMoscapCv(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        bias_v=bias_v,
        capacitance_f=capacitance_f,
        quality=quality,
        series_resistance_ohm=resistance,
        corner_hz=corner_hz,
        leakage_a=leakage,
        loss_frequency_hz=float(frequency_hz[loss_index]),
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        capacitance_spectrum_f=spectrum,
        quality_spectrum=quality_spectrum,
    )
