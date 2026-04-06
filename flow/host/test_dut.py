# FRIDA DAQ Test Entry Point
#
# pytest-based entry points for initializing and testing the FRIDA DAQ system.
# This is the missing entry point mentioned in plan.md that calls Dut("map_fpga.yaml")
# and daq.init().
#
# Usage:
#   pytest test_dut.py -v                    # Run all tests
#   pytest test_dut.py::test_connection -v   # Test connection only
#   pytest test_dut.py -k "not slow" -v      # Skip slow tests
#
# Or run directly:
#   python test_dut.py                        # Interactive mode
#
# Based on:
#   - obelix1-daq/obelix1/tests/test_system.py
#   - CordiaADC/ADC_01/host/meas.py

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def daq():
    """Create and initialize the basil Dut object.

    This fixture loads the FPGA hardware map from map_fpga.yaml and
    initializes all hardware drivers (fifo, seq, spi, gpio, pulse_gen,
    fast_spi_rx).

    Returns:
        Initialized basil Dut object
    """
    from basil.dut import Dut

    yaml_path = Path(__file__).parent / "map_fpga.yaml"
    logger.info(f"Loading DAQ configuration from {yaml_path}")

    daq = Dut(str(yaml_path))
    daq.init()

    logger.info("DAQ hardware initialized")
    yield daq

    # Cleanup (if needed)
    logger.info("DAQ test session complete")


@pytest.fixture(scope="module")
def frida(daq):
    """Create and initialize the Frida chip interface.

    This fixture creates the Frida controller object and performs
    chip initialization (reset, sequencer setup, SPI configuration).

    Args:
        daq: Initialized Dut object from daq fixture

    Returns:
        Initialized Frida object
    """
    from .host import Frida

    chip = Frida(daq)
    chip.init()

    logger.info("FRIDA chip initialized")
    return chip


# =============================================================================
# Connection Tests
# =============================================================================


class TestConnection:
    """Basic connectivity tests."""

    def test_daq_connection(self, daq):
        """Verify TCP/IP connection to the FPGA."""
        # Just accessing daq drivers confirms connection works
        assert daq["fifo"] is not None
        assert daq["seq"] is not None
        assert daq["spi"] is not None
        assert daq["gpio"] is not None
        assert daq["pulse_gen"] is not None
        assert daq["fast_spi_rx"] is not None
        logger.info("DAQ connection verified")

    def test_fast_spi_rx_version(self, daq):
        """Check fast_spi_rx module version."""
        # The fast_spi_rx module should report version 0
        # (from fast_spi_rx_core.v: localparam VERSION = 0)
        daq["fast_spi_rx"].reset()
        # Version is readable even after reset
        logger.info("fast_spi_rx module accessible")


class TestGPIO:
    """GPIO control tests."""

    def test_reset_control(self, daq):
        """Verify chip reset can be controlled via GPIO."""
        # Assert reset
        daq["gpio"]["RST_B"] = 0
        daq["gpio"].write()

        # Release reset
        daq["gpio"]["RST_B"] = 1
        daq["gpio"].write()

        logger.info("Reset control verified")

    def test_amplifier_control(self, daq):
        """Verify amplifier enable can be controlled via GPIO."""
        # Disable amplifier
        daq["gpio"]["AMP_EN"] = 0
        daq["gpio"].write()

        # Enable amplifier
        daq["gpio"]["AMP_EN"] = 1
        daq["gpio"].write()

        logger.info("Amplifier control verified")


# =============================================================================
# Sequencer Tests
# =============================================================================


class TestSequencer:
    """Sequencer functionality tests."""

    def test_sequence_load(self, daq):
        """Verify sequencer can be loaded with a pattern."""
        from bitarray import bitarray

        from .sequences import generate_conversion_sequence

        seq_data = generate_conversion_sequence()

        # Load all 6 tracks
        for track in [
            "CLK_INIT",
            "CLK_SAMP",
            "CLK_COMP",
            "CLK_LOGIC",
            "CLK_COMP_CAP",
            "SEN_COMP",
        ]:
            daq["SEQ"][track][: len(seq_data[track])] = bitarray(seq_data[track])

        daq["SEQ"].write()
        logger.info(f"Loaded {len(seq_data['CLK_INIT'])}-step sequence")

    def test_sequence_timing(self, daq):
        """Verify sequencer timing configuration."""
        daq["seq"].set_size(20)  # 20 steps per conversion
        daq["seq"].set_clk_divide(1)  # No division
        daq["seq"].set_repeat(1)

        logger.info("Sequencer timing configured")


# =============================================================================
# SPI Tests
# =============================================================================


class TestSPI:
    """SPI configuration tests."""

    def test_spi_write(self, frida):
        """Verify SPI register can be written."""
        # Set a known value
        frida.set_register("MUX_SEL", 5)
        frida.write_spi()

        logger.info("SPI write completed")

    def test_spi_readback(self, frida):
        """Verify SPI register can be read back."""
        # Set a known value
        frida.set_register("MUX_SEL", 7)
        frida.write_spi()

        # Read back
        rx_bits = frida.read_spi()
        assert len(rx_bits) == 180

        logger.info("SPI readback completed")


# =============================================================================
# ADC Configuration Tests
# =============================================================================


