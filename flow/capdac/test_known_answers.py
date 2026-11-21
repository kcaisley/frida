"""Known answers for the capacitive DAC, each derived on paper from the circuit, not from the code:
the arrays' weights and plates, a run's steps and LSB, the settling of single-pole steps of known
time constant, delay and gain (``analyze_settling``), the static linearity of drawn plates with one
known error (``analyze_mismatch``), the bench's capacitance from transitions of known fractions
(``analyze_cap_mismatch``), the metrics, the behavioral model (its design, its drawn DAC, its
switching charge and a Pelgrom draw), the drivers' sizing against an RC of the budget, the runs and
the netlist's weights where a kit is installed.

The synthetic settling run (``settling_run``) is the testbench's schedule (``TbParams``): each
stage's P state a linear edge of ``transition_time_s`` through mid-supply a window into its turn
and back the window after; its main bottom plate and its share of the differential top plate one
response ``f`` of the edge, ``lag_s`` after it, by superposition (up at the first edge, down at the
second); the differential's step the design's times a gain a stage. An RC is f(t) = 1 - exp(-t /
tau)."""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import hdl21 as h
import numpy as np
import pytest
from scipy.constants import Boltzmann

from flow import comp
from flow.layout.devices.mosfet.table import MosfetTable
from flow.pipeline import Meas, MeasInfo

from . import model as capdac_model
from . import runs as capdac_runs
from . import subckt
from .analysis import (
    analyze_cap_mismatch,
    analyze_decisions,
    analyze_mismatch,
    analyze_settling,
    analyze_transition,
    metrics,
)
from .model import Model
from .params import Params, Redundancy, TbParams, WeightImpl, _switched_f, _weights
from .types import AnalysisMismatch, AnalysisSettling, AnalysisSwitching, AnalysisTransition

VDD = 1.2
EDGE_S = 30e-12  # the testbench's transition_time_s
# 8-bit binary sides: seven stages of 64 to 1 units (127 in all), unit capacitors and difference strips
UNIT8 = Params(bits=8, redundancy=Redundancy.BINARY, extra=0, weight_impl=WeightImpl.UNIT_CAPS)
DIFF8 = Params(bits=8, redundancy=Redundancy.BINARY, extra=0)
BINARY8 = (64, 32, 16, 8, 4, 2, 1)
TAUS = (150e-12, 120e-12, 100e-12, 80e-12, 60e-12, 50e-12, 40e-12)
STAMP = datetime(2026, 11, 21, tzinfo=UTC)


def near(expected, rel: float = 1e-6):
    """``pytest.approx`` at a relative tolerance alone: its default absolute one, 1e-12, would pass
    any two capacitances in farads or times in seconds."""
    return pytest.approx(expected, rel=rel, abs=0.0)


def rc(tau_s: float) -> Callable[[np.ndarray], np.ndarray]:
    """A single-pole step's response, 0 before it starts."""
    return lambda t: np.where(t > 0, -np.expm1(-np.clip(t, 0.0, None) / tau_s), 0.0)


def settling_run(
    params: Params = UNIT8,
    responses: Sequence[Callable[[np.ndarray], np.ndarray]] | None = None,
    *,
    lag_s: float = 0.0,
    gains: Sequence[float] | None = None,
    shift_s: float = 0.0,
    window_s: float = 4e-9,
    dt_s: float = 1e-12,
    vdd: float = VDD,
    scale_v: float = 1.0,
) -> Meas:
    """A settling measurement of ``params`` as ``flow.pipeline.read`` gives one: every saved signal
    on one time axis of ``dt_s``. Each stage's state edges are ``shift_s`` later than the stimulus'
    (the analysis times from the edge it finds); ``scale_v`` multiplies the whole differential."""
    tb = TbParams(params=params, window_s=window_s, waveform_sample_interval_s=dt_s, vdd=vdd)
    responses = responses if responses is not None else [rc(tau) for tau in TAUS[: tb.stages]]
    time_s = np.arange(0.0, tb.stop_s + dt_s / 2, dt_s)
    steps = tb.ideal_step_v * (np.ones(tb.stages) if gains is None else np.asarray(gains))
    differential = np.full_like(time_s, -steps.sum() / 2)
    v: dict[str, np.ndarray] = {}
    for stage, response in enumerate(responses):
        up, down = (tb.window_start_s(stage, rising) + EDGE_S / 2 + shift_s for rising in (True, False))
        ramp = lambda at: np.clip((time_s - at) / EDGE_S + 0.5, 0.0, 1.0)
        fraction = response(time_s - up - lag_s) - response(time_s - down - lag_s)
        v[f"dac_state_p_{stage}"] = vdd * (ramp(up) - ramp(down))
        v[f"dut_p.main_{stage}"] = vdd * fraction
        differential = differential + steps[stage] * fraction
    v["vdac_p"] = vdd / 2 + scale_v * differential / 2
    v["vdac_n"] = vdd / 2 - scale_v * differential / 2
    return Meas(
        group=None,
        index=None,
        dut=params,
        info=MeasInfo(backend="spice", timestamp_utc=STAMP),
        param=tb,
        time_s=time_s,
        v=v,
    )


def plates_meas(params: Params, sides: Sequence[tuple[np.ndarray, ...]], *, pelgrom: float = 0.0) -> Meas:
    """A Monte Carlo measurement of ``params`` whose runs drew these plates (F, a row a run): each
    side's (main, difference), P then N, every plate the design has as its probe in fF."""
    (main_p, diff_p), (main_n, diff_n) = sides
    runs = len(main_p)
    tb = TbParams(params=params, window_s=4e-9, waveform_sample_interval_s=1e-12, pelgrom=pelgrom, mc_runs=runs)
    v = {
        f"c{kind}_{side}_{stage}.drawn": plates[:, stage] * 1e15
        for side, (main, diff) in (("p", (main_p, diff_p)), ("n", (main_n, diff_n)))
        for kind, plates, design in (("main", main, tb.main_f), ("diff", diff, tb.diff_f))
        for stage in range(tb.stages)
        if design[stage] > 0
    }
    info = MeasInfo(backend="spice", timestamp_utc=STAMP, readbacks={"runs": runs})
    return Meas(group=1, index=None, dut=params, info=info, param=tb, v=v)


def nominal_sides(params: Params, runs: int = 1, vdd: float = VDD) -> list[np.ndarray]:
    """The design's plates, a row a run: main and difference, P's then N's."""
    main_f, diff_f = Model.plates(params, vdd)
    return [
        np.tile(main_f, (runs, 1)),
        np.tile(diff_f, (runs, 1)),
        np.tile(main_f, (runs, 1)),
        np.tile(diff_f, (runs, 1)),
    ]


def synthetic_table(*, rho: float = 1.0, fo4_s: float = 0.0, unit_ohm: float = 1e6) -> MosfetTable:
    """A kit's MOSFET table: each type's unit on-resistance ``unit_ohm`` (the switching resistance
    ``rho`` times it), its FO4 delay ``fo4_s``. A large unit resistance draws a driver of many
    units, its resistance near the one asked."""
    return MosfetTable(
        pdk="synthetic",
        vdd_v=1.0,
        switching_ohm={"NMOS/LOW": rho * unit_ohm, "PMOS/LOW": rho * unit_ohm},
        triode_ohm={"NMOS/LOW": unit_ohm, "PMOS/LOW": unit_ohm},
        fo4_delay_s={"LOW": fo4_s},
    )


def use_table(monkeypatch: pytest.MonkeyPatch, table: MosfetTable, *, tau_scale: float = 1.0) -> None:
    monkeypatch.setattr(subckt, "mosfet_table", lambda pdk: table)
    monkeypatch.setattr("flow.layout.devices.mosfet.netlist.mosfet_table", lambda pdk: table)
    monkeypatch.setattr(subckt, "import_module", lambda name: SimpleNamespace(DRIVER_TAU_SCALE=tau_scale))


