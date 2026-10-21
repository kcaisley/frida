"""An ADC campaign's figures and metrics from its captures (``flow.adc.campaign``): ``MeasAdc``
alone, so a SPICE campaign and the behavioral model's take the same path.

Every capture is decoded with the design weights and with the "extracted" weights of its
``cap_table`` readback (a PEX table, or the behavioral model's extraction); the calibrations learn
from the training ramp and are checked on the other. The figures are the viewer's details (shared
x, named series, drawn like every block's), from the same analyses the paper's figures
(``flow.analysis.plots``) draw. The decision-path density is its paths, each distinct one with how
many conversions took it (``Detail.paths``): the whole conversion, its last decisions, and where
the conversions at one input end.

The mismatch study's ramps (``mc_*``) are each decoded with the design weights and with calibration
2 learned from that ramp (calibration 3's threshold fits need many more trials a branch than these
short ramps have): the spread of their worst DNL and INL over the capacitor draws at each Pelgrom
coefficient is what that matching costs, and what calibration wins back.
"""

from __future__ import annotations

import math
from itertools import takewhile
from pathlib import Path

import numpy as np

from flow.adc.behavioral import calc_redundancy_margins
from flow.analysis.adc import (
    analyze_adc_code_spectrum,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_power,
    analyze_adc_ramp,
)
from flow.analysis.calibration2 import analyze_adc_calibration2
from flow.analysis.calibration3 import analyze_adc_calibration3
from flow.analysis.io import read_extracted_calibration
from flow.analysis.types import MeasAdc
from flow.sweep import Detail

from .campaign import NOMINAL_RATE_HZ, UNIT_MISMATCH, hsu_errors, input_noise

# the figures, in the order the viewer shows them: name -> title. Each is one curve (one series, or
# one family of decision paths), so instances compared on one plot stay readable; what a second
# curve would add is a figure of its own
FIGURES = {
    "redundancy": "Error tolerance by stage",
    "code_density": "Ramp code density",
    "inl": "Ramp INL, design weights",
    "inl_calibrated": "Ramp INL, calibrated",
    "dnl": "Ramp DNL, design weights",
    "dnl_calibrated": "Ramp DNL, calibrated",
    "trajectory": "Decision paths at one input",
    "trajectory_final": "Decision paths: the last decisions",
    "trajectory_codes": "Output codes at one input",
    "noise_spectrum": "Output-code noise density",
    "noise_input": "Output noise over the input",
    "enob_rate": "ENOB over the conversion rate",
    "enob_fin": "ENOB over the input frequency at 10 MS/s",
    "spectrum_low": "Spectrum at 10 MS/s, low input frequency",
    "spectrum_nyquist": "Spectrum at 10 MS/s, input near Nyquist",
    "hsu_rate": "Integrated error over the conversion rate",
    "hsu_fastest": "Fastest error-free rate over the DAC settling",
    "hsu_map": "Integrated error over the rate and the DAC settling",
    "power_rate": "Supply power over the conversion rate",
    "energy_input": "Energy per conversion over the input",
    "energy_dac_input": "DAC energy per conversion over the input",
    "calibration_weights": "Weight error of the extracted array",
    "mismatch_dnl": "Worst DNL over capacitor mismatch",
    "mismatch_inl": "Worst INL over capacitor mismatch",
    "mismatch_inl_calibrated": "Worst INL after calibration over capacitor mismatch",
    "mismatch_missing": "Missing codes over capacitor mismatch",
}
RAILS = {"vdd_a": "VDD_A", "vdd_d": "VDD_D", "vdd_dac": "VDD_DAC"}


# the decision paths drawn: the last decisions' zoom, and at most this many distinct paths a plot
FINAL_DECISIONS = 6
MAX_PATHS = 400


