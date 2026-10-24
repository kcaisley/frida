"""The layout flow's own targets (``python -m flow layout.<target>``): checks of each PDK's rows,
not of a block."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _run


def mos_inv() -> Path:
    """One NMOS and one PMOS row cell from each PDK's hand-written netlist (``mos_inv.sp``), by the
    floorplan ``design/layout/mos_inv.json``, with the three tools in every PDK."""
    return _all_pdks(
        new_run("layout", "mos_inv"),
        lambda run_dir, pdk: _run(
            run_dir, pdk, "mos_inv", ROOT / f"pdk/{pdk}/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json"
        ),
    )
