"""Minimal serializer-sequencer pattern test.

Each pattern string is a space-separated list of serializer words.  Each word
is ``serdes_ratio`` bits wide and represents that many serialized time slices
for one output channel.  The function spreads each track across
``serdes_ratio`` parallel sequencer lanes, which the FPGA's 8:1 OSERDES
recombines into a single high-speed serial output.

Run from the repository root after programming the serializer firmware:

    uv run python flow/scans/test_serdes.py
"""

from __future__ import annotations

import csv
import socket
import time
from array import array
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from yaml import safe_load

from flow.scans.plot import (
    LEGEND_FACE_COLOR,
    NORD_BLUE,
    NORD_GREEN,
    NORD_RED,
    PNG_FACE_COLOR,
    SPINE_COLOR,
    TEXT_COLOR,
    style_ax,
    style_grid,
)

MAP_PATH = Path(__file__).resolve().parent / "map_fpga.yaml"
SCOPE_IP = "192.168.10.60"
SCOPE_PORT = 4000
SCOPE_OUT_DIR = Path("build/scope")
SCOPE_BANDWIDTH_HZ = 2.0e9
SEQ_CLK_HZ = 200.0e6

SERDES_RATIO = 8
# fmt: off
SEQ_PATTERNS = {
    "INIT":    "00000000 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "SAMP":    "00000000 00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "COMP":    "00000000 00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    #"COMP":    "01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 01010101 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "LOGIC":   "00000000 00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "RX_EN":   "00000000 00000000 00000000 00000000 00000000 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "RX_TEST": "00000000 00000000 00000000 00000000 11111111 11111111 00001111 00001111 00001111 00001111 00000000 11111111 00001111 11111111 11111111 00001111 00001111 00001111 00001111 00000000 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
}
# fmt: on


def bitarray_to_seq_gen_format(
    patterns: dict[str, str],
    serdes_ratio: int,
) -> array:
    """Build the raw sequencer memory image from per-track serializer patterns.

    Each pattern string is space-separated serializer words, one per sequencer
    fabric tick.  Each word is ``serdes_ratio`` bits: the first character is
    OSERDES D1 (data[0]), the last is D8 (data[7]).

    The function spreads each track across ``serdes_ratio`` parallel sequencer
    lanes.  The FPGA's ``ramb_8_to_n`` (WIDTH>8) packs one byte per lane per
    sequencer word, so byte 0 of each word is the first track's OSERDES byte,
    byte 1 is the second track's, etc.  Unused lanes are zero-filled.

    Returns an ``array("B")`` ready for ``seq_gen.set_data()``.
    """
    tracks = tuple(patterns.keys())
    n_tracks = len(tracks)

    # Parse and validate all patterns.
    parsed: dict[str, list[str]] = {}
    seq_words: int | None = None
    for name, pattern in patterns.items():
        words = pattern.split()
        if seq_words is None:
            seq_words = len(words)
        elif len(words) != seq_words:
            raise ValueError(f"{name}: expected {seq_words} words, got {len(words)}")
        for word in words:
            if len(word) != serdes_ratio or any(bit not in "01" for bit in word):
                raise ValueError(f"{name}: invalid serializer word {word!r}")
        parsed[name] = words

    assert seq_words is not None
    used_bits_per_word = n_tracks * serdes_ratio
    if used_bits_per_word % 8:
        raise ValueError(f"used_bits_per_word={used_bits_per_word} is not byte-aligned")

    # The FPGA serializer sequencer is currently OUT_BITS=64: eight byte-wide
    # lanes per sequencer word.  Only six lanes are used here
    # (INIT/SAMP/COMP/LOGIC/RX_EN/RX_TEST); the remaining two lanes must be
    # explicitly padded so each following word starts on the next 64-bit RAM row.
    seq_gen_lanes = 8
    if n_tracks > seq_gen_lanes:
        raise ValueError(f"{n_tracks} tracks do not fit in {seq_gen_lanes} seq_gen lanes")

    memory = array("B")
    for word_index in range(seq_words):
        for name in tracks:
            value = 0
            for lane, bit in enumerate(parsed[name][word_index]):
                value |= int(bit) << lane
            memory.append(value)
        memory.extend(0 for _ in range(seq_gen_lanes - n_tracks))

    expected = seq_words * seq_gen_lanes
    if len(memory) != expected:
        raise RuntimeError(f"expected {expected} bytes, built {len(memory)}")
    return memory


