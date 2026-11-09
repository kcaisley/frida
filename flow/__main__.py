r"""The flow's one entry point: a block's steps, from one to another, over its instances.

    python -m flow <block> --to STEP [--from STEP] [--run NAME|DIR] [--instance I ...] [--pdk P ...] [--workers N] [--predict]
    python -m flow opt <block> --problem P [--pdk P] [--budget N] [--workers N] [--best N] [--finalists N] [--table]
    python -m flow web.serve

A step is one tool: it takes its inputs and makes its outputs, and its configuration is the tool's
own, in the block's Python files and the kit's (the runs a sweep states, a layout's placement, which
signoff a kit takes), never a flag here. The steps make a small graph, each after those it needs:

    netlist -> sim -> record -> figures
               sim -> circuit          record -> table
    netlist -> layout -> drc -> lvs -> pex
    sim, pex -> pexsim
    record, pex -> page

``--to`` runs the steps that lead from ``--from`` (``netlist`` by default) to it, both included:
``--to record`` simulates and records, ``--to lvs`` lays out and signs off without extraction,
``--from table --to table`` exports what the runs hold; with ``record/`` deleted, ``--from record
--to record`` analyses again what ``sim`` kept. ``circuit`` adds the circuit simulator's runs of a
block whose full characterization is behavioral (the ADC's Spectre runs) and records again; it
takes picked instances alone. ``figures`` draws a record's figures, or, over a ``--run DIR`` of the
lab's captures, the figures the block's analyses make of them. ``layout`` runs the block's own
``lay_out`` where it has a ``layout.py`` (with the signoff it plans, FRIDA-1's Calibre:
``flow.layout.signoff.write_plan``), else ALIGN through the shared step (its netlists and
constraints too: the netlist step's edge to it only orders them); ``drc``, ``lvs`` and ``pex``
run, each in its folder, that plan, else the checker the kit names
(``flow.layout.signoff.checker``: the open tools, else Calibre), on its GDS. ``pexsim`` simulates
the sim step's runs again with the open extractor's capacitances back-annotated onto the schematic
(``flow.layout.annotate``: each layout net found on its schematic net through LVS; each run's DUT
a flat copy with the capacitors, ``flow.sweep.runner.simulate``) and records them alike, a record
of its own beside the instance's (``pexsim/instance.json``: the same metric names, the
annotation's totals); it refuses an extraction more than a small share of whose capacitance has no
schematic net or one the DUT lacks, and testbenches none of which holds the DUT, and leaves an extraction with devices and RC (a kit's) to the block's own
simulation of it (the ADC's circuit step). ``page`` writes the instance's page from whatever of
its record and layout exists.

A run is ``build/<block>/<run>/``, each instance in ``<pdk>/<name>/`` there (a named instance by its
name, a grid's by its digest), a folder a step: ``netlist/``, ``sim/<run>/``, ``circuit/<run>/``,
``record/``, ``figures/``, ``layout/``, ``drc/``, ``lvs/``, ``pex/``, ``pexsim/<run>/``,
``page/``; its record, ``instance.json``, beside them, which the viewer's table reads. ``--from netlist`` makes a new run
(named ``--run NAME``, else by its stamp); a later ``--from`` takes the newest run, or the one
``--run`` names (a name under ``build/<block>/`` or a directory), and the instances in it. A step
skips an instance whose output is complete and not older than what it was made from (make's rule),
so a run stopped part way resumes where it stopped; to make a step again, delete its folder or start
a new run. A step whose inputs are missing fails, naming the command that makes them.

``--instance`` picks a named instance, the label of one of the design space's (``grid(name,
parameter=value, ...)``) or a digest, else the design space is run; ``--pdk``, else every PDK
the block admits. ``--predict`` prints the run, the instances and the steps each would run, with a
rough count, and runs nothing. ``opt`` searches one of a block's problems (``flow.opt.runner``), and
``web.serve`` serves the viewer on http://127.0.0.1:8765.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from enum import Enum, auto
from importlib import import_module
from pathlib import Path
from typing import Any


class Step(Enum):
    """One tool's step over an instance (``TABLE``: over a run), in an order that puts each after
    the steps it needs (``needs``); its folder in an instance's directory is its name."""

    NETLIST = auto()
    SIM = auto()
    CIRCUIT = auto()
    RECORD = auto()
    FIGURES = auto()
    TABLE = auto()
    LAYOUT = auto()
    DRC = auto()
    LVS = auto()
    PEX = auto()
    PEXSIM = auto()
    PAGE = auto()

    def __str__(self) -> str:
        return self.name.lower()

    @property
    def needs(self) -> tuple[Step, ...]:
        """The steps whose outputs this one takes."""
        match self:
            case Step.NETLIST:
                return ()
            case Step.SIM | Step.LAYOUT:
                return (Step.NETLIST,)
            case Step.CIRCUIT:
                return (Step.SIM,)
            case Step.RECORD:
                return (Step.NETLIST, Step.SIM)
            case Step.FIGURES | Step.TABLE:
                return (Step.RECORD,)
            case Step.DRC:
                return (Step.LAYOUT,)
            case Step.LVS:
                return (Step.DRC,)
            case Step.PEX:
                return (Step.LVS,)
            case Step.PEXSIM:
                return (Step.SIM, Step.LVS, Step.PEX)
            case Step.PAGE:
                return (Step.RECORD, Step.PEX)

    @property
    def ancestors(self) -> set[Step]:
        """This step and every step it needs, directly or through others."""
        return {self}.union(*(need.ancestors for need in self.needs))


