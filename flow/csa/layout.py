"""Charge-sensitive amplifier layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/csa_*.json``), each checked with DRC and
LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: NMOS and PMOS input with
Krummenacher feedback, NMOS input with continuous and with reset feedback. The row cells draw MOS
only: the layout's netlist leaves the feedback capacitor out. The runner is the comparator's
(``flow.comp.layout``).

    uv run python -m flow.csa.layout csa_krum_tsmc65
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime
from importlib import import_module
from pathlib import Path

from hdl21.prefix import f

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, CsaParams, write_netlist


def _netlists(params: CsaParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The amplifier's netlist in ``pdk``, without its feedback capacitor; the file stem names the
    subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(dataclasses.replace(params, cf=0 * f), out_dir / f"{name}.sp", logic)


def _csa(run_dir: Path, pdk: str, case: str) -> Path:
    """An amplifier case: its netlist into ``run_dir/netlist/``, then the three tools as its
    floorplan places it."""

    name = f"csa_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- NMOS input, Krummenacher feedback


def csa_krum_tsmc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc65", "krum")


def csa_krum_tsmc28(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc28", "krum")


def csa_krum_ihp130(run_dir: Path) -> Path:
    return _csa(run_dir, "ihp130", "krum")


def csa_krum_tower180(run_dir: Path) -> Path:
    return _csa(run_dir, "tower180", "krum")


def csa_krum_lf150(run_dir: Path) -> Path:
    return _csa(run_dir, "lf150", "krum")


def csa_krum_tpsc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tpsc65", "krum")


# ---- PMOS input, Krummenacher feedback


def csa_krum_pmos_tsmc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc65", "krum_pmos")


def csa_krum_pmos_tsmc28(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc28", "krum_pmos")


def csa_krum_pmos_ihp130(run_dir: Path) -> Path:
    return _csa(run_dir, "ihp130", "krum_pmos")


def csa_krum_pmos_tower180(run_dir: Path) -> Path:
    return _csa(run_dir, "tower180", "krum_pmos")


def csa_krum_pmos_lf150(run_dir: Path) -> Path:
    return _csa(run_dir, "lf150", "krum_pmos")


def csa_krum_pmos_tpsc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tpsc65", "krum_pmos")


# ---- NMOS input, continuous feedback


def csa_continuous_tsmc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc65", "continuous")


def csa_continuous_tsmc28(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc28", "continuous")


def csa_continuous_ihp130(run_dir: Path) -> Path:
    return _csa(run_dir, "ihp130", "continuous")


def csa_continuous_tower180(run_dir: Path) -> Path:
    return _csa(run_dir, "tower180", "continuous")


def csa_continuous_lf150(run_dir: Path) -> Path:
    return _csa(run_dir, "lf150", "continuous")


def csa_continuous_tpsc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tpsc65", "continuous")


# ---- NMOS input, reset feedback


def csa_reset_tsmc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc65", "reset")


def csa_reset_tsmc28(run_dir: Path) -> Path:
    return _csa(run_dir, "tsmc28", "reset")


def csa_reset_ihp130(run_dir: Path) -> Path:
    return _csa(run_dir, "ihp130", "reset")


def csa_reset_tower180(run_dir: Path) -> Path:
    return _csa(run_dir, "tower180", "reset")


def csa_reset_lf150(run_dir: Path) -> Path:
    return _csa(run_dir, "lf150", "reset")


def csa_reset_tpsc65(run_dir: Path) -> Path:
    return _csa(run_dir, "tpsc65", "reset")


def csa_krum_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            csa_krum_tsmc65,
            csa_krum_tsmc28,
            csa_krum_ihp130,
            csa_krum_tower180,
            csa_krum_lf150,
            csa_krum_tpsc65,
        ),
    )


def csa_krum_pmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            csa_krum_pmos_tsmc65,
            csa_krum_pmos_tsmc28,
            csa_krum_pmos_ihp130,
            csa_krum_pmos_tower180,
            csa_krum_pmos_lf150,
            csa_krum_pmos_tpsc65,
        ),
    )


def csa_continuous_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            csa_continuous_tsmc65,
            csa_continuous_tsmc28,
            csa_continuous_ihp130,
            csa_continuous_tower180,
            csa_continuous_lf150,
            csa_continuous_tpsc65,
        ),
    )


def csa_reset_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            csa_reset_tsmc65,
            csa_reset_tsmc28,
            csa_reset_ihp130,
            csa_reset_tower180,
            csa_reset_lf150,
            csa_reset_tpsc65,
        ),
    )


ALL_PDKS = (
    csa_krum_all_pdks,
    csa_krum_pmos_all_pdks,
    csa_continuous_all_pdks,
    csa_reset_all_pdks,
)


def all_csa_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named amplifier layout target."""

    targets = {
        target.__name__: target
        for target in (
            csa_krum_tsmc65,
            csa_krum_tsmc28,
            csa_krum_ihp130,
            csa_krum_tower180,
            csa_krum_lf150,
            csa_krum_tpsc65,
            csa_krum_pmos_tsmc65,
            csa_krum_pmos_tsmc28,
            csa_krum_pmos_ihp130,
            csa_krum_pmos_tower180,
            csa_krum_pmos_lf150,
            csa_krum_pmos_tpsc65,
            csa_continuous_tsmc65,
            csa_continuous_tsmc28,
            csa_continuous_ihp130,
            csa_continuous_tower180,
            csa_continuous_lf150,
            csa_continuous_tpsc65,
            csa_reset_tsmc65,
            csa_reset_tsmc28,
            csa_reset_ihp130,
            csa_reset_tower180,
            csa_reset_lf150,
            csa_reset_tpsc65,
            *ALL_PDKS,
            all_csa_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available charge-sensitive amplifier layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "csa" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
