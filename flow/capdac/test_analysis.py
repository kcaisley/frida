"""The capacitive DAC's analyses on synthetic data: RC steps of known delay, time constant, amplitude
and gain (``analyze_settling``), Monte Carlo draws of known plates (``analyze_mismatch``), and the
bench's A-to-B switching curves of known transitions as a converter captures them (``MeasCdac``,
each point as ``adc.analyze_switching`` gives it: ``analyze_transition``, ``analyze_cap_mismatch``)."""

import math
from dataclasses import replace
from datetime import UTC, datetime

import hdl21 as h
import numpy as np
import pytest

from flow import adc, capdac, comp
from flow.analysis.types import MeasCdac, Wave
from flow.pipeline import Meas, MeasInfo
from flow.scans.scan_cdac import _build_cdac_params

# an 8-bit binary array of unit capacitors: seven stages, 64 to 1 units
PARAMS = capdac.Params(bits=8, redundancy=capdac.Redundancy.BINARY, extra=0, weight_impl=capdac.WeightImpl.UNIT_CAPS)
VDD, EDGE = 1.2, 30e-12
TAUS = (200e-12, 150e-12, 100e-12, 80e-12, 60e-12, 50e-12, 40e-12)


def _rc(taus: tuple[float, ...], *, lag: float = 40e-12, window: float = 4e-9, gain: float = 1.0) -> Meas:
    """Each stage's main bottom plate and the differential top plate an RC of ``taus[stage]`` starting
    ``lag`` after its state's edge, the top plate stepping by ``gain`` times the design's step, on
    the simulator's time axis as ``flow.pipeline.read`` gives it."""
    tb = capdac.TbParams(params=PARAMS, window_s=window, waveform_sample_interval_s=window / 4000, vdd=VDD)
    time_s = np.arange(0.0, tb.stop_s + window / 8000, window / 4000)
    steps = gain * tb.ideal_step_v
    differential = np.full_like(time_s, -steps.sum() / 2)
    v = {}
    for stage, tau in enumerate(taus):
        up, down = (tb.window_start_s(stage, rising) + EDGE / 2 for rising in (True, False))
        state = np.where((time_s >= up) & (time_s < down), VDD, 0.0)
        rising = 1 - np.exp(-np.clip(time_s - up - lag, 0.0, None) / tau)
        falling = np.exp(-np.clip(time_s - down - lag, 0.0, None) / tau)
        fraction = np.where(time_s < down, rising, rising * falling)
        v[f"dac_state_p_{stage}"] = state
        v[f"dut_p.main_{stage}"] = VDD * fraction
        differential = differential + steps[stage] * fraction
    v["vdac_p"], v["vdac_n"] = 0.6 + differential / 2, 0.6 - differential / 2
    return Meas(
        group=None,
        index=None,
        dut=PARAMS,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 11, 4, tzinfo=UTC)),
        param=tb,
        time_s=time_s,
        v=v,
    )


def test_the_run_gives_the_designs_plates_and_steps():
    """``TbParams`` sizes the design's plates from its weights: unit capacitors, no difference
    plates; each side's switched capacitance the kT/C sizing's; the steps the weights' shares."""
    tb = capdac.TbParams(params=PARAMS, window_s=4e-9, waveform_sample_interval_s=1e-12, vdd=VDD)
    assert tb.weights == (64, 32, 16, 8, 4, 2, 1) and tb.stages == 7 and not tb.diff_f.any()
    np.testing.assert_allclose(tb.main_f / tb.main_f[-1], tb.weights)
    assert tb.full_scale_v == pytest.approx(VDD) and tb.lsb_v == pytest.approx(2 * VDD / 2**8)
    np.testing.assert_allclose(tb.ideal_step_v, 2 * VDD * np.asarray(tb.weights) / sum(tb.weights))