def between(start: Step, stop: Step) -> list[Step]:
    """The steps from ``start`` to ``stop``, both included, in the order they run: those that need
    ``start`` and that ``stop`` needs."""
    steps = [step for step in Step if start in step.ancestors and step in stop.ancestors]
    if not steps:
        raise SystemExit(f"--from {start} does not lead to --to {stop}: {stop} needs {_needed(stop)}")
    return steps


def _needed(step: Step) -> str:
    """The steps ``step`` needs, as a sentence's words."""
    return ", ".join(str(need) for need in sorted(step.ancestors - {step}, key=lambda s: s.value)) or "nothing"


def pipeline_blocks() -> list[str]:
    """The blocks on the pipeline: those whose ``sweep.py`` gives ``runs`` (one that no longer
    imports, a block not yet ported, gives none)."""
    from flow.sweep import runner

    def on_pipeline(block: str) -> bool:
        try:
            return hasattr(import_module(f"flow.{block}.sweep"), "runs")
        except ImportError:
            return False

    return [block for block in runner.sweep_blocks() if on_pipeline(block)]


# ---------------------------------------------------------------- an instance's steps


@dataclass(frozen=True)
class Job:
    """One instance's steps in a run: its block, PDK, name in the run (a named instance's name, a
    grid's digest), label and parameters, its directory, the steps to run, and the run as
    ``--run`` takes it (for the commands a failure names)."""

    block: str
    pdk: str
    name: str
    label: str
    params: Any
    out: Path
    steps: tuple[Step, ...]
    run: str


def _marker(out: Path, step: Step) -> Path:
    """A step's record of its run on an instance: ``<step>/step.json``, written once it ends."""
    return out / str(step) / "step.json"


def _ended(out: Path, step: Step) -> dict | None:
    """The step's record on this instance where it ended without error, else None."""
    path = _marker(out, step)
    if not path.exists():
        return None
    ended = json.loads(path.read_text())
    return ended if ended.get("error") is None else None


def done(out: Path, step: Step) -> bool:
    """Whether the step's output on this instance is complete: it ended without error, after each
    step it needs ended without error, each of those complete too (make's rule: made again where
    what it was made from, or what that was made from, is newer, failed or gone). The page shows
    whatever exists: complete unless a step it shows ended after it."""
    ended = _ended(out, step)
    if ended is None:
        return False
    if step is Step.PAGE:
        shown = (_marker(out, need) for need in step.ancestors - {step})
        return all(json.loads(path.read_text())["finished"] <= ended["finished"] for path in shown if path.exists())
    for need in step.needs:
        made = _ended(out, need)
        if made is None or made["finished"] > ended["finished"] or not done(out, need):
            return False
    return True


