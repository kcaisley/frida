"""Calibration 1: mechanistic BOUT weights from physical CDAC S-curves.

The SAR logic initializes each P/N element from its programmed A-state and,
for decision bit ``B``, selects the endpoint ``P_final = 1 - B`` and
``N_final = B``.  A-state therefore selects the physical switching direction,
while B selects which endpoint is reached.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from flow.analysis.cdac import analyze_cdac_cap_mismatch
from flow.analysis.types import AnalysisAdcCalibration, MeasCdacExt
from flow.cdac import get_cdac_weights

type LogicBit = Literal[0, 1]
type CdacDirection = Literal["1to0", "0to1"]
type FloatArray = NDArray[np.float64]
type Uint8Array = NDArray[np.uint8]

# AnalysisCdacCapMismatch.effective_fraction_by_direction uses this order.
CDAC_DIRECTION_BY_INDEX: tuple[CdacDirection, CdacDirection] = ("1to0", "0to1")


@dataclass(frozen=True, slots=True)
class CdacEndpointAction:
    """One element's transition from its A-state to a B-selected endpoint."""

    initial_p: LogicBit
    initial_n: LogicBit
    bout: LogicBit
    final_p: LogicBit
    final_n: LogicBit
    p_direction: CdacDirection | None
    n_direction: CdacDirection | None

    @property
    def changed_sides(self) -> tuple[Literal["p", "n"], ...]:
        """Return the sides which change for this endpoint selection."""

        sides: list[Literal["p", "n"]] = []
        if self.p_direction is not None:
            sides.append("p")
        if self.n_direction is not None:
            sides.append("n")
        return tuple(sides)


@dataclass(frozen=True, slots=True)
class CdacEndpointSeparation:
    """Direction-selected P/N movements and their B-endpoint separation."""

    initial_p: Uint8Array
    initial_n: Uint8Array
    p_direction_index: Uint8Array
    n_direction_index: Uint8Array
    p_movement: FloatArray
    n_movement: FloatArray
    weight: FloatArray


@dataclass(frozen=True, slots=True)
class CdacWeightAudit:
    """Measured-weight deviations after matching the nominal total scale."""

    nominal_weight: FloatArray
    normalized_measured_weight: FloatArray
    weight_error: FloatArray
    minimum_binary_path_shift: float
    maximum_binary_path_shift: float
    maximum_absolute_weight_error: float


def _logic_bit(value: int, name: str) -> LogicBit:
    """Validate and return one binary logic value."""

    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value not in (0, 1):
        raise ValueError(f"{name} must be integer zero or one")
    return 0 if value == 0 else 1


def _transition(initial: LogicBit, final: LogicBit) -> CdacDirection | None:
    """Return the physical transition needed to reach ``final``."""

    if initial == final:
        return None
    return "0to1" if initial == 0 else "1to0"


def cdac_endpoint_action(a_p: int, a_n: int, bout: int) -> CdacEndpointAction:
    """Map one pair's A-states and BOUT to final states and physical actions.

    The mapping follows the fabricated SAR logic: the P-side logic receives
    the complementary comparator output and the N-side logic receives BOUT.
    Unequal P/N A-states are intentionally supported; they can make an endpoint
    selection change both sides or neither side.
    """

    initial_p = _logic_bit(a_p, "a_p")
    initial_n = _logic_bit(a_n, "a_n")
    decision = _logic_bit(bout, "bout")
    final_p: LogicBit = 1 if decision == 0 else 0
    final_n = decision
    return CdacEndpointAction(
        initial_p=initial_p,
        initial_n=initial_n,
        bout=decision,
        final_p=final_p,
        final_n=final_n,
        p_direction=_transition(initial_p, final_p),
        n_direction=_transition(initial_n, final_n),
    )


def cdac_endpoint_action_truth_table() -> tuple[CdacEndpointAction, ...]:
    """Return all eight A-state/BOUT endpoint-action combinations."""

    return tuple(cdac_endpoint_action(a_p, a_n, bout) for a_p in (0, 1) for a_n in (0, 1) for bout in (0, 1))


