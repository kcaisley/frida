"""The sampler's analyses, metrics and record on an ideal RC sampler of known time constant, pedestal
and feedthrough, as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest

from flow import capdac
from flow.pipeline import Meas, MeasInfo, Plot

from . import runs
from .analysis import (
    analyze_acquisition,
    analyze_droop,
    analyze_energy,
    analyze_hold,
    analyze_sine,
    analyze_track,
    metrics,
)
from .params import (
    ADC_CM,
    ADC_PERIOD_S,
    ADC_TRACK_S,
    LEAKAGE_GMIN_S,
    NOMINAL_VIN,
    SUPPLY_SWEEP,
    VIN_BOTTOM,
    VIN_SWEEP,
    Params,
    Stimulus,
    TbParams,
)
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


# the gate capacitance each ideal clock source charges and discharges
CLOCK_LOAD_F = 10e-15


def ideal_run(tb: TbParams, *, tau_s: float = 0.2e-9, pedestal_v: float = -2e-3, droop_v_per_s: float = 0.0) -> Meas:
    """A run of any of ``tb``'s stimuli (a level, a step, a sine; a DAC step ignored) into an ideal
    RC sampler: closed while the clock is above mid-supply, relaxing to the input with ``tau_s``,
    leaving ``pedestal_v`` as it opens and drifting at ``droop_v_per_s`` while open; a sample every
    ``waveform_sample_interval_s``. The supply delivers 1 uA; each clock source charges
    ``CLOCK_LOAD_F`` on its rising edge and takes the charge back on its falling one."""

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
        else:
            value += droop_v_per_s * dt
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
        i={
            "vdd": np.full_like(time_s, 1e-6),
            "clk": CLOCK_LOAD_F * np.gradient(clock, time_s),
            "clk_b": -CLOCK_LOAD_F * np.gradient(clock, time_s),
        },
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
    # half edge before the switch closes adds nothing: the ideal switch closes at mid-supply), the
    # band half an LSB of the step itself: 200 ps x ln 2^13 = 1.802 ns
    assert result.metrics["acquisition_12b_s"] == pytest.approx(200e-12 * 13 * math.log(2), rel=5e-3)
    # the model of the same RC and pedestal predicts every held sample of an ideal switch
    assert result.metrics["model_error_v"] < 1e-4
    # no device values saved by the synthetic runs: no stress figures
    assert math.isnan(result.metrics["terminal_max_v"])
    # 1 uA from 1.2 V over the level runs' 15 ns period, and each clock's 10 fF charged from 1.2 V
    # once: 1.2 x (15 fC + 24 fC) = 46.8 fJ (in femtojoules: approx's default absolute tolerance
    # is above a value in joules)
    assert result.metrics["energy_per_cycle_j"] / 1e-15 == pytest.approx(46.8, rel=1e-3)
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
    # over the levels the largest of those that settled: a level without a reading is outside the range
    assert values["ron_max_ohm"] == np.nanmax(ron)
    # over the supplies (here the same points) a point without a reading may be the largest: unknown
    assert math.isnan(values["ron_max_supply_ohm"])
    # the largest pedestal where a point settled: the highest two never did
    assert values["pedestal_max_v"] == pytest.approx(hold.pedestal_v[-3])
    assert values["input_range_v"] == pytest.approx(vin[-3] - vin[0])


def test_a_supply_or_corner_maximum_is_unknown_where_one_of_its_runs_has_no_reading() -> None:
    """Three supply runs at 100, 400 and 200 ohm give 400 ohm; with the 400-ohm run unreadable (NaN)
    the largest is unknown, NaN, not the 200 ohm of the two read. The corners alike."""
    vin = np.full(3, 0.6)
    rows = {"group": None, "index": None, "dut": Params(), "vdd_v": np.full(3, 1.2), "vin_v": vin}

    def track(ron: np.ndarray) -> AnalysisTrack:
        return AnalysisTrack(
            **rows,
            tau_s=ron * 1e-12,
            ron_ohm=ron,
            bandwidth_hz=1 / (2 * np.pi * ron * 1e-12),
            track_error_v=np.zeros(3),
        )

    hold = AnalysisHold(**rows, pedestal_v=np.full(3, 1e-3), droop_v_per_s=np.zeros(3), feedthrough=np.full(3, 1e-3))
    read = track(np.asarray([100.0, 400.0, 200.0]))
    unread = track(np.asarray([100.0, np.nan, 200.0]))
    assert metrics(track=read, hold=hold, supply=read)["ron_max_supply_ohm"] == 400.0
    assert math.isnan(metrics(track=read, hold=hold, supply=unread)["ron_max_supply_ohm"])
    corners = metrics(track=read, hold=hold, supply=read, corners=unread, corners_hold=hold)
    assert math.isnan(corners["ron_max_corner_ohm"]) and corners["pedestal_max_corner_v"] == 1e-3


def test_the_energy_counts_each_clocks_charge_once_though_its_source_takes_it_back() -> None:
    """[Baker] Eq. (11.15), p. 355: V_DD I_avg, the current drawn from V_DD. A clock source that
    charges 10 fF and takes it back nets nothing, but its driver draws C V_DD from V_DD each
    period: 1.2 V x (1 uA x 10 ns + 2 x 10 fF x 1.2 V) = 1.2 x (10 fC + 24 fC) = 40.8 fJ."""
    energy = analyze_energy([ideal_run(TbParams(input_step_v=0.0))])
    assert energy.energy_per_cycle_j[0] / 1e-15 == pytest.approx(40.8, rel=1e-3)


def test_the_energy_counts_the_supplys_net_charge() -> None:
    """[Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, the supply's average current. A supply that
    delivers 1 uA and takes back 10 fF x 1.2 V on each clock fall nets 1 uA x 10 ns less that
    charge a period, the clocks' charge counted as before: 1.2 V x (10 fC - 12 fC + 24 fC) = 26.4 fJ."""
    run = ideal_run(TbParams(input_step_v=0.0))
    returned = CLOCK_LOAD_F * np.minimum(np.gradient(run.v["clk"], run.time_s), 0.0)
    energy = analyze_energy([replace(run, i={**run.i, "vdd": run.i["vdd"] + returned})])
    assert energy.energy_per_cycle_j[0] / 1e-15 == pytest.approx(26.4, rel=1e-3)


def test_the_droop_is_the_slope_over_the_adcs_hold() -> None:
    """A held output falling 1e3 V/s over the ADC's 87.5 ns hold reads -1e3 V/s, with a DAC step
    or without (its step recorded), at the run's temperature."""
    tb = TbParams(input_step_v=0.0, clock_period_s=ADC_PERIOD_S, clock_high_time_s=ADC_TRACK_S, periods=3)
    droop = analyze_droop(
        [
            ideal_run(tb, droop_v_per_s=-1e3),
            ideal_run(replace(tb, temperature_c=125.0, dac_step_v=0.35), droop_v_per_s=-1e3),
        ]
    )
    assert droop.droop_v_per_s == pytest.approx([-1e3, -1e3], rel=1e-3)
    assert list(droop.temperature_c) == [25.0, 125.0] and list(droop.step_v) == [0.0, 0.35]


def test_the_metrics_take_the_droop_over_the_adcs_hold_where_it_was_run() -> None:
    track, hold = analyze_track([rc_run(TB)]), analyze_hold([rc_run(TB)])
    tb = TbParams(input_step_v=0.0, clock_period_s=ADC_PERIOD_S, clock_high_time_s=ADC_TRACK_S, periods=3)
    droop = analyze_droop(
        [ideal_run(tb, droop_v_per_s=-1.0), ideal_run(replace(tb, temperature_c=125.0), droop_v_per_s=-50.0)]
    )
    values = metrics(track=track, hold=hold, supply=track, droop=droop)
    assert values["droop_v_per_s"] == pytest.approx(-1.0, rel=1e-3)
    assert values["droop_hot_v_per_s"] == pytest.approx(-50.0, rel=1e-3)


def test_the_dac_runs_raise_the_lower_side_by_the_adcs_first_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """flow.adc's first decision raises the side below the reference by a_0 = V c_0 / C_p of its
    default array: the DAC runs step the held output up by it from the lowest level a side reaches
    and from the common mode, never past the supply."""
    monkeypatch.setattr(runs.importlib, "import_module", lambda name: SimpleNamespace(install=_Install()))
    benches = runs.testbenches("tsmc65", Params())
    main_f, diff_f = capdac.Model.plates_f(capdac.Model.Behavioral(), "p", capdac.Params(), 1.2)
    step = 1.2 * (main_f[0] - diff_f[0]) / (main_f.sum() + diff_f.sum())
    assert benches["dac_low"].input_voltage == pytest.approx(VIN_BOTTOM * 1.2, abs=1e-4)
    assert benches["dac_cm"].input_voltage == pytest.approx(ADC_CM * 1.2, abs=1e-4)
    for name in ("dac_low", "dac_cm"):
        assert benches[name].dac_step_v == pytest.approx(step, abs=1e-4)
        assert benches[name].input_voltage + benches[name].dac_step_v < 1.2
    # every run at a gmin below the leakage and the off switch's conduction a hold shows
    assert all(tb.gmin_s == LEAKAGE_GMIN_S for tb in benches.values())


def test_a_sine_outside_the_settled_levels_fits_no_aperture() -> None:
    """Where no level settles, no held sample lies inside the settled range: no model error and no
    aperture (NaN), and the model takes none."""
    tb = TbParams(
        stimulus=Stimulus.SINE,
        input_voltage=0.7,
        input_step_v=0.0,
        sine_amplitude_v=0.44,
        sine_frequency_hz=1 / (32 * ADC_PERIOD_S),
        clock_period_s=ADC_PERIOD_S,
        clock_high_time_s=ADC_TRACK_S,
        periods=34,
        waveform_sample_interval_s=50e-12,
    )
    track = analyze_track([rc_run(TB, tau_s=50e-9)])
    hold = analyze_hold([rc_run(TB, tau_s=50e-9)])
    sine = analyze_sine([ideal_run(tb)], track=track, hold=hold)
    assert math.isnan(sine.aperture_s[0]) and math.isnan(sine.model_error_v[0])


def level_run(tb: TbParams, *, tau_rise_s: float, tau_fall_s: float, pedestal_v: float = 0.0, feedthrough: float = 0.0):
    """A run of ``tb`` as the level runs drive it (sim.testbench's two input pulses in series: one
    stepping in mid-hold, over ``tb.input_transition_time_s`` where given, else a clock edge, and
    one in mid-track over a clock edge, each change centred where sim.testbench centres it) into a
    first-order switch closed between the clock's mid-supply crossings: closed, the output follows
    the input with ``tau_rise_s`` while below it and ``tau_fall_s`` while above; as it opens it
    jumps by ``pedestal_v``; open, it follows ``feedthrough`` of the input's change. A sample every
    picosecond."""
    period, high, edge = float(tb.clock_period_s), float(tb.clock_high_time_s), float(tb.clock_transition_time_s)
    vdd, vin, hold_v, track_v = float(tb.vdd), float(tb.input_voltage), float(tb.input_step_v), float(tb.track_step_v)
    time_s = np.arange(0.0, tb.stop_s, 1e-12)

    def pulse(amplitude: float, delay: float, width: float, ramp: float) -> np.ndarray:
        phase = np.mod(time_s - delay, 2 * period)
        up = np.clip(phase / ramp, 0.0, 1.0) - np.clip((phase - ramp - width) / ramp, 0.0, 1.0)
        return amplitude * (np.where(time_s < delay, 0.0, up) - 0.5)

    track = pulse(track_v, (edge + high) / 2, period - edge, edge)
    if tb.input_transition_time_s is None:
        data = vin + pulse(hold_v, high + (period - high) / 2, period, edge) + track
    else:
        slew = float(tb.input_transition_time_s)
        data = vin + pulse(hold_v, high + (period - high) / 2 - (slew - edge) / 2, period - slew, slew) + track
    phase = np.mod(time_s, period)
    clock = vdd * (np.clip(phase / edge, 0.0, 1.0) - np.clip((phase - edge - high) / edge, 0.0, 1.0))
    closed = (phase >= edge / 2) & (phase < edge + high + edge / 2)
    output = np.empty_like(time_s)
    value, opened, was_closed = float(data[0]), float(data[0]), False
    for index in range(len(time_s)):
        if closed[index]:
            tau = tau_rise_s if data[index] >= value else tau_fall_s
            value = data[index] + (value - data[index]) * math.exp(-1e-12 / tau)
            output[index] = value
        else:
            if was_closed:
                value, opened = value + pedestal_v, float(data[index])
            output[index] = value + feedthrough * (data[index] - opened)
        was_closed = bool(closed[index])
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"clk": clock, "clk_b": vdd - clock, "vin": data, "vout": output},
        i={"vdd": np.zeros_like(time_s)},
    )


