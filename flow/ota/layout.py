"""Amplifier layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN) from its hand-written floorplan (``design/layout/ota_*.json``), each checked with DRC
and LVS; a ``*_all_pdks`` target runs one case in all six PDKs. Cases: five-transistor amplifiers with NMOS and PMOS inputs, telescopic and folded cascodes, the self-biased complementary amplifier, and a two-stage amplifier. The runner is the
comparator's (``flow.comp.layout``).

    uv run python -m flow.ota.layout ota_five_t_tsmc65
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
from pathlib import Path

from flow.comp.layout import FLOORPLANS, ROOT, _all_pdks, _finish, _run

from .subckt import CASES, OtaParams, write_netlist


def _netlists(params: OtaParams, pdk: str, out_dir: Path, name: str) -> Path:
    """The amplifier's netlist in ``pdk``; the file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{name}.sp", logic)


def _ota(run_dir: Path, pdk: str, case: str) -> Path:
    """A amplifier case: its netlist into ``run_dir/netlist/``, then the three tools as its floorplan
    places it."""

    name = f"ota_{case}"
    netlist = _netlists(CASES[case], pdk, run_dir / "netlist", name)
    return _run(run_dir, pdk, name, netlist, FLOORPLANS / f"{name}.json")


# ---- five-transistor amplifier, NMOS input


def ota_five_t_tsmc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc65", "five_t")


def ota_five_t_tsmc28(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc28", "five_t")


def ota_five_t_ihp130(run_dir: Path) -> Path:
    return _ota(run_dir, "ihp130", "five_t")


def ota_five_t_tower180(run_dir: Path) -> Path:
    return _ota(run_dir, "tower180", "five_t")


def ota_five_t_lf150(run_dir: Path) -> Path:
    return _ota(run_dir, "lf150", "five_t")


def ota_five_t_tpsc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tpsc65", "five_t")


# ---- five-transistor amplifier, PMOS input


def ota_five_t_pmos_tsmc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc65", "five_t_pmos")


def ota_five_t_pmos_tsmc28(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc28", "five_t_pmos")


def ota_five_t_pmos_ihp130(run_dir: Path) -> Path:
    return _ota(run_dir, "ihp130", "five_t_pmos")


def ota_five_t_pmos_tower180(run_dir: Path) -> Path:
    return _ota(run_dir, "tower180", "five_t_pmos")


def ota_five_t_pmos_lf150(run_dir: Path) -> Path:
    return _ota(run_dir, "lf150", "five_t_pmos")


def ota_five_t_pmos_tpsc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tpsc65", "five_t_pmos")


# ---- telescopic cascode


def ota_telescopic_tsmc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc65", "telescopic")


def ota_telescopic_tsmc28(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc28", "telescopic")


def ota_telescopic_ihp130(run_dir: Path) -> Path:
    return _ota(run_dir, "ihp130", "telescopic")


def ota_telescopic_tower180(run_dir: Path) -> Path:
    return _ota(run_dir, "tower180", "telescopic")


def ota_telescopic_lf150(run_dir: Path) -> Path:
    return _ota(run_dir, "lf150", "telescopic")


def ota_telescopic_tpsc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tpsc65", "telescopic")


# ---- folded cascode


def ota_folded_tsmc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc65", "folded")


def ota_folded_tsmc28(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc28", "folded")


def ota_folded_ihp130(run_dir: Path) -> Path:
    return _ota(run_dir, "ihp130", "folded")


def ota_folded_tower180(run_dir: Path) -> Path:
    return _ota(run_dir, "tower180", "folded")


def ota_folded_lf150(run_dir: Path) -> Path:
    return _ota(run_dir, "lf150", "folded")


def ota_folded_tpsc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tpsc65", "folded")


# ---- self-biased complementary amplifier


def ota_self_biased_tsmc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc65", "self_biased")


def ota_self_biased_tsmc28(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc28", "self_biased")


def ota_self_biased_ihp130(run_dir: Path) -> Path:
    return _ota(run_dir, "ihp130", "self_biased")


def ota_self_biased_tower180(run_dir: Path) -> Path:
    return _ota(run_dir, "tower180", "self_biased")


def ota_self_biased_lf150(run_dir: Path) -> Path:
    return _ota(run_dir, "lf150", "self_biased")


def ota_self_biased_tpsc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tpsc65", "self_biased")


# ---- telescopic first stage, common-source second stages


def ota_two_stage_tsmc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc65", "two_stage")


def ota_two_stage_tsmc28(run_dir: Path) -> Path:
    return _ota(run_dir, "tsmc28", "two_stage")


def ota_two_stage_ihp130(run_dir: Path) -> Path:
    return _ota(run_dir, "ihp130", "two_stage")


def ota_two_stage_tower180(run_dir: Path) -> Path:
    return _ota(run_dir, "tower180", "two_stage")


def ota_two_stage_lf150(run_dir: Path) -> Path:
    return _ota(run_dir, "lf150", "two_stage")


def ota_two_stage_tpsc65(run_dir: Path) -> Path:
    return _ota(run_dir, "tpsc65", "two_stage")


# ---- each case in all six PDKs


def ota_five_t_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ota_five_t_tsmc65,
            ota_five_t_tsmc28,
            ota_five_t_ihp130,
            ota_five_t_tower180,
            ota_five_t_lf150,
            ota_five_t_tpsc65,
        ),
    )


def ota_five_t_pmos_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ota_five_t_pmos_tsmc65,
            ota_five_t_pmos_tsmc28,
            ota_five_t_pmos_ihp130,
            ota_five_t_pmos_tower180,
            ota_five_t_pmos_lf150,
            ota_five_t_pmos_tpsc65,
        ),
    )


def ota_telescopic_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ota_telescopic_tsmc65,
            ota_telescopic_tsmc28,
            ota_telescopic_ihp130,
            ota_telescopic_tower180,
            ota_telescopic_lf150,
            ota_telescopic_tpsc65,
        ),
    )


