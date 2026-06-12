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

from flow.scans.basic import N_SWEEP_POINTS, V_START, V_STOP, VINP_SWEEP_V

VDD = 1.2
CONVPER_S = 1.28e-6
SEQ_BIT_S = 20e-9
EDGE_S = 0.1e-9
OUTDIR = Path(__file__).resolve().parents[2] / "build" / "adc_pex" / "pwl"
PLOT_PATH = Path(__file__).resolve().parents[2] / "build" / "adc_pex" / "pwl_waveforms.png"

TRACKS = {
    "seq_init": "00 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
    "seq_samp": "00 00 11 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
    "seq_comp": "00 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00 00 00 00 00 00 00 00 00 00",
    # basic.py LOGIC track maps to the ADC seq_update input.
    "seq_update": "00 01 00 00 00 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 00 00 00 00 00 00 00 00 00 00 00",
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
    if N_SWEEP_POINTS < 2:
        raise ValueError("N_SWEEP_POINTS must be at least 2")

    points = [(0.0, VINP_SWEEP_V[0])]
    previous = VINP_SWEEP_V[0]
    for index, value in enumerate(VINP_SWEEP_V[1:], start=1):
        time_s = index * CONVPER_S
        points.append((time_s - EDGE_S, previous))
        points.append((time_s, value))
        previous = value
    points.append((N_SWEEP_POINTS * CONVPER_S, previous))
    return points


def track_bits(pattern: str) -> list[int]:
    bits = [int(bit) for bit in pattern.replace(" ", "")]
    if len(bits) != 64:
        raise ValueError(f"expected 64 sequencer bits, got {len(bits)} from {pattern!r}")
    return bits


def sequencer_points(pattern: str) -> list[tuple[float, float]]:
    bits = track_bits(pattern)
    timeline = bits * N_SWEEP_POINTS
    points: list[tuple[float, float]] = [(0.0, timeline[0] * VDD)]
    previous = timeline[0]

    for index, bit in enumerate(timeline[1:], start=1):
        if bit == previous:
            continue
        boundary_s = index * SEQ_BIT_S
        points.append((boundary_s, previous * VDD))
        points.append((boundary_s + EDGE_S, bit * VDD))
        previous = bit

    points.append((N_SWEEP_POINTS * CONVPER_S, previous * VDD))
    return points


def main() -> None:
    print("Generating ADC PEX Spectre PWL files")
    print(f"Sweep points: {N_SWEEP_POINTS} Vin_p values from {V_START:.3f} V to {V_STOP:.3f} V")
    print(f"Vdiff range: {V_START - 0.6:.3f} V to {V_STOP - 0.6:.3f} V")
    print(f"Conversion period: {CONVPER_S / 1e-6:.3f} us, tstop: {N_SWEEP_POINTS * CONVPER_S / 1e-6:.3f} us")

    waveforms = {"vin_p": vin_p_points()}
    for name, pattern in TRACKS.items():
        waveforms[name] = sequencer_points(pattern)

    for name, points in waveforms.items():
        write_pwl(OUTDIR / f"{name}.pwl", points)
    plot_pwl_waveforms(waveforms)


if __name__ == "__main__":
    main()