LEVEL_TB = TbParams(input_voltage=0.6, input_step_v=0.01, track_step_v=0.01)


def test_a_level_run_steps_onto_its_level_in_mid_track_and_reads_the_closed_switchs_time_constant() -> None:
    """The level runs' input: 10 mV below the level until mid-track, on it until mid-hold, 10 mV
    above until the next mid-track, on it again: every track phase ends on the level, reached from
    below and from above in turn. A switch with tau 100 ps on a rising step and 200 ps on a falling
    one: the slower direction's, 200 ps, into 1 pF R_on = 200 ohm. The step is a 50 ps ramp that
    starts 2.5 ns before the instant the track error is read at (a clock edge before the clock's
    falling crossing): a first-order response leaves s (tau / T)(e^(T / tau) - 1) e^(-t / tau) =
    10 mV x 4 x (e^0.25 - 1) x e^-12.5 = 42.3 nV on the falling steps."""
    run = level_run(LEVEL_TB, tau_rise_s=100e-12, tau_fall_s=200e-12)
    falls = [k * 10e-9 + 5.05e-9 for k in range(1, 5)]
    assert np.interp(falls, run.time_s, run.v["vin"]) == pytest.approx(0.6, abs=1e-9)
    assert np.interp([2e-9, 12e-9, 22e-9], run.time_s, run.v["vin"]) == pytest.approx([0.59, 0.61, 0.59], abs=1e-9)
    track = analyze_track([run])
    assert track.tau_s[0] == pytest.approx(200e-12, rel=0.01)
    assert track.ron_ohm[0] == pytest.approx(200.0, rel=0.01)
    assert track.track_error_v[0] == pytest.approx(0.01 * 4 * (math.exp(0.25) - 1) * math.exp(-12.5), rel=0.01)
    assert analyze_track([level_run(LEVEL_TB, tau_rise_s=300e-12, tau_fall_s=200e-12)]).tau_s[0] == pytest.approx(
        300e-12, rel=0.01
    )


