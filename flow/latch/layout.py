"""Latch layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/latch_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: static C2MOS latches with and without reset, a master-slave flip-flop, a divide-by-two flip-flop, and NAND and NOR SR latches. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.latch.layout latch_latch_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

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


# ---- static C2MOS latch


def latch_latch_tsmc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc65", "latch")


def latch_latch_tsmc28(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc28", "latch")


def latch_latch_ihp130(run_dir: Path) -> Path:
    return _latch(run_dir, "ihp130", "latch")


def latch_latch_tower180(run_dir: Path) -> Path:
    return _latch(run_dir, "tower180", "latch")


def latch_latch_lf150(run_dir: Path) -> Path:
    return _latch(run_dir, "lf150", "latch")


def latch_latch_tpsc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tpsc65", "latch")


# ---- static latch with reset


def latch_latch_rst_tsmc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc65", "latch_rst")


def latch_latch_rst_tsmc28(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc28", "latch_rst")


def latch_latch_rst_ihp130(run_dir: Path) -> Path:
    return _latch(run_dir, "ihp130", "latch_rst")


def latch_latch_rst_tower180(run_dir: Path) -> Path:
    return _latch(run_dir, "tower180", "latch_rst")


def latch_latch_rst_lf150(run_dir: Path) -> Path:
    return _latch(run_dir, "lf150", "latch_rst")


def latch_latch_rst_tpsc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tpsc65", "latch_rst")


# ---- master-slave flip-flop with reset


def latch_flop_rst_tsmc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc65", "flop_rst")


def latch_flop_rst_tsmc28(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc28", "flop_rst")


def latch_flop_rst_ihp130(run_dir: Path) -> Path:
    return _latch(run_dir, "ihp130", "flop_rst")


def latch_flop_rst_tower180(run_dir: Path) -> Path:
    return _latch(run_dir, "tower180", "flop_rst")


def latch_flop_rst_lf150(run_dir: Path) -> Path:
    return _latch(run_dir, "lf150", "flop_rst")


def latch_flop_rst_tpsc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tpsc65", "flop_rst")


# ---- divide-by-two flip-flop


def latch_div2_tsmc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc65", "div2")


def latch_div2_tsmc28(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc28", "div2")


def latch_div2_ihp130(run_dir: Path) -> Path:
    return _latch(run_dir, "ihp130", "div2")


def latch_div2_tower180(run_dir: Path) -> Path:
    return _latch(run_dir, "tower180", "div2")


def latch_div2_lf150(run_dir: Path) -> Path:
    return _latch(run_dir, "lf150", "div2")


def latch_div2_tpsc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tpsc65", "div2")


# ---- NAND SR latch


def latch_sr_nand_tsmc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc65", "sr_nand")


def latch_sr_nand_tsmc28(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc28", "sr_nand")


def latch_sr_nand_ihp130(run_dir: Path) -> Path:
    return _latch(run_dir, "ihp130", "sr_nand")


def latch_sr_nand_tower180(run_dir: Path) -> Path:
    return _latch(run_dir, "tower180", "sr_nand")


def latch_sr_nand_lf150(run_dir: Path) -> Path:
    return _latch(run_dir, "lf150", "sr_nand")


def latch_sr_nand_tpsc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tpsc65", "sr_nand")


# ---- NOR SR latch


def latch_sr_nor_tsmc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc65", "sr_nor")


def latch_sr_nor_tsmc28(run_dir: Path) -> Path:
    return _latch(run_dir, "tsmc28", "sr_nor")


def latch_sr_nor_ihp130(run_dir: Path) -> Path:
    return _latch(run_dir, "ihp130", "sr_nor")


def latch_sr_nor_tower180(run_dir: Path) -> Path:
    return _latch(run_dir, "tower180", "sr_nor")


def latch_sr_nor_lf150(run_dir: Path) -> Path:
    return _latch(run_dir, "lf150", "sr_nor")


def latch_sr_nor_tpsc65(run_dir: Path) -> Path:
    return _latch(run_dir, "tpsc65", "sr_nor")


# ---- each case in all six PDKs


def latch_latch_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            latch_latch_tsmc65,
            latch_latch_tsmc28,
            latch_latch_ihp130,
            latch_latch_tower180,
            latch_latch_lf150,
            latch_latch_tpsc65,
        ),
    )


def latch_latch_rst_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            latch_latch_rst_tsmc65,
            latch_latch_rst_tsmc28,
            latch_latch_rst_ihp130,
            latch_latch_rst_tower180,
            latch_latch_rst_lf150,
            latch_latch_rst_tpsc65,
        ),
    )


def latch_flop_rst_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            latch_flop_rst_tsmc65,
            latch_flop_rst_tsmc28,
            latch_flop_rst_ihp130,
            latch_flop_rst_tower180,
            latch_flop_rst_lf150,
            latch_flop_rst_tpsc65,
        ),
    )


def latch_div2_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            latch_div2_tsmc65,
            latch_div2_tsmc28,
            latch_div2_ihp130,
            latch_div2_tower180,
            latch_div2_lf150,
            latch_div2_tpsc65,
        ),
    )


def latch_sr_nand_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            latch_sr_nand_tsmc65,
            latch_sr_nand_tsmc28,
            latch_sr_nand_ihp130,
            latch_sr_nand_tower180,
            latch_sr_nand_lf150,
            latch_sr_nand_tpsc65,
        ),
    )


def latch_sr_nor_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            latch_sr_nor_tsmc65,
            latch_sr_nor_tsmc28,
            latch_sr_nor_ihp130,
            latch_sr_nor_tower180,
            latch_sr_nor_lf150,
            latch_sr_nor_tpsc65,
        ),
    )


ALL_PDKS = (
    latch_latch_all_pdks,
    latch_latch_rst_all_pdks,
    latch_flop_rst_all_pdks,
    latch_div2_all_pdks,
    latch_sr_nand_all_pdks,
    latch_sr_nor_all_pdks,
)


def all_latch_layouts(run_dir: Path) -> Path:
    """The six ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named latch layout target."""

    targets = {
        target.__name__: target
        for target in (
            latch_latch_tsmc65,
            latch_latch_tsmc28,
            latch_latch_ihp130,
            latch_latch_tower180,
            latch_latch_lf150,
            latch_latch_tpsc65,
            latch_latch_rst_tsmc65,
            latch_latch_rst_tsmc28,
            latch_latch_rst_ihp130,
            latch_latch_rst_tower180,
            latch_latch_rst_lf150,
            latch_latch_rst_tpsc65,
            latch_flop_rst_tsmc65,
            latch_flop_rst_tsmc28,
            latch_flop_rst_ihp130,
            latch_flop_rst_tower180,
            latch_flop_rst_lf150,
            latch_flop_rst_tpsc65,
            latch_div2_tsmc65,
            latch_div2_tsmc28,
            latch_div2_ihp130,
            latch_div2_tower180,
            latch_div2_lf150,
            latch_div2_tpsc65,
            latch_sr_nand_tsmc65,
            latch_sr_nand_tsmc28,
            latch_sr_nand_ihp130,
            latch_sr_nand_tower180,
            latch_sr_nand_lf150,
            latch_sr_nand_tpsc65,
            latch_sr_nor_tsmc65,
            latch_sr_nor_tsmc28,
            latch_sr_nor_ihp130,
            latch_sr_nor_tower180,
            latch_sr_nor_lf150,
            latch_sr_nor_tpsc65,
            *ALL_PDKS,
            all_latch_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available latch layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "latch" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
