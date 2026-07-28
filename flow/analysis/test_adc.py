"""Software-only tests for typed ADC analyses."""

from __future__ import annotations

import math

import numpy as np
import pytest

from flow.analysis.adc import (
    analyze_adc_code_density,
    analyze_adc_decision_paths,
    analyze_adc_distribution,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_endpoint_linearity,
    analyze_adc_transfer,
)
from flow.analysis.models import (
    AdcSettings,
    AnalysisKind,
    AnalysisRequest,
    AnalysisSpec,
    BackendKind,
    BlockKind,
    DataColumn,
    DataTable,
    RunData,
)


def adc_run(run_id: str, *, parameters=None, **columns) -> RunData:
    return RunData(
        run_id,
        BackendKind.BEHAVIORAL,
        BlockKind.ADC,
        (
            DataTable(
                "conversions",
                tuple(DataColumn(name, np.asarray(values)) for name, values in columns.items()),
            ),
        ),
        parameters=parameters or {},
    )


def adc_request(
    run: RunData,
    kind: AnalysisKind,
    settings: AdcSettings,
    *,
    name: str = "analysis",
) -> AnalysisRequest:
    return AnalysisRequest(
        AnalysisSpec(name, kind, (run.run_id,), settings),
        runs=(run,),
    )


def test_dynamic_analysis_recovers_sine_and_spectral_metrics() -> None:
    rng = np.random.default_rng(12345)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 20_000
    amplitude_codes = 1_500.0
    offset_codes = 2_040.0
    phase_rad = 0.37
    noise_rms_codes = 2.0
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = (
        offset_codes
        + amplitude_codes * np.sin(2.0 * np.pi * input_frequency_hz * time_s + phase_rad)
        + rng.normal(0.0, noise_rms_codes, sample_count)
    )
    run = adc_run("sine", dout=samples)
    result = analyze_adc_dynamic(
        adc_request(
            run,
            AnalysisKind.ADC_DYNAMIC,
            AdcSettings(
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=input_frequency_hz * (1.0 + 5e-6),
            ),
        )
    )

    assert result.metric("sample_count") == sample_count
    assert result.metric("fitted_frequency_hz") == pytest.approx(input_frequency_hz, abs=0.02)
    assert result.metric("amplitude_codes") == pytest.approx(amplitude_codes, rel=2e-4)
    assert result.metric("offset_codes") == pytest.approx(offset_codes, abs=0.05)
    assert result.metric("phase_rad") == pytest.approx(phase_rad, abs=2e-4)
    assert result.metric("residual_rms_codes") == pytest.approx(noise_rms_codes, rel=0.03)
    assert result.metric("enob_bits") == pytest.approx(
        (result.metric("sinad_db") - 1.76) / 6.02
    )
    assert len(result.table("fit")) == sample_count


def test_dynamic_analysis_separates_noise_and_harmonics() -> None:
    rng = np.random.default_rng(7)
    sample_rate_hz = 1.0e6
    input_frequency_hz = 12_345.678
    sample_count = 65_536
    time_s = np.arange(sample_count) / sample_rate_hz
    samples = (
        2_048.0
        + 1_500.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s + 0.2)
        + 15.0 * np.sin(2.0 * np.pi * 2.0 * input_frequency_hz * time_s - 0.1)
        + rng.normal(0.0, 1.0, sample_count)
    )
    run = adc_run("sine", dout=samples)
    result = analyze_adc_dynamic(
        adc_request(
            run,
            AnalysisKind.ADC_DYNAMIC,
            AdcSettings(
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=input_frequency_hz,
            ),
        )
    )

    assert result.metric("spectral_snr_db") == pytest.approx(60.51, abs=0.15)
    assert result.metric("spectral_thd_db") == pytest.approx(-40.0, abs=0.15)
    assert result.metric("spectral_sfdr_db") == pytest.approx(40.0, abs=0.15)
    assert result.metric("spectral_sndr_db") == pytest.approx(39.96, abs=0.15)
    assert result.metric("spectral_enob_bits") == pytest.approx(
        (result.metric("spectral_sndr_db") - 1.76) / 6.02
    )


