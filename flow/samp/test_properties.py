"""Properties of the sampler's analyses, metrics and behavioral model over generated inputs
(Hypothesis): what a measured duration, amplitude or ratio must do when the run is moved, scaled or
repeated, on the closed-form switch of ``test_known_answers.sampler_run``."""

from __future__ import annotations

import math
from dataclasses import fields, replace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy import constants

from .analysis import analyze_hold, analyze_track, metrics
from .model import Model
from .params import VIN_SWEEP, Params, SwitchType
from .test_known_answers import (
    EDGE_S,
    HIGH_S,
    STEP_V,
    TB,
    characterized_model,
    ron_of,
    sampler_run,
    tau_of,
    track_result,
)
from .types import AnalysisHold, AnalysisTrack

# each example simulates nothing but builds a 60 000-point run: fewer examples than the default 100
RUNS = settings(max_examples=30)


def _values(result: AnalysisTrack | AnalysisHold) -> dict[str, np.ndarray]:
    return {
        field.name: getattr(result, field.name)
        for field in fields(result)
        if field.name.endswith(("_s", "_ohm", "_hz", "_v", "_per_s", "feedthrough"))
    }


# ---- analyze_track


@RUNS
@given(tau_s=st.floats(10e-12, 2.4e-9), cload_f=st.floats(0.1e-12, 10e-12))
def test_the_time_constant_is_recovered_and_the_resistance_is_it_over_the_load(tau_s: float, cload_f: float) -> None:
    """Any tau whose 1/e^2 point (2 tau) falls inside the 5.05 ns the switch is closed: tau to 0.5 %,
    R_on = tau / C_L and f_-3dB = 1 / (2 pi tau) exactly from it."""
    track = analyze_track([sampler_run(replace(TB, cload=cload_f), tau_s=tau_s)])
    assert tau_of(track)[0] == pytest.approx(tau_s, rel=5e-3)
    assert ron_of(track)[0] == pytest.approx(tau_of(track)[0] / cload_f, rel=1e-12)
    assert track.bandwidth_hz[0] * 2 * math.pi * tau_of(track)[0] == pytest.approx(1.0, rel=1e-12)


@RUNS
@given(tau_s=st.floats(2.6e-9, 50e-9))
def test_a_time_constant_past_half_the_track_phase_is_not_measured(tau_s: float) -> None:
    """2 tau past the 5.05 ns the switch is closed: the error never reaches 1/e^2, no number."""
    track = analyze_track([sampler_run(TB, tau_s=tau_s)])
    assert math.isnan(tau_of(track)[0]) and math.isnan(ron_of(track)[0])


@RUNS
@given(shift_s=st.floats(0.0, 30e-9))
def test_moving_the_run_later_changes_no_figure(shift_s: float) -> None:
    """Every figure is a duration, a level difference or a ratio: the same run, all of it later by
    any time, gives the same numbers."""
    knobs = {"tau_s": 1e-9, "pedestal_v": -1.5e-3, "droop_v_per_s": -2e3, "feedthrough": 3e-4}
    base, moved = sampler_run(TB, **knobs), sampler_run(TB, **knobs, shift_s=shift_s)
    for analyze in (analyze_track, analyze_hold):
        before, after = _values(analyze([base])), _values(analyze([moved]))
        for name, value in before.items():
            np.testing.assert_allclose(after[name], value, rtol=1e-6, atol=1e-12, err_msg=name)


@RUNS
@given(scale=st.floats(0.25, 2.0))
def test_scaling_every_voltage_scales_the_levels_and_keeps_the_times_and_ratios(scale: float) -> None:
    """Supply, input, step, pedestal and droop all times k: the pedestal, the track error and the
    droop times k; the time constant, the resistance and the feedthrough as they were."""
    knobs = {"tau_s": 1e-9, "feedthrough": 3e-4}
    levels = {"pedestal_v": -1.5e-3, "droop_v_per_s": -2e3}
    tb = replace(TB, vdd=TB.vdd * scale, input_voltage=TB.input_voltage * scale, input_step_v=TB.input_step_v * scale)
    base = sampler_run(TB, **knobs, **levels)
    scaled = sampler_run(tb, **knobs, **{name: value * scale for name, value in levels.items()})
    track, track_k = analyze_track([base]), analyze_track([scaled])
    hold, hold_k = analyze_hold([base]), analyze_hold([scaled])
    assert track_k.track_error_v[0] == pytest.approx(scale * track.track_error_v[0], rel=1e-6)
    assert hold_k.pedestal_v[0] == pytest.approx(scale * hold.pedestal_v[0], rel=1e-6)
    assert hold_k.droop_v_per_s[0] == pytest.approx(scale * hold.droop_v_per_s[0], rel=1e-6)
    assert tau_of(track_k)[0] == pytest.approx(tau_of(track)[0], rel=1e-6)
    assert ron_of(track_k)[0] == pytest.approx(ron_of(track)[0], rel=1e-6)
    assert hold_k.feedthrough[0] == pytest.approx(hold.feedthrough[0], rel=1e-6)


