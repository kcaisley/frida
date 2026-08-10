"""Software-only tests for typed comparator analyses."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.analysis.comp import (
    analyze_comp_offset_noise,
    analyze_comp_power,
    analyze_comp_timing,
    classify_comp_common_mode_validity,
)
from flow.analysis.types import (
    CompDaq,
    CompIntWave,
    MeasCompInt,
    MeasInfo,
)
from flow.comp.sim import CompTbParams


def comparator_measurement() -> MeasCompInt:
    """Build internal comparator records with known timing and current."""

    time_s = np.linspace(0.0, 20e-9, 2_001)
    trial_index = np.arange(3)
    vin_diff_v = np.asarray([-1e-3, 0.0, 1e-3])
    clock = np.tile(np.where(time_s >= 5e-9, 1.2, 0.0), (3, 1))
    output = np.stack([np.where(time_s >= 7e-9, sign, 0.0) for sign in (-1.0, 0.05, 1.0)])
    zeros = np.zeros_like(output)
    return MeasCompInt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasCompInt",
            backend="spice",
            timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC),
            readbacks={"vdd_v": 1.2},
        ),
        param=CompTbParams(),
        daq=CompDaq(
            trial_index=trial_index,
            vin_diff_v=vin_diff_v,
            vin_cm_v=np.full(3, 0.6),
            decision=np.asarray([0, 1, 1], dtype=np.uint8),
        ),
        wave=CompIntWave(
            trial_index=trial_index,
            time_s=time_s,
            vin_p_v=np.tile((0.6 + vin_diff_v / 2)[:, None], (1, len(time_s))),
            vin_n_v=np.tile((0.6 - vin_diff_v / 2)[:, None], (1, len(time_s))),
            clock_v=clock,
            vout_p_v=0.6 + output / 2,
            vout_n_v=0.6 - output / 2,
            comp_p_v=zeros,
            comp_n_v=zeros,
            vdd_i=np.full_like(output, 10e-6),
        ),
    )


def test_comp_offset_noise_uses_binary_decision_curve() -> None:
    measurements = []
    rng = np.random.default_rng(4)
    for vin_diff_v in np.linspace(-3e-3, 3e-3, 25):
        msmt = comparator_measurement()
        sigma = 0.8e-3
        decisions = rng.random(2_000) < 0.5 * (
            1.0 + np.vectorize(__import__("math").erf)(vin_diff_v / (sigma * np.sqrt(2.0)))
        )
        object.__setattr__(
            msmt,
            "daq",
            CompDaq(
                trial_index=np.arange(len(decisions)),
                vin_diff_v=np.full(len(decisions), vin_diff_v),
                vin_cm_v=np.full(len(decisions), 0.6),
                decision=decisions.astype(np.uint8),
            ),
        )
        measurements.append(msmt)
    result = analyze_comp_offset_noise(measurements)
    assert result.offset_v == pytest.approx(0.0, abs=0.15e-3)
    assert result.noise_sigma_v == pytest.approx(0.8e-3, rel=0.15)
    assert result.decision_polarity == 1
    assert result.validity == "valid"


def test_comp_offset_noise_accepts_descending_physical_polarity() -> None:
    measurements = []
    rng = np.random.default_rng(14)
    for vin_diff_v in np.linspace(-3e-3, 3e-3, 25):
        msmt = comparator_measurement()
        sigma = 0.7e-3
        increasing_probability = 0.5 * (1.0 + np.vectorize(__import__("math").erf)(vin_diff_v / (sigma * np.sqrt(2.0))))
        decisions = rng.random(2_000) >= increasing_probability
        object.__setattr__(
            msmt,
            "daq",
            CompDaq(
                trial_index=np.arange(len(decisions)),
                vin_diff_v=np.full(len(decisions), vin_diff_v),
                vin_cm_v=np.full(len(decisions), 0.8),
                decision=decisions.astype(np.uint8),
            ),
        )
        measurements.append(msmt)

    result = analyze_comp_offset_noise(measurements)
    assert result.offset_v == pytest.approx(0.0, abs=0.15e-3)
    assert result.noise_sigma_v == pytest.approx(sigma, rel=0.15)
    assert result.decision_polarity == -1
    assert result.validity == "valid"


def test_comp_offset_noise_reports_invalid_curves_in_analysis_only() -> None:
    measurements = []
    for vin_diff_v, ones in zip(np.linspace(-2e-3, 2e-3, 5), (0, 90, 10, 100, 100), strict=True):
        msmt = comparator_measurement()
        decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
        object.__setattr__(
            msmt,
            "daq",
            CompDaq(
                trial_index=np.arange(100),
                vin_diff_v=np.full(100, vin_diff_v),
                vin_cm_v=np.full(100, 0.8),
                decision=decisions,
            ),
        )
        measurements.append(msmt)
    result = analyze_comp_offset_noise(measurements)
    assert result.validity == "non_monotonic"
    assert np.isnan(result.offset_v)
    assert np.isnan(result.noise_sigma_v)

    for msmt in measurements:
        object.__setattr__(
            msmt,
            "daq",
            CompDaq(
                trial_index=np.arange(100),
                vin_diff_v=msmt.daq.vin_diff_v,
                vin_cm_v=msmt.daq.vin_cm_v,
                decision=np.zeros(100, dtype=np.uint8),
            ),
        )
    result = analyze_comp_offset_noise(measurements)
    assert result.validity == "unbracketed"
    assert np.isnan(result.offset_v)


def test_comp_offset_noise_accounts_for_batched_correlation_and_wander() -> None:
    batch_ones = (
        (0,) * 10,
        (98, 93, 90, 99, 96, 100, 94, 98, 99, 100),
        (100, 92, 86, 99, 87, 99, 94, 95, 80, 92),
        (100,) * 10,
    )
    measurements = []
    for vin_diff_v, ones_per_batch in zip(
        (-1e-3, 0.0, 0.1e-3, 1e-3),
        batch_ones,
        strict=True,
    ):
        decisions = np.concatenate(
            [
                np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
                for ones in ones_per_batch
            ]
        )
        base = comparator_measurement()
        measurements.append(
            replace(
                base,
                info=replace(
                    base.info,
                    readbacks={
                        "capture_batch_count": 10,
                        "capture_batch_trials": 100,
                        "capture_batch_interval_s": 0.5,
                    },
                ),
                daq=CompDaq(
                    trial_index=np.arange(len(decisions)),
                    vin_diff_v=np.full(len(decisions), vin_diff_v),
                    vin_cm_v=np.full(len(decisions), 0.8),
                    decision=decisions,
                ),
            )
        )

    unbatched = [replace(msmt, info=replace(msmt.info, readbacks={})) for msmt in measurements]
    assert analyze_comp_offset_noise(unbatched).validity == "non_monotonic"
    batched = analyze_comp_offset_noise(measurements)
    assert batched.validity == "valid"
    assert batched.decision_polarity == 1

    contiguous_batches = [
        replace(
            msmt,
            info=replace(msmt.info, readbacks={**msmt.info.readbacks, "capture_batch_interval_s": 0.0}),
        )
        for msmt in measurements
    ]
    assert analyze_comp_offset_noise(contiguous_batches).validity == "valid"


def test_comp_offset_noise_combines_numerically_equivalent_voltage_bins() -> None:
    measurements = []
    points = (
        (-1e-3, np.zeros(10, dtype=np.uint8)),
        (0.0, np.zeros(10, dtype=np.uint8)),
        (0.1 + 0.2 - 0.3, np.ones(10, dtype=np.uint8)),
        (1e-3, np.ones(10, dtype=np.uint8)),
    )
    for vin_diff_v, decisions in points:
        msmt = comparator_measurement()
        object.__setattr__(
            msmt,
            "daq",
            CompDaq(
                trial_index=np.arange(len(decisions)),
                vin_diff_v=np.full(len(decisions), vin_diff_v),
                vin_cm_v=np.full(len(decisions), 0.8),
                decision=decisions,
            ),
        )
        measurements.append(msmt)

    result = analyze_comp_offset_noise(measurements)
    np.testing.assert_array_equal(result.vin_diff_v, (-1e-3, 0.0, 1e-3))
    np.testing.assert_array_equal(result.trial_count, (10, 20, 10))
    np.testing.assert_allclose(result.decision_probability, (0.0, 0.5, 1.0))


def test_common_mode_context_classifies_only_exercised_stuck_outputs() -> None:
    def group(vin_cm_v: float, probabilities: tuple[float, ...], *, center_v: float = 0.0) -> list[MeasCompInt]:
        measurements = []
        for vin_diff_v, probability in zip(
            np.linspace(center_v - 2e-3, center_v + 2e-3, len(probabilities)),
            probabilities,
            strict=True,
        ):
            base = comparator_measurement()
            ones = round(100 * probability)
            measurements.append(
                replace(
                    base,
                    daq=CompDaq(
                        trial_index=np.arange(100),
                        vin_diff_v=np.full(100, vin_diff_v),
                        vin_cm_v=np.full(100, vin_cm_v),
                        decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
                    ),
                )
            )
        return measurements

    valid = group(0.6, (0.0, 0.5, 1.0))
    stuck_low = group(0.8, (0.0, 0.0, 0.0))
    stuck_high = group(1.0, (1.0, 1.0, 1.0))
    groups = [valid, stuck_low, stuck_high]
    classified = classify_comp_common_mode_validity(
        groups,
        [analyze_comp_offset_noise(values) for values in groups],
    )
    assert [analysis.validity for analysis in classified] == ["valid", "stuck-low", "stuck-high"]

    isolated = classify_comp_common_mode_validity(
        [stuck_low],
        [analyze_comp_offset_noise(stuck_low)],
    )
    assert isolated[0].validity == "unbracketed"
    outside_neighbor_transition = group(0.8, (0.0, 0.0, 0.0), center_v=0.012)
    outside = classify_comp_common_mode_validity(
        [valid, outside_neighbor_transition],
        [analyze_comp_offset_noise(valid), analyze_comp_offset_noise(outside_neighbor_transition)],
    )
    assert outside[1].validity == "unbracketed"


def test_comp_timing_and_power_use_internal_waveforms() -> None:
    msmt = comparator_measurement()
    timing = analyze_comp_timing(
        [msmt],
        unresolved_threshold_v=0.1,
    )
    assert timing.clock_to_decision_s[0] == pytest.approx(2e-9, abs=20e-12)
    np.testing.assert_array_equal(timing.unresolved, (0, 1, 0))

    power = analyze_comp_power([msmt])
    assert power.average_power_w[0] == pytest.approx(12e-6)
