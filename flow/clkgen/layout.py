"""Clock generator layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

A ``*_all_pdks`` function lays out one case in all six PDKs by ALIGN from its hand-written floorplan
(``design/layout/clkgen_*.json``), each checked with DRC and LVS. Cases: non-overlapping clocks, a
rising-edge pulse, and a clock gate. The runner is the shared layout step's (``flow.layout.step``).

    uv run python -m flow clkgen.layout_nonoverlap
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.layout.step import FLOORPLANS, all_pdks, finish, signed_off

from .subckt import CASES, ClkgenParams, write_netlist


def _netlists(params: ClkgenParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The clock generator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _clkgen(run_dir: Path, pdk: str, case: str) -> Path:
    """A clock generator case: its netlist into ``run_dir/netlist/``, then ALIGN as its floorplan
    places it."""

    name = f"clkgen_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return signed_off(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def clkgen_nonoverlap_all_pdks(run_dir: Path) -> Path:
    """Non-overlapping clocks."""
    return all_pdks(run_dir, _clkgen, "nonoverlap")


def clkgen_pulse_all_pdks(run_dir: Path) -> Path:
    """Rising-edge pulse."""
    return all_pdks(run_dir, _clkgen, "pulse")


def clkgen_gate_all_pdks(run_dir: Path) -> Path:
    """Clock gate."""
    return all_pdks(run_dir, _clkgen, "gate")


ALL_PDKS = (clkgen_nonoverlap_all_pdks, clkgen_pulse_all_pdks, clkgen_gate_all_pdks)


def all_clkgen_layouts(run_dir: Path) -> Path:
    """The three ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return finish(run_dir, {}, failures)
