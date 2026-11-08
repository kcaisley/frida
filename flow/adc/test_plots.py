"""The ADC's figures (``flow.adc.plots``): the record's details in the viewer's order, then those only
the lab studies draw, each a Plot spec of analysis results, its values to six significant digits."""

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
    analyze_cdac_settling,
    analyze_code_spectrum,
    analyze_decision_paths,
    analyze_dynamic,
    analyze_energy,
    analyze_input_noise,
    analyze_interferer,
    analyze_mismatch_prediction,
    analyze_noise,
    analyze_power,
    analyze_power_waveform,
    analyze_ramp,
    analyze_sampling_noise,
    analyze_sequence_map,
    analyze_sequencer,
    analyze_transfer,
)
from flow.adc.params import FINAL_DECISIONS, PELGROM_AXIS, UNIT_MISMATCH, Recipe, TbParams
from flow.adc.test_analysis import (
    adc_cdac_settling_measurement,
    adc_conditions,
    adc_measurement,
    adc_ramp_measurement,
    adc_sampling_measurement,
    timing_sequences,
    tone_codes,
)
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
# the figures only the lab studies draw (the figures step over captures, the scans' tests), after the record's
LAB_FIGURES = (
    "transfer",
    "ramp_transfer",
    "sequence_enob",
    "sequence_plausible",
    "sequence_shift",
    "noise_rate",
    "noise_enob_rate",
    "codes_rate",
    "interferer",
    "interferer_lines",
    "sampling_noise",
    "cdac_settling_first",
    "cdac_settling_middle",
    "cdac_settling_last",
    "power_analog",
    "power_digital",
    "power_dac",
    "sequencer",
)


def test_the_figures_are_the_records_in_the_viewers_order() -> None:
    """Each figure is a ``@plot`` of its own name: the record's first, written in the order the viewer
    shows them, then those only the lab studies draw."""
    functions = [(name, value) for name, value in vars(plots).items() if name.startswith("plot_")]
    assert tuple(name.removeprefix("plot_") for name, _ in functions) == FIGURES + LAB_FIGURES
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
    its lines, the white floor marked and the variance's split in the title; a stuck capture has
    neither; drawn by both renderers' rules on the analysis plots' canvas."""
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
        assert floor.label == "White floor"
        assert figure.title == (
            f"Output-code noise: {spectrum.total_rms_lsb:.2f} LSB rms = lines {spectrum.narrowband_rms_lsb:.2f}"
            f" ⊕ white {spectrum.broadband_rms_lsb:.2f}"
        )
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(figure, tmp_path / "noise_spectrum")
    assert plt.imread(png).shape[:2] == (2700, 4800)
    stuck = plots.plot_noise_spectrum(
        analyze_code_spectrum(adc_measurement(np.full(16_384, 2_000), sample_rate_hz=2.0e6))
    )
    assert stuck.y_markers == [] and stuck.x_bands == [] and stuck.title == "Output-code noise"
    # nothing to draw on the log axes, as matplotlib says
    with pytest.warns(UserWarning, match="no positive values"):
        assert render(stuck, tmp_path / "stuck")


def test_a_sine_sweep_draws_its_enob_and_spectra_at_its_own_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two sines at 100 kS/s, 1 and 8 kHz (a lab study's sweep, not the record's 10 MS/s): the ENOB
    over the input frequency and the spectra name their own rate; every ENOB is referred to full
    scale; drawn on the analysis plots' canvas."""
    dynamics = []
    for index, frequency_hz in enumerate((1_000.0, 8_000.0)):
        time_s = np.arange(4_096) / 100_000.0
        samples = np.rint(2_048.0 + 1_200.0 * np.sin(2.0 * np.pi * frequency_hz * time_s + 0.2))
        dynamics.append(
            analyze_dynamic(
                adc_measurement(
                    samples, sample_rate_hz=100_000.0, input_frequency_hz=frequency_hz, logic_phase_delay_symbols=index
                )
            )
        )
    enob = [float(f"{dynamic.spectral_enob_fs_bits:.6g}") for dynamic in dynamics]
    fin = plots.plot_enob_fin(dynamics)
    assert fin.title == "ENOB over the input frequency at 0.1 MS/s"
    assert (fin.x, fin.series) == ([0.01, 0.08], {"ENOB": enob})
    # a -4.6 dBFS sine: its ENOB referred to full scale, above the one at its own amplitude
    assert enob[0] > dynamics[0].spectral_enob_bits + 0.7
    low = plots.plot_spectrum_low(dynamics[0])
    assert low.title == "Spectrum at 0.1 MS/s, low input frequency" and list(low.series) == ["0.001 MHz input"]
    assert low.x[-1] == pytest.approx(50_000.0, rel=1e-3) and low.y_label == "Power (dBFS)"
    assert plots.plot_spectrum_nyquist(dynamics[1]).title == "Spectrum at 0.1 MS/s, input near Nyquist"
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    for figure in (fin, low):
        (png, _pdf) = render(figure, tmp_path / figure.name)
        assert plt.imread(png).shape[:2] == (2700, 4800)