def test_a_pedestal_larger_than_the_step_does_not_move_the_time_constant() -> None:
    """A switch that leaves -15 mV as it opens: each track phase starts 15 mV (and the 10 mV the
    input has since stepped) from where it settles before the step in mid-track, more than that
    step's own 10 mV. The time constant is read from the step, not from the phase's start: 200 ps."""
    run = level_run(LEVEL_TB, tau_rise_s=200e-12, tau_fall_s=200e-12, pedestal_v=-15e-3)
    track = analyze_track([run])
    assert track.tau_s[0] == pytest.approx(200e-12, rel=0.01) and track.ron_ohm[0] == pytest.approx(200.0, rel=0.01)


def test_a_level_runs_hold_reads_the_step_off_the_level() -> None:
    """The input sits on the level as the clock falls and leaves it by 10 mV in mid-hold: the
    pedestal (-2 mV) from the hold's first half, the feedthrough (1e-3) over that step."""
    hold = analyze_hold(
        [level_run(LEVEL_TB, tau_rise_s=100e-12, tau_fall_s=100e-12, pedestal_v=-2e-3, feedthrough=1e-3)]
    )
    assert hold.pedestal_v[0] == pytest.approx(-2e-3, abs=1e-6)
    assert hold.feedthrough[0] == pytest.approx(1e-3, rel=1e-3)


