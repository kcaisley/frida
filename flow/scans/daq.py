# DAQ Helper Functions — FPGA module operations
#
# Standalone async functions for operating the basil FPGA modules
# (spi, gpio, seq_gen, pulse_gen, fast_spi_rx) via a Backend.
# These know the register offsets and protocols but carry no chip state.
#
# Used by:
#   - flow/scans/chip.py (Frida class methods call these)
#   - tests/test_daq.py (board-level tests call these directly)
#
# Address map (from map_fpga.yaml / daq_core.v):
#   0x10000  seq_gen
#   0x20000  spi
#   0x30000  gpio
#   0x40000  pulse_gen
#   0x50000  fast_spi_rx

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flow.scans.chip import Backend

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Base addresses
# -------------------------------------------------------------------------

SEQ_CLK_FREQ = 200_000_000  # Hz — sequencer clock from PLL

SEQ_BASE = 0x10000
SPI_BASE = 0x20000
GPIO_BASE = 0x30000
PULSE_GEN_BASE = 0x40000
FAST_SPI_RX_BASE = 0x50000

# -------------------------------------------------------------------------
# SPI module offsets
# -------------------------------------------------------------------------

_SPI_READY = 1
_SPI_START = 1
_SPI_SIZE = 3  # 16-bit LE
_SPI_MEM = 16
_SPI_MEM_BYTES = 32  # matches daq_core.v MEM_BYTES parameter
_SPI_RX_MEM = _SPI_MEM + _SPI_MEM_BYTES  # receive RAM starts after transmit RAM

# -------------------------------------------------------------------------
# GPIO module offsets
# -------------------------------------------------------------------------

_GPIO_OUTPUT = 2
GPIO_RST_B_BIT = 0
GPIO_AMP_EN_BIT = 1
GPIO_LOOPBACK_BIT = 2
GPIO_SPI_LOOPBACK_BIT = 3
GPIO_DEBUG_COUNTER_BIT = 4
GPIO_TIEHIGH_BIT = 5

# -------------------------------------------------------------------------
# Sequencer module offsets
# -------------------------------------------------------------------------

_SEQ_READY = 1
_SEQ_EN_EXT_START = 2
_SEQ_CLK_DIV = 3
_SEQ_SIZE = 4  # 32-bit LE
_SEQ_REPEAT = 12  # 32-bit LE
_SEQ_MEM = 64

# -------------------------------------------------------------------------
# Pulse generator module offsets
# -------------------------------------------------------------------------

_PGEN_START = 1
_PGEN_DELAY = 3  # 32-bit LE
_PGEN_WIDTH = 7  # 32-bit LE

# -------------------------------------------------------------------------
# Fast SPI RX module offsets
# -------------------------------------------------------------------------

_FSPI_RESET = 0
_FSPI_EN = 2
_FSPI_LOST_COUNT = 3
_FSPI_MEM = 16


# -------------------------------------------------------------------------
# Byte encoding helpers
# -------------------------------------------------------------------------


def le16(value: int) -> list[int]:
    """Encode a 16-bit value as little-endian bytes."""
    return [value & 0xFF, (value >> 8) & 0xFF]


def le32(value: int) -> list[int]:
    """Encode a 32-bit value as little-endian bytes."""
    return [
        value & 0xFF,
        (value >> 8) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 24) & 0xFF,
    ]


# -------------------------------------------------------------------------
# SPI operations
# -------------------------------------------------------------------------


async def spi_write(backend: Backend, data: bytes | Sequence[int], n_bits: int) -> bytes:
    """Shift data out through the SPI module and return the received bits.

    The SPI master simultaneously shifts out data on MOSI and captures
    the MISO stream into the RX RAM.  This function writes the provided
    data and returns whatever was captured during the transaction.
    """
    n_bytes = (n_bits + 7) // 8
    # Transfer exactly the requested number of bits.
    # Padding to a full byte would overrun the chip shift register,
    # causing a spurious offset on the next readback.
    await backend.write(SPI_BASE + _SPI_MEM, list(data))
    await backend.write(SPI_BASE + _SPI_SIZE, le16(n_bits))
    await backend.write(SPI_BASE + _SPI_START, [0x01])
    await backend.wait_for_ready(SPI_BASE + _SPI_READY)
    return bytes(await backend.read(SPI_BASE + _SPI_RX_MEM, n_bytes))