@RUNS
@given(periods=st.integers(4, 9), tau_s=st.floats(0.3e-9, 1e-9))
@pytest.mark.xfail(
    strict=True, reason="samp-1: the track error is a median over alternating step signs: zero for an even count"
)
def test_the_track_errors_magnitude_does_not_depend_on_the_number_of_periods(periods: int, tau_s: float) -> None:
    """The residue s exp(-T / tau) / (1 + exp(-(T + t_r) / tau)) is the same on every track phase
    (up steps below the input, down steps above it, to the first phase's a < 0.7 %): its magnitude
    to 1 % whatever the number of periods."""
    a = math.exp(-(HIGH_S + EDGE_S) / tau_s)
    expected = STEP_V * math.exp(-HIGH_S / tau_s) / (1 + a)
    track = analyze_track([sampler_run(replace(TB, periods=periods), tau_s=tau_s)])
    assert abs(track.track_error_v[0]) == pytest.approx(expected, rel=0.01)


@RUNS
@given(periods=st.integers(4, 9), tau_s=st.floats(100e-12, 300e-12))
@pytest.mark.xfail(
    strict=True, reason="samp-2: tau is a median over up and down steps: which one it reports depends on the count"
)
def test_the_time_constant_does_not_depend_on_the_number_of_periods(periods: int, tau_s: float) -> None:
    """A switch twice as slow on a falling step as on a rising one: one switch, one input level, one
    time constant, the same for any number of periods as for the bench's six."""
    bench = analyze_track([sampler_run(TB, tau_s=tau_s, tau_fall_s=2 * tau_s)])
    other = analyze_track([sampler_run(replace(TB, periods=periods), tau_s=tau_s, tau_fall_s=2 * tau_s)])
    assert tau_of(other)[0] == pytest.approx(tau_of(bench)[0], rel=1e-3)


# ---- analyze_hold


@RUNS
@given(
    pedestal_v=st.floats(-20e-3, 20e-3),
    feedthrough=st.floats(-0.1, 0.1),
    vin_v=st.floats(0.1, 1.1),
)
def test_a_pedestal_and_a_feedthrough_are_recovered_at_any_level(
    pedestal_v: float, feedthrough: float, vin_v: float
) -> None:
    """A settled switch (tau = 100 ps) at any input level: the pedestal it leaves and the share of
    the input it follows while open, to 1 nV and 1e-9."""
    hold = analyze_hold(
        [sampler_run(replace(TB, input_voltage=vin_v), tau_s=100e-12, pedestal_v=pedestal_v, feedthrough=feedthrough)]
    )
    assert hold.pedestal_v[0] == pytest.approx(pedestal_v, abs=1e-9)
    assert hold.feedthrough[0] == pytest.approx(feedthrough, abs=1e-9)
    assert hold.vin_v[0] == vin_v


@RUNS
@given(droop_v_per_s=st.floats(-1e6, 1e6))
def test_a_linear_droop_is_recovered(droop_v_per_s: float) -> None:
    """Any linear drift of the held output (before the input steps): its slope."""
    hold = analyze_hold([sampler_run(TB, tau_s=100e-12, droop_v_per_s=droop_v_per_s)])
    assert hold.droop_v_per_s[0] == pytest.approx(droop_v_per_s, rel=1e-6, abs=1e-3)


@RUNS
@given(pedestal_v=st.floats(-5e-3, 5e-3), droop_v_per_s=st.floats(1e4, 1e6), sign=st.sampled_from((-1.0, 1.0)))
@pytest.mark.xfail(strict=True, reason="samp-7: the pedestal counts the droop of the 1.2 ns before its held point")
def test_the_pedestal_does_not_depend_on_the_droop(pedestal_v: float, droop_v_per_s: float, sign: float) -> None:
    """The step the opening switch leaves, whatever the held output does after it: to 1 uV."""
    hold = analyze_hold([sampler_run(TB, tau_s=100e-12, pedestal_v=pedestal_v, droop_v_per_s=sign * droop_v_per_s)])
    assert hold.pedestal_v[0] == pytest.approx(pedestal_v, abs=1e-6)


