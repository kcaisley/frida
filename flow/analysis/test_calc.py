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


def test_cross_distinguishes_interior_contact_from_endpoint_contact() -> None:
    axis = np.arange(5.0)
    touch = np.array([0.0, 1.0, 0.0, -1.0, 0.0])
    assert np.isnan(calc.cross(touch, axis, 0.0, edge="rising", occurrence=1))
    assert np.isnan(calc.cross(touch, axis, 0.0, edge="rising", occurrence=-1))
    np.testing.assert_allclose(calc.cross(touch, axis, 0.0, edge="falling"), [2.0])
    plateau = np.array([-1.0, 0.0, 0.0, 1.0, -1.0])
    np.testing.assert_allclose(calc.cross(plateau, axis, 0.0, edge="rising"), [1.0])
    np.testing.assert_allclose(calc.cross(plateau, axis, 0.0, edge="falling"), [3.5])
    interior_touch = np.array([-1.0, 0.0, -1.0])
    assert calc.cross(interior_touch, axis[:3], 0.0, edge="rising", occurrence=1) == pytest.approx(1.0)
    np.testing.assert_allclose(calc.cross(interior_touch, axis[:3], 0.0, edge="either"), [1.0])
    falling_plateau = np.array([-1.0, 1.0, 0.0, 0.0, -1.0, 1.0])
    assert calc.cross(falling_plateau, np.arange(6.0), 0.0, edge="falling", occurrence=1) == pytest.approx(2.0)


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


def test_settling_band_and_absolute_tolerance() -> None:
    axis = np.arange(5.0)
    signal = np.array([10.0, 20.0, 21.0, 19.9, 20.0])
    assert calc.settlingTime(signal, axis, initial=10.0, final=20.0, percent_of_step=2.0) == pytest.approx(2.727272727)
    assert calc.settlingTime(signal, axis, final=20.0, absolute_tolerance=1.0) == pytest.approx(0.9)


def test_settling_time_interpolates_the_last_band_entry() -> None:
    assert calc.settlingTime(
        [0.0, 1.2, 0.8, 1.0], [0.0, 1.0, 2.0, 3.0], initial=0.0, final=1.0, percent_of_step=10.0
    ) == pytest.approx(2.5)


def test_continuous_stddev_weights_the_independent_axis() -> None:
    signal = [0.0, 2.0, 2.0]
    axis = [0.0, 1.0, 3.0]
    assert calc.stddev(signal) == pytest.approx(0.9428090415820634)
    assert calc.stddev(signal, axis) == pytest.approx(0.7453559924999299)
    with pytest.raises(ValueError, match="discrete observations"):
        calc.stddev(signal, axis, sample=True)


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


def test_dft_reports_one_sided_signal_amplitudes() -> None:
    frequency, amplitudes = calc.dft(np.full(8, 2.0), 1.0)
    assert frequency[0] == 0.0
    assert abs(amplitudes[0]) == pytest.approx(2.0)
    sine = [0.0, 1.0, 0.0, -1.0, 0.0, 1.0, 0.0, -1.0]
    frequency, amplitudes = calc.dft(sine, 1.0)
    assert abs(amplitudes[np.flatnonzero(frequency == 0.25)[0]]) == pytest.approx(1.0)
    frequency, amplitudes = calc.dft([1.0, -1.0] * 4, 1.0)
    assert abs(amplitudes[-1]) == pytest.approx(1.0)


def test_transfer_linearity_composes_from_calculator_operations() -> None:
    code = np.array([0.0, 1.0, 3.0, 4.0])
    transfer = np.array([0.0, 1.1, 3.0, 4.2])
    np.testing.assert_allclose(calc.deriv(transfer, code), [1.1, 0.95, 1.2])
    counts, edges = calc.histogram([0.1, 0.9, 1.1, 1.9], bins=2, value_range=(0.0, 2.0))
    np.testing.assert_array_equal(counts, [2, 2])
    np.testing.assert_allclose(edges, [0.0, 1.0, 2.0])
    np.testing.assert_allclose(calc.dnl([90, 100, 110], ideal_count=100), [-0.1, 0.0, 0.1])
    np.testing.assert_allclose(calc.inl([-0.1, 0.0, 0.1], endpoint_correct=False), [-0.1, -0.1, 0.0])
    assert calc.linear_fit([1.0, 3.0, 5.0], [0.0, 1.0, 2.0]) == pytest.approx((2.0, 1.0))
    assert calc.median([1.0, 2.0, 9.0]) == pytest.approx(2.0)
    np.testing.assert_allclose(calc.percentile([0.0, 10.0], (25.0, 75.0)), [2.5, 7.5])
    assert calc.xmin([2.0, 1.0, 3.0], [0.0, 1.0, 2.0]) == pytest.approx(1.0)
    assert calc.xmax([2.0, 1.0, 3.0], [0.0, 1.0, 2.0]) == pytest.approx(2.0)


def test_sine_fit_recovers_signal_with_frequency_error() -> None:
    sample_rate = 1000.0
    time_s = np.arange(1000) / sample_rate
    signal = 2.0 + 3.0 * np.sin(2.0 * np.pi * 41.25 * time_s + 0.4)
    fit = calc.sine_fit(signal, sample_rate=sample_rate, frequency=41.0, frequency_search_fraction=0.02)
    assert fit.frequency_hz == pytest.approx(41.25, abs=1e-5)
    assert fit.amplitude == pytest.approx(3.0, abs=1e-5)
    assert fit.phase_rad == pytest.approx(0.4, abs=1e-5)
    assert fit.offset == pytest.approx(2.0, abs=1e-5)
    assert fit.residual_rms < 1e-5
    np.testing.assert_allclose(fit.time_s, time_s)
    np.testing.assert_allclose(fit.fitted, signal, atol=1e-5)
    np.testing.assert_allclose(fit.residual, np.zeros_like(signal), atol=1e-5)
