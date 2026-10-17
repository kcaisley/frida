"""Sampler analyses and plots on an ideal RC sampler of known time constant, pedestal and feedthrough."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from hdl21.prefix import p

from flow.analysis.types import MeasInfo, Wave
from flow.samp.analysis import MeasSamp, analyze_samp_hold, analyze_samp_track
from flow.samp.plots import plot_samp_hold, plot_samp_resistance, plot_samp_supply, plot_samp_waveforms
from flow.samp.sim import SampTbParams
from flow.samp.subckt import CASES


def _rc_sampler(vin: float = 0.6, *, tau_s: float = 0.2e-9, pedestal_v: float = -2e-3, feedthrough: float = 1e-3):
    """Four 10 ns periods tracking for 5 ns into 1 pF, the input stepping 0.1 V in mid-hold."""

    params = SampTbParams(
        samp=CASES["frida1"],
        input_voltage=vin,
        input_step_v=0.1,
        cload=1 * p,
        clock_period_s=10e-9,
        clock_high_time_s=5e-9,
        clock_transition_time_s=50e-12,
        periods=4,
    )
    period, high, step = 10e-9, 5e-9, 0.1
    time_s = np.arange(0.0, 4 * period, 1e-12)
    phase = np.mod(time_s, period)
    clock = np.where(phase < high, 1.2, 0.0)
    # the input steps up, then down, every period, half-way through the hold phase
    data = vin + step / 2 * np.where(np.floor((time_s - 7.5e-9) / period) % 2 == 0, 1.0, -1.0)
    data[time_s < 7.5e-9] = vin - step / 2
    output = np.empty_like(time_s)
    value = vin
    for index, (t, level) in enumerate(zip(time_s, data, strict=True)):
        if phase[index] < high:
            if index and phase[index - 1] >= high or index == 0:
                start, start_value = t, value
            value = level + (start_value - level) * np.exp(-(t - start) / tau_s)
        else:
            if phase[index - 1] < high:
                value += pedestal_v
            if data[index] != data[index - 1]:
                value += feedthrough * (data[index] - data[index - 1])
        output[index] = value
    return MeasSamp(
        group=None,
        index=None,
        dut=params.samp,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 18, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"clk": clock[None], "clk_b": 1.2 - clock[None], "din": data[None], "dout": output[None]},
            i={"vdd": np.zeros((1, len(time_s)))},
        ),
    )


def test_tracking_recovers_the_time_constant_and_resistance() -> None:
    track = analyze_samp_track([_rc_sampler()])
    assert track.time_constant_s[0] == pytest.approx(0.2e-9, abs=2e-12)
    assert track.on_resistance_ohm[0] == pytest.approx(200.0, rel=0.01)
    assert track.bandwidth_hz[0] == pytest.approx(1 / (2 * np.pi * 0.2e-9), rel=0.01)
    assert abs(track.track_error_v[0]) < 1e-6


def test_hold_recovers_the_pedestal_and_feedthrough() -> None:
    hold = analyze_samp_hold([_rc_sampler()])
    assert hold.pedestal_v[0] == pytest.approx(-2e-3, abs=1e-6)
    assert hold.feedthrough[0] == pytest.approx(1e-3, rel=1e-3)
    assert hold.droop_v_per_s[0] == pytest.approx(0.0, abs=1.0)


def test_every_plot_renders(tmp_path: Path) -> None:
    measurements = [_rc_sampler(vin) for vin in (0.4, 0.6, 0.8)]
    track, hold = analyze_samp_track(measurements), analyze_samp_hold(measurements)
    paths = (
        *plot_samp_resistance([track, track], labels=["a", "b"], output_path=tmp_path / "resistance"),
        *plot_samp_hold([hold], labels=["a"], output_path=tmp_path / "hold"),
        *plot_samp_supply([track], labels=["a"], output_path=tmp_path / "supply"),
        *plot_samp_waveforms(measurements[:2], labels=["a", "b"], output_path=tmp_path / "waveforms"),
    )
    assert paths and all(path.exists() for path in paths)
