"""Cml layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/cml_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: NMOS- and PMOS-input buffers, a latch, a divide-by-two, and an XOR. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.cml.layout cml_buffer_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, CmlParams, write_netlist


def _netlists(params: CmlParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The CML's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _cml(run_dir: Path, pdk: str, case: str) -> Path:
    """A CML case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"cml_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- NMOS-input buffer


def cml_buffer_tsmc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc65", "buffer")


def cml_buffer_tsmc28(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc28", "buffer")


def cml_buffer_ihp130(run_dir: Path) -> Path:
    return _cml(run_dir, "ihp130", "buffer")


def cml_buffer_tower180(run_dir: Path) -> Path:
    return _cml(run_dir, "tower180", "buffer")


def cml_buffer_lf150(run_dir: Path) -> Path:
    return _cml(run_dir, "lf150", "buffer")


def cml_buffer_tpsc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tpsc65", "buffer")


# ---- PMOS-input buffer


def cml_buffer_pmos_tsmc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc65", "buffer_pmos")


def cml_buffer_pmos_tsmc28(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc28", "buffer_pmos")


def cml_buffer_pmos_ihp130(run_dir: Path) -> Path:
    return _cml(run_dir, "ihp130", "buffer_pmos")


def cml_buffer_pmos_tower180(run_dir: Path) -> Path:
    return _cml(run_dir, "tower180", "buffer_pmos")


def cml_buffer_pmos_lf150(run_dir: Path) -> Path:
    return _cml(run_dir, "lf150", "buffer_pmos")


def cml_buffer_pmos_tpsc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tpsc65", "buffer_pmos")


# ---- latch


def cml_latch_tsmc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc65", "latch")


def cml_latch_tsmc28(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc28", "latch")


def cml_latch_ihp130(run_dir: Path) -> Path:
    return _cml(run_dir, "ihp130", "latch")


def cml_latch_tower180(run_dir: Path) -> Path:
    return _cml(run_dir, "tower180", "latch")


def cml_latch_lf150(run_dir: Path) -> Path:
    return _cml(run_dir, "lf150", "latch")


def cml_latch_tpsc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tpsc65", "latch")


# ---- divide-by-two


def cml_divider_tsmc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc65", "divider")


def cml_divider_tsmc28(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc28", "divider")


def cml_divider_ihp130(run_dir: Path) -> Path:
    return _cml(run_dir, "ihp130", "divider")


def cml_divider_tower180(run_dir: Path) -> Path:
    return _cml(run_dir, "tower180", "divider")


def cml_divider_lf150(run_dir: Path) -> Path:
    return _cml(run_dir, "lf150", "divider")


def cml_divider_tpsc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tpsc65", "divider")


# ---- XOR


def cml_xor_tsmc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc65", "xor")


def cml_xor_tsmc28(run_dir: Path) -> Path:
    return _cml(run_dir, "tsmc28", "xor")


def cml_xor_ihp130(run_dir: Path) -> Path:
    return _cml(run_dir, "ihp130", "xor")


def cml_xor_tower180(run_dir: Path) -> Path:
    return _cml(run_dir, "tower180", "xor")


def cml_xor_lf150(run_dir: Path) -> Path:
    return _cml(run_dir, "lf150", "xor")


def cml_xor_tpsc65(run_dir: Path) -> Path:
    return _cml(run_dir, "tpsc65", "xor")


# ---- each case in all six PDKs


def cml_buffer_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            cml_buffer_tsmc65,
            cml_buffer_tsmc28,
            cml_buffer_ihp130,
            cml_buffer_tower180,
            cml_buffer_lf150,
            cml_buffer_tpsc65,
        ),
    )


def cml_buffer_pmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            cml_buffer_pmos_tsmc65,
            cml_buffer_pmos_tsmc28,
            cml_buffer_pmos_ihp130,
            cml_buffer_pmos_tower180,
            cml_buffer_pmos_lf150,
            cml_buffer_pmos_tpsc65,
        ),
    )


def cml_latch_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            cml_latch_tsmc65,
            cml_latch_tsmc28,
            cml_latch_ihp130,
            cml_latch_tower180,
            cml_latch_lf150,
            cml_latch_tpsc65,
        ),
    )


def cml_divider_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            cml_divider_tsmc65,
            cml_divider_tsmc28,
            cml_divider_ihp130,
            cml_divider_tower180,
            cml_divider_lf150,
            cml_divider_tpsc65,
        ),
    )


def cml_xor_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            cml_xor_tsmc65,
            cml_xor_tsmc28,
            cml_xor_ihp130,
            cml_xor_tower180,
            cml_xor_lf150,
            cml_xor_tpsc65,
        ),
    )


ALL_PDKS = (cml_buffer_all_pdks, cml_buffer_pmos_all_pdks, cml_latch_all_pdks, cml_divider_all_pdks, cml_xor_all_pdks)


def all_cml_layouts(run_dir: Path) -> Path:
    """The five ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named CML layout target."""

    targets = {
        target.__name__: target
        for target in (
            cml_buffer_tsmc65,
            cml_buffer_tsmc28,
            cml_buffer_ihp130,
            cml_buffer_tower180,
            cml_buffer_lf150,
            cml_buffer_tpsc65,
            cml_buffer_pmos_tsmc65,
            cml_buffer_pmos_tsmc28,
            cml_buffer_pmos_ihp130,
            cml_buffer_pmos_tower180,
            cml_buffer_pmos_lf150,
            cml_buffer_pmos_tpsc65,
            cml_latch_tsmc65,
            cml_latch_tsmc28,
            cml_latch_ihp130,
            cml_latch_tower180,
            cml_latch_lf150,
            cml_latch_tpsc65,
            cml_divider_tsmc65,
            cml_divider_tsmc28,
            cml_divider_ihp130,
            cml_divider_tower180,
            cml_divider_lf150,
            cml_divider_tpsc65,
            cml_xor_tsmc65,
            cml_xor_tsmc28,
            cml_xor_ihp130,
            cml_xor_tower180,
            cml_xor_lf150,
            cml_xor_tpsc65,
            *ALL_PDKS,
            all_cml_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available CML layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "cml" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
