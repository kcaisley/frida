"""The ADC's figures (``flow.adc.plots``): the record's details in the viewer's order, each a Plot spec
of analysis results, its values to six significant digits."""

from __future__ import annotations

import inspect
import math

import numpy as np

from flow import pipeline
from flow.adc import plots
from flow.adc.analysis import _mismatch_statistics, analyze_decision_paths, analyze_mismatch_prediction, analyze_ramp
from flow.adc.params import FINAL_DECISIONS, PELGROM_AXIS, UNIT_MISMATCH
from flow.adc.test_analysis import adc_measurement, adc_ramp_measurement
from flow.adc.types import AnalysisCalibration2, AnalysisMismatch, AnalysisReference

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


def test_a_ramps_figures_grade_its_codes_without_the_clipped_ends() -> None:
    """The code density, INL and DNL of a ramp over the codes it grades, the clipped end codes left
    out; the calibrated ones name their calibration."""
    measurement = adc_ramp_measurement()
    design = analyze_ramp(measurement)
    nominal = design.weights * 4095.0 / np.sum(design.weights)
    calibrated_weights = nominal.copy()
    calibrated_weights[:2] *= (1.02, 0.97)
    calibrated_weights *= 4095.0 / np.sum(calibrated_weights)
    calibration = AnalysisCalibration2(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        method="calibration2",
        label="Cal. 2: least-squares fit to a known ramp",
        code_max=4095,
        nominal_weights=nominal,
        calibrated_weights=calibrated_weights,
        measured_weight_mask=np.ones(len(nominal), dtype=np.bool_),
        training_sample_count=0,
        validation_sample_count=0,
        output_gain=1.0,
        output_offset_lsb=0.0,
    )
    decoded = analyze_ramp(measurement, calibration=calibration)
    density = plots.plot_code_density(design)
    assert density.histogram and density.x_ticks == "code"
    assert density.x == [float(code) for code in range(1, 4095)]
    assert list(density.series) == ["Design weights"]
    inl = plots.plot_inl(design)
    assert inl.series["Design weights"] == [float(f"{value:.6g}") for value in design.inl]
    assert list(plots.plot_inl_calibrated(decoded).series) == ["Calibration 2"]
    assert list(plots.plot_dnl_calibrated(decoded).series) == ["Calibration 2"]
    assert plots.plot_dnl(design).y_label == "DNL (LSB)"


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
