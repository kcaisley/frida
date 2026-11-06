"""The CDAC's lab figures: each stage's capacitance from its switching curves
(``analyze_cap_mismatch``), one curve a quantity, so compared converters overlay as instances; drawn
on the analysis plots' canvas."""

from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

import flow.analysis.plots as analysis_plots
from flow import capdac
from flow.pipeline import Plot
from flow.plot import render

FIGURES = (
    capdac.plot_fraction_stage,
    capdac.plot_fraction_error_stage,
    capdac.plot_asymmetry_stage,
    capdac.plot_separation_stage,
    capdac.plot_main_stage,
    capdac.plot_bias_stage,
)


def cap_mismatch(index: int = 0) -> capdac.AnalysisCapMismatch:
    """One converter's sixteen stages, each side's alike: main 0.02 and difference 0.005 of its
    side, the direction bias 0.001 in the converter's mode (P's) and none in the other; the design
    expecting 0.014 of each."""
    bias = np.zeros((2, 16, 2))
    bias[0, :, 1] = 0.001
    return capdac.AnalysisCapMismatch(
        group=0,
        index=index,
        dut=None,
        main_fraction=np.full((2, 16), 0.02),
        diff_fraction=np.full((2, 16), 0.005),
        effective_fraction=np.full((2, 16), 0.015),
        effective_fraction_by_direction=np.full((2, 16, 2), 0.015),
        direction_bias=bias,
        expected_fraction=np.full(16, 0.014),
    )


def canvas(figure: Plot, path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``figure`` renders on the analysis plots' canvas (4800 x 2700 at their resolution)."""
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    png = next(drawn for drawn in render(figure, path) if drawn.suffix == ".png")
    assert plt.imread(png).shape[:2] == (2700, 4800)


def test_each_stages_capacitance_is_a_curve_by_stage(tmp_path: Path, monkeypatch) -> None:
    """The effective fraction (P's and N's mean), its error from the design's, P less N, the
    difference plates together, the main plates and the direction bias: a curve each over the stages,
    C0 first, ticked by stage."""
    figures = [figure(cap_mismatch()) for figure in FIGURES]
    assert [figure.name for figure in figures] == [
        "fraction_stage",
        "fraction_error_stage",
        "asymmetry_stage",
        "separation_stage",
        "main_stage",
        "bias_stage",
    ]
    for figure, value in zip(figures, (0.015, 0.001, 0.0, 0.01, 0.02, 0.0005), strict=True):
        assert figure.x == list(map(float, range(16))) and figure.x_ticks == "step"
        ((curve,),) = [list(figure.series.values())]
        assert curve == pytest.approx([value] * 16)
        canvas(figure, tmp_path / figure.name, monkeypatch)


def test_each_converter_draws_its_own_and_a_missing_stage_is_a_gap(tmp_path: Path, monkeypatch) -> None:
    """The legacy comparison of four converters is each converter's own figures (compared as
    instances); a stage whose curves gave no transition is NaN, a gap."""
    for index in range(4):
        result = cap_mismatch(index)
        if index == 3:
            effective = result.effective_fraction.copy()
            effective[:, 5] = np.nan
            result = replace(result, effective_fraction=effective)
        figure = capdac.plot_fraction_stage(result)
        canvas(figure, tmp_path / f"adc{index:02d}_{figure.name}", monkeypatch)
    assert np.isnan(figure.series["Effective fraction"][5])
    assert sorted(path.name for path in tmp_path.glob("*.pdf")) == [f"adc{i:02d}_fraction_stage.pdf" for i in range(4)]
