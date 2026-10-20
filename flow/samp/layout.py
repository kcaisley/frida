"""Sampler layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/samp_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: the FRIDA-1
transmission gate, the transmission gate with half-size charge-injection dummies, the bootstrapped
NMOS switch, and the NMOS switch alone. The runner is the comparator's (``flow.comp.layout``).

    uv run python -m flow.samp.layout samp_bootstrap_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, SampParams, write_netlist


def _netlists(params: SampParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The sampler's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _samp(run_dir: Path, pdk: str, case: str) -> Path:
    """A sampler case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"samp_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- FRIDA-1 transmission gate


def samp_frida1_tsmc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc65", "frida1")


def samp_frida1_tsmc28(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc28", "frida1")


def samp_frida1_ihp130(run_dir: Path) -> Path:
    return _samp(run_dir, "ihp130", "frida1")


def samp_frida1_tower180(run_dir: Path) -> Path:
    return _samp(run_dir, "tower180", "frida1")


def samp_frida1_lf150(run_dir: Path) -> Path:
    return _samp(run_dir, "lf150", "frida1")


def samp_frida1_tpsc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tpsc65", "frida1")


# ---- transmission gate with charge-injection dummies


def samp_tgate_dummy_tsmc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc65", "tgate_dummy")


def samp_tgate_dummy_tsmc28(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc28", "tgate_dummy")


def samp_tgate_dummy_ihp130(run_dir: Path) -> Path:
    return _samp(run_dir, "ihp130", "tgate_dummy")


def samp_tgate_dummy_tower180(run_dir: Path) -> Path:
    return _samp(run_dir, "tower180", "tgate_dummy")


def samp_tgate_dummy_lf150(run_dir: Path) -> Path:
    return _samp(run_dir, "lf150", "tgate_dummy")


def samp_tgate_dummy_tpsc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tpsc65", "tgate_dummy")


# ---- bootstrapped NMOS switch


def samp_bootstrap_tsmc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc65", "bootstrap")


def samp_bootstrap_tsmc28(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc28", "bootstrap")


def samp_bootstrap_ihp130(run_dir: Path) -> Path:
    return _samp(run_dir, "ihp130", "bootstrap")


def samp_bootstrap_tower180(run_dir: Path) -> Path:
    return _samp(run_dir, "tower180", "bootstrap")


def samp_bootstrap_lf150(run_dir: Path) -> Path:
    return _samp(run_dir, "lf150", "bootstrap")


def samp_bootstrap_tpsc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tpsc65", "bootstrap")


# ---- each case in all six PDKs


def samp_frida1_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            samp_frida1_tsmc65,
            samp_frida1_tsmc28,
            samp_frida1_ihp130,
            samp_frida1_tower180,
            samp_frida1_lf150,
            samp_frida1_tpsc65,
        ),
    )


def samp_tgate_dummy_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            samp_tgate_dummy_tsmc65,
            samp_tgate_dummy_tsmc28,
            samp_tgate_dummy_ihp130,
            samp_tgate_dummy_tower180,
            samp_tgate_dummy_lf150,
            samp_tgate_dummy_tpsc65,
        ),
    )


# ---- NMOS switch alone


def samp_nmos_tsmc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc65", "nmos")


def samp_nmos_tsmc28(run_dir: Path) -> Path:
    return _samp(run_dir, "tsmc28", "nmos")


def samp_nmos_ihp130(run_dir: Path) -> Path:
    return _samp(run_dir, "ihp130", "nmos")


def samp_nmos_tower180(run_dir: Path) -> Path:
    return _samp(run_dir, "tower180", "nmos")


def samp_nmos_lf150(run_dir: Path) -> Path:
    return _samp(run_dir, "lf150", "nmos")


def samp_nmos_tpsc65(run_dir: Path) -> Path:
    return _samp(run_dir, "tpsc65", "nmos")


def samp_bootstrap_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            samp_bootstrap_tsmc65,
            samp_bootstrap_tsmc28,
            samp_bootstrap_ihp130,
            samp_bootstrap_tower180,
            samp_bootstrap_lf150,
            samp_bootstrap_tpsc65,
        ),
    )


def samp_nmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            samp_nmos_tsmc65,
            samp_nmos_tsmc28,
            samp_nmos_ihp130,
            samp_nmos_tower180,
            samp_nmos_lf150,
            samp_nmos_tpsc65,
        ),
    )


ALL_PDKS = (samp_frida1_all_pdks, samp_tgate_dummy_all_pdks, samp_bootstrap_all_pdks, samp_nmos_all_pdks)


def all_samp_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named sampler layout target."""

    targets = {
        target.__name__: target
        for target in (
            samp_frida1_tsmc65,
            samp_frida1_tsmc28,
            samp_frida1_ihp130,
            samp_frida1_tower180,
            samp_frida1_lf150,
            samp_frida1_tpsc65,
            samp_tgate_dummy_tsmc65,
            samp_tgate_dummy_tsmc28,
            samp_tgate_dummy_ihp130,
            samp_tgate_dummy_tower180,
            samp_tgate_dummy_lf150,
            samp_tgate_dummy_tpsc65,
            samp_bootstrap_tsmc65,
            samp_bootstrap_tsmc28,
            samp_bootstrap_ihp130,
            samp_bootstrap_tower180,
            samp_bootstrap_lf150,
            samp_bootstrap_tpsc65,
            samp_nmos_tsmc65,
            samp_nmos_tsmc28,
            samp_nmos_ihp130,
            samp_nmos_tower180,
            samp_nmos_lf150,
            samp_nmos_tpsc65,
            *ALL_PDKS,
            all_samp_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available sampler layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "samp" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
