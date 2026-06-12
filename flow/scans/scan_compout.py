"""Focused comparator-output capture scan for sequencer/FastRX alignment debug.

Run from /local/frida:
    uv run python -m flow.scans.scan_compout

This is a single-input hardware scan intended to make the comparator output bit
sequence easy to inspect.  It drives Vin_p to 700 mV while Vin_n is assumed to be
600 mV, then runs a custom 64-bit sequencer pattern:

- INIT pulse as in ``basic.py``.
- Initial LOGIC pulse as in ``basic.py``.
- SAMP high for four sequencer chunks.
- 10 comparator pulses with no SAR logic updates.
- One LOGIC pulse to apply the MSB DAC update.
- 7 more comparator pulses.

For the intended debug condition, the rough expected comparator sequence is ten
ones followed by seven zeros: ``11111111110000000``.
"""

from __future__ import annotations

from pathlib import Path
from time import sleep

from flow.scans.basic import CODE_WEIGHTS, NUM_CAPTURE_BITS, scpi_float, spi_config_to_bytes

ADC_INDEX = 0
VIN_P = 0.700
VIN_N = 0.600
SLEEP_TIME = 0.2
SEQ_SIZE = 64
CAPTURE_REPEATS = 1
EXPECTED_COMP_BITS = "1" * 10 + "0" * 7
MAX_PRINT_WORDS = 12

# Literal 64-bit sequencer tracks, grouped as two sequencer chunks per token.
# The sequencer is temporal left-to-right: bit 0, bit 1, ..., bit 63.
# Exactly 34 enabled samples: enough for two 17-bit FastRX words, with no
# extra SEN-fall partial-word flush.
# fmt: off
#                  0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
INIT_PATTERN    = "00 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
SAMP_PATTERN    = "00 00 11 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
COMP_PATTERN    = "00 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00 00 00 00 00 00 00 00 00 00"
LOGIC_PATTERN   = "00 01 00 00 00 00 00 00 00 00 00 00 00 00 10 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
RX_EN_PATTERN   = "00 00 00 00 01 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 10 00 00 00 00 00 00 00 00 00 00"
RX_TEST_PATTERN = "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
# fmt: on
COMP_BITS = tuple(range(9, 42, 2))


def pattern_high_bits(pattern: str) -> tuple[int, ...]:
    bits = pattern.replace(" ", "")
    if len(bits) != SEQ_SIZE:
        raise ValueError(f"expected {SEQ_SIZE} bits, got {len(bits)} from {pattern!r}")
    return tuple(index for index, bit in enumerate(bits) if bit == "1")


def bitarray_from_pattern(pattern: str):
    from bitarray import bitarray

    bits = pattern.replace(" ", "")
    if len(bits) != SEQ_SIZE:
        raise ValueError(f"expected {SEQ_SIZE} bits, got {len(bits)} from {pattern!r}")
    return bitarray(pattern)


def print_sequencer_summary() -> None:
    rx_en_bits = pattern_high_bits(RX_EN_PATTERN)
    print("Custom comp_out debug sequencer")
    print(f"  INIT    {INIT_PATTERN}  high={pattern_high_bits(INIT_PATTERN)}")
    print(f"  SAMP    {SAMP_PATTERN}  high={pattern_high_bits(SAMP_PATTERN)}")
    print(f"  COMP    {COMP_PATTERN}  high={pattern_high_bits(COMP_PATTERN)}")
    print(f"  LOGIC   {LOGIC_PATTERN}  high={pattern_high_bits(LOGIC_PATTERN)}")
    print(f"  RX_EN   {RX_EN_PATTERN}  high={rx_en_bits[0]}..{rx_en_bits[-1]} ({len(rx_en_bits)} chunks)")
    print(f"  RX_TEST {RX_TEST_PATTERN}  high=off")
    print(f"  comparator pulse bits: {COMP_BITS}")
    print(f"  rough expected Bbits: {EXPECTED_COMP_BITS}")


