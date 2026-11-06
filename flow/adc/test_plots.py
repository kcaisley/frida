"""The ADC's figures (``flow.adc.plots``): the record's details in the viewer's order, each a Plot spec
of analysis results, its values to six significant digits."""

from __future__ import annotations

import inspect
import math
from dataclasses import replace
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import pytest

import flow.analysis.plots as analysis_plots
from flow import pipeline
from flow.adc import plots
from flow.adc.analysis import (
    _mismatch_statistics,
    analyze_code_spectrum,
    analyze_decision_paths,
    analyze_mismatch_prediction,
    analyze_ramp,
)
from flow.adc.params import FINAL_DECISIONS, PELGROM_AXIS, UNIT_MISMATCH
from flow.adc.test_analysis import adc_measurement, adc_ramp_measurement, tone_codes
from flow.adc.types import (
    AnalysisCalibration,
    AnalysisCalibration1,
    AnalysisCalibration2,
    AnalysisMismatch,
    AnalysisReference,
)
from flow.analysis.types import MeasAdc
from flow.plot import render
from flow.test_plot import drawn

# the viewer's details of a characterization, in its order (every record's, the ladder's and the
# reference driver's where the record has them)
FIGURES = (
    "redundancy",
    "code_density",
    "inl",
    "inl_calibrated",
    "dnl",
    "dnl_calibrated",
    "trajectory",
    "trajectory_final",
    "trajectory_codes",
    "noise_spectrum",
    "noise_input",
    "enob_rate",
    "enob_fin",
    "enob_ladder",
    "spectrum_low",
    "spectrum_nyquist",
    "hsu_rate",
    "power_rate",
    "energy_input",
    "energy_dac_input",
    "calibration_weights",
    "mismatch_weight_sigma",
    "mismatch_transition_sigma",
    "mismatch_margin",
    "mismatch_dnl",
    "mismatch_inl",
    "reference_noise",
    "reference_r_out",
)


def test_the_figures_are_the_records_in_the_viewers_order() -> None:
    """Each figure is a ``@plot`` of its own name, written in the order the viewer shows them."""
    functions = [(name, value) for name, value in vars(plots).items() if name.startswith("plot_")]
    assert tuple(name.removeprefix("plot_") for name, _ in functions) == FIGURES
    for name, function in functions:
        assert inspect.isfunction(function) and pipeline.STAGE_FUNCTIONS.get(function) == "plot", name
        assert f'"{name.removeprefix("plot_")}",' in inspect.getsource(function), name


def calibration_of(
    measurement: MeasAdc,
    kind: type[AnalysisCalibration],
    method: Literal["extracted", "calibration1", "calibration2", "calibration3"],
) -> AnalysisCalibration:
    """Weights a little off the design's in a ramp's first two decisions, as ``method`` learns them
    (the extracted array's: the ``AnalysisCalibration`` itself)."""
    design = analyze_ramp(measurement)
    nominal = design.weights * 4095.0 / np.sum(design.weights)
    calibrated_weights = nominal.copy()
    calibrated_weights[:2] *= (1.02, 0.97)
    calibrated_weights *= 4095.0 / np.sum(calibrated_weights)
    return kind(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        method=method,
        label=f"{method}: weights learned",
        code_max=4095,
        nominal_weights=nominal,
        calibrated_weights=calibrated_weights,
        measured_weight_mask=np.ones(len(nominal), dtype=np.bool_),
        training_sample_count=0,
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )


def test_a_ramps_figures_grade_its_codes_without_the_clipped_ends() -> None:
    """The code density, INL and DNL of a ramp over the codes it grades, the clipped end codes left
    out; the calibrated ones name their calibration."""
    measurement = adc_ramp_measurement()
    design = analyze_ramp(measurement)
    decoded = analyze_ramp(measurement, calibration=calibration_of(measurement, AnalysisCalibration2, "calibration2"))
    density = plots.plot_code_density(design)
    assert density.histogram and density.x_ticks == "code"
    assert density.x == [float(code) for code in range(1, 4095)]
    assert list(density.series) == ["Design weights"]
    inl = plots.plot_inl(design)
    assert inl.series["Design weights"] == [float(f"{value:.6g}") for value in design.inl]
    assert list(plots.plot_inl_calibrated(decoded).series) == ["Calibration 2"]
    assert list(plots.plot_dnl_calibrated(decoded).series) == ["Calibration 2"]
    assert plots.plot_dnl(design).y_label == "DNL (LSB)"


