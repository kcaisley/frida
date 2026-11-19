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
from .analysis import analyze_droop, analyze_energy, analyze_hold, analyze_sine, analyze_track, metrics
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
    # half edge before the switch closes adds nothing: the ideal switch closes at mid-supply)
    assert result.metrics["acquisition_12b_s"] == pytest.approx(200e-12 * math.log(1.0 / (1.2 / 2**13)), rel=0.02)
    # the model of the same RC and pedestal predicts every held sample of an ideal switch
    assert result.metrics["model_error_v"] < 1e-4
    # no device values saved by the synthetic runs: no stress figures
    assert math.isnan(result.metrics["terminal_max_v"])
    # 1 uA from 1.2 V over a 10 ns period, and each clock's 10 fF charged from 1.2 V once
    assert result.metrics["energy_per_cycle_j"] == pytest.approx(1.2 * (1e-6 * 10e-9 + 2 * 10e-15 * 1.2), rel=1e-3)
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


def test_the_energy_counts_each_clocks_charge_once_though_its_source_takes_it_back() -> None:
    """[Baker] Eq. (11.15), p. 355: V_DD I_avg, the current drawn from V_DD. A clock source that
    charges 10 fF and takes it back nets nothing, but its driver draws C V_DD from V_DD each
    period: 1.2 V x (1 uA x 10 ns + 2 x 10 fF x 1.2 V)."""
    energy = analyze_energy([ideal_run(TbParams(input_step_v=0.0))])
    assert energy.energy_per_cycle_j[0] == pytest.approx(1.2 * (1e-6 * 10e-9 + 2 * 10e-15 * 1.2), rel=1e-3)


def test_the_energy_counts_the_supplys_net_charge() -> None:
    """[Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, the supply's average current. A supply that
    delivers 1 uA and takes back 10 fF x 1.2 V on each clock fall nets 1 uA x 10 ns less that
    charge a period, the clocks' charge counted as before."""
    run = ideal_run(TbParams(input_step_v=0.0))
    returned = CLOCK_LOAD_F * np.minimum(np.gradient(run.v["clk"], run.time_s), 0.0)
    energy = analyze_energy([replace(run, i={**run.i, "vdd": run.i["vdd"] + returned})])
    net_c = 1e-6 * 10e-9 - CLOCK_LOAD_F * 1.2
    assert energy.energy_per_cycle_j[0] == pytest.approx(1.2 * (net_c + 2 * CLOCK_LOAD_F * 1.2), rel=1e-3)


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
    # the runs that read a hold's leakage at a gmin below it, the others at Spectre's own
    leaky = {"droop", "droop_hot", "dac_low", "dac_cm"}
    assert {name for name, tb in benches.items() if tb.gmin_s == LEAKAGE_GMIN_S} == leaky
    assert all(tb.gmin_s is None for name, tb in benches.items() if name not in leaky)


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
