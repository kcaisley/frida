# FRIDA Chip Controller — unified for simulation and hardware
#
# Drives the FRIDA ADC test chip via an abstract backend that works in:
# - Simulation: cocotb + cocotbext-ams (SimBackend wraps BasilBusDriver)
# - Hardware: basil DAQ over SiTcp (HardwareBackend wraps basil Dut)
#
# Chip-level operations (register configuration, sequencer setup, ADC
# control) are shared. The Backend abstraction handles transport.
# FPGA module operations are delegated to DAQ helpers (flow/scans/daq.py).

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np
import yaml
from bitarray import bitarray

import flow.scans.daq as daq

if TYPE_CHECKING:
    from types import SimpleNamespace

    from basil.dut import Dut

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

N_ADCS = 16
SPI_BITS = 180
N_COMP_BITS = 17


# -------------------------------------------------------------------------
# Typed chip register map
# -------------------------------------------------------------------------


class CfgReg(Enum):
    """Typed FRIDA configuration-register identifiers."""

    MUX_SEL = "MUX_SEL"
    DAC_ASTATE_P = "DAC_ASTATE_P"
    DAC_BSTATE_P = "DAC_BSTATE_P"
    DAC_ASTATE_N = "DAC_ASTATE_N"
    DAC_BSTATE_N = "DAC_BSTATE_N"
    ADC_0 = "ADC_0"
    ADC_1 = "ADC_1"
    ADC_2 = "ADC_2"
    ADC_3 = "ADC_3"
    ADC_4 = "ADC_4"
    ADC_5 = "ADC_5"
    ADC_6 = "ADC_6"
    ADC_7 = "ADC_7"
    ADC_8 = "ADC_8"
    ADC_9 = "ADC_9"
    ADC_10 = "ADC_10"
    ADC_11 = "ADC_11"
    ADC_12 = "ADC_12"
    ADC_13 = "ADC_13"
    ADC_14 = "ADC_14"
    ADC_15 = "ADC_15"


@dataclass(frozen=True)
class CfgRegDef:
    """Definition of one FRIDA configuration register field."""

    offset: int
    size: int
    default: int
    description: str = ""


def _load_cfgreg_defs() -> dict[CfgReg, CfgRegDef]:
    """Load the typed FRIDA chip register map from map_chip.yaml."""
    reg_path = Path(__file__).parent / "map_chip.yaml"
    with open(reg_path) as f:
        raw = yaml.safe_load(f)

    cfgregs: dict[CfgReg, CfgRegDef] = {}
    for reg in CfgReg:
        entry = raw[reg.value]
        cfgregs[reg] = CfgRegDef(
            offset=entry["offset"],
            size=entry["size"],
            default=entry.get("default", 0),
            description=entry.get("description", ""),
        )
    return cfgregs


CFGREG_DEFS = _load_cfgreg_defs()
ADC_CFGREGS = tuple(getattr(CfgReg, f"ADC_{i}") for i in range(N_ADCS))


# -------------------------------------------------------------------------
# Sequencer helpers (pure Python, no I/O)
# -------------------------------------------------------------------------


def _generate_conversion_sequence(
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 2.5,
    init_pulse_ns: float = 5.0,
    samp_pulse_ns: float = 12.5,
    n_comp_bits: int = N_COMP_BITS,
    capture_delay_steps: int = 1,
) -> dict[str, list[int]]:
    """Generate sequencer waveforms for one ADC conversion cycle.

    At 400 MHz (2.5 ns/step), 100 ns = 40 steps:
      - CLK_INIT : 5 ns pulse  (2 steps) at t=0
      - CLK_SAMP : 12.5 ns pulse (5 steps) at t=5 ns
      - CLK_COMP : 17 pulses, each 2.5 ns, starting at t=15 ns
      - CLK_LOGIC: 16 pulses interleaved with CLK_COMP (first comp is free)
      - CLK_COMP_CAP: capture clock for fast_spi_rx, delayed by capture_delay_steps
      - SEN_COMP : frame enable, high across all 17 capture cycles
    """
    n_steps = int(conversion_period_ns / seq_clk_period_ns)

    clk_init = [0] * n_steps
    clk_samp = [0] * n_steps
    clk_comp = [0] * n_steps
    clk_logic = [0] * n_steps
    clk_comp_cap = [0] * n_steps
    sen_comp = [0] * n_steps

    init_steps = int(init_pulse_ns / seq_clk_period_ns)  # 2
    samp_steps = int(samp_pulse_ns / seq_clk_period_ns)  # 4
    samp_start = init_steps  # step 2
    comp_start = init_steps + samp_steps  # step 6

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


