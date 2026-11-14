"""The amplifier's figures, from results alone, drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from pathlib import Path

from flow import plot as figures

from . import plots
from .analysis import analyze_ac, analyze_distortion, analyze_noise, analyze_slew
from .params import SUPPLY_SWEEP, TbParams
from .test_analysis import sine_run, step_run, two_pole


def test_every_figure_renders(tmp_path: Path) -> None:
    runs = [
        two_pole(
            100.0 * factor, 1e6, 1e9, tb=TbParams(vdd=1.2 * factor, vin_cm_v=vin_cm), noise_v_per_rthz=10e-9 * factor
        )
        for vin_cm, factor in zip((0.4, 0.6, 0.8), SUPPLY_SWEEP, strict=True)
    ]
    ac = analyze_ac(runs)
    noise = analyze_noise(runs, ac=ac)
    slew, distortion = analyze_slew([step_run(1e9, 2e8)]), analyze_distortion([sine_run(0.01)])
    over_frequency = [
        plots.plot_gain(ac),
        plots.plot_phase(ac),
        plots.plot_psrr(ac),
        plots.plot_cmrr(ac),
        plots.plot_noise_density(noise),
    ]
    over_conditions = [
        plots.plot_gain_cm(ac),
        plots.plot_unity_gain_bandwidth_cm(ac),
        plots.plot_noise_in_1mhz_cm(noise),
        plots.plot_noise_in_cm(noise),
        plots.plot_gain_supply(ac),
        plots.plot_unity_gain_bandwidth_supply(ac),
        plots.plot_power_supply(ac),
    ]
    unity_gain = [plots.plot_step_response(slew), plots.plot_spectrum(distortion)]
    drawn = [*over_frequency, *over_conditions, *unity_gain]
    assert len({plot.name for plot in drawn}) == 14
    assert all(plot.x_log and len(plot.x) == len(ac.frequency_hz) for plot in over_frequency)
    assert all(len(plot.x) == len(SUPPLY_SWEEP) for plot in over_conditions)
    assert all(len(values) == len(plot.x) for plot in drawn for values in plot.series.values())
    paths = [path for plot in drawn for path in figures.render(plot, tmp_path / plot.name)]
    assert paths and all(path.exists() for path in paths)
