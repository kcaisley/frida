"""Follower layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/follower_*.json``), each checked with DRC
and LVS. Cases: NMOS and PMOS source followers, and NMOS and PMOS flipped voltage followers. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow follower.layout_source
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, FollowerParams, write_netlist


def _netlists(params: FollowerParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The follower's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _follower(run_dir: Path, pdk: str, case: str) -> Path:
    """A follower case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"follower_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def follower_source_all_pdks(run_dir: Path) -> Path:
    """NMOS source follower."""
    return _all_pdks(run_dir, _follower, "source")


def follower_source_pmos_all_pdks(run_dir: Path) -> Path:
    """PMOS source follower."""
    return _all_pdks(run_dir, _follower, "source_pmos")


def follower_flipped_all_pdks(run_dir: Path) -> Path:
    """NMOS flipped voltage follower."""
    return _all_pdks(run_dir, _follower, "flipped")


def follower_flipped_pmos_all_pdks(run_dir: Path) -> Path:
    """PMOS flipped voltage follower with an output sink."""
    return _all_pdks(run_dir, _follower, "flipped_pmos")


ALL_PDKS = (
    follower_source_all_pdks,
    follower_source_pmos_all_pdks,
    follower_flipped_all_pdks,
    follower_flipped_pmos_all_pdks,
)


def all_follower_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
