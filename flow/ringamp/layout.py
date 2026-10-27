"""Ring amplifier layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

A ``*_all_pdks`` function lays out one case in all six PDKs by ALIGN from its hand-written floorplan
(``design/layout/ringamp_*.json``), each checked with DRC and LVS. Cases: the single-ended ring
amplifier and one with a stronger output stage. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow ringamp.layout_se
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, RingampParams, write_netlist


def _netlists(params: RingampParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The ring amplifier's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _ringamp(run_dir: Path, pdk: str, case: str) -> Path:
    """A ring amplifier case: its netlist into ``run_dir/netlist/``, then ALIGN as its floorplan
    places it."""

    name = f"ringamp_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def ringamp_se_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ringamp, "se")


def ringamp_se_strong_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _ringamp, "se_strong")


ALL_PDKS = (ringamp_se_all_pdks, ringamp_se_strong_all_pdks)


def all_ringamp_layouts(run_dir: Path) -> Path:
    """The two ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
