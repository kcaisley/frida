"""Ring amplifier layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/ringamp_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: the single-ended ring amplifier and one with a stronger output stage. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.ringamp.layout ringamp_se_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, RingampParams, write_netlist


def _netlists(params: RingampParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The ring amplifier's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _ringamp(run_dir: Path, pdk: str, case: str) -> Path:
    """A ring amplifier case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"ringamp_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- single-ended ring amplifier


def ringamp_se_tsmc65(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tsmc65", "se")


def ringamp_se_tsmc28(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tsmc28", "se")


def ringamp_se_ihp130(run_dir: Path) -> Path:
    return _ringamp(run_dir, "ihp130", "se")


def ringamp_se_tower180(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tower180", "se")


def ringamp_se_lf150(run_dir: Path) -> Path:
    return _ringamp(run_dir, "lf150", "se")


def ringamp_se_tpsc65(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tpsc65", "se")


# ---- stronger output stage


def ringamp_se_strong_tsmc65(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tsmc65", "se_strong")


def ringamp_se_strong_tsmc28(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tsmc28", "se_strong")


def ringamp_se_strong_ihp130(run_dir: Path) -> Path:
    return _ringamp(run_dir, "ihp130", "se_strong")


def ringamp_se_strong_tower180(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tower180", "se_strong")


def ringamp_se_strong_lf150(run_dir: Path) -> Path:
    return _ringamp(run_dir, "lf150", "se_strong")


def ringamp_se_strong_tpsc65(run_dir: Path) -> Path:
    return _ringamp(run_dir, "tpsc65", "se_strong")


# ---- each case in all six PDKs


def ringamp_se_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ringamp_se_tsmc65,
            ringamp_se_tsmc28,
            ringamp_se_ihp130,
            ringamp_se_tower180,
            ringamp_se_lf150,
            ringamp_se_tpsc65,
        ),
    )


def ringamp_se_strong_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ringamp_se_strong_tsmc65,
            ringamp_se_strong_tsmc28,
            ringamp_se_strong_ihp130,
            ringamp_se_strong_tower180,
            ringamp_se_strong_lf150,
            ringamp_se_strong_tpsc65,
        ),
    )


ALL_PDKS = (ringamp_se_all_pdks, ringamp_se_strong_all_pdks)


def all_ringamp_layouts(run_dir: Path) -> Path:
    """The two ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named ring amplifier layout target."""

    targets = {
        target.__name__: target
        for target in (
            ringamp_se_tsmc65,
            ringamp_se_tsmc28,
            ringamp_se_ihp130,
            ringamp_se_tower180,
            ringamp_se_lf150,
            ringamp_se_tpsc65,
            ringamp_se_strong_tsmc65,
            ringamp_se_strong_tsmc28,
            ringamp_se_strong_ihp130,
            ringamp_se_strong_tower180,
            ringamp_se_strong_lf150,
            ringamp_se_strong_tpsc65,
            *ALL_PDKS,
            all_ringamp_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available ring amplifier layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = (
        ROOT / "build" / "layout" / "ringamp" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