def settling_of(
    settling_s: Sequence[float], delay_s: Sequence[float], step_v: Sequence[float], lsb_v: float = 1e-3
) -> AnalysisSettling:
    """An ``AnalysisSettling`` whose two directions are alike: each stage's settling, delay and step."""
    settling, delay, step = (np.asarray(x, dtype=np.float64) for x in (settling_s, delay_s, step_v))
    return AnalysisSettling(
        group=None,
        index=None,
        dut=None,
        lsb_v=lsb_v,
        full_scale_v=0.5,
        gain=1.0,
        window_s=4e-9,
        ideal_step_v=step,
        step_rise_v=step,
        step_fall_v=-step,
        delay_rise_s=delay,
        delay_fall_s=delay,
        settling_rise_s=settling,
        settling_fall_s=settling,
    )


# ---- the arrays' weights and plates


def test_a_binary_side_is_the_powers_of_two_and_its_code_full_scale_less_one_lsb() -> None:
    """N - 1 binary steps of an N-bit converter, C0 heaviest: 2^(N-2) ... 1, summing to 2^(N-1) - 1;
    the decoder's weights (twice each, and the last decision's 1) sum to 2^N - 1, the code's full
    scale less one LSB."""
    weights = Model.weights(UNIT8)
    assert weights == BINARY8 and sum(weights) == 2**7 - 1
    assert sum(2 * w for w in weights) + 1 == 2**8 - 1


@pytest.mark.parametrize(
    ("params", "weights"),
    [
        # the MSB split in two halves: 64 -> 32, 32
        (Params(bits=8, redundancy=Redundancy.MSB_SPLIT, extra=1), (32, 32, 32, 16, 8, 4, 2, 1)),
        # the lightest binary weight of at least 2 split: 2 -> 1, 1
        (Params(bits=8, redundancy=Redundancy.LSB_SPLIT, extra=1), (64, 32, 16, 8, 4, 1, 1, 1)),
    ],
)
def test_a_split_array_halves_the_weight_it_names(params: Params, weights: tuple[int, ...]) -> None:
    assert Model.weights(params) == weights and sum(weights) == 127


def test_the_kt_c_minimum_equals_the_quantization_noise_at_the_references_full_scale() -> None:
    """``_switched_f``: both sides' sampled noise 2 kT/C ([Razavi-ADC] Eq. (11.52), p. 230, a
    side's kT over its whole array) equals LSB^2 / 12 ([Razavi-ADC] Eq. (12.6), p. 239) at LSB =
    2 V / 2^N, a full scale of +-V; ``scale`` minimums are ``scale`` times it."""
    for bits, vdd in ((10, 1.0), (12, 1.2), (14, 0.9)):
        params = Params(bits=bits, redundancy=Redundancy.BINARY, extra=0, scale=1)
        c_f = _switched_f(params, vdd)
        lsb_v = 2 * vdd / 2**bits
        assert 2 * Boltzmann * 300.0 / c_f == near(lsb_v**2 / 12, rel=1e-12)
        assert _switched_f(replace(params, scale=3), vdd) == near(3 * c_f, rel=1e-12)


@pytest.mark.xfail(
    strict=True,
    reason="capdac-1: the kT/C minimum is sized at a full scale of the reference; a difference-strip "
    "side's own full scale is below it, so at scale 1 its sampled noise exceeds its quantization noise",
)
def test_at_one_minimum_a_sides_sampled_noise_is_its_own_quantization_noise() -> None:
    """``Params``: at ``scale`` 1 "the sampled noise of both sides, 2 kT/C, equals the quantization
    noise". The noise a top plate samples is kT over its whole load ([Razavi-ADC] Eq. (11.52), p.
    230: every plate on it, ``TbParams.load_f``); the quantization noise is LSB^2 / 12 of the
    converter's own LSB ([Razavi-ADC] Eq. (12.6), p. 239; ``TbParams.lsb_v``, 2 FS / 2^N with FS the
    reference's share main less difference). Unit capacitors switch their whole load: equal. FRIDA-1's
    strips switch 78 % of it: the noise is 1 / 0.78 = 1.28 times the quantization noise."""
    for params in (Params(scale=1), replace(UNIT8, scale=1)):
        tb = TbParams(params=params, vdd=VDD, window_s=4e-9, waveform_sample_interval_s=2e-12)
        sampled = 2 * Boltzmann * 300.0 / tb.load_f
        assert sampled == near(tb.lsb_v**2 / 12, rel=1e-9), params.weight_impl


def test_a_strips_plates_share_its_coarse_weight_and_differ_by_its_own() -> None:
    """A fine piece w of a difference strip of coarse weight 64: main (64 + w) / 2 and difference
    (64 - w) / 2 units; a whole piece all main; unit capacitors all main. The unit is the side's
    switched capacitance over the total weight."""
    params = Params(bits=10, redundancy=Redundancy.BINARY, extra=0)  # 256 ... 1, 511 units
    main_f, diff_f = Model.plates(params, 1.0)
    unit_f = _switched_f(params, 1.0) / 511
    # 256 and 128 and 64 are whole pieces; 32 is (48, 16), 1 is (32.5, 31.5)
    np.testing.assert_allclose(main_f / unit_f, [256, 128, 64, 48, 40, 36, 34, 33, 32.5], rtol=1e-12)
    np.testing.assert_allclose(diff_f / unit_f, [0, 0, 0, 16, 24, 28, 30, 31, 31.5], rtol=1e-12)
    unit_main, unit_diff = Model.plates(replace(params, weight_impl=WeightImpl.UNIT_CAPS), 1.0)
    np.testing.assert_allclose(unit_main / unit_f, [256, 128, 64, 32, 16, 8, 4, 2, 1], rtol=1e-12)
    assert not unit_diff.any()


def test_a_runs_steps_are_its_weights_in_lsb_and_sum_to_twice_its_full_scale() -> None:
    """Each stage's differential step ([Razavi-ADC] Eq. (11.1), p. 210: its switched plates over the
    top plate, times the reference; both sides, so twice) is 2^N w / W LSB, whatever its plates'
    difference share: the steps sum to 2 FS = 2^N (W / W) LSB. FRIDA-1's full scale is the
    reference's 0.78 share (main less difference over the plates)."""
    for params in (UNIT8, DIFF8, Params()):
        tb = TbParams(params=params, vdd=VDD, window_s=4e-9, waveform_sample_interval_s=2e-12)
        weights = np.asarray(tb.weights, dtype=np.float64)
        np.testing.assert_allclose(tb.ideal_step_v / tb.lsb_v, 2**params.bits * weights / weights.sum(), rtol=1e-12)
        assert tb.ideal_step_v.sum() == near(2 * tb.full_scale_v, rel=1e-12)
    frida = TbParams(params=Params(), vdd=VDD, window_s=4e-9, waveform_sample_interval_s=2e-12)
    assert frida.full_scale_v == pytest.approx(0.78011 * VDD, abs=1e-5 * VDD)
    assert TbParams(params=UNIT8, vdd=VDD, window_s=4e-9, waveform_sample_interval_s=2e-12).full_scale_v == VDD


def test_a_runs_schedule_switches_each_stage_up_one_window_and_down_the_next() -> None:
    """A window before the first stage and two windows a stage: 7 stages in 15 windows; stage k up at
    (2k + 1) W and down at (2k + 2) W; the converter's A state alternating from 0."""
    tb = TbParams(params=UNIT8, vdd=VDD, window_s=4e-9, waveform_sample_interval_s=2e-12)
    assert tb.stop_s == near(15 * 4e-9)
    assert [tb.window_start_s(k, rising=True) for k in (0, 6)] == near([4e-9, 52e-9])
    assert [tb.window_start_s(k, rising=False) for k in (0, 6)] == near([8e-9, 56e-9])
    assert tb.astate == (0, 1, 0, 1, 0, 1, 0)