def test_each_decoding_a_lab_study_compares_is_drawn_by_its_weights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lab study draws each decoding of one ramp on the record's figures: the design weights', the
    extracted array's and each calibration's, each a figure of its own named by its weights (the
    code density as the code widths over the ideal), on the analysis plots' canvas."""
    measurement = adc_ramp_measurement()
    decoded = [
        analyze_ramp(measurement, calibration=calibration_of(measurement, AnalysisCalibration, method))
        for method in ("extracted", "calibration1", "calibration3")
    ]
    names = [["Extracted weights"], ["Calibration 1"], ["Calibration 3"]]
    for function in (plots.plot_code_density, plots.plot_inl_calibrated, plots.plot_dnl_calibrated):
        assert [list(function(ramp).series) for ramp in decoded] == names
    density = plots.plot_code_density(decoded[0])
    assert density.y_label == "Code width (count / ideal)" and density.histogram
    (widths,) = density.series.values()
    assert np.nanmean(widths) == pytest.approx(1.0, rel=1e-3)
    for name in ("PLOT_PNGS", "PLOT_SVGS"):
        monkeypatch.setattr(analysis_plots, name, True)
    for function in (plots.plot_code_density, plots.plot_inl_calibrated, plots.plot_dnl_calibrated):
        paths = render(function(decoded[1]), tmp_path / function.__name__)
        assert [path.suffix for path in paths] == [".png", ".svg", ".pdf"]
        assert plt.imread(paths[0]).shape[:2] == (2700, 4800)
        assert function(decoded[1]).y_label.split(" (")[0] in paths[1].read_text()


def test_the_weight_figure_names_its_weights_and_shades_those_not_measured() -> None:
    """The weights' error against the design's, the extracted array's (the record's) or a
    calibration's (a lab study's), each named by its weights; the decisions whose weight was not
    measured (the terminal one, a calibration's unresolved ones) shaded, the first band labelled."""
    measurement = adc_ramp_measurement()
    extracted = calibration_of(measurement, AnalysisCalibration, "extracted")
    mask = np.ones(len(extracted.nominal_weights), dtype=np.bool_)
    mask[-1] = False
    last = len(mask) - 1
    figure = plots.plot_calibration_weights(replace(extracted, measured_weight_mask=mask))
    assert figure.title == "Weight error of the extracted array" and list(figure.series) == ["Extracted weights"]
    assert figure.x == [float(decision) for decision in range(last + 1)] and figure.x_ticks == "step"
    assert figure.x_bands == [pipeline.Band(last - 0.5, last + 0.5, "Not measured")]
    # the first two decisions' weights off the design's, one up and one down
    (error,) = figure.series.values()
    assert error[0] > 0 > error[1]
    mask[5:8] = False
    calibration1 = replace(calibration_of(measurement, AnalysisCalibration1, "calibration1"), measured_weight_mask=mask)
    calibrated = plots.plot_calibration_weights(calibration1)
    assert calibrated.title == "Weight error found by calibration 1" and list(calibrated.series) == ["Calibration 1"]
    assert [(band.low, band.high, band.label) for band in calibrated.x_bands] == [
        (4.5, 7.5, "Not measured"),
        (last - 0.5, last + 0.5, ""),
    ]


