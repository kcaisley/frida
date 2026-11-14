"""The amplifier's figures, each a ``Plot`` spec from synthetic analysis results whose every row
and point differs: the quantity, unit, scale and label of each axis (``notation.md``'s, Razavi's
names), curves equal to the result's arrays, titles and markers from the results alone; then all
fifteen drawn by matplotlib (``flow.plot.render``)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from flow import plot as figures
from flow.pipeline import Band, Marker, Plot

from . import plots
from .params import CM_SWEEP, SPECTRUM_FLOOR_DB, SUPPLY_SWEEP, Params
from .types import AnalysisAc, AnalysisDistortion, AnalysisNoise, AnalysisRange, AnalysisSlew


def frequency_hz() -> np.ndarray:
    """The small-signal sweep: 1 kHz to 100 GHz, twenty points a decade."""
    return np.logspace(3, 11, 161)


def ac(vdd_v: np.ndarray, vin_cm_v: np.ndarray) -> AnalysisAc:
    """An AC result over the given points, every array distinct by point and frequency (random,
    seeded), the last point's low-frequency gain lost (NaN) as a point whose feedback saturates reads."""
    rng = np.random.default_rng(3)
    points, columns = len(vdd_v), len(frequency_hz())
    gain_dc_db = rng.uniform(20.0, 40.0, points)
    gain_dc_db[-1] = np.nan
    return AnalysisAc(
        group=None,
        index=None,
        dut=Params(),
        vdd_v=vdd_v,
        vin_cm_v=vin_cm_v,
        frequency_hz=frequency_hz(),
        gain_db=rng.uniform(-40.0, 40.0, (points, columns)),
        phase_deg=rng.uniform(-270.0, 0.0, (points, columns)),
        gain_dc_db=gain_dc_db,
        unity_gain_bandwidth_hz=rng.uniform(1e8, 1e9, points),
        phase_margin_deg=rng.uniform(45.0, 90.0, points),
        bandwidth_hz=rng.uniform(1e6, 1e7, points),
        gbw_hz=rng.uniform(1e8, 1e9, points),
        gain_margin_db=rng.uniform(5.0, 20.0, points),
        psrr_db=rng.uniform(0.0, 80.0, (points, columns)),
        cmrr_db=rng.uniform(0.0, 80.0, (points, columns)),
        psrr_dc_db=rng.uniform(20.0, 60.0, points),
        cmrr_dc_db=rng.uniform(30.0, 80.0, points),
        idd_a=rng.uniform(20e-6, 60e-6, points),
        iss_a=rng.uniform(20e-6, 60e-6, points),
        vout_v=rng.uniform(0.5, 0.7, points),
        vout_cm_v=np.full(points, np.nan),
        saturation_margin_v=rng.uniform(-0.1, 0.2, points),
        saturation_margin_pair_v=rng.uniform(-0.1, 0.2, points),
    )


def nominal() -> AnalysisAc:
    """One point at 0.71 V and 1.2 V."""
    return ac(np.asarray([1.2]), np.asarray([0.71]))


def by_cm() -> AnalysisAc:
    """Over CM_SWEEP's thirteen common modes at 1.2 V."""
    return ac(np.full(len(CM_SWEEP), 1.2), np.asarray(CM_SWEEP) * 1.2)


def by_supply() -> AnalysisAc:
    """Over SUPPLY_SWEEP's supplies of a 1.2 V nominal, each at its own common mode."""
    vdd_v = np.asarray(SUPPLY_SWEEP) * 1.2
    return ac(vdd_v, vdd_v / 2)


def span() -> AnalysisRange:
    """An input common-mode range of 0.62 V to 1.05 V at 1.2 V."""
    return AnalysisRange(
        group=None,
        index=None,
        dut=Params(),
        vdd_v=1.2,
        vin_cm_v=0.71,
        vin_cm_min_v=0.62,
        vin_cm_max_v=1.05,
        vin_cm_range_v=0.43,
    )