def test_a_hold_step_over_a_nanosecond_is_read_before_its_change_starts() -> None:
    """The level runs' hold step changing over 1 ns (TbParams.input_transition_time_s), centred
    7.525 ns into the 10 ns period (the hold from the clock's falling crossing, 5.075 ns), into a
    switch that holds a feedthrough of 1e-3 and leaks nothing. The droop is read from 6.3 ns,
    halfway between the fall and the step, to half a clock edge before the change starts (7.525 -
    0.5 - 0.025 = 7.0 ns): the output is still there, so the droop reads 0, the pedestal -2 mV and
    the feedthrough 1e-3. Read to a clock edge before the crossing (7.475 ns) it would take in
    4.5 mV of the change, 4.5 uV on the output over 1.175 ns: 3.8 kV/s. The track step keeps its
    clock edge: tau 200 ps."""
    slow = replace(LEVEL_TB, input_transition_time_s=1e-9)
    hold = analyze_hold([level_run(slow, tau_rise_s=100e-12, tau_fall_s=100e-12, pedestal_v=-2e-3, feedthrough=1e-3)])
    assert hold.droop_v_per_s[0] == pytest.approx(0.0, abs=1.0)
    assert hold.pedestal_v[0] == pytest.approx(-2e-3, abs=1e-6)
    assert hold.feedthrough[0] == pytest.approx(1e-3, rel=1e-3)
    track = analyze_track([level_run(slow, tau_rise_s=200e-12, tau_fall_s=200e-12)])
    assert track.tau_s[0] == pytest.approx(200e-12, rel=0.01)


