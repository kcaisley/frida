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

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flow.scans.chip import Backend

# -------------------------------------------------------------------------
# Base addresses
# -------------------------------------------------------------------------

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


async def spi_write(backend: Backend, data: bytes | Sequence[int], n_bits: int) -> None:
    """Shift data out through the SPI module."""
    await backend.write(SPI_BASE + _SPI_MEM, list(data))
    await backend.write(SPI_BASE + _SPI_SIZE, le16(n_bits))
    await backend.write(SPI_BASE + _SPI_START, [0x01])
    await backend.wait_for_ready(SPI_BASE + _SPI_READY)


async def spi_read(backend: Backend, n_bits: int, *, exact_bits: bool = False) -> bytes:
    """Shift zeros in and return the received data.

    Args:
        backend: Transport backend for DAQ register access.
        n_bits: Number of SPI bits to shift.
        exact_bits: If True, request exactly ``n_bits`` clock cycles from the
            SPI core. If False, round up to a full number of bytes to ensure
            every RX RAM byte is written.
    """
    n_bytes = (n_bits + 7) // 8
    # By default transfer a full number of bytes so every receive RAM position
    # is written (avoids X values in simulation when n_bits isn't a multiple of 8).
    xfer_bits = n_bits if exact_bits else (n_bytes * 8)
    await backend.write(SPI_BASE + _SPI_MEM, [0] * n_bytes)
    await backend.write(SPI_BASE + _SPI_SIZE, le16(xfer_bits))
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


async def seq_load(backend: Backend, mem_data: Sequence[int], n_steps: int) -> None:
    """Load a pattern into sequencer memory and configure timing."""
    await backend.write(SEQ_BASE + _SEQ_MEM, list(mem_data))
    await backend.write(SEQ_BASE + _SEQ_SIZE, le32(n_steps))
    await backend.write(SEQ_BASE + _SEQ_CLK_DIV, [0x01])


async def seq_trigger(backend: Backend, size: int, repeat: int = 1) -> None:
    """Configure sequencer size/repeat, trigger via pulse_gen, wait for ready."""
    await backend.write(SEQ_BASE + _SEQ_SIZE, le32(size))
    await backend.write(SEQ_BASE + _SEQ_REPEAT, le32(repeat))
    await backend.write(SEQ_BASE + _SEQ_EN_EXT_START, [0x01])
    await backend.write(PULSE_GEN_BASE + _PGEN_DELAY, le32(1))
    await backend.write(PULSE_GEN_BASE + _PGEN_WIDTH, le32(1))
    await backend.write(PULSE_GEN_BASE + _PGEN_START, [0x01])
    await backend.wait_for_ready(SEQ_BASE + _SEQ_READY)


# -------------------------------------------------------------------------
# Fast SPI RX operations
# -------------------------------------------------------------------------


async def fspi_reset(backend: Backend) -> None:
    """Reset the fast_spi_rx module."""
    await backend.write(FAST_SPI_RX_BASE + _FSPI_RESET, [0x01])


async def fspi_set_en(backend: Backend, enable: bool) -> None:
    """Enable or disable the fast_spi_rx module."""
    await backend.write(FAST_SPI_RX_BASE + _FSPI_EN, [0x01 if enable else 0x00])


async def fspi_get_lost_count(backend: Backend) -> int:
    """Read the fast_spi_rx lost data counter."""
    data = await backend.read(FAST_SPI_RX_BASE + _FSPI_LOST_COUNT, 1)
    return data[0]


async def fspi_read_fifo(backend: Backend, n_bytes: int) -> bytes:
    """Read data from the fast_spi_rx / FIFO.

    In simulation this reads from bus memory; in hardware this reads
    from the SiTcp TCP stream. The backend handles the difference.
    """
    return await backend.read_fifo_data(n_bytes)