def noise(result: AnalysisAc) -> AnalysisNoise:
    """A noise result of ``result``'s points, every array distinct (random, seeded)."""
    rng = np.random.default_rng(5)
    points = len(result.vdd_v)
    return AnalysisNoise(
        group=None,
        index=None,
        dut=Params(),
        vdd_v=result.vdd_v,
        vin_cm_v=result.vin_cm_v,
        frequency_hz=result.frequency_hz,
        noise_out_v_per_rthz=rng.uniform(5e-8, 50e-8, (points, len(result.frequency_hz))),
        noise_in_v_per_rthz=rng.uniform(5e-9, 50e-9, (points, len(result.frequency_hz))),
        spot_frequency_hz=1e6,
        noise_in_1mhz_v_per_rthz=rng.uniform(5e-9, 50e-9, points),
        noise_out_v=rng.uniform(1e-3, 5e-3, points),
        noise_in_v=rng.uniform(100e-6, 500e-6, points),
    )


def slew() -> AnalysisSlew:
    """A step result of two points on a non-uniform axis, each output distinct."""
    time_s = np.sort(np.random.default_rng(9).uniform(0.0, 20e-9, 400))
    two = np.asarray([1.0, 2.0])
    return AnalysisSlew(
        group=None,
        index=None,
        dut=Params(),
        vin_low_v=0.7 * two,
        vin_high_v=0.9 * two,
        vin_rise_s=5.005e-9 * two,
        vin_fall_s=15.005e-9 * two,
        vout_low_v=0.46 * two,
        vout_high_v=0.74 * two,
        slew_rate_rise_v_per_s=0.6e9 * two,
        slew_rate_fall_v_per_s=-0.25e9 * two,
        settling_rise_s=0.5e-9 * two,
        settling_fall_s=1.1e-9 * two,
        overshoot_rise=0.01 * two,
        overshoot_fall=0.02 * two,
        idd_a=30e-6 * two,
        time_s=time_s,
        vout_v=np.vstack([0.6 + 0.1 * np.sin(time_s / 3e-9), 0.6 + 0.1 * np.cos(time_s / 3e-9)]),
    )


def distortion() -> AnalysisDistortion:
    """A sine result of two points, its spectrum from DC to the 5 GHz Nyquist frequency."""
    frequency = np.fft.rfftfreq(8000, d=100e-12)
    rng = np.random.default_rng(11)
    two = np.asarray([1.0, 2.0])
    return AnalysisDistortion(
        group=None,
        index=None,
        dut=Params(),
        vin_cm_v=0.76 * two,
        vin_amplitude_v=0.06 * two,
        vin_frequency_hz=10e6 * two,
        thd_db=-40.0 * two,
        sndr_db=40.0 * two,
        gain=0.9 * two,
        frequency_hz=frequency,
        spectrum_db=rng.uniform(-250.0, 0.0, (2, len(frequency))),
    )


