"""Known answers for what the record adds beside the settling's own numbers, each derived on paper:
one side's settling in the converter's direction, the corner runs, the full scale's share of the
reference, the sampled noise against the quantization noise, the settling's budget and limit, the
supply's energy and the drivers' share of it, the bottom plates' excursion past the rails, the 95th
percentile's upper confidence bound, and which arrays a kit admits (``params.valid``)."""

from __future__ import annotations

import importlib
import math
from dataclasses import replace
from types import SimpleNamespace

import hdl21 as h
import numpy as np
import pytest

from flow.pipeline import Level

from . import runs as capdac_runs
from .analysis import _p95_upper, analyze_settling, metrics
from .model import Model
from .params import Params, Redundancy, TbParams
from .test_known_answers import BINARY8, TAUS, UNIT8, VDD, near, settling_of, settling_run


def test_one_side_settles_its_half_step_in_the_converters_direction() -> None:
    """The P top plate alone carries half the differential step, 2^N w / W / 2 of the LSB times 2:
    s / (LSB / 2) = 2^N w / W, so an RC of tau started ``lag`` after the edge settles at lag + tau
    ln(2^8 w / 127), ln 2 tau sooner than the two sides together; C0, C2, C4, C6 (A state 0) rising,
    the others falling: the same by symmetry."""
    lag = 35e-12
    result = analyze_settling(settling_run(UNIT8, lag_s=lag))
    expected = lag + np.asarray(TAUS) * np.log(2**8 * np.asarray(BINARY8) / 127)
    np.testing.assert_allclose(result.side_settling_s, expected, atol=0.05e-12)
    np.testing.assert_allclose(result.settling_s - result.side_settling_s, np.asarray(TAUS) * math.log(2), atol=0.1e-12)


def test_the_record_judges_the_settling_against_settle_ps_and_its_budget() -> None:
    """UNIT8 at settle_ps 1000, margin 2: the MSB (tau 150 ps, a 2^9 64 / 127 = 258 half-LSB step)
    settles in 150 ps ln 258 = 832.9 ps, 1.666 of the 500 ps budget and within settle_ps; one side
    150 ps ln 129. Unit capacitors switch their whole top plate: the full scale is the reference, its
    share 1, the rule met. At ``scale`` 2 the plate is twice 24 kT / LSB^2, so both sides' 2 kT / C
    is LSB^2 / 24: half the quantization noise."""
    found = metrics(settling=analyze_settling(settling_run(UNIT8)))
    assert found["settling_max_s"] == pytest.approx(150e-12 * math.log(258), abs=0.05e-12)
    assert found["settling_budget_ratio"] == pytest.approx(150e-12 * math.log(258) / 500e-12, abs=1e-3)
    assert found["settling_side_max_s"] == pytest.approx(150e-12 * math.log(129), abs=0.05e-12)
    assert found["settles_in_time"] is True
    assert found["full_scale_fraction"] == near(1.0, rel=1e-9) and found["full_scale_meets_rule"] is True
    assert found["ktc_noise_ratio"] == near(0.5, rel=1e-9)


def test_a_corner_run_past_settle_ps_fails_the_bound_and_a_missing_one_counts_as_late() -> None:
    """A slow corner whose slowest stage takes 1.2 ns is past settle_ps (1 ns): not in time; a corner
    without a measured settling (NaN) is not in time either; the corners' slowest reported."""
    typical = settling_of([300e-12, 200e-12], [40e-12, 30e-12], [0.2, 0.1])
    typical = replace(typical, settle_s=1e-9, budget_s=0.5e-9, side_settling_s=np.asarray([280e-12, 180e-12]))
    late = replace(
        typical, settling_rise_s=np.asarray([1.2e-9, 200e-12]), settling_fall_s=np.asarray([1.2e-9, 200e-12])
    )
    found = metrics(settling=typical, slow=late, fast=typical)
    assert found["settling_slow_max_s"] == 1.2e-9 and found["settling_fast_max_s"] == 300e-12
    assert found["settles_in_time"] is False
    assert metrics(settling=typical, fast=typical)["settles_in_time"] is True
    unmeasured = replace(typical, settling_rise_s=np.asarray([math.nan, 200e-12]))
    assert metrics(settling=typical, slow=unmeasured)["settles_in_time"] is False


