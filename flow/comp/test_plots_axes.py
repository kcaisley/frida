"""The comparator's figures against docs/references.md's notation: each axis labelled with
Razavi's name for its quantity and its SI unit in ASCII (or none, dimensionless), each series by its
quantity in lower case, and each figure drawing the analysis data it names."""

from __future__ import annotations

import math
import re

import numpy as np
import pytest

from flow.pipeline import Plot

from . import plots
from .analysis import analyze_common_mode, analyze_edge_eye, analyze_response, analyze_scope_edges
from .params import SUPPLY_SWEEP, Params
from .test_known_answers import (
    conversions_of,
    converter_wave,
    expected_curve,
    metric_inputs,
    offset_noise_of,
    scope_wave,
)
from .types import AnalysisCommonMode, AnalysisMetastability, AnalysisSamplingNoise, AnalysisScurve

# docs/references.md's axis labels for the comparator's quantities (its "Comparators" and
# "Amplifiers" tables and the supplies'), each "<Name> (<unit>)" or a dimensionless name
DIFFERENTIAL_INPUT = "Differential input (V)"
COMMON_MODE = "Input common mode (V)"
DELAY = "Clock-to-decision delay (s)"
NOISE = "Input-referred noise (V)"
OFFSET = "Offset (V)"
ENERGY = "Energy per decision (J)"
SUPPLY_RELATIVE = "Supply over nominal"
PROBABILITY = "Decision probability"
UNRESOLVED = "Fraction unresolved"
# a unit as the notation writes it: SI base units in ASCII, never scaled
UNITS = {"V", "A", "s", "Hz", "ohm", "F", "C", "W", "J", "deg", "dB", "LSB", "V/s", "V/sqrt(Hz)"}
SCALED = re.compile(r"\((m|u|µ|n|p|f|k|M|G)(V|A|s|Hz|F|W|J|ohm|Ω)\)")


def metastability() -> AnalysisMetastability:
    return metric_inputs()["metastability"]


def scurve() -> AnalysisScurve:
    return AnalysisScurve(
        group=None,
        index=None,
        dut=Params(),
        vin_diff_v=np.asarray([-1e-3, 0.0, 1e-3]),
        probability=np.asarray([0.1, 0.5, 0.9]),
        unresolved_fraction=np.asarray([0.0, 0.25, 0.0]),
        total_unresolved_fraction=0.25 / 3,
    )


def common_mode() -> AnalysisCommonMode:
    inputs = np.linspace(-2e-3, 2e-3, 9)
    return analyze_common_mode(
        [
            expected_curve(inputs, 0.1e-3, 0.5e-3, 1000, vin_cm_v=0.6),
            expected_curve(inputs * 0.01, 0.0, 0.5e-3, 1000, vin_cm_v=0.7),  # too narrow: unbracketed
            expected_curve(inputs, -0.2e-3, 0.4e-3, 1000, vin_cm_v=0.8),
        ]
    )


def sampling() -> AnalysisSamplingNoise:
    return AnalysisSamplingNoise(
        group=None,
        index=None,
        dut=Params(),
        coupling_percent=np.asarray([25.0, 75.0]),
        sampling_mode=("track", "hold"),
        offset_v=np.asarray([0.1e-3, 0.2e-3]),
        noise_sigma_v=np.asarray([0.4e-3, 0.5e-3]),
        decision_polarity=np.asarray([1, 1]),
        validity=("valid", "unbracketed"),
        vin_diff_v=np.asarray([[-1e-3, 0.0, 1e-3], [-2e-3, 2e-3, math.nan]]),
        decision_probability=np.asarray([[0.0, 0.5, 1.0], [0.2, 0.3, math.nan]]),
        trial_count=np.asarray([[10, 10, 10], [10, 10, 0]]),
    )


