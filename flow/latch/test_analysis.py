"""The latch's analyses, metrics and record on synthetic runs with known setup, delay, current and
upset, as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

import math
import warnings
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot

from . import runs
from .analysis import analyze_constraint, analyze_sr, analyze_timing, analyze_upset, metrics
from .params import (
    DATA_OFFSET_SWEEP_S,
    PERIOD_SWEEP_S,
    SUPPLY_SWEEP,
    UPSET_CHARGES_C,
    Bench,
    Params,
    Style,
    TbParams,
)
from .types import AnalysisConstraint, AnalysisSr, AnalysisTiming, AnalysisUpset, Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))
INPUTS = ("d", "s", "r", "rst", "clk", "clkb")  # the nets whose sources' currents a run saves


def approx(expected: Any, **tolerance: Any) -> Any:
    """``pytest.approx`` relative alone: 1e-6 unless ``rel`` is given, no absolute floor unless
    ``abs`` is (pytest's default floor, 1e-12, would pass any femtojoule, femtocoulomb or
    femtofarad value and blur a picosecond one), the other options passed through."""
    return pytest.approx(expected, **{"rel": 1e-6, "abs": 0.0, **tolerance})


def upset_name(charge_c: float) -> str:
    """An upset run's name, as runs.testbenches gives it."""
    return f"upset_{charge_c * 1e15:.3g}fc".replace(".", "p")


def pulse(time_s, v1, v2, period, width, delay, transition):
    """A periodic trapezoid like the testbench's pulse sources."""
    phase = np.where(time_s >= delay, (time_s - delay) % period, -1.0)
    rising = np.clip(phase / transition, 0, 1)
    falling = np.clip((phase - transition - width) / transition, 0, 1)
    return np.where(phase < 0, v1, v1 + (v2 - v1) * (rising - falling))


def measurement(tb: TbParams, time_s: np.ndarray, v: dict[str, np.ndarray], current_a: float) -> Meas:
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={**{net: np.zeros(len(time_s)) for net in INPUTS}, **v},
        i={"vdd": np.full(len(time_s), current_a), **{net: np.zeros(len(time_s)) for net in INPUTS}},
    )


def flop_run(
    offset_s: float,
    *,
    vdd: float = 1.2,
    setup_s: float = 30e-12,
    delay_s: float = 40e-12,
    step_s: float = 1e-12,
    **changes: float,
) -> Meas:
    """A flip-flop that takes d as it was setup_s before each rising edge, delay_s after that edge,
    sampled every ``step_s``."""
    tb = TbParams(params=runs.flop_rst(), vdd=vdd, data_offset_s=offset_s, **changes)
    period, transition = float(tb.clock_period_s), float(tb.transition_time_s)
    time_s = np.arange(0, float(tb.reset_time_s) + (tb.cycles + 1) * period, step_s)
    clock = pulse(time_s, 0.0, vdd, period, period / 2 - transition, period / 2, transition)
    capture = period / 2 + transition / 2
    first = max(1, math.ceil((float(tb.reset_time_s) + transition + offset_s - capture) / period))
    data = pulse(
        time_s,
        0.0,
        vdd,
        2 * period,
        period - transition,
        capture + first * period - offset_s - transition / 2,
        transition,
    )
    edges = np.arange(capture, float(time_s[-1]), period)
    taken = np.interp(edges - setup_s, time_s, data) > vdd / 2
    output = np.zeros_like(time_s)
    for edge, value in zip(edges, taken, strict=True):
        output[time_s >= edge + delay_s] = vdd * value
    return measurement(tb, time_s, {"clk": clock, "d": data, "q": output}, 30e-6)


def latch_run(offset_s: float, *, vdd: float = 1.2, setup_s: float = 30e-12, delay_s: float = 40e-12) -> Meas:
    """A latch whose q follows d, delay_s later, while clk is high, and then holds d as it was
    setup_s before the falling edge."""
    tb = TbParams(params=Params(), vdd=vdd, data_offset_s=offset_s)
    period, transition = float(tb.clock_period_s), float(tb.transition_time_s)
    time_s = np.arange(0, float(tb.reset_time_s) + (tb.cycles + 1) * period, 1e-12)
    clock = pulse(time_s, 0.0, vdd, period, period / 2 - transition, period / 2, transition)
    capture = period + transition / 2
    first = max(1, math.ceil((float(tb.reset_time_s) + transition + offset_s - capture) / period))
    data = pulse(
        time_s,
        0.0,
        vdd,
        2 * period,
        period - transition,
        capture + first * period - offset_s - transition / 2,
        transition,
    )
    output = np.zeros_like(time_s)
    for fall in np.arange(capture, float(time_s[-1]), period):
        rise = fall - period / 2
        transparent = (time_s >= rise + delay_s) & (time_s < fall + delay_s)
        output[transparent] = vdd * (np.interp(time_s[transparent] - delay_s, time_s, data) > vdd / 2)
        output[time_s >= fall + delay_s] = vdd * (np.interp(fall - setup_s, time_s, data) > vdd / 2)
    return measurement(tb, time_s, {"clk": clock, "d": data, "q": output}, 30e-6)


def sr_run(vdd: float, design: Params | None = None, delay_s: float = 25e-12) -> Meas:
    """An SR latch whose q rises delay_s after each set and falls delay_s after each reset."""
    tb = TbParams(params=runs.sr_nand() if design is None else design, vdd=vdd)
    period, transition = float(tb.data_period_s), float(tb.transition_time_s)
    time_s = np.arange(0, 3 * period, 1e-12)
    idle, active = (vdd, 0.0) if tb.params == runs.sr_nand() else (0.0, vdd)
    set_v = pulse(time_s, idle, active, period, period / 4, period / 4, transition)
    reset_v = pulse(time_s, idle, active, period, period / 4, 3 * period / 4, transition)
    phase = (time_s - period / 4 - transition / 2 - delay_s) % period
    output = np.where((time_s > period / 4) & (phase < period / 2), vdd, 0.0)
    return measurement(tb, time_s, {"s": set_v, "r": reset_v, "q": output}, 10e-6)


def upset_run(charge_c: float, critical_c: float, design: Params | None = None) -> Meas:
    """A latch holding q at 1.2 V that, struck at 2 ns, dips by 60 mV per femtocoulomb (at most to
    ground) and stays down from the critical charge on, else recovers within 0.2 ns."""
    tb = TbParams(params=runs.latch_dice() if design is None else design, bench=Bench.UPSET, charge_c=charge_c)
    time_s = np.arange(0.0, 4e-9, 1e-12)
    dip = min(1.2, 0.06 * charge_c * 1e15)
    struck = (time_s >= 2e-9) & ((time_s < 2.2e-9) | (charge_c >= critical_c))
    return measurement(tb, time_s, {"q": np.where(struck, 1.2 - dip, 1.2)}, 1e-6)


def test_flop_setup_hold_and_clock_to_q() -> None:
    offsets = [round(value * 1e-12, 15) for value in (-100, -50, 0, 20, 40, 60, 100, 200)]
    sweep = [flop_run(offset) for offset in offsets]
    timing = analyze_timing(sweep)
    passing = timing.data_offset_s > 30e-12
    assert np.all(timing.captured_fraction[passing] == 1.0) and np.all(timing.held_fraction[~passing] == 1.0)
    assert timing.delay_rise_s[passing] == approx(40e-12, abs=2e-12)
    assert timing.delay_fall_s[passing] == approx(40e-12, abs=2e-12)
    assert timing.energy_per_cycle_j == approx(1.2 * 30e-6 * 2e-9)
    constraint = analyze_constraint(sweep, timing=timing)
    assert constraint.setup_s == approx(40e-12)
    assert constraint.hold_s == approx(-20e-12)
    assert constraint.delay_rise_s == approx(40e-12, abs=2e-12)
    with pytest.raises(ValueError, match="data offset sweep"):
        analyze_constraint(sweep[:2], timing=analyze_timing(sweep[:2]))
    with pytest.raises(ValueError, match="clocked"):
        analyze_timing([sr_run(1.2)])


def test_sr_set_and_reset_delays() -> None:
    for design in (runs.sr_nand(), runs.sr_nor()):
        result = analyze_sr([sr_run(1.0, design), sr_run(1.2, design)])
        assert result.delay_rise_s == approx([25e-12, 25e-12], abs=2e-12)
        assert result.delay_fall_s == approx([25e-12, 25e-12], abs=2e-12)
        assert result.energy_per_cycle_j == approx(np.array([1.0, 1.2]) * 10e-6 * 5.2e-9)
    with pytest.raises(ValueError, match="SR latch"):
        analyze_sr([flop_run(0.5e-9)])


