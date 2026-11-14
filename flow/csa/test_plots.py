"""The amplifier's figures, from results alone, drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flow import plot as figures

from . import plots
from .analysis import analyze_noise, analyze_pulse, analyze_supply
from .params import CHARGES_C, SUPPLY_SWEEP
from .test_analysis import noise, pulse


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
    response, density = plots.plot_pulse(result), plots.plot_noise_density(found)
    drawn = [response, *over_charge, density, *over_supply]
    assert len({plot.name for plot in drawn}) == 9
    assert all(plot.x_log and len(plot.x) == len(CHARGES_C) for plot in over_charge)
    assert all(len(plot.x) == len(SUPPLY_SWEEP) for plot in over_supply)
    # a series a charge, one sample a nanosecond of the 50 ps record
    assert list(response.series) == ["0.25 fC", "0.5 fC", "1 fC", "2 fC"]
    assert response.x[1] - response.x[0] == pytest.approx(1e-9)
    assert density.x_log and density.y_log and len(density.x) == 91
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)
