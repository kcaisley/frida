"""Software-only tests for calibration 3 from Hsu slow-ramp thresholds."""

from __future__ import annotations

from dataclasses import replace

import hdl21 as h
import numpy as np
import pytest

from flow.adc.sim import AdcTbParams
from flow.analysis.adc import analyze_adc_ramp
from flow.analysis.calibration3 import analyze_adc_calibration3
from flow.analysis.plots import plot_adc_calibration_weights
from flow.analysis.test_adc import adc_measurement
from flow.analysis.types import MeasAdc
from flow.scans.params import AdcScanParams

NOMINAL_WEIGHTS = np.asarray(
    [1536, 1024, 640, 384, 192, 128, 64, 48, 24, 20, 10, 8, 8, 4, 2, 2, 1],
    dtype=np.float64,
)


def _threshold_ramp_measurement(
    *,
    cycles: int = 40,
    samples_per_cycle: int = 16_384,
    noise_sigma_v: float = 40e-6,
) -> tuple[MeasAdc, np.ndarray, np.ndarray]:
    """Build a SAR whose Hsu branch thresholds have known directional steps."""

    rng = np.random.default_rng(20260813)
    one_cycle_vin_diff_v = np.linspace(-1.0, 1.0, samples_per_cycle, endpoint=False)
    vin_diff_v = np.tile(one_cycle_vin_diff_v, cycles)

    # Deliberately perturb the largest weights so an applied calibration has a
    # signal which is much larger than this synthetic comparator noise.  The
    # unequal up/down split also verifies that the analysis does not assume a
    # comparator decision always moves the same physical side of the CDAC.
    mismatch = np.asarray([1.04, 0.97, 1.02, 0.98, 1.01, 0.99, 1.01, 0.99, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    endpoint_weight_v = NOMINAL_WEIGHTS[:-1] * 250e-6 * mismatch
    down_step_v = endpoint_weight_v * np.linspace(0.47, 0.52, 16)
    up_step_v = endpoint_weight_v - down_step_v

    decisions = np.empty((len(vin_diff_v), 17), dtype=np.uint8)
    decision_level_v = np.zeros(len(vin_diff_v), dtype=np.float64)
    for decision_index in range(17):
        # Independent Gaussian decision noise is intentionally simpler than the
        # real capture.  The production analysis comments identify source drift
        # and conversion correlation which this numerical fixture cannot model.
        decision = vin_diff_v + rng.normal(0.0, noise_sigma_v, len(vin_diff_v)) >= decision_level_v
        decisions[:, decision_index] = decision
        if decision_index < 16:
            decision_level_v += np.where(
                decision,
                up_step_v[decision_index],
                -down_step_v[decision_index],
            )

    nominal_raw = decisions.astype(np.int64) @ NOMINAL_WEIGHTS.astype(np.int64)
    nominal_dout = np.rint(nominal_raw * 4095 / np.sum(NOMINAL_WEIGHTS)).astype(np.int64)
    base = adc_measurement(np.zeros(len(vin_diff_v), dtype=np.int64), observed_adc=0)
    assert isinstance(base, MeasAdc)
    params = AdcScanParams(
        tb=AdcTbParams(
            dut=base.param.tb.dut,
            conversions=len(vin_diff_v),
            symbol_rate=base.param.tb.symbol_rate,
            vin_cm=h.Vdc.Params(dc=0.6),
            vin_diff=h.Vpwl.Params(wave=f"0 -1 {samples_per_cycle / base.sample_rate_hz:.12g} 1"),
        ),
        board_id=7,
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
        campaign="adc_ramp",
    )
    return (
        replace(
            base,
            param=params,
            conversion_index=np.arange(len(vin_diff_v)),
            bout=decisions,
            dout_raw=nominal_raw,
            dout=nominal_dout,
            vin_diff_v=vin_diff_v,
        ),
        down_step_v,
        up_step_v,
    )


@pytest.fixture(scope="module")
def threshold_analysis():
    """Share the relatively expensive synthetic threshold extraction."""

    measurement, expected_down_step_v, expected_up_step_v = _threshold_ramp_measurement()
    return (
        analyze_adc_calibration3(measurement, ramp=analyze_adc_ramp(measurement)),
        expected_down_step_v,
        expected_up_step_v,
    )


def test_threshold_calibration_recovers_both_directional_movements(threshold_analysis) -> None:
    """Measured weights follow the known down-plus-up threshold movements without side assumptions."""

    result, expected_down_step_v, expected_up_step_v = threshold_analysis
    expected_endpoint_v = expected_down_step_v + expected_up_step_v

    assert (result.group, result.index) == (7, 0)
    assert result.method == "calibration3"
    measured = int(np.count_nonzero(result.measured_weight_mask))
    # The first four, deliberately perturbed steps resolve on this fixture.
    assert measured >= 4
    assert np.all(result.measured_weight_mask[:measured])
    # Within the measured prefix, weight ratios equal the endpoint-movement ratios.
    np.testing.assert_allclose(
        result.calibrated_weights[:measured] / result.calibrated_weights[0],
        expected_endpoint_v[:measured] / expected_endpoint_v[0],
        rtol=2e-3,
    )
    assert np.all(result.calibrated_weights > 0.0)
    assert np.sum(result.nominal_weights) == pytest.approx(4095.0)
    assert np.sum(result.calibrated_weights) == pytest.approx(4095.0)


def test_threshold_calibration_keeps_design_ratios_in_the_unmeasured_tail(threshold_analysis) -> None:
    """The terminal half-step is unobservable, so it and unresolved steps keep nominal ratios."""

    result, _, _ = threshold_analysis
    measured = int(np.count_nonzero(result.measured_weight_mask))
    tail = slice(measured, None)
    np.testing.assert_allclose(
        result.calibrated_weights[tail] / result.calibrated_weights[-1],
        result.nominal_weights[tail] / result.nominal_weights[-1],
    )


def test_threshold_calibration_uses_common_weight_plot(
    threshold_analysis,
    tmp_path,
) -> None:
    """Render calibration 3 through the method-independent plotting API."""

    result, _, _ = threshold_analysis
    plot_paths = plot_adc_calibration_weights(
        (result,),
        output_path=tmp_path / "direct_threshold_calibration",
    )
    assert tuple(path.suffix for path in plot_paths) == (".pdf",)
    assert plot_paths[0].is_file()
    assert plot_paths[0].stat().st_size > 0