def test_the_full_corner_runs_are_the_slow_and_fast_supplies_and_corners(monkeypatch: pytest.MonkeyPatch) -> None:
    """At ``Level.FULL``: the slow corner at 90 % of a 1.2 V supply (1.08 V), 125 C, and the fast at
    110 % (1.32 V); both draw their plates at the nominal 1.2 V, so their design plates are the
    typical run's."""
    site = SimpleNamespace(install=SimpleNamespace(supply_voltage=lambda corner: 1.2))
    monkeypatch.setattr(capdac_runs, "importlib", SimpleNamespace(import_module=lambda name: site))
    benches = capdac_runs.testbenches("tsmc65", UNIT8, Level.FULL)
    assert list(benches) == ["settling", "mc_a1", "mc_a5", "mc_a10", "settling_slow", "settling_fast"]
    slow, fast, typical = benches["settling_slow"], benches["settling_fast"], benches["settling"]
    assert (slow.vdd, slow.corner, slow.temperature_c) == (near(1.08), h.pdk.Corner.SLOW, 125.0)
    assert (fast.vdd, fast.corner, fast.temperature_c) == (near(1.32), h.pdk.Corner.FAST, 25.0)
    np.testing.assert_array_equal(slow.main_f, typical.main_f)
    np.testing.assert_array_equal(fast.diff_f, typical.diff_f)
    assert list(capdac_runs.testbenches("tsmc65", UNIT8)) == ["settling", "mc_a1", "mc_a5", "mc_a10"]


def test_the_supply_energy_is_v_times_its_charge_each_window() -> None:
    """A constant 1 uA drawn from 1.2 V over every 4 ns window is 4.8 fJ a window, 14 windows (7
    stages up and down): 67.2 fJ in all."""
    meas = settling_run(UNIT8)
    meas = replace(meas, i={"vdd": np.full_like(meas.time_s, 1e-6)})
    found = metrics(settling=analyze_settling(meas))
    assert found["supply_energy_j"] == near(14 * 1.2 * 1e-6 * 4e-9, rel=1e-6)


def test_the_drivers_energy_is_what_the_plates_charge_leaves_over_the_transitions() -> None:
    """The design's UNIT8 plates (C_k, C_t their sum) on the bench: P rising draws C_k V (1 - C_k /
    C_t) from the reference, P falling none; N falling (all but k left at the reference) draws (C_t -
    C_k) V C_k / C_t, N rising none. Per stage 2 V C_k (C_t - C_k) / C_t, an energy V times that. A
    supply energy of that plus 1 fJ for each of the 8 x 7 transitions leaves 1 fJ a transition."""
    model = Model.design("tsmc65", UNIT8, reference_v=VDD)
    main_f, _ = Model.plates(UNIT8, VDD)
    total = float(main_f.sum())
    plates_j = float(np.sum(VDD * 2 * VDD * main_f * (total - main_f) / total))
    assert model.bench_driver_energy_j(plates_j + 56 * 1e-15) == near(1e-15, rel=1e-6)


def test_a_bottom_plate_past_a_rail_is_its_excursion() -> None:
    """C3's main plate overshooting the supply by 50 mV and C5's dipping 20 mV below ground: 50 mV."""
    meas = settling_run(UNIT8)
    v = dict(meas.v)
    v["dut_p.main_3"] = v["dut_p.main_3"] + 0.05 * (v["dut_p.main_3"] > VDD / 2)
    v["dut_p.main_5"] = v["dut_p.main_5"] - 0.02 * (v["dut_p.main_5"] < VDD / 2)
    assert analyze_settling(replace(meas, v=v)).excursion_v == pytest.approx(0.05, abs=1e-9)


def test_the_95th_percentiles_upper_bound_is_its_order_statistic() -> None:
    """Of 100 runs, P(Binomial(100, 0.95) <= 98) = 0.963 >= 0.95 and <= 97 is 0.882: the 99th
    smallest, 99 of 1 ... 100; of 3 runs no order statistic bounds it."""
    assert _p95_upper(np.arange(1.0, 101.0)) == 99.0
    assert math.isnan(_p95_upper(np.asarray([1.0, 2.0, 3.0])))


def test_a_slow_kit_admits_only_the_arrays_its_drivers_can_be_sized_for() -> None:
    """GF180's FO4 delay is so large a fraction of the 500 ps budget that a 14-bit binary strip
    side's MSB chain would take it all: refused; FRIDA-1's 12-bit array admitted; in TSMC65 every
    array of the grid."""
    params = importlib.import_module("flow.capdac.params")
    for kit in ("gf180", "tsmc65"):
        try:
            importlib.import_module(f"pdk.{kit}.hdl21.site")
        except ImportError:
            pytest.skip(f"the {kit} kit is not installed")
    assert not params.valid(Params(bits=14, redundancy=Redundancy.BINARY, extra=0, scale=2), "gf180")
    assert params.valid(capdac_runs.frida1(), "gf180")
    assert all(params.valid(p, "tsmc65") for _, p in capdac_runs.arrays.instances("tsmc65"))


def test_a_corner_runs_plates_are_drawn_at_the_nominal_supply() -> None:
    """``nominal_vdd`` draws the plates; ``vdd`` alone moves the steps' volts, not the plates."""
    base = TbParams(params=UNIT8, vdd=1.2, window_s=4e-9, waveform_sample_interval_s=2e-12)
    low = replace(base, vdd=1.08, nominal_vdd=1.2)
    np.testing.assert_array_equal(low.main_f, base.main_f)
    np.testing.assert_allclose(low.ideal_step_v, 0.9 * base.ideal_step_v, rtol=1e-12)
