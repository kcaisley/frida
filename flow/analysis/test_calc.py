"""Numerical behavior of the reusable signal calculator."""

from __future__ import annotations

import numpy as np
import pytest

from flow.analysis import calc


def test_crossings_and_delay_interpolate_events() -> None:
    time_s = np.linspace(0.0, 4.0, 401)
    clock = np.sin(2.0 * np.pi * time_s)
    response = np.sin(2.0 * np.pi * (time_s - 0.1))

    crossings = calc.cross(clock, time_s, 0.0, edge="rising")
    assert crossings[0] == pytest.approx(1.0)
    _trigger, _response, delay = calc.delay(
        clock,
        response,
        time_s,
        0.0,
        0.0,
    )
    assert delay == pytest.approx(0.1, abs=1e-3)


def test_settling_and_power() -> None:
    time_s = np.linspace(0.0, 10.0, 1_001)
    settled = 1.0 - np.exp(-time_s)
    settling = calc.settlingTime(
        settled,
        time_s,
        initial=0.0,
        final=1.0,
        percent_of_step=1.0,
    )
    assert 4.0 < settling < 6.0
    assert calc.average(np.full(len(time_s), 1e-3) * 1.2) == pytest.approx(1.2e-3)


def test_cross_edge_selection_and_occurrence() -> None:
    axis = np.arange(5.0)
    signal = np.array([-1.0, 1.0, -1.0, 1.0, -1.0])
    np.testing.assert_allclose(calc.cross(signal, axis, 0.0, edge="either"), [0.5, 1.5, 2.5, 3.5])
    assert calc.cross(signal, axis, 0.0, edge="rising", occurrence=-1) == pytest.approx(2.5)
    assert np.isnan(calc.cross(signal, axis, 0.0, occurrence=3))


def test_clip_value_and_time_weighted_average() -> None:
    axis = np.array([0.0, 1.0, 3.0])
    signal = np.array([0.0, 2.0, 2.0])
    clipped, clipped_axis = calc.clip(signal, axis, 0.5, 2.0)
    np.testing.assert_allclose(clipped_axis, [0.5, 1.0, 2.0])
    np.testing.assert_allclose(clipped, [1.0, 2.0, 2.0])
    assert calc.value(signal, axis, 2.0) == pytest.approx(2.0)
    assert calc.value(signal, axis, 2.0, method="roundDown") == pytest.approx(2.0)
    assert calc.integ(signal, axis) == pytest.approx(5.0)
    assert calc.average(signal, axis) == pytest.approx(5.0 / 3.0)
    assert calc.average(signal) == pytest.approx(4.0 / 3.0)
    sampled, sample_axis = calc.sample(signal, axis, 0.0, 3.0, 0.5)
    np.testing.assert_allclose(sample_axis, np.arange(0.0, 3.5, 0.5))
    np.testing.assert_allclose(sampled, np.minimum(2.0 * sample_axis, 2.0))


def test_step_based_settling_and_absolute_band() -> None:
    axis = np.arange(5.0)
    signal = np.array([10.0, 20.0, 21.0, 19.9, 20.0])
    assert calc.settlingTime(signal, axis, initial=10.0, final=20.0, percent_of_step=2.0) == pytest.approx(3.0)
    assert calc.settlingTime(signal, axis, final=20.0, absolute_tolerance=1.0) == pytest.approx(1.0)


def test_spectral_and_density_operations() -> None:
    sample_rate = 128.0
    signal = np.sin(2.0 * np.pi * 8.0 * np.arange(128) / sample_rate)
    frequency, transform = calc.dft(signal, sample_rate)
    assert frequency[np.argmax(np.abs(transform))] == pytest.approx(8.0)
    psd_frequency, power_density = calc.psd(signal, sample_rate=sample_rate)
    assert psd_frequency[np.argmax(power_density)] == pytest.approx(8.0)
    assert calc.rmsNoise(np.ones(3), np.array([0.0, 1.0, 2.0])) == pytest.approx(np.sqrt(2.0))
    assert calc.thd(100.0, 1.0) == pytest.approx(-20.0)
    assert calc.frequency(signal, np.arange(128) / sample_rate, threshold=0.0) == pytest.approx(8.0)