def every_plot() -> dict[str, Plot]:
    """Every figure of the block, each from analyses whose numbers are known."""
    supply = metric_inputs()["supply"]
    edges = analyze_scope_edges([conversions_of(scope_wave(), 4)])
    eye = analyze_edge_eye(conversions_of(converter_wave(conversions=2), 3))
    response = analyze_response(conversions_of(converter_wave(), 3))
    figures = [
        plots.plot_metastability(metastability()),
        plots.plot_noise_cm(common_mode()),
        plots.plot_offset_cm(common_mode()),
        plots.plot_delay_supply_small(supply),
        plots.plot_delay_supply_large(supply),
        plots.plot_energy_supply(metric_inputs()["power"]),
        plots.plot_scurve(scurve()),
        plots.plot_scurve_unresolved(scurve()),
        plots.plot_offset_noise(offset_noise_of("valid")),
        plots.plot_common_mode_scurves(common_mode()),
        plots.plot_sampling_noise_scurves(sampling()),
        plots.plot_sampling_offset(sampling()),
        plots.plot_sampling_noise(sampling()),
        plots.plot_scope_eye(edges),
        plots.plot_scope_timing(edges),
        plots.plot_scope_response(edges),
        plots.plot_sr_eye(eye),
        plots.plot_xc_eye(eye),
        plots.plot_sr_timing(eye),
        plots.plot_xc_timing(eye),
        plots.plot_sr_response(response),
        plots.plot_xc_response(response),
    ]
    return {figure.name: figure for figure in figures}


FIGURES = every_plot()


def unit(label: str) -> str | None:
    """The unit an axis label ends with, in parentheses; None for a dimensionless one."""
    found = re.search(r"\(([^()]*(?:\([^()]*\))?)\)$", label)
    return found.group(1) if found else None


def marked(names, reasons: dict[str, str]):
    """Each name, those in ``reasons`` marked as the suspected bug each names."""
    return [
        pytest.param(name, marks=pytest.mark.xfail(strict=True, reason=reasons[name])) if name in reasons else name
        for name in names
    ]


PROBABILITY_LABEL = "comp-3: the S-curve's probability is labelled P(high), not Decision probability"
MEDIAN_LABEL = "comp-4: a response map's curve is the series 'Median', not a quantity in lower case"
INDEX_AXIS = "comp-5: a response map's decision axis reads 'Decision (B0 first)', a parenthesis that is no unit"


@pytest.mark.parametrize(
    "name", marked(sorted(FIGURES), dict.fromkeys(("scope_response", "sr_response", "xc_response"), INDEX_AXIS))
)
def test_every_axis_is_in_an_si_base_unit_or_dimensionless(name: str) -> None:
    """Each axis label states an unscaled SI unit as the notation writes it, or none: a ratio, a
    share, a category (the figures of categories and indices: their rows or columns named)."""
    figure = FIGURES[name]
    for label in (figure.x_label, figure.y_label):
        assert not SCALED.search(label), label
        found = unit(label)
        assert found is None or found in UNITS, label


@pytest.mark.parametrize(
    ("name", "x_label", "y_label"),
    [
        ("metastability", DIFFERENTIAL_INPUT, DELAY),
        ("noise_cm", COMMON_MODE, NOISE),
        ("offset_cm", COMMON_MODE, OFFSET),
        ("delay_supply_0p5mv", SUPPLY_RELATIVE, DELAY),
        ("delay_supply_100mv", SUPPLY_RELATIVE, DELAY),
        ("energy_supply", SUPPLY_RELATIVE, ENERGY),
        ("scurve_unresolved", DIFFERENTIAL_INPUT, UNRESOLVED),
        ("offset_noise", DIFFERENTIAL_INPUT, PROBABILITY),
        ("sampling_offset", None, OFFSET),
        ("sampling_noise", None, NOISE),
        ("common_mode_scurves", DIFFERENTIAL_INPUT, None),
        ("sampling_noise_scurves", DIFFERENTIAL_INPUT, None),
        pytest.param(
            "scurve",
            DIFFERENTIAL_INPUT,
            PROBABILITY,
            marks=pytest.mark.xfail(strict=True, reason=PROBABILITY_LABEL),
        ),
    ],
)
def test_the_records_and_the_captures_axes_are_the_notations(
    name: str, x_label: str | None, y_label: str | None
) -> None:
    figure = FIGURES[name]
    if x_label is not None:
        assert figure.x_label == x_label
    if y_label is not None:
        assert figure.y_label == y_label


@pytest.mark.parametrize(
    "name",
    marked(
        sorted(name for name, figure in FIGURES.items() if figure.series),
        {
            "scurve": PROBABILITY_LABEL,
            "offset_noise": PROBABILITY_LABEL,
            **dict.fromkeys(("scope_response", "sr_response", "xc_response"), MEDIAN_LABEL),
        },
    ),
)
def test_every_series_is_named_by_its_quantity_in_lower_case(name: str) -> None:
    """docs/references.md, composing a name: "A series label is the quantity in lower case"."""
    for label in FIGURES[name].series:
        assert label == label.lower() and re.fullmatch(r"[a-z][a-z0-9 ,\-]*", label), label


