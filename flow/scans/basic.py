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

for _ in range(16):
    bits[0 + _] = (0x7FFF >> _) & 1
    bits[16 + _] = (0x7FFF >> _) & 1
    bits[32 + _] = (0x7FFF >> _) & 1
    bits[48 + _] = (0x7FFF >> _) & 1

bits[176] = 1  # MUX_SEL=1

# ADC_1 offset=71, 7 bits: en_init(0) en_samp_p(1) en_samp_n(2) en_comp(3) en_update(4) dac_mode(5) dac_diffcaps(6)
bits[71] = 1
bits[72] = 1
bits[73] = 1
bits[74] = 1
bits[75] = 1

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
print("SPI verify: %d mismatches (skip bit 0)" % ((bits[1:] ^ rb[1:]).count(1)))

# Load adc sequencer pattern (40 steps)
daq["SEQ"].clear()
daq["SEQ"]["INIT"][0:40] = bitarray("1100000000000000000000000000000000000000")
daq["SEQ"]["SAMP"][0:40] = bitarray("0011111000000000000000000000000000000000")
daq["SEQ"]["COMP"][0:40] = bitarray("0000000101010101010101010101010101010000")
daq["SEQ"]["LOGIC"][0:40] = bitarray("0000000010101010101010101010101010101000")
daq["SEQ"]["RX_CLK"][0:40] = bitarray("0000000001010101010101010101010101010101")
daq["SEQ"]["RX_EN"][0:40] = bitarray("0000000111111111111111111111111111111111")
daq["SEQ"].write(40)
daq["seq_gen"].set_size(40)
daq["seq_gen"].set_clk_divide(1)

# Trigger and capture
daq["fast_spi_rx"].reset()
daq["fast_spi_rx"].set_en(True)
daq["fifo"].get_data()

daq["GPIO"]["RX_EN_MUX"] = 1
daq["GPIO"].write()
daq["seq_gen"].set_repeat(1)
daq["seq_gen"].set_en_ext_start(True)

daq["GPIO"]["SEQ_START"] = 1
daq["GPIO"].write()
time.sleep(0.0001)
daq["GPIO"]["SEQ_START"] = 0
daq["GPIO"].write()
daq["seq_gen"].reset()

# Read FIFO
time.sleep(0.01)
data = daq["fifo"].get_data()
print("FIFO words: %d" % len(data))
for i in range(min(16, len(data))):
    w = int(data[i])
    print("  [%d] ID=%04b frame=%012b data=%016b" % (i, (w >> 28) & 0xF, (w >> 16) & 0xFFF, w & 0xFFFF))

daq["intf"].close()
