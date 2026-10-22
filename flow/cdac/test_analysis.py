"""CDAC settling analysis on synthetic RC steps of known delay, time constant and amplitude."""

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.capdriver.subckt import CapDriverParams
from flow.cdac.analysis import MeasCdac, analyze_cdac_settling, ideal_steps_v, lsb_v, settling_tau_s
from flow.cdac.sim import CdacTbParams, window_start_s
from flow.cdac.subckt import CdacParams

DAC = CdacParams(
    driver=CapDriverParams(n_stages=3),
    main_f=(400e-15, 200e-15, 100e-15),
    diff_f=(0.0, 0.0, 50e-15),
    parasitic_f=250e-15,
)
VDD, EDGE = 1.2, 30e-12


def _rc(taus: tuple[float, ...], *, lag: float = 40e-12, window: float = 4e-9, adc_bits: int = 10) -> MeasCdac:
    """Each stage's bottom plate and differential top plate an RC of ``taus[stage]`` starting ``lag``
    after its state's edge, the top plate stepping by the capacitances' step."""
    tb = CdacTbParams(dac=DAC, adc_bits=adc_bits, window_s=window, waveform_sample_interval_s=window / 4000, vdd=VDD)
    stages = DAC.driver.n_stages
    time_s = np.arange(0.0, (2 * stages + 1) * window + window / 8000, window / 4000)
    steps = ideal_steps_v(DAC, VDD)
    differential = np.full_like(time_s, -steps.sum() / 2)
    v = {}
    for stage, tau in enumerate(taus):
        up, down = (window_start_s(tb, stage, rising) + EDGE / 2 for rising in (True, False))
        state = np.where((time_s >= up) & (time_s < down), VDD, 0.0)
        rising = 1 - np.exp(-np.clip(time_s - up - lag, 0.0, None) / tau)
        falling = np.exp(-np.clip(time_s - down - lag, 0.0, None) / tau)
        fraction = np.where(time_s < down, rising, rising * falling)
        v[f"dac_state_p[{stage}]"] = state[None, :]
        v[f"dac_botplate_p[{stage}]"] = (VDD * fraction)[None, :]
        differential = differential + steps[stage] * fraction
    v["vdac_p"], v["vdac_n"] = (0.6 + differential / 2)[None, :], (0.6 - differential / 2)[None, :]
    return MeasCdac(
        group=None,
        index=None,
        dut=DAC,
        info=MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 22, tzinfo=UTC)),
        param=tb,
        trial_index=np.arange(1),
        wave=Wave(record_index=np.arange(1), time_s=time_s, v=v),
    )


def test_an_rc_step_settles_when_its_exponential_reaches_half_an_lsb():
    taus, lag = (200e-12, 100e-12, 60e-12), 40e-12
    result = analyze_cdac_settling(_rc(taus, lag=lag))
    lsb = lsb_v(DAC, VDD, 10)
    assert result.lsb_v == pytest.approx(lsb) and result.settled
    steps = ideal_steps_v(DAC, VDD)
    np.testing.assert_allclose(result.step_rise_v, steps, rtol=1e-6)
    np.testing.assert_allclose(result.step_fall_v, -steps, rtol=1e-6)
    assert result.step_error_lsb < 1e-3
    resolution = 2e-12  # a sample is 1 ps; the edges are interpolated
    expected_delay = lag + np.asarray(taus) * math.log(2)
    expected_settling = lag + np.asarray(taus) * np.log(steps / (lsb / 2))
    for measured in (result.delay_rise_s, result.delay_fall_s):
        np.testing.assert_allclose(measured, expected_delay, atol=resolution)
    for measured in (result.settling_rise_s, result.settling_fall_s):
        np.testing.assert_allclose(measured, expected_settling, atol=resolution)
    # the model's time constant: started at the driver's 50 %, at half an LSB when SPICE is
    ratio = np.log(steps / (lsb / 2))
    np.testing.assert_allclose(result.tau_s, np.asarray(taus) * (1 - math.log(2) / ratio), rtol=0.02)
    modeled = result.delay_s + result.tau_s * np.log(np.abs(result.step_v) / (lsb / 2))
    np.testing.assert_allclose(modeled, result.settling_s, rtol=1e-9)


def test_a_step_still_moving_at_its_window_middle_is_not_settled():
    result = analyze_cdac_settling(_rc((900e-12, 100e-12, 60e-12), window=4e-9))
    assert not result.settled
    assert result.settling_s[0] > result.window_s / 2


def test_a_step_inside_the_tolerance_has_no_time_constant():
    assert settling_tau_s(1e-9, 0.1e-9, 0.4e-3, 0.5e-3) == 0.0
    assert settling_tau_s(0.05e-9, 0.1e-9, 2e-3, 0.5e-3) == 0.0
    assert settling_tau_s(1.1e-9, 0.1e-9, 0.5e-3 * math.e, 0.5e-3) == pytest.approx(1e-9)