@RUNS
@given(
    periods=st.integers(4, 9),
    feedthrough=st.floats(1e-4, 1e-2),
    droop_v_per_s=st.floats(1e3, 1e4),
    sign=st.sampled_from((-1.0, 1.0)),
)
@pytest.mark.xfail(strict=True, reason="samp-8: the feedthrough counts the droop: cancelled only by an even count")
def test_the_feedthrough_does_not_depend_on_the_droop(
    periods: int, feedthrough: float, droop_v_per_s: float, sign: float
) -> None:
    """The share of the input's step the held output follows, whatever its droop and the number of
    holds: to 0.1 %."""
    hold = analyze_hold(
        [
            sampler_run(
                replace(TB, periods=periods), tau_s=100e-12, feedthrough=feedthrough, droop_v_per_s=sign * droop_v_per_s
            )
        ]
    )
    assert hold.feedthrough[0] == pytest.approx(feedthrough, rel=1e-3)


# ---- metrics


def _analyses(ron_ohm: np.ndarray, feedthrough: float = 1e-3) -> tuple[AnalysisTrack, AnalysisHold]:
    vin = np.asarray([fraction * 1.2 for fraction in VIN_SWEEP])
    rows = {"group": None, "index": None, "dut": Params(), "vdd_v": np.full(len(vin), 1.2), "vin_v": vin}
    track = track_result(vdd_v=rows["vdd_v"], vin_v=vin, ron_ohm=ron_ohm, track_error_v=np.zeros(len(vin)))
    hold = AnalysisHold(
        **rows,
        pedestal_v=np.zeros(len(vin)),
        droop_v_per_s=np.zeros(len(vin)),
        feedthrough=np.full(len(vin), feedthrough),
    )
    return track, hold


@given(
    ron_ohm=st.lists(
        st.one_of(st.floats(10.0, 1e5), st.just(math.nan)), min_size=len(VIN_SWEEP), max_size=len(VIN_SWEEP)
    )
)
def test_the_largest_resistance_bounds_every_settled_point(ron_ohm: list[float]) -> None:
    """ron_max_ohm is the largest settled resistance: at least every settled one, the nominal one
    among them; NaN where none settled."""
    track, hold = _analyses(np.asarray(ron_ohm))
    values = metrics(track=track, hold=hold, supply=track)
    settled = [value for value in ron_ohm if not math.isnan(value)]
    if settled:
        assert values["ron_max_ohm"] == max(settled)
        assert math.isnan(values["ron_ohm"]) or values["ron_max_ohm"] >= values["ron_ohm"]
    else:
        assert math.isnan(values["ron_max_ohm"])


@given(data=st.data())
def test_a_contiguous_settled_range_is_its_span(data: st.DataObject) -> None:
    """Settled from the i-th to the j-th input level and nowhere else: the input range is (j - i)/12
    of the supply, and it grows as the settled range grows."""
    first = data.draw(st.integers(0, len(VIN_SWEEP) - 1))
    last = data.draw(st.integers(first, len(VIN_SWEEP) - 1))
    ron = np.full(len(VIN_SWEEP), math.nan)
    ron[first : last + 1] = 300.0
    track, hold = _analyses(ron)
    span = metrics(track=track, hold=hold, supply=track)["input_range_v"]
    assert span == pytest.approx((last - first) / 12 * 1.2, abs=1e-12)
    if last + 1 < len(VIN_SWEEP):
        ron[last + 1] = 300.0
        wider, hold = _analyses(ron)
        assert metrics(track=wider, hold=hold, supply=wider)["input_range_v"] > span


@given(feedthrough=st.floats(1e-6, 1.0), sign=st.sampled_from((-1.0, 1.0)))
def test_the_feedthrough_in_db_is_twenty_log_of_its_magnitude(feedthrough: float, sign: float) -> None:
    track, hold = _analyses(np.full(len(VIN_SWEEP), 200.0), feedthrough=sign * feedthrough)
    assert metrics(track=track, hold=hold, supply=track)["feedthrough_db"] == pytest.approx(
        20 * math.log10(feedthrough), abs=1e-9
    )


# ---- the behavioral model


