"""Software-only tests for direct numerical waveform helpers."""

from __future__ import annotations

import numpy as np
import pytest

from flow.analysis.measure import (
    amplitude_spectrum,
    endpoint_linearity,
    find_crossings,
    measure_average_power,
    measure_charge_injection,
    measure_delay,
    measure_offset_crossing,
    measure_settling,
    sample_at_edges,
    statistics,
)


def test_crossings_delay_and_edge_samples_interpolate_events() -> None:
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
    sample_axis, sampled = sample_at_edges(
        time_s,
        clock,
        (response,),
        0.0,
        sample_fraction=0.5,
    )
    assert len(sample_axis) == 2
    assert sampled[0].shape == sample_axis.shape


def test_spectrum_recovers_dc_and_coherent_tone() -> None:
    sample_rate_hz = 1.0e9
    time_s = np.arange(10_000) / sample_rate_hz
    signal = 0.6 + 0.5 * np.sin(2.0 * np.pi * 20.0e6 * time_s)
    frequency_hz, amplitude = amplitude_spectrum(
        signal,
        1.0 / sample_rate_hz,
        window="none",
    )
    tone_bin = int(np.argmin(np.abs(frequency_hz - 20.0e6)))
    assert amplitude[0] == pytest.approx(0.6, rel=1e-6)
    assert amplitude[tone_bin] == pytest.approx(0.5, rel=1e-6)


def test_settling_power_offset_charge_statistics_and_linearity() -> None:
    time_s = np.linspace(0.0, 10.0, 1_001)
    settled = 1.0 - np.exp(-time_s)
    input_difference = np.linspace(-0.1, 0.1, len(time_s))
    output_difference = input_difference - 0.01

    settling = measure_settling(
        time_s,
        settled,
        target=1.0,
        relative_tolerance=0.01,
    )
    assert 4.0 < settling < 6.0
    assert measure_average_power(np.full(len(time_s), 1e-3), 1.2) == pytest.approx(1.2e-3)
    assert measure_offset_crossing(input_difference, output_difference, time_s) == pytest.approx(0.01)
    assert measure_charge_injection(settled[100], settled[200]) == pytest.approx(settled[200] - settled[100])
    assert statistics(input_difference)["mean"] == pytest.approx(0.0, abs=1e-12)

    dnl, inl, lsb = endpoint_linearity([0, 1, 2], [0.0, 0.5, 1.0])
    np.testing.assert_allclose(dnl, 0.0)
    np.testing.assert_allclose(inl, 0.0)
    assert lsb == pytest.approx(0.5)
