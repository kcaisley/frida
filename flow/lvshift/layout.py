"""Level shifter layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/lvshift_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: the cross-coupled core, with an input inverter and reset, and with output inverters. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.lvshift.layout lvshift_core_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, LvShiftParams, write_netlist


def _netlists(params: LvShiftParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The level shifter's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _lvshift(run_dir: Path, pdk: str, case: str) -> Path:
    """A level shifter case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"lvshift_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- cross-coupled core


def lvshift_core_tsmc65(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tsmc65", "core")


def lvshift_core_tsmc28(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tsmc28", "core")


def lvshift_core_ihp130(run_dir: Path) -> Path:
    return _lvshift(run_dir, "ihp130", "core")


def lvshift_core_tower180(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tower180", "core")


def lvshift_core_lf150(run_dir: Path) -> Path:
    return _lvshift(run_dir, "lf150", "core")


def lvshift_core_tpsc65(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tpsc65", "core")


# ---- input inverter and reset


def lvshift_single_rst_tsmc65(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tsmc65", "single_rst")


def lvshift_single_rst_tsmc28(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tsmc28", "single_rst")


def lvshift_single_rst_ihp130(run_dir: Path) -> Path:
    return _lvshift(run_dir, "ihp130", "single_rst")


def lvshift_single_rst_tower180(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tower180", "single_rst")


def lvshift_single_rst_lf150(run_dir: Path) -> Path:
    return _lvshift(run_dir, "lf150", "single_rst")


def lvshift_single_rst_tpsc65(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tpsc65", "single_rst")


# ---- input inverter and output inverters


def lvshift_buffered_tsmc65(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tsmc65", "buffered")


def lvshift_buffered_tsmc28(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tsmc28", "buffered")


def lvshift_buffered_ihp130(run_dir: Path) -> Path:
    return _lvshift(run_dir, "ihp130", "buffered")


def lvshift_buffered_tower180(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tower180", "buffered")


def lvshift_buffered_lf150(run_dir: Path) -> Path:
    return _lvshift(run_dir, "lf150", "buffered")


def lvshift_buffered_tpsc65(run_dir: Path) -> Path:
    return _lvshift(run_dir, "tpsc65", "buffered")


# ---- each case in all six PDKs


def lvshift_core_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            lvshift_core_tsmc65,
            lvshift_core_tsmc28,
            lvshift_core_ihp130,
            lvshift_core_tower180,
            lvshift_core_lf150,
            lvshift_core_tpsc65,
        ),
    )


def lvshift_single_rst_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            lvshift_single_rst_tsmc65,
            lvshift_single_rst_tsmc28,
            lvshift_single_rst_ihp130,
            lvshift_single_rst_tower180,
            lvshift_single_rst_lf150,
            lvshift_single_rst_tpsc65,
        ),
    )


def lvshift_buffered_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            lvshift_buffered_tsmc65,
            lvshift_buffered_tsmc28,
            lvshift_buffered_ihp130,
            lvshift_buffered_tower180,
            lvshift_buffered_lf150,
            lvshift_buffered_tpsc65,
        ),
    )


ALL_PDKS = (lvshift_core_all_pdks, lvshift_single_rst_all_pdks, lvshift_buffered_all_pdks)


def all_lvshift_layouts(run_dir: Path) -> Path:
    """The three ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named level shifter layout target."""

    targets = {
        target.__name__: target
        for target in (
            lvshift_core_tsmc65,
            lvshift_core_tsmc28,
            lvshift_core_ihp130,
            lvshift_core_tower180,
            lvshift_core_lf150,
            lvshift_core_tpsc65,
            lvshift_single_rst_tsmc65,
            lvshift_single_rst_tsmc28,
            lvshift_single_rst_ihp130,
            lvshift_single_rst_tower180,
            lvshift_single_rst_lf150,
            lvshift_single_rst_tpsc65,
            lvshift_buffered_tsmc65,
            lvshift_buffered_tsmc28,
            lvshift_buffered_ihp130,
            lvshift_buffered_tower180,
            lvshift_buffered_lf150,
            lvshift_buffered_tpsc65,
            *ALL_PDKS,
            all_lvshift_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available level shifter layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = (
        ROOT / "build" / "layout" / "lvshift" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
