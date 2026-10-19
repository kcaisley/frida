"""Schmitt trigger layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/schmitt_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: the inverting trigger with
normal and with stronger feedback, and the buffer. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow.schmitt.layout schmitt_inv_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, SchmittParams, write_netlist


def _netlists(params: SchmittParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The trigger's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _schmitt(run_dir: Path, pdk: str, case: str) -> Path:
    """A trigger case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"schmitt_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- Inverting trigger


def schmitt_inv_tsmc65(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tsmc65", "inv")


def schmitt_inv_tsmc28(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tsmc28", "inv")


def schmitt_inv_ihp130(run_dir: Path) -> Path:
    return _schmitt(run_dir, "ihp130", "inv")


def schmitt_inv_tower180(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tower180", "inv")


def schmitt_inv_lf150(run_dir: Path) -> Path:
    return _schmitt(run_dir, "lf150", "inv")


def schmitt_inv_tpsc65(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tpsc65", "inv")


# ---- Inverting trigger, stronger feedback


def schmitt_inv_wide_tsmc65(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tsmc65", "inv_wide")


def schmitt_inv_wide_tsmc28(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tsmc28", "inv_wide")


def schmitt_inv_wide_ihp130(run_dir: Path) -> Path:
    return _schmitt(run_dir, "ihp130", "inv_wide")


def schmitt_inv_wide_tower180(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tower180", "inv_wide")


def schmitt_inv_wide_lf150(run_dir: Path) -> Path:
    return _schmitt(run_dir, "lf150", "inv_wide")


def schmitt_inv_wide_tpsc65(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tpsc65", "inv_wide")


# ---- Buffer


def schmitt_buffer_tsmc65(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tsmc65", "buffer")


def schmitt_buffer_tsmc28(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tsmc28", "buffer")


def schmitt_buffer_ihp130(run_dir: Path) -> Path:
    return _schmitt(run_dir, "ihp130", "buffer")


def schmitt_buffer_tower180(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tower180", "buffer")


def schmitt_buffer_lf150(run_dir: Path) -> Path:
    return _schmitt(run_dir, "lf150", "buffer")


def schmitt_buffer_tpsc65(run_dir: Path) -> Path:
    return _schmitt(run_dir, "tpsc65", "buffer")


def schmitt_inv_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            schmitt_inv_tsmc65,
            schmitt_inv_tsmc28,
            schmitt_inv_ihp130,
            schmitt_inv_tower180,
            schmitt_inv_lf150,
            schmitt_inv_tpsc65,
        ),
    )


def schmitt_inv_wide_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            schmitt_inv_wide_tsmc65,
            schmitt_inv_wide_tsmc28,
            schmitt_inv_wide_ihp130,
            schmitt_inv_wide_tower180,
            schmitt_inv_wide_lf150,
            schmitt_inv_wide_tpsc65,
        ),
    )


def schmitt_buffer_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            schmitt_buffer_tsmc65,
            schmitt_buffer_tsmc28,
            schmitt_buffer_ihp130,
            schmitt_buffer_tower180,
            schmitt_buffer_lf150,
            schmitt_buffer_tpsc65,
        ),
    )


ALL_PDKS = (
    schmitt_inv_all_pdks,
    schmitt_inv_wide_all_pdks,
    schmitt_buffer_all_pdks,
)


def all_schmitt_layouts(run_dir: Path) -> Path:
    """The three ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named Schmitt trigger layout target."""

    targets = {
        target.__name__: target
        for target in (
            schmitt_inv_tsmc65,
            schmitt_inv_tsmc28,
            schmitt_inv_ihp130,
            schmitt_inv_tower180,
            schmitt_inv_lf150,
            schmitt_inv_tpsc65,
            schmitt_inv_wide_tsmc65,
            schmitt_inv_wide_tsmc28,
            schmitt_inv_wide_ihp130,
            schmitt_inv_wide_tower180,
            schmitt_inv_wide_lf150,
            schmitt_inv_wide_tpsc65,
            schmitt_buffer_tsmc65,
            schmitt_buffer_tsmc28,
            schmitt_buffer_ihp130,
            schmitt_buffer_tower180,
            schmitt_buffer_lf150,
            schmitt_buffer_tpsc65,
            *ALL_PDKS,
            all_schmitt_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available Schmitt trigger layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = (
        ROOT / "build" / "layout" / "schmitt" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