def test_the_energy_figures_draw_every_rail_and_the_dacs_over_the_input() -> None:
    """The energy a conversion takes over a DC input (a lab study's captures, their supplies read
    back), every rail's and the DAC's: each rail's dynamic power at the active rate and its static
    power at the sample rate."""
    captures = []
    for index, level_v in enumerate((-0.25, 0.0, 0.25)):
        readbacks = {}
        for rail, active_w in (("vdd_a", 2e-6), ("vdd_d", 4e-6), ("vdd_dac", 6e-6)):
            # the DAC's power grows with the input, the other rails' stays
            active_w *= 1 + index * (rail == "vdd_dac")
            readbacks[f"{rail}_active_average_power_w"] = active_w
            readbacks[f"{rail}_static_average_power_w"] = active_w / 4
        captures.append(adc_measurement([2048] * 8, vin_diff_v=level_v, readbacks=readbacks))
    energy = analyze_energy(captures, power=[analyze_power(capture) for capture in captures])
    total = plots.plot_energy_input(energy)
    dac = plots.plot_energy_dac_input(energy)
    assert total.x == dac.x == [-0.25, 0.0, 0.25]
    np.testing.assert_allclose(total.series["Total"], energy.total_energy_j, rtol=1e-5)
    np.testing.assert_allclose(dac.series["VDD_DAC"], energy.vdd_dac_energy_j, rtol=1e-5)
    # the DAC's grows with the input here, the others stay
    assert dac.series["VDD_DAC"][0] < dac.series["VDD_DAC"][1] < dac.series["VDD_DAC"][2]
    assert total.y_label == dac.y_label == "Energy per conversion (J)"


def test_the_mismatch_figures_are_at_the_assumed_matching() -> None:
    """The predicted mismatch by stage at the assumed matching, and the worst DNL and INL over the
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


def test_dc_steps_draw_their_transfer_and_noise_over_the_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lab study's DC steps (a capture a level, as one staircase capture too): the mean code over the
    input, and the codes' spread there on the record's noise figure; drawn on the analysis plots'
    canvas."""
    levels = np.linspace(-0.6, 0.6, 16)
    codes = [[2 * step, 2 * step, 2 * step + 1, 2 * step + 2] for step in range(16)]
    steps = [adc_measurement(code, vin_diff_v=level) for code, level in zip(codes, levels, strict=True)]
    transfer = plots.plot_transfer(analyze_transfer(steps))
    assert transfer.x == [float(f"{level:.6g}") for level in levels] and transfer.y_ticks == "code"
    assert transfer.series == {"Mean code": [2 * step + 0.75 for step in range(16)]}
    noise = plots.plot_noise_input(analyze_input_noise(steps))
    assert noise.name == "noise_input" and noise.x == transfer.x
    assert noise.series["Noise"] == [float(f"{np.std([0, 0, 1, 2]):.6g}")] * 16
    # one staircase capture holding the same conversions: the same figure
    staircase = adc_measurement(np.concatenate(codes), vin_diff_v=np.repeat(levels, 4))
    assert plots.plot_noise_input(analyze_input_noise([staircase])) == noise
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    for figure in (transfer, noise):
        (png, _pdf) = render(figure, tmp_path / figure.name)
        assert plt.imread(png).shape[:2] == (2700, 4800)