def _mark(out: Path, step: Step, started: float, error: str | None = None, **outputs: Any) -> None:
    """The step's record on this instance: when it finished, its seconds, its error and outputs."""
    path = _marker(out, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    finished = time.time()
    entry = {"step": str(step), "finished": finished, "seconds": round(finished - started, 1), "error": error}
    path.write_text(json.dumps({**entry, **outputs}, indent=1) + "\n")


def _command(job: Job, step: Step) -> str:
    """The command that makes ``step``'s output on this instance (the steps before it that are
    complete skipped)."""
    return f"python -m flow {job.block} --to {step} --run {job.run} --pdk {job.pdk} --instance {job.name}"


def _missing(job: Job, step: Step) -> str | None:
    """What ``step`` needs on this instance that is not complete, and the command that makes it;
    None where it has all it needs. The page takes whatever exists of the instance's record and
    layout, one of them at least."""
    if step is Step.PAGE:
        if done(job.out, Step.RECORD) or done(job.out, Step.LAYOUT):
            return None
        return f"page needs the record or the layout: {_command(job, Step.RECORD)}, or --to pex"
    for need in step.needs:
        if not done(job.out, need):
            return f"{step} needs its {need} step's output: {_command(job, need)}"
    return None


def _outputs(out: Path, step: Step) -> dict:
    """What a step that ended made on this instance (its ``step.json``), else nothing."""
    return _ended(out, step) or {}


def _netlist(job: Job) -> dict:
    """The circuit as simulated and its size (``flow.sweep.runner.write_netlist``)."""
    from flow.sweep import runner

    runner.write_netlist(job.block, job.pdk, job.params, job.out / "netlist")
    return {}


def _sim(job: Job) -> dict:
    """Each of the instance's testbench runs simulated and its measurement kept (``sim/<run>/``)."""
    from flow.sweep import runner

    runs = runner.runs_of(job.block, job.pdk, job.params)
    runner.simulate(job.block, job.pdk, runs, job.out / "sim")
    return {"runs": list(runs)}


def _fresh(out: Path, step: Step) -> Path:
    """The step's folder, emptied where the step ended before (its output out of date, made again
    whole); a step that failed or stopped part way keeps what it made, which it then reuses (the
    sim step its kept measurements)."""
    import shutil

    if _ended(out, step) is not None:
        shutil.rmtree(out / str(step))
    return out / str(step)


def _record(job: Job, circuit: dict[str, Path] | None = None) -> dict:
    """The instance's record from the measurements its sim step kept, and its circuit step's
    (``circuit``, else those of a complete circuit step), as ``instance.json``."""
    from flow import pipeline
    from flow.sweep import runner

    out = job.out
    files = {run: out / "sim" / run / "result.h5" for run in json.loads(_marker(out, Step.SIM).read_text())["runs"]}
    if circuit is None and done(out, Step.CIRCUIT):
        runs = json.loads(_marker(out, Step.CIRCUIT).read_text())["runs"]
        circuit = {run: out / "circuit" / run / "result.h5" for run in runs}
    ran = sum(json.loads(_marker(out, step).read_text())["seconds"] for step in (Step.NETLIST, Step.SIM))
    runner.record(
        job.block,
        job.pdk,
        job.params,
        out,
        {**files, **(circuit or {})},
        json.loads((out / "netlist" / "geometry.json").read_text()),
        label=job.label,
        name=job.name,
        level=pipeline.Level.CIRCUIT if circuit else pipeline.Level.FULL,
        netlist=out / "netlist" / f"{job.block}.cdl",
        seconds=ran,
    )
    return {"circuit": bool(circuit)}


def _circuit(job: Job) -> dict:
    """The circuit simulator's runs of the instance (``flow.sweep.runner.circuit_runs``) simulated
    and kept (``circuit/<run>/``), then its record made again with them."""
    from flow.sweep import runner

    runs = runner.circuit_runs(job.block, job.pdk, job.params)
    files = runner.simulate(job.block, job.pdk, runs, job.out / "circuit")
    started = time.time()
    _mark(job.out, Step.RECORD, started, **_record(job, files))
    _join_layout(job)
    return {"runs": list(runs)}


def _figures(job: Job) -> dict:
    """Each of the record's figures (its details, ``flow.pipeline.Plot`` specs) drawn by matplotlib
    into ``figures/`` (``flow.plot.render``)."""
    from flow.pipeline import Plot
    from flow.plot import render

    record = json.loads((job.out / "instance.json").read_text())
    paths = [
        path
        for detail in record["details"]
        for path in render(Plot.from_json(detail), job.out / "figures" / detail["name"])
    ]
    return {"figures": [str(path.relative_to(job.out)) for path in paths]}


def _layout(job: Job) -> dict:
    """The instance laid out into ``layout/``: by its block's own ``lay_out`` where it has a
    ``layout.py`` (``flow.layout.step.lay_out_own``: the ADC's block assembly, or a FRIDA-1
    flavor's tape-out layout with its signoff plan, which the drc, lvs and pex steps run), else by
    ALIGN through the shared layout step (``flow.layout.step.lay_out_align``)."""
    from flow.layout import step

    if step.own_layout(job.block):
        return step.lay_out_own(job.block, job.pdk, job.params, job.out / "layout")
    # the design by its instance (a top cell of its own: COMP_FRIDA1_0), as the GDS of several
    # instances open or merge in one layout
    return step.lay_out_align(job.block, job.pdk, job.params, job.out / "layout", f"{job.block}_{job.name}")


def _plan(job: Job):
    """The signoff the block's own ``lay_out`` planned (``flow.layout.signoff.write_plan``), else
    None."""
    from flow.layout.signoff import read_plan

    path = _outputs(job.out, Step.LAYOUT).get("plan")
    return read_plan(Path(path)) if path else None


def _drc(job: Job) -> dict:
    """DRC of the layout's GDS into ``drc/``: as its ``lay_out`` planned it (``planned_drc``), else
    by the checker its kit names (``flow.layout.signoff.checker``: the open tools by default); its
    violations a count, not a failure."""
    from flow.layout import signoff

    laid, plan = _outputs(job.out, Step.LAYOUT), _plan(job)
    if plan is not None:
        return signoff.planned_drc(plan, job.out / "drc")
    source = Path(laid["source"]) if laid.get("source") else None
    checker = signoff.checker(job.pdk, job.block)
    return signoff.drc(job.pdk, Path(laid["gds"]), job.out / "drc", checker, source=source)


def _lvs(job: Job) -> dict:
    """LVS of the layout's GDS against its LVS source into ``lvs/``: as its ``lay_out`` planned it
    (``planned_lvs``: an expected mismatch among its warnings), else by its kit's checker; not run
    where the layout has no source (blocks side by side, unconnected)."""
    from flow.layout import signoff

    laid, plan = _outputs(job.out, Step.LAYOUT), _plan(job)
    if plan is not None:
        return signoff.planned_lvs(plan, job.out / "lvs")
    if not laid.get("source"):
        return {"lvs_correct": None, "skipped": "no LVS source: its blocks side by side, unconnected"}
    checker = signoff.checker(job.pdk, job.block)
    return signoff.lvs(job.pdk, Path(laid["gds"]), Path(laid["source"]), job.out / "lvs", checker)


def _pex(job: Job) -> dict:
    """The layout's extraction into ``pex/``: as its ``lay_out`` planned it (``planned_pex``, against
    its PEX source), else ``flow.layout.step.extracted`` (KLayout-PEX by the engine its kit names for
    the block, FasterCap by default, ``flow.layout.signoff.engine``; or the kit's extractor where its
    kit names Calibre), its engine among its outputs; not run where LVS was not (no source),
    refused where LVS found the layout other than its netlist (a planned signoff's LVS step holds
    it to its expectation)."""
    from flow.layout import signoff, step

    laid, checked, plan = _outputs(job.out, Step.LAYOUT), _outputs(job.out, Step.LVS), _plan(job)
    if plan is not None:
        return signoff.planned_pex(plan, job.out / "pex")
    if checked.get("skipped"):
        return {"skipped": checked["skipped"]}
    if checked.get("lvs_correct") is False:
        raise RuntimeError(f"LVS found the layout other than its netlist ({checked['lvs_report']}): not extracted")
    gds, engine = Path(laid["gds"]), signoff.engine(job.pdk, job.block)
    return step.extracted(job.pdk, gds, gds.stem, job.out / "pex", signoff.checker(job.pdk, job.block), engine=engine)


def _pexsim(job: Job) -> dict:
    """The instance's runs simulated again with its extraction back-annotated (``pexsim/<run>/``)
    and recorded alike (``pexsim/instance.json``: the record's shape and metric names, the
    annotation's totals beside them): the extraction's capacitors, each net found on the
    schematic's through LVS (``flow.layout.annotate``), in each testbench's DUT
    (``flow.sweep.runner.simulate``). Not run where the layout was not extracted, nor for an
    extraction with devices and RC (a kit's: a block's own simulation of it, the ADC's circuit
    step's); refused where more than a small share of the capacitance has no schematic net. The
    record's annotation names the extractor (its engine)."""
    from flow.layout import annotate
    from flow.sweep import runner

    extracted, checked = _outputs(job.out, Step.PEX), _outputs(job.out, Step.LVS)
    if extracted.get("skipped"):
        return {"skipped": f"no extraction ({extracted['skipped']})"}
    if "nets" not in extracted:
        return {"skipped": f"{extracted['extractor']} extraction has devices and RC, not capacitances to back-annotate"}
    if "probes" not in extracted:
        made = f"delete {runner._shown(job.out / 'pex')}, then {_command(job, Step.PEX)}"
        raise RuntimeError(f"its extraction has no net probes (made before them): make it again, {made}")
    found = annotate.annotation(Path(extracted["netlist"]), Path(extracted["probes"]), Path(checked["lvs_report"]))
    runs = runner.runs_of(job.block, job.pdk, job.params)
    for kept in (job.out / "pexsim").glob("*/annotation.json"):  # a failed pexsim's, kept to resume
        if kept.stat().st_mtime < _marker(job.out, Step.PEX).stat().st_mtime:  # of an extraction since redone
            (kept.parent / "result.h5").unlink(missing_ok=True)
    began = time.monotonic()
    files = runner.simulate(job.block, job.pdk, runs, job.out / "pexsim", annotation=found)
    ran = time.monotonic() - began
    added = {run: job.out / "pexsim" / run / "annotation.json" for run in runs}
    added = {run: json.loads(path.read_text()) for run, path in added.items() if path.exists()}
    if not any(entry["instances"] for entry in added.values()):
        dut = next((entry["dut"] for entry in added.values()), job.block)
        raise RuntimeError(f"no testbench of {job.block} instantiates {dut} directly: nothing was back-annotated")
    summary = {
        "extractor": extracted["extractor"],
        **found.summary(),
        **next((entry for entry in added.values() if entry["instances"]), {}),
        "unannotated": [run for run in runs if not added.get(run, {}).get("instances")],
    }
    record = runner.record(
        job.block,
        job.pdk,
        job.params,
        job.out / "pexsim",
        files,
        json.loads((job.out / "netlist" / "geometry.json").read_text()),
        label=job.label,
        name=job.name,
        netlist=job.out / "netlist" / f"{job.block}.cdl",
        seconds=ran,
    )
    runner.write_record(job.out / "pexsim" / "instance.json", {**record, "annotation": summary})
    return {"runs": list(runs), **summary}


def _page(job: Job) -> dict:
    """The instance's page (``flow.web.page.page``) in ``page/``: its record and whatever of its
    layout exists."""
    from flow.web.page import page

    (job.out / "page").mkdir(parents=True, exist_ok=True)
    return {"page": str(page(job.out, job.out / "page" / "page.html").relative_to(job.out))}


def _body(step: Step):
    """The function that runs ``step`` on one instance, None for one that runs over a run
    (``TABLE``)."""
    return {
        Step.NETLIST: _netlist,
        Step.SIM: _sim,
        Step.CIRCUIT: _circuit,
        Step.RECORD: _record,
        Step.FIGURES: _figures,
        Step.LAYOUT: _layout,
        Step.DRC: _drc,
        Step.LVS: _lvs,
        Step.PEX: _pex,
        Step.PEXSIM: _pexsim,
        Step.PAGE: _page,
    }.get(step)


def _made(ended: dict) -> dict:
    """A step's outputs, from its ``step.json``: its record of the run (``_mark``'s) left out."""
    return {key: value for key, value in ended.items() if key not in ("step", "finished", "seconds", "error")}


def _join_layout(job: Job) -> None:
    """The layout steps' outcome joined to the instance's record (``instance.json``, a record of
    the layout alone where it is not characterized, so the viewer's table and
    ``flow.sweep.lookup.laid_out`` find it): its GDS, LVS source, size, router, signoff, extraction,
    the layout step's error and each step's seconds; a characterized record also its layout area
    and density. Nothing where it is not laid out."""
    from flow.sweep import runner

    marked = {step: _marker(job.out, step) for step in (Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX)}
    if not marked[Step.LAYOUT].exists():
        return
    made = {step: json.loads(path.read_text()) for step, path in marked.items() if path.exists()}
    ended = {step: made[step] for step in made if done(job.out, step)}
    laid, drc, lvs, pex = (ended.get(step, {}) for step in marked)
    path = job.out / "instance.json"
    record = (
        json.loads(path.read_text())
        if path.exists()
        else runner._base_record(job.block, job.pdk, job.params, job.label, job.name)
    )
    width, height = laid.get("cell_um") or (None, None)
    record["layout"] = {
        "gds": runner._shown(laid["gds"]) if laid.get("gds") else None,
        "netlist": runner._shown(laid["source"]) if laid.get("source") else None,
        "w_um": width,
        "h_um": height,
        "floorplan": None if not laid else "lay_out" if "plan" in laid else "generator" if laid["placed"] else None,
        "router": laid.get("router"),
        "route_shorts": laid.get("route_shorts"),
        "signoff": drc.get("checker"),
        "drc_violations": drc.get("violations"),
        "lvs_correct": lvs.get("lvs_correct"),
        "warnings": lvs.get("warnings"),
        "pex": runner._shown_pex(_made(pex)) if pex else None,
        "error": made[Step.LAYOUT].get("error"),
        "seconds": round(sum(entry["seconds"] for entry in made.values()), 1),
        "steps": {str(step): {"seconds": entry["seconds"], "error": entry["error"]} for step, entry in made.items()},
    }
    if record["metrics"] and width:
        gate = record["metrics"].get("device_area_um2")
        record["metrics"].update(layout_area_um2=width * height, density=gate / (width * height) if gate else None)
    runner.write_record(path, record)


def _brief(step: Step, outputs: dict) -> str:
    """What a step found, for its outcome's line: a layout's size, DRC's violations, LVS's verdict,
    an extraction's nets."""
    if outputs.get("skipped"):
        return f" (not run: {outputs['skipped']})"
    match step:
        case Step.LAYOUT:
            return f" ({' x '.join(f'{v:g}' for v in outputs['cell_um'])} um)"
        case Step.DRC:
            return f" ({_count(outputs['violations'], 'violation')}, {outputs['checker']})"
        case Step.LVS:
            correct = outputs["lvs_correct"]
            verdict = "no deck" if correct is None else "match" if correct else "no match"
            return f" ({verdict}, {outputs['lvs_checker'] or '-'})"
        case Step.PEX:
            return f" ({len(outputs['nets'])} nets)" if "nets" in outputs else f" ({outputs['extractor']})"
        case Step.PEXSIM:
            return (
                f" ({_count(len(outputs['runs']), 'run')}, {outputs.get('added_f', 0.0) * 1e15:.4g} fF added, "
                f"{outputs['unmapped_share']:.1%} of the extraction on no schematic net)"
            )
    return ""


def run_steps(job: Job) -> list[str]:
    """The job's steps on its instance, in order, in this (fresh) process: each skipped where its
    output is complete (``done``), failed where what it needs is missing (``_missing``), else run
    in its folder (emptied where it ended before: ``_fresh``), a layout step's log, the flow's own
    lines, in it (``<step>/step.log``; each tool's own log beside its results). A failure leaves
    the steps after it not run (the page, which takes whatever exists, runs); a characterization
    step's failure (netlist, sim, record) is also the instance's record
    (``flow.sweep.runner.failed_record``), and a layout step's joins it (``_join_layout``), so the
    viewer's table shows it. Each step's outcome, a line each."""
    from contextlib import nullcontext

    from flow.layout import logs
    from flow.sweep import runner

    outcomes: list[str] = []
    failed: set[Step] = set()
    for step in job.steps:
        if failed & step.ancestors and step is not Step.PAGE:
            failed.add(step)
            outcomes.append(f"{step} not run")
            continue
        if done(job.out, step):
            outcomes.append(f"{step} done")
            continue
        missing = _missing(job, step)
        if missing:
            failed.add(step)
            outcomes.append(f"{step} failed: {missing}")
            continue
        started = time.time()
        folder = _fresh(job.out, step)
        logged = step in (Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX)
        try:
            with logs.instance_log(folder / "step.log") if logged else nullcontext():
                outputs = _body(step)(job)
        except Exception:  # noqa: BLE001 - every instance reports its own failure
            error = traceback.format_exc(limit=6)[-4000:]
            _mark(job.out, step, started, error=error)
            if step in (Step.NETLIST, Step.SIM, Step.RECORD):
                runner.failed_record(
                    job.block, job.pdk, job.params, job.out, f"{step}: {error}", label=job.label, name=job.name
                )
            if logged or step is Step.RECORD:
                _join_layout(job)
            failed.add(step)
            outcomes.append(f"{step} failed: {error.strip().splitlines()[-1]}")
            continue
        _mark(job.out, step, started, **outputs)
        if logged or step is Step.RECORD:
            _join_layout(job)
        outcomes.append(f"{step} ok in {time.time() - started:.1f} s{_brief(step, outputs)}")
    return outcomes


# ---------------------------------------------------------------- a run's instances


def _run_dir(block: str, value: str | None, start: Step) -> tuple[Path, str]:
    """The run the steps work in, and how it was found: ``--run``'s (a name under
    ``build/<block>/``, or a directory), a new one where the steps start at the netlist, else the
    block's newest."""
    from flow.sweep import runner

    if value is not None:
        path = Path(value).absolute() if "/" in value or value.startswith(".") else runner.RUNS_DIR / block / value
        if start is not Step.NETLIST and not path.is_dir():
            raise SystemExit(f"no run {value} of {block} ({path}): python -m flow {block} --to netlist --run {value}")
        return path, "resumed" if path.is_dir() else "new"
    if start is Step.NETLIST:
        return runner.RUNS_DIR / block / _stamp(), "new"
    try:
        return runner.newest_run(block), "the latest"
    except FileNotFoundError:
        raise SystemExit(f"no run of {block} yet to start at {start}: python -m flow {block} --to {start}") from None


def _stamp() -> str:
    """Now, as a new run's name: ``YYYYmmdd_HHMMSS``."""
    from datetime import datetime

    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def _run_name(block: str, run: Path) -> str:
    """The run as ``--run`` takes it: its name where it is under ``build/<block>/``, else its path."""
    from flow.sweep import runner

    return run.name if run.parent == runner.RUNS_DIR / block else str(run)


def _pdks(block: str, names: list[str] | None, given: list[str] | None, run: Path, reused: bool) -> list[str]:
    """The PDKs to run in: those given, else a reused run's own (its instances' PDKs), else every
    PDK in which the block admits an instance (one whose kit this checkout lacks left out)."""
    from flow.sweep import runner

    if given:
        return list(given)
    if reused:
        return [pdk for pdk in runner.PDKS if (run / pdk).is_dir()]
    found = []
    for pdk in runner.PDKS:
        try:
            if runner.labelled_space(block, pdk) or names:
                found.append(pdk)
        except (LookupError, ModuleNotFoundError):  # a design space of a kit this checkout lacks
            continue
    return found


def instances(block: str, pdk: str, names: list[str] | None, run: Path, reused: bool) -> dict[str, tuple[str, Any]]:
    """The instances to run in ``pdk``, by their name in the run (a named instance's name, a grid's
    digest), with their labels and parameters: those ``names`` pick (``flow.sweep.runner.select``),
    else a reused run's own (those its design still has), else the design space."""
    from flow import pipeline
    from flow.sweep import runner

    named = pipeline.names(import_module(f"flow.{block}.sweep"))
    if names:
        picked = runner.select(block, pdk, names)
    elif reused:
        folders = sorted(path for path in (run / pdk).iterdir() if path.is_dir()) if (run / pdk).is_dir() else []
        known = set(named) | set(runner.labelled_space(block, pdk))
        for folder in folders:
            if folder.name not in known:
                print(f"{folder}: not in {block}'s design any more, left out")
        picked = runner.select(block, pdk, [folder.name for folder in folders if folder.name in known])
    else:
        picked = runner.labelled_space(block, pdk)
    return {(label if label in named else ident): (label, params) for ident, (label, params) in picked.items()}


def _pending(job: Job) -> tuple[list[Step], dict[Step, str]]:
    """The job's steps that would run: each whose output is not complete, or that needs one that
    would run (made again after it); and those of them that would fail, with why: what they need
    neither complete nor to run (``_missing``), or a step they need that would fail (not run; the
    page, which takes whatever exists, excepted)."""
    pending: list[Step] = []
    failing: dict[Step, str] = {}
    for step in job.steps:
        if done(job.out, step) and not any(need in pending for need in step.needs):
            continue
        pending.append(step)
        if step is Step.PAGE:
            shown = (Step.RECORD, Step.LAYOUT)
            if not any(done(job.out, s) or (s in pending and s not in failing) for s in shown):
                failing[step] = _missing(job, step) or "page needs the record or the layout"
        elif any(need in failing for need in step.needs):
            failing[step] = f"not run, as {next(need for need in step.needs if need in failing)} fails"
        elif any(need not in pending and not done(job.out, need) for need in step.needs):
            failing[step] = _missing(job, step) or "a step it needs is not complete"
    return pending, failing


def _simulations(job: Job, pending: list[Step]) -> int:
    """How many testbench runs the job's pending steps would simulate (those kept already not)."""
    from flow.sweep import runner

    runs = {}
    if Step.SIM in pending:
        runs |= {f"sim/{n}": tb for n, tb in runner.runs_of(job.block, job.pdk, job.params).items()}
    if Step.CIRCUIT in pending:
        runs |= {f"circuit/{n}": tb for n, tb in runner.circuit_runs(job.block, job.pdk, job.params).items()}
    if Step.PEXSIM in pending:
        runs |= {f"pexsim/{n}": tb for n, tb in runner.runs_of(job.block, job.pdk, job.params).items()}
    return sum(not (job.out / name / "result.h5").exists() for name in runs)


def _pool(workers: int):
    """A pool of fresh processes, one an instance: hdl21 compiles a generated module in place, for
    one PDK."""
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context

    return ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1)


