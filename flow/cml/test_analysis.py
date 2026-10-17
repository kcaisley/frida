"""CML analysis and plots on synthetic records of known swing, delay, and function."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.cml.analysis import MeasCml, analyze_cml_switching
from flow.cml.plots import plot_cml_frequency, plot_cml_tail, plot_cml_waveforms
from flow.cml.sim import CmlTbParams
from flow.cml.subckt import CASES


def _square(time_s, period, delay):
    """A ±1 square wave of ``period`` whose first rising edge is at ``delay``."""
    return np.where(((time_s - delay) % period) < period / 2, 1.0, -1.0) * np.where(time_s >= delay, 1.0, -1.0)


def _record(case: str, *, delay_s: float = 20e-12, swing_v: float = 0.25, wrong: bool = False) -> MeasCml:
    """The case's ideal output ``delay_s`` after its inputs, ``swing_v`` single-ended; ``wrong`` inverts it."""
    params = CmlTbParams(cml=CASES[case])
    period, data_period = float(params.clock_period_s), float(params.data_period_s)
    time_s = np.arange(0, float(params.tstop_s), 0.5e-12)
    data = _square(time_s, data_period, data_period / 4)
    clock = _square(time_s, period, period / 4)
    late = time_s - delay_s
    if case == "divider":
        rises = np.floor((late - period / 4) / period)
        output = np.where(rises % 2 == 0, 1.0, -1.0)
    elif case == "xor":
        output = _square(late, data_period, data_period / 4) * _square(late, period, period / 4) * -1.0
    else:
        output = _square(late, data_period, data_period / 4)
    output = -output if wrong else output
    v = {}
    for name, value in (("in", data), ("clk", clock), ("out", output)):
        v[f"{name}p"] = (1.0 + swing_v * value / 2)[None, :]
        v[f"{name}n"] = (1.0 - swing_v * value / 2)[None, :]
    return MeasCml(
        group=None,
        index=None,
        dut=params.cml,
        info=MeasInfo(
            backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC), readbacks={"tail_drive_v": 0.55}
        ),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(record_index=np.arange(1), time_s=time_s, v=v, i={"vdd": np.full((1, len(time_s)), 30e-6)}),
    )


def test_buffer_xor_and_divider_swing_delay_and_function() -> None:
    for case in ("buffer", "xor", "divider"):
        result = analyze_cml_switching([_record(case)])
        assert result.swing_v[0] == pytest.approx(0.25)
        assert result.delay_s[0] == pytest.approx(20e-12, abs=1e-12)
        assert result.correct_fraction[0] == pytest.approx(1.0)
        assert result.supply_current_a[0] == pytest.approx(30e-6)
        assert result.power_w[0] == pytest.approx(1.2 * 30e-6)
    assert analyze_cml_switching([_record("buffer", wrong=True)]).correct_fraction[0] == pytest.approx(0.0)


def test_architecture_comparison_plots_render(tmp_path: Path) -> None:
    records = [_record("buffer", delay_s=delay) for delay in (10e-12, 20e-12)]
    switching = analyze_cml_switching(records)
    paths = (
        *plot_cml_frequency([switching], labels=["a"], output_path=tmp_path / "frequency"),
        *plot_cml_tail([switching], labels=["a"], output_path=tmp_path / "tail"),
        *plot_cml_waveforms(records[:1], labels=["a"], output_path=tmp_path / "waveforms"),
    )
    assert paths and all(path.exists() for path in paths)
