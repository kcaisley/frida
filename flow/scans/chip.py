# FRIDA Chip Controller — cocotb-native
#
# Drives the FRIDA ADC chip via basil's BasilBusDriver directly from a
# cocotb test. No socket IPC — the scan IS the cocotb test.
#
# Register addresses and protocols match the basil hardware layers
# (spi, gpio, seq_gen, pulse_gen, fast_spi_rx) used in flow/host/host.py.

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import yaml
from basil.utils.sim.BasilBusDriver import BasilBusDriver
from bitarray import bitarray

if TYPE_CHECKING:
    from cocotb.handle import SimHandleBase

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

N_ADCS = 16
SPI_BITS = 180
N_COMP_BITS = 17

# Base addresses (from map_fpga.yaml)
_SEQ_BASE = 0x10000
_SPI_BASE = 0x20000
_GPIO_BASE = 0x30000
_PULSE_GEN_BASE = 0x40000
_FAST_SPI_RX_BASE = 0x50000

# Register offsets within each basil hardware module
# (derived from basil HL drivers: spi.py, gpio.py, seq_gen.py, etc.)
_SPI_READY = 1  # bit 0 of byte at offset 1
_SPI_START = 1  # writeonly byte at offset 1
_SPI_SIZE = 3  # 16-bit LE at offset 3
_SPI_MEM = 16  # data memory starts at offset 16

_GPIO_OUTPUT = 2  # 1 byte for 8-bit GPIO (io_bytes=1)
_GPIO_RST_B_BIT = 0
_GPIO_AMP_EN_BIT = 1

_SEQ_READY = 1
_SEQ_START = 1
_SEQ_EN_EXT_START = 2
_SEQ_CLK_DIV = 3
_SEQ_SIZE = 4  # 32-bit LE at offset 4
_SEQ_REPEAT = 12  # 32-bit LE at offset 12
_SEQ_MEM = 64  # sequence memory starts at offset 64

_PGEN_START = 1
_PGEN_DELAY = 3  # 32-bit LE at offset 3
_PGEN_WIDTH = 7  # 32-bit LE at offset 7

_FSPI_RESET = 0
_FSPI_EN = 2  # bit 0 of byte at offset 2
_FSPI_LOST_COUNT = 3


# -------------------------------------------------------------------------
# Sequencer helpers
# -------------------------------------------------------------------------


def _generate_conversion_sequence(
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 2.5,
    init_pulse_ns: float = 5.0,
    samp_pulse_ns: float = 10.0,
    n_comp_bits: int = N_COMP_BITS,
    capture_delay_steps: int = 1,
) -> dict[str, list[int]]:
    """Generate sequencer waveforms for one ADC conversion cycle.

    Identical logic to flow/host/sequences.py:generate_conversion_sequence().
    """
    n_steps = int(conversion_period_ns / seq_clk_period_ns)

    clk_init = [0] * n_steps
    clk_samp = [0] * n_steps
    clk_comp = [0] * n_steps
    clk_logic = [0] * n_steps
    clk_comp_cap = [0] * n_steps
    sen_comp = [0] * n_steps

    init_steps = int(init_pulse_ns / seq_clk_period_ns)
    samp_steps = int(samp_pulse_ns / seq_clk_period_ns)
    samp_start = init_steps
    comp_start = init_steps + samp_steps

    for i in range(init_steps):
        clk_init[i] = 1
    for i in range(samp_start, samp_start + samp_steps):
        clk_samp[i] = 1

    n_logic_bits = n_comp_bits - 1
    for bit in range(n_comp_bits):
        comp_step = comp_start + bit * 2
        if comp_step < n_steps:
            clk_comp[comp_step] = 1
        logic_step = comp_start + bit * 2 + 1
        if bit < n_logic_bits and logic_step < n_steps:
            clk_logic[logic_step] = 1

    for bit in range(n_comp_bits):
        sample_step = comp_start + bit * 2 + 1 + capture_delay_steps
        if sample_step < n_steps:
            clk_comp_cap[sample_step] = 1

    sen_start = comp_start
    last_capture = comp_start + (n_comp_bits - 1) * 2 + 1 + capture_delay_steps
    sen_end = min(last_capture + 2, n_steps)
    for i in range(sen_start, sen_end):
        sen_comp[i] = 1

    return {
        "CLK_INIT": clk_init,
        "CLK_SAMP": clk_samp,
        "CLK_COMP": clk_comp,
        "CLK_LOGIC": clk_logic,
        "CLK_COMP_CAP": clk_comp_cap,
        "SEN_COMP": sen_comp,
    }


