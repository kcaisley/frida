"""Software-only tests for rendering normalized runs and results."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from flow.analysis.adc import (
    analyze_adc_code_density,
    analyze_adc_decision_paths,
    analyze_adc_distribution,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
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
    PlotKind,
    PlotRequest,
    PlotSpec,
    RunData,
    WaveformSettings,
)
from flow.analysis.measure import analyze_spectrum
from flow.analysis.plot import render_plot


def run_data(run_id: str, table_name: str = "data", **columns) -> RunData:
    return RunData(
        run_id,
        BackendKind.BEHAVIORAL,
        BlockKind.ADC,
        (
            DataTable(
                table_name,
                tuple(DataColumn(name, np.asarray(values)) for name, values in columns.items()),
            ),
        ),
    )


def analysis_request(run: RunData, name: str, kind: AnalysisKind, settings) -> AnalysisRequest:
    return AnalysisRequest(
        AnalysisSpec(name, kind, (run.run_id,), settings),
        runs=(run,),
    )


def assert_plot_formats(paths: tuple[Path, ...]) -> None:
    assert tuple(path.suffix for path in paths) == (".png", ".pdf", ".svg")
    for path in paths:
        assert path.is_file()
        assert path.stat().st_size > 0


def test_time_and_frequency_plots_use_caller_labels(tmp_path: Path) -> None:
    time_s = np.arange(1_024) * 1e-9
    voltage = 0.6 + 0.5 * np.sin(2.0 * np.pi * 20.0e6 * time_s)
    current = 1e-3 + 0.2e-3 * np.cos(2.0 * np.pi * 10.0e6 * time_s)
    run = run_data("waveforms", "waveforms", time_s=time_s, voltage_v=voltage, current_a=current)
    time_artifacts = render_plot(
        PlotRequest(
            PlotSpec(
                "time",
                PlotKind.TIME_DOMAIN,
                (run.run_id,),
                tmp_path / "time.png",
                title="Arbitrary quantities",
                table="waveforms",
                y_columns=("voltage_v", "current_a"),
                labels={
                    "voltage_v": "Input voltage (V)",
                    "current_a": "Supply current (A)",
                },
                info_lines={"voltage_v": ("Voltage information",)},
            ),
            runs=(run,),
        )
    )
    assert_plot_formats(time_artifacts.paths)
    svg = time_artifacts.paths[-1].read_text()
    assert "Input voltage (V)" in svg
    assert "Supply current (A)" in svg
    assert "Voltage information" in svg
    assert "Time (µs)" in svg

    spectrum = analyze_spectrum(
        analysis_request(
            run,
            "spectrum",
            AnalysisKind.SPECTRUM,
            WaveformSettings(
                signal_columns=("voltage_v", "current_a"),
                window="none",
            ),
        )
    )
    frequency_artifacts = render_plot(
        PlotRequest(
            PlotSpec(
                "frequency",
                PlotKind.FREQUENCY_DOMAIN,
                (spectrum.name,),
                tmp_path / "frequency.png",
                y_columns=("voltage_v_amplitude", "current_a_amplitude"),
                labels={
                    "voltage_v_amplitude": "Voltage magnitude (dBV)",
                    "current_a_amplitude": "Current magnitude (dBA)",
                },
                x_limit=(0.0, 100e6),
            ),
            results=(spectrum,),
        )
    )
    assert_plot_formats(frequency_artifacts.paths)
    frequency_svg = frequency_artifacts.paths[-1].read_text()
    assert "Voltage magnitude (dBV)" in frequency_svg
    assert "Current magnitude (dBA)" in frequency_svg
    assert "Frequency (MHz)" in frequency_svg


def test_adc_transfer_distribution_and_linearity_plots(tmp_path: Path) -> None:
    run = run_data(
        "adc",
        "conversions",
        vin_diff_v=np.repeat(np.linspace(-0.6, 0.6, 16), 8),
        dout=np.repeat(np.arange(16), 8),
    )
    settings = AdcSettings(adc_bits=4, code_range=(1, 14))
    results = (
        analyze_adc_transfer(
            analysis_request(run, "transfer", AnalysisKind.ADC_TRANSFER, settings)
        ),
        analyze_adc_distribution(
            analysis_request(run, "distribution", AnalysisKind.ADC_DISTRIBUTION, settings)
        ),
        analyze_adc_code_density(
            analysis_request(run, "linearity", AnalysisKind.ADC_CODE_DENSITY, settings)
        ),
    )
    specs = (
        PlotSpec("transfer_plot", PlotKind.TRANSFER, ("transfer",), tmp_path / "transfer"),
        PlotSpec(
            "distribution_plot",
            PlotKind.DISTRIBUTION,
            ("distribution",),
            tmp_path / "distribution",
        ),
        PlotSpec("linearity_plot", PlotKind.LINEARITY, ("linearity",), tmp_path / "linearity"),
    )
    for spec, result in zip(specs, results, strict=True):
        artifacts = render_plot(PlotRequest(spec, results=(result,)))
        assert_plot_formats(artifacts.paths)


def test_dynamic_and_sweep_plots_share_analysis_results(tmp_path: Path) -> None:
    dynamic_results = []
    for index, frequency in enumerate((1_000.0, 8_000.0)):
        sample_rate_hz = 100_000.0
        time_s = np.arange(4_096) / sample_rate_hz
        samples = 2_048.0 + 1_200.0 * np.sin(2.0 * np.pi * frequency * time_s + 0.2)
        run = run_data(f"sine{index}", "conversions", dout=samples)
        dynamic_results.append(
            analyze_adc_dynamic(
                analysis_request(
                    run,
                    f"dynamic{index}",
                    AnalysisKind.ADC_DYNAMIC,
                    AdcSettings(
                        sample_rate_hz=sample_rate_hz,
                        input_frequency_hz=frequency,
                    ),
                )
            )
        )
    sweep = analyze_adc_dynamic_sweep(
        AnalysisRequest(
            AnalysisSpec(
                "sweep",
                AnalysisKind.ADC_DYNAMIC_SWEEP,
                tuple(result.name for result in dynamic_results),
                AdcSettings(),
            ),
            results=tuple(dynamic_results),
        )
    )
    dynamic_artifacts = render_plot(
        PlotRequest(
            PlotSpec(
                "dynamic_plot",
                PlotKind.ADC_DYNAMIC,
                (dynamic_results[0].name,),
                tmp_path / "dynamic",
            ),
            results=(dynamic_results[0],),
        )
    )
    sweep_artifacts = render_plot(
        PlotRequest(
            PlotSpec(
                "sweep_plot",
                PlotKind.ADC_DYNAMIC_SWEEP,
                (sweep.name,),
                tmp_path / "sweep",
            ),
            results=(sweep,),
        )
    )
    assert_plot_formats(dynamic_artifacts.paths)
    assert_plot_formats(sweep_artifacts.paths)


def test_decision_path_and_grouped_parameter_sweep_plots(tmp_path: Path) -> None:
    decision_run = run_data(
        "decisions",
        "conversions",
        bout=("101", "011"),
        dout=(5, 3),
    )
    decision_result = analyze_adc_decision_paths(
        analysis_request(
            decision_run,
            "decision_paths",
            AnalysisKind.ADC_DECISION_PATHS,
            AdcSettings(adc_bits=3, code_weights=(4, 2, 1)),
        )
    )
    decision_artifacts = render_plot(
        PlotRequest(
            PlotSpec(
                "decision_plot",
                PlotKind.DECISION_PATHS,
                (decision_result.name,),
                tmp_path / "decision",
            ),
            results=(decision_result,),
        )
    )
    assert_plot_formats(decision_artifacts.paths)

    sweep_run = run_data(
        "timing_sweep",
        "sweep",
        conversion_rate_msps=(1.0, 2.0, 1.0, 2.0),
        sigma_lsb=(1.0, 1.5, 0.8, 1.1),
        comparator_time_percent=(25.0, 25.0, 75.0, 75.0),
    )
    sweep_artifacts = render_plot(
        PlotRequest(
            PlotSpec(
                "timing_plot",
                PlotKind.SWEEP,
                (sweep_run.run_id,),
                tmp_path / "timing",
                title="Timing sweep",
                table="sweep",
                x_column="conversion_rate_msps",
                y_columns=("sigma_lsb",),
                group_column="comparator_time_percent",
                labels={
                    "conversion_rate_msps": "Conversion rate (MSPS)",
                    "sigma_lsb": "Decision variation (LSB)",
                },
                legend_title="Comparator time",
                x_ticks=(1.0, 2.0),
                secondary_x_reciprocal=50.0,
                secondary_x_label="Decision interval (ns)",
            ),
            runs=(sweep_run,),
        )
    )
    assert_plot_formats(sweep_artifacts.paths)
    svg = sweep_artifacts.paths[-1].read_text()
    assert "Conversion rate (MSPS)" in svg
    assert "Decision interval (ns)" in svg
    assert "Comparator time" in svg
