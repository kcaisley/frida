"""Software-only tests for typed measurement and analysis plots."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pytest
from basil.HL.tektronix_oscilloscope import CapturedWaveform, XScale, YScale
from matplotlib import colors as mcolors
from matplotlib.ticker import FixedLocator

import flow.analysis.plots as analysis_plots
from flow import adc
from flow.adc.plots import plot_power_rate
from flow.adc.test_analysis import adc_measurement
from flow.analysis.plots import (
    CURVE_COLORS,
    DENSITY_COLOR_MAP,
    GRID_MAJOR_COLOR,
    LEGEND_FACE_COLOR,
    NORD_BLUE,
    NORD_ORANGE,
    NORD_YELLOW,
    PLOT_STYLE,
    SPECTRUM_COLOR_MAP,
    SPINE_COLOR,
    TEXT_COLOR,
    plot_cdac_cap_mismatch,
    plot_cdac_cap_mismatch_comparison,
    plot_serdes_output_word_grid,
    plot_serdes_symbol_eye_grid,
    plot_waveforms,
    style_grid,
    style_measurement_text,
)
from flow.analysis.test_types import cdac_physical
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
)
from flow.plot import render
from flow.scans.scan_cdac import _build_cdac_params


def test_serdes_output_word_grid_keeps_each_eight_symbol_pattern(tmp_path: Path, monkeypatch) -> None:
    figures = []
    save_figure = analysis_plots.save_figure

    def capture(fig, output_path, **kwargs):
        figures.append(fig)
        return save_figure(fig, output_path, **kwargs)

    monkeypatch.setattr(analysis_plots, "save_figure", capture)
    samples_in_symbols = np.arange(-20, 1300) / 10
    captures = {}
    for rate_mbd in (320, 960, 1600):
        time_s = samples_in_symbols / (rate_mbd * 1e6)
        scale = XScale(float(time_s[1] - time_s[0]), float(time_s[0]), "s")
        for high_symbols in range(1, 8):
            high = np.mod(np.floor(samples_in_symbols).astype(int), 8) < high_symbols
            voltage = np.where(high, 0.5, -0.5)
            captures[(rate_mbd, high_symbols)] = [
                {3: CapturedWaveform(3, np.rint(voltage * 1000).astype(int), voltage, scale, YScale(0.2, -0.2))}
            ]
    paths = plot_serdes_output_word_grid(captures, output_channel=3, output_path=tmp_path / "words")
    assert all(path.is_file() for path in paths)
    assert len(figures[0].axes) == 28
    assert [ax.get_title() for ax in figures[0].axes if ax.get_title()] == [f"{high} of 8" for high in range(1, 8)]


def test_serdes_symbol_eye_folds_nonconstant_contexts(tmp_path: Path, monkeypatch) -> None:
    from flow.scans.test_serdes import SERDES_EYE_PATTERN

    figures = []
    save_figure = analysis_plots.save_figure

    def capture(fig, output_path, **kwargs):
        figures.append(fig)
        return save_figure(fig, output_path, **kwargs)

    monkeypatch.setattr(analysis_plots, "save_figure", capture)
    samples_in_symbols = np.arange(-20, 2600) / 10
    bit_index = np.mod(np.floor(samples_in_symbols).astype(int), 256)
    marker = np.where((samples_in_symbols >= 0) & (bit_index < 8), 0.5, -0.5)
    output = np.where(np.fromiter((SERDES_EYE_PATTERN[index] == "1" for index in bit_index), bool), 0.5, -0.5)
    captures = {}
    for rate_mbd in (320, 960, 1600):
        time_s = samples_in_symbols / (rate_mbd * 1e6)
        scale = XScale(float(time_s[1] - time_s[0]), float(time_s[0]), "s")
        captures[rate_mbd] = [
            {
                channel: CapturedWaveform(
                    channel, np.rint(voltage * 1000).astype(int), voltage, scale, YScale(0.2, -0.2)
                )
                for channel, voltage in ((1, marker), (3, output))
            }
        ]
    paths = plot_serdes_symbol_eye_grid(
        captures,
        marker_channel=1,
        output_channel=3,
        pattern=SERDES_EYE_PATTERN,
        output_path=tmp_path / "symbol_eye",
    )
    assert all(path.is_file() for path in paths)
    assert len(figures[0].axes) == 3
    assert all("256 symbols" in axis.get_title() for axis in figures[0].axes)
    assert all("geometric center eye height" in axis.get_title() for axis in figures[0].axes)
    assert all("1000 mV" in axis.get_title() for axis in figures[0].axes)


def assert_plot_formats(paths: tuple[Path, ...]) -> None:
    assert tuple(path.suffix for path in paths) == (".png", ".svg", ".pdf")
    for path in paths:
        assert path.is_file()
        assert path.stat().st_size > 0
    assert plt.imread(paths[0]).shape[:2] == (2700, 4800)


def read_svg(paths: tuple[Path, ...]) -> str:
    return next(path for path in paths if path.suffix == ".svg").read_text()


@pytest.fixture(autouse=True)
def enable_all_plot_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise every shared output switch without changing production defaults."""

    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    monkeypatch.setattr(analysis_plots, "PLOT_PDFS", True)
    monkeypatch.setattr(analysis_plots, "PLOT_SVGS", True)


