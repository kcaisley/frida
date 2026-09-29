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


def test_settling_time_preserves_boolean_validity_sample_boundaries() -> None:
    assert calc.settlingTime([False, True, False, True, True], np.arange(5.0)) == pytest.approx(3.0)
    assert calc.settlingTime([True, True], [0.0, 1.0]) == pytest.approx(0.0)
    assert np.isnan(calc.settlingTime([False, True, False], [0.0, 1.0, 2.0]))
    assert np.isnan(calc.settlingTime([True, False], [0.0, np.nan]))
    assert np.isnan(calc.settlingTime([True], [0.0]))
    with pytest.raises(ValueError, match="Boolean validity"):
        calc.settlingTime([False, True], [0.0, 1.0], final=1.0)


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


def test_median_period_frequency_rejects_nearby_edges_and_long_gaps() -> None:
    axis = np.arange(0.0, 12.0, 0.25)
    signal = np.full(len(axis), -1.0)
    for edge in (1.0, 1.5, 3.0, 5.0, 11.0):
        signal[(axis >= edge) & (axis < edge + 0.25)] = 1.0
    assert calc.frequency(
        signal, axis, threshold=0.0, method="median_period", minimum_separation=1.0, minimum_crossings=3
    ) == pytest.approx(0.5)
    assert np.isnan(
        calc.frequency(signal, axis, threshold=0.0, method="median_period", minimum_separation=1.0, minimum_crossings=5)
    )
    assert calc.frequency(signal, axis, threshold=0.0) == pytest.approx(0.4)


def test_waveform_jitter_uses_crossings_and_mean_period_by_default() -> None:
    axis = [-0.5, 0.5, 0.6, 1.4, 1.7, 2.7]
    signal = [-1.0, 1.0, -1.0, 1.0, -1.0, 1.0]
    np.testing.assert_allclose(calc.abs_jitter(signal, axis, threshold=0.0, nominal_period=1.0), [0.0, 0.0, 0.2])
    np.testing.assert_allclose(calc.period_jitter(signal, axis, threshold=0.0), [-0.1, 0.1])
    np.testing.assert_allclose(calc.period_jitter(signal, axis, threshold=0.0, nominal_period=1.0), [0.0, 0.2])


def test_jitter_axes_units_moving_reference_and_scalar_output() -> None:
    axis = [-0.5, 0.5, 0.6, 1.4, 1.7, 2.7, 2.8, 3.4]
    signal = [-1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0]
    absolute = calc.abs_jitter(signal, axis, threshold=0.0, nominal_period=1.0, x_unit="crossing_time", y_unit="rad")
    assert isinstance(absolute, tuple)
    crossing_time, phase = absolute
    np.testing.assert_allclose(crossing_time, [0.0, 1.0, 2.2, 3.1])
    np.testing.assert_allclose(phase, [0.0, 0.0, 0.4 * np.pi, 0.2 * np.pi])
    absolute = calc.abs_jitter(
        signal, axis, threshold=0.0, nominal_period=1.0, zero_ref=-0.1, x_unit="time", y_unit="ui"
    )
    assert isinstance(absolute, tuple)
    reference_time, ui = absolute
    np.testing.assert_allclose(reference_time, [-0.1, 0.9, 1.9, 2.9])
    np.testing.assert_allclose(ui, [0.1, 0.1, 0.3, 0.2])
    absolute = calc.abs_jitter(signal, axis, threshold=0.0, nominal_period=1.0, x_unit="cycle", y_unit="deg")
    assert isinstance(absolute, tuple)
    cycles, degrees = absolute
    np.testing.assert_allclose(cycles, [1.0, 2.0, 3.0, 4.0])
    np.testing.assert_allclose(degrees, [0.0, 0.0, 72.0, 36.0])
    period_result = calc.period_jitter(signal, axis, threshold=0.0, bin_size=2, x_unit="cycle")
    assert isinstance(period_result, tuple)
    cycles, moving = period_result
    np.testing.assert_allclose(cycles, [1.0, 2.0, 3.0])
    np.testing.assert_allclose(moving, [0.0, 0.1, -0.15])
    period_result = calc.period_jitter(signal, axis, threshold=0.0, x_unit="time")
    assert isinstance(period_result, tuple)
    trailing_edges, period_error = period_result
    np.testing.assert_allclose(trailing_edges, [1.0, 2.2, 3.1])
    np.testing.assert_allclose(period_error, [-1.0 / 30.0, 1.0 / 6.0, -2.0 / 15.0])
    assert calc.period_jitter(signal, axis, threshold=0.0, nominal_period=1.0, output_type="sd") == pytest.approx(
        np.std([0.0, 0.2, -0.1])
    )
    with pytest.raises(ValueError, match="bin_size cannot"):
        calc.period_jitter(signal, axis, threshold=0.0, nominal_period=1.0, bin_size=2)
    with pytest.raises(ValueError, match="cannot have an x axis"):
        calc.period_jitter(signal, axis, threshold=0.0, output_type="sd", x_unit="cycle")
    assert np.isnan(calc.period_jitter([0.0], [0.0], output_type="sd"))