def test_transfer_distribution_and_code_density_share_normalized_data() -> None:
    run = adc_run(
        "ramp",
        vin_diff_v=(-0.1, -0.1, 0.0, 0.0, 0.1, 0.1),
        dout=(0, 0, 1, 2, 3, 3),
    )
    settings = AdcSettings(adc_bits=2, code_range=(1, 2))
    transfer = analyze_adc_transfer(
        adc_request(run, AnalysisKind.ADC_TRANSFER, settings, name="transfer")
    )
    distribution = analyze_adc_distribution(
        adc_request(run, AnalysisKind.ADC_DISTRIBUTION, settings, name="distribution")
    )
    linearity = analyze_adc_code_density(
        adc_request(run, AnalysisKind.ADC_CODE_DENSITY, settings, name="linearity")
    )

    np.testing.assert_allclose(
        transfer.table("transfer").column("mean_code"),
        (0.0, 1.5, 3.0),
    )
    np.testing.assert_array_equal(
        distribution.table("distribution").column("count"),
        (2, 1, 1, 2),
    )
    assert linearity.metric("ideal_count") == 1.0
    assert linearity.metric("missing_codes") == 0
    np.testing.assert_allclose(linearity.table("linearity").column("dnl"), (0.0, 0.0))


def test_endpoint_linearity_interpolates_static_code_transitions() -> None:
    inputs = np.linspace(-0.6, 0.6, 129)
    ideal_codes = np.linspace(0.0, 15.0, len(inputs))
    ideal_run = adc_run("ideal_static", vin_diff_v=inputs, dout=ideal_codes)
    ideal = analyze_adc_endpoint_linearity(
        adc_request(
            ideal_run,
            AnalysisKind.ADC_ENDPOINT_LINEARITY,
            AdcSettings(adc_bits=4),
            name="endpoint",
        )
    )
    assert ideal.metric("endpoint_lsb_v") == pytest.approx(0.08)
    assert ideal.metric("maximum_abs_dnl") < 1e-12
    assert ideal.metric("maximum_abs_inl") < 1e-12
    assert ideal.metric("missing_codes") == 0

    nonlinear_codes = ideal_codes + 0.15 * np.sin(np.pi * ideal_codes / 15.0)
    nonlinear_run = adc_run(
        "nonlinear_static",
        vin_diff_v=inputs,
        dout=nonlinear_codes,
    )
    nonlinear = analyze_adc_endpoint_linearity(
        adc_request(
            nonlinear_run,
            AnalysisKind.ADC_ENDPOINT_LINEARITY,
            AdcSettings(adc_bits=4),
            name="endpoint",
        )
    )
    assert nonlinear.metric("maximum_abs_inl") > 0.05


def test_transfer_can_take_one_scalar_input_from_each_run_metadata() -> None:
    runs = (
        RunData(
            "low",
            BackendKind.MEASUREMENT,
            BlockKind.ADC,
            (DataTable("conversions", (DataColumn("dout", np.asarray([10, 12])),)),),
            parameters={"vin_diff_v": -0.1},
        ),
        RunData(
            "high",
            BackendKind.MEASUREMENT,
            BlockKind.ADC,
            (DataTable("conversions", (DataColumn("dout", np.asarray([20, 22])),)),),
            parameters={"vin_diff_v": 0.1},
        ),
    )
    spec = AnalysisSpec(
        "transfer",
        AnalysisKind.ADC_TRANSFER,
        ("low", "high"),
        AdcSettings(),
    )
    result = analyze_adc_transfer(AnalysisRequest(spec, runs=runs))
    np.testing.assert_allclose(result.table("transfer").column("mean_code"), (11.0, 21.0))