# ---- analyze_settling


@pytest.mark.parametrize("params", [UNIT8, DIFF8], ids=["unit", "strip"])
def test_a_single_pole_step_settles_tau_ln_of_its_step_over_half_an_lsb(params: Params) -> None:
    """An RC of tau started ``lag`` after the state's edge: the bottom plate at half its swing lag +
    tau ln 2 after the edge, and the differential within half an LSB of its end at lag + tau ln(|step|
    / (LSB / 2)) ([Razavi-ADC] Eq. (8.14), p. 151: ln 14 for a 7-LSB step), up and down; the drawn
    gain 1 and the steps the design's."""
    lag = 35e-12
    meas = settling_run(params, lag_s=lag)
    tb, result = meas.param, analyze_settling(meas)
    taus = np.asarray(TAUS)
    assert result.gain == near(1.0, rel=1e-9) and result.lsb_v == near(tb.lsb_v, rel=1e-9)
    ratio = tb.ideal_step_v / (tb.lsb_v / 2)  # 2^(N+1) w / W
    np.testing.assert_allclose(ratio, 2**9 * np.asarray(BINARY8) / 127, rtol=1e-12)
    for settling in (result.settling_rise_s, result.settling_fall_s):
        np.testing.assert_allclose(settling, lag + taus * np.log(ratio), atol=0.05e-12)
    for delay in (result.delay_rise_s, result.delay_fall_s):
        np.testing.assert_allclose(delay, lag + taus * math.log(2), atol=0.05e-12)
    np.testing.assert_allclose(result.step_rise_v, tb.ideal_step_v, rtol=1e-9)
    np.testing.assert_allclose(result.step_fall_v, -tb.ideal_step_v, rtol=1e-9)
    assert result.step_error_lsb < 1e-6 and result.settled


def test_a_steps_time_constant_restarts_its_exponential_at_the_drivers_delay() -> None:
    """``tau_s`` is the time constant that, started at the driver's delay d (the plate's 50 %),
    reaches half an LSB when the step does: an RC from the edge settles at t_s = tau ln(s/h) and its
    delay is tau ln 2, so the model's tau' = (t_s - d) / ln(s/h) = tau (1 - ln 2 / ln(s/h))."""
    meas = settling_run(UNIT8)
    result = analyze_settling(meas)
    ln_ratio = np.log(meas.param.ideal_step_v / (meas.param.lsb_v / 2))
    np.testing.assert_allclose(result.tau_s, np.asarray(TAUS) * (1 - math.log(2) / ln_ratio), rtol=1e-3)


def test_a_drawn_array_at_a_gain_scales_its_full_scale_and_lsb_and_keeps_its_steps_exact() -> None:
    """Every step 0.7 of the design's (the top plate's load beyond the design's plates): the gain is
    0.7 and so are the full scale and the LSB the settling is measured to; the steps' error is none,
    and the settling, a ratio of the step to the LSB, is unchanged."""
    base, low = analyze_settling(settling_run(UNIT8)), analyze_settling(settling_run(UNIT8, scale_v=0.7))
    tb = TbParams(params=UNIT8, vdd=VDD, window_s=4e-9, waveform_sample_interval_s=1e-12)
    assert low.gain == near(0.7, rel=1e-9)
    assert low.full_scale_v == near(0.7 * tb.full_scale_v, rel=1e-9)
    assert low.lsb_v == near(0.7 * tb.lsb_v, rel=1e-9) and low.step_error_lsb < 1e-6
    np.testing.assert_allclose(low.settling_s, base.settling_s, atol=0.05e-12)


def test_one_stage_drawn_large_moves_the_least_squares_gain_and_errs_by_its_excess() -> None:
    """C2 (16 of 127 units) drawn 1 % large, the rest as designed: the least-squares gain of the
    rising steps s_k = g_k d_k on the design's d_k is sum(g_k d_k^2) / sum(d_k^2) = 1 + 0.01 * 16^2
    / 5461 (5461 = 64^2 + ... + 1^2); C2's step errs from g d_2 by (1.01 - g) d_2, in the LSB at that
    gain (g times the design's, d_2 being 2^8 16 / 127 of its LSB): (1.01 - g) / g * 4096 / 127 =
    0.307 LSB; the MSB's by (g - 1) / g * 2^8 64 / 127 = 0.060 LSB."""
    gains = [1.0, 1.0, 1.01, 1.0, 1.0, 1.0, 1.0]
    result = analyze_settling(settling_run(UNIT8, gains=gains))
    g = 1 + 0.01 * 256 / 5461
    assert result.gain == near(g, rel=1e-9)
    assert result.step_error_lsb == near((1.01 - g) / g * 4096 / 127, rel=1e-6)
    assert result.step_error_lsb == pytest.approx(0.30725, abs=1e-5)


@pytest.mark.xfail(
    strict=True,
    reason="capdac-5: analyze_settling's full scale is the design's at the fitted gain, not half the sum "
    "of the drawn steps (Model.full_scale_v's), once one stage is drawn other than its weight",
)
def test_the_drawn_arrays_full_scale_is_half_the_sum_of_its_steps() -> None:
    """The converter's input range is what its decisions' steps span: +-half their sum (as
    ``Model.full_scale_v`` gives it, and the design's, ``TbParams``: the steps sum to 2 FS). C2 drawn
    1 % large adds 0.01 of its step: FS = FS_design (1 + 0.01 * 16 / 127), and the LSB 2 FS / 2^N,
    against the fitted gain's FS_design (1 + 0.01 * 256 / 5461)."""
    gains = [1.0, 1.0, 1.01, 1.0, 1.0, 1.0, 1.0]
    meas = settling_run(UNIT8, gains=gains)
    result = analyze_settling(meas)
    assert result.full_scale_v == near(result.step_rise_v.sum() / 2, rel=1e-9)
    assert result.full_scale_v == near(meas.param.full_scale_v * (1 + 0.01 * 16 / 127), rel=1e-9)
    assert result.lsb_v == near(2 * result.full_scale_v / 2**8, rel=1e-9)


def test_a_step_that_rings_settles_when_it_last_enters_the_band() -> None:
    """The MSB's step rings, 1 - exp(-t / tau) cos(omega t) (tau 150 ps, 1.5 GHz): it passes half an
    LSB of its end several times; the settling time is its last entry into the band. Found here by
    brute force on a 0.01 ps grid of the formula itself."""
    tau, omega = 150e-12, 2 * math.pi * 1.5e9

    def ringing(t: np.ndarray) -> np.ndarray:
        return np.where(t > 0, 1 - np.exp(-np.clip(t, 0.0, None) / tau) * np.cos(omega * t), 0.0)

    responses = [ringing, *(rc(t) for t in TAUS[1:])]
    meas = settling_run(UNIT8, responses)
    tb, result = meas.param, analyze_settling(meas)
    t = np.arange(0.0, 2e-9, 0.01e-12)
    outside = np.abs(tb.ideal_step_v[0] * (ringing(t) - 1)) > tb.lsb_v / 2
    last = t[np.flatnonzero(outside)[-1]]
    assert result.settling_rise_s[0] == pytest.approx(last, abs=0.2e-12)
    first = t[np.flatnonzero(~outside & (t > 0))[0]]
    assert first < last - 100e-12  # the band entered and left before


def test_a_step_still_moving_past_its_windows_middle_is_not_settled() -> None:
    """An MSB of tau 600 ps takes 600 ps ln 258 = 3.3 ns, past half its 4 ns window."""
    result = analyze_settling(settling_run(UNIT8, [rc(600e-12), *(rc(t) for t in TAUS[1:])]))
    assert not result.settled and result.settling_s[0] > 2e-9


