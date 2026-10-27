"""Comparator layouts in standard-cell rows: netlist, floorplan, ALIGN build and signoff per PDK.

``layout_named`` lays out one named instance (``flow.comp.sweep``'s ``@named``) in the PDKs by
ALIGN, each checked with DRC and LVS: from its hand-written floorplan
(``design/layout/comp_<name>.json``), or, ``auto``, by ALIGN on its own from the transistor netlist
with its library cells recognized. Every PDK runs whatever the others do; it raises at the end when
any failed (``failures.json``). ``layout_netlist`` and ``layout_floorplan`` give the sweep's layout
step (``flow.sweep.runner.layout``) an instance's netlists.

Tools: ``ALIGN_HOME`` (an ALIGN install); Calibre, Assura or KLayout as each PDK's signoff provider
(``pdk/<pdk>/signoff.py``) uses them.

    uv run python -m flow layout comp --instance frida1
"""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

from klayout import db

from flow.circuit import devices
from flow.layout.align.build import build as align_build
from flow.layout.pdkproc import in_pdk
from flow.layout.signoff import row_signoff

from .params import (
    STRUCTURE,
    Bias,
    Latch,
    OutputStage,
    Params,
)
from .subckt import Nets, netlist

ROOT = Path(__file__).resolve().parents[2]
FLOORPLANS = ROOT / "design" / "layout"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")

# where the ports leave the block, as in both comparator floorplans (circuit knowledge, not placement)
ESCAPE = {"up": ["inp", "inn"], "down": ["clk", "clkb", "outp", "outn"]}
# the structures with a hand-written floorplan (design/layout/comp_<name>.json): each latch (its
# floorplan named after it, comp_strongarm.json), and the dynamic-bias double tail (the modified double
# tail's latch, the input pair's tail switched onto C_TAIL, with C_P: flow.comp.sweep's dynamic_bias)
FLOORPLAN_CASES = {
    **{latch.name.lower(): {"latch": latch} for latch in Latch},
    "dynamic_bias": {"latch": Latch.DOUBLE_TAIL_MODIFIED, "bias": Bias.DYNAMIC},
}


def _structure(comp: Params) -> tuple[object, ...]:
    """The comparator's devices and wiring (``STRUCTURE``)."""
    return tuple(getattr(comp, key) for key in STRUCTURE)


def write_netlist(params: Params, path: Path, pdk, constant_from=None) -> Path:
    """The comparator after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.circuit.devices.write_netlist``)."""
    return devices.write_netlist(params, path, pdk, constant_from, generator=netlist, nets=Nets)


def layout_netlist(out_dir: Path, pdk: str, comp: Params) -> Path:
    """The all-transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), as a comparator is laid out without a floorplan (the sweep's
    layout step, ``flow.sweep.runner.layout_job``)."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(
        Params(**{**comp.__dict__, "output_stage": OutputStage.TRANSISTORS}), out_dir / "comp_transistors.sp", logic
    )
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "comp.sp")


def layout_floorplan(out_dir: Path, pdk: str, comp: Params) -> tuple[Path, Path] | None:
    """The hand-written floorplan of the instance's structure (``FLOORPLAN_CASES``:
    ``design/layout/comp_<name>.json``) with the netlist it places, the standard-cell output stage's;
    None where it has none."""

    floorplan = next(
        (
            path
            for name, structure in FLOORPLAN_CASES.items()
            if _structure(Params(**structure)) == _structure(comp)
            and (path := FLOORPLANS / f"comp_{name}.json").exists()
        ),
        None,
    )
    if floorplan is None:
        return None
    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    stdcells = Params(**{**comp.__dict__, "output_stage": OutputStage.STDCELLS})
    return write_netlist(stdcells, out_dir / f"{floorplan.stem}.sp", logic), floorplan


def _netlists(params: Params, pdk: str, out_dir: Path, name: str) -> tuple[Path, Path]:
    """The two netlists of a comparator in ``pdk``: standard-cell output stage and all-transistor.
    The file stem names the subcircuit."""

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    stage = lambda s: Params(**{**params.__dict__, "output_stage": s})
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
    """One design in one PDK by ALIGN into ``run_dir/align/``, signed off in
    ``run_dir/align/signoff/``: placed as its hand-written floorplan says, or, without one, by ALIGN
    on its own (it derives its constraints, places and routes)."""

    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    out = run_dir / "align"
    entry: dict[str, Any] = {}
    summary[f"{pdk}/align"] = entry
    try:
        gds = align_build(pdk, floorplan, netlist, out, name=name)  # named as the design
        entry.update(gds=str(gds), cell_um=_cell_um(gds))
        check = row_signoff(pdk, gds, netlist, floorplan, out / "signoff")
        entry.update(drc_violations=check.drc_violations, lvs_correct=check.lvs_correct)
        if check.drc_violations or not check.lvs_correct:
            failures[f"{pdk}/align"] = f"DRC {check.drc_violations} violations, LVS correct {check.lvs_correct}"
    except Exception as error:  # noqa: BLE001 - report the failure with every other PDK's
        entry["error"] = failures[f"{pdk}/align"] = repr(error)
        drc = out / "signoff" / "drc_violations.json"
        if drc.exists():  # DRC ran before the failure
            entry["drc_violations"] = sum(json.loads(drc.read_text())["violations"].values())
    return _finish(run_dir, summary, failures)


def _comp(run_dir: Path, pdk: str, name: str, params: Params, floorplan: Path | None) -> Path:
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


def _all_pdks(run_dir: Path, case: Callable[..., Path], *args: Any, pdks: tuple[str, ...] = PDKS) -> Path:
    """``case(run_dir / pdk, pdk, *args)`` in every PDK (or ``pdks``); every failure collected, the
    summaries merged."""

    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    for pdk in pdks:
        sub = run_dir / pdk
        try:
            case(sub, pdk, *args)
        except Exception as error:  # noqa: BLE001 - report every PDK
            found = sub / "failures.json"
            failures.update(json.loads(found.read_text()) if found.exists() else {pdk: repr(error)})
        if (sub / "summary.json").exists():
            summary.update(json.loads((sub / "summary.json").read_text()))
    return _finish(run_dir, summary, failures)


def layout_named(run_dir: Path, name: str, params: Params, *, auto: bool = False, pdks: tuple[str, ...] = PDKS) -> Path:
    """The named instance ``name`` in each of ``pdks`` by ALIGN, into ``run_dir/<pdk>/``:
    from its hand-written floorplan, or ``auto`` from ALIGN's placement."""

    floorplan = None if auto else FLOORPLANS / f"comp_{name}.json"
    if floorplan is not None and not floorplan.exists():
        raise FileNotFoundError(f"{floorplan}: no hand-written floorplan of {name}; lay it out from ALIGN's (auto)")
    return _all_pdks(run_dir, _comp, f"comp_{name}", params, floorplan, pdks=pdks)
