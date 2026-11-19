"""Known answers for the sampler's analyses, metrics and behavioral model: synthetic runs of a
switch with a closed-form response on the bench's own timing (``sampler_run``), and hand-built
analysis results, each expected value derived on paper from the closed form, not from the code."""

from __future__ import annotations

import math
from dataclasses import fields, replace
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from scipy import constants

from flow.pipeline import Meas, MeasInfo

from . import model as model_module
from .analysis import analyze_hold, analyze_track, metrics
from .model import Model
from .params import NOMINAL_VIN, VIN_SWEEP, Params, SwitchType, TbParams
from .types import AnalysisHold, AnalysisTrack

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 11, 18, tzinfo=UTC))


def sampler_run(
    tb: TbParams,
    *,
    tau_s: float,
    tau_fall_s: float | None = None,
    pedestal_v: float = 0.0,
    droop_v_per_s: float = 0.0,
    feedthrough: float = 0.0,
    dt_s: float = 1e-12,
    shift_s: float = 0.0,
) -> Meas:
    """A run of ``tb`` as the bench drives it (sim.testbench's two pulse sources: the clock rising
    at each period's start over ``clock_transition_time_s``, high for ``clock_high_time_s``; the
    input low for a period, high for the next, each change in mid-hold) into a switch that closes
    and opens at the clock's mid-supply crossings. Closed, the output relaxes to the input with
    ``tau_s`` (``tau_fall_s`` on a falling step); as it opens it jumps by ``pedestal_v``; open, it
    drifts at ``droop_v_per_s`` and follows ``feedthrough`` of the input's change since it opened.
    Before the first closing it holds the input's first level. A sample every ``dt_s``, the whole
    run moved later by ``shift_s``."""

    period, high, edge = float(tb.clock_period_s), float(tb.clock_high_time_s), float(tb.clock_transition_time_s)
    vdd, vin, step = float(tb.vdd), float(tb.input_voltage), float(tb.input_step_v)
    tau_fall_s = tau_s if tau_fall_s is None else tau_fall_s
    time_s = np.arange(0.0, tb.stop_s + dt_s / 2, dt_s)
    starts = np.arange(tb.periods + 1) * period
    clock_knots = np.stack([starts, starts + edge, starts + edge + high, starts + 2 * edge + high], axis=1).ravel()
    clock = np.interp(time_s, clock_knots, np.tile([0.0, vdd, vdd, 0.0], tb.periods + 1))
    low, high_v = vin - step / 2, vin + step / 2
    first = high + (period - high) / 2
    changes = first + 2 * period * np.arange(tb.periods // 2 + 2)
    data_knots = np.r_[
        0.0, np.stack([changes, changes + edge, changes + edge + period, changes + 2 * edge + period], axis=1).ravel()
    ]
    data_levels = np.r_[low, np.tile([low, high_v, high_v, low], len(changes))]
    data = np.interp(time_s, data_knots, data_levels)

    def data_at(at: float) -> float:
        return float(np.interp(at, data_knots, data_levels))

    output = np.full_like(time_s, low)
    held, opened, opened_data = low, None, low
    for k in range(tb.periods + 1):
        closes, opens = k * period + edge / 2, k * period + edge + high + edge / 2
        if opened is not None:
            hold = (time_s >= opened) & (time_s < closes)
            output[hold] = held + droop_v_per_s * (time_s[hold] - opened) + feedthrough * (data[hold] - opened_data)
            start = held + droop_v_per_s * (closes - opened) + feedthrough * (data_at(closes) - opened_data)
        else:
            start = held
        level = data_at(closes)
        tau = tau_s if level >= start else tau_fall_s
        track = (time_s >= closes) & (time_s < opens)
        output[track] = level + (start - level) * np.exp(-(time_s[track] - closes) / tau)
        held = level + (start - level) * math.exp(-(opens - closes) / tau) + pedestal_v
        opened, opened_data = opens, data_at(opens)
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s + shift_s,
        v={"clk": clock, "clk_b": vdd - clock, "vin": data, "vout": output},
        i={"vdd": np.zeros_like(time_s)},
    )


