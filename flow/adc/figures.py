"""An ADC campaign's figures and metrics from its captures (``flow.adc.campaign``): ``MeasAdc``
alone, so a SPICE campaign and the behavioral model's take the same path.

Every capture is decoded with the design weights and with the "extracted" weights of its
``cap_table`` readback (a PEX table, or the behavioral model's extraction); the calibrations learn
from the training ramp and are checked on the other. The figures are the analysis plots
(``flow.analysis.plots``) of one ADC, written as SVG for the viewer.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from pathlib import Path

import numpy as np

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

from .campaign import NOMINAL_RATE_HZ

# the figures, in the order the viewer shows them: name -> title
FIGURES = {
    "code_density": "Ramp code density",
    "inl_dnl": "Ramp INL and DNL",
    "trajectory": "Decision-path density",
    "enob_rate": "ENOB and SNDR over the conversion rate",
    "power_rate": "Supply power over the conversion rate",
    "energy_input": "Energy per conversion over the input",
    "noise_spectrum": "Output-code noise spectral density by source",
    "enob_fin": "ENOB and SNDR over the input frequency",
    "spectrum_low": "Spectrum at 10 MS/s, low input frequency",
    "spectrum_nyquist": "Spectrum at 10 MS/s, input near Nyquist",
    "calibration_weights": "Calibrated digital weights",
    "calibration_inl_dnl": "INL and DNL after each calibration",
}


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


def adc_figures(captures: dict[str, MeasAdc], out_dir: Path) -> tuple[dict[str, float], dict[str, Path]]:
    """The campaign's metrics and its figures (name -> SVG path; ``FIGURES`` names them) from its
    captures by name; ``noise_sampling`` and ``noise_comparator`` (the noise capture with one
    source) add the noise spectrum by source where present."""

    out_dir.mkdir(parents=True, exist_ok=True)
    figures: dict[str, Path] = {}

    def keep(name: str, paths: tuple[Path, ...]) -> None:
        figures[name] = next(path for path in paths if path.suffix == ".svg")

    check, train = captures["ramp_check"], captures["ramp_train"]
    extracted = _extracted(check)
    ramps = (analyze_adc_ramp(check), analyze_adc_ramp(check, calibration=extracted))
    rates = sorted((m for n, m in captures.items() if n.startswith("rate_")), key=lambda m: float(m.tb.symbol_rate))
    dynamics = [analyze_adc_dynamic(m, calibration=_extracted(m)) for m in rates]
    powers = [analyze_adc_power(m) for m in rates]
    fins = [m for n, m in captures.items() if n.startswith("fin_")]
    fin_dynamics = [analyze_adc_dynamic(m, calibration=_extracted(m)) for m in fins]
    dcs = [m for n, m in sorted(captures.items()) if n.startswith("dc_")]
    train_ramp = analyze_adc_ramp(train)
    learned = (
        analyze_adc_calibration2(train, ramp=train_ramp),
        analyze_adc_calibration3(train, ramp=train_ramp),
    )
    with _svg_only():
        keep("code_density", plots.plot_adc_ramp_histogram(ramps, output_path=out_dir / "code_density", msmt=check))
        keep("inl_dnl", plots.plot_adc_ramp_nonlinearity(ramps, output_path=out_dir / "inl_dnl", msmt=check))
        trajectory = captures["trajectory"]
        keep(
            "trajectory",
            plots.plot_adc_decision_path_density(
                trajectory, analyze_adc_decision_paths(trajectory), output_path=out_dir / "trajectory"
            ),
        )
        keep(
            "enob_rate",
            plots.plot_adc_dynamic_sweep(rates, dynamics, output_path=out_dir / "enob_rate", x_axis="sample_rate"),
        )
        keep(
            "power_rate",
            plots.plot_adc_power_sweep(
                rates, powers, output_path=out_dir / "power_rate", rate_axis="sampling", merge_static=True
            ),
        )
        keep(
            "energy_input",
            plots.plot_adc_conversion_energy(
                dcs, [analyze_adc_power(m) for m in dcs], output_path=out_dir / "energy_input"
            ),
        )
        sources = {"noise_sampling": "Sampling switch (kT/C)", "noise_comparator": "Comparator", "noise": "Total ADC"}
        present = {name: label for name, label in sources.items() if name in captures}
        keep(
            "noise_spectrum",
            plots.plot_adc_code_spectrum(
                [analyze_adc_code_spectrum(captures[name], calibration=_extracted(captures[name])) for name in present],
                labels=tuple(present.values()),
                title="Output-code noise by source",
                output_path=out_dir / "noise_spectrum",
            ),
        )
        keep(
            "enob_fin",
            plots.plot_adc_dynamic_sweep(
                fins, fin_dynamics, output_path=out_dir / "enob_fin", x_axis="input_frequency"
            ),
        )
        at_nominal = sorted(
            (
                (dynamic.input_frequency_hz, measurement, dynamic)
                for measurement, dynamic in zip(fins, fin_dynamics, strict=True)
                if round(dynamic.sample_rate_hz) == round(NOMINAL_RATE_HZ)
            ),
            key=lambda entry: entry[0],
        )
        for name, (_frequency, measurement, dynamic) in (
            ("spectrum_low", at_nominal[0]),
            ("spectrum_nyquist", at_nominal[-1]),
        ):
            keep(name, plots.plot_adc_dynamic(measurement, dynamic, output_path=out_dir / name))
        keep(
            "calibration_weights",
            plots.plot_adc_calibration_weights((extracted, *learned), output_path=out_dir / "calibration_weights"),
        )
        calibrated = [*ramps, *(analyze_adc_ramp(check, calibration=calibration) for calibration in learned)]
        keep(
            "calibration_inl_dnl",
            plots.plot_adc_ramp_nonlinearity(
                calibrated, output_path=out_dir / "calibration_inl_dnl", msmt=check, stacked=True
            ),
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
        "enob_nyquist_bits": at_nominal[-1][2].spectral_enob_bits,
        "enob_low_fin_bits": at_nominal[0][2].spectral_enob_bits,
        "inl_max_lsb": ramps[0].maximum_abs_inl,
        "dnl_max_lsb": ramps[0].maximum_abs_dnl,
        "inl_max_extracted_lsb": ramps[1].maximum_abs_inl,
        "missing_codes": float(ramps[0].missing_codes),
        "power_w": power_w,
        "energy_per_conversion_j": power_w / dynamic.sample_rate_hz,
        "fom_walden_j": power_w / (2**dynamic.spectral_enob_bits * dynamic.sample_rate_hz),
        "fom_schreier_db": dynamic.spectral_sndr_db + 10 * math.log10(dynamic.sample_rate_hz / 2 / power_w),
        "noise_rms_lsb": noise_lsb,
    }
    return metrics, figures
