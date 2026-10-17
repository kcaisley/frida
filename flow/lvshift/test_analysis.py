"""Level shifter analysis and plots on synthetic records of known delay, energy, and idle current."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.lvshift.analysis import MeasLvShift, analyze_lvshift_switching
from flow.lvshift.plots import plot_lvshift_vdd, plot_lvshift_vddl, plot_lvshift_waveforms
from flow.lvshift.sim import LvShiftTbParams
from flow.lvshift.subckt import CASES


def _record(vddl: float, *, vdd: float = 1.2, follows: bool = True) -> MeasLvShift:
    """A shifter whose outp follows inp 50 ps late at vdd levels (or stays low), drawing 10 µA from
    vdd and 1 µA from vddl."""
    params = LvShiftTbParams(lvshift=CASES["core"], vdd=vdd, vddl=vddl)
    period = float(params.period_s)
    time_s = np.arange(0, params.cycles * period, 2e-12)
    phase = (time_s - period / 2) % period
    high = (time_s >= period / 2) & (phase < period / 2)
    source = np.where(high, vddl, 0.0)
    late = np.interp(time_s - 50e-12, time_s, high.astype(np.float64))
    output = vdd * late if follows else np.zeros_like(time_s)
    reset = np.where(time_s < period / 4, vdd, 0.0)
    return MeasLvShift(
        group=None,
        index=None,
        dut=params.lvshift,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={
                name: trace[None, :]
                for name, trace in (("inp", source), ("rst", reset), ("outp", output), ("outn", vdd - output))
            },
            i={"vdd": np.full((1, len(time_s)), 10e-6), "vddl": np.full((1, len(time_s)), 1e-6)},
        ),
    )


def test_delays_energy_idle_and_failure() -> None:
    result = analyze_lvshift_switching([_record(0.6), _record(0.3, follows=False)])
    assert result.rise_delay_s[0] == pytest.approx(50e-12, abs=3e-12)
    assert result.fall_delay_s[0] == pytest.approx(50e-12, abs=3e-12)
    assert result.switched_fraction == pytest.approx([1.0, 0.0])
    assert result.energy_per_cycle_j[0] == pytest.approx((1.2 * 10e-6 + 0.6 * 1e-6) * 4e-9)
    assert result.static_current_a[0] == pytest.approx(10e-6)
    assert np.isnan(result.rise_delay_s[1])


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    vddl = analyze_lvshift_switching([_record(level) for level in (0.5, 0.6, 0.8)])
    vdd = analyze_lvshift_switching([_record(0.6, vdd=level) for level in (1.1, 1.2)])
    paths = (
        *plot_lvshift_vddl([vddl], labels=["a"], output_path=tmp_path / "vddl"),
        *plot_lvshift_vdd([vdd], labels=["a"], output_path=tmp_path / "vdd"),
        *plot_lvshift_waveforms([_record(0.6)], labels=["a"], output_path=tmp_path / "waveforms"),
    )
    assert paths and all(path.exists() for path in paths)