def test_a_ramps_transfer_is_drawn_by_its_weights(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ramp's reconstructed transfer, each decoding a figure named by its weights, its codes ticked
    as codes; drawn on the analysis plots' canvas."""
    measurement = adc_ramp_measurement()
    design = analyze_ramp(measurement)
    calibrated = analyze_ramp(
        measurement, calibration=calibration_of(measurement, AnalysisCalibration1, "calibration1")
    )
    figure = plots.plot_ramp_transfer(design)
    assert (figure.name, figure.y_ticks) == ("ramp_transfer", "code")
    assert figure.x == [float(f"{value:.6g}") for value in design.transfer_vin_diff_v]
    assert figure.series == {"Design weights": [float(f"{value:.6g}") for value in design.transfer_mean_dout]}
    assert list(plots.plot_ramp_transfer(calibrated).series) == ["Calibration 1"]
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(figure, tmp_path / "ramp_transfer")
    assert plt.imread(png).shape[:2] == (2700, 4800)


def test_the_sequence_maps_name_each_sequence_by_its_decision_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operating conditions over sequence and rate as three maps, a column a sequence named by its
    COMP and LOGIC decision word (as the catalogue names it) and a row a symbol rate; the ENOB empty
    where the codes are not plausible; drawn on the analysis plots' canvas."""
    conditions = adc_conditions(3, {(1, 1): [1000] * 100})
    sequences = analyze_sequence_map([conditions])
    words = [
        recipe.name.lower().split("_comp")[1].replace("_logic", "/")
        for recipe in Recipe
        if recipe.rows in timing_sequences[:4]
    ]
    for function, label in (
        (plots.plot_sequence_enob, "ENOB (bits)"),
        (plots.plot_sequence_plausible, "Plausible ADCs (of 1)"),
        (plots.plot_sequence_shift, "|Mean code − reference| (LSB)"),
    ):
        figure = function(sequences)
        assert (figure.x, figure.series, figure.x_labels, figure.y_labels) == ([], {}, words, ["256 MBd", "512 MBd"])
        assert figure.heatmap is not None and figure.heatmap.label == label
        assert figure.heatmap.x == [-0.5, 0.5, 1.5, 2.5, 3.5] and figure.heatmap.y == [-0.5, 0.5, 1.5]
    enob = plots.plot_sequence_enob(sequences).heatmap
    assert enob is not None and math.isnan(enob.z[1][1]) and enob.z[0][1] == float(f"{sequences.enob_bits[0, 1]:.6g}")
    plausible = plots.plot_sequence_plausible(sequences).heatmap
    assert plausible is not None and plausible.z == [[1.0, 1.0, 1.0, 1.0], [1.0, 0.0, 1.0, 1.0]]
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(plots.plot_sequence_enob(sequences), tmp_path / "sequence_enob")
    assert plt.imread(png).shape[:2] == (2700, 4800)


def test_sequences_sharing_a_decision_word_are_numbered() -> None:
    """Two sequences of one decision word (another INIT phase, period or sampling) are told apart by
    their places."""
    base = timing_sequences[0]
    longer = tuple(row + "0" * 8 for row in base)
    assert plots._sequence_labels([base, longer]) == [
        f"1: {plots._sequence_label(base)}",
        f"2: {plots._sequence_label(base)}",
    ]


def test_a_fixed_inputs_noise_and_enob_over_the_rate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One sequence's fixed-input captures over the rate: their noise referred to the input (a large
    spread kept, a constant code none) and its noise-equivalent ENOB, named by the sequence where
    the captures share one; drawn on the analysis plots' canvas."""
    noises = [
        analyze_noise(adc_measurement(codes, sample_rate_hz=rate))
        for codes, rate in (([100, 101, 99, 100], 1.0e6), ([0, 100], 2.0e6), ([100] * 4, 3.0e6))
    ]
    noise = plots.plot_noise_rate(noises)
    name = f"Sequence {plots._sequence_label(noises[0].sequence)}"
    assert noise.x == [1e6, 2e6, 3e6] and list(noise.series) == [name]
    lsb = noises[0].input_lsb_v
    values = noise.series[name]
    assert values[:2] == [float(f"{np.std([100, 101, 99, 100]) * lsb:.6g}"), float(f"{50 * lsb:.6g}")]
    assert math.isnan(values[2]) and noise.y_label == "Input-referred noise, rms (V)"
    enob = plots.plot_noise_enob_rate(noises)
    assert enob.series[name][:2] == [float(f"{result.enob_bits:.6g}") for result in noises[:2]]
    assert math.isnan(enob.series[name][2])
    # another LOGIC timing among them: no one sequence to name
    other = analyze_noise(adc_measurement([100, 101], sample_rate_hz=4.0e6, logic_phase_delay_symbols=1))
    assert list(plots.plot_noise_rate([*noises, other]).series) == ["Fixed input"]
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    for figure in (noise, enob):
        (png, _pdf) = render(figure, tmp_path / figure.name)
        assert plt.imread(png).shape[:2] == (2700, 4800)


