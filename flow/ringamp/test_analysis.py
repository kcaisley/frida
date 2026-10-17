"""Ring amplifier analyses and plots on synthetic open-loop and closed-loop records."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.ringamp.analysis import MeasRingamp, analyze_ringamp_settling, analyze_ringamp_transfer
from flow.ringamp.plots import plot_ringamp_deadzone, plot_ringamp_step, plot_ringamp_transfer, plot_ringamp_waveforms
from flow.ringamp.sim import RingampTbParams
from flow.ringamp.subckt import CASES


def _measurement(params: RingampTbParams, time_s, v, current):
    return MeasRingamp(
        group=None,
        index=None,
        dut=params.ringamp,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={k: x[None, :] for k, x in v.items()},
            i={"vdd": current[None, :]},
        ),
    )


def _open(biasn: float = 0.5, trip_v: float = 0.56, gain: float = 50.0) -> MeasRingamp:
    """An inverting amplifier of ``gain`` about ``trip_v`` on the testbench's triangle, its current peaking at the trip."""
    params = RingampTbParams(ringamp=CASES["se"], biasn=biasn, biasp=1.2 - biasn)
    period = float(params.period_s)
    time_s = np.arange(0, 2.5 * period, 10e-12)
    source = np.interp(time_s, [0, period / 2, 1.5 * period, 2.5 * period], [0.3, 0.3, 0.9, 0.3])
    output = np.clip(0.6 - gain * (source - trip_v), 0.0, 1.2)
    current = 20e-6 * np.exp(-(((source - trip_v) / 0.05) ** 2))
    return _measurement(params, time_s, {"inp": source, "out": output}, current)


def _closed(step_v: float, error_v: float = 0.01, tau_s: float = 0.3e-9) -> MeasRingamp:
    """A closed-loop output settling exponentially to -step plus ``error_v`` after the step."""
    params = RingampTbParams(ringamp=CASES["se"], closed_loop=True, step_v=step_v)
    time_s = np.arange(0, float(params.step_delay_s) + float(params.settle_time_s), 2e-12)
    step_s = float(params.step_delay_s) + float(params.transition_time_s) / 2
    after = np.clip(time_s - step_s, 0.0, None)
    output = 0.5 + (-step_v + error_v) * (1 - np.exp(-after / tau_s))
    current = 25e-6 + 100e-6 * np.exp(-after / tau_s) * (time_s > step_s)
    return _measurement(params, time_s, {"inp": np.full_like(time_s, 0.5), "out": output}, current)


def test_open_loop_trip_gain_and_current() -> None:
    result = analyze_ringamp_transfer([_open()])
    assert result.trip_v[0] == pytest.approx(0.56, abs=1e-3)
    assert result.hysteresis_v[0] == pytest.approx(0.0, abs=1e-3)
    assert result.gain_v_per_v[0] == pytest.approx(50.0, rel=0.05)
    assert result.current_at_trip_a[0] == pytest.approx(20e-6, rel=0.01)


def test_closed_loop_error_settling_and_charge() -> None:
    result = analyze_ringamp_settling([_closed(0.1)])
    assert result.output_step_v[0] == pytest.approx(-0.09, abs=1e-4)
    assert result.gain_error[0] == pytest.approx(-0.1, abs=1e-3)
    # within 1 % of the 90 mV change after ln(100) time constants
    assert result.settling_time_s[0] == pytest.approx(np.log(100) * 0.3e-9, rel=0.02)
    assert result.overshoot[0] == pytest.approx(0.0, abs=1e-6)
    assert result.quiescent_current_a[0] == pytest.approx(25e-6, rel=1e-3)
    assert result.settling_charge_c[0] == pytest.approx(100e-6 * 0.3e-9, rel=0.02)


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    transfer = analyze_ringamp_transfer([_open(biasn, 0.5 + biasn / 10) for biasn in (0.4, 0.5)])
    steps = [_closed(step) for step in (-0.1, 0.1)]
    settling = analyze_ringamp_settling(steps)
    paths = (
        *plot_ringamp_transfer([transfer], labels=["a"], output_path=tmp_path / "transfer"),
        *plot_ringamp_deadzone([settling], labels=["a"], output_path=tmp_path / "deadzone"),
        *plot_ringamp_step([settling], labels=["a"], output_path=tmp_path / "step"),
        *plot_ringamp_waveforms([steps], labels=["a"], output_path=tmp_path / "waveforms"),
    )
    assert paths and all(path.exists() for path in paths)
