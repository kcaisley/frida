"""Phase interpolator layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/pi_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: CMOS and CML interpolators at equal and three-to-one weights. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.pi.layout pi_cmos_half_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, PiParams, write_netlist


def _netlists(params: PiParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The phase interpolator's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _pi(run_dir: Path, pdk: str, case: str) -> Path:
    """A phase interpolator case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"pi_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- CMOS, equal weights


def pi_cmos_half_tsmc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc65", "cmos_half")


def pi_cmos_half_tsmc28(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc28", "cmos_half")


def pi_cmos_half_ihp130(run_dir: Path) -> Path:
    return _pi(run_dir, "ihp130", "cmos_half")


def pi_cmos_half_tower180(run_dir: Path) -> Path:
    return _pi(run_dir, "tower180", "cmos_half")


def pi_cmos_half_lf150(run_dir: Path) -> Path:
    return _pi(run_dir, "lf150", "cmos_half")


def pi_cmos_half_tpsc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tpsc65", "cmos_half")


# ---- CMOS, three to one


def pi_cmos_quarter_tsmc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc65", "cmos_quarter")


def pi_cmos_quarter_tsmc28(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc28", "cmos_quarter")


def pi_cmos_quarter_ihp130(run_dir: Path) -> Path:
    return _pi(run_dir, "ihp130", "cmos_quarter")


def pi_cmos_quarter_tower180(run_dir: Path) -> Path:
    return _pi(run_dir, "tower180", "cmos_quarter")


def pi_cmos_quarter_lf150(run_dir: Path) -> Path:
    return _pi(run_dir, "lf150", "cmos_quarter")


def pi_cmos_quarter_tpsc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tpsc65", "cmos_quarter")


# ---- CML, equal tails


def pi_cml_half_tsmc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc65", "cml_half")


def pi_cml_half_tsmc28(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc28", "cml_half")


def pi_cml_half_ihp130(run_dir: Path) -> Path:
    return _pi(run_dir, "ihp130", "cml_half")


def pi_cml_half_tower180(run_dir: Path) -> Path:
    return _pi(run_dir, "tower180", "cml_half")


def pi_cml_half_lf150(run_dir: Path) -> Path:
    return _pi(run_dir, "lf150", "cml_half")


def pi_cml_half_tpsc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tpsc65", "cml_half")


# ---- CML, three to one


def pi_cml_quarter_tsmc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc65", "cml_quarter")


def pi_cml_quarter_tsmc28(run_dir: Path) -> Path:
    return _pi(run_dir, "tsmc28", "cml_quarter")


def pi_cml_quarter_ihp130(run_dir: Path) -> Path:
    return _pi(run_dir, "ihp130", "cml_quarter")


def pi_cml_quarter_tower180(run_dir: Path) -> Path:
    return _pi(run_dir, "tower180", "cml_quarter")


def pi_cml_quarter_lf150(run_dir: Path) -> Path:
    return _pi(run_dir, "lf150", "cml_quarter")


def pi_cml_quarter_tpsc65(run_dir: Path) -> Path:
    return _pi(run_dir, "tpsc65", "cml_quarter")


# ---- each case in all six PDKs


def pi_cmos_half_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            pi_cmos_half_tsmc65,
            pi_cmos_half_tsmc28,
            pi_cmos_half_ihp130,
            pi_cmos_half_tower180,
            pi_cmos_half_lf150,
            pi_cmos_half_tpsc65,
        ),
    )


def pi_cmos_quarter_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            pi_cmos_quarter_tsmc65,
            pi_cmos_quarter_tsmc28,
            pi_cmos_quarter_ihp130,
            pi_cmos_quarter_tower180,
            pi_cmos_quarter_lf150,
            pi_cmos_quarter_tpsc65,
        ),
    )


def pi_cml_half_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            pi_cml_half_tsmc65,
            pi_cml_half_tsmc28,
            pi_cml_half_ihp130,
            pi_cml_half_tower180,
            pi_cml_half_lf150,
            pi_cml_half_tpsc65,
        ),
    )


def pi_cml_quarter_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            pi_cml_quarter_tsmc65,
            pi_cml_quarter_tsmc28,
            pi_cml_quarter_ihp130,
            pi_cml_quarter_tower180,
            pi_cml_quarter_lf150,
            pi_cml_quarter_tpsc65,
        ),
    )


ALL_PDKS = (pi_cmos_half_all_pdks, pi_cmos_quarter_all_pdks, pi_cml_half_all_pdks, pi_cml_quarter_all_pdks)


def all_pi_layouts(run_dir: Path) -> Path:
    """The four ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named phase interpolator layout target."""

    targets = {
        target.__name__: target
        for target in (
            pi_cmos_half_tsmc65,
            pi_cmos_half_tsmc28,
            pi_cmos_half_ihp130,
            pi_cmos_half_tower180,
            pi_cmos_half_lf150,
            pi_cmos_half_tpsc65,
            pi_cmos_quarter_tsmc65,
            pi_cmos_quarter_tsmc28,
            pi_cmos_quarter_ihp130,
            pi_cmos_quarter_tower180,
            pi_cmos_quarter_lf150,
            pi_cmos_quarter_tpsc65,
            pi_cml_half_tsmc65,
            pi_cml_half_tsmc28,
            pi_cml_half_ihp130,
            pi_cml_half_tower180,
            pi_cml_half_lf150,
            pi_cml_half_tpsc65,
            pi_cml_quarter_tsmc65,
            pi_cml_quarter_tsmc28,
            pi_cml_quarter_ihp130,
            pi_cml_quarter_tower180,
            pi_cml_quarter_lf150,
            pi_cml_quarter_tpsc65,
            *ALL_PDKS,
            all_pi_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available phase interpolator layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "pi" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