def pack_seq_tracks(seq: dict[str, list[int]]) -> list[int]:
    """Pack sequencer track dict into byte array for seq_gen memory.

    Each byte holds one timestep: bit 0=CLK_INIT, ..., bit 5=SEN_COMP,
    bit 6=TEST_DATA, bit 7=SPARE_7.
    """
    track_order = [
        "CLK_INIT",
        "CLK_SAMP",
        "CLK_COMP",
        "CLK_LOGIC",
        "CLK_COMP_CAP",
        "SEN_COMP",
        "TEST_DATA",
    ]
    n_steps = len(next(iter(seq.values())))
    mem_data = []
    for step in range(n_steps):
        byte = 0
        for bit_pos, track in enumerate(track_order):
            if track in seq and seq[track][step]:
                byte |= 1 << bit_pos
        mem_data.append(byte)
    return mem_data


# -------------------------------------------------------------------------
# Backend Protocol
# -------------------------------------------------------------------------


class Backend(Protocol):
    """Transport abstraction for FRIDA chip communication.

    Both simulation (cocotb BasilBusDriver) and hardware (basil SiTcp)
    implement this interface. DAQ helpers and the Frida class call these
    methods without knowing which transport is in use.
    """

    async def init(self) -> None: ...

    async def write(self, addr: int, data: Sequence[int]) -> None: ...

    async def read(self, addr: int, size: int) -> list[int]: ...

    async def wait_for_ready(self, addr: int, timeout: int = 10000) -> None: ...

    async def read_fifo_data(self, n_bytes: int) -> bytes: ...

    async def reset_fifo(self) -> None: ...

    async def short_delay(self) -> None: ...


# -------------------------------------------------------------------------
# SimBackend — cocotb BasilBusDriver
# -------------------------------------------------------------------------


