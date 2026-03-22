# FRIDA DAQ Host Package
#
# Based on:
#   - obelix1-daq/obelix1/system/__init__.py (package structure)
#
# This package provides the data acquisition interface for the FRIDA ADC chip.
# It uses the basil framework to communicate with the FPGA over Ethernet.
#
# Usage:
#     from basil.dut import Dut
#     from frida.daq.host import Frida
#
#     # Initialize hardware
#     daq = Dut("frida/daq/host/map_fpga.yaml")
#     daq.init()
#
#     # Create chip interface
#     chip = Frida(daq)
#     chip.init()
#
#     # Configure and run
#     chip.select_adc(0)
#     chip.enable_adc(0)
#     chip.write_spi()
#     data = chip.run_conversions(100)
#
# Or use the test entry point:
#     pytest test_dut.py -v
#     python -m frida.daq.host.test_dut

from .host import Frida
from .sequences import (
    generate_conversion_sequence,
    generate_multi_conversion_sequence,
    print_sequence_timing,
    sequence_from_csv,
    sequence_to_csv,
)

__all__ = [
    "Frida",
    "generate_conversion_sequence",
    "generate_multi_conversion_sequence",
    "print_sequence_timing",
    "sequence_from_csv",
    "sequence_to_csv",
]