def test_an_rc_step_settles_when_its_exponential_reaches_half_an_lsb():
    lag = 40e-12
    meas = _rc(TAUS, lag=lag)
    result = capdac.analyze_settling(meas)
    lsb = meas.param.lsb_v
    assert result.gain == pytest.approx(1.0, rel=1e-6) and result.settled
    assert result.lsb_v == pytest.approx(lsb, rel=1e-6) and result.full_scale_v == pytest.approx(VDD, rel=1e-6)
    steps = meas.param.ideal_step_v
    np.testing.assert_allclose(result.step_rise_v, steps, rtol=1e-6)
    np.testing.assert_allclose(result.step_fall_v, -steps, rtol=1e-6)
    assert result.step_error_lsb < 1e-3
    resolution = 2e-12  # a sample is 1 ps; the edges are interpolated
    expected_delay = lag + np.asarray(TAUS) * math.log(2)
    expected_settling = lag + np.asarray(TAUS) * np.log(steps / (lsb / 2))
    for measured in (result.delay_rise_s, result.delay_fall_s):
        np.testing.assert_allclose(measured, expected_delay, atol=resolution)
    for measured in (result.settling_rise_s, result.settling_fall_s):
        np.testing.assert_allclose(measured, expected_settling, atol=resolution)
    # the model's time constant: started at the driver's 50 %, at half an LSB when SPICE is
    modeled = result.delay_s + result.tau_s * np.log(np.abs(result.step_v) / (lsb / 2))
    np.testing.assert_allclose(modeled, result.settling_s, rtol=1e-9)
    metrics = capdac.metrics(settling=result)
    assert metrics["stages"] == 7 and metrics["settling_max_s"] == pytest.approx(max(expected_settling), abs=2e-12)
    assert metrics["settling_msb_s"] == result.settling_s[0] and metrics["lsb_v"] == result.lsb_v


def test_a_drawn_array_below_its_design_scales_its_full_scale_and_lsb():
    """Steps 0.65 of the design's (the top plates' load beyond the design's plates): the gain, and the
    full scale and LSB the settling is measured to, scale with it; the weights still fit."""
    result = capdac.analyze_settling(_rc(TAUS, gain=0.65))
    assert result.gain == pytest.approx(0.65, rel=1e-6)
    assert result.full_scale_v == pytest.approx(0.65 * VDD, rel=1e-6) and result.step_error_lsb < 1e-3


def test_a_step_still_moving_at_its_window_middle_is_not_settled():
    result = capdac.analyze_settling(_rc((900e-12, *TAUS[1:]), window=4e-9))
    assert not result.settled
    assert result.settling_s[0] > result.window_s / 2


def test_a_step_inside_the_tolerance_has_no_time_constant():
    def settling(settling_s: float, delay_s: float, step_v: float) -> capdac.AnalysisSettling:
        one = np.asarray([settling_s])
        return capdac.AnalysisSettling(
            group=None,
            index=None,
            dut=None,
            lsb_v=1e-3,
            full_scale_v=0.5,
            gain=1.0,
            window_s=4e-9,
            ideal_step_v=np.asarray([step_v]),
            step_rise_v=np.asarray([step_v]),
            step_fall_v=np.asarray([-step_v]),
            delay_rise_s=np.asarray([delay_s]),
            delay_fall_s=np.asarray([delay_s]),
            settling_rise_s=one,
            settling_fall_s=one,
        )

    assert settling(1e-9, 0.1e-9, 0.4e-3).tau_s[0] == 0.0
    assert settling(0.05e-9, 0.1e-9, 2e-3).tau_s[0] == 0.0
    assert settling(1.1e-9, 0.1e-9, 0.5e-3 * math.e).tau_s[0] == pytest.approx(1e-9)


def test_the_record_plots_the_settling_and_the_model_by_stage():
    result = capdac.analyze_settling(_rc(TAUS))
    settling, model = capdac.plot_settling_stage(result), capdac.plot_model_stage(result)
    assert (settling.name, model.name) == ("settling_stage", "model_stage")
    assert settling.x == model.x == list(range(7))
    assert settling.series["settling"] == list(result.settling_s)
    assert model.series == {"delay": list(result.delay_s), "time constant": list(result.tau_s)}
    record = capdac.record({"settling": _rc(TAUS)})
    assert [plot.name for plot in record.details] == ["settling_stage", "model_stage"]
    assert record.waves == {"settling": "settling"} and record.metrics["stages"] == 7
    with pytest.raises(RuntimeError, match="did not settle"):
        capdac.record({"settling": _rc((900e-12, *TAUS[1:]))})


def _draws(main_p: np.ndarray, main_n: np.ndarray) -> Meas:
    """A Monte Carlo measurement of ``PARAMS`` whose runs drew these main plates (F, a row a run), as
    ``flow.pipeline.read`` gives one: each plate's probe in fF, a value a run."""
    tb = capdac.TbParams(params=PARAMS, window_s=4e-9, waveform_sample_interval_s=1e-12, mc_runs=len(main_p))
    v = {
        f"cmain_{side}_{stage}.drawn": plates[:, stage] * 1e15
        for side, plates in (("p", main_p), ("n", main_n))
        for stage in range(tb.stages)
    }
    return Meas(
        group=1,
        index=None,
        dut=PARAMS,
        info=MeasInfo(
            backend="spice", timestamp_utc=datetime(2026, 11, 4, tzinfo=UTC), readbacks={"runs": len(main_p)}
        ),
        param=tb,
        v=v,
    )


