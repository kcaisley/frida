"""One-off: A/B runs that located the ~6-8 MHz interferer in the THS4541 supply connection.

Fixed 50 mV / 700 mV perfboard input, ADC00-03, seven 160-symbol sequences at
2/6/10 MSPS, 100,000 conversions each, scope powered off throughout:

    A  amplifier +5/-1 V supplies disconnected            20261009_105940
    B  supplies connected, amplifier enabled (AMP_EN=1)    20261009_110638
    C  supplies connected, amplifier disabled (AMP_EN=0)   20261009_110933

Each run gets the standard sequence-ENOB overview and noise-distribution grid;
one extra figure overlays the three runs' code spectra (comp11110000_logic10000111)
per rate. These runs have no scope records, so analyze_adc_noise cannot confirm
a readout by the scope/FastRX bit comparison; here a capture counts as a valid
readout when FastRX lost no frames. Regenerate from the repository root (needs the scans under build/):

    uv run python docs/images/interferer_hunt/plot_interferer_ab.py
"""

import dataclasses
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.adc.sequences import SEQUENCES, AdcSequence
from flow.analysis import calc
from flow.analysis.adc import analyze_adc_noise, analyze_adc_operating_conditions
from flow.analysis.io import read_measurement, read_measurement_param, write_analysis
from flow.analysis.plots import (
    PLOT_STYLE,
    plot_adc_noise_distribution_grid,
    plot_adc_sequence_chip_overview,
    save_figure,
    style_grid,
)

ROOT = Path(__file__).resolve().parents[3]
# Figures go to the original result directory; the PDFs beside this script are copies.
OUT_DIR = ROOT / "build/analysis/adc/20261009_interferer_ab"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RUNS = {
    "A: amp supplies off": "20261009_105940_adc_sequence_static",
    "B: amp supplies on, enabled": "20261009_110638_adc_sequence_static",
    "C: amp supplies on, disabled": "20261009_110933_adc_sequence_static",
}
# Overview titles use the interferer-hunt deck's test numbers.
TEST_TITLES = {
    "A: amp supplies off": "test #12, amplifier supply unplugged",
    "B: amp supplies on, enabled": "test #13, amplifier supply on, enabled",
    "C: amp supplies on, disabled": "test #14, amplifier supply on, disabled",
}
SPECTRUM_SEQUENCE = dict(SEQUENCES)["symbol160_init4_samp20_comp11110000_logic10000111"]
catalogue = tuple(sequence for name, sequence in SEQUENCES if name.startswith("symbol160_init4_samp20_"))

# {run: {rate: {adc: (frequency_hz, asd_lsb_per_sqrt_hz, std_lsb)}}}
spectra: dict[str, dict[float, dict[int, tuple[np.ndarray, np.ndarray, float]]]] = {}
for run, folder in RUNS.items():
    run_out = OUT_DIR / run.split(":")[0]
    paths = sorted((ROOT / "build/scan_adc" / folder).glob("[0-9][0-9][0-9][0-9]_capture.h5"))
    paths_by_adc: dict[int, list[Path]] = {}
    for path in paths:
        paths_by_adc.setdefault(read_measurement_param(path).observed_adc, []).append(path)
    conditions, all_measurements, all_noise = [], [], []
    for adc_index, adc_paths in sorted(paths_by_adc.items()):
        measurements = [read_measurement(path) for path in adc_paths]
        # Scope-less captures: accept the readout when FastRX lost no frames.
        noise = [
            dataclasses.replace(
                analyze_adc_noise(measurement),
                readout_valid=int(measurement.info.readbacks.get("fastrx_lost_count", -1)) == 0,
            )
            for measurement in measurements
        ]
        result = analyze_adc_operating_conditions(measurements, noise=noise)
        conditions.append(result)
        write_analysis(run_out / f"adc{adc_index:02d}_operating_conditions.h5", result)
        all_measurements.extend(measurements)
        all_noise.extend(noise)
        for measurement in measurements:
            if AdcSequence.from_tb_params(measurement.param.tb) != SPECTRUM_SEQUENCE:
                continue
            codes = measurement.dout.astype(np.float64)
            codes -= codes.mean()
            frequency_hz, psd = calc.psd(codes, sample_rate=measurement.sample_rate_hz, segment_length=8192)
            spectra.setdefault(run, {}).setdefault(measurement.sample_rate_hz, {})[adc_index] = (
                frequency_hz,
                np.sqrt(psd),
                float(codes.std()),
            )
    plot_adc_sequence_chip_overview(
        conditions,
        sequences=catalogue,
        title=f"{len(conditions)} ADCs · fixed 50 mV input · {TEST_TITLES[run]}",
        output_path=run_out / "all_adc_sequence_overview",
    )
    plot_adc_noise_distribution_grid(all_measurements, all_noise, output_path=run_out / "adc_noise_distribution_grid")
    print(f"{run}: {len(paths)} captures -> {run_out}")

rates = sorted(next(iter(spectra.values())))
with mpl.rc_context(PLOT_STYLE):
    fig, axes = plt.subplots(len(rates), 1, figsize=(9.6, 10.0))
    for ax, rate in zip(axes, rates):
        for run in RUNS:
            frequency_hz, asd, _ = spectra[run][rate][0]
            stds = ", ".join(f"{spectra[run][rate][adc][2]:.2f}" for adc in sorted(spectra[run][rate]))
            ax.semilogy(frequency_hz / 1e6, asd, label=f"{run} (ADC00–03 std {stds} LSB)")
        ax.set_xlim(0, rate / 2e6)
        ax.set_title(f"{rate / 1e6:g} MSPS")
        ax.set_ylabel("ASD (LSB/√Hz)")
        ax.legend(loc="upper right", fontsize=8)
        style_grid(ax)
    axes[-1].set_xlabel("Frequency, 0 to Nyquist (MHz)")
    fig.suptitle("ADC00 code noise spectra, comp11110000_logic10000111 – amplifier supply A/B")
    save_figure(fig, OUT_DIR / "code_spectra_ab")
print(f"Figures in {OUT_DIR}")