def _astate_array(values: Sequence[int] | NDArray[np.integer], name: str) -> Uint8Array:
    """Validate one one-dimensional A-state vector."""

    raw = np.asarray(values)
    if raw.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional, got shape {raw.shape}")
    if np.issubdtype(raw.dtype, np.bool_) or not np.issubdtype(raw.dtype, np.integer):
        raise ValueError(f"{name} must contain integer zero/one values")
    if np.any((raw != 0) & (raw != 1)):
        raise ValueError(f"{name} must contain only zero or one")
    return np.ascontiguousarray(raw, dtype=np.uint8)


def extract_endpoint_separation_weights(
    dac_astate_p: Sequence[int] | NDArray[np.integer],
    dac_astate_n: Sequence[int] | NDArray[np.integer],
    measured_by_side_and_direction: FloatArray,
    *,
    allow_unresolved: bool = False,
) -> CdacEndpointSeparation:
    """Select each side's A-state direction and add the endpoint movements.

    ``measured_by_side_and_direction`` has shape ``(2, element_count, 2)``.
    Side index zero is P and one is N. Direction index zero is ``1to0`` and
    index one is ``0to1``. For either equal or unequal P/N A-states, the
    distance between the ``B=0`` and ``B=1`` endpoints is the sum of the
    direction-selected P and N movement magnitudes.
    """

    initial_p = _astate_array(dac_astate_p, "dac_astate_p")
    initial_n = _astate_array(dac_astate_n, "dac_astate_n")
    if initial_p.shape != initial_n.shape:
        raise ValueError("P/N A-state vectors must have the same shape")
    measured = np.asarray(measured_by_side_and_direction, dtype=np.float64)
    expected_shape = (2, len(initial_p), 2)
    if measured.shape != expected_shape:
        raise ValueError(f"measured_by_side_and_direction has shape {measured.shape}, expected {expected_shape}")
    # A=0 selects the 0-to-1 measurement (index 1); A=1 selects 1-to-0
    # (index 0). P and N are selected independently.
    p_direction_index = np.ascontiguousarray(1 - initial_p, dtype=np.uint8)
    n_direction_index = np.ascontiguousarray(1 - initial_n, dtype=np.uint8)
    element = np.arange(len(initial_p))
    p_movement = np.ascontiguousarray(measured[0, element, p_direction_index], dtype=np.float64)
    n_movement = np.ascontiguousarray(measured[1, element, n_direction_index], dtype=np.float64)
    unresolved = (
        not np.all(np.isfinite(p_movement))
        or not np.all(np.isfinite(n_movement))
        or np.any(p_movement <= 0.0)
        or np.any(n_movement <= 0.0)
    )
    if unresolved and not allow_unresolved:
        raise ValueError("selected measured movements must be finite and positive")
    return CdacEndpointSeparation(
        initial_p=initial_p,
        initial_n=initial_n,
        p_direction_index=p_direction_index,
        n_direction_index=n_direction_index,
        p_movement=p_movement,
        n_movement=n_movement,
        weight=np.ascontiguousarray(p_movement + n_movement, dtype=np.float64),
    )


def audit_measured_weights(
    nominal_weight: Sequence[float] | FloatArray,
    measured_weight: Sequence[float] | FloatArray,
) -> CdacWeightAudit:
    """Normalize totals and bound the weighted-code shift over binary paths.

    For decision vector ``b``, the raw-code shift is ``b @ weight_error``.
    With unconstrained binary decisions, its exact extrema are the sums of the
    negative and positive errors, respectively. This is a diagnostic bound,
    not proof that every binary path is reachable by the SAR conversion.
    """

    nominal = np.ascontiguousarray(nominal_weight, dtype=np.float64)
    measured = np.ascontiguousarray(measured_weight, dtype=np.float64)
    if nominal.ndim != 1 or measured.ndim != 1 or nominal.shape != measured.shape or not len(nominal):
        raise ValueError("nominal and measured weights must be aligned non-empty vectors")
    if not np.all(np.isfinite(nominal)) or not np.all(np.isfinite(measured)):
        raise ValueError("nominal and measured weights must be finite")
    if np.any(nominal <= 0.0) or np.any(measured <= 0.0):
        raise ValueError("nominal and measured weights must be positive")
    normalized_measured = np.ascontiguousarray(measured * np.sum(nominal) / np.sum(measured), dtype=np.float64)
    error = np.ascontiguousarray(normalized_measured - nominal, dtype=np.float64)
    return CdacWeightAudit(
        nominal_weight=nominal,
        normalized_measured_weight=normalized_measured,
        weight_error=error,
        minimum_binary_path_shift=float(np.sum(error[error < 0.0])),
        maximum_binary_path_shift=float(np.sum(error[error > 0.0])),
        maximum_absolute_weight_error=float(np.max(np.abs(error))),
    )