def _path_details(trajectory: MeasAdc) -> list[Detail]:
    """The trajectory capture's decision paths (one input, many conversions): every distinct path of
    running code estimates with how many conversions took it, over the whole conversion and over
    its last decisions (where noise splits them), and the histogram of the codes they end on (its
    mean and spread in the curve's name)."""

    analysis = analyze_adc_decision_paths(trajectory)
    estimates = np.round(np.asarray(analysis.estimate_dout, dtype=np.float64), 6)
    steps = estimates.shape[1]

    def family(first: int) -> list[dict]:
        unique, counts = np.unique(estimates[:, first:], axis=0, return_counts=True)
        order = np.argsort(-counts, kind="stable")[:MAX_PATHS]
        return [{"y": [float(f"{y:.6g}") for y in unique[i]], "count": int(counts[i])} for i in order]

    final = np.asarray(analysis.final_dout, dtype=np.float64)
    mean, sigma = float(np.mean(final)), float(np.std(final))
    codes = np.arange(math.floor(final.min()) - 2, math.ceil(final.max()) + 3)
    counts = np.array([np.count_nonzero(final == code) for code in codes], dtype=np.float64)
    first = max(steps - 1 - FINAL_DECISIONS, 0)
    label = "Code estimate (LSB)"
    return [
        Detail("trajectory", FIGURES["trajectory"], "Decisions made", label, list(range(steps)), {}, paths=family(0)),
        Detail(
            "trajectory_final",
            FIGURES["trajectory_final"],
            "Decisions made",
            label,
            list(range(first, steps)),
            {},
            paths=family(first),
        ),
        Detail(
            "trajectory_codes",
            FIGURES["trajectory_codes"],
            "Output code",
            "Conversions",
            [float(code) for code in codes],
            {f"Conversions (mean {mean:.2f}, σ {sigma:.2f} LSB)": [float(count) for count in counts]},
        ),
    ]


def _extracted(measurement: MeasAdc):
    return read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)


def _by_code(ramps, values: str) -> tuple[list[float], dict[str, list[float]]]:
    """Each decoding's per-code ``values`` (dnl, inl, or the count over the ideal) over the codes
    any of them grades, the clipped end codes left out as the linearity leaves them: one shared
    axis, NaN where a decoding has no such code."""
    codes = np.arange(
        min(int(np.min(ramp.linearity_code)) for ramp in ramps.values()),
        max(int(np.max(ramp.linearity_code)) for ramp in ramps.values()) + 1,
    )
    series = {}
    for label, ramp in ramps.items():
        column = np.full(len(codes), np.nan)
        if values == "density":
            code = np.asarray(ramp.code, dtype=np.int64)
            graded = (code >= ramp.linearity_code.min()) & (code <= ramp.linearity_code.max())
            column[code[graded] - codes[0]] = ramp.count[graded] / ramp.ideal_count
        else:
            column[np.asarray(ramp.linearity_code, dtype=np.int64) - codes[0]] = getattr(ramp, values)
        series[label] = column.tolist()
    return codes.astype(float).tolist(), series