def test_nominal_draws_are_ideal_and_a_heavy_msb_leaves_a_gap_no_calibration_recovers():
    tb = capdac.TbParams(params=PARAMS, window_s=4e-9, waveform_sample_interval_s=1e-12)
    nominal = np.tile(tb.main_f, (2, 1))
    heavy = nominal.copy()
    heavy[1, 0] *= 1.01  # the second run's MSB 0.64 of a unit heavy, both sides
    result = capdac.analyze_mismatch(_draws(heavy, heavy))
    assert result.runs == 2
    # the nominal run: every code one LSB wide, nothing to recover
    assert result.dac_inl_lsb[0] == pytest.approx(0.0, abs=1e-9) and result.inl_lsb[0] == pytest.approx(0.0, abs=1e-6)
    assert result.gap_lsb[0] == pytest.approx(0.0, abs=1e-9) and result.missing_codes[0] == 0
    # the heavy MSB: a binary array has no redundancy below it, so the mid-scale code widens past
    # one LSB and no weight recovers it
    assert result.gap_lsb[1] > 0.1 and result.dac_dnl_lsb[1] > 0.1
    assert result.dac_inl_curve_lsb.shape == (2**7,)


# ---- the bench's switching curves (flow/analysis/test_cdac.py until their analyses moved here)


def switched(points: list[MeasCdac]) -> list[capdac.AnalysisSwitching]:
    """Each captured point of a switching curve as the CDAC sees it (``adc.analyze_switching``)."""
    return [adc.analyze_switching(point) for point in points]


def transition_of(curve: list[MeasCdac]):
    """Fit one switching curve the way the runner does: S-curve fit, then CDAC placement."""

    points = switched(curve)
    return capdac.analyze_transition(points, offset=comp.analyze_offset_noise([capdac.analyze_decisions(points)]))


def cap_mismatch_of(measurements: list[MeasCdac], comparator: comp.AnalysisOffsetNoise):
    """Fit every curve of one ADC, preferring its fine sweep stage, then decompose (as the runner does)."""

    curves: dict[tuple[object, ...], list[MeasCdac]] = {}
    for measurement in measurements:
        params = measurement.param
        curves.setdefault(
            (params.cdac_side, params.cdac_element, params.cdac_direction, params.tb.dac_diffcaps), []
        ).append(measurement)
    transitions = [
        transition_of([point for point in curve if point.param.sweep_stage == "fine"] or curve)
        for curve in curves.values()
    ]
    return capdac.analyze_cap_mismatch(switched(measurements), transitions=transitions, comparator=comparator)


def comparator_offset(measurement: MeasCdac, offset_v: float, *, index: int | None = None) -> comp.AnalysisOffsetNoise:
    """Return a valid comparator characterization of the measured ADC's comparator."""

    return comp.AnalysisOffsetNoise(
        group=measurement.group,
        index=measurement.index if index is None else index,
        dut=measurement.param.tb.params.comp,
        vin_cm_v=0.8,
        vin_diff_v=np.asarray([offset_v - 1e-3, offset_v, offset_v + 1e-3]),
        decision_probability=np.asarray([0.0, 0.5, 1.0]),
        trial_count=np.asarray([100, 100, 100]),
        offset_v=offset_v,
        noise_sigma_v=5e-4,
        decision_polarity=1,
        validity="valid",
    )


