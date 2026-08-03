"""Software-only tests for typed measurement and analysis plots."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib import colors as mcolors
from matplotlib.ticker import FixedLocator
from PIL import Image

import flow.analysis.plots as analysis_plots
from flow.analysis.adc import (
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise,
    analyze_adc_noise_sweep,
    analyze_adc_nonlin,
    analyze_adc_power_sweep,
    analyze_adc_transfer,
)
from flow.analysis.plots import (
    GRID_MAJOR_COLOR,
    LEGEND_FACE_COLOR,
    NORD_COLORS,
    SPINE_COLOR,
    TEXT_COLOR,
    animate_adc_decision_path_density,
    apply_plot_style,
    plot_adc_decision_path_density,
    plot_adc_decision_paths,
    plot_adc_dynamic,
    plot_adc_dynamic_sweep,
    plot_adc_noise,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_noise_violin_sweep,
    plot_adc_nonlin,
    plot_adc_power_sweep,
    plot_adc_transfer,
    plot_measurement_waveforms,
    style_ax,
    style_grid,
    style_legend,
)
from flow.analysis.test_adc import adc_measurement


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
    assert ax.get_legend().get_frame().get_facecolor()[:3] == mcolors.to_rgb(LEGEND_FACE_COLOR)
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
        plot_adc_noise(
            [msmt],
            analyze_adc_noise([msmt]),
            output_path=tmp_path / "noise",
        ),
        plot_adc_nonlin(
            msmt,
            analyze_adc_nonlin(msmt, method="code_density", code_range=(1, 14)),
            output_path=tmp_path / "nonlin",
        ),
    )
    for paths in outputs:
        assert_plot_formats(paths)


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
