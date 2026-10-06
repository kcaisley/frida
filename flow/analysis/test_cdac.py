"""Software-only tests for A-to-B CDAC transition analysis."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import hdl21 as h
import numpy as np
import pytest

from flow.analysis.cdac import analyze_cdac_cap_mismatch, analyze_cdac_transition
from flow.analysis.comp import analyze_comp_offset_noise
from flow.analysis.types import (
    AnalysisCompOffsetNoise,
    MeasCdac,
    MeasInfo,
    Wave,
)
from flow.scans.scan_cdac import _build_cdac_params


def transition_of(curve: list[MeasCdac]):
    """Fit one switching curve the way the runner does: S-curve fit, then CDAC placement."""

    return analyze_cdac_transition(curve, offset=analyze_comp_offset_noise(curve))


def cap_mismatch_of(measurements: list[MeasCdac], comparator: AnalysisCompOffsetNoise):
    """Fit every curve of one ADC, preferring its fine sweep stage, then decompose (as the runner does)."""

    curves: dict[tuple[object, ...], list[MeasCdac]] = {}
    for measurement in measurements:
        params = measurement.param
        curves.setdefault(
            (params.cdac_side, params.cdac_element, params.cdac_direction, params.tb.dac_diffcaps), []
        ).append(measurement)
    transitions = [
        transition_of([point for point in curve if point.param.sweep_stage == "fine"] or curve)
        for curve in curves.values()
    ]
    return analyze_cdac_cap_mismatch(measurements, transitions=transitions, comparator=comparator)


def comparator_offset(measurement: MeasCdac, offset_v: float, *, index: int | None = None) -> AnalysisCompOffsetNoise:
    """Return a valid comparator characterization of the measured ADC's comparator."""

    return AnalysisCompOffsetNoise(
        group=measurement.group,
        index=measurement.index if index is None else index,
        dut=measurement.param.tb.dut.comp,
        vin_cm_v=0.8,
        vin_diff_v=np.asarray([offset_v - 1e-3, offset_v, offset_v + 1e-3]),
        decision_probability=np.asarray([0.0, 0.5, 1.0]),
        trial_count=np.asarray([100, 100, 100]),
        offset_v=offset_v,
        noise_sigma_v=5e-4,
        decision_polarity=1,
        validity="valid",
    )


def test_analyze_cdac_cap_mismatch_recovers_main_diff_and_direction_pairs() -> None:
    comparator_offset_v = 8.0e-3
    expected_mode_weights = {0: 0.20, 1: 0.10}
    measurements = []
    for direction in ("1to0", "0to1"):
        for diffcaps, normalized_weight in expected_mode_weights.items():
            direction_sign = 1.0 if direction == "0to1" else -1.0
            transition_v = comparator_offset_v - direction_sign * normalized_weight * 1.2
            for input_index, probability in enumerate((0.0, 0.5, 1.0)):
                vin_diff_v = transition_v + (input_index - 1) * 10e-3
                params = _build_cdac_params(
                    adc_index=0,
                    side="p",
                    element=15,
                    direction=direction,
                    dac_diffcaps=diffcaps,
                    vin_diff_v=vin_diff_v,
                    conversions=100,
                    sweep_stage="fine",
                )
                ones = round(100 * probability)
                decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
                before_p = np.tile(params.tb.dac_astate_p, (100, 1))
                before_n = np.tile(params.tb.dac_astate_n, (100, 1))
                after_p = np.tile(params.tb.dac_bstate_p, (100, 1))
                after_n = np.tile(params.tb.dac_bstate_n, (100, 1))
                measurements.append(
                    MeasCdac(
                        group=params.board_id,
                        index=params.observed_adc,
                        dut=params.tb.dut.cdac,
                        info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 4, tzinfo=UTC)),
                        param=params,
                        trial_index=np.arange(100),
                        dac_state_p=after_p,
                        dac_state_n=after_n,
                        vin_diff_v=np.full(100, vin_diff_v),
                        decision=decisions,
                        dac_state_before_p=before_p,
                        dac_state_before_n=before_n,
                        vin_cm_v=np.full(100, 0.8),
                        fastrx_word=np.asarray(
                            [(1 << 28) | (frame << 17) | int(decision) for frame, decision in enumerate(decisions)],
                            dtype=np.uint32,
                        ),
                        fastrx_frame=np.arange(100, dtype=np.uint32),
                        wave=Wave(
                            record_index=np.asarray([0], dtype=np.int64),
                            time_s=np.asarray([0.0, 1e-9]),
                            v={
                                "vin_diff": np.asarray([[vin_diff_v, vin_diff_v]]),
                                "seq_comp": np.asarray([[0.0, 1.2]]),
                                "comp_out": np.asarray([[0.0, 1.2]]),
                            },
                        ),
                    )
                )
            base = measurements[-1]
            coarse_v = transition_v + 20e-3
            coarse_params = replace(
                base.param,
                sweep_stage="coarse",
                tb=replace(base.param.tb, vin_diff=h.Vdc.Params(dc=coarse_v)),
            )
            measurements.append(
                replace(
                    base,
                    param=coarse_params,
                    vin_diff_v=np.full(100, coarse_v),
                    decision=np.zeros(100, dtype=np.uint8),
                    fastrx_word=np.asarray(
                        [(1 << 28) | (frame << 17) for frame in range(100)],
                        dtype=np.uint32,
                    ),
                    wave=replace(base.wave, v={**base.wave.v, "vin_diff": np.asarray([[coarse_v, coarse_v]])}),
                )
            )

    result = cap_mismatch_of(measurements, comparator_offset(measurements[0], comparator_offset_v))

    assert (result.group, result.index) == (0, 0)
    assert result.dut == measurements[0].dut
    assert result.effective_fraction[0, 15] == pytest.approx(0.10)
    np.testing.assert_allclose(result.effective_fraction_by_direction[0, 15], (0.10, 0.10))
    assert result.main_fraction[0, 15] == pytest.approx(0.15)
    assert result.diff_fraction[0, 15] == pytest.approx(0.05)
    np.testing.assert_allclose(result.direction_bias[0, 15], 0.0, atol=1e-15)
    assert np.all(np.isnan(result.main_fraction[1]))


