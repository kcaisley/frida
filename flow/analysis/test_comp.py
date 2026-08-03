"""Software-only tests for typed comparator analyses."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from flow.analysis.comp import (
    analyze_comp_offset_noise,
    analyze_comp_power,
    analyze_comp_timing,
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
            decision=np.asarray([0, 1, 1]),
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
