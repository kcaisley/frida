"""One-off: the lowest-noise ADC code spectrum measured so far, against the same
case with the amplifier supplies on (interferer present).

Searches every capture of the two clean 9 Oct runs (A: amplifier supply leads
unplugged, 105940; D: leads in, supplies turned down, 153529) for the smallest
code standard deviation that is not a stuck conversion
(sigma >= 0.3 LSB), then plots its Welch ASD (8192-sample Hann segments)
with the same ADC, sequence and rate from run C (supplies on, amp disabled,
110933). The dashed line is the ideal quantization-noise density,
(1/sqrt(12) LSB) / sqrt(fs/2). Regenerate from the repository root (needs the scans under build/):

    uv run python docs/images/interferer_hunt/plot_best_spectrum.py
"""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from flow.adc.sequences import SEQUENCES, AdcSequence
from flow.analysis import calc
from flow.analysis.io import read_measurement
from flow.analysis.plots import PLOT_STYLE, save_figure, style_grid

ROOT = Path(__file__).resolve().parents[3]
# Figures go to the original result directory; the PDFs beside this script are copies.
OUT_DIR = ROOT / "build/adc_code_noise_spectra/best"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CLEAN = {"A": "20261009_105940_adc_sequence_static", "D": "20261009_153529_adc_sequence_static"}
DIRTY = ("C", "20261009_110933_adc_sequence_static")


SEQUENCE_NAMES = {sequence: name for name, sequence in SEQUENCES}


def case_key(path: Path) -> tuple[int, str, float]:
    measurement = read_measurement(path)
    sequence = SEQUENCE_NAMES.get(AdcSequence.from_tb_params(measurement.param.tb), "unnamed")
    return (measurement.param.observed_adc, sequence, measurement.sample_rate_hz)


best = None
for run, folder in CLEAN.items():
    for path in sorted((ROOT / "build/scan_adc" / folder).glob("*_capture.h5")):
        measurement = read_measurement(path)
        std = float(measurement.dout.astype(np.float64).std())
        # Below the 0.29-LSB quantization floor means stuck conversions (the 6/8 and
        # 7/8 COMP reset limits at 6-10 MSPS return one or a few codes), not low noise.
        if std < 0.3:
            continue
        if best is None or std < best[0]:
            best = (std, run, path, measurement)
std, run, path, measurement = best
key = case_key(path)
dirty_path = next(p for p in sorted((ROOT / "build/scan_adc" / DIRTY[1]).glob("*_capture.h5")) if case_key(p) == key)
dirty = read_measurement(dirty_path)

rate = measurement.sample_rate_hz
with mpl.rc_context(PLOT_STYLE):
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    for label, m in (
        (f"Run {run}: amp supplies off", measurement),
        (f"Run {DIRTY[0]}: amp supplies on (disabled)", dirty),
    ):
        codes = m.dout.astype(np.float64)
        codes -= codes.mean()
        frequency_hz, psd = calc.psd(codes, sample_rate=m.sample_rate_hz, segment_length=8192)
        ax.semilogy(frequency_hz / 1e6, np.sqrt(psd), label=f"{label}, σ = {codes.std():.2f} LSB")
    ax.axhline((1 / np.sqrt(12)) / np.sqrt(rate / 2), linestyle="--", label="Ideal quantization, 0.29 LSB")
    ax.set_xlim(0, rate / 2e6)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("ASD (LSB/√Hz)")
    ax.set_title(
        f"ADC{key[0]:02d} code spectrum, {rate / 1e6:g} MSPS, {key[1].removeprefix('symbol160_init4_samp20_')}"
    )
    ax.legend(loc="upper right", fontsize=9)
    style_grid(ax)
    save_figure(fig, OUT_DIR / "best_code_spectrum")
print(f"best: run {run}, {path.relative_to(ROOT)}, std {std:.3f} LSB, {rate / 1e6:g} MSPS, ADC{key[0]:02d}")
print(f"sequence: {key[1]}")
print(f"compare: {dirty_path.relative_to(ROOT)}")
