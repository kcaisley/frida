"""The comparator's analyses on synthetic measurements: a testbench run's signals on an uneven time
axis (as Spectre's own steps leave them), and decisions as a capture or a simulation gives them."""

from __future__ import annotations

import dataclasses
import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot

from . import plots
from .analysis import (
    analyze_clock_check,
    analyze_common_mode,
    analyze_decisions,
    analyze_delay,
    analyze_kickback,
    analyze_metastability,
    analyze_offset_noise,
    analyze_power,
    analyze_scurve,
    analyze_timing,
    metrics,
)
from .params import CHARGE_METER, CHARGE_METER_F, Params, TbParams
from .types import AnalysisDecisions

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 24, tzinfo=UTC))


def run(tb: TbParams, *, delay_s=lambda diff: 200e-12, current_a: float = 50e-6, kick_v: float = 0.0) -> Meas:
    """A run of ``tb`` as its raw output reads: the clock's edges, a latch splitting ``delay_s`` of
    its input after the clock's midpoint toward its input's sign, the output holding it, the supply
    drawing ``current_a``, the inputs kicked by ``kick_v`` in the first cycle; on an uneven time
    axis, dense around each clock edge."""

    rng = np.random.default_rng(1)
    trials = len(tb.trial_point)
    edges = tb.trial_start_s + tb.reset_time_s
    time_s = np.unique(
        np.concatenate(
            [
                np.linspace(0.0, tb.stop_s, 40 * trials + 1),
                rng.uniform(0.0, tb.stop_s, 200 * trials),
                *(edge + np.linspace(-50e-12, 3e-9, 800) for edge in edges),
                # and around each cycle's end, where the decision is read
                *(start + tb.cycle_s + np.linspace(-200e-12, 100e-12, 61) for start in tb.trial_start_s),
            ]
        )
    )
    time_s = time_s[time_s <= tb.stop_s]
    trial = np.minimum((time_s // tb.cycle_s).astype(int), trials - 1)
    points = np.asarray(tb.points)
    cm, diff = points[tb.trial_point[trial], 0], points[tb.trial_point[trial], 1]
    since_s = time_s - edges[trial]
    vdd = tb.vdd
    clock = vdd * np.clip(since_s / tb.transition_time_s, 0.0, 1.0)
    trial_delay_s = np.asarray([delay_s(abs(points[point, 1])) for point in tb.trial_point])[trial]
    split = np.clip((since_s - tb.transition_time_s / 2 - trial_delay_s) / 20e-12 + 0.5, 0.0, 1.0)
    sign = np.where(diff >= 0, 1.0, -1.0)
    kick = kick_v * np.exp(-(((time_s - edges[0] - 100e-12) / 50e-12) ** 2))
    meas = Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={
            "clk": clock,
            "latch_p": vdd / 2 * (1 + sign * split),
            "latch_n": vdd / 2 * (1 - sign * split),
            "outp": vdd * (sign > 0),
            "outn": vdd * (sign < 0),
            "inp": cm + diff / 2 + kick,
            "inn": cm - diff / 2,
        },
        i={"vdd": np.full_like(time_s, current_a)},
    )
    # the testbench's charge meter: the supply's charge since the run began, over its capacitance
    meas.v[CHARGE_METER] = current_a * time_s / CHARGE_METER_F
    return meas


def decisions_at() -> AnalysisDecisions:
    """Three decisions, as a capture or a simulation gives them, to replace the trials of."""
    tb = TbParams(vin_cm_values_v=(0.6,), vin_diff_values_v=(-1e-3, 0.0, 1e-3))
    return AnalysisDecisions(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        trial_index=np.arange(3),
        vin_diff_v=np.asarray([-1e-3, 0.0, 1e-3]),
        vin_cm_v=np.full(3, 0.6),
        decision=np.asarray([0, 1, 1], dtype=np.uint8),
    )


def test_a_runs_decisions_and_delays_are_read_on_the_simulators_own_steps() -> None:
    tb = TbParams(vin_diff_values_v=(-1e-3, 0.5e-3, 2e-3), conversions=2)
    meas = run(tb)
    assert np.ptp(np.diff(meas.time_s)) > 0  # an uneven axis
    decisions = analyze_decisions(meas)
    assert decisions.decision.tolist() == [0, 0, 1, 1, 1, 1]
    assert decisions.resolved is not None and decisions.resolved.all()
    np.testing.assert_allclose(decisions.vin_diff_v, np.repeat(tb.vin_diff_values_v, 2))
    timing = analyze_timing(meas, decisions=decisions)
    np.testing.assert_allclose(timing.clock_to_decision_s, 200e-12, atol=1e-12)
    assert not timing.unresolved.any()
    delay = analyze_delay(meas, decisions=decisions, timing=timing)
    np.testing.assert_allclose(delay.delay_s, 200e-12, atol=1e-12)
    assert delay.delay_s.shape == (1, 3)


def test_metastability_reads_the_regeneration_time_constant() -> None:
    tb = TbParams(vin_diff_values_v=(0.1e-3, 1e-3, 10e-3))
    meas = run(tb, delay_s=lambda diff: 150e-12 + 30e-12 * math.log(10e-3 / diff))
    decisions = analyze_decisions(meas)
    delay = analyze_delay(meas, decisions=decisions, timing=analyze_timing(meas, decisions=decisions))
    metastability = analyze_metastability(meas, delay=delay)
    assert metastability.regeneration_tau_s == pytest.approx(30e-12, rel=0.02)


def test_the_clock_check_passes_a_comparator_the_longer_clock_does_not_change() -> None:
    def check(evaluation_s: float, longer_s: float, slow_s: float):
        results = []
        for evaluation in (evaluation_s, longer_s):
            tb = TbParams(vin_diff_values_v=(-0.1e-3, 0.1e-3, 0.3e-3, 1e-3), evaluation_time_s=evaluation)
            meas = run(tb, delay_s=lambda diff: slow_s * 0.1e-3 / diff)
            decisions = analyze_decisions(meas)
            delay = analyze_delay(meas, decisions=decisions, timing=analyze_timing(meas, decisions=decisions))
            results.append((meas, decisions, analyze_metastability(meas, delay=delay)))
        meas, decisions, metastability = zip(*results, strict=True)
        return analyze_clock_check(meas, decisions=decisions, metastability=metastability)

    assert check(4e-9, 8e-9, 200e-12).decides_in_time
    # 10 uV extrapolated past the evaluation
    slow = check(4e-9, 8e-9, 2e-9)
    assert not slow.decides_in_time and "10 uV" in slow.reasons[-1]


def test_power_is_time_weighted_and_energy_is_per_cycle() -> None:
    tb = TbParams(vin_diff_values_v=(1e-3,), conversions=3, vdd=1.0)
    power = analyze_power([run(tb, current_a=40e-6), run(replace(tb, vdd=1.2), current_a=50e-6)])
    np.testing.assert_allclose(power.average_power_w, (40e-6, 60e-6))
    np.testing.assert_allclose(power.energy_per_decision_j, np.asarray((40e-6, 60e-6)) * tb.cycle_s)


def test_kickback_is_the_inputs_largest_excursion_in_the_first_cycle() -> None:
    tb = TbParams(vin_diff_values_v=(1e-3,))
    kickback = analyze_kickback(run(tb, kick_v=5e-3))
    assert kickback.kickback_v == pytest.approx(5e-3, rel=0.02)
    assert kickback.kickback_diff_v == pytest.approx(5e-3, rel=0.02)


def test_the_scurve_counts_unresolved_decisions_apart() -> None:
    base = decisions_at()
    decisions = replace(
        base,
        trial_index=np.arange(6),
        vin_diff_v=np.repeat([-1e-3, 1e-3], 3),
        vin_cm_v=np.full(6, 0.6),
        decision=np.asarray([0, 0, 1, 1, 1, 0], dtype=np.uint8),
        resolved=np.asarray([True, True, False, True, True, True]),
    )
    scurve = analyze_scurve([decisions])
    np.testing.assert_allclose(scurve.probability, (0.0, 2 / 3))
    np.testing.assert_allclose(scurve.unresolved_fraction, (1 / 3, 0.0))
    assert scurve.total_unresolved_fraction == pytest.approx(1 / 6)
    figure = plots.plot_scurve(scurve)
    assert isinstance(figure, Plot) and figure.name == "scurve" and figure.series["P(high)"][0] == 0.0


def test_the_probit_fit_reads_the_noise_from_every_point() -> None:
    """On an ideal S-curve at 40 decisions a point, the Gaussian of most likelihood reads the noise
    to about 6 % between draws, where the 16/84 % crossings alone read it to 12-14 %."""
    rng = np.random.default_rng(7)
    inputs = np.linspace(-0.6e-3, 0.6e-3, 25)
    sigma, fits = 0.2e-3, []
    for _ in range(60):
        decision = np.concatenate(
            [rng.random(40) < 0.5 * (1.0 + math.erf((v - 20e-6) / (sigma * math.sqrt(2.0)))) for v in inputs]
        )
        fit = analyze_offset_noise(
            [
                replace(
                    decisions_at(),
                    trial_index=np.arange(len(decision)),
                    vin_diff_v=np.repeat(inputs, 40),
                    vin_cm_v=np.full(len(decision), 0.6),
                    decision=decision.astype(np.uint8),
                )
            ]
        )
        assert fit.validity == "valid"
        fits.append(fit.noise_sigma_v)
    assert np.mean(fits) == pytest.approx(sigma, rel=0.05)
    assert np.std(fits) < 0.09 * sigma


def test_the_metrics_are_the_records_keys() -> None:
    tb = TbParams(vin_diff_values_v=(0.1e-3, 0.5e-3, 100e-3))
    meas = run(tb)
    decisions = analyze_decisions(meas)
    delay = analyze_delay(meas, decisions=decisions, timing=analyze_timing(meas, decisions=decisions))
    fit = analyze_offset_noise(
        [
            replace(
                decisions_at(),
                trial_index=np.arange(30),
                vin_diff_v=np.repeat([-1e-3, 0.0, 1e-3], 10),
                vin_cm_v=np.full(30, 0.6),
                decision=np.repeat([0, 1, 1], 10).astype(np.uint8) * (np.arange(30) % 2 | (np.arange(30) >= 20)),
            )
        ]
    )
    values = metrics(
        small=delay,
        large=delay,
        metastability=analyze_metastability(meas, delay=delay),
        power=analyze_power([meas, meas]),
        kickback=analyze_kickback(meas),
        offsets=[fit],
        nominal=fit,
        scurve=analyze_scurve([decisions]),
        supply=[delay],
    )
    assert set(dataclasses.asdict(values)) == {
        "delay_0p5mv_s",
        "delay_100mv_s",
        "delay_0p1mv_s",
        "regeneration_tau_s",
        "energy_0p5mv_j",
        "energy_100mv_j",
        "kickback_v",
        "kickback_diff_v",
        "noise_v",
        "offset_v",
        "noise_max_v",
        "delay_max_supply_s",
        "unresolved_fraction",
        "decides_in_time",
    }
    assert values.delay_0p5mv_s == pytest.approx(200e-12, abs=1e-12)
    assert Params() == delay.dut


def test_offset_noise_uses_binary_decision_curve() -> None:
    measurements = []
    rng = np.random.default_rng(4)
    for vin_diff_v in np.linspace(-3e-3, 3e-3, 25):
        msmt = decisions_at()
        sigma = 0.8e-3
        decisions = rng.random(2_000) < 0.5 * (
            1.0 + np.vectorize(__import__("math").erf)(vin_diff_v / (sigma * np.sqrt(2.0)))
        )
        msmt = replace(
            msmt,
            trial_index=np.arange(len(decisions)),
            vin_diff_v=np.full(len(decisions), vin_diff_v),
            vin_cm_v=np.full(len(decisions), 0.6),
            decision=decisions.astype(np.uint8),
        )
        measurements.append(msmt)
    result = analyze_offset_noise(measurements)
    assert result.offset_v == pytest.approx(0.0, abs=0.15e-3)
    assert result.noise_sigma_v == pytest.approx(0.8e-3, rel=0.15)
    assert result.decision_polarity == 1
    assert result.validity == "valid"


def test_offset_noise_leaves_out_unresolved_trials_and_flags_a_slow_comparator() -> None:
    rng = np.random.default_rng(5)

    def curve(unresolved_share: float) -> list[AnalysisDecisions]:
        measurements = []
        for vin_diff_v in np.linspace(-3e-3, 3e-3, 25):
            decisions = rng.random(2_000) < 0.5 * (1.0 + math.erf(vin_diff_v / (0.8e-3 * np.sqrt(2.0))))
            resolved = rng.random(2_000) >= unresolved_share
            # an undecided latch leaves the output holding a stale decision: here always low
            decisions = np.where(resolved, decisions, False)
            measurements.append(
                replace(
                    decisions_at(),
                    trial_index=np.arange(2_000),
                    vin_diff_v=np.full(2_000, vin_diff_v),
                    vin_cm_v=np.full(2_000, 0.6),
                    decision=decisions.astype(np.uint8),
                    resolved=resolved,
                )
            )
        return measurements

    # a few undecided trials are left out: the fit is the resolved trials' S-curve
    few = analyze_offset_noise(curve(0.005))
    assert few.validity == "valid"
    assert few.offset_v == pytest.approx(0.0, abs=0.15e-3)
    assert few.noise_sigma_v == pytest.approx(0.8e-3, rel=0.15)
    # a comparator too slow for its clock gives no noise or offset
    slow = analyze_offset_noise(curve(0.2))
    assert slow.validity == "unresolved"
    assert math.isnan(slow.noise_sigma_v) and math.isnan(slow.offset_v)


@pytest.mark.parametrize("one_counts, expected_offset", (((0, 5, 5, 10), 1.5e-3), ((0, 2, 5), math.nan)))
def test_offset_is_the_most_likely_gaussians_and_requires_a_bracketed_crossing(one_counts, expected_offset) -> None:
    """Two points at 50 %: the most likely Gaussian is centred between them (the crossings alone
    took the first)."""
    msmt = decisions_at()
    trials = 10
    sample_count = trials * len(one_counts)
    decisions = np.concatenate([np.r_[np.ones(count), np.zeros(trials - count)] for count in one_counts])
    msmt = replace(
        msmt,
        trial_index=np.arange(sample_count),
        vin_diff_v=np.repeat(np.arange(len(one_counts)) * 1e-3, trials),
        vin_cm_v=np.full(sample_count, 0.6),
        decision=decisions,
    )
    analysis = analyze_offset_noise([msmt])
    if math.isnan(expected_offset):
        assert math.isnan(analysis.offset_v)
        assert analysis.validity == "unbracketed"
    else:
        assert analysis.offset_v == pytest.approx(expected_offset, rel=1e-6)
        assert analysis.noise_sigma_v == pytest.approx(0.926e-3, rel=1e-3)
        assert analysis.validity == "valid"


def test_offset_noise_accepts_descending_physical_polarity() -> None:
    measurements = []
    rng = np.random.default_rng(14)
    for vin_diff_v in np.linspace(-3e-3, 3e-3, 25):
        msmt = decisions_at()
        sigma = 0.7e-3
        increasing_probability = 0.5 * (1.0 + np.vectorize(__import__("math").erf)(vin_diff_v / (sigma * np.sqrt(2.0))))
        decisions = rng.random(2_000) >= increasing_probability
        msmt = replace(
            msmt,
            trial_index=np.arange(len(decisions)),
            vin_diff_v=np.full(len(decisions), vin_diff_v),
            vin_cm_v=np.full(len(decisions), 0.8),
            decision=decisions.astype(np.uint8),
        )
        measurements.append(msmt)

    result = analyze_offset_noise(measurements)
    assert result.offset_v == pytest.approx(0.0, abs=0.15e-3)
    assert result.noise_sigma_v == pytest.approx(sigma, rel=0.15)
    assert result.decision_polarity == -1
    assert result.validity == "valid"


def test_offset_noise_reports_invalid_curves_in_analysis_only() -> None:
    measurements = []
    for vin_diff_v, ones in zip(np.linspace(-2e-3, 2e-3, 5), (0, 90, 10, 100, 100), strict=True):
        msmt = decisions_at()
        decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
        msmt = replace(
            msmt,
            trial_index=np.arange(100),
            vin_diff_v=np.full(100, vin_diff_v),
            vin_cm_v=np.full(100, 0.8),
            decision=decisions,
        )
        measurements.append(msmt)
    result = analyze_offset_noise(measurements)
    assert result.validity == "non_monotonic"
    assert np.isnan(result.offset_v)
    assert np.isnan(result.noise_sigma_v)

    measurements = [replace(msmt, decision=np.zeros(100, dtype=np.uint8)) for msmt in measurements]
    result = analyze_offset_noise(measurements)
    assert result.validity == "unbracketed"
    assert np.isnan(result.offset_v)


def test_offset_noise_accounts_for_batched_correlation_and_wander() -> None:
    batch_ones = (
        (0,) * 10,
        (98, 93, 90, 99, 96, 100, 94, 98, 99, 100),
        (100, 92, 86, 99, 87, 99, 94, 95, 80, 92),
        (100,) * 10,
    )
    measurements = []
    for vin_diff_v, ones_per_batch in zip(
        (-1e-3, 0.0, 0.1e-3, 1e-3),
        batch_ones,
        strict=True,
    ):
        decisions = np.concatenate(
            [
                np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
                for ones in ones_per_batch
            ]
        )
        base = decisions_at()
        measurements.append(
            replace(
                base,
                info=replace(
                    base.info,
                    readbacks={
                        "capture_batch_count": 10,
                        "capture_batch_trials": 100,
                        "capture_batch_interval_s": 0.5,
                    },
                ),
                trial_index=np.arange(len(decisions)),
                vin_diff_v=np.full(len(decisions), vin_diff_v),
                vin_cm_v=np.full(len(decisions), 0.8),
                decision=decisions,
            )
        )

    unbatched = [replace(msmt, info=replace(msmt.info, readbacks={})) for msmt in measurements]
    assert analyze_offset_noise(unbatched).validity == "non_monotonic"
    batched = analyze_offset_noise(measurements)
    assert batched.validity == "valid"
    assert batched.decision_polarity == 1

    contiguous_batches = [
        replace(
            msmt,
            info=replace(msmt.info, readbacks={**msmt.info.readbacks, "capture_batch_interval_s": 0.0}),
        )
        for msmt in measurements
    ]
    assert analyze_offset_noise(contiguous_batches).validity == "valid"


def test_offset_noise_combines_numerically_equivalent_voltage_bins() -> None:
    measurements = []
    points = (
        (-1e-3, np.zeros(10, dtype=np.uint8)),
        (0.0, np.zeros(10, dtype=np.uint8)),
        (0.1 + 0.2 - 0.3, np.ones(10, dtype=np.uint8)),
        (1e-3, np.ones(10, dtype=np.uint8)),
    )
    for vin_diff_v, decisions in points:
        msmt = decisions_at()
        msmt = replace(
            msmt,
            trial_index=np.arange(len(decisions)),
            vin_diff_v=np.full(len(decisions), vin_diff_v),
            vin_cm_v=np.full(len(decisions), 0.8),
            decision=decisions,
        )
        measurements.append(msmt)

    result = analyze_offset_noise(measurements)
    np.testing.assert_array_equal(result.vin_diff_v, (-1e-3, 0.0, 1e-3))
    np.testing.assert_array_equal(result.trial_count, (10, 20, 10))
    np.testing.assert_allclose(result.decision_probability, (0.0, 0.5, 1.0))


def test_common_mode_context_classifies_only_exercised_stuck_outputs() -> None:
    def group(vin_cm_v: float, probabilities: tuple[float, ...], *, center_v: float = 0.0) -> list[AnalysisDecisions]:
        measurements = []
        for vin_diff_v, probability in zip(
            np.linspace(center_v - 2e-3, center_v + 2e-3, len(probabilities)),
            probabilities,
            strict=True,
        ):
            base = decisions_at()
            ones = round(100 * probability)
            measurements.append(
                replace(
                    base,
                    trial_index=np.arange(100),
                    vin_diff_v=np.full(100, vin_diff_v),
                    vin_cm_v=np.full(100, vin_cm_v),
                    decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
                )
            )
        return measurements

    def classify(*groups: list[AnalysisDecisions]):
        return analyze_common_mode([measurement for values in groups for measurement in values])

    valid = group(0.6, (0.0, 0.5, 1.0))
    stuck_low = group(0.8, (0.0, 0.0, 0.0))
    stuck_high = group(1.0, (1.0, 1.0, 1.0))
    classified = classify(valid, stuck_low, stuck_high)
    assert classified.validity == ("valid", "stuck-low", "stuck-high")
    np.testing.assert_allclose(classified.vin_cm_v, (0.6, 0.8, 1.0))
    # each common mode's S-curve, a row
    np.testing.assert_allclose(classified.decision_probability[0], (0.0, 0.5, 1.0))
    assert classified.trial_count.tolist() == [[100] * 3] * 3

    assert classify(stuck_low).validity == ("unbracketed",)
    outside_neighbor_transition = group(0.8, (0.0, 0.0, 0.0), center_v=0.012)
    assert classify(valid, outside_neighbor_transition).validity == ("valid", "unbracketed")

    # Single-common-mode fits cannot report a stuck output; only the
    # common-mode analysis, which sees the neighbors, can.
    assert analyze_offset_noise(stuck_low).validity == "unbracketed"
    with pytest.raises(ValueError, match="at one common mode"):
        analyze_common_mode([replace(valid[0], vin_cm_v=np.linspace(0.6, 0.7, 100))])
    with pytest.raises(ValueError, match="one input common mode"):
        analyze_offset_noise([*valid, *stuck_low])
