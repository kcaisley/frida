"""The ADC's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
first a characterization's details, which the viewer shows in the order they are written here (the
record's, ``flow.adc.search.record``), then the figures only the lab studies draw. Each is one curve
(one series, or one family of decision paths), or one map, so instances compared on one plot stay
readable; what a second curve would add is a figure of its own. The decision-path density is its
paths, each distinct one with how many conversions took it (``Plot.paths``): the whole conversion,
its last decisions, and where the conversions at one input end. Every value is written to six
significant digits, as the viewer's other exports. The same specs draw the lab captures, a study's
figures (``python -m flow.plot adc <captures>``, ``flow.plot.figures``; a scan's test),
a figure a decoding, calibration, capture or sweep, each named by its weights, its rate or its
sequence.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import numpy as np

from flow.pipeline import Band, Heatmap, Marker, Plot, plot

from .params import CDAC_SETTLING_TOLERANCE_V, FINAL_DECISIONS, LADDER, MAX_PATHS, TbParams
from .types import (
    AnalysisCalibration,
    AnalysisCdacSettling,
    AnalysisCodeSpectrum,
    AnalysisDecisionPaths,
    AnalysisDynamic,
    AnalysisEnergy,
    AnalysisHsu,
    AnalysisInputNoise,
    AnalysisInterferer,
    AnalysisLadder,
    AnalysisMismatchPrediction,
    AnalysisNoise,
    AnalysisPower,
    AnalysisPowerWaveform,
    AnalysisRamp,
    AnalysisRedundancy,
    AnalysisReference,
    AnalysisSamplingNoise,
    AnalysisSequenceMap,
    AnalysisSequencer,
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
    title, and the bins standing clearly above the floor (lines: an interferer, a wandering hump)
    shaded at their full resolution. A stuck capture (one code) has no floor: no curve on the log
    axes, and neither floor nor lines."""
    frequency_hz, density = _log_binned(spectrum.frequency_hz, spectrum.asd_v_per_sqrt_hz)
    half_bin_hz = spectrum.bin_hz / 2
    floor_v = math.sqrt(spectrum.white_floor_lsb2_per_hz) * spectrum.input_lsb_v
    split = (
        f": {spectrum.total_rms_lsb:.2f} LSB rms = lines {spectrum.narrowband_rms_lsb:.2f}"
        f" ⊕ white {spectrum.broadband_rms_lsb:.2f}"
    )
    return _plot(
        "noise_spectrum",
        f"Output-code noise{split if spectrum.spectrum_valid else ''}",
        "Frequency (Hz)",
        "Input-referred noise (V/√Hz)",
        frequency_hz,
        {"Output code": density},
        x_log=True,
        y_log=True,
        y_markers=[Marker(_six(floor_v), "White floor")] if spectrum.spectrum_valid else [],
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
    """Each stage's capacitor weight sigma at the assumed matching (``UNIT_MISMATCH``)."""
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
    """The DNL sigma at each stage's transition at the assumed matching."""
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
    """Each stage's redundancy margin over its mismatch sigma at the assumed matching."""
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


# ---- the lab studies' figures (the figures step over captures, the scans' tests), none of them the record's: each
# from the results of its captures, one curve or one map as the record's


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


@plot
def plot_sequence_enob(sequences: AnalysisSequenceMap) -> Plot:
    """A fixed input's noise-equivalent ENOB over sequence and symbol rate (``AnalysisSequenceMap``):
    one ADC's where its codes are plausible, a chip's median where three quarters of its ADCs' are;
    every other cell empty."""
    return _sequence_map(
        "sequence_enob", "Noise-equivalent ENOB by sequence and rate", sequences, sequences.enob_bits, "ENOB (bits)"
    )


@plot
def plot_sequence_plausible(sequences: AnalysisSequenceMap) -> Plot:
    """How many of the ADCs give plausible codes at each sequence and symbol rate (one ADC: 1 or 0):
    a code not constant, its mean near the reference, its readout valid."""
    return _sequence_map(
        "sequence_plausible",
        "ADCs with plausible codes by sequence and rate",
        sequences,
        sequences.plausible_count,
        f"Plausible ADCs (of {sequences.adc_count})",
    )


@plot
def plot_sequence_shift(sequences: AnalysisSequenceMap) -> Plot:
    """How far the mean code moves from its reference (each ADC's median over every sequence at the
    slowest rate) at each sequence and symbol rate: the ADCs' median."""
    return _sequence_map(
        "sequence_shift",
        "Mean-code shift by sequence and rate",
        sequences,
        sequences.shift_dout,
        "|Mean code − reference| (LSB)",
    )


@plot
def plot_noise_rate(noises: Sequence[AnalysisNoise]) -> Plot:
    """A fixed input's output-code noise over the conversion rate (the captures of one sequence, in
    rate order), referred to the input through each capture's LSB; none where the code stays
    constant (its noise under what the codes resolve)."""
    return _plot(
        "noise_rate",
        "Fixed-input noise over the conversion rate",
        "Conversion rate (Hz)",
        "Input-referred noise, rms (V)",
        [noise.sample_rate_hz for noise in noises],
        {_sequences_label(noises): [noise.input_referred_noise_rms_v for noise in noises]},
    )


@plot
def plot_noise_enob_rate(noises: Sequence[AnalysisNoise]) -> Plot:
    """The noise-equivalent ENOB of those captures (a full-scale sine's, with the fixed input's noise
    alone), as ``plot_noise_rate`` takes them."""
    return _plot(
        "noise_enob_rate",
        "Noise-equivalent ENOB over the conversion rate",
        "Conversion rate (Hz)",
        "ENOB (bits)",
        [noise.sample_rate_hz for noise in noises],
        {_sequences_label(noises): [noise.enob_bits for noise in noises]},
    )


@plot
def plot_codes_rate(noises: Sequence[AnalysisNoise]) -> Plot:
    """A fixed input's output codes over the conversion rate (the captures of one sequence, in rate
    order, one at a rate): each code's share of a capture's conversions, a column a capture reaching
    halfway to its neighbours, by decade, from two codes under the lowest any capture reaches to two
    over the highest; the mean code over it."""
    rates = np.asarray([noise.sample_rate_hz for noise in noises], dtype=np.float64)
    if np.any(np.diff(rates) <= 0) or len({len(noise.code) for noise in noises}) != 1:
        raise ValueError("the codes over the rate take captures of one resolution in rate order, one at a rate")
    counts = np.asarray([noise.count for noise in noises], dtype=np.float64)
    shares = counts / counts.sum(axis=1, keepdims=True)
    populated = np.flatnonzero(counts.sum(axis=0) > 0)
    first, last = max(int(populated[0]) - 2, 0), min(int(populated[-1]) + 2, counts.shape[1] - 1)
    codes = np.asarray(noises[0].code[first : last + 1], dtype=np.float64)
    return _plot(
        "codes_rate",
        "Fixed-input output codes over the conversion rate",
        "Conversion rate (Hz)",
        "Output code (LSB)",
        rates,
        {"Mean code": [noise.mean_dout for noise in noises]},
        y_ticks="code",
        heatmap=Heatmap(
            x=[_six(edge) for edge in _cells(rates)],
            y=[*(code - 0.5 for code in codes.tolist()), float(codes[-1]) + 0.5],
            z=[[_six(share) if share > 0 else math.nan for share in row] for row in shares[:, first : last + 1].T],
            label="Share of conversions",
            log=True,
        ),
    )


@plot
def plot_interferer(interferer: AnalysisInterferer) -> Plot:
    """How well each candidate frequency of one interferer explains the code spectra's lines at every
    rate (``analyze_interferer``: its aliases' height over each spectrum's floor, summed over the
    rates), the best candidate marked; its many candidates thinned to the highest of each of 2000
    runs of them (``_peaks``), so a line keeps its peak."""
    frequency_hz, score_db = _peaks(interferer.candidate_frequency_hz, interferer.score_db)
    found_hz = interferer.frequency_hz
    return _plot(
        "interferer",
        "Interferer frequency from its aliases",
        "Candidate frequency (Hz)",
        "Lines over floor, summed (dB)",
        frequency_hz,
        {"Score": score_db},
        x_markers=[Marker(_six(found_hz), f"{found_hz / 1e6:.3f} MHz")],
    )


@plot
def plot_interferer_lines(interferer: AnalysisInterferer) -> Plot:
    """The strongest line of the code spectra at each rate (``analyze_interferer``'s observed peak, the
    median over a rate's captures): where the interferer's alias lands at that rate."""
    return _plot(
        "interferer_lines",
        "Strongest code-spectrum line at each rate",
        "Conversion rate (Hz)",
        "Line frequency (Hz)",
        interferer.sample_rate_hz,
        {"Strongest line": interferer.observed_peak_hz},
    )


@plot
def plot_sampling_noise(sampling: AnalysisSamplingNoise) -> Plot:
    """The held differential voltage 1 ns after SAMP falls, about its mean (``analyze_sampling_noise``:
    not kT/C alone, the comparator may already act), a histogram of 25 µV bins, every capture's
    alike so compared ones overlay; its spread (the sample's) and its count in the curve's name."""
    error_v = np.asarray(sampling.held_diff_v, dtype=np.float64) - float(np.mean(sampling.held_diff_v))
    centres_v, shares = _histogram(error_v, 25e-6)
    return _plot(
        "sampling_noise",
        "Held voltage 1 ns after SAMP falls",
        "VDAC_P − VDAC_N about its mean (V)",
        "Share of conversions",
        centres_v,
        {f"σ {sampling.sigma_v * 1e6:.1f} µV, {len(error_v)} conversions": shares},
        histogram=True,
    )


@plot
def plot_cdac_settling_first(settling: AnalysisCdacSettling) -> Plot:
    """The top plates' settling after the first stage's update (``analyze_cdac_settling``), as
    ``_settling`` draws a stage's."""
    return _settling("cdac_settling_first", settling, 0)


@plot
def plot_cdac_settling_middle(settling: AnalysisCdacSettling) -> Plot:
    """The top plates' settling after the middle stage's update."""
    return _settling("cdac_settling_middle", settling, 1)


@plot
def plot_cdac_settling_last(settling: AnalysisCdacSettling) -> Plot:
    """The top plates' settling after the last stage's update."""
    return _settling("cdac_settling_last", settling, 2)


@plot
def plot_power_analog(waveform: AnalysisPowerWaveform) -> Plot:
    """The analog supply's (VDD_A's) power over one simulated conversion, as ``_power`` draws a rail's."""
    return _power("power_analog", waveform, 0, "VDD_A")


@plot
def plot_power_digital(waveform: AnalysisPowerWaveform) -> Plot:
    """The digital supply's (VDD_D's) power over one simulated conversion."""
    return _power("power_digital", waveform, 1, "VDD_D")


@plot
def plot_power_dac(waveform: AnalysisPowerWaveform) -> Plot:
    """The DAC reference's (VDD_DAC's) power over one simulated conversion."""
    return _power("power_dac", waveform, 2, "VDD_DAC")


@plot
def plot_sequencer(sequencer: AnalysisSequencer) -> Plot:
    """The sequencer's outputs over one period from INIT's rise (``analyze_sequencer``), a row each
    with INIT on top and a cell a symbol, high where it is 1: a capture's timing diagram."""
    period_s = 1.0 / sequencer.symbol_rate_hz
    symbols = sequencer.high.shape[1]
    return Plot(
        "sequencer",
        "Sequencer outputs over one period",
        "Time from INIT's rise (s)",
        "Sequencer output",
        [],
        {},
        y_labels=["LOGIC", "COMP", "SAMP", "INIT"],
        heatmap=Heatmap(
            x=[_six(symbol * period_s) for symbol in range(symbols + 1)],
            y=[row - 0.5 for row in range(5)],
            z=[[1.0 if high else 0.0 for high in sequencer.high[row]] for row in (3, 2, 1, 0)],
            label="High",
        ),
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


def _peaks(x: np.ndarray, y: np.ndarray, runs: int = 2000) -> tuple[list[float], list[float]]:
    """A long curve thinned to its highest point in each of ``runs`` equal runs of its points (every
    point where it has no more), so a narrow peak keeps its height and place."""
    if len(x) <= runs:
        return np.asarray(x).tolist(), np.asarray(y).tolist()
    edges = np.linspace(0, len(x), runs + 1).astype(np.int64)
    picks = [start + int(np.argmax(y[start:stop])) for start, stop in pairwise(edges)]
    return np.asarray(x)[picks].tolist(), np.asarray(y)[picks].tolist()


def _power(name: str, waveform: AnalysisPowerWaveform, rail: int, supply: str) -> Plot:
    """One rail's instantaneous power from INIT's rise over one conversion (``analyze_power_waveform``,
    its ``rail``-th: VDD_A, VDD_D, VDD_DAC), its static and active averages marked and the sampling
    phase (SAMP high) shaded; the rest of the timing is ``plot_sequencer``'s."""
    time_s = np.asarray(waveform.time_s, dtype=np.float64)
    phases = [
        Band(_six(time_s[first]), _six(time_s[last]), "SAMP")
        for first, last in _runs(np.asarray(waveform.samp_high, dtype=np.bool_))
    ]
    return _plot(
        name,
        f"{supply} power over one conversion",
        "Time from INIT's rise (s)",
        "Power (W)",
        time_s,
        {supply: waveform.rail_power_w[rail]},
        y_markers=[
            Marker(_six(waveform.static_power_w[rail]), "Static average"),
            Marker(_six(waveform.active_power_w[rail]), "Active average"),
        ],
        x_bands=phases,
    )


def _settling(name: str, settling: AnalysisCdacSettling, position: int) -> Plot:
    """The top plates' settling at the stage the analysis aligns in ``position`` (0, 1 and 2: its
    first, middle and last), each conversion's |VDAC_P - VDAC_N - their settled difference| a path
    over the time from the stage's comparator clock, on a log axis (an exponential settling a
    straight line there), the band a plate settles to marked. Drawn down to a thousandth of the
    band: below it the plates are settled far within it, and where the difference crosses its
    settled value it would dip without end."""
    stages = list(dict.fromkeys(int(stage) for stage in settling.stage_index))
    stage = stages[min(position, len(stages) - 1)]
    rows = np.asarray(settling.stage_index) == stage
    error = np.abs(
        np.asarray(settling.vdac_p_settling_error_v)[rows] - np.asarray(settling.vdac_n_settling_error_v)[rows]
    )
    floor_v = CDAC_SETTLING_TOLERANCE_V / 1000
    return Plot(
        name,
        f"Top-plate settling of C{stage}'s update",
        "Time from the comparator clock (s)",
        "Differential settling error (V)",
        [_six(value) for value in settling.time_s],
        {},
        paths=[{"y": [_six(value) if value >= floor_v else math.nan for value in row], "count": 1} for row in error],
        y_log=True,
        y_markers=[Marker(CDAC_SETTLING_TOLERANCE_V, f"{CDAC_SETTLING_TOLERANCE_V * 1e3:g} mV: a plate settled")],
    )


def _histogram(values: np.ndarray, width: float) -> tuple[list[float], list[float]]:
    """``values`` counted in bins ``width`` wide on its multiples, each bin's share of them, an empty
    bin either side (the outline closes on the axis): the bins' centres and shares."""
    low = math.floor(float(np.min(values)) / width) - 1
    high = math.floor(float(np.max(values)) / width) + 1
    edges = np.arange(low, high + 2) * width
    counts, _ = np.histogram(values, bins=edges)
    return ((edges[:-1] + edges[1:]) / 2).tolist(), (counts / len(values)).tolist()


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


def _sequence_map(name: str, title: str, sequences: AnalysisSequenceMap, values: np.ndarray, label: str) -> Plot:
    """A map over sequence (a column each, named by its decision word) and symbol rate (a row each,
    the slowest at the bottom), its values to six significant digits."""
    columns, rows = len(sequences.sequence), len(sequences.symbol_rate_hz)
    return Plot(
        name,
        title,
        "Sequence (COMP / LOGIC decision word)",
        "Symbol rate",
        [],
        {},
        x_labels=_sequence_labels(sequences.sequence),
        y_labels=[f"{rate / 1e6:g} MBd" for rate in sequences.symbol_rate_hz],
        heatmap=Heatmap(
            x=[index - 0.5 for index in range(columns + 1)],
            y=[index - 0.5 for index in range(rows + 1)],
            z=[[_six(value) for value in row] for row in np.asarray(values, dtype=np.float64)],
            label=label,
        ),
    )


def _sequences_label(noises: Sequence[AnalysisNoise]) -> str:
    """A curve's name: the captures' sequence by its decision word (``_sequence_label``), where they
    share one (at any INIT phase), or else ``Fixed input``."""
    words = {_sequence_label(noise.sequence) for noise in noises}
    return f"Sequence {words.pop()}" if len(words) == 1 else "Fixed input"


def _cells(centres: np.ndarray) -> list[float]:
    """The edges of cells around ascending ``centres``: halfway between neighbours, the outer ones as
    far out as their inner half-gap (a tenth of a lone centre either side), none below 0."""
    if len(centres) == 1:
        return [0.9 * float(centres[0]), 1.1 * float(centres[0])]
    middles = (centres[1:] + centres[:-1]) / 2
    low = max(float(2 * centres[0] - middles[0]), 0.0)
    return [low, *middles.tolist(), float(2 * centres[-1] - middles[-1])]


def _sequence_labels(sequences: Sequence[tuple[str, ...]]) -> list[str]:
    """Each sequence by its decision word (``_sequence_label``); where two share one (another period,
    INIT or SAMP), each numbered as well."""
    labels = [_sequence_label(sequence) for sequence in sequences]
    if len(set(labels)) < len(labels):
        return [f"{index + 1}: {label}" for index, label in enumerate(labels)]
    return labels


def _sequence_label(rows: tuple[str, ...]) -> str:
    """A sequence (its rows, INIT, SAMP, COMP, LOGIC) by its decision word: COMP's and LOGIC's
    symbols from its second COMP rise after INIT to its third (the first decision has no update
    before it), ``11110000/00001111``, as the recipes name it (``comp11110000_logic00001111``,
    ``flow.adc.params.Recipe``)."""
    _, _, comp, logic = TbParams.from_init(rows)
    rises = [index for index in range(1, len(comp)) if comp[index] == "1" and comp[index - 1] == "0"]
    if len(rises) < 2:
        return f"{comp}/{logic}"
    start = rises[1]
    stop = rises[2] if len(rises) > 2 else start + 8
    return f"{comp[start:stop]}/{logic[start:stop]}"
