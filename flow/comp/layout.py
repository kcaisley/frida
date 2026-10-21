"""Comparator layouts in standard-cell rows: netlist, floorplan, build and signoff per PDK and tool.

A ``*_all_pdks`` function lays out one case in all six PDKs with all three tools (cIcCreator,
laygo, ALIGN), each checked with DRC and LVS.
Cases: the FRIDA-1 comparator and the size sweep's example double tail (c040), each from its
hand-written floorplan (``design/layout``, "manual") or laid out by ALIGN on its own from the
transistor netlist with its library cells recognized ("auto", ALIGN's placement the floorplan of
cIcCreator and laygo); the characterization's six topologies (``flow.comp.sim``: StrongARM,
triple tail and the double tails) at its sizing, each from its hand-written floorplan; and
``mos_inv`` (one NMOS and one PMOS row cell). Every (pdk, tool) runs whatever the others do;
the function raises at the end when any failed (``failures.json``).

Tools: ``CICPY`` (cicpy 0.3, with ``compile``), ``LAYGO_CLIENT`` (the hosted laygo server's
client, needs internet), ``ALIGN_HOME`` (an ALIGN install); Calibre, Assura or KLayout as each
PDK's signoff provider (``pdk/<pdk>/signoff.py``) uses them.

    uv run python -m flow comp.layout_c040_manual
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
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
BUILD: dict[str, Callable[..., Path]] = {"cic": cic_build, "laygo": laygo_build, "align": align_build}

# the example double tail ("c040"): the size sweep's topology 40 at the half profile, as
# `write_case_netlist("40_half", ...)` in flow.comp.subckt builds it
C040 = CompParams(**topologies()[40], **SIZE_PROFILES["half"], **LENGTHS)
# where the ports leave the block, as in both comparator floorplans (circuit knowledge, not placement)
ESCAPE = {"up": ["inp", "inn"], "down": ["clk", "clkb", "outp", "outn"]}


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
        raise RuntimeError(f"{len(failures)} layouts failed; see {path}")
    return run_dir


def _run(run_dir: Path, pdk: str, name: str, netlist: Path, floorplan: Path | None) -> Path:
    """One design in one PDK, the three tools into ``run_dir/<tool>/``, each signed off in
    ``run_dir/<tool>/signoff/``. Without a floorplan, ALIGN runs on its own first (it derives its
    constraints, places and routes) and its placement becomes the floorplan of cIcCreator and laygo
    (``run_dir/floorplan/``); with one, all three tools place as it says."""

    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    tools = list(BUILD)
    if floorplan is None:
        tools = ["align", *(t for t in tools if t != "align")]
    for tool in tools:
        out = run_dir / tool
        entry: dict[str, Any] = {}
        summary[f"{pdk}/{tool}"] = entry
        if floorplan is None and tool != "align":
            try:
                floorplan = align_floorplan(
                    run_dir / "align" / name, netlist, pdk, run_dir / "floorplan", name=name, escape=ESCAPE
                )
            except Exception as error:  # noqa: BLE001 - ALIGN's placement is the others' floorplan
                failures[f"{pdk}/floorplan"] = repr(error)
                del summary[f"{pdk}/{tool}"]
                break
        try:
            if tool == "align":  # named as the design, also without a floorplan
                gds = BUILD[tool](pdk, floorplan, netlist, out, name=name)
            else:
                assert floorplan is not None  # given, or from ALIGN's placement above
                gds = BUILD[tool](pdk, floorplan, netlist, out)
            entry.update(gds=str(gds), cell_um=_cell_um(gds))
            check = row_signoff(pdk, gds, netlist, floorplan, out / "signoff")  # ALIGN on its own: no floorplan yet
            entry.update(drc_violations=check.drc_violations, lvs_correct=check.lvs_correct)
            if check.drc_violations or not check.lvs_correct:
                failures[f"{pdk}/{tool}"] = f"DRC {check.drc_violations} violations, LVS correct {check.lvs_correct}"
        except Exception as error:  # noqa: BLE001 - report every independent tool failure
            entry["error"] = failures[f"{pdk}/{tool}"] = repr(error)
            drc = out / "signoff" / "drc_violations.json"
            if drc.exists():  # DRC ran before the failure
                entry["drc_violations"] = sum(json.loads(drc.read_text())["violations"].values())
    return _finish(run_dir, summary, failures)


def _comp(run_dir: Path, pdk: str, name: str, params: CompParams, floorplan: Path | None) -> Path:
    """A comparator: its netlists into ``run_dir/netlist/``, then ``_run``. A hand-written floorplan
    places the generator's standard-cell netlist (it names those cells). Without one, the
    transistor netlist with the library cells it contains recognized (flow/layout/stdcells.py):
    logic is always the PDK's library cells."""

    stdcells, transistors = _netlists(params, pdk, run_dir / "netlist", name)
    if floorplan is not None:
        netlist = stdcells
    else:
        netlist = in_pdk(
            pdk, "flow.layout.stdcells", "recognize_file", transistors, run_dir / "netlist" / f"{name}_recognized.sp"
        )
    return _run(run_dir, pdk, name, netlist, floorplan)


