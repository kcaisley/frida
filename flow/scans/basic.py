"""FRIDA ADC basic scan and readout script."""

import csv
import math
from pathlib import Path
from time import sleep

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from basil.dut import Dut
from bitarray import bitarray

# TODO:
# Check what plot looks like, for:
# - different channels
# - different common mode voltages, and the full ADC range
# - VDDA / VDDD +-10%
# - Various clock speeds
# - phase between logic and comp clock (increase clock speed of sequencer)
# - different DAC init voltages
# - with diff caps enabled / disabled

NUM_ADCS = 1
N_SWEEP_POINTS = 100
V_START = 0.010
V_STOP = 1.190
SLEEP_TIME = 0.2
CONVERSIONS_PER_VIN = 10
SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / "basic_scan"

CSV_FIELDS = [
    "adc",
    "sweep_index",
    "vin_set_v",
    "vin_read_v",
    "conversion_index",
    "raw_word0",
    "raw_word1",
    "id0",
    "id1",
    "frame0",
    "frame1",
    "spi0",
    "spi1",
    "Bbits",
    "Dout",
]

# Capacitor array weights from caparray.sp, labeled left-to-right as C16..C1.
# These sum to 2047 = 2^11 - 1 (11-bit DAC range). The 17 output-bit weights
# W16..W0 are [2*C16, 2*C15, ..., 2*C1, 1], which sum to 4095 = 2^12 - 1.
CAP_WEIGHTS = [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
CODE_WEIGHTS = [2 * weight for weight in CAP_WEIGHTS] + [1]
NUM_CAPTURE_BITS = len(CODE_WEIGHTS)
DECIMATE_PHASE = 0  # Try 1 if the decoded transfer still looks phase-shifted/noisy.
MAX_RAW_FASTRX_WORDS = 2 * CONVERSIONS_PER_VIN  # Print all expected raw words; all words are still decoded.


def scpi_float(value) -> float:
    """Convert a SCPI response to float, accepting comma-separated readback strings."""
    return float(str(value).strip().split(",")[0])


def decode_conversion(spi0: int, spi1: int, data_size: int) -> tuple[str, int]:
    """Decode two FastRX words into Bbits and recombine W16..W0 into Dout.

    fast_spi_rx shifts samples left, so temporal order within each displayed word is
    left-to-right: bit DATA_SIZE-1 -> bit 0. The decimated 17-bit output is labeled
    Bbits = B16..B0 and recombined directly with CODE_WEIGHTS = W16..W0.
    """
    samples = [(spi0 >> i) & 1 for i in range(data_size - 1, -1, -1)]
    samples += [(spi1 >> i) & 1 for i in range(data_size - 1, -1, -1)]
    decimated = [samples[DECIMATE_PHASE + 2 * i] for i in range(NUM_CAPTURE_BITS)]

    Bbits = "".join(str(bit) for bit in decimated)
    Dout = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, decimated))
    return Bbits, Dout


def write_adc_csv(adc_index: int, rows: list[dict]) -> Path:
    """Write one ADC's captured conversion data before plotting it."""
    SCAN_OUTDIR.mkdir(parents=True, exist_ok=True)
    csv_path = SCAN_OUTDIR / f"adc_{adc_index:02d}.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"ADC {adc_index:02d}: saved data to {csv_path}")
    return csv_path