def steps(args: argparse.Namespace) -> None:
    """Run ``args``' steps (``parser``) over the instances it picks, or print them (``--predict``)."""
    from flow.sweep import runner

    start, stop = Step[args.start.upper()], Step[args.to.upper()]
    chosen = between(start, stop)
    if Step.CIRCUIT in chosen and not args.instances:
        raise SystemExit("the circuit step runs the circuit simulator: pick the instances (--instance I ...)")
    run, found = _run_dir(args.block, args.run, start)
    if chosen == [Step.FIGURES] and _captures(run):
        _capture_figures(args.block, run, args.predict)
        return
    reused = found != "new" and start is not Step.NETLIST
    name = _run_name(args.block, run)
    jobs = []
    for pdk in _pdks(args.block, args.instances, args.pdks, run, reused):
        try:
            picked = instances(args.block, pdk, args.instances, run, reused)
        except LookupError as error:
            raise SystemExit(str(error)) from None
        each = tuple(step for step in chosen if step is not Step.TABLE)
        jobs += [
            Job(args.block, pdk, n, label, params, run / pdk / n, each, name) for n, (label, params) in picked.items()
        ]
    if not jobs:
        raise SystemExit(f"no instance of {args.block} to run in {', '.join(args.pdks or runner.PDKS)}")
    if Step.CIRCUIT in chosen and not any(runner.circuit_runs(j.block, j.pdk, j.params) for j in jobs):
        raise SystemExit(f"{args.block} has no circuit simulator runs beyond its full ones: its sim step runs them")
    print(f"{args.block}: {found} run {runner._shown(run)}; steps {', '.join(map(str, chosen))}")
    if args.predict:
        _predict(jobs, chosen)
        return
    if found == "new":  # a run from before run.json keeps its time, its name's stamp
        runner.new_run(args.block, run_dir=run)
    failures = _run_jobs(jobs, args.workers) if jobs[0].steps else []
    if Step.TABLE in chosen:
        unrecorded = [job for job in jobs if not (job.out / "instance.json").exists()]
        if unrecorded:
            raise SystemExit(
                f"table needs every instance's record, {len(unrecorded)} of {len(jobs)} have none: "
                f"python -m flow {args.block} --to record --run {name}"
            )
        runner.table([args.block], args.workers, run=run)
    if failures:
        raise SystemExit(f"{len(failures)} of {len(jobs)} instances failed; the first: {failures[0]}")


