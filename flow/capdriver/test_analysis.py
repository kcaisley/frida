"""Capacitor driver analysis and plots on synthetic RC outputs of known delay, resistance and energy."""

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.capdriver.analysis import MeasCapdriver, analyze_capdriver_drive
from flow.capdriver.plots import plot_capdriver_load, plot_capdriver_supply
from flow.capdriver.sim import CapdriverTbParams
from flow.capdriver.subckt import CASES


def _rc(load: float, *, resistance: float = 2e3, lag: float = 50e-12, vdd: float = 1.2) -> MeasCapdriver:
    """An output following each input edge after ``lag`` as an RC of ``resistance`` into ``load``,
    the supply current charging it (C V per rising output)."""
    period = max(2e-9, 2e5 * load)
    params = CapdriverTbParams(driver=CASES["x1"], vdd=vdd, cload=load, period_s=period, transition_time_s=30e-12)
    time_s = np.arange(0.0, 2 * period, period / 4000)
    tau = resistance * load

    def edges(start: float) -> tuple[np.ndarray, np.ndarray]:
        # each input edge's middle: half the source's 30 ps transition after it starts
        up, down = start + period / 4 + 15e-12, start + 3 * period / 4 + 15e-12
        level = np.where(time_s < up, 0.0, np.where(time_s < down, 1.0, 0.0))
        rising = np.clip((time_s - up - lag) / tau, 0.0, None)
        falling = np.clip((time_s - down - lag) / tau, 0.0, None)
        output = np.where(
            time_s < down + lag, 1 - np.exp(-rising), np.exp(-falling) * (1 - math.exp(-(period / 2) / tau))
        )
        output = np.where((time_s >= up) & (time_s < start + period), output, 0.0)
        level = np.where((time_s >= start) & (time_s < start + period), level, 0.0)
        return level * vdd, output * vdd

    state, out_state = edges(0.0)
    invert, out_invert = edges(period)
    output = np.where(time_s < period, out_state, out_invert)
    # the supply delivers C dV/dt while the output rises
    current = (
        np.where(np.diff(output, prepend=0.0) > 0, np.diff(output, prepend=0.0) / np.diff(time_s, prepend=1.0), 0.0)
        * load
    )
    return MeasCapdriver(
        group=None,
        index=None,
        dut=params.driver,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 19, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"dac_state": state[None, :], "dac_drive_invert": invert[None, :], "dac_drive": output[None, :]},
            i={"vdd": current[None, :]},
        ),
    )


def test_delay_transition_settling_and_energy_of_an_rc_driver() -> None:
    drive = analyze_capdriver_drive([_rc(load) for load in (10e-15, 100e-15, 1e-12)])
    tau = 2e3 * drive.load_f
    # mid-supply after ln 2 RC behind the lag, from the input edge's mid-supply crossing
    np.testing.assert_allclose(drive.state_rise_delay_s, 50e-12 + math.log(2) * tau, rtol=0.03)
    np.testing.assert_allclose(drive.invert_fall_delay_s, 50e-12 + math.log(2) * tau, rtol=0.03)
    np.testing.assert_allclose(drive.rise_time_s, math.log(9) * tau, rtol=0.02)
    np.testing.assert_allclose(drive.rise_settling_s, 50e-12 + math.log(100) * tau, rtol=0.03)
    rise_ohm, fall_ohm = drive.drive_resistance_ohm()
    assert rise_ohm == pytest.approx(2e3, rel=0.01) and fall_ohm == pytest.approx(2e3, rel=0.01)
    # one rising output per state cycle draws C V from the supply: C V² per cycle
    np.testing.assert_allclose(drive.energy_per_cv2, 1.0, rtol=0.02)


def test_drive_plots_render(tmp_path: Path) -> None:
    load = analyze_capdriver_drive([_rc(value) for value in (10e-15, 100e-15)])
    supply = analyze_capdriver_drive([_rc(100e-15, vdd=value) for value in (1.0, 1.2)])
    paths = (
        *plot_capdriver_load([load], labels=["a"], output_path=tmp_path / "load"),
        *plot_capdriver_supply([supply], labels=["a"], output_path=tmp_path / "supply"),
    )
    assert paths and all(path.exists() for path in paths)
