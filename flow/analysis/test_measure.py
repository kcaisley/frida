"""Software-only tests for direct numerical waveform helpers."""

from __future__ import annotations

import numpy as np
import pytest

from flow.analysis.measure import (
    find_crossings,
    measure_average_power,
    measure_delay,
    measure_settling,
)


def test_crossings_and_delay_interpolate_events() -> None:
    time_s = np.linspace(0.0, 4.0, 401)
    clock = np.sin(2.0 * np.pi * time_s)
    response = np.sin(2.0 * np.pi * (time_s - 0.1))

    crossings = find_crossings(clock, time_s, 0.0, rising=True)
    assert crossings[0] == pytest.approx(1.0)
    _trigger, _response, delay = measure_delay(
        time_s,
        clock,
        response,
        0.0,
        0.0,
    )
    assert delay == pytest.approx(0.1, abs=1e-3)


def test_settling_and_power() -> None:
    time_s = np.linspace(0.0, 10.0, 1_001)
    settled = 1.0 - np.exp(-time_s)
    settling = measure_settling(
        time_s,
        settled,
        target=1.0,
        relative_tolerance=0.01,
    )
    assert 4.0 < settling < 6.0
    assert measure_average_power(np.full(len(time_s), 1e-3), 1.2) == pytest.approx(1.2e-3)
