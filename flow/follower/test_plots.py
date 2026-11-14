"""The follower's figures from synthetic results: each Plot spec's quantity, unit and scale on
both axes (the labels in Razavi's notation) and its one curve equal to the result's
arrays; then every figure drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from flow import plot as figures
from flow.pipeline import Plot

from . import plots, runs
from .types import AnalysisCharacteristic, AnalysisImpedance, AnalysisTransfer


def transfer() -> AnalysisTransfer:
    """Three points of distinct, made-up values (the supply's three corners, or three input
    levels), the response over five frequencies differing from row to row."""
    frequency_hz = np.asarray([1e3, 1e5, 1e7, 1e9, 1e11])
    return AnalysisTransfer(
        group=None,
        index=None,
        dut=runs.source(),
        vdd_v=np.asarray([1.08, 1.2, 1.32]),
        vin_v=np.asarray([0.3, 0.6, 0.9]),
        vout_v=np.asarray([0.01, 0.25, 0.52]),
        gain_dc=np.asarray([0.2, 0.84, 0.853]),
        bandwidth_hz=np.asarray([3.1e8, 5.9e8, 6.24e8]),
        psrr_dc_db=np.asarray([12.5, 19.0, 20.0]),
        idd_a=np.asarray([2e-5, 2.1e-5, 2.2e-5]),
        frequency_hz=frequency_hz,
        gain_db=np.asarray([[-1.4, -1.4, -1.5, -4.0, -35.0], [-2.0, -2.0, -2.1, -5.0, -36.0], [-9.0] * 5]),
        cload_f=100e-15,
    )


def impedance() -> AnalysisImpedance:
    """Three points of made-up output impedances, the impedance over five frequencies row by row."""
    return AnalysisImpedance(
        group=None,
        index=None,
        dut=runs.source(),
        vin_v=np.asarray([0.3, 0.6, 0.9]),
        rout_ohm=np.asarray([9e3, 3e3, 2.44e3]),
        frequency_hz=np.asarray([1e3, 1e5, 1e7, 1e9, 1e11]),
        zout_ohm=np.asarray([[2.44e3, 2.44e3, 2.5e3, 6e3, 2e4], [1.0] * 5, [2.0] * 5]),
        cload_f=100e-15,
    )


def characteristic() -> AnalysisCharacteristic:
    """An input range from 0.45 V to 1.2 V (the three points' levels 0.6 and 0.9 V inside it, 0.3 V
    below it), over a made-up DC sweep of four steps from ground to 1.2 V."""
    return AnalysisCharacteristic(
        group=None,
        index=None,
        dut=runs.source(),
        vin_v=np.asarray([0.15, 0.45, 0.75, 1.05]),
        vout_v=np.asarray([0.0, 0.1, 0.4, 0.66]),
        gain=np.asarray([0.1, 0.8, 0.85, 0.86]),
        vin_nominal_v=0.9,
        vin_min_v=0.45,
        vin_max_v=1.2,
    )


def floats(values: np.ndarray) -> list[float]:
    return [float(value) for value in values]


# Each plot: the result it takes, its name, the x axis's label (quantity and unit) and scale, the
# y axis's, the x values and its one series (label, values) as the result holds them. Labels and
# units are the notation's: "Input level (V)", "Output (V)", "Gain (V/V)", "Gain (dB)",
# "-3 dB bandwidth (Hz)", "Output resistance (ohm)", "Output impedance (ohm)", "PSRR (dB)",
# "Frequency (Hz)", and
# "Supply (V)" for the supply sweep, its x the results' supplies; a bandwidth, an impedance and a frequency
# span decades (log), the rest are linear. Over the input level the bandwidth, the output
# resistance and the PSRR are drawn inside the input range alone (0.45 V to 1.2 V): the level
# 0.3 V below it is a gap (NaN), where the follower does not follow.
@pytest.mark.parametrize(
    ("draw", "name", "x_label", "x_log", "y_label", "y_log", "x", "series"),
    [
        pytest.param(
            lambda: plots.plot_vout_vin(characteristic()),
            "vout_vin",
            "Input level (V)",
            False,
            "Output (V)",
            False,
            lambda: floats(characteristic().vin_v),
            lambda: ("output", floats(characteristic().vout_v)),
            id="vout_vin",
        ),
        pytest.param(
            lambda: plots.plot_gain_vin(characteristic()),
            "gain_vin",
            "Input level (V)",
            False,
            "Gain (V/V)",
            False,
            lambda: floats(characteristic().vin_v),
            lambda: ("gain", floats(characteristic().gain)),
            id="gain_vin",
        ),
        pytest.param(
            lambda: plots.plot_bandwidth_vin(transfer(), characteristic()),
            "bandwidth_vin",
            "Input level (V)",
            False,
            "-3 dB bandwidth (Hz)",
            True,
            lambda: floats(transfer().vin_v),
            lambda: ("bandwidth", [math.nan, *floats(transfer().bandwidth_hz)[1:]]),
            id="bandwidth_vin",
        ),
        pytest.param(
            lambda: plots.plot_rout_vin(impedance(), characteristic()),
            "rout_vin",
            "Input level (V)",
            False,
            "Output resistance (ohm)",
            True,
            lambda: floats(impedance().vin_v),
            lambda: ("output resistance", [math.nan, *floats(impedance().rout_ohm)[1:]]),
            id="rout_vin",
        ),
        pytest.param(
            lambda: plots.plot_psrr_vin(transfer(), characteristic()),
            "psrr_vin",
            "Input level (V)",
            False,
            "PSRR (dB)",
            False,
            lambda: floats(transfer().vin_v),
            lambda: ("PSRR", [math.nan, *floats(transfer().psrr_dc_db)[1:]]),
            id="psrr_vin",
        ),
        pytest.param(
            lambda: plots.plot_gain_frequency(transfer()),
            "gain_frequency",
            "Frequency (Hz)",
            True,
            "Gain (dB)",
            False,
            lambda: floats(transfer().frequency_hz),
            lambda: ("gain", floats(transfer().gain_db[0])),
            id="gain_frequency",
        ),
        pytest.param(
            lambda: plots.plot_zout_frequency(impedance()),
            "zout_frequency",
            "Frequency (Hz)",
            True,
            "Output impedance (ohm)",
            True,
            lambda: floats(impedance().frequency_hz),
            lambda: ("output impedance", floats(impedance().zout_ohm[0])),
            id="zout_frequency",
        ),
        pytest.param(
            lambda: plots.plot_gain_supply(transfer()),
            "gain_supply",
            "Supply (V)",
            False,
            "Gain (V/V)",
            False,
            lambda: floats(transfer().vdd_v),
            lambda: ("gain", floats(transfer().gain_dc)),
            id="gain_supply",
        ),
        pytest.param(
            lambda: plots.plot_bandwidth_supply(transfer()),
            "bandwidth_supply",
            "Supply (V)",
            False,
            "-3 dB bandwidth (Hz)",
            True,
            lambda: floats(transfer().vdd_v),
            lambda: ("bandwidth", floats(transfer().bandwidth_hz)),
            id="bandwidth_supply",
        ),
        pytest.param(
            lambda: plots.plot_psrr_supply(transfer()),
            "psrr_supply",
            "Supply (V)",
            False,
            "PSRR (dB)",
            False,
            lambda: floats(transfer().vdd_v),
            lambda: ("PSRR", floats(transfer().psrr_dc_db)),
            id="psrr_supply",
        ),
    ],
)
def test_each_plot_states_its_axes_and_draws_the_result(
    draw: Callable[[], Plot],
    name: str,
    x_label: str,
    x_log: bool,
    y_label: str,
    y_log: bool,
    x: Callable[[], list[float]],
    series: Callable[[], tuple[str, list[float]]],
) -> None:
    drawn = draw()
    assert isinstance(drawn, Plot) and drawn.name == name
    assert (drawn.x_label, drawn.x_log) == (x_label, x_log)
    assert (drawn.y_label, drawn.y_log) == (y_label, y_log)
    assert drawn.x == x()
    label, values = series()
    assert list(drawn.series) == [label]
    assert drawn.series[label] == pytest.approx(values, nan_ok=True)
    assert len(drawn.x) == len(values)


def test_a_plot_of_the_lowest_frequency_says_which_in_its_title() -> None:
    """Each plot of a value at the sweep's lowest frequency (1 kHz here) names it in its title."""
    for drawn in (
        plots.plot_rout_vin(impedance(), characteristic()),
        plots.plot_psrr_vin(transfer(), characteristic()),
        plots.plot_gain_supply(transfer()),
        plots.plot_psrr_supply(transfer()),
    ):
        assert " at 1 kHz " in drawn.title, drawn.name


