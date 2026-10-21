"""Typed comparator results and the simulation analyses of the comparator testbench.

The comparator's measurement (``MeasComp``) and its offset and noise analyses stay shared in
``flow.analysis``: lab captures and the ADC flows use them too. These are the analyses only the
comparator's own simulations feed: clock-to-decision timing and its delay map over the input,
supply power, and the generated-candidate summary.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from flow.analysis import calc
from flow.analysis.types import (
    Analysis,
    AnalysisCompOffsetNoise,
    MeasComp,
    check_identity,
    measurement_identity,
)
from flow.comp.sim import CompTbParams
from flow.comp.subckt import CompNets


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCompTiming(Analysis):
    """Comparator timing and metastability results across measurements."""

    source_index: np.ndarray
    trial_index: np.ndarray
    clock_to_decision_s: np.ndarray
    settling_s: np.ndarray
    unresolved: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCompDelay(Analysis):
    """Comparator clock-to-decision delay over common mode and differential input.

    ``delay_s`` has one row per common mode and one column per differential
    input: the median delay of that point's resolved trials, NaN where none
    resolved.
    """

    vin_cm_v: np.ndarray
    vin_diff_v: np.ndarray
    delay_s: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCompPower(Analysis):
    """Comparator average consumed power per measurement."""

    source_index: np.ndarray
    supply_v: np.ndarray
    average_power_w: np.ndarray
    energy_per_decision_j: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisCompCandidate(Analysis):
    """Noise, power, and settling summary of one generated comparator candidate."""

    candidate_id: str
    candidate_label: str
    size_profile: Literal["half", "double", "fabricated"]
    validity: Literal["valid", "unbracketed", "non_monotonic", "unresolved"]
    topology_index: int
    total_width_units: int
    total_active_area_units: int
    total_active_area_um2: float
    device_count: int
    geometry_signature: str
    offset_v: float
    noise_sigma_v: float
    average_power_w: float
    energy_per_decision_j: float
    maximum_clock_to_decision_s: float
    maximum_settling_s: float
    unresolved_fraction: float


def analyze_comp_timing(measurements: Sequence[MeasComp]) -> AnalysisCompTiming:
    """Measure clock-to-decision delay, settling, and unresolved trials."""

    identity = measurement_identity(measurements)
    source_indices = []
    trial_indices = []
    delays = []
    settling = []
    unresolved = []
    for source_index, measurement in enumerate(measurements):
        wave = measurement.wave
        if wave is None:
            raise ValueError("comparator timing requires waveform records")
        for record, trial_index in enumerate(wave.record_index):
            clock = wave.v[CompNets.clk.name][record]
            # Settling is a property of the dynamic comparator core. The held
            # output latch can retain the previous decision throughout reset,
            # so using vout_p-vout_n would often look resolved before the clock.
            output_difference = wave.v[CompNets.latch_p.name][record] - wave.v[CompNets.latch_n.name][record]
            # Time both signals at the midpoint of their own swing.
            clock_threshold = float((calc.ymin(clock) + calc.ymax(clock)) / 2.0)
            response = np.abs(output_difference)
            response_threshold = float(calc.ymax(response) / 2.0)
            trigger_s, _response_s, delay_s = calc.delay(
                clock,
                response,
                wave.time_s,
                clock_threshold,
                response_threshold,
            )
            source_indices.append(source_index)
            trial_indices.append(trial_index)
            delays.append(delay_s)
            # A latch still within 0.1 V of balance at the end of the record
            # has not resolved.
            is_unresolved = abs(output_difference[-1]) < 0.1
            if math.isfinite(trigger_s) and not is_unresolved:
                evaluation_v, evaluation_s = calc.clip(
                    output_difference, wave.time_s, trigger_s, float(wave.time_s[-1])
                )
                # Settled within 1% of the final latch step.
                settled_at_s = calc.settlingTime(evaluation_v, evaluation_s, percent_of_step=1.0)
                settling_s = settled_at_s - trigger_s if math.isfinite(settled_at_s) else math.nan
            else:
                settling_s = math.nan
            settling.append(settling_s)
            unresolved.append(is_unresolved)
    return AnalysisCompTiming(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        source_index=np.asarray(source_indices, dtype=np.int64),
        trial_index=np.asarray(trial_indices, dtype=np.int64),
        clock_to_decision_s=np.asarray(delays, dtype=np.float64),
        settling_s=np.asarray(settling, dtype=np.float64),
        unresolved=np.asarray(unresolved, dtype=np.bool_),
    )


def analyze_comp_delay(
    measurements: Sequence[MeasComp],
    *,
    timing: AnalysisCompTiming,
) -> AnalysisCompDelay:
    """Median clock-to-decision delay of the resolved trials at every swept input point."""

    identity = measurement_identity(measurements)
    check_identity(timing, identity, name="comparator timing")
    vin_cm_v = np.unique(np.concatenate([measurement.vin_cm_v for measurement in measurements]))
    vin_diff_v = np.unique(np.concatenate([measurement.vin_diff_v for measurement in measurements]))
    # each timed record's input point, from its measurement and row
    record_cm_v = np.asarray(
        [
            measurements[source].vin_cm_v[row]
            for source, row in zip(timing.source_index, timing.trial_index, strict=True)
        ]
    )
    record_diff_v = np.asarray(
        [
            measurements[source].vin_diff_v[row]
            for source, row in zip(timing.source_index, timing.trial_index, strict=True)
        ]
    )
    delay_s = np.full((len(vin_cm_v), len(vin_diff_v)), np.nan)
    for row, cm_v in enumerate(vin_cm_v):
        for column, diff_v in enumerate(vin_diff_v):
            selected = np.isclose(record_cm_v, cm_v) & np.isclose(record_diff_v, diff_v) & ~timing.unresolved
            if np.any(selected):
                delay_s[row, column] = float(np.median(timing.clock_to_decision_s[selected]))
    return AnalysisCompDelay(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=vin_cm_v,
        vin_diff_v=vin_diff_v,
        delay_s=delay_s,
    )


def analyze_comp_power(measurements: Sequence[MeasComp]) -> AnalysisCompPower:
    """Time-weight comparator power within each record and average records equally."""

    identity = measurement_identity(measurements)
    supply_v = []
    average_power_w = []
    energy_per_decision_j = []
    for measurement in measurements:
        readbacks = measurement.info.readbacks
        if "vdd_v" in readbacks or "supply_v" in readbacks:
            voltage = float(readbacks["vdd_v"] if "vdd_v" in readbacks else readbacks["supply_v"])
        elif isinstance(measurement.tb, CompTbParams):
            voltage = float(measurement.tb.vdd)
        else:
            voltage = float(measurement.tb.vdd_a.dc)
        stored_power = measurement.info.readbacks.get("vdd_active_average_power_w")
        if stored_power is None:
            wave = measurement.wave
            if wave is None:
                raise ValueError("comparator power without a stored average requires waveform records")
            power = calc.average(
                [calc.average(np.abs(current * voltage), wave.time_s) for current in wave.i[CompNets.vdd.name]]
            )
        else:
            power = float(stored_power)
        stored_energy = measurement.info.readbacks.get("energy_per_decision_j")
        if stored_energy is not None:
            energy = float(stored_energy)
        elif all(hasattr(measurement.param, name) for name in ("reset_time_s", "evaluation_time_s")):
            energy = power * (float(measurement.param.reset_time_s) + float(measurement.param.evaluation_time_s))
        else:
            energy = math.nan
        supply_v.append(voltage)
        average_power_w.append(power)
        energy_per_decision_j.append(energy)
    return AnalysisCompPower(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        source_index=np.arange(len(measurements), dtype=np.int64),
        supply_v=np.asarray(supply_v),
        average_power_w=np.asarray(average_power_w),
        energy_per_decision_j=np.asarray(energy_per_decision_j),
    )


def analyze_comp_candidate(
    measurement: MeasComp,
    *,
    offset: AnalysisCompOffsetNoise,
    timing: AnalysisCompTiming,
    power: AnalysisCompPower,
) -> AnalysisCompCandidate:
    """Summarize one generated comparator candidate from its earlier results.

    Candidate geometry comes from the measurement's readbacks; noise, timing,
    and power come from the matching per-candidate analyses.
    """

    identity = measurement.identity
    for name, result in (("offset", offset), ("timing", timing), ("power", power)):
        check_identity(result, identity, name=name)
    readbacks = measurement.info.readbacks
    required = {
        "candidate_id",
        "candidate_label",
        "topology_index",
        "size_profile",
        "total_width_units",
        "device_width_signature",
        "total_active_area_units",
        "total_active_area_um2",
        "device_geometry_signature",
    }
    if missing := sorted(required.difference(readbacks)):
        raise ValueError(f"comparator candidate measurement is missing readbacks {missing}")
    if len(power.average_power_w) != 1:
        raise ValueError("comparator candidate requires a power analysis of exactly this measurement")
    finite_delay = timing.clock_to_decision_s[np.isfinite(timing.clock_to_decision_s)]
    finite_settling = timing.settling_s[np.isfinite(timing.settling_s)]
    if np.any(timing.unresolved):
        # An unresolved trial settles no sooner than the end of evaluation.
        maximum_settling_s = float(getattr(measurement.param, "evaluation_time_s", math.nan))
    else:
        maximum_settling_s = float(calc.ymax(finite_settling)) if len(finite_settling) else math.nan
    geometry_signature = str(readbacks["device_geometry_signature"])
    size_profile = str(readbacks["size_profile"])
    if size_profile not in ("half", "double", "fabricated"):
        raise ValueError(f"unknown comparator candidate size profile {size_profile!r}")
    return AnalysisCompCandidate(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        candidate_id=str(readbacks["candidate_id"]),
        candidate_label=str(readbacks["candidate_label"]),
        size_profile=size_profile,
        validity=offset.validity,
        topology_index=int(readbacks["topology_index"]),
        total_width_units=int(readbacks["total_width_units"]),
        total_active_area_units=int(readbacks["total_active_area_units"]),
        total_active_area_um2=float(readbacks["total_active_area_um2"]),
        device_count=0 if not geometry_signature else len(geometry_signature.split(",")),
        geometry_signature=geometry_signature,
        offset_v=offset.offset_v,
        noise_sigma_v=offset.noise_sigma_v,
        average_power_w=float(power.average_power_w[0]),
        energy_per_decision_j=float(power.energy_per_decision_j[0]),
        maximum_clock_to_decision_s=float(calc.ymax(finite_delay)) if len(finite_delay) else math.nan,
        maximum_settling_s=maximum_settling_s,
        unresolved_fraction=calc.average(timing.unresolved),
    )
