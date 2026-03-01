"""FRIDA PDK package namespace and shared helpers."""

from __future__ import annotations

from importlib import import_module

_KNOWN_PDKS: tuple[str, ...] = ("ihp130", "tsmc65", "tsmc28", "tower180")


def _resolve_tech_name(tech_name: str | None) -> str:
    """Resolve a tech-name token, defaulting to the active PDK."""
    import hdl21 as h

    if tech_name is not None:
        name = tech_name.strip().lower()
    else:
        pdk_module = h.pdk.default()
        if pdk_module is None:
            raise RuntimeError(
                "No active PDK is set. Call `h.pdk.set_default(...)` first."
            )
        module_name = getattr(pdk_module, "__name__", "")
        parts = module_name.split(".")
        name = ""
        if len(parts) >= 2 and parts[-1] == "pdk_logic":
            name = parts[-2]
        elif parts and parts[-1] in _KNOWN_PDKS:
            name = parts[-1]
    if not name:
        raise RuntimeError("No active PDK is set. Call `h.pdk.set_default(...)` first.")
    if name not in _KNOWN_PDKS:
        known = ", ".join(_KNOWN_PDKS)
        raise ValueError(f"Unknown PDK '{name}'. Known: {known}")
    return name


def _install_class(tech_name: str) -> type:
    """Import and return the ``Install`` class for the given PDK."""
    mod = import_module(f"pdk.{tech_name}.pdk_logic")
    return mod.Install
