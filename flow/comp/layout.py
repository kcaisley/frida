"""Comparator layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A target names one case and one PDK and lays it out with all three tools (cIcCreator, laygo,
ALIGN), each checked with DRC and LVS; a ``*_all_pdks`` target runs one case in all six PDKs.
Cases: the FRIDA-1 comparator and the size sweep's example double tail (c040), each from its
hand-written floorplan (``design/layout``, "manual") or from ALIGN's placement ("auto"), and
``mos_inv`` (one NMOS and one PMOS row cell). Every (pdk, tool) runs whatever the others do;
the target raises at the end when any failed (``failures.json``).

Tools: ``CICPY`` (cicpy 0.3, with ``compile``), ``LAYGO_CLIENT`` (the hosted laygo server's
client, needs internet), ``ALIGN_HOME`` (an ALIGN install); Calibre, Assura or KLayout as each
PDK's signoff provider (``pdk/<pdk>/signoff.py``) uses them.

    uv run python -m flow.comp.layout comp_c040_manual_tsmc65
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from importlib import import_module
from pathlib import Path
from types import FunctionType
from typing import Any

from klayout import db

from flow.layout.align.build import build as align_build
from flow.layout.cic.build import build as cic_build
from flow.layout.floorplan import align_floorplan
from flow.layout.laygo.build import build as laygo_build
from flow.layout.pdkproc import in_pdk
from flow.layout.signoff import row_signoff

from .subckt import FRIDA1, LENGTHS, SIZE_PROFILES, CompParams, OutputStage, topologies, write_netlist

ROOT = Path(__file__).resolve().parents[2]
FLOORPLANS = ROOT / "design" / "layout"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")
BUILD = {"cic": cic_build, "laygo": laygo_build, "align": align_build}

# the example double tail ("c040"): the size sweep's topology 40 at the half profile, as
# `python -m flow.comp.subckt 40_half ...` builds it
C040 = CompParams(**topologies()[40], **SIZE_PROFILES["half"], **LENGTHS)
# where the ports leave the block, as in both comparator floorplans (circuit knowledge, not placement)
ESCAPE = {"up": ["inp", "inn"], "down": ["clk", "clkb", "outp", "outn"]}

Target = FunctionType  # a target: (run_dir) -> run_dir


def _netlists(params: CompParams, pdk: str, out_dir: Path, name: str) -> tuple[Path, Path]:
    """The two netlists of a comparator in ``pdk``: standard-cell output stage and all-transistor.
    The file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    stage = lambda s: CompParams(**{**params.__dict__, "output_stage": s})
    stdcells = write_netlist(stage(OutputStage.STDCELLS), out_dir / f"{name}_stdcells.sp", logic)
    transistors = write_netlist(stage(OutputStage.TRANSISTORS), out_dir / f"{name}_transistors.sp", logic)
    return stdcells, transistors


def _cell_um(gds: Path) -> list[float]:
    """Width and height (um) of the GDS's largest top cell."""

    layout = db.Layout()
    layout.read(str(gds))
    box = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).dbbox()
    return [round(box.width(), 3), round(box.height(), 3)]


def _finish(run_dir: Path, summary: dict[str, dict[str, Any]], failures: dict[str, str]) -> Path:
    """Write ``summary.json`` (and ``failures.json``); raise when anything failed."""

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if failures:
        path = run_dir / "failures.json"
        path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} comparator layouts failed; see {path}")
    return run_dir


def _run(run_dir: Path, pdk: str, name: str, netlist: Path, floorplan: Path | None) -> Path:
    """One design in one PDK: the floorplan (from ALIGN's placement when none is given), the three
    tools into ``run_dir/<tool>/``, each signed off in ``run_dir/<tool>/signoff/``."""

    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    if floorplan is None:
        try:
            floorplan = align_floorplan(netlist, pdk, run_dir / "floorplan", name=name, escape=ESCAPE)
        except Exception as error:  # noqa: BLE001 - every tool needs the floorplan
            return _finish(run_dir, summary, {f"{pdk}/floorplan": repr(error)})
    for tool, build in BUILD.items():
        out = run_dir / tool
        entry: dict[str, Any] = {}
        summary[f"{pdk}/{tool}"] = entry
        try:
            gds = build(pdk, floorplan, netlist, out)
            entry.update(gds=str(gds), cell_um=_cell_um(gds))
            check = row_signoff(pdk, gds, netlist, floorplan, out / "signoff")
            entry.update(drc_violations=check.drc_violations, lvs_correct=check.lvs_correct)
            if check.drc_violations or not check.lvs_correct:
                failures[f"{pdk}/{tool}"] = f"DRC {check.drc_violations} violations, LVS correct {check.lvs_correct}"
        except Exception as error:  # noqa: BLE001 - report every independent tool failure
            entry["error"] = failures[f"{pdk}/{tool}"] = repr(error)
            drc = out / "signoff" / "drc_violations.json"
            if drc.exists():  # DRC ran before the failure
                entry["drc_violations"] = sum(json.loads(drc.read_text())["violations"].values())
    return _finish(run_dir, summary, failures)


