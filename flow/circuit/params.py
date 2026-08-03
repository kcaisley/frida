"""
Shared parameters, enums, and dataclasses for FRIDA HDL21 generators.
"""

from typing import ClassVar

import hdl21 as h
from hdl21.pdk import Corner
from hdl21.prefix import m
from pydantic.dataclasses import dataclass


@h.paramclass
class Pvt:
    """Process, Voltage, and Temperature condition."""

    p = h.Param(dtype=Corner, desc="Process corner", default=Corner.TYP)
    v = h.Param(dtype=Corner, desc="Voltage corner", default=Corner.TYP)
    t = h.Param(dtype=Corner, desc="Temperature corner", default=Corner.TYP)

    def __repr__(self) -> str:
        return f"Pvt({self.p.name}, {self.v.name}, {self.t.name})"


@dataclass
class SupplyVals:
    """
    Supply voltage values mapped from corners to physical voltages.

    Values are resolved from the active PDK's ``Install.supply_voltage()``
    classmethod when available.
    """

    VDD: h.Scalar

    # Fallback values used only when no active PDK metadata is available.
    VDD_VALS: ClassVar[list] = [1080 * m, 1200 * m, 1320 * m]  # -10%, nom, +10%

    @classmethod
    def corner(
        cls,
        corner: Corner,
        rail_name: str = "VDD",
        tech_name: str | None = None,
    ) -> "SupplyVals":
        """Create `SupplyVals` from a voltage corner and active/ selected PDK."""
        try:
            from pdk import _install_class, _resolve_tech_name

            name = _resolve_tech_name(tech_name)
            install_cls = _install_class(name)
            return cls(VDD=install_cls.supply_voltage(corner, rail_name))
        except (
            ImportError,
            RuntimeError,
            ValueError,
            AttributeError,
            KeyError,
            TypeError,
        ):
            pass

        idx = {Corner.SLOW: 0, Corner.TYP: 1, Corner.FAST: 2}.get(corner)
        if idx is None:
            raise ValueError(f"Invalid corner: {corner}")
        return cls(VDD=cls.VDD_VALS[idx])


def temperature_c(corner: Corner) -> int:
    """Map a PVT temperature corner to degrees Celsius."""

    return {Corner.SLOW: -40, Corner.TYP: 25, Corner.FAST: 125}[corner]
