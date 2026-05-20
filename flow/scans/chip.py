# FRIDA Chip Controller — unified for simulation and hardware
#
# Drives the FRIDA ADC test chip via a basil Dut instance.
#
# Chip-level operations (register configuration, sequencer setup, ADC
# control) are shared. FPGA module operations go directly through
# basil module interfaces (self._daq["module"].method()).
"""FRIDA chip controller providing a high-level API for the FRIDA ADC chip."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
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
            (``daq["spi"]``, ``daq["GPIO"]``, ``daq["SEQ"]``, etc.).
        peripherals: Optional namespace with ``.awg`` and ``.psu``
            attributes for controlling external instruments.

    """

    def __init__(
        self,
        daq: Dut,
        peripherals: SimpleNamespace | None = None,
    ) -> None:
        """Initialise the controller, load register defaults, and bring the chip out of reset.

        Args:
            daq: basil Dut instance providing module access.
            peripherals: Optional namespace with ``.awg`` / ``.psu`` attributes.

        """
        self._daq = daq
        self.peripherals = peripherals
        self._gpio_out = 0x00
        self.n_adcs = 16
        self.n_spi_bits = 180
        self.n_comp_bits = 17
        self._registers = {
            "MUX_SEL": {"offset": 176, "size": 4, "value": 0},
            "DAC_ASTATE_P": {"offset": 48, "size": 16, "value": 0b0111111111111111},
            "DAC_BSTATE_P": {"offset": 32, "size": 16, "value": 0b0111111111111111},
            "DAC_ASTATE_N": {"offset": 16, "size": 16, "value": 0b0111111111111111},
            "DAC_BSTATE_N": {"offset": 0, "size": 16, "value": 0b0111111111111111},
        }
        self._registers.update({f"ADC_{i}": {"offset": 64 + i * 7, "size": 7, "value": 0} for i in range(self.n_adcs)})
        self._daq["FASTRX"].reset()
        self._daq["FASTRX"].set_en(True)
        self.set_and_reset()
        self.write_adc_cfg()
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
    GPIO_SEQ_START_BIT = 6
    GPIO_FASTRX_EN_MUX_BIT = 7

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

    def set_seq_fastrx_en(self, value: bool) -> None:
        """Set gpio[6] high or low.

        When ``fastrx_en_mux=gpio``, this controls both the sequencer
        trigger (rising edge) and the fastrx_en signal (static level).
        """
        if value:
            self._gpio_out |= 1 << self.GPIO_SEQ_START_BIT
            logger.info("Triggering sequencer and fastrx enable with GPIO")
        else:
            self._gpio_out &= ~(1 << self.GPIO_SEQ_START_BIT)
            logger.info("Ending fastrx enable window")
        self._daq["gpio"].set_data([self._gpio_out])

    def set_fastrx_en_mux(self, source: str) -> None:
        """Select the fastrx_en source.

        When ``"gpio"`` (gpio[7]=0), fastrx_en comes from gpio[6]
        (the same pin that triggers the sequencer).  When ``"seqout"``
        (gpio[7]=1), fastrx_en comes from the sequencer's FASTRX_EN track
        (seq_out[5]).

        Args:
            source: ``"gpio"`` or ``"seqout"``.

        """
        if source == "gpio":
            self._gpio_out &= ~(1 << self.GPIO_FASTRX_EN_MUX_BIT)
        elif source == "seqout":
            self._gpio_out |= 1 << self.GPIO_FASTRX_EN_MUX_BIT
        else:
            raise ValueError(f"Unknown fastrx_en source {source!r}; expected 'gpio' or 'seqout'")
        self._daq["gpio"].set_data([self._gpio_out])
        logger.info("fastrx_en source: %s", source)

    # -----------------------------------------------------------------
    # ADC Configuration Register Control
    #
    # The helpers below (adc_output_mux, adc_clkgate_and_mode,
    # adc_dac_states) only edit the internal _registers dict —
    # no hardware I/O occurs until write_adc_cfg() is called.
    # -----------------------------------------------------------------
    def adc_output_mux(self, adc_num: int) -> None:
        """Select which ADC output appears on COMP_OUT.

        Local helper — edits _registers only; call write_adc_cfg()
        to commit to hardware.
        """
        if not 0 <= adc_num < self.n_adcs:
            raise ValueError(f"ADC number must be 0-15, got {adc_num}")
        self._registers["MUX_SEL"]["value"] = adc_num

    def adc_clkgate_and_mode(
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
        """Configure clock gating and mode bits for one ADC channel.

        Local helper — edits _registers only; call write_adc_cfg()
        to commit to hardware.
        """
        if not 0 <= adc_num < self.n_adcs:
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
        self._registers[f"ADC_{adc_num}"]["value"] = value

    def adc_dac_states(
        self,
        astate_p: int = 0,
        bstate_p: int = 0,
        astate_n: int = 0,
        bstate_n: int = 0,
    ) -> None:
        """Set the shared DAC initial states for all ADCs.

        Local helper — edits _registers only; call write_adc_cfg()
        to commit to hardware.
        """
        self._registers["DAC_ASTATE_P"]["value"] = astate_p & 0xFFFF
        self._registers["DAC_BSTATE_P"]["value"] = bstate_p & 0xFFFF
        self._registers["DAC_ASTATE_N"]["value"] = astate_n & 0xFFFF
        self._registers["DAC_BSTATE_N"]["value"] = bstate_n & 0xFFFF

    def write_adc_cfg(self) -> None:
        """Shift the current register values into the chip and verify.

        Builds a 180-bit bitarray from the ``_registers`` dict, then
        performs two SPI transactions:
          1. First write — commits the bits and discards the returned
             bits (they reflect the *previous* register state).
          2. Second write — shifts the same bits again; the returned bits
             now match what was written in step 1, so we read them back
             and compare against the expected bit pattern.
        """
        bits = bitarray(self.n_spi_bits)
        bits.setall(0)

        # Build 180-bit list from _registers dict
        for r in self._registers.values():
            val = r["value"] & ((1 << r["size"]) - 1)
            for i in range(r["size"]):
                bits[r["offset"] + i] = (val >> i) & 1

        spi_bytes = bits.tobytes()

        # First write: commit the bits, discard the stale readback
        self._daq["spi"].set_data(list(spi_bytes))
        self._daq["spi"].set_size(self.n_spi_bits)
        self._daq["spi"].start()
        self._daq["spi"].wait_for_ready()
        logger.info("SPI register programmed")

        # Second write: shift again, capture the bits that were written
        self._daq["spi"].set_data(list(spi_bytes))
        self._daq["spi"].set_size(self.n_spi_bits)
        self._daq["spi"].start()
        self._daq["spi"].wait_for_ready()
        raw = bytes(self._daq["spi"].get_data(size=23))

        readback = bitarray()
        readback.frombytes(raw)
        readback = readback[: self.n_spi_bits]

        # Verify that the readback matches what was written.
        # The SPI SDO path has a 1-bit pipeline delay: the first captured
        # sample is stale (from before the shift started), so skip bit 0.
        n_mismatch = (bits[1:] ^ readback[1:]).count(1)
        if n_mismatch:
            logger.error(
                "SPI register verification failed: %d/%d bits mismatch (bit 0 excluded)",
                n_mismatch,
                self.n_spi_bits - 1,
            )
            logger.error(
                "expected: %s",
                bits.to01(),
            )
            logger.error(
                "readback: %s",
                readback.to01(),
            )
        else:
            logger.info("SPI register verification passed!")

    # -----------------------------------------------------------------
    # Sequencer Configuration
    # -----------------------------------------------------------------

    # Sequencer track names in display order (must match map_fpga.yaml TrackRegister)
    SEQ_TRACKS: tuple[str, ...] = (
        "INIT",
        "SAMP",
        "COMP",
        "LOGIC",
        "RX_CLK",
        "RX_EN",
        "RX_TEST",
    )

    SEQ_CLK_FREQ = 200_000_000

    # Number of steps in every sequencer pattern
    N_SEQ_STEPS: int = 40

    # Named sequencer patterns — each maps track name → 40-char '0'/'1' string.
    SEQUENCES: dict[str, dict[str, str]] = {
        "adc": {  # full SAR conversion
            "INIT": "1100000000000000000000000000000000000000",
            "SAMP": "0011111000000000000000000000000000000000",
            "COMP": "0000000101010101010101010101010101010000",
            "LOGIC": "0000000010101010101010101010101010101000",
            "RX_CLK": "0000000001010101010101010101010101010101",
            "RX_EN": "0000000111111111111111111111111111111111",
        },
        "comp": {  # continuous comparator clock
            "INIT": "0000000000000000000000000000000000000000",
            "SAMP": "1111111111111111111111111111111111111111",
            "COMP": "1010101010101010101010101010101010101010",
            "LOGIC": "0000000000000000000000000000000000000000",
            "RX_CLK": "0101010101010101010101010101010101010101",
            "RX_EN": "1111111111111111111111111111111111111111",
        },
        "samp_comp": {  # single sample-and-compare
            "INIT": "0000000000000000000000000000000000000000",
            "SAMP": "1111100000000000000000000000000000000000",
            "COMP": "0000010000000000000000000000000000000000",
            "LOGIC": "0000000000000000000000000000000000000000",
            "RX_CLK": "0000000100000000000000000000000000000000",
            "RX_EN": "0000011110000000000000000000000000000000",
        },
        "calib": {  # DAC A→B calibration
            "INIT": "1100000000000000000000000000000000000000",
            "SAMP": "0011111000000000000000000000000000000000",
            "COMP": "0000000101000000000000000000000000000000",
            "LOGIC": "0000000010000000000000000000000000000000",
            "RX_CLK": "0000000001010000000000000000000000000000",
            "RX_EN": "0011111111111000000000000000000000000000",
        },
        "fastrx": {  # fast RX loopback test
            "INIT": "0001010101010101010101010101010101000000",  # mirrors RX_CLK
            "SAMP": "1111111111111111111111111111111111111111",  # mirrors RX_EN
            "COMP": "0011110011110011110011110011110011110000",  # mirrors RX_TEST
            "LOGIC": "0000000000000000000000000000000000000000",
            "RX_CLK": "0001010101010101010101010101010101000000",
            "RX_EN": "1111111111111111111111111111111111111111",  # stays high, to allow incremeting
            "RX_TEST": "0011110011110011110011110011110011110000",
        },
    }

    def configure_sequencer(
        self,
        pattern: str = "adc",
        *,
        clkdiv: int = 1,
    ) -> None:
        """Load a sequencer pattern into the FPGA sequencer SRAM.

        Args:
            pattern: ``"adc"``, ``"comp"``, ``"samp_comp"``,
                ``"calib"``, or ``"fastrx"``.
            clkdiv: Sequencer clock divider; 1 = full speed.

        """
        if pattern not in self.SEQUENCES:
            raise ValueError(f"Unknown pattern {pattern!r}; expected {', '.join(self.SEQUENCES)}")
        tracks = self.SEQUENCES[pattern]

        self._daq["SEQ"].clear()
        for name, pattern_bits in tracks.items():
            self._daq["SEQ"][name][0 : self.N_SEQ_STEPS] = bitarray(pattern_bits)
        self._daq["SEQ"].write(self.N_SEQ_STEPS)

        self._daq["SEQ"].set_size(self.N_SEQ_STEPS)
        self._daq["SEQ"].set_clk_divide(clkdiv)

        logger.info("Sequencer pattern (%d steps):", self.N_SEQ_STEPS)
        for name in self.SEQ_TRACKS:
            line = self._daq["SEQ"][name][0 : self.N_SEQ_STEPS].to01() if name in tracks else "0" * self.N_SEQ_STEPS
            logger.info("  %-18s %s", name, line)

        eff_freq = self.SEQ_CLK_FREQ / clkdiv
        logger.info(
            "Sequencer pattern loaded: %d steps, clkdiv=%d (%.2f MHz effective)",
            self.N_SEQ_STEPS,
            clkdiv,
            eff_freq / 1e6,
        )

    def trigger_sequencer(
        self,
        repeats: int = 1,
    ) -> None:
        """Arm the sequencer for external start, and wait for completion.

        Drives gpio[6] high to start the sequencer and assert fastrx_en,
        waits for the expected duration, then clears gpio[6].

        Args:
            repeats: Number of sequencer repetitions.

        """
        import time

        if repeats <= 0:
            raise ValueError("repeats must be >= 1")

        self._daq["FASTRX"].reset()
        self._daq["FASTRX"].set_en(True)

        self._daq["SEQ"].set_repeat(repeats)
        self._daq["SEQ"].set_en_ext_start(True)

        # Drive gpio[6] high: rising edge starts the sequencer
        self.set_seq_fastrx_en(True)

        # Calculate expected run time
        clkdiv = self._daq["SEQ"].get_clk_divide()
        period = 1.0 / (self.SEQ_CLK_FREQ / clkdiv)
        duration_ns = int(self.N_SEQ_STEPS * period * repeats * 1e9)
        logger.info(
            "Waiting %d ns for sequencer to complete (%d steps, %d repeats)", duration_ns, self.N_SEQ_STEPS, repeats
        )
        time.sleep(duration_ns / 1e9)

        self.set_seq_fastrx_en(False)

        # Reset the sequencer state machine so outputs don't latch
        # at their last-step values. The SRAM pattern is preserved.
        self._daq["SEQ"].reset()

    # -----------------------------------------------------------------
    # FastRX and FIFO Configuration
    # -----------------------------------------------------------------

    def read_fastrx_fifo(self, words: int) -> np.ndarray:
        """Read *words* from the fastrx FIFO and log each word.

        Waits briefly for data to propagate from the FPGA FIFO
        through SiTCP into the Python socket buffer before reading.

        Args:
            words: Number of FIFO words to read.

        Returns:
            1-D numpy array of raw 32-bit FIFO words.

        """
        import time

        # Loop around get_data() until we have enough words
        fifo_data = []
        timeout = 1.0  # seconds
        deadline = time.monotonic() + timeout

        # This loop is a bit suspect
        while len(fifo_data) < words:
            if time.monotonic() > deadline:
                logger.warning(
                    "FIFO read timeout after %.1f s: got %d/%d words",
                    timeout,
                    len(fifo_data),
                    words,
                )
                break
            chunk = self._daq["fifo"].get_data()
            if chunk is not None and len(chunk) > 0:
                fifo_data.extend(chunk)
                deadline = time.monotonic() + timeout  # reset timeout on data
            else:
                time.sleep(0.001)
        fifo_data = np.array(fifo_data[:words])

        lost = self._daq["FASTRX"].get_lost_count()
        if lost > 0:
            logger.warning("FASTRX lost %d words (FIFO overflow)", lost)

        logger.info("FIFO read: requested %d words, got %d", words, len(fifo_data))

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

        return fifo_data

    def test_fastrx_fifo(self, words: int) -> np.ndarray:
        """Read *words* from the FIFO in counter test mode.

        Resets fastrx, drains stale data, waits briefly, then reads.
        Each word is logged as a raw counter value.

        Args:
            words: Number of FIFO words to read.

        Returns:
            1-D numpy array of raw 32-bit FIFO words.

        """
        import time

        self._daq["FASTRX"].reset()
        self._daq["FASTRX"].set_en(True)
        self._daq["fifo"]["RESET"]  # drain stale TCP buffer

        time.sleep(0.02)
        fifo_data = self._daq["fifo"].get_data()
        fifo_data = fifo_data[:words]

        lost = self._daq["FASTRX"].get_lost_count()
        if lost > 0:
            logger.warning("FASTRX lost %d words (FIFO overflow)", lost)

        logger.info("FIFO read: requested %d words, got %d", words, len(fifo_data))

        for i, w in enumerate(fifo_data):
            logger.info("FIFO[%d]: counter=0x%08X (%d)", i, int(w), int(w))

        return fifo_data

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
        """Set the supply voltage via the PSU peripheral.

        If no PSU is configured (manual mode), this is a no-op.
        """
        if self.peripherals is None or not hasattr(self.peripherals, "psu"):
            logger.info("VDD=%.2f V (manual mode — no PSU configured)", v)
            return
        self.peripherals.psu.set_voltage(v)
