"""One-off: narrowband vs broadband ADC code noise, and locating the tone by its aliases.

Fixed 50 mV / 700 mV input, sequence comp11110000_logic10000111, ADC00-03 at
2/6/10 MSPS, 100,000 conversions each, from two 2026-10-08 campaigns: the
scope-less run (19:55) and the scope re-run (20:41). Codes are decoded with
ideal binary weights. Regenerate from the repository root (needs the scans under build/):

    uv run python docs/images/interferer_hunt/plot_code_noise.py
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
OUT_DIR = ROOT / "build/adc_code_noise_spectra"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RUNS = {
    "scope-less run 19:55": ROOT / "build/scan_adc/20261008_195543_adc_sequence_static",
    "scope re-run 20:41": ROOT / "build/scan_adc/20261008_204141_adc_sequence_static",
}
SEQUENCE = "symbol160_init4_samp20_comp11110000_logic10000111"
SEGMENT = 8192  # Welch segment: 244 Hz bins at 2 MSPS, 1.2 kHz at 10 MSPS
TONE_HALF_WIDTH_HZ = 25e3  # the tone wanders by a few kHz within one capture; harmonic k spreads k times wider
HARMONICS = 8  # harmonics of the interferer counted as interference (higher ones vanish into the floor)

sequence = dict(SEQUENCES)[SEQUENCE]


def alias(frequency_hz: np.ndarray | float, sample_rate_hz: float) -> np.ndarray | float:
    """Fold a true frequency into the first Nyquist zone of a sampler."""
    return np.abs((np.asarray(frequency_hz) + sample_rate_hz / 2) % sample_rate_hz - sample_rate_hz / 2)


def code_spectrum(codes: np.ndarray, sample_rate_hz: float) -> dict:
    """Welch spectrum of the mean-free codes, its white floor, and its strongest peak."""
    centered = codes - codes.mean()
    frequency_hz, psd = calc.psd(centered, sample_rate=sample_rate_hz, segment_length=SEGMENT)
    return {
        "rate": sample_rate_hz,
        "codes": centered,
        "frequency_hz": frequency_hz,
        "psd": psd,
        "floor": np.median(psd),  # robust white-noise level, LSB²/Hz
        "peak_hz": frequency_hz[np.argmax(psd[1:]) + 1],
        "total_rms": np.sqrt(np.sum(psd) * (frequency_hz[1] - frequency_hz[0])),
    }


def split_interference(s: dict, true_hz_estimate: float) -> None:
    """Add the interferer's own frequency, its harmonic bands, and the variance split to ``s``.

    The capture's strongest peak is unfolded to the true frequency nearest the
    run-level estimate; the excess above the floor within each harmonic band is
    interference, everything else is the broadband remainder.
    """
    rate, frequency_hz, psd = s["rate"], s["frequency_hz"], s["psd"]
    zones = np.arange(0, 40)
    candidates = np.concatenate([zones * rate + s["peak_hz"], zones * rate - s["peak_hz"]])
    fundamental_hz = candidates[np.argmin(np.abs(candidates - true_hz_estimate))]
    band = np.zeros_like(frequency_hz, dtype=bool)
    harmonic_hz = []
    for k in range(1, HARMONICS + 1):
        harmonic_hz.append(alias(k * fundamental_hz, rate))
        band |= np.abs(frequency_hz - harmonic_hz[-1]) <= k * TONE_HALF_WIDTH_HZ
    bin_hz = frequency_hz[1] - frequency_hz[0]
    tone_variance = np.sum(np.clip(psd[band] - s["floor"], 0, None)) * bin_hz
    s.update(
        fundamental_hz=fundamental_hz,
        harmonic_hz=np.array(harmonic_hz),
        tone_band=band,
        tone_rms=np.sqrt(tone_variance),
        rest_rms=np.sqrt(s["total_rms"] ** 2 - tone_variance),
    )


# {run: {sample rate: {adc: spectrum}}}
data: dict[str, dict[float, dict[int, dict]]] = {}
for run, run_dir in RUNS.items():
    for path in sorted(run_dir.glob("[0-9][0-9][0-9][0-9]_capture.h5")):
        measurement = read_measurement(path)
        if AdcSequence.from_tb_params(measurement.param.tb) != sequence:
            continue
        rate = measurement.sample_rate_hz
        data.setdefault(run, {}).setdefault(rate, {})[measurement.param.observed_adc] = code_spectrum(
            measurement.dout.astype(np.float64), rate
        )
rates = sorted(next(iter(data.values())))

peaks = {
    run: {rate: np.median([s["peak_hz"] for s in by_rate[rate].values()]) for rate in rates}
    for run, by_rate in data.items()
}
# Candidate true frequency: score every frequency by how strong the spectrum is at its alias,
# relative to the white floor, summed in dB over the three rates and averaged over ADCs.
candidate_hz = np.arange(0, 30e6, 1e3)
score_db = {}
for run, by_rate in data.items():
    total = np.zeros_like(candidate_hz)
    for rate in rates:
        per_adc = [
            10 * np.log10(np.interp(alias(candidate_hz, rate), s["frequency_hz"], s["psd"]) / s["floor"])
            for s in by_rate[rate].values()
        ]
        total += np.mean(per_adc, axis=0)
    score_db[run] = total
true_hz = {run: candidate_hz[np.argmax(score)] for run, score in score_db.items()}
print({run: f"{f / 1e6:.3f} MHz" for run, f in true_hz.items()})

for run, by_rate in data.items():
    for by_adc in by_rate.values():
        for s_ in by_adc.values():
            split_interference(s_, true_hz[run])

# Report the split for every capture; the figures pick out representative ones.
for run, by_rate in data.items():
    for rate in rates:
        for adc, s in sorted(by_rate[rate].items()):
            print(
                f"{run:22} {rate / 1e6:4.0f} MSPS ADC{adc:02d}: total {s['total_rms']:.2f} LSB = "
                f"interference {s['tone_rms']:.2f} ({s['fundamental_hz'] / 1e6:.3f} MHz + harmonics) ⊕ rest {s['rest_rms']:.2f} LSB"
            )

# --- Figure 1: what "splitting the variance" means, for one capture -----------------------------
run0 = next(iter(data))
s = data[run0][rates[0]][0]
rate = rates[0]
with mpl.rc_context(PLOT_STYLE):
    fig, (ax_time, ax_asd, ax_cum) = plt.subplots(3, 1, figsize=(9.6, 10.0))

    # (a) Time domain: raw codes and the tone component alone (FFT band-pass around the peak).
    spectrum = np.fft.rfft(s["codes"])
    fft_hz = np.fft.rfftfreq(len(s["codes"]), 1 / rate)
    in_band = np.interp(fft_hz, s["frequency_hz"], s["tone_band"].astype(float)) > 0.5
    tone_only = np.fft.irfft(np.where(in_band, spectrum, 0), len(s["codes"]))
    shown = slice(0, 200)  # 100 µs at 2 MSPS
    time_us = np.arange(len(s["codes"]))[shown] / rate * 1e6
    ax_time.step(time_us, s["codes"][shown], where="mid", label=f"output code − mean ({s['total_rms']:.2f} LSB RMS)")
    ax_time.plot(
        time_us,
        tone_only[shown],
        linewidth=2.0,
        label=f"interference only: {s['fundamental_hz'] / 1e6:.2f} MHz + harmonics, aliased",
    )
    ax_time.set_xlabel("Time (µs)")
    ax_time.set_ylabel("Code (LSB)")
    ax_time.set_title("(a) The codes are an aliased periodic interferer plus fast, random scatter")
    ax_time.legend(loc="upper right")

    # (b) Spectrum: white floor vs the tone sitting on top of it.
    f_khz = s["frequency_hz"] / 1e3
    asd = np.sqrt(s["psd"])
    ax_asd.semilogy(f_khz, asd, label="code noise spectrum")
    floor_line = ax_asd.axhline(
        np.sqrt(s["floor"]),
        linestyle="--",
        label=f"white floor: {s['rest_rms']:.2f} LSB RMS over 0–{rate / 2e6:g} MHz (broadband)",
    )
    ax_asd.fill_between(
        f_khz,
        np.sqrt(s["floor"]),
        asd,
        where=s["tone_band"],
        alpha=0.5,
        label=f"area above floor in the harmonic bands: {s['tone_rms']:.2f} LSB RMS (interference)",
    )
    for k, harmonic in enumerate(s["harmonic_hz"][:4], start=1):
        ax_asd.annotate(
            f"{k}·f₀" if k > 1 else "f₀",
            xy=(harmonic / 1e3, asd[np.argmin(np.abs(s["frequency_hz"] - harmonic))]),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
        )
    ax_asd.set_xlim(0, rate / 2e3)
    ax_asd.set_xlabel("Frequency (kHz)")
    ax_asd.set_ylabel("Amplitude spectral density (LSB/√Hz)")
    ax_asd.set_title("(b) Noise spectrum of the codes: flat floor plus the aliased harmonics of one interferer")
    ax_asd.legend(loc="upper right")

    # (c) Cumulative RMS: how the total builds up from 0 Hz to Nyquist.
    bin_hz = s["frequency_hz"][1] - s["frequency_hz"][0]
    cumulative = np.sqrt(np.cumsum(s["psd"]) * bin_hz)
    ax_cum.plot(f_khz, cumulative, label="measured: √∫ PSD from 0 to f")
    ax_cum.plot(f_khz, np.sqrt(s["floor"] * s["frequency_hz"]), linestyle="--", label="white floor alone: √(floor · f)")
    ax_cum.annotate(
        "step at f₀; smaller steps\nat its harmonics",
        xy=(s["peak_hz"] / 1e3, np.interp(s["peak_hz"], s["frequency_hz"], cumulative)),
        xytext=(s["peak_hz"] / 1e3 + 120, 0.45),
        arrowprops={"arrowstyle": "->"},
    )
    ax_cum.text(
        0.98,
        0.08,
        f"{s['total_rms']:.2f}² = {s['tone_rms']:.2f}² + {s['rest_rms']:.2f}²   (LSB²)",
        transform=ax_cum.transAxes,
        ha="right",
    )
    ax_cum.set_xlim(0, rate / 2e3)
    ax_cum.set_ylim(0, None)
    ax_cum.set_xlabel("Frequency (kHz)")
    ax_cum.set_ylabel("Cumulative noise (LSB RMS)")
    ax_cum.set_title("(c) Variances add: total² = interference² + broadband²")
    ax_cum.legend(loc="lower right", bbox_to_anchor=(1.0, 0.15))
    for ax in (ax_time, ax_asd, ax_cum):
        style_grid(ax)
    fig.suptitle(f"Splitting the code variance – ADC00, {rate / 1e6:g} MSPS, 4of8 sequence, {run0}")
    save_figure(fig, OUT_DIR / "1_variance_split")

# --- Figure 2: the same interferer at three conversion rates ------------------------------------
with mpl.rc_context(PLOT_STYLE):
    fig, axes = plt.subplots(len(rates), len(data), figsize=(12.0, 9.0), sharey=True)
    for column, (run, by_rate) in enumerate(data.items()):
        for row, rate in enumerate(rates):
            ax = axes[row, column]
            for adc, s in sorted(by_rate[rate].items()):
                ax.semilogy(
                    s["frequency_hz"] / 1e6, np.sqrt(s["psd"]), label=f"ADC{adc:02d} ({s['total_rms']:.2f} LSB RMS)"
                )
            for k in range(1, 5):
                ax.axvline(
                    alias(k * true_hz[run], rate) / 1e6,
                    linestyle=":" if k == 1 else (0, (1, 4)),
                    color=mpl.rcParams["axes.edgecolor"],
                    label=f"aliases of {true_hz[run] / 1e6:.2f} MHz (×1 dotted, ×2–4 sparse)" if k == 1 else None,
                )
            ax.set_xlim(0, rate / 2e6)
            ax.set_title(f"{rate / 1e6:g} MSPS – {run}")
            ax.legend(loc="upper right", fontsize=8)
            style_grid(ax)
            if row == len(rates) - 1:
                ax.set_xlabel("Frequency, 0 to Nyquist (MHz)")
            if column == 0:
                ax.set_ylabel("ASD (LSB/√Hz)")
    fig.suptitle(
        "Code noise spectra at three conversion rates – the interferer and its harmonics move, the floor stays"
    )
    save_figure(fig, OUT_DIR / "2_spectra_by_rate")

# --- Figure 3: unfolding the aliases to find the true frequency ---------------------------------
with mpl.rc_context(PLOT_STYLE):
    fig, (ax_fold, ax_score) = plt.subplots(2, 1, figsize=(9.6, 8.5), sharex=True)
    run = next(iter(data))
    for rate in rates:
        (line,) = ax_fold.plot(candidate_hz / 1e6, alias(candidate_hz, rate) / 1e6, label=f"{rate / 1e6:g} MSPS fold")
        ax_fold.axhline(
            peaks[run][rate] / 1e6,
            linestyle=":",
            color=line.get_color(),
            label=f"observed at {rate / 1e6:g} MSPS: {peaks[run][rate] / 1e3:.0f} kHz",
        )
    ax_fold.axvline(true_hz[run] / 1e6, linestyle="--", color=mpl.rcParams["axes.edgecolor"])
    ax_fold.set_ylabel("Apparent frequency in codes (MHz)")
    ax_fold.set_title(f"(a) Every rate folds a true frequency differently ({run})")
    ax_fold.legend(loc="upper right", fontsize=8, ncols=2)
    for run, score in score_db.items():
        ax_score.plot(candidate_hz / 1e6, score, label=f"{run}: best {true_hz[run] / 1e6:.2f} MHz")
    ax_score.set_xlabel("Candidate true interferer frequency (MHz)")
    ax_score.set_ylabel("Spectrum above floor at\nall three aliases (dB, summed)")
    ax_score.set_title("(b) Only a few frequencies line up with all three observed peaks")
    ax_score.text(
        0.01,
        0.03,
        "Repeats every 30 MHz (LCM of 2, 6, 10 MHz) and mirrors about 15 MHz: 8.15 ≡ 21.85 MHz",
        transform=ax_score.transAxes,
        va="bottom",
    )
    ax_score.legend(loc="upper right")
    for ax in (ax_fold, ax_score):
        style_grid(ax)
    fig.suptitle("Locating the interferer from its aliases")
    save_figure(fig, OUT_DIR / "3_alias_search")
print(f"Figures in {OUT_DIR}")