def test_the_slower_directions_delay_step_and_time_constant_go_together() -> None:
    """Each stage's delay, step and tau are of the direction that settles later."""
    result = AnalysisSettling(
        group=None,
        index=None,
        dut=None,
        lsb_v=1e-3,
        full_scale_v=0.5,
        gain=1.0,
        window_s=4e-9,
        ideal_step_v=np.asarray([0.1, 0.1]),
        step_rise_v=np.asarray([0.1, 0.1]),
        step_fall_v=np.asarray([-0.05, -0.2]),
        delay_rise_s=np.asarray([10e-12, 10e-12]),
        delay_fall_s=np.asarray([20e-12, 20e-12]),
        settling_rise_s=np.asarray([300e-12, 200e-12]),
        settling_fall_s=np.asarray([250e-12, 400e-12]),
    )
    np.testing.assert_allclose(result.settling_s, [300e-12, 400e-12])
    np.testing.assert_allclose(result.delay_s, [10e-12, 20e-12])
    np.testing.assert_allclose(result.step_v, [0.1, -0.2])
    np.testing.assert_allclose(result.tau_s, [290e-12 / math.log(200), 380e-12 / math.log(400)], rtol=1e-12)


@pytest.mark.xfail(
    strict=True,
    reason="capdac-4: a stage whose driver delay is not measured (NaN) gets a time constant of 0, an "
    "ideal step, instead of none",
)
def test_a_stage_without_a_measured_delay_has_no_time_constant() -> None:
    """tau = (t_s - d) / ln(|s| / h) is undefined where d is: NaN, not 0 (which the behavioral ADC
    reads as a step complete at once)."""
    result = settling_of([300e-12, 300e-12], [50e-12, math.nan], [0.1, 0.1])
    assert result.tau_s[0] > 0 and math.isnan(result.tau_s[1])


# ---- analyze_mismatch


def test_a_perfect_array_has_no_dnl_inl_or_gap_and_no_missing_codes() -> None:
    """Drawn as designed (P and N alike, the converter's A state): every code one unit step wide."""
    for params in (UNIT8, DIFF8, Params(bits=8, redundancy=Redundancy.MSB_REDIST, extra=2)):
        main_p, diff_p, main_n, diff_n = nominal_sides(params)
        result = analyze_mismatch(plates_meas(params, [(main_p, diff_p), (main_n, diff_n)]))
        for values in (result.dac_inl_lsb, result.dac_dnl_lsb, result.dnl_lsb, result.inl_lsb, result.gap_lsb):
            assert values[0] == pytest.approx(0.0, abs=1e-9), params
        assert result.missing_codes[0] == 0


def _heavy_msb(delta_units: float) -> AnalysisMismatch:
    """An 8-bit binary side of unit capacitors, its MSB ``delta_units`` units heavier, both sides."""
    main_p, diff_p, main_n, diff_n = nominal_sides(UNIT8)
    unit_f = main_p[0, -1]
    main_p[0, 0] += delta_units * unit_f
    main_n[0, 0] += delta_units * unit_f
    return analyze_mismatch(plates_meas(UNIT8, [(main_p, diff_p), (main_n, diff_n)]))


def test_an_msb_heavy_by_delta_units_errs_only_at_its_major_transition() -> None:
    """MSB 64 + delta of 127 + delta units (delta 0.64, 1 %), the DAC alone ([Razavi-ADC] Example
    8.4, p. 146: only the major transition errs): its LSB the end points' (127 + delta) / 127 units,
    code 64's output (64 + delta) 127 / (127 + delta) LSB, an INL of 63 delta / (127 + delta), and the
    step 63 -> 64 (1 + delta) 127 / (127 + delta) LSB, a DNL of 126 delta / (127 + delta)
    ([Razavi-ADC] Eq. (8.5), p. 145). The converter: the codes either side of mid-scale 1 + delta
    unit steps wide, the other 252 one; DNL against the mean width ([Razavi-ADC] Eq. (12.11), p. 242)
    252 delta / (254 + 2 delta), no code missing. With every decision's true weight no calibration
    narrows those two paths: each 1 + delta drawn units (127 / (127 + delta) of a code each), the
    widest less one code 126 delta / (127 + delta)."""
    d = 0.64
    result = _heavy_msb(d)
    assert result.dac_inl_lsb[0] == near(63 * d / (127 + d), rel=1e-9)
    assert result.dac_dnl_lsb[0] == near(126 * d / (127 + d), rel=1e-9)
    assert result.dnl_lsb[0] == near(252 * d / (254 + 2 * d), rel=1e-9)
    assert result.missing_codes[0] == 0
    assert result.gap_lsb[0] == near(126 * d / (127 + d), rel=1e-9)


@pytest.mark.xfail(
    strict=True,
    reason="capdac-3: the converter's INL is referred to a line through the first and the last code's "
    "starts, not through the first and last transitions (the end points)",
)
def test_an_msb_heavy_by_delta_units_has_the_inl_of_its_transitions_against_the_end_points() -> None:
    """[Razavi-ADC] Eq. (12.12), p. 244: INL_j = V_j - j Delta against the straight line through the
    characteristic's end points, the first and the last transition (V_1 and V_255 of codes 1 to 254),
    Delta = (V_255 - V_1) / 254 = (1 + 2 delta / 254) unit steps. V_127 - V_1 = 126 steps, so INL_127
    = 126 / (1 + 2 delta / 254) - 126 = -252 delta / (254 + 2 delta); V_129 - V_1 = 128 + 2 delta steps,
    INL_129 = +252 delta / (254 + 2 delta): the worst |INL| equals the worst DNL here."""
    d = 0.64
    assert _heavy_msb(d).inl_lsb[0] == near(252 * d / (254 + 2 * d), rel=1e-9)


def test_an_msb_one_unit_light_misses_the_two_codes_either_side_of_mid_scale() -> None:
    """MSB 63 of 126 drawn units: the lower half's highest threshold, -63 + (32 + ... + 1), meets the
    first decision's at 0, and so does the upper half's lowest: codes 127 and 128 hold no input, two
    missing codes, each a DNL of -1 ([Razavi-ADC] Example 12.4, p. 242). The DAC alone: code 64's
    output 63 127 / 126 LSB, an INL of -1/2, and the major step 0 of its LSB, a DNL of -1. Every path
    is one drawn unit, 127 / 126 of a code: a gap of 1 / 126."""
    result = _heavy_msb(-1.0)
    assert result.missing_codes[0] == 2 and result.dnl_lsb[0] == near(1.0, rel=1e-9)
    assert result.dac_inl_lsb[0] == near(0.5, rel=1e-9)
    assert result.dac_dnl_lsb[0] == near(1.0, rel=1e-9)
    assert result.gap_lsb[0] == near(1 / 126, rel=1e-6)


def test_a_redundant_array_leaves_nothing_unrecoverable_where_a_binary_one_does() -> None:
    """MSB_REDIST's MSB of 48 of 127 units (8 bits, one extra cycle; a strip of main 56 and
    difference 8 units) with its main plate 1 % large, 0.56 units: the stages after it outweigh it
    by 79 - 48 units, so the two halves overlap around mid-scale, every threshold on a grid of one
    drawn unit offset by 0.56, and no path is wider than a drawn unit (less than a code, the load
    being larger): no gap. The binary array's MSB 0.64 units heavy leaves 0.632 of a code (above)."""
    params = Params(bits=8, redundancy=Redundancy.MSB_REDIST, extra=1)
    assert Model.weights(params) == (48, 32, 20, 12, 8, 4, 2, 1)
    main_p, diff_p, main_n, diff_n = nominal_sides(params)
    for main in (main_p, main_n):
        main[0, 0] *= 1.01
    result = analyze_mismatch(plates_meas(params, [(main_p, diff_p), (main_n, diff_n)]))
    assert result.gap_lsb[0] == 0.0 and result.missing_codes[0] == 0


