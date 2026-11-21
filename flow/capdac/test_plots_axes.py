"""The capacitive DAC's figures against docs/references.md's notation: each axis labelled with
Razavi's name for its quantity and its SI unit in ASCII as the notation writes it (or none, a ratio
or an index), each series by its quantity in lower case, one quantity a figure, and each figure
drawing the analysis data it names."""

from __future__ import annotations

import re

import numpy as np
import pytest

from flow.pipeline import Plot

from . import plots
from .analysis import analyze_cap_mismatch, analyze_mismatch, analyze_settling
from .test_known_answers import UNIT8, comparator, nominal_sides, placed, plates_meas, settling_run
from .types import AnalysisCapMismatch, AnalysisMismatch

# docs/references.md's axis labels for the DAC's quantities ("Converters and DACs", "Amplifiers")
SETTLING = "Settling time (s)"
INL = "INL (LSB)"
DNL = "DNL (LSB)"
PELGROM = "Pelgrom coefficient (%·sqrt(fF))"
# a unit as the notation writes it: SI base units in ASCII, never scaled; the Pelgrom coefficient's
UNITS = {"V", "A", "s", "Hz", "ohm", "F", "C", "W", "J", "deg", "dB", "LSB", "V/s", "%·sqrt(fF)"}
STAGE_FIGURES = (
    "settling_stage",
    "model_stage",
    "fraction_stage",
    "fraction_error_stage",
    "asymmetry_stage",
    "separation_stage",
    "main_stage",
    "bias_stage",
)


def mismatch_conditions() -> list[AnalysisMismatch]:
    """Three Monte Carlo conditions, given out of order (1, 0.1, 0.5 %·sqrt(fF)), each of two runs:
    the design's plates and one whose MSB is 0.1, 0.5 or 1 unit heavy."""
    results = []
    for pelgrom, delta in ((0.010, 1.0), (0.001, 0.1), (0.005, 0.5)):
        main_p, diff_p, main_n, diff_n = nominal_sides(UNIT8, runs=2)
        main_p[1, 0] *= 1 + delta / 64
        main_n[1, 0] *= 1 + delta / 64
        results.append(analyze_mismatch(plates_meas(UNIT8, [(main_p, diff_p), (main_n, diff_n)], pelgrom=pelgrom)))
    return results


def cap_mismatch() -> AnalysisCapMismatch:
    """Stage 2 of four on the bench: main 0.15, difference 0.05, a 0.02 bias, P and N alike."""
    fractions = {(side, 2, 0): (0.20, 0.20) for side in ("p", "n")} | {
        (side, 2, 1): (0.12, 0.08) for side in ("p", "n")
    }
    points, fits = placed(fractions, offset_v=1e-3)
    return analyze_cap_mismatch(points, transitions=fits, comparator=comparator(1e-3))


SETTLED = analyze_settling(settling_run(UNIT8))
CONDITIONS = mismatch_conditions()
MIDDLE = next(result for result in CONDITIONS if result.pelgrom == 0.005)
BENCH = cap_mismatch()


def every_figure() -> dict[str, Plot]:
    figures = [
        plots.plot_settling_stage(SETTLED),
        plots.plot_model_stage(SETTLED),
        plots.plot_mismatch_inl(CONDITIONS),
        plots.plot_mismatch_gap(CONDITIONS),
        plots.plot_mismatch_dac_inl(CONDITIONS),
        plots.plot_dac_inl(MIDDLE),
        plots.plot_dac_dnl(MIDDLE),
        plots.plot_fraction_stage(BENCH),
        plots.plot_fraction_error_stage(BENCH),
        plots.plot_asymmetry_stage(BENCH),
        plots.plot_separation_stage(BENCH),
        plots.plot_main_stage(BENCH),
        plots.plot_bias_stage(BENCH),
    ]
    return {figure.name: figure for figure in figures}


FIGURES = every_figure()


def unit(label: str) -> str | None:
    """The unit an axis label ends with, in parentheses; None for a dimensionless one."""
    found = re.search(r"\(([^()]*(?:\([^()]*\))?)\)$", label)
    return found.group(1) if found else None


# ---- the notation


@pytest.mark.parametrize(
    ("name", "x_label"),
    [
        *((name, "Stage") for name in STAGE_FIGURES),
        ("dac_inl", "Code"),
        ("dac_dnl", "Code"),
        ("mismatch_inl", PELGROM),
        ("mismatch_gap", PELGROM),
        ("mismatch_dac_inl", PELGROM),
    ],
)
def test_each_x_axis_is_the_notations(name: str, x_label: str) -> None:
    """Rule 6: "<Name> (<unit>)"; a dimensionless quantity, an index here, has no parenthesis; the
    Pelgrom coefficient's label as the table writes it."""
    assert FIGURES[name].x_label == x_label


