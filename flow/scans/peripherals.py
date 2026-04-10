# Peripheral Interfaces for FRIDA Scans
#
# Abstract interfaces for lab instruments (PSU, AWG) used by both
# hardware and simulation backends. Hardware backends use SCPI over
# basil Serial/Visa; simulation backends drive the cocotbext-ams bridge.

from __future__ import annotations

from abc import ABC, abstractmethod


class PowerSupply(ABC):
    """Abstract power supply interface."""

    @abstractmethod
    async def set_voltage(self, v: float) -> None: ...

    @abstractmethod
    async def on(self) -> None: ...

    @abstractmethod
    async def off(self) -> None: ...


class FunctionGenerator(ABC):
    """Abstract function generator / AWG interface."""

    @abstractmethod
    async def set_differential(self, diff: float, cm: float) -> None:
        """Set differential input voltage.

        Args:
            diff: Differential voltage (vin_p - vin_n).
            cm: Common-mode voltage (vin_p + vin_n) / 2.
        """

    @abstractmethod
    async def start_sin(
        self, amplitude: float, offset: float, freq_hz: float,
    ) -> None:
        """Start a sinusoidal output.

        Args:
            amplitude: Peak differential amplitude.
            offset: Common-mode offset voltage.
            freq_hz: Frequency in Hz.
        """