def _comp(run_dir: Path, pdk: str, name: str, params: CompParams, floorplan: Path | None, gates: bool = False) -> Path:
    """A comparator: its netlists into ``run_dir/netlist/``, then ``_run``. A hand-written floorplan
    places the generator's standard-cell netlist (it names those cells). From ALIGN's placement:
    the transistor netlist with the library cells it contains recognized (flow/layout/stdcells.py),
    or, ``gates``, the standard-cell netlist with its cells as transistors, for the row cells (and
    ALIGN's own logic gates) to draw."""

    stdcells, transistors = _netlists(params, pdk, run_dir / "netlist", name)
    if floorplan is not None:
        netlist = stdcells
    elif gates:
        netlist = in_pdk(pdk, "flow.layout.stdcells", "expand_file", stdcells, run_dir / "netlist" / f"{name}_gates.sp")
    else:
        netlist = in_pdk(
            pdk, "flow.layout.stdcells", "recognize_file", transistors, run_dir / "netlist" / f"{name}_recognized.sp"
        )
    return _run(run_dir, pdk, name, netlist, floorplan)


def _all_pdks(run_dir: Path, targets: tuple[Target, ...]) -> Path:
    """The per-PDK targets into ``run_dir/<pdk>/``; every failure collected, the summaries merged."""

    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    for target in targets:
        sub = run_dir / target.__name__.rsplit("_", 1)[1]
        try:
            target(sub)
        except Exception as error:  # noqa: BLE001 - report every PDK
            found = sub / "failures.json"
            failures.update(json.loads(found.read_text()) if found.exists() else {target.__name__: repr(error)})
        if (sub / "summary.json").exists():
            summary.update(json.loads((sub / "summary.json").read_text()))
    return _finish(run_dir, summary, failures)


# ---- FRIDA-1, hand-written floorplan


def comp_frida1_manual_tsmc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc65", "comp_frida1", FRIDA1, FLOORPLANS / "comp_frida1.json")