def capture_and_plot_scope_waveforms(
    ip: str = SCOPE_IP,
    port: int = SCOPE_PORT,
    out_dir: Path = SCOPE_OUT_DIR,
) -> tuple[Path, Path]:
    labels = {1: "seq_init", 2: "seq_samp", 3: "seq_comp", 4: "seq_logic"}

    def write(sock: socket.socket, command: str) -> None:
        sock.sendall(command.encode() + b"\n")

    def query(sock: socket.socket, command: str) -> str:
        write(sock, command)
        data = bytearray()
        while not data.endswith(b"\n"):
            data.extend(sock.recv(1_000_000))
        return data.decode(errors="replace").strip()

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")

    traces: dict[int, tuple[list[float], list[float], list[int]]] = {}
    with socket.create_connection((ip, port), timeout=5) as scope:
        scope.settimeout(10)
        print(query(scope, "*IDN?"))
        for channel in labels:
            write(scope, f"DATA:SOURCE CH{channel}")
            write(scope, "DATA:ENCdg ASCII")
            write(scope, "DATA:WIDTH 2")
            write(scope, "DATA:START 1")
            write(scope, f"DATA:STOP {query(scope, 'HORizontal:RECOrdlength?').split()[-1]}")

            xincr = float(query(scope, "WFMOutpre:XINCR?").split()[-1])
            xzero = float(query(scope, "WFMOutpre:XZERO?").split()[-1])
            pt_off = float(query(scope, "WFMOutpre:PT_OFF?").split()[-1])
            ymult = float(query(scope, "WFMOutpre:YMULT?").split()[-1])
            yoff = float(query(scope, "WFMOutpre:YOFF?").split()[-1])
            yzero = float(query(scope, "WFMOutpre:YZERO?").split()[-1])

            raw = [int(value) for value in query(scope, "CURVE?").split(",") if value]
            time_s = [xzero + (index - pt_off) * xincr for index in range(len(raw))]
            volts = [(value - yoff) * ymult + yzero for value in raw]
            traces[channel] = (time_s, volts, raw)

    csv_path = out_dir / f"serdes_scope_{stamp}.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["time_s", *[f"{labels[channel]}_v" for channel in labels], *[f"{labels[channel]}_raw" for channel in labels]]
        )
        n_samples = min(len(trace[0]) for trace in traces.values())
        for index in range(n_samples):
            writer.writerow(
                [
                    traces[1][0][index],
                    *[traces[channel][1][index] for channel in labels],
                    *[traces[channel][2][index] for channel in labels],
                ]
            )

    png_path = out_dir / f"serdes_scope_{stamp}.png"
    plot_paths = plot_scope_csv(csv_path, png_path)

    print(f"Saved scope waveform CSV: {csv_path}")
    for plot_path in plot_paths:
        print(f"Saved scope waveform plot: {plot_path}")
    return csv_path, png_path


