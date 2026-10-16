"""Delay line and ring layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/delay_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: inverter, current-starved, coupled and tail-controlled rings, and inverter, coupled and current-starved delay lines. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.delay.layout delay_ring5_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, DelayParams, write_netlist


def _netlists(params: DelayParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The delay line and ring's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _delay(run_dir: Path, pdk: str, case: str) -> Path:
    """A delay line and ring case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"delay_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- five-stage inverter ring


def delay_ring5_tsmc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc65", "ring5")


def delay_ring5_tsmc28(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc28", "ring5")


def delay_ring5_ihp130(run_dir: Path) -> Path:
    return _delay(run_dir, "ihp130", "ring5")


def delay_ring5_tower180(run_dir: Path) -> Path:
    return _delay(run_dir, "tower180", "ring5")


def delay_ring5_lf150(run_dir: Path) -> Path:
    return _delay(run_dir, "lf150", "ring5")


def delay_ring5_tpsc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tpsc65", "ring5")


# ---- five-stage current-starved ring


def delay_ring5_starved_tsmc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc65", "ring5_starved")


def delay_ring5_starved_tsmc28(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc28", "ring5_starved")


def delay_ring5_starved_ihp130(run_dir: Path) -> Path:
    return _delay(run_dir, "ihp130", "ring5_starved")


def delay_ring5_starved_tower180(run_dir: Path) -> Path:
    return _delay(run_dir, "tower180", "ring5_starved")


def delay_ring5_starved_lf150(run_dir: Path) -> Path:
    return _delay(run_dir, "lf150", "ring5_starved")


def delay_ring5_starved_tpsc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tpsc65", "ring5_starved")


# ---- four-stage coupled ring with injection


def delay_ring4_coupled_tsmc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc65", "ring4_coupled")


def delay_ring4_coupled_tsmc28(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc28", "ring4_coupled")


def delay_ring4_coupled_ihp130(run_dir: Path) -> Path:
    return _delay(run_dir, "ihp130", "ring4_coupled")


def delay_ring4_coupled_tower180(run_dir: Path) -> Path:
    return _delay(run_dir, "tower180", "ring4_coupled")


def delay_ring4_coupled_lf150(run_dir: Path) -> Path:
    return _delay(run_dir, "lf150", "ring4_coupled")


def delay_ring4_coupled_tpsc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tpsc65", "ring4_coupled")


# ---- four-stage coupled ring on a shared tail


def delay_ring4_tail_tsmc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc65", "ring4_tail")


def delay_ring4_tail_tsmc28(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc28", "ring4_tail")


def delay_ring4_tail_ihp130(run_dir: Path) -> Path:
    return _delay(run_dir, "ihp130", "ring4_tail")


def delay_ring4_tail_tower180(run_dir: Path) -> Path:
    return _delay(run_dir, "tower180", "ring4_tail")


def delay_ring4_tail_lf150(run_dir: Path) -> Path:
    return _delay(run_dir, "lf150", "ring4_tail")


def delay_ring4_tail_tpsc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tpsc65", "ring4_tail")


# ---- four-stage inverter delay line


def delay_chain4_tsmc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc65", "chain4")


def delay_chain4_tsmc28(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc28", "chain4")


def delay_chain4_ihp130(run_dir: Path) -> Path:
    return _delay(run_dir, "ihp130", "chain4")


def delay_chain4_tower180(run_dir: Path) -> Path:
    return _delay(run_dir, "tower180", "chain4")


def delay_chain4_lf150(run_dir: Path) -> Path:
    return _delay(run_dir, "lf150", "chain4")


def delay_chain4_tpsc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tpsc65", "chain4")


# ---- two-stage coupled differential buffer


def delay_chain2_coupled_tsmc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc65", "chain2_coupled")


def delay_chain2_coupled_tsmc28(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc28", "chain2_coupled")


def delay_chain2_coupled_ihp130(run_dir: Path) -> Path:
    return _delay(run_dir, "ihp130", "chain2_coupled")


def delay_chain2_coupled_tower180(run_dir: Path) -> Path:
    return _delay(run_dir, "tower180", "chain2_coupled")


def delay_chain2_coupled_lf150(run_dir: Path) -> Path:
    return _delay(run_dir, "lf150", "chain2_coupled")


def delay_chain2_coupled_tpsc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tpsc65", "chain2_coupled")


# ---- four-stage current-starved delay line


def delay_chain4_starved_tsmc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc65", "chain4_starved")


def delay_chain4_starved_tsmc28(run_dir: Path) -> Path:
    return _delay(run_dir, "tsmc28", "chain4_starved")


def delay_chain4_starved_ihp130(run_dir: Path) -> Path:
    return _delay(run_dir, "ihp130", "chain4_starved")


def delay_chain4_starved_tower180(run_dir: Path) -> Path:
    return _delay(run_dir, "tower180", "chain4_starved")


def delay_chain4_starved_lf150(run_dir: Path) -> Path:
    return _delay(run_dir, "lf150", "chain4_starved")


def delay_chain4_starved_tpsc65(run_dir: Path) -> Path:
    return _delay(run_dir, "tpsc65", "chain4_starved")


# ---- each case in all six PDKs


def delay_ring5_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            delay_ring5_tsmc65,
            delay_ring5_tsmc28,
            delay_ring5_ihp130,
            delay_ring5_tower180,
            delay_ring5_lf150,
            delay_ring5_tpsc65,
        ),
    )


def delay_ring5_starved_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            delay_ring5_starved_tsmc65,
            delay_ring5_starved_tsmc28,
            delay_ring5_starved_ihp130,
            delay_ring5_starved_tower180,
            delay_ring5_starved_lf150,
            delay_ring5_starved_tpsc65,
        ),
    )


def delay_ring4_coupled_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            delay_ring4_coupled_tsmc65,
            delay_ring4_coupled_tsmc28,
            delay_ring4_coupled_ihp130,
            delay_ring4_coupled_tower180,
            delay_ring4_coupled_lf150,
            delay_ring4_coupled_tpsc65,
        ),
    )


