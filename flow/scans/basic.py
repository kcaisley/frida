import time
from pathlib import Path

from basil.dut import Dut
from bitarray import bitarray

daq = Dut(str(Path(__file__).resolve().parent / "map_fpga.yaml"))
daq.init()

# Release reset
daq["GPIO"]["RST_B"] = 0
daq["GPIO"].write()
daq["GPIO"]["RST_B"] = 1
daq["GPIO"].write()

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


# ADC_1 offset=71, 7 bits: en_init(0) en_samp_p(1) en_samp_n(2) en_comp(3) en_update(4) dac_mode(5) dac_diffcaps(6)
# - dac_mode=1 means SAR mode (DAC driven by comparator output, standard operation)
# - dac_mode=0 means calibration mode (DAC toggles between astate/bstate)
# - dac_diffcaps=1 enables differential capacitor mode (needed for unit-length caps)
# - Only ADC_1 (bits 71..77) is enabled; ADC_0 (bits 64..70) and ADCs 2-15
#   (bits 78..176) default to 0 from bits.setall(0), so their enables stay off.
bits[71:78] = bitarray("1111111")
bits[176] = 1  # MUX_SEL=1, so we select ADC 1

spi_bytes = bits.tobytes()
daq["spi"].set_data(list(spi_bytes))
daq["spi"].set_size(180)
daq["spi"].start()
daq["spi"].wait_for_ready()

daq["spi"].set_data(list(spi_bytes))
daq["spi"].set_size(180)
daq["spi"].start()
daq["spi"].wait_for_ready()
raw = bytes(daq["spi"].get_data(size=23))
rb = bitarray()
rb.frombytes(raw)
rb = rb[:180]
print(f"SPI verify: {((bits[1:] ^ rb[1:]).count(1))} mismatches (skip bit 0)")

# Load adc sequencer pattern (40 steps)
daq["SEQ"].clear()
# Note: python slices are "half open": start number is inclusive, but end number is not
# Note: Sequencer is temporally shift left to right
# fmt: off
#                                      0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19
daq["SEQ"]["INIT"][0:40] =   bitarray("11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["SEQ"]["SAMP"][0:40] =   bitarray("00 11 11 10 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["SEQ"]["COMP"][0:40] =   bitarray("00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01")
daq["SEQ"]["LOGIC"][0:40] =  bitarray("00 00 00 00 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10")
daq["SEQ"]["RX_CLK"][0:40] = bitarray("00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00")
daq["SEQ"]["RX_EN"][0:40] =  bitarray("00 00 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11")
                                #      init      | ||                                           ||
                                #         samp   | ||                                           ||
                                #                comp0                                          ||
                                #                  logic1                                       logic16
                                #                   comp1                                        comp16
# fmt: on

# Write the loaded sequence pattern to the sequencer hardware memory.
# - write() on TrackRegister serializes the bitarrays and sends them to seq_gen.
# - The argument '40' specifies the number of steps to write.
daq["SEQ"].write(40)  # TrackRegister.write: basil/basil/RL/TrackRegister.py#L39

# Configure sequencer operational parameters.
# These methods are proxied from the seq_gen hardware driver (basil/HL/seq_gen.py)
# via the TrackRegister object.
daq["SEQ"].set_size(40)  # seq_gen.set_size: basil/HL/seq_gen.py#L59
daq["SEQ"].set_clk_divide(1)  # seq_gen.set_clk_divide: basil/HL/seq_gen.py#L68
daq["SEQ"].set_repeat(1)  # seq_gen.set_repeat: basil/HL/seq_gen.py#L77
daq["SEQ"].set_en_ext_start(True)  # seq_gen.set_en_ext_start: basil/HL/seq_gen.py#L103

# Trigger and capture
# Arm FastRX receiver
# - FASTRX is a fast_spi_rx RegisterHardwareLayer (basil/HL/fast_spi_rx.py)
# - reset() clears internal state, set_en(True) enables capture on next clock edge
daq["FASTRX"].reset()
daq["FASTRX"].set_en(True)

# I belive one of these should flush stale TCP FIFO data from previous runs
# - fifo is a sitcp_fifo HardwareLayer (basil/HL/sitcp_fifo.py)
# - RESET clears the SiTCP buffer, get_data() drains any remaining
daq["fifo"]["RESET"]
daq["fifo"].get_data()

# Route fastrx_en from GPIO[6] (SEQ_START pulse) instead of seq_out[5]
# - GPIO is a StdRegister register (basil/RL/StdRegister.py), proxied to gpio driver (basil/HL/gpio.py)
# - RX_EN_MUX=0 means fastrx_en follows GPIO[6]
# - write() pushes the full GPIO byte to the FPGA
daq["GPIO"]["RX_EN_MUX"] = 0
daq["GPIO"].write()

# Drive GPIO[6] high then low to generate a rising edge trigger pulse
# RX_EN_MUX=0 means fastrx_en follows GPIO[6], so keep it high until sequencer finishes
daq["GPIO"]["SEQ_START"] = 1
daq["GPIO"].write()

# Wait for sequencer to complete (READY goes low during run, high when done)
# - seq_gen.wait_for_ready polls the READY register (basil/HL/seq_gen.py#L91)
daq["SEQ"].wait_for_ready()

# Now safe to release SEQ_START without cutting off fastrx_en mid-capture
daq["GPIO"]["SEQ_START"] = 0
daq["GPIO"].write()

# Reset sequencer state machine so outputs don't latch at last-step values
daq["SEQ"].reset()
data = daq["fifo"].get_data()
print("FIFO words: %d" % len(data))
for i in range(min(16, len(data))):
    w = int(data[i])
    print(f"  [{i}] ID={(w >> 28) & 0xF:04b} frame={(w >> 16) & 0xFFF:012b} data={w & 0xFFFF:016b}")

daq.close()
