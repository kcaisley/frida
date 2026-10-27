"""Schmitt trigger layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

A ``*_all_pdks`` function lays out one case in all six PDKs by ALIGN from its hand-written floorplan
(``design/layout/schmitt_*.json``), each checked with DRC and LVS. Cases: the inverting trigger with
normal and with stronger feedback, and the buffer. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow schmitt.layout_inv
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, SchmittParams, write_netlist


def _netlists(params: SchmittParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The trigger's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _schmitt(run_dir: Path, pdk: str, case: str) -> Path:
    """A trigger case: its netlist into ``run_dir/netlist/``, then ALIGN as its floorplan
    places it."""

    name = f"schmitt_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def schmitt_inv_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _schmitt, "inv")


def schmitt_inv_wide_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _schmitt, "inv_wide")


def schmitt_buffer_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _schmitt, "buffer")


ALL_PDKS = (
    schmitt_inv_all_pdks,
    schmitt_inv_wide_all_pdks,
    schmitt_buffer_all_pdks,
)


def all_schmitt_layouts(run_dir: Path) -> Path:
    """The three ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