def comp_frida1_manual_tsmc28(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc28", "comp_frida1", FRIDA1, FLOORPLANS / "comp_frida1.json")


def comp_frida1_manual_ihp130(run_dir: Path) -> Path:
    return _comp(run_dir, "ihp130", "comp_frida1", FRIDA1, FLOORPLANS / "comp_frida1.json")


def comp_frida1_manual_tower180(run_dir: Path) -> Path:
    return _comp(run_dir, "tower180", "comp_frida1", FRIDA1, FLOORPLANS / "comp_frida1.json")


def comp_frida1_manual_lf150(run_dir: Path) -> Path:
    return _comp(run_dir, "lf150", "comp_frida1", FRIDA1, FLOORPLANS / "comp_frida1.json")


def comp_frida1_manual_tpsc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tpsc65", "comp_frida1", FRIDA1, FLOORPLANS / "comp_frida1.json")


# ---- c040, hand-written floorplan


def comp_c040_manual_tsmc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc65", "comp_c040", C040, FLOORPLANS / "comp_c040.json")


def comp_c040_manual_tsmc28(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc28", "comp_c040", C040, FLOORPLANS / "comp_c040.json")


def comp_c040_manual_ihp130(run_dir: Path) -> Path:
    return _comp(run_dir, "ihp130", "comp_c040", C040, FLOORPLANS / "comp_c040.json")


def comp_c040_manual_tower180(run_dir: Path) -> Path:
    return _comp(run_dir, "tower180", "comp_c040", C040, FLOORPLANS / "comp_c040.json")


def comp_c040_manual_lf150(run_dir: Path) -> Path:
    return _comp(run_dir, "lf150", "comp_c040", C040, FLOORPLANS / "comp_c040.json")


def comp_c040_manual_tpsc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tpsc65", "comp_c040", C040, FLOORPLANS / "comp_c040.json")


# ---- FRIDA-1, floorplan from ALIGN's placement


def comp_frida1_auto_tsmc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc65", "comp_frida1", FRIDA1, None)


def comp_frida1_auto_tsmc28(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc28", "comp_frida1", FRIDA1, None)


def comp_frida1_auto_ihp130(run_dir: Path) -> Path:
    return _comp(run_dir, "ihp130", "comp_frida1", FRIDA1, None)


def comp_frida1_auto_tower180(run_dir: Path) -> Path:
    return _comp(run_dir, "tower180", "comp_frida1", FRIDA1, None)


def comp_frida1_auto_lf150(run_dir: Path) -> Path:
    return _comp(run_dir, "lf150", "comp_frida1", FRIDA1, None)


def comp_frida1_auto_tpsc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tpsc65", "comp_frida1", FRIDA1, None)


# ---- c040, floorplan from ALIGN's placement


def comp_c040_auto_tsmc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc65", "comp_c040", C040, None)


def comp_c040_auto_tsmc28(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc28", "comp_c040", C040, None)


def comp_c040_auto_ihp130(run_dir: Path) -> Path:
    return _comp(run_dir, "ihp130", "comp_c040", C040, None)


def comp_c040_auto_tower180(run_dir: Path) -> Path:
    return _comp(run_dir, "tower180", "comp_c040", C040, None)


def comp_c040_auto_lf150(run_dir: Path) -> Path:
    return _comp(run_dir, "lf150", "comp_c040", C040, None)


def comp_c040_auto_tpsc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tpsc65", "comp_c040", C040, None)


# ---- frida1, its standard cells as transistors, floorplan from ALIGN's placement


def comp_frida1_gates_tsmc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc65", "comp_frida1", FRIDA1, None, gates=True)


def comp_frida1_gates_tsmc28(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc28", "comp_frida1", FRIDA1, None, gates=True)


def comp_frida1_gates_ihp130(run_dir: Path) -> Path:
    return _comp(run_dir, "ihp130", "comp_frida1", FRIDA1, None, gates=True)


def comp_frida1_gates_tower180(run_dir: Path) -> Path:
    return _comp(run_dir, "tower180", "comp_frida1", FRIDA1, None, gates=True)


def comp_frida1_gates_lf150(run_dir: Path) -> Path:
    return _comp(run_dir, "lf150", "comp_frida1", FRIDA1, None, gates=True)


def comp_frida1_gates_tpsc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tpsc65", "comp_frida1", FRIDA1, None, gates=True)


# ---- c040, its standard cells as transistors, floorplan from ALIGN's placement


def comp_c040_gates_tsmc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc65", "comp_c040", C040, None, gates=True)


def comp_c040_gates_tsmc28(run_dir: Path) -> Path:
    return _comp(run_dir, "tsmc28", "comp_c040", C040, None, gates=True)


def comp_c040_gates_ihp130(run_dir: Path) -> Path:
    return _comp(run_dir, "ihp130", "comp_c040", C040, None, gates=True)


def comp_c040_gates_tower180(run_dir: Path) -> Path:
    return _comp(run_dir, "tower180", "comp_c040", C040, None, gates=True)


def comp_c040_gates_lf150(run_dir: Path) -> Path:
    return _comp(run_dir, "lf150", "comp_c040", C040, None, gates=True)


def comp_c040_gates_tpsc65(run_dir: Path) -> Path:
    return _comp(run_dir, "tpsc65", "comp_c040", C040, None, gates=True)


# ---- one NMOS and one PMOS row cell, from each PDK's hand-written netlist


def mos_inv_tsmc65(run_dir: Path) -> Path:
    return _run(
        run_dir, "tsmc65", "mos_inv", ROOT / "pdk/tsmc65/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json"
    )


def mos_inv_tsmc28(run_dir: Path) -> Path:
    return _run(
        run_dir, "tsmc28", "mos_inv", ROOT / "pdk/tsmc28/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json"
    )


def mos_inv_ihp130(run_dir: Path) -> Path:
    return _run(
        run_dir, "ihp130", "mos_inv", ROOT / "pdk/ihp130/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json"
    )


def mos_inv_tower180(run_dir: Path) -> Path:
    return _run(
        run_dir, "tower180", "mos_inv", ROOT / "pdk/tower180/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json"
    )


def mos_inv_lf150(run_dir: Path) -> Path:
    return _run(run_dir, "lf150", "mos_inv", ROOT / "pdk/lf150/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json")


def mos_inv_tpsc65(run_dir: Path) -> Path:
    return _run(
        run_dir, "tpsc65", "mos_inv", ROOT / "pdk/tpsc65/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json"
    )


# ---- each case in all six PDKs


def comp_frida1_manual_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            comp_frida1_manual_tsmc65,
            comp_frida1_manual_tsmc28,
            comp_frida1_manual_ihp130,
            comp_frida1_manual_tower180,
            comp_frida1_manual_lf150,
            comp_frida1_manual_tpsc65,
        ),
    )


def comp_c040_manual_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            comp_c040_manual_tsmc65,
            comp_c040_manual_tsmc28,
            comp_c040_manual_ihp130,
            comp_c040_manual_tower180,
            comp_c040_manual_lf150,
            comp_c040_manual_tpsc65,
        ),
    )


def comp_frida1_auto_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            comp_frida1_auto_tsmc65,
            comp_frida1_auto_tsmc28,
            comp_frida1_auto_ihp130,
            comp_frida1_auto_tower180,
            comp_frida1_auto_lf150,
            comp_frida1_auto_tpsc65,
        ),
    )