# the bench every switch is characterized on (params.py), at FRIDA-1's 1.2 V and mid-supply input
TB = TbParams(vdd=1.2, input_voltage=0.6, input_step_v=0.1)
STEP_V = 0.1
HIGH_S = 5e-9
EDGE_S = 50e-12


def track_names() -> tuple[str, str]:
    """AnalysisTrack's names for tau and R_on, in whichever spelling it gives them: the notation's
    ``tau_s`` and ``ron_ohm``, or ``time_constant_s`` and ``on_resistance_ohm``."""
    names = {field.name for field in fields(AnalysisTrack)}
    return (
        "tau_s" if "tau_s" in names else "time_constant_s",
        "ron_ohm" if "ron_ohm" in names else "on_resistance_ohm",
    )


def tau_of(track: AnalysisTrack) -> np.ndarray:
    return getattr(track, track_names()[0])


def ron_of(track: AnalysisTrack) -> np.ndarray:
    return getattr(track, track_names()[1])


def track_result(
    *, vdd_v: np.ndarray, vin_v: np.ndarray, ron_ohm: np.ndarray, track_error_v: np.ndarray, cload_f: float = 1e-12
) -> AnalysisTrack:
    """An AnalysisTrack of the given on-resistances into ``cload_f``: tau = R C, f_-3dB = 1 / (2 pi tau)."""
    tau, ron = track_names()
    return AnalysisTrack(
        group=None,
        index=None,
        dut=Params(),
        vdd_v=vdd_v,
        vin_v=vin_v,
        bandwidth_hz=1 / (2 * math.pi * ron_ohm * cload_f),
        track_error_v=track_error_v,
        **{tau: ron_ohm * cload_f, ron: ron_ohm},
    )


# ---- analyze_track


def test_an_rc_step_gives_its_time_constant_resistance_and_bandwidth() -> None:
    """tau = 200 ps into 1 pF: R_on = tau / C = 200 ohm, f_-3dB = 1 / (2 pi tau) = 795.8 MHz."""
    # [Razavi-Analog] Eq. (13.31), p. 552: tau = R_on C_H, the sampler's time constant
    # [Razavi-ADC] Eq. (3.26), p. 29: an RC sampler's attenuation 1/sqrt(R_on^2 C_1^2 w^2 + 1), -3 dB at w = 1/(R_on C_1)
    track = analyze_track([sampler_run(TB, tau_s=200e-12)])
    assert tau_of(track)[0] == pytest.approx(200e-12, rel=1e-3)
    assert ron_of(track)[0] == pytest.approx(200.0, rel=1e-3)
    assert track.bandwidth_hz[0] == pytest.approx(1 / (2 * math.pi * 200e-12), rel=1e-3)
    assert track.vdd_v[0] == 1.2 and track.vin_v[0] == 0.6


def test_the_resistance_is_the_time_constant_over_the_bench_load() -> None:
    """The same 200 ps step read into 2 pF is 100 ohm: R_on = tau / C_L."""
    track = analyze_track([sampler_run(replace(TB, cload=2e-12), tau_s=200e-12)])
    assert ron_of(track)[0] == pytest.approx(100.0, rel=1e-3)


def test_the_track_error_is_the_residue_left_at_the_end_of_tracking() -> None:
    """tau = 1 ns, a 0.1 V step alternating up and down, the switch closed T + t_r = 5.05 ns a
    period: each phase starts from s / (1 + a) of error (a = exp(-(T + t_r) / tau), the residue the
    last phase left counted against the new step), so at t_r before the clock's fall, T after it
    closed, the output lags the input by s exp(-T / tau) / (1 + a) = 0.6695 mV, below it on an up
    step and above it on a down step: that magnitude."""
    # [Razavi-ADC] Sec. 3.9.1, p. 53: the error |V_in - V_out| left when acquisition ends
    a = math.exp(-(HIGH_S + EDGE_S) / 1e-9)
    expected = STEP_V * math.exp(-HIGH_S / 1e-9) / (1 + a)
    track = analyze_track([sampler_run(TB, tau_s=1e-9)])
    assert abs(track.track_error_v[0]) == pytest.approx(expected, rel=1e-3)