def test_cap_mismatch_recovers_main_diff_and_direction_pairs() -> None:
    comparator_offset_v = 8.0e-3
    expected_mode_weights = {0: 0.20, 1: 0.10}
    measurements = []
    for direction in ("1to0", "0to1"):
        for diffcaps, normalized_weight in expected_mode_weights.items():
            direction_sign = 1.0 if direction == "0to1" else -1.0
            transition_v = comparator_offset_v - direction_sign * normalized_weight * 1.2
            for input_index, probability in enumerate((0.0, 0.5, 1.0)):
                vin_diff_v = transition_v + (input_index - 1) * 10e-3
                params = _build_cdac_params(
                    adc_index=0,
                    side="p",
                    element=15,
                    direction=direction,
                    dac_diffcaps=diffcaps,
                    vin_diff_v=vin_diff_v,
                    conversions=100,
                    sweep_stage="fine",
                )
                ones = round(100 * probability)
                decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
                before_p = np.tile(params.tb.dac_astate_p, (100, 1))
                before_n = np.tile(params.tb.dac_astate_n, (100, 1))
                after_p = np.tile(params.tb.dac_bstate_p, (100, 1))
                after_n = np.tile(params.tb.dac_bstate_n, (100, 1))
                measurements.append(
                    MeasCdac(
                        group=params.board_id,
                        index=params.observed_adc,
                        dut=params.tb.params.cdac,
                        info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 4, tzinfo=UTC)),
                        param=params,
                        trial_index=np.arange(100),
                        dac_state_p=after_p,
                        dac_state_n=after_n,
                        vin_diff_v=np.full(100, vin_diff_v),
                        decision=decisions,
                        dac_state_before_p=before_p,
                        dac_state_before_n=before_n,
                        vin_cm_v=np.full(100, 0.8),
                        fastrx_word=np.asarray(
                            [(1 << 28) | (frame << 17) | int(decision) for frame, decision in enumerate(decisions)],
                            dtype=np.uint32,
                        ),
                        fastrx_frame=np.arange(100, dtype=np.uint32),
                        wave=Wave(
                            record_index=np.asarray([0], dtype=np.int64),
                            time_s=np.asarray([0.0, 1e-9]),
                            v={
                                "vin_diff": np.asarray([[vin_diff_v, vin_diff_v]]),
                                "seq_comp": np.asarray([[0.0, 1.2]]),
                                "comp_out": np.asarray([[0.0, 1.2]]),
                            },
                        ),
                    )
                )
            base = measurements[-1]
            coarse_v = transition_v + 20e-3
            coarse_params = replace(
                base.param,
                sweep_stage="coarse",
                tb=replace(base.param.tb, vin_diff=h.Vdc.Params(dc=coarse_v)),
            )
            measurements.append(
                replace(
                    base,
                    param=coarse_params,
                    vin_diff_v=np.full(100, coarse_v),
                    decision=np.zeros(100, dtype=np.uint8),
                    fastrx_word=np.asarray(
                        [(1 << 28) | (frame << 17) for frame in range(100)],
                        dtype=np.uint32,
                    ),
                    wave=replace(base.wave, v={**base.wave.v, "vin_diff": np.asarray([[coarse_v, coarse_v]])}),
                )
            )

    result = cap_mismatch_of(measurements, comparator_offset(measurements[0], comparator_offset_v))

    assert (result.group, result.index) == (0, 0)
    assert result.dut == measurements[0].dut
    assert result.effective_fraction[0, 15] == pytest.approx(0.10)
    np.testing.assert_allclose(result.effective_fraction_by_direction[0, 15], (0.10, 0.10))
    assert result.main_fraction[0, 15] == pytest.approx(0.15)
    assert result.diff_fraction[0, 15] == pytest.approx(0.05)
    np.testing.assert_allclose(result.direction_bias[0, 15], 0.0, atol=1e-15)
    assert np.all(np.isnan(result.main_fraction[1]))