def test_decision_paths_and_dynamic_sweep_use_common_result_tables() -> None:
    decision_run = adc_run(
        "decisions",
        bout=("101", "101", "011"),
        dout=(5, 5, 3),
    )
    paths = analyze_adc_decision_paths(
        adc_request(
            decision_run,
            AnalysisKind.ADC_DECISION_PATHS,
            AdcSettings(
                adc_bits=3,
                code_weights=(4, 2, 1),
                selection="same_code",
            ),
            name="paths",
        )
    )
    assert paths.metric("path_count") == 2
    assert len(paths.table("decision_paths")) == 8

    dynamic_results = []
    for index, frequency in enumerate((1_000.0, 5_000.0)):
        sample_rate = 100_000.0
        time_s = np.arange(2_048) / sample_rate
        run = adc_run(
            f"sine{index}",
            parameters={
                "conversion_rate_hz": sample_rate,
                "logic_offset": index - 1,
            },
            dout=2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * frequency * time_s),
        )
        dynamic_results.append(
            analyze_adc_dynamic(
                adc_request(
                    run,
                    AnalysisKind.ADC_DYNAMIC,
                    AdcSettings(
                        sample_rate_hz=sample_rate,
                        input_frequency_hz=frequency,
                        frequency_search_fraction=0.0,
                    ),
                    name=f"dynamic{index}",
                )
            )
        )
    spec = AnalysisSpec(
        "sweep",
        AnalysisKind.ADC_DYNAMIC_SWEEP,
        tuple(result.name for result in dynamic_results),
        AdcSettings(),
    )
    sweep = analyze_adc_dynamic_sweep(
        AnalysisRequest(spec, results=tuple(dynamic_results))
    )
    assert sweep.metric("point_count") == 2
    np.testing.assert_allclose(
        sweep.table("dynamic_sweep").column("input_frequency_hz"),
        (1_000.0, 5_000.0),
    )
    custom_spec = AnalysisSpec(
        "custom_sweep",
        AnalysisKind.ADC_DYNAMIC_SWEEP,
        tuple(result.name for result in dynamic_results),
        AdcSettings(
            sweep_axis="conversion_rate_hz",
            sweep_group="logic_offset",
        ),
    )
    custom_sweep = analyze_adc_dynamic_sweep(
        AnalysisRequest(custom_spec, results=tuple(dynamic_results))
    )
    np.testing.assert_allclose(
        custom_sweep.table("dynamic_sweep").column("conversion_rate_hz"),
        (100_000.0, 100_000.0),
    )
    np.testing.assert_array_equal(
        custom_sweep.table("dynamic_sweep").column("logic_offset"),
        (-1, 0),
    )


@pytest.mark.parametrize(
    ("samples", "sample_rate_hz", "input_frequency_hz", "message"),
    [
        ([1.0] * 7, 1_000.0, 10.0, "at least eight"),
        ([1.0] * 8, 0.0, 10.0, "sample_rate_hz"),
        ([1.0] * 8, 1_000.0, 500.0, "Nyquist"),
    ],
)
def test_dynamic_analysis_rejects_invalid_records(
    samples: list[float],
    sample_rate_hz: float,
    input_frequency_hz: float,
    message: str,
) -> None:
    run = adc_run("invalid", dout=samples)
    with pytest.raises(ValueError, match=message):
        analyze_adc_dynamic(
            adc_request(
                run,
                AnalysisKind.ADC_DYNAMIC,
                AdcSettings(
                    sample_rate_hz=sample_rate_hz,
                    input_frequency_hz=input_frequency_hz,
                ),
            )
        )


def test_dynamic_analysis_reports_time_domain_sinad_consistently() -> None:
    sample_rate_hz = 100_000.0
    input_frequency_hz = 1_000.0
    time_s = np.arange(1_000) / sample_rate_hz
    samples = 2_000.0 + 500.0 * np.sin(2.0 * np.pi * input_frequency_hz * time_s)
    run = adc_run("exact", dout=samples)
    result = analyze_adc_dynamic(
        adc_request(
            run,
            AnalysisKind.ADC_DYNAMIC,
            AdcSettings(
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=input_frequency_hz,
                frequency_search_fraction=0.0,
            ),
        )
    )
    assert result.metric("fitted_frequency_hz") == input_frequency_hz
    assert result.metric("amplitude_codes") == pytest.approx(500.0)
    assert result.metric("offset_codes") == pytest.approx(2_000.0)
    assert result.metric("residual_rms_codes") < 1e-9
    assert math.isinf(result.metric("sinad_db")) or result.metric("sinad_db") > 250.0
