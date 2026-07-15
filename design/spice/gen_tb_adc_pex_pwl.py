#!/usr/bin/env python3
"""Generate external PWL files for ``tb_adc_pex_spectre.sp``.

Run from /local/frida before launching Spectre:

    uv run python design/spice/gen_tb_adc_pex_pwl.py

This writes compact two-column Spectre PWL files under ``build/adc_pex/pwl``.
The Spectre deck references these files instead of carrying thousands of inline
PWL points.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

VDD = 1.2
N_CONVERSIONS = 121
TRANSFER_V_START = 0.0
TRANSFER_V_STOP = 1.2
TRANSFER_V_STEP = 0.01
TRANSFER_VINP_SWEEP = tuple(
    TRANSFER_V_START + step * TRANSFER_V_STEP
    for step in range(round((TRANSFER_V_STOP - TRANSFER_V_START) / TRANSFER_V_STEP) + 1)
)
CONVPER_S = 1.28e-6
SERDES_RATIO = 8
SEQ_WORDS = 32
# Use the same 32x8 track format as the FPGA while retaining the slower PEX
# conversion period. Each simulated serializer interval is therefore 5 ns.
SERDES_INTERVAL_S = CONVPER_S / (SEQ_WORDS * SERDES_RATIO)
EDGE_S = 0.1e-9
OUTDIR = Path(__file__).resolve().parents[2] / "build" / "adc_pex" / "pwl"
PLOT_PATH = Path(__file__).resolve().parents[2] / "build" / "adc_pex" / "pwl_waveforms.png"

SEQ_PATTERNS = {
    "INIT": "00000000 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "SAMP": "00000000 00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "COMP": "00000000 00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "LOGIC": "00000000 00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
}

PWL_TRACK_NAMES = {
    "INIT": "seq_init",
    "SAMP": "seq_samp",
    "COMP": "seq_comp",
    "LOGIC": "seq_update",
}


def fmt_time(seconds: float) -> str:
    return f"{seconds / 1e-6:.4f}u"


def fmt_value(value: float) -> str:
    return f"{value:.6g}"


def write_pwl(path: Path, points: list[tuple[float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for time_s, value in points:
            f.write(f"{fmt_time(time_s)} {fmt_value(value)}\n")
    print(f"wrote {len(points)} points to {path}")


def plot_pwl_waveforms(waveforms: dict[str, list[tuple[float, float]]], out: Path = PLOT_PATH) -> None:
    """Plot generated PWL waveforms as stacked line traces sharing one time axis."""
    out.parent.mkdir(parents=True, exist_ok=True)
    names = list(waveforms)
    fig, axes = plt.subplots(len(names), 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    if len(names) == 1:
        axes = [axes]

    for ax, name in zip(axes, names, strict=True):
        points = waveforms[name]
        times_us = [time_s / 1e-6 for time_s, _ in points]
        values = [value for _, value in points]
        ax.plot(times_us, values, linewidth=1.2)
        ax.set_ylabel(f"{name}\n(V)")
        ax.grid(True, alpha=0.3)
        ax.set_ylim(-0.08, 1.28)

    axes[-1].set_xlabel("Time (µs)")
    fig.suptitle("ADC PEX Spectre PWL waveforms")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote PWL waveform plot to {out}")


def vin_p_points() -> list[tuple[float, float]]:
    if len(TRANSFER_VINP_SWEEP) != N_CONVERSIONS:
        raise ValueError(f"transfer sweep has {len(TRANSFER_VINP_SWEEP)} points, expected {N_CONVERSIONS}")

    points = [(0.0, TRANSFER_VINP_SWEEP[0])]
    previous = TRANSFER_VINP_SWEEP[0]
    for index, value in enumerate(TRANSFER_VINP_SWEEP[1:], start=1):
        time_s = index * CONVPER_S
        points.append((time_s - EDGE_S, previous))
        points.append((time_s, value))
        previous = value
    points.append((N_CONVERSIONS * CONVPER_S, previous))
    return points


def track_bits(pattern: str) -> list[int]:
    words = pattern.split()
    if len(words) != SEQ_WORDS:
        raise ValueError(f"expected {SEQ_WORDS} serializer words, got {len(words)} from {pattern!r}")
    for word in words:
        if len(word) != SERDES_RATIO or any(bit not in "01" for bit in word):
            raise ValueError(f"invalid serializer word {word!r}; expected {SERDES_RATIO} bits")
    return [int(bit) for word in words for bit in word]


def sequencer_points(pattern: str) -> list[tuple[float, float]]:
    bits = track_bits(pattern)
    timeline = bits * N_CONVERSIONS
    points: list[tuple[float, float]] = [(0.0, timeline[0] * VDD)]
    previous = timeline[0]

    for index, bit in enumerate(timeline[1:], start=1):
        if bit == previous:
            continue
        boundary_s = index * SERDES_INTERVAL_S
        points.append((boundary_s, previous * VDD))
        points.append((boundary_s + EDGE_S, bit * VDD))
        previous = bit

    points.append((N_CONVERSIONS * CONVPER_S, previous * VDD))
    return points


def main() -> None:
    print("Generating ADC PEX Spectre PWL files")
    print(f"Sweep points: {N_CONVERSIONS} Vin_p values from {TRANSFER_V_START:.3f} V to {TRANSFER_V_STOP:.3f} V")
    print(f"Vdiff range: {TRANSFER_V_START - 0.6:.3f} V to {TRANSFER_V_STOP - 0.6:.3f} V")
    print(f"Conversion period: {CONVPER_S / 1e-6:.3f} us, tstop: {N_CONVERSIONS * CONVPER_S / 1e-6:.3f} us")
    print(
        f"Track format: {SEQ_WORDS} words x {SERDES_RATIO}:1 intervals; "
        f"simulated interval: {SERDES_INTERVAL_S / 1e-9:.3f} ns"
    )

    waveforms = {"vin_p": vin_p_points()}
    for track, name in PWL_TRACK_NAMES.items():
        waveforms[name] = sequencer_points(SEQ_PATTERNS[track])

    for name, points in waveforms.items():
        write_pwl(OUTDIR / f"{name}.pwl", points)
    plot_pwl_waveforms(waveforms)


if __name__ == "__main__":
    main()