def test_the_track_error_does_not_vanish_with_an_even_number_of_track_phases() -> None:
    """Five periods (four measured track phases, two up and two down): the residue is still
    s exp(-T / tau) / (1 + a) = 0.6695 mV in magnitude on every phase."""
    a = math.exp(-(HIGH_S + EDGE_S) / 1e-9)
    expected = STEP_V * math.exp(-HIGH_S / 1e-9) / (1 + a)
    track = analyze_track([sampler_run(replace(TB, periods=5), tau_s=1e-9)])
    assert abs(track.track_error_v[0]) == pytest.approx(expected, rel=1e-3)


def test_a_switch_too_slow_to_reach_two_time_constants_has_no_time_constant() -> None:
    """tau = 3 ns: 1/e^2 of the error is 6 ns after closing, past the 5.05 ns the switch is closed."""
    track = analyze_track([sampler_run(TB, tau_s=3e-9)])
    assert math.isnan(tau_of(track)[0]) and math.isnan(ron_of(track)[0])
    assert math.isnan(track.bandwidth_hz[0])


def test_each_run_is_one_point_in_order() -> None:
    """Three runs at 0.3, 0.6 and 0.9 V with 100, 200 and 400 ps: one point each, in that order."""
    runs = [
        sampler_run(replace(TB, input_voltage=vin), tau_s=tau)
        for vin, tau in ((0.3, 100e-12), (0.6, 200e-12), (0.9, 400e-12))
    ]
    track = analyze_track(runs)
    np.testing.assert_allclose(track.vin_v, [0.3, 0.6, 0.9])
    np.testing.assert_allclose(tau_of(track), [100e-12, 200e-12, 400e-12], rtol=1e-3)


# ---- analyze_hold


def test_a_known_pedestal_droop_and_feedthrough_are_recovered() -> None:
    """A settled switch (tau = 100 ps) that leaves -2 mV as it opens and follows 1e-3 of the input
    while open: pedestal -2 mV, feedthrough 1e-3 (the output's change over the input's), no droop."""
    # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal, the voltage error the opening switch leaves on C_H
    # [Pelgrom] Sec. 8.2.3, p. 387: hold-mode feedthrough, the input's transfer to the held output
    hold = analyze_hold([sampler_run(TB, tau_s=100e-12, pedestal_v=-2e-3, feedthrough=1e-3)])
    assert hold.pedestal_v[0] == pytest.approx(-2e-3, abs=1e-9)
    assert hold.feedthrough[0] == pytest.approx(1e-3, rel=1e-6)
    assert hold.droop_v_per_s[0] == pytest.approx(0.0, abs=1e-3)
    assert hold.vdd_v[0] == 1.2 and hold.vin_v[0] == 0.6


def test_a_linear_droop_is_its_slope() -> None:
    """A held output falling 10 uV a nanosecond (a leak of 10 nA from 1 pF) droops -1e4 V/s."""
    # [Pelgrom] Eq. (8.3), p. 387: V_droop = -I_leak T_hold / C_hold, a linear fall over the hold
    hold = analyze_hold([sampler_run(TB, tau_s=100e-12, droop_v_per_s=-1e4)])
    assert hold.droop_v_per_s[0] == pytest.approx(-1e4, rel=1e-6)


def test_the_pedestal_is_the_step_at_the_opening_whatever_the_droop() -> None:
    """-2 mV left at the opening and a droop of -1e5 V/s: the pedestal is the -2 mV step; read
    1.225 to 1.25 ns into the hold (halfway to the input's step) without the droop taken back, it
    reads about -2.12 mV."""
    hold = analyze_hold([sampler_run(TB, tau_s=100e-12, pedestal_v=-2e-3, droop_v_per_s=-1e5)])
    assert hold.pedestal_v[0] == pytest.approx(-2e-3, abs=1e-6)


def test_the_feedthrough_is_the_inputs_share_whatever_the_droop() -> None:
    """Feedthrough 1e-3 and a droop of 1e4 V/s over seven periods (five measured holds): the
    feedthrough is 1e-3; the droop's 25 uV over the 2.5 ns between the two readings, over the
    0.1 V step, would add +-2.5e-4 by the step's sign."""
    hold = analyze_hold([sampler_run(replace(TB, periods=7), tau_s=100e-12, feedthrough=1e-3, droop_v_per_s=1e4)])
    assert hold.feedthrough[0] == pytest.approx(1e-3, rel=1e-3)