def test_every_figure_renders(tmp_path: Path) -> None:
    drawn = [
        plots.plot_vout_vin(characteristic()),
        plots.plot_gain_vin(characteristic()),
        plots.plot_bandwidth_vin(transfer(), characteristic()),
        plots.plot_rout_vin(impedance(), characteristic()),
        plots.plot_psrr_vin(transfer(), characteristic()),
        plots.plot_gain_frequency(transfer()),
        plots.plot_zout_frequency(impedance()),
        plots.plot_gain_supply(transfer()),
        plots.plot_bandwidth_supply(transfer()),
        plots.plot_psrr_supply(transfer()),
    ]
    assert len({plot.name for plot in drawn}) == 10
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)


def test_the_plots_over_the_input_level_shade_the_input_range() -> None:
    """Every plot over the input level shades the input range (0.45 V to 1.2 V) as a band; those
    of a follower's small-signal figures (bandwidth, output resistance, PSRR) draw a level outside
    it (0.3 V) as a gap, the levels inside it as the results hold them, and say so in the title."""
    drawn = [
        plots.plot_vout_vin(characteristic()),
        plots.plot_gain_vin(characteristic()),
        plots.plot_bandwidth_vin(transfer(), characteristic()),
        plots.plot_rout_vin(impedance(), characteristic()),
        plots.plot_psrr_vin(transfer(), characteristic()),
    ]
    for each in drawn:
        assert [(band.low, band.high) for band in each.x_bands] == [(0.45, 1.2)], each.name
    for each in drawn[2:]:
        (values,) = each.series.values()
        assert math.isnan(values[0]) and all(math.isfinite(value) for value in values[1:]), each.name
        assert "inside the input range" in each.title, each.name


