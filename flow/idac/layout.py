"""Current source layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

A ``*_all_pdks`` function lays out one case in all six PDKs by ALIGN from its hand-written floorplan
(``design/layout/idac_*.json``), each checked with DRC and LVS. Cases: switched NMOS units, a
cascoded steered PMOS unit, steered NMOS units, and a PMOS bias mirror. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow idac.layout_nmos_switched
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, IdacParams, write_netlist


def _netlists(params: IdacParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The current source's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _idac(run_dir: Path, pdk: str, case: str) -> Path:
    """A current source case: its netlist into ``run_dir/netlist/``, then ALIGN as its floorplan
    places it."""

    name = f"idac_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def idac_nmos_switched_all_pdks(run_dir: Path) -> Path:
    """Two switched NMOS units."""
    return _all_pdks(run_dir, _idac, "nmos_switched")


def idac_pmos_steer_cas_all_pdks(run_dir: Path) -> Path:
    """Cascoded steered PMOS unit."""
    return _all_pdks(run_dir, _idac, "pmos_steer_cas")


def idac_nmos_steer_all_pdks(run_dir: Path) -> Path:
    """Four steered NMOS units."""
    return _all_pdks(run_dir, _idac, "nmos_steer")


def idac_pmos_mirror_all_pdks(run_dir: Path) -> Path:
    """PMOS bias mirror."""
    return _all_pdks(run_dir, _idac, "pmos_mirror")


ALL_PDKS = (
    idac_nmos_switched_all_pdks,
    idac_pmos_steer_cas_all_pdks,
    idac_nmos_steer_all_pdks,
    idac_pmos_mirror_all_pdks,
)


def all_idac_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
