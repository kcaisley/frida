"""The sampler's analyses, metrics and record on an ideal RC sampler of known time constant, pedestal
and feedthrough, as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot

from . import runs
from .analysis import analyze_hold, analyze_track, metrics
from .params import NOMINAL_VIN, SUPPLY_SWEEP, VIN_SWEEP, Params, Stimulus, TbParams
from .runs import results
from .types import AnalysisHold, AnalysisTrack

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 26, tzinfo=UTC))


def rc_run(tb: TbParams, *, tau_s: float = 0.2e-9, pedestal_v: float = -2e-3, feedthrough: float = 1e-3) -> Meas:
    """A run of ``tb`` as an ideal RC sampler: tracking its input with ``tau_s`` while the clock is
    high, leaving ``pedestal_v`` as it opens, ``feedthrough`` of the input's step while it holds;
    ideal clock and input edges, a sample every picosecond."""

    period, high, vin, step = tb.clock_period_s, tb.clock_high_time_s, tb.input_voltage, tb.input_step_v
    time_s = np.arange(0.0, tb.stop_s, 1e-12)
    phase = np.mod(time_s, period)
    clock = np.where(phase < high, tb.vdd, 0.0)
    # the input steps up, then down, every period, half-way through the hold phase
    first = high + (period - high) / 2
    data = vin + step / 2 * np.where(np.floor((time_s - first) / period) % 2 == 0, 1.0, -1.0)
    data[time_s < first] = vin - step / 2
    output = np.empty_like(time_s)
    value = vin
    for k in range(tb.periods):
        track = (time_s >= k * period) & (time_s < k * period + high)
        level = data[track][0]
        output[track] = level + (value - level) * np.exp(-(time_s[track] - k * period) / tau_s)
        value = output[track][-1] + pedestal_v
        hold = (time_s >= k * period + high) & (time_s < (k + 1) * period)
        output[hold] = value + feedthrough * (data[hold] - data[hold][0])
        value = output[hold][-1]
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"clk": clock, "clk_b": tb.vdd - clock, "vin": data, "vout": output},
        i={"vdd": np.zeros_like(time_s)},
    )


TB = TbParams(input_step_v=0.1, periods=4)


def test_tracking_recovers_the_time_constant_and_resistance() -> None:
    track = analyze_track([rc_run(TB)])
    assert track.tau_s[0] == pytest.approx(0.2e-9, abs=2e-12)
    assert track.ron_ohm[0] == pytest.approx(200.0, rel=0.01)
    assert track.bandwidth_hz[0] == pytest.approx(1 / (2 * np.pi * 0.2e-9), rel=0.01)
    assert abs(track.track_error_v[0]) < 1e-6
    # the time constant of the exponential, not from the clock edge: a switch slow to turn on reads alike
    late = rc_run(TB)
    shifted = np.interp(late.time_s - 40e-12, late.time_s, late.v["vout"])
    delayed = analyze_track([replace(late, v={**late.v, "vout": shifted})])
    assert delayed.tau_s[0] == pytest.approx(0.2e-9, abs=2e-12)


def test_hold_recovers_the_pedestal_and_feedthrough() -> None:
    hold = analyze_hold([rc_run(TB)])
    assert hold.pedestal_v[0] == pytest.approx(-2e-3, abs=1e-6)
    assert hold.feedthrough[0] == pytest.approx(1e-3, rel=1e-3)
    assert hold.droop_v_per_s[0] == pytest.approx(0.0, abs=1.0)


def test_a_run_that_never_settles_has_no_resistance() -> None:
    track = analyze_track([rc_run(TB, tau_s=50e-9)])
    assert math.isnan(track.ron_ohm[0]) and math.isnan(track.tau_s[0])


def ideal_run(tb: TbParams, *, tau_s: float = 0.2e-9, pedestal_v: float = -2e-3) -> Meas:
    """A run of any of ``tb``'s stimuli (a level, a step, a sine; a DAC step ignored) into an ideal
    RC sampler: closed while the clock is above mid-supply, relaxing to the input with ``tau_s``,
    leaving ``pedestal_v`` as it opens; a sample every ``waveform_sample_interval_s``."""

    period, high, edge = tb.clock_period_s, tb.clock_high_time_s, tb.clock_transition_time_s
    dt = tb.waveform_sample_interval_s
    time_s = np.arange(0.0, tb.stop_s + dt / 2, dt)
    phase = np.mod(time_s, period)
    clock = np.interp(phase, [0.0, edge, edge + high, 2 * edge + high, period], [0.0, tb.vdd, tb.vdd, 0.0, 0.0])
    if tb.stimulus is Stimulus.SINE:
        data = tb.input_voltage + tb.sine_amplitude_v * np.sin(2 * np.pi * tb.sine_frequency_hz * time_s)
    else:
        first = high + (period - high) / 2
        data = tb.input_voltage + tb.input_step_v / 2 * np.where(
            np.floor((time_s - first) / period) % 2 == 0, 1.0, -1.0
        )
        data[time_s < first] = tb.input_voltage - tb.input_step_v / 2
    output = np.empty_like(time_s)
    value, closed = float(data[0]), False
    decay = math.exp(-dt / tau_s)
    for index, level in enumerate(data):
        now = clock[index] > tb.vdd / 2
        if closed and not now:
            value += pedestal_v
        if now:
            value = level + (value - level) * decay
        closed = now
        output[index] = value
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"clk": clock, "clk_b": tb.vdd - clock, "vin": data, "vout": output},
        i={"vdd": np.full_like(time_s, 1e-6), "clk": np.zeros_like(time_s), "clk_b": np.zeros_like(time_s)},
    )


def test_the_record_reads_every_run_and_names_its_waves(monkeypatch: pytest.MonkeyPatch) -> None:
    """``results`` from every run ``testbenches`` names: the metrics at the nominal input, the
    plots the behavioral model reads (``ron_vin``, over the levels and the top one), the three
    transients the viewer shows."""

    monkeypatch.setattr(runs.importlib, "import_module", lambda name: SimpleNamespace(install=_Install()))
    benches = runs.testbenches("tsmc65", Params())
    result = results({name: ideal_run(tb) for name, tb in benches.items()})
    assert {
        "ron_ohm",
        "ron_max_ohm",
        "input_range_v",
        "bandwidth_hz",
        "track_error_v",
        "pedestal_v",
        "pedestal_max_v",
        "droop_v_per_s",
        "feedthrough_db",
        "ron_max_supply_ohm",
        "ron_max_corner_ohm",
        "acquisition_12b_s",
        "thd_high_db",
        "model_error_v",
        "energy_per_cycle_j",
        "terminal_max_v",
    } <= set(result.metrics)
    assert result.metrics["ron_ohm"] == pytest.approx(200.0, rel=0.01)
    assert result.metrics["pedestal_v"] == pytest.approx(-2e-3, abs=1e-6)
    # the levels 1/12 to 11/12 of 1.2 V, and the top one, 1.195 V: 1.095 V
    assert result.metrics["input_range_v"] == pytest.approx(1.195 - 0.1)
    # [Razavi-ADC] Eq. (3.82), p. 54: t_acq = R C ln(2^(N+1)) from the clock's edge midpoint (its
    # half edge before the switch closes adds nothing: the ideal switch closes at mid-supply)
    assert result.metrics["acquisition_12b_s"] == pytest.approx(200e-12 * math.log(1.0 / (1.2 / 2**13)), rel=0.02)
    # the model of the same RC and pedestal predicts every held sample of an ideal switch
    assert result.metrics["model_error_v"] < 1e-4
    # no device values saved by the synthetic runs: no stress figures
    assert math.isnan(result.metrics["terminal_max_v"])
    # 1 uA from 1.2 V over a 10 ns period
    assert result.metrics["energy_per_cycle_j"] == pytest.approx(1.2e-6 * 10e-9, rel=1e-6)
    assert [plot.name for plot in result.details] == [
        "ron_vin",
        "track_error_vin",
        "pedestal_vin",
        "feedthrough_vin",
        "ron_supply",
        "pedestal_supply",
    ]
    assert all(isinstance(plot, Plot) for plot in result.details)
    ron = result.details[0]
    assert ron.x == pytest.approx([*(f * 1.2 for f in VIN_SWEEP), 1.195], abs=1e-4)
    assert result.details[4].x == pytest.approx(list(SUPPLY_SWEEP))
    assert result.waves == {
        "input 1/12 of the supply": "vin_1",
        "input 6/12 of the supply": "vin_6",
        "input 11/12 of the supply": "vin_11",
    }


class _Install:
    @staticmethod
    def supply_voltage(corner) -> float:
        return 1.2


def test_the_metrics_take_the_nominal_point_and_the_largest_settled() -> None:
    vin = np.asarray([f * 1.2 for f in VIN_SWEEP])
    ron = np.linspace(100.0, 600.0, len(vin))
    ron[-2:] = np.nan  # the highest inputs never settle
    rows = {"group": None, "index": None, "dut": Params(), "vdd_v": np.full(len(vin), 1.2), "vin_v": vin}
    track = AnalysisTrack(
        **rows,
        tau_s=ron * 1e-12,
        ron_ohm=ron,
        bandwidth_hz=1 / (2 * np.pi * ron * 1e-12),
        track_error_v=np.zeros(len(vin)),
    )
    hold = AnalysisHold(
        **rows,
        pedestal_v=np.linspace(-1e-3, 3e-3, len(vin)),
        droop_v_per_s=np.zeros(len(vin)),
        feedthrough=np.full(len(vin), 1e-3),
    )
    values = metrics(track=track, hold=hold, supply=track)
    nominal = VIN_SWEEP.index(NOMINAL_VIN)
    assert values["ron_ohm"] == ron[nominal] and values["pedestal_v"] == hold.pedestal_v[nominal]
    assert values["ron_max_ohm"] == values["ron_max_supply_ohm"] == np.nanmax(ron)
    # the largest pedestal where a point settled: the highest two never did
    assert values["pedestal_max_v"] == pytest.approx(hold.pedestal_v[-3])
    assert values["input_range_v"] == pytest.approx(vin[-3] - vin[0])