def ota_folded_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ota_folded_tsmc65,
            ota_folded_tsmc28,
            ota_folded_ihp130,
            ota_folded_tower180,
            ota_folded_lf150,
            ota_folded_tpsc65,
        ),
    )


def ota_self_biased_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ota_self_biased_tsmc65,
            ota_self_biased_tsmc28,
            ota_self_biased_ihp130,
            ota_self_biased_tower180,
            ota_self_biased_lf150,
            ota_self_biased_tpsc65,
        ),
    )


def ota_two_stage_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            ota_two_stage_tsmc65,
            ota_two_stage_tsmc28,
            ota_two_stage_ihp130,
            ota_two_stage_tower180,
            ota_two_stage_lf150,
            ota_two_stage_tpsc65,
        ),
    )


ALL_PDKS = (
    ota_five_t_all_pdks,
    ota_five_t_pmos_all_pdks,
    ota_telescopic_all_pdks,
    ota_folded_all_pdks,
    ota_self_biased_all_pdks,
    ota_two_stage_all_pdks,
)


def all_ota_layouts(run_dir: Path) -> Path:
    """The six ``*_all_pdks`` targets into ``run_dir/<target>/``."""

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
            ota_five_t_tsmc65,
            ota_five_t_tsmc28,
            ota_five_t_ihp130,
            ota_five_t_tower180,
            ota_five_t_lf150,
            ota_five_t_tpsc65,
            ota_five_t_pmos_tsmc65,
            ota_five_t_pmos_tsmc28,
            ota_five_t_pmos_ihp130,
            ota_five_t_pmos_tower180,
            ota_five_t_pmos_lf150,
            ota_five_t_pmos_tpsc65,
            ota_telescopic_tsmc65,
            ota_telescopic_tsmc28,
            ota_telescopic_ihp130,
            ota_telescopic_tower180,
            ota_telescopic_lf150,
            ota_telescopic_tpsc65,
            ota_folded_tsmc65,
            ota_folded_tsmc28,
            ota_folded_ihp130,
            ota_folded_tower180,
            ota_folded_lf150,
            ota_folded_tpsc65,
            ota_self_biased_tsmc65,
            ota_self_biased_tsmc28,
            ota_self_biased_ihp130,
            ota_self_biased_tower180,
            ota_self_biased_lf150,
            ota_self_biased_tpsc65,
            ota_two_stage_tsmc65,
            ota_two_stage_tsmc28,
            ota_two_stage_ihp130,
            ota_two_stage_tower180,
            ota_two_stage_lf150,
            ota_two_stage_tpsc65,
            *ALL_PDKS,
            all_ota_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available amplifier layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "ota" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