def _all_pdks(run_dir: Path, case: Callable[..., Path], *args: Any) -> Path:
    """``case(run_dir / pdk, pdk, *args)`` in every PDK; every failure collected, the summaries
    merged."""

    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    for pdk in PDKS:
        sub = run_dir / pdk
        try:
            case(sub, pdk, *args)
        except Exception as error:  # noqa: BLE001 - report every PDK
            found = sub / "failures.json"
            failures.update(json.loads(found.read_text()) if found.exists() else {pdk: repr(error)})
        if (sub / "summary.json").exists():
            summary.update(json.loads((sub / "summary.json").read_text()))
    return _finish(run_dir, summary, failures)


# ---- the characterization's six topologies (flow.comp.sim), hand-written floorplans


def _topology(run_dir: Path, pdk: str, topology: str) -> Path:
    """One of the characterization's topologies at its shared sizing, as ``comp_characterization``
    simulates it."""

    from flow.comp.sim import TOPOLOGIES, TOPOLOGY_SIZES

    name = f"comp_{topology}"
    return _comp(run_dir, pdk, name, CompParams(**TOPOLOGIES[topology], **TOPOLOGY_SIZES), FLOORPLANS / f"{name}.json")


def _mos_inv(run_dir: Path, pdk: str) -> Path:
    """One NMOS and one PMOS row cell, from the PDK's hand-written netlist."""

    return _run(run_dir, pdk, "mos_inv", ROOT / f"pdk/{pdk}/layout/netlists/mos_inv.sp", FLOORPLANS / "mos_inv.json")


# ---- each case in all six PDKs


def comp_frida1_manual_all_pdks(run_dir: Path) -> Path:
    """FRIDA-1, by its hand-written floorplan."""
    return _all_pdks(run_dir, _comp, "comp_frida1", FRIDA1, FLOORPLANS / "comp_frida1.json")


def comp_c040_manual_all_pdks(run_dir: Path) -> Path:
    """c040, by its hand-written floorplan."""
    return _all_pdks(run_dir, _comp, "comp_c040", C040, FLOORPLANS / "comp_c040.json")


def comp_strongarm_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _topology, "strongarm")


def comp_triple_tail_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _topology, "triple_tail")


def comp_double_tail_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _topology, "double_tail")


def comp_double_tail_self_timed_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _topology, "double_tail_self_timed")


def comp_double_tail_modified_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _topology, "double_tail_modified")


def comp_double_tail_modified_self_timed_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _topology, "double_tail_modified_self_timed")


def comp_frida1_auto_all_pdks(run_dir: Path) -> Path:
    """FRIDA-1, its floorplan from ALIGN's placement."""
    return _all_pdks(run_dir, _comp, "comp_frida1", FRIDA1, None)


def comp_c040_auto_all_pdks(run_dir: Path) -> Path:
    """c040, its floorplan from ALIGN's placement."""
    return _all_pdks(run_dir, _comp, "comp_c040", C040, None)


def mos_inv_all_pdks(run_dir: Path) -> Path:
    return _all_pdks(run_dir, _mos_inv)


ALL_PDKS = (
    comp_frida1_manual_all_pdks,
    comp_c040_manual_all_pdks,
    comp_strongarm_all_pdks,
    comp_triple_tail_all_pdks,
    comp_double_tail_all_pdks,
    comp_double_tail_self_timed_all_pdks,
    comp_double_tail_modified_all_pdks,
    comp_double_tail_modified_self_timed_all_pdks,
    comp_frida1_auto_all_pdks,
    comp_c040_auto_all_pdks,
    mos_inv_all_pdks,
)


def all_comp_layouts(run_dir: Path) -> Path:
    """The ``*_all_pdks`` functions into ``run_dir/<function>/``."""

    failures: dict[str, str] = {}
    for target in ALL_PDKS:
        try:
            target(run_dir / target.__name__)
        except Exception as error:  # noqa: BLE001 - run every case
            failures[target.__name__] = repr(error)
    return _finish(run_dir, {}, failures)