def test_the_decision_paths_are_drawn_weighted_by_their_conversions() -> None:
    """The distinct decision paths at one input, each with how many conversions took it, over the
    whole conversion and its last decisions, and the histogram of the codes they end on."""
    measurement = adc_measurement([5, 5, 3])
    bout = np.asarray([[1, 0, 1] + [0] * 14, [1, 0, 1] + [0] * 14, [0, 1, 1] + [0] * 14], dtype=np.uint8)
    object.__setattr__(measurement, "bout", bout)
    paths = analyze_decision_paths(measurement)
    steps = paths.estimate_dout.shape[1]
    whole = plots.plot_trajectory(paths)
    assert whole.x == list(range(steps)) and whole.series == {}
    assert sorted(path["count"] for path in whole.paths) == [1, 2]
    assert (whole.x_ticks, whole.y_ticks) == ("step", "code")
    final = plots.plot_trajectory_final(paths)
    assert final.x == list(range(steps - 1 - FINAL_DECISIONS, steps))
    assert all(len(path["y"]) == len(final.x) for path in final.paths)
    codes = plots.plot_trajectory_codes(paths)
    assert codes.histogram and codes.x == [float(code) for code in range(1, 8)]
    ((label, counts),) = codes.series.items()
    assert counts == [0.0, 0.0, 1.0, 0.0, 2.0, 0.0, 0.0]
    assert label == f"Conversions (mean {np.mean([5, 5, 3]):.2f}, σ {np.std([5, 5, 3]):.2f} LSB)"


def test_the_decision_paths_hold_each_estimate_and_keep_a_rare_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path is a conversion's running estimates as they are, held from one decision to the next
    (drawn as steps: no estimate made up between decisions); a branch one conversion in three takes,
    64 codes off, stays among the last decisions' paths and the codes they end on; drawn on the
    analysis plots' canvas."""
    paths = analyze_decision_paths(adc_measurement([100, 101, 102]))
    estimates = {tuple(float(f"{y:.6g}") for y in row) for row in np.asarray(paths.estimate_dout, dtype=np.float64)}
    whole = plots.plot_trajectory(paths)
    assert {tuple(path["y"]) for path in whole.paths} == estimates
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(whole, tmp_path / "trajectory")
    assert plt.imread(png).shape[:2] == (2700, 4800)
    # drawn (saving nothing from here on) as steps held through each decision
    assert all(line.get_drawstyle() == "steps-post" for line in drawn(whole, monkeypatch).axes[0].lines)
    branched = paths.estimate_dout.copy()
    branched[:, -1] = (2240, 2240, 2304)
    rare = replace(paths, estimate_dout=branched, final_dout=np.asarray([2240, 2240, 2304], dtype=np.int64))
    assert {path["y"][-1] for path in plots.plot_trajectory_final(rare).paths} == {2240.0, 2304.0}
    codes = plots.plot_trajectory_codes(rare)
    (counts,) = codes.series.values()
    assert codes.x[0] < 2240 and codes.x[-1] > 2304
    assert (counts[codes.x.index(2240.0)], counts[codes.x.index(2304.0)]) == (2.0, 1.0)


def test_a_capture_on_one_code_spreads_under_a_code() -> None:
    """Every conversion on one code: a spread under a code, which the codes cannot resolve, not
    none."""
    paths = analyze_decision_paths(adc_measurement([2_048] * 10))
    ((label, counts),) = plots.plot_trajectory_codes(paths).series.items()
    assert label == "Conversions (mean 2048.00, one code: σ under 1 LSB)"
    assert counts == [0.0, 0.0, 10.0, 0.0, 0.0]