def _captures(run: Path) -> bool:
    """Whether ``run`` is a directory of captures (the lab's, ``flow.scans.runner``'s: HDF5 files
    beneath it, through linked folders too: a study's links to its campaigns), not a run of
    instances."""
    from flow.plot import capture_files

    return not (run / "run.json").exists() and not list(run.glob("*/*/instance.json")) and bool(capture_files(run))


def _capture_figures(block: str, run: Path, predict: bool) -> None:
    """The figures step over a directory of captures: each figure the block's analyses make of
    them (``flow.plot.figures``) drawn into ``run/figures/``, a line each; make's rule as an
    instance's step (``run/figures/step.json``)."""
    from flow import plot

    print(f"{block}: captures {run}; step figures")
    ended = _ended(run, Step.FIGURES)
    # make's rule over the captures: drawn again where one is newer than the figures
    if ended is not None and all(path.stat().st_mtime <= ended["finished"] for path in plot.capture_files(run)):
        print("figures done")
        return
    if predict:
        print(f"figures of {len(plot.capture_files(run))} captures")
        return
    started = time.time()
    folder = _fresh(run, Step.FIGURES)
    try:
        paths = plot.figures(block, [run], out_dir=folder)
    except Exception:
        _mark(run, Step.FIGURES, started, error=traceback.format_exc(limit=6)[-4000:])
        raise
    _mark(run, Step.FIGURES, started, figures=[str(path.relative_to(folder)) for path in paths])
    print(*paths, sep="\n")