def test_the_dac_curves_are_the_run_at_the_95th_percentile_of_the_dacs_inl() -> None:
    """Three runs, the MSB heavy by 0, 0.32 and 0.64 units: the DAC's worst INL 0, x, about 2x; the
    95th percentile (linear, of three) at 1.9 x, nearest the third run, whose INL at code 64 is 63
    delta / (127 + delta)."""
    main_p, diff_p, main_n, diff_n = nominal_sides(UNIT8, runs=3)
    unit_f = main_p[0, -1]
    for run, delta in enumerate((0.0, 0.32, 0.64)):
        main_p[run, 0] += delta * unit_f
        main_n[run, 0] += delta * unit_f
    result = analyze_mismatch(plates_meas(UNIT8, [(main_p, diff_p), (main_n, diff_n)]))
    assert result.runs == 3 and len(result.dac_inl_curve_lsb) == 128
    assert result.dac_inl_curve_lsb[64] == near(63 * 0.64 / 127.64, rel=1e-9)
    assert result.dac_dnl_curve_lsb[63] == near(126 * 0.64 / 127.64, rel=1e-9)
    values = result.dac_inl_lsb
    assert result.dac_inl_p95_lsb == near(values[1] + 0.9 * (values[2] - values[1]), rel=1e-12)


def test_scaling_every_drawn_plate_changes_no_linearity() -> None:
    """Each step is its plates' share of the top plate: 3.7 times every plate, both sides, gives the
    same transfer."""
    main_p, diff_p, main_n, diff_n = nominal_sides(DIFF8)
    rng = np.random.default_rng(7)
    main_p = main_p * (1 + 0.01 * rng.standard_normal(main_p.shape))
    base = analyze_mismatch(plates_meas(DIFF8, [(main_p, diff_p), (main_n, diff_n)]))
    scaled = analyze_mismatch(plates_meas(DIFF8, [(3.7 * main_p, 3.7 * diff_p), (3.7 * main_n, 3.7 * diff_n)]))
    for name in ("dac_inl_lsb", "dac_dnl_lsb", "dnl_lsb", "inl_lsb", "gap_lsb", "missing_codes"):
        np.testing.assert_allclose(getattr(scaled, name), getattr(base, name), rtol=1e-9, atol=1e-12, err_msg=name)


# ---- the bench's switching curves: analyze_decisions, analyze_transition, analyze_cap_mismatch

DUT, COMPARATOR = "frida-adc-7", "comparator-design"


def switching(side: str, stage: int, direction: str, diffcaps: int, *, vdd_dac_v: float = 1.2, stages: int = 4):
    """One point of a curve as ``adc.analyze_switching`` gives it: three trials of known inputs."""
    return AnalysisSwitching(
        group=0,
        index=7,
        dut=DUT,
        info=MeasInfo(backend="physical", timestamp_utc=STAMP),
        param=None,
        campaign="cdac_ab",
        side=side,
        stage=stage,
        direction=direction,
        diffcaps=diffcaps,
        trial_index=np.arange(3),
        vin_diff_v=np.asarray([-1e-3, 0.0, 1e-3]),
        vin_cm_v=np.full(3, 0.6),
        decision=np.asarray([0, 1, 1]),
        vdd_dac_v=vdd_dac_v,
        stages=stages,
        expected_fraction=np.full(stages, 0.25),
        comparator=COMPARATOR,
    )


def transition(side: str, stage: int, direction: str, diffcaps: int, transition_v: float) -> AnalysisTransition:
    return AnalysisTransition(
        group=0,
        index=7,
        dut=DUT,
        side="p" if side == "p" else "n",
        element=stage,
        direction="0to1" if direction == "0to1" else "1to0",
        diffcaps=diffcaps,
        vin_diff_v=np.asarray([0.0]),
        decision_probability=np.asarray([0.5]),
        trial_count=np.asarray([3]),
        transition_v=transition_v,
        valid=math.isfinite(transition_v),
    )


def comparator(offset_v: float) -> comp.AnalysisOffsetNoise:
    return comp.AnalysisOffsetNoise(
        group=0,
        index=7,
        dut=COMPARATOR,
        vin_cm_v=0.6,
        vin_diff_v=np.asarray([offset_v - 1e-3, offset_v, offset_v + 1e-3]),
        decision_probability=np.asarray([0.0, 0.5, 1.0]),
        trial_count=np.asarray([100, 100, 100]),
        offset_v=offset_v,
        noise_sigma_v=0.3e-3,
        decision_polarity=1,
        validity=comp.Validity.VALID,
    )


def placed(fractions: dict[tuple[str, int, int], tuple[float, float]], offset_v: float, vdd_dac_v: float = 1.2):
    """The curves of plates of known fractions: a P plate rising by f of the reference raises the
    comparator's input by f V, so the curve turns where V_in + f V = V_OS, at V_OS - f V; falling, at
    V_OS + f V; an N plate the other way round. ``fractions``: (side, stage, mode) -> each direction's
    fraction (1to0, 0to1)."""
    points, fits = [], []
    for (side, stage, diffcaps), (down, up) in fractions.items():
        for direction, fraction in (("1to0", down), ("0to1", up)):
            moves = (1 if side == "p" else -1) * (1 if direction == "0to1" else -1)
            points.append(switching(side, stage, direction, diffcaps, vdd_dac_v=vdd_dac_v))
            fits.append(transition(side, stage, direction, diffcaps, offset_v - moves * fraction * vdd_dac_v))
    return points, fits


def test_a_stages_two_modes_give_its_main_and_difference_plates() -> None:
    """Main 0.15 and difference 0.05 of the side: together (mode 0) 0.20, against each other (mode 1,
    as the converter switches them) 0.10; P's and N's alike; the direction bias half of 1to0 less
    0to1 (0.02 in mode 1); separation P's and N's difference plates together."""
    fractions = {
        ("p", 2, 0): (0.20, 0.20),
        ("p", 2, 1): (0.12, 0.08),
        ("n", 2, 0): (0.20, 0.20),
        ("n", 2, 1): (0.12, 0.08),
    }
    points, fits = placed(fractions, offset_v=-3e-3)
    result = analyze_cap_mismatch(points, transitions=fits, comparator=comparator(-3e-3))
    np.testing.assert_allclose(result.effective_fraction[:, 2], [0.10, 0.10], rtol=1e-12)
    np.testing.assert_allclose(result.main_fraction[:, 2], [0.15, 0.15], rtol=1e-12)
    np.testing.assert_allclose(result.diff_fraction[:, 2], [0.05, 0.05], rtol=1e-12)
    np.testing.assert_allclose(result.direction_bias[:, 2, 1], [0.02, 0.02], rtol=1e-12)
    np.testing.assert_allclose(result.direction_bias[:, 2, 0], [0.0, 0.0], atol=1e-15)
    assert result.fraction[2] == near(0.10) and result.separation[2] == near(0.10)
    assert result.main[2] == near(0.15) and result.bias[2] == near(0.02)
    assert result.asymmetry[2] == pytest.approx(0.0, abs=1e-15)
    assert result.fraction_error[2] == near(0.10 - 0.25)
    assert np.isnan(result.effective_fraction[0, 0])  # a stage without curves


def test_an_invalid_transition_leaves_its_stage_unmeasured() -> None:
    points, fits = placed({("p", 1, 1): (0.1, 0.1)}, offset_v=0.0)
    fits[1] = replace(fits[1], transition_v=math.nan, valid=False)
    result = analyze_cap_mismatch(points, transitions=fits, comparator=comparator(0.0))
    assert np.isnan(result.effective_fraction[0, 1])
    assert result.effective_fraction_by_direction[0, 1, 0] == near(0.1)