@pytest.mark.parametrize(
    "name",
    marked(
        ("common_mode_scurves", "sampling_noise_scurves"),
        dict.fromkeys(("common_mode_scurves", "sampling_noise_scurves"), PROBABILITY_LABEL),
    ),
)
def test_the_scurve_maps_colour_bar_is_the_decision_probability(name: str) -> None:
    heatmap = FIGURES[name].heatmap
    assert heatmap is not None and heatmap.label == PROBABILITY


# ---------------------------------------------------------------- the data each draws


def test_the_metastability_figure_draws_the_delay_over_the_input_on_a_log_axis() -> None:
    figure = FIGURES["metastability"]
    assert figure.x == pytest.approx([0.1e-3, 0.3e-3]) and figure.x_log
    assert figure.series == {"delay": pytest.approx([400e-12, 370e-12])}


def test_the_common_mode_figures_draw_each_valid_fit_and_nan_for_the_rest() -> None:
    """Three common modes, the middle one's curve too narrow to bracket: its noise and offset NaN."""
    fit = common_mode()
    assert fit.validity == ("valid", "unbracketed", "valid")
    for name, values in (("noise_cm", fit.noise_sigma_v), ("offset_cm", fit.offset_v)):
        figure = FIGURES[name]
        assert figure.x == pytest.approx([0.6, 0.7, 0.8])
        (series,) = figure.series.values()
        assert series[0] == pytest.approx(values[0]) and series[2] == pytest.approx(values[2])
        assert math.isnan(series[1])
    assert FIGURES["noise_cm"].series["noise"][0] == pytest.approx(0.5e-3, rel=0.05)
    assert FIGURES["offset_cm"].series["offset"][2] == pytest.approx(-0.2e-3, abs=0.05 * 0.4e-3)


def test_the_supply_figures_draw_each_corners_small_and_large_input_delay_and_energy() -> None:
    """The supply runs' inputs ascending (0.5 mV, 100 mV): the 0.5 mV delay is each corner's first
    column (350, 300, 280 ps), the 100 mV delay its last (95, 90, 85 ps)."""
    small, large, energy = FIGURES["delay_supply_0p5mv"], FIGURES["delay_supply_100mv"], FIGURES["energy_supply"]
    assert small.x == large.x == energy.x == list(SUPPLY_SWEEP)
    assert small.series == {"delay": pytest.approx([350e-12, 300e-12, 280e-12])}
    assert large.series == {"delay": pytest.approx([95e-12, 90e-12, 85e-12])}
    assert energy.series == {"energy": pytest.approx([0.5e-12, 1.0e-12])}


def test_the_scurve_figures_draw_each_inputs_probability_and_unresolved_share() -> None:
    assert FIGURES["scurve"].x == pytest.approx([-1e-3, 0.0, 1e-3])
    assert list(FIGURES["scurve"].series.values()) == [pytest.approx([0.1, 0.5, 0.9])]
    assert FIGURES["scurve_unresolved"].series == {"unresolved": pytest.approx([0.0, 0.25, 0.0])}


def test_the_offset_noise_figure_marks_the_offset_and_shades_a_sigma_either_side_where_valid() -> None:
    """Offset 0.1 mV and noise 0.4 mV: the marker at 0.1 mV, the band from -0.3 to 0.5 mV; a fit not
    valid has neither."""
    figure = FIGURES["offset_noise"]
    assert [marker.at for marker in figure.x_markers] == pytest.approx([0.1e-3])
    assert [(band.low, band.high) for band in figure.x_bands] == [pytest.approx((-0.3e-3, 0.5e-3))]
    assert list(figure.series.values()) == [pytest.approx([0.0, 0.5, 1.0])]
    invalid = plots.plot_offset_noise(offset_noise_of("non_monotonic"))
    assert invalid.x_markers == [] and invalid.x_bands == []