def expected() -> dict[str, tuple[Callable[[], Plot], str, str, bool, bool, np.ndarray, dict[str, np.ndarray]]]:
    """Each figure by name: how to draw it from the synthetic results, its x and y labels (the
    quantity and its SI unit, notation.md), whether each axis is logarithmic, and its x and curves as
    the results hold them: over frequency at the result's first point, over the common mode at each
    of its points, over the supply at each supply, the step over time and the spectrum above DC to
    the seventh harmonic (75 MHz), clipped at its floor."""
    point, cm, supply, band = nominal(), by_cm(), by_supply(), span()
    point_noise, cm_noise = noise(point), noise(cm)
    step, sine = slew(), distortion()
    frequency = point.frequency_hz
    shown = (sine.frequency_hz > 0) & (sine.frequency_hz <= 75e6)
    return {
        "gain": (
            lambda: plots.plot_gain(point),
            "Frequency (Hz)",
            "Gain (dB)",
            True,
            False,
            frequency,
            {"gain": point.gain_db[0]},
        ),
        "phase": (
            lambda: plots.plot_phase(point),
            "Frequency (Hz)",
            "Phase (deg)",
            True,
            False,
            frequency,
            {"phase": point.phase_deg[0]},
        ),
        "psrr": (
            lambda: plots.plot_psrr(point),
            "Frequency (Hz)",
            "PSRR (dB)",
            True,
            False,
            frequency,
            {"PSRR": point.psrr_db[0]},
        ),
        "cmrr": (
            lambda: plots.plot_cmrr(point),
            "Frequency (Hz)",
            "CMRR (dB)",
            True,
            False,
            frequency,
            {"CMRR": point.cmrr_db[0]},
        ),
        "noise_density": (
            lambda: plots.plot_noise_density(point_noise),
            "Frequency (Hz)",
            "Input-referred noise (V/sqrt(Hz))",
            True,
            True,
            frequency,
            {"input-referred noise": point_noise.noise_in_v_per_rthz[0]},
        ),
        "gain_cm": (
            lambda: plots.plot_gain_cm(cm, band),
            "Input common mode (V)",
            "Low-frequency gain (dB)",
            False,
            False,
            cm.vin_cm_v,
            {"low-frequency gain": cm.gain_dc_db},
        ),
        "saturation_margin_cm": (
            lambda: plots.plot_saturation_margin_cm(cm, band),
            "Input common mode (V)",
            "Drain-source voltage less saturation voltage (V)",
            False,
            False,
            cm.vin_cm_v,
            {"saturation margin": cm.saturation_margin_pair_v},
        ),
        "unity_gain_bandwidth_cm": (
            lambda: plots.plot_unity_gain_bandwidth_cm(cm, band),
            "Input common mode (V)",
            "Unity-gain bandwidth (Hz)",
            False,
            True,
            cm.vin_cm_v,
            {"unity-gain bandwidth": cm.unity_gain_bandwidth_hz},
        ),
        "noise_in_1mhz_cm": (
            lambda: plots.plot_noise_in_1mhz_cm(cm_noise, band),
            "Input common mode (V)",
            "Input-referred noise (V/sqrt(Hz))",
            False,
            True,
            cm_noise.vin_cm_v,
            {"input-referred noise": cm_noise.noise_in_1mhz_v_per_rthz},
        ),
        "noise_in_cm": (
            lambda: plots.plot_noise_in_cm(cm_noise, band),
            "Input common mode (V)",
            "Input-referred noise (V)",
            False,
            False,
            cm_noise.vin_cm_v,
            {"input-referred noise": cm_noise.noise_in_v},
        ),
        "gain_supply": (
            lambda: plots.plot_gain_supply(supply),
            "Supply (V)",
            "Low-frequency gain (dB)",
            False,
            False,
            supply.vdd_v,
            {"low-frequency gain": supply.gain_dc_db},
        ),
        "unity_gain_bandwidth_supply": (
            lambda: plots.plot_unity_gain_bandwidth_supply(supply),
            "Supply (V)",
            "Unity-gain bandwidth (Hz)",
            False,
            False,
            supply.vdd_v,
            {"unity-gain bandwidth": supply.unity_gain_bandwidth_hz},
        ),
        "power_supply": (
            lambda: plots.plot_power_supply(supply),
            "Supply (V)",
            "Power (W)",
            False,
            False,
            supply.vdd_v,
            # [Baker] Sec. 24.1, p. 805: power dissipation, VDD x IDD
            {"power": supply.vdd_v * supply.idd_a},
        ),
        "step_response": (
            lambda: plots.plot_step_response(step),
            "Time (s)",
            "Output (V)",
            False,
            False,
            step.time_s,
            {"output": step.vout_v[0]},
        ),
        "spectrum": (
            lambda: plots.plot_spectrum(sine),
            "Frequency (Hz)",
            "Output over the input amplitude (dB)",
            False,
            False,
            sine.frequency_hz[shown],
            {"output": np.maximum(sine.spectrum_db[0][shown], SPECTRUM_FLOOR_DB)},
        ),
    }


