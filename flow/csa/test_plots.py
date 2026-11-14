"""The amplifier's figures, from results alone: each spec's axes (quantity, unit, scale) and curves
against results of known values, and every figure drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from flow import plot as figures
from flow.pipeline import Plot

from . import plots
from .analysis import analyze_noise, analyze_pulse, analyze_supply
from .params import CHARGES_C, SUPPLY_SWEEP
from .test_analysis import noise, pulse, pulse_result
from .types import AnalysisNoise, AnalysisSupply

RESPONSES = (plots.plot_pulse_q250, plots.plot_pulse_q500, plots.plot_pulse_q1000, plots.plot_pulse_q2000)


def test_every_figure_renders(tmp_path: Path) -> None:
    result = analyze_pulse([pulse(charge) for charge in CHARGES_C])
    found = analyze_noise([noise(1e-7)], pulse=result)
    points = [analyze_pulse([pulse(min(CHARGES_C), vdd=1.2 * factor)]) for factor in SUPPLY_SWEEP]
    supply = analyze_supply(points, noises=[analyze_noise([noise(1e-7)], pulse=point) for point in points])
    over_charge = [plots.plot_amplitude_charge(result), plots.plot_gain_charge(result), plots.plot_tot_charge(result)]
    over_supply = [
        plots.plot_gain_supply(supply),
        plots.plot_peaking_supply(supply),
        plots.plot_enc_supply(supply),
        plots.plot_power_supply(supply),
    ]
    responses = [draw(result) for draw in RESPONSES]
    density = plots.plot_noise_density(found)
    drawn = [*responses, *over_charge, density, *over_supply]
    assert len({plot.name for plot in drawn}) == 12
    assert all(plot.x_log and len(plot.x) == len(CHARGES_C) for plot in over_charge)
    assert all(len(plot.x) == len(SUPPLY_SWEEP) for plot in over_supply)
    # one curve a figure, one sample a nanosecond of the 50 ps record
    assert [plot.name for plot in responses] == ["pulse_q250", "pulse_q500", "pulse_q1000", "pulse_q2000"]
    assert all(list(plot.series) == ["output excursion"] for plot in responses)
    assert responses[0].x[1] - responses[0].x[0] == pytest.approx(1e-9)
    assert density.x_log and density.y_log and len(density.x) == 91
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)


# ---- each spec from results of known values ------------------------------------------------------

CHARGES = np.asarray(CHARGES_C)
# a response a charge on 0.25 ns steps: the figure keeps one sample a nanosecond (PULSE_STEP_S), every 4th
STEP_S = 0.25e-9
TIME_S = np.arange(41) * STEP_S
PULSE = pulse_result(
    charge_c=CHARGES,
    vdd_v=np.full(4, 1.2),
    amplitude_v=np.asarray([0.025, 0.05, 0.099, 0.196]),
    tot_s=np.asarray([20e-9, 40e-9, 60e-9, 80e-9]),
    time_s=TIME_S,
    pulse_v=np.outer(np.asarray([0.025, 0.05, 0.099, 0.196]), TIME_S / 10e-9),
)
NOISE = AnalysisNoise(
    group=None,
    index=None,
    dut=PULSE.dut,
    vout_v=np.asarray([0.5]),
    idd_a=np.asarray([4e-6]),
    noise_out_v=np.asarray([1e-3]),
    charge_gain_v_per_c=np.asarray([1e14]),
    enc_electrons=np.asarray([60.0]),
    frequency_hz=np.logspace(0, 9, 10),
    noise_out_v_per_rthz=np.logspace(-6, -8, 10)[None, :],
)
SUPPLY = AnalysisSupply(
    group=None,
    index=None,
    dut=PULSE.dut,
    vdd_v=np.asarray([1.08, 1.2, 1.32]),
    charge_gain_v_per_c=np.asarray([0.9e14, 1e14, 1.05e14]),
    peaking_time_s=np.asarray([12e-9, 10e-9, 9e-9]),
    enc_electrons=np.asarray([140.0, 125.0, 118.0]),
    power_w=np.asarray([4e-6, 5e-6, 6e-6]),
)


def axes(spec: Plot) -> tuple[str, str, str, bool, bool]:
    return spec.name, spec.x_label, spec.y_label, spec.x_log, spec.y_log


# One figure a charge, each one curve: the row of that charge, every 4th sample of the 0.25 ns steps
# (one a nanosecond, PULSE_STEP_S); a result without the charge has no such figure.
def test_a_pulse_figure_a_charge_keeps_a_sample_a_nanosecond() -> None:
    for draw, charge, row in zip(RESPONSES, CHARGES_C, PULSE.pulse_v, strict=True):
        spec = draw(PULSE)
        assert axes(spec) == (
            f"pulse_q{round(charge * 1e18)}",
            "Time from the injection (s)",
            "Output excursion (V)",
            False,
            False,
        )
        assert f"{charge * 1e15:g} fC" in spec.title
        assert spec.x == pytest.approx(TIME_S[::4])
        assert spec.series == {"output excursion": pytest.approx(row[::4])}
    with pytest.raises(ValueError, match="no response"):
        plots.plot_pulse_q2000(pulse_result(charge_c=[0.25e-15], amplitude_v=[0.025]))


@pytest.mark.parametrize(
    ("draw", "name", "y_label", "y_log", "label", "field"),
    (
        (plots.plot_amplitude_charge, "amplitude_charge", "Amplitude (V)", True, "amplitude", "amplitude_v"),
        (plots.plot_gain_charge, "gain_charge", "Charge gain (V/C)", False, "charge gain", "charge_gain_v_per_c"),
        (plots.plot_tot_charge, "tot_charge", "Time over threshold (s)", False, "time over threshold", "tot_s"),
    ),
)
def test_the_figures_over_the_charge(draw, name: str, y_label: str, y_log: bool, label: str, field: str) -> None:
    spec = draw(PULSE)
    assert axes(spec) == (name, "Injected charge (C)", y_label, True, y_log)
    assert spec.x == pytest.approx(CHARGES)
    assert spec.series == {label: pytest.approx(getattr(PULSE, field))}


def test_the_noise_density_figure() -> None:
    spec = plots.plot_noise_density(NOISE)
    assert axes(spec) == ("noise_density", "Frequency (Hz)", "Output noise (V/sqrt(Hz))", True, True)
    assert spec.x == pytest.approx(NOISE.frequency_hz)
    assert spec.series == {"output noise": pytest.approx(NOISE.noise_out_v_per_rthz[0])}


@pytest.mark.parametrize(
    ("draw", "name", "y_label", "label", "field"),
    (
        (plots.plot_gain_supply, "gain_supply", "Charge gain (V/C)", "charge gain", "charge_gain_v_per_c"),
        (plots.plot_peaking_supply, "peaking_supply", "Peaking time (s)", "peaking time", "peaking_time_s"),
        (plots.plot_enc_supply, "enc_supply", "ENC (electrons)", "ENC", "enc_electrons"),
        (plots.plot_power_supply, "power_supply", "Power (W)", "power", "power_w"),
    ),
)
def test_the_figures_over_the_supply(draw, name: str, y_label: str, label: str, field: str) -> None:
    # the supplies 1.08, 1.2 and 1.32 V, on x as they are
    spec = draw(SUPPLY)
    assert axes(spec) == (name, "Supply (V)", y_label, False, False)
    assert spec.x == pytest.approx(SUPPLY.vdd_v)
    assert spec.series == {label: pytest.approx(getattr(SUPPLY, field))}


# A supply sweep of two points (the nominal 1.2 V and 1.32 V, as analyze_supply takes any number of
# pulse results): each curve has a point a supply, at that supply's place on the axis (the second
# 1.1 times the first).
def test_a_supply_figure_follows_the_result_s_supplies() -> None:
    two = AnalysisSupply(
        group=None,
        index=None,
        dut=PULSE.dut,
        vdd_v=np.asarray([1.2, 1.32]),
        charge_gain_v_per_c=np.asarray([1e14, 1.05e14]),
        peaking_time_s=np.asarray([10e-9, 9e-9]),
        enc_electrons=np.asarray([125.0, 118.0]),
        power_w=np.asarray([5e-6, 6e-6]),
    )
    for draw in (plots.plot_gain_supply, plots.plot_peaking_supply, plots.plot_enc_supply, plots.plot_power_supply):
        spec = draw(two)
        assert all(len(curve) == len(spec.x) for curve in spec.series.values())
        assert spec.x[1] / spec.x[0] == pytest.approx(1.1)
