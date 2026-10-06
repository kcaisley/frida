"""Tests for calibration 1 from mechanistic CDAC measurements."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

from flow.adc.sim import AdcTbParams
from flow.analysis.calibration1 import analyze_adc_calibration1
from flow.analysis.types import AnalysisCdacCapMismatch, Identity, MeasCdac
from flow.caparray import get_caparray_weights
from flow.scans.params import AdcScanParams


def test_calibration1_public_analysis_returns_common_weights() -> None:
    params = AdcScanParams(
        tb=AdcTbParams(),
        board_id=0,
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
    )
    nominal_cap_weight = 2.0 * np.asarray(get_caparray_weights(params.tb.dut.cdac), dtype=np.float64)
    element_count = len(nominal_cap_weight)
    measured = np.repeat((nominal_cap_weight / 2.0)[None, :, None], 2, axis=0)
    measured = np.repeat(measured, 2, axis=2)
    identity = Identity(0, 0, params.tb.dut.cdac)
    measurement = cast(
        MeasCdac,
        SimpleNamespace(param=params, tb=params.tb, identity=identity, trial_index=np.arange(100)),
    )

    def cap_mismatch(by_direction: np.ndarray) -> AnalysisCdacCapMismatch:
        nan = np.full((2, element_count), np.nan)
        return AnalysisCdacCapMismatch(
            group=0,
            index=0,
            dut=params.tb.dut.cdac,
            main_fraction=nan,
            diff_fraction=nan,
            effective_fraction=nan,
            effective_fraction_by_direction=by_direction,
            direction_bias=np.full((2, element_count, 2), np.nan),
        )

    result = analyze_adc_calibration1((measurement,), cap_mismatch=cap_mismatch(measured))

    assert result.method == "calibration1"
    assert (result.group, result.index, result.dut) == (0, 0, params.tb.dut)
    np.testing.assert_allclose(result.calibrated_weights, result.nominal_weights)
    np.testing.assert_array_equal(result.measured_weight_mask, [True] * element_count + [False])
    assert result.training_sample_count == 100

    measured[0, 5, :] = np.nan
    hybrid = analyze_adc_calibration1((measurement,), cap_mismatch=cap_mismatch(measured))
    assert not hybrid.measured_weight_mask[5]
    assert np.all(np.isfinite(hybrid.calibrated_weights))
    assert np.sum(hybrid.calibrated_weights) == pytest.approx(4095.0)

    other_channel = replace(cap_mismatch(measured), index=1)
    with pytest.raises(ValueError, match="does not match"):
        analyze_adc_calibration1((measurement,), cap_mismatch=other_channel)


def test_calibration1_selects_p_and_n_directions_from_each_a_state() -> None:
    """A=0 uses the 0-to-1 movement and A=1 the 1-to-0 movement, independently per side."""

    a_p = (0, 1) * 8
    a_n = (0, 0, 1, 1) * 4
    params = AdcScanParams(
        tb=AdcTbParams(dac_astate_p=a_p, dac_astate_n=a_n),
        board_id=0,
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
    )
    nominal_cap_weight = np.asarray(get_caparray_weights(params.tb.dut.cdac), dtype=np.float64)
    by_direction = np.empty((2, 16, 2))
    # Selected movements are each nominal half-weight; unselected ones are
    # deliberately wrong or NaN so a wrong selection would be visible.
    for element in range(16):
        by_direction[0, element, 1 - a_p[element]] = nominal_cap_weight[element]
        by_direction[0, element, a_p[element]] = np.nan
        by_direction[1, element, 1 - a_n[element]] = nominal_cap_weight[element]
        by_direction[1, element, a_n[element]] = 100.0 * nominal_cap_weight[element]
    nan = np.full((2, 16), np.nan)
    cap_mismatch = AnalysisCdacCapMismatch(
        group=0,
        index=0,
        dut=params.tb.dut.cdac,
        main_fraction=nan,
        diff_fraction=nan,
        effective_fraction=nan,
        effective_fraction_by_direction=by_direction,
        direction_bias=np.full((2, 16, 2), np.nan),
    )
    measurement = cast(
        MeasCdac,
        SimpleNamespace(
            param=params,
            tb=params.tb,
            identity=Identity(0, 0, params.tb.dut.cdac),
            trial_index=np.arange(10),
        ),
    )

    result = analyze_adc_calibration1((measurement,), cap_mismatch=cap_mismatch)

    assert np.all(result.measured_weight_mask[:16])
    np.testing.assert_allclose(result.calibrated_weights, result.nominal_weights)