def test_upset_critical_charge_and_dip() -> None:
    upset = analyze_upset([upset_run(charge * 1e-15, 20e-15) for charge in (50, 5, 10, 20)])
    assert upset.charge_c == approx([5e-15, 10e-15, 20e-15, 50e-15])
    assert list(upset.upset_fraction) == [0.0, 0.0, 1.0, 1.0]
    assert upset.dip_v == approx([0.3, 0.6, 1.2, 1.2])
    # the critical charge lies between the largest recovered strike and the smallest flipping one
    assert (upset.critical_charge_c, upset.flip_charge_c) == approx((10e-15, 20e-15))
    alone = analyze_upset([upset_run(5e-15, 20e-15)])
    assert alone.critical_charge_c == approx(5e-15) and math.isnan(alone.flip_charge_c)
    with pytest.raises(ValueError, match="upset bench"):
        analyze_upset([flop_run(0.2e-9)])


def test_the_metrics_take_the_nominal_supply_and_what_the_design_ran() -> None:
    """A flip-flop's record: its delays and energy at the nominal supply, its setup and hold, the
    highest clock frequency at which every edge captures; no critical charge."""
    supply = analyze_timing([flop_run(0.5e-9, vdd=1.2 * factor, delay_s=40e-12 / factor) for factor in SUPPLY_SWEEP])
    sweep = [flop_run(offset) for offset in (-100e-12, 0.0, 20e-12, 40e-12, 100e-12)]
    period = analyze_timing(
        [
            flop_run(value / 2, clock_period_s=value, transition_time_s=3.75e-12, reset_time_s=1e-9, cycles=12)
            for value in (1e-9, 500e-12, 300e-12)
        ]
    )
    found = metrics(supply=supply, constraint=analyze_constraint(sweep, timing=analyze_timing(sweep)), period=period)
    assert isinstance(found, Metrics)
    assert found.delay_rise_s == approx(40e-12, abs=2e-12)
    assert found.delay_max_supply_s == approx(40e-12 / 0.9, abs=2e-12)
    assert found.energy_per_cycle_j == approx(1.2 * 30e-6 * 2e-9)
    assert (found.setup_s, found.hold_s) == approx((40e-12, -20e-12))
    assert found.fmax_hz == approx(1 / 300e-12) and math.isnan(found.critical_charge_c)
    alone = metrics(supply=analyze_sr([sr_run(1.2 * factor) for factor in SUPPLY_SWEEP]))
    assert alone.delay_fall_s == approx(25e-12, abs=2e-12)
    unmeasured = (alone.setup_s, alone.hold_s, alone.fmax_hz, alone.captured_1mhz_fraction, alone.critical_charge_c)
    assert all(math.isnan(value) for value in unmeasured)


def test_the_record_holds_the_metrics_and_each_sweeps_plots() -> None:
    """``results`` from one instance's runs, by the names ``testbenches`` gives them: a flip-flop's
    (supply, data offset, clock period), an SR latch's (supply) and a struck latch's."""
    flop = {f"supply_{round(factor * 100)}": flop_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP}
    # the offset runs' flip-flop takes d as it was 35 ps before the edge, between grid points
    flop |= {f"offset_{round(offset * 1e12)}ps": flop_run(offset, setup_s=35e-12) for offset in DATA_OFFSET_SWEEP_S}
    flop |= {
        f"period_{round(value * 1e12)}ps": flop_run(
            value / 2,
            clock_period_s=value,
            transition_time_s=min(PERIOD_SWEEP_S) / 8,
            reset_time_s=value * max(2, math.ceil(0.5e-9 / value)),
            cycles=12,
        )
        for value in PERIOD_SWEEP_S
    }
    flop["slow_1mhz"] = flop_run(0.5e-6, clock_period_s=1e-6, cycles=4, step_s=100e-12)
    record = runs.results(flop)
    assert set(record.metrics) == set(Metrics.__dataclass_fields__)
    # d crossing 30 ps before the edge is held, 40 ps before it taken: setup 40 ps (the failing
    # offset captured nothing, so the grid's), hold -30 ps; the period runs' flip-flop, 30 ps
    assert record.metrics["setup_s"] == approx(40e-12) and record.metrics["hold_s"] == approx(-30e-12)
    assert record.metrics["captured_1mhz_fraction"] == 1.0
    # data half a period ahead: every period whose half exceeds the 30 ps setup works, down to the
    # grid's 63 ps
    assert record.metrics["fmax_hz"] == approx(1 / 63e-12)
    assert all(isinstance(detail, Plot) and len(detail.series) == 1 for detail in record.details)
    assert [detail.name for detail in record.details] == [
        *("delay_rise_supply", "delay_fall_supply", "energy_supply"),
        *("delay_rise_offset", "delay_fall_offset", "captured_offset", "held_offset"),
        *("captured_frequency", "delay_rise_frequency", "delay_fall_frequency"),
    ]
    assert record.waves == {"nominal": "supply_100"}

    sr = runs.results({f"supply_{round(factor * 100)}": sr_run(1.2 * factor) for factor in SUPPLY_SWEEP})
    assert [detail.name for detail in sr.details] == ["delay_rise_supply", "delay_fall_supply", "energy_supply"]
    assert sr.metrics["delay_rise_s"] == approx(25e-12, abs=2e-12) and math.isnan(sr.metrics["fmax_hz"])

    # a struck C2MOS latch: the upset plots, and the strike that flips it among the waves
    latch = {f"supply_{round(factor * 100)}": latch_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP}
    latch |= {f"offset_{round(offset * 1e12)}ps": latch_run(offset, setup_s=35e-12) for offset in DATA_OFFSET_SWEEP_S}
    latch |= {upset_name(charge): upset_run(charge, 20e-15, Params()) for charge in UPSET_CHARGES_C}
    struck = runs.results(latch)
    assert struck.metrics["delay_rise_s"] == approx(40e-12, abs=2e-12)
    assert struck.metrics["setup_s"] == approx(40e-12) and struck.metrics["hold_s"] == approx(-30e-12)
    # flipping from 20 fC: of the 10 % grid's 19.2 and 21.1 fC, the one recovers and the other flips
    assert struck.metrics["critical_charge_c"] == approx(19.2e-15)
    assert struck.metrics["flip_charge_c"] == approx(21.1e-15)
    assert [detail.name for detail in struck.details][-2:] == ["dip_charge", "upset_charge"]
    assert struck.waves == {"nominal": "supply_100", "21.1 fC strike": "upset_21p1fc"}


# Closed-form validation. Each run below is built from signals whose answer follows on paper: a
# clock and data as the timing bench drives them (trapezoids, sim.testbench), q a single-pole
# response starting a known dead time after the event that moves it, the supply current a known
# leakage plus a known charge per cycle, a strike's dip a normalized double exponential of known
# peak. Every run is sampled on a variable-step axis as Spectre writes one (steps drawn between 0.3
# and 1.7 ps), and every expected value is derived from the closed form, not from the analysis.
#
# Sampling tolerances, stated once: the clock's and data's mid-supply crossings lie on linear
# ramps, at least a few picoseconds from a corner, so linear interpolation finds them exactly. q's
# crossing of mid-supply on a single pole V (1 - exp(-t / tau)) is off by at most the linear
# interpolation error over that crossing's step h divided by the slope there: |q''| h^2 / 8 over
# |q'|, h^2 / (8 tau), under 0.04 ps for h = 1.7 ps and tau = 10 ps; delays are checked to 0.1 ps.
# The supply's charge pulses are Gaussians of sigma 5 ps, so the trapezoidal average over steps of
# at most 0.34 sigma is within 1e-4 of the integral, and the tail of a pulse past four sigma holds
# 3e-5 of its charge; currents and energies are checked to 1e-3 relative.

STEP_MIN_S, STEP_MAX_S = 0.3e-12, 1.7e-12
DEAD_S = 20e-12  # from the event that moves q to the start of q's single-pole response
TAU_RISE_S, TAU_FALL_S = 10e-12, 15e-12
LEAKAGE_A, CHARGE_C, SIGMA_S = 1e-6, 10e-15, 5e-12


def simulator_axis(stop_s: float, seed: int = 1) -> np.ndarray:
    """Time points from 0 to ``stop_s``, its steps drawn uniformly between 0.3 and 1.7 ps (a mean
    of 1 ps), as a variable-step simulator writes them."""
    steps = np.random.default_rng(seed).uniform(STEP_MIN_S, STEP_MAX_S, int(1.2 * stop_s / 1e-12) + 100)
    time_s = np.r_[0.0, np.cumsum(steps)]
    return np.r_[time_s[time_s < stop_s], stop_s]


