"""The latch's analyses, metrics and record on synthetic runs with known setup, delay, current and
upset, as a run's measurement (``flow.pipeline.Meas``) reads."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot

from . import runs
from .analysis import analyze_constraint, analyze_sr, analyze_timing, analyze_upset, metrics
from .params import DATA_OFFSET_SWEEP_S, PERIOD_SWEEP_S, SUPPLY_SWEEP, UPSET_CHARGES_C, Bench, Params, TbParams
from .types import Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))


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
        v=v,
        i={"vdd": np.full(len(time_s), current_a)},
    )


def flop_run(
    offset_s: float, *, vdd: float = 1.2, setup_s: float = 30e-12, delay_s: float = 40e-12, **changes: float
) -> Meas:
    """A flip-flop that takes d as it was setup_s before each rising edge, delay_s after that edge."""
    tb = TbParams(params=runs.flop_rst(), vdd=vdd, data_offset_s=offset_s, **changes)
    period, transition = float(tb.clock_period_s), float(tb.transition_time_s)
    time_s = np.arange(0, float(tb.reset_time_s) + (tb.cycles + 1) * period, 1e-12)
    clock = pulse(time_s, 0.0, vdd, period, period / 2, period / 2, transition)
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
    clock = pulse(time_s, 0.0, vdd, period, period / 2, period / 2, transition)
    capture = period + 1.5 * transition
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
        rise = fall - period / 2 - transition
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
    assert timing.clock_to_q_rise_s[passing] == pytest.approx(40e-12, abs=2e-12)
    assert timing.clock_to_q_fall_s[passing] == pytest.approx(40e-12, abs=2e-12)
    assert timing.energy_per_cycle_j == pytest.approx(1.2 * 30e-6 * 2e-9)
    constraint = analyze_constraint(sweep, timing=timing)
    assert constraint.setup_s == pytest.approx(40e-12)
    assert constraint.hold_s == pytest.approx(-20e-12)
    assert constraint.clock_to_q_rise_s == pytest.approx(40e-12, abs=2e-12)
    with pytest.raises(ValueError, match="data offset sweep"):
        analyze_constraint(sweep[:2], timing=analyze_timing(sweep[:2]))
    with pytest.raises(ValueError, match="clocked"):
        analyze_timing([sr_run(1.2)])


def test_sr_set_and_reset_delays() -> None:
    for design in (runs.sr_nand(), runs.sr_nor()):
        result = analyze_sr([sr_run(1.0, design), sr_run(1.2, design)])
        assert result.delay_rise_s == pytest.approx([25e-12, 25e-12], abs=2e-12)
        assert result.delay_fall_s == pytest.approx([25e-12, 25e-12], abs=2e-12)
        assert result.energy_per_cycle_j == pytest.approx(np.array([1.0, 1.2]) * 10e-6 * 5.2e-9)
    with pytest.raises(ValueError, match="SR latch"):
        analyze_sr([flop_run(0.5e-9)])


def test_upset_critical_charge_and_dip() -> None:
    upset = analyze_upset([upset_run(charge * 1e-15, 20e-15) for charge in (50, 5, 10, 20)])
    assert upset.charge_c == pytest.approx([5e-15, 10e-15, 20e-15, 50e-15])
    assert list(upset.upset_fraction) == [0.0, 0.0, 1.0, 1.0]
    assert upset.dip_v == pytest.approx([0.3, 0.6, 1.2, 1.2])
    assert upset.critical_charge_c == pytest.approx(20e-15)
    assert math.isnan(analyze_upset([upset_run(5e-15, 20e-15)]).critical_charge_c)
    with pytest.raises(ValueError, match="upset bench"):
        analyze_upset([flop_run(0.2e-9)])


def test_the_metrics_take_the_nominal_supply_and_what_the_design_ran() -> None:
    """A flip-flop's record: its delays and energy at the nominal supply, its setup and hold, the
    highest clock frequency at which every edge captures; no critical charge."""
    supply = analyze_timing([flop_run(0.5e-9, vdd=1.2 * factor, delay_s=40e-12 / factor) for factor in SUPPLY_SWEEP])
    sweep = [flop_run(offset) for offset in (-100e-12, 0.0, 20e-12, 40e-12, 100e-12)]
    period = analyze_timing(
        [
            flop_run(value / 4, clock_period_s=value, transition_time_s=value / 8, reset_time_s=1e-9, cycles=12)
            for value in (1e-9, 500e-12, 300e-12)
        ]
    )
    found = metrics(supply=supply, constraint=analyze_constraint(sweep, timing=analyze_timing(sweep)), period=period)
    assert isinstance(found, Metrics)
    assert found.delay_rise_s == pytest.approx(40e-12, abs=2e-12)
    assert found.delay_max_supply_s == pytest.approx(40e-12 / 0.9, abs=2e-12)
    assert found.energy_per_cycle_j == pytest.approx(1.2 * 30e-6 * 2e-9)
    assert (found.setup_s, found.hold_s) == pytest.approx((40e-12, -20e-12))
    assert found.fmax_hz == pytest.approx(1 / 300e-12) and math.isnan(found.critical_charge_c)
    alone = metrics(supply=analyze_sr([sr_run(1.2 * factor) for factor in SUPPLY_SWEEP]))
    assert alone.delay_fall_s == pytest.approx(25e-12, abs=2e-12)
    assert all(math.isnan(value) for value in (alone.setup_s, alone.hold_s, alone.fmax_hz, alone.critical_charge_c))


def test_the_record_holds_the_metrics_and_each_sweeps_plots() -> None:
    """``results`` from one instance's runs, by the names ``testbenches`` gives them: a flip-flop's
    (supply, data offset, clock period), an SR latch's (supply) and a struck latch's."""
    flop = {f"supply_{round(factor * 100)}": flop_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP}
    flop |= {f"offset_{round(offset * 1e12)}ps": flop_run(offset) for offset in DATA_OFFSET_SWEEP_S}
    flop |= {
        f"period_{round(value * 1e12)}ps": flop_run(
            value / 4,
            clock_period_s=value,
            transition_time_s=min(50e-12, value / 8),
            reset_time_s=max(0.5e-9, 2 * value),
            cycles=12,
        )
        for value in PERIOD_SWEEP_S
    }
    record = runs.results(flop)
    assert set(record.metrics) == set(Metrics.__dataclass_fields__)
    assert record.metrics["setup_s"] == pytest.approx(50e-12) and record.metrics["hold_s"] == pytest.approx(-25e-12)
    assert all(isinstance(detail, Plot) and len(detail.series) == 1 for detail in record.details)
    assert [detail.name for detail in record.details] == [
        *("delay_rise_supply", "delay_fall_supply", "energy_supply"),
        *("clock_to_q_rise_offset", "clock_to_q_fall_offset", "captured_offset", "held_offset"),
        *("captured_frequency", "clock_to_q_rise_frequency", "clock_to_q_fall_frequency"),
    ]
    assert record.waves == {"nominal": "supply_100"}

    sr = runs.results({f"supply_{round(factor * 100)}": sr_run(1.2 * factor) for factor in SUPPLY_SWEEP})
    assert [detail.name for detail in sr.details] == ["delay_rise_supply", "delay_fall_supply", "energy_supply"]
    assert sr.metrics["delay_rise_s"] == pytest.approx(25e-12, abs=2e-12) and math.isnan(sr.metrics["fmax_hz"])

    # a struck C2MOS latch: the upset plots, and the strike that flips it among the waves
    latch = {f"supply_{round(factor * 100)}": latch_run(0.5e-9, vdd=1.2 * factor) for factor in SUPPLY_SWEEP}
    latch |= {f"offset_{round(offset * 1e12)}ps": latch_run(offset) for offset in DATA_OFFSET_SWEEP_S}
    latch |= {f"upset_{round(charge * 1e15)}fc": upset_run(charge, 20e-15, Params()) for charge in UPSET_CHARGES_C}
    struck = runs.results(latch)
    assert struck.metrics["delay_rise_s"] == pytest.approx(40e-12, abs=2e-12)
    assert struck.metrics["setup_s"] == pytest.approx(50e-12) and struck.metrics["hold_s"] == pytest.approx(-25e-12)
    assert struck.metrics["critical_charge_c"] == pytest.approx(20e-15)
    assert [detail.name for detail in struck.details][-2:] == ["dip_charge", "upset_charge"]
    assert struck.waves == {"nominal": "supply_100", "20 fC strike": "upset_20fc"}