def test_a_title_states_the_results_own_lowest_frequency() -> None:
    """A sweep from 10 MHz (not the bench's 1 kHz): each plot of a value at its lowest frequency
    says " at 10 MHz "; from 2.5 GHz, " at 2.5 GHz "."""
    for start_hz, said in ((1e7, " at 10 MHz "), (2.5e9, " at 2.5 GHz ")):
        frequency_hz = start_hz * np.asarray([1.0, 10.0, 100.0, 1e3, 1e4])
        swept = dataclasses.replace(transfer(), frequency_hz=frequency_hz)
        impedances = dataclasses.replace(impedance(), frequency_hz=frequency_hz)
        for drawn in (
            plots.plot_rout_vin(impedances, characteristic()),
            plots.plot_psrr_vin(swept, characteristic()),
            plots.plot_gain_supply(swept),
            plots.plot_psrr_supply(swept),
        ):
            assert said in drawn.title, drawn.name


def test_a_value_beyond_the_sweep_inside_the_range_is_a_gap() -> None:
    """A bandwidth beyond the sweep (NaN) at a level inside the input range stays a gap, the other
    levels as the result holds them: the plot draws the result, it fills nothing in."""
    beyond = dataclasses.replace(transfer(), bandwidth_hz=np.asarray([3.1e8, math.nan, 6.24e8]))
    for drawn in (plots.plot_bandwidth_vin(beyond, characteristic()), plots.plot_bandwidth_supply(beyond)):
        values = drawn.series["bandwidth"]
        assert math.isnan(values[1]) and values[2] == 6.24e8, drawn.name


def test_the_titles_state_the_source_the_load_and_the_input() -> None:
    """notation.md rule 6, the title carries the condition: the responses over frequency and the
    bandwidths and step metrics' plots name the ideal source (R_S = 0, [Razavi-Analog] Eq. (6.64),
    p. 192: Z_out's shape depends on R_S) and the 100 fF load, the responses over frequency the
    nominal input (the result's first point, 0.3 V); the supply plots where they hold the input:
    an NMOS input at its level (0.3 V, the first point's), a PMOS one at its distance below the
    supply (1.08 V - 0.3 V = 0.78 V)."""
    for drawn in (
        plots.plot_gain_frequency(transfer()),
        plots.plot_zout_frequency(impedance()),
        plots.plot_bandwidth_vin(transfer(), characteristic()),
        plots.plot_bandwidth_supply(transfer()),
    ):
        assert "from an ideal source (R_S = 0) into 100 fF" in drawn.title, drawn.name
    for drawn in (plots.plot_gain_frequency(transfer()), plots.plot_zout_frequency(impedance())):
        assert "at the nominal input, 0.3 V," in drawn.title, drawn.name
    for drawn in (plots.plot_gain_supply, plots.plot_bandwidth_supply, plots.plot_psrr_supply):
        assert "the input held at 0.3 V" in drawn(transfer()).title
        pmos = dataclasses.replace(transfer(), dut=runs.source_pmos())
        assert "the input held 0.78 V below the supply" in drawn(pmos).title


def test_the_dc_sweep_plots_span_ground_to_the_supply() -> None:
    """The characteristic and its gain are drawn over the DC sweep's own levels (here its four
    steps' middles, 0.15 V to 1.05 V of a 1.2 V sweep), not the thirteen AC levels: the curve
    bends where the DC sweep does ([Razavi-Analog] Fig. 3.34(c), p. 68)."""
    for drawn in (plots.plot_vout_vin(characteristic()), plots.plot_gain_vin(characteristic())):
        assert drawn.x == [0.15, 0.45, 0.75, 1.05], drawn.name
