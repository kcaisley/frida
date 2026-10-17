"""Delay analyses and plots on synthetic records with known frequency, delay, and current."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.delay.analysis import MeasDelay, analyze_delay_oscillation, analyze_delay_propagation
from flow.delay.plots import (
    plot_delay_line_control,
    plot_delay_line_supply,
    plot_delay_ring_control,
    plot_delay_ring_supply,
)
from flow.delay.sim import DelayTbParams
from flow.delay.subckt import CASES


def _measurement(case: str, vdd: float, control_v: float, outp: np.ndarray, time_s: np.ndarray, current_a: float):
    params = DelayTbParams(delay=CASES[case], vdd=vdd, control_v=control_v)
    return MeasDelay(
        group=None,
        index=None,
        dut=params.delay,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"outp": outp[None, :], "inp": np.zeros((1, len(time_s)))},
            i={"vdd": np.full((1, len(time_s)), current_a)},
        ),
    )


def test_ring_frequency_current_and_energy() -> None:
    time_s = np.arange(0, 40e-9, 2e-12)
    sweep = []
    for vdd, frequency_hz in ((1.0, 1e9), (1.2, 2e9)):
        # a ring held until en rises at 1 ns, then a sine at the given frequency
        outp = np.where(time_s > 1e-9, vdd / 2 * (1 - np.cos(2 * np.pi * frequency_hz * (time_s - 1e-9))), 0.0)
        sweep.append(_measurement("ring5", vdd, 0.8, outp, time_s, 50e-6))
    result = analyze_delay_oscillation(sweep)
    assert result.frequency_hz == pytest.approx([1e9, 2e9], rel=1e-3)
    assert result.supply_current_a == pytest.approx([50e-6, 50e-6])
    assert result.energy_per_cycle_j == pytest.approx([50e-15, 30e-15], rel=1e-3)
    assert result.duty_cycle == pytest.approx([0.5, 0.5], abs=0.01)
    assert result.oscillating.all()
    stopped = analyze_delay_oscillation([_measurement("ring5", 1.2, 0.8, np.zeros_like(time_s), time_s, 0.0)])
    assert not stopped.oscillating[0] and np.isnan(stopped.frequency_hz[0])
    with pytest.raises(ValueError, match="requires a ring"):
        analyze_delay_oscillation([replace(sweep[0], dut=CASES["chain4"])])


def test_line_delay_follows_the_input_by_the_set_shift() -> None:
    time_s = np.arange(0, 40e-9, 1e-12)
    params = DelayTbParams()
    phase = (time_s - float(params.period_s) / 4) % float(params.period_s)
    source = np.where((time_s >= float(params.period_s) / 4) & (phase < float(params.period_s) / 2), 1.2, 0.0)
    shifted = np.interp(time_s - 60e-12, time_s, source, left=0.0)
    measurement = _measurement("chain4", 1.2, 0.8, shifted, time_s, 20e-6)
    measurement = replace(
        measurement, wave=replace(measurement.wave, v={"outp": shifted[None, :], "inp": source[None, :]})
    )
    result = analyze_delay_propagation([measurement])
    assert result.rise_delay_s[0] == pytest.approx(60e-12, abs=2e-12)
    assert result.fall_delay_s[0] == pytest.approx(60e-12, abs=2e-12)
    assert result.energy_per_cycle_j[0] == pytest.approx(1.2 * 20e-6 * 4e-9)
    assert result.valid[0]


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    time_s = np.arange(0, 40e-9, 2e-12)
    phase = time_s % 4e-9
    source = np.where(phase < 2e-9, 1.0, 0.0)
    analyses = {"ring_supply": [], "ring_control": [], "line_supply": [], "line_control": []}
    for case in ("ring5_starved", "chain4_starved"):
        for sweep in ("supply", "control"):
            measurements = []
            for step in (1.0, 1.1, 1.2):
                vdd, control_v = (step, 0.8) if sweep == "supply" else (1.2, step - 0.4)
                # frequency and speed grow with both supply and control
                speed = vdd * control_v
                if case.startswith("ring"):
                    outp = vdd / 2 * (1 - np.cos(2 * np.pi * speed * 1e9 * time_s))
                    measurements.append(_measurement(case, vdd, control_v, outp, time_s, speed * 1e-4))
                else:
                    shifted = np.interp(time_s - 50e-12 / speed, time_s, source * vdd, left=0.0)
                    measurement = _measurement(case, vdd, control_v, shifted, time_s, 1e-5)
                    wave = replace(measurement.wave, v={"outp": shifted[None, :], "inp": source[None, :] * vdd})
                    measurements.append(replace(measurement, wave=wave))
            if case.startswith("ring"):
                analyses[f"ring_{sweep}"].append(analyze_delay_oscillation(measurements))
            else:
                analyses[f"line_{sweep}"].append(analyze_delay_propagation(measurements))
    paths = (
        *plot_delay_ring_supply(analyses["ring_supply"], labels=["a"], output_path=tmp_path / "ring_supply"),
        *plot_delay_ring_control(analyses["ring_control"], labels=["a"], output_path=tmp_path / "ring_control"),
        *plot_delay_line_supply(analyses["line_supply"], labels=["a"], output_path=tmp_path / "line_supply"),
        *plot_delay_line_control(analyses["line_control"], labels=["a"], output_path=tmp_path / "line_control"),
    )
    assert paths and all(path.exists() for path in paths)
