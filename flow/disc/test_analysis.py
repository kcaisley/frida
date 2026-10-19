"""Discriminator analyses and plots on synthetic responses of known trip points and delays."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.disc.analysis import MeasDisc, analyze_disc_delay, analyze_disc_trip
from flow.disc.plots import plot_disc_delay, plot_disc_transfer
from flow.disc.sim import DiscTbParams, stop_time_s
from flow.disc.subckt import CASES

VDD, THRESHOLD = 1.2, 0.6


def _record(params: DiscTbParams, time_s: np.ndarray, inp: np.ndarray, out: np.ndarray) -> MeasDisc:
    return MeasDisc(
        group=None,
        index=None,
        dut=params.disc,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"inp": inp[None, :], "out": out[None, :], "inn": np.full((1, len(time_s)), THRESHOLD)},
            i={"vdd": np.full((1, len(time_s)), 3e-6)},
        ),
    )


def _triangle(offset: float, hysteresis: float) -> MeasDisc:
    """A discriminator switching high where the triangle's input passes threshold + offset +
    hysteresis / 2 on the way up, low where it passes threshold + offset - hysteresis / 2 down."""
    params = DiscTbParams(disc=CASES["nmos_hyst"], vdd=VDD, threshold_v=THRESHOLD)
    time_s = np.arange(0.0, stop_time_s(params), 1e-9)
    settle, ramp = float(params.ramp_time_s) / 40, float(params.ramp_time_s)
    up = np.clip((time_s - settle) / ramp, 0, 1)
    down = np.clip((time_s - 2 * settle - ramp) / ramp, 0, 1)
    inp = THRESHOLD - 0.1 + 0.2 * (up - down)
    state, out = False, np.zeros_like(time_s)
    for index, level in enumerate(inp - THRESHOLD - offset):
        state = level >= hysteresis / 2 if not state else level > -hysteresis / 2
        out[index] = VDD * state
    return _record(params, time_s, inp, out)


def _step(overdrive: float, delay: float) -> MeasDisc:
    """An output ramping rail to rail in 200 ps, ``delay`` after the input crosses the threshold
    each way (the input's 100 ps edges between 100 mV below it and ``overdrive`` above)."""
    params = DiscTbParams(disc=CASES["nmos"], vdd=VDD, threshold_v=THRESHOLD, overdrive_v=overdrive)
    time_s = np.arange(0.0, float(params.period_s), 1e-12)
    period, edge, low, high = float(params.period_s), 100e-12, THRESHOLD - 0.1, THRESHOLD + overdrive
    rising = np.clip((time_s - period / 4) / edge, 0, 1)
    falling = np.clip((time_s - 3 * period / 4 + edge) / edge, 0, 1)
    inp = low + (high - low) * (rising - falling)
    up_s = period / 4 + edge * 0.1 / (high - low)
    down_s = 3 * period / 4 - edge + edge * overdrive / (high - low)
    out = VDD * (np.clip((time_s - up_s - delay) / 200e-12, 0, 1) - np.clip((time_s - down_s - delay) / 200e-12, 0, 1))
    return _record(params, time_s, inp, out)


def test_trip_points_offset_and_hysteresis() -> None:
    trip = analyze_disc_trip([_triangle(2e-3, 10e-3)])
    assert trip.rise_trip_v[0] == pytest.approx(7e-3, abs=1e-4)
    assert trip.fall_trip_v[0] == pytest.approx(-3e-3, abs=1e-4)
    assert trip.offset_v[0] == pytest.approx(2e-3, abs=1e-4)
    assert trip.hysteresis_v[0] == pytest.approx(10e-3, abs=2e-4)
    with pytest.raises(ValueError, match="triangle"):
        analyze_disc_trip([_step(10e-3, 1e-9)])


def test_delays_transitions_and_timewalk() -> None:
    overdrives = (5e-3, 100e-3, 20e-3)
    delays = {overdrive: 1e-9 + 2e-11 / overdrive for overdrive in overdrives}
    delay = analyze_disc_delay([_step(overdrive, delays[overdrive]) for overdrive in overdrives])
    assert delay.overdrive_v == pytest.approx([5e-3, 20e-3, 100e-3])
    expected = np.asarray([delays[overdrive] for overdrive in sorted(overdrives)]) + 100e-12
    assert delay.rise_delay_s == pytest.approx(expected, rel=1e-3)
    assert delay.fall_delay_s == pytest.approx(expected, rel=1e-3)
    assert delay.timewalk_s == pytest.approx(expected - expected[-1], abs=1e-12)
    assert delay.rise_time_s == pytest.approx([160e-12] * 3, rel=1e-2)
    assert delay.fall_time_s == pytest.approx([160e-12] * 3, rel=1e-2)
    assert delay.supply_current_a == pytest.approx([3e-6] * 3)


def test_comparison_plots_render(tmp_path: Path) -> None:
    trip = analyze_disc_trip([_triangle(1e-3, 8e-3)])
    delay = analyze_disc_delay([_step(overdrive, 1e-9 + 2e-11 / overdrive) for overdrive in (5e-3, 50e-3)])
    paths = (
        *plot_disc_transfer([trip], labels=["a"], output_path=tmp_path / "transfer"),
        *plot_disc_delay([delay], labels=["a"], output_path=tmp_path / "delay"),
    )
    assert paths and all(path.exists() for path in paths)
