"""An ADC campaign's figures and metrics from its captures (``flow.adc.campaign``): ``MeasAdc``
alone, so a SPICE campaign and the behavioral model's take the same path.

Every capture is decoded with the design weights and with the "extracted" weights of its
``cap_table`` readback (a PEX table, or the behavioral model's extraction); the calibrations learn
from the training ramp and are checked on the other. The figures are the viewer's details (shared
x, named series, drawn like every block's), from the same analyses the paper's figures
(``flow.analysis.plots``) draw; the decision-path density, a 2-D histogram, is that plot's SVG.

The mismatch study's ramps (``mc_*``) are each decoded with the design weights and with calibration
2 learned from that ramp (calibration 3's threshold fits need many more trials a branch than these
short ramps have): the spread of their worst DNL and INL over the capacitor draws at each Pelgrom
coefficient is what that matching costs, and what calibration wins back.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from itertools import takewhile
from pathlib import Path

import numpy as np

from flow.adc.behavioral import calc_redundancy_margins
from flow.analysis import plots
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
from flow.sweep.runner import ROOT

from .campaign import NOMINAL_RATE_HZ, UNIT_MISMATCH

# the figures, in the order the viewer shows them: name -> title
FIGURES = {
    "redundancy": "Redundancy by conversion stage",
    "code_density": "Ramp code density",
    "inl": "Ramp INL by decoding",
    "dnl": "Ramp DNL by decoding",
    "trajectory": "Decision-path density",
    "enob_rate": "ENOB over the conversion rate",
    "power_rate": "Supply power over the conversion rate",
    "energy_input": "Energy per conversion over the input",
    "noise_spectrum": "Output-code noise density by source",
    "enob_fin": "ENOB over the input frequency",
    "spectrum_low": "Spectrum at 10 MS/s, low input frequency",
    "spectrum_nyquist": "Spectrum at 10 MS/s, input near Nyquist",
    "calibration_weights": "Calibrated weights against the design's",
    "mismatch_dnl": "Worst DNL over capacitor mismatch",
    "mismatch_inl": "Worst INL over capacitor mismatch",
    "mismatch_missing": "Missing codes over capacitor mismatch",
}
RAILS = {"vdd_a": "VDD_A", "vdd_d": "VDD_D", "vdd_dac": "VDD_DAC"}


@contextmanager
def _svg_only():
    """The plots write SVG for the viewer instead of their default PDF."""
    saved = plots.PLOT_PNGS, plots.PLOT_SVGS, plots.PLOT_PDFS
    plots.PLOT_PNGS, plots.PLOT_SVGS, plots.PLOT_PDFS = False, True, False
    try:
        yield
    finally:
        plots.PLOT_PNGS, plots.PLOT_SVGS, plots.PLOT_PDFS = saved


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
    titles them) from its captures by name: data the viewer plots, but the decision-path density,
    an SVG under ``out_dir``. ``noise_sampling`` and ``noise_comparator`` (the noise capture with
    one source) add the noise spectrum by source where present, the ``mc_*`` ramps the mismatch
    study."""

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
    learned = {
        "Calibration 2": analyze_adc_calibration2(train, ramp=train_ramp),
        "Calibration 3": analyze_adc_calibration3(train, ramp=train_ramp),
    }
    decoded = ramps | {label: analyze_adc_ramp(check, calibration=c) for label, c in learned.items()}
    # each stage's error tolerance: the design's weights and the extracted array's
    redundancy = {
        "Design weights": calc_redundancy_margins(extracted.nominal_weights),
        "Extracted weights": calc_redundancy_margins(extracted.calibrated_weights),
    }
    coefficients, mismatch = _mismatch_study(captures)
    drawn, drawn_calibrated = mismatch.values()
    harpe = int(np.argmin(np.abs(coefficients - UNIT_MISMATCH)))

    add(
        "redundancy",
        "Conversion stage (C0 first)",
        "Error tolerance (%)",
        range(len(redundancy["Design weights"])),
        redundancy,
    )
    add("code_density", "Output code", "Code width (count / ideal)", *_by_code(ramps, "density"))
    add("inl", "Output code", "INL (LSB)", *_by_code(decoded, "inl"))
    add("dnl", "Output code", "DNL (LSB)", *_by_code(decoded, "dnl"))
    trajectory = captures["trajectory"]
    with _svg_only():
        paths = plots.plot_adc_decision_path_density(
            trajectory, analyze_adc_decision_paths(trajectory), output_path=out_dir / "trajectory"
        )
    details.append(
        Detail(
            name="trajectory",
            title=FIGURES["trajectory"],
            x_label="",
            y_label="",
            x=[],
            series={},
            figure=str(next(path for path in paths if path.suffix == ".svg").relative_to(ROOT)),
        )
    )
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
    add(
        "power_rate",
        "Conversion rate (Hz)",
        "Supply power (W)",
        rate_hz,
        {
            label: [getattr(p, f"{rail}_static_power_w") + getattr(p, f"{rail}_dynamic_power_w") for p in powers]
            for rail, label in RAILS.items()
        }
        | {"Total": [p.total_power_w for p in powers]},
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
    add(
        "energy_input",
        "Differential input (V)",
        "Energy per conversion (J)",
        [float(np.mean(m.vin_diff_v)) for m in dcs],
        energy | {"Total": np.sum(list(energy.values()), axis=0)},
    )
    sources = {"noise_sampling": "Sampling switch (kT/C)", "noise_comparator": "Comparator", "noise": "Total ADC"}
    spectra = {
        label: analyze_adc_code_spectrum(captures[name], calibration=_extracted(captures[name]))
        for name, label in sources.items()
        if name in captures
    }
    frequency_hz = next(iter(spectra.values())).frequency_hz
    add(
        "noise_spectrum",
        "Frequency (Hz)",
        "Noise density (LSB/sqrt(Hz))",
        *_log_binned(frequency_hz, {label: spectrum.asd_lsb_per_sqrt_hz for label, spectrum in spectra.items()}),
        x_log=True,
        y_log=True,
    )
    # the input frequency over the rate, shared by the three rates
    by_rate: dict[float, dict[float, float]] = {}
    for d in fin_dynamics:
        by_rate.setdefault(round(d.sample_rate_hz), {})[round(d.input_frequency_hz / d.sample_rate_hz, 6)] = (
            d.spectral_enob_bits if d.spectral_enob_bits > 0 else math.nan
        )
    fractions = sorted({fraction for enobs in by_rate.values() for fraction in enobs})
    add(
        "enob_fin",
        "Input frequency / conversion rate",
        "ENOB (bits)",
        fractions,
        {
            f"{rate / 1e6:g} MS/s": [enobs.get(f, math.nan) for f in fractions]
            for rate, enobs in sorted(by_rate.items())
        },
    )
    at_nominal = sorted(
        (d for d in fin_dynamics if round(d.sample_rate_hz) == round(NOMINAL_RATE_HZ)),
        key=lambda d: d.input_frequency_hz,
    )
    for name, dynamic in (("spectrum_low", at_nominal[0]), ("spectrum_nyquist", at_nominal[-1])):
        add(
            name,
            "Frequency (Hz)",
            "Power (dBFS)",
            dynamic.spectrum_frequency_hz,
            {f"{dynamic.input_frequency_hz / 1e6:.3g} MHz input": dynamic.spectrum_dbfs},
        )
    add(
        "calibration_weights",
        "Decision (B0 first)",
        "Weight error (%)",
        range(len(extracted.nominal_weights)),
        {
            label: 100.0 * (calibration.calibrated_weights / calibration.nominal_weights - 1.0)
            for label, calibration in ({"Extracted weights": extracted} | learned).items()
        },
    )
    for name, key, y_label in (
        ("mismatch_dnl", "dnl", "Max |DNL| (LSB)"),
        ("mismatch_inl", "inl", "Max |INL| (LSB)"),
        ("mismatch_missing", "missing", "Missing codes"),
    ):
        add(
            name,
            "Pelgrom coefficient A_C (%·sqrt(fF))",
            y_label,
            coefficients * 100,
            {
                f"{label}, {name_}": np.percentile(stats[key], q, axis=1)
                for label, stats in mismatch.items()
                for name_, q in (("median", 50), ("95th percentile", 95))
            },
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
    metrics = {
        "enob_bits": dynamic.spectral_enob_bits,
        "sndr_db": dynamic.spectral_sndr_db,
        "sfdr_db": dynamic.spectral_sfdr_db,
        "enob_nyquist_bits": at_nominal[-1].spectral_enob_bits,
        "enob_low_fin_bits": at_nominal[0].spectral_enob_bits,
        "inl_max_lsb": ramps["Design weights"].maximum_abs_inl,
        "dnl_max_lsb": ramps["Design weights"].maximum_abs_dnl,
        "inl_max_extracted_lsb": ramps["Extracted weights"].maximum_abs_inl,
        "missing_codes": float(ramps["Design weights"].missing_codes),
        "power_w": power_w,
        "energy_per_conversion_j": power_w / dynamic.sample_rate_hz,
        "fom_walden_j": power_w / (2**dynamic.spectral_enob_bits * dynamic.sample_rate_hz),
        "fom_schreier_db": dynamic.spectral_sndr_db + 10 * math.log10(dynamic.sample_rate_hz / 2 / power_w),
        "noise_rms_lsb": noise_lsb,
        # the fastest rate before the ENOB first falls a bit below the slowest rate's: past it the
        # comparator or the DAC runs out of time (the sampler's distortion slopes off more gently)
        "rate_max_hz": list(
            takewhile(lambda d: d.spectral_enob_bits >= dynamics[0].spectral_enob_bits - 1.0, dynamics)
        )[-1].sample_rate_hz,
        "redundancy_first_pct": float(redundancy["Design weights"][0]),
        "redundancy_first_extracted_pct": float(redundancy["Extracted weights"][0]),
        # the 95th percentile over the capacitor draws at Harpe's matching (0.10 %·sqrt(fF)): the
        # array's own layout error and the draw, decoded with the design weights and recalibrated
        "mismatch_dnl_p95_lsb": float(np.percentile(drawn["dnl"][harpe], 95)),
        "mismatch_inl_p95_lsb": float(np.percentile(drawn["inl"][harpe], 95)),
        "mismatch_missing_codes_p95": float(np.percentile(drawn["missing"][harpe], 95)),
        "mismatch_inl_p95_calibrated_lsb": float(np.percentile(drawn_calibrated["inl"][harpe], 95)),
    }
    return metrics, details
