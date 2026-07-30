"""Typed comparator analyses for external and internal measurements."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, cast

import numpy as np

from flow.analysis.measure import measure_average_power, measure_delay, measure_settling
from flow.analysis.types import (
    AnalysisCompOffsetNoise,
    AnalysisCompPower,
    AnalysisCompTiming,
    MeasCompExt,
    MeasCompInt,
)
from flow.circuit import SupplyVals

CompMeasurement = MeasCompExt | MeasCompInt


def analyze_comp_offset_noise(
    measurements: Sequence[CompMeasurement],
) -> AnalysisCompOffsetNoise:
    """Fit comparator offset and input noise from binary decision sweeps."""

    if not measurements:
        raise ValueError("comparator offset/noise analysis requires measurements")
    vin_diff_v = np.concatenate([msmt.daq.vin_diff_v for msmt in measurements])
    decisions = np.concatenate([msmt.daq.decision for msmt in measurements])
    unique_input, inverse = np.unique(vin_diff_v, return_inverse=True)
    if len(unique_input) < 3:
        raise ValueError("comparator offset/noise analysis requires at least three inputs")
    probability = np.asarray([np.mean(decisions[inverse == index]) for index in range(len(unique_input))])
    count = np.bincount(inverse, minlength=len(unique_input)).astype(np.int64)
    order = np.argsort(probability)
    sorted_probability = probability[order]
    sorted_input = unique_input[order]
    if np.any(np.diff(sorted_probability) < 0):
        raise ValueError("comparator decision probability must be monotonic")

    def input_at_probability(target: float) -> float:
        if not sorted_probability[0] <= target <= sorted_probability[-1]:
            return math.nan
        return float(np.interp(target, sorted_probability, sorted_input))

    p16 = input_at_probability(0.158655)
    p50 = input_at_probability(0.5)
    p84 = input_at_probability(0.841345)
    noise_sigma_v = abs(p84 - p16) / 2.0 if math.isfinite(p16) and math.isfinite(p84) else math.nan
    return AnalysisCompOffsetNoise(
        vin_diff_v=unique_input,
        decision_probability=probability,
        trial_count=count,
        offset_v=p50,
        noise_sigma_v=noise_sigma_v,
    )


def analyze_comp_timing(
    measurements: Sequence[MeasCompInt],
    *,
    clock_threshold_v: float | None = None,
    decision_threshold_v: float | None = None,
    settling_tolerance: float = 0.01,
    unresolved_threshold_v: float = 0.1,
) -> AnalysisCompTiming:
    """Measure clock-to-decision delay, settling, and unresolved trials."""

    if not measurements:
        raise ValueError("comparator timing analysis requires measurements")
    source_indices = []
    trial_indices = []
    delays = []
    settling = []
    unresolved = []
    for source_index, msmt in enumerate(measurements):
        for record, trial_index in enumerate(msmt.wave.trial_index):
            clock = msmt.wave.clock_v[record]
            output_difference = msmt.wave.vout_p_v[record] - msmt.wave.vout_n_v[record]
            clock_threshold = (
                float((np.min(clock) + np.max(clock)) / 2.0) if clock_threshold_v is None else clock_threshold_v
            )
            response = np.abs(output_difference)
            response_threshold = float(np.max(response) / 2.0) if decision_threshold_v is None else decision_threshold_v
            _trigger_s, _response_s, delay_s = measure_delay(
                msmt.wave.time_s,
                clock,
                response,
                clock_threshold,
                response_threshold,
            )
            source_indices.append(source_index)
            trial_indices.append(trial_index)
            delays.append(delay_s)
            settling.append(
                measure_settling(
                    msmt.wave.time_s,
                    output_difference,
                    relative_tolerance=settling_tolerance,
                )
            )
            unresolved.append(abs(output_difference[-1]) < unresolved_threshold_v)
    return AnalysisCompTiming(
        source_index=np.asarray(source_indices, dtype=np.int64),
        trial_index=np.asarray(trial_indices, dtype=np.int64),
        clock_to_decision_s=np.asarray(delays, dtype=np.float64),
        settling_s=np.asarray(settling, dtype=np.float64),
        unresolved=np.asarray(unresolved, dtype=np.uint8),
    )


def _supply_voltage_v(msmt: MeasCompInt) -> float:
    for name in ("vdd_v", "supply_v"):
        if name in msmt.info.readbacks:
            return float(msmt.info.readbacks[name])
    return float(cast(Any, SupplyVals.corner(msmt.param.pvt.v).VDD))


def analyze_comp_power(measurements: Sequence[MeasCompInt]) -> AnalysisCompPower:
    """Calculate average comparator power consumption."""

    if not measurements:
        raise ValueError("comparator power analysis requires measurements")
    supply_v = []
    average_power_w = []
    for msmt in measurements:
        voltage = _supply_voltage_v(msmt)
        current = msmt.wave.vdd_i.reshape(-1)
        supply_v.append(voltage)
        average_power_w.append(measure_average_power(current, voltage))
    return AnalysisCompPower(
        source_index=np.arange(len(measurements), dtype=np.int64),
        supply_v=np.asarray(supply_v),
        average_power_w=np.asarray(average_power_w),
    )
