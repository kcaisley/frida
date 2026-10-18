"""Follower analyses and plots on synthetic responses of known gain, bandwidth, and impedance."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.follower.analysis import (
    MeasFollower,
    MeasFollowerStep,
    analyze_follower_impedance,
    analyze_follower_slew,
    analyze_follower_transfer,
)
from flow.follower.plots import (
    plot_follower_bandwidth,
    plot_follower_psrr,
    plot_follower_response,
    plot_follower_slew,
    plot_follower_transfer,
)
from flow.follower.sim import FollowerTbParams
from flow.follower.subckt import CASES


def _single_pole(vin: float, value: float, pole_hz: float, *, output_test: bool = False) -> MeasFollower:
    """A follower whose response is ``value`` falling at one pole ``pole_hz``; the output 0.3 V below vin."""
    frequency_hz = np.logspace(3, 11, 161)
    response = value / (1 + 1j * frequency_hz / pole_hz)
    params = FollowerTbParams(follower=CASES["source"], vin=vin, output_test=output_test)
    return MeasFollower(
        group=None,
        index=None,
        dut=params.follower,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC),
            readbacks={"op_supply_current_a": 40e-6, "op_vout_v": vin - 0.3},
        ),
        param=params,
        frequency_hz=frequency_hz,
        magnitude=np.abs(response),
        phase_deg=np.degrees(np.unwrap(np.angle(response))),
        supply_gain_v_per_v=np.full_like(frequency_hz, 0.01 * value),
    )


def _step(rise_v_per_s: float, fall_v_per_s: float) -> MeasFollowerStep:
    """A follower output ramping between 0.6 and 0.9 V at the given slopes after each input edge
    (20 ns period: up at 5 ns, down at 15 ns), drawing 40 µA."""
    params = FollowerTbParams(follower=CASES["source"], vin=0.9, step_v=0.3)
    time_s = np.arange(0.0, 20e-9, 5e-12)
    rising = np.clip(0.6 + rise_v_per_s * (time_s - 5e-9), 0.6, 0.9)
    output = np.where(time_s < 15e-9, rising, np.clip(0.9 - fall_v_per_s * (time_s - 15e-9), 0.6, 0.9))
    vin = np.where((time_s >= 5e-9) & (time_s < 15e-9), 1.05, 0.75)
    return MeasFollowerStep(
        group=None,
        index=None,
        dut=params.follower,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"vin": vin[None, :], "vout": output[None, :]},
            i={"vdd": np.full((1, len(time_s)), 40e-6)},
        ),
    )


def test_transfer_gain_bandwidth_and_impedance() -> None:
    transfer = analyze_follower_transfer([_single_pole(vin, 0.85, 1e9) for vin in (0.6, 0.9)])
    assert transfer.gain_v_per_v == pytest.approx([0.85, 0.85], rel=1e-6)
    assert transfer.bandwidth_hz == pytest.approx([1e9, 1e9], rel=0.01)
    assert transfer.level_shift_v == pytest.approx([0.3, 0.3])
    # the supply passes a hundredth of the input's gain: 40 dB of rejection
    assert transfer.psrr_db == pytest.approx([40.0, 40.0], abs=1e-6)
    impedance = analyze_follower_impedance([_single_pole(0.9, 1500.0, 2e9, output_test=True)])
    assert impedance.impedance_ohm[0] == pytest.approx(1500.0, rel=1e-6)
    with pytest.raises(ValueError, match="on the input"):
        analyze_follower_transfer([_single_pole(0.9, 1500.0, 2e9, output_test=True)])
    with pytest.raises(ValueError, match="output test current"):
        analyze_follower_impedance([_single_pole(0.9, 0.85, 1e9)])


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    transfer = analyze_follower_transfer([_single_pole(vin, 0.8, 1e9 * (1 + vin)) for vin in (0.3, 0.6, 0.9)])
    impedance = analyze_follower_impedance(
        [_single_pole(vin, 1000.0 / (1 + vin), 2e9, output_test=True) for vin in (0.3, 0.6, 0.9)]
    )
    paths = (
        *plot_follower_transfer([transfer], labels=["a"], output_path=tmp_path / "transfer"),
        *plot_follower_bandwidth([transfer], [impedance], labels=["a"], output_path=tmp_path / "bandwidth"),
        *plot_follower_response([transfer], [impedance], labels=["a"], output_path=tmp_path / "response"),
    )
    assert paths and all(path.exists() for path in paths)


def test_slew_rates_settling_and_overshoot_of_a_ramped_step() -> None:
    # 1 V/ns up (the device pulls), 0.1 V/ns down (only the bias current)
    slew = analyze_follower_slew([_step(1e9, 1e8)])
    assert slew.low_v[0] == pytest.approx(0.6) and slew.high_v[0] == pytest.approx(0.9)
    assert slew.rise_slew_v_per_s[0] == pytest.approx(1e9, rel=1e-3)
    assert slew.fall_slew_v_per_s[0] == pytest.approx(-1e8, rel=1e-3)
    # within 1 % of the 0.3 V step: 0.297 V of ramp after the edge's middle
    assert slew.rise_settling_s[0] == pytest.approx(0.297e-9, rel=0.02)
    assert slew.fall_settling_s[0] == pytest.approx(2.97e-9, rel=0.01)
    assert slew.rise_overshoot[0] == 0.0 and slew.fall_overshoot[0] == 0.0
    assert slew.supply_current_a[0] == pytest.approx(40e-6)


def test_psrr_and_slew_plots_render(tmp_path: Path) -> None:
    transfer = analyze_follower_transfer([_single_pole(vin, 0.8, 1e9) for vin in (0.3, 0.6, 0.9)])
    step = _step(1e9, 1e8)
    paths = (
        *plot_follower_psrr([transfer], labels=["a"], output_path=tmp_path / "psrr"),
        *plot_follower_slew([step], [analyze_follower_slew([step])], labels=["a"], output_path=tmp_path / "slew"),
    )
    assert paths and all(path.exists() for path in paths)
