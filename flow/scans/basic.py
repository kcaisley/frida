"""FRIDA ADC basic scan and readout script."""

from pathlib import Path
from time import sleep

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from basil.dut import Dut
from bitarray import bitarray

N_SWEEP_POINTS = 100
V_START = 0.010
V_STOP = 1.190
SLEEP_TIME = 0.2
CONVERSIONS_PER_VIN = 10

daq = Dut(str(Path(__file__).resolve().parent / "map_fpga.yaml"))
daq.init()

# Release reset
daq["gpio0"]["RST_B"] = 0
daq["gpio0"].write()
daq["gpio0"]["RST_B"] = 1
daq["gpio0"].write()

# Build 180-bit SPI config: MUX_SEL=1, ADC_1 enabled, DACs=0x7FFF
bits = bitarray(180)
bits.setall(0)

# SPI config wiring:
# - We fill 4 banks (banks 0..3). Each bank has 16 bit positions.
# - Each bit of bank k is taken from the corresponding bit of 0x7FFF
#   (pattern: 0x7FFF >> i) & 1 for i in 0..15.
# - Banks are laid out consecutively in memory:
#     bank 0: bits 0..15
#     bank 1: bits 16..31
#     bank 2: bits 32..47
#     bank 3: bits 48..63

# Configure DAC values for ADC channels.
# All DACs are set to 0x7FFF.
# These bit arrays are big endian, but the hardware is little endian
bits[0:16] = bitarray("1111111111111111")  # DAC_ASTATE_P
bits[16:32] = bitarray("1111111111111111")  # DAC_BSTATE_P
bits[32:48] = bitarray("1111111111111111")  # DAC_ASTATE_N
bits[48:64] = bitarray("1111111111111111")  # DAC_BSTATE_N


# ADC_1 control bits (offset=71, 7 bits wide):
#   Bit   field     value  meaning
#   71    en_init   1      Enable INIT pulse (DAC reset before conversion)
#   72    en_samp_p 1      Enable sample phase P-side
#   73    en_samp_n 1      Enable sample phase N-side
#   74    en_comp   1      Enable comparator clock
#   75    en_update 1      Enable DAC update (load SAR decision into DAC)
#   76    dac_mode  1      SAR mode (0 = calibration mode)
#   77    dac_diffcaps 1   Enable differential caps (needed for unit caps)
#
# All 7 bits = 1 means full SAR operation. Only ADC_1 (offset 71..77) is
# enabled; ADC_0 (offset 64..70) and ADCs 2-15 (offset 78..176) stay 0.
bits[71:78] = bitarray("1111111")
# MUX_SEL[3:0] = 4'b0001, so we select ADC 1.
# Verilog mapping: mux_sel = spi_bits[179:176], with bit 176 as the LSB.
# Python slices are half-open, so 176:180 covers exactly four bits: 176, 177, 178, 179.
# Python slice order is therefore LSB-first: bits[176:180] = [mux_sel[0], ..., mux_sel[3]].
bits[176:180] = bitarray("1100")

spi_bytes = bits.tobytes()
daq["spi0"].set_data(list(spi_bytes))
daq["spi0"].set_size(180)
daq["spi0"].start()
daq["spi0"].wait_for_ready()

daq["spi0"].set_data(list(spi_bytes))
daq["spi0"].set_size(180)
daq["spi0"].start()
daq["spi0"].wait_for_ready()
raw = bytes(daq["spi0"].get_data(size=23))
rb = bitarray()
rb.frombytes(raw)
rb = rb[:180]
print(f"SPI verify: {((bits[1:] ^ rb[1:]).count(1))} mismatches (skip bit 0)")