class SimBackend:
    """Simulation backend using cocotb's BasilBusDriver.

    All bus operations are native cocotb coroutines.  Instantiate inside
    a ``@cocotb.test()`` function where the simulator is running.
    """

    def __init__(self, dut) -> None:
        from basil.utils.sim.BasilBusDriver import BasilBusDriver as _Drv

        self._dut = dut
        self._bus = _Drv(dut)

    async def init(self) -> None:
        await self._bus.init()
        # Initialize FIFO_READ if present (tb_daq_core exposes it)
        try:
            self._dut.FIFO_READ.value = 0
        except AttributeError:
            pass  # Not all testbenches have FIFO_READ

    async def write(self, addr: int, data: Sequence[int]) -> None:
        await self._bus.write(addr, list(data))

    @staticmethod
    def _logic_to_u8_with_xz_as_zero(value) -> int:
        """Convert a cocotb Logic/LogicArray value to a byte, mapping X/Z to 0."""
        bits = str(value)
        cleaned = "".join("0" if ch in "xXzZuUwWlLhH-" else ch for ch in bits)
        if len(cleaned) > 8:
            cleaned = cleaned[-8:]
        return int(cleaned, 2) & 0xFF

    async def read(self, addr: int, size: int) -> list[int]:
        """Read bytes from the simulated bus.

        Falls back to a tolerant implementation when the bus value contains
        X/Z bits, which can happen for the final partial byte of an exact-bit
        SPI transfer in simulation.
        """
        from cocotb.triggers import RisingEdge

        try:
            return list(await self._bus.read(addr, size))
        except ValueError:
            result = []

            self._bus.bus.BUS_DATA.value = self._bus._high_impedance
            self._bus.bus.BUS_ADD.value = self._bus._x
            self._bus.bus.BUS_RD.value = 0

            await RisingEdge(self._bus.clock)

            byte = 0
            while byte <= size:
                if byte == size:
                    self._bus.bus.BUS_RD.value = 0
                else:
                    self._bus.bus.BUS_RD.value = 1

                self._bus.bus.BUS_ADD.value = addr + byte

                await RisingEdge(self._bus.clock)

                if byte != 0:
                    bus_val = self._bus.bus.BUS_DATA.value
                    if self._bus._has_byte_acces and self._bus.bus.BUS_BYTE_ACCESS.value == 0:
                        word = str(bus_val)
                        if len(word) < 32:
                            word = word.rjust(32, "0")
                        for i in range(0, 32, 8):
                            result.append(self._logic_to_u8_with_xz_as_zero(word[i : i + 8]))
                    else:
                        if len(bus_val) == 8:
                            result.append(self._logic_to_u8_with_xz_as_zero(bus_val))
                        else:
                            result.append(self._logic_to_u8_with_xz_as_zero(bus_val[7:0]))

                if self._bus._has_byte_acces and self._bus.bus.BUS_BYTE_ACCESS.value == 0:
                    byte += 4
                else:
                    byte += 1

            self._bus.bus.BUS_ADD.value = self._bus._x
            self._bus.bus.BUS_DATA.value = self._bus._high_impedance
            await RisingEdge(self._bus.clock)

            return result

    async def wait_for_ready(self, addr: int, timeout: int = 10000) -> None:
        from cocotb.triggers import RisingEdge

        for _ in range(timeout):
            data = await self._bus.read(addr, 1)
            if data[0] & 0x01:
                return
            await RisingEdge(self._bus.clock)
        raise TimeoutError(f"Timeout waiting for READY at 0x{addr:05x}")

    async def read_fifo_data(self, n_bytes: int) -> bytes:
        """Read FIFO data directly from testbench signals.

        The testbench exposes FIFO_DATA, FIFO_EMPTY, and FIFO_READ as
        top-level ports. We read 32-bit words by toggling FIFO_READ.
        """
        from cocotb.triggers import RisingEdge

        result = bytearray()
        n_words = (n_bytes + 3) // 4

        for _ in range(n_words):
            # Check if FIFO has data
            try:
                empty = int(self._dut.FIFO_EMPTY.value)
            except ValueError:
                break  # FIFO_EMPTY is X/Z — no valid data
            if empty:
                break
            # Read the current word
            word = self._dut.FIFO_DATA.value.to_unsigned()
            result.extend(word.to_bytes(4, "little"))
            # Pulse FIFO_READ to advance to next word
            self._dut.FIFO_READ.value = 1
            await RisingEdge(self._bus.clock)
            self._dut.FIFO_READ.value = 0
            await RisingEdge(self._bus.clock)

        return bytes(result[:n_bytes])

    async def reset_fifo(self) -> None:
        pass  # No bram_fifo to reset; fast_spi_rx reset clears the pipeline

    async def short_delay(self) -> None:
        from cocotb.triggers import RisingEdge

        for _ in range(4):
            await RisingEdge(self._bus.clock)


# -------------------------------------------------------------------------
# HardwareBackend — basil Dut over SiTcp
# -------------------------------------------------------------------------


class HardwareBackend:
    """Hardware backend using a basil Dut connected over SiTcp.

    Bus operations are synchronous UDP/TCP calls wrapped in async def
    so the Frida class can use a uniform ``await`` interface.
    The caller must initialise the Dut (``daq.init()``) before
    constructing this backend.
    """

    def __init__(self, daq: Dut) -> None:
        self._daq = daq

    async def init(self) -> None:
        pass  # Dut already initialized by caller

    async def write(self, addr: int, data: Sequence[int]) -> None:
        self._daq["intf"].write(addr, data)

    async def read(self, addr: int, size: int) -> list[int]:
        return list(self._daq["intf"].read(addr, size))

    async def wait_for_ready(self, addr: int, timeout: int = 10000) -> None:
        for _ in range(timeout):
            data = self._daq["intf"].read(addr, 1)
            if data[0] & 0x01:
                return
            time.sleep(0.001)
        raise TimeoutError(f"Timeout waiting for READY at 0x{addr:05x}")

    async def read_fifo_data(self, n_bytes: int) -> bytes:
        return bytes(self._daq["fifo"].get_data())

    async def reset_fifo(self) -> None:
        # sitcp_fifo has no reset() method. Drain any stale bytes that
        # accumulated in the TCP stream since the last conversion so the
        # next read starts clean.
        self._daq["fifo"].get_data()

    async def short_delay(self) -> None:
        time.sleep(0.01)