@pytest.mark.parametrize("name", list(expected()))
def test_each_figure_has_its_axes_and_the_results_curves(name: str) -> None:
    draw, x_label, y_label, x_log, y_log, x, series = expected()[name]
    figure = draw()
    assert figure.name == name
    assert (figure.x_label, figure.y_label) == (x_label, y_label)
    assert (figure.x_log, figure.y_log) == (x_log, y_log)
    np.testing.assert_allclose(figure.x, x, rtol=1e-12)
    assert set(figure.series) == set(series)
    for label, values in series.items():
        # NaN where a point lost its output (the last common mode's and supply's gain)
        np.testing.assert_array_equal(figure.series[label], values)


# Each figure marks what the analysis read on it: the -3 dB and unity-gain bandwidths on the gain
# ([Razavi-Analog] Fig. 6.43, p. 204), -180 deg and the unity-gain bandwidth labelled with the phase
# margin on the phase ([Razavi-Analog] Fig. 10.10, p. 417), the spot frequency on the noise density,
# the input common-mode range on the sweeps over it (none without a range), zero on the saturation
# margin, the 1 % band about each level (1 % of the 0.28 V step) and each edge's settled instant
# on the step, the second to seventh harmonics on the spectrum; titles name the point's input common
# mode and supply, and frequencies in engineering notation (the 1 MHz spot, the 10 MHz tone).
def test_each_figure_marks_the_analysis_values() -> None:
    point, cm, band, step, sine = nominal(), by_cm(), span(), slew(), distortion()
    gain = plots.plot_gain(point)
    assert gain.x_markers == [
        Marker(float(point.bandwidth_hz[0]), "-3 dB bandwidth"),
        Marker(float(point.unity_gain_bandwidth_hz[0]), "unity-gain bandwidth"),
    ]
    assert "input common mode 0.71 V, supply 1.2 V" in gain.title
    phase = plots.plot_phase(point)
    assert phase.y_markers == [Marker(-180.0, "-180 deg")]
    assert phase.x_markers[0].at == float(point.unity_gain_bandwidth_hz[0])
    assert f"{point.phase_margin_deg[0]:.3g}" in phase.x_markers[0].label
    assert plots.plot_noise_density(noise(point)).x_markers == [Marker(1e6, "spot")]
    assert plots.plot_gain_cm(cm, band).x_bands == [Band(0.62, 1.05, "input common-mode range")]
    assert plots.plot_saturation_margin_cm(cm, band).y_markers == [Marker(0.0, "saturation edge")]
    assert plots.plot_gain_cm(cm, replace(band, vin_cm_min_v=float("nan"))).x_bands == []
    figure = plots.plot_step_response(step)
    assert [marker.at for marker in figure.x_markers] == pytest.approx([5.505e-9, 16.105e-9])
    levels = [0.74 + 0.0028, 0.74 - 0.0028, 0.46 + 0.0028, 0.46 - 0.0028]
    assert [marker.at for marker in figure.y_markers] == pytest.approx(levels)
    assert [marker.at for marker in plots.plot_spectrum(sine).x_markers] == [20e6, 30e6, 40e6, 50e6, 60e6, 70e6]
    assert "at 1 MHz over" in plots.plot_noise_in_1mhz_cm(noise(by_cm()), band).title
    assert "on a 10 MHz sine" in plots.plot_spectrum(sine).title


def test_every_figure_renders(tmp_path: Path) -> None:
    drawn = [draw() for draw, *_ in expected().values()]
    assert len({figure.name for figure in drawn}) == 15
    paths = [path for figure in drawn for path in figures.render(figure, tmp_path / figure.name)]
    assert paths and all(path.exists() for path in paths)
