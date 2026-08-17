"""
Shared parameters, enums, and dataclasses for FRIDA HDL21 generators.
"""

import math
from typing import Protocol, cast

import hdl21 as h
from hdl21.pdk import Corner
from hdl21.prefix import m


@h.paramclass
class PvtParams:
    """Process, Voltage, and Temperature condition."""

    p = h.Param(dtype=Corner, desc="Process corner", default=Corner.TYP)
    v = h.Param(dtype=Corner, desc="Voltage corner", default=Corner.TYP)
    t = h.Param(dtype=Corner, desc="Temperature corner", default=Corner.TYP)

    def __repr__(self) -> str:
        return f"PvtParams({self.p.name}, {self.v.name}, {self.t.name})"


# Preserve imports and persisted qualified-type references created before the
# parameter class adopted the repository's ``*Params`` naming convention.
Pvt = PvtParams


_FALLBACK_VDD_VALUES = (1080 * m, 1200 * m, 1320 * m)  # -10%, nominal, +10%


class _SupplyVoltageProvider(Protocol):
    """Structural type implemented by each local PDK installation class."""

    def supply_voltage(self, corner: Corner, rail: str = "VDD") -> h.Scalar: ...


def supply_voltage(
    corner: Corner,
    rail_name: str = "VDD",
    tech_name: str | None = None,
) -> h.Scalar:
    """Resolve one supply voltage from the active or selected PDK."""

    try:
        from pdk import _install_class, _resolve_tech_name

        name = _resolve_tech_name(tech_name)
        install_cls = cast(_SupplyVoltageProvider, _install_class(name))
        return install_cls.supply_voltage(corner, rail_name)
    except (
        ImportError,
        RuntimeError,
        ValueError,
        AttributeError,
        KeyError,
        TypeError,
    ):
        pass

    index = {Corner.SLOW: 0, Corner.TYP: 1, Corner.FAST: 2}.get(corner)
    if index is None:
        raise ValueError(f"Invalid corner: {corner}")
    return _FALLBACK_VDD_VALUES[index]


def temperature_c(corner: Corner) -> int:
    """Map a PVT temperature corner to degrees Celsius."""

    return {Corner.SLOW: -40, Corner.TYP: 25, Corner.FAST: 125}[corner]


def validate_uniform_sweep(minimum: h.Scalar, maximum: h.Scalar, step: h.Scalar) -> None:
    """Validate an inclusive, uniformly spaced scalar sweep."""

    minimum_value = float(minimum)
    maximum_value = float(maximum)
    step_value = float(step)
    if not all(math.isfinite(value) for value in (minimum_value, maximum_value, step_value)):
        raise ValueError("sweep values must be finite")
    if minimum_value > maximum_value:
        raise ValueError("sweep minimum must not exceed its maximum")
    if step_value <= 0.0:
        raise ValueError("sweep step must be positive")
    steps = (maximum_value - minimum_value) / step_value
    if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1.0e-9):
        raise ValueError("sweep endpoints must align to its step")


def build_uniform_sweep_values(minimum: h.Scalar, maximum: h.Scalar, step: h.Scalar) -> tuple[float, ...]:
    """Return an inclusive uniform grid without cumulative addition error."""

    validate_uniform_sweep(minimum, maximum, step)
    minimum_value = float(minimum)
    step_value = float(step)
    point_count = round((float(maximum) - minimum_value) / step_value) + 1
    return tuple(minimum_value + index * step_value for index in range(point_count))
