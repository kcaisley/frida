"""The chain's figures (``flow.delay.plots``) from synthetic results of known values: each spec's
name, axes (quantity, unit, scale) and its one curve, the result's array over the sweep it was
measured on; and every figure drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from flow import plot as figures
from flow.pipeline import Marker, Plot

from . import plots, runs
from .params import CONTROL_SWEEP, SUPPLY_SWEEP, Oscillation
from .types import AnalysisOscillation, AnalysisPropagation

SUPPLIES = np.array([1.08, 1.2, 1.32])
CONTROLS = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2])


def oscillation(
    vdd_v: np.ndarray, vcont_v: np.ndarray, frequency_hz: np.ndarray, idd_a: np.ndarray
) -> AnalysisOscillation:
    """A five-stage ring's result at the given points (swing 1.2 V, duty cycle 0.5 at 1 GHz and
    0.1 more a GHz, 0.5 + 1e-10 s (f - 1 GHz))."""
    count = len(vdd_v)
    return AnalysisOscillation(
        group=None,
        index=None,
        dut=runs.ring5_starved(),
        vdd_v=vdd_v,
        vcont_v=vcont_v,
        oscillation_frequency_hz=frequency_hz,
        idd_a=idd_a,
        swing_v=np.full(count, 1.2),
        duty_cycle=0.5 + 1e-10 * (frequency_hz - 1e9),
        oscillation=tuple(Oscillation.TIMED if np.isfinite(f) else Oscillation.STOPPED for f in frequency_hz),
    )


def propagation(
    vdd_v: np.ndarray, vcont_v: np.ndarray, rise_s: np.ndarray, fall_s: np.ndarray, idd_a: np.ndarray
) -> AnalysisPropagation:
    """A four-stage line's result at the given points: delays ``rise_s`` and ``fall_s`` to the rising
    and falling output, its transitions 1.1 and 0.7 times them, a 4 ns input clock."""
    count = len(vdd_v)
    return AnalysisPropagation(
        group=None,
        index=None,
        dut=runs.chain4_starved(),
        vdd_v=vdd_v,
        vcont_v=vcont_v,
        clock_period_s=np.full(count, 4e-9),
        delay_rise_s=rise_s,
        delay_fall_s=fall_s,
        rise_time_s=1.1 * rise_s,
        fall_time_s=0.7 * fall_s,
        idd_a=idd_a,
        valid=np.isfinite(rise_s),
    )


# Over the supply (control 0.8 V): a ring at 0.8, 1.0 and 1.25 GHz drawing 40, 50 and 62.5 uA; a line
# with delays 60, 50, 40 ps (rising output) and 54, 45, 36 ps (falling) drawing 10, 12 and 14 uA.
RING_SUPPLY = oscillation(SUPPLIES, np.full(3, 0.8), np.array([0.8e9, 1e9, 1.25e9]), np.array([40e-6, 50e-6, 62.5e-6]))
LINE_SUPPLY = propagation(
    SUPPLIES,
    np.full(3, 0.8),
    np.array([60e-12, 50e-12, 40e-12]),
    np.array([54e-12, 45e-12, 36e-12]),
    np.array([10e-6, 12e-6, 14e-6]),
)
# Over the control (1.2 V supply): a ring at f = 1 GHz + 2 GHz/V (V_cont - 0.8 V), its gain 2 GHz/V at
# every point (a line's slope, exact for any difference), drawing 50 uA; a line with its delays
# 50 ps / (V_cont / 0.8 V), the falling 0.9 of it, drawing 12 uA; a NaN where the 0.5 V point failed.
RING_CONTROL = oscillation(np.full(8, 1.2), CONTROLS, 1e9 + 2e9 * (CONTROLS - 0.8), np.full(8, 50e-6))
DELAYS_S = 50e-12 * 0.8 / CONTROLS
DELAYS_S[0] = math.nan
LINE_CONTROL = propagation(np.full(8, 1.2), CONTROLS, DELAYS_S, 0.9 * DELAYS_S, np.full(8, 12e-6))


def assert_axes(plot: Plot, name: str, x_label: str, y_label: str, *, y_log: bool = False) -> list[float]:
    """The spec's name and axes, its x linear and its y as given; its one curve's values."""
    assert plot.name == name
    assert (plot.x_label, plot.y_label) == (x_label, y_label)
    assert (plot.x_log, plot.y_log) == (False, y_log)
    (values,) = plot.series.values()
    assert len(values) == len(plot.x)
    return values


def same(values: list[float], expected: np.ndarray | list[float]) -> bool:
    """Equal values, NaN where the expectation is NaN."""
    return np.allclose(np.asarray(values, dtype=float), np.asarray(expected, dtype=float), rtol=1e-12, equal_nan=True)


# The supply plots: x the supply over its nominal (notation: "Supply over nominal", the ratio), the
# result's supplies 1.08, 1.2 and 1.32 V over 1.2 V, so SUPPLY_SWEEP itself. The curves: the ring's
# frequency as measured; its stage delay 1 / (2 * 5 * f) = 125, 100, 80 ps ([Razavi-PLL] Sec. 3.3.2,
# p. 74); its energy a cycle V_DD I_DD / f = 54, 60, 66 fJ ([Baker] Eq. (11.15), p. 355); the line's
# delays as measured, its stage delay (t_PLH + t_PHL) / (2 * 4) = 14.25, 11.875, 9.5 ps, and its
# energy an input cycle V_DD I_DD T = 43.2, 57.6, 73.92 fJ; the ring's duty cycle as measured, 0.48,
# 0.5, 0.525 ([Razavi-PLL] Sec. 11.10, p. 365). Every axis linear, in SI units; no point unmarked.
def test_the_supply_plots() -> None:
    assert list(SUPPLY_SWEEP) == pytest.approx((SUPPLIES / SUPPLIES[1]).tolist())
    cases: list[tuple[Callable[..., Plot], object, str, str, list[float]]] = [
        (
            plots.plot_oscillation_frequency_supply,
            RING_SUPPLY,
            "oscillation_frequency_supply",
            "Oscillation frequency (Hz)",
            [0.8e9, 1e9, 1.25e9],
        ),
        (plots.plot_delay_rise_supply, LINE_SUPPLY, "delay_rise_supply", "Delay (s)", [60e-12, 50e-12, 40e-12]),
        (plots.plot_delay_fall_supply, LINE_SUPPLY, "delay_fall_supply", "Delay (s)", [54e-12, 45e-12, 36e-12]),
        (
            plots.plot_stage_delay_supply,
            RING_SUPPLY,
            "stage_delay_supply",
            "Stage delay (s)",
            [125e-12, 100e-12, 80e-12],
        ),
        (
            plots.plot_stage_delay_supply,
            LINE_SUPPLY,
            "stage_delay_supply",
            "Stage delay (s)",
            [14.25e-12, 11.875e-12, 9.5e-12],
        ),
        (plots.plot_energy_supply, RING_SUPPLY, "energy_supply", "Energy per cycle (J)", [54e-15, 60e-15, 66e-15]),
        (
            plots.plot_energy_supply,
            LINE_SUPPLY,
            "energy_supply",
            "Energy per cycle (J)",
            [43.2e-15, 57.6e-15, 73.92e-15],
        ),
        (plots.plot_duty_cycle_supply, RING_SUPPLY, "duty_cycle_supply", "Duty cycle", [0.48, 0.5, 0.525]),
    ]
    for function, result, name, y_label, expected in cases:
        spec = function(result)
        values = assert_axes(spec, name, "Supply over nominal", y_label)
        assert spec.x == list(SUPPLY_SWEEP)
        assert same(values, expected), name
        assert spec.x_markers == [], name


# The control plots: x the control voltage in volts, the result's own points (0.5 to 1.2 V). The
# curves: the ring's frequency as measured, its gain 2 GHz/V everywhere ([Razavi-PLL] Sec. 1.6, p.
# 27: K_VCO, the frequency's slope over the control; any difference of a line is its slope), its
# energy a cycle 1.2 V * 50 uA / f, its duty cycle 0.5 + 0.2 V^-1 (V_cont - 0.8 V); the line's
# delays and transitions as measured (NaN where its point failed), all four on one log axis (they
# span several times over a starved control), and its energy an input cycle 1.2 V * 12 uA * 4 ns =
# 57.6 fJ.
def test_the_control_plots() -> None:
    frequency = 1e9 + 2e9 * (CONTROLS - 0.8)
    cases: list[tuple[Callable[..., Plot], object, str, str, np.ndarray, bool]] = [
        (
            plots.plot_oscillation_frequency_control,
            RING_CONTROL,
            "oscillation_frequency_control",
            "Oscillation frequency (Hz)",
            frequency,
            False,
        ),
        (plots.plot_kvco_control, RING_CONTROL, "kvco_control", "VCO gain (Hz/V)", np.full(8, 2e9), False),
        (plots.plot_delay_rise_control, LINE_CONTROL, "delay_rise_control", "Delay (s)", DELAYS_S, True),
        (plots.plot_delay_fall_control, LINE_CONTROL, "delay_fall_control", "Delay (s)", 0.9 * DELAYS_S, True),
        (plots.plot_rise_time_control, LINE_CONTROL, "rise_time_control", "Rise time (s)", 1.1 * DELAYS_S, True),
        (plots.plot_fall_time_control, LINE_CONTROL, "fall_time_control", "Fall time (s)", 0.63 * DELAYS_S, True),
        (
            plots.plot_duty_cycle_control,
            RING_CONTROL,
            "duty_cycle_control",
            "Duty cycle",
            0.5 + 0.2 * (CONTROLS - 0.8),
            False,
        ),
        (
            plots.plot_energy_control,
            RING_CONTROL,
            "energy_control",
            "Energy per cycle (J)",
            1.2 * 50e-6 / frequency,
            False,
        ),
        (
            plots.plot_energy_control,
            LINE_CONTROL,
            "energy_control",
            "Energy per cycle (J)",
            np.full(8, 57.6e-15),
            False,
        ),
    ]
    for function, result, name, y_label, expected, y_log in cases:
        spec = function(result)
        values = assert_axes(spec, name, "Control voltage (V)", y_label, y_log=y_log)
        assert spec.x == pytest.approx(CONTROLS.tolist())
        assert same(values, expected), name
    assert len(CONTROLS) == len(CONTROL_SWEEP)


def test_every_figure_renders(tmp_path: Path) -> None:
    drawn = [
        plots.plot_oscillation_frequency_supply(RING_SUPPLY),
        plots.plot_delay_rise_supply(LINE_SUPPLY),
        plots.plot_delay_fall_supply(LINE_SUPPLY),
        plots.plot_stage_delay_supply(RING_SUPPLY),
        plots.plot_stage_delay_supply(LINE_SUPPLY),
        plots.plot_energy_supply(RING_SUPPLY),
        plots.plot_energy_supply(LINE_SUPPLY),
        plots.plot_duty_cycle_supply(RING_SUPPLY),
        plots.plot_duty_cycle_control(RING_CONTROL),
        plots.plot_oscillation_frequency_control(RING_CONTROL),
        plots.plot_kvco_control(RING_CONTROL),
        plots.plot_delay_rise_control(LINE_CONTROL),
        plots.plot_delay_fall_control(LINE_CONTROL),
        plots.plot_rise_time_control(LINE_CONTROL),
        plots.plot_fall_time_control(LINE_CONTROL),
        plots.plot_energy_control(RING_CONTROL),
        plots.plot_energy_control(LINE_CONTROL),
    ]
    # every figure of the module is drawn here, each under its own name
    defined = {name.removeprefix("plot_") for name in vars(plots) if name.startswith("plot_")}
    assert {plot.name for plot in drawn} == defined
    for k, plot in enumerate(drawn):
        paths = figures.render(plot, tmp_path / f"{plot.name}_{k}")
        assert paths and all(path.exists() for path in paths)


# Each title states its condition (notation rule 6): a supply plot the nominal supply in volts (the
# result's 1.2 V at SUPPLY_SWEEP's 1.0) and the control it was measured at, where the chain has one
# (the controlled test chains at 0.8 V; a plain ring none), a control plot the supply it was measured
# at (1.2 V); an energy plot that the bias is excluded, a line's energy per input cycle over either
# sweep; the VCO gain is named as its axis is ([Razavi-PLL] Sec. 1.6, p. 27: K_VCO, the "gain" of
# the VCO).
def test_the_titles_state_their_condition() -> None:
    supply = [
        plots.plot_oscillation_frequency_supply(RING_SUPPLY),
        plots.plot_delay_rise_supply(LINE_SUPPLY),
        plots.plot_delay_fall_supply(LINE_SUPPLY),
        plots.plot_stage_delay_supply(RING_SUPPLY),
        plots.plot_stage_delay_supply(LINE_SUPPLY),
        plots.plot_energy_supply(RING_SUPPLY),
        plots.plot_energy_supply(LINE_SUPPLY),
        plots.plot_duty_cycle_supply(RING_SUPPLY),
    ]
    assert all(spec.title.endswith("(nominal 1.2 V, control 0.8 V)") for spec in supply)
    plain = replace(RING_SUPPLY, dut=runs.ring5())
    for function in (
        plots.plot_oscillation_frequency_supply,
        plots.plot_stage_delay_supply,
        plots.plot_energy_supply,
        plots.plot_duty_cycle_supply,
    ):
        assert function(plain).title.endswith("over the supply (nominal 1.2 V)") or function(plain).title.endswith(
            "over the supply, bias excluded (nominal 1.2 V)"
        )
    assert plots.plot_stage_delay_supply(RING_SUPPLY).title.startswith("Mean stage delay")
    assert plots.plot_energy_supply(LINE_SUPPLY).title.startswith("Energy per input cycle")
    assert plots.plot_energy_supply(RING_SUPPLY).title == (
        "Energy per cycle over the supply, bias excluded (nominal 1.2 V, control 0.8 V)"
    )
    assert plots.plot_energy_control(LINE_CONTROL).title == (
        "Energy per input cycle over the control, bias excluded (supply 1.2 V)"
    )
    assert (
        plots.plot_energy_control(RING_CONTROL).title
        == "Energy per cycle over the control, bias excluded (supply 1.2 V)"
    )
    assert plots.plot_kvco_control(RING_CONTROL).title == "VCO gain over the control (supply 1.2 V)"
    control = [
        plots.plot_oscillation_frequency_control(RING_CONTROL),
        plots.plot_duty_cycle_control(RING_CONTROL),
        plots.plot_delay_rise_control(LINE_CONTROL),
        plots.plot_delay_fall_control(LINE_CONTROL),
        plots.plot_rise_time_control(LINE_CONTROL),
        plots.plot_fall_time_control(LINE_CONTROL),
    ]
    assert all(spec.title.endswith("over the control (supply 1.2 V)") for spec in control)
    # the nominal supply measured, not the PDK's: a supply sweep about 1 V says 1 V
    lower = replace(RING_SUPPLY, vdd_v=np.array([0.9, 1.0, 1.1]))
    assert plots.plot_oscillation_frequency_supply(lower).title.endswith("(nominal 1 V, control 0.8 V)")
    # the supply measured, not the PDK's: a control sweep run at 1 V says 1 V
    low = replace(RING_CONTROL, vdd_v=np.full(8, 1.0))
    assert plots.plot_oscillation_frequency_control(low).title == "Ring frequency over the control (supply 1 V)"


# A point whose drawn value is missing is a gap in its curve, so each is marked at its x, and only
# those: a ring's by its state (stopped at 110 % of the supply, slow at 0.5 V of the control, every
# quantity NaN there as analyze_oscillation leaves it), a line's as not timed where its drawn quantity
# is NaN (LINE_CONTROL's 0.5 V delays and transitions). A line's energy at that point is finite (its
# current was found), so it is drawn and not marked; and a line's point that is not valid but whose
# delays were found (an output transition missing) is drawn, unmarked, on the delay plots.
def test_the_points_not_timed_are_marked(tmp_path: Path) -> None:
    stopped = replace(
        RING_SUPPLY,
        oscillation_frequency_hz=np.array([0.8e9, 1e9, np.nan]),
        duty_cycle=np.array([0.48, 0.5, np.nan]),
        oscillation=(Oscillation.TIMED, Oscillation.TIMED, Oscillation.STOPPED),
    )
    for function in (
        plots.plot_oscillation_frequency_supply,
        plots.plot_stage_delay_supply,
        plots.plot_energy_supply,
        plots.plot_duty_cycle_supply,
    ):
        assert function(stopped).x_markers == [Marker(SUPPLY_SWEEP[2], "stopped")]
    nan_at_first = np.r_[np.nan, np.ones(7)]
    slow = replace(
        RING_CONTROL,
        oscillation_frequency_hz=RING_CONTROL.oscillation_frequency_hz * nan_at_first,
        duty_cycle=RING_CONTROL.duty_cycle * nan_at_first,
        oscillation=(Oscillation.SLOW,) + (Oscillation.TIMED,) * 7,
    )
    for function in (plots.plot_oscillation_frequency_control, plots.plot_kvco_control, plots.plot_duty_cycle_control):
        assert function(slow).x_markers == [Marker(0.5, "slow")]
    for function in (
        plots.plot_delay_rise_control,
        plots.plot_delay_fall_control,
        plots.plot_rise_time_control,
        plots.plot_fall_time_control,
    ):
        assert function(LINE_CONTROL).x_markers == [Marker(0.5, "not timed")]
    assert plots.plot_energy_control(LINE_CONTROL).x_markers == []
    transitionless = replace(
        LINE_SUPPLY, rise_time_s=np.array([np.nan, 55e-12, 44e-12]), valid=np.array([False, True, True])
    )
    for function in (plots.plot_delay_rise_supply, plots.plot_delay_fall_supply, plots.plot_stage_delay_supply):
        spec = function(transitionless)
        assert spec.x_markers == [] and all(math.isfinite(value) for value in next(iter(spec.series.values())))
    # drawn with its marker and its curve's gap
    paths = figures.render(plots.plot_oscillation_frequency_supply(stopped), tmp_path / "stopped")
    assert paths and all(path.exists() for path in paths)
