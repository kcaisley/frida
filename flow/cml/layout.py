"""Cml layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/cml_*.json``), each checked with DRC
and LVS. Cases: NMOS- and PMOS-input buffers, a latch, a divide-by-two, and an XOR. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow cml.layout_buffer
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, CmlParams, write_netlist


def _netlists(params: CmlParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The CML's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _cml(run_dir: Path, pdk: str, case: str) -> Path:
    """A CML case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"cml_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def cml_buffer_all_pdks(run_dir: Path) -> Path:
    """NMOS-input buffer."""
    return _all_pdks(run_dir, _cml, "buffer")


def cml_buffer_pmos_all_pdks(run_dir: Path) -> Path:
    """PMOS-input buffer."""
    return _all_pdks(run_dir, _cml, "buffer_pmos")


def cml_latch_all_pdks(run_dir: Path) -> Path:
    """Latch."""
    return _all_pdks(run_dir, _cml, "latch")


def cml_divider_all_pdks(run_dir: Path) -> Path:
    """Divide-by-two."""
    return _all_pdks(run_dir, _cml, "divider")


def cml_xor_all_pdks(run_dir: Path) -> Path:
    """XOR."""
    return _all_pdks(run_dir, _cml, "xor")


ALL_PDKS = (cml_buffer_all_pdks, cml_buffer_pmos_all_pdks, cml_latch_all_pdks, cml_divider_all_pdks, cml_xor_all_pdks)


def all_cml_layouts(run_dir: Path) -> Path:
    """The five ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