def _run_jobs(jobs: list[Job], workers: int) -> list[str]:
    """Each job's steps in a process of its own, at most ``workers`` at once, a line each as it ends;
    the lines of those that failed."""
    from concurrent.futures import as_completed

    from flow.sweep import runner

    # one BLAS thread a worker (the spawned workers inherit it): numpy's pool of a thread a core in
    # every worker oversubscribes the machine many times over
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(variable, "1")
    print(f"{_count(len(jobs), 'instance')} on {_count(min(workers, len(jobs)), 'worker')}", flush=True)
    failures = []
    with _pool(workers) as pool:
        futures = {pool.submit(run_steps, job): job for job in jobs}
        for count, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                outcomes = future.result()
            except Exception as error:  # noqa: BLE001 - a worker that died
                outcomes = [f"failed: {error!r}"]
            line = f"[{count}/{len(jobs)}] {runner._shown(job.out)}: {', '.join(outcomes)}"
            print(line, flush=True)
            if any(" failed" in outcome or outcome.startswith("failed") for outcome in outcomes):
                failures.append(line)
    return failures


def _predict(jobs: list[Job], chosen: list[Step]) -> None:
    """Each job's pending steps (``_pending``: those that would fail marked, with why) and
    simulator runs, a line each, then the totals."""
    total_steps = total_runs = complete = total_failing = 0
    for job in jobs:
        pending, failing = _pending(job)
        runs = _simulations(job, [step for step in pending if step not in failing])
        total_steps += len(pending) - len(failing)
        total_failing += len(failing)
        total_runs += runs
        complete += len(job.steps) - len(pending)
        shown = (
            ", ".join(f"{step} (fails: {failing[step]})" if step in failing else str(step) for step in pending)
            or "nothing (complete)"
        )
        print(f"{job.pdk} {job.name} ({job.label}): {shown}{f'; {_count(runs, "simulator run")}' if runs else ''}")
    pdks = len({job.pdk for job in jobs})
    table = "; then the table" if Step.TABLE in chosen else ""
    fails = f", {total_failing} would fail" if total_failing else ""
    print(
        f"{_count(len(jobs), 'instance')} in {_count(pdks, 'PDK')}: {_count(total_steps, 'step')} to run{fails}, "
        f"{complete} complete, about {_count(total_runs, 'simulator run')}{table}"
    )


