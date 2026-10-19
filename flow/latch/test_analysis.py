"""Latch analyses and plots on synthetic records with known setup, delay, current, and upset."""

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.latch.analysis import (
    MeasLatch,
    analyze_latch_constraint,
    analyze_latch_sr,
    analyze_latch_timing,
    analyze_latch_upset,
)
from flow.latch.plots import plot_latch_frequency, plot_latch_setup_hold, plot_latch_supply, plot_latch_upset
from flow.latch.sim import LatchTbParams
from flow.latch.subckt import CASES


def _pulse(time_s, v1, v2, period, width, delay, transition):
    """A periodic trapezoid like the testbench's pulse sources."""
    phase = np.where(time_s >= delay, (time_s - delay) % period, -1.0)
    rising = np.clip(phase / transition, 0, 1)
    falling = np.clip((phase - transition - width) / transition, 0, 1)
    return np.where(phase < 0, v1, v1 + (v2 - v1) * (rising - falling))


def _measurement(params: LatchTbParams, time_s: np.ndarray, v: dict[str, np.ndarray], current_a: float):
    return MeasLatch(
        group=None,
        index=None,
        dut=params.latch,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={name: trace[None, :] for name, trace in v.items()},
            i={"vdd": np.full((1, len(time_s)), current_a)},
        ),
    )


def _flop(offset_s: float, *, vdd: float = 1.2, setup_s: float = 30e-12, delay_s: float = 40e-12) -> MeasLatch:
    """A flip-flop that takes d as it was setup_s before each rising edge, delay_s after that edge."""
    params = LatchTbParams(latch=CASES["flop_rst"], vdd=vdd, data_offset_s=offset_s)
    period, transition = float(params.clock_period_s), float(params.transition_time_s)
    time_s = np.arange(0, float(params.reset_time_s) + 9 * period, 1e-12)
    clock = _pulse(time_s, 0.0, vdd, period, period / 2, period / 2, transition)
    capture = period / 2 + transition / 2
    first = max(1, math.ceil((float(params.reset_time_s) + transition + offset_s - capture) / period))
    data = _pulse(
        time_s,
        0.0,
        vdd,
        2 * period,
        period - transition,
        capture + first * period - offset_s - transition / 2,
        transition,
    )
    edges = capture + period * np.arange(9)
    taken = np.interp(edges - setup_s, time_s, data) > vdd / 2
    output = np.zeros_like(time_s)
    for edge, value in zip(edges, taken, strict=True):
        output[time_s >= edge + delay_s] = vdd * value
    return _measurement(params, time_s, {"clk": clock, "d": data, "q": output}, 30e-6)


def test_flop_setup_hold_and_clock_to_q() -> None:
    offsets = [round(value * 1e-12, 15) for value in (-100, -50, 0, 20, 40, 60, 100, 200)]
    sweep = [_flop(offset) for offset in offsets]
    timing = analyze_latch_timing(sweep)
    passing = timing.data_offset_s > 30e-12
    assert np.all(timing.captured_fraction[passing] == 1.0) and np.all(timing.held_fraction[~passing] == 1.0)
    assert timing.clock_to_q_rise_s[passing] == pytest.approx(40e-12, abs=2e-12)
    assert timing.clock_to_q_fall_s[passing] == pytest.approx(40e-12, abs=2e-12)
    assert timing.energy_per_cycle_j == pytest.approx(1.2 * 30e-6 * 2e-9)
    constraint = analyze_latch_constraint(sweep, timing=timing)
    assert constraint.setup_s == pytest.approx(40e-12)
    assert constraint.hold_s == pytest.approx(-20e-12)
    with pytest.raises(ValueError, match="data offset sweep"):
        analyze_latch_constraint(sweep[:2], timing=analyze_latch_timing(sweep[:2]))