def test_the_codes_over_the_rate_are_each_captures_shares(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fixed input's codes over the rate: a column a capture, reaching halfway to its neighbours,
    each code's share of its conversions, by decade, two empty codes either side of the codes any
    capture reaches, a rare far one kept; the mean code over it; each ADC on its own codes; drawn on
    the analysis plots' canvas."""
    noises = [
        analyze_noise(adc_measurement([100, 100, 101, 101, 101, 102], sample_rate_hz=rate))
        for rate in (1.0e6, 2.0e6, 3.0e6)
    ]
    codes = plots.plot_codes_rate(noises)
    assert codes.heatmap is not None and codes.heatmap.log and codes.y_ticks == "code"
    assert codes.heatmap.label == "Share of conversions"
    assert codes.heatmap.x == [0.5e6, 1.5e6, 2.5e6, 3.5e6]
    assert codes.heatmap.y == [code - 0.5 for code in range(98, 106)]
    column = [row[0] for row in codes.heatmap.z]
    assert column[2:5] == [float(f"{2 / 6:.6g}"), 0.5, float(f"{1 / 6:.6g}")]
    assert all(math.isnan(share) for share in column[:2] + column[5:])
    assert codes.series == {"Mean code": [float(f"{605 / 6:.6g}")] * 3}
    rare = plots.plot_codes_rate([analyze_noise(adc_measurement([100] * 1000 + [1000], sample_rate_hz=1.0e6))])
    assert rare.heatmap is not None and (rare.heatmap.y[0], rare.heatmap.y[-1]) == (97.5, 1002.5)
    assert rare.heatmap.x == [0.9e6, 1.1e6]
    # every conversion on one code: one cell holds them all; another ADC's map on its own codes
    one = plots.plot_codes_rate([analyze_noise(adc_measurement([2200] * 5, sample_rate_hz=1.0e6, observed_adc=1))])
    assert one.heatmap is not None and one.heatmap.y[0] == 2197.5
    assert [share for row in one.heatmap.z for share in row if not math.isnan(share)] == [1.0]
    with pytest.raises(ValueError, match="rate order"):
        plots.plot_codes_rate(list(reversed(noises)))
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(codes, tmp_path / "codes_rate")
    assert plt.imread(png).shape[:2] == (2700, 4800)


def test_the_interferer_search_marks_its_frequency_and_each_rates_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interferer at 8.15 MHz folded at 2, 6 and 10 MS/s, a stuck capture left out: each candidate's
    score, thinned to 2000 points that keep its peak in its place, the best candidate marked; the
    strongest line at each rate; drawn on the analysis plots' canvas."""
    measurements = [
        adc_measurement(tone_codes(rate, tone_hz=8.15e6, count=16_384, seed=index), sample_rate_hz=rate, observed_adc=2)
        for index, rate in enumerate((2.0e6, 6.0e6, 10.0e6))
    ]
    stuck = adc_measurement(np.full(16_384, 2_000), sample_rate_hz=2.0e6, logic_phase_delay_symbols=1, observed_adc=2)
    spectra = [analyze_code_spectrum(measurement) for measurement in (*measurements, stuck)]
    interferer = analyze_interferer(spectra)
    figure = plots.plot_interferer(interferer)
    (score,) = figure.series.values()
    assert len(figure.x) == 2000 < len(interferer.candidate_frequency_hz)
    assert max(score) == float(f"{np.max(interferer.score_db):.6g}")
    assert figure.x[score.index(max(score))] == pytest.approx(interferer.frequency_hz, rel=1e-5)
    (found,) = figure.x_markers
    assert found.at == pytest.approx(8.15e6, rel=1e-3) and found.label == f"{interferer.frequency_hz / 1e6:.3f} MHz"
    lines = plots.plot_interferer_lines(interferer)
    assert lines.x == [2e6, 6e6, 10e6]
    assert lines.series == {"Strongest line": [float(f"{value:.6g}") for value in interferer.observed_peak_hz]}
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    for drawn_figure in (figure, lines):
        (png, _pdf) = render(drawn_figure, tmp_path / drawn_figure.name)
        assert plt.imread(png).shape[:2] == (2700, 4800)


def test_the_held_voltage_is_a_histogram_of_25_uv_bins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The held differential voltage about its mean: bins 25 µV wide on its multiples, their shares
    summing to one, an empty bin either side; another design's offset makes no difference; its
    spread and count named; drawn on the analysis plots' canvas."""
    sampling = analyze_sampling_noise(adc_sampling_measurement())
    figure = plots.plot_sampling_noise(sampling)
    assert figure.histogram and figure.x_label == "VDAC_P − VDAC_N about its mean (V)"
    np.testing.assert_allclose(np.diff(figure.x), 25e-6)
    ((label, shares),) = figure.series.items()
    assert label == f"σ {sampling.sigma_v * 1e6:.1f} µV, {len(sampling.held_diff_v)} conversions"
    assert sum(shares) == pytest.approx(1.0, abs=1e-5) and shares[0] == shares[-1] == 0.0
    offset = plots.plot_sampling_noise(replace(sampling, held_p_v=sampling.held_p_v + 0.01))
    assert (offset.x, offset.series) == (figure.x, figure.series)
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(figure, tmp_path / "sampling_noise")
    assert plt.imread(png).shape[:2] == (2700, 4800)


def test_the_cdac_settles_at_its_first_middle_and_last_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The top plates' settling at the three stages the analysis aligns (C0, C7 and C15 of a 16-stage
    array), each conversion's differential error against its settled value a path on a log axis,
    down to a thousandth of the band a plate settles to, which is marked; drawn on the analysis
    plots' canvas."""
    settling = analyze_cdac_settling(adc_cdac_settling_measurement())
    figures = [
        plots.plot_cdac_settling_first(settling),
        plots.plot_cdac_settling_middle(settling),
        plots.plot_cdac_settling_last(settling),
    ]
    assert [figure.title for figure in figures] == [f"Top-plate settling of C{stage}'s update" for stage in (0, 7, 15)]
    for figure, stage in zip(figures, (0, 7, 15), strict=True):
        rows = settling.stage_index == stage
        error = np.abs(settling.vdac_p_settling_error_v[rows] - settling.vdac_n_settling_error_v[rows])
        assert figure.y_log and figure.series == {} and len(figure.paths) == np.count_nonzero(rows)
        assert figure.x == [float(f"{value:.6g}") for value in settling.time_s]
        np.testing.assert_allclose(
            [path["y"] for path in figure.paths], np.where(error >= 1e-6, error, np.nan), rtol=1e-5, atol=0
        )
        assert [marker.at for marker in figure.y_markers] == [1e-3]
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    (png, _pdf) = render(figures[0], tmp_path / "cdac_settling_first")
    assert plt.imread(png).shape[:2] == (2700, 4800)