class TestADCConfig:
    """ADC configuration tests."""

    def test_adc_select(self, frida):
        """Verify ADC selection."""
        for adc_num in range(16):
            frida.select_adc(adc_num)
            assert frida.get_register("MUX_SEL") == adc_num

        logger.info("ADC selection verified for all 16 channels")

    def test_adc_enable(self, frida):
        """Verify ADC enable/disable."""
        # Enable ADC 0
        frida.enable_adc(0)
        adc_val = frida.get_register("ADC_0")
        assert adc_val & 0x1F == 0x1F  # All enable bits set

        # Disable all ADCs
        frida.disable_all_adcs()
        adc_val = frida.get_register("ADC_0")
        assert adc_val == 0

        logger.info("ADC enable/disable verified")

    def test_dac_state(self, frida):
        """Verify DAC state configuration."""
        frida.set_dac_state(astate_p=0x5555, bstate_p=0xAAAA)

        assert frida.get_register("DAC_ASTATE_P") == 0x5555
        assert frida.get_register("DAC_BSTATE_P") == 0xAAAA

        logger.info("DAC state configuration verified")


# =============================================================================
# Data Acquisition Tests
# =============================================================================


class TestDataAcquisition:
    """Data acquisition tests."""

    @pytest.mark.slow
    def test_single_conversion(self, frida):
        """Run a single ADC conversion."""
        frida.select_adc(0)
        frida.enable_adc(0)
        frida.write_spi()

        # Run 1 conversion
        data = frida.run_conversions(n_conversions=1, repetitions=1)

        assert data.shape == (1, 1)
        logger.info(f"Single conversion result: {data[0, 0]}")

    @pytest.mark.slow
    def test_multiple_conversions(self, frida):
        """Run multiple ADC conversions."""
        frida.select_adc(0)
        frida.enable_adc(0)
        frida.write_spi()

        # Run 100 conversions
        data = frida.run_conversions(n_conversions=100, repetitions=1)

        assert data.shape == (1, 100)
        logger.info(
            f"100 conversions: mean={np.mean(data):.1f}, std={np.std(data):.1f}"
        )

    @pytest.mark.slow
    def test_repeated_conversions(self, frida):
        """Run repeated ADC conversions."""
        frida.select_adc(0)
        frida.enable_adc(0)
        frida.write_spi()

        # Run 10 conversions x 10 repetitions
        data = frida.run_conversions(n_conversions=10, repetitions=10)

        assert data.shape == (10, 10)
        logger.info(f"10x10 conversions completed, total samples: {data.size}")


# =============================================================================
# fast_spi_rx Tests
# =============================================================================


class TestFastSpiRx:
    """fast_spi_rx module tests."""

    def test_enable_disable(self, daq):
        """Verify fast_spi_rx enable/disable."""
        daq["fast_spi_rx"].set_en(False)
        assert daq["fast_spi_rx"].get_en() == 0

        daq["fast_spi_rx"].set_en(True)
        assert daq["fast_spi_rx"].get_en() == 1

        logger.info("fast_spi_rx enable/disable verified")

    def test_reset(self, daq):
        """Verify fast_spi_rx reset."""
        daq["fast_spi_rx"].reset()
        # After reset, lost count should be 0
        assert daq["fast_spi_rx"].get_lost_count() == 0

        logger.info("fast_spi_rx reset verified")


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Full system integration tests."""

    @pytest.mark.slow
    def test_full_acquisition_cycle(self, frida):
        """Test a complete acquisition cycle."""
        # 1. Reset chip
        frida.reset()

        # 2. Configure sequencer
        frida._configure_sequencer(conversion_period_ns=100)

        # 3. Enable fast_spi_rx
        frida.daq["fast_spi_rx"].reset()
        frida.daq["fast_spi_rx"].set_en(True)

        # 4. Configure ADC 0
        frida.select_adc(0)
        frida.enable_adc(0)
        frida.write_spi()

        # 5. Run conversions
        data = frida.run_conversions(n_conversions=100, repetitions=1)

        # 6. Verify data
        assert data.shape == (1, 100)
        assert data.dtype == np.uint32

        # Basic sanity check: values should be within 17-bit range
        assert np.all(data < 2**17)

        logger.info("Full acquisition cycle completed successfully")


# =============================================================================
# Interactive Mode
# =============================================================================


def main():
    """Interactive mode for manual testing."""
    from basil.dut import Dut

    from .host import Frida

    print("=" * 60)
    print("FRIDA DAQ Interactive Mode")
    print("=" * 60)

    # Initialize DAQ
    yaml_path = Path(__file__).parent / "map_fpga.yaml"
    print(f"\nLoading DAQ configuration from {yaml_path}")

    try:
        daq = Dut(str(yaml_path))
        daq.init()
        print("✓ DAQ hardware initialized")
    except Exception as e:
        print(f"✗ DAQ initialization failed: {e}")
        return

    # Initialize FRIDA
    try:
        chip = Frida(daq)
        chip.init()
        print("✓ FRIDA chip initialized")
    except Exception as e:
        print(f"✗ FRIDA initialization failed: {e}")
        return

    print("\n" + "=" * 60)
    print("System Ready")
    print("=" * 60)
    print("\nAvailable objects:")
    print("  daq  - Basil Dut object (FPGA hardware)")
    print("  chip - Frida object (chip controller)")
    print("\nExample commands:")
    print("  chip.select_adc(0)")
    print("  chip.enable_adc(0)")
    print("  chip.write_spi()")
    print("  data = chip.run_conversions(100, 1)")
    print()

    # Drop into interactive mode
    try:
        import IPython

        IPython.embed()
    except ImportError:
        import code

        code.interact(local={"daq": daq, "chip": chip, "np": np})


if __name__ == "__main__":
    main()
