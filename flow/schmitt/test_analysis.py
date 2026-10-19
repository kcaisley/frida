"""Schmitt trigger analyses and plots on synthetic records of known trip points and delays."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.schmitt.analysis import MeasSchmitt, analyze_schmitt_delay, analyze_schmitt_trip
from flow.schmitt.plots import plot_schmitt_supply, plot_schmitt_transfer
from flow.schmitt.sim import SchmittTbParams, stop_time_s
from flow.schmitt.subckt import CASES


def _record(params: SchmittTbParams, time_s: np.ndarray, inp: np.ndarray, out: np.ndarray, current: float):
    return MeasSchmitt(
        group=None,
        index=None,
        dut=params.schmitt,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"inp": inp[None, :], "out": out[None, :]},
            i={"vdd": np.full((1, len(time_s)), current)},
        ),
    )


def _triangle(vdd: float, high: float, low: float, case: str = "inv") -> MeasSchmitt:
    """A trigger switching where the triangle's input passes ``high`` on the way up and ``low`` on
    the way down; the inverting one's output falls, the buffer's rises, on the way up."""
    params = SchmittTbParams(schmitt=CASES[case], vdd=vdd)
    time_s = np.arange(0.0, stop_time_s(params), 0.5e-9)
    ramp = float(params.ramp_time_s)
    settle = ramp / 40
    inp = vdd * (np.clip((time_s - settle) / ramp, 0, 1) - np.clip((time_s - 2 * settle - ramp) / ramp, 0, 1))
    state, out = False, np.zeros_like(time_s)
    for index, level in enumerate(inp):
        state = level >= high if not state else level > low
        out[index] = vdd * (state if case == "buffer" else not state)
    return _record(params, time_s, inp, out, 0.0)


def _step(delay: float) -> MeasSchmitt:
    """An inverting output ramping rail to rail in 100 ps, ``delay`` after each input edge's middle,
    drawing 10 µA over the 4 ns period."""
    params = SchmittTbParams(schmitt=CASES["inv"], step=True, waveform_sample_interval_s=1e-12)
    time_s = np.arange(0.0, float(params.period_s), 1e-12)
    rising = np.clip((time_s - 1e-9) / 50e-12, 0, 1) - np.clip((time_s - 3e-9 + 50e-12) / 50e-12, 0, 1)
    up, down = 1e-9 + 25e-12 + delay, 3e-9 - 25e-12 + delay
    out = 1.2 * (
        1 - np.clip((time_s - up + 50e-12) / 100e-12, 0, 1) + np.clip((time_s - down + 50e-12) / 100e-12, 0, 1)
    )
    return _record(params, time_s, 1.2 * rising, out, 10e-6)


@pytest.mark.parametrize("case", ("inv", "buffer"))
def test_trip_points_and_hysteresis(case) -> None:
    trip = analyze_schmitt_trip([_triangle(1.2, 0.7, 0.45, case), _triangle(1.0, 0.6, 0.38, case)])
    assert trip.vdd_v == pytest.approx([1.0, 1.2])
    assert trip.rise_trip_v == pytest.approx([0.6, 0.7], abs=1e-3)
    assert trip.fall_trip_v == pytest.approx([0.38, 0.45], abs=1e-3)
    assert trip.hysteresis_v == pytest.approx([0.22, 0.25], abs=2e-3)
    with pytest.raises(ValueError, match="triangle"):
        analyze_schmitt_trip([_step(40e-12)])


def test_step_delays_transitions_and_energy() -> None:
    delay = analyze_schmitt_delay([_step(40e-12)])
    assert delay.rise_delay_s[0] == pytest.approx(40e-12, abs=1e-12)
    assert delay.fall_delay_s[0] == pytest.approx(40e-12, abs=1e-12)
    assert delay.out_rise_time_s[0] == pytest.approx(80e-12, rel=0.02)
    assert delay.out_fall_time_s[0] == pytest.approx(80e-12, rel=0.02)
    assert delay.energy_per_cycle_j[0] == pytest.approx(1.2 * 10e-6 * 4e-9, rel=1e-3)


def test_comparison_plots_render(tmp_path: Path) -> None:
    trip = analyze_schmitt_trip([_triangle(1.2, 0.7, 0.45), _triangle(1.0, 0.6, 0.38)])
    delay = analyze_schmitt_delay([_step(40e-12)])
    paths = (
        *plot_schmitt_transfer([trip], [delay], labels=["a"], output_path=tmp_path / "transfer"),
        *plot_schmitt_supply([trip], labels=["a"], output_path=tmp_path / "supply"),
    )
    assert paths and all(path.exists() for path in paths)