def _spice_power_measurement() -> MeasAdc:
    """A simulated conversion with its sequencer's outputs (INIT 25-50 ns, SAMP 75-100 ns, COMP
    125-150 ns, LOGIC 175-200 ns) and every rail's current, active until 650 ns."""
    readbacks = {
        "vdd_a_active_average_power_w": 12.0e-6,
        "vdd_d_active_average_power_w": 24.0e-6,
        "vdd_dac_active_average_power_w": 36.0e-6,
    }
    measurement = adc_measurement([100, 101, 102], readbacks=readbacks, internal=True, waveform_sample_count=201)
    assert measurement.wave is not None
    time_s = measurement.wave.time_s
    levels = {}
    for name, (start_s, stop_s) in {
        "seq_init": (25e-9, 50e-9),
        "seq_samp": (75e-9, 100e-9),
        "seq_comp": (125e-9, 150e-9),
        "seq_logic": (175e-9, 200e-9),
    }.items():
        levels[name] = np.zeros_like(measurement.wave.v["seq_init"])
        levels[name][0, (time_s >= start_s) & (time_s <= stop_s)] = 1.2
    currents = {}
    for rail, static_a, active_a in (
        ("vdd_a", 2.0e-6, 10.0e-6),
        ("vdd_d", 4.0e-6, 20.0e-6),
        ("vdd_dac", 6.0e-6, 30.0e-6),
    ):
        currents[rail] = np.full_like(levels["seq_init"], active_a)
        currents[rail][0, time_s > 650e-9] = static_a
    return replace(measurement, wave=replace(measurement.wave, i=currents, v={**measurement.wave.v, **levels}))


