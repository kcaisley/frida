"""Follower layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/follower_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: NMOS and PMOS source followers, and NMOS and PMOS flipped voltage followers. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.follower.layout follower_source_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

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


# ---- NMOS source follower


def follower_source_tsmc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc65", "source")


def follower_source_tsmc28(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc28", "source")


def follower_source_ihp130(run_dir: Path) -> Path:
    return _follower(run_dir, "ihp130", "source")


def follower_source_tower180(run_dir: Path) -> Path:
    return _follower(run_dir, "tower180", "source")


def follower_source_lf150(run_dir: Path) -> Path:
    return _follower(run_dir, "lf150", "source")


def follower_source_tpsc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tpsc65", "source")


# ---- PMOS source follower


def follower_source_pmos_tsmc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc65", "source_pmos")


def follower_source_pmos_tsmc28(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc28", "source_pmos")


def follower_source_pmos_ihp130(run_dir: Path) -> Path:
    return _follower(run_dir, "ihp130", "source_pmos")


def follower_source_pmos_tower180(run_dir: Path) -> Path:
    return _follower(run_dir, "tower180", "source_pmos")


def follower_source_pmos_lf150(run_dir: Path) -> Path:
    return _follower(run_dir, "lf150", "source_pmos")


def follower_source_pmos_tpsc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tpsc65", "source_pmos")


# ---- NMOS flipped voltage follower


def follower_flipped_tsmc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc65", "flipped")


def follower_flipped_tsmc28(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc28", "flipped")


def follower_flipped_ihp130(run_dir: Path) -> Path:
    return _follower(run_dir, "ihp130", "flipped")


def follower_flipped_tower180(run_dir: Path) -> Path:
    return _follower(run_dir, "tower180", "flipped")


def follower_flipped_lf150(run_dir: Path) -> Path:
    return _follower(run_dir, "lf150", "flipped")


def follower_flipped_tpsc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tpsc65", "flipped")


# ---- PMOS flipped voltage follower with an output sink


def follower_flipped_pmos_tsmc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc65", "flipped_pmos")


def follower_flipped_pmos_tsmc28(run_dir: Path) -> Path:
    return _follower(run_dir, "tsmc28", "flipped_pmos")


def follower_flipped_pmos_ihp130(run_dir: Path) -> Path:
    return _follower(run_dir, "ihp130", "flipped_pmos")


def follower_flipped_pmos_tower180(run_dir: Path) -> Path:
    return _follower(run_dir, "tower180", "flipped_pmos")


def follower_flipped_pmos_lf150(run_dir: Path) -> Path:
    return _follower(run_dir, "lf150", "flipped_pmos")


def follower_flipped_pmos_tpsc65(run_dir: Path) -> Path:
    return _follower(run_dir, "tpsc65", "flipped_pmos")


# ---- each case in all six PDKs


def follower_source_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            follower_source_tsmc65,
            follower_source_tsmc28,
            follower_source_ihp130,
            follower_source_tower180,
            follower_source_lf150,
            follower_source_tpsc65,
        ),
    )


def follower_source_pmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            follower_source_pmos_tsmc65,
            follower_source_pmos_tsmc28,
            follower_source_pmos_ihp130,
            follower_source_pmos_tower180,
            follower_source_pmos_lf150,
            follower_source_pmos_tpsc65,
        ),
    )


def follower_flipped_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            follower_flipped_tsmc65,
            follower_flipped_tsmc28,
            follower_flipped_ihp130,
            follower_flipped_tower180,
            follower_flipped_lf150,
            follower_flipped_tpsc65,
        ),
    )


def follower_flipped_pmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            follower_flipped_pmos_tsmc65,
            follower_flipped_pmos_tsmc28,
            follower_flipped_pmos_ihp130,
            follower_flipped_pmos_tower180,
            follower_flipped_pmos_lf150,
            follower_flipped_pmos_tpsc65,
        ),
    )


ALL_PDKS = (
    follower_source_all_pdks,
    follower_source_pmos_all_pdks,
    follower_flipped_all_pdks,
    follower_flipped_pmos_all_pdks,
)


def all_follower_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named follower layout target."""

    targets = {
        target.__name__: target
        for target in (
            follower_source_tsmc65,
            follower_source_tsmc28,
            follower_source_ihp130,
            follower_source_tower180,
            follower_source_lf150,
            follower_source_tpsc65,
            follower_source_pmos_tsmc65,
            follower_source_pmos_tsmc28,
            follower_source_pmos_ihp130,
            follower_source_pmos_tower180,
            follower_source_pmos_lf150,
            follower_source_pmos_tpsc65,
            follower_flipped_tsmc65,
            follower_flipped_tsmc28,
            follower_flipped_ihp130,
            follower_flipped_tower180,
            follower_flipped_lf150,
            follower_flipped_tpsc65,
            follower_flipped_pmos_tsmc65,
            follower_flipped_pmos_tsmc28,
            follower_flipped_pmos_ihp130,
            follower_flipped_pmos_tower180,
            follower_flipped_pmos_lf150,
            follower_flipped_pmos_tpsc65,
            *ALL_PDKS,
            all_follower_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available follower layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = (
        ROOT / "build" / "layout" / "follower" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
