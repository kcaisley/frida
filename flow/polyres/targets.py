"""The poly resistor's targets (``python -m flow polyres.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run

from . import layout, sim


def check() -> Path:
    """Each PDK's resistor simulated at its narrowest width and 4 um, against the row cell's model value."""
    return sim.polyres_check(new_run("sim", "polyres", "check"))


def layout_signoff() -> Path:
    """A 4 um resistor row cell in every PDK with one: drawn, DRC, and LVS where the PDK has a source line."""
    return layout.polyres_signoff(new_run("layout", "polyres", "signoff"))
