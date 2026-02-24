"""FRIDA PDK package namespace and shared helpers."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

import hdl21 as h
from hdl21.pdk import Corner

_KNOWN_PDKS: tuple[str, ...] = ("ihp130", "tsmc65", "tsmc28", "tower180")


def _active_tech_name() -> str | None:
    """Infer the active technology name from `h.pdk.default()`."""
    pdk_module = h.pdk.default()
    if pdk_module is None:
        return None
    module_name = getattr(pdk_module, "__name__", "")
    parts = module_name.split(".")
    if len(parts) >= 2 and parts[-1] == "pdk_logic":
        return parts[-2]
    if parts and parts[-1] in _KNOWN_PDKS:
        return parts[-1]
    return None


def _resolve_tech_name(tech_name: str | None) -> str:
    """Resolve a tech-name token, defaulting to the active PDK."""
    name = (tech_name or _active_tech_name() or "").strip().lower()
    if not name:
        raise RuntimeError("No active PDK is set. Call `h.pdk.set_default(...)` first.")
    if name not in _KNOWN_PDKS:
        known = ", ".join(_KNOWN_PDKS)
        raise ValueError(f"Unknown PDK '{name}'. Known: {known}")
    return name


def _pdk_data_module(tech_name: str | None = None) -> ModuleType:
    """Import and return `pdk.<tech>.pdk_data`."""
    name = _resolve_tech_name(tech_name)
    return import_module(f"pdk.{name}.pdk_data")


def supply_rails(tech_name: str | None = None) -> tuple[dict[str, object], ...]:
    """Get compile/simulation supply-rail metadata for a PDK."""
    mod = _pdk_data_module(tech_name)
    fn = getattr(mod, "supply_rails", None)
    if fn is None:
        raise AttributeError(f"{mod.__name__} does not define `supply_rails()`.")
    rails = fn()
    if not isinstance(rails, tuple):
        raise TypeError(f"{mod.__name__}.supply_rails() must return a tuple.")
    return rails


def supply_voltage(
    corner: Corner,
    rail_name: str = "VDD",
    tech_name: str | None = None,
) -> float:
    """
    Get rail voltage in volts for process-voltage corner `corner`.

    Corner mapping:
    - `Corner.SLOW` -> `min_volts`
    - `Corner.TYP` -> `nominal_volts`
    - `Corner.FAST` -> `max_volts`
    """
    rail_key = rail_name.strip().upper()
    for rail in supply_rails(tech_name):
        name = str(rail.get("name", "")).strip().upper()
        if name != rail_key:
            continue
        field = {
            Corner.SLOW: "min_volts",
            Corner.TYP: "nominal_volts",
            Corner.FAST: "max_volts",
        }.get(corner)
        if field is None:
            raise ValueError(f"Unsupported corner '{corner}'.")
        value = rail.get(field, rail.get("nominal_volts"))
        if value is None:
            raise ValueError(f"Rail '{rail_name}' in PDK '{tech_name}' has no voltage value.")
        return float(value)
    raise KeyError(f"Rail '{rail_name}' not found in PDK '{_resolve_tech_name(tech_name)}'.")


__all__ = ["supply_rails", "supply_voltage"]
