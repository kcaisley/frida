"""FRIDA ADC basic scan and readout script."""

from pathlib import Path
from time import sleep

from basil.dut import Dut
from bitarray import bitarray

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
bits[0:16] = bitarray("1111111111111110")  # DAC_ASTATE_P
bits[16:32] = bitarray("1111111111111110")  # DAC_BSTATE_P
bits[32:48] = bitarray("1111111111111110")  # DAC_ASTATE_N
bits[48:64] = bitarray("1111111111111110")  # DAC_BSTATE_N


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
bits[176] = 0  # MUX_SEL=0001, so we select ADC 1

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
# daq["seq0"]["INIT"][0:64] =   bitarray("00 00 00 00 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["SAMP"][0:64] =    bitarray("00 00 11 11 10 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["COMP"][0:64] =    bitarray("00 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["LOGIC"][0:64] =   bitarray("00 00 00 00 00 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 00 00 00 00 00 00 00 00 00 00 00")
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
daq["seq0"].set_repeat(4)  # seq_gen.set_repeat: basil/HL/seq_gen.py#L77
daq["seq0"].set_en_ext_start(True)  # seq_gen.set_en_ext_start: basil/HL/seq_gen.py#L103

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

# Capacitor array weights from caparray.sp (bit 0 = LSB = smallest cap)
# These sum to 2047 = 2^11 - 1 (11-bit DAC range)
CAP_WEIGHTS = [1, 1, 2, 4, 4, 5, 10, 12, 24, 32, 64, 96, 192, 320, 512, 768]
DATA_SIZE = daq["fastrx0"].get_size()  # 17
SPI_MASK = (1 << DATA_SIZE) - 1  # 0x1FFFF

# Sweep voltages and take measurements
voltages = [v / 1000.0 for v in range(100, 1101, 100)]  # 100mV to 1000mV in 100mV steps
print("\nStarting voltage sweep...")
for v in voltages:
    print(f"Setting PSU to {v * 1000:.0f} mV ({v:.3f} V)")
    daq["psu0"].set_voltage(v)
    daq["psu0"].enable_output()
    sleep(0.2)
    actual = daq["psu0"].get_voltage()
    print(f"PSU readback: {actual * 1000:.0f} mV ({actual:.3f} V)")

    # Drive GPIO[6] high then low to generate a rising edge trigger pulse
    # RX_EN_MUX=0 means fastrx_en follows GPIO[6], so keep it high until sequencer finishes
    daq["gpio0"]["SEQ_START"] = 1
    daq["gpio0"].write()

    # Wait for sequencer to run through sequence
    sleep(0.5)

    # Now safe to release SEQ_START without cutting off fastrx_en mid-capture
    daq["gpio0"]["SEQ_START"] = 0
    daq["gpio0"].write()

    while not daq["seq0"].is_done():  # is_done will not actually return 1, unless SEQ_START is ended.
        sleep(0.5)
        print("Waiting for sequencer!")

    # Reset sequencer state machine so outputs don't latch at last-step values
    # daq["seq0"].reset()
    data = daq["fifo0"].get_data()
    print(f"FIFO ({len(data)} words)")

    # # Show raw parsed words
    for i in range(min(16, len(data))):
        identifier, frame_counter, spi_data = daq["fastrx0"].parse_word(int(data[i]))
        data_str = f"{spi_data:0{DATA_SIZE}b}"
        frame_str = f"{frame_counter:0{28 - DATA_SIZE}b}" if 28 - DATA_SIZE > 0 else ""
        if frame_str:
            print(f"  [{i}] ID={identifier:04b} frame={frame_str} data={data_str}")
        else:
            print(f"  [{i}] ID={identifier:04b} data={data_str}")

    # # Decimate 34 raw bits -> 17 bits (keep even samples), apply capacitor weights
    # raw_codes = []
    # for pair_idx in range(len(data) // 2):
    #     print(f"working on raw codes{pair_idx}")
    #     w0 = int(data[2 * pair_idx]) & SPI_MASK
    #     w1 = int(data[2 * pair_idx + 1]) & SPI_MASK

    #     combined = w0 | (w1 << DATA_SIZE)
    #     result_17 = 0
    #     for i in range(DATA_SIZE):
    #         result_17 |= ((combined >> (2 * i)) & 1) << i

    #     code = sum(CAP_WEIGHTS[i] * ((result_17 >> i) & 1) for i in range(16))
    #     raw_codes.append(code)

    # avg = sum(raw_codes) / len(raw_codes) if raw_codes else 0
    # print(f"Raw codes: {raw_codes}")
    # print(f"V={v * 1000:.0f}mV  mean_code={avg:.1f}\n")

    daq["psu0"].disable_output()

    # sleep based on Alex's gut feeling
    sleep(0.5)

print("Done.")
daq.close()
