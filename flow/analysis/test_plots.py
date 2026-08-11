"""Software-only tests for typed measurement and analysis plots."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib import colors as mcolors
from matplotlib.ticker import FixedLocator
from PIL import Image
from PIL.GifImagePlugin import GifImageFile

import flow.analysis.plots as analysis_plots
from flow.analysis.adc import (
    analyze_adc_code_distribution,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise_sweep,
    analyze_adc_nonlinearity,
    analyze_adc_power_sweep,
    analyze_adc_ramp,
    analyze_adc_transfer,
)
from flow.analysis.comp import analyze_comp_offset_noise
from flow.analysis.plots import (
    COMMON_MODE_COLOR_MAP,
    GRID_MAJOR_COLOR,
    LEGEND_FACE_COLOR,
    NORD_COLORS,
    SPINE_COLOR,
    TEXT_COLOR,
    animate_adc_decision_path_density,
    apply_plot_style,
    plot_adc_code_distribution,
    plot_adc_decision_path_density,
    plot_adc_decision_paths,
    plot_adc_dynamic,
    plot_adc_dynamic_sweep,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_noise_violin_sweep,
    plot_adc_nonlinearity,
    plot_adc_power_sweep,
    plot_adc_ramp_histogram,
    plot_adc_ramp_transfer,
    plot_adc_transfer,
    plot_cdac_cap_mismatch,
    plot_cdac_cap_mismatch_comparison,
    plot_comp_campaign,
    plot_measurement_waveforms,
    style_ax,
    style_grid,
    style_legend,
)
from flow.analysis.test_adc import adc_measurement, adc_ramp_measurement
from flow.analysis.test_comp import comparator_measurement
from flow.analysis.test_types import all_measurements
from flow.analysis.types import AnalysisCdacCapMismatch, CompDaq
from flow.scans.scan_cdac import _build_cdac_params
from flow.scans.scan_comp import _build_comp_params


def assert_plot_formats(paths: tuple[Path, ...]) -> None:
    assert tuple(path.suffix for path in paths) == (".png", ".pdf", ".svg")
    for path in paths:
        assert path.is_file()
        assert path.stat().st_size > 0


def test_shared_plot_style_uses_computer_modern_and_nord() -> None:
    """Keep typography, palette, axes, grids, and legends consistent."""

    apply_plot_style()
    assert plt.rcParams["mathtext.fontset"] == "cm"
    assert plt.rcParams["font.family"] == ["serif"]
    assert plt.rcParams["axes.prop_cycle"].by_key()["color"] == list(NORD_COLORS)
    assert plt.rcParams["savefig.dpi"] == 200

    fig, ax = plt.subplots()
    ax.plot((0, 1), (0, 1), label="trace")
    quarter_ticks = np.arange(0.0, 1.01, 0.25)
    ax.set_xticks(quarter_ticks, minor=True)
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    assert ax.spines["left"].get_edgecolor() == mcolors.to_rgba(SPINE_COLOR)
    assert ax.xaxis.label.get_color() == TEXT_COLOR
    assert ax.get_xgridlines()[0].get_color() == GRID_MAJOR_COLOR
    assert isinstance(ax.xaxis.get_minor_locator(), FixedLocator)
    assert np.array_equal(ax.get_xticks(minor=True), quarter_ticks[1:-1])
    assert ax.get_axisbelow() is True
    legend = ax.get_legend()
    assert legend is not None
    assert legend.get_frame().get_facecolor()[:3] == mcolors.to_rgb(LEGEND_FACE_COLOR)
    plt.close(fig)


def test_waveform_plot_uses_typed_signal_names_and_scaled_time(tmp_path: Path) -> None:
    msmt = adc_measurement([1, 2, 3], internal=True)
    paths = plot_measurement_waveforms(
        msmt,
        signal_names=("vin_diff_v", "dac_botplate_p_15_v"),
        output_path=tmp_path / "wave",
    )
    assert_plot_formats(paths)
    svg = paths[-1].read_text()
    assert "vin_diff_v" in svg
    assert "dac_botplate_p_15_v" in svg
    assert "Time (" in svg
    assert "Datetime: 2026-07-29 00:00" in svg
    assert "LOGIC offset:" not in svg


def test_comparator_campaign_and_cdac_ab_plots_are_separate_per_adc(tmp_path: Path) -> None:
    comparator_groups = []
    comparator_analyses = []
    for vin_cm_v in (0.6, 0.8):
        group = []
        for vin_diff_v, ones in ((-1e-3, 100), (0.0, 50), (1e-3, 0)):
            base = comparator_measurement()
            group.append(
                replace(
                    base,
                    param=_build_comp_params(
                        adc_index=0,
                        campaign="comp_common_mode",
                        sampling_mode="track",
                        sweep_stage="fixed",
                        vin_cm_v=vin_cm_v,
                        vin_diff_v=vin_diff_v,
                        conversions=100,
                    ),
                    daq=CompDaq(
                        trial_index=np.arange(100),
                        vin_diff_v=np.full(100, vin_diff_v),
                        vin_cm_v=np.full(100, vin_cm_v),
                        decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
                    ),
                )
            )
        comparator_groups.append(group)
        comparator_analyses.append(analyze_comp_offset_noise(group))
    comparator_paths = plot_comp_campaign(
        comparator_groups,
        comparator_analyses,
        output_path=tmp_path / "comp_campaign",
        formats=("png",),
    )
    assert comparator_paths[0].is_file()
    assert plt.imread(comparator_paths[0]).shape[:2] == (1800, 3200)

    params = _build_cdac_params(
        adc_index=0,
        side="p",
        element=0,
        direction="1to0",
        dac_diffcaps=0,
        vin_diff_v=0.3,
        conversions=1,
        sweep_stage="fixed",
    )
    cdac_measurement = replace(all_measurements()[4], param=params)
    cdac_analysis = AnalysisCdacCapMismatch(
        adc_index=0,
        curve_element=np.asarray([0], dtype=np.int64),
        curve_side=np.asarray([0], dtype=np.uint8),
        curve_direction=np.asarray([0], dtype=np.uint8),
        curve_diffcaps=np.asarray([0], dtype=np.uint8),
        transition_v=np.asarray([0.3]),
        normalized_step=np.asarray([-0.25]),
        curve_valid=np.asarray([1], dtype=np.uint8),
        main_fraction=np.full((2, 16), 0.02),
        diff_fraction=np.full((2, 16), 0.005),
        effective_fraction=np.full((2, 16), 0.015),
        direction_bias=np.zeros((2, 16, 2)),
    )
    cdac_paths = plot_cdac_cap_mismatch(
        [cdac_measurement],
        cdac_analysis,
        output_path=tmp_path / "cdac_ab",
        formats=("png",),
    )
    assert cdac_paths[0].is_file()
    assert plt.imread(cdac_paths[0]).shape[:2] == (1800, 3200)

    comparison_groups = []
    comparison_analyses = []
    for adc_index in range(4):
        adc_params = _build_cdac_params(
            adc_index=adc_index,
            side="p",
            element=0,
            direction="1to0",
            dac_diffcaps=0,
            vin_diff_v=0.3,
            conversions=1,
            sweep_stage="fixed",
        )
        comparison_groups.append([replace(cdac_measurement, param=adc_params)])
        comparison_analyses.append(replace(cdac_analysis, adc_index=adc_index))
    comparison_paths = plot_cdac_cap_mismatch_comparison(
        comparison_groups,
        comparison_analyses,
        output_path=tmp_path / "cdac_ab_comparison",
        formats=("png",),
    )
    assert comparison_paths[0].is_file()
    assert plt.imread(comparison_paths[0]).shape[:2] == (1800, 3200)


def test_comparator_common_mode_crop_and_sampling_noise_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    figures = []

    def capture_figure(fig, *_args, **_kwargs):
        figures.append(fig)
        return ()

    monkeypatch.setattr(analysis_plots, "_save_figure", capture_figure)

    def group(
        campaign: str,
        mode: str,
        vin_cm_v: float,
        *,
        center_v: float = 0.0,
        coupling_percent: float | None = None,
    ):
        measurements = []
        for vin_diff_v, ones in (
            (center_v - 1.0e-3, 0),
            (center_v, 50),
            (center_v + 1.0e-3, 100),
        ):
            base = comparator_measurement()
            measurements.append(
                replace(
                    base,
                    param=_build_comp_params(
                        adc_index=0,
                        campaign=campaign,
                        sampling_mode=mode,
                        sweep_stage="fixed",
                        vin_cm_v=vin_cm_v,
                        vin_diff_v=vin_diff_v,
                        conversions=100,
                        requested_dac_rail_percent=coupling_percent,
                    ),
                    daq=CompDaq(
                        trial_index=np.arange(100),
                        vin_diff_v=np.full(100, vin_diff_v),
                        vin_cm_v=np.full(100, vin_cm_v),
                        decision=np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8))),
                    ),
                )
            )
        return measurements

    common_groups = [
        group("comp_common_mode", "track", vin_cm_v, center_v=10.0e-3) for vin_cm_v in (0.6, 0.7, 0.8, 1.0)
    ]
    plot_comp_campaign(
        common_groups,
        [analyze_comp_offset_noise(values) for values in common_groups],
        output_path=Path("unused_common"),
    )
    common_figure = figures[-1]
    assert [ax.get_title() for ax in common_figure.axes] == [
        "Comparator S-curve (CDF)",
        "Gaussian fit of μ (threshold) and σ (noise)",
    ]
    assert common_figure.axes[0].get_xlim() == pytest.approx((0.0, 25.0))
    assert common_figure.axes[0].get_xlabel() == "Differential input (mV)"
    assert common_figure.axes[1].get_ylim() == pytest.approx((0.0, 25.0))
    assert [
        line.get_label() for line in common_figure.axes[0].get_lines() if line.get_label().startswith("Vin_cm")
    ] == [
        "Vin_cm = 0.7 V",
        "Vin_cm = 0.8 V",
        "Vin_cm = 1 V",
    ]
    assert common_figure.axes[1].get_xticks() == pytest.approx((0.7, 0.8, 1.0))
    assert common_figure.axes[1].get_xlim() == pytest.approx((0.65, 1.05))
    assert common_figure.axes[1].get_xlabel() == "Common-mode input (V)"
    assert common_figure.axes[1].get_ylabel() == "Input error (mV)"
    common_fit_lines = [line for line in common_figure.axes[0].get_lines() if line.get_label().startswith("Vin_cm")]
    assert len(common_figure.axes[0].collections) == 3
    assert all(len(line.get_xdata()) == 1_001 for line in common_fit_lines)
    expected_common_mode_colors = [
        COMMON_MODE_COLOR_MAP((vin_cm_v - 0.7) / (1.2 - 0.7)) for vin_cm_v in (0.7, 0.8, 1.0)
    ]
    for line, expected_color in zip(common_fit_lines, expected_common_mode_colors, strict=True):
        np.testing.assert_allclose(mcolors.to_rgba(line.get_color()), expected_color)
    for violin, expected_color in zip(
        common_figure.axes[1].collections,
        expected_common_mode_colors,
        strict=True,
    ):
        np.testing.assert_allclose(violin.get_facecolor()[0, :3], expected_color[:3], atol=0.01)
        assert violin.get_facecolor()[0, 3] == pytest.approx(0.55)

    sampling_groups = [
        group(
            "comp_sampling_noise",
            mode,
            0.7,
            center_v=10.0e-3 + coupling_percent * 5.0e-6 + (0.2e-3 if mode == "hold" else 0.0),
            coupling_percent=coupling_percent,
        )
        for coupling_percent in (0.0, 25.0, 50.0, 75.0, 100.0)
        for mode in ("track", "hold")
    ]
    plot_comp_campaign(
        sampling_groups,
        [analyze_comp_offset_noise(values) for values in sampling_groups],
        output_path=Path("unused_sampling"),
    )
    sampling_figure = figures[-1]
    assert [ax.get_title() for ax in sampling_figure.axes] == [
        "Comparator S-curves (CDF)",
        "Gaussian fit of μ (threshold) and σ (noise)",
    ]
    assert sampling_figure.axes[0].get_xlim() == pytest.approx((0.0, 25.0))
    curve_labels = [text.get_text() for text in sampling_figure.axes[0].get_legend().get_texts()]
    assert len(curve_labels) == 10
    assert any(label == "Track P/N = 0/100%" for label in curve_labels)
    assert any(label == "Hold P/N = 100/0%" for label in curve_labels)
    sampling_fit_lines = [line for line in sampling_figure.axes[0].get_lines() if " P/N = " in line.get_label()]
    assert len(sampling_fit_lines) == 10
    assert len(sampling_figure.axes[0].collections) == 10
    assert all(len(line.get_xdata()) == 1_001 for line in sampling_fit_lines)
    distribution_ax = sampling_figure.axes[1]
    assert distribution_ax.get_xlim() == pytest.approx((-8.0, 108.0))
    assert distribution_ax.get_ylim() == pytest.approx((0.0, 25.0))
    assert distribution_ax.get_xticks() == pytest.approx((0.0, 25.0, 50.0, 75.0, 100.0))
    assert distribution_ax.get_xlabel() == "VDAC coupling (P/N % of VDD_DAC)"
    assert distribution_ax.get_ylabel() == "Input error (mV)"
    distribution_labels = [text.get_text() for text in distribution_ax.get_legend().get_texts()]
    assert distribution_labels == ["Track", "Hold"]
    assert len(distribution_ax.collections) == 10
    assert len(distribution_ax.texts) == 10
    assert "Vin_cm = 0.7 V" in sampling_figure._suptitle.get_text()

    for fig in figures:
        plt.close(fig)


def test_cdac_pex_expectation_includes_recorded_topplate_parasitic() -> None:
    params = _build_cdac_params(
        adc_index=0,
        side="p",
        element=0,
        direction="1to0",
        dac_diffcaps=0,
        vin_diff_v=0.3,
        conversions=1,
        sweep_stage="fixed",
    )
    base = replace(all_measurements()[4], param=params)
    measurement = replace(
        base,
        info=replace(base.info, readbacks={"cdac_topplate_parasitic_weight": 100.0}),
    )
    weights = np.asarray(params.dut.cdac.weights, dtype=np.float64)
    expected = weights / (np.sum(65.0 * np.ceil(weights / 64.0)) + 100.0)
    np.testing.assert_allclose(
        analysis_plots._expected_cdac_effective_fraction([measurement]),
        expected,
    )

    inconsistent = replace(
        measurement,
        info=replace(measurement.info, readbacks={"cdac_topplate_parasitic_weight": 200.0}),
    )
    with pytest.raises(ValueError, match="inconsistent"):
        analysis_plots._expected_cdac_effective_fraction([measurement, inconsistent])


def test_adc_transfer_noise_and_linearity_plots(tmp_path: Path) -> None:
    msmt = adc_measurement(
        np.repeat(np.arange(16), 8),
        vin_diff_v=np.repeat(np.linspace(-0.6, 0.6, 16), 8),
        internal=True,
    )
    outputs = (
        plot_adc_transfer(
            [msmt],
            analyze_adc_transfer([msmt]),
            output_path=tmp_path / "transfer",
        ),
        plot_adc_code_distribution(
            [msmt],
            analyze_adc_code_distribution([msmt]),
            output_path=tmp_path / "noise",
        ),
        plot_adc_nonlinearity(
            msmt,
            analyze_adc_nonlinearity(msmt, method="code_density", code_range=(1, 14)),
            output_path=tmp_path / "nonlin",
        ),
    )
    for paths in outputs:
        assert_plot_formats(paths)


def test_adc_ramp_plots_render_completed_analysis(tmp_path: Path) -> None:
    """Keep ramp plotters independent of measurements and CDAC fitting."""

    analysis = analyze_adc_ramp(adc_ramp_measurement())
    nominal = analysis.curves[0]
    analysis = replace(
        analysis,
        curves=(nominal, replace(nominal, label="Measured CDAC", transfer_mean_dout=nominal.transfer_mean_dout + 1.0)),
    )
    outputs = (
        plot_adc_ramp_transfer(analysis, output_path=tmp_path / "ramp_transfer"),
        plot_adc_ramp_histogram(analysis, output_path=tmp_path / "ramp_histogram"),
        plot_adc_nonlinearity(analysis, output_path=tmp_path / "ramp_nonlinearity"),
    )
    for paths in outputs:
        assert_plot_formats(paths)
        svg = paths[-1].read_text()
        assert "Nominal CDAC" in svg
        assert "Measured CDAC" in svg


def test_dynamic_sweep_and_decision_path_plots(tmp_path: Path) -> None:
    measurements = []
    for index, frequency_hz in enumerate((1_000.0, 8_000.0)):
        sample_rate_hz = 100_000.0
        time_s = np.arange(4_096) / sample_rate_hz
        samples = np.rint(2_048.0 + 1_200.0 * np.sin(2.0 * np.pi * frequency_hz * time_s + 0.2))
        measurements.append(
            adc_measurement(
                samples,
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=frequency_hz,
                logic_phase_delay_symbols=index,
            )
        )
    dynamic = analyze_adc_dynamic(measurements[0])
    sweep = analyze_adc_dynamic_sweep(measurements)
    assert_plot_formats(
        plot_adc_dynamic(
            measurements[0],
            dynamic,
            output_path=tmp_path / "dynamic",
        )
    )
    assert_plot_formats(
        plot_adc_dynamic_sweep(
            measurements,
            sweep,
            output_path=tmp_path / "sweep",
        )
    )

    decisions = analyze_adc_decision_paths(measurements[0], selection="single")
    paths = plot_adc_decision_paths(
        measurements[0],
        decisions,
        output_path=tmp_path / "decisions",
    )
    assert_plot_formats(paths)
    decision_svg = paths[-1].read_text()
    assert "ADC decision paths" in decision_svg
    assert GRID_MAJOR_COLOR.lower() not in decision_svg.lower()

    all_decisions = analyze_adc_decision_paths(measurements[0], selection="all")
    density_paths = plot_adc_decision_path_density(
        measurements[0],
        all_decisions,
        output_path=tmp_path / "decision_density",
    )
    assert_plot_formats(density_paths)
    density_svg = density_paths[-1].read_text()
    assert "decision-path density" in density_svg
    assert "Conversions per path" in density_svg
    assert GRID_MAJOR_COLOR.lower() not in density_svg.lower()
    assert plt.imread(density_paths[0]).shape[:2] == (1080, 1920)


def test_decision_path_density_holds_each_discrete_estimate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not invent linearly interpolated SAR estimates between decisions."""

    msmt = adc_measurement([100, 101, 102])
    analysis = analyze_adc_decision_paths(msmt, selection="all")
    original_histogram2d = np.histogram2d
    original_line_collection = analysis_plots.LineCollection
    sampled_estimates = []
    rendered_segments = []

    def record_histogram2d(x, y, *args, **kwargs):
        sampled_estimates.append(np.asarray(y))
        return original_histogram2d(x, y, *args, **kwargs)

    def record_line_collection(segments, *args, **kwargs):
        rendered_segments.extend(np.asarray(segments, dtype=np.float64))
        return original_line_collection(segments, *args, **kwargs)

    monkeypatch.setattr(np, "histogram2d", record_histogram2d)
    monkeypatch.setattr(analysis_plots, "LineCollection", record_line_collection)
    plot_adc_decision_path_density(
        msmt,
        analysis,
        output_path=tmp_path / "held_decision_density",
    )

    sampled = sampled_estimates[0].reshape(len(analysis.estimate_dout), -1)
    expected = np.concatenate(
        (
            np.repeat(analysis.estimate_dout[:, :-1], 8, axis=1),
            analysis.estimate_dout[:, -1, None],
        ),
        axis=1,
    )
    np.testing.assert_array_equal(sampled, expected)

    # The largest jump in one representative path must be connected at the
    # exact integer decision boundary and at its true endpoint values.
    cycle = int(np.argmax(np.abs(np.diff(analysis.estimate_dout[0])))) + 1
    previous = analysis.estimate_dout[0, cycle - 1]
    current = analysis.estimate_dout[0, cycle]
    expected_segment = np.asarray(((float(cycle), previous), (float(cycle), current)))
    assert abs(current - previous) > 1
    assert any(np.allclose(segment, expected_segment) for segment in rendered_segments)