@pytest.mark.parametrize(
    ("name", "y_label"),
    [
        ("settling_stage", SETTLING),
        ("mismatch_inl", INL),
        ("mismatch_dac_inl", INL),
        ("dac_inl", INL),
        ("dac_dnl", DNL),
    ],
)
def test_each_y_axis_of_a_notation_quantity_is_its_label(name: str, y_label: str) -> None:
    """The settling time, the INL and the DNL ([Razavi-ADC] Sec. 8.2.1, p. 145 for a DAC; Eq.
    (12.11), p. 242 and Eq. (12.12), p. 244 for an ADC) in LSB; the statistic (worst, 95th
    percentile) and whose LSB in the title."""
    assert FIGURES[name].y_label == y_label


@pytest.mark.parametrize("name", sorted(FIGURES))
def test_every_y_axis_is_in_a_notation_unit_or_dimensionless(name: str) -> None:
    """Each y label ends in a unit as the notation writes it, or has none (a fraction)."""
    found = unit(FIGURES[name].y_label)
    assert found is None or found in UNITS, FIGURES[name].y_label


@pytest.mark.parametrize("name", sorted(FIGURES))
def test_every_series_is_named_by_its_quantity_in_lower_case(name: str) -> None:
    """docs/references.md, composing a name: "A series label is the quantity in lower case"."""
    for label in FIGURES[name].series:
        assert label == label.lower() and re.fullmatch(r"[a-z][a-z0-9 ,\-]*", label), label


@pytest.mark.xfail(
    strict=True,
    reason="capdac-10: the model's figure draws two quantities, the delay and the time constant, on one "
    "'Time (s)' axis",
)
def test_the_models_figure_draws_one_quantity() -> None:
    """Rule 6, "One quantity per axis", and the viewer's one curve a plot: the delay and the time
    constant are two quantities, each its own figure (``Delay (s)``, ``Time constant (s)``)."""
    figure = FIGURES["model_stage"]
    assert len(figure.series) == 1 and figure.y_label in ("Delay (s)", "Time constant (s)")


# ---- the data each draws


def test_the_settling_and_model_figures_draw_each_stages_slower_direction() -> None:
    settling, model = FIGURES["settling_stage"], FIGURES["model_stage"]
    assert settling.x == model.x == list(range(7))
    (curve,) = settling.series.values()
    np.testing.assert_array_equal(curve, SETTLED.settling_s)
    np.testing.assert_array_equal(model.series["delay"], SETTLED.delay_s)
    np.testing.assert_array_equal(model.series["time constant"], SETTLED.tau_s)


@pytest.mark.parametrize(
    ("name", "field"),
    [("mismatch_inl", "inl_p95_lsb"), ("mismatch_gap", "gap_p95_lsb"), ("mismatch_dac_inl", "dac_inl_p95_lsb")],
)
def test_the_monte_carlo_figures_draw_each_conditions_95th_percentile_in_order(name: str, field: str) -> None:
    """The conditions in order of their coefficient, in %·sqrt(fF) (a fraction of 0.001 is 0.1)."""
    figure = FIGURES[name]
    assert figure.x == pytest.approx([0.1, 0.5, 1.0], rel=1e-12)
    ordered = sorted(CONDITIONS, key=lambda result: result.pelgrom)
    (curve,) = figure.series.values()
    np.testing.assert_allclose(curve, [getattr(result, field) for result in ordered], rtol=1e-12)
    assert curve[0] < curve[1] < curve[2]  # the heavier MSB, the worse


def test_the_dac_figures_draw_the_chosen_runs_curves_by_code() -> None:
    """Codes 0 to 127; the 0.5-unit run's INL at code 64 is 63 delta / (127 + delta) and its DNL at
    the major transition 126 delta / (127 + delta) ([Razavi-ADC] Example 8.4, p. 146)."""
    inl, dnl = FIGURES["dac_inl"], FIGURES["dac_dnl"]
    assert inl.x == dnl.x == list(range(128)) and inl.x_ticks == dnl.x_ticks == "code"
    (inl_curve,), (dnl_curve,) = inl.series.values(), dnl.series.values()
    np.testing.assert_array_equal(inl_curve, MIDDLE.dac_inl_curve_lsb)
    assert inl_curve[64] == pytest.approx(63 * 0.5 / 127.5, rel=1e-9)
    assert dnl_curve[63] == pytest.approx(126 * 0.5 / 127.5, rel=1e-9)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("fraction_stage", 0.10),
        ("fraction_error_stage", 0.10 - 0.25),
        ("asymmetry_stage", 0.0),
        ("separation_stage", 0.10),
        ("main_stage", 0.15),
        ("bias_stage", 0.02),
    ],
)
def test_the_bench_figures_draw_each_stage_and_a_gap_where_it_has_no_curves(name: str, value: float) -> None:
    figure = FIGURES[name]
    assert figure.x == [0.0, 1.0, 2.0, 3.0] and figure.x_ticks == "step"
    (curve,) = figure.series.values()
    assert curve[2] == pytest.approx(value, abs=1e-12)
    assert all(np.isnan(curve[stage]) for stage in (0, 1, 3))
