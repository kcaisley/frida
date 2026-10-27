"""Discriminator layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

A ``*_all_pdks`` function lays out one case in all six PDKs by ALIGN from its hand-written floorplan
(``design/layout/disc_*.json``), each checked with DRC and LVS. Cases: NMOS and PMOS input pairs,
each with a current-mirror load and with hysteresis. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow disc.layout_nmos
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, DiscParams, write_netlist


def _netlists(params: DiscParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The discriminator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _disc(run_dir: Path, pdk: str, case: str) -> Path:
    """A discriminator case: its netlist into ``run_dir/netlist/``, then ALIGN as its
floorplan places it."""

    name = f"disc_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def disc_nmos_all_pdks(run_dir: Path) -> Path:
    """NMOS input pair, current-mirror load."""
    return _all_pdks(run_dir, _disc, "nmos")


def disc_nmos_hyst_all_pdks(run_dir: Path) -> Path:
    """NMOS input pair, hysteresis."""
    return _all_pdks(run_dir, _disc, "nmos_hyst")


def disc_pmos_all_pdks(run_dir: Path) -> Path:
    """PMOS input pair, current-mirror load."""
    return _all_pdks(run_dir, _disc, "pmos")


def disc_pmos_hyst_all_pdks(run_dir: Path) -> Path:
    """PMOS input pair, hysteresis."""
    return _all_pdks(run_dir, _disc, "pmos_hyst")


ALL_PDKS = (
    disc_nmos_all_pdks,
    disc_nmos_hyst_all_pdks,
    disc_pmos_all_pdks,
    disc_pmos_hyst_all_pdks,
)


def all_disc_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