def _count(number: int, noun: str) -> str:
    """``number`` of ``noun``, plural where it is not one."""
    return f"{number} {noun}{'' if number == 1 else 's'}"


# ---------------------------------------------------------------- the command line


def parser() -> argparse.ArgumentParser:
    """The steps' arguments (``python -m flow <block> ...``)."""
    from flow.sweep import runner

    words = [str(step) for step in Step]
    command = argparse.ArgumentParser(prog="python -m flow", description=(__doc__ or "").split("\n\n")[0])
    command.add_argument("block", choices=pipeline_blocks(), help="a block on the pipeline")
    shown = ", ".join(words)
    command.add_argument("--to", required=True, choices=words, metavar="STEP", help=f"the last step: {shown}")
    command.add_argument("--from", dest="start", default="netlist", choices=words, metavar="STEP", help="the first")
    command.add_argument("--run", metavar="NAME|DIR", help="the run (default: new from netlist, else the latest)")
    command.add_argument("--instance", action="append", dest="instances", metavar="I", help="a name, label or digest")
    command.add_argument("--pdk", action="append", choices=runner.PDKS, dest="pdks", metavar="P")
    # a Spectre X run holds 3 of the server's 120 licences: 36 at once leaves others theirs (an
    # ALIGN layout a core and some GB each: 36 fit the server too)
    command.add_argument("--workers", type=int, default=36, help="instances at once (default: 36)")
    command.add_argument("--predict", action="store_true", help="print what would run, run nothing")
    return command