def test_analyze_cdac_cap_mismatch_retains_side_asymmetry_and_direction_bias() -> None:
    comparator_offset_v = -6e-3
    measurements = []
    expected = {
        "p": {0: (0.20, 0.02), 1: (0.10, 0.01)},
        "n": {0: (0.18, 0.015), 1: (0.12, -0.005)},
    }
    for side in ("p", "n"):
        side_sign = 1.0 if side == "p" else -1.0
        for direction_index, direction in enumerate(("1to0", "0to1")):
            direction_sign = 1.0 if direction == "0to1" else -1.0
            for diffcaps in (0, 1):
                mean_weight, bias = expected[side][diffcaps]
                oriented_weight = mean_weight + (bias if direction_index == 0 else -bias)
                signed_step = side_sign * direction_sign * oriented_weight
                transition_v = comparator_offset_v - signed_step * 1.2
                for input_index, probability in enumerate((0.0, 0.5, 1.0)):
                    vin_diff_v = transition_v + (input_index - 1) * 10e-3
                    params = _build_cdac_params(
                        adc_index=0,
                        side=side,
                        element=15,
                        direction=direction,
                        dac_diffcaps=diffcaps,
                        vin_diff_v=vin_diff_v,
                        conversions=100,
                        sweep_stage="coarse",
                    )
                    ones = round(100 * probability)
                    decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
                    before_p = np.tile(params.tb.dac_astate_p, (100, 1))
                    before_n = np.tile(params.tb.dac_astate_n, (100, 1))
                    after_p = np.tile(params.tb.dac_bstate_p, (100, 1))
                    after_n = np.tile(params.tb.dac_bstate_n, (100, 1))
                    measurements.append(
                        MeasCdac(
                            group=params.board_id,
                            index=params.observed_adc,
                            dut=params.tb.dut.cdac,
                            info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 4, tzinfo=UTC)),
                            param=params,
                            trial_index=np.arange(100),
                            dac_state_p=after_p,
                            dac_state_n=after_n,
                            vin_diff_v=np.full(100, vin_diff_v),
                            decision=decisions,
                            dac_state_before_p=before_p,
                            dac_state_before_n=before_n,
                            vin_cm_v=np.full(100, 0.8),
                            fastrx_word=np.asarray(
                                [(1 << 28) | (frame << 17) | int(decision) for frame, decision in enumerate(decisions)],
                                dtype=np.uint32,
                            ),
                            fastrx_frame=np.arange(100, dtype=np.uint32),
                            wave=Wave(
                                record_index=np.asarray([0], dtype=np.int64),
                                time_s=np.asarray([0.0, 1e-9]),
                                v={
                                    "vin_diff": np.asarray([[vin_diff_v, vin_diff_v]]),
                                    "seq_comp": np.asarray([[0.0, 1.2]]),
                                    "comp_out": np.asarray([[0.0, 1.2]]),
                                },
                            ),
                        )
                    )

    for vin_diff_v in (-20e-3, 0.0, 20e-3):
        params = _build_cdac_params(
            adc_index=0,
            side="p",
            element=14,
            direction="1to0",
            dac_diffcaps=0,
            vin_diff_v=vin_diff_v,
            conversions=100,
            sweep_stage="coarse",
        )
        base = measurements[0]
        measurements.append(
            replace(
                base,
                param=params,
                dac_state_p=np.tile(params.tb.dac_bstate_p, (100, 1)),
                dac_state_n=np.tile(params.tb.dac_bstate_n, (100, 1)),
                vin_diff_v=np.full(100, vin_diff_v),
                decision=np.ones(100, dtype=np.uint8),
                dac_state_before_p=np.tile(params.tb.dac_astate_p, (100, 1)),
                dac_state_before_n=np.tile(params.tb.dac_astate_n, (100, 1)),
                wave=replace(base.wave, v={**base.wave.v, "vin_diff": np.asarray([[vin_diff_v, vin_diff_v]])}),
            )
        )

    result = cap_mismatch_of(measurements, comparator_offset(measurements[0], comparator_offset_v))

    assert result.effective_fraction[0, 15] == pytest.approx(0.10)
    assert result.effective_fraction[1, 15] == pytest.approx(0.12)
    np.testing.assert_allclose(result.effective_fraction_by_direction[0, 15], (0.11, 0.09))
    np.testing.assert_allclose(result.effective_fraction_by_direction[1, 15], (0.115, 0.125))
    assert result.main_fraction[0, 15] == pytest.approx(0.15)
    assert result.main_fraction[1, 15] == pytest.approx(0.15)
    assert result.diff_fraction[0, 15] == pytest.approx(0.05)
    assert result.diff_fraction[1, 15] == pytest.approx(0.03)
    np.testing.assert_allclose(result.direction_bias[0, 15], (0.02, 0.01))
    np.testing.assert_allclose(result.direction_bias[1, 15], (0.015, -0.005))
    assert np.isnan(result.main_fraction[0, 14])
    assert np.isnan(result.diff_fraction[0, 14])
    assert np.isnan(result.direction_bias[0, 14, 0])


