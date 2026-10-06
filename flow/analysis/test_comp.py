"""Software-only tests for typed comparator analyses."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.analysis.comp import (
    analyze_comp_candidate,
    analyze_comp_common_mode,
    analyze_comp_offset_noise,
    analyze_comp_power,
    analyze_comp_timing,
)
from flow.analysis.types import (
    MeasComp,
    MeasInfo,
    Wave,
)
from flow.comp.sim import CompTbParams


def comparator_measurement() -> MeasComp:
    """Build internal comparator records with known timing and current."""

    time_s = np.linspace(0.0, 20e-9, 2_001)
    trial_index = np.arange(3)
    vin_diff_v = np.asarray([-1e-3, 0.0, 1e-3])
    clock = np.tile(np.where(time_s >= 5e-9, 1.2, 0.0), (3, 1))
    output = np.stack([np.where(time_s >= 7e-9, sign, 0.0) for sign in (-1.0, 0.05, 1.0)])
    params = CompTbParams()
    return MeasComp(
        group=None,
        index=None,
        dut=params.comp,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC), readbacks={"vdd_v": 1.2}),
        param=params,
        trial_index=trial_index,
        vin_diff_v=vin_diff_v,
        vin_cm_v=np.full(3, 0.6),
        decision=np.asarray([0, 1, 1], dtype=np.uint8),
        wave=Wave(
            record_index=trial_index,
            time_s=time_s,
            v={
                "inp": np.tile((0.6 + vin_diff_v / 2)[:, None], (1, len(time_s))),
                "inn": np.tile((0.6 - vin_diff_v / 2)[:, None], (1, len(time_s))),
                "clk": clock,
                "outp": 0.6 + output / 2,
                "outn": 0.6 - output / 2,
                "latch_p": 0.6 + output / 2,
                "latch_n": 0.6 - output / 2,
            },
            i={"vdd": np.full_like(output, 1e-05)},
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
        msmt = replace(
            msmt,
            trial_index=np.arange(len(decisions)),
            vin_diff_v=np.full(len(decisions), vin_diff_v),
            vin_cm_v=np.full(len(decisions), 0.6),
            decision=decisions.astype(np.uint8),
        )
        measurements.append(msmt)
    result = analyze_comp_offset_noise(measurements)
    assert result.offset_v == pytest.approx(0.0, abs=0.15e-3)
    assert result.noise_sigma_v == pytest.approx(0.8e-3, rel=0.15)
    assert result.decision_polarity == 1
    assert result.validity == "valid"


@pytest.mark.parametrize("one_counts, expected_offset", (((0, 5, 5, 10), 1e-3), ((0, 2, 5), math.nan)))
def test_comp_offset_uses_first_contact_and_requires_a_bracketed_crossing(one_counts, expected_offset) -> None:
    msmt = comparator_measurement()
    trials = 10
    sample_count = trials * len(one_counts)
    decisions = np.concatenate([np.r_[np.ones(count), np.zeros(trials - count)] for count in one_counts])
    msmt = replace(
        msmt,
        trial_index=np.arange(sample_count),
        vin_diff_v=np.repeat(np.arange(len(one_counts)) * 1e-3, trials),
        vin_cm_v=np.full(sample_count, 0.6),
        decision=decisions,
    )
    analysis = analyze_comp_offset_noise([msmt])
    if math.isnan(expected_offset):
        assert math.isnan(analysis.offset_v)
        assert analysis.validity == "unbracketed"
    else:
        assert analysis.offset_v == pytest.approx(expected_offset)
        assert analysis.noise_sigma_v == pytest.approx(1.18269e-3)
        assert analysis.validity == "valid"


def test_comp_offset_noise_accepts_descending_physical_polarity() -> None:
    measurements = []
    rng = np.random.default_rng(14)
    for vin_diff_v in np.linspace(-3e-3, 3e-3, 25):
        msmt = comparator_measurement()
        sigma = 0.7e-3
        increasing_probability = 0.5 * (1.0 + np.vectorize(__import__("math").erf)(vin_diff_v / (sigma * np.sqrt(2.0))))
        decisions = rng.random(2_000) >= increasing_probability
        msmt = replace(
            msmt,
            trial_index=np.arange(len(decisions)),
            vin_diff_v=np.full(len(decisions), vin_diff_v),
            vin_cm_v=np.full(len(decisions), 0.8),
            decision=decisions.astype(np.uint8),
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
        msmt = replace(
            msmt,
            trial_index=np.arange(100),
            vin_diff_v=np.full(100, vin_diff_v),
            vin_cm_v=np.full(100, 0.8),
            decision=decisions,
        )
        measurements.append(msmt)
    result = analyze_comp_offset_noise(measurements)
    assert result.validity == "non_monotonic"
    assert np.isnan(result.offset_v)
    assert np.isnan(result.noise_sigma_v)

    measurements = [replace(msmt, decision=np.zeros(100, dtype=np.uint8)) for msmt in measurements]
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
                trial_index=np.arange(len(decisions)),
                vin_diff_v=np.full(len(decisions), vin_diff_v),
                vin_cm_v=np.full(len(decisions), 0.8),
                decision=decisions,
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
        msmt = replace(
            msmt,
            trial_index=np.arange(len(decisions)),
            vin_diff_v=np.full(len(decisions), vin_diff_v),
            vin_cm_v=np.full(len(decisions), 0.8),
            decision=decisions,
        )
        measurements.append(msmt)

    result = analyze_comp_offset_noise(measurements)
    np.testing.assert_array_equal(result.vin_diff_v, (-1e-3, 0.0, 1e-3))
    np.testing.assert_array_equal(result.trial_count, (10, 20, 10))
    np.testing.assert_allclose(result.decision_probability, (0.0, 0.5, 1.0))


def test_common_mode_context_classifies_only_exercised_stuck_outputs() -> None:
    def group(vin_cm_v: float, probabilities: tuple[float, ...], *, center_v: float = 0.0) -> list[MeasComp]:
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
                    trial_index=np.arange(100),
                    vin_diff_v=np.full(100, vin_diff_v),
                    vin_cm_v=np.full(100, vin_cm_v),
                    decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
                )
            )
        return measurements

    def classify(*groups: list[MeasComp]):
        measurements = [measurement for values in groups for measurement in values]
        return analyze_comp_common_mode(measurements, offsets=[analyze_comp_offset_noise(values) for values in groups])

    valid = group(0.6, (0.0, 0.5, 1.0))
    stuck_low = group(0.8, (0.0, 0.0, 0.0))
    stuck_high = group(1.0, (1.0, 1.0, 1.0))
    classified = classify(valid, stuck_low, stuck_high)
    assert classified.validity == ("valid", "stuck-low", "stuck-high")
    np.testing.assert_allclose(classified.vin_cm_v, (0.6, 0.8, 1.0))

    assert classify(stuck_low).validity == ("unbracketed",)
    outside_neighbor_transition = group(0.8, (0.0, 0.0, 0.0), center_v=0.012)
    assert classify(valid, outside_neighbor_transition).validity == ("valid", "unbracketed")

    # Single-common-mode fits cannot report a stuck output; only the
    # common-mode analysis, which sees the neighbors, can.
    assert analyze_comp_offset_noise(stuck_low).validity == "unbracketed"
    with pytest.raises(ValueError, match="one fit per measured common mode"):
        analyze_comp_common_mode([*valid, *stuck_low], offsets=[analyze_comp_offset_noise(valid)])
    with pytest.raises(ValueError, match="one input common mode"):
        analyze_comp_offset_noise([*valid, *stuck_low])


def test_comp_timing_and_power_use_internal_waveforms() -> None:
    msmt = comparator_measurement()
    timing = analyze_comp_timing([msmt])
    assert timing.clock_to_decision_s[0] == pytest.approx(2e-9, abs=20e-12)
    np.testing.assert_array_equal(timing.unresolved, (0, 1, 0))

    power = analyze_comp_power([msmt])
    assert power.average_power_w[0] == pytest.approx(12e-6)
    assert power.energy_per_decision_j[0] == pytest.approx(480e-15)


def test_comp_settling_starts_at_the_interpolated_clock_trigger() -> None:
    msmt = comparator_measurement()
    assert msmt.wave is not None
    time_s = np.asarray((0.0, 2.0, 4.0)) * 1e-9
    voltage = {name: values[:, :3] for name, values in msmt.wave.v.items()}
    voltage.update(
        clk=np.tile((0.0, 1.2, 1.2), (3, 1)),
        latch_p=np.tile((0.5, 0.75, 1.0), (3, 1)),
        latch_n=np.tile((0.5, 0.25, 0.0), (3, 1)),
    )
    msmt = replace(
        msmt,
        wave=replace(msmt.wave, time_s=time_s, v=voltage, i={"vdd": np.zeros((3, 3))}),
    )
    assert msmt.wave is not None
    timing = analyze_comp_timing([msmt])
    # Clock crosses at 1 ns, where the differential output is 0.25 V.
    # Its 1% band starts at 0.9925 V, reached at 3.97 ns.
    np.testing.assert_allclose(timing.clock_to_decision_s, 1e-9)
    np.testing.assert_allclose(timing.settling_s, 2.97e-9)


def test_comp_power_time_weights_each_trial_and_preserves_stored_power() -> None:
    msmt = comparator_measurement()
    assert msmt.wave is not None
    time_s = np.asarray((0.0, 1.0, 10.0)) * 1e-9
    current = np.asarray((10.0, 20.0, -30.0))[:, None] * np.asarray((0.0, 1.0, 1.0)) * 1e-6
    msmt = replace(
        msmt,
        wave=replace(
            msmt.wave,
            time_s=time_s,
            v={name: values[:, :3] for name, values in msmt.wave.v.items()},
            i={"vdd": current},
        ),
    )
    assert msmt.wave is not None
    # The ramp occupies 1 ns and the plateau 9 ns: each rectified mean
    # is 95% of its plateau, then the three trial powers are averaged.
    power = analyze_comp_power([msmt])
    assert power.average_power_w[0] == pytest.approx(22.8e-6)
    msmt = replace(msmt, info=replace(msmt.info, readbacks={"vdd_active_average_power_w": 77e-6}))
    assert msmt.wave is not None
    assert analyze_comp_power([msmt]).average_power_w[0] == pytest.approx(77e-6)


def test_comp_candidate_sweep_reuses_metrics_and_orders_by_total_active_area() -> None:
    base = comparator_measurement()
    inputs = np.repeat(np.linspace(-2e-3, 2e-3, 5), 100)
    decisions = np.concatenate(
        [
            np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
            for ones in (0, 25, 50, 75, 100)
        ]
    )
    daq = {
        "trial_index": np.arange(len(inputs)),
        "vin_diff_v": inputs,
        "vin_cm_v": np.full(len(inputs), 0.8),
        "decision": decisions,
    }

    def candidate(candidate_id: str, width: int, area: int) -> MeasComp:
        return replace(
            base,
            info=replace(
                base.info,
                readbacks={
                    "vdd_v": 1.2,
                    "vdd_active_average_power_w": width * 1e-9,
                    "energy_per_decision_j": width * 40e-18,
                    "candidate_id": candidate_id,
                    "candidate_label": candidate_id,
                    "topology_index": width,
                    "size_profile": "half",
                    "total_width_units": width,
                    "device_width_signature": f"M0:{width}",
                    "total_active_area_units": area,
                    "total_active_area_um2": area * 0.0072,
                    "device_geometry_signature": f"M0:{width}:{area}",
                },
            ),
            **daq,
        )

    candidates = []
    for measurement in (
        candidate("larger-area", width=100, area=200),
        candidate("smaller-area", width=200, area=100),
    ):
        candidates.append(
            analyze_comp_candidate(
                measurement,
                offset=analyze_comp_offset_noise([measurement]),
                timing=analyze_comp_timing([measurement]),
                power=analyze_comp_power([measurement]),
            )
        )
    np.testing.assert_allclose([candidate.total_active_area_um2 for candidate in candidates], [1.44, 0.72])
    np.testing.assert_allclose([candidate.average_power_w for candidate in candidates], [100e-9, 200e-9])
    assert all(candidate.validity == "valid" for candidate in candidates)
    np.testing.assert_allclose([candidate.maximum_settling_s for candidate in candidates], 30e-9)
    assert [candidate.total_width_units for candidate in candidates] == [100, 200]


def test_comp_candidate_rejects_a_prior_result_of_another_design() -> None:
    measurement = comparator_measurement()
    other_params = replace(measurement.param, comp=replace(measurement.param.comp, tail_w=99))
    other = replace(measurement, dut=other_params.comp, param=other_params)
    with pytest.raises(ValueError, match="does not match"):
        analyze_comp_candidate(
            measurement,
            offset=analyze_comp_offset_noise([other]),
            timing=analyze_comp_timing([measurement]),
            power=analyze_comp_power([measurement]),
        )
