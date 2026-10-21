"""Latch layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/latch_*.json``), each checked with DRC and
LVS. Cases: static C2MOS latches with and without reset, a master-slave flip-flop, a divide-by-two
flip-flop, a TSPC flip-flop and divide-by-two, a DICE latch, and NAND and NOR SR latches. The runner
is the comparator's (``flow.comp.layout``).

    uv run python -m flow latch.layout_latch
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, _all_pdks, _finish, _run

from .subckt import CASES, LatchParams, write_netlist


def _netlists(params: LatchParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The latch's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _latch(run_dir: Path, pdk: str, case: str) -> Path:
    """A latch case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"latch_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- each case in all six PDKs


def latch_latch_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "latch")


def latch_latch_rst_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "latch_rst")


def latch_flop_rst_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "flop_rst")


def latch_div2_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "div2")


def latch_sr_nand_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "sr_nand")


def latch_sr_nor_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "sr_nor")


def latch_flop_tspc_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "flop_tspc")


def latch_div2_tspc_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "div2_tspc")


def latch_latch_dice_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _latch, "latch_dice")


ALL_PDKS = (
    latch_latch_all_pdks,
    latch_latch_rst_all_pdks,
    latch_flop_rst_all_pdks,
    latch_div2_all_pdks,
    latch_sr_nand_all_pdks,
    latch_sr_nor_all_pdks,
    latch_flop_tspc_all_pdks,
    latch_div2_tspc_all_pdks,
    latch_latch_dice_all_pdks,
)


def all_latch_layouts(run_dir: Path) -> Path:
    """The nine ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