def test_a_simulated_conversions_rail_power_and_its_sequencer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One simulated conversion: the supply power over the rate; each rail's instantaneous power from
    INIT's rise, a figure each, its static and active averages marked and the sampling phase shaded;
    the capture's programmed sequencer outputs as a map, INIT on top, a cell a symbol; drawn on the
    analysis plots' canvas."""
    measurement = _spice_power_measurement()
    power = analyze_power(measurement)
    assert plots.plot_power_rate([power]).series == {"Total": [float(f"{power.total_power_w:.6g}")]}
    waveform = analyze_power_waveform(measurement, power=power)
    figures = [plots.plot_power_analog(waveform), plots.plot_power_digital(waveform), plots.plot_power_dac(waveform)]
    assert [figure.title for figure in figures] == [
        f"{supply} power over one conversion" for supply in ("VDD_A", "VDD_D", "VDD_DAC")
    ]
    samp = [(waveform.time_s[first], waveform.time_s[last]) for first, last in plots._runs(waveform.samp_high)]
    for rail, figure in enumerate(figures):
        assert figure.x == [float(f"{value:.6g}") for value in waveform.time_s]
        assert list(figure.series.values()) == [[float(f"{value:.6g}") for value in waveform.rail_power_w[rail]]]
        assert [(marker.at, marker.label) for marker in figure.y_markers] == [
            (float(f"{waveform.static_power_w[rail]:.6g}"), "Static average"),
            (float(f"{waveform.active_power_w[rail]:.6g}"), "Active average"),
        ]
        assert [band.label for band in figure.x_bands] == ["SAMP"]
        assert [(band.low, band.high) for band in figure.x_bands] == pytest.approx(samp)
    sequencer = analyze_sequencer(measurement)
    diagram = plots.plot_sequencer(sequencer)
    init, _, _, logic = TbParams.from_init(measurement.tb.rows)
    assert diagram.y_labels == ["LOGIC", "COMP", "SAMP", "INIT"] and diagram.heatmap is not None
    assert diagram.heatmap.z[3] == [1.0 if bit == "1" else 0.0 for bit in init]
    assert diagram.heatmap.z[0] == [1.0 if bit == "1" else 0.0 for bit in logic]
    assert diagram.heatmap.x[-1] == pytest.approx(len(init) / float(measurement.tb.symbol_rate))
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    for figure in (figures[0], diagram):
        (png, _pdf) = render(figure, tmp_path / figure.name)
        assert plt.imread(png).shape[:2] == (2700, 4800)