def test_a_curves_decisions_are_its_points_trials_in_order_and_its_transition_the_fits_50_percent() -> None:
    """``analyze_decisions``: two points of three trials each, six decisions in order;
    ``analyze_transition``: the S-curve fit's offset, at its coordinates."""
    first = switching("n", 3, "1to0", 0)
    second = replace(first, trial_index=np.arange(3, 6), vin_diff_v=np.asarray([2e-3, 3e-3, 4e-3]), decision=np.ones(3))
    decisions = analyze_decisions([first, second])
    np.testing.assert_array_equal(decisions.trial_index, np.arange(6))
    np.testing.assert_allclose(decisions.vin_diff_v, [-1e-3, 0.0, 1e-3, 2e-3, 3e-3, 4e-3])
    np.testing.assert_array_equal(decisions.decision, [0, 1, 1, 1, 1, 1])
    fit = comp.AnalysisOffsetNoise(
        group=0,
        index=7,
        dut=DUT,
        vin_cm_v=0.6,
        vin_diff_v=np.asarray([-1e-3, 0.0, 1e-3, 2e-3, 3e-3, 4e-3]),
        decision_probability=np.asarray([0.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
        trial_count=np.ones(6),
        offset_v=-0.4e-3,
        noise_sigma_v=0.2e-3,
        decision_polarity=1,
        validity=comp.Validity.VALID,
    )
    placed_fit = analyze_transition([first, second], offset=fit)
    assert (placed_fit.side, placed_fit.element, placed_fit.direction, placed_fit.diffcaps) == ("n", 3, "1to0", 0)
    assert placed_fit.valid and placed_fit.transition_v == -0.4e-3


# ---- metrics


def test_the_metrics_are_their_analyses_numbers() -> None:
    """Stages, the slowest and the MSB's settling, the largest delay and time constant (each of its
    stage's slower direction), the window, gain, full scale, LSB and step error as analyzed; at each
    Monte Carlo condition, mc_a<A in 0.1 %·sqrt(fF)> of its 95th percentiles."""
    result = settling_of([300e-12, 500e-12, 200e-12], [40e-12, 30e-12, 60e-12], [0.2, 0.1, 0.05])
    found = metrics(settling=result)
    assert found["stages"] == 3.0
    assert found["settling_max_s"] == 500e-12 and found["settling_msb_s"] == 300e-12
    assert found["delay_max_s"] == 60e-12
    assert found["tau_max_s"] == near(max(260e-12 / math.log(400), 470e-12 / math.log(200)))
    assert (found["window_s"], found["gain"], found["lsb_v"], found["full_scale_v"]) == (4e-9, 1.0, 1e-3, 0.5)
    main_p, diff_p, main_n, diff_n = nominal_sides(UNIT8, runs=2)
    main_p[1, 0] *= 1.01
    mismatch = analyze_mismatch(plates_meas(UNIT8, [(main_p, diff_p), (main_n, diff_n)], pelgrom=0.005))
    with_mc = metrics(settling=result, mismatch=(mismatch,))
    assert with_mc["mc_a5_dac_inl_p95_lsb"] == near(float(np.percentile(mismatch.dac_inl_lsb, 95)))
    assert with_mc["mc_a5_inl_p95_lsb"] == near(float(np.percentile(mismatch.inl_lsb, 95)))
    assert with_mc["mc_a5_gap_p95_lsb"] == near(float(np.percentile(mismatch.gap_lsb, 95)))


@pytest.mark.xfail(
    strict=True,
    reason="capdac-4: the metrics' largest delay takes Python's max over an array with a NaN, which keeps "
    "or drops it by where it stands",
)
def test_the_largest_delay_does_not_depend_on_which_stage_lacks_one() -> None:
    """The same three delays, one not measured, in either order: the same largest delay."""
    first = metrics(settling=settling_of([300e-12] * 3, [math.nan, 40e-12, 60e-12], [0.2, 0.1, 0.05]))
    later = metrics(settling=settling_of([300e-12] * 3, [40e-12, math.nan, 60e-12], [0.2, 0.1, 0.05]))
    assert first["delay_max_s"] == later["delay_max_s"] or (
        math.isnan(first["delay_max_s"]) and math.isnan(later["delay_max_s"])
    )


# ---- the behavioral model


def test_a_designs_model_settles_each_stage_to_half_an_lsb_at_its_budget() -> None:
    """``Model.design``: no delay, each stage's step s = 2^N w / W LSB decays as s exp(-t / tau) and
    reaches half an LSB at settle_ps / settle_margin: tau = budget / ln(2^(N+1) w / W); the LSB 2 FS /
    2^N at FRIDA-1's 0.78011 share of 1.2 V."""
    params = Params(settle_ps=1200.0, settle_margin=3.0)
    model = Model.design("tsmc65", params, reference_v=1.2)
    weights = np.asarray(Model.weights(params), dtype=np.float64)
    steps_lsb = 2**12 * weights / weights.sum()
    np.testing.assert_allclose(steps_lsb * np.exp(-400e-12 / np.asarray(model.tau_s)), 0.5, rtol=1e-12)
    assert model.lsb_v == near(2 * 0.78011 * 1.2 / 4096, rel=2e-5)
    assert model.full_scale_v(1.2) == near(0.78011 * 1.2, rel=2e-5)
    assert model.full_scale_v(0.6) == near(0.78011 * 0.6, rel=2e-5)


def test_one_capacitor_switched_onto_the_rest_divides_the_reference_and_draws_its_series_charge() -> None:
    """``Model.switch``, one side: C1 = 3 fF rising to 1 V, C2 = 5 fF held at ground, a 2 fF parasitic:
    the top plate steps C1 / (C1 + C2 + Cp) V = 0.3 V ([Razavi-ADC] Eq. (11.1), p. 210, with the
    parasitic in the divider, Eq. (11.3), p. 211); C1 draws C1 (1 - 0.3) V = 2.1 fC from the
    reference, an energy of 2.1 fJ. Falling back, nothing is at the reference: no charge."""
    main_f, diff_f = np.asarray([3e-15, 5e-15]), np.zeros(2)
    before, after = np.asarray([[0, 0], [1, 0]]), np.asarray([[1, 0], [0, 0]])
    top, charge, transitions = Model.switch(main_f, diff_f, 2e-15, 1.0, 1, before, after)
    np.testing.assert_allclose(top, [0.3, -0.3], rtol=1e-12)
    np.testing.assert_allclose(charge, [2.1e-15, 0.0], atol=1e-30)
    assert transitions.tolist() == [2, 2]


def test_a_capacitor_charged_onto_a_held_top_plate_draws_c_v_squared() -> None:
    """[Razavi-ADC] Fig. 16.29, p. 348: charging C1 from zero to V1 draws C1 V1^2 from V1. A top plate
    held by a parasitic a million times larger moves 1e-6 V: C1 = 4 fF to 0.9 V draws 4 fF 0.9 V
    (1 - 1e-6), 3.24 fJ times 0.9 V."""
    top, charge, _ = Model.switch(np.asarray([4e-15]), np.zeros(1), 4e-9, 0.9, 1, np.asarray([[0]]), np.asarray([[1]]))
    assert charge[0] * 0.9 == near(4e-15 * 0.9**2, rel=2e-6) and abs(top[0]) < 1e-6


def test_a_stage_whose_difference_plate_falls_as_its_main_rises_steps_by_their_difference() -> None:
    """diffcaps 1 (capdac's arrays): the main plate 6 fF rises 1 V while the difference plate 2 fF
    falls 1 V, on a 10 fF top plate (2 fF parasitic): (6 - 2) / 10 V = 0.4 V; the main plate draws 6
    fF (1 - 0.4) V = 3.6 fC. With diffcaps 0 they rise together: 0.8 V, 6 fF 0.2 V + 2 fF 0.2 V."""
    main_f, diff_f = np.asarray([6e-15]), np.asarray([2e-15])
    top, charge, _ = Model.switch(main_f, diff_f, 2e-15, 1.0, 1, np.asarray([[0]]), np.asarray([[1]]))
    assert top[0] == near(0.4) and charge[0] == near(3.6e-15)
    top, charge, _ = Model.switch(main_f, diff_f, 2e-15, 1.0, 0, np.asarray([[0]]), np.asarray([[1]]))
    assert top[0] == near(0.8) and charge[0] == near(1.6e-15)


def test_a_pelgrom_draws_spread_is_its_coefficient_times_the_root_of_its_capacitance() -> None:
    """``Model.draw``: sigma_C = A sqrt(C 1 fF): 0.5 %, 400 fF: 0.1 fF; 25 fF: 0.025 fF."""
    draws = Model.draw(np.tile([400e-15, 25e-15], (40000, 1)), pelgrom=0.005, rng=np.random.default_rng(3))
    np.testing.assert_allclose(np.std(draws, axis=0), [0.1e-15, 0.025e-15], rtol=0.02)


@pytest.mark.xfail(
    strict=True,
    reason="capdac-2: Model.draw spreads each capacitor by the coefficient, which Pelgrom states for a "
    "pair's difference: a pair then differs sqrt(2) times more than the coefficient says",
)
def test_a_pair_drawn_at_pelgroms_coefficient_differs_by_it() -> None:
    """[Pelgrom] Eq. (4.34), p. 144 and Eq. (6.10), p. 283: the coefficient A_C states the spread of
    the difference of two like capacitors, sigma_dC / C = A_C / sqrt(C) (a 400 fF pair at 0.5 %: 0.1
    fF). Two 400 fF capacitors drawn at 0.5 % differ by 0.1 fF rms."""
    draws = Model.draw(np.tile([400e-15, 400e-15], (40000, 1)), pelgrom=0.005, rng=np.random.default_rng(4))
    assert np.std(draws[:, 0] - draws[:, 1]) == near(0.1e-15, rel=0.02)


def test_the_drawn_monte_carlo_run_is_ranked_by_its_gap_then_its_inl(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Model.drawn``: five runs of gaps 0.3, 0.1, 0.5, 0.1, 0.4 (INL 1, 2, 1, 1, 1): ranked 3, 1, 0,
    4, 2 (the tie of 0.1 by INL); the 50th percentile the third of them, run 0, the 100th run 2."""
    gaps, inls = np.asarray([0.3, 0.1, 0.5, 0.1, 0.4]), np.asarray([1.0, 2.0, 1.0, 1.0, 1.0])
    runs = np.arange(5, dtype=np.float64)[:, None] * np.ones(2)
    result = SimpleNamespace(gap_lsb=gaps, inl_lsb=inls, main_p_f=runs, diff_p_f=runs, main_n_f=runs, diff_n_f=runs)
    monkeypatch.setattr(capdac_model, "characterized", lambda *a, **k: {"waves": {"mc_a5": "mc.h5"}})
    monkeypatch.setattr(capdac_model, "read_measurement", lambda path: None)
    monkeypatch.setattr(capdac_model, "analyze_mismatch", lambda meas: result)
    (main_p, _), _ = Model.drawn("tsmc65", UNIT8, "mc_a5", 50.0)
    assert main_p[0] == 0.0
    assert Model.drawn("tsmc65", UNIT8, "mc_a5", 0.0)[0][0][0] == 3.0
    assert Model.drawn("tsmc65", UNIT8, "mc_a5", 100.0)[0][0][0] == 2.0


# ---- the drivers' sizing (subckt, PDK-free on a synthetic MOSFET table)


def test_a_driver_into_its_load_alone_settles_its_stage_at_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_drive_r_ohm`` with the switching resistance the on-resistance (rho 1) and a chain without
    delay: the step settles as an RC of R C_L ([Razavi-Analog] Eq. (13.31), p. 552) to half an LSB in
    R C_L ln(2^(N+1) w / W) ([Razavi-ADC] Eq. (8.14), p. 151), which is the budget settle_ps /
    settle_margin; with the kit's scale s, s R C_L ln(...)."""
    use_table(monkeypatch, synthetic_table())
    params = Params(bits=10, redundancy=Redundancy.BINARY, extra=0, settle_ps=1000.0, settle_margin=2.0)
    for share, load_f in ((256 / 511, 120e-15), (1 / 511, 0.4e-15)):
        r_ohm = subckt._drive_r_ohm(params, share, load_f, "synthetic", False, 4.0)
        assert r_ohm * load_f * math.log(2**11 * share) == near(500e-12, rel=1e-12)
    use_table(monkeypatch, synthetic_table(), tau_scale=0.8)
    r_ohm = subckt._drive_r_ohm(params, 0.5, 100e-15, "synthetic", False, 4.0)
    assert 0.8 * r_ohm * 100e-15 * math.log(2**10) == near(500e-12, rel=1e-12)


def test_a_stage_driven_as_sized_settles_in_the_analysis_at_its_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every stage of an 8-bit binary unit side driven by ``_drive_r_ohm``'s resistance into its
    plate's load (its plate in series with the rest of the top plate, the rest held ideally: [Razavi-ADC]
    Eq. (11.10), p. 215, without the rest's switches), each a chain of inner inverters of 20 ps
    (FO4) before it: each step, an RC of R C_L started the chain's delay after the edge, settles in
    ``analyze_settling`` at settle_ps / settle_margin."""
    use_table(monkeypatch, synthetic_table(fo4_s=20e-12))
    params = replace(UNIT8, settle_ps=1000.0, settle_margin=2.0)
    tb = TbParams(params=params, vdd=VDD, window_s=4e-9, waveform_sample_interval_s=1e-12)
    top_f = tb.load_f
    loads = tb.main_f * (top_f - tb.main_f) / top_f
    weights = np.asarray(_weights(params), dtype=np.float64)
    taus, lags = [], []
    for weight, load_f in zip(weights, loads, strict=True):
        r_ohm = subckt._drive_r_ohm(params, weight / weights.sum(), load_f, "synthetic", False, 4.0)
        chain = len(subckt.DriverRequest(r_ohm, False, fanin=4.0).stages("synthetic"))
        taus.append(r_ohm * load_f)
        lags.append((chain - 1) * 20e-12)
    assert len(set(lags)) == 1  # one chain length here
    result = analyze_settling(settling_run(params, [rc(t) for t in taus], lag_s=lags[0]))
    np.testing.assert_allclose(result.settling_s, 500e-12, atol=0.05e-12)


def test_a_plates_load_is_its_capacitance_in_series_with_the_rest_of_the_top_plate() -> None:
    """``_plate_load``: [Razavi-ADC] Eq. (11.10), p. 215: k C0 of m C0 on the top plate loads its
    switch with (k C0)((m - k) C0) / (m C0); 64 of 128 fF: 32 fF; with 3 fF to the shield and 1 fF to a
    plate that swings the other way (twice: 2 fF): 37 fF."""
    stage = [
        {frozenset(("MAIN", "TOP")): 64e-15, frozenset(("MAIN", "SHIELD")): 3e-15, frozenset(("MAIN", "DIFF")): 1e-15}
    ]
    assert subckt._plate_load(stage, "MAIN", "DIFF", 128e-15) == near(37e-15, rel=1e-12)
    assert subckt._plate_load(stage, "MAIN", None, 128e-15) == near(35e-15, rel=1e-12)


# ---- the runs


def test_the_runs_window_sampling_and_monte_carlo_conditions(monkeypatch: pytest.MonkeyPatch) -> None:
    """``testbenches``: a window of 4 settle_ps rounded up to 100 ps (1000 ps: 4 ns; 1010 ps: 4.1 ns),
    sampled every 2000th of it, at the kit's supply; Monte Carlo at 0.1, 0.5 and 1 %·sqrt(fF), a
    hundred runs each, named mc_a1, mc_a5, mc_a10."""
    site = SimpleNamespace(install=SimpleNamespace(supply_voltage=lambda corner: 1.2))
    monkeypatch.setattr(capdac_runs, "importlib", SimpleNamespace(import_module=lambda name: site))
    benches = capdac_runs.testbenches("tsmc65", UNIT8)
    assert list(benches) == ["settling", "mc_a1", "mc_a5", "mc_a10"]
    settling = benches["settling"]
    assert (settling.window_s, settling.waveform_sample_interval_s, settling.vdd) == near((4e-9, 2e-12, 1.2))
    assert [benches[name].pelgrom for name in ("mc_a1", "mc_a5", "mc_a10")] == [0.001, 0.005, 0.010]
    assert all(benches[name].mc_runs == 100 for name in ("mc_a1", "mc_a5", "mc_a10"))
    assert capdac_runs.testbenches("tsmc65", replace(UNIT8, settle_ps=1010.0))["settling"].window_s == near(4.1e-9)


def test_the_record_draws_the_dac_curves_of_the_middle_condition() -> None:
    """``results``: the metrics of every condition, the DAC's INL and DNL by code of the middle one
    (0.5 %), the settling's and the Monte Carlo runs' measurements kept."""
    measurements = {"settling": settling_run(UNIT8)}
    for name, pelgrom, delta in (("mc_a1", 0.001, 0.1), ("mc_a5", 0.005, 0.5), ("mc_a10", 0.010, 1.0)):
        main_p, diff_p, main_n, diff_n = nominal_sides(UNIT8, runs=1)
        main_p[0, 0] *= 1 + delta / 64
        main_n[0, 0] *= 1 + delta / 64
        measurements[name] = plates_meas(UNIT8, [(main_p, diff_p), (main_n, diff_n)], pelgrom=pelgrom)
    record = capdac_runs.results(measurements)
    names = [figure.name for figure in record.details]
    assert names == [
        "settling_stage",
        "model_stage",
        "mismatch_inl",
        "mismatch_gap",
        "mismatch_dac_inl",
        "dac_inl",
        "dac_dnl",
    ]
    dac_inl = next(figure for figure in record.details if figure.name == "dac_inl")
    (curve,) = dac_inl.series.values()
    assert curve[64] == near(63 * 0.5 / 127.5, rel=1e-9)  # the 0.5-unit condition's
    assert record.metrics["mc_a10_dac_inl_p95_lsb"] == near(63 / 128, rel=1e-9)
    assert record.waves == {"settling": "settling", "mc_a1": "mc_a1", "mc_a5": "mc_a5", "mc_a10": "mc_a10"}


def test_the_grid_holds_120_arrays_and_frida1_the_fabricated_one() -> None:
    """2 x 3 x 2 binary arrays (scales, resolutions, builds) and 3 x 3 x 3 x 2 x 2 redundant ones."""
    arrays = list(capdac_runs.arrays.instances("tsmc65"))
    assert len(arrays) == 12 + 108
    assert sum(params.redundancy is Redundancy.BINARY for _, params in arrays) == 12
    assert capdac_runs.frida1() == Params() and Model.weights(Params())[0] == 768


# ---- the netlist (a kit installed: the weights it draws)


def _kit(name: str) -> None:
    try:
        importlib.import_module(f"pdk.{name}.hdl21.site")
    except ImportError:
        pytest.skip(f"the {name} kit is not installed")
    h.pdk.set_default(importlib.import_module(f"pdk.{name}").pdk_logic)


@pytest.mark.parametrize("params", [UNIT8, DIFF8], ids=["unit", "strip"])
def test_the_netlist_draws_each_stages_weight_and_drives_its_plates_as_the_dac_switches(params: Params) -> None:
    """At the kit's supply V: each stage's capacitors, main less difference, are w units of the side's
    kT/C capacitance over its weight; its main plate driven by a copy of its state, its difference
    plate by the complement of its state on the difference drivers' input, its main plate sensed by
    an inverter onto dac_plate; every capacitor on the top plate."""
    _kit("tsmc65")
    supply = importlib.import_module("pdk.tsmc65.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    module = subckt.netlist(params)
    unit_f = _switched_f(params, supply) / sum(_weights(params))
    for stage, weight in enumerate(_weights(params)):
        net = 0.0
        for name, instance in module.instances.items():
            if name.startswith(f"Xc_{stage}_"):
                request = instance.of._generated_by.params
                net += request.net_f if hasattr(request, "net_f") else request.c_f
                assert instance.conns["TOP"] is module.vdac
        assert net == near(weight * unit_f, rel=1e-9)
        main = module.instances[f"drive_main_{stage}"]
        assert not main.of._generated_by.params.invert and main.conns["Y"] is module.signals[f"main_{stage}"]
        sense = module.instances[f"sense_{stage}"]
        assert sense.of._generated_by.params.invert and sense.conns["A"] is module.signals[f"main_{stage}"]
        if params.weight_impl is WeightImpl.DIFFERENCE_CAPS:
            diff = module.instances[f"drive_diff_{stage}"]
            assert diff.of._generated_by.params.invert
            assert diff.conns["A"].parent is module.ports["dac_state_diff"] and diff.conns["A"].index == stage


@pytest.mark.xfail(
    strict=True,
    reason="capdac-6: where the drivers and the arrangement do not stand still in three attempts, the "
    "netlist builds drivers sized for the loads of an arrangement it does not draw, without a word",
)
def test_drivers_that_do_not_settle_their_sizing_are_not_built_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    """``netlist``: "until the arrangement, which the drivers' widths choose, stands still". Drawn
    loads that grow 50 % each time they are drawn never stand still: the netlist either raises, or
    its drivers are those of the loads its arrangement draws (the last two sizings equal)."""
    _kit("tsmc65")
    drawn, sized = subckt._plate_loads, subckt._keys
    calls: list[object] = []

    def growing(*args, **kwargs):
        calls.append(None)
        return [(m * 1.5 ** len(calls), d if d is None else d * 1.5 ** len(calls)) for m, d in drawn(*args, **kwargs)]

    keys: list[object] = []
    monkeypatch.setattr(subckt, "_plate_loads", growing)
    monkeypatch.setattr(subckt, "_keys", lambda *a, **k: keys.append(sized(*a, **k)) or keys[-1])
    try:
        subckt.netlist(UNIT8)
    except (RuntimeError, ValueError):
        return
    assert keys[-1] == keys[-2]


@pytest.mark.xfail(
    strict=True,
    reason="capdac-11: the grid holds 14-bit arrays whose MSB drivers a slow kit cannot size within "
    "settle_ps (the FO4 chain alone takes the budget): their netlist raises, and no params.valid drops them",
)
def test_every_binary_14_bit_array_the_grid_runs_in_gf180_is_sized() -> None:
    """``runs``: each instance's "drivers sized to settle each stage within its settle_ps", in every
    kit a grid runs in (all installed kits whose ``params.valid`` admits the design). In GF180 the
    14-bit binary arrays' MSB driver tapers at FO4 from a minimum flip-flop through six inverters,
    whose five inner FO4 delays exceed the 500 ps budget: such an array is either sized or not run."""
    _kit("gf180")
    valid = getattr(importlib.import_module("flow.capdac.params"), "valid", None)
    for _label, params in capdac_runs.arrays.instances("gf180"):
        if params.bits == 14 and params.redundancy is Redundancy.BINARY and (valid is None or valid(params, "gf180")):
            subckt.netlist(params)
