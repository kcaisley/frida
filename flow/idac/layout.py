"""Current source layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/idac_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: switched NMOS units, a cascoded steered PMOS unit, steered NMOS units, and a PMOS bias mirror. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.idac.layout idac_nmos_switched_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, IdacParams, write_netlist


def _netlists(params: IdacParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The current source's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _idac(run_dir: Path, pdk: str, case: str) -> Path:
    """A current source case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"idac_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- two switched NMOS units


def idac_nmos_switched_tsmc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc65", "nmos_switched")


def idac_nmos_switched_tsmc28(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc28", "nmos_switched")


def idac_nmos_switched_ihp130(run_dir: Path) -> Path:
    return _idac(run_dir, "ihp130", "nmos_switched")


def idac_nmos_switched_tower180(run_dir: Path) -> Path:
    return _idac(run_dir, "tower180", "nmos_switched")


def idac_nmos_switched_lf150(run_dir: Path) -> Path:
    return _idac(run_dir, "lf150", "nmos_switched")


def idac_nmos_switched_tpsc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tpsc65", "nmos_switched")


# ---- cascoded steered PMOS unit


def idac_pmos_steer_cas_tsmc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc65", "pmos_steer_cas")


def idac_pmos_steer_cas_tsmc28(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc28", "pmos_steer_cas")


def idac_pmos_steer_cas_ihp130(run_dir: Path) -> Path:
    return _idac(run_dir, "ihp130", "pmos_steer_cas")


def idac_pmos_steer_cas_tower180(run_dir: Path) -> Path:
    return _idac(run_dir, "tower180", "pmos_steer_cas")


def idac_pmos_steer_cas_lf150(run_dir: Path) -> Path:
    return _idac(run_dir, "lf150", "pmos_steer_cas")


def idac_pmos_steer_cas_tpsc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tpsc65", "pmos_steer_cas")


# ---- four steered NMOS units


def idac_nmos_steer_tsmc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc65", "nmos_steer")


def idac_nmos_steer_tsmc28(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc28", "nmos_steer")


def idac_nmos_steer_ihp130(run_dir: Path) -> Path:
    return _idac(run_dir, "ihp130", "nmos_steer")


def idac_nmos_steer_tower180(run_dir: Path) -> Path:
    return _idac(run_dir, "tower180", "nmos_steer")


def idac_nmos_steer_lf150(run_dir: Path) -> Path:
    return _idac(run_dir, "lf150", "nmos_steer")


def idac_nmos_steer_tpsc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tpsc65", "nmos_steer")


# ---- PMOS bias mirror


def idac_pmos_mirror_tsmc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc65", "pmos_mirror")


def idac_pmos_mirror_tsmc28(run_dir: Path) -> Path:
    return _idac(run_dir, "tsmc28", "pmos_mirror")


def idac_pmos_mirror_ihp130(run_dir: Path) -> Path:
    return _idac(run_dir, "ihp130", "pmos_mirror")


def idac_pmos_mirror_tower180(run_dir: Path) -> Path:
    return _idac(run_dir, "tower180", "pmos_mirror")


def idac_pmos_mirror_lf150(run_dir: Path) -> Path:
    return _idac(run_dir, "lf150", "pmos_mirror")


def idac_pmos_mirror_tpsc65(run_dir: Path) -> Path:
    return _idac(run_dir, "tpsc65", "pmos_mirror")


# ---- each case in all six PDKs


def idac_nmos_switched_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            idac_nmos_switched_tsmc65,
            idac_nmos_switched_tsmc28,
            idac_nmos_switched_ihp130,
            idac_nmos_switched_tower180,
            idac_nmos_switched_lf150,
            idac_nmos_switched_tpsc65,
        ),
    )


def idac_pmos_steer_cas_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            idac_pmos_steer_cas_tsmc65,
            idac_pmos_steer_cas_tsmc28,
            idac_pmos_steer_cas_ihp130,
            idac_pmos_steer_cas_tower180,
            idac_pmos_steer_cas_lf150,
            idac_pmos_steer_cas_tpsc65,
        ),
    )


def idac_nmos_steer_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            idac_nmos_steer_tsmc65,
            idac_nmos_steer_tsmc28,
            idac_nmos_steer_ihp130,
            idac_nmos_steer_tower180,
            idac_nmos_steer_lf150,
            idac_nmos_steer_tpsc65,
        ),
    )


def idac_pmos_mirror_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            idac_pmos_mirror_tsmc65,
            idac_pmos_mirror_tsmc28,
            idac_pmos_mirror_ihp130,
            idac_pmos_mirror_tower180,
            idac_pmos_mirror_lf150,
            idac_pmos_mirror_tpsc65,
        ),
    )


ALL_PDKS = (
    idac_nmos_switched_all_pdks,
    idac_pmos_steer_cas_all_pdks,
    idac_nmos_steer_all_pdks,
    idac_pmos_mirror_all_pdks,
)


def all_idac_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named current source layout target."""

    targets = {
        target.__name__: target
        for target in (
            idac_nmos_switched_tsmc65,
            idac_nmos_switched_tsmc28,
            idac_nmos_switched_ihp130,
            idac_nmos_switched_tower180,
            idac_nmos_switched_lf150,
            idac_nmos_switched_tpsc65,
            idac_pmos_steer_cas_tsmc65,
            idac_pmos_steer_cas_tsmc28,
            idac_pmos_steer_cas_ihp130,
            idac_pmos_steer_cas_tower180,
            idac_pmos_steer_cas_lf150,
            idac_pmos_steer_cas_tpsc65,
            idac_nmos_steer_tsmc65,
            idac_nmos_steer_tsmc28,
            idac_nmos_steer_ihp130,
            idac_nmos_steer_tower180,
            idac_nmos_steer_lf150,
            idac_nmos_steer_tpsc65,
            idac_pmos_mirror_tsmc65,
            idac_pmos_mirror_tsmc28,
            idac_pmos_mirror_ihp130,
            idac_pmos_mirror_tower180,
            idac_pmos_mirror_lf150,
            idac_pmos_mirror_tpsc65,
            *ALL_PDKS,
            all_idac_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available current source layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "idac" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