def test_decision_path_density_animation(tmp_path: Path) -> None:
    """Build a cumulative GIF through the shared density-frame renderer."""

    msmt = adc_measurement([100, 101, 102])
    analysis = analyze_adc_decision_paths(msmt, selection="all")
    paths = animate_adc_decision_path_density(
        msmt,
        analysis,
        output_path=tmp_path / "decision_density",
        frame_count=3,
    )
    assert tuple(path.suffix for path in paths) == (".gif",)
    assert paths[0].is_file()
    assert paths[0].stat().st_size > 0
    assert plt.imread(paths[0]).shape[:2] == (1080, 1920)
    with Image.open(paths[0]) as animation:
        assert isinstance(animation, GifImageFile)
        assert animation.n_frames == 3
        assert animation.info["duration"] == 250
        for frame_index in range(animation.n_frames):
            animation.seek(frame_index)
            assert animation.dispose_extent == (0, 0, 1920, 1080)


def test_noise_rate_and_power_sweep_plots(tmp_path: Path) -> None:
    measurements = []
    for adc_index, sample_rate_hz in ((0, 100_000.0), (1, 200_000.0)):
        time_s = np.arange(4_096) / sample_rate_hz
        samples = np.rint(2_048.0 + 1_200.0 * np.sin(2.0 * np.pi * 1_000.0 * time_s))
        readbacks = {}
        for rail, current_a in (("vdd_a", 2e-6), ("vdd_d", 40e-6), ("vdd_dac", 20e-6)):
            readbacks[f"{rail}_measured_voltage_v"] = 1.2
            readbacks[f"{rail}_measured_current_a"] = 0.5 * current_a
            readbacks[f"{rail}_active_average_current_a"] = current_a
            readbacks[f"{rail}_active_average_power_w"] = 1.2 * current_a
        measurements.append(
            adc_measurement(
                samples,
                sample_rate_hz=sample_rate_hz,
                input_frequency_hz=1_000.0,
                observed_adc=adc_index,
                readbacks=readbacks,
            )
        )

    dynamic_paths = plot_adc_noise_sweep(
        measurements,
        analyze_adc_noise_sweep(measurements),
        output_path=tmp_path / "dynamic_rate",
        series_labels=("ADC00", "ADC01"),
    )
    assert_plot_formats(dynamic_paths)
    assert plt.imread(dynamic_paths[0]).shape[:2] == (1080, 1920)
    dynamic_svg = dynamic_paths[-1].read_text().lower()
    assert "snr (db)" in dynamic_svg
    assert "enob (bit)" in dynamic_svg
    assert "input-referred noise (lsb rms)" in dynamic_svg
    assert "input-referred noise (mv rms)" in dynamic_svg
    assert "time per decision cycle (ns)" in dynamic_svg
    power_paths = plot_adc_power_sweep(
        measurements,
        analyze_adc_power_sweep(measurements),
        output_path=tmp_path / "power",
    )
    assert len(power_paths) == 6
    assert_plot_formats(power_paths[:3])
    assert_plot_formats(power_paths[3:])
    for svg_path in (power_paths[2], power_paths[5]):
        power_svg = svg_path.read_text()
        assert "static and dynamic supply power" in power_svg
        assert "VDD_A static" in power_svg
        assert "VDD_A dynamic" in power_svg
        assert "Total:" in power_svg


