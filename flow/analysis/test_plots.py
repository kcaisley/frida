"""Software-only tests for typed measurement and analysis plots."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mcolors

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
    apply_plot_style,
    plot_adc_decision_paths,
    plot_adc_dynamic,
    plot_adc_dynamic_rate_sweep,
    plot_adc_dynamic_sweep,
    plot_adc_noise,
    plot_adc_noise_sweep,
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
    style_ax(ax)
    style_grid(ax)
    style_legend(ax)
    assert ax.spines["left"].get_edgecolor() == mcolors.to_rgba(SPINE_COLOR)
    assert ax.xaxis.label.get_color() == TEXT_COLOR
    assert ax.get_xgridlines()[0].get_color() == GRID_MAJOR_COLOR
    assert ax.get_legend().get_frame().get_facecolor()[:3] == mcolors.to_rgb(LEGEND_FACE_COLOR)
    plt.close(fig)


def test_waveform_plot_uses_typed_signal_names_and_scaled_time(tmp_path: Path) -> None:
    msmt = adc_measurement([1, 2, 3])
    paths = plot_measurement_waveforms(
        msmt,
        signal_names=("vin_diff_v", "comp_out_v"),
        output_path=tmp_path / "wave",
    )
    assert_plot_formats(paths)
    svg = paths[-1].read_text()
    assert "vin_diff_v" in svg
    assert "comp_out_v" in svg
    assert "Time (" in svg
    assert "Recorded: 2026-07-29 00:00" in svg
    assert "LOGIC offset:" not in svg


def test_adc_transfer_noise_and_linearity_plots(tmp_path: Path) -> None:
    msmt = adc_measurement(
        np.repeat(np.arange(16), 8),
        vin_diff_v=np.repeat(np.linspace(-0.6, 0.6, 16), 8),
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
    assert "ADC decision paths" in paths[-1].read_text()


def test_dynamic_rate_and_power_sweep_plots(tmp_path: Path) -> None:
    measurements = []
    for adc_index, sample_rate_hz in ((0, 100_000.0), (1, 200_000.0)):
        time_s = np.arange(4_096) / sample_rate_hz
        samples = np.rint(2_048.0 + 1_200.0 * np.sin(2.0 * np.pi * 1_000.0 * time_s))
        readbacks = {}
        for rail, current_a in (("vdd_a", 2e-6), ("vdd_d", 40e-6), ("vdd_dac", 20e-6)):
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

    dynamic_paths = plot_adc_dynamic_rate_sweep(
        measurements,
        analyze_adc_dynamic_sweep(measurements),
        output_path=tmp_path / "dynamic_rate",
    )
    assert_plot_formats(dynamic_paths)
    dynamic_svg = dynamic_paths[-1].read_text().lower()
    assert "sndr (db)" in dynamic_svg
    assert "enob (bit)" in dynamic_svg
    assert "input-referred noise (mv rms)" in dynamic_svg
    assert "time per decision cycle (ns)" in dynamic_svg
    assert_plot_formats(
        plot_adc_power_sweep(
            measurements,
            analyze_adc_power_sweep(measurements),
            output_path=tmp_path / "power",
        )
    )


def test_noise_sweep_plot_uses_stable_timing_colors(tmp_path: Path) -> None:
    measurements = [
        adc_measurement(
            [100, 101, 99, 100],
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
    svg = paths[-1].read_text().lower()
    assert "input-referred noise rms (lsb)" in svg
    assert "input-referred noise rms (mv)" in svg
    assert "as % of decision cycle" in svg
    assert "logic offsets:" not in svg
    assert "#eceff4" in svg
    for color in ("#4c566a", "#5e81ac", "#a3be8c", "#bf616a", "#d08770", "#b48ead", "#88c0d0"):
        assert color in svg
