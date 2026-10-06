"""Typed analysis for physical and whole-ADC A-to-B CDAC measurements."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
    AnalysisCdacTransition,
    AnalysisCompOffsetNoise,
    Identity,
    MeasCdac,
    check_identity,
    measurement_identity,
)
from flow.caparray import get_caparray_weights


def analyze_cdac_transition(
    measurements: Sequence[MeasCdac],
    *,
    offset: AnalysisCompOffsetNoise,
) -> AnalysisCdacTransition:
    """Place one element's switching-curve fit at its CDAC side, element, direction, and mode.

    ``offset`` is the S-curve fit of exactly these measurements, made by
    ``analyze_comp_offset_noise``; its 50% point is the transition. The runner
    chooses which sweep stage (for example only the fine points) forms the curve.
    """

    identity = measurement_identity(measurements)
    check_identity(offset, identity, name="switching-curve fit")
    keys = set()
    for measurement in measurements:
        params = measurement.param
        if params.campaign != "cdac_ab":
            raise ValueError("A-to-B CDAC analysis requires campaign='cdac_ab'")
        keys.add((params.cdac_side, params.cdac_element, params.cdac_direction, int(params.tb.dac_diffcaps)))
    if len(keys) != 1:
        raise ValueError("CDAC transition requires measurements of exactly one switching curve")
    side, element, direction, diffcaps = next(iter(keys))
    if side not in ("p", "n") or element is None or direction not in ("1to0", "0to1"):
        raise ValueError("CDAC measurement is missing a valid side, element, or direction")
    fitted_inputs = np.unique(np.round(np.concatenate([m.vin_diff_v for m in measurements]), decimals=12))
    if not np.array_equal(fitted_inputs, offset.vin_diff_v):
        raise ValueError("switching-curve fit was not made from these measurements")
    valid = offset.validity != "non_monotonic" and math.isfinite(offset.offset_v)
    return AnalysisCdacTransition(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        side="p" if side == "p" else "n",
        element=element,
        direction="1to0" if direction == "1to0" else "0to1",
        diffcaps=diffcaps,
        vin_diff_v=offset.vin_diff_v,
        decision_probability=offset.decision_probability,
        trial_count=offset.trial_count,
        transition_v=offset.offset_v if valid else math.nan,
        valid=valid,
    )


def analyze_cdac_cap_mismatch(
    measurements: Sequence[MeasCdac],
    *,
    transitions: Sequence[AnalysisCdacTransition],
    comparator: AnalysisCompOffsetNoise,
) -> AnalysisCdacCapMismatch:
    """Decompose main/diff normalized capacitance of one ADC from its switching curves.

    ``transitions`` holds one fit per measured curve. The comparator offset is
    the reference point of every step: an element's normalized movement is
    ``(offset - transition) / VDD_DAC``.
    """

    identity = measurement_identity(measurements)
    check_identity(transitions, identity, name="CDAC transition")
    first = measurements[0]
    check_identity(
        comparator,
        Identity(identity.group, identity.index, first.param.tb.dut.comp),
        name="comparator offset",
    )
    if comparator.validity != "valid":
        raise ValueError("CDAC analysis requires a valid comparator offset")
    element_count = len(get_caparray_weights(first.param.tb.dut.cdac))
    measured_curves = {
        (
            measurement.param.cdac_side,
            measurement.param.cdac_element,
            measurement.param.cdac_direction,
            int(measurement.param.tb.dac_diffcaps),
        )
        for measurement in measurements
    }
    by_curve = {(t.side, t.element, t.direction, t.diffcaps): t for t in transitions}
    if len(by_curve) != len(transitions) or set(by_curve) != measured_curves:
        raise ValueError("CDAC transitions must contain exactly one fit per measured switching curve")
    vdd_dac_v = {float(measurement.tb.vdd_dac.dc) for measurement in measurements}
    if len(vdd_dac_v) != 1:
        raise ValueError("CDAC measurements must share one VDD_DAC")
    reference_v = next(iter(vdd_dac_v))

    per_mode_direction = np.full((2, element_count, 2, 2), np.nan, dtype=np.float64)
    for (side, element, direction, diffcaps), transition in by_curve.items():
        if not 0 <= element < element_count:
            raise ValueError("CDAC measurement element is outside the configured CDAC")
        signed_step = (comparator.offset_v - transition.transition_v) / reference_v if transition.valid else math.nan
        side_sign = 1.0 if side == "p" else -1.0
        direction_sign = 1.0 if direction == "0to1" else -1.0
        per_mode_direction[0 if side == "p" else 1, element, diffcaps, 0 if direction == "1to0" else 1] = (
            side_sign * direction_sign * signed_step
        )

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
                    mode_values.append(calc.average(directions))
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
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        main_fraction=main_fraction,
        diff_fraction=diff_fraction,
        effective_fraction=effective_fraction,
        effective_fraction_by_direction=effective_fraction_by_direction,
        direction_bias=direction_bias,
    )
