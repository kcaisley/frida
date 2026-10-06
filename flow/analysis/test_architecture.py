"""Run the main analyses on an ADC other than FRIDA.

A hypothetical 10-bit converter with 12 switched capacitors (13 decisions)
exercises every place where a decision count, capacitor count, or code range
must come from the measurement parameters. Any literal FRIDA size fails here.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import hdl21 as h
import numpy as np
import pytest

from flow.adc import AdcParams
from flow.adc.sim import AdcTbParams
from flow.analysis.adc import (
    analyze_adc_code_density_nonlinearity,
    analyze_adc_code_distribution,
    analyze_adc_decision_paths,
    analyze_adc_noise,
    analyze_adc_operating_conditions,
    analyze_adc_ramp,
    analyze_adc_transfer,
)
from flow.analysis.calibration1 import analyze_adc_calibration1
from flow.analysis.calibration2 import analyze_adc_calibration2
from flow.analysis.cdac import analyze_cdac_cap_mismatch, analyze_cdac_transition
from flow.analysis.comp import analyze_comp_offset_noise
from flow.analysis.test_cdac import comparator_offset
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
    Identity,
    MeasAdc,
    MeasCdac,
    MeasInfo,
)
from flow.caparray import CapArrayConfig, get_caparray_weights
from flow.scans.params import AdcScanParams
from flow.scans.scan_cdac import _build_cdac_params

CAPACITOR_WEIGHTS = (192, 128, 80, 48, 32, 16, 12, 8, 4, 2, 1, 1)


def small_adc() -> AdcParams:
    return AdcParams(adc_bits=10, cdac=CapArrayConfig(n_dac=9, n_extra=3, weights=CAPACITOR_WEIGHTS))


def small_scan_params(conversions: int, vin_diff) -> AdcScanParams:
    template = AdcTbParams()
    return AdcScanParams(
        tb=AdcTbParams(
            dut=small_adc(),
            conversions=conversions,
            symbol_rate=1.0e6 * len(template.seq_init_pattern),
            vin_cm=h.Vdc.Params(dc=0.6),
            vin_diff=vin_diff,
            dac_astate_p=(0, 1) * 6,
            dac_astate_n=(0, 1) * 6,
            dac_bstate_p=(0,) * 12,
            dac_bstate_n=(0,) * 12,
        ),
        board_id=1,
        observed_adc=5,
        active_adc_mask=tuple(int(index == 5) for index in reversed(range(16))),
    )


def small_measurement(bout: np.ndarray, vin_diff_v: np.ndarray, vin_diff) -> MeasAdc:
    weights = np.asarray([2 * weight for weight in CAPACITOR_WEIGHTS] + [1], dtype=np.int64)
    dout_raw = bout.astype(np.int64) @ weights
    params = small_scan_params(len(bout), vin_diff)
    return MeasAdc(
        group=params.board_id,
        index=params.observed_adc,
        dut=params.tb.dut,
        info=MeasInfo(backend="behavioral", timestamp_utc=datetime(2026, 10, 5, tzinfo=UTC)),
        param=params,
        conversion_index=np.arange(len(bout)),
        bout=bout,
        dout_raw=dout_raw,
        dout=np.rint(dout_raw * 1023 / np.sum(weights)).astype(np.int64),
        vin_diff_v=vin_diff_v,
        wave=None,
    )


def small_ramp(cycles: int = 8, samples_per_cycle: int = 2_048) -> MeasAdc:
    weights = np.asarray([2 * weight for weight in CAPACITOR_WEIGHTS] + [1], dtype=np.int64)
    remaining = np.rint(np.linspace(0.0, np.sum(weights), samples_per_cycle)).astype(np.int64)
    one_cycle = np.zeros((samples_per_cycle, len(weights)), dtype=np.uint8)
    for decision, weight in enumerate(weights):
        one_cycle[:, decision] = remaining >= weight
        remaining -= one_cycle[:, decision] * weight
    return small_measurement(
        np.tile(one_cycle, (cycles, 1)),
        np.tile(np.linspace(-1.0, 1.0, samples_per_cycle, endpoint=False), cycles),
        h.Vpwl.Params(wave=f"0 -1 {samples_per_cycle / 1.0e6:.12g} 1"),
    )


def test_small_adc_is_a_different_architecture() -> None:
    assert len(get_caparray_weights(small_adc().cdac)) == 12
    assert small_adc().adc_bits == 10


def test_ramp_code_density_and_calibration_use_the_measured_architecture() -> None:
    measurement = small_ramp()
    ramp = analyze_adc_ramp(measurement)
    assert ramp.period_conversions == pytest.approx(2_048, rel=1e-6)
    assert len(ramp.code) == 1024 and len(ramp.weights) == 13
    density = analyze_adc_code_density_nonlinearity(measurement, ramp=ramp)
    assert density.code[0] == 1 and density.code[-1] == 1022
    calibration = analyze_adc_calibration2(measurement, ramp=ramp)
    assert calibration.calibrated_weights.shape == (13,)
    assert calibration.code_max == 1023
    assert np.sum(calibration.calibrated_weights) == pytest.approx(1023.0)
    recalibrated = analyze_adc_ramp(measurement, calibration=calibration)
    assert recalibrated.decoding == "calibration2"
    assert len(recalibrated.code) == 1024 and len(recalibrated.weights) == 13


def test_static_noise_and_decision_paths_use_the_measured_architecture() -> None:
    rng = np.random.default_rng(5)
    bout = rng.integers(0, 2, size=(200, 13), dtype=np.uint8)
    measurement = small_measurement(bout, np.zeros(200), h.Vdc.Params(dc=0.0))
    assert analyze_adc_code_distribution([measurement]).count.shape == (1, 1024)
    assert analyze_adc_transfer([measurement]).sample_count.sum() == 200
    paths = analyze_adc_decision_paths(measurement)
    assert paths.estimate_dout.shape == (200, 14)
    assert paths.estimate_dout[0, -1] == pytest.approx(measurement.dout[0], abs=0.5)
    noise = analyze_adc_noise(measurement)
    assert noise.code_max == 1023
    assert noise.input_lsb_v == pytest.approx(1.2 / 1023)
    conditions = analyze_adc_operating_conditions([measurement], noise=[noise])
    assert (conditions.group, conditions.index) == (1, 5)


def test_cdac_mismatch_and_calibration1_use_the_measured_capacitor_count() -> None:
    measurements = []
    transition_v = 3e-3
    for input_index, probability in enumerate((0.0, 0.5, 1.0)):
        vin_diff_v = transition_v + (input_index - 1) * 10e-3
        params = _build_cdac_params(
            adc_index=5,
            side="p",
            element=11,
            direction="0to1",
            dac_diffcaps=1,
            vin_diff_v=vin_diff_v,
            conversions=100,
            sweep_stage="fine",
        )
        small = small_scan_params(100, h.Vdc.Params(dc=vin_diff_v))
        params = replace(params, board_id=1, tb=replace(small.tb, dac_diffcaps=1, conversions=100))
        ones = round(100 * probability)
        measurements.append(
            MeasCdac(
                group=params.board_id,
                index=params.observed_adc,
                dut=params.tb.dut.cdac,
                info=MeasInfo(
                    backend="physical",
                    timestamp_utc=datetime(2026, 10, 5, tzinfo=UTC),
                    readbacks={"cdac_topplate_parasitic_weight": 0.0},
                ),
                param=params,
                trial_index=np.arange(100),
                dac_state_p=np.zeros((100, 12), dtype=np.uint8),
                dac_state_n=np.zeros((100, 12), dtype=np.uint8),
                vin_diff_v=np.full(100, vin_diff_v),
                decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
                wave=None,
            )
        )
    transition = analyze_cdac_transition(measurements, offset=analyze_comp_offset_noise(measurements))
    mismatch = analyze_cdac_cap_mismatch(
        measurements, transitions=[transition], comparator=comparator_offset(measurements[0], 0.0)
    )
    assert mismatch.effective_fraction.shape == (2, 12)
    assert mismatch.effective_fraction_by_direction[0, 11, 1] == pytest.approx(-transition_v / 1.2)

    tb = measurements[0].tb
    nominal = np.asarray(CAPACITOR_WEIGHTS, dtype=np.float64)
    by_direction = np.repeat(np.repeat(nominal[None, :, None], 2, axis=0), 2, axis=2)
    nan = np.full((2, 12), np.nan)
    cap_mismatch = AnalysisCdacCapMismatch(
        group=1,
        index=5,
        dut=tb.dut.cdac,
        main_fraction=nan,
        diff_fraction=nan,
        effective_fraction=nan,
        effective_fraction_by_direction=by_direction,
        direction_bias=np.full((2, 12, 2), np.nan),
    )
    fake = cast(
        MeasCdac,
        SimpleNamespace(tb=tb, identity=Identity(1, 5, tb.dut.cdac), trial_index=np.arange(3)),
    )
    calibration = analyze_adc_calibration1((fake,), cap_mismatch=cap_mismatch)
    assert calibration.calibrated_weights.shape == (13,)
    assert calibration.code_max == 1023
    np.testing.assert_allclose(calibration.calibrated_weights, calibration.nominal_weights)