# ---- the lab studies as ``python -m flow adc --from figures --to figures --run <run>``: a campaign's captures,
# each board and channel's, made into its figures by the analyses as they chain


def _captured(dout, *, rate: float, rows, vin: float = 0.05, observed_adc: int = 0, readbacks=None) -> MeasAdc:
    """A lab capture of a fixed input at ``rate`` conversions a second, its sequencer playing
    ``rows`` (board 7)."""
    import hdl21 as h

    capture = adc_measurement(dout, sample_rate_hz=rate, observed_adc=observed_adc, readbacks=readbacks)
    tb = replace(capture.tb, vin_diff=h.Vdc.Params(dc=vin)).sequenced(rows, symbol_rate=rate * len(rows[0]))
    return replace(capture, param=replace(capture.param, tb=tb))


def _written(run: Path, captures) -> Path:
    from flow.analysis.io import write_measurement

    for number, capture in enumerate(captures):
        write_measurement(run / f"{number:04d}_capture.h5", capture)
    return run


def test_a_campaigns_rate_sweeps_are_a_figure_each(tmp_path: Path) -> None:
    """A campaign's captures of one ADC over two sequences and three rates: the noise over the rate
    of each sequence its own figure (``MeasAdc.sweep``), as one sweep's captures draw it."""
    import json

    from flow import plot

    rng = np.random.default_rng(3)
    captures = [
        _captured(np.rint(1000 + rng.normal(0, 1 + rate / 1e6, 400)), rate=rate, rows=rows)
        for rows in timing_sequences[:2]
        for rate in (1e6, 2e6, 4e6)
    ]
    run = _written(tmp_path / "run", captures)
    paths = plot.figures("adc", [run], ["noise_rate"], backend="web", out_dir=tmp_path / "out")
    assert sorted(path.stem for path in paths) == sorted(f"noise_rate_board7_channel0_{c.sweep}" for c in captures[::3])
    for path, sweep in zip(sorted(paths), sorted({c.sweep: c for c in captures}.items()), strict=True):
        expected = plots.plot_noise_rate([analyze_noise(c) for c in captures if c.sweep == sweep[0]])
        assert json.loads(path.read_text()) == json.loads(json.dumps(expected.to_json()))


def test_the_interferer_search_takes_each_sweep_of_a_campaign(tmp_path: Path) -> None:
    """The alias search over one sequence's rates (``analyze_interferer`` of their code spectra), a
    figure a sequence: a campaign of two never mixes its sequences' lines."""
    import json

    from flow import plot

    shown = Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC10000111.rows
    other = Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111.rows
    captures = [
        _captured(tone_codes(rate, tone_hz=tone, count=4096, seed=seed), rate=rate, rows=rows)
        for rows, tone in ((shown, 8.15e6), (other, 7.143e6))
        for seed, rate in enumerate((2e6, 6e6, 10e6))
    ]
    run = _written(tmp_path / "run", captures)
    paths = plot.figures("adc", [run], ["interferer"], backend="web", out_dir=tmp_path / "out")
    assert len(paths) == 2
    path = tmp_path / "out" / f"interferer_board7_channel0_{captures[0].sweep}.json"
    expected = plots.plot_interferer(analyze_interferer([analyze_code_spectrum(c) for c in captures[:3]]))
    assert json.loads(path.read_text()) == json.loads(json.dumps(plot._finite(expected.to_json())))
    assert expected.x_markers[0].at == pytest.approx(8.15e6, rel=1e-3)