@given(load_f=st.floats(10e-15, 10e-12), temperature_k=st.floats(200.0, 400.0))
def test_the_held_noise_is_two_kt_over_c(load_f: float, temperature_k: float) -> None:
    """noise_v^2 C = 2 k T for any plate and temperature ([Razavi-ADC] Sec. 3.6, p. 41)."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        found = characterized_model(monkeypatch, [200.0] * len(VIN_SWEEP), [0.0] * len(VIN_SWEEP))
    behavioral = found.behavioral(load_f=load_f, temperature_k=temperature_k)
    assert behavioral.noise_v**2 * load_f == pytest.approx(2 * constants.k * temperature_k, rel=1e-9)


@given(
    resistance_ohm=st.floats(1.0, 1e4),
    load_f=st.floats(10e-15, 10e-12),
    slope_v_per_s=st.floats(-1e9, 1e9),
    vin_v=st.floats(0.0, 1.2),
)
def test_the_held_value_lags_by_r_c_times_the_slope(
    resistance_ohm: float, load_f: float, slope_v_per_s: float, vin_v: float
) -> None:
    """No noise, no jitter: held = v - R C dv/dt on each side, the lag linear in the slope."""
    switch = Model.Behavioral(ron_table_v=(0.0, 1.2), ron_table_ohm=(resistance_ohm, resistance_ohm))
    held = Model.sample(
        Params(),
        switch,
        {"p": np.asarray([vin_v]), "n": np.asarray([vin_v])},
        {"p": np.asarray([slope_v_per_s]), "n": np.asarray([-slope_v_per_s])},
        load_f={"p": load_f, "n": load_f},
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    lag = resistance_ohm * load_f * slope_v_per_s
    assert held["p"][0] == pytest.approx(vin_v - lag, abs=1e-15)
    assert held["n"][0] == pytest.approx(vin_v + lag, abs=1e-15)


@given(vin_v=st.floats(0.0, 1.2), conductance=st.floats(1e-4, 1e-1))
def test_a_balanced_transmission_gate_is_symmetric_about_mid_gate(vin_v: float, conductance: float) -> None:
    """n = p and equal thresholds: the NMOS overdrive at v is the PMOS's at V_G - v, so R(v) = R(V_G - v),
    and mid-supply is the largest resistance wherever both conduct."""
    switch = Model.Behavioral(n_conductance_s_per_v=conductance, p_conductance_s_per_v=conductance)
    pair = Model.resistance(Params(), switch, np.asarray([vin_v, 1.2 - vin_v, 0.6]), 1.2)
    assert pair[0] == pytest.approx(pair[1], rel=1e-12)
    assert pair[2] >= pair[0] * (1 - 1e-12)


@given(mos_w=st.integers(1, 256), mos_l=st.integers(1, 8))
def test_the_conductances_scale_with_w_over_l(mos_w: int, mos_l: int) -> None:
    """k' W/L: twice the width twice the conductance, twice the length half; a transmission gate
    has both devices, the NMOS and bootstrapped switches the NMOS alone, the PMOS switch the PMOS."""
    switch = Model.Behavioral()
    unit_n, unit_p = Model.conductances(Params(mos_w=1, mos_l=1), switch)
    n, p = Model.conductances(Params(mos_w=mos_w, mos_l=mos_l), switch)
    assert n == pytest.approx(unit_n * mos_w / mos_l, rel=1e-12)
    assert p == pytest.approx(unit_p * mos_w / mos_l, rel=1e-12)
    for switch_type, has_n, has_p in (
        (SwitchType.NMOS, True, False),
        (SwitchType.PMOS, False, True),
        (SwitchType.BOOTSTRAP, True, False),
    ):
        n, p = Model.conductances(Params(switch_type=switch_type, mos_w=mos_w, mos_l=mos_l), switch)
        assert (n > 0, p > 0) == (has_n, has_p)


@given(
    curve=st.lists(st.floats(10.0, 1e4), min_size=2, max_size=11),
    data=st.data(),
)
def test_a_measured_curve_is_read_at_its_points(curve: list[float], data: st.DataObject) -> None:
    """The measured on-resistance at a measured input level is the measurement itself."""
    levels = tuple(0.1 * (index + 1) for index in range(len(curve)))
    switch = Model.Behavioral(ron_table_v=levels, ron_table_ohm=tuple(curve))
    index = data.draw(st.integers(0, len(curve) - 1))
    assert Model.resistance(Params(), switch, np.asarray([levels[index]]), 1.2)[0] == pytest.approx(curve[index])