def single_pole(
    time_s: np.ndarray, steps: list[tuple[float, float]], *, initial: float, tau_rise_s: float, tau_fall_s: float
) -> np.ndarray:
    """A single-pole response: from ``initial``, toward each (onset, level) of ``steps`` in turn,
    v(t) = level + (v(onset) - level) exp(-(t - onset) / tau), tau that of its direction."""
    output = np.full(len(time_s), float(initial))
    start = float(initial)
    ends = [onset for onset, _ in steps[1:]] + [math.inf]
    for (onset, level), end in zip(steps, ends, strict=True):
        tau = tau_rise_s if level > start else tau_fall_s
        span = (time_s >= onset) & (time_s < end)
        output[span] = level + (start - level) * np.exp(-(time_s[span] - onset) / tau)
        if math.isfinite(end):
            start = level + (start - level) * math.exp(-(end - onset) / tau)
    return output


def charge_pulses(time_s: np.ndarray, instants: np.ndarray, *, charge_c: float, leakage_a: float) -> np.ndarray:
    """A supply current: ``leakage_a`` and, after each instant, a Gaussian pulse of ``charge_c``,
    sigma ``SIGMA_S`` wide and centred four sigma after it."""
    current = np.full(len(time_s), leakage_a)
    for instant in instants:
        shape = np.exp(-0.5 * ((time_s - instant - 4 * SIGMA_S) / SIGMA_S) ** 2)
        current += charge_c / (math.sqrt(2 * math.pi) * SIGMA_S) * shape
    return current


def timing_stimulus(tb: TbParams, time_s: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The timing bench's clk and d (sim.testbench) on ``time_s``, clk's rising mid-supply
    crossings and d's (rising first, then alternating)."""
    vdd, period, transition = float(tb.vdd), float(tb.clock_period_s), float(tb.transition_time_s)
    clock = pulse(time_s, 0.0, vdd, period, period / 2 - transition, period / 2, transition)
    capture = period / 2 + transition / 2 + (0.0 if tb.params.flop else period / 2)
    offset = float(tb.data_offset_s)
    first = max(1, math.ceil((float(tb.reset_time_s) + transition + offset - capture) / period))
    delay = capture + first * period - offset - transition / 2
    data = pulse(time_s, 0.0, vdd, 2 * period, period - transition, delay, transition)
    rises = np.arange(period / 2 + transition / 2, float(time_s[-1]), period)
    return clock, data, rises, np.arange(delay + transition / 2, float(time_s[-1]), period)


def data_level(data_edges: np.ndarray, at: float, vdd: float) -> float:
    """d at ``at``: high after an odd number of its crossings (the first rises)."""
    return vdd * (int(np.sum(data_edges <= at)) % 2)


def timing_meas(
    tb: TbParams,
    time_s: np.ndarray,
    clock: np.ndarray,
    data: np.ndarray,
    q: np.ndarray,
    i: np.ndarray,
    clock_i: np.ndarray | None = None,
):
    """A timing run's measurement: the inputs' sources deliver no current but ``clock_i`` on clk;
    the inputs the run does not drive (s, r, rst) at ground."""
    vdd = float(tb.vdd)
    inputs = {net: np.zeros(len(time_s)) for net in INPUTS}
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={**inputs, "clk": clock, "clkb": vdd - clock, "d": data, "q": q, "qb": vdd - q},
        i={"vdd": i, **inputs, **({} if clock_i is None else {"clk": clock_i})},
    )


def flop_model(
    offset_s: float,
    *,
    design: Params | None = None,
    aperture_s: float = -15e-12,
    pushout_s: float = 0.0,
    pushout_scale_s: float = 20e-12,
    stuck: bool = False,
    dead_s: float = DEAD_S,
    leak_s: float = math.inf,
    clock_charge_c: float = 0.0,
    step_s: float | None = None,
    vdd: float = 1.2,
    **changes: Any,
) -> Meas:
    """A flip-flop that at each rising clk crossing t_k takes d as it is at t_k - ``aperture_s``
    (negative: after the edge) and drives q toward it from t_k + ``dead_s`` + ``pushout_s`` exp(-m /
    ``pushout_scale_s``), m the time from the data change it took to the aperture; a divider
    (``design``) toggles instead, from the first edge after rst falls (with a reset; q held low
    until then); ``stuck``, q stays low; a finite ``leak_s``, q decays toward
    ground with that time constant from each edge's onset on (a dynamic node losing its state).
    The supply delivers LEAKAGE_A and CHARGE_C after each rising edge, the clock's source
    ``clock_charge_c`` after each rising edge and takes it back after each falling one. Sampled on a
    variable-step axis, or every ``step_s``."""
    tb = TbParams(params=runs.flop_rst() if design is None else design, vdd=vdd, data_offset_s=offset_s, **changes)
    time_s = simulator_axis(tb.stop_s) if step_s is None else np.r_[np.arange(0.0, tb.stop_s, step_s), tb.stop_s]
    clock, data, rises, data_edges = timing_stimulus(tb, time_s)
    margin = offset_s - aperture_s if offset_s > aperture_s else offset_s - aperture_s + float(tb.clock_period_s)
    onset = dead_s + pushout_s * math.exp(-margin / pushout_scale_s)
    released = float(tb.reset_time_s) + float(tb.transition_time_s) / 2 if tb.params.reset else 0.0
    steps, level = [], 0.0
    for edge in rises:
        if tb.params.divider and edge <= released:
            continue
        level = vdd - level if tb.params.divider else data_level(data_edges, edge - aperture_s, vdd)
        steps.append((float(edge) + onset, 0.0 if stuck else level))
    q = single_pole(time_s, steps, initial=0.0, tau_rise_s=TAU_RISE_S, tau_fall_s=TAU_FALL_S)
    if math.isfinite(leak_s):
        onsets = np.asarray([step for step, _ in steps])
        since = time_s - np.r_[0.0, onsets][np.searchsorted(onsets, time_s, side="right")]
        q = q * np.exp(-np.maximum(since - 5 * TAU_FALL_S, 0.0) / leak_s)
    current = charge_pulses(time_s, rises, charge_c=CHARGE_C, leakage_a=LEAKAGE_A)
    falls = rises + float(tb.clock_period_s) / 2
    clock_i = charge_pulses(time_s, rises, charge_c=clock_charge_c, leakage_a=0.0) - charge_pulses(
        time_s, falls[falls < float(time_s[-1]) - 8 * SIGMA_S], charge_c=clock_charge_c, leakage_a=0.0
    )
    return timing_meas(tb, time_s, clock, data, q, current, clock_i)


def latch_model(offset_s: float, *, aperture_s: float = 10e-12, vdd: float = 1.2) -> Meas:
    """A C2MOS latch transparent from each rising clk crossing r_k to ``aperture_s`` before the
    falling one that follows, f_k: q moves toward d DEAD_S after d changes in that window (after
    r_k, for a change while it was opaque) with a single pole, and holds otherwise."""
    tb = TbParams(params=Params(), vdd=vdd, data_offset_s=offset_s)
    period = float(tb.clock_period_s)
    time_s = simulator_axis(tb.stop_s)
    clock, data, rises, data_edges = timing_stimulus(tb, time_s)
    steps, level = [], 0.0
    for rise in rises:
        close = rise + period / 2 - aperture_s
        if (opening := data_level(data_edges, rise, vdd)) != level:
            steps.append((float(rise) + DEAD_S, opening))
            level = opening
        for edge in data_edges[(data_edges > rise) & (data_edges < close)]:
            level = data_level(data_edges, edge, vdd)
            steps.append((float(edge) + DEAD_S, level))
    q = single_pole(time_s, steps, initial=0.0, tau_rise_s=TAU_RISE_S, tau_fall_s=TAU_FALL_S)
    current = charge_pulses(time_s, rises, charge_c=CHARGE_C, leakage_a=LEAKAGE_A)
    return timing_meas(tb, time_s, clock, data, q, current)


