# Peripheral Interfaces for FRIDA Scans
#
# Hardware backends for lab instruments (PSU, AWG) used by FRIDA scans.
# These use SCPI over basil Serial/Visa. Simulation backends live in sim.py.

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from basil.dut import Dut

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Hardware backends (SCPI over basil Serial / Visa)
# -------------------------------------------------------------------------


class BasilPSU:
    """Hardware power supply via basil — wraps an instrument driver loaded
    from map_fpga.yaml (or a standalone Dut).

    Args:
        daq: Initialized basil Dut object.
        channel_name: Name of the PSU driver key in the Dut (default "psu").
        voltage_channel: PSU channel number (instrument-specific, default 1).
    """

    def __init__(self, daq: Dut, channel_name: str = "psu", voltage_channel: int = 1) -> None:
        self._daq = daq
        self._name = channel_name
        self._ch = voltage_channel

    async def set_voltage(self, v: float) -> None:
        self._daq[self._name].set_voltage(self._ch, v)
        logger.info("BasilPSU: channel %d → %.3f V", self._ch, v)

    async def on(self) -> None:
        self._daq[self._name].set_enable(self._ch, True)
        logger.info("BasilPSU: channel %d ON", self._ch)

    async def off(self) -> None:
        self._daq[self._name].set_enable(self._ch, False)
        logger.info("BasilPSU: channel %d OFF", self._ch)


class BasilAWG:
    """Hardware function generator via basil — wraps the Agilent 33250A
    (or compatible) driver loaded from map_awg.yaml.

    Initialises its own Dut from ``map_awg.yaml`` in the same directory as
    this file, or accepts an already-initialised Dut for flexibility.

    Args:
        daq: Initialized basil Dut object containing the AWG driver.
            If None, loads map_awg.yaml from flow/scans/ automatically.
        channel_name: Name of the AWG driver key in the Dut (default "awg").
    """

    def __init__(self, daq: Dut | None = None, channel_name: str = "awg") -> None:
        if daq is None:
            from basil.dut import Dut

            map_path = Path(__file__).resolve().parent / "map_awg.yaml"
            daq = Dut(str(map_path))
            daq.init()
            logger.info("BasilAWG: initialized from %s", map_path)
        self._daq = daq
        self._name = channel_name

    async def set_differential(self, diff: float, cm: float) -> None:
        """Set DC differential voltage by outputting vin_p on the AWG and
        computing vin_n = 2*cm - vin_p externally (single-output instrument).

        For a single-output AWG the common-mode offset is output directly and
        the caller is expected to use the PCB sediff stage for the conversion.
        This method sets a DC level equal to ``cm + diff/2`` (vin_p-equivalent).
        """
        vin_p = cm + diff / 2
        self._daq[self._name].set_voltage(vin_p)
        logger.info("BasilAWG: DC output → %.4f V (diff=%.4f, cm=%.4f)", vin_p, diff, cm)

    async def start_sin(self, amplitude: float, offset: float, freq_hz: float) -> None:
        """Start a sinusoidal output.

        Args:
            amplitude: Peak amplitude in volts (half the peak-to-peak swing).
            offset: DC offset (common-mode) in volts.
            freq_hz: Frequency in Hz.
        """
        self._daq[self._name].set_sine(freq_hz, amplitude, offset)
        logger.info(
            "BasilAWG: sine %.1f Hz, amp=%.3f V, offset=%.3f V",
            freq_hz,
            amplitude,
            offset,
        )