def _log_binned(frequency_hz: np.ndarray, densities: dict[str, np.ndarray], bins: int = 300):
    """Densities averaged in power over log-spaced frequency bins (a 50k-bin spectrum is more than
    a plot can show): the bins' geometric centres, NaN where a bin is empty."""
    positive = frequency_hz > 0
    edges = np.geomspace(frequency_hz[positive].min(), frequency_hz.max() * (1 + 1e-9), bins + 1)
    index = np.digitize(frequency_hz, edges) - 1
    inside = positive & (index >= 0) & (index < bins)
    counts = np.bincount(index[inside], minlength=bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        series = {
            label: np.sqrt(np.bincount(index[inside], weights=density[inside] ** 2, minlength=bins) / counts).tolist()
            for label, density in densities.items()
        }
    return np.sqrt(edges[:-1] * edges[1:]).tolist(), series


def _mismatch_study(captures: dict[str, MeasAdc]) -> tuple[np.ndarray, dict[str, dict[str, np.ndarray]]]:
    """Each mismatch ramp's worst DNL and INL and missing codes by decoding, as arrays of shape
    (Pelgrom coefficients, draws)."""
    rows: dict[float, list[dict[str, tuple[float, float, float]]]] = {}
    for name, measurement in sorted(captures.items()):
        if not name.startswith("mc_"):
            continue
        design = analyze_adc_ramp(measurement)
        calibration = analyze_adc_calibration2(measurement, ramp=design)
        ramps = {"Design weights": design, "Calibration 2": analyze_adc_ramp(measurement, calibration=calibration)}
        coefficient = float(measurement.info.readbacks["unit_mismatch"])
        rows.setdefault(coefficient, []).append(
            {
                label: (ramp.maximum_abs_dnl, ramp.maximum_abs_inl, float(ramp.missing_codes))
                for label, ramp in ramps.items()
            }
        )
    coefficients = np.asarray(sorted(rows))
    decodings = {
        label: {
            key: np.asarray([[draw[label][column] for draw in rows[c]] for c in coefficients])
            for column, key in enumerate(("dnl", "inl", "missing"))
        }
        for label in rows[coefficients[0]][0]
    }
    return coefficients, decodings


def adc_figures(captures: dict[str, MeasAdc], out_dir: Path) -> tuple[dict[str, float], list[Detail]]:
    """The campaign's metrics and its figures as the viewer's details (``FIGURES`` names and
    titles them) from its captures by name. ``noise_sampling`` and ``noise_comparator`` (the noise
    capture with one source) add each source's rms noise where present, the ``mc_*`` ramps the
    mismatch study."""

    out_dir.mkdir(parents=True, exist_ok=True)
    details: list[Detail] = []

    def add(name: str, x_label: str, y_label: str, x, series, **scales) -> None:
        details.append(
            Detail(
                name=name,
                title=FIGURES[name],
                x_label=x_label,
                y_label=y_label,
                # six significant digits, as the viewer's other exports
                x=[float(f"{value:.6g}") for value in x],
                series={label: [float(f"{value:.6g}") for value in ys] for label, ys in series.items()},
                **scales,
            )
        )

    check, train = captures["ramp_check"], captures["ramp_train"]
    extracted = _extracted(check)
    ramps = {
        "Design weights": analyze_adc_ramp(check),
        "Extracted weights": analyze_adc_ramp(check, calibration=extracted),
    }
    rates = sorted((m for n, m in captures.items() if n.startswith("rate_")), key=lambda m: float(m.tb.symbol_rate))
    dynamics = [analyze_adc_dynamic(m, calibration=_extracted(m)) for m in rates]
    powers = [analyze_adc_power(m) for m in rates]
    fins = [m for n, m in captures.items() if n.startswith("fin_")]
    fin_dynamics = [analyze_adc_dynamic(m, calibration=_extracted(m)) for m in fins]
    dcs = [m for n, m in sorted(captures.items()) if n.startswith("dc_")]
    train_ramp = analyze_adc_ramp(train)
    learned = {"Calibration 2": analyze_adc_calibration2(train, ramp=train_ramp)}
    # calibration 3 fits a threshold in every late branch, and a ramp can hold too few hits there to
    # bracket one; then it is left out (``calibration3_fitted`` says so) rather than failing the rest
    try:
        learned["Calibration 3"] = analyze_adc_calibration3(train, ramp=train_ramp)
    except ValueError:
        pass
    decoded = ramps | {label: analyze_adc_ramp(check, calibration=c) for label, c in learned.items()}
    # each stage's error tolerance: the design's weights and the extracted array's
    redundancy = {
        "Design weights": calc_redundancy_margins(extracted.nominal_weights),
        "Extracted weights": calc_redundancy_margins(extracted.calibrated_weights),
    }
    coefficients, mismatch = _mismatch_study(captures)
    drawn, drawn_calibrated = mismatch.values()
    harpe = int(np.argmin(np.abs(coefficients - UNIT_MISMATCH)))

    # the decodings a ramp is graded by: the design weights (the converter as it comes) and the best
    # calibration learned (calibration 3 where it fitted)
    best = "Calibration 3" if "Calibration 3" in learned else "Calibration 2"
    add(
        "redundancy",
        "Conversion stage (C0 first)",
        "Error tolerance (%)",
        range(len(redundancy["Design weights"])),
        {"Design weights": redundancy["Design weights"]},
    )
    add(
        "code_density",
        "Output code",
        "Code width (count / ideal)",
        *_by_code({"Design weights": ramps["Design weights"]}, "density"),
    )
    for name, values, label in (
        ("inl", "inl", "Design weights"),
        ("inl_calibrated", "inl", best),
        ("dnl", "dnl", "Design weights"),
        ("dnl_calibrated", "dnl", best),
    ):
        add(name, "Output code", f"{values.upper()} (LSB)", *_by_code({label: decoded[label]}, values))
    details += _path_details(captures["trajectory"])
    spectrum = analyze_adc_code_spectrum(captures["noise"], calibration=_extracted(captures["noise"]))
    add(
        "noise_spectrum",
        "Frequency (Hz)",
        "Noise density (LSB/sqrt(Hz))",
        *_log_binned(spectrum.frequency_hz, {"Total ADC": spectrum.asd_lsb_per_sqrt_hz}),
        x_log=True,
        y_log=True,
    )
    levels_v, sigma_lsb = input_noise(captures)
    add("noise_input", "Differential input (V)", "Output noise (LSB rms)", levels_v, {"Noise": sigma_lsb})
    rate_hz = [d.sample_rate_hz for d in dynamics]
    add(
        "enob_rate",
        "Conversion rate (Hz)",
        "ENOB (bits)",
        rate_hz,
        # no ENOB where the output no longer follows the input (SNDR under 1.76 dB): a point
        # there would only stretch the axis
        {"ENOB": [d.spectral_enob_bits if d.spectral_enob_bits > 0 else math.nan for d in dynamics]},
        x_log=True,
    )
    at_nominal = sorted(
        (d for d in fin_dynamics if round(d.sample_rate_hz) == round(NOMINAL_RATE_HZ)),
        key=lambda d: d.input_frequency_hz,
    )
    add(
        "enob_fin",
        "Input frequency / conversion rate",
        "ENOB (bits)",
        [d.input_frequency_hz / d.sample_rate_hz for d in at_nominal],
        {"ENOB": [d.spectral_enob_bits if d.spectral_enob_bits > 0 else math.nan for d in at_nominal]},
    )
    for name, dynamic in (("spectrum_low", at_nominal[0]), ("spectrum_nyquist", at_nominal[-1])):
        add(
            name,
            "Frequency (Hz)",
            "Power (dBFS)",
            dynamic.spectrum_frequency_hz,
            {f"{dynamic.input_frequency_hz / 1e6:.3g} MHz input": dynamic.spectrum_dbfs},
        )
    # Hsu's study (A. H. T. Chang, MIT PhD thesis 2013, sec. 3.3.3): every code centre once, noise-free, at each
    # rate and with the DAC's settling time constants scaled; the integrated |code - ideal timing's|
    hsu_rates, tau_scales, hsu = hsu_errors(captures)
    nominal_tau = int(np.argmin(np.abs(tau_scales - 1.0)))
    add("hsu_rate", "Conversion rate (Hz)", "Integrated error (LSB)", hsu_rates, {"Integrated error": hsu[nominal_tau]})
    # each scale's fastest rate before the integrated error first passes a code in 1024 (Hsu's zero,
    # less the rare metastable decision at a code centre), counting up from the slowest; NaN where
    # even the slowest does
    tolerance = max(1.0, len(captures["hsu_reference"].dout) / 1024)
    fastest = []
    for row in hsu:
        failing = np.flatnonzero(row > tolerance)
        fastest.append(hsu_rates[-1] if not len(failing) else hsu_rates[failing[0] - 1] if failing[0] else math.nan)
    add(
        "hsu_fastest",
        "Settling time constant (x the array's)",
        "Fastest error-free rate (Hz)",
        tau_scales,
        {"Fastest error-free rate": fastest},
        x_log=True,
    )
    details.append(
        Detail(
            name="hsu_map",
            title=FIGURES["hsu_map"],
            x_label="Conversion rate (Hz)",
            y_label="Settling time constant (x the array's)",
            x=[float(rate) for rate in hsu_rates],
            series={},
            grid={
                "y": [float(scale) for scale in tau_scales],
                "z": [[float(value) for value in row] for row in hsu],
                "z_label": "Integrated error (LSB)",
                "z_max": 10.0,
            },
        )
    )
    add(
        "power_rate",
        "Conversion rate (Hz)",
        "Supply power (W)",
        rate_hz,
        {"Total": [p.total_power_w for p in powers]},
        x_log=True,
        y_log=True,
    )
    dc_powers = [analyze_adc_power(m) for m in dcs]
    energy = {
        label: [
            getattr(p, f"{rail}_dynamic_power_w") / p.active_conversion_rate_hz
            + getattr(p, f"{rail}_static_power_w") / p.sample_rate_hz
            for p in dc_powers
        ]
        for rail, label in RAILS.items()
    }
    vin = [float(np.mean(m.vin_diff_v)) for m in dcs]
    add(
        "energy_input",
        "Differential input (V)",
        "Energy per conversion (J)",
        vin,
        {"Total": np.sum(list(energy.values()), axis=0)},
    )
    add("energy_dac_input", "Differential input (V)", "Energy per conversion (J)", vin, {"VDD_DAC": energy["VDD_DAC"]})
    add(
        "calibration_weights",
        "Decision (B0 first)",
        "Weight error (%)",
        range(len(extracted.nominal_weights)),
        {"Extracted weights": 100.0 * (extracted.calibrated_weights / extracted.nominal_weights - 1.0)},
    )
    # the 95th percentile over the draws at each matching: the worst one converter in twenty sees
    for name, label, key, y_label in (
        ("mismatch_dnl", "Design weights", "dnl", "Max |DNL| (LSB)"),
        ("mismatch_inl", "Design weights", "inl", "Max |INL| (LSB)"),
        ("mismatch_inl_calibrated", "Calibration 2", "inl", "Max |INL| (LSB)"),
        ("mismatch_missing", "Design weights", "missing", "Missing codes"),
    ):
        add(
            name,
            "Pelgrom coefficient A_C (%·sqrt(fF))",
            y_label,
            coefficients * 100,
            {f"{label}, 95th percentile": np.percentile(mismatch[label][key], 95, axis=1)},
            x_log=True,
        )

    nominal = next(
        (d, p) for d, p in zip(dynamics, powers, strict=True) if round(d.sample_rate_hz) == round(NOMINAL_RATE_HZ)
    )
    dynamic, power = nominal
    power_w = sum(
        getattr(power, f"{rail}_{kind}_power_w")
        for rail in ("vdd_a", "vdd_d", "vdd_dac")
        for kind in ("static", "dynamic")
    )
    noise = captures["noise"]
    noise_lsb = float(np.std(noise.dout))
    # each noise source alone (the noise capture with only it on), where the campaign has them
    by_source = {
        f"noise_{source}_rms_lsb": float(np.std(captures[f"noise_{source}"].dout))
        for source in ("sampling", "comparator")
        if f"noise_{source}" in captures
    }
    metrics = {
        "enob_bits": dynamic.spectral_enob_bits,
        "sndr_db": dynamic.spectral_sndr_db,
        "sfdr_db": dynamic.spectral_sfdr_db,
        "enob_nyquist_bits": at_nominal[-1].spectral_enob_bits,
        "enob_low_fin_bits": at_nominal[0].spectral_enob_bits,
        "inl_max_lsb": ramps["Design weights"].maximum_abs_inl,
        "dnl_max_lsb": ramps["Design weights"].maximum_abs_dnl,
        "inl_max_extracted_lsb": ramps["Extracted weights"].maximum_abs_inl,
        "inl_max_calibrated_lsb": decoded[best].maximum_abs_inl,
        "dnl_max_calibrated_lsb": decoded[best].maximum_abs_dnl,
        "missing_codes": float(ramps["Design weights"].missing_codes),
        "power_w": power_w,
        "energy_per_conversion_j": power_w / dynamic.sample_rate_hz,
        "fom_walden_j": power_w / (2**dynamic.spectral_enob_bits * dynamic.sample_rate_hz),
        "fom_schreier_db": dynamic.spectral_sndr_db + 10 * math.log10(dynamic.sample_rate_hz / 2 / power_w),
        "noise_rms_lsb": noise_lsb,
        **by_source,
        # the rails' share: the noise at the input's ends (their plates unbalanced) over mid-scale's
        "noise_input_edge_lsb": float(max(sigma_lsb[0], sigma_lsb[-1])),
        "noise_input_mid_lsb": float(sigma_lsb[len(sigma_lsb) // 2]),
        # Hsu's study at the array's own settling: the fastest error-free rate, and the error at 10 MS/s
        "error_free_rate_max_hz": float(fastest[nominal_tau]),
        "integrated_error_nominal_lsb": float(hsu[nominal_tau][-1]),
        # the fastest rate before the ENOB first falls a bit below the slowest rate's: past it the
        # comparator or the DAC runs out of time (the sampler's distortion slopes off more gently)
        "rate_max_hz": list(
            takewhile(lambda d: d.spectral_enob_bits >= dynamics[0].spectral_enob_bits - 1.0, dynamics)
        )[-1].sample_rate_hz,
        "redundancy_first_pct": float(redundancy["Design weights"][0]),
        "redundancy_first_extracted_pct": float(redundancy["Extracted weights"][0]),
        "calibration3_fitted": float("Calibration 3" in learned),
        # the 95th percentile over the capacitor draws at Harpe's matching (0.10 %·sqrt(fF)): the
        # array's own layout error and the draw, decoded with the design weights and recalibrated
        "mismatch_dnl_p95_lsb": float(np.percentile(drawn["dnl"][harpe], 95)),
        "mismatch_inl_p95_lsb": float(np.percentile(drawn["inl"][harpe], 95)),
        "mismatch_missing_codes_p95": float(np.percentile(drawn["missing"][harpe], 95)),
        "mismatch_inl_p95_calibrated_lsb": float(np.percentile(drawn_calibrated["inl"][harpe], 95)),
    }
    return metrics, details
