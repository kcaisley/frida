"""Typed current source measurements, results, and analyses.

A ``MeasIdac`` is one output voltage sweep of the current source testbench: per output voltage,
the currents into the unit's out and dump pins and the supply current. The figures are the
current at the nominal output voltage, the output resistance there, the compliance range over
which the current stays within 5 %, and for a switched unit its on-off ratio and how much of
the current a steered unit loses between its two states.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, check_identity, measurement_identity
from flow.idac.sim import IdacTbParams
from flow.idac.subckt import IdacParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasIdac(Meas):
    """Current source output sweep at one reference current and enable state: one row per output
    voltage, with the bias node's voltage."""

    dut: IdacParams
    param: IdacTbParams
    vout_v: np.ndarray
    out_current_a: np.ndarray
    dump_current_a: np.ndarray
    supply_current_a: np.ndarray
    vbias_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisIdacOutput(Analysis):
    """Current source output characteristic at each bias.

    ``current_a`` (magnitude, into an NMOS unit or out of a PMOS one) and
    ``output_resistance_ohm`` are at the nominal output voltage; ``compliance_low_v`` and
    ``compliance_high_v`` bound the output voltages around it whose current is within 5 % of
    that; ``dump_current_a`` is the dump pin's. ``vout_v``, ``iv_current_a`` and ``iv_resistance_ohm``
    (one row per bias) hold the whole characteristic.
    """

    vbias_v: np.ndarray
    iref_a: np.ndarray
    enabled: np.ndarray
    current_a: np.ndarray
    output_resistance_ohm: np.ndarray
    compliance_low_v: np.ndarray
    compliance_high_v: np.ndarray
    dump_current_a: np.ndarray
    supply_current_a: np.ndarray
    vout_v: np.ndarray
    iv_current_a: np.ndarray
    iv_resistance_ohm: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisIdacSteering(Analysis):
    """A switched unit's two states at each bias, at the nominal output voltage.

    ``on_off_ratio`` is the enabled output current over the disabled one's magnitude;
    ``total_change`` how much the sum of output and dump currents moves between the states,
    relative to the enabled output current (0 for a lossless steering pair).
    """

    vbias_v: np.ndarray
    iref_a: np.ndarray
    on_current_a: np.ndarray
    off_current_a: np.ndarray
    on_dump_a: np.ndarray
    off_dump_a: np.ndarray
    on_off_ratio: np.ndarray
    total_change: np.ndarray


def analyze_idac_output(measurements: Sequence[MeasIdac]) -> AnalysisIdacOutput:
    """Measure current, output resistance, compliance range, and supply current at each bias."""

    identity = measurement_identity(measurements)
    vout_v = measurements[0].vout_v
    if any(not np.allclose(item.vout_v, vout_v) for item in measurements):
        raise ValueError("current source analysis requires one output sweep for every point")
    rows = []
    for measurement in measurements:
        tb = measurement.param
        nominal = float(tb.vout)
        current = np.abs(measurement.out_current_a)
        current_a = calc.value(current, vout_v, nominal)
        slope = np.gradient(current, vout_v)
        compliance_low, compliance_high = calc.compliance_range(current, vout_v, nominal)
        rows.append(
            (
                calc.value(measurement.vbias_v, vout_v, nominal),
                float(tb.iref),
                tb.en,
                current_a,
                1 / abs(calc.value(slope, vout_v, nominal)),
                compliance_low,
                compliance_high,
                calc.value(np.abs(measurement.dump_current_a), vout_v, nominal),
                calc.value(measurement.supply_current_a, vout_v, nominal),
                current,
                1 / np.maximum(np.abs(slope), 1e-15),
            )
        )
    vbias, iref, enabled, current_a, resistance, low, high, dump, supply, iv, iv_resistance = zip(*rows)
    return AnalysisIdacOutput(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vbias_v=np.asarray(vbias, dtype=np.float64),
        iref_a=np.asarray(iref, dtype=np.float64),
        enabled=np.asarray(enabled, dtype=np.bool_),
        current_a=np.asarray(current_a, dtype=np.float64),
        output_resistance_ohm=np.asarray(resistance, dtype=np.float64),
        compliance_low_v=np.asarray(low, dtype=np.float64),
        compliance_high_v=np.asarray(high, dtype=np.float64),
        dump_current_a=np.asarray(dump, dtype=np.float64),
        supply_current_a=np.asarray(supply, dtype=np.float64),
        vout_v=np.asarray(vout_v, dtype=np.float64),
        iv_current_a=np.asarray(iv, dtype=np.float64),
        iv_resistance_ohm=np.asarray(iv_resistance, dtype=np.float64),
    )


def analyze_idac_steering(measurements: Sequence[MeasIdac], *, on: AnalysisIdacOutput) -> AnalysisIdacSteering:
    """Compare a switched unit's disabled sweeps with its enabled result at the same biases."""

    identity = measurement_identity(measurements)
    check_identity(on, identity, name="on")
    if any(item.param.en for item in measurements) or not np.all(on.enabled):
        raise ValueError("steering compares disabled sweeps with an enabled result")
    if len(measurements) != len(on.current_a):
        raise ValueError("steering requires one disabled sweep per enabled bias")
    rows = []
    for index, measurement in enumerate(measurements):
        tb = measurement.param
        if not math.isclose(float(tb.iref), on.iref_a[index]):
            raise ValueError("steering requires the disabled sweeps in the enabled result's bias order")
        nominal = float(tb.vout)
        off_current = calc.value(np.abs(measurement.out_current_a), measurement.vout_v, nominal)
        off_dump = calc.value(np.abs(measurement.dump_current_a), measurement.vout_v, nominal)
        on_total = on.current_a[index] + on.dump_current_a[index]
        rows.append(
            (
                off_current,
                off_dump,
                on.current_a[index] / off_current if off_current > 0 else math.inf,
                (off_current + off_dump - on_total) / on.current_a[index],
            )
        )
    off_current, off_dump, ratio, change = (np.asarray(column, dtype=np.float64) for column in zip(*rows))
    return AnalysisIdacSteering(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vbias_v=on.vbias_v,
        iref_a=on.iref_a,
        on_current_a=on.current_a,
        off_current_a=off_current,
        on_dump_a=on.dump_current_a,
        off_dump_a=off_dump,
        on_off_ratio=ratio,
        total_change=change,
    )