def _sr(vdd: float, case: str = "sr_nand", delay_s: float = 25e-12) -> MeasLatch:
    """An SR latch whose q rises delay_s after each set and falls delay_s after each reset."""
    params = LatchTbParams(latch=CASES[case], vdd=vdd)
    period, transition = float(params.data_period_s), float(params.transition_time_s)
    time_s = np.arange(0, 3 * period, 1e-12)
    low_active = case == "sr_nand"
    idle, active = (vdd, 0.0) if low_active else (0.0, vdd)
    set_v = _pulse(time_s, idle, active, period, period / 4, period / 4, transition)
    reset_v = _pulse(time_s, idle, active, period, period / 4, 3 * period / 4, transition)
    phase = (time_s - period / 4 - transition / 2 - delay_s) % period
    output = np.where((time_s > period / 4) & (phase < period / 2), vdd, 0.0)
    return _measurement(params, time_s, {"s": set_v, "r": reset_v, "q": output}, 10e-6)


def test_sr_set_and_reset_delays() -> None:
    for case in ("sr_nand", "sr_nor"):
        result = analyze_latch_sr([_sr(1.0, case), _sr(1.2, case)])
        assert result.set_delay_s == pytest.approx([25e-12, 25e-12], abs=2e-12)
        assert result.reset_delay_s == pytest.approx([25e-12, 25e-12], abs=2e-12)
        assert result.energy_per_cycle_j == pytest.approx(np.array([1.0, 1.2]) * 10e-6 * 5.2e-9)
    with pytest.raises(ValueError, match="SR latch"):
        analyze_latch_sr([_flop(0.5e-9)])


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    offsets = [round(value * 1e-12, 15) for value in range(-100, 201, 20)]
    sweep = [_flop(offset) for offset in offsets]
    timing = analyze_latch_timing(sweep)
    supply = analyze_latch_timing([_flop(0.5e-9, vdd=vdd) for vdd in (1.0, 1.1, 1.2)])
    sr = analyze_latch_sr([_sr(vdd) for vdd in (1.0, 1.1, 1.2)])
    paths = (
        *plot_latch_setup_hold(
            [timing],
            [analyze_latch_constraint(sweep, timing=timing)],
            labels=["flop"],
            output_path=tmp_path / "setup_hold",
        ),
        *plot_latch_supply([supply], [sr], labels=["flop", "sr"], output_path=tmp_path / "supply"),
        *plot_latch_frequency([supply], labels=["flop"], output_path=tmp_path / "frequency"),
    )
    assert paths and all(path.exists() for path in paths)


def _upset(charge_c: float, critical_c: float) -> MeasLatch:
    """A latch holding q at 1.2 V that, struck at 2 ns, dips by 60 mV per femtocoulomb (at most to
    ground) and stays down from the critical charge on, else recovers within 0.2 ns."""
    params = LatchTbParams(latch=CASES["latch_dice"], upset_charge_c=charge_c)
    time_s = np.arange(0.0, 4e-9, 1e-12)
    dip = min(1.2, 0.06 * charge_c * 1e15)
    struck = (time_s >= 2e-9) & ((time_s < 2.2e-9) | (charge_c >= critical_c))
    return _measurement(params, time_s, {"q": np.where(struck, 1.2 - dip, 1.2)}, 1e-6)


def test_upset_critical_charge_and_dip() -> None:
    upset = analyze_latch_upset([_upset(charge * 1e-15, 20e-15) for charge in (50, 5, 10, 20)])
    assert upset.charge_c == pytest.approx([5e-15, 10e-15, 20e-15, 50e-15])
    assert list(upset.upset) == [0.0, 0.0, 1.0, 1.0]
    assert upset.q_dip_v == pytest.approx([0.3, 0.6, 1.2, 1.2])
    assert upset.critical_charge_c == pytest.approx(20e-15)
    assert math.isnan(analyze_latch_upset([_upset(5e-15, 20e-15)]).critical_charge_c)
    with pytest.raises(ValueError, match="upset bench"):
        analyze_latch_upset([_flop(0.2e-9)])


def test_upset_plot_renders(tmp_path: Path) -> None:
    upset = analyze_latch_upset([_upset(charge * 1e-15, 20e-15) for charge in (5, 20, 50)])
    paths = plot_latch_upset([upset], labels=["a"], output_path=tmp_path / "upset")
    assert paths and all(path.exists() for path in paths)