# -------------------------------------------------------------------------
# Frida Chip Controller
# -------------------------------------------------------------------------


class Frida:
    """Unified controller for the FRIDA ADC test chip.

    Works seamlessly in both simulation (cocotb + cocotbext-ams) and
    hardware (basil DAQ over SiTcp).  The *backend* handles transport;
    DAQ helpers handle FPGA module protocols; this class owns chip state.

    Args:
        backend: Transport backend (SimBackend or HardwareBackend).
        peripherals: Optional namespace with ``.awg`` and ``.psu``
            attributes for controlling external instruments.
    """

    def __init__(
        self,
        backend: Backend,
        peripherals: SimpleNamespace | None = None,
    ) -> None:
        self._backend = backend
        self.peripherals = peripherals

        self.spi_bits = bitarray(SPI_BITS)
        self.spi_bits.setall(0)

        self._gpio_out = 0x00
        self._seq_n_steps = 40  # updated by _configure_sequencer
        self._registers = CFGREG_DEFS

        for reg, regdef in self._registers.items():
            self._write_cfgreg_bits(reg, regdef.default)

    async def init(self, write_initial_spi: bool = True) -> None:
        """Initialize the backend, sequencer, fast_spi_rx, and chip.

        Args:
            write_initial_spi: If True, preload the chip SPI register with the
                current local ``spi_bits`` contents immediately after reset.
                Set False for tests that need to control the first SPI
                transaction shape explicitly.
        """
        await self._backend.init()
        await self._configure_sequencer()
        await daq.fastrx_reset(self._backend)
        await daq.fastrx_set_en(self._backend, True)
        await self.reset()
        if write_initial_spi:
            await self.reg_write()
        logger.info("FRIDA chip initialized")

    # -----------------------------------------------------------------
    # Reset / GPIO
    # -----------------------------------------------------------------

    async def reset(self) -> None:
        """Toggle RST_B low then high."""
        self._gpio_out &= ~(1 << daq.GPIO_RST_B_BIT)
        await daq.gpio_write(self._backend, self._gpio_out)
        await self._backend.short_delay()
        self._gpio_out |= 1 << daq.GPIO_RST_B_BIT
        await daq.gpio_write(self._backend, self._gpio_out)
        await self._backend.short_delay()

    async def set_amplifier_enabled(self, enabled: bool) -> None:
        """Enable or disable the PCB input amplifier (THS4520)."""
        if enabled:
            self._gpio_out |= 1 << daq.GPIO_AMP_EN_BIT
        else:
            self._gpio_out &= ~(1 << daq.GPIO_AMP_EN_BIT)
        await daq.gpio_write(self._backend, self._gpio_out)
        logger.info("Input amplifier %s", "enabled" if enabled else "disabled")

    async def enable_amplifier(self) -> None:
        """Enable the PCB input amplifier."""
        await self.set_amplifier_enabled(True)

    async def disable_amplifier(self) -> None:
        """Disable the PCB input amplifier (bypass mode)."""
        await self.set_amplifier_enabled(False)

    # -----------------------------------------------------------------
    # SPI Register Access (pure Python, no I/O)
    # -----------------------------------------------------------------

    def _write_cfgreg_bits(self, reg: CfgReg, value: int) -> None:
        """Write a typed configuration register into the local SPI bit array."""
        regdef = self._registers[reg]
        mask = (1 << regdef.size) - 1
        value &= mask
        for i in range(regdef.size):
            self.spi_bits[regdef.offset + i] = (value >> i) & 1

    def _read_cfgreg_bits(self, reg: CfgReg) -> int:
        """Read a typed configuration register from the local SPI bit array."""
        regdef = self._registers[reg]
        value = 0
        for i in range(regdef.size):
            if self.spi_bits[regdef.offset + i]:
                value |= 1 << i
        return value

    def set_register(self, reg: CfgReg, value: int) -> None:
        """Set a typed configuration register in the local SPI bit array."""
        self._write_cfgreg_bits(reg, value)

    def get_register(self, reg: CfgReg) -> int:
        """Get a typed configuration register from the local SPI bit array."""
        return self._read_cfgreg_bits(reg)

    # -----------------------------------------------------------------
    # ADC Configuration (pure Python, no I/O)
    # -----------------------------------------------------------------

    def select_adc(self, adc_num: int) -> None:
        """Select which ADC output appears on COMP_OUT."""
        if not 0 <= adc_num < N_ADCS:
            raise ValueError(f"ADC number must be 0-15, got {adc_num}")
        self.set_register(CfgReg.MUX_SEL, adc_num)

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
        """Configure an individual ADC channel."""
        if not 0 <= adc_num < N_ADCS:
            raise ValueError(f"ADC number must be 0-15, got {adc_num}")
        value = (
            (int(en_init) << 0)
            | (int(en_samp_p) << 1)
            | (int(en_samp_n) << 2)
            | (int(en_comp) << 3)
            | (int(en_update) << 4)
            | (int(dac_mode) << 5)
            | (int(dac_diffcaps) << 6)
        )
        self.set_register(ADC_CFGREGS[adc_num], value)

    def enable_all_adcs(self) -> None:
        """Enable all 16 ADCs with default settings."""
        for i in range(N_ADCS):
            self.enable_adc(i)

    def disable_all_adcs(self) -> None:
        """Disable all 16 ADCs."""
        for reg in ADC_CFGREGS:
            self.set_register(reg, 0)

    def set_dac_state(
        self,
        astate_p: int = 0,
        bstate_p: int = 0,
        astate_n: int = 0,
        bstate_n: int = 0,
    ) -> None:
        """Set the shared DAC initial states for all ADCs."""
        self.set_register(CfgReg.DAC_ASTATE_P, astate_p & 0xFFFF)
        self.set_register(CfgReg.DAC_BSTATE_P, bstate_p & 0xFFFF)
        self.set_register(CfgReg.DAC_ASTATE_N, astate_n & 0xFFFF)
        self.set_register(CfgReg.DAC_BSTATE_N, bstate_n & 0xFFFF)

    # -----------------------------------------------------------------
    # Bus Operations (async, use DAQ helpers)
    # -----------------------------------------------------------------

    async def reg_write(self) -> None:
        """Shift the current register bit array into the chip."""
        await daq.spi_write(self._backend, self.spi_bits.tobytes(), SPI_BITS)

    async def reg_read(self, *, exact_bits: bool = False) -> bitarray:
        """Read back the chip register contents.

        Args:
            exact_bits: If True, request exactly ``SPI_BITS`` clock cycles from
                the SPI master. If False, round the transfer up to a full number
                of bytes to ensure the entire receive RAM is written.
        """
        raw = await daq.spi_read(self._backend, SPI_BITS, exact_bits=exact_bits)
        result = bitarray()
        result.frombytes(raw)
        return result[:SPI_BITS]

    async def run_conversions(
        self,
        n_conversions: int = 1,
        repetitions: int = 1,
    ) -> np.ndarray:
        """Run ADC conversions and return comp_out bits.

        Returns:
            Array of shape (repetitions, n_conversions, N_COMP_BITS)
            with individual bits (0 or 1), MSB first.
        """
        await daq.fastrx_reset(self._backend)
        await daq.fastrx_set_en(self._backend, True)
        await self._backend.reset_fifo()

        total_steps = self._seq_n_steps * n_conversions
        await daq.seq_trigger(self._backend, total_steps, repetitions)

        n_total = n_conversions * repetitions
        n_bytes = n_total * 2 * 4
        fifo_data = await daq.fastrx_read_fifo(self._backend, n_bytes)

        lost = await daq.fastrx_get_lost_count(self._backend)
        if lost > 0:
            logger.warning("fast_spi_rx lost %d words (FIFO overflow)", lost)

        return self._parse_comp_out(fifo_data, n_conversions, repetitions)

    async def sample_and_compare(self) -> int:
        """Run a single conversion and return the first comp_out bit."""
        bits = await self.run_conversions(n_conversions=1)
        return int(bits[0, 0, 0])

    # -----------------------------------------------------------------
    # Peripheral Dispatch
    # -----------------------------------------------------------------

    async def set_vin(self, diff: float, cm: float = 0.6) -> None:
        """Set the input voltage via the AWG peripheral."""
        if self.peripherals is None or not hasattr(self.peripherals, "awg"):
            raise RuntimeError("No AWG peripheral configured")
        await self.peripherals.awg.set_differential(diff, cm)

    async def set_vdd(self, v: float) -> None:
        """Set the supply voltage via the PSU peripheral."""
        if self.peripherals is None or not hasattr(self.peripherals, "psu"):
            raise RuntimeError("No PSU peripheral configured")
        await self.peripherals.psu.set_voltage(v)

    # -----------------------------------------------------------------
    # Data Parsing
    # -----------------------------------------------------------------

    @staticmethod
    def _parse_comp_out(
        fifo_data: bytes,
        n_conversions: int,
        repetitions: int = 1,
    ) -> np.ndarray:
        """Parse fast_spi_rx FIFO data into per-conversion bit arrays.

        The fast_spi_rx output format (32-bit words):
            [31:28] IDENTIFIER (4'b0001)
            [27:16] Frame counter (12 bits)
            [15:0]  Captured data (16 bits)

        For 17-bit conversions: word 0 has bits 0-15, word 1 has bit 16.

        Returns:
            Array of shape (repetitions, n_conversions, N_COMP_BITS),
            MSB first.
        """
        words = np.frombuffer(fifo_data, dtype=np.uint32)
        n_total = n_conversions * repetitions
        bits = np.zeros((n_total, N_COMP_BITS), dtype=np.int32)

        for i in range(n_total):
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

        return bits.reshape(repetitions, n_conversions, N_COMP_BITS)

    @staticmethod
    def bits_to_codes(bits: np.ndarray, weights: np.ndarray) -> np.ndarray:
        """Convert captured bits to weighted codes."""
        from flow.circuit.measure import redundant_bits_to_code

        original_shape = bits.shape
        n_bits = original_shape[-1]
        bits_flat = bits.reshape(-1, n_bits)
        codes_flat = redundant_bits_to_code(bits_flat, weights)
        return codes_flat.reshape(original_shape[:-1])

    # -----------------------------------------------------------------
    # High-Level Scan Utilities
    # -----------------------------------------------------------------

    async def measure_conversions(
        self,
        adc_num: int,
        n_conversions: int = 100,
        repetitions: int = 1,
        weights: np.ndarray | None = None,
    ) -> dict:
        """Configure an ADC and run conversions."""
        self.select_adc(adc_num)
        self.enable_adc(adc_num)
        await self.reg_write()

        bits = await self.run_conversions(n_conversions, repetitions)
        result: dict = {"adc": adc_num, "bits": bits}

        if weights is not None:
            result["codes"] = self.bits_to_codes(bits, weights)

        return result

    # -----------------------------------------------------------------
    # Private Helpers
    # -----------------------------------------------------------------

    async def _configure_sequencer(
        self,
        conversion_period_ns: int = 100,
        seq_clk_period_ns: float = 2.5,
        capture_delay_steps: int = 1,
    ) -> None:
        """Load the default conversion sequence into the sequencer."""
        seq = _generate_conversion_sequence(
            conversion_period_ns=conversion_period_ns,
            seq_clk_period_ns=seq_clk_period_ns,
            capture_delay_steps=capture_delay_steps,
        )
        n_steps = len(seq["CLK_INIT"])
        self._seq_n_steps = n_steps
        mem_data = pack_seq_tracks(seq)
        await daq.seq_load(self._backend, mem_data, n_steps)
