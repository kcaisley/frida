"""Regression tests for the Murmann ADC survey area comparison."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

import flow.analysis.plots as analysis_plots
from phys.adc_survey import (
    FRIDA_TARGET_AREA_UM2,
    FRIDA_TARGET_CONVERSION_ENERGY_PJ,
    FRIDA_TARGET_ENOB,
    FRIDA_TARGET_POWER_W,
    FRIDA_TARGET_SAMPLING_RATE_HZ,
    FRIDA_TARGET_SNDR_DB,
    FRIDA_TARGET_WALDEN_FOM_FJ,
    load_filtered_points,
    plot_tradeoff,
    technology_category,
)
from phys.model import plot_hit_rate_vs_fluence, plot_max_counting_rate_vs_window


def test_technology_color_categories() -> None:
    assert technology_category(180.0) == "≥ 90 nm"
    assert technology_category(90.0) == "≥ 90 nm"
    assert technology_category(65.0) == "55 / 65 nm"
    assert technology_category(55.0) == "55 / 65 nm"
    assert technology_category(45.0) == "40 / 45 nm"
    assert technology_category(40.0) == "40 / 45 nm"
    assert technology_category(38.0) == "40 / 45 nm"
    assert technology_category(32.0) == "28 / 32 nm"
    assert technology_category(28.0) == "28 / 32 nm"
    assert technology_category(22.0) == "20 / 22 nm"
    assert technology_category(20.0) == "20 / 22 nm"
    assert technology_category(16.0) == "≤ 16 nm"
    assert technology_category(8.0) == "≤ 16 nm"


def test_frida_target_metrics() -> None:
    assert FRIDA_TARGET_AREA_UM2 == pytest.approx(3_600.0)
    assert FRIDA_TARGET_CONVERSION_ENERGY_PJ == pytest.approx(10.0)
    assert FRIDA_TARGET_SNDR_DB == pytest.approx(67.98)
    assert FRIDA_TARGET_WALDEN_FOM_FJ == pytest.approx(4.8828125)
    assert FRIDA_TARGET_CONVERSION_ENERGY_PJ == pytest.approx(
        FRIDA_TARGET_POWER_W / FRIDA_TARGET_SAMPLING_RATE_HZ * 1e12
    )
    assert FRIDA_TARGET_SNDR_DB == pytest.approx(6.02 * FRIDA_TARGET_ENOB + 1.76)


def test_filtered_adc_survey_points_and_metrics() -> None:
    points = load_filtered_points()

    assert len(points) == 270
    assert Counter(point.conference for point in points) == {"ISSCC": 140, "VLSI": 130}
    assert Counter(point.architecture_family for point in points) == {
        "SAR": 89,
        "Pipeline SAR": 47,
        "Pipeline": 34,
        "CT ΔΣ": 55,
        "DT / incrmntl. ΔΣ": 16,
        "Slope / ramp": 3,
        "VCO / time-based": 13,
        "Other": 13,
    }

    for point in points:
        assert point.area_mm2 <= 0.25
        assert point.enob >= 6.0 - 1e-9
        assert point.nyquist_rate_hz >= 0.1e6
        assert point.conversion_energy_pj <= 1_000.0
        assert point.enob == pytest.approx((point.sndr_plot_db - 1.76) / 6.02)
        assert point.conversion_energy_pj == pytest.approx(point.power_w / point.nyquist_rate_hz * 1e12)
        assert point.walden_fom_fj == pytest.approx(point.power_w / (point.nyquist_rate_hz * 2**point.enob) * 1e15)


def test_physics_plots_use_shared_formats_and_canvas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    monkeypatch.setattr(analysis_plots, "PLOT_SVGS", True)
    monkeypatch.setattr(analysis_plots, "PLOT_PDFS", True)
    points = load_filtered_points()[:12]
    outputs = (
        plot_tradeoff(
            points,
            x_metric=lambda point: point.area_mm2 * 1e6,
            y_metric=lambda point: point.enob,
            xlabel="Reported ADC area (µm²)",
            ylabel="Effective number of bits (ENOB)",
            title="ADC effective resolution vs reported area",
            output_path=tmp_path / "adc_survey",
            target_x=FRIDA_TARGET_AREA_UM2,
            target_y=FRIDA_TARGET_ENOB,
            xscale="log",
        ),
        plot_hit_rate_vs_fluence(output_path=tmp_path / "hit_rate"),
        plot_max_counting_rate_vs_window(output_path=tmp_path / "count_rate"),
    )
    for paths in outputs:
        assert tuple(path.suffix for path in paths) == (".png", ".svg", ".pdf")
        assert plt.imread(paths[0]).shape[:2] == (2700, 4800)
