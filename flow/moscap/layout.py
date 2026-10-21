"""Mos capacitor layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/moscap_*.json``), each checked with DRC and
LVS. Cases: NMOS and complementary decaps, and NMOS and PMOS two-net capacitors. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow moscap.layout_decap_n
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, MosCapParams, write_netlist


def _netlists(params: MosCapParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The MOS capacitor's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _moscap(run_dir: Path, pdk: str, case: str) -> Path:
    """A MOS capacitor case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"moscap_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def moscap_decap_n_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _moscap, "decap_n")


def moscap_decap_np_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _moscap, "decap_np")


def moscap_cap_n_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _moscap, "cap_n")


def moscap_cap_p_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _moscap, "cap_p")


ALL_PDKS = (moscap_decap_n_all_pdks, moscap_decap_np_all_pdks, moscap_cap_n_all_pdks, moscap_cap_p_all_pdks)


def all_moscap_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
