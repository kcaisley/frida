"""Opt-in hardware pytests for the three FRIDA GPIO register blocks.

Each test writes only the outputs belonging to one GPIO block, verifies their
physical register readback, and restores the prior state before returning.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_gpio.py
"""

from pathlib import Path

import pytest
from yaml import safe_load

MAP_PATH = Path(__file__).resolve().parent / "map_fpga.yaml"
pytestmark = pytest.mark.hw


@pytest.fixture(scope="module")
def gpio_daq():
    """Initialize only the GPIO hardware and register layers."""
    config = safe_load(MAP_PATH.read_text())
    gpio_names = {"gpio0", "gpio1", "gpio2"}
    config["hw_drivers"] = [driver for driver in config["hw_drivers"] if driver["name"] in gpio_names]
    config["registers"] = [register for register in config["registers"] if register["name"] in gpio_names]

    from basil.dut import Dut

    daq = Dut(config)
    daq.init()
    try:
        yield daq
    finally:
        daq.close()


def test_gpio0_debug_control_write_and_readback(gpio_daq) -> None:
    """Hardware, GPIO0: toggle internal debug controls and restore them."""
    gpio = gpio_daq["gpio0"]
    fields = (
        "RST_B",
        "AMP_EN",
        "RX_LOOPBACK",
        "SPI_LOOPBACK",
        "DBG_FIFO",
        "RX_TIEHIGH",
        "SEQ_START",
        "RX_EN_MUX",
    )
    tested_fields = (
        "RX_LOOPBACK",
        "SPI_LOOPBACK",
        "DBG_FIFO",
        "RX_TIEHIGH",
        "RX_EN_MUX",
    )

    gpio.read()
    original = {field: gpio[field].tovalue() for field in fields}
    try:
        for field in tested_fields:
            expected = 1 - original[field]
            gpio[field] = expected
            gpio.write()
            gpio.read()
            assert gpio[field].tovalue() == expected

            gpio[field] = original[field]
            gpio.write()
    finally:
        for field, value in original.items():
            gpio[field] = value
        gpio.write()

    gpio.read()
    assert {field: gpio[field].tovalue() for field in fields} == original


def test_gpio1_comp_idelay_programming(gpio_daq) -> None:
    """Hardware, GPIO1: load another IDELAY tap value, then restore it."""
    gpio = gpio_daq["gpio1"]
    gpio.read()
    assert gpio["COMP_IDELAY_RDY"].tovalue(), "comparator IDELAYCTRL is not ready"
    original_taps = gpio["COMP_IDELAY_TAPS"].tovalue()
    test_taps = (original_taps + 1) % 32

    try:
        gpio["COMP_IDELAY_TAPS"] = test_taps
        gpio["COMP_IDELAY_LOAD"] = 1
        gpio.write()
        gpio["COMP_IDELAY_LOAD"] = 0
        gpio.write()

        gpio.read()
        assert gpio["COMP_IDELAY_TAPS"].tovalue() == test_taps
        assert gpio["COMP_IDELAY_LOAD"].tovalue() == 0
        assert gpio["COMP_IDELAY_RDY"].tovalue()
    finally:
        gpio["COMP_IDELAY_TAPS"] = original_taps
        gpio["COMP_IDELAY_LOAD"] = 1
        gpio.write()
        gpio["COMP_IDELAY_LOAD"] = 0
        gpio.write()

    gpio.read()
    assert gpio["COMP_IDELAY_TAPS"].tovalue() == original_taps
    assert gpio["COMP_IDELAY_LOAD"].tovalue() == 0


def test_gpio2_pll_command_and_status_registers(gpio_daq) -> None:
    """Hardware, GPIO2: test request readback without applying a new divider."""
    gpio = gpio_daq["gpio2"]
    gpio.read()
    original_request = gpio["REQUEST_N"].tovalue()
    original_apply = gpio["APPLY_TOGGLE"].tovalue()
    # GPIO initialization resets its output latch independently of the PLL
    # controller, so this register-wiring test preserves rather than judges
    # transaction status. test_plldrp.py owns lock and error assertions.
    original_status = {
        field: gpio[field].tovalue() for field in ("APPLIED_TOGGLE", "BUSY", "LOCKED", "ERROR", "ACTIVE_N")
    }

    test_request = 20 if original_request != 20 else 19
    try:
        # Keeping APPLY_TOGGLE unchanged verifies the writable request field
        # without initiating a PLL reconfiguration.
        gpio["REQUEST_N"] = test_request
        gpio["APPLY_TOGGLE"] = original_apply
        gpio.write()
        gpio.read()

        assert gpio["REQUEST_N"].tovalue() == test_request
        assert gpio["APPLY_TOGGLE"].tovalue() == original_apply
        assert {
            field: gpio[field].tovalue() for field in ("APPLIED_TOGGLE", "BUSY", "LOCKED", "ERROR", "ACTIVE_N")
        } == original_status
    finally:
        gpio["REQUEST_N"] = original_request
        gpio["APPLY_TOGGLE"] = original_apply
        gpio.write()

    gpio.read()
    assert gpio["REQUEST_N"].tovalue() == original_request
    assert gpio["APPLY_TOGGLE"].tovalue() == original_apply
