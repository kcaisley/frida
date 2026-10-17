"""OTA analysis and plots on synthetic responses of known gain, bandwidth, and phase margin."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo
from flow.ota.analysis import MeasOta, analyze_ota_ac
from flow.ota.plots import plot_ota_bode, plot_ota_common_mode, plot_ota_supply
from flow.ota.sim import OtaTbParams
from flow.ota.subckt import CASES


def _two_pole(gain: float, pole_hz: float, second_hz: float, *, vdd: float = 1.2, vcm: float = 0.6) -> MeasOta:
    """An amplifier of DC gain ``gain`` and poles at ``pole_hz`` and ``second_hz``."""
    frequency_hz = np.logspace(3, 11, 161)
    response = gain / ((1 + 1j * frequency_hz / pole_hz) * (1 + 1j * frequency_hz / second_hz))
    params = OtaTbParams(ota=CASES["five_t"], vdd=vdd, vcm=vcm)
    return MeasOta(
        group=None,
        index=None,
        dut=params.ota,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC),
            readbacks={"op_supply_current_a": 50e-6, "op_outp_v": 0.6},
        ),
        param=params,
        frequency_hz=frequency_hz,
        gain_v_per_v=np.abs(response),
        phase_deg=np.degrees(np.unwrap(np.angle(response))),
    )


def test_gain_bandwidth_and_phase_margin_of_a_two_pole_amplifier() -> None:
    result = analyze_ota_ac([_two_pole(100.0, 1e6, 1e9)])
    # unity gain near the gain-bandwidth product; both poles' phase there sets the margin
    assert result.dc_gain_db[0] == pytest.approx(40.0, abs=0.01)
    assert result.ugbw_hz[0] == pytest.approx(99.5e6, rel=0.01)
    expected = 180 - np.degrees(np.arctan(result.ugbw_hz[0] / 1e6) + np.arctan(result.ugbw_hz[0] / 1e9))
    assert result.phase_margin_deg[0] == pytest.approx(expected, abs=0.3)
    assert result.power_w[0] == pytest.approx(1.2 * 50e-6)
    assert result.output_cm_v[0] == pytest.approx(0.6)
    below_unity = analyze_ota_ac([_two_pole(0.5, 1e6, 1e9)])
    assert np.isnan(below_unity.ugbw_hz[0]) and np.isnan(below_unity.phase_margin_deg[0])


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    vcm = analyze_ota_ac([_two_pole(100.0 * value, 1e6, 1e9, vcm=value) for value in (0.4, 0.6, 0.8)])
    supply = analyze_ota_ac([_two_pole(100.0, 1e6 * value, 1e9, vdd=value) for value in (1.0, 1.2)])
    paths = (
        *plot_ota_bode([vcm], labels=["a"], output_path=tmp_path / "bode"),
        *plot_ota_common_mode([vcm], labels=["a"], output_path=tmp_path / "common_mode"),
        *plot_ota_supply([supply], labels=["a"], output_path=tmp_path / "supply"),
    )
    assert paths and all(path.exists() for path in paths)