def test_cap_mismatch_retains_side_asymmetry_and_direction_bias() -> None:
    comparator_offset_v = -6e-3
    measurements = []
    expected = {
        "p": {0: (0.20, 0.02), 1: (0.10, 0.01)},
        "n": {0: (0.18, 0.015), 1: (0.12, -0.005)},
    }
    for side in ("p", "n"):
        side_sign = 1.0 if side == "p" else -1.0
        for direction_index, direction in enumerate(("1to0", "0to1")):
            direction_sign = 1.0 if direction == "0to1" else -1.0
            for diffcaps in (0, 1):
                mean_weight, bias = expected[side][diffcaps]
                oriented_weight = mean_weight + (bias if direction_index == 0 else -bias)
                signed_step = side_sign * direction_sign * oriented_weight
                transition_v = comparator_offset_v - signed_step * 1.2
                for input_index, probability in enumerate((0.0, 0.5, 1.0)):
                    vin_diff_v = transition_v + (input_index - 1) * 10e-3
                    params = _build_cdac_params(
                        adc_index=0,
                        side=side,
                        element=15,
                        direction=direction,
                        dac_diffcaps=diffcaps,
                        vin_diff_v=vin_diff_v,
                        conversions=100,
                        sweep_stage="coarse",
                    )
                    ones = round(100 * probability)
                    decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
                    before_p = np.tile(params.tb.dac_astate_p, (100, 1))
                    before_n = np.tile(params.tb.dac_astate_n, (100, 1))
                    after_p = np.tile(params.tb.dac_bstate_p, (100, 1))
                    after_n = np.tile(params.tb.dac_bstate_n, (100, 1))
                    measurements.append(
                        MeasCdac(
                            group=params.board_id,
                            index=params.observed_adc,
                            dut=params.tb.params.cdac,
                            info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 4, tzinfo=UTC)),
                            param=params,
                            trial_index=np.arange(100),
                            dac_state_p=after_p,
                            dac_state_n=after_n,
                            vin_diff_v=np.full(100, vin_diff_v),
                            decision=decisions,
                            dac_state_before_p=before_p,
                            dac_state_before_n=before_n,
                            vin_cm_v=np.full(100, 0.8),
                            fastrx_word=np.asarray(
                                [(1 << 28) | (frame << 17) | int(decision) for frame, decision in enumerate(decisions)],
                                dtype=np.uint32,
                            ),
                            fastrx_frame=np.arange(100, dtype=np.uint32),
                            wave=Wave(
                                record_index=np.asarray([0], dtype=np.int64),
                                time_s=np.asarray([0.0, 1e-9]),
                                v={
                                    "vin_diff": np.asarray([[vin_diff_v, vin_diff_v]]),
                                    "seq_comp": np.asarray([[0.0, 1.2]]),
                                    "comp_out": np.asarray([[0.0, 1.2]]),
                                },
                            ),
                        )
                    )

    for vin_diff_v in (-20e-3, 0.0, 20e-3):
        params = _build_cdac_params(
            adc_index=0,
            side="p",
            element=14,
            direction="1to0",
            dac_diffcaps=0,
            vin_diff_v=vin_diff_v,
            conversions=100,
            sweep_stage="coarse",
        )
        base = measurements[0]
        measurements.append(
            replace(
                base,
                param=params,
                dac_state_p=np.tile(params.tb.dac_bstate_p, (100, 1)),
                dac_state_n=np.tile(params.tb.dac_bstate_n, (100, 1)),
                vin_diff_v=np.full(100, vin_diff_v),
                decision=np.ones(100, dtype=np.uint8),
                dac_state_before_p=np.tile(params.tb.dac_astate_p, (100, 1)),
                dac_state_before_n=np.tile(params.tb.dac_astate_n, (100, 1)),
                wave=replace(base.wave, v={**base.wave.v, "vin_diff": np.asarray([[vin_diff_v, vin_diff_v]])}),
            )
        )

    result = cap_mismatch_of(measurements, comparator_offset(measurements[0], comparator_offset_v))

    assert result.effective_fraction[0, 15] == pytest.approx(0.10)
    assert result.effective_fraction[1, 15] == pytest.approx(0.12)
    np.testing.assert_allclose(result.effective_fraction_by_direction[0, 15], (0.11, 0.09))
    np.testing.assert_allclose(result.effective_fraction_by_direction[1, 15], (0.115, 0.125))
    assert result.main_fraction[0, 15] == pytest.approx(0.15)
    assert result.main_fraction[1, 15] == pytest.approx(0.15)
    assert result.diff_fraction[0, 15] == pytest.approx(0.05)
    assert result.diff_fraction[1, 15] == pytest.approx(0.03)
    np.testing.assert_allclose(result.direction_bias[0, 15], (0.02, 0.01))
    np.testing.assert_allclose(result.direction_bias[1, 15], (0.015, -0.005))
    assert np.isnan(result.main_fraction[0, 14])
    assert np.isnan(result.diff_fraction[0, 14])
    assert np.isnan(result.direction_bias[0, 14, 0])


def _curve(side: str, direction: str, diffcaps: int, transition_v: float) -> list[MeasCdac]:
    measurements = []
    for input_index, probability in enumerate((0.0, 0.5, 1.0)):
        vin_diff_v = transition_v + (input_index - 1) * 10e-3
        params = _build_cdac_params(
            adc_index=0,
            side=side,
            element=15,
            direction=direction,
            dac_diffcaps=diffcaps,
            vin_diff_v=vin_diff_v,
            conversions=100,
            sweep_stage="fine",
        )
        ones = round(100 * probability)
        decisions = np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
        measurements.append(
            MeasCdac(
                group=params.board_id,
                index=params.observed_adc,
                dut=params.tb.params.cdac,
                info=MeasInfo(backend="physical", timestamp_utc=datetime(2026, 8, 4, tzinfo=UTC)),
                param=params,
                trial_index=np.arange(100),
                dac_state_p=np.tile(params.tb.dac_bstate_p, (100, 1)),
                dac_state_n=np.tile(params.tb.dac_bstate_n, (100, 1)),
                vin_diff_v=np.full(100, vin_diff_v),
                decision=decisions,
                wave=None,
            )
        )
    return measurements