# Load adc sequencer pattern (40 steps)
daq["seq0"].clear()
# Note: python slices are "half open": start number is inclusive, but end number is not
# Note: Sequencer is temporally shift left to right
# fmt: off
#                                        0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
daq["seq0"]["INIT"][0:64] =    bitarray("00 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["SAMP"][0:64] =    bitarray("00 00 11 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["COMP"][0:64] =    bitarray("00 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["LOGIC"][0:64] =   bitarray("00 01 00 00 00 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["RX_EN"][0:64] =   bitarray("00 00 00 00 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["RX_TEST"][0:64] = bitarray("00 00 00 00 11 11 01 01 01 01 00 11 01 11 11 01 01 01 01 00 11 00 00 00 00 00 00 00 00 00 00 00")
                                  #      init      | ||                       |                   ||
                                  #         samp   | ||                                           ||
                                  #                comp0                                          ||
                                  #                  logic1                                       logic16
                                  #                   comp1                                        comp16
# fmt: on

# Write the loaded sequence pattern to the sequencer hardware memory.
# - write() on TrackRegister serializes the bitarrays and sends them to seq_gen.
# - The argument '64' specifies the number of steps to write.
daq["seq0"].write(64)  # TrackRegister.write: basil/basil/RL/TrackRegister.py#L39

# Configure sequencer operational parameters.
# These methods are proxied from the seq_gen hardware driver (basil/HL/seq_gen.py)
# via the TrackRegister object.
daq["seq0"].set_size(64)  # seq_gen.set_size: basil/HL/seq_gen.py#L59
daq["seq0"].set_clk_divide(1)  # seq_gen.set_clk_divide: basil/HL/seq_gen.py#L68
daq["seq0"].set_repeat(CONVERSIONS_PER_VIN)  # seq_gen.set_repeat: basil/HL/seq_gen.py#L77
# daq["seq0"].set_en_ext_start(True)  # GPIO external start via gpio0.SEQ_START.
daq["seq0"].set_en_ext_start(False)  # Software start via seq0.start().

# Arm FastRX receiver
# FASTRX is a fast_spi_rx RegisterHardwareLayer (basil/HL/fast_spi_rx.py)
# RX_LOOPBACK = 1 sets fastrx_en to be driven by seq_out[4], the RX_EN track
# RX_LOOPBACK = 0 sets fastrx_en to be driven by gpio[6], shared with SEQ_START
# Enable loopback mode to use sequencer test data instead of COMP_OUT
# reset() clears internal state, set_en(True) enables capture on next clock edge
daq["gpio0"]["RX_LOOPBACK"] = 0
daq["gpio0"].write()
daq["fastrx0"].reset()
daq["fastrx0"].set_en(True)

# I belive one of these should flush stale TCP FIFO data from previous runs
# - fifo is a sitcp_fifo HardwareLayer (basil/HL/sitcp_fifo.py)
# - RESET clears the SiTCP buffer, get_data() drains any remaining
daq["fifo0"]["RESET"]
daq["fifo0"].get_data()

# RX_EN_MUX=1 sets fastrx_en to be driven by seq_out[4], the RX_EN track
# RX_EN_MUX=0 sets fastrx_en to be driven by gpio[6], shared with SEQ_START
# .write() pushes the full GPIO byte to the FPGA
daq["gpio0"]["RX_EN_MUX"] = 1
daq["gpio0"].write()

# Capacitor array weights from caparray.sp in temporal SAR decision order.
# The comparator decisions are captured MSB-first, so CAP_WEIGHTS[0] is the first
# decision weight and CAP_WEIGHTS[-1] is the last weighted decision. These sum to
# 2047 = 2^11 - 1 (11-bit DAC range).
CAP_WEIGHTS = [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
NUM_DECISION_BITS = len(CAP_WEIGHTS)
NUM_CAPTURE_BITS = NUM_DECISION_BITS + 1  # One extra final post-update comparator sample.
DATA_SIZE = daq["fastrx0"].get_size()
if DATA_SIZE != NUM_CAPTURE_BITS:
    raise RuntimeError(f"FastRX DATA_SIZE={DATA_SIZE}, expected {NUM_CAPTURE_BITS} from CAP_WEIGHTS")
DECIMATE_PHASE = 0  # Try 1 if the decoded transfer still looks phase-shifted/noisy.
MAX_RAW_FASTRX_WORDS = 2 * CONVERSIONS_PER_VIN  # Print all expected raw words; all words are still decoded.


def scpi_float(value) -> float:
    """Convert a SCPI response to float, accepting comma-separated readback strings."""
    return float(str(value).strip().split(",")[0])


def decode_conversion(spi0: int, spi1: int) -> tuple[str, int]:
    """Decode two FastRX words into a comparator trace and 12-bit-scale code.

    fast_spi_rx shifts samples left, so temporal order within each displayed word is
    left-to-right: bit DATA_SIZE-1 -> bit 0. CAP_WEIGHTS is also in temporal SAR
    decision order, so decimated sample i maps directly to CAP_WEIGHTS[i]. The extra
    final post-update compare is retained in the printed trace but not weighted into
    the code.
    """
    samples = [(spi0 >> i) & 1 for i in range(DATA_SIZE - 1, -1, -1)]
    samples += [(spi1 >> i) & 1 for i in range(DATA_SIZE - 1, -1, -1)]
    decimated = [samples[DECIMATE_PHASE + 2 * i] for i in range(NUM_CAPTURE_BITS)]

    # FIXME: The -1 weight index is suspicious, but removing it produced a split transfer curve.
    code_11bit = sum(CAP_WEIGHTS[i - 1] * decimated[i] for i in range(NUM_DECISION_BITS))
    decoded_bits = "".join(str(bit) for bit in decimated)
    return decoded_bits, 2 * code_11bit


# Sweep voltages and take measurements
voltages = [V_START + i * (V_STOP - V_START) / (N_SWEEP_POINTS - 1) for i in range(N_SWEEP_POINTS)]

plot_sample_voltages_mv = []
plot_sample_codes = []

# Keithley 2450 SCPI setup: source voltage, measure voltage/current as configured by commands.
daq["psu0"].source_volt()

print("\nStarting voltage sweep...")
for v in voltages:
    print(f"Setting PSU to {v * 1000:.0f} mV ({v:.3f} V)")
    daq["psu0"].set_voltage(v)
    daq["psu0"].on()
    sleep(SLEEP_TIME)
    actual = scpi_float(daq["psu0"].get_voltage())
    print(f"PSU readback: {actual * 1000:.0f} mV ({actual:.3f} V)")

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
        print("Waiting for sequencer!")

    # Reset sequencer state machine so outputs don't latch at last-step values
    # daq["seq0"].reset()
    data = daq["fifo0"].get_data()
    print(f"FIFO ({len(data)} words)")

    # # Show raw parsed words
    for i in range(min(MAX_RAW_FASTRX_WORDS, len(data))):
        identifier, frame_counter, spi_data = daq["fastrx0"].parse_word(int(data[i]))
        data_str = f"{spi_data:0{DATA_SIZE}b}"
        frame_str = f"{frame_counter:0{28 - DATA_SIZE}b}" if 28 - DATA_SIZE > 0 else ""
        if frame_str:
            print(f"  [{i}] ID={identifier:04b} frame={frame_str} data={data_str}")
        else:
            print(f"  [{i}] ID={identifier:04b} data={data_str}")

    # Decimate the two oversampled FastRX words into one comparator trace,
    # then apply the redundant capacitor weights to the weighted DAC decision bits.
    # CAP_WEIGHTS sum to 2047 per side; multiply by 2 for a nominal 12-bit-scale code.
    codes_12bit = []
    decoded_bits = []
    if len(data) % 2:
        print(f"Warning: odd FIFO word count ({len(data)}); ignoring last word for code decode")

    for pair_idx in range(len(data) // 2):
        _, frame0, spi0 = daq["fastrx0"].parse_word(int(data[2 * pair_idx]))
        _, frame1, spi1 = daq["fastrx0"].parse_word(int(data[2 * pair_idx + 1]))
        if frame0 != frame1:
            print(f"Warning: paired FIFO words have different frames: {frame0} != {frame1}")

        decoded_trace, code_12bit = decode_conversion(spi0, spi1)
        decoded_bits.append(decoded_trace)
        codes_12bit.append(code_12bit)

    print(f"Decoded {NUM_CAPTURE_BITS}b: {decoded_bits}")
    print(f"12-bit codes: {codes_12bit}")
    if codes_12bit:
        voltage_mv = v * 1000
        plot_sample_voltages_mv.extend([voltage_mv] * len(codes_12bit))
        plot_sample_codes.extend(codes_12bit)
    print(f"V={v * 1000:.1f}mV\n")

    # sleep based on Alex's gut feeling
    sleep(SLEEP_TIME)

daq["psu0"].off()
daq.close()

if plot_sample_codes:
    plot_path = Path(__file__).resolve().parents[2] / "build" / "basic_scan_transfer.png"
    plot_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(plot_sample_voltages_mv, plot_sample_codes, s=14, alpha=0.45, label="individual conversions")
    ax.set_title("FRIDA ADC basic voltage sweep")
    ax.set_xlabel("Input voltage (mV)")
    ax.set_ylabel("Effective output code (nominal 12-bit scale)")
    ax.set_xlim(V_START * 1000, V_STOP * 1000)
    ax.set_ylim(0, 4095)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"Saved transfer plot to {plot_path}")
else:
    print("No decoded codes collected; skipping transfer plot.")

print("Done.")