def plot_scope_csv(csv_path: Path, png_path: Path | None = None) -> tuple[Path, ...]:
    labels = ["seq_init", "seq_samp", "seq_comp", "seq_logic"]
    colors = [NORD_BLUE, NORD_GREEN, NORD_RED, "#D08770"]

    rows = []
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))

    time_ns = [float(row["time_s"]) * 1e9 for row in rows]
    voltages = {label: [float(row[f"{label}_v"]) for row in rows] for label in labels}

    active_indices = []
    edge_count = max(1, len(rows) // 20)
    for label in labels:
        values = voltages[label]
        span = max(values) - min(values)
        if span <= 1e-3:
            continue
        baseline_samples = sorted(values[:edge_count] + values[-edge_count:])
        baseline = baseline_samples[len(baseline_samples) // 2]
        threshold = 0.15 * span
        active_indices.extend(index for index, value in enumerate(values) if abs(value - baseline) > threshold)

    if active_indices:
        start = time_ns[min(active_indices)]
        stop = time_ns[max(active_indices)]
        pad = 0.05 * (stop - start)
        xlim = (start - pad, stop + pad)
    else:
        xlim = (time_ns[0], time_ns[-1])

    fig, axes = plt.subplots(4, 1, figsize=(8, 6.4), sharex=True)
    fig.patch.set_facecolor(PNG_FACE_COLOR)
    axes[0].set_title("Measured ADC LVDS sequencer inputs", color=TEXT_COLOR, pad=6)

    for ax, label, color in zip(axes, labels, colors, strict=True):
        volts = [float(row[f"{label}_v"]) for row in rows]
        ax.plot(time_ns, volts, color=color, linewidth=1.2)
        ax.set_ylabel(f"{label} (V)", fontfamily="monospace")
        ax.set_xlim(*xlim)
        style_ax(ax)
        style_grid(ax)

    info = "\n".join(
        (
            f"Sequencer rate: {SEQ_CLK_HZ / 1e6:.0f} MHz",
            f"8:1 serializer rate: {SEQ_CLK_HZ * SERDES_RATIO / 1e9:.1f} GHz",
            f"Scope bandwidth: {SCOPE_BANDWIDTH_HZ / 1e9:.1f} GHz",
        )
    )
    axes[0].text(
        0.98,
        0.88,
        info,
        transform=axes[0].transAxes,
        ha="right",
        va="top",
        color=TEXT_COLOR,
        bbox={"boxstyle": "round", "facecolor": LEGEND_FACE_COLOR, "edgecolor": SPINE_COLOR, "alpha": 0.9},
    )

    axes[-1].set_xlabel("Time (ns)")
    fig.subplots_adjust(left=0.13, right=0.985, bottom=0.09, top=0.93, hspace=0.18)
    png_path = png_path or csv_path.with_suffix(".png")
    plot_paths = (png_path, png_path.with_suffix(".pdf"), png_path.with_suffix(".svg"))
    for plot_path in plot_paths:
        save_kwargs = {"facecolor": PNG_FACE_COLOR}
        if plot_path.suffix == ".png":
            save_kwargs["dpi"] = 200
        fig.savefig(plot_path, **save_kwargs)
    plt.close(fig)
    return plot_paths


def main() -> None:
    from basil.dut import Dut

    config = safe_load(MAP_PATH.read_text())
    config["transfer_layer"] = [layer for layer in config["transfer_layer"] if layer["name"] != "visa0"]
    config["hw_drivers"] = [driver for driver in config["hw_drivers"] if driver["name"] != "psu0"]
    daq = Dut(config)
    daq.init()

    daq["gpio0"]["RST_B"] = 0
    daq["gpio0"].write()
    daq["gpio0"]["RST_B"] = 1
    daq["gpio0"].write()

    repeat = 2
    memory = bitarray_to_seq_gen_format(SEQ_PATTERNS, SERDES_RATIO)
    # Write raw bytes directly to seq_gen memory, bypassing TrackRegister.
    # TrackRegister.write() does bit/byte reversal that only matches the
    # original 8-bit-wide sequencer; for the 64-bit serializer firmware the
    # reversal scrambles the OSERDES byte lanes.  _drv reaches through the
    # TrackRegister (RL) wrapper to the underlying seq_gen (HL) driver, which
    # exposes set_data() for writing sequencer memory verbatim.
    daq["seq0"]._drv.set_data(memory)
    daq["seq0"].set_size(len(SEQ_PATTERNS["INIT"].split()))
    daq["seq0"].set_clk_divide(1)
    daq["seq0"].set_repeat(repeat)
    daq["seq0"].set_en_ext_start(False)
    daq["seq0"].start()

    print(f"Loaded serializer sequencer pattern: repeat={repeat}")
    print("Started sequencer")

    capture_and_plot_scope_waveforms()


if __name__ == "__main__":
    main()