def _with_gate(run: Meas, settles_s: float, *, low: float = 0.5, high: float = 1.1) -> Meas:
    """``run`` with a boosted gate saved: ``low`` above the input for ``settles_s`` from each
    track phase's start (never where NaN: it ramps from ``low`` to ``high`` over the whole phase),
    then ``high`` above it; 0 V while holding."""
    tb = run.param
    period, high_s, edge = float(tb.clock_period_s), float(tb.clock_high_time_s), float(tb.clock_transition_time_s)
    phase = np.mod(run.time_s, period)
    tracking = (phase >= edge / 2) & (phase < edge + high_s + edge / 2)
    ramp = low + (high - low) * np.clip((phase - edge / 2) / (edge + high_s), 0.0, 1.0)
    drive = ramp if math.isnan(settles_s) else np.where(phase - edge / 2 < settles_s, low, high)
    return replace(run, v={**run.v, "gate": np.where(tracking, run.v["vin"] + drive, 0.0)})


def test_a_window_that_reads_the_gate_drives_own_settling_gives_no_time_constant() -> None:
    """A 100 ps switch whose gate drive settles 650 ps after the input's step in mid-track, and a
    tail of 5 % of the 10 mV step on the output falling with 700 ps (the gate's settling coupled
    through its overlap). At 650 ps the switch's own error is e^-6.5 of its peak, but with the tail
    the error is 0.05 e^(-650/700) = 0.0197 of it, above e^-4 = 0.0183: the window is read, and it
    falls with about 700 ps, more than twice the first e-fold (about 100 ps): NaN, not 700 ps."""
    period, high = float(LEVEL_TB.clock_period_s), float(LEVEL_TB.clock_high_time_s)
    edge = float(LEVEL_TB.clock_transition_time_s)
    ended = edge + high / 2 + edge / 2  # the mid-track step's end, into the period
    # the gate drive switches to its settled value settles_s + edge / 2 into the period (_with_gate)
    run = _with_gate(level_run(LEVEL_TB, tau_rise_s=100e-12, tau_fall_s=100e-12), ended + 0.65e-9 - edge / 2)
    phase = np.mod(run.time_s, period)
    after = (phase >= ended) & (phase < edge + high)
    level = np.interp(run.time_s - phase + edge + high, run.time_s, run.v["vin"])
    toward = np.sign(run.v["vout"] - level)
    tail = np.where(after, 0.05 * 0.01 * np.exp(-(phase - ended) / 700e-12), 0.0)
    track = analyze_track([replace(run, v={**run.v, "vout": run.v["vout"] + toward * tail})])
    assert math.isnan(track.tau_s[0]) and math.isnan(track.ron_ohm[0])


