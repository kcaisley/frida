"""Software-only integration test for explicit post-processing plans."""

import numpy as np

from flow.analysis.models import (
    AdcSettings,
    AnalysisKind,
    AnalysisPlan,
    AnalysisSpec,
    BackendKind,
    BlockKind,
    PlotKind,
    PlotSpec,
    SourceFormat,
    SourceSpec,
)
from flow.analysis.runner import run_analysis_plan


def test_analysis_plan_returns_results_and_renders_requested_plots(tmp_path) -> None:
    source = SourceSpec(
        "adc",
        BackendKind.BEHAVIORAL,
        BlockKind.ADC,
        SourceFormat.COLUMN_MAPPING,
        {
            "vin_diff_v": (-0.1, -0.1, 0.1, 0.1),
            "dout": (10, 12, 20, 22),
        },
        table_name="conversions",
    )
    analysis = AnalysisSpec(
        "transfer",
        AnalysisKind.ADC_TRANSFER,
        ("adc",),
        AdcSettings(),
    )
    plot = PlotSpec(
        "transfer_plot",
        PlotKind.TRANSFER,
        ("transfer",),
        tmp_path / "plots" / "transfer",
        formats=("png",),
    )
    report = run_analysis_plan(
        AnalysisPlan(
            sources=(source,),
            analyses=(analysis,),
            plots=(plot,),
        )
    )

    assert report.results[0].metric("input_points") == 2
    assert report.runs[0].run_id == "adc"
    assert report.plots[0].paths == (tmp_path / "plots" / "transfer.png",)
    assert not tuple(tmp_path.glob("**/*.csv"))
    assert not tuple(tmp_path.glob("**/analysis_manifest.json"))


def test_analysis_plan_resolves_result_dependencies_out_of_order() -> None:
    sample_rate_hz = 100_000.0
    sample_count = 2_048
    sources = []
    dynamics = []
    for index, frequency_hz in enumerate((1_000.0, 5_000.0)):
        time_s = np.arange(sample_count) / sample_rate_hz
        run_id = f"sine{index}"
        result_name = f"dynamic{index}"
        sources.append(
            SourceSpec(
                run_id,
                BackendKind.BEHAVIORAL,
                BlockKind.ADC,
                SourceFormat.COLUMN_MAPPING,
                {"dout": 2_048.0 + 1_000.0 * np.sin(2.0 * np.pi * frequency_hz * time_s)},
                table_name="conversions",
            )
        )
        dynamics.append(
            AnalysisSpec(
                result_name,
                AnalysisKind.ADC_DYNAMIC,
                (run_id,),
                AdcSettings(
                    sample_rate_hz=sample_rate_hz,
                    input_frequency_hz=frequency_hz,
                    frequency_search_fraction=0.0,
                ),
            )
        )

    sweep = AnalysisSpec(
        "sweep",
        AnalysisKind.ADC_DYNAMIC_SWEEP,
        tuple(spec.name for spec in dynamics),
        AdcSettings(),
    )
    report = run_analysis_plan(
        AnalysisPlan(
            sources=tuple(sources),
            analyses=(sweep, *dynamics),
            plots=(),
        )
    )

    assert tuple(result.name for result in report.results) == (
        "dynamic0",
        "dynamic1",
        "sweep",
    )
    assert report.results[-1].metric("point_count") == 2
