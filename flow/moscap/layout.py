"""Mos capacitor layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/moscap_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: NMOS and complementary decaps, and NMOS and PMOS two-net capacitors. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.moscap.layout moscap_decap_n_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

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


# ---- two NMOS decap units


def moscap_decap_n_tsmc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc65", "decap_n")


def moscap_decap_n_tsmc28(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc28", "decap_n")


def moscap_decap_n_ihp130(run_dir: Path) -> Path:
    return _moscap(run_dir, "ihp130", "decap_n")


def moscap_decap_n_tower180(run_dir: Path) -> Path:
    return _moscap(run_dir, "tower180", "decap_n")


def moscap_decap_n_lf150(run_dir: Path) -> Path:
    return _moscap(run_dir, "lf150", "decap_n")


def moscap_decap_n_tpsc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tpsc65", "decap_n")


# ---- complementary decap


def moscap_decap_np_tsmc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc65", "decap_np")


def moscap_decap_np_tsmc28(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc28", "decap_np")


def moscap_decap_np_ihp130(run_dir: Path) -> Path:
    return _moscap(run_dir, "ihp130", "decap_np")


def moscap_decap_np_tower180(run_dir: Path) -> Path:
    return _moscap(run_dir, "tower180", "decap_np")


def moscap_decap_np_lf150(run_dir: Path) -> Path:
    return _moscap(run_dir, "lf150", "decap_np")


def moscap_decap_np_tpsc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tpsc65", "decap_np")


# ---- two-net NMOS capacitor


def moscap_cap_n_tsmc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc65", "cap_n")


def moscap_cap_n_tsmc28(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc28", "cap_n")


def moscap_cap_n_ihp130(run_dir: Path) -> Path:
    return _moscap(run_dir, "ihp130", "cap_n")


def moscap_cap_n_tower180(run_dir: Path) -> Path:
    return _moscap(run_dir, "tower180", "cap_n")


def moscap_cap_n_lf150(run_dir: Path) -> Path:
    return _moscap(run_dir, "lf150", "cap_n")


def moscap_cap_n_tpsc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tpsc65", "cap_n")


# ---- two-net PMOS capacitor


def moscap_cap_p_tsmc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc65", "cap_p")


def moscap_cap_p_tsmc28(run_dir: Path) -> Path:
    return _moscap(run_dir, "tsmc28", "cap_p")


def moscap_cap_p_ihp130(run_dir: Path) -> Path:
    return _moscap(run_dir, "ihp130", "cap_p")


def moscap_cap_p_tower180(run_dir: Path) -> Path:
    return _moscap(run_dir, "tower180", "cap_p")


def moscap_cap_p_lf150(run_dir: Path) -> Path:
    return _moscap(run_dir, "lf150", "cap_p")


def moscap_cap_p_tpsc65(run_dir: Path) -> Path:
    return _moscap(run_dir, "tpsc65", "cap_p")


# ---- each case in all six PDKs


def moscap_decap_n_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            moscap_decap_n_tsmc65,
            moscap_decap_n_tsmc28,
            moscap_decap_n_ihp130,
            moscap_decap_n_tower180,
            moscap_decap_n_lf150,
            moscap_decap_n_tpsc65,
        ),
    )


def moscap_decap_np_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            moscap_decap_np_tsmc65,
            moscap_decap_np_tsmc28,
            moscap_decap_np_ihp130,
            moscap_decap_np_tower180,
            moscap_decap_np_lf150,
            moscap_decap_np_tpsc65,
        ),
    )


def moscap_cap_n_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            moscap_cap_n_tsmc65,
            moscap_cap_n_tsmc28,
            moscap_cap_n_ihp130,
            moscap_cap_n_tower180,
            moscap_cap_n_lf150,
            moscap_cap_n_tpsc65,
        ),
    )


def moscap_cap_p_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            moscap_cap_p_tsmc65,
            moscap_cap_p_tsmc28,
            moscap_cap_p_ihp130,
            moscap_cap_p_tower180,
            moscap_cap_p_lf150,
            moscap_cap_p_tpsc65,
        ),
    )


ALL_PDKS = (moscap_decap_n_all_pdks, moscap_decap_np_all_pdks, moscap_cap_n_all_pdks, moscap_cap_p_all_pdks)


def all_moscap_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named MOS capacitor layout target."""

    targets = {
        target.__name__: target
        for target in (
            moscap_decap_n_tsmc65,
            moscap_decap_n_tsmc28,
            moscap_decap_n_ihp130,
            moscap_decap_n_tower180,
            moscap_decap_n_lf150,
            moscap_decap_n_tpsc65,
            moscap_decap_np_tsmc65,
            moscap_decap_np_tsmc28,
            moscap_decap_np_ihp130,
            moscap_decap_np_tower180,
            moscap_decap_np_lf150,
            moscap_decap_np_tpsc65,
            moscap_cap_n_tsmc65,
            moscap_cap_n_tsmc28,
            moscap_cap_n_ihp130,
            moscap_cap_n_tower180,
            moscap_cap_n_lf150,
            moscap_cap_n_tpsc65,
            moscap_cap_p_tsmc65,
            moscap_cap_p_tsmc28,
            moscap_cap_p_ihp130,
            moscap_cap_p_tower180,
            moscap_cap_p_lf150,
            moscap_cap_p_tpsc65,
            *ALL_PDKS,
            all_moscap_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available MOS capacitor layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "moscap" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