def plot_adc_transfer(adc_index: int, rows: list[dict]) -> Path:
    """Create one transfer plot per ADC from already-saved conversion rows."""
    plot_path = SCAN_OUTDIR / f"adc_{adc_index:02d}_transfer.png"
    voltages_mv = [float(row["vin_set_v"]) * 1000 for row in rows]
    codes = [int(row["Dout"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    if codes:
        ax.scatter(voltages_mv, codes, s=14, alpha=0.45, label="individual conversions")
        ax.legend()
    ax.set_title(f"FRIDA ADC {adc_index:02d} basic voltage sweep")
    ax.set_xlabel("Input voltage (mV)")
    ax.set_ylabel("Effective output code")
    ax.set_xlim(V_START * 1000, V_STOP * 1000)
    ax.set_ylim(0, 4095)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved transfer plot to {plot_path}")
    return plot_path


def plot_code_histogram(adc_index: int, rows: list[dict]) -> Path:
    """Plot a 1-code-bin histogram for repeated conversions at one input voltage."""
    plot_path = SCAN_OUTDIR / f"adc_{adc_index:02d}_histogram.png"
    codes = [int(row["Dout"]) for row in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    if codes:
        code_min = min(codes)
        code_max = max(codes)
        bins = [code - 0.5 for code in range(code_min, code_max + 2)]
        ax.hist(codes, bins=bins, alpha=0.65, edgecolor="black", label="output code counts")

        mean = sum(codes) / len(codes)
        variance = sum((code - mean) ** 2 for code in codes) / len(codes)
        sigma = math.sqrt(variance)
        stats = f"N = {len(codes)}\nμ = {mean:.2f} codes\nσ = {sigma:.2f} codes"
        ax.text(
            0.98,
            0.95,
            stats,
            transform=ax.transAxes,
            ha="right",
            va="top",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
        )

        ax.set_xlim(code_min - 1, code_max + 1)
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No decoded codes", transform=ax.transAxes, ha="center", va="center")

    if rows:
        voltage_mv = sum(float(row["vin_set_v"]) for row in rows) / len(rows) * 1000
        ax.set_title(f"FRIDA ADC {adc_index:02d} output-code histogram at {voltage_mv:.1f} mV")
    else:
        ax.set_title(f"FRIDA ADC {adc_index:02d} output-code histogram")
    ax.set_xlabel("Output code (Dout)")
    ax.set_ylabel("Conversions per 1-code bin")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"ADC {adc_index:02d}: saved histogram plot to {plot_path}")
    return plot_path


# Step 1: Connect to the DAQ hardware described by the FPGA Basil YAML map.
daq = Dut(str(Path(__file__).resolve().parent / "map_fpga.yaml"))
daq.init()

# Step 2: Release chip reset.
daq["gpio0"]["RST_B"] = 0
daq["gpio0"].write()
daq["gpio0"]["RST_B"] = 1
daq["gpio0"].write()

# Step 3: Load the shared ADC sequencer pattern.
daq["seq0"].clear()
# Note: Python slices are half-open: start is inclusive, end is exclusive.
# Note: Sequencer is temporal left to right.
# fmt: off
#                                        0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
daq["seq0"]["INIT"][0:64] =    bitarray("00 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["SAMP"][0:64] =    bitarray("00 00 11 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["COMP"][0:64] =    bitarray("00 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["LOGIC"][0:64] =   bitarray("00 01 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00 00 00 00 00 00 00 00 00 00")
# daq["seq0"]["LOGIC"][0:64] =   bitarray("00 01 00 00 00 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["RX_EN"][0:64] =   bitarray("00 00 00 00 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["RX_TEST"][0:64] = bitarray("00 00 00 00 11 11 01 01 01 01 00 11 01 11 11 01 01 01 01 00 11 00 00 00 00 00 00 00 00 00 00 00")
                                    #      init      | ||                       |                   ||
                                    #         samp   | ||                                           ||
                                    #                comp0                                          ||
                                    #                  logic1                                       logic16
                                    #                   comp1                                        comp16
# fmt: on

# Step 4: Configure sequencer operation for software-start repeated conversions.
daq["seq0"].write(64)  # TrackRegister.write: basil/basil/RL/TrackRegister.py#L39
daq["seq0"].set_size(64)  # seq_gen.set_size: basil/HL/seq_gen.py#L59
daq["seq0"].set_clk_divide(1)  # seq_gen.set_clk_divide: basil/HL/seq_gen.py#L68
daq["seq0"].set_repeat(CONVERSIONS_PER_VIN)  # seq_gen.set_repeat: basil/HL/seq_gen.py#L77
# daq["seq0"].set_en_ext_start(True)  # GPIO external start via gpio0.SEQ_START.
daq["seq0"].set_en_ext_start(False)  # Software start via seq0.start().

# Step 5: Arm FastRX and route capture enable from the sequencer RX_EN track.
# FASTRX is a fast_spi_rx RegisterHardwareLayer (basil/HL/fast_spi_rx.py)
# RX_LOOPBACK = 1 sets fastrx_en to be driven by seq_out[4], the RX_EN track
# RX_LOOPBACK = 0 sets fastrx_en to be driven by gpio[6], shared with SEQ_START
daq["gpio0"]["RX_LOOPBACK"] = 0
daq["gpio0"].write()
daq["fastrx0"].reset()
daq["fastrx0"].set_en(True)

# RX_EN_MUX=1 sets fastrx_en to be driven by seq_out[4], the RX_EN track.
daq["gpio0"]["RX_EN_MUX"] = 1
daq["gpio0"].write()

# Step 6: Flush stale FIFO data and validate FastRX width before scanning.
daq["fifo0"]["RESET"]
daq["fifo0"].get_data()

data_size = daq["fastrx0"].get_size()
if data_size != NUM_CAPTURE_BITS:
    raise RuntimeError(f"FastRX DATA_SIZE={data_size}, expected {NUM_CAPTURE_BITS} from CAP_WEIGHTS")

# Step 7: Configure the Keithley 2450 as the ADC input voltage source.
daq["psu0"].source_volt()

# Step 8: Build the voltage sweep and scan each ADC one at a time.
voltages = [V_START + i * (V_STOP - V_START) / (N_SWEEP_POINTS - 1) for i in range(N_SWEEP_POINTS)]
print(f"\nStarting voltage sweep for {NUM_ADCS} ADCs...")
print(f"Cap weights C16..C1: {CAP_WEIGHTS}")
print(f"Bit weights W16..W0: {CODE_WEIGHTS}")

for adc_index in range(NUM_ADCS):
    print(f"\n=== Starting ADC {adc_index:02d} sweep ===")

    # Build 180-bit SPI config: selected ADC enabled, DACs=0xFFFF.
    bits = bitarray(180)
    bits.setall(0)

    # SPI config wiring:
    # - We fill 4 banks (banks 0..3). Each bank has 16 bit positions.
    # - Each bit of bank k is taken from the corresponding bit of 0xFFFF
    #   (pattern: 0xFFFF >> i) & 1 for i in 0..15.
    # - Banks are laid out consecutively in memory:
    #     bank 0: bits 0..15
    #     bank 1: bits 16..31
    #     bank 2: bits 32..47
    #     bank 3: bits 48..63
    # These bit arrays are big endian, but the hardware is little endian.
    bits[0:16] = bitarray("1111111111111111")  # DAC_ASTATE_P
    bits[16:32] = bitarray("1111111111111111")  # DAC_BSTATE_P
    bits[32:48] = bitarray("1111111111111111")  # DAC_ASTATE_N
    bits[48:64] = bitarray("1111111111111111")  # DAC_BSTATE_N

    # Per-ADC control bits start at bit 64, with 7 control bits per ADC:
    #   BASE+0 en_init       Enable INIT pulse (DAC reset before conversion)
    #   BASE+1 en_samp_p     Enable sample phase P-side
    #   BASE+2 en_samp_n     Enable sample phase N-side
    #   BASE+3 en_comp       Enable comparator clock
    #   BASE+4 en_update     Enable DAC update (load SAR decision into DAC)
    #   BASE+5 dac_mode      SAR mode (0 = calibration mode)
    #   BASE+6 dac_diffcaps  Enable differential caps (needed for unit caps)
    base = 64 + 7 * adc_index
    bits[base : base + 7] = bitarray("1111111")

    # MUX_SEL[3:0] selects which ADC comparator output reaches FastRX.
    # Verilog mapping: mux_sel = spi_bits[179:176], with bit 176 as the LSB.
    # Python slice order here is therefore LSB-first: [mux_sel[0], ..., mux_sel[3]].
    bits[176:180] = bitarray(f"{adc_index:04b}"[::-1])

    # Program SPI twice, preserving the behavior used by the working single-ADC script.
    spi_bytes = bits.tobytes()
    for _ in range(2):
        daq["spi0"].set_data(list(spi_bytes))
        daq["spi0"].set_size(180)
        daq["spi0"].start()
        daq["spi0"].wait_for_ready()

    raw = bytes(daq["spi0"].get_data(size=23))
    rb = bitarray()
    rb.frombytes(raw)
    rb = rb[:180]
    print(f"ADC {adc_index:02d} SPI verify: {((bits[1:] ^ rb[1:]).count(1))} mismatches (skip bit 0)")

    # Clear stale capture data before each ADC sweep.
    daq["fifo0"]["RESET"]
    daq["fifo0"].get_data()

    rows = []
    for sweep_index, voltage in enumerate(voltages):
        print(f"ADC {adc_index:02d}: setting PSU to {voltage * 1000:.0f} mV ({voltage:.3f} V)")
        daq["psu0"].set_voltage(voltage)
        daq["psu0"].on()
        sleep(SLEEP_TIME)
        actual = scpi_float(daq["psu0"].get_voltage())
        print(f"ADC {adc_index:02d}: PSU readback {actual * 1000:.0f} mV ({actual:.3f} V)")

        # Start the sequencer via the Basil bus. RX_EN_MUX=1 keeps FastRX enable driven
        # by the sequencer RX_EN track, so no GPIO start/holdoff signal is needed.
        daq["seq0"].start()

        # Old GPIO external-start version. If re-enabling this, also set:
        # daq["seq0"].set_en_ext_start(True)
        # daq["gpio0"]["SEQ_START"] = 1
        # daq["gpio0"].write()
        # sleep(0.001)
        # daq["gpio0"]["SEQ_START"] = 0
        # daq["gpio0"].write()

        while not daq["seq0"].is_done():  # is_done will not actually return 1, unless SEQ_START is ended.
            sleep(0.1)
            print(f"ADC {adc_index:02d}: waiting for sequencer!")

        data = daq["fifo0"].get_data()
        print(f"ADC {adc_index:02d}: FIFO ({len(data)} words)")

        # Show raw parsed words.
        for i in range(min(MAX_RAW_FASTRX_WORDS, len(data))):
            identifier, frame_counter, spi_data = daq["fastrx0"].parse_word(int(data[i]))
            data_str = f"{spi_data:0{data_size}b}"
            frame_str = f"{frame_counter:0{28 - data_size}b}" if 28 - data_size > 0 else ""
            if frame_str:
                print(f"  [{i}] ID={identifier:04b} frame={frame_str} data={data_str}")
            else:
                print(f"  [{i}] ID={identifier:04b} data={data_str}")

        if len(data) % 2:
            print(
                f"ADC {adc_index:02d}: warning: odd FIFO word count ({len(data)}); ignoring last word for code decode"
            )

        Dout_list = []
        Bbits_list = []
        for pair_idx in range(len(data) // 2):
            raw_word0 = int(data[2 * pair_idx])
            raw_word1 = int(data[2 * pair_idx + 1])
            id0, frame0, spi0 = daq["fastrx0"].parse_word(raw_word0)
            id1, frame1, spi1 = daq["fastrx0"].parse_word(raw_word1)
            if frame0 != frame1:
                print(f"ADC {adc_index:02d}: warning: paired FIFO words have different frames: {frame0} != {frame1}")

            Bbits, Dout = decode_conversion(spi0, spi1, data_size)
            Bbits_list.append(Bbits)
            Dout_list.append(Dout)
            rows.append(
                {
                    "adc": adc_index,
                    "sweep_index": sweep_index,
                    "vin_set_v": voltage,
                    "vin_read_v": actual,
                    "conversion_index": pair_idx,
                    "raw_word0": raw_word0,
                    "raw_word1": raw_word1,
                    "id0": id0,
                    "id1": id1,
                    "frame0": frame0,
                    "frame1": frame1,
                    "spi0": spi0,
                    "spi1": spi1,
                    "Bbits": Bbits,
                    "Dout": Dout,
                }
            )

        print(f"ADC {adc_index:02d}: Bbits_list B16..B0: {Bbits_list}")
        print(f"ADC {adc_index:02d}: Dout_list = sum(W16..W0 * B16..B0): {Dout_list}")
        print(
            f"ADC {adc_index:02d}: code spread={max(Dout_list) - min(Dout_list) if Dout_list else 'n/a'}, code average={sum(Dout_list) / len(Dout_list) if Dout_list else 'n/a'}"
        )
        print(f"ADC {adc_index:02d}: V={voltage * 1000:.1f}mV\n")

        # sleep based on Alex's gut feeling
        sleep(SLEEP_TIME)

    write_adc_csv(adc_index, rows)
    plot_adc_transfer(adc_index, rows)
    # plot_code_histogram expects rows from repeated conversions at one fixed input voltage.
    # Step 9: Always turn off the source output and close hardware connections.
    daq["psu0"].off()
    daq.close()

print("Done.")
