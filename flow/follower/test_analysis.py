"""Follower analyses and plots on synthetic responses of known gain, bandwidth, and impedance."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo
from flow.follower.analysis import MeasFollower, analyze_follower_impedance, analyze_follower_transfer
from flow.follower.plots import plot_follower_bandwidth, plot_follower_response, plot_follower_transfer
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
    )


def test_transfer_gain_bandwidth_and_impedance() -> None:
    transfer = analyze_follower_transfer([_single_pole(vin, 0.85, 1e9) for vin in (0.6, 0.9)])
    assert transfer.gain_v_per_v == pytest.approx([0.85, 0.85], rel=1e-6)
    assert transfer.bandwidth_hz == pytest.approx([1e9, 1e9], rel=0.01)
    assert transfer.level_shift_v == pytest.approx([0.3, 0.3])
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