def test_the_scurve_map_gives_each_curve_its_own_cells() -> None:
    """Curve A at -1, 0 and +1 mV (cells cut halfway, the outer ones as far out: -1.5, -0.5, 0.5,
    1.5 mV), curve B at -2 and +2 mV (-4, 0, 4 mV): the columns cut at every edge, -4, -1.5, -0.5,
    0, 0.5, 1.5, 4 mV; A's row empty outside its cells, B's its two values each side of 0."""
    figure = FIGURES["sampling_noise_scurves"]
    heatmap = figure.heatmap
    assert heatmap is not None
    assert heatmap.x == pytest.approx([-4e-3, -1.5e-3, -0.5e-3, 0.0, 0.5e-3, 1.5e-3, 4e-3])
    assert heatmap.y == [-0.5, 0.5, 1.5]
    np.testing.assert_allclose(heatmap.z[0], [math.nan, 0.0, 0.5, 0.5, 1.0, math.nan])
    np.testing.assert_allclose(heatmap.z[1], [0.2, 0.2, 0.2, 0.3, 0.3, 0.3])
    assert figure.y_labels == ["25/75 % track", "75/25 % hold (unbracketed)"]


def test_the_sampling_figures_draw_each_curve_a_category_nan_where_not_valid() -> None:
    for name, value in (("sampling_offset", 0.1e-3), ("sampling_noise", 0.4e-3)):
        figure = FIGURES[name]
        assert figure.x == [0.0, 1.0] and figure.x_labels == ["25/75 % track", "75/25 % hold (unbracketed)"]
        (series,) = figure.series.values()
        assert series[0] == pytest.approx(value) and math.isnan(series[1])


def test_the_converter_maps_draw_their_shares_on_their_own_cells_with_the_clock_shaded() -> None:
    """Each map's z a row a voltage (or time) cell and a column a time (or decision) cell, its edges
    the analysis's; the eyes shade the clock high from each rise (4 ns), the conversions each
    decision's."""
    edges = analyze_scope_edges([conversions_of(scope_wave(), 4)])
    eye = analyze_edge_eye(conversions_of(converter_wave(conversions=2), 3))
    for name, x, y, z in (
        ("scope_eye", edges.eye_time_s, edges.voltage_v, edges.eye_share),
        ("scope_timing", edges.timing_time_s, edges.voltage_v, edges.timing_share),
        ("sr_eye", eye.eye_time_s, eye.voltage_v, eye.sr_eye),
        ("xc_eye", eye.eye_time_s, eye.voltage_v, eye.xc_eye),
        ("sr_timing", eye.timing_time_s, eye.voltage_v, eye.sr_timing),
        ("xc_timing", eye.timing_time_s, eye.voltage_v, eye.xc_timing),
    ):
        heatmap = FIGURES[name].heatmap
        assert heatmap is not None and heatmap.log
        assert heatmap.x == pytest.approx(list(x), rel=1e-5) and heatmap.y == pytest.approx(
            list(y), rel=1e-5, abs=1e-12
        )
        np.testing.assert_allclose(np.asarray(heatmap.z, dtype=float), z, rtol=1e-5)
    for name in ("scope_eye", "sr_eye", "xc_eye"):
        (band,) = FIGURES[name].x_bands
        assert (band.low, band.high) == pytest.approx((0.0, 4e-9), abs=1e-11)
    timing = FIGURES["sr_timing"].x_bands
    assert [(band.low, band.high) for band in timing] == [
        pytest.approx((k * 10e-9, k * 10e-9 + 4e-9), abs=1e-11) for k in range(3)
    ]
    assert [band.label for band in timing] == ["B0", "", ""]


def test_the_response_figures_draw_each_decisions_median_over_its_map() -> None:
    response = analyze_response(conversions_of(converter_wave(), 3))
    for name, median in (("sr_response", response.sr_median_s), ("xc_response", response.xc_median_s)):
        figure = FIGURES[name]
        assert figure.x == [0.0, 1.0, 2.0] and figure.x_ticks == "step"
        (series,) = figure.series.values()
        np.testing.assert_allclose(series, median, rtol=1e-5)
        assert figure.heatmap is not None and figure.heatmap.x == [-0.5, 0.5, 1.5, 2.5]
    none = plots.plot_sr_response(
        analyze_response(
            conversions_of(converter_wave(sr_s=(1.8e-9, 2.6e-9, 1.2e-9), targets=(False, False, False)), 3)
        )
    )
    assert none.title.endswith("none timed") and none.heatmap is None