def analyze(
    measurements: Sequence[MeasCdacExt],
    *,
    comparator_offset_v: float,
) -> AnalysisAdcCalibration:
    """Extract 17 normalized BOUT weights from physical CDAC S-curves.

    B0..B15 come from the direction selected by C0..C15's programmed P/N
    A-state. B16 is a terminal digital half-step, not a separately switched
    capacitor; its scale is inferred by projecting the sixteen measured
    movements onto their nominal design weights. This is the one coefficient
    marked as not directly measured in the common result.
    """

    if not measurements:
        raise ValueError("calibration 1 requires physical CDAC S-curve measurements")
    cap_analysis = analyze_cdac_cap_mismatch(
        measurements,
        comparator_offset_v=comparator_offset_v,
    )
    scan_params = measurements[0].param
    params = scan_params.tb
    nominal_cap_weight = np.asarray(
        [2.0 * value for value in get_cdac_weights(params.dut.cdac)],
        dtype=np.float64,
    )
    if nominal_cap_weight.shape != (16,):
        raise ValueError("calibration 1 requires a sixteen-element FRIDA CDAC")
    endpoint = extract_endpoint_separation_weights(
        params.dac_astate_p,
        params.dac_astate_n,
        cap_analysis.effective_fraction_by_direction,
        allow_unresolved=True,
    )
    measured_cap_weight = endpoint.weight
    resolved = (
        np.isfinite(endpoint.p_movement)
        & np.isfinite(endpoint.n_movement)
        & (endpoint.p_movement > 0.0)
        & (endpoint.n_movement > 0.0)
    )
    if not np.any(resolved):
        raise ValueError("calibration 1 has no resolved direction-selected CDAC weights")
    # A failed or non-physical S-curve fit must not silently become a negative
    # backend coefficient. Fit one volts-per-design-unit scale from the valid
    # elements, retain each valid measured endpoint separation, and preserve
    # nominal ratios for unresolved elements. The common result mask makes the
    # fallback visible to plots and CSV output.
    measured_scale = float(
        np.dot(nominal_cap_weight[resolved], measured_cap_weight[resolved])
        / np.dot(nominal_cap_weight[resolved], nominal_cap_weight[resolved])
    )
    hybrid_cap_weight = nominal_cap_weight * measured_scale
    hybrid_cap_weight[resolved] = measured_cap_weight[resolved]
    terminal_weight = measured_scale
    code_max = (1 << params.dut.adc_bits) - 1
    nominal_weight = np.concatenate((nominal_cap_weight, [1.0]))
    nominal_weight *= code_max / np.sum(nominal_weight)
    calibrated_weight = np.concatenate((hybrid_cap_weight, [terminal_weight]))
    calibrated_weight *= code_max / np.sum(calibrated_weight)
    adc_index = -1 if scan_params.observed_adc is None else scan_params.observed_adc
    return AnalysisAdcCalibration(
        adc_index=adc_index,
        method="calibration1",
        label="CDAC S-curve hybrid weights",
        code_max=code_max,
        nominal_weights=nominal_weight,
        calibrated_weights=calibrated_weight,
        measured_weight_mask=np.concatenate((resolved, [False])),
        training_sample_count=sum(len(measurement.daq.trial_index) for measurement in measurements),
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )
