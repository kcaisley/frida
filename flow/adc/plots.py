"""The ADC's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
first a characterization's details, which the viewer shows in the order they are written here (the
record's, ``flow.adc.sweep.record``), then the figures only the lab studies draw. Each is one curve
(one series, or one family of decision paths), or one map, so instances compared on one plot stay
readable; what a second curve would add is a figure of its own. The decision-path density is its
paths, each distinct one with how many conversions took it (``Plot.paths``): the whole conversion,
its last decisions, and where the conversions at one input end. Every value is written to six
significant digits, as the viewer's other exports. The same specs draw the lab captures: a study
(``flow.adc.targets``, a scan's test) renders those of its captures' results with
``flow.plot.render``, a figure a decoding, calibration, capture or group of captures, each named by
its weights, its rate or its sequence.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from flow.pipeline import Band, Marker, Plot, plot

from .params import FINAL_DECISIONS, LADDER, MAX_PATHS
from .types import (
    AnalysisCalibration,
    AnalysisCodeSpectrum,
    AnalysisDecisionPaths,
    AnalysisDynamic,
    AnalysisEnergy,
    AnalysisHsu,
    AnalysisInputNoise,
    AnalysisLadder,
    AnalysisMismatchPrediction,
    AnalysisPower,
    AnalysisRamp,
    AnalysisRedundancy,
    AnalysisReference,
    AnalysisTransfer,
)


@plot
def plot_redundancy(redundancy: AnalysisRedundancy) -> Plot:
    """Each stage's error tolerance with the design weights."""
    return _plot(
        "redundancy",
        "Error tolerance by stage",
        "Conversion stage (C0 first)",
        "Error tolerance (%)",
        range(len(redundancy.design_pct)),
        {"Design weights": redundancy.design_pct},
        x_ticks="step",
    )


@plot
def plot_code_density(ramp: AnalysisRamp) -> Plot:
    """The ramp's code density, named by the weights that decoded it (the record's: the design
    weights; a lab study's: each decoding it compares): a histogram, a bin a code (a step outline,
    so compared instances overlay)."""
    code = np.asarray(ramp.code, dtype=np.int64)
    graded = (code >= ramp.linearity_code.min()) & (code <= ramp.linearity_code.max())
    return _plot(
        "code_density",
        "Ramp code density",
        "Output code",
        "Code width (count / ideal)",
        *_by_code(_decoding_label(ramp.decoding), ramp, code[graded], ramp.count[graded] / ramp.ideal_count),
        x_ticks="code",
        histogram=True,
    )


@plot
def plot_inl(ramp: AnalysisRamp) -> Plot:
    """The ramp's INL with the design weights (decoded otherwise: ``plot_inl_calibrated``)."""
    return _plot(
        "inl",
        "Ramp INL, design weights",
        "Output code",
        "INL (LSB)",
        *_by_code(_decoding_label(ramp.decoding), ramp, ramp.linearity_code, ramp.inl),
        x_ticks="code",
    )


@plot
def plot_inl_calibrated(ramp: AnalysisRamp) -> Plot:
    """The ramp's INL decoded by other weights than the design's, named by them (the record's: the
    calibration that grades it best; a lab study's: the extracted weights and each calibration)."""
    return _plot(
        "inl_calibrated",
        "Ramp INL, calibrated",
        "Output code",
        "INL (LSB)",
        *_by_code(_decoding_label(ramp.decoding), ramp, ramp.linearity_code, ramp.inl),
        x_ticks="code",
    )


@plot
def plot_dnl(ramp: AnalysisRamp) -> Plot:
    """The ramp's DNL with the design weights (decoded otherwise: ``plot_dnl_calibrated``)."""
    return _plot(
        "dnl",
        "Ramp DNL, design weights",
        "Output code",
        "DNL (LSB)",
        *_by_code(_decoding_label(ramp.decoding), ramp, ramp.linearity_code, ramp.dnl),
        x_ticks="code",
    )


@plot
def plot_dnl_calibrated(ramp: AnalysisRamp) -> Plot:
    """The ramp's DNL decoded by other weights than the design's, as ``plot_inl_calibrated``."""
    return _plot(
        "dnl_calibrated",
        "Ramp DNL, calibrated",
        "Output code",
        "DNL (LSB)",
        *_by_code(_decoding_label(ramp.decoding), ramp, ramp.linearity_code, ramp.dnl),
        x_ticks="code",
    )


@plot
def plot_trajectory(paths: AnalysisDecisionPaths) -> Plot:
    """The decision paths at one input, over the whole conversion: every distinct path of running
    code estimates, with how many conversions took it."""
    estimates = np.round(np.asarray(paths.estimate_dout, dtype=np.float64), 6)
    steps = estimates.shape[1]
    # decisions are steps, the estimates codes: whole-number ticks on both
    return Plot(
        "trajectory",
        "Decision paths at one input",
        "Decisions made",
        "Code estimate (LSB)",
        list(range(steps)),
        {},
        paths=_family(estimates, 0),
        x_ticks="step",
        y_ticks="code",
    )


@plot
def plot_trajectory_final(paths: AnalysisDecisionPaths) -> Plot:
    """The decision paths over the last decisions (``FINAL_DECISIONS``), where noise splits them."""
    estimates = np.round(np.asarray(paths.estimate_dout, dtype=np.float64), 6)
    steps = estimates.shape[1]
    first = max(steps - 1 - FINAL_DECISIONS, 0)
    return Plot(
        "trajectory_final",
        "Decision paths: the last decisions",
        "Decisions made",
        "Code estimate (LSB)",
        list(range(first, steps)),
        {},
        paths=_family(estimates, first),
        x_ticks="step",
        y_ticks="code",
    )


@plot
def plot_trajectory_codes(paths: AnalysisDecisionPaths) -> Plot:
    """The histogram of the codes the decision paths end on, a bin a code and two empty ones either
    side (the outline closes on the axis), their mean and spread in the curve's name: on one code
    alone, a spread under a code, which the codes cannot resolve (not none)."""
    final = np.asarray(paths.final_dout, dtype=np.float64)
    mean, sigma = float(np.mean(final)), float(np.std(final))
    codes = np.arange(math.floor(final.min()) - 2, math.ceil(final.max()) + 3)
    counts = np.array([np.count_nonzero(final == code) for code in codes], dtype=np.float64)
    spread = "one code: σ under 1 LSB" if np.count_nonzero(counts) == 1 else f"σ {sigma:.2f} LSB"
    return Plot(
        "trajectory_codes",
        "Output codes at one input",
        "Output code",
        "Conversions",
        [float(code) for code in codes],
        {f"Conversions (mean {mean:.2f}, {spread})": [float(count) for count in counts]},
        x_ticks="code",
        y_ticks="integer",
        histogram=True,
    )


@plot
def plot_noise_spectrum(spectrum: AnalysisCodeSpectrum) -> Plot:
    """The output code's noise density at a fixed input, referred to the input through the capture's
    LSB (the unit a probe's spectrum shares) and averaged in power over log-spaced bins; its white
    floor (the density's median) marked, the variance's split (total = lines ⊕ broadband) in the
    floor's label, and the bins standing clearly above the floor (lines: an interferer, a wandering
    hump) shaded at their full resolution. A stuck capture (one code) has no floor: no curve on the
    log axes, and neither floor nor lines."""
    frequency_hz, density = _log_binned(spectrum.frequency_hz, spectrum.asd_v_per_sqrt_hz)
    half_bin_hz = spectrum.bin_hz / 2
    floor_v = math.sqrt(spectrum.white_floor_lsb2_per_hz) * spectrum.input_lsb_v
    split = (
        f"White floor; total {spectrum.total_rms_lsb:.2f} = lines {spectrum.narrowband_rms_lsb:.2f}"
        f" ⊕ broadband {spectrum.broadband_rms_lsb:.2f} LSB rms"
    )
    return _plot(
        "noise_spectrum",
        "Output-code noise density",
        "Frequency (Hz)",
        "Input-referred noise (V/√Hz)",
        frequency_hz,
        {"Output code": density},
        x_log=True,
        y_log=True,
        y_markers=[Marker(_six(floor_v), split)] if spectrum.spectrum_valid else [],
        x_bands=[
            Band(_six(spectrum.frequency_hz[first] - half_bin_hz), _six(spectrum.frequency_hz[last] + half_bin_hz))
            for first, last in _runs(spectrum.line_mask)
        ],
    )


@plot
def plot_noise_input(noise: AnalysisInputNoise) -> Plot:
    """The output code's noise over the input: the record's staircase, or a lab study's DC steps."""
    return _plot(
        "noise_input",
        "Output noise over the input",
        "Differential input (V)",
        "Output noise (LSB rms)",
        noise.level_v,
        {"Noise": noise.sigma_lsb},
    )


@plot
def plot_enob_rate(dynamics: Sequence[AnalysisDynamic]) -> Plot:
    """The ENOB over the conversion rate (its sines in rate order). Every ENOB here is the spectral
    one referred to full scale (an ideal N-bit quantizer reads N, whatever the sine's amplitude),
    none where the output no longer follows the input (SNDR under 1.76 dB): a point there would only
    stretch the axis."""
    return _plot(
        "enob_rate",
        "ENOB over the conversion rate",
        "Conversion rate (Hz)",
        "ENOB (bits)",
        [dynamic.sample_rate_hz for dynamic in dynamics],
        {"ENOB": [_enob(dynamic) for dynamic in dynamics]},
        x_log=True,
    )


@plot
def plot_enob_fin(dynamics: Sequence[AnalysisDynamic]) -> Plot:
    """The ENOB over the input frequency at one rate (its sines in frequency order; the record's:
    the nominal rate), as ``plot_enob_rate`` gives it."""
    return _plot(
        "enob_fin",
        f"ENOB over the input frequency at {_rate(dynamics[0].sample_rate_hz)}",
        "Input frequency / conversion rate",
        "ENOB (bits)",
        [dynamic.input_frequency_hz / dynamic.sample_rate_hz for dynamic in dynamics],
        {"ENOB": [_enob(dynamic) for dynamic in dynamics]},
    )


@plot
def plot_enob_ladder(ladder: AnalysisLadder) -> Plot:
    """The ENOB ladder: the nominal rate's sine with one impairment more a step, ticked by their
    names (``LADDER``)."""
    return _plot(
        "enob_ladder",
        "ENOB as impairments are added",
        "Impairment added",
        "ENOB (bits)",
        range(len(LADDER)),
        {"ENOB": ladder.enob_bits},
        x_labels=[label for _, label, _, _ in LADDER],
    )


@plot
def plot_spectrum_low(dynamic: AnalysisDynamic) -> Plot:
    """The spectrum of a sine at a low input frequency (the record's: the nominal rate's lowest),
    its rate in the title."""
    return _plot(
        "spectrum_low",
        f"Spectrum at {_rate(dynamic.sample_rate_hz)}, low input frequency",
        "Frequency (Hz)",
        "Power (dBFS)",
        dynamic.spectrum_frequency_hz,
        {f"{dynamic.input_frequency_hz / 1e6:.3g} MHz input": dynamic.spectrum_dbfs},
    )


@plot
def plot_spectrum_nyquist(dynamic: AnalysisDynamic) -> Plot:
    """The spectrum of a sine near Nyquist (the record's: the nominal rate's highest input
    frequency), its rate in the title."""
    return _plot(
        "spectrum_nyquist",
        f"Spectrum at {_rate(dynamic.sample_rate_hz)}, input near Nyquist",
        "Frequency (Hz)",
        "Power (dBFS)",
        dynamic.spectrum_frequency_hz,
        {f"{dynamic.input_frequency_hz / 1e6:.3g} MHz input": dynamic.spectrum_dbfs},
    )


@plot
def plot_hsu_rate(hsu: AnalysisHsu) -> Plot:
    """Hsu's study (A. H. T. Chang, MIT PhD thesis 2013, sec. 3.3.3): every code centre once,
    noise-free, at each rate with the array's own settling; the integrated |code - ideal timing's|."""
    return _plot(
        "hsu_rate",
        "Integrated error over the conversion rate",
        "Conversion rate (Hz)",
        "Integrated error (LSB)",
        hsu.rate_hz,
        {"Integrated error": hsu.integrated_error_lsb},
    )


@plot
def plot_power_rate(powers: Sequence[AnalysisPower]) -> Plot:
    """The supply power over the conversion rate (its captures in rate order)."""
    return _plot(
        "power_rate",
        "Supply power over the conversion rate",
        "Conversion rate (Hz)",
        "Supply power (W)",
        [power.sample_rate_hz for power in powers],
        {"Total": [power.total_power_w for power in powers]},
        x_log=True,
        y_log=True,
    )


@plot
def plot_energy_input(energy: AnalysisEnergy) -> Plot:
    """The energy a conversion takes over the input, every rail."""
    return _plot(
        "energy_input",
        "Energy per conversion over the input",
        "Differential input (V)",
        "Energy per conversion (J)",
        energy.vin_diff_v,
        {"Total": energy.total_energy_j},
    )


@plot
def plot_energy_dac_input(energy: AnalysisEnergy) -> Plot:
    """The DAC reference's (VDD_DAC's) share of it."""
    return _plot(
        "energy_dac_input",
        "DAC energy per conversion over the input",
        "Differential input (V)",
        "Energy per conversion (J)",
        energy.vin_diff_v,
        {"VDD_DAC": energy.vdd_dac_energy_j},
    )


@plot
def plot_calibration_weights(calibration: AnalysisCalibration) -> Plot:
    """The weights' error against the design's, a decision each: the extracted array's (the
    record's) or a calibration's (a lab study's), named by its weights; the decisions whose weight
    was not measured but kept at the design's ratios shaded (the terminal decision, a calibration's
    unresolved tail)."""
    label = _decoding_label(calibration.method)
    unmeasured = _runs(~np.asarray(calibration.measured_weight_mask, dtype=bool))
    return _plot(
        "calibration_weights",
        "Weight error of the extracted array"
        if calibration.method == "extracted"
        else f"Weight error found by {label.lower()}",
        "Decision (B0 first)",
        "Weight error (%)",
        range(len(calibration.nominal_weights)),
        {label: 100.0 * (calibration.calibrated_weights / calibration.nominal_weights - 1.0)},
        x_ticks="step",
        x_bands=[
            Band(first - 0.5, last + 0.5, "Not measured" if index == 0 else "")
            for index, (first, last) in enumerate(unmeasured)
        ],
    )


@plot
def plot_mismatch_weight_sigma(prediction: AnalysisMismatchPrediction) -> Plot:
    """Each stage's capacitor weight sigma at Harpe's matching."""
    return _plot(
        "mismatch_weight_sigma",
        "Capacitor weight σ by stage",
        "Conversion stage (C0 first)",
        "Weight σ (LSB)",
        range(len(prediction.weight_sigma_lsb)),
        {_matching_label(prediction): prediction.weight_sigma_lsb},
        x_ticks="step",
    )


@plot
def plot_mismatch_transition_sigma(prediction: AnalysisMismatchPrediction) -> Plot:
    """The DNL sigma at each stage's transition at Harpe's matching."""
    return _plot(
        "mismatch_transition_sigma",
        "DNL σ at each stage's transition",
        "Conversion stage (C0 first)",
        "DNL σ (LSB)",
        range(len(prediction.transition_sigma_lsb)),
        {_matching_label(prediction): prediction.transition_sigma_lsb},
        x_ticks="step",
    )


@plot
def plot_mismatch_margin(prediction: AnalysisMismatchPrediction) -> Plot:
    """Each stage's redundancy margin over its mismatch sigma at Harpe's matching."""
    return _plot(
        "mismatch_margin",
        "Redundancy margin over its mismatch σ by stage",
        "Conversion stage (C0 first)",
        "Margin / σ",
        range(len(prediction.margin_over_sigma)),
        {_matching_label(prediction): prediction.margin_over_sigma},
        x_ticks="step",
    )


@plot
def plot_mismatch_dnl(prediction: AnalysisMismatchPrediction) -> Plot:
    """The worst DNL one converter in twenty sees over the matching, decoded with the design weights."""
    return _plot(
        "mismatch_dnl",
        "Worst DNL over the Pelgrom coefficient (predicted 95th percentile)",
        "Pelgrom coefficient A_C (%·sqrt(fF))",
        "Max |DNL| (LSB)",
        prediction.coefficient * 100,
        {"Design weights, 95th percentile": prediction.dnl_p95_lsb},
        x_log=True,
    )


@plot
def plot_mismatch_inl(prediction: AnalysisMismatchPrediction) -> Plot:
    """The worst INL one converter in twenty sees over the matching, decoded with the design weights."""
    return _plot(
        "mismatch_inl",
        "Worst INL over the Pelgrom coefficient (predicted 95th percentile)",
        "Pelgrom coefficient A_C (%·sqrt(fF))",
        "Max |INL| (LSB)",
        prediction.coefficient * 100,
        {"Design weights, 95th percentile": prediction.inl_p95_lsb},
        x_log=True,
    )


@plot
def plot_reference_noise(reference: AnalysisReference) -> Plot:
    """The ENOB the converter loses to its reference's white noise, its sampler and comparator ideal."""
    return _plot(
        "reference_noise",
        "ENOB lost to the reference's noise, sampler and comparator ideal",
        "Reference noise (V RMS)",
        "ENOB loss (bits)",
        reference.noise_v,
        {"ENOB loss": reference.noise_loss_bits},
        x_log=True,
    )


@plot
def plot_reference_r_out(reference: AnalysisReference) -> Plot:
    """The ENOB the converter loses to its reference driver's output resistance at its decoupling,
    its sampler and comparator ideal (the record draws it where the converter has decoupling)."""
    return _plot(
        "reference_r_out",
        "ENOB lost to the reference driver's resistance at its decoupling, sampler and comparator ideal",
        "Reference output resistance (Ω)",
        "ENOB loss (bits)",
        reference.r_out_ohm,
        {"ENOB loss": reference.r_out_loss_bits},
        x_log=True,
    )


# ---- the lab studies' figures (flow.adc.targets, the scans' tests), none of them the record's: each
# from the results of its captures, one curve each as the record's


@plot
def plot_transfer(transfer: AnalysisTransfer) -> Plot:
    """The static transfer of DC steps: the mean output code at each differential input (the codes'
    spread there is ``plot_noise_input``'s)."""
    return _plot(
        "transfer",
        "Static transfer",
        "Differential input (V)",
        "Mean output code (LSB)",
        transfer.vin_diff_v,
        {"Mean code": transfer.mean_dout},
        y_ticks="code",
    )


@plot
def plot_ramp_transfer(ramp: AnalysisRamp) -> Plot:
    """A ramp's transfer as its phase reconstructs it (``analyze_ramp``): the mean output code at
    each inferred input, named by the weights that decoded it (each decoding a figure, as the ramp's
    linearity)."""
    return _plot(
        "ramp_transfer",
        "Ramp transfer",
        "Inferred differential input (V)",
        "Mean output code (LSB)",
        ramp.transfer_vin_diff_v,
        {_decoding_label(ramp.decoding): ramp.transfer_mean_dout},
        y_ticks="code",
    )


def _plot(name: str, title: str, x_label: str, y_label: str, x, series: dict[str, Any], **options: Any) -> Plot:
    """A figure's spec, its values to six significant digits, as the viewer's other exports."""
    return Plot(
        name=name,
        title=title,
        x_label=x_label,
        y_label=y_label,
        x=[_six(value) for value in x],
        series={label: [_six(value) for value in ys] for label, ys in series.items()},
        **options,
    )