def test_the_time_constant_waits_for_the_gate_drive_to_settle() -> None:
    """A bootstrap whose gate stands 0.5 V above its input for the first 600 ps of each track phase
    and 1.1 V from then on, the output settling with 300 ps before and 100 ps after (the switch
    closes on a 100 mV step): the on switch's time constant is the settled 100 ps, R_on = 100 ohm,
    where the error's 1/e and 1/e^2 points (300 ps and 600 ps: neither after the gate settles) are
    300 ps apart, which a gate that settles at once reads."""
    tb = TbParams(input_step_v=0.1, periods=4)
    run = rc_run(tb, tau_s=300e-12)
    time_s, output = run.time_s, run.v["vout"].copy()
    for k in range(tb.periods):
        start, change = k * tb.clock_period_s, k * tb.clock_period_s + 600e-12
        after = (time_s >= change) & (time_s < start + tb.clock_high_time_s)
        level = run.v["vin"][after][0]
        left = float(np.interp(change, time_s, output)) - level
        output[after] = level + left * np.exp(-(time_s[after] - change) / 100e-12)
    two_rates = replace(run, v={**run.v, "vout": output})
    settled = analyze_track([_with_gate(two_rates, 600e-12)])
    assert settled.tau_s[0] == pytest.approx(100e-12, abs=2e-12)
    assert settled.ron_ohm[0] == pytest.approx(100.0, rel=0.02)
    at_once = analyze_track([_with_gate(two_rates, 0.0)])
    assert at_once.tau_s[0] == pytest.approx(300e-12, abs=3e-12)


def test_an_output_settled_before_its_gate_drive_gives_no_time_constant() -> None:
    """A switch whose output settles with 50 ps while its gate drive takes 600 ps to reach its
    value: by then the error is e^-12 of its largest, under e^-4, and what is left of it says
    nothing of the switch: no time constant. With the gate drive there after 150 ps (e^-3) it is
    read from there: 50 ps."""
    tb = TbParams(input_step_v=0.1, periods=4)
    run = rc_run(tb, tau_s=50e-12)
    late = analyze_track([_with_gate(run, 600e-12)])
    assert math.isnan(late.tau_s[0]) and math.isnan(late.ron_ohm[0])
    assert analyze_track([_with_gate(run, 150e-12)]).tau_s[0] == pytest.approx(50e-12, abs=2e-12)


def test_a_gate_drive_that_never_settles_gives_no_time_constant() -> None:
    """A gate still rising as the clock starts to fall (a ramp over the whole phase from 0.5 V to
    1.1 V: 2 % of its end value is reached only in the last 4 % of it): no time constant, no on-resistance, though the
    output itself settles (tau 200 ps)."""
    tb = TbParams(input_step_v=0.1, periods=4)
    track = analyze_track([_with_gate(rc_run(tb, tau_s=200e-12), math.nan)])
    assert math.isnan(track.tau_s[0]) and math.isnan(track.ron_ohm[0]) and math.isnan(track.bandwidth_hz[0])
    assert track.track_error_v[0] < 1e-6