def test_noise_sweep_plot_uses_stable_timing_colors(tmp_path: Path) -> None:
    measurements = [
        adc_measurement(
            [100, 100, 100, 100] if offset == -3 else [100, 101, 99, 100],
            sample_rate_hz=1.0e6,
            logic_phase_delay_symbols=offset,
        )
        for offset in range(-3, 4)
    ]
    paths = plot_adc_noise_sweep(
        measurements,
        analyze_adc_noise_sweep(measurements),
        output_path=tmp_path / "noise_sweep",
    )
    assert_plot_formats(paths)
    assert plt.imread(paths[0]).shape[:2] == (1080, 1920)
    svg = paths[-1].read_text().lower()
    assert "snr (db)" in svg
    assert "enob (bit)" in svg
    assert "input-referred noise (lsb rms)" in svg
    assert "input-referred noise (mv rms)" in svg
    assert "as % of decision cycle" in svg
    assert "logic offsets:" not in svg
    assert "#eceff4" in svg
    for color in ("#4c566a", "#5e81ac", "#a3be8c", "#bf616a", "#d08770", "#b48ead", "#88c0d0"):
        assert color in svg


def test_noise_distribution_sweep_uses_one_count_scale(tmp_path: Path) -> None:
    measurements = [
        adc_measurement(
            [100, 100, 101, 101, 101, 102],
            sample_rate_hz=sample_rate_hz,
            observed_adc=0,
            logic_phase_delay_symbols=2,
        )
        for sample_rate_hz in (1.0e6, 2.0e6, 3.0e6)
    ]
    paths = plot_adc_noise_distribution_sweep(
        measurements,
        analyze_adc_noise_sweep(measurements),
        output_path=tmp_path / "noise_distributions",
    )

    assert_plot_formats(paths)
    assert plt.imread(paths[0]).shape[:2] == (1080, 1920)
    svg = paths[-1].read_text()
    assert "ADC00 fixed-input output-code distributions" in svg
    assert "Global histogram scale" in svg
    assert "Mean ±1σ" in svg