def test_a_run_without_an_input_step_has_no_hold_figures() -> None:
    """With no input step there is no step to hold against: NaN, not a number."""
    hold = analyze_hold([sampler_run(replace(TB, input_step_v=0.0), tau_s=100e-12)])
    assert all(math.isnan(value[0]) for value in (hold.pedestal_v, hold.droop_v_per_s, hold.feedthrough))


# ---- metrics


def _results(
    ron_ohm: np.ndarray, pedestal_v: np.ndarray, *, feedthrough: float = 1e-3, vdd: float = 1.2
) -> tuple[AnalysisTrack, AnalysisHold]:
    """Analysis results over VIN_SWEEP at ``vdd``: tau = R 1 pF, the bandwidth from it."""
    vin = np.asarray([fraction * vdd for fraction in VIN_SWEEP])
    rows = {"group": None, "index": None, "dut": Params(), "vdd_v": np.full(len(vin), vdd), "vin_v": vin}
    track = track_result(
        vdd_v=rows["vdd_v"], vin_v=vin, ron_ohm=ron_ohm, track_error_v=np.linspace(-1e-6, 1e-6, len(vin))
    )
    hold = AnalysisHold(
        **rows,
        pedestal_v=pedestal_v,
        droop_v_per_s=np.full(len(vin), -50.0),
        feedthrough=np.full(len(vin), feedthrough),
    )
    return track, hold


def test_the_metrics_read_the_mid_supply_point() -> None:
    """Every nominal metric is the value at V_in = V_DD / 2 (the sixth of eleven points); the
    feedthrough 1e-3 is -60 dB; the bandwidth 1/(2 pi 350 ps)."""
    ron = np.linspace(100.0, 600.0, len(VIN_SWEEP))  # 350 ohm at mid-supply
    pedestal = np.linspace(-1e-3, 1e-3, len(VIN_SWEEP))  # 0 at mid-supply
    track, hold = _results(ron, pedestal)
    values = metrics(track=track, hold=hold, supply=track)
    nominal = VIN_SWEEP.index(NOMINAL_VIN)
    assert track.vin_v[nominal] == pytest.approx(0.6)
    assert values["ron_ohm"] == pytest.approx(350.0)
    assert values["bandwidth_hz"] == pytest.approx(1 / (2 * math.pi * 350e-12))
    assert values["track_error_v"] == pytest.approx(0.0, abs=1e-15)
    assert values["pedestal_v"] == pytest.approx(0.0, abs=1e-15)
    assert values["feedthrough_db"] == pytest.approx(-60.0)
    assert values["ron_max_ohm"] == pytest.approx(600.0)
    assert values["ron_max_supply_ohm"] == pytest.approx(600.0)
    assert values["pedestal_max_v"] == pytest.approx(1e-3)
    assert values["input_range_v"] == pytest.approx(10 / 12 * 1.2)


def test_a_negative_feedthrough_is_its_magnitude_in_db() -> None:
    """A held output moving against the input by 1e-2 of it is -40 dB."""
    track, hold = _results(np.full(len(VIN_SWEEP), 200.0), np.zeros(len(VIN_SWEEP)), feedthrough=-1e-2)
    assert metrics(track=track, hold=hold, supply=track)["feedthrough_db"] == pytest.approx(-40.0)


def test_the_largest_resistance_over_the_supply_is_the_supplys() -> None:
    """The supply's runs (90, 100, 110 %) at 500, 350 and 250 ohm: 500 ohm, whatever the input runs say."""
    track, hold = _results(np.full(len(VIN_SWEEP), 200.0), np.zeros(len(VIN_SWEEP)))
    supply = track_result(
        vdd_v=np.asarray([1.08, 1.2, 1.32]),
        vin_v=np.asarray([0.54, 0.6, 0.66]),
        ron_ohm=np.asarray([500.0, 350.0, 250.0]),
        track_error_v=np.zeros(3),
    )
    assert metrics(track=track, hold=hold, supply=supply)["ron_max_supply_ohm"] == pytest.approx(500.0)


