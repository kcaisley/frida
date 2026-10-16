"""Clock generator layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/clkgen_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: non-overlapping clocks, a rising-edge pulse, and a clock gate. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.clkgen.layout clkgen_nonoverlap_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, ClkgenParams, write_netlist


def _netlists(params: ClkgenParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The clock generator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _clkgen(run_dir: Path, pdk: str, case: str) -> Path:
    """A clock generator case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"clkgen_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- non-overlapping clocks


def clkgen_nonoverlap_tsmc65(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tsmc65", "nonoverlap")


def clkgen_nonoverlap_tsmc28(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tsmc28", "nonoverlap")


def clkgen_nonoverlap_ihp130(run_dir: Path) -> Path:
    return _clkgen(run_dir, "ihp130", "nonoverlap")


def clkgen_nonoverlap_tower180(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tower180", "nonoverlap")


def clkgen_nonoverlap_lf150(run_dir: Path) -> Path:
    return _clkgen(run_dir, "lf150", "nonoverlap")


def clkgen_nonoverlap_tpsc65(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tpsc65", "nonoverlap")


# ---- rising-edge pulse


def clkgen_pulse_tsmc65(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tsmc65", "pulse")


def clkgen_pulse_tsmc28(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tsmc28", "pulse")


def clkgen_pulse_ihp130(run_dir: Path) -> Path:
    return _clkgen(run_dir, "ihp130", "pulse")


def clkgen_pulse_tower180(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tower180", "pulse")


def clkgen_pulse_lf150(run_dir: Path) -> Path:
    return _clkgen(run_dir, "lf150", "pulse")


def clkgen_pulse_tpsc65(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tpsc65", "pulse")


# ---- clock gate


def clkgen_gate_tsmc65(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tsmc65", "gate")


def clkgen_gate_tsmc28(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tsmc28", "gate")


def clkgen_gate_ihp130(run_dir: Path) -> Path:
    return _clkgen(run_dir, "ihp130", "gate")


def clkgen_gate_tower180(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tower180", "gate")


def clkgen_gate_lf150(run_dir: Path) -> Path:
    return _clkgen(run_dir, "lf150", "gate")


def clkgen_gate_tpsc65(run_dir: Path) -> Path:
    return _clkgen(run_dir, "tpsc65", "gate")


# ---- each case in all six PDKs


def clkgen_nonoverlap_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            clkgen_nonoverlap_tsmc65,
            clkgen_nonoverlap_tsmc28,
            clkgen_nonoverlap_ihp130,
            clkgen_nonoverlap_tower180,
            clkgen_nonoverlap_lf150,
            clkgen_nonoverlap_tpsc65,
        ),
    )


def clkgen_pulse_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            clkgen_pulse_tsmc65,
            clkgen_pulse_tsmc28,
            clkgen_pulse_ihp130,
            clkgen_pulse_tower180,
            clkgen_pulse_lf150,
            clkgen_pulse_tpsc65,
        ),
    )


def clkgen_gate_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            clkgen_gate_tsmc65,
            clkgen_gate_tsmc28,
            clkgen_gate_ihp130,
            clkgen_gate_tower180,
            clkgen_gate_lf150,
            clkgen_gate_tpsc65,
        ),
    )


ALL_PDKS = (clkgen_nonoverlap_all_pdks, clkgen_pulse_all_pdks, clkgen_gate_all_pdks)


def all_clkgen_layouts(run_dir: Path) -> Path:
    """The three ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named clock generator layout target."""

    targets = {
        target.__name__: target
        for target in (
            clkgen_nonoverlap_tsmc65,
            clkgen_nonoverlap_tsmc28,
            clkgen_nonoverlap_ihp130,
            clkgen_nonoverlap_tower180,
            clkgen_nonoverlap_lf150,
            clkgen_nonoverlap_tpsc65,
            clkgen_pulse_tsmc65,
            clkgen_pulse_tsmc28,
            clkgen_pulse_ihp130,
            clkgen_pulse_tower180,
            clkgen_pulse_lf150,
            clkgen_pulse_tpsc65,
            clkgen_gate_tsmc65,
            clkgen_gate_tsmc28,
            clkgen_gate_ihp130,
            clkgen_gate_tower180,
            clkgen_gate_lf150,
            clkgen_gate_tpsc65,
            *ALL_PDKS,
            all_clkgen_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available clock generator layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "clkgen" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