def test_the_full_scale_step_is_the_converters_own_worst_case(monkeypatch: pytest.MonkeyPatch) -> None:
    """flow.adc's converter: 10 MS/s (a 100 ns period, 12.5 ns of it tracking), 0.7 V common mode
    and +-0.47 V a side at full scale, of 1.2 V. The step: 0.94 V (0.23 V to 1.17 V) about 0.7 V in
    mid-hold, over 2 / (pi f_s) = 63.66 ns, so its slope, 0.94 V / 63.66 ns = 1.4765e7 V/s, is a
    full-scale sine's at Nyquist, 2 pi x 5 MHz x 0.47 V; at the highest supply the same, 1.1 times
    as large (1.32 V: 0.77 V, 1.034 V). The level runs' 10 mV hold steps change no faster: over
    0.01 V / 1.4765e7 V/s = 0.6773 ns (vin_top's 5 mV step over the same time, at half the slope).
    Every run saves every transistor's values. 26 runs."""
    monkeypatch.setattr(runs.importlib, "import_module", lambda name: SimpleNamespace(install=_Install()))
    benches = runs.testbenches("tsmc65", Params())
    assert len(benches) == 26
    step = benches["acquire"]
    assert (step.vdd, step.input_voltage, step.input_step_v) == pytest.approx((1.2, 0.7, 0.94))
    assert (step.clock_period_s, step.clock_high_time_s) == (ADC_PERIOD_S, ADC_TRACK_S) == (100e-9, 12.5e-9)
    assert step.input_transition_time_s == pytest.approx(63.662e-9, rel=1e-4)
    assert step.input_step_v / step.input_transition_time_s == pytest.approx(2 * math.pi * 5e6 * 0.47, rel=1e-4)
    assert step.oppoint and step.track_step_v == 0.0
    highest = benches["acquire_110"]
    assert (highest.vdd, highest.input_voltage, highest.input_step_v) == pytest.approx((1.32, 0.77, 1.034))
    assert highest.input_transition_time_s == step.input_transition_time_s and highest.oppoint
    # the level, supply and corner runs step a 120th of the supply in mid-track and in mid-hold,
    # tracking 10 ns (5 ns for the gate drive to settle, 5 ns to read the time constant over) of 15 ns
    for name in ("vin_1", "vin_6", "supply_90", "supply_110", "slow", "fast", "hot", "skew"):
        assert benches[name].track_step_v == benches[name].input_step_v == pytest.approx(0.01)
        assert (benches[name].clock_high_time_s, benches[name].clock_period_s) == pytest.approx((10e-9, 15e-9))
        assert benches[name].input_transition_time_s == pytest.approx(0.6773e-9, rel=1e-4)
    assert all(bench.oppoint for bench in benches.values())
    # the highest level, 1.195 V, steps half as far: its input reaches the 1.2 V supply and no further
    top = benches["vin_top"]
    assert (top.input_voltage, top.input_step_v, top.track_step_v) == pytest.approx((1.195, 0.005, 0.005))
    assert top.input_voltage + top.track_step_v == pytest.approx(top.vdd)
    assert all(tb.input_voltage - tb.track_step_v > 0 for tb in benches.values())
    for name in ("droop", "droop_hot", "sine_1", "sine_15", "dac_low", "dac_cm"):
        assert benches[name].track_step_v == benches[name].input_step_v == 0.0