def test_no_settled_point_has_no_range_and_no_resistance() -> None:
    track, hold = _results(np.full(len(VIN_SWEEP), np.nan), np.zeros(len(VIN_SWEEP)))
    values = metrics(track=track, hold=hold, supply=track)
    assert values["input_range_v"] == 0.0
    assert math.isnan(values["ron_max_ohm"]) and math.isnan(values["ron_ohm"])


def test_the_input_range_stops_at_a_point_that_never_settles() -> None:
    """Settled at 1/12 and 2/12 of the supply, not at 3/12, settled again from 4/12 to 11/12: the
    range the switch settles over is 4/12 to 11/12 of 1.2 V, 0.7 V (it holds mid-supply); not the
    1.0 V from the lowest to the highest settled point across the gap."""
    ron = np.full(len(VIN_SWEEP), 300.0)
    ron[2] = np.nan
    track, hold = _results(ron, np.zeros(len(VIN_SWEEP)))
    assert metrics(track=track, hold=hold, supply=track)["input_range_v"] == pytest.approx(0.7)


def test_the_largest_pedestal_is_over_settled_points_only() -> None:
    """metrics' docstring: the largest pedestal "where a point settled". The top two inputs never
    settle (an NMOS switch off there) and hold a 50 mV step that is no pedestal; every settled
    point leaves 1 mV: the largest is 1 mV."""
    ron = np.full(len(VIN_SWEEP), 300.0)
    ron[-2:] = np.nan
    pedestal = np.full(len(VIN_SWEEP), 1e-3)
    pedestal[-2:] = 50e-3
    track, hold = _results(ron, pedestal)
    assert metrics(track=track, hold=hold, supply=track)["pedestal_max_v"] == pytest.approx(1e-3)


def test_the_droop_metric_is_named_as_the_notation_names_it() -> None:
    """docs/references.md, Sampling and clocks: droop is ``droop_v_per_s`` (a quotient is
    ``_<u>_per_<u>``); ``droop_v_s`` reads as volt-seconds."""
    track, hold = _results(np.full(len(VIN_SWEEP), 200.0), np.zeros(len(VIN_SWEEP)))
    values = metrics(track=track, hold=hold, supply=track)
    assert "droop_v_per_s" in values and "droop_v_s" not in values
    assert values["droop_v_per_s"] == pytest.approx(-50.0)


def test_the_track_fields_are_named_as_the_notation_names_them() -> None:
    """docs/references.md: tau is ``tau_s`` and R_on ``ron_ohm`` (the metrics already say ``ron_ohm``)."""
    names = {field.name for field in fields(AnalysisTrack)}
    assert {"tau_s", "ron_ohm"} <= names
    assert not {"time_constant_s", "on_resistance_ohm"} & names


# ---- the behavioral model


