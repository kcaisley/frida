"""Calibration 1: mechanistic BOUT weights from physical CDAC S-curves.

The SAR logic initializes each P/N element from its programmed A-state and,
for decision bit ``B``, selects the endpoint ``P_final = 1 - B`` and
``N_final = B``.  A-state therefore selects the physical switching direction,
while B selects which endpoint is reached: an element starting at A=0 moves
0-to-1 and one starting at A=1 moves 1-to-0, on each side independently. For
equal or unequal P/N A-states, the distance between the ``B=0`` and ``B=1``
endpoints is the sum of the direction-selected P and N movement magnitudes.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from flow.analysis.types import (
    AnalysisAdcCalibration,
    AnalysisCdacCapMismatch,
    MeasCdac,
    check_identity,
    measurement_identity,
)
from flow.caparray import get_caparray_weights


def analyze_adc_calibration1(
    measurements: Sequence[MeasCdac],
    *,
    cap_mismatch: AnalysisCdacCapMismatch,
) -> AnalysisAdcCalibration:
    """Extract normalized BOUT weights from physical CDAC S-curves.

    Each capacitor's weight comes from the direction selected by its
    programmed P/N A-state in ``cap_mismatch``, which already references
    every step to the comparator offset. The terminal decision is a digital
    half-step, not a separately switched capacitor; its scale is inferred by
    projecting the measured movements onto their nominal design weights. This
    is the one coefficient marked as not directly measured in the result.
    The result applies to the whole ADC, so its DUT parameters are the ADC's.
    """

    identity = measurement_identity(measurements)
    check_identity(cap_mismatch, identity, name="CDAC cap mismatch")
    tb = measurements[0].tb
    # Every switched capacitor contributes twice its unit weight (both CDAC
    # sides move), and the terminal comparison adds one unit.
    nominal_bout_weight = np.asarray([2 * weight for weight in get_caparray_weights(tb.dut.cdac)] + [1], float)
    nominal_cap_weight = nominal_bout_weight[:-1]
    initial_p = np.asarray(tb.dac_astate_p, dtype=np.int64)
    initial_n = np.asarray(tb.dac_astate_n, dtype=np.int64)
    measured = np.asarray(cap_mismatch.effective_fraction_by_direction, dtype=np.float64)
    if (
        initial_p.shape != (len(nominal_cap_weight),)
        or initial_n.shape != initial_p.shape
        or np.any((initial_p != 0) & (initial_p != 1))
        or np.any((initial_n != 0) & (initial_n != 1))
    ):
        raise ValueError("P/N A-states must contain one zero or one per capacitor")
    if measured.shape != (2, len(nominal_cap_weight), 2):
        raise ValueError("CDAC direction results must hold two sides, every capacitor, and two directions")
    # Direction index 0 is 1-to-0 and 1 is 0-to-1: A=0 selects index 1 and
    # A=1 selects index 0, independently for P (side 0) and N (side 1).
    element = np.arange(len(nominal_cap_weight))
    p_movement = measured[0, element, 1 - initial_p]
    n_movement = measured[1, element, 1 - initial_n]
    measured_cap_weight = p_movement + n_movement
    resolved = np.isfinite(p_movement) & np.isfinite(n_movement) & (p_movement > 0.0) & (n_movement > 0.0)
    if not np.any(resolved):
        raise ValueError("calibration 1 has no resolved direction-selected CDAC weights")
    # A failed or non-physical S-curve fit must not silently become a negative
    # backend coefficient. Fit one volts-per-design-unit scale from the valid
    # elements, retain each valid measured endpoint separation, and preserve
    # nominal ratios for unresolved elements. The result mask makes the
    # fallback visible to plots.
    measured_scale = float(
        np.dot(nominal_cap_weight[resolved], measured_cap_weight[resolved])
        / np.dot(nominal_cap_weight[resolved], nominal_cap_weight[resolved])
    )
    hybrid_cap_weight = nominal_cap_weight * measured_scale
    hybrid_cap_weight[resolved] = measured_cap_weight[resolved]
    terminal_weight = nominal_bout_weight[-1] * measured_scale
    code_max = (1 << tb.dut.adc_bits) - 1
    nominal_weight = nominal_bout_weight * code_max / np.sum(nominal_bout_weight)
    calibrated_weight = np.concatenate((hybrid_cap_weight, [terminal_weight]))
    calibrated_weight *= code_max / np.sum(calibrated_weight)
    return AnalysisAdcCalibration(
        group=identity.group,
        index=identity.index,
        dut=tb.dut,
        method="calibration1",
        label="CDAC S-curve hybrid weights",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=calibrated_weight,
        measured_weight_mask=np.concatenate((resolved, [False])),
        training_sample_count=sum(len(measurement.trial_index) for measurement in measurements),
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )
