"""Phase interpolator analyses and plots on a synthetic linear mix of two slewed phases."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.pi.analysis import MeasPi, analyze_pi_linearity, analyze_pi_phase
from flow.pi.plots import plot_pi_frequency, plot_pi_transfer, plot_pi_waveforms
from flow.pi.sim import PiTbParams
from flow.pi.subckt import CASES


def _trapezoid(time_s, period, delay, transition):
    """A ±1 clock of ``period`` with ``transition`` edges, its first rising edge starting at ``delay``."""
    phase = (time_s - delay) % period
    high = period / 2 - transition
    return np.interp(phase, [0, transition, transition + high, 2 * transition + high, period], [-1, 1, 1, -1, -1])


def _mix(case: str, spacing_deg: float, *, period_s: float = 400e-12) -> MeasPi:
    """The case's phases and an output that is their weighted sum 20 ps later: an ideal linear interpolator."""
    params = PiTbParams(pi=CASES[case], spacing_deg=spacing_deg, period_s=period_s, transition_time_s=period_s / 4)
    time_s = np.arange(0, params.cycles * period_s, 0.5e-12)
    a = _trapezoid(time_s, period_s, period_s / 4, period_s / 4)
    b = _trapezoid(time_s, period_s, period_s / 4 + spacing_deg / 360 * period_s, period_s / 4)
    weights = params.pi.weight_a, params.pi.weight_b
    late = time_s - 20e-12
    output = (
        weights[0] * _trapezoid(late, period_s, period_s / 4, period_s / 4)
        + weights[1] * _trapezoid(late, period_s, period_s / 4 + spacing_deg / 360 * period_s, period_s / 4)
    ) / sum(weights)
    v = {}
    for name, value in (("a", a), ("b", b), ("out", output)):
        v[f"{name}p"] = (0.6 + 0.3 * value)[None, :]
        v[f"{name}n"] = (0.6 - 0.3 * value)[None, :]
    return MeasPi(
        group=None,
        index=None,
        dut=params.pi,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(record_index=np.arange(1), time_s=time_s, v=v, i={"vdd": np.full((1, len(time_s)), 50e-6)}),
    )


def test_a_linear_mix_follows_its_weights() -> None:
    for case, share in (("cml_half", 0.5), ("cml_quarter", 0.25)):
        # spacings over which both edges still ramp where the mix crosses: the linear range
        sweep = [_mix(case, spacing) for spacing in (0.0, 20.0, 40.0, 60.0)]
        phase = analyze_pi_phase(sweep)
        # the mix crosses where the weighted edges cancel: the spacing's weight share past A, plus 20 ps
        assert phase.output_phase_deg == pytest.approx(360 * 20e-12 / 400e-12 + share * phase.spacing_deg, abs=0.5)
        assert phase.duty_cycle == pytest.approx(0.5, abs=0.01)
        linearity = analyze_pi_linearity(sweep, phase=phase)
        assert linearity.slope == pytest.approx(share, abs=0.01)
        assert linearity.max_inl_deg < 0.5


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    sweep = [_mix("cml_half", spacing) for spacing in (0.0, 45.0, 90.0, 135.0)]
    phase = analyze_pi_phase(sweep)
    frequency = analyze_pi_phase([_mix("cml_half", 90.0, period_s=period) for period in (400e-12, 800e-12)])
    paths = (
        *plot_pi_transfer(
            [phase], [analyze_pi_linearity(sweep, phase=phase)], labels=["a"], output_path=tmp_path / "transfer"
        ),
        *plot_pi_frequency([frequency], labels=["a"], output_path=tmp_path / "frequency"),
        *plot_pi_waveforms(sweep[2:3], labels=["a"], output_path=tmp_path / "waveforms"),
    )
    assert paths and all(path.exists() for path in paths)
