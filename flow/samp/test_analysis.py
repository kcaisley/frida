"""The sampler's analyses, metrics and record on an ideal RC sampler of known time constant, pedestal
and feedthrough, as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot

from .analysis import analyze_hold, analyze_track, metrics
from .params import NOMINAL_VIN, SUPPLY_SWEEP, VIN_SWEEP, Params, TbParams
from .sweep import record
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
        v={"clk": clock, "clk_b": tb.vdd - clock, "din": data, "dout": output},
        i={"vdd": np.zeros_like(time_s)},
    )


TB = TbParams(input_step_v=0.1, periods=4)


def test_tracking_recovers_the_time_constant_and_resistance() -> None:
    track = analyze_track([rc_run(TB)])
    assert track.time_constant_s[0] == pytest.approx(0.2e-9, abs=2e-12)
    assert track.on_resistance_ohm[0] == pytest.approx(200.0, rel=0.01)
    assert track.bandwidth_hz[0] == pytest.approx(1 / (2 * np.pi * 0.2e-9), rel=0.01)
    assert abs(track.track_error_v[0]) < 1e-6
    # the time constant of the exponential, not from the clock edge: a switch slow to turn on reads alike
    late = rc_run(TB)
    shifted = np.interp(late.time_s - 40e-12, late.time_s, late.v["dout"])
    delayed = analyze_track([replace(late, v={**late.v, "dout": shifted})])
    assert delayed.time_constant_s[0] == pytest.approx(0.2e-9, abs=2e-12)


def test_hold_recovers_the_pedestal_and_feedthrough() -> None:
    hold = analyze_hold([rc_run(TB)])
    assert hold.pedestal_v[0] == pytest.approx(-2e-3, abs=1e-6)
    assert hold.feedthrough[0] == pytest.approx(1e-3, rel=1e-3)
    assert hold.droop_v_per_s[0] == pytest.approx(0.0, abs=1.0)


def test_a_run_that_never_settles_has_no_resistance() -> None:
    track = analyze_track([rc_run(TB, tau_s=50e-9)])
    assert math.isnan(track.on_resistance_ohm[0]) and math.isnan(track.time_constant_s[0])


def test_the_record_reads_every_run_and_names_its_waves() -> None:
    """``record`` from every run ``runs`` names: the metrics at mid-supply input, the plots the
    behavioral model reads (``ron_vin``), the three transients the viewer shows."""

    supply = 1.2
    base = TbParams(params=Params(), vdd=supply, input_step_v=round(supply / 12, 4), periods=3)
    runs = {f"vin_{round(f * 12)}": replace(base, input_voltage=round(f * supply, 4)) for f in VIN_SWEEP}
    runs |= {
        f"supply_{round(f * 100)}": replace(
            base, vdd=round(f * supply, 4), input_voltage=round(NOMINAL_VIN * f * supply, 4)
        )
        for f in SUPPLY_SWEEP
        if f != 1.0
    }
    result = record({name: rc_run(tb) for name, tb in runs.items()})
    assert list(result.metrics) == [
        "ron_ohm",
        "ron_max_ohm",
        "input_range_v",
        "bandwidth_hz",
        "track_error_v",
        "pedestal_v",
        "pedestal_max_v",
        "droop_v_s",
        "feedthrough_db",
        "ron_max_supply_ohm",
    ]
    assert result.metrics["ron_ohm"] == pytest.approx(200.0, rel=0.01)
    assert result.metrics["feedthrough_db"] == pytest.approx(-60.0, abs=0.1)
    assert result.metrics["input_range_v"] == pytest.approx(10 / 12 * supply)
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
    assert ron.x == pytest.approx([f * supply for f in VIN_SWEEP], abs=1e-4) and list(ron.series) == ["on-resistance"]
    assert result.details[4].x == list(SUPPLY_SWEEP)
    assert result.waves == {
        "input 1/12 of the supply": "vin_1",
        "input 6/12 of the supply": "vin_6",
        "input 11/12 of the supply": "vin_11",
    }


def test_the_metrics_take_the_nominal_point_and_the_largest_settled() -> None:
    vin = np.asarray([f * 1.2 for f in VIN_SWEEP])
    ron = np.linspace(100.0, 600.0, len(vin))
    ron[-2:] = np.nan  # the highest inputs never settle
    rows = {"group": None, "index": None, "dut": Params(), "vdd_v": np.full(len(vin), 1.2), "vin_v": vin}
    track = AnalysisTrack(
        **rows,
        time_constant_s=ron * 1e-12,
        on_resistance_ohm=ron,
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
    assert values["pedestal_max_v"] == pytest.approx(3e-3)
    assert values["input_range_v"] == pytest.approx(vin[-3] - vin[0])
