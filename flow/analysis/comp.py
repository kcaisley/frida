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
    AnalysisCompCommonMode,
    AnalysisCompOffsetNoise,
    MeasCdac,
    MeasComp,
    check_identity,
    measurement_identity,
)


def analyze_comp_offset_noise(
    measurements: Sequence[MeasComp | MeasCdac],
) -> AnalysisCompOffsetNoise:
    """Pool decision sweeps at one input common mode and fit offset and input noise.

    The same S-curve fit locates a CDAC switching curve's transition, so CDAC
    curves are accepted too; their common mode comes from the testbench when
    the DAQ did not record it. Trials a simulation marks unresolved (the latch
    still undecided when the decision was read: the output holds the previous
    one) are left out; where more than 1 % of them are, the comparator is too
    slow for its clock and the fit is ``unresolved``.
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
    resolved = np.concatenate(
        [
            np.ones(len(measurement.decision), dtype=np.bool_)
            if getattr(measurement, "resolved", None) is None
            else np.asarray(measurement.resolved, dtype=np.bool_)
            for measurement in measurements
        ]
    )
    unresolved_fraction = 1.0 - float(np.mean(resolved))
    # more than 1 % undecided: the comparator is too slow for its clock, and its curve is kept as read
    if unresolved_fraction <= 0.01:
        vin_diff_v, decisions = vin_diff_v[resolved], decisions[resolved]
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
    validity: Literal["valid", "unbracketed", "non_monotonic", "unresolved"]
    if unresolved_fraction > 0.01:
        validity = "unresolved"
        p50 = math.nan
        noise_sigma_v = math.nan
    elif significant_reversal:
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
    validity: list[Literal["valid", "unbracketed", "non_monotonic", "unresolved", "stuck-low", "stuck-high"]] = []
    for position, result in enumerate(ordered):
        label: Literal["valid", "unbracketed", "non_monotonic", "unresolved", "stuck-low", "stuck-high"] = (
            result.validity
        )
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
