"""The sampler's figures against docs/references.md's notation: each axis label as the table writes
it (``<Name> (<unit>)``, the SI base unit, the condition in the title), each series the quantity in
lower case, and each figure drawing the values of the results it is given, unscaled."""

from __future__ import annotations

import re

import numpy as np
import pytest

from . import plots
from .params import SUPPLY_SWEEP, VIN_SWEEP, Params
from .test_known_answers import track_result
from .types import AnalysisHold, AnalysisTrack

# the table's units in ASCII (docs/references.md, "Composing a name not in the table", rule 6)
LABEL = re.compile(r"^[A-Z][a-z0-9 -]*[a-z0-9] \((V|A|s|Hz|ohm|F|C|W|J|deg|dB|LSB|V/s|V/sqrt\(Hz\))\)$")


def _track(vdd_v: np.ndarray, vin_v: np.ndarray, ron_ohm: np.ndarray) -> AnalysisTrack:
    return track_result(vdd_v=vdd_v, vin_v=vin_v, ron_ohm=ron_ohm, track_error_v=np.linspace(-3e-6, 2e-6, len(vin_v)))


def _hold(vdd_v: np.ndarray, vin_v: np.ndarray) -> AnalysisHold:
    return AnalysisHold(
        group=None,
        index=None,
        dut=Params(),
        vdd_v=vdd_v,
        vin_v=vin_v,
        pedestal_v=np.linspace(-2e-3, 1e-3, len(vin_v)),
        droop_v_per_s=np.full(len(vin_v), -40.0),
        feedthrough=np.geomspace(1e-5, 1e-3, len(vin_v)) * np.where(np.arange(len(vin_v)) % 2, -1.0, 1.0),
    )


VIN = np.asarray([fraction * 1.2 for fraction in VIN_SWEEP])
RON = np.linspace(130.0, 550.0, len(VIN))
RON[-1] = np.nan  # a point that never settled
BY_VIN = (_track(np.full(len(VIN), 1.2), VIN, RON), _hold(np.full(len(VIN), 1.2), VIN))
SUPPLY_V = np.asarray([factor * 1.2 for factor in SUPPLY_SWEEP])
BY_SUPPLY = (_track(SUPPLY_V, SUPPLY_V / 2, np.asarray([600.0, 450.0, 380.0])), _hold(SUPPLY_V, SUPPLY_V / 2))


@pytest.mark.parametrize(
    ("figure", "source", "x_label", "y_label", "series", "y_log"),
    [
        (plots.plot_ron_vin, BY_VIN[0], "Input level (V)", "On-resistance (ohm)", "on-resistance", True),
        (plots.plot_track_error_vin, BY_VIN[0], "Input level (V)", "Output minus input (V)", "track error", False),
        (plots.plot_pedestal_vin, BY_VIN[1], "Input level (V)", "Pedestal (V)", "pedestal", False),
        (plots.plot_feedthrough_vin, BY_VIN[1], "Input level (V)", "Feedthrough (dB)", "feedthrough", False),
        (plots.plot_ron_supply, BY_SUPPLY[0], "Supply over nominal", "On-resistance (ohm)", "on-resistance", True),
        (plots.plot_pedestal_supply, BY_SUPPLY[1], "Supply over nominal", "Pedestal (V)", "pedestal", False),
    ],
)
def test_each_figure_labels_its_axes_as_the_notation_does(figure, source, x_label, y_label, series, y_log) -> None:
    """docs/references.md: V_in "Input level (V)", a relative supply sweep "Supply over nominal",
    R_on "On-resistance (ohm)", the track error "Output minus input (V)", the pedestal "Pedestal
    (V)", the hold-mode feedthrough "Feedthrough (dB)"; one series, the quantity in lower case; a
    resistance spanning decades on a log axis; the label never the condition, the title says it."""
    drawn = figure(source)
    assert (drawn.x_label, drawn.y_label) == (x_label, y_label)
    assert list(drawn.series) == [series]
    assert drawn.y_log is y_log and drawn.x_log is False
    assert drawn.title and drawn.name == figure.__name__.removeprefix("plot_")
    for label in (drawn.x_label, drawn.y_label):
        assert LABEL.match(label) or label == "Supply over nominal", label


@pytest.mark.parametrize(
    ("figure", "source", "values"),
    [
        (plots.plot_ron_vin, BY_VIN[0], RON),
        (plots.plot_track_error_vin, BY_VIN[0], BY_VIN[0].track_error_v),
        (plots.plot_pedestal_vin, BY_VIN[1], BY_VIN[1].pedestal_v),
        (plots.plot_feedthrough_vin, BY_VIN[1], 20 * np.log10(np.abs(BY_VIN[1].feedthrough))),
    ],
)
def test_each_input_figure_draws_its_results_over_their_input_levels(figure, source, values) -> None:
    """x the results' own V_in in volts, y their values in the base unit (ohm, V; the feedthrough
    20 log10 of its magnitude: 1e-5 is -100 dB, 1e-3 -60 dB), a point that never settled a gap."""
    drawn = figure(source)
    np.testing.assert_array_equal(drawn.x, source.vin_v)
    (series,) = drawn.series.values()
    np.testing.assert_allclose(series, values, rtol=1e-12, equal_nan=True)
    if figure is plots.plot_feedthrough_vin:
        assert series[0] == pytest.approx(-100.0) and series[-1] == pytest.approx(-60.0)


@pytest.mark.parametrize(
    ("figure", "source", "values"),
    [
        (plots.plot_ron_supply, BY_SUPPLY[0], [600.0, 450.0, 380.0]),
        (plots.plot_pedestal_supply, BY_SUPPLY[1], list(BY_SUPPLY[1].pedestal_v)),
    ],
)
def test_each_supply_figure_draws_its_results_over_the_supply_over_nominal(figure, source, values) -> None:
    """The supply's runs at 1.08, 1.2 and 1.32 V: x their V_DD over the nominal 1.2 V (0.9, 1.0,
    1.1), y their values unscaled."""
    drawn = figure(source)
    np.testing.assert_allclose(drawn.x, source.vdd_v / 1.2, rtol=1e-12)
    (series,) = drawn.series.values()
    np.testing.assert_allclose(series, values, rtol=1e-12)


@pytest.mark.xfail(strict=True, reason="samp-13: the supply figures take x from SUPPLY_SWEEP, not from their results")
@pytest.mark.parametrize("figure", [plots.plot_ron_supply, plots.plot_pedestal_supply])
def test_a_supply_figure_has_one_x_per_point_of_its_results(figure) -> None:
    """A supply analysis of two runs (90 and 110 %): two points drawn, x as long as the series."""
    vdd = np.asarray([1.08, 1.32])
    source = (
        _track(vdd, vdd / 2, np.asarray([600.0, 380.0])) if figure is plots.plot_ron_supply else _hold(vdd, vdd / 2)
    )
    drawn = figure(source)
    assert all(len(drawn.x) == len(series) == 2 for series in drawn.series.values())
