"""Typed comparator analyses for external and internal measurements."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
from scipy.stats import norm
from scipy.stats import t as student_t

from flow.analysis import calc
from flow.analysis.types import (
    AnalysisCompCandidate,
    AnalysisCompCommonMode,
    AnalysisCompOffsetNoise,
    AnalysisCompPower,
    AnalysisCompTiming,
    MeasCdac,
    MeasComp,
    check_identity,
    measurement_identity,
)
from flow.comp.sim import CompTbParams
from flow.comp.subckt import CompNets


def analyze_comp_offset_noise(
    measurements: Sequence[MeasComp | MeasCdac],
) -> AnalysisCompOffsetNoise:
    """Pool decision sweeps at one input common mode and fit offset and input noise.

    The same S-curve fit locates a CDAC switching curve's transition, so CDAC
    curves are accepted too; their common mode comes from the testbench when
    the DAQ did not record it.
    """

    identity = measurement_identity(measurements)
    # Compare common modes at 1 µV resolution, finer than any programmed step.
    common_modes = np.unique(
        np.round(
            np.concatenate(
                [
                    np.full(len(measurement.decision), float(measurement.tb.vin_cm.dc))
                    if isinstance(measurement, MeasCdac) and measurement.vin_cm_v is None
                    else np.asarray(measurement.vin_cm_v)
                    for measurement in measurements
                ]
            ),
            decimals=6,
        )
    )
    if len(common_modes) != 1:
        raise ValueError("comparator offset/noise analysis requires measurements at one input common mode")

    # Round inputs to 1 pV so repeated programmed values pool exactly.
    vin_diff_v = np.round(
        np.concatenate([measurement.vin_diff_v for measurement in measurements]),
        decimals=12,
    )
    decisions = np.concatenate([measurement.decision for measurement in measurements])
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
    trend = float(np.dot(unique_input - calc.average(unique_input), probability - calc.average(probability)))
    decision_polarity: Literal[-1, 1] = 1 if trend >= 0.0 else -1

    # Adjacent-point reversals are tested across the complete curve. Use
    # Bonferroni-adjusted 95% Wilson bounds so a long 100 µV grid does not
    # acquire an almost-certain false failure from repeated pairwise tests.
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
        point_inputs = np.round(measurement.vin_diff_v, decimals=12)
        point_decisions = np.asarray(measurement.decision)
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
            student_t.ppf(0.975, len(batch_array) - 1)
            * calc.stddev(batch_array, sample=True)
            / np.sqrt(len(batch_array))
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

    # Measure the first rising contact of the 16%, 50%, and 84% points: the
    # Gaussian mean and +-1 sigma. Endpoint-only contacts remain unbracketed.
    p16 = calc.cross(fitted_probability, unique_input, 0.158655, occurrence=1)
    p50 = calc.cross(fitted_probability, unique_input, 0.5, occurrence=1)
    p84 = calc.cross(fitted_probability, unique_input, 0.841345, occurrence=1)
    noise_sigma_v = abs(p84 - p16) / 2.0 if math.isfinite(p16) and math.isfinite(p84) else math.nan
    validity: Literal["valid", "unbracketed", "non_monotonic"]
    if significant_reversal:
        validity = "non_monotonic"
        p50 = math.nan
        noise_sigma_v = math.nan
    elif all(math.isfinite(value) for value in (p16, p50, p84)):
        validity = "valid"
    else:
        validity = "unbracketed"
    return AnalysisCompOffsetNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=float(common_modes[0]),
        vin_diff_v=unique_input,
        decision_probability=probability,
        trial_count=count,
        offset_v=p50,
        noise_sigma_v=noise_sigma_v,
        decision_polarity=decision_polarity,
        validity=validity,
    )


def analyze_comp_common_mode(
    measurements: Sequence[MeasComp],
    *,
    offsets: Sequence[AnalysisCompOffsetNoise],
) -> AnalysisCompCommonMode:
    """Classify each common mode, distinguishing stuck outputs from unbracketed curves.

    ``offsets`` holds one fit per common mode in ``measurements``. An
    unbracketed curve is relabeled stuck only when it is pinned and the
    offset of the nearest valid common mode on either side lies inside its
    swept input range, so the transition should have been observed.
    """

    identity = measurement_identity(measurements)
    check_identity(offsets, identity, name="comparator offset")
    measured_modes = {
        round(float(value), 6) for measurement in measurements for value in np.unique(measurement.vin_cm_v)
    }
    ordered = sorted(offsets, key=lambda result: result.vin_cm_v)
    common_modes = np.asarray([result.vin_cm_v for result in ordered])
    if len(set(common_modes.tolist())) != len(ordered) or {round(value, 6) for value in common_modes} != measured_modes:
        raise ValueError("comparator offsets must contain exactly one fit per measured common mode")

    valid = np.asarray([result.validity == "valid" for result in ordered], dtype=np.bool_)
    validity: list[Literal["valid", "unbracketed", "non_monotonic", "stuck-low", "stuck-high"]] = []
    for position, result in enumerate(ordered):
        label: Literal["valid", "unbracketed", "non_monotonic", "stuck-low", "stuck-high"] = result.validity
        # A curve that never leaves 10% or 90% probability is pinned; the
        # 0.1/0.9 levels sit well outside the noise of a bracketed S-curve.
        probability = result.decision_probability
        pinned = "stuck-low" if np.all(probability <= 0.10) else "stuck-high" if np.all(probability >= 0.90) else None
        if result.validity == "unbracketed" and pinned is not None:
            lower = np.flatnonzero((common_modes < result.vin_cm_v) & valid)
            upper = np.flatnonzero((common_modes > result.vin_cm_v) & valid)
            neighbors = [int(lower[-1])] if len(lower) else []
            neighbors += [int(upper[0])] if len(upper) else []
            minimum_v = float(calc.ymin(result.vin_diff_v))
            maximum_v = float(calc.ymax(result.vin_diff_v))
            if any(minimum_v <= ordered[neighbor].offset_v <= maximum_v for neighbor in neighbors):
                label = pinned
        validity.append(label)
    return AnalysisCompCommonMode(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=common_modes,
        offset_v=np.asarray([result.offset_v for result in ordered]),
        noise_sigma_v=np.asarray([result.noise_sigma_v for result in ordered]),
        validity=tuple(validity),
    )


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
