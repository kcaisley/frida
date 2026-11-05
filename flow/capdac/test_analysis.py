"""The capacitive DAC's analyses on synthetic data: RC steps of known delay, time constant, amplitude
and gain (``analyze_settling``), and Monte Carlo draws of known plates (``analyze_mismatch``)."""

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from flow import capdac
from flow.pipeline import Meas, MeasInfo

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
