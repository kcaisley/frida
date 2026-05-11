# FRIDA Chip Controller — unified for simulation and hardware
#
# Drives the FRIDA ADC test chip via a basil Dut instance.
#
# Chip-level operations (register configuration, sequencer setup, ADC
# control) are shared. FPGA module operations go directly through
# basil module interfaces (self._daq["module"].method()).

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import yaml
from bitarray import bitarray

if TYPE_CHECKING:
    from basil.dut import Dut

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Frida Chip Controller
# -------------------------------------------------------------------------
class Frida:
    """Unified controller for the FRIDA ADC test chip.

    Works seamlessly in both simulation (cocotb + cocotbext-ams) and
    hardware (basil DAQ over SiTcp).  The *daq* is a basil Dut instance;
    FPGA module operations go directly through its module interfaces.

    Args:
        daq: basil Dut instance providing module access
            (``daq["spi"]``, ``daq["gpio"]``, ``daq["seq_gen"]``, etc.).
        peripherals: Optional namespace with ``.awg`` and ``.psu``
            attributes for controlling external instruments.
    """

    # Chip-level constants
    N_ADCS = 16
    SPI_BITS = 180
    N_COMP_BITS = 17

    def _load_registers(self) -> dict:
        """Parse map_chip.yaml into a plain dict of register definitions.

        Validates that every expected register is present and that each
        entry has the required ``offset`` and ``size`` keys.
        """
        reg_path = Path(__file__).parent / "map_chip.yaml"
        with open(reg_path) as f:
            raw = yaml.safe_load(f)

        registers: dict[str, dict] = {}
        for name, entry in raw.items():
            if "offset" not in entry or "size" not in entry:
                raise ValueError(f"Register '{name}' in {reg_path} is missing 'offset' or 'size'")
            registers[name] = {
                "offset": entry["offset"],
                "size": entry["size"],
                "default": entry.get("default", 0),
            }

        # Validate the expected register set is present
        expected = {"MUX_SEL", "DAC_ASTATE_P", "DAC_BSTATE_P", "DAC_ASTATE_N", "DAC_BSTATE_N"}
        expected |= {f"ADC_{i}" for i in range(self.N_ADCS)}
        missing = expected - set(registers)
        if missing:
            raise ValueError(f"Missing registers in {reg_path}: {sorted(missing)}")

        return registers

    def __init__(
        self,
        daq: Dut,
        peripherals: SimpleNamespace | None = None,
    ) -> None:
        """Initialise the controller, load register defaults, and bring the
        chip out of reset.

        Args:
            daq: basil Dut instance providing module access.
            peripherals: Optional namespace with ``.awg`` / ``.psu`` attributes.
        """
        self._daq = daq
        self.peripherals = peripherals
        self._gpio_out = 0x00
        self._seq_n_steps = self.N_SEQ_STEPS
        self.spi_bits = bitarray(self.SPI_BITS)
        self.spi_bits.setall(0)
        self._registers = self._load_registers()
        self._adc_regs = tuple(f"ADC_{i}" for i in range(self.N_ADCS))
        for name, rdef in self._registers.items():
            self.set_register(name, rdef["default"])

        self._daq["fast_spi_rx"].reset()
        self._daq["fast_spi_rx"].set_en(True)
        self.set_and_reset()
        self.reg_write()
        logger.info("FRIDA chip initialized")

    # -----------------------------------------------------------------
    # Reset / GPIO
    # -----------------------------------------------------------------

    GPIO_RST_B_BIT = 0
    GPIO_AMP_EN_BIT = 1
    GPIO_LOOPBACK_BIT = 2
    GPIO_SPI_LOOPBACK_BIT = 3
    GPIO_DEBUG_COUNTER_BIT = 4
    GPIO_TIEHIGH_BIT = 5

    def set_and_reset(self) -> None:
        """Toggle RST_B low then high."""
        self._gpio_out &= ~(1 << self.GPIO_RST_B_BIT)
        self._daq["gpio"].set_data([self._gpio_out])
        self._gpio_out |= 1 << self.GPIO_RST_B_BIT
        self._daq["gpio"].set_data([self._gpio_out])

    def set_diffamp(self, enabled: bool) -> None:
        """Enable or disable the PCB input differential amplifier (THS4520)."""
        if enabled:
            self._gpio_out |= 1 << self.GPIO_AMP_EN_BIT
        else:
            self._gpio_out &= ~(1 << self.GPIO_AMP_EN_BIT)
        self._daq["gpio"].set_data([self._gpio_out])
        logger.info("Input diff-amp %s", "enabled" if enabled else "disabled")

    def set_spi_loopback(self, enabled: bool) -> None:
        """Enable or disable SPI SDO loopback (read back SDI instead of chip SDO).

        When enabled, the FPGA routes SPI_SDI back into the SPI master's SDO
        input, bypassing the chip.  SDI still drives the chip — only the
        receive path is redirected.
        """
        if enabled:
            self._gpio_out |= 1 << self.GPIO_SPI_LOOPBACK_BIT
        else:
            self._gpio_out &= ~(1 << self.GPIO_SPI_LOOPBACK_BIT)
        self._daq["gpio"].set_data([self._gpio_out])
        logger.info("SPI loopback %s", "enabled" if enabled else "disabled")

    def set_fastrx_loopback(self, enabled: bool) -> None:
        """Enable or disable fast_spi_rx test data loopback.

        When enabled, the FPGA routes seq_out[6] (fastrx_test_data) into the
        fast_spi_rx input instead of the COMP_OUT pin.
        """
        if enabled:
            self._gpio_out |= 1 << self.GPIO_LOOPBACK_BIT
        else:
            self._gpio_out &= ~(1 << self.GPIO_LOOPBACK_BIT)
        self._daq["gpio"].set_data([self._gpio_out])
        logger.info("Fast RX loopback %s", "enabled" if enabled else "disabled")

    def set_fifo_debug_counter(self, enabled: bool) -> None:
        """Replace fast_spi_rx FIFO output with a counting-up sequence.

        When enabled, the FPGA mux routes a debug up-counter to the
        FASTRX FIFO data port instead of the real COMP_OUT capture.
        Useful for verifying the upstream FIFO/DMA chain independently.
        """
        if enabled:
            self._gpio_out |= 1 << self.GPIO_DEBUG_COUNTER_BIT
        else:
            self._gpio_out &= ~(1 << self.GPIO_DEBUG_COUNTER_BIT)
        self._daq["gpio"].set_data([self._gpio_out])
        logger.info("Debug counter %s", "enabled" if enabled else "disabled")

    def set_fastrx_tiehigh(self, enabled: bool) -> None:
        """Tie the fast_spi_rx input high via GPIO bit 5.

        When enabled, the FPGA drives the FASTRX input high regardless
        of the COMP_OUT pin state.  Useful for verifying the capture
        chain reports all-ones when the input is pinned.
        """
        if enabled:
            self._gpio_out |= 1 << self.GPIO_TIEHIGH_BIT
        else:
            self._gpio_out &= ~(1 << self.GPIO_TIEHIGH_BIT)
        self._daq["gpio"].set_data([self._gpio_out])
        logger.info("Fast RX tie-high %s", "enabled" if enabled else "disabled")

    # -----------------------------------------------------------------
    # SPI Register Access (pure Python, no I/O)
    # -----------------------------------------------------------------
    def set_register(self, reg: str, value: int) -> None:
        """Write a named register into the local SPI bit array."""
        r = self._registers[reg]
        value &= (1 << r["size"]) - 1
        for i in range(r["size"]):
            self.spi_bits[r["offset"] + i] = (value >> i) & 1

    # -----------------------------------------------------------------
    # ADC Configuration (pure Python, no I/O)
    # -----------------------------------------------------------------
    def select_adc(self, adc_num: int) -> None:
        """Select which ADC output appears on COMP_OUT."""
        if not 0 <= adc_num < self.N_ADCS:
            raise ValueError(f"ADC number must be 0-15, got {adc_num}")
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
        """Configure an individual ADC channel."""
        if not 0 <= adc_num < self.N_ADCS:
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
        self.set_register(self._adc_regs[adc_num], value)

    def disable_all_adcs(self) -> None:
        """Disable all 16 ADCs."""
        for reg in self._adc_regs:
            self.set_register(reg, 0)

    def set_dac_state(
        self,
        astate_p: int = 0,
        bstate_p: int = 0,
        astate_n: int = 0,
        bstate_n: int = 0,
    ) -> None:
        """Set the shared DAC initial states for all ADCs."""
        self.set_register("DAC_ASTATE_P", astate_p & 0xFFFF)
        self.set_register("DAC_BSTATE_P", bstate_p & 0xFFFF)
        self.set_register("DAC_ASTATE_N", astate_n & 0xFFFF)
        self.set_register("DAC_BSTATE_N", bstate_n & 0xFFFF)

    # -----------------------------------------------------------------
    # Bus Operations
    # -----------------------------------------------------------------
    def reg_write(self) -> None:
        """Shift the current register bit array into the chip and verify.

        Performs two SPI transactions:
          1. First write — commits ``self.spi_bits`` and discards the
             returned bits (they reflect the *previous* register state).
          2. Second write — shifts the same bits again; the returned bits
             now match what was written in step 1, so we read them back
             and compare against the expected bit pattern.
        """
        spi = self._daq["spi"]
        spi_bytes = self.spi_bits.tobytes()

        # First write: commit the bits, discard the stale readback
        spi.set_data(list(spi_bytes))
        spi.set_size(self.SPI_BITS)
        spi.start()
        spi.wait_for_ready()
        logger.info("SPI register programmed")

        # Second write: shift again, capture the bits that were written
        spi.set_data(list(spi_bytes))
        spi.set_size(self.SPI_BITS)
        spi.start()
        spi.wait_for_ready()
        raw = bytes(spi.get_data(size=23))

        readback = bitarray()
        readback.frombytes(raw)
        readback = readback[: self.SPI_BITS]

        # Verify that the readback matches what was written.
        # The SPI SDO path has a 1-bit pipeline delay: the first captured
        # sample is stale (from before the shift started), so skip bit 0.
        expected = self.spi_bits.copy()
        n_mismatch = (expected[1:] ^ readback[1:]).count(1)
        if n_mismatch:
            logger.error(
                "SPI register verification failed: %d/%d bits mismatch (bit 0 excluded)",
                n_mismatch,
                self.SPI_BITS - 1,
            )
            logger.error(
                "expected: %s",
                expected.to01(),
            )
            logger.error(
                "readback: %s",
                readback.to01(),
            )
        else:
            logger.info("SPI register verification passed!")

    # Sequencer track names in display order (must match map_fpga.yaml TrackRegister)
    SEQ_TRACKS: tuple[str, ...] = (
        "CLK_INIT",
        "CLK_SAMP",
        "CLK_COMP",
        "CLK_LOGIC",
        "FASTRX_CLK",
        "FASTRX_EN",
        "FASTRX_TEST_DATA",
    )

    SEQ_CLK_FREQ = 200_000_000

    # Number of steps in every sequencer pattern
    N_SEQ_STEPS: int = 40

    # Named sequencer patterns — each maps track name → 40-char '0'/'1' string.
    SEQUENCES: dict[str, dict[str, str]] = {
        "adc": {  # full SAR conversion
            "CLK_INIT": "1100000000000000000000000000000000000000",
            "CLK_SAMP": "0011111000000000000000000000000000000000",
            "CLK_COMP": "0000000101010101010101010101010101010000",
            "CLK_LOGIC": "0000000010101010101010101010101010101000",
            "FASTRX_CLK": "0000000001010101010101010101010101010101",
            "FASTRX_EN": "0000000111111111111111111111111111111111",
        },
        "comp": {  # continuous comparator clock
            "CLK_INIT": "0000000000000000000000000000000000000000",
            "CLK_SAMP": "1111111111111111111111111111111111111111",
            "CLK_COMP": "1010101010101010101010101010101010101010",
            "CLK_LOGIC": "0000000000000000000000000000000000000000",
            "FASTRX_CLK": "0101010101010101010101010101010101010101",
            "FASTRX_EN": "1111111111111111111111111111111111111111",
        },
        "samp_comp": {  # single sample-and-compare
            "CLK_INIT": "0000000000000000000000000000000000000000",
            "CLK_SAMP": "1111100000000000000000000000000000000000",
            "CLK_COMP": "0000010000000000000000000000000000000000",
            "CLK_LOGIC": "0000000000000000000000000000000000000000",
            "FASTRX_CLK": "0000000100000000000000000000000000000000",
            "FASTRX_EN": "0000011110000000000000000000000000000000",
        },
        "calib": {  # DAC A→B calibration
            "CLK_INIT": "1100000000000000000000000000000000000000",
            "CLK_SAMP": "0011111000000000000000000000000000000000",
            "CLK_COMP": "0000000101000000000000000000000000000000",
            "CLK_LOGIC": "0000000010000000000000000000000000000000",
            "FASTRX_CLK": "0000000001010000000000000000000000000000",
            "FASTRX_EN": "0011111111111000000000000000000000000000",
        },
        "fastrx": {  # fast RX loopback test
            "CLK_INIT": "0001010101010101010101010101010101010000",  # mirrors FASTRX_CLK
            "CLK_SAMP": "1111111111111111111111111111111111111110",  # mirrors FASTRX_EN
            "CLK_COMP": "0011110011110011110011110011110011110000",  # mirrors FASTRX_TEST_DATA
            "CLK_LOGIC": "0000000000000000000000000000000000000000",
            "FASTRX_CLK": "0001010101010101010101010101010101010000",
            "FASTRX_EN": "1111111111111111111111111111111111111110",
            "FASTRX_TEST_DATA": "0011110011110011110011110011110011110000",
        },
    }

    def run_conversions(
        self,
        n_conversions: int = 1,
        repetitions: int = 1,
        *,
        counter_mode: bool = False,
    ) -> np.ndarray:
        """Run ADC conversions and return comp_out bits.

        Args:
            n_conversions: Number of conversions per repetition.
            repetitions: Number of sequencer repetitions (or number of
                words to read in *counter_mode*).
            counter_mode: If True, skip the sequencer and just read
                *repetitions* words directly from the FIFO.

        Returns:
            Array of shape (repetitions, n_conversions, N_COMP_BITS)
            with individual bits (0 or 1), MSB first.
        """
        self._daq["fast_spi_rx"].reset()
        self._daq["fast_spi_rx"].set_en(True)
        # Drain stale — keep reading until the FIFO is empty
        while len(self._daq["fifo"].get_data()) > 0:
            pass

        if counter_mode:
            # Counter mode: flush, wait, then read *repetitions* words
            import time

            time.sleep(0.02)
            fifo_data = self._daq["fifo"].get_data()
            fifo_data = fifo_data[:repetitions]
        else:
            total_steps = self._seq_n_steps * n_conversions
            self._daq["seq_gen"].set_size(total_steps)
            self._daq["seq_gen"].set_repeat(repetitions)
            self._daq["seq_gen"].set_en_ext_start(True)
            self._daq["pulse_gen"].set_delay(1)
            self._daq["pulse_gen"].set_width(1)
            self._daq["pulse_gen"].start()
            self._daq["seq_gen"].wait_for_ready()
            fifo_data = self._daq["fifo"].get_data()

        lost = self._daq["fast_spi_rx"].get_lost_count()
        if lost > 0:
            logger.warning("fast_spi_rx lost %d words (FIFO overflow)", lost)

        # Raw FIFO word dump
        if counter_mode:
            for i, w in enumerate(fifo_data):
                logger.info("FIFO[%d]: counter=0x%08X (%d)", i, int(w), int(w))
        else:
            for i, w in enumerate(fifo_data):
                w = int(w)
                ident = (w >> 28) & 0xF
                frame = (w >> 16) & 0xFFF
                data = w & 0xFFFF
                logger.info(
                    "FIFO[%d]: ID=%s frame=%s data=%s",
                    i,
                    format(ident, "04b"),
                    format(frame, "012b"),
                    format(data, "016b"),
                )

        if counter_mode:
            return fifo_data.reshape(-1, 1, 1)

        bits = self._parse_comp_out(fifo_data.tobytes(), n_conversions, repetitions)
        for rep in range(bits.shape[0]):
            for conv in range(bits.shape[1]):
                word = "".join(str(b) for b in bits[rep, conv])
                logger.info("FAST_RX  data=%s", word)
        return bits

    # -----------------------------------------------------------------
    # Peripheral Dispatch
    # -----------------------------------------------------------------
    def set_vin(self, diff: float, cm: float = 0.6) -> None:
        """Set the input voltage via the AWG peripheral.

        Args:
            diff: Differential voltage (V).  The AWG outputs
                ``high = cm + diff/2`` and ``low = cm - diff/2``.
            cm: Common-mode voltage (V), default 0.6 V.
        """
        if self.peripherals is None or not hasattr(self.peripherals, "awg"):
            raise RuntimeError("No AWG peripheral configured")
        low = cm - diff / 2
        high = cm + diff / 2
        self.peripherals.awg.set_voltage(low, high, unit="V")

    def set_vdd(self, v: float) -> None:
        """Set the supply voltage via the PSU peripheral."""
        if self.peripherals is None or not hasattr(self.peripherals, "psu"):
            raise RuntimeError("No PSU peripheral configured")
        self.peripherals.psu.set_voltage(v)

    # -----------------------------------------------------------------
    # Data Parsing
    # -----------------------------------------------------------------
    def _parse_comp_out(
        self,
        fifo_data: bytes,
        n_conversions: int,
        repetitions: int = 1,
        *,
        weights: np.ndarray | None = None,
    ) -> np.ndarray:
        """Parse fast_spi_rx FIFO data into per-conversion bit arrays.

        The fast_spi_rx output format (32-bit words):
            [31:28] IDENTIFIER (4'b0001)
            [27:16] Frame counter (12 bits)
            [15:0]  Captured data (16 bits)

        For 17-bit conversions: word 0 has bits 0-15, word 1 has bit 16.

        If *weights* are provided, the raw bits are converted to codes via
        ``redundant_bits_to_code`` before reshaping.

        Returns:
            Array of shape ``(repetitions, n_conversions, N_COMP_BITS)``
            (or ``(repetitions, n_conversions)`` when *weights* is given),
            MSB first.
        """
        words = np.frombuffer(fifo_data, dtype=np.uint32)
        n_total = n_conversions * repetitions
        bits = np.zeros((n_total, self.N_COMP_BITS), dtype=np.int32)

        for i in range(n_total):
            idx = i * 2
            if idx + 1 < len(words):
                code = (words[idx] & 0xFFFF) | ((words[idx + 1] & 0x1) << 16)
            elif idx < len(words):
                code = words[idx] & 0xFFFF
            else:
                code = 0
            for b in range(self.N_COMP_BITS):
                bit_pos = self.N_COMP_BITS - 1 - b
                bits[i, b] = (code >> bit_pos) & 1

        bits = bits.reshape(repetitions, n_conversions, self.N_COMP_BITS)

        if weights is not None:
            from flow.circuit.measure import redundant_bits_to_code

            original_shape = bits.shape
            n_bits = original_shape[-1]
            bits_flat = bits.reshape(-1, n_bits)
            codes_flat = redundant_bits_to_code(bits_flat, weights)
            return codes_flat.reshape(original_shape[:-1])

        return bits

    # -----------------------------------------------------------------
    # Sequencer Configuration
    # -----------------------------------------------------------------
    def configure_sequencer(
        self,
        sequence: str = "adc",
        *,
        seq_clk_div: int = 1,
    ) -> None:
        """Load a sequencer pattern into the FPGA sequencer SRAM.

        Args:
            sequence: ``"adc"``, ``"comp"``, ``"samp_comp"``,
                ``"calib"``, or ``"fastrx"``.
            seq_clk_div: Sequencer clock divider; 1 = full speed.
        """
        if sequence not in self.SEQUENCES:
            raise ValueError(f"Unknown sequence {sequence!r}; expected {', '.join(self.SEQUENCES)}")
        tracks = self.SEQUENCES[sequence]
        n_steps = self.N_SEQ_STEPS
        self._seq_n_steps = n_steps

        # Load each track into the SEQ TrackRegister, then write to hw in one call.
        seq_reg = self._daq["SEQ"]
        seq_reg.clear()
        for name, pattern in tracks.items():
            seq_reg[name][0:n_steps] = bitarray(pattern)
        seq_reg.write(n_steps)

        # Configure timing on the underlying seq_gen driver.
        self._daq["seq_gen"].set_size(n_steps)
        self._daq["seq_gen"].set_clk_divide(seq_clk_div)

        # Visual dump for debugging — read directly from the track bitarrays.
        logger.info("Sequencer pattern (%d steps):", n_steps)
        for name in self.SEQ_TRACKS:
            line = seq_reg[name][0:n_steps].to01() if name in tracks else "0" * n_steps
            logger.info("  %-18s %s", name, line)

        eff_freq = self.SEQ_CLK_FREQ / seq_clk_div
        logger.info(
            "Sequencer pattern loaded: %d steps, clk_div=%d (%.2f MHz effective)",
            n_steps,
            seq_clk_div,
            eff_freq / 1e6,
        )