def comp_c040_auto_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            comp_c040_auto_tsmc65,
            comp_c040_auto_tsmc28,
            comp_c040_auto_ihp130,
            comp_c040_auto_tower180,
            comp_c040_auto_lf150,
            comp_c040_auto_tpsc65,
        ),
    )


def comp_frida1_gates_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            comp_frida1_gates_tsmc65,
            comp_frida1_gates_tsmc28,
            comp_frida1_gates_ihp130,
            comp_frida1_gates_tower180,
            comp_frida1_gates_lf150,
            comp_frida1_gates_tpsc65,
        ),
    )


def comp_c040_gates_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir,
        (
            comp_c040_gates_tsmc65,
            comp_c040_gates_tsmc28,
            comp_c040_gates_ihp130,
            comp_c040_gates_tower180,
            comp_c040_gates_lf150,
            comp_c040_gates_tpsc65,
        ),
    )


def mos_inv_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(
        run_dir, (mos_inv_tsmc65, mos_inv_tsmc28, mos_inv_ihp130, mos_inv_tower180, mos_inv_lf150, mos_inv_tpsc65)
    )


ALL_PDKS = (
    comp_frida1_manual_all_pdks,
    comp_c040_manual_all_pdks,
    comp_frida1_auto_all_pdks,
    comp_c040_auto_all_pdks,
    comp_frida1_gates_all_pdks,
    comp_c040_gates_all_pdks,
    mos_inv_all_pdks,
)


def all_comp_layouts(run_dir: Path) -> Path:
    """The five ``*_all_pdks`` targets into ``run_dir/<target>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)


def main() -> None:
    """Create one output directory and run one named comparator layout target."""

    targets = {
        target.__name__: target
        for target in (
            comp_frida1_manual_tsmc65,
            comp_frida1_manual_tsmc28,
            comp_frida1_manual_ihp130,
            comp_frida1_manual_tower180,
            comp_frida1_manual_lf150,
            comp_frida1_manual_tpsc65,
            comp_c040_manual_tsmc65,
            comp_c040_manual_tsmc28,
            comp_c040_manual_ihp130,
            comp_c040_manual_tower180,
            comp_c040_manual_lf150,
            comp_c040_manual_tpsc65,
            comp_frida1_auto_tsmc65,
            comp_frida1_auto_tsmc28,
            comp_frida1_auto_ihp130,
            comp_frida1_auto_tower180,
            comp_frida1_auto_lf150,
            comp_frida1_auto_tpsc65,
            comp_c040_auto_tsmc65,
            comp_c040_auto_tsmc28,
            comp_c040_auto_ihp130,
            comp_c040_auto_tower180,
            comp_c040_auto_lf150,
            comp_c040_auto_tpsc65,
            comp_frida1_gates_tsmc65,
            comp_frida1_gates_tsmc28,
            comp_frida1_gates_ihp130,
            comp_frida1_gates_tower180,
            comp_frida1_gates_lf150,
            comp_frida1_gates_tpsc65,
            comp_c040_gates_tsmc65,
            comp_c040_gates_tsmc28,
            comp_c040_gates_ihp130,
            comp_c040_gates_tower180,
            comp_c040_gates_lf150,
            comp_c040_gates_tpsc65,
            mos_inv_tsmc65,
            mos_inv_tsmc28,
            mos_inv_ihp130,
            mos_inv_tower180,
            mos_inv_lf150,
            mos_inv_tpsc65,
            *ALL_PDKS,
            all_comp_layouts,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available comparator layout targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = ROOT / "build" / "layout" / "comp" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