def _six(value: float) -> float:
    """``value`` to six significant digits (a spec's numbers, as the viewer's other exports)."""
    return float(f"{value:.6g}")


def _by_code(
    label: str, ramp: AnalysisRamp, code: np.ndarray, values: np.ndarray
) -> tuple[list[float], dict[str, list[float]]]:
    """``values`` at each ``code`` over the codes the ramp grades (its linearity codes, the clipped
    end codes left out as the linearity leaves them), NaN where it has none: the axis and the one
    series ``label``."""
    axis = np.arange(int(np.min(ramp.linearity_code)), int(np.max(ramp.linearity_code)) + 1)
    column = np.full(len(axis), np.nan)
    column[np.asarray(code, dtype=np.int64) - axis[0]] = values
    return axis.astype(float).tolist(), {label: column.tolist()}


def _decoding_label(decoding: str) -> str:
    """The name of the weights a decoding stands for (``AnalysisRamp.decoding``,
    ``AnalysisCalibration.method``): the design's, the extracted array's or a calibration's
    (``Calibration 2``)."""
    if decoding == "uncalibrated_dout":
        return "Design weights"
    if decoding == "extracted":
        return "Extracted weights"
    return f"Calibration {decoding.removeprefix('calibration')}"


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """The first and the last index of each run of True in ``mask``, in order."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], np.asarray(mask, dtype=np.int8), [0]))))
    return [(int(start), int(stop) - 1) for start, stop in zip(edges[::2], edges[1::2], strict=True)]


def _log_binned(frequency_hz: np.ndarray, density: np.ndarray, bins: int = 300) -> tuple[list[float], list[float]]:
    """A density averaged in power over log-spaced frequency bins (a spectrum's thousands of bins
    are more than a plot can show): the populated bins' geometric centres and values. A log bin no
    bin of the spectrum falls in (near DC, where they are finer than the spectrum's) is left out,
    not a gap, so the curve stays joined there in both renderers."""
    positive = frequency_hz > 0
    edges = np.geomspace(frequency_hz[positive].min(), frequency_hz.max() * (1 + 1e-9), bins + 1)
    index = np.digitize(frequency_hz, edges) - 1
    inside = positive & (index >= 0) & (index < bins)
    counts = np.bincount(index[inside], minlength=bins)
    power = np.bincount(index[inside], weights=density[inside] ** 2, minlength=bins)
    populated = counts > 0
    return np.sqrt(edges[:-1] * edges[1:])[populated].tolist(), np.sqrt(power[populated] / counts[populated]).tolist()


def _family(estimates: np.ndarray, first: int) -> list[dict[str, Any]]:
    """The distinct paths of running estimates from decision ``first`` on, each with how many
    conversions took it, the most taken first (at most ``MAX_PATHS``)."""
    unique, counts = np.unique(estimates[:, first:], axis=0, return_counts=True)
    order = np.argsort(-counts, kind="stable")[:MAX_PATHS]
    return [{"y": [float(f"{y:.6g}") for y in unique[i]], "count": int(counts[i])} for i in order]


def _rate(rate_hz: float) -> str:
    """A conversion rate as a title names it: ``10 MS/s``, ``0.3125 MS/s``."""
    return f"{rate_hz / 1e6:g} MS/s"


def _enob(dynamic: AnalysisDynamic) -> float:
    """A sine's spectral ENOB referred to full scale, NaN where its SNDR is under 1.76 dB."""
    return dynamic.spectral_enob_fs_bits if dynamic.spectral_sndr_db > 1.76 else math.nan


def _matching_label(prediction: AnalysisMismatchPrediction) -> str:
    """The predictions' series name: the Pelgrom coefficient they are at."""
    return f"A_C {prediction.unit_mismatch * 100:g} %·sqrt(fF)"