def test_a_chips_sequence_maps_are_each_adcs_and_its_adcs_together(tmp_path: Path) -> None:
    """The operating conditions over sequence and rate as maps: each ADC's, and its board's ADCs'
    together (``analyze_sequence_map`` of every channel's conditions)."""
    import json

    from flow import plot

    captures = [
        _captured([1000, 1001, 1002, 1001] * 25, rate=rate, rows=rows, observed_adc=adc)
        for adc in (0, 1)
        for rate in (1e6, 2e6)
        for rows in timing_sequences[:3]
    ]
    run = _written(tmp_path / "run", captures)
    paths = plot.figures("adc", [run], ["sequence_enob"], backend="web", out_dir=tmp_path / "out")
    assert sorted(path.stem for path in paths) == [
        "sequence_enob_board7",
        "sequence_enob_board7_channel0",
        "sequence_enob_board7_channel1",
    ]
    board = json.loads((tmp_path / "out/sequence_enob_board7.json").read_text())
    assert board["title"] == plots.plot_sequence_enob(analyze_sequence_map([adc_conditions(0, {})])).title


def test_every_figure_of_a_lab_tree_with_ramps_and_fixed_inputs(tmp_path: Path, capsys) -> None:
    """Every figure of a board's lab captures, a ramp and a fixed input's rate sweep: each analysis
    takes the captures of its kind and says why it draws nothing from the others; none of the
    simulation's analyses (of plain waves, ``pipeline.Meas``) is given a lab capture."""
    from flow import plot

    physical = [
        replace(capture, info=replace(capture.info, backend="physical"))
        for capture in (
            adc_ramp_measurement(),
            *(_captured([1000, 1001, 1002, 1001] * 25, rate=rate, rows=timing_sequences[0]) for rate in (1e6, 2e6)),
        )
    ]
    paths = plot.figures("adc", [_written(tmp_path / "run", physical)], backend="web", out_dir=tmp_path / "out")
    drawn = {path.stem.split("_board")[0] for path in paths}
    assert {"ramp_transfer", "inl", "noise_rate", "codes_rate"} <= drawn
    printed = capsys.readouterr().out
    assert "analyze_ramp: ADC ramp analysis requires a PWL differential-input source" in printed
    assert "analyze_mismatch: the mismatch statistics take a behavioral capture" in printed


def test_a_ramps_calibrations_and_its_codes_decoded_by_each(tmp_path: Path, capsys) -> None:
    """A ramp's calibrations, a figure each (the analyses giving one of ``AnalysisCalibration``'s
    kinds: calibration 1 wants the DAC's curves, calibration 3 a noisy ramp, so this one's draws
    calibration 2 alone and says why the others are not drawn); with ``priors``, its codes decoded
    by each calibration it gives instead of the design's weights."""
    from flow import plot
    from flow.analysis.io import write_measurement

    ramp = adc_ramp_measurement()
    write_measurement(tmp_path / "run/0000_ramp.h5", ramp)
    (weights,) = plot.figures("adc", [tmp_path / "run"], ["calibration_weights"], out_dir=tmp_path / "w")
    assert weights.stem == "calibration_weights_board7_channel0_calibration2_0000_ramp"
    assert "analyze_calibration3: threshold fit requires" in capsys.readouterr().out
    (design,) = plot.figures("adc", [tmp_path / "run"], ["inl"], backend="web", out_dir=tmp_path / "d")
    (decoded,) = plot.figures(
        "adc", [tmp_path / "run"], ["inl_calibrated"], backend="web", out_dir=tmp_path / "c", priors=True
    )
    assert design.stem == "inl_board7_channel0_0000_ramp"
    assert decoded.stem == "inl_calibrated_board7_channel0_0000_ramp_calibration2"
    with pytest.raises(ValueError, match="no figure sampling_noise of adc from these captures"):
        plot.figures("adc", [tmp_path / "run"], ["sampling_noise"], out_dir=tmp_path / "x")
