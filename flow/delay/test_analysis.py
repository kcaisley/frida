"""The chain's analyses, metrics and record on synthetic runs of known frequency, delay and current,
as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot

from . import runs
from .analysis import analyze_oscillation, analyze_propagation, metrics
from .params import CONTROL_SWEEP, NOMINAL_CONTROL, SUPPLY_SWEEP, Params, TbParams
from .types import AnalysisOscillation, AnalysisPropagation, Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))


def run(tb: TbParams, outp: np.ndarray, time_s: np.ndarray, current_a: float, inp: np.ndarray | None = None) -> Meas:
    """A run of ``tb`` whose output is ``outp`` over ``time_s`` (its input ``inp``, else none) and
    whose supply draws ``current_a`` throughout."""
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"outp": outp, "inp": np.zeros_like(time_s) if inp is None else inp},
        i={"vdd": np.full(len(time_s), current_a)},
    )


def ring_run(tb: TbParams, frequency_hz: float, current_a: float = 50e-6) -> Meas:
    """A ring held until its enable rises, then a rail-to-rail sine at ``frequency_hz``."""
    time_s = np.arange(0, tb.stop_time_s, 2e-12)
    started = time_s > tb.enable_delay_s
    outp = np.where(started, tb.vdd / 2 * (1 - np.cos(2 * np.pi * frequency_hz * (time_s - tb.enable_delay_s))), 0.0)
    return run(tb, outp, time_s, current_a)


def line_run(tb: TbParams, delay_s: float, current_a: float = 20e-6) -> Meas:
    """A delay line whose output is its input clock ``delay_s`` later, inverted by an odd chain."""
    time_s = np.arange(0, tb.stop_time_s, 1e-12)
    period = tb.clock_period_s
    phase = (time_s - period / 4) % period
    source = np.where((time_s >= period / 4) & (phase < period / 2), tb.vdd, 0.0)
    shifted = np.interp(time_s - delay_s, time_s, source, left=0.0)
    return run(tb, tb.vdd - shifted if tb.params.stages % 2 else shifted, time_s, current_a, source)


def test_ring_frequency_current_and_energy() -> None:
    ring = runs.ring5()
    sweep = [
        ring_run(TbParams(params=ring, vdd=vdd, vcont_v=0.8), frequency_hz)
        for vdd, frequency_hz in ((1.0, 1e9), (1.2, 2e9))
    ]
    result = analyze_oscillation(sweep)
    assert isinstance(result, AnalysisOscillation) and result.dut == ring
    assert result.oscillation_frequency_hz == pytest.approx([1e9, 2e9], rel=1e-3)
    assert result.idd_a == pytest.approx([50e-6, 50e-6])
    assert result.average_power_w == pytest.approx([50e-6, 60e-6])
    assert result.energy_per_cycle_j == pytest.approx([50e-15, 30e-15], rel=1e-3)
    assert result.swing_v == pytest.approx([1.0, 1.2], rel=1e-3)
    assert result.duty_cycle == pytest.approx([0.5, 0.5], abs=0.01)
    # a period is two passes around the five stages
    assert result.stage_delay_s == pytest.approx([100e-12, 50e-12], rel=1e-3)
    assert result.oscillating.all()
    tb = TbParams(params=ring)
    time_s = np.arange(0, tb.stop_time_s, 2e-12)
    stopped = analyze_oscillation([run(tb, np.zeros_like(time_s), time_s, 0.0)])
    assert not stopped.oscillating[0] and np.isnan(stopped.oscillation_frequency_hz[0])
    with pytest.raises(ValueError, match="requires a ring"):
        analyze_oscillation([replace(sweep[0], dut=runs.chain4())])
    with pytest.raises(ValueError, match="requires a transient"):
        analyze_oscillation([replace(sweep[0], time_s=np.zeros(0), v={}, i={})])


def test_line_delay_follows_the_input_by_the_set_shift() -> None:
    result = analyze_propagation([line_run(TbParams(params=runs.chain4()), 60e-12)])
    assert isinstance(result, AnalysisPropagation)
    assert result.delay_rise_s[0] == pytest.approx(60e-12, abs=2e-12)
    assert result.delay_fall_s[0] == pytest.approx(60e-12, abs=2e-12)
    assert result.delay_s[0] == pytest.approx(60e-12, abs=2e-12)
    assert result.stage_delay_s[0] == pytest.approx(15e-12, abs=1e-12)
    assert result.clock_period_s[0] == pytest.approx(4e-9)
    assert result.average_power_w[0] == pytest.approx(1.2 * 20e-6)
    assert result.energy_per_cycle_j[0] == pytest.approx(1.2 * 20e-6 * 4e-9)
    assert result.valid[0]
    with pytest.raises(ValueError, match="not a ring"):
        analyze_propagation([ring_run(TbParams(params=runs.ring5()), 1e9)])


def test_an_inverting_line_is_timed_to_the_edge_its_output_makes() -> None:
    """An odd chain's output falls after a rising input: each delay is named by the output's edge,
    and both are found."""
    result = analyze_propagation([line_run(TbParams(params=Params(stages=3)), 45e-12)])
    assert result.delay_rise_s[0] == pytest.approx(45e-12, abs=2e-12)
    assert result.delay_fall_s[0] == pytest.approx(45e-12, abs=2e-12)
    assert result.valid[0]


def _ring_measurements(ring: Params) -> dict[str, Meas]:
    """A controlled ring's runs, its frequency rising with the supply and with the control: 1 GHz
    at the nominal point, 2 GHz/V over the supply and over the control."""
    measurements = {}
    for factor in SUPPLY_SWEEP:
        tb = TbParams(params=ring, vdd=round(1.2 * factor, 4), vcont_v=0.8)
        measurements[f"supply_{round(factor * 100)}"] = ring_run(tb, 1e9 + 2e9 * (tb.vdd - 1.2))
    for step in CONTROL_SWEEP:
        if not math.isclose(step, NOMINAL_CONTROL):
            tb = TbParams(params=ring, vcont_v=round(1.2 * step, 4))
            measurements[f"control_{round(step * 12)}"] = ring_run(tb, 1e9 + 2e9 * (tb.vcont_v - 0.8))
    return measurements


def test_a_controlled_rings_record() -> None:
    ring = runs.ring5_starved()
    record = runs.results(_ring_measurements(ring))
    assert set(record.metrics) == set(Metrics.__dataclass_fields__)
    assert record.metrics["oscillation_frequency_hz"] == pytest.approx(1e9, rel=1e-3)
    assert record.metrics["swing_v"] == pytest.approx(1.2, rel=1e-3)
    assert record.metrics["stage_delay_s"] == pytest.approx(100e-12, rel=1e-3)
    assert record.metrics["average_power_w"] == pytest.approx(1.2 * 50e-6)
    assert record.metrics["energy_per_cycle_j"] == pytest.approx(60e-15, rel=1e-3)
    # the slowest stage delay over the supply: the lowest supply's, 0.76 GHz
    assert record.metrics["stage_delay_max_supply_s"] == pytest.approx(1 / (10 * 0.76e9), rel=1e-3)
    assert record.metrics["kvco_hz_per_v"] == pytest.approx(2e9, rel=1e-3)
    # a ring has no line's numbers
    for name in ("delay_rise_s", "delay_fall_s", "rise_time_s", "fall_time_s", "kdl_s_per_v"):
        assert math.isnan(record.metrics[name])
    assert [plot.name for plot in record.details] == [
        "oscillation_frequency_supply",
        "stage_delay_supply",
        "energy_supply",
        "oscillation_frequency_control",
        "kvco_control",
        "energy_control",
    ]
    assert all(isinstance(plot, Plot) for plot in record.details)
    assert record.details[0].x == list(SUPPLY_SWEEP) and len(record.details[3].x) == len(CONTROL_SWEEP)
    assert record.details[4].series["vco gain"] == pytest.approx([2e9] * len(CONTROL_SWEEP), rel=1e-2)
    assert record.waves == {"nominal": "supply_100"}


def test_a_plain_lines_record() -> None:
    line = runs.chain4()
    measurements = {
        f"supply_{round(factor * 100)}": line_run(TbParams(params=line, vdd=round(1.2 * factor, 4)), 40e-12 / factor)
        for factor in SUPPLY_SWEEP
    }
    record = runs.results(measurements)
    assert record.metrics["delay_rise_s"] == pytest.approx(40e-12, abs=2e-12)
    assert record.metrics["delay_fall_s"] == pytest.approx(40e-12, abs=2e-12)
    assert record.metrics["stage_delay_s"] == pytest.approx(10e-12, abs=1e-12)
    assert record.metrics["stage_delay_max_supply_s"] == pytest.approx(10e-12 / 0.9, abs=1e-12)
    assert record.metrics["energy_per_cycle_j"] == pytest.approx(1.2 * 20e-6 * 4e-9)
    for name in ("oscillation_frequency_hz", "swing_v", "kvco_hz_per_v", "kdl_s_per_v"):
        assert math.isnan(record.metrics[name])
    assert [plot.name for plot in record.details] == [
        "delay_rise_supply",
        "delay_fall_supply",
        "stage_delay_supply",
        "energy_supply",
    ]


def test_a_controlled_lines_gain() -> None:
    """A starved line's delay falling 100 ps/V over the control: its gain about the nominal."""
    line = runs.chain4_starved()
    by_supply = [line_run(TbParams(params=line, vdd=round(1.2 * factor, 4)), 80e-12) for factor in SUPPLY_SWEEP]
    by_control = [
        line_run(TbParams(params=line, vcont_v=round(1.2 * step, 4)), 80e-12 - 100e-12 * (1.2 * step - 0.8))
        for step in CONTROL_SWEEP
    ]
    values = metrics(supply=analyze_propagation(by_supply), control=analyze_propagation(by_control))
    assert values.kdl_s_per_v == pytest.approx(-100e-12, rel=0.05)
    assert math.isnan(values.kvco_hz_per_v)