def configure_sequencer(daq) -> None:
    daq["seq0"].clear()
    daq["seq0"]["INIT"][0:SEQ_SIZE] = bitarray_from_pattern(INIT_PATTERN)
    daq["seq0"]["SAMP"][0:SEQ_SIZE] = bitarray_from_pattern(SAMP_PATTERN)
    daq["seq0"]["COMP"][0:SEQ_SIZE] = bitarray_from_pattern(COMP_PATTERN)
    daq["seq0"]["LOGIC"][0:SEQ_SIZE] = bitarray_from_pattern(LOGIC_PATTERN)
    daq["seq0"]["RX_EN"][0:SEQ_SIZE] = bitarray_from_pattern(RX_EN_PATTERN)
    daq["seq0"]["RX_TEST"][0:SEQ_SIZE] = bitarray_from_pattern(RX_TEST_PATTERN)

    daq["seq0"].write(SEQ_SIZE)
    daq["seq0"].set_size(SEQ_SIZE)
    daq["seq0"].set_clk_divide(1)
    daq["seq0"].set_repeat(CAPTURE_REPEATS)
    daq["seq0"].set_en_ext_start(False)


def configure_adc_spi(daq, adc_index: int) -> None:
    from bitarray import bitarray

    spi_config = {
        "dac_astate_p": "1111111111111111",
        "dac_bstate_p": "1111111111111111",
        "dac_astate_n": "1111111111111111",
        "dac_bstate_n": "1111111111111111",
        "en_init": 1,
        "en_samp_p": 1,
        "en_samp_n": 1,
        "en_comp": 1,
        "en_update": 1,
        "dac_mode": 1,
        "dac_diffcaps": 1,
        "mux_sel": adc_index,
    }

    spi_bytes = spi_config_to_bytes(spi_config)
    for _ in range(2):
        daq["spi0"].set_data(list(spi_bytes))
        daq["spi0"].set_size(180)
        daq["spi0"].start()
        daq["spi0"].wait_for_ready()

    raw = bytes(daq["spi0"].get_data(size=23))
    readback = bitarray()
    readback.frombytes(raw)
    readback = readback[:180]
    expected = bitarray()
    expected.frombytes(spi_bytes)
    expected = expected[:180]
    print(f"ADC {adc_index:02d} SPI verify: {((expected[1:] ^ readback[1:]).count(1))} mismatches (skip bit 0)")


def decode_words_with_phase(spi0: int, spi1: int, data_size: int, phase: int) -> tuple[str, int]:
    samples = [(spi0 >> i) & 1 for i in range(data_size - 1, -1, -1)]
    samples += [(spi1 >> i) & 1 for i in range(data_size - 1, -1, -1)]
    bits = [samples[phase + 2 * i] for i in range(NUM_CAPTURE_BITS)]
    bbits = "".join(str(bit) for bit in bits)
    dout = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, bits, strict=True))
    return bbits, dout


def parsed_samples(daq, data: list[int], data_size: int) -> list[int]:
    samples: list[int] = []
    for word in data:
        _, _, spi_data = daq["fastrx0"].parse_word(int(word))
        samples.extend((spi_data >> i) & 1 for i in range(data_size - 1, -1, -1))
    return samples


def print_decoded_data(daq, data, data_size: int, *, label: str, full_sequence_aligned: bool) -> None:
    print(f"{label}: FIFO words: {len(data)}")
    for i, word in enumerate(data[:MAX_PRINT_WORDS]):
        identifier, frame_counter, spi_data = daq["fastrx0"].parse_word(int(word))
        data_str = f"{spi_data:0{data_size}b}"
        frame_str = f"{frame_counter:0{28 - data_size}b}" if 28 - data_size > 0 else ""
        if frame_str:
            print(f"[{i}] ID={identifier:04b} frame={frame_str} data={data_str}")
        else:
            print(f"[{i}] ID={identifier:04b} data={data_str}")
    if len(data) > MAX_PRINT_WORDS:
        print(f"... skipped {len(data) - MAX_PRINT_WORDS} additional FIFO words")

    if len(data) >= 2:
        raw_word0 = int(data[0])
        raw_word1 = int(data[1])
        _, _, spi0 = daq["fastrx0"].parse_word(raw_word0)
        _, _, spi1 = daq["fastrx0"].parse_word(raw_word1)
        for phase in (0, 1):
            bbits, dout = decode_words_with_phase(spi0, spi1, data_size, phase)
            marker = " <- expected" if bbits == EXPECTED_COMP_BITS else ""
            print(f"first two words decoded with phase {phase}: Bbits={bbits} Dout={dout}{marker}")

    if full_sequence_aligned:
        samples = parsed_samples(daq, data, data_size)
        if len(samples) > max(COMP_BITS):
            comp_bits = "".join(str(samples[index]) for index in COMP_BITS)
            print(f"samples at COMP_BITS {COMP_BITS}: {comp_bits} expected≈{EXPECTED_COMP_BITS}")
        else:
            print(
                f"not enough full-sequence samples to extract COMP_BITS: got {len(samples)}, need {max(COMP_BITS) + 1}"
            )