# -------------------------------------------------------------------------
# Bus helpers
# -------------------------------------------------------------------------


def _le16(value: int) -> list[int]:
    """Encode a 16-bit value as little-endian bytes."""
    return [value & 0xFF, (value >> 8) & 0xFF]


def _le32(value: int) -> list[int]:
    """Encode a 32-bit value as little-endian bytes."""
    return [
        value & 0xFF,
        (value >> 8) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 24) & 0xFF,
    ]


# -------------------------------------------------------------------------
# Frida class
# -------------------------------------------------------------------------


class Frida:
    """cocotb-native controller for the FRIDA ADC test chip.

    Drives the basil bus directly via BasilBusDriver — no socket IPC.

    Args:
        dut: cocotb DUT handle.
        peripherals: SimpleNamespace with .awg and .psu attributes.
    """

    def __init__(self, dut: SimHandleBase, peripherals: SimpleNamespace):
        self.dut = dut
        self.peripherals = peripherals
        self.spi_bits = bitarray(SPI_BITS)
        self.spi_bits.setall(0)

        # Will be initialized in init()
        self._bus: BasilBusDriver | None = None

        # Load register definitions
        reg_path = Path(__file__).parent / "map_dut.yaml"
        with open(reg_path) as f:
            self._registers = yaml.safe_load(f)

        # GPIO shadow register
        self._gpio_out = 0x00

    async def init(self) -> None:
        """Initialize the bus driver and chip."""
        self._bus = BasilBusDriver(self.dut)
        await self._bus.init()

        # Configure sequencer with default timing
        await self._configure_sequencer()

        # Enable fast_spi_rx
        await self._fspi_reset()
        await self._fspi_set_en(True)

        # Release reset
        await self.reset()

        # Load default SPI config
        await self.write_spi()

        logger.info("FRIDA chip initialized (cocotb-native)")

    # ---------------------------------------------------------------------
    # Reset
    # ---------------------------------------------------------------------

    async def reset(self) -> None:
        """Toggle RST_B low then high."""
        assert self._bus is not None
        self._gpio_out &= ~(1 << _GPIO_RST_B_BIT)
        await self._bus.write(_GPIO_BASE + _GPIO_OUTPUT, [self._gpio_out])
        # A few bus clock cycles for the reset to propagate
        from cocotb.triggers import RisingEdge

        for _ in range(4):
            await RisingEdge(self._bus.clock)
        self._gpio_out |= 1 << _GPIO_RST_B_BIT
        await self._bus.write(_GPIO_BASE + _GPIO_OUTPUT, [self._gpio_out])
        for _ in range(4):
            await RisingEdge(self._bus.clock)

    # ---------------------------------------------------------------------
    # SPI register access (pure Python, same as host.py)
    # ---------------------------------------------------------------------

    def set_register(self, name: str, value: int) -> None:
        if name not in self._registers:
            raise ValueError(f"Unknown register: {name}")
        reg = self._registers[name]
        offset = reg["offset"]
        size = reg["size"]
        for i in range(size):
            self.spi_bits[offset + i] = (value >> i) & 1

    def get_register(self, name: str) -> int:
        if name not in self._registers:
            raise ValueError(f"Unknown register: {name}")
        reg = self._registers[name]
        offset = reg["offset"]
        size = reg["size"]
        value = 0
        for i in range(size):
            if self.spi_bits[offset + i]:
                value |= 1 << i
        return value

    # ---------------------------------------------------------------------
    # ADC configuration (same as host.py)
    # ---------------------------------------------------------------------

    def select_adc(self, adc_num: int) -> None:
        self.set_register("MUX_SEL", adc_num)

    def enable_adc(
        self,
        adc_num: int,
        en_init: bool = True,
        en_samp_p: bool = True,
        en_samp_n: bool = True,
        en_comp: bool = True,
        en_update: bool = True,
        dac_mode: bool = False,
        dac_diffcaps: bool = False,
    ) -> None:
        value = (
            (int(en_init) << 0)
            | (int(en_samp_p) << 1)
            | (int(en_samp_n) << 2)
            | (int(en_comp) << 3)
            | (int(en_update) << 4)
            | (int(dac_mode) << 5)
            | (int(dac_diffcaps) << 6)
        )
        self.set_register(f"ADC_{adc_num}", value)

    def disable_all_adcs(self) -> None:
        for i in range(N_ADCS):
            self.set_register(f"ADC_{i}", 0)

    def set_dac_state(
        self,
        astate_p: int = 0,
        bstate_p: int = 0,
        astate_n: int = 0,
        bstate_n: int = 0,
    ) -> None:
        self.set_register("DAC_ASTATE_P", astate_p & 0xFFFF)
        self.set_register("DAC_BSTATE_P", bstate_p & 0xFFFF)
        self.set_register("DAC_ASTATE_N", astate_n & 0xFFFF)
        self.set_register("DAC_BSTATE_N", bstate_n & 0xFFFF)

    # ---------------------------------------------------------------------
    # Bus operations (async, use BasilBusDriver)
    # ---------------------------------------------------------------------

    async def write_spi(self) -> None:
        """Shift the current SPI bit array into the chip."""
        assert self._bus is not None
        data = list(self.spi_bits.tobytes())

        # Write data to SPI memory
        await self._bus.write(_SPI_BASE + _SPI_MEM, data)

        # Set size and start
        await self._bus.write(_SPI_BASE + _SPI_SIZE, _le16(SPI_BITS))
        await self._bus.write(_SPI_BASE + _SPI_START, [0x01])

        # Wait for ready
        await self._wait_ready(_SPI_BASE + _SPI_READY)

    async def run_conversion(self, n_conversions: int = 1) -> np.ndarray:
        """Run ADC conversions and return comp_out bits.

        Returns:
            Array of shape (n_conversions, N_COMP_BITS) with individual
            bits (0 or 1), MSB first.
        """
        assert self._bus is not None

        # Reset fast_spi_rx
        await self._fspi_reset()
        await self._fspi_set_en(True)

        # Configure sequencer for N conversions
        seq = _generate_conversion_sequence()
        n_steps = len(seq["CLK_INIT"])
        await self._bus.write(
            _SEQ_BASE + _SEQ_SIZE,
            _le32(n_steps * n_conversions),
        )
        await self._bus.write(_SEQ_BASE + _SEQ_REPEAT, _le32(1))

        # Enable external start and trigger via pulse_gen
        await self._bus.write(_SEQ_BASE + _SEQ_EN_EXT_START, [0x01])
        await self._bus.write(_PULSE_GEN_BASE + _PGEN_DELAY, _le32(1))
        await self._bus.write(_PULSE_GEN_BASE + _PGEN_WIDTH, _le32(1))
        await self._bus.write(_PULSE_GEN_BASE + _PGEN_START, [0x01])

        # Wait for sequencer to finish
        await self._wait_ready(_SEQ_BASE + _SEQ_READY)

        # Read comp_out bits from fast_spi_rx FIFO
        # Each conversion: 2 words × 4 bytes = 8 bytes
        n_bytes = n_conversions * 2 * 4
        fifo_data = await self._bus.read(_FAST_SPI_RX_BASE + 16, n_bytes)

        return self._parse_comp_out(fifo_data, n_conversions)

    async def sample_and_compare(self) -> int:
        """Run a single sample-and-compare (no full conversion).

        Pulses seq_samp then seq_comp once and reads comp_out.

        Returns:
            comp_out value (0 or 1).
        """
        # Generate a minimal sequence: samp + 1 comp
        seq_data = _generate_conversion_sequence()
        n_steps = len(seq_data["CLK_INIT"])

        # We use the full sequence but only care about the first comp_out
        assert self._bus is not None
        await self._fspi_reset()
        await self._fspi_set_en(True)

        await self._bus.write(_SEQ_BASE + _SEQ_SIZE, _le32(n_steps))
        await self._bus.write(_SEQ_BASE + _SEQ_REPEAT, _le32(1))
        await self._bus.write(_SEQ_BASE + _SEQ_EN_EXT_START, [0x01])
        await self._bus.write(_PULSE_GEN_BASE + _PGEN_DELAY, _le32(1))
        await self._bus.write(_PULSE_GEN_BASE + _PGEN_WIDTH, _le32(1))
        await self._bus.write(_PULSE_GEN_BASE + _PGEN_START, [0x01])
        await self._wait_ready(_SEQ_BASE + _SEQ_READY)

        # Read first comp_out bit
        fifo_data = await self._bus.read(_FAST_SPI_RX_BASE + 16, 8)
        words = np.frombuffer(bytes(fifo_data), dtype=np.uint32)
        if len(words) >= 1:
            return int(words[0] & 0x01)
        return 0

    # ---------------------------------------------------------------------
    # Peripheral dispatch
    # ---------------------------------------------------------------------

    async def set_vin(self, diff: float, cm: float = 0.6) -> None:
        """Set the input voltage via the AWG peripheral."""
        await self.peripherals.awg.set_differential(diff, cm)

    async def set_vdd(self, v: float) -> None:
        """Set the supply voltage via the PSU peripheral."""
        await self.peripherals.psu.set_voltage(v)

    # ---------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------

    async def _configure_sequencer(self) -> None:
        """Load the default conversion sequence into the sequencer."""
        assert self._bus is not None
        seq = _generate_conversion_sequence()
        n_steps = len(seq["CLK_INIT"])

        # Pack tracks into bytes: bit 0=CLK_INIT, 1=CLK_SAMP, etc.
        track_order = [
            "CLK_INIT",
            "CLK_SAMP",
            "CLK_COMP",
            "CLK_LOGIC",
            "CLK_COMP_CAP",
            "SEN_COMP",
        ]
        mem_data = []
        for step in range(n_steps):
            byte = 0
            for bit_pos, track in enumerate(track_order):
                if seq[track][step]:
                    byte |= 1 << bit_pos
            mem_data.append(byte)

        # Write sequence memory
        await self._bus.write(_SEQ_BASE + _SEQ_MEM, mem_data)

        # Configure sequencer registers
        await self._bus.write(_SEQ_BASE + _SEQ_SIZE, _le32(n_steps))
        await self._bus.write(_SEQ_BASE + _SEQ_CLK_DIV, [0x01])  # no division

    async def _fspi_reset(self) -> None:
        assert self._bus is not None
        await self._bus.write(_FAST_SPI_RX_BASE + _FSPI_RESET, [0x01])

    async def _fspi_set_en(self, enable: bool) -> None:
        assert self._bus is not None
        await self._bus.write(
            _FAST_SPI_RX_BASE + _FSPI_EN,
            [0x01 if enable else 0x00],
        )

    async def _wait_ready(self, addr: int) -> None:
        """Poll a READY register until bit 0 is set."""
        assert self._bus is not None
        from cocotb.triggers import RisingEdge

        for _ in range(10000):
            data = await self._bus.read(addr, 1)
            if data[0] & 0x01:
                return
            await RisingEdge(self._bus.clock)
        raise TimeoutError(f"Timeout waiting for READY at 0x{addr:05x}")

    @staticmethod
    def _parse_comp_out(fifo_data: list[int], n_conversions: int) -> np.ndarray:
        """Parse fast_spi_rx FIFO data into per-conversion bit arrays.

        Returns:
            Array of shape (n_conversions, N_COMP_BITS), MSB first.
        """
        words = np.frombuffer(bytes(fifo_data), dtype=np.uint32)
        bits = np.zeros((n_conversions, N_COMP_BITS), dtype=np.int32)

        for i in range(n_conversions):
            idx = i * 2
            if idx + 1 < len(words):
                code = (words[idx] & 0xFFFF) | ((words[idx + 1] & 0x1) << 16)
            elif idx < len(words):
                code = words[idx] & 0xFFFF
            else:
                code = 0
            for b in range(N_COMP_BITS):
                bit_pos = N_COMP_BITS - 1 - b
                bits[i, b] = (code >> bit_pos) & 1

        return bits