def test_shared_plot_style_uses_computer_modern_and_nord() -> None:
    """Keep typography, palette, axes, grids, and legends consistent."""

    with mpl.rc_context(PLOT_STYLE):
        assert plt.rcParams["mathtext.fontset"] == "cm"
        assert plt.rcParams["font.family"] == ["serif"]
        assert plt.rcParams["font.size"] == 10.0
        assert plt.rcParams["axes.prop_cycle"].by_key()["color"] == list(CURVE_COLORS)
        assert plt.rcParams["figure.figsize"] == [9.6, 5.4]
        assert plt.rcParams["figure.constrained_layout.use"] is True
        assert plt.rcParams["savefig.dpi"] == 500
        assert plt.rcParams["axes.titlesize"] == 12.0
        assert plt.rcParams["figure.titlesize"] == 12.0
        assert plt.rcParams["axes.labelsize"] == 10.0
        assert plt.rcParams["xtick.labelsize"] == 10.0
        assert plt.rcParams["ytick.labelsize"] == 10.0
        assert plt.rcParams["xtick.major.size"] == plt.rcParams["ytick.major.size"] == 2.5
        assert plt.rcParams["xtick.minor.size"] == plt.rcParams["ytick.minor.size"] == 1.5
        assert plt.rcParams["legend.fontsize"] == 10.0
        assert plt.rcParams["legend.title_fontsize"] == 10.0
        assert plt.rcParams["legend.linewidth"] == 0.8
        assert plt.rcParams["lines.linewidth"] == 1.0
        assert plt.rcParams["lines.markersize"] == 4.0
        assert plt.rcParams["text.color"] == "black"
        assert plt.rcParams["axes.labelcolor"] == TEXT_COLOR
        assert plt.rcParams["axes.edgecolor"] == SPINE_COLOR
        assert plt.rcParams["axes.grid"] is False
        assert plt.rcParams["xtick.color"] == TEXT_COLOR
        assert plt.rcParams["ytick.color"] == TEXT_COLOR
        assert mcolors.to_hex(SPECTRUM_COLOR_MAP(0.0)) == NORD_BLUE.lower()
        assert mcolors.to_hex(SPECTRUM_COLOR_MAP(0.5)) == NORD_ORANGE.lower()
        assert mcolors.to_hex(SPECTRUM_COLOR_MAP(1.0)) == NORD_YELLOW.lower()
        assert mcolors.to_hex(DENSITY_COLOR_MAP(0.0)) == mcolors.to_hex(SPECTRUM_COLOR_MAP(0.2))
        assert mcolors.to_hex(DENSITY_COLOR_MAP(0.0)) != NORD_BLUE.lower()

        fig, ax = plt.subplots()
        ax.plot((0, 1), (0, 1), label="trace")
        scatter = ax.scatter((0.5,), (0.5,))
        assert np.array_equal(scatter.get_sizes(), np.asarray([16.0]))
        quarter_ticks = np.arange(0.0, 1.01, 0.25)
        ax.set_xticks(quarter_ticks, minor=True)
        style_grid(ax)
        ax.legend()
        colorbar = fig.colorbar(mpl.cm.ScalarMappable(), ax=ax)
        colorbar.set_label("Scale")
        fig.canvas.draw()
        assert ax.spines["left"].get_edgecolor() == mcolors.to_rgba(SPINE_COLOR)
        assert ax.xaxis.label.get_color() == TEXT_COLOR
        assert ax.get_xticklabels()[0].get_color() == TEXT_COLOR
        assert colorbar.outline.get_edgecolor() == mcolors.to_rgba(SPINE_COLOR)
        assert colorbar.ax.get_yticklabels()[0].get_color() == TEXT_COLOR
        assert colorbar.ax.yaxis.label.get_color() == TEXT_COLOR
        assert ax.get_xgridlines()[0].get_color() == GRID_MAJOR_COLOR
        assert isinstance(ax.xaxis.get_minor_locator(), FixedLocator)
        assert np.array_equal(ax.get_xticks(minor=True), quarter_ticks[1:-1])
        assert ax.get_axisbelow() is True
        assert ax.lines[0].get_alpha() in (None, 1.0)
        legend = ax.get_legend()
        assert legend is not None
        assert legend.get_frame().get_facecolor()[:3] == mcolors.to_rgb(LEGEND_FACE_COLOR)
        assert legend.get_frame().get_linewidth() == 0.8
        plt.close(fig)


