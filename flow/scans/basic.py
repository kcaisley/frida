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


# ADC_1 offset=71, 7 bits: en_init(0) en_samp_p(1) en_samp_n(2) en_comp(3) en_update(4) dac_mode(5) dac_diffcaps(6)
# - dac_mode=1 means SAR mode (DAC driven by comparator output, standard operation)
# - dac_mode=0 means calibration mode (DAC toggles between astate/bstate)
# - dac_diffcaps=1 enables differential capacitor mode (needed for unit-length caps)
# - Only ADC_1 (bits 71..77) is enabled; ADC_0 (bits 64..70) and ADCs 2-15
#   (bits 78..176) default to 0 from bits.setall(0), so their enables stay off.
bits[71:78] = bitarray("1111111")
bits[176] = 1  # MUX_SEL=0001, so we select ADC 1

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
#                                       0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19
daq["seq0"]["INIT"][0:40] =    bitarray("11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["SAMP"][0:40] =    bitarray("00 11 11 10 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
daq["seq0"]["COMP"][0:40] =    bitarray("00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01")
daq["seq0"]["LOGIC"][0:40] =   bitarray("00 00 00 00 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10")
daq["seq0"]["RX_EN"][0:40] =   bitarray("00 00 11 11 11 11 11 11 11 11 11 11 00 00 00 00 00 00 00 00")
daq["seq0"]["RX_TEST"][0:40] = bitarray("00 00 11 01 01 01 01 01 01 01 10 11 00 00 00 00 00 00 00 00")
# daq["seq0"]["RX_CLK"][0:40] =  bitarray("00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00")
                                  #      init      | ||                                           ||
                                  #         samp   | ||                                           ||
                                  #                comp0                                          ||
                                  #                  logic1                                       logic16
                                  #                   comp1                                        comp16
# fmt: on

# Write the loaded sequence pattern to the sequencer hardware memory.
# - write() on TrackRegister serializes the bitarrays and sends them to seq_gen.
# - The argument '40' specifies the number of steps to write.
daq["seq0"].write(40)  # TrackRegister.write: basil/basil/RL/TrackRegister.py#L39

# Configure sequencer operational parameters.
# These methods are proxied from the seq_gen hardware driver (basil/HL/seq_gen.py)
# via the TrackRegister object.
daq["seq0"].set_size(40)  # seq_gen.set_size: basil/HL/seq_gen.py#L59
daq["seq0"].set_clk_divide(1)  # seq_gen.set_clk_divide: basil/HL/seq_gen.py#L68
daq["seq0"].set_repeat(4)  # seq_gen.set_repeat: basil/HL/seq_gen.py#L77
daq["seq0"].set_en_ext_start(True)  # seq_gen.set_en_ext_start: basil/HL/seq_gen.py#L103

# Trigger and capture
# Arm FastRX receiver
# - FASTRX is a fast_spi_rx RegisterHardwareLayer (basil/HL/fast_spi_rx.py)
# - reset() clears internal state, set_en(True) enables capture on next clock edge

# Enable loopback mode to use sequencer test data instead of COMP_OUT
daq["gpio0"]["RX_LOOPBACK"] = 1  # Enable fast_spi_rx loopback
daq["fastrx0"].reset()
daq["fastrx0"].set_en(True)

# Enable loopback mode to use sequencer test data instead of COMP_OUT

# I belive one of these should flush stale TCP FIFO data from previous runs
# - fifo is a sitcp_fifo HardwareLayer (basil/HL/sitcp_fifo.py)
# - RESET clears the SiTCP buffer, get_data() drains any remaining
daq["fifo0"]["RESET"]
daq["fifo0"].get_data()

# Route fastrx_en from GPIO[6] (SEQ_START pulse) instead of seq_out[5]
# - GPIO is a StdRegister register (basil/RL/StdRegister.py), proxied to gpio driver (basil/HL/gpio.py)
# - RX_EN_MUX=0 means fastrx_en follows GPIO[6]
# - write() pushes the full GPIO byte to the FPGA
daq["gpio0"]["RX_EN_MUX"] = 1
daq["gpio0"].write()

# Drive GPIO[6] high then low to generate a rising edge trigger pulse
# RX_EN_MUX=0 means fastrx_en follows GPIO[6], so keep it high until sequencer finishes
daq["gpio0"]["SEQ_START"] = 1
daq["gpio0"].write()

# Wait for sequencer to complete by polling is_done()
sleep(0.5)


# Now safe to release SEQ_START without cutting off fastrx_en mid-capture
daq["gpio0"]["SEQ_START"] = 0
daq["gpio0"].write()

while not daq["seq0"].is_done():  # is_done will not actually return 1, unless SEQ_START is ended.
    sleep(0.01)

# Reset sequencer state machine so outputs don't latch at last-step values
daq["seq0"].reset()
data = daq["fifo0"].get_data()
print("FIFO words: %d" % len(data))

data_size = daq["fastrx0"].get_size()

for i in range(min(16, len(data))):
    identifier, frame_counter, spi_data = daq["fastrx0"].parse_word(int(data[i]))
    data_str = f"{spi_data:0{data_size}b}"
    frame_str = f"{frame_counter:0{28 - data_size}b}" if 28 - data_size > 0 else ""
    if frame_str:
        print(f"  [{i}] ID={identifier:04b} frame={frame_str} data={data_str}")
    else:
        print(f"  [{i}] ID={identifier:04b} data={data_str}")

daq.close()