def opt_parser() -> argparse.ArgumentParser:
    """The optimizer's arguments (``python -m flow opt <block> ...``)."""
    from importlib.util import find_spec

    from flow.sweep import runner

    text = "optimize the block over its parameters for one of its problems (its opt.py)"
    command = argparse.ArgumentParser(prog="python -m flow opt", description=text)
    command.add_argument("block", choices=[b for b in pipeline_blocks() if find_spec(f"flow.{b}.opt") is not None])
    command.add_argument("--problem", required=True, help='a problem by its label, as "adc(bits=12)"')
    command.add_argument("--pdk", choices=runner.PDKS, default="tsmc65")
    command.add_argument("--budget", type=int, default=500, help="trials in the study, those before included")
    command.add_argument("--workers", type=int, default=48)
    command.add_argument("--best", type=int, metavar="N", help="print the study's N best feasible designs, run none")
    command.add_argument(
        "--finalists", type=int, metavar="N", help="characterize the study's N best feasible designs in full"
    )
    command.add_argument("--table", action="store_true", help="export the study as the viewer's table, run none")
    return command


def optimize(argv: list[str]) -> None:
    """``python -m flow opt``: one of a block's problems searched (``flow.opt.runner``)."""
    from flow.opt import runner as opt

    args = opt_parser().parse_args(argv)
    if args.table:
        print(opt.table(args.block, args.pdk, args.problem, args.workers))
    elif args.best:
        for entry in opt.best(args.block, args.pdk, args.problem)[: args.best]:
            print(entry)
    elif args.finalists:
        for entry in opt.finalize(args.block, args.pdk, args.problem, args.finalists, args.workers):
            print(entry)
    else:
        print(opt.optimize(args.block, args.pdk, args.problem, args.budget, args.workers))


def usage() -> None:
    """The commands, the steps (each with those it needs) and the blocks on the pipeline."""
    for line in (__doc__ or "").splitlines():
        if line.startswith("    python -m flow"):
            print(line.strip())
    print("steps:")
    for step in Step:
        print(f"  {step}{f' (needs {", ".join(map(str, step.needs))})' if step.needs else ''}")
    print(f"blocks: {', '.join(pipeline_blocks())}")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        usage()
    elif argv[0] == "opt":
        optimize(argv[1:])
    elif argv[0] == "web.serve":
        from flow.web import server

        server.serve(8765, "127.0.0.1")
    else:
        steps(parser().parse_args(argv))


if __name__ == "__main__":
    # the module by its name, not as __main__: the jobs it sends its spawned workers name their
    # functions by its module, which a worker imports (it never runs a package's __main__)
    import_module("flow.__main__").main()