def delay_ring4_tail_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            delay_ring4_tail_tsmc65,
            delay_ring4_tail_tsmc28,
            delay_ring4_tail_ihp130,
            delay_ring4_tail_tower180,
            delay_ring4_tail_lf150,
            delay_ring4_tail_tpsc65,
        ),
    )


def delay_chain4_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            delay_chain4_tsmc65,
            delay_chain4_tsmc28,
            delay_chain4_ihp130,
            delay_chain4_tower180,
            delay_chain4_lf150,
            delay_chain4_tpsc65,
        ),
    )


def delay_chain2_coupled_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            delay_chain2_coupled_tsmc65,
            delay_chain2_coupled_tsmc28,
            delay_chain2_coupled_ihp130,
            delay_chain2_coupled_tower180,
            delay_chain2_coupled_lf150,
            delay_chain2_coupled_tpsc65,
        ),
    )


def delay_chain4_starved_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            delay_chain4_starved_tsmc65,
            delay_chain4_starved_tsmc28,
            delay_chain4_starved_ihp130,
            delay_chain4_starved_tower180,
            delay_chain4_starved_lf150,
            delay_chain4_starved_tpsc65,
        ),
    )


ALL_PDKS = (
    delay_ring5_all_pdks,
    delay_ring5_starved_all_pdks,
    delay_ring4_coupled_all_pdks,
    delay_ring4_tail_all_pdks,
    delay_chain4_all_pdks,
    delay_chain2_coupled_all_pdks,
    delay_chain4_starved_all_pdks,
)


def all_delay_layouts(run_dir: Path) -> Path:
    """The seven ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named delay line and ring layout target."""

    targets = {
        target.__name__: target
        for target in (
            delay_ring5_tsmc65,
            delay_ring5_tsmc28,
            delay_ring5_ihp130,
            delay_ring5_tower180,
            delay_ring5_lf150,
            delay_ring5_tpsc65,
            delay_ring5_starved_tsmc65,
            delay_ring5_starved_tsmc28,
            delay_ring5_starved_ihp130,
            delay_ring5_starved_tower180,
            delay_ring5_starved_lf150,
            delay_ring5_starved_tpsc65,
            delay_ring4_coupled_tsmc65,
            delay_ring4_coupled_tsmc28,
            delay_ring4_coupled_ihp130,
            delay_ring4_coupled_tower180,
            delay_ring4_coupled_lf150,
            delay_ring4_coupled_tpsc65,
            delay_ring4_tail_tsmc65,
            delay_ring4_tail_tsmc28,
            delay_ring4_tail_ihp130,
            delay_ring4_tail_tower180,
            delay_ring4_tail_lf150,
            delay_ring4_tail_tpsc65,
            delay_chain4_tsmc65,
            delay_chain4_tsmc28,
            delay_chain4_ihp130,
            delay_chain4_tower180,
            delay_chain4_lf150,
            delay_chain4_tpsc65,
            delay_chain2_coupled_tsmc65,
            delay_chain2_coupled_tsmc28,
            delay_chain2_coupled_ihp130,
            delay_chain2_coupled_tower180,
            delay_chain2_coupled_lf150,
            delay_chain2_coupled_tpsc65,
            delay_chain4_starved_tsmc65,
            delay_chain4_starved_tsmc28,
            delay_chain4_starved_ihp130,
            delay_chain4_starved_tower180,
            delay_chain4_starved_lf150,
            delay_chain4_starved_tpsc65,
            *ALL_PDKS,
            all_delay_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available delay line and ring layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "delay" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