def test_save_figure_preserves_explicit_layout_across_formats(tmp_path: Path) -> None:
    """Do not let later output backends replace a manually positioned layout."""

    with mpl.rc_context(PLOT_STYLE):
        figure, axis = plt.subplots(layout="none")
        figure.subplots_adjust(left=0.2, right=0.7, bottom=0.25, top=0.8)
        expected_position = axis.get_position().bounds
        paths = analysis_plots.save_figure(figure, tmp_path / "explicit_layout")

    assert_plot_formats(paths)
    np.testing.assert_allclose(axis.get_position().bounds, expected_position)


def test_waveform_plot_uses_typed_signal_names_and_scaled_time(tmp_path: Path) -> None:
    msmt = adc_measurement([1, 2, 3], internal=True)
    assert msmt.wave is not None
    paths = plot_waveforms(
        msmt.wave,
        signals={"vin_p": "vin_p", "dac_botplate_p[0]": "dac_botplate_p[0]", "i(vdd_a)": "VDD_A current"},
        title="ADC waveforms",
        setup_lines=style_measurement_text(msmt),
        output_path=tmp_path / "wave",
    )
    assert_plot_formats(paths)
    svg = read_svg(paths)
    assert "vin_p" in svg
    assert "dac_botplate_p[0]" in svg
    assert "VDD_A current (A)" in svg
    assert "Time (" in svg
    assert "Source: SPICE" in svg
    assert "Conversion: 1.6 MSPS" in svg
    assert "Repetition: 1000 ns" in svg
    assert "CDAC init: h'5555" in svg
    assert "Datetime:" not in svg
    assert "LOGIC offset:" not in svg


def test_cdac_ab_plots_are_separate_per_adc(tmp_path: Path) -> None:
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
    cdac_measurement = replace(
        cdac_physical(), group=params.board_id, index=params.observed_adc, dut=params.tb.dut.cdac, param=params
    )
    cdac_analysis = AnalysisCdacCapMismatch(
        group=0,
        index=0,
        dut=cdac_measurement.dut,
        main_fraction=np.full((2, 16), 0.02),
        diff_fraction=np.full((2, 16), 0.005),
        effective_fraction=np.full((2, 16), 0.015),
        effective_fraction_by_direction=np.full((2, 16, 2), 0.015),
        direction_bias=np.zeros((2, 16, 2)),
    )
    cdac_paths = plot_cdac_cap_mismatch(
        [cdac_measurement],
        cdac_analysis,
        output_path=tmp_path / "cdac_ab",
    )
    assert cdac_paths[0].is_file()
    assert plt.imread(cdac_paths[0]).shape[:2] == (2700, 4800)

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
        comparison_analyses.append(replace(cdac_analysis, index=adc_index))
    comparison_paths = plot_cdac_cap_mismatch_comparison(
        comparison_groups,
        comparison_analyses,
        output_path=tmp_path / "cdac_ab_comparison",
    )
    assert comparison_paths[0].is_file()
    assert plt.imread(comparison_paths[0]).shape[:2] == (2700, 4800)


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
    base = replace(
        cdac_physical(), group=params.board_id, index=params.observed_adc, dut=params.tb.dut.cdac, param=params
    )
    measurement = replace(
        base,
        info=replace(base.info, readbacks={"cdac_topplate_parasitic_weight": 100.0}),
    )
    weights = np.asarray(params.tb.dut.cdac.weights, dtype=np.float64)
    expected = weights / (np.sum(65.0 * np.ceil(weights / 64.0)) + 100.0)
    np.testing.assert_allclose(measurement.expected_effective_fraction, expected)

    # Measurements of one ADC that disagree on the expectation cannot share one plot.
    inconsistent = replace(
        measurement,
        info=replace(measurement.info, readbacks={"cdac_topplate_parasitic_weight": 200.0}),
    )
    analysis = AnalysisCdacCapMismatch(
        group=None,
        index=None,
        dut=measurement.dut,
        main_fraction=np.zeros((2, 16)),
        diff_fraction=np.zeros((2, 16)),
        effective_fraction=np.zeros((2, 16)),
        effective_fraction_by_direction=np.zeros((2, 16, 2)),
        direction_bias=np.zeros((2, 16, 2)),
    )
    with pytest.raises(ValueError, match="inconsistent"):
        plot_cdac_cap_mismatch([measurement, inconsistent], analysis, output_path=Path("unused"))


def test_power_rate_of_each_adc(tmp_path: Path) -> None:
    """Each ADC's supply power over its rate, the ADC's spec, from its captures' supply readbacks (its
    noise over the rate is the noise spec's: flow/adc/test_plots.py)."""
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

    # each ADC's supply power over its rate, the ADC's spec: every rail's active power together
    for measurement in measurements:
        figure = plot_power_rate([adc.analyze_power(measurement)])
        assert figure.x == [measurement.sample_rate_hz] and figure.series == {"Total": [74.4e-6]}
        power_paths = render(figure, tmp_path / f"power_adc{measurement.param.observed_adc:02d}")
        assert_plot_formats(power_paths)
        assert "Supply power over the conversion rate" in read_svg(power_paths)