def _curve(side: str, direction: str, diffcaps: int, transition_v: float) -> list[MeasCdac]:
    measurements = []
    for input_index, probability in enumerate((0.0, 0.5, 1.0)):
        vin_diff_v = transition_v + (input_index - 1) * 10e-3
        params = _build_cdac_params(
            adc_index=0,
            side=side,
            element=15,
            direction=direction,
            dac_diffcaps=diffcaps,
            vin_diff_v=vin_diff_v,
            conversions=100,
            sweep_stage="fine",
        )
        ones = round(100 * probability)
        decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
        measurements.append(
            MeasCdac(
                group=params.board_id,
                index=params.observed_adc,
                dut=params.tb.dut.cdac,
                info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 4, tzinfo=UTC)),
                param=params,
                trial_index=np.arange(100),
                dac_state_p=np.tile(params.tb.dac_bstate_p, (100, 1)),
                dac_state_n=np.tile(params.tb.dac_bstate_n, (100, 1)),
                vin_diff_v=np.full(100, vin_diff_v),
                decision=decisions,
                wave=None,
            )
        )
    return measurements


def test_cdac_transition_records_curve_coordinates_and_rejects_mixed_curves() -> None:
    curve = _curve("p", "0to1", 1, 4e-3)
    transition = transition_of(curve)
    assert (transition.side, transition.element, transition.direction, transition.diffcaps) == ("p", 15, "0to1", 1)
    assert transition.valid
    assert transition.transition_v == pytest.approx(4e-3)
    with pytest.raises(ValueError, match="not made from these measurements"):
        analyze_cdac_transition(curve, offset=analyze_comp_offset_noise(_curve("p", "0to1", 1, 9e-3)))
    with pytest.raises(ValueError, match="exactly one switching curve"):
        mixed = [*curve, *_curve("n", "0to1", 1, 4e-3)]
        analyze_cdac_transition(mixed, offset=analyze_comp_offset_noise(mixed))


def test_cdac_cap_mismatch_rejects_mismatched_or_missing_prior_results() -> None:
    curve = _curve("p", "0to1", 1, 4e-3)
    transition = transition_of(curve)
    with pytest.raises(ValueError, match="comparator offset"):
        analyze_cdac_cap_mismatch(curve, transitions=[transition], comparator=comparator_offset(curve[0], 0.0, index=3))
    with pytest.raises(ValueError, match="exactly one fit per measured switching curve"):
        analyze_cdac_cap_mismatch(
            [*curve, *_curve("n", "0to1", 1, 4e-3)],
            transitions=[transition],
            comparator=comparator_offset(curve[0], 0.0),
        )