def test_the_acquisition_band_is_half_an_lsb_of_the_step() -> None:
    """[Razavi-ADC] Eq. (3.81), (3.82), p. 54: an output settling over V_FS is within V_FS / 2^(N+1)
    after t_acq = R C ln 2^(N+1), whatever V_FS and the supply. An ideal switch of 200 ps closing
    at the clock's mid-supply crossing, stepping 0.5 V or 0.94 V at a 1.2 V supply: 200 ps x 11,
    13 and 15 x ln 2 = 1.525, 1.802 and 2.079 ns at 10, 12 and 14 bits, both steps alike."""
    tb = TbParams(input_voltage=0.6, clock_period_s=ADC_PERIOD_S, clock_high_time_s=ADC_TRACK_S, periods=4)
    expected = [200e-12 * (bits + 1) * math.log(2) for bits in (10, 12, 14)]
    for step in (0.5, 0.94):
        found = analyze_acquisition([ideal_run(replace(tb, input_step_v=step), pedestal_v=0.0)])
        assert list(found.bits) == [10, 12, 14] and found.step_v[0] == step
        assert found.acquisition_s[0] == pytest.approx(expected, rel=5e-3)


def test_the_droop_is_read_once_the_holds_first_half_has_passed() -> None:
    """The droop's window is the third quarter of the hold. A held output falling 1e3 V/s with a
    1 mV transient that dies with 4 ns from each clock fall (a kicked gate relaxing): at the
    middle of the ADC's 87.4 ns hold the transient is 1 mV x exp(-43.7 / 4) = 18 nV, which over
    the 21.8 ns window adds under 1 V/s; from a quarter into the hold it would still be
    1 mV x exp(-21.9 / 4) = 4 uV, a tenth of the droop over the hold's middle half."""
    tb = TbParams(input_step_v=0.0, clock_period_s=ADC_PERIOD_S, clock_high_time_s=ADC_TRACK_S, periods=3)
    run = ideal_run(tb, droop_v_per_s=-1e3)
    since_fall = np.mod(run.time_s - (tb.clock_transition_time_s * 1.5 + tb.clock_high_time_s), tb.clock_period_s)
    relaxing = replace(run, v={**run.v, "vout": run.v["vout"] + 1e-3 * np.exp(-since_fall / 4e-9)})
    assert analyze_droop([relaxing]).droop_v_per_s[0] == pytest.approx(-1e3, rel=2e-3)


def test_a_feedthrough_under_what_its_run_resolves_is_reported_as_the_floor() -> None:
    """An ideal sampler's held output is a straight line before the input steps: its floor is
    nothing and its feedthrough, 1e-3, is -60 dB. A held output that strays 2 uV from that line
    before a 0.1 V step resolves no ratio under 2e-5 (-94 dB): a feedthrough of 1e-6 (-120 dB)
    is then reported as the floor, one of 1e-3 as it is."""
    hold = analyze_hold([rc_run(TB)])
    assert hold.feedthrough_floor is not None and hold.feedthrough_floor[0] < 1e-9
    track = analyze_track([rc_run(TB)])
    assert metrics(track=track, hold=hold, supply=track)["feedthrough_db"] == pytest.approx(-60.0, abs=1e-3)
    # a 2 uV bump on the held output, 0.2 ns wide, three quarters of the way from the opening to the step
    run = rc_run(TB, feedthrough=1e-6)
    period, high = TB.clock_period_s, TB.clock_high_time_s
    phase = np.mod(run.time_s, period)
    bump = 2e-6 * np.clip(1 - np.abs(phase - (high + 0.75 * (period - high) / 2)) / 0.1e-9, 0.0, None)
    strayed = analyze_hold([replace(run, v={**run.v, "vout": run.v["vout"] + bump})])
    assert strayed.feedthrough[0] == pytest.approx(1e-6, rel=1e-3)
    assert strayed.feedthrough_floor is not None and strayed.feedthrough_floor[0] == pytest.approx(2e-5, rel=1e-2)
    values = metrics(track=track, hold=strayed, supply=track)
    assert values["feedthrough_db"] == values["feedthrough_floor_db"] == pytest.approx(20 * math.log10(2e-5), abs=0.1)
    resolved = replace(strayed, feedthrough=np.asarray([1e-3]))
    assert metrics(track=track, hold=resolved, supply=track)["feedthrough_db"] == pytest.approx(-60.0, abs=1e-6)
