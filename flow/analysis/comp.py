"""Typed comparator analyses for external and internal measurements."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import SupportsFloat, cast

import numpy as np
from scipy.stats import norm
from scipy.stats import t as student_t

from flow.analysis.measure import measure_average_power, measure_delay, measure_settling
from flow.analysis.types import (
    AnalysisCompCandidateSweep,
    AnalysisCompOffsetNoise,
    AnalysisCompPower,
    AnalysisCompTiming,
    MeasCdacExt,
    MeasCompExt,
    MeasCompInt,
)
from flow.circuit.params import supply_voltage


def analyze_comp_offset_noise(
    measurements: Sequence[MeasCompExt | MeasCompInt | MeasCdacExt],
) -> AnalysisCompOffsetNoise:
    """Fit comparator offset and input noise from binary decision sweeps."""

    if not measurements:
        raise ValueError("comparator offset/noise analysis requires measurements")
    vin_diff_v = np.round(
        np.concatenate([measurement.daq.vin_diff_v for measurement in measurements]),
        decimals=12,
    )
    decisions = np.concatenate([measurement.daq.decision for measurement in measurements])
    unique_input, inverse = np.unique(vin_diff_v, return_inverse=True)
    if len(unique_input) < 3:
        raise ValueError("comparator offset/noise analysis requires at least three inputs")
    count = np.bincount(inverse, minlength=len(unique_input)).astype(np.int64)
    decision_count = np.bincount(
        inverse,
        weights=np.asarray(decisions, dtype=np.float64),
        minlength=len(unique_input),
    )
    probability = decision_count / count
    trend = float(np.dot(unique_input - np.mean(unique_input), probability - np.mean(probability)))
    decision_polarity = 1 if trend >= 0.0 else -1

    # Adjacent-point reversals are tested across the complete curve. Use
    # Bonferroni-adjusted Wilson bounds so a long 100 µV grid does not acquire
    # an almost-certain false failure from repeated 95% pairwise tests.
    comparison_count = max(len(unique_input) - 1, 1)
    z_monotonic = float(norm.ppf(1.0 - 0.05 / (2.0 * comparison_count)))
    denominator = 1.0 + z_monotonic**2 / count
    interval_center = (probability + z_monotonic**2 / (2.0 * count)) / denominator
    interval_half_width = (
        z_monotonic
        * np.sqrt(probability * (1.0 - probability) / count + z_monotonic**2 / (4.0 * count**2))
        / denominator
    )
    lower_probability = interval_center - interval_half_width
    upper_probability = interval_center + interval_half_width

    # A physical fine point is deliberately acquired in host-side batches.
    # Trials inside one sequencer burst share the same analog state, so their
    # Bernoulli outcomes are not independent. Keep the simultaneous Wilson
    # interval as the minimum uncertainty, but widen it with the between-batch
    # 95% interval whenever the persisted batching metadata permits an exact
    # reconstruction. A nonzero host interval additionally exposes slow drift;
    # zero-interval transport batches still expose within-capture correlation.
    # Simulations and legacy/unbatched measurements retain Wilson-only behavior.
    batch_probabilities: list[list[float]] = [[] for _ in unique_input]
    for measurement in measurements:
        batch_count = int(measurement.info.readbacks.get("capture_batch_count", 1))
        batch_trials = int(measurement.info.readbacks.get("capture_batch_trials", 0))
        point_inputs = np.round(measurement.daq.vin_diff_v, decimals=12)
        point_decisions = np.asarray(measurement.daq.decision)
        if (
            batch_count < 2
            or batch_trials < 1
            or batch_count * batch_trials != len(point_decisions)
            or len(np.unique(point_inputs)) != 1
        ):
            continue
        input_index = int(np.searchsorted(unique_input, point_inputs[0]))
        batch_probabilities[input_index].extend(
            np.mean(point_decisions.reshape(batch_count, batch_trials), axis=1).tolist()
        )
    for input_index, point_batches in enumerate(batch_probabilities):
        if len(point_batches) < 2:
            continue
        batch_array = np.asarray(point_batches, dtype=np.float64)
        cluster_half_width = float(
            student_t.ppf(0.975, len(batch_array) - 1) * np.std(batch_array, ddof=1) / np.sqrt(len(batch_array))
        )
        lower_probability[input_index] = min(
            lower_probability[input_index],
            max(0.0, probability[input_index] - cluster_half_width),
        )
        upper_probability[input_index] = max(
            upper_probability[input_index],
            min(1.0, probability[input_index] + cluster_half_width),
        )
    if decision_polarity > 0:
        oriented_probability = probability
        oriented_lower = lower_probability
        oriented_upper = upper_probability
    else:
        oriented_probability = 1.0 - probability
        oriented_lower = 1.0 - upper_probability
        oriented_upper = 1.0 - lower_probability

    significant_reversal = np.any(
        (oriented_probability[:-1] > oriented_probability[1:]) & (oriented_lower[:-1] > oriented_upper[1:])
    )
    fitted_probability = np.maximum.accumulate(oriented_probability)

    def input_at_probability(target: float) -> float:
        if not fitted_probability[0] <= target <= fitted_probability[-1]:
            return math.nan
        return float(np.interp(target, fitted_probability, unique_input))

    p16 = input_at_probability(0.158655)
    p50 = input_at_probability(0.5)
    p84 = input_at_probability(0.841345)
    noise_sigma_v = abs(p84 - p16) / 2.0 if math.isfinite(p16) and math.isfinite(p84) else math.nan
    if significant_reversal:
        validity = "non_monotonic"
        p50 = math.nan
        noise_sigma_v = math.nan
    elif all(math.isfinite(value) for value in (p16, p50, p84)):
        validity = "valid"
    else:
        validity = "unbracketed"
    return AnalysisCompOffsetNoise(
        vin_diff_v=unique_input,
        decision_probability=probability,
        trial_count=count,
        offset_v=p50,
        noise_sigma_v=noise_sigma_v,
        decision_polarity=decision_polarity,
        validity=validity,
    )


def classify_comp_common_mode_validity(
    measurement_groups: Sequence[Sequence[MeasCompExt | MeasCompInt]],
    analyses: Sequence[AnalysisCompOffsetNoise],
) -> tuple[AnalysisCompOffsetNoise, ...]:
    """Contextually distinguish stuck comparator outputs from unbracketed curves."""

    if len(measurement_groups) != len(analyses) or not measurement_groups:
        raise ValueError("common-mode classification requires aligned non-empty groups and analyses")
    common_modes = []
    for group in measurement_groups:
        if not group:
            raise ValueError("common-mode classification groups must not be empty")
        values = {float(value) for measurement in group for value in measurement.daq.vin_cm_v}
        if len(values) != 1:
            raise ValueError("each common-mode classification group must contain one Vin_cm")
        common_modes.append(next(iter(values)))
    if len(common_modes) != len(set(common_modes)):
        raise ValueError("common-mode classification groups must have unique Vin_cm values")

    classified = list(analyses)
    common_mode_array = np.asarray(common_modes)
    valid_analyses = np.asarray(
        [candidate.validity == "valid" for candidate in analyses],
        dtype=np.bool_,
    )
    for index, analysis in enumerate(analyses):
        if analysis.validity != "unbracketed":
            continue
        probability = analysis.decision_probability
        stuck_label = None
        if np.all(probability <= 0.10):
            stuck_label = "stuck-low"
        elif np.all(probability >= 0.90):
            stuck_label = "stuck-high"
        if stuck_label is None:
            continue

        lower_candidates = np.flatnonzero((common_mode_array < common_modes[index]) & valid_analyses)
        upper_candidates = np.flatnonzero((common_mode_array > common_modes[index]) & valid_analyses)
        neighbor_indices = []
        if lower_candidates.size:
            neighbor_indices.append(int(lower_candidates[np.argmax(common_mode_array[lower_candidates])]))
        if upper_candidates.size:
            neighbor_indices.append(int(upper_candidates[np.argmin(common_mode_array[upper_candidates])]))
        captured_minimum_v = float(np.min(analysis.vin_diff_v))
        captured_maximum_v = float(np.max(analysis.vin_diff_v))
        expected_transition_was_exercised = any(
            captured_minimum_v <= analyses[neighbor].offset_v <= captured_maximum_v for neighbor in neighbor_indices
        )
        if expected_transition_was_exercised:
            classified[index] = replace(analysis, validity=stuck_label)
    return tuple(classified)


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
    for source_index, measurement in enumerate(measurements):
        for record, trial_index in enumerate(measurement.wave.trial_index):
            clock = measurement.wave.clock_v[record]
            # Settling is a property of the dynamic comparator core. The held
            # output latch can retain the previous decision throughout reset,
            # so using vout_p-vout_n would often look resolved before the clock.
            output_difference = measurement.wave.comp_p_v[record] - measurement.wave.comp_n_v[record]
            clock_threshold = (
                float((np.min(clock) + np.max(clock)) / 2.0) if clock_threshold_v is None else clock_threshold_v
            )
            response = np.abs(output_difference)
            response_threshold = float(np.max(response) / 2.0) if decision_threshold_v is None else decision_threshold_v
            trigger_s, _response_s, delay_s = measure_delay(
                measurement.wave.time_s,
                clock,
                response,
                clock_threshold,
                response_threshold,
            )
            source_indices.append(source_index)
            trial_indices.append(trial_index)
            delays.append(delay_s)
            is_unresolved = abs(output_difference[-1]) < unresolved_threshold_v
            if math.isfinite(trigger_s) and not is_unresolved:
                evaluation = measurement.wave.time_s >= trigger_s
                settled_at_s = measure_settling(
                    measurement.wave.time_s[evaluation],
                    output_difference[evaluation],
                    relative_tolerance=settling_tolerance,
                )
                settling_s = settled_at_s - trigger_s if math.isfinite(settled_at_s) else math.nan
            else:
                settling_s = math.nan
            settling.append(settling_s)
            unresolved.append(is_unresolved)
    return AnalysisCompTiming(
        source_index=np.asarray(source_indices, dtype=np.int64),
        trial_index=np.asarray(trial_indices, dtype=np.int64),
        clock_to_decision_s=np.asarray(delays, dtype=np.float64),
        settling_s=np.asarray(settling, dtype=np.float64),
        unresolved=np.asarray(unresolved, dtype=np.uint8),
    )


def _supply_voltage_v(measurement: MeasCompInt) -> float:
    for name in ("vdd_v", "supply_v"):
        if name in measurement.info.readbacks:
            return float(measurement.info.readbacks[name])
    return float(cast(SupportsFloat, supply_voltage(measurement.param.pvt.v)))


def analyze_comp_power(measurements: Sequence[MeasCompInt]) -> AnalysisCompPower:
    """Calculate average comparator power consumption."""

    if not measurements:
        raise ValueError("comparator power analysis requires measurements")
    supply_v = []
    average_power_w = []
    energy_per_decision_j = []
    for measurement in measurements:
        voltage = _supply_voltage_v(measurement)
        stored_power = measurement.info.readbacks.get("vdd_active_average_power_w")
        if stored_power is None:
            current = measurement.wave.vdd_i.reshape(-1)
            power = measure_average_power(current, voltage)
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
        source_index=np.arange(len(measurements), dtype=np.int64),
        supply_v=np.asarray(supply_v),
        average_power_w=np.asarray(average_power_w),
        energy_per_decision_j=np.asarray(energy_per_decision_j),
    )


def analyze_comp_candidate_sweep(measurements: Sequence[MeasCompInt]) -> AnalysisCompCandidateSweep:
    """Reuse the typed comparator analyses and align one row per candidate."""

    if not measurements:
        raise ValueError("comparator candidate analysis requires measurements")

    rows = []
    seen_candidates = set()
    for measurement in measurements:
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
        missing = sorted(required.difference(readbacks))
        if missing:
            raise ValueError(f"comparator candidate measurement is missing readbacks {missing}")
        candidate_id = str(readbacks["candidate_id"])
        if candidate_id in seen_candidates:
            raise ValueError(f"duplicate comparator candidate {candidate_id!r}")
        seen_candidates.add(candidate_id)

        noise = analyze_comp_offset_noise([measurement])
        timing = analyze_comp_timing([measurement])
        power = analyze_comp_power([measurement])
        finite_delay = timing.clock_to_decision_s[np.isfinite(timing.clock_to_decision_s)]
        finite_settling = timing.settling_s[np.isfinite(timing.settling_s)]
        unresolved_fraction = float(np.mean(timing.unresolved))
        maximum_delay_s = float(np.max(finite_delay)) if len(finite_delay) else math.nan
        if np.any(timing.unresolved):
            maximum_settling_s = float(getattr(measurement.param, "evaluation_time_s", math.nan))
        else:
            maximum_settling_s = float(np.max(finite_settling)) if len(finite_settling) else math.nan
        geometry_signature = str(readbacks["device_geometry_signature"])
        rows.append(
            {
                "candidate_id": candidate_id,
                "candidate_label": str(readbacks["candidate_label"]),
                "size_profile": str(readbacks["size_profile"]),
                "validity": noise.validity,
                "topology_index": int(readbacks["topology_index"]),
                "total_width_units": int(readbacks["total_width_units"]),
                "total_active_area_units": int(readbacks["total_active_area_units"]),
                "total_active_area_um2": float(readbacks["total_active_area_um2"]),
                "device_count": 0 if not geometry_signature else len(geometry_signature.split(",")),
                "geometry_signature": geometry_signature,
                "offset_v": noise.offset_v,
                "noise_sigma_v": noise.noise_sigma_v,
                "average_power_w": float(power.average_power_w[0]),
                "energy_per_decision_j": float(power.energy_per_decision_j[0]),
                "maximum_clock_to_decision_s": maximum_delay_s,
                "maximum_settling_s": maximum_settling_s,
                "unresolved_fraction": unresolved_fraction,
            }
        )

    # Summed MOS W*L is the primary axis. The exact generator insertion-order
    # geometry signature and candidate ID make ties stable and reproducible.
    rows.sort(
        key=lambda row: (
            row["total_active_area_units"],
            row["geometry_signature"],
            row["candidate_id"],
        )
    )

    def float_array(name: str) -> np.ndarray:
        return np.asarray([row[name] for row in rows], dtype=np.float64)

    def int_array(name: str) -> np.ndarray:
        return np.asarray([row[name] for row in rows], dtype=np.int64)

    return AnalysisCompCandidateSweep(
        candidate_id=tuple(str(row["candidate_id"]) for row in rows),
        candidate_label=tuple(str(row["candidate_label"]) for row in rows),
        size_profile=tuple(str(row["size_profile"]) for row in rows),
        validity=tuple(str(row["validity"]) for row in rows),
        topology_index=int_array("topology_index"),
        total_width_units=int_array("total_width_units"),
        total_active_area_units=int_array("total_active_area_units"),
        total_active_area_um2=float_array("total_active_area_um2"),
        device_count=int_array("device_count"),
        offset_v=float_array("offset_v"),
        noise_sigma_v=float_array("noise_sigma_v"),
        average_power_w=float_array("average_power_w"),
        energy_per_decision_j=float_array("energy_per_decision_j"),
        maximum_clock_to_decision_s=float_array("maximum_clock_to_decision_s"),
        maximum_settling_s=float_array("maximum_settling_s"),
        unresolved_fraction=float_array("unresolved_fraction"),
    )