def test_a_code_spectrum_is_input_referred_with_its_floor_and_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fixed-input capture's code spectrum in V/√Hz through its LSB, on log axes: an interferer
    folded to its alias (8.15 MHz at 2, 6 and 10 MS/s: 150 kHz, 2.15 MHz, 1.85 MHz) shaded among
    its lines, the white floor marked with the variance's split; a stuck capture has neither;
    drawn by both renderers' rules on the analysis plots' canvas."""
    for rate_hz, alias_hz in ((2.0e6, 150e3), (6.0e6, 2.15e6), (10.0e6, 1.85e6)):
        capture = adc_measurement(tone_codes(rate_hz, tone_hz=8.15e6, count=16_384), sample_rate_hz=rate_hz)
        spectrum = analyze_code_spectrum(capture)
        figure = plots.plot_noise_spectrum(spectrum)
        assert (figure.x_log, figure.y_log, figure.y_label) == (True, True, "Input-referred noise (V/√Hz)")
        # the LSB density, log-binned, through the capture's LSB
        (density,) = figure.series.values()
        _, lsb_density = plots._log_binned(spectrum.frequency_hz, spectrum.asd_lsb_per_sqrt_hz)
        np.testing.assert_allclose(density, np.asarray(lsb_density) * spectrum.input_lsb_v, rtol=1e-5)
        assert any(band.low <= alias_hz <= band.high for band in figure.x_bands), (rate_hz, figure.x_bands)
        (floor,) = figure.y_markers
        assert floor.at == pytest.approx(math.sqrt(spectrum.white_floor_lsb2_per_hz) * spectrum.input_lsb_v, rel=1e-5)
        assert floor.label == (
            f"White floor; total {spectrum.total_rms_lsb:.2f} = lines {spectrum.narrowband_rms_lsb:.2f}"
            f" ⊕ broadband {spectrum.broadband_rms_lsb:.2f} LSB rms"
        )
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(figure, tmp_path / "noise_spectrum")
    assert plt.imread(png).shape[:2] == (2700, 4800)
    stuck = plots.plot_noise_spectrum(
        analyze_code_spectrum(adc_measurement(np.full(16_384, 2_000), sample_rate_hz=2.0e6))
    )
    assert stuck.y_markers == [] and stuck.x_bands == []
    # nothing to draw on the log axes, as matplotlib says
    with pytest.warns(UserWarning, match="no positive values"):
        assert render(stuck, tmp_path / "stuck")


def test_the_mismatch_figures_are_at_harpes_matching() -> None:
    """The predicted mismatch by stage at Harpe's matching, and the worst DNL and INL over the
    Pelgrom coefficient."""
    main_f = np.array([16, 8, 4, 2, 1], dtype=np.float64) * 0.2e-15
    weights = np.asarray([2 * value for value in (16, 8, 4, 2, 1)] + [1], dtype=np.float64)
    statistics = _mismatch_statistics(main_f, np.zeros_like(main_f), 0.0, weights, 63)
    prediction = analyze_mismatch_prediction(AnalysisMismatch(group=None, index=None, dut=None, **statistics))
    label = f"A_C {UNIT_MISMATCH * 100:g} %·sqrt(fF)"
    for function in (plots.plot_mismatch_weight_sigma, plots.plot_mismatch_transition_sigma):
        figure = function(prediction)
        assert list(figure.series) == [label] and figure.x == [float(stage) for stage in range(5)]
    sigma = plots.plot_mismatch_weight_sigma(prediction).series[label]
    assert sigma == [float(f"{value:.6g}") for value in UNIT_MISMATCH * statistics["weight_sigma"]]
    dnl = plots.plot_mismatch_dnl(prediction)
    assert dnl.x_log and dnl.x == [float(f"{value:.6g}") for value in PELGROM_AXIS * 100]
    assert np.all(np.diff(dnl.series["Design weights, 95th percentile"]) >= 0)


def test_the_reference_figures_show_the_loss_over_their_grids() -> None:
    """The ENOB the reference's noise and its driver's resistance cost, over their grids, to six
    significant digits."""
    reference = AnalysisReference(
        group=None,
        index=None,
        dut=None,
        decap_f=1e-12,
        noise_v=np.asarray([1e-6, 1e-5, 1e-4]),
        noise_loss_bits=np.asarray([0.0012345678, 0.05, math.pi]),
        r_out_ohm=np.asarray([1.0, 10.0]),
        r_out_loss_bits=np.asarray([0.01, 0.2]),
        noise_max_v=1e-5,
        r_max_ohm=10.0,
        enob_loss_max_bits=0.1,
    )
    noise = plots.plot_reference_noise(reference)
    assert noise.x_log and noise.x == [1e-6, 1e-5, 1e-4]
    assert noise.series == {"ENOB loss": [0.00123457, 0.05, 3.14159]}
    r_out = plots.plot_reference_r_out(reference)
    assert r_out.x == [1.0, 10.0] and r_out.series == {"ENOB loss": [0.01, 0.2]}
    assert r_out.x_label == "Reference output resistance (Ω)"