# -------------------------------------------------------------------------
# GPIO operations
# -------------------------------------------------------------------------


async def gpio_write(backend: Backend, gpio_byte: int) -> None:
    """Write a value to the GPIO output register."""
    await backend.write(GPIO_BASE + _GPIO_OUTPUT, [gpio_byte])


# -------------------------------------------------------------------------
# Sequencer operations
# -------------------------------------------------------------------------


async def seq_load(
    backend: Backend,
    mem_data: Sequence[int],
    n_steps: int,
    clk_div: int = 1,
) -> None:
    """Load a pattern into sequencer memory and configure timing.

    Args:
        backend: Transport backend for DAQ register access.
        mem_data: Packed sequencer pattern bytes.
        n_steps: Number of sequencer steps in the loaded pattern.
        clk_div: Sequencer clock divider. A value of 1 advances the pattern on
            every sequencer clock. Larger values slow the effective sequencer
            step rate without changing the FPGA HDL.
    """
    if not 1 <= clk_div <= 255:
        raise ValueError(f"clk_div must be in the range 1..255, got {clk_div}")

    await backend.write(SEQ_BASE + _SEQ_MEM, list(mem_data))
    await backend.write(SEQ_BASE + _SEQ_SIZE, le32(n_steps))
    await backend.write(SEQ_BASE + _SEQ_CLK_DIV, [clk_div & 0xFF])
    print(mem_data)
    # Visual dump of sequencer memory for debugging
    track_names = [
        "CLK_INIT",
        "CLK_SAMP",
        "CLK_COMP",
        "CLK_LOGIC",
        "FASTRX_CLK",
        "FASTRX_EN",
        "FASTRX_TEST_DATA",
    ]
    logger.info("Sequencer pattern (%d steps):", n_steps)
    for bit_pos, name in enumerate(track_names):
        line = "".join("1" if (byte >> bit_pos) & 1 else "0" for byte in mem_data)
        logger.info("  %-18s %s", name, line)

    eff_freq = SEQ_CLK_FREQ / clk_div
    logger.info(
        "Sequencer pattern loaded: %d steps, clk_div=%d (%.2f MHz effective)",
        n_steps,
        clk_div,
        eff_freq / 1e6,
    )


async def seq_trigger(backend: Backend, size: int, repeat: int = 1) -> None:
    """Configure sequencer size/repeat, trigger via pulse_gen, wait for ready."""
    await backend.write(SEQ_BASE + _SEQ_SIZE, le32(size))
    await backend.write(SEQ_BASE + _SEQ_REPEAT, le32(repeat))
    await backend.write(SEQ_BASE + _SEQ_EN_EXT_START, [0x01])
    await backend.write(PULSE_GEN_BASE + _PGEN_DELAY, le32(1))
    await backend.write(PULSE_GEN_BASE + _PGEN_WIDTH, le32(1))
    await backend.write(PULSE_GEN_BASE + _PGEN_START, [0x01])
    await backend.wait_for_ready(SEQ_BASE + _SEQ_READY)
    logger.info("Sequencer triggered: %d steps, cycles=%d", size, repeat)


# -------------------------------------------------------------------------
# Fast SPI RX operations
# -------------------------------------------------------------------------


async def fastrx_reset(backend: Backend) -> None:
    """Reset the fast_spi_rx module."""
    await backend.write(FAST_SPI_RX_BASE + _FSPI_RESET, [0x01])


async def fastrx_set_en(backend: Backend, enable: bool) -> None:
    """Enable or disable the fast_spi_rx module."""
    await backend.write(FAST_SPI_RX_BASE + _FSPI_EN, [0x01 if enable else 0x00])


async def fastrx_get_lost_count(backend: Backend) -> int:
    """Read the fast_spi_rx lost data counter."""
    data = await backend.read(FAST_SPI_RX_BASE + _FSPI_LOST_COUNT, 1)
    return data[0]


async def fastrx_read_fifo(backend: Backend, n_bytes: int) -> bytes:
    """Read data from the fast_spi_rx / FIFO.

    In simulation this reads from bus memory; in hardware this reads
    from the SiTcp TCP stream. The backend handles the difference.
    """
    return await backend.read_fifo_data(n_bytes)
