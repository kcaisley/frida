"""Board-level tests for the FRIDA DAQ FPGA firmware (daq_core).

Tests each basil module (SPI, GPIO, sequencer, pulse_gen, fast_spi_rx)
via the DAQ helper functions. Runs in both simulation (cocotb + Icarus)
and hardware (basil Dut over SiTcp).

Usage:
    uv run pytest tests/test_daq.py -k sim          # simulation only
    uv run pytest tests/test_daq.py -k hw            # hardware only
    uv run pytest tests/test_daq.py -m "not hw"      # skip hardware
    uv run pytest tests/test_daq.py                   # both
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from flow.scans.chip import (
    SimBackend,
    _generate_conversion_sequence,
    pack_seq_tracks,
)
from flow.scans.daq import (
    GPIO_LOOPBACK_BIT,
    GPIO_RST_B_BIT,
    fspi_read_fifo,
    fspi_reset,
    fspi_set_en,
    gpio_write,
    seq_load,
    seq_trigger,
    spi_read,
    spi_write,
)

REPO = Path(__file__).resolve().parents[1]
DESIGN_FPGA = REPO / "design" / "fpga"


# =========================================================================
# Shared test logic (backend-agnostic)
# =========================================================================


async def check_spi_loopback(backend):
    """Write a known pattern through SPI, read back, verify match.

    tb_daq_core.v wires spi_sdo <- spi_sdi (MOSI loopback to MISO),
    so what we shift out should come back on the next read.
    """
    pattern = bytes([0xAA, 0x55] * 11 + [0xAA])  # 23 bytes >= 180 bits
    await spi_write(backend, pattern, 180)
    rx = await spi_read(backend, 180)
    assert rx[:23] == pattern[:23], f"SPI loopback mismatch: {rx[:23]} != {pattern[:23]}"


async def check_gpio_reset(backend):
    """Verify GPIO register accepts writes (toggle RST_B)."""
    await gpio_write(backend, 0x00)
    await backend.short_delay()
    await gpio_write(backend, 1 << GPIO_RST_B_BIT)
    await backend.short_delay()


async def check_sequencer_runs(backend):
    """Load a conversion sequence, trigger it, verify it completes."""
    seq = _generate_conversion_sequence()
    n_steps = len(seq["CLK_INIT"])
    mem_data = pack_seq_tracks(seq)
    await seq_load(backend, mem_data, n_steps)
    await seq_trigger(backend, n_steps, repeat=1)


async def check_sequencer_loopback(backend):
    """Verify sequencer data via fast_spi_rx loopback.

    Loads a known pattern on the TEST_DATA track (seq_out[6]),
    enables loopback mode (GPIO bit 2), triggers the sequencer,
    and reads back captured bits via fast_spi_rx.
    """
    n_steps = 40

    sen_comp = [0] * n_steps
    test_data = [0] * n_steps

    sen_start = 6
    sen_end = sen_start + 17 * 2 + 2
    for i in range(sen_start, min(sen_end, n_steps)):
        sen_comp[i] = 1

    for i in range(n_steps):
        test_data[i] = i % 2

    seq = {
        "CLK_INIT": [0] * n_steps,
        "CLK_SAMP": [0] * n_steps,
        "CLK_COMP": [0] * n_steps,
        "CLK_LOGIC": [0] * n_steps,
        "CLK_COMP_CAP": [0] * n_steps,
        "SEN_COMP": sen_comp,
        "TEST_DATA": test_data,
    }
    mem_data = pack_seq_tracks(seq)

    await gpio_write(backend, 1 << GPIO_LOOPBACK_BIT)
    await fspi_reset(backend)
    await fspi_set_en(backend, True)
    await backend.reset_fifo()

    await seq_load(backend, mem_data, n_steps)
    await seq_trigger(backend, n_steps, repeat=1)

    fifo_data = await fspi_read_fifo(backend, 8)
    await gpio_write(backend, 0x00)

    words = np.frombuffer(fifo_data, dtype=np.uint32)
    assert len(words) >= 1, "No data captured from fast_spi_rx"

    identifier = (words[0] >> 28) & 0xF
    assert identifier == 0x1, f"Wrong IDENTIFIER: {identifier:#x}, expected 0x1"

    data_bits = words[0] & 0xFFFF
    assert data_bits != 0, "Captured data is all zeros — loopback may not be working"


async def check_fspi_enable(backend):
    """Verify fast_spi_rx can be reset and toggled."""
    await fspi_reset(backend)
    await fspi_set_en(backend, True)
    await fspi_set_en(backend, False)
    await fspi_set_en(backend, True)


# =========================================================================
# cocotb simulation tests (discovered by the pytest plugin inside Icarus)
# =========================================================================

import cocotb
from cocotb.clock import Clock


@cocotb.test()
async def sim_spi_loopback(dut):
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    backend = SimBackend(dut)
    await backend.init()
    await check_spi_loopback(backend)


@cocotb.test()
async def sim_gpio_reset(dut):
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    backend = SimBackend(dut)
    await backend.init()
    await check_gpio_reset(backend)


@cocotb.test()
async def sim_sequencer_runs(dut):
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    backend = SimBackend(dut)
    await backend.init()
    await check_sequencer_runs(backend)


@cocotb.test()
async def sim_sequencer_loopback(dut):
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    backend = SimBackend(dut)
    await backend.init()
    await check_sequencer_loopback(backend)


@cocotb.test()
async def sim_fspi_enable(dut):
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    backend = SimBackend(dut)
    await backend.init()
    await check_fspi_enable(backend)


# =========================================================================
# pytest: simulation runner (cocotb plugin builds + launches simulator)
# =========================================================================


@pytest.fixture
def daq_core(hdl):
    """Build tb_daq_core for simulation."""
    import basil

    basil_fw = Path(basil.__file__).parent / "firmware" / "modules"

    hdl.toplevel = "tb_daq_core"
    hdl.sources = [
        DESIGN_FPGA / "tb_daq_core.v",
        DESIGN_FPGA / "daq_core.v",
    ]
    hdl.includes = [DESIGN_FPGA, basil_fw, basil_fw / "utils"]
    hdl.always = True
    hdl.build()
    return hdl


@pytest.mark.cocotb_runner
def test_daq_sim(daq_core):
    """Run all sim_* cocotb tests inside Icarus."""
    daq_core.test()


# =========================================================================
# pytest: hardware tests
# =========================================================================


@pytest.fixture(scope="module")
def hw_backend():
    """Connect to the FPGA and return a HardwareBackend."""
    from basil.dut import Dut

    from flow.scans.chip import HardwareBackend

    yaml_path = Path(__file__).resolve().parents[1] / "flow" / "scans" / "map_fpga.yaml"
    daq = Dut(str(yaml_path))
    daq.init()
    yield HardwareBackend(daq)


@pytest.mark.hw
def test_spi_loopback_hw(hw_backend):
    asyncio.run(check_spi_loopback(hw_backend))


@pytest.mark.hw
def test_gpio_reset_hw(hw_backend):
    asyncio.run(check_gpio_reset(hw_backend))


@pytest.mark.hw
def test_sequencer_runs_hw(hw_backend):
    asyncio.run(check_sequencer_runs(hw_backend))


@pytest.mark.hw
def test_sequencer_loopback_hw(hw_backend):
    asyncio.run(check_sequencer_loopback(hw_backend))


@pytest.mark.hw
def test_fspi_enable_hw(hw_backend):
    asyncio.run(check_fspi_enable(hw_backend))
