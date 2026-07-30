"""Opt-in hardware pytest for exact 17-bit FastRX capture alignment.

The test routes a recognizable sequencer pattern through the FPGA-internal
FastRX loopback. It therefore checks the sequencer-to-SEN timing, temporal bit
order, FastRX framing, and FIFO transport without depending on ADC behavior or
the analog COMP_OUT timing.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_fastrx.py
"""

import dataclasses
from pathlib import Path
from time import monotonic, sleep

import pytest
from yaml import safe_load

from flow.scans.params import AdcTbParams, load_board_map
from flow.scans.scan_adc import (
    calculate_fastrx_capture_alignment,
    convert_params_to_seqgen_fmt,
)

MAP_PATH = Path(__file__).resolve().parent / "map_fpga.yaml"
EXPECTED_BITS = "10110100101100101"
TEST_REPEATS = 64
CAPTURE_TIMEOUT_S = 2.0
pytestmark = pytest.mark.hw


def test_fastrx_captures_exact_internal_17_bit_pattern() -> None:
    """Hardware: capture every test bit in order with contiguous frame IDs."""

    params = AdcTbParams()
    timing_model = load_board_map()["boards"]["00"]["capture_timing_model"]
    capture_start_words = sorted(
        {
            calculate_fastrx_capture_alignment(
                dataclasses.replace(params, symbol_rate=rate_mbd * 1.0e6),
                **timing_model,
            ).rx_sen_start_word
            for rate_mbd in range(80, 1601, 80)
        }
    )
    memory = convert_params_to_seqgen_fmt(
        params,
        rx_sen_start_word=capture_start_words[0],
    )
    sequence_words = len(params.seq_init_pattern) // 8

    # Initialize only the hardware blocks participating in this loopback.
    config = safe_load(MAP_PATH.read_text())
    driver_names = {"fifo0", "seq0", "gpio0", "fastrx0"}
    register_names = {"seq0", "gpio0"}
    config["hw_drivers"] = [driver for driver in config["hw_drivers"] if driver["name"] in driver_names]
    config["registers"] = [register for register in config["registers"] if register["name"] in register_names]

    from basil.dut import Dut

    daq = Dut(config)
    seq = gpio = None
    original_seq = original_gpio = None
    try:
        daq.init()
        seq = daq["seq0"]
        gpio = daq["gpio0"]
        gpio_fields = (
            "RST_B",
            "AMP_EN",
            "RX_LOOPBACK",
            "SPI_LOOPBACK",
            "DBG_FIFO",
            "RX_TIEHIGH",
            "SEQ_START",
            "RX_EN_MUX",
        )
        gpio.read()
        original_gpio = {field: gpio[field].tovalue() for field in gpio_fields}
        original_seq = {
            "memory": bytes(seq.get_data(size=len(memory))),
            "size": int(seq.get_size()),
            "clk_divide": int(seq.get_clk_divide()),
            "repeat": int(seq.get_repeat()),
            "en_ext_start": int(seq.get_en_ext_start()),
        }

        gpio["RX_LOOPBACK"] = 1
        gpio["DBG_FIFO"] = 0
        gpio["RX_TIEHIGH"] = 0
        gpio["SEQ_START"] = 0
        gpio["RX_EN_MUX"] = 1
        gpio.write()

        for capture_start_word in capture_start_words:
            memory = convert_params_to_seqgen_fmt(params, rx_sen_start_word=capture_start_word)
            # Byte lane four carries RX_SEN in bit zero and RX_TEST in bit one.
            for bit_index, bit in enumerate(EXPECTED_BITS):
                if bit == "1":
                    memory[(capture_start_word + bit_index) * 8 + 4] |= 1 << 1

            seq.reset()
            daq["fastrx0"].reset()
            sleep(0.001)
            seq.set_data(memory)
            seq.set_size(sequence_words)
            seq.set_clk_divide(1)
            seq.set_repeat(TEST_REPEATS)
            seq.set_en_ext_start(False)
            daq["fastrx0"].set_en(True)
            assert int(daq["fastrx0"].get_size()) == len(EXPECTED_BITS)

            daq["fifo0"]["RESET"]
            daq["fifo0"].get_data()
            seq.start()
            deadline = monotonic() + CAPTURE_TIMEOUT_S
            while not seq.is_done():
                if monotonic() >= deadline:
                    raise TimeoutError("sequencer did not finish the FastRX loopback")
                sleep(0.001)

            expected_fifo_bytes = 4 * TEST_REPEATS
            while int(daq["fifo0"]["FIFO_SIZE"]) < expected_fifo_bytes:
                if monotonic() >= deadline:
                    raise TimeoutError("FastRX did not deliver every loopback frame")
                sleep(0.001)
            sleep(0.01)

            words = list(daq["fifo0"].get_data())
            assert len(words) == TEST_REPEATS
            expected_data = int(EXPECTED_BITS, 2)
            for frame_index, word in enumerate(words):
                identifier, frame, data = daq["fastrx0"].parse_word(int(word))
                assert identifier == 1
                assert frame == frame_index
                assert data == expected_data, (
                    f"start word {capture_start_word}, frame {frame_index}: "
                    f"captured {data:017b}, expected {EXPECTED_BITS}"
                )
            assert int(daq["fastrx0"].get_lost_count()) == 0
    finally:
        try:
            if seq is not None and original_seq is not None:
                seq.reset()
                seq.set_data(original_seq["memory"])
                seq.set_size(original_seq["size"])
                seq.set_clk_divide(original_seq["clk_divide"])
                seq.set_repeat(original_seq["repeat"])
                seq.set_en_ext_start(original_seq["en_ext_start"])
            if gpio is not None and original_gpio is not None:
                for field, value in original_gpio.items():
                    gpio[field] = value
                gpio.write()
            if "daq" in locals():
                daq["fastrx0"].reset()
                daq["fifo0"]["RESET"]
                daq["fifo0"].get_data()
        finally:
            daq.close()