# [Baker] Eq. (10.17), p. 333: an RC's delay to the 50 % point, 0.7 RC (ln 2 of a single pole)
# [Razavi-PLL] Fig. 13.40, p. 424: CK-to-Q delay
# A flip-flop that starts q's single pole DEAD_S after the clock's mid-supply crossing reaches
# mid-supply tau ln 2 later: the CK-to-Q delay is DEAD_S + tau ln 2, 26.93 ps rising (tau 10 ps)
# and 30.40 ps falling (tau 15 ps). With d 0.5 ns ahead every edge takes the new value.
# [Baker] Eq. (11.14), p. 355: the average current, the charge a period over the period
# [Baker] Eq. (11.15), p. 355: the average power, V_DD I_avg
# The supply delivers LEAKAGE_A and CHARGE_C a cycle, so I_DD = LEAKAGE_A + CHARGE_C / T_CK = 6 uA
# and the energy a cycle V_DD I_DD T_CK = V_DD (LEAKAGE_A T_CK + CHARGE_C): 14.4 fJ at 1.2 V.
def test_closed_form_flop_clock_to_q_current_and_energy() -> None:
    timing = analyze_timing([flop_model(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
    assert timing.delay_rise_s == approx(np.full(3, DEAD_S + TAU_RISE_S * math.log(2)), abs=1e-13)
    assert timing.delay_fall_s == approx(np.full(3, DEAD_S + TAU_FALL_S * math.log(2)), abs=1e-13)
    assert list(timing.captured_fraction) == [1.0] * 3 and list(timing.held_fraction) == [0.0] * 3
    assert timing.idd_a == approx(np.full(3, LEAKAGE_A + CHARGE_C / 2e-9), rel=1e-3)
    supply_v = 1.2 * np.asarray(SUPPLY_SWEEP)
    assert timing.energy_per_cycle_j == approx(supply_v * (LEAKAGE_A * 2e-9 + CHARGE_C), rel=1e-3)
    assert list(timing.vdd_v) == approx(list(supply_v))


# [Baker] Eq. (11.14), p. 355: a CMOS driver supplies current from V_DD only while its PMOS is on,
# the charge it puts on its load each period
# The clock's ideal source delivers CLOCK_C into clk at each rising edge and takes it back at each
# falling one. A CMOS driver on V_DD would draw the delivered charge from V_DD and sink the returned
# one to ground, so the drivers' current is CLOCK_C / T_CK = 2.5 uA (5 fC every 2 ns), the cell's
# own I_DD unchanged, and the energy a cycle V_DD (LEAKAGE_A T_CK + CHARGE_C + CLOCK_C) =
# 1.2 V x (1 uA x 2 ns + 10 fC + 5 fC) = 1.2 V x 17 fC = 20.4 fJ. The window runs from the first
# event to the last, whole periods, so each holds one rising and one falling clock edge.
def test_closed_form_the_energy_counts_the_inputs_drivers() -> None:
    clock_c = 5e-15
    timing = analyze_timing([flop_model(0.5e-9, clock_charge_c=clock_c)])
    assert timing.idd_drivers_a[0] == approx(clock_c / 2e-9, rel=1e-3)
    assert timing.idd_a[0] == approx(LEAKAGE_A + CHARGE_C / 2e-9, rel=1e-3)
    assert timing.energy_per_cycle_j[0] == approx(1.2 * (LEAKAGE_A * 2e-9 + CHARGE_C + clock_c), rel=1e-3)
    assert timing.energy_per_cycle_j[0] == approx(20.4e-15, rel=1e-3)


def ringing(meas: Meas, amplitude_a: float, *, clock_leak_a: float = 0.0) -> Meas:
    """``meas`` with every input source's current, and the supply's, alternating +/-``amplitude_a``
    from one written point to the next on top of its own (a simulator's numerical ringing, of zero
    mean), and ``clock_leak_a`` more flowing out of clk's source into the cell throughout."""
    alternating = amplitude_a * (-1.0) ** np.arange(len(meas.time_s))
    currents = {net: current + alternating for net, current in meas.i.items()}
    currents["clk"] = currents["clk"] + clock_leak_a
    return replace(meas, i=currents)


# [Baker] Eq. (11.14), p. 355: a CMOS driver supplies current from V_DD only while its PMOS is on
# Every input source's current and the supply's carry a ringing of +/-3 uA, alternating at every
# written point, and clk's source a constant 0.4 uA into the cell besides its 5 fC a rising edge
# (taken back a falling one). A driver's pull-up conducts from each rising ramp's start (the
# mid-supply crossing less half the 50 ps transition) to the next falling ramp's start: on clk
# exactly T/2 of each period, so over the whole periods from the first event to the last the
# drivers' current is CLOCK_C / T + 0.4 uA / 2 = 2.5 + 0.2 = 2.7 uA, the cell's I_DD unchanged at
# LEAKAGE_A + CHARGE_C / T = 6 uA. The ringing's trapezoidal integral is (A - A) h / 2 = 0 over
# each whole step; where a span ends inside a step, of length h, a fraction f of it, the part
# left is A f (1 - f) h <= A h / 4 = 1.3 aC (h <= 1.7 ps). Each period holds at most five span
# ends (clk's two, clkb's two, d's one), 6.4 aC, 3.2 nA over 2 ns: 1.2e-3 of 2.7 uA, checked to
# 2e-3. The positive part alone, as a rectifier counts it, would add A / 2 = 1.5 uA an input.
def test_closed_form_the_drivers_current_cancels_ringing_and_counts_the_pull_up_alone() -> None:
    clock_c, ringing_a, leak_a = 5e-15, 3e-6, 0.4e-6
    timing = analyze_timing([ringing(flop_model(0.5e-9, clock_charge_c=clock_c), ringing_a, clock_leak_a=leak_a)])
    assert timing.idd_drivers_a[0] == approx(clock_c / 2e-9 + leak_a / 2, rel=2e-3)
    assert timing.idd_a[0] == approx(LEAKAGE_A + CHARGE_C / 2e-9, rel=1e-3)
    assert timing.energy_per_cycle_j[0] == approx(
        1.2 * (LEAKAGE_A * 2e-9 + CHARGE_C + clock_c + leak_a * 1e-9), rel=1e-3
    )


# The SR latch's set source, ringing +/-3 uA at every point as every input's and the supply's, still
# delivers CHARGE_C a set and reset period while its driver's pull-up conducts: the drivers' current
# CHARGE_C / T = 1.923 uA at each supply (NAND and NOR), the ringing's residue under A h / 4 = 1.3 aC
# at each of the four span ends a period (s's two, r's two): 5.1 aC over 5.2 ns, 1 nA, 5e-4 of it.
def test_closed_form_sr_drivers_current_cancels_ringing() -> None:
    for design in (runs.sr_nand(), runs.sr_nor()):
        result = analyze_sr([ringing(sr_model(design, vdd=1.2 * factor), 3e-6) for factor in SUPPLY_SWEEP])
        assert result.idd_drivers_a == approx(np.full(3, CHARGE_C / 5.2e-9), rel=2e-3)
        assert result.idd_a == approx(np.full(3, LEAKAGE_A + 2 * CHARGE_C / 5.2e-9), rel=1e-3)


# A latch's path to q opens at the rising clk edge; d crossing mid-supply 0.5 ns before the closing
# (falling) edge comes 0.55 ns after the opening one, so the launch is d's crossing and the delay
# from it is DEAD_S + tau ln 2, as the flip-flop's.
# [Baker] Eq. (10.17), p. 333: an RC's delay to the 50 % point, 0.7 RC
def test_closed_form_latch_delay_runs_from_the_data_while_transparent() -> None:
    timing = analyze_timing([latch_model(0.5e-9)])
    assert timing.delay_rise_s[0] == approx(DEAD_S + TAU_RISE_S * math.log(2), abs=1e-13)
    assert timing.delay_fall_s[0] == approx(DEAD_S + TAU_FALL_S * math.log(2), abs=1e-13)
    assert (timing.captured_fraction[0], timing.held_fraction[0]) == (1.0, 0.0)
    # the events (falling crossings) a whole number of periods apart: I_DD = LEAKAGE_A + CHARGE_C / T_CK
    assert timing.idd_a[0] == approx(LEAKAGE_A + CHARGE_C / 2e-9, rel=1e-3)
    # d changing 50 ps after the latch closed (10 ps before the falling crossing) leaves the old value
    late = analyze_timing([latch_model(-50e-12)])
    assert (late.captured_fraction[0], late.held_fraction[0]) == (0.0, 1.0)
    assert math.isnan(late.delay_rise_s[0]) and math.isnan(late.delay_fall_s[0])


# A divider toggles q at each rising edge: launch at the clock, delay DEAD_S + tau ln 2; one that
# never toggles keeps the old value at every edge.
def test_closed_form_divider_toggles_and_a_stuck_one_holds() -> None:
    toggling = analyze_timing([flop_model(0.5e-9, design=runs.div2())])
    assert toggling.delay_rise_s[0] == approx(DEAD_S + TAU_RISE_S * math.log(2), abs=1e-13)
    assert toggling.delay_fall_s[0] == approx(DEAD_S + TAU_FALL_S * math.log(2), abs=1e-13)
    assert (toggling.captured_fraction[0], toggling.held_fraction[0]) == (1.0, 0.0)
    stuck = analyze_timing([flop_model(0.5e-9, design=runs.div2(), stuck=True)])
    assert (stuck.captured_fraction[0], stuck.held_fraction[0]) == (0.0, 1.0)
    assert math.isnan(stuck.delay_rise_s[0]) and math.isnan(stuck.delay_fall_s[0])


# not in the reference texts: a divider's edge is captured where q toggles within 0.95 T_CK of it,
# its old value the one the edges before it set in turn
# A TSPC divider (no reset: q starts low, and toggles from the first edge on) at T_CK = 100 ps
# whose q answers each rising edge t_k with a single pole from t_k + t_d: q crosses mid-supply
# t_d + tau ln 2 after the edge (the previous toggle's tail, e^{-(T_CK - t_d) / tau} of the swing,
# shifts it by under 0.06 ps). With t_d = DEAD_S, 26.93 ps rising and 30.40 ps falling, both
# before the sample instant 0.95 T_CK = 95 ps after the edge: every edge captured, the delays
# t_d + tau ln 2. With t_d = 120 ps, 126.93 and 130.40 ps, between T_CK and 2 T_CK: each edge's
# toggle lands in the next edge's window, so at every launch q still shows the value from two
# edges back and no edge is captured (a window read alone would pair each edge with the toggle
# of the one before and report 26.93 and 30.40 ps, the lag less T_CK). With t_d = 92 ps, 98.93 and
# 102.40 ps, past 0.95 T_CK: no edge either. The divider with reset, q held low until rst falls,
# the same.
def test_closed_form_divider_late_by_more_than_a_period_is_not_captured() -> None:
    fast = {"clock_period_s": 100e-12, "transition_time_s": min(PERIOD_SWEEP_S) / 8, "cycles": 12}
    for design in (runs.div2_tspc(), runs.div2()):
        settled = analyze_timing([flop_model(50e-12, design=design, **fast)])
        assert settled.captured_fraction[0] == 1.0
        assert settled.delay_rise_s[0] == approx(DEAD_S + TAU_RISE_S * math.log(2), abs=1e-13)
        assert settled.delay_fall_s[0] == approx(DEAD_S + TAU_FALL_S * math.log(2), abs=1e-13)
        for dead_s in (120e-12, 92e-12):
            late = analyze_timing([flop_model(50e-12, design=design, dead_s=dead_s, **fast)])
            assert late.captured_fraction[0] == 0.0
            assert math.isnan(late.delay_rise_s[0]) and math.isnan(late.delay_fall_s[0])


# [Baker] Fig. 10.9, p. 333: t_PLH and t_PHL, between the 50 % points
# not in the reference texts: a divider's q read 0.05 T_CK before its clock edge, so that a toggle
# on the clock's ramp, ahead of its mid-supply crossing, is that edge's
# A TSPC divider at T_CK = 2 ns (50 ps edges) whose q starts its single pole t_d = -7.43 ps from
# each rising edge's mid-supply crossing, on the clock's ramp (which starts 25 ps before it): q
# crosses mid-supply t_d + tau ln 2 from the edge, -0.50 ps rising (tau 10 ps) and 2.97 ps falling
# (tau 15 ps). Every edge toggles q, so every edge is captured, the rising delay negative. The same
# divider at a 1 MHz clock written every 100 ps (the slow run's strobe), q's toggle between two
# written points around the edge: read 50 ns before each edge, every edge is captured.
def test_closed_form_divider_toggling_on_the_clocks_ramp() -> None:
    early = analyze_timing([flop_model(0.5e-9, design=runs.div2_tspc(), dead_s=-7.43e-12)])
    assert early.captured_fraction[0] == 1.0
    assert early.delay_rise_s[0] == approx(-7.43e-12 + TAU_RISE_S * math.log(2), abs=1e-13)
    assert early.delay_fall_s[0] == approx(-7.43e-12 + TAU_FALL_S * math.log(2), abs=1e-13)
    slow = {"clock_period_s": 1e-6, "cycles": 4, "step_s": 100e-12}
    coarse = analyze_timing([flop_model(0.5e-6, design=runs.div2_tspc(), dead_s=-7.43e-12, **slow)])
    assert coarse.captured_fraction[0] == 1.0


# Edge cases of a flip-flop's run at T_CK = 2 ns (8 cycles after a 0.5 ns reset): the events are
# the rising crossings after reset + T_CK / 2 = 1.5 ns that have a rising crossing after them, at
# 3.025, 5.025, ..., 15.025 ns (seven). d first rises before the first of them and toggles every
# cycle, so the new values alternate 1, 0, 1, 0, 1, 0, 1. A q that never leaves ground never moves
# from the old value to the new one, so no edge is captured (where the new value is 0, q was there
# already); it ends at the old value, 0, at the four edges whose new value is 1: held 4/7, no delay
# either way. Data 100 ps after the edge (85 ps past a 15 ps aperture) is held at every edge.
def test_closed_form_flop_edge_cases_stuck_and_late_data() -> None:
    stuck = analyze_timing([flop_model(0.5e-9, stuck=True)])
    assert stuck.captured_fraction[0] == 0.0 and stuck.held_fraction[0] == approx(4 / 7)
    assert math.isnan(stuck.delay_rise_s[0]) and math.isnan(stuck.delay_fall_s[0])
    late = analyze_timing([flop_model(-100e-12)])
    assert (late.captured_fraction[0], late.held_fraction[0]) == (0.0, 1.0)


# A run whose clock never crosses mid-supply has no capturing edge: the shares of zero events are
# 0/0, undefined (NaN), as are its delays and its current (no two events to average between).
def test_closed_form_a_run_without_clock_edges_has_no_fractions() -> None:
    run = flop_model(0.5e-9)
    flat = replace(run, v={**run.v, "clk": np.zeros_like(run.time_s), "clkb": np.full_like(run.time_s, 1.2)})
    timing = analyze_timing([flat])
    assert math.isnan(timing.delay_rise_s[0]) and math.isnan(timing.idd_a[0])
    assert math.isnan(timing.captured_fraction[0]) and math.isnan(timing.held_fraction[0])


# [Baker] Fig. 13.25, p. 401: D FF setup time
# [Baker] Fig. 13.26, p. 402: D FF hold time
# not in the reference texts: setup at a 10 % CK-to-Q pushout (standard-cell characterization)
# The flip-flop samples d 15 ps after the edge (aperture -15 ps) and its CK-to-Q delay grows by
# P exp(-(o - a) / L) as d's offset o nears the aperture a (P = 40 ps, L = 20 ps), over a base
# t0 = DEAD_S + tau ln 2. Against the delay at the largest offset o_max, the 10 % pushout bound
# t0 + P e^{-(o - a)/L} <= 1.1 (t0 + P e^{-(o_max - a)/L}) holds from
# o* = a + L ln(P / (0.1 t0 + 1.1 P e^{-(o_max - a)/L})): 38.96 ps rising (t0 26.93 ps), 36.54 ps
# falling (t0 30.40 ps). On the 10 ps grid the 30 ps offset captures with its delay pushed out past
# the bound and the 40 ps one passes, so the setup is the bound's crossing on the line through the
# delays at 30 and 40 ps: 40 - 10 (1.1 d(o_max) - d(40)) / (d(30) - d(40)), 39.18 ps rising and
# 37.09 ps falling, the later of the two 39.18 ps, 0.22 ps past the exponential's own crossing
# (the line lies above a convex curve). d changing later than the aperture is held: every offset
# below -15 ps, so the hold is minus the largest such grid offset, 20 ps (at most one grid step
# above the aperture's 15 ps).
def test_closed_form_setup_at_the_pushout_and_hold_at_the_aperture() -> None:
    aperture, pushout, scale = -15e-12, 40e-12, 20e-12
    sweep = [flop_model(offset, aperture_s=aperture, pushout_s=pushout) for offset in DATA_OFFSET_SWEEP_S]
    timing = analyze_timing(sweep)
    constraint = analyze_constraint(sweep, timing=timing)
    largest = max(DATA_OFFSET_SWEEP_S)
    crossing, line = [], []
    for tau in (TAU_RISE_S, TAU_FALL_S):
        base = DEAD_S + tau * math.log(2)
        crossing.append(
            aperture
            + scale * math.log(pushout / (0.1 * base + 1.1 * pushout * math.exp(-(largest - aperture) / scale)))
        )

        def delay(offset: float, base: float = base) -> float:
            return base + pushout * math.exp(-(offset - aperture) / scale)

        line.append(40e-12 - 10e-12 * (1.1 * delay(largest) - delay(40e-12)) / (delay(30e-12) - delay(40e-12)))
    assert crossing == approx([38.96e-12, 36.54e-12], abs=0.01e-12)
    assert line == approx([39.18e-12, 37.09e-12], abs=0.01e-12)
    assert constraint.setup_s == approx(max(line), abs=0.05e-12)
    assert 0 < constraint.setup_s - max(crossing) < 0.3e-12
    assert constraint.hold_s == approx(-max(o for o in DATA_OFFSET_SWEEP_S if o < aperture))
    assert constraint.hold_s == approx(20e-12)
    # the delays the setup is judged against: at the largest offset, without measurable pushout
    assert constraint.delay_rise_s == approx(DEAD_S + TAU_RISE_S * math.log(2), abs=1e-13)
    assert constraint.delay_fall_s == approx(DEAD_S + TAU_FALL_S * math.log(2), abs=1e-13)
    # each captured offset's delay is the closed form's, pushout included
    captured = timing.data_offset_s > aperture
    expected = (
        DEAD_S + TAU_RISE_S * math.log(2) + pushout * np.exp(-(timing.data_offset_s[captured] - aperture) / scale)
    )
    assert timing.delay_rise_s[captured] == approx(expected, abs=1e-13)


# Edge cases of the constraint: NaN where the sweep has no boundary. A flip-flop whose aperture lies
# past the largest offset (400 ps before the edge) never captures and holds at every offset: no
# setup and no hold. Offsets from 0 up, past the 15 ps aperture after the edge and without
# pushout, all capture and none holds: no boundary either. A flip-flop sampling 5 ps before its
# edge holds at offset 0 and captures from 10 ps on: its hold is 0 - 0, a positive zero.
def test_closed_form_constraint_outside_the_sweep() -> None:
    never = [flop_model(offset, aperture_s=400e-12) for offset in DATA_OFFSET_SWEEP_S]
    found = analyze_constraint(never, timing=analyze_timing(never))
    assert math.isnan(found.setup_s) and math.isnan(found.hold_s)
    always = [flop_model(offset) for offset in DATA_OFFSET_SWEEP_S if offset >= 0]
    found = analyze_constraint(always, timing=analyze_timing(always))
    assert math.isnan(found.setup_s) and math.isnan(found.hold_s)
    edge = [flop_model(offset, aperture_s=5e-12) for offset in DATA_OFFSET_SWEEP_S if offset <= 50e-12]
    found = analyze_constraint(edge, timing=analyze_timing(edge))
    assert found.hold_s == 0.0 and math.copysign(1.0, found.hold_s) == 1.0
    assert found.setup_s == approx(10e-12)
    with pytest.raises(ValueError, match="one supply"):
        mixed = [flop_model(offset, vdd=vdd) for offset, vdd in ((0.0, 1.2), (0.1e-9, 1.2), (0.2e-9, 1.08))]
        analyze_constraint(mixed, timing=analyze_timing(mixed))


# The latch closes 15 ps after its falling crossing (aperture -15 ps) and has no pushout: d
# crossing at most 15 ps after the edge is passed on (setup -10 ps, the smallest such grid offset:
# the failing -20 ps captures nothing), d crossing later is held (every offset from -20 ps down:
# hold 20 ps).
def test_closed_form_latch_setup_and_hold_at_its_closing_aperture() -> None:
    sweep = [latch_model(offset, aperture_s=-15e-12) for offset in DATA_OFFSET_SWEEP_S]
    constraint = analyze_constraint(sweep, timing=analyze_timing(sweep))
    assert constraint.setup_s == approx(min(o for o in DATA_OFFSET_SWEEP_S if o > -15e-12))
    assert constraint.setup_s == approx(-10e-12)
    assert constraint.hold_s == approx(-max(o for o in DATA_OFFSET_SWEEP_S if o < -15e-12))
    assert constraint.hold_s == approx(20e-12)


def sr_model(
    design: Params,
    *,
    vdd: float = 1.2,
    sets: bool = True,
    misses: int | None = None,
    stop_s: float | None = None,
) -> Meas:
    """An SR latch on the timing bench's set and reset pulses (sim.testbench): q starts its single
    pole toward V_DD DEAD_S after each active set crossing and toward ground DEAD_S after each
    active reset crossing; the supply delivers LEAKAGE_A and CHARGE_C after each, the set source
    CHARGE_C after each of its rising crossings and takes it back after each falling one (an ideal
    source charging and discharging its gate). ``sets`` False: s stays idle; ``misses``: q ignores
    that set (counted from 0); ``stop_s``: the run ends there."""
    tb = TbParams(params=design, vdd=vdd)
    period, transition = float(tb.data_period_s), float(tb.transition_time_s)
    time_s = simulator_axis(tb.stop_s if stop_s is None else stop_s)
    idle, active = (vdd, 0.0) if design.style is Style.SR_NAND else (0.0, vdd)
    set_v = pulse(time_s, idle, active, period, period / 4, period / 4, transition)
    if not sets:
        set_v = np.full_like(time_s, idle)
    reset_v = pulse(time_s, idle, active, period, period / 4, 3 * period / 4, transition)
    set_edges = np.arange(period / 4 + transition / 2, float(time_s[-1]), period) if sets else np.zeros(0)
    reset_edges = np.arange(3 * period / 4 + transition / 2, float(time_s[-1]), period)
    moving = [edge for count, edge in enumerate(set_edges) if count != misses]
    steps = sorted(
        [(float(edge) + DEAD_S, vdd) for edge in moving] + [(float(edge) + DEAD_S, 0.0) for edge in reset_edges]
    )
    q = single_pole(time_s, steps, initial=0.0, tau_rise_s=TAU_RISE_S, tau_fall_s=TAU_FALL_S)
    current = charge_pulses(time_s, np.sort(np.r_[set_edges, reset_edges]), charge_c=CHARGE_C, leakage_a=LEAKAGE_A)
    inputs = {net: np.zeros(len(time_s)) for net in INPUTS}
    # the set pulse's active edge crosses mid-supply at period / 4 + transition / 2 each period, its
    # return a quarter period and a transition later: a NOR latch's s rises at the first, a NAND's at
    # the second
    active_s = np.arange(period / 4 + transition / 2, float(time_s[-1]), period)
    returns_s = active_s + period / 4 + transition
    set_rises, set_falls = (returns_s, active_s) if design.style is Style.SR_NAND else (active_s, returns_s)
    if sets:
        inputs["s"] = charge_pulses(time_s, set_rises, charge_c=CHARGE_C, leakage_a=0.0) - charge_pulses(
            time_s, set_falls, charge_c=CHARGE_C, leakage_a=0.0
        )
    return Meas(
        group=None,
        index=None,
        dut=design,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={**{net: np.zeros(len(time_s)) for net in INPUTS}, "s": set_v, "r": reset_v, "q": q, "qb": vdd - q},
        i={"vdd": current, **inputs},
    )


# [Baker] Fig. 10.9, p. 333: propagation delays at the 50 % points
# [Baker] Eq. (10.17), p. 333: 0.7 RC, ln 2 of a single pole
# q rises DEAD_S + tau_rise ln 2 = 26.93 ps after the active set crossing and falls DEAD_S +
# tau_fall ln 2 = 30.40 ps after the active reset one, NAND (active low) and NOR (active high).
# [Baker] Eq. (11.14), p. 355: the average current, the charge a period over the period
# One set and one reset in the data period T (5.2 ns), each CHARGE_C: I_DD = LEAKAGE_A + 2 CHARGE_C
# / T = 4.846 uA; the set's source delivers CHARGE_C a period, its driver's current CHARGE_C / T;
# the energy a set and reset cycle V_DD (LEAKAGE_A T + 3 CHARGE_C).
def test_closed_form_sr_delays_current_and_energy() -> None:
    for design in (runs.sr_nand(), runs.sr_nor()):
        result = analyze_sr([sr_model(design, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
        assert result.delay_rise_s == approx(np.full(3, DEAD_S + TAU_RISE_S * math.log(2)), abs=1e-13)
        assert result.delay_fall_s == approx(np.full(3, DEAD_S + TAU_FALL_S * math.log(2)), abs=1e-13)
        assert result.idd_a == approx(np.full(3, LEAKAGE_A + 2 * CHARGE_C / 5.2e-9), rel=1e-3)
        assert result.idd_drivers_a == approx(np.full(3, CHARGE_C / 5.2e-9), rel=1e-3)
        supply_v = 1.2 * np.asarray(SUPPLY_SWEEP)
        assert result.energy_per_cycle_j == approx(supply_v * (LEAKAGE_A * 5.2e-9 + 3 * CHARGE_C), rel=1e-3)


# Edge cases: a set input that never moves leaves no set edge, so no rise delay and no window for
# the current, and q never rises, so no falling crossing either; a run ending at two data periods
# (10.4 ns) has its second set and reset (at 6.525 and 9.125 ns) but not the whole period after
# the second set (to 11.725 ns), so its delays stand and its current is undefined. A latch that
# misses the second set (q stays low from the first reset) answers it only at the third set, a
# period later, past the active pulse's quarter period: no rise delay, and its second reset finds q
# low already, its next fall a period later too: no fall delay.
def test_closed_form_sr_without_a_set_or_a_whole_period() -> None:
    idle = analyze_sr([sr_model(runs.sr_nand(), sets=False)])
    assert all(math.isnan(value[0]) for value in (idle.delay_rise_s, idle.delay_fall_s, idle.idd_a))
    short = analyze_sr([sr_model(runs.sr_nand(), stop_s=2 * 5.2e-9)])
    assert short.delay_rise_s[0] == approx(DEAD_S + TAU_RISE_S * math.log(2), abs=1e-13)
    assert short.delay_fall_s[0] == approx(DEAD_S + TAU_FALL_S * math.log(2), abs=1e-13)
    assert math.isnan(short.idd_a[0])
    missed = analyze_sr([sr_model(runs.sr_nand(), misses=1)])
    assert math.isnan(missed.delay_rise_s[0]) and math.isnan(missed.delay_fall_s[0])


def upset_model(charge_c: float, *, node_f: float = 6e-15, held: bool = True, vdd: float = 1.2) -> Meas:
    """A C2MOS latch holding q at V_DD, struck at its upset time: q dips by Q / C (``node_f``) along
    a double exponential normalized to that peak (time constants 5 and 50 ps) and recovers, or,
    where Q / C exceeds V_DD / 2, decays to ground with 30 ps; ``held`` False, q held ground."""
    tb = TbParams(params=Params(), bench=Bench.UPSET, charge_c=charge_c, vdd=vdd)
    time_s = simulator_axis(tb.stop_s)
    after = np.maximum(time_s - float(tb.upset_time_s), 0.0)
    fast, slow = 5e-12, 50e-12
    peak_s = fast * slow * math.log(slow / fast) / (slow - fast)
    shape = (np.exp(-after / slow) - np.exp(-after / fast)) / (math.exp(-peak_s / slow) - math.exp(-peak_s / fast))
    dip = charge_c / node_f
    q = vdd * np.exp(-after / 30e-12) if dip > vdd / 2 else vdd - dip * shape
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"q": q if held else np.zeros_like(time_s)},
        i={"vdd": np.full(len(time_s), LEAKAGE_A)},
    )


# not in the reference texts: critical charge, the smallest charge on the storage node that flips
# the stored state (single-event upset)
# not in the reference texts: a double-exponential dip e^{-t/t2} - e^{-t/t1} peaks where its slope
# is zero, at t_p = t1 t2 ln(t2 / t1) / (t2 - t1) (12.79 ps for 5 and 50 ps), normalized to 1 there
# A node of 6 fF dips Q / C and flips once that passes V_DD / 2, from Q_c = C V_DD / 2 = 3.6 fC, so
# of the 10 % grid's strikes (..., 3.14, 3.45, 3.8, 4.18 fC, ...) the 3.8 fC and larger flip: the
# critical charge lies in (3.45, 3.8] fC, the bounds the analysis gives, the lower within 10 % of
# Q_c. The recovered dips are Q / C; a flipped q decays to ground within e^{-2 ns / 30 ps} of V_DD,
# so its dip is V_DD. The sampled minimum misses the peak by at most |q''| h^2 / 8, for the largest
# recovered dip, 3.45 fC / 6 fF = 0.575 V: 0.575 V x 4.0e-3 / ps^2 x (1.7 ps)^2 / 8 = 0.83 mV, checked
# to 1 mV.
def test_closed_form_upset_dip_and_critical_charge() -> None:
    upset = analyze_upset([upset_model(charge) for charge in UPSET_CHARGES_C])
    critical = 6e-15 * 1.2 / 2
    flips = np.asarray(UPSET_CHARGES_C) > critical
    assert list(upset.upset_fraction) == [float(flip) for flip in flips]
    assert upset.dip_v == approx(np.where(flips, 1.2, np.asarray(UPSET_CHARGES_C) / 6e-15), abs=1e-3)
    assert upset.flip_charge_c == approx(min(c for c in UPSET_CHARGES_C if c > critical))
    assert upset.critical_charge_c == approx(max(c for c in UPSET_CHARGES_C if c <= critical))
    assert (upset.critical_charge_c, upset.flip_charge_c) == approx((3.45e-15, 3.8e-15))
    assert upset.critical_charge_c < critical <= upset.flip_charge_c
    assert critical / upset.critical_charge_c < 1.1
    assert upset.cload_f == approx(2e-15)


# Edge cases: a latch that never took the 1 holds ground before the strike, so its runs say nothing
# (NaN, not "no flip"), and with no run that held a 1 there is no critical charge; one strike that
# recovers bounds the critical charge from below by its own charge, with no flip above it.
def test_closed_form_upset_without_a_held_one_or_a_flip() -> None:
    empty = analyze_upset([upset_model(charge, held=False) for charge in (1e-15, 50e-15)])
    assert all(math.isnan(value) for value in (*empty.upset_fraction, *empty.dip_v))
    assert math.isnan(empty.critical_charge_c) and math.isnan(empty.flip_charge_c)
    single = analyze_upset([upset_model(2e-15)])
    assert single.dip_v[0] == approx(2e-15 / 6e-15, abs=1e-3)
    assert single.critical_charge_c == approx(2e-15) and math.isnan(single.flip_charge_c)
    # the smallest strike flips: the critical charge is below it, bounded by 0
    weak = analyze_upset([upset_model(charge, node_f=0.5e-15) for charge in (1e-15, 2e-15)])
    assert (weak.critical_charge_c, weak.flip_charge_c) == approx((0.0, 1e-15))


def timing_result(**arrays: Any) -> AnalysisTiming:
    """An AnalysisTiming of a flip-flop with the given arrays (three points by default)."""
    base = {
        "vdd_v": 1.2 * np.asarray(SUPPLY_SWEEP),
        "clock_period_s": np.full(3, 2e-9),
        "data_offset_s": np.full(3, 0.5e-9),
        "delay_rise_s": np.array([50e-12, 40e-12, 33e-12]),
        "delay_fall_s": np.array([55e-12, 44e-12, 36e-12]),
        "captured_fraction": np.ones(3),
        "held_fraction": np.zeros(3),
        "idd_a": np.array([5e-6, 6e-6, 7e-6]),
        "idd_drivers_a": np.array([1e-6, 1e-6, 1e-6]),
    }
    return AnalysisTiming(group=None, index=None, dut=runs.flop_rst(), **{**base, **arrays})


# [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg
# The metrics are arithmetic on the analyses: at the nominal supply (the run at the sweep's median
# supply, 1.2 V) the delays 40 and 44 ps and the energy V_DD (I_DD + I_drivers) T_CK = 1.2 V x 7 uA
# x 2 ns = 16.8 fJ; the slowest delay over the supply, 55 ps; setup and hold as the constraint has
# them.
# [Razavi-PLL] Sec. 15.1, p. 453: maximum allowable input frequency, f_max
# not in the reference texts: f_max as the top of the contiguous passing band from the slowest clock
# f_max is the top of the band that works from the slowest clock up: of 1, 2, 3.33, 5 and 6.67 GHz
# with captured shares 1, 1, 0.5, 1, 0, that is 2 GHz (the 5 GHz pass above a failure does not
# count); a run that fails at the slowest clock has no f_max; one that never fails, the fastest.
def test_closed_form_metrics_arithmetic() -> None:
    periods = np.array([1e-9, 500e-12, 300e-12, 200e-12, 150e-12])
    period = timing_result(
        vdd_v=np.full(5, 1.2),
        clock_period_s=periods,
        data_offset_s=periods / 2,
        delay_rise_s=np.full(5, 40e-12),
        delay_fall_s=np.full(5, 44e-12),
        captured_fraction=np.array([1.0, 1.0, 0.5, 1.0, 0.0]),
        held_fraction=np.array([0.0, 0.0, 0.5, 0.0, 1.0]),
        idd_a=np.full(5, 6e-6),
        idd_drivers_a=np.zeros(5),
    )
    constraint = AnalysisConstraint(
        group=None,
        index=None,
        dut=runs.flop_rst(),
        vdd_v=1.2,
        clock_period_s=2e-9,
        delay_rise_s=40e-12,
        delay_fall_s=44e-12,
        setup_s=50e-12,
        hold_s=25e-12,
    )
    slow = timing_result(**{name: value[:1] for name, value in dataclasses_arrays(timing_result()).items()})
    found = metrics(supply=timing_result(), constraint=constraint, period=period, slow=slow)
    assert (found.delay_rise_s, found.delay_fall_s) == approx((40e-12, 44e-12))
    assert found.energy_per_cycle_j == approx(1.2 * 7e-6 * 2e-9)
    assert found.delay_max_supply_s == approx(55e-12)
    assert (found.setup_s, found.hold_s) == approx((50e-12, 25e-12))
    assert found.fmax_hz == approx(1 / 500e-12)
    assert found.captured_1mhz_fraction == 1.0
    assert math.isnan(found.critical_charge_c) and math.isnan(found.flip_charge_c)
    # the supply runs in any order: the nominal run is the one at the median supply, 1.2 V, whose
    # delays are 40 and 44 ps and energy 16.8 fJ wherever it stands
    for order in ([2, 1, 0], [1, 2, 0], [0, 2, 1]):
        moved = timing_result(**{name: value[order] for name, value in dataclasses_arrays(timing_result()).items()})
        again = metrics(supply=moved)
        assert (again.delay_rise_s, again.delay_fall_s) == approx((40e-12, 44e-12))
        assert again.energy_per_cycle_j == approx(1.2 * 7e-6 * 2e-9)
    # an even number of runs has no run at the median supply
    with pytest.raises(ValueError, match="nominal supply"):
        metrics(
            supply=timing_result(**{name: value[:2] for name, value in dataclasses_arrays(timing_result()).items()})
        )
    # the runs in any order: the band is taken from the slowest clock up
    shuffled = replace(
        period,
        clock_period_s=periods[::-1],
        captured_fraction=period.captured_fraction[::-1],
        held_fraction=period.held_fraction[::-1],
    )
    assert shuffled.fmax_hz == approx(1 / 500e-12)
    # a supply run without a delay (NaN) is passed over by the slowest delay; all NaN, NaN unwarned
    gap = metrics(supply=timing_result(delay_fall_s=np.array([math.nan, 44e-12, 36e-12])))
    assert gap.delay_max_supply_s == approx(50e-12)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        none = metrics(supply=timing_result(delay_rise_s=np.full(3, math.nan), delay_fall_s=np.full(3, math.nan)))
    assert math.isnan(none.delay_max_supply_s)
    # failing at the slowest clock: no f_max; never failing: the fastest clock's
    never = metrics(supply=timing_result(), period=replace(period, captured_fraction=np.zeros(5)))
    assert math.isnan(never.fmax_hz)
    always = metrics(supply=timing_result(), period=replace(period, captured_fraction=np.ones(5)))
    assert always.fmax_hz == approx(1 / 150e-12)
    # an SR latch's delays, its energy V_DD (I_DD + I_drivers) T over its set and reset period, and
    # a critical charge between the largest recovered strike and the smallest flipping one
    sr = AnalysisSr(
        group=None,
        index=None,
        dut=runs.sr_nand(),
        vdd_v=1.2 * np.asarray(SUPPLY_SWEEP),
        data_period_s=np.full(3, 5.2e-9),
        delay_rise_s=np.array([30e-12, 25e-12, 21e-12]),
        delay_fall_s=np.array([33e-12, 27e-12, 23e-12]),
        idd_a=np.array([4e-6, 5e-6, 6e-6]),
        idd_drivers_a=np.array([1e-6, 2e-6, 3e-6]),
    )
    upset = AnalysisUpset(
        group=None,
        index=None,
        dut=Params(),
        cload_f=2e-15,
        charge_c=np.array([1e-15, 5e-15, 10e-15]),
        upset_fraction=np.array([0.0, 1.0, 1.0]),
        dip_v=np.array([0.2, 1.2, 1.2]),
    )
    alone = metrics(supply=sr, upset=upset)
    assert (alone.delay_rise_s, alone.delay_fall_s) == approx((25e-12, 27e-12))
    assert alone.energy_per_cycle_j == approx(1.2 * 7e-6 * 5.2e-9)
    assert alone.delay_max_supply_s == approx(33e-12)
    assert (alone.critical_charge_c, alone.flip_charge_c) == approx((1e-15, 5e-15))


def dataclasses_arrays(result: AnalysisTiming) -> dict[str, np.ndarray]:
    """An AnalysisTiming's array fields by name."""
    return {
        name: getattr(result, name) for name in result.__dataclass_fields__ if name not in ("group", "index", "dut")
    }


# [Razavi-PLL] Sec. 15.1, p. 453: f_max, the maximum allowable input frequency
# not in the reference texts: f_max to within the period grid's 10 % step, at or above the
# reported value and below the next tested frequency
# A flip-flop that samples d 30 ps before the edge, its data half a period ahead and every period's
# edges an eighth of the shortest (the period runs, runs.testbenches): every edge captures while
# T_CK / 2 > 30 ps, so its own f_max is 1 / 60 ps = 16.67 GHz. The sweep's answer is the shortest
# grid period above 60 ps, 63 ps (15.87 GHz), the next one, 57 ps, failing: f_max lies between the
# two, at most 10 % above the reported value. The delay at each period of 150 ps and more is
# DEAD_S + tau ln 2 (at shorter ones the previous edge's tail, e^{-(T_CK - DEAD_S) / tau} of the
# swing, still shifts it).
def test_closed_form_fmax_from_the_period_runs() -> None:
    period = analyze_timing(
        [
            flop_model(
                value / 2,
                aperture_s=30e-12,
                clock_period_s=value,
                transition_time_s=min(PERIOD_SWEEP_S) / 8,
                reset_time_s=value * max(2, math.ceil(0.5e-9 / value)),
                cycles=12,
            )
            for value in PERIOD_SWEEP_S
        ]
    )
    working = np.asarray(PERIOD_SWEEP_S) / 2 > 30e-12
    assert list(period.captured_fraction[working]) == [1.0] * int(working.sum())
    assert np.all(period.captured_fraction[~working] < 1.0)
    settled = np.asarray(PERIOD_SWEEP_S) >= 150e-12
    assert period.delay_rise_s[settled] == approx(DEAD_S + TAU_RISE_S * math.log(2), abs=1e-13)
    supply = analyze_timing([flop_model(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
    found = metrics(supply=supply, period=period)
    assert found.fmax_hz == approx(1 / min(p for p in PERIOD_SWEEP_S if p / 2 > 30e-12))
    assert found.fmax_hz <= 1 / 60e-12 < 1.1 * found.fmax_hz
    assert found.fmax_hz == approx(1 / 63e-12)


# [Razavi-PLL] Sec. 15.2.2, p. 459: dynamic latches lose their state through leakage when the clock
# is too slow, a lower bound on the operating frequency
# At a 1 MHz clock (the slow run: d half a period ahead, sampled every 100 ps) a static flip-flop
# keeps q and captures every edge. A dynamic one whose q leaks to ground with a 50 ns time constant
# has lost a stored 1 long before the sample instant, 0.95 us after its edge: q never ends at a new
# 1, and where the new value is 0 q was there already at the launch, so no edge is captured.
def test_closed_form_the_slow_clock_finds_a_leaking_flop() -> None:
    slow = {"clock_period_s": 1e-6, "cycles": 4, "step_s": 100e-12}
    static = analyze_timing([flop_model(0.5e-6, **slow)])
    assert static.captured_fraction[0] == 1.0
    leaking = analyze_timing([flop_model(0.5e-6, leak_s=50e-9, **slow)])
    assert leaking.captured_fraction[0] == 0.0
    supply = analyze_timing([flop_model(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP])
    assert metrics(supply=supply, slow=leaking).captured_1mhz_fraction == 0.0
    assert metrics(supply=supply, slow=static).captured_1mhz_fraction == 1.0
