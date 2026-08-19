"""Software-only tests for calibration 3 from Hsu slow-ramp thresholds."""

from __future__ import annotations

from dataclasses import replace

import hdl21 as h
import numpy as np
import pytest

from flow.analysis.adc import analyze_adc_ramp
from flow.analysis.calibration3 import _extract_prefix_thresholds, _fit_probit_threshold, _hybrid_weights, analyze
from flow.analysis.plots import plot_adc_calibration_weights
from flow.analysis.test_adc import adc_measurement
from flow.analysis.types import AdcDaq, MeasAdcExt
from flow.scans.params import AdcTbParams

NOMINAL_WEIGHTS = np.asarray(
    [1536, 1024, 640, 384, 192, 128, 64, 48, 24, 20, 10, 8, 8, 4, 2, 2, 1],
    dtype=np.float64,
)


def _threshold_ramp_measurement(
    *,
    cycles: int = 40,
    samples_per_cycle: int = 16_384,
    noise_sigma_v: float = 40e-6,
) -> tuple[MeasAdcExt, np.ndarray, np.ndarray]:
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
    assert isinstance(base, MeasAdcExt)
    params = AdcTbParams(
        dut=base.param.dut,
        conversions=len(vin_diff_v),
        symbol_rate=base.param.symbol_rate,
        board_id="test_board",
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
        campaign="adc_ramp",
        vin_cm=h.Vdc.Params(dc=0.6),
        vin_diff=h.Vpwl.Params(wave="0 -1 0.001 1"),
    )
    return (
        replace(
            base,
            param=params,
            daq=AdcDaq(
                conversion_index=np.arange(len(vin_diff_v)),
                bout=decisions,
                dout_raw=nominal_raw,
                dout=nominal_dout,
                vin_diff_v=vin_diff_v,
            ),
        ),
        down_step_v,
        up_step_v,
    )


def test_probit_fit_recovers_threshold_and_effective_noise() -> None:
    """Recover a known p50 and effective input-noise width."""

    rng = np.random.default_rng(17)
    vin_diff_v = np.tile(np.linspace(-10e-3, 10e-3, 4096), 40)
    threshold_v = 1.2e-3
    noise_sigma_v = 0.35e-3
    decision = (vin_diff_v + rng.normal(0.0, noise_sigma_v, len(vin_diff_v)) >= threshold_v).astype(np.uint8)

    fitted_threshold_v, fitted_sigma_v, threshold_std_v, trial_count = _fit_probit_threshold(
        vin_diff_v,
        decision,
        vin_diff_min_v=-10e-3,
        vin_diff_max_v=10e-3,
    )

    assert trial_count == len(vin_diff_v)
    assert fitted_threshold_v == pytest.approx(threshold_v, abs=15e-6)
    assert fitted_sigma_v == pytest.approx(noise_sigma_v, rel=0.04)
    assert 0.0 < threshold_std_v < 10e-6


@pytest.fixture(scope="module")
def threshold_analysis():
    """Share the relatively expensive synthetic threshold extraction."""

    measurement, expected_down_step_v, expected_up_step_v = _threshold_ramp_measurement()
    ramp = analyze_adc_ramp(measurement)
    extraction = _extract_prefix_thresholds(
        measurement.daq.bout,
        measurement.daq.vin_diff_v,
        np.ones(len(measurement.daq.bout), dtype=np.bool_),
        vin_diff_min_v=-1.0,
        vin_diff_max_v=1.0,
    )
    return (
        analyze(measurement, ramp),
        extraction,
        expected_down_step_v,
        expected_up_step_v,
    )


def test_threshold_calibration_recovers_both_directional_movements(threshold_analysis) -> None:
    """Extract the all-zero/all-one threshold differences without side assumptions."""

    result, extraction, expected_down_step_v, expected_up_step_v = threshold_analysis

    assert result.adc_index == 0
    assert result.method == "calibration3"
    assert extraction["down_threshold_v"][0] == extraction["up_threshold_v"][0]
    assert extraction["down_step_v"][:10] == pytest.approx(expected_down_step_v[:10], abs=80e-6)
    assert extraction["up_step_v"][:10] == pytest.approx(expected_up_step_v[:10], abs=80e-6)
    assert extraction["endpoint_weight_v"][:10] == pytest.approx(
        expected_down_step_v[:10] + expected_up_step_v[:10],
        abs=120e-6,
    )
    assert np.all(result.calibrated_weights > 0.0)
    assert np.sum(result.nominal_weights) == pytest.approx(4095.0)
    assert np.sum(result.calibrated_weights) == pytest.approx(4095.0)
    resolved = extraction["step_resolved"]
    resolved_prefix_count = int(np.argmax(~resolved)) if np.any(~resolved) else 16
    assert np.count_nonzero(result.measured_weight_mask) <= resolved_prefix_count


def test_threshold_calibration_uses_common_weight_plot(
    threshold_analysis,
    tmp_path,
) -> None:
    """Render calibration 3 through the method-independent plotting API."""

    result, _, _, _ = threshold_analysis
    plot_paths = plot_adc_calibration_weights(
        (result,),
        output_path=tmp_path / "direct_threshold_calibration",
    )
    assert tuple(path.suffix for path in plot_paths) == (".pdf",)
    assert plot_paths[0].is_file()
    assert plot_paths[0].stat().st_size > 0


def test_hybrid_decoder_preserves_unobservable_terminal_ratio() -> None:
    """Use extracted prefix values while retaining nominal ratios in the tail."""

    endpoint_weight_v = NOMINAL_WEIGHTS[:-1] * 240e-6
    endpoint_weight_v[:3] *= (1.05, 0.98, 1.02)
    calibrated = _hybrid_weights(
        NOMINAL_WEIGHTS,
        endpoint_weight_v,
        3,
        code_max=4095,
    )

    assert np.sum(calibrated) == pytest.approx(4095.0)
    assert calibrated[0] / calibrated[1] == pytest.approx(endpoint_weight_v[0] / endpoint_weight_v[1])
    assert calibrated[-2] / calibrated[-1] == pytest.approx(NOMINAL_WEIGHTS[-2] / NOMINAL_WEIGHTS[-1])