def test_noise_violin_sweep_overlays_exact_lsb_bins(tmp_path: Path) -> None:
    measurements = [
        adc_measurement(
            [100, 100, 101, 101, 101, 102],
            sample_rate_hz=sample_rate_hz,
            observed_adc=0,
            logic_phase_delay_symbols=2,
        )
        for sample_rate_hz in (1.0e6, 2.0e6, 3.0e6)
    ]
    paths = plot_adc_noise_violin_sweep(
        measurements,
        analyze_adc_noise_sweep(measurements),
        output_path=tmp_path / "noise_violins",
    )

    assert_plot_formats(paths)
    assert plt.imread(paths[0]).shape[:2] == (1080, 1920)
    svg = paths[-1].read_text()
    assert "ADC00 fixed-input output-code violin distributions" in svg
    assert "KDE (bandwidth 0.5)" in svg
    assert "Exact LSB counts" in svg
    assert "Median" not in svg


def test_noise_sweep_plot_labels_three_point_quadratic_as_guide(tmp_path: Path) -> None:
    measurements = [
        adc_measurement(
            [100, 101, 99 + index, 100],
            sample_rate_hz=sample_rate_hz,
            logic_phase_delay_symbols=2,
        )
        for index, sample_rate_hz in enumerate((2.0e6, 6.0e6, 10.0e6))
    ]
    paths = plot_adc_noise_sweep(
        measurements,
        analyze_adc_noise_sweep(measurements),
        output_path=tmp_path / "noise_sweep_quadratic",
        quadratic_guide=True,
    )
    assert "quadratic guide (3 points)" in paths[-1].read_text().lower()


def test_noise_sweep_plot_accepts_explicit_comparison_series(tmp_path: Path) -> None:
    measurements = [
        adc_measurement(
            [100, 101, 99 + index, 100],
            sample_rate_hz=sample_rate_hz,
            logic_phase_delay_symbols=2,
        )
        for index, sample_rate_hz in enumerate((2.0e6, 6.0e6, 10.0e6))
    ]
    paths = plot_adc_noise_sweep(
        measurements,
        analyze_adc_noise_sweep(measurements),
        output_path=tmp_path / "noise_comparison",
        series_labels=("Measured ADC00", "Generated SPICE", "PEX SPICE"),
        title="ADC00 measurement vs SPICE",
    )
    svg = paths[-1].read_text()
    assert "ADC00 measurement vs SPICE" in svg
    assert "Measured ADC00" in svg
    assert "Generated SPICE" in svg
    assert "PEX SPICE" in svg
    assert "COMP→LOGIC interval" not in svg
