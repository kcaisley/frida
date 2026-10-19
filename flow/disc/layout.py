"""Discriminator layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/disc_*.json``), each checked with DRC and
LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: NMOS and PMOS input pairs, each
with a current-mirror load and with hysteresis. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow.disc.layout disc_nmos_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, DiscParams, write_netlist


def _netlists(params: DiscParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The discriminator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _disc(run_dir: Path, pdk: str, case: str) -> Path:
    """A discriminator case: its netlist into ``run_dir/netlist/``, then the three tools as its
    floorplan places it."""

    name = f"disc_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- NMOS input pair, current-mirror load


def disc_nmos_tsmc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc65", "nmos")


def disc_nmos_tsmc28(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc28", "nmos")


def disc_nmos_ihp130(run_dir: Path) -> Path:
    return _disc(run_dir, "ihp130", "nmos")


def disc_nmos_tower180(run_dir: Path) -> Path:
    return _disc(run_dir, "tower180", "nmos")


def disc_nmos_lf150(run_dir: Path) -> Path:
    return _disc(run_dir, "lf150", "nmos")


def disc_nmos_tpsc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tpsc65", "nmos")


# ---- NMOS input pair, hysteresis


def disc_nmos_hyst_tsmc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc65", "nmos_hyst")


def disc_nmos_hyst_tsmc28(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc28", "nmos_hyst")


def disc_nmos_hyst_ihp130(run_dir: Path) -> Path:
    return _disc(run_dir, "ihp130", "nmos_hyst")


def disc_nmos_hyst_tower180(run_dir: Path) -> Path:
    return _disc(run_dir, "tower180", "nmos_hyst")


def disc_nmos_hyst_lf150(run_dir: Path) -> Path:
    return _disc(run_dir, "lf150", "nmos_hyst")


def disc_nmos_hyst_tpsc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tpsc65", "nmos_hyst")


# ---- PMOS input pair, current-mirror load


def disc_pmos_tsmc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc65", "pmos")


def disc_pmos_tsmc28(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc28", "pmos")


def disc_pmos_ihp130(run_dir: Path) -> Path:
    return _disc(run_dir, "ihp130", "pmos")


def disc_pmos_tower180(run_dir: Path) -> Path:
    return _disc(run_dir, "tower180", "pmos")


def disc_pmos_lf150(run_dir: Path) -> Path:
    return _disc(run_dir, "lf150", "pmos")


def disc_pmos_tpsc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tpsc65", "pmos")


# ---- PMOS input pair, hysteresis


def disc_pmos_hyst_tsmc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc65", "pmos_hyst")


def disc_pmos_hyst_tsmc28(run_dir: Path) -> Path:
    return _disc(run_dir, "tsmc28", "pmos_hyst")


def disc_pmos_hyst_ihp130(run_dir: Path) -> Path:
    return _disc(run_dir, "ihp130", "pmos_hyst")


def disc_pmos_hyst_tower180(run_dir: Path) -> Path:
    return _disc(run_dir, "tower180", "pmos_hyst")


def disc_pmos_hyst_lf150(run_dir: Path) -> Path:
    return _disc(run_dir, "lf150", "pmos_hyst")


def disc_pmos_hyst_tpsc65(run_dir: Path) -> Path:
    return _disc(run_dir, "tpsc65", "pmos_hyst")


def disc_nmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            disc_nmos_tsmc65,
            disc_nmos_tsmc28,
            disc_nmos_ihp130,
            disc_nmos_tower180,
            disc_nmos_lf150,
            disc_nmos_tpsc65,
        ),
    )


def disc_nmos_hyst_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            disc_nmos_hyst_tsmc65,
            disc_nmos_hyst_tsmc28,
            disc_nmos_hyst_ihp130,
            disc_nmos_hyst_tower180,
            disc_nmos_hyst_lf150,
            disc_nmos_hyst_tpsc65,
        ),
    )


def disc_pmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            disc_pmos_tsmc65,
            disc_pmos_tsmc28,
            disc_pmos_ihp130,
            disc_pmos_tower180,
            disc_pmos_lf150,
            disc_pmos_tpsc65,
        ),
    )


def disc_pmos_hyst_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            disc_pmos_hyst_tsmc65,
            disc_pmos_hyst_tsmc28,
            disc_pmos_hyst_ihp130,
            disc_pmos_hyst_tower180,
            disc_pmos_hyst_lf150,
            disc_pmos_hyst_tpsc65,
        ),
    )


ALL_PDKS = (
    disc_nmos_all_pdks,
    disc_nmos_hyst_all_pdks,
    disc_pmos_all_pdks,
    disc_pmos_hyst_all_pdks,
)


def all_disc_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named discriminator layout target."""

    targets = {
        target.__name__: target
        for target in (
            disc_nmos_tsmc65,
            disc_nmos_tsmc28,
            disc_nmos_ihp130,
            disc_nmos_tower180,
            disc_nmos_lf150,
            disc_nmos_tpsc65,
            disc_nmos_hyst_tsmc65,
            disc_nmos_hyst_tsmc28,
            disc_nmos_hyst_ihp130,
            disc_nmos_hyst_tower180,
            disc_nmos_hyst_lf150,
            disc_nmos_hyst_tpsc65,
            disc_pmos_tsmc65,
            disc_pmos_tsmc28,
            disc_pmos_ihp130,
            disc_pmos_tower180,
            disc_pmos_lf150,
            disc_pmos_tpsc65,
            disc_pmos_hyst_tsmc65,
            disc_pmos_hyst_tsmc28,
            disc_pmos_hyst_ihp130,
            disc_pmos_hyst_tower180,
            disc_pmos_hyst_lf150,
            disc_pmos_hyst_tpsc65,
            *ALL_PDKS,
            all_disc_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available discriminator layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "disc" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
