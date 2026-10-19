"""Cascode bias generator layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/bias_*.json``), each checked with DRC and
LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: wide-swing and margin
cascode-gate diodes. The runner is the comparator's (``flow.comp.layout``).

    uv run python -m flow.bias.layout bias_wide_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, BiasParams, write_netlist


def _netlists(params: BiasParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The generator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _bias(run_dir: Path, pdk: str, case: str) -> Path:
    """A generator case: its netlist into ``run_dir/netlist/``, then the three tools as its
    floorplan places it."""

    name = f"bias_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- Wide-swing cascode gates


def bias_wide_tsmc65(run_dir: Path) -> Path:
    return _bias(run_dir, "tsmc65", "wide")


def bias_wide_tsmc28(run_dir: Path) -> Path:
    return _bias(run_dir, "tsmc28", "wide")


def bias_wide_ihp130(run_dir: Path) -> Path:
    return _bias(run_dir, "ihp130", "wide")


def bias_wide_tower180(run_dir: Path) -> Path:
    return _bias(run_dir, "tower180", "wide")


def bias_wide_lf150(run_dir: Path) -> Path:
    return _bias(run_dir, "lf150", "wide")


def bias_wide_tpsc65(run_dir: Path) -> Path:
    return _bias(run_dir, "tpsc65", "wide")


# ---- Margin cascode gates


def bias_margin_tsmc65(run_dir: Path) -> Path:
    return _bias(run_dir, "tsmc65", "margin")


def bias_margin_tsmc28(run_dir: Path) -> Path:
    return _bias(run_dir, "tsmc28", "margin")


def bias_margin_ihp130(run_dir: Path) -> Path:
    return _bias(run_dir, "ihp130", "margin")


def bias_margin_tower180(run_dir: Path) -> Path:
    return _bias(run_dir, "tower180", "margin")


def bias_margin_lf150(run_dir: Path) -> Path:
    return _bias(run_dir, "lf150", "margin")


def bias_margin_tpsc65(run_dir: Path) -> Path:
    return _bias(run_dir, "tpsc65", "margin")


def bias_wide_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            bias_wide_tsmc65,
            bias_wide_tsmc28,
            bias_wide_ihp130,
            bias_wide_tower180,
            bias_wide_lf150,
            bias_wide_tpsc65,
        ),
    )


def bias_margin_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            bias_margin_tsmc65,
            bias_margin_tsmc28,
            bias_margin_ihp130,
            bias_margin_tower180,
            bias_margin_lf150,
            bias_margin_tpsc65,
        ),
    )


ALL_PDKS = (
    bias_wide_all_pdks,
    bias_margin_all_pdks,
)


def all_bias_layouts(run_dir: Path) -> Path:
    """The two ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named cascode bias layout target."""

    targets = {
        target.__name__: target
        for target in (
            bias_wide_tsmc65,
            bias_wide_tsmc28,
            bias_wide_ihp130,
            bias_wide_tower180,
            bias_wide_lf150,
            bias_wide_tpsc65,
            bias_margin_tsmc65,
            bias_margin_tsmc28,
            bias_margin_ihp130,
            bias_margin_tower180,
            bias_margin_lf150,
            bias_margin_tpsc65,
            *ALL_PDKS,
            all_bias_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available cascode bias layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "bias" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