def test_a_transition_records_its_curves_coordinates_and_rejects_mixed_curves() -> None:
    curve = _curve("p", "0to1", 1, 4e-3)
    transition = transition_of(curve)
    assert (transition.side, transition.element, transition.direction, transition.diffcaps) == ("p", 15, "0to1", 1)
    assert transition.valid
    assert transition.transition_v == pytest.approx(4e-3)
    with pytest.raises(ValueError, match="not made from these measurements"):
        capdac.analyze_transition(
            switched(curve),
            offset=comp.analyze_offset_noise([capdac.analyze_decisions(switched(_curve("p", "0to1", 1, 9e-3)))]),
        )
    with pytest.raises(ValueError, match="exactly one switching curve"):
        mixed = [*curve, *_curve("n", "0to1", 1, 4e-3)]
        capdac.analyze_transition(
            switched(mixed), offset=comp.analyze_offset_noise([capdac.analyze_decisions(switched(mixed))])
        )


def test_cap_mismatch_rejects_mismatched_or_missing_prior_results() -> None:
    curve = _curve("p", "0to1", 1, 4e-3)
    transition = transition_of(curve)
    with pytest.raises(ValueError, match="comparator offset"):
        capdac.analyze_cap_mismatch(
            switched(curve), transitions=[transition], comparator=comparator_offset(curve[0], 0.0, index=3)
        )
    with pytest.raises(ValueError, match="exactly one fit per measured switching curve"):
        capdac.analyze_cap_mismatch(
            switched([*curve, *_curve("n", "0to1", 1, 4e-3)]),
            transitions=[transition],
            comparator=comparator_offset(curve[0], 0.0),
        )


def test_the_points_of_one_converter_share_the_designs_expectation() -> None:
    """Each point carries the design's expectation of each stage's effective fraction (with the top
    plate's parasitic the capture recorded), which the decomposition carries for the error from it;
    points that disagree on it are not decomposed together."""
    readbacks = {"cdac_topplate_parasitic_weight": 100.0}
    curve = [replace(point, info=replace(point.info, readbacks=readbacks)) for point in _curve("p", "0to1", 1, 4e-3)]
    weights = np.asarray(capdac.Model.weights(curve[0].param.tb.params.cdac), dtype=np.float64)
    expected = weights / (np.sum(65.0 * np.ceil(weights / 64.0)) + 100.0)
    np.testing.assert_allclose(adc.analyze_switching(curve[0]).expected_fraction, expected)
    result = capdac.analyze_cap_mismatch(
        switched(curve), transitions=[transition_of(curve)], comparator=comparator_offset(curve[0], 0.0)
    )
    np.testing.assert_allclose(result.expected_fraction, expected)
    np.testing.assert_allclose(result.fraction_error, result.fraction - expected, equal_nan=True)
    other = replace(curve[-1], info=replace(curve[-1].info, readbacks={"cdac_topplate_parasitic_weight": 200.0}))
    inconsistent = [*curve[:-1], other]
    with pytest.raises(ValueError, match="inconsistent"):
        capdac.analyze_cap_mismatch(
            switched(inconsistent),
            transitions=[transition_of(inconsistent)],
            comparator=comparator_offset(curve[0], 0.0),
        )


def test_a_point_without_a_recorded_common_mode_takes_its_testbenchs() -> None:
    """The converter fills the DAQ's missing common mode from the testbench, as the comparator's
    decisions need one; the comparator's design is the identity of its offset."""
    point = _curve("n", "1to0", 0, 2e-3)[0]
    assert point.vin_cm_v is None
    switching = adc.analyze_switching(point)
    np.testing.assert_array_equal(switching.vin_cm_v, np.full(100, float(point.tb.vin_cm.dc)))
    assert (switching.side, switching.stage, switching.direction, switching.diffcaps) == ("n", 15, "1to0", 0)
    assert switching.stages == 16 and switching.comparator == point.param.tb.params.comp
    decisions = capdac.analyze_decisions([switching])
    assert decisions.param == point.param and decisions.info == point.info
    np.testing.assert_array_equal(decisions.vin_diff_v, point.vin_diff_v)