def test_period_jitter_auto_threshold_uses_time_average() -> None:
    axis = np.arange(18.0)
    signal = [0, 2, 2, 0, 0, 0, 0, 3, 3, 0, 0, 0, 0, 4, 4, 0, 0, 0]
    assert calc.average(signal, axis) == pytest.approx(18.0 / 17.0)
    np.testing.assert_allclose(calc.period_jitter(signal, axis), [-0.0441176470588234, 0.0441176470588234])
    np.testing.assert_allclose(calc.period_jitter(signal, axis, threshold=2.0), [-1.0 / 12.0, 1.0 / 12.0])


def test_eye_diagram_folds_requested_interval_into_waveform() -> None:
    axis = np.arange(0.0, 8.5, 0.5)
    signal = 2 * axis
    folded = calc.eyeDiagram(signal, 1.0, 7.0, 2.0, axis=axis)
    np.testing.assert_allclose(folded[[0, 4, 6], 0], [0.0, 2.0, 0.0])
    np.testing.assert_allclose(folded[[0, 4, 6], 1], [2.0, 6.0, 6.0])
    assert np.isnan(folded[5]).all()
    np.testing.assert_allclose(calc.eyeDiagram(np.arange(9.0), 1.0, 7.0, 2.0)[-1], [2.0, 7.0])


def test_eye_diagram_interpolates_uneven_off_grid_windows() -> None:
    axis = [0.0, 0.8, 1.7, 2.8, 4.2]
    folded = calc.eyeDiagram(np.asarray(axis) * 2.0, 0.5, 3.3, 1.5, axis=axis)
    np.testing.assert_allclose(folded[:4], [[0.0, 1.0], [0.3, 1.6], [1.2, 3.4], [1.5, 4.0]])
    assert np.isnan(folded[4]).all()
    np.testing.assert_allclose(folded[5:], [[0.0, 4.0], [0.8, 5.6], [1.3, 6.6]])


def test_eye_segments_preserve_origin_identity_and_window_bounds() -> None:
    axis = np.arange(0.0, 8.5, 0.5)
    signal = 2 * axis
    segments = calc._eye_segments(signal, axis, 2.0, 1.0, count=3, window=(0.0, 1.0))
    assert [index for index, _ in segments] == [0, 1, 2]
    np.testing.assert_allclose(segments[0][1], np.column_stack((np.arange(0.0, 1.25, 0.25), [2, 3, 4, 5, 6])))
    np.testing.assert_allclose(segments[1][1][:, 0], segments[0][1][:, 0])
    assert [index for index, _ in calc._eye_segments(signal, axis, 2.0, [1.0, 7.0], complete=True)] == [0]
    assert calc._eye_segments(signal, axis, 2.0, [7.0], window=(0.0, 1.0), complete=True) == ()


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
    counts, edges = np.histogram([0.1, 0.9, 1.1, 1.9], bins=2, range=(0.0, 2.0))
    np.testing.assert_array_equal(counts, [2, 2])
    np.testing.assert_allclose(edges, [0.0, 1.0, 2.0])
    np.testing.assert_allclose(calc.dnl([90, 100, 110], ideal_count=100), [-0.1, 0.0, 0.1])
    np.testing.assert_allclose(calc.inl([-0.1, 0.0, 0.1], endpoint_correct=False), [-0.1, -0.1, 0.0])
    assert np.median([1.0, 2.0, 9.0]) == pytest.approx(2.0)
    np.testing.assert_allclose(np.percentile([0.0, 10.0], (25.0, 75.0)), [2.5, 7.5])
    assert calc.xmin([2.0, 1.0, 3.0], [0.0, 1.0, 2.0]) == pytest.approx(1.0)
    assert calc.xmax([2.0, 1.0, 3.0], [0.0, 1.0, 2.0]) == pytest.approx(2.0)
