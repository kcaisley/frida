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


def test_transition_times_and_slew_match_piecewise_linear_reference() -> None:
    axis = [0.0, 1.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    signal = [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
    np.testing.assert_allclose(calc.riseTime(signal, axis, 0.0, 1.0, occurrence=None), [1.6, 0.8])
    np.testing.assert_allclose(calc.fallTime(signal, axis, 1.0, 0.0, occurrence=None), [0.8, 0.8])
    assert calc.riseTime(signal, axis, 0.0, 1.0, occurrence=-1) == pytest.approx(0.8)
    assert calc.slewrate(signal, axis, 0.0, 1.0, occurrence=1) == pytest.approx(0.5)
    assert calc.slewrate(signal, axis, 1.0, 0.0, occurrence=1) == pytest.approx(-1.0)
    assert np.isnan(calc.riseTime([0.0, 0.5], [0.0, 1.0], 0.0, 1.0))
    with pytest.raises(ValueError, match="percentages"):
        calc.riseTime(signal, axis, 0.0, 1.0, percent_low=90.0, percent_high=10.0)


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


def test_frequency_averages_the_full_crossing_span() -> None:
    axis = np.arange(0.0, 12.0, 0.25)
    signal = np.full(len(axis), -1.0)
    for edge in (1.0, 1.5, 3.0, 5.0, 11.0):
        signal[(axis >= edge) & (axis < edge + 0.25)] = 1.0
    assert calc.frequency(signal, axis, threshold=0.0) == pytest.approx(0.4)
    assert np.isnan(calc.frequency([-1.0, 1.0], [0.0, 1.0], threshold=0.0))


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


def test_jitter_matches_variable_duty_cycle_piecewise_linear_reference() -> None:
    axis = np.asarray([0.0, 1.0, 1.4, 2.5, 3.9, 5.1, 5.4, 6.8, 8.1, 9.1, 9.7, 11.2, 12.0])
    signal = np.asarray([0.0, 2.0, 2.0, 0.0, 0.0, 3.0, 3.0, 0.0, 0.0, 4.0, 4.0, 0.0, 0.0])
    mean_level = np.trapezoid(signal, axis) / 12.0
    edges = np.asarray([mean_level / 2.0, 3.9 + mean_level * 1.2 / 3.0, 8.1 + mean_level / 4.0])
    periods = np.diff(edges)
    np.testing.assert_allclose(calc.period_jitter(signal, axis), periods - np.mean(periods))
    assert calc.period_jitter(signal, axis, output_type="sd") == pytest.approx(np.std(periods - np.mean(periods)))
    cycle, jitter_ui = calc.abs_jitter(signal, axis, threshold=1.0, nominal_period=4.0, x_unit="cycle", y_unit="ui")
    np.testing.assert_allclose(cycle, [1.0, 2.0, 3.0])
    np.testing.assert_allclose(jitter_ui, (np.asarray([0.5, 4.3, 8.35]) - [0.5, 4.5, 8.5]) / 4.0)
    np.testing.assert_allclose(calc.abs_jitter(signal, axis, nominal_period=4.0), [0.0, -0.3, -0.4])
    np.testing.assert_array_equal(calc.abs_jitter([0.0, 0.0], [0.0, 1.0], threshold=1.0, nominal_period=4.0), [])
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


def test_eye_height_at_xy_measures_inner_trace_intercepts() -> None:
    folded = np.asarray(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [np.nan, np.nan],
            [0.0, 2.0],
            [1.0, 2.0],
            [np.nan, np.nan],
            [0.0, 3.0],
            [1.0, 3.0],
        ]
    )
    assert calc.eyeHeightAtXY(folded, 0.5, 1.0) == pytest.approx(2.0)
    assert calc.eyeHeightAtXY(folded, 0.5, 1.0, output="above") == pytest.approx(1.0)
    assert calc.eyeHeightAtXY(folded, 0.5, 1.0, output="below") == pytest.approx(1.0)
    assert np.isnan(calc.eyeHeightAtXY(folded, 0.5, 2.0))
    assert np.isnan(calc.eyeHeightAtXY(folded, 0.5, 4.0))
    assert np.isnan(calc.eyeHeightAtXY(folded, 2.0, 1.0))
    sloped = np.asarray([[0.0, 0.0], [1.0, 1.0], [np.nan, np.nan], [0.0, 3.0], [1.0, 2.0]])
    assert calc.eyeHeightAtXY(sloped, 0.5, 1.5) == pytest.approx(2.0)


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


def test_frequency_response_measures_match_a_two_pole_loop() -> None:
    frequency = np.logspace(0, 9, 2_001)
    s = 2j * np.pi * frequency
    # 60 dB DC gain, poles at 1 kHz and 10 MHz: unity gain near 1 MHz, phase margin near 84°
    loop = 1_000.0 / ((1 + s / (2 * np.pi * 1e3)) * (1 + s / (2 * np.pi * 1e7)))
    assert calc.db20(1_000.0) == pytest.approx(60.0)
    corner_db = 10.0 * np.log10(2.0)  # a single pole is 3.0103 dB down at its frequency
    assert calc.bandwidth(loop, frequency, corner_db, "low") == pytest.approx(1e3, rel=1e-3)
    assert calc.bandwidth(loop, frequency, 3.0, "low") < 1e3
    assert calc.gainBwProd(loop, frequency) == pytest.approx(1e6, rel=1e-3)
    unity = calc.unityGainFreq(loop, frequency)
    assert unity == pytest.approx(0.995e6, rel=5e-3)
    expected = 180.0 - np.degrees(np.arctan(unity / 1e3) + np.arctan(unity / 1e7))
    assert calc.phaseMargin(loop, frequency) == pytest.approx(expected, abs=0.05)
    assert np.isnan(calc.gainMargin(loop, frequency))  # two poles never reach -180°
    three = loop / (1 + s / (2 * np.pi * 2e7))
    assert calc.gainMargin(three, frequency) < 0
    assert calc.gainMargin(three, frequency, stable=True) == pytest.approx(-calc.gainMargin(three, frequency))
    exact = -np.degrees(np.arctan(frequency / 1e3) + np.arctan(frequency / 1e7))
    np.testing.assert_allclose(calc.phaseDegUnwrapped(loop), exact, atol=1e-9)


def test_margins_read_an_inverting_start_the_same_from_either_side() -> None:
    frequency = np.logspace(0, 9, 2_001)
    s = 2j * np.pi * frequency
    loop = 1_000.0 / ((1 + s / (2 * np.pi * 1e3)) * (1 + s / (2 * np.pi * 1e7)))
    # an inverting loop gain starts at 180°: just above and just below must give one margin
    above, below = -loop * np.exp(1j * np.radians(1e-6)), -loop * np.exp(-1j * np.radians(1e-6))
    assert calc.phaseMargin(above, frequency) == pytest.approx(calc.phaseMargin(below, frequency), abs=1e-3)
    assert calc.phaseMargin(above, frequency) == pytest.approx(calc.phaseMargin(loop, frequency) - 180.0, abs=1e-3)


def test_bandwidth_high_pass_and_band_pass() -> None:
    frequency = np.logspace(0, 8, 1_601)
    s = 2j * np.pi * frequency
    high = (s / (2 * np.pi * 1e3)) / (1 + s / (2 * np.pi * 1e3))
    corner_db = 10.0 * np.log10(2.0)
    assert calc.bandwidth(high, frequency, corner_db, "high") == pytest.approx(1e3, rel=1e-3)
    band = high / (1 + s / (2 * np.pi * 1e6))
    assert calc.bandwidth(band, frequency, corner_db, "band") == pytest.approx(1e6 - 1e3, rel=3e-3)
    assert np.isnan(calc.bandwidth(np.ones(4), np.arange(1.0, 5.0), 3.0, "low"))
    with pytest.raises(ValueError, match="type"):
        calc.bandwidth(high, frequency, 3.0, "notch")


def test_duty_cycle_overshoot_intersections_and_running_integral() -> None:
    axis = np.arange(0.0, 10.0, 0.01)
    pulses = np.where((axis % 2.0) < 0.5, 1.0, 0.0)
    _x, duties = calc.dutyCycle(pulses, axis, threshold=0.5)
    np.testing.assert_allclose(duties, 25.0, atol=1.0)
    assert calc.dutyCycle(pulses, axis, threshold=0.5, output_type="average") == pytest.approx(25.0, abs=1.0)
    cycles, _ = calc.dutyCycle(pulses, axis, threshold=0.5, x_unit="cycle")
    np.testing.assert_array_equal(cycles, np.arange(1, len(cycles) + 1))
    step = 1.0 - np.exp(-axis) * np.cos(3.0 * axis)
    assert calc.overshoot(step, axis, 0.0, 1.0) == pytest.approx(100.0 * (step.max() - 1.0))
    assert calc.overshoot(1.0 - step, axis, 1.0, 0.0) == pytest.approx(100.0 * (step.max() - 1.0))
    np.testing.assert_allclose(calc.intersect(axis, 10.0 - axis, axis), [5.0], atol=1e-9)
    running = calc.iinteg(np.ones(5), np.arange(5.0))
    np.testing.assert_allclose(running, [0.0, 1.0, 2.0, 3.0, 4.0])
    assert running[-1] == pytest.approx(calc.integ(np.ones(5), np.arange(5.0)))


def test_delay_measure_counts_both_crossings_from_the_start() -> None:
    axis = np.linspace(0.05, 4.05, 401)
    trigger = np.sin(2.0 * np.pi * axis)  # rising through zero at 1, 2, 3, 4
    response = np.sin(2.0 * np.pi * (axis - 0.1))  # rising at 0.1, 1.1, ...; falling at 0.6, 1.6, ...
    assert calc.delayMeasure(trigger, response, axis, edge1="rising", edge2="rising", value1=0.0, value2=0.0) == (
        pytest.approx(-0.9, abs=1e-3)
    )
    # the response's fourth crossing of either direction (1.6) after the trigger's first rising one (1.0)
    assert calc.delayMeasure(trigger, response, axis, edge1="rising", value1=0.0, value2=0.0, nth2=4) == (
        pytest.approx(0.6, abs=1e-3)
    )
    # thresholds default to each waveform's time average (here about zero)
    assert calc.delayMeasure(trigger, response, axis, edge1="rising", edge2="rising", nth2=2) == (
        pytest.approx(0.1, abs=2e-3)
    )
    assert np.isnan(calc.delayMeasure(trigger, response, axis, value1=0.0, value2=5.0))
    # a single sample has no time average to default the thresholds to
    assert np.isnan(calc.delayMeasure([0.0], [1.0], [0.0]))
