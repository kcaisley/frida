"""The comparator's analyses on synthetic measurements: a testbench run's signals on an uneven time
axis (as Spectre's own steps leave them), and decisions as a capture or a simulation gives them."""

from __future__ import annotations

import dataclasses
import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest
from basil.HL.tektronix_oscilloscope import CapturedWaveform, XScale, YScale

from flow import adc
from flow.adc.sim import symbol160_init4_samp20_comp11111100_logic11000011
from flow.adc.test_analysis import adc_measurement, adc_timing_measurement
from flow.analysis.types import MeasAdc
from flow.pipeline import Meas, MeasInfo, Plot, Wave

from . import analysis, plots
from .analysis import (
    analyze_clock_check,
    analyze_common_mode,
    analyze_decisions,
    analyze_delay,
    analyze_edge_eye,
    analyze_kickback,
    analyze_metastability,
    analyze_offset_noise,
    analyze_power,
    analyze_response,
    analyze_scope_edges,
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
    curve = replace(
        decisions_at(),
        trial_index=np.arange(30),
        vin_diff_v=np.repeat([-1e-3, 0.0, 1e-3], 10),
        vin_cm_v=np.full(30, 0.6),
        decision=np.repeat([0, 1, 1], 10).astype(np.uint8) * (np.arange(30) % 2 | (np.arange(30) >= 20)),
    )
    fit = analyze_offset_noise([curve])
    values = metrics(
        small=delay,
        large=delay,
        metastability=analyze_metastability(meas, delay=delay),
        power=analyze_power([meas, meas]),
        kickback=analyze_kickback(meas),
        common_mode=analyze_common_mode([curve]),
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


def scope_records(captures: int = 4) -> list[MeasAdc]:
    """A converter's scope records as the bench takes them (``scan_adc``'s paired COMP and COMP_OUT
    captures, at 320 MBd): ``captures`` records of one conversion, COMP high six symbols of each
    decision, COMP_OUT toggling 5 ns after each rise but at B3, which it holds; each capture a
    little later than the one before."""
    sequence = symbol160_init4_samp20_comp11111100_logic11000011
    rate = 320e6
    step_s = 0.1e-9
    time_s = np.arange(-20e-9, 600e-9, step_s)
    scale = XScale(step_s, float(time_s[0]), "s")
    edge_symbols = [index for index, bit in enumerate(sequence.comp) if bit == "1" and sequence.comp[index - 1] == "0"]
    records = []
    for capture_index in range(captures):
        edge_s = np.asarray(edge_symbols) / rate + capture_index * 0.03e-9
        comp_v = np.full(len(time_s), -0.2)
        out_v = np.full(len(time_s), -0.2)
        output_high = False
        for decision, edge in enumerate(edge_s):
            comp_v[(time_s >= edge) & (time_s < edge + 6 / rate)] = 0.2
            if decision != 3:
                output_high = not output_high
                ramp = np.clip((time_s - edge - 5e-9 - capture_index * 0.02e-9) / 1e-9, 0, 1)
                out_v += (0.4 if output_high else -0.4) * ramp
        records.append(
            {
                channel: CapturedWaveform(channel, np.rint(values * 1000).astype(int), values, scale, YScale(0.2, -0.2))
                for channel, values in ((3, comp_v), (2, out_v))
            }
        )
    base = adc_measurement([2048], observed_adc=1)
    params = replace(base.param, tb=replace(base.param.tb, symbol_rate=rate, **sequence.as_tb_fields()))
    return [
        replace(
            base,
            param=params,
            wave=Wave(
                record_index=np.asarray([0]),
                time_s=time_s,
                v={
                    "seq_comp": np.asarray(record[3].data)[None, :],
                    "seq_logic": np.zeros((1, len(time_s))),
                    "comp_out": np.asarray(record[2].data)[None, :],
                },
            ),
        )
        for record in records
    ]


def test_the_scope_edges_time_each_decision_and_fold_comp_out_at_its_rise() -> None:
    edges = analyze_scope_edges([adc.analyze_conversions(record) for record in scope_records()])
    bounds = edges.delay_bounds_s
    assert bounds[0] == pytest.approx(5.5e-9, abs=0.1e-9)
    assert bounds[1] == pytest.approx(5.56e-9, abs=0.1e-9)
    # B3 holds COMP_OUT: no transition to time in any record
    assert edges.unchanged[3] == 4
    assert np.count_nonzero(np.isfinite(edges.delays_s[:, 3])) == 0
    period_s = 8 / 320e6
    assert edges.decision_period_s == pytest.approx(period_s)
    assert edges.conversion_rate_hz == pytest.approx(320e6 / 160)
    # COMP is high six symbols of each decision, from each rise
    assert edges.clock_high_s == pytest.approx(6 / 320e6, abs=0.2e-9)
    np.testing.assert_allclose(edges.rise_s, np.arange(17) * period_s, atol=0.2e-9)
    np.testing.assert_allclose(edges.fall_s - edges.rise_s, 6 / 320e6, atol=0.2e-9)
    # the maps: each record (or decision) once in every time cell inside the records, over COMP_OUT's range
    assert edges.eye_share.shape == (len(edges.voltage_v) - 1, len(edges.eye_time_s) - 1)
    np.testing.assert_allclose(np.nansum(edges.eye_share, axis=0), 1.0)
    np.testing.assert_allclose(np.nansum(edges.timing_share, axis=0), 1.0)
    assert edges.voltage_v[0] < -0.2 and edges.voltage_v[-1] > 0.2
    assert edges.eye_time_s[0] == pytest.approx(-0.2 * period_s) and edges.eye_time_s[-1] == pytest.approx(period_s)
    # each decision's delays a column: B3's empty, the others' shares one in all
    assert edges.response_share.shape == (48, 17)
    assert np.all(np.isnan(edges.response_share[:, 3])) and math.isnan(edges.response_median_s[3])
    np.testing.assert_allclose(np.nansum(np.delete(edges.response_share, 3, axis=1), axis=0), 1.0)
    assert edges.response_s[0] == pytest.approx(bounds[0]) and edges.response_s[-1] == pytest.approx(bounds[1])


def test_the_scope_edges_take_one_sequence_and_rate() -> None:
    records = scope_records(2)
    faster = replace(records[1], param=replace(records[1].param, tb=replace(records[1].param.tb, symbol_rate=640e6)))
    with pytest.raises(ValueError, match="one sequence and symbol rate"):
        analyze_scope_edges([adc.analyze_conversions(records[0]), adc.analyze_conversions(faster)])


def repeated(measurement: MeasAdc, conversions: int = 2) -> MeasAdc:
    """A simulated capture's one conversion saved ``conversions`` times."""
    wave = measurement.wave
    assert wave is not None
    return replace(
        measurement,
        param=replace(measurement.param, conversions=conversions),
        conversion_index=np.arange(conversions),
        bout=np.repeat(measurement.bout, conversions, axis=0),
        dout_raw=np.repeat(measurement.dout_raw, conversions),
        dout=np.repeat(measurement.dout, conversions),
        vin_diff_v=np.repeat(measurement.vin_diff_v, conversions),
        fastrx_word=np.repeat(measurement.fastrx_word, conversions) if measurement.fastrx_word is not None else None,
        wave=replace(
            wave,
            record_index=np.arange(conversions),
            v={name: np.repeat(values, conversions, axis=0) for name, values in wave.v.items()},
        ),
    )


def test_the_edge_eye_folds_every_conversion_and_takes_the_xc_latchs_magnitude() -> None:
    eye = analyze_edge_eye(adc.analyze_conversions(repeated(adc_timing_measurement())))
    assert eye.records == 2
    period_s = 2e-9
    assert eye.decision_period_s == pytest.approx(period_s)
    np.testing.assert_allclose(eye.decision_edge_s, np.arange(17) * period_s, atol=20e-12)
    # the clock is high 0.8 ns of each decision
    assert eye.clock_high_s == pytest.approx(0.8e-9, abs=20e-12)
    np.testing.assert_allclose(eye.fall_s - eye.decision_edge_s, 0.8e-9, atol=20e-12)
    # the eye from 0.1 periods before each rise to 1.1 after, the conversion to a period after its last
    assert eye.eye_time_s[0] == pytest.approx(-0.2e-9) and eye.eye_time_s[-1] == pytest.approx(2.2e-9)
    assert eye.timing_time_s[-1] > eye.decision_edge_s[-1] + 0.99 * period_s
    # every decision of both conversions in each eye cell (34 of them), every conversion in each conversion cell
    for share in (eye.sr_eye, eye.xc_eye):
        np.testing.assert_allclose(np.nansum(share, axis=0), 1.0)
    for share in (eye.sr_timing, eye.xc_timing):
        assert np.nanmax(np.nansum(share, axis=0)) == pytest.approx(1.0)
    # |P - N| is never below zero: no cell under 0 V holds anything
    below = (eye.voltage_v[1:] <= 0) & (eye.voltage_v[:-1] < 0)
    assert np.all(np.isnan(eye.xc_eye[below])) and np.all(np.isnan(eye.xc_timing[below]))
    assert eye.supply_v == pytest.approx(1.2)


def test_the_response_counts_held_decisions_and_maps_each_decisions_timed_ones() -> None:
    response = analyze_response(adc.analyze_conversions(adc_timing_measurement()))
    assert len(np.unique(response.decision_index)) == 17
    second = response.decision_index == 1
    assert np.count_nonzero(response.sr_held[second]) == 1
    assert np.count_nonzero(np.isfinite(response.sr_response_s[second])) == 0
    # each decision's timed responses one in all, a held decision's column empty
    assert response.sr_share.shape == (48, 17)
    assert np.all(np.isnan(response.sr_share[:, 1])) and math.isnan(response.sr_median_s[1])
    timed = np.isfinite(response.sr_median_s)
    np.testing.assert_allclose(np.nansum(response.sr_share[:, timed], axis=0), 1.0)
    np.testing.assert_allclose(response.xc_median_s, response.internal_response_s, equal_nan=True)


def test_a_decisions_shares_are_of_its_own_timed_responses() -> None:
    """Four responses timed of one decision's forty, and forty timed four times each: each cell the
    same share of its decision's timed ones."""
    values = np.array([1.0, 1.1, 1.2, 1.3]) * 1e-9
    decision = np.zeros(40, dtype=int)
    sparse = analysis._per_decision("xc", decision, np.r_[values, np.full(36, np.nan)], 1)
    dense = analysis._per_decision("sr", decision, np.repeat(values, 10), 1)
    np.testing.assert_allclose(sparse["xc_share"], dense["sr_share"], equal_nan=True)
    assert np.nansum(sparse["xc_share"]) == pytest.approx(1.0)
    assert np.count_nonzero(np.isfinite(sparse["xc_share"])) == 4
    # none timed: no cells, the median NaN
    empty = analysis._per_decision("xc", decision, np.full(40, np.nan), 1)
    assert empty["xc_s"].size == 0 and empty["xc_share"].shape == (0, 1) and math.isnan(empty["xc_median_s"][0])


def test_a_records_analyses_ignore_a_high_clock_at_its_boundary() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    clock = measurement.wave.v["clk_comp"].copy()
    clock[0, 0] = 1.2  # Tail of the preceding conversion, not a new COMP edge.
    measurement = replace(measurement, wave=replace(measurement.wave, v={**measurement.wave.v, "clk_comp": clock}))
    np.testing.assert_array_equal(adc.analyze_timing_closure(measurement).decision_index, np.arange(17))
    conversions = adc.analyze_conversions(measurement)
    np.testing.assert_array_equal(analyze_response(conversions).decision_index, np.arange(17))
    np.testing.assert_allclose(analyze_edge_eye(conversions).decision_edge_s, np.arange(17) * 2e-9, atol=20e-12)


def test_the_response_requires_both_xc_rails_and_times_one_sr_output() -> None:
    measurement = adc_timing_measurement()
    assert measurement.wave is not None
    time = measurement.wave.time_s
    signals = {name: values.copy() for name, values in measurement.wave.v.items()}
    glitch = (time >= 1.5e-9) & (time < 1.6e-9)
    signals["comp.latch_p"][0, glitch] = 0.5
    signals["comp_out_p"][0, glitch] = 0.5
    not_low_enough = (time >= 5e-9) & (time < 5.8e-9)
    signals["comp.latch_p"][0, not_low_enough] = 0.7
    weak_midpoint_decision = (time >= 7.25e-9) & (time < 7.8e-9)
    signals["comp.latch_p"][0, weak_midpoint_decision] = 0.7
    signals["comp.latch_n"][0, weak_midpoint_decision] = 0.55
    del signals["comp_out_n"]
    result = analyze_response(adc.analyze_conversions(replace(measurement, wave=replace(measurement.wave, v=signals))))

    np.testing.assert_array_equal(result.decision_index, np.arange(17))
    assert result.internal_response_s[0] == pytest.approx(0.595e-9, abs=11e-12)
    assert result.sr_response_s[0] == pytest.approx(0.595e-9, abs=11e-12)
    assert result.sr_held[1] and np.isnan(result.sr_response_s[1])
    assert np.isnan(result.internal_response_s[2])
    assert np.isfinite(result.sr_response_s[2])
    assert np.isfinite(result.internal_response_s[3])
