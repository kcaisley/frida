"""Opt-in hardware pytest for Basil seq_gen memory and register readback.

This test writes the same 64-bit sequencer image and control settings used by
the scan scripts, reads them back through Basil, and restores the prior state.
It does not start the sequencer or exercise the physical serializer outputs.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_seqgen.py
"""

from pathlib import Path

import pytest
from yaml import safe_load

from flow.scans.scan_adc import (
    SEQ_GEN_LANES,
    SEQ_PATTERNS,
    SERDES_RATIO,
    convert_dict_to_seqgen_fmt,
)

MAP_PATH = Path(__file__).resolve().parent / "map_fpga.yaml"
TEST_CLK_DIVIDE = 1
TEST_REPEAT = 3
pytestmark = pytest.mark.hw


def test_seq_gen_memory_and_register_readback() -> None:
    """Hardware: write and read back seq_gen memory and control registers."""
    memory = convert_dict_to_seqgen_fmt(
        SEQ_PATTERNS,
        SERDES_RATIO,
        SEQ_GEN_LANES,
    )
    sequence_words = len(SEQ_PATTERNS["INIT"].split())

    # Limit this test to the sequencer so unrelated FPGA blocks cannot prevent
    # its initialization or be modified as a side effect.
    config = safe_load(MAP_PATH.read_text())
    config["hw_drivers"] = [driver for driver in config["hw_drivers"] if driver["name"] == "seq0"]
    config["registers"] = [register for register in config["registers"] if register["name"] == "seq0"]

    from basil.dut import Dut

    daq = Dut(config)
    seq = None
    original = None
    try:
        daq.init()
        seq = daq["seq0"]
        assert seq.is_ready, "sequencer must be idle before its memory is changed"

        original = {
            "memory": bytes(seq.get_data(size=len(memory))),
            "size": int(seq.get_size()),
            "clk_divide": int(seq.get_clk_divide()),
            "repeat": int(seq.get_repeat()),
            "en_ext_start": int(seq.get_en_ext_start()),
        }

        # This is the same public Basil sequence used by scan_adc.py,
        # scan_compout.py, and loopback_serdes.py. The packing helper is tested
        # independently by test_helpers.py.
        seq.set_data(memory)
        seq.set_size(sequence_words)
        seq.set_clk_divide(TEST_CLK_DIVIDE)
        seq.set_repeat(TEST_REPEAT)
        seq.set_en_ext_start(False)

        assert bytes(seq.get_data(size=len(memory))) == bytes(memory)
        assert int(seq.get_size()) == sequence_words
        assert int(seq.get_clk_divide()) == TEST_CLK_DIVIDE
        assert int(seq.get_repeat()) == TEST_REPEAT
        assert int(seq.get_en_ext_start()) == 0
    finally:
        try:
            if seq is not None and original is not None:
                seq.set_data(original["memory"])
                seq.set_size(original["size"])
                seq.set_clk_divide(original["clk_divide"])
                seq.set_repeat(original["repeat"])
                seq.set_en_ext_start(original["en_ext_start"])
        finally:
            daq.close()