def test_the_differential_kt_over_c_of_two_1_pf_plates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each 1 pF plate at 300 K holds sqrt(kT/C) = 64.4 uV rms; the two, uncorrelated, 2kT/C
    differentially: 91.0 uV."""
    # [Razavi-ADC] Eq. (3.55), p. 39: V_n,out,rms = sqrt(kT/C_1), 64 uV at 1 pF and 300 K
    # [Razavi-ADC] Sec. 3.6, p. 41: the two sides' noise uncorrelated, 2kT/C_1 in V_out1 - V_out2
    behavioral = characterized_model(monkeypatch, [200.0] * len(VIN_SWEEP), [0.0] * len(VIN_SWEEP)).behavioral(
        load_f=1e-12
    )
    assert behavioral.noise_v == pytest.approx(math.sqrt(2 * constants.k * 300.0 / 1e-12), rel=1e-9)
    assert behavioral.noise_v == pytest.approx(91.0e-6, rel=1e-3)


def test_each_side_holds_kt_over_c_of_its_plate() -> None:
    """200 000 samples of two 1 pF plates, an ideal switch, no slope: each side's spread is
    sqrt(kT/C) = 64.4 uV (to 1 %, the estimate's own error 0.16 %), the two uncorrelated, so their
    difference sqrt(2kT/C)."""
    count = 200_000
    switch = Model.Behavioral(
        noise_v=math.sqrt(2 * constants.k * 300.0 / 1e-12), n_conductance_s_per_v=0.0, p_conductance_s_per_v=0.0
    )
    held = Model.sample(
        Params(),
        switch,
        {"p": np.full(count, 0.6), "n": np.full(count, 0.6)},
        {"p": np.zeros(count), "n": np.zeros(count)},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(1),
    )
    side = math.sqrt(constants.k * 300.0 / 1e-12)
    assert np.std(held["p"]) == pytest.approx(side, rel=0.01)
    assert np.std(held["n"]) == pytest.approx(side, rel=0.01)
    assert np.std(held["p"] - held["n"]) == pytest.approx(math.sqrt(2) * side, rel=0.01)


def test_a_ramp_lags_by_the_time_constant() -> None:
    """A 1 V/us ramp through 200 ohm into 1 pF: held 200 ps late, 0.2 mV below the input."""
    # [Razavi-ADC] Eq. (3.26), p. 29: the RC sampler's phase shift tan^-1(R_on C_1 w), a delay of R_on C_1 for R_on C_1 w << 1
    switch = Model.Behavioral(ron_table_v=(0.0, 1.2), ron_table_ohm=(200.0, 200.0))
    held = Model.sample(
        Params(),
        switch,
        {"p": np.asarray([0.6]), "n": np.asarray([0.6])},
        {"p": np.asarray([1e6]), "n": np.asarray([-1e6])},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    assert held["p"][0] == pytest.approx(0.6 - 0.2e-3, abs=1e-12)
    assert held["n"][0] == pytest.approx(0.6 + 0.2e-3, abs=1e-12)


def test_a_transmission_gates_resistance_from_its_triode_conductances() -> None:
    """n = p = 10 mS/V, thresholds 0.35 V, gate at 1.2 V: at 0.6 V both overdrives are 0.25 V, 5 mS,
    200 ohm; at 0.2 V only the NMOS conducts, 10 m (1.2 - 0.2 - 0.35) = 6.5 mS, 153.8 ohm."""
    # [Razavi-Analog] Eq. (2.11), p. 15: R_on = 1 / (mu Cox W/L (V_GS - V_TH))
    switch = Model.Behavioral(n_conductance_s_per_v=10e-3, p_conductance_s_per_v=10e-3)
    resistance = Model.resistance(Params(), switch, np.asarray([0.6, 0.2]), 1.2)
    np.testing.assert_allclose(resistance, [200.0, 1 / 6.5e-3], rtol=1e-12)


def test_a_bootstrapped_switch_keeps_its_resistance_over_the_input() -> None:
    """SwitchType.BOOTSTRAP boosts the gate one supply above the input while tracking: V_GS =
    V_DD = 1.2 V at every input, so n = 10 mS/V gives 1 / (10 m (1.2 - 0.35)) = 117.6 ohm at 0.1,
    0.6 and 1.0 V alike (where a plain NMOS gate at 1.2 V would be off at 1.0 V)."""
    # [Razavi-ADC] Sec. 3.8.1, p. 43: the bootstrapped gate holds V_GS = V_b (V_DD) as V_in swings
    switch = Model.Behavioral(n_conductance_s_per_v=10e-3)
    resistance = Model.resistance(Params(switch_type=SwitchType.BOOTSTRAP), switch, np.asarray([0.1, 0.6, 1.0]), 1.2)
    np.testing.assert_allclose(resistance, 1 / (10e-3 * 0.85), rtol=1e-9)


def _record(ron: list[float | None], pedestal: list[float]) -> dict[str, Any]:
    """A characterization record as Model.of reads it: its plots' JSON (None where a point failed)."""
    vin = [round(fraction * 1.2, 4) for fraction in VIN_SWEEP]
    return {
        "block": "samp",
        "metrics": {"bandwidth_hz": 1e9, "pedestal_v": pedestal[VIN_SWEEP.index(NOMINAL_VIN)]},
        "details": [
            {"name": "ron_vin", "x": vin, "series": {"on-resistance": ron}},
            {"name": "pedestal_vin", "x": vin, "series": {"pedestal": pedestal}},
        ],
    }


def characterized_model(
    monkeypatch: pytest.MonkeyPatch, ron: list[float | None], pedestal: list[float], params: Params | None = None
) -> Model:
    """Model.of on a record of these curves (``_record``), looked up instead of characterized."""
    record = _record(ron, pedestal)
    monkeypatch.setattr(model_module, "characterized", lambda *args, **kwargs: record)
    return Model.of("tsmc65", Params() if params is None else params, simulate=False)


def test_the_model_does_not_track_where_the_characterization_never_settled(monkeypatch: pytest.MonkeyPatch) -> None:
    """An NMOS switch measured 150 to 400 ohm up to 0.7 V and never settling above (tau past half the
    5.05 ns it is closed: R past 2.525 ns / 1 pF = 2525 ohm): at 1.0 V the model's on-resistance
    must be at least that, not the 400 ohm of the last settled point."""
    ron: list[float | None] = [150.0, 170.0, 200.0, 250.0, 300.0, 350.0, 400.0, None, None, None, None]
    found = characterized_model(monkeypatch, ron, [-2e-3] * len(VIN_SWEEP), Params(switch_type=SwitchType.NMOS))
    resistance = Model.resistance(found.params, found.behavioral(load_f=1e-12), np.asarray([1.0]), 1.2)
    assert resistance[0] >= 2525.0


def test_the_model_holds_the_characterized_pedestal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A switch characterized to leave -2 mV at every input holds 0.6 V as 0.598 V on each side
    (the mean of 200 000 samples; their kT/C spread 64 uV, so the mean to 0.2 uV)."""
    found = characterized_model(monkeypatch, [200.0] * len(VIN_SWEEP), [-2e-3] * len(VIN_SWEEP))
    count = 200_000
    held = found.hold(
        {"p": np.full(count, 0.6), "n": np.full(count, 0.6)},
        {"p": np.zeros(count), "n": np.zeros(count)},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(2),
    )
    assert float(np.mean(held["p"])) == pytest.approx(0.598, abs=2e-6)
    assert float(np.mean(held["n"])) == pytest.approx(0.598, abs=2e-6)


def test_each_side_holds_the_kt_over_c_of_its_own_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plates of 1 pF and 4 pF: sqrt(kT/C) = 64.4 uV on the first, 32.2 uV on the second (to 1 %),
    not 40.7 uV each (the kT/C of their 2.5 pF mean)."""
    found = replace(characterized_model(monkeypatch, [200.0] * len(VIN_SWEEP), [0.0] * len(VIN_SWEEP)), jitter_s=0.0)
    count = 200_000
    held = found.hold(
        {"p": np.full(count, 0.6), "n": np.full(count, 0.6)},
        {"p": np.zeros(count), "n": np.zeros(count)},
        load_f={"p": 1e-12, "n": 4e-12},
        gate_v=1.2,
        rng=np.random.default_rng(3),
    )
    assert np.std(held["p"]) == pytest.approx(math.sqrt(constants.k * 300.0 / 1e-12), rel=0.01)
    assert np.std(held["n"]) == pytest.approx(math.sqrt(constants.k * 300.0 / 4e-12), rel=0.01)


def test_the_model_reads_the_characterized_resistance_at_its_input_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    """At each input level the characterization settled at, the model's on-resistance is the one
    measured there; its bandwidth the record's."""
    ron: list[float | None] = [150.0, 170.0, 200.0, 250.0, 300.0, 350.0, 400.0, None, None, None, None]
    found = characterized_model(monkeypatch, ron, [0.0] * len(VIN_SWEEP))
    levels = np.asarray([round(fraction * 1.2, 4) for fraction in VIN_SWEEP[:7]])
    resistance = Model.resistance(found.params, found.behavioral(load_f=1e-12), levels, 1.2)
    np.testing.assert_allclose(resistance, [150.0, 170.0, 200.0, 250.0, 300.0, 350.0, 400.0], rtol=1e-12)
    assert found.bandwidth_hz == 1e9