def capture_with_seqout_rx_en(daq, data_size: int) -> list[int]:
    daq["fifo0"]["RESET"]
    daq["fifo0"].get_data()

    daq["seq0"].start()
    sleep(0.01)
    while not daq["seq0"].is_done():
        sleep(0.1)
        print("waiting for sequencer")

    return list(daq["fifo0"].get_data())


def capture_with_gpio_window(daq, data_size: int) -> list[int]:
    print("Retrying with GPIO external-start / full-sequence FastRX enable window")
    daq["fifo0"]["RESET"]
    daq["fifo0"].get_data()
    daq["fastrx0"].reset()
    daq["fastrx0"].set_en(True)

    daq["seq0"].set_en_ext_start(True)
    daq["gpio0"]["RX_EN_MUX"] = 0
    daq["gpio0"].write()

    daq["gpio0"]["SEQ_START"] = 1
    daq["gpio0"].write()
    sleep(0.0001)
    daq["gpio0"]["SEQ_START"] = 0
    daq["gpio0"].write()

    while not daq["seq0"].is_done():
        sleep(0.1)
        print("waiting for sequencer")

    return list(daq["fifo0"].get_data())


def capture_once(daq, data_size: int) -> None:
    daq["gpio0"]["RX_EN_MUX"] = 1
    daq["gpio0"].write()
    daq["seq0"].set_en_ext_start(False)

    data = capture_with_seqout_rx_en(daq, data_size)
    print_decoded_data(daq, data, data_size, label="seqout RX_EN capture", full_sequence_aligned=False)
    if data:
        return

    data = capture_with_gpio_window(daq, data_size)
    print_decoded_data(daq, data, data_size, label="GPIO-window capture", full_sequence_aligned=False)


def main() -> None:
    from basil.dut import Dut

    print_sequencer_summary()

    daq = Dut(str(Path(__file__).resolve().parent / "map_fpga.yaml"))
    daq.init()
    try:
        daq["gpio0"]["RST_B"] = 0
        daq["gpio0"].write()
        daq["gpio0"]["RST_B"] = 1
        daq["gpio0"].write()

        configure_sequencer(daq)

        daq["gpio0"]["RX_LOOPBACK"] = 0
        daq["gpio0"].write()
        daq["fastrx0"].reset()
        daq["fastrx0"].set_en(True)
        daq["gpio0"]["RX_EN_MUX"] = 1
        daq["gpio0"].write()

        data_size = daq["fastrx0"].get_size()
        if data_size != NUM_CAPTURE_BITS:
            raise RuntimeError(f"FastRX DATA_SIZE={data_size}, expected {NUM_CAPTURE_BITS}")

        configure_adc_spi(daq, ADC_INDEX)

        daq["psu0"].source_volt()
        daq["psu0"].set_voltage(VIN_P)
        daq["psu0"].on()
        sleep(SLEEP_TIME)
        vin_read = scpi_float(daq["psu0"].get_voltage())
        print(f"Vin_p set/read: {VIN_P:.6g} V / {vin_read:.6g} V; Vin_n assumed {VIN_N:.6g} V")

        capture_once(daq, data_size)
    finally:
        try:
            daq["psu0"].off()
        finally:
            daq.close()

    print("Done.")


if __name__ == "__main__":
    main()
