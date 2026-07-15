"""Focused comparator-output capture scan for sequencer/FastRX alignment debug.

Run from /local/frida:
    uv run python -m flow.scans.scan_compout

This is a single-input hardware scan intended to make the comparator output bit
sequence easy to inspect. Set the external inputs to Vin_p=700 mV and
Vin_n=600 mV before running the custom 32-word serializer pattern:

- INIT and SAMP pulses match ``basic.py``.
- The first 10 comparator pulses have no SAR logic updates.
- One LOGIC pulse applies the MSB DAC update.
- The final 7 comparator pulses complete the 17-bit conversion.
- RX_SEN stays high for exactly 17 cycles of the 200 MHz FastRX clock, producing
  one FastRX word with no oversampling or phase decimation.

For the intended debug condition, the rough expected comparator sequence is ten
ones followed by seven zeros: ``11111111110000000``.
"""

from __future__ import annotations

from pathlib import Path
from time import sleep

from flow.scans.basic import (
    ADC_CODE_WEIGHTS,
    NUM_CAPTURE_BITS,
    SEQ_GEN_LANES,
    SERDES_RATIO,
    bitarray_to_seq_gen_format,
    decode_conversion,
    spi_config_to_bytes,
)

ADC_INDEX = 0
CODE_WEIGHTS = ADC_CODE_WEIGHTS[ADC_INDEX]
VIN_P = 0.700
VIN_N = 0.600
SEQ_WORDS = 32
CAPTURE_REPEATS = 1
EXPECTED_COMP_BITS = "1" * 10 + "0" * 7
MAX_PRINT_WORDS = 12

# Each eight-bit output word is temporal left-to-right and becomes eight
# 0.625 ns intervals at the OSERDES output. RX_SEN/RX_TEST remain one bit per
# 5 ns sequencer word because they are internal FPGA controls.
# fmt: off
SEQ_PATTERNS = {
    "INIT":    "00000000 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "SAMP":    "00000000 00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "COMP":    "00000000 00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "LOGIC":   "00000000 00001111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "RX_SEN":  "0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 0 0 0",
    "RX_TEST": "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0",
}
# fmt: on


def active_words(pattern: str) -> tuple[int, ...]:
    words = pattern.split()
    if len(words) != SEQ_WORDS:
        raise ValueError(f"expected {SEQ_WORDS} words, got {len(words)} from {pattern!r}")
    return tuple(index for index, word in enumerate(words) if "1" in word)


def print_sequencer_summary() -> None:
    print("Custom comp_out serializer/FastRX debug sequencer")
    for name, pattern in SEQ_PATTERNS.items():
        print(f"  {name:<7} active words={active_words(pattern)}")
    print(f"  rough expected Bbits: {EXPECTED_COMP_BITS}")


def configure_sequencer(daq) -> None:
    memory = bitarray_to_seq_gen_format(SEQ_PATTERNS, SERDES_RATIO, SEQ_GEN_LANES)

    # Bypass TrackRegister: its byte/bit reversal only matches the original
    # 8-bit sequencer, not the current 64-bit serializer memory layout.
    daq["seq0"]._drv.set_data(memory)
    daq["seq0"].set_size(SEQ_WORDS)
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


def print_decoded_data(daq, data, data_size: int) -> None:
    print(f"RX_SEN capture: FIFO words: {len(data)}")
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

    if data:
        _, _, spi_data = daq["fastrx0"].parse_word(int(data[0]))
        bbits, dout = decode_conversion(spi_data, data_size, CODE_WEIGHTS)
        marker = " <- expected" if bbits == EXPECTED_COMP_BITS else ""
        print(f"first word decoded: Bbits={bbits} Dout={dout}{marker}")


def capture_once(daq, data_size: int) -> None:
    daq["gpio0"]["RX_EN_MUX"] = 1
    daq["gpio0"].write()
    daq["seq0"].set_en_ext_start(False)

    daq["fifo0"]["RESET"]
    daq["fifo0"].get_data()
    daq["seq0"].start()
    sleep(0.01)
    while not daq["seq0"].is_done():
        sleep(0.1)
        print("waiting for sequencer")

    print_decoded_data(daq, list(daq["fifo0"].get_data()), data_size)


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

        print(f"Using externally supplied Vin_p={VIN_P:.6g} V and Vin_n={VIN_N:.6g} V")

        capture_once(daq, data_size)
    finally:
        daq.close()

    print("Done.")


if __name__ == "__main__":
    main()
