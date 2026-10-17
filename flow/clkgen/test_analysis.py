"""Clock conditioning analysis and plots on a synthetic clock gate of known delay and gaps."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.clkgen.analysis import MeasClkgen, analyze_clkgen_timing
from flow.clkgen.plots import plot_clkgen_frequency, plot_clkgen_supply, plot_clkgen_waveforms
from flow.clkgen.sim import ClkgenTbParams
from flow.clkgen.subckt import CASES


def _gate(vdd: float = 1.2, period_s: float = 1e-9) -> MeasClkgen:
    """A gate that passes clk 40 ps late once en is high, outn its complement 10 ps before outp."""
    params = ClkgenTbParams(clkgen=CASES["gate"], vdd=vdd, period_s=period_s)
    time_s = np.arange(0, params.cycles * period_s, 1e-12)
    clock = np.where((time_s >= period_s / 2) & (((time_s - period_s / 2) % period_s) < period_s / 2), vdd, 0.0)
    enable = np.where(time_s >= 2.25 * period_s, vdd, 0.0)
    gated = np.interp(time_s - 40e-12, time_s, clock * (enable > 0)) * np.interp(time_s - 40e-12, time_s, enable) / vdd
    early = np.interp(time_s - 30e-12, time_s, clock * (enable > 0)) * np.interp(time_s - 30e-12, time_s, enable) / vdd
    return MeasClkgen(
        group=None,
        index=None,
        dut=params.clkgen,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC)),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(
            record_index=np.arange(1),
            time_s=time_s,
            v={"clk": clock[None, :], "en": enable[None, :], "outp": gated[None, :], "outn": (vdd - early)[None, :]},
            i={"vdd": np.full((1, len(time_s)), 20e-6)},
        ),
    )


def test_gate_delay_width_gaps_and_enable() -> None:
    result = analyze_clkgen_timing([_gate()])
    assert result.delay_s[0] == pytest.approx(40e-12, abs=2e-12)
    assert result.high_width_s[0] == pytest.approx(500e-12, abs=2e-12)
    assert result.duty_cycle[0] == pytest.approx(0.5, abs=0.02)
    # outn rises 10 ps before outp falls, and falls 10 ps before outp rises
    assert result.rise_gap_s[0] == pytest.approx(-10e-12, abs=2e-12)
    assert result.fall_gap_s[0] == pytest.approx(10e-12, abs=2e-12)
    assert result.pulses_before_enable[0] == 0 and result.pulse_fraction[0] == pytest.approx(1.0)
    assert result.energy_per_cycle_j[0] == pytest.approx(1.2 * 20e-6 * 1e-9)


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    supply = analyze_clkgen_timing([_gate(vdd) for vdd in (1.0, 1.2)])
    frequency = analyze_clkgen_timing([_gate(period_s=period) for period in (1e-9, 500e-12)])
    paths = (
        *plot_clkgen_supply([supply], labels=["a"], output_path=tmp_path / "supply"),
        *plot_clkgen_frequency([frequency], labels=["a"], output_path=tmp_path / "frequency"),
        *plot_clkgen_waveforms([_gate()], labels=["a"], output_path=tmp_path / "waveforms"),
    )
    assert paths and all(path.exists() for path in paths)
