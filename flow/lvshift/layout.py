"""Level shifter layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

A ``*_all_pdks`` function lays out one case in all six PDKs by ALIGN from its hand-written floorplan
(``design/layout/lvshift_*.json``), each checked with DRC and LVS. Cases: the cross-coupled core,
with an input inverter and reset, and with output inverters. The runner is the comparator's
(``flow.layout.step``).

    uv run python -m flow lvshift.layout_core
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.layout.step import FLOORPLANS, all_pdks, finish, signed_off

from .subckt import CASES, LvShiftParams, write_netlist


def _netlists(params: LvShiftParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The level shifter's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _lvshift(run_dir: Path, pdk: str, case: str) -> Path:
    """A level shifter case: its netlist into ``run_dir/netlist/``, then ALIGN as its floorplan
    places it."""

    name = f"lvshift_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return signed_off(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def lvshift_core_all_pdks(run_dir: Path) -> Path:
    return all_pdks(run_dir, _lvshift, "core")


def lvshift_single_rst_all_pdks(run_dir: Path) -> Path:
    return all_pdks(run_dir, _lvshift, "single_rst")


def lvshift_buffered_all_pdks(run_dir: Path) -> Path:
    return all_pdks(run_dir, _lvshift, "buffered")


ALL_PDKS = (lvshift_core_all_pdks, lvshift_single_rst_all_pdks, lvshift_buffered_all_pdks)


def all_lvshift_layouts(run_dir: Path) -> Path:
    """The three ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return finish(run_dir, {}, failures)
