"""FRIDA DAQ FPGA firmware tests.

Hardware tests (``-m hw``) connect directly to the FPGA via SiTcp.
Simulation tests (``-m sim``) use the cocotb Python runner to build
``tb_daq_core`` with Icarus and drive it via SiSim over TCP.

Usage:
    uv run pytest flow/scans/test_daq.py -m hw       # hardware only
    uv run pytest flow/scans/test_daq.py -m sim      # simulation only
    uv run pytest flow/scans/test_daq.py              # all tests
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest

from flow.scans.chip import Frida

REPO = Path(__file__).resolve().parents[2]
DESIGN_FPGA = REPO / "design" / "fpga"

# ── fixtures ────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def daq():
    """Connect to the FPGA and return a basil Dut instance."""
    from basil.dut import Dut

    yaml_path = Path(__file__).resolve().parent / "map_fpga.yaml"
    daq = Dut(str(yaml_path))
    daq.init()
    yield daq


@pytest.fixture(scope="module")
def sim_daq(sim_runner):
    """Connect to the running cocotb simulation and return a basil Dut.

    Depends on ``sim_runner`` to ensure the simulator is up before
    SiSim tries to connect.
    """
    from basil.dut import Dut

    yaml_path = Path(__file__).resolve().parent / "map_sim.yaml"
    daq = Dut(str(yaml_path))
    daq.init()  # blocks until TCP server is ready (up to 120 s)
    yield daq
    daq["tcp"].close()


@pytest.fixture(scope="module")
def sim_runner():
    """Build tb_daq_core with Icarus and start the cocotb TCP server.

    Uses the cocotb Python runner so no Makefile is needed.  The
    ``basil.utils.sim.Test`` test module starts the socket server inside
    the simulator process; ``sim_daq`` then connects via SiSim.
    """
    import basil
    from cocotb_tools.runner import get_runner

    basil_fw = Path(basil.__file__).parent / "firmware" / "modules"
    build_dir = REPO / "scratch" / "sim" / "daq_core"

    runner = get_runner("icarus")
    runner.build(
        sources=[
            DESIGN_FPGA / "tb_daq_core.v",
            DESIGN_FPGA / "daq_core.v",
        ],
        includes=[DESIGN_FPGA, basil_fw, basil_fw / "utils"],
        hdl_toplevel="tb_daq_core",
        build_dir=str(build_dir),
        always=True,
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="tb_daq_core",
        test_module="basil.utils.sim.Test",
        build_dir=str(build_dir),
    )
    yield runner


# ── hardware tests ──────────────────────────────────────────────────────────


@pytest.mark.hw
def test_gpio_reset(daq):
    """Verify GPIO register accepts writes (toggle RST_B)."""
    daq["gpio"].set_data([0x00])
    daq["gpio"].set_data([1 << Frida.GPIO_RST_B_BIT])


@pytest.mark.hw
def test_fspi_enable(daq):
    """Verify FASTRX can be reset and toggled."""
    daq["FASTRX"].reset()
    daq["FASTRX"].set_en(True)
    daq["FASTRX"].set_en(False)
    daq["FASTRX"].set_en(True)


@pytest.mark.hw
def test_counter_fifo(daq):
    """Verify debug counter FIFO source.

    Enables the debug counter via GPIO bit 4, reads FIFO data, and checks
    that words form a continuous ascending sequence. The counter may start
    at an arbitrary value, so the test subtracts the first value and verifies
    the result counts 0, 1, 2, ..., N-1.
    """
    daq["gpio"].set_data([1 << Frida.GPIO_DEBUG_COUNTER_BIT])
    daq["FASTRX"].reset()
    daq["FASTRX"].set_en(True)
    daq["fifo"].get_data()  # drain

    time.sleep(0.1)  # let counter fill

    N_WORDS = 25
    data = daq["fifo"].get_data()

    daq["gpio"].set_data([0x00])
    daq["fifo"].get_data()  # drain

    assert len(data) >= N_WORDS, f"Insufficient data: {len(data)} words"
    words = [int(w) for w in data[:N_WORDS]]
    first = words[0]
    norm = [w - first for w in words]
    assert norm == list(range(N_WORDS)), f"Not sequential: {norm}"

    logger = logging.getLogger(__name__)
    logger.info(
        "Counter FIFO test passed: first raw value was %d, normalised sequence %s",
        first,
        norm,
    )


@pytest.mark.hw
def test_sequencer_tiehigh(daq):
    """Verify fastrx_in tied high via GPIO bit 5.

    Sets GPIO bit 5 to force fastrx_in to constant 1, loads a sequencer
    pattern with a toggling FASTRX_CLK and constant FASTRX_EN, triggers,
    and reads back FIFO data.  All captured data bits should be 1.
    """
    n_steps = 40
    mem_data = []
    for i in range(33):
        clk = i % 2
        mem_data.append(0x20 | (clk << 4))
    mem_data += [0x00] * 7

    daq["FASTRX"].reset()
    daq["FASTRX"].set_en(True)
    daq["fifo"].get_data()  # drain

    daq["gpio"].set_data([1 << Frida.GPIO_TIEHIGH_BIT])
    daq["SEQ"].set_data(mem_data)
    daq["SEQ"].set_size(n_steps)
    daq["SEQ"].set_clk_divide(4)
    daq["SEQ"].set_repeat(4)
    daq["SEQ"].set_en_ext_start(True)
    daq["pulse_gen"].set_delay(1)
    daq["pulse_gen"].set_width(1)
    daq["pulse_gen"].start()
    daq["SEQ"].wait_for_ready()

    time.sleep(0.1)

    daq["gpio"].set_data([0x00])

    data = daq["fifo"].get_data()
    assert len(data) > 0, "No FIFO data received"
    data_words = [int(w) & 0xFFFF for w in data]
    assert 0xFFFF in data_words, f"No all-1s word found: {[f'0x{w:04X}' for w in data_words[:5]]}"


# ── simulation tests ──────────────────────────────────────────────────────────────────────────


@pytest.mark.sim
def test_sim_gpio_reset(sim_daq):
    """Verify GPIO register accepts writes in simulation."""
    sim_daq["gpio"].set_data([0x00])
    sim_daq["gpio"].set_data([1 << Frida.GPIO_RST_B_BIT])


@pytest.mark.sim
def test_sim_fspi_enable(sim_daq):
    """Verify FASTRX can be reset and toggled in simulation."""
    sim_daq["FASTRX"].reset()
    sim_daq["FASTRX"].set_en(True)
    sim_daq["FASTRX"].set_en(False)
    sim_daq["FASTRX"].set_en(True)


@pytest.mark.sim
def test_sim_spi_loopback(sim_daq):
    """Write a known pattern through SPI and verify loopback readback.

    tb_daq_core.v wires spi_sdo <- spi_sdi (MOSI loopback to MISO).
    After the transfer the RX memory contains the looped-back data.
    """
    pattern = [0xAA, 0x55] * 11 + [0xAA]  # 23 bytes ≥ 180 bits
    sim_daq["spi"].set_data(pattern)
    sim_daq["spi"].set_size(180)
    sim_daq["spi"].start()
    sim_daq["spi"].wait_for_ready()
    rx = list(sim_daq["spi"].get_data(size=23))
    assert rx == pattern, f"SPI loopback mismatch: {rx}"


@pytest.mark.sim
def test_sim_sequencer_tiehigh(sim_daq):
    """Verify fastrx_in tied high via GPIO bit 5 in simulation."""
    n_steps = 40
    mem_data = []
    for i in range(33):
        clk = i % 2
        mem_data.append(0x20 | (clk << 4))
    mem_data += [0x00] * 7

    sim_daq["FASTRX"].reset()
    sim_daq["FASTRX"].set_en(True)
    sim_daq["fifo"].get_data()  # drain

    sim_daq["gpio"].set_data([1 << Frida.GPIO_TIEHIGH_BIT])
    sim_daq["SEQ"].set_data(mem_data)
    sim_daq["SEQ"].set_size(n_steps)
    sim_daq["SEQ"].set_clk_divide(4)
    sim_daq["SEQ"].set_repeat(4)
    sim_daq["SEQ"].set_en_ext_start(True)
    sim_daq["pulse_gen"].set_delay(1)
    sim_daq["pulse_gen"].set_width(1)
    sim_daq["pulse_gen"].start()
    sim_daq["SEQ"].wait_for_ready()

    sim_daq["gpio"].set_data([0x00])

    data = sim_daq["fifo"].get_data()
    assert len(data) > 0, "No FIFO data received from simulation"
    data_words = [int(w) & 0xFFFF for w in data]
    assert 0xFFFF in data_words, f"No all-1s word found: {[f'0x{w:04X}' for w in data_words[:5]]}"
