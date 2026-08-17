"""Typed analysis for physical and whole-ADC A-to-B CDAC measurements."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from flow.analysis.comp import analyze_comp_offset_noise
from flow.analysis.types import AnalysisCdacCapMismatch, MeasCdacExt, Measurement
from flow.cdac import get_cdac_weights


def analyze_cdac_cap_mismatch(
    measurements: Sequence[MeasCdacExt],
    *,
    comparator_offset_v: float,
) -> AnalysisCdacCapMismatch:
    """Fit every P50 and decompose main/diff normalized capacitance in one ADC."""

    if not measurements:
        raise ValueError("A-to-B CDAC analysis requires measurements")
    if any(measurement.param.campaign != "cdac_ab" for measurement in measurements):
        raise ValueError("A-to-B CDAC analysis requires campaign='cdac_ab'")
    adc_indices = {measurement.param.observed_adc for measurement in measurements}
    if len(adc_indices) != 1 or None in adc_indices:
        raise ValueError("A-to-B CDAC analysis operates on one explicitly selected ADC")
    adc_index = next(index for index in adc_indices if index is not None)
    if not math.isfinite(comparator_offset_v):
        raise ValueError("comparator_offset_v must be finite")
    element_counts = {len(get_cdac_weights(measurement.param.dut.cdac)) for measurement in measurements}
    if len(element_counts) != 1:
        raise ValueError("A-to-B CDAC analysis requires one CDAC configuration")
    element_count = next(iter(element_counts))

    grouped: dict[tuple[int, int, int, int], list[MeasCdacExt]] = {}
    for measurement in measurements:
        params = measurement.param
        if params.cdac_element is None or params.cdac_side is None or params.cdac_direction is None:
            raise ValueError("CDAC measurement is missing its side, element, or direction")
        if not 0 <= params.cdac_element < element_count:
            raise ValueError("CDAC measurement element is outside the configured CDAC")
        key = (
            params.cdac_element,
            0 if params.cdac_side == "p" else 1,
            0 if params.cdac_direction == "1to0" else 1,
            params.dac_diffcaps,
        )
        grouped.setdefault(key, []).append(measurement)

    curve_keys = sorted(grouped)
    transitions = []
    normalized_steps = []
    curve_valid = []
    per_mode_direction = np.full((2, element_count, 2, 2), np.nan, dtype=np.float64)
    for element, side, direction, diffcaps in curve_keys:
        curve_measurements = grouped[(element, side, direction, diffcaps)]
        fine_measurements = [
            measurement for measurement in curve_measurements if measurement.param.sweep_stage == "fine"
        ]
        fit = analyze_comp_offset_noise(fine_measurements or curve_measurements)
        transition_v = fit.offset_v
        valid = fit.validity != "non_monotonic" and math.isfinite(transition_v)
        params = curve_measurements[0].param
        signed_step = (comparator_offset_v - transition_v) / float(params.vdd_dac.dc) if valid else math.nan
        side_sign = 1.0 if params.cdac_side == "p" else -1.0
        direction_sign = 1.0 if params.cdac_direction == "0to1" else -1.0
        oriented_step = side_sign * direction_sign * signed_step
        transitions.append(transition_v)
        normalized_steps.append(signed_step)
        curve_valid.append(valid)
        per_mode_direction[side, element, diffcaps, direction] = oriented_step

    main_fraction = np.full((2, element_count), np.nan, dtype=np.float64)
    diff_fraction = np.full((2, element_count), np.nan, dtype=np.float64)
    effective_fraction = np.full((2, element_count), np.nan, dtype=np.float64)
    effective_fraction_by_direction = per_mode_direction[:, :, 1, :].copy()
    direction_bias = np.full((2, element_count, 2), np.nan, dtype=np.float64)
    for side in range(2):
        for element in range(element_count):
            mode_values = []
            for diffcaps in range(2):
                directions = per_mode_direction[side, element, diffcaps]
                if np.all(np.isfinite(directions)):
                    mode_values.append(float(np.mean(directions)))
                    direction_bias[side, element, diffcaps] = float((directions[0] - directions[1]) / 2.0)
                else:
                    mode_values.append(math.nan)
            # The fabricated cap-driver XOR is active high: dac_diffcaps=0
            # switches main and diff together, whereas dac_diffcaps=1 switches
            # them oppositely.  Normal ADC operation therefore measures
            # main-minus-diff in mode 1; mode 0 supplies main-plus-diff for the
            # component decomposition.
            w_plus, w_minus = mode_values
            if math.isfinite(w_minus):
                effective_fraction[side, element] = w_minus
            if math.isfinite(w_minus) and math.isfinite(w_plus):
                main_fraction[side, element] = (w_plus + w_minus) / 2.0
                diff_fraction[side, element] = (w_plus - w_minus) / 2.0

    return AnalysisCdacCapMismatch(
        adc_index=adc_index,
        curve_element=np.asarray([key[0] for key in curve_keys], dtype=np.int64),
        curve_side=np.asarray([key[1] for key in curve_keys], dtype=np.uint8),
        curve_direction=np.asarray([key[2] for key in curve_keys], dtype=np.uint8),
        curve_diffcaps=np.asarray([key[3] for key in curve_keys], dtype=np.uint8),
        transition_v=np.asarray(transitions, dtype=np.float64),
        normalized_step=np.asarray(normalized_steps, dtype=np.float64),
        curve_valid=np.asarray(curve_valid, dtype=np.uint8),
        main_fraction=main_fraction,
        diff_fraction=diff_fraction,
        effective_fraction=effective_fraction,
        effective_fraction_by_direction=effective_fraction_by_direction,
        direction_bias=direction_bias,
    )


def analyze_cdac_cap_mismatch_campaign(
    measurement_runs: Sequence[Sequence[Measurement]],
    *,
    adc_indices: Sequence[int],
    board_id: str,
    comparator_offset_v_by_adc: Mapping[int, float],
) -> tuple[
    tuple[tuple[MeasCdacExt, ...], ...],
    tuple[AnalysisCdacCapMismatch, ...],
]:
    """Reduce selectively reacquired runs and analyze one complete ADC campaign.

    Each later run atomically replaces every point belonging to the same ADC,
    side, element, direction, and diffcaps curve. Physical points from distinct
    acquisition sessions are never combined into one fitted curve.
    """

    selected_adc_indices = tuple(adc_indices)
    if not selected_adc_indices or len(set(selected_adc_indices)) != len(selected_adc_indices):
        raise ValueError("CDAC campaign requires unique ADC indices")
    if not board_id:
        raise ValueError("CDAC campaign requires an explicit board_id")

    selected_curve_measurements: dict[tuple[int, str, int, str, int], list[MeasCdacExt]] = {}
    for measurement_run in measurement_runs:
        grouped_in_run: dict[tuple[int, str, int, str, int], list[MeasCdacExt]] = {}
        for measurement in measurement_run:
            if not isinstance(measurement, MeasCdacExt):
                raise TypeError(f"CDAC campaign contains {type(measurement).__name__}, expected MeasCdacExt")
            if measurement.param.campaign != "cdac_ab":
                raise ValueError("CDAC campaign contains a point outside campaign='cdac_ab'")
            if int(measurement.info.readbacks.get("fastrx_lost_count", 0)) or int(
                measurement.info.readbacks.get("spi_mismatches", 0)
            ):
                raise ValueError("CDAC campaign contains a corrupt physical capture")
            params = measurement.param
            if (
                params.observed_adc is None
                or params.cdac_side is None
                or params.cdac_element is None
                or params.cdac_direction is None
            ):
                raise ValueError("CDAC measurement is missing its ADC, side, element, or direction")
            if params.observed_adc not in selected_adc_indices:
                raise ValueError(f"CDAC campaign contains unexpected ADC{params.observed_adc:02d}")
            curve_key = (
                params.observed_adc,
                params.cdac_side,
                params.cdac_element,
                params.cdac_direction,
                params.dac_diffcaps,
            )
            grouped_in_run.setdefault(curve_key, []).append(measurement)

        for key, curve_measurements in grouped_in_run.items():
            physical_measurements = [
                measurement for measurement in curve_measurements if measurement.info.backend == "physical"
            ]
            if physical_measurements:
                session_ids = {
                    measurement.info.readbacks.get("acquisition_session_id") for measurement in physical_measurements
                }
                completed = [
                    measurement
                    for measurement in physical_measurements
                    if measurement.info.readbacks.get("curve_complete") is True
                ]
                latest_timestamp = max(measurement.info.timestamp_utc for measurement in physical_measurements)
                if (
                    len(physical_measurements) != len(curve_measurements)
                    or None in session_ids
                    or len(session_ids) != 1
                    or len(completed) != 1
                    or completed[0].info.timestamp_utc != latest_timestamp
                ):
                    raise ValueError(f"CDAC campaign contains an incomplete or mixed-session curve {key}")

        selected_curve_measurements.update(grouped_in_run)

    measurements = tuple(
        measurement
        for curve_key in sorted(selected_curve_measurements)
        for measurement in selected_curve_measurements[curve_key]
    )
    if {measurement.param.observed_adc for measurement in measurements} != set(selected_adc_indices):
        raise ValueError("CDAC campaign does not contain exactly the requested ADCs")

    expected_curves = {
        (side, element, direction, diffcaps)
        for side in ("p", "n")
        for element in range(16)
        for direction in ("1to0", "0to1")
        for diffcaps in (0, 1)
    }
    groups = []
    analyses = []
    for adc_index in selected_adc_indices:
        adc_measurements = tuple(
            measurement for measurement in measurements if measurement.param.observed_adc == adc_index
        )
        observed_curves = {
            (
                measurement.param.cdac_side,
                measurement.param.cdac_element,
                measurement.param.cdac_direction,
                measurement.param.dac_diffcaps,
            )
            for measurement in adc_measurements
        }
        if observed_curves != expected_curves:
            raise ValueError(f"ADC{adc_index:02d} A-to-B CDAC campaign is incomplete")
        if {measurement.param.board_id for measurement in adc_measurements} != {board_id}:
            raise ValueError(f"ADC{adc_index:02d} CDAC measurements do not match board {board_id}")
        if adc_index not in comparator_offset_v_by_adc:
            raise ValueError(f"ADC{adc_index:02d} has no accepted comparator calibration")
        groups.append(adc_measurements)
        analyses.append(
            analyze_cdac_cap_mismatch(
                adc_measurements,
                comparator_offset_v=float(comparator_offset_v_by_adc[adc_index]),
            )
        )
    return tuple(groups), tuple(analyses)
