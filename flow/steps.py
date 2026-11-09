"""An instance's steps (``python -m flow``, whose manual ``flow.__main__`` is): the step graph
(``Step``, ``between``), make's rule over a step's folder (``done``: its ``step.json``), each step's
body, and ``run_steps``, which runs a job's steps on its instance in a worker of its own, each with
its log (``flow.logs.step_log``: ``<step>/step.log``, the warnings and errors on the console, their
counts by tool in ``step.json``).
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass
from enum import Enum, auto
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
    """A step's outputs, from its ``step.json``: its record of the run (``_mark``'s, its log's
    counts too) left out."""
    return {key: value for key, value in ended.items() if key not in ("step", "finished", "seconds", "error", "log")}


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


def _logged(counts: dict[str, dict[str, int]]) -> str:
    """A step's warnings and errors by tool (``flow.logs.step_log``'s counts), for its outcome's
    line: `` [align 4 warnings, 2 errors; spectre 26 warnings]``; nothing where there were none."""
    nouns = {"WARNING": "warning", "ERROR": "error", "CRITICAL": "critical error"}
    tools = [
        f"{tool} {', '.join(_count(n, nouns[level]) for level, n in levels.items())}" for tool, levels in counts.items()
    ]
    return f" [{'; '.join(tools)}]" if tools else ""


def run_steps(job: Job) -> list[str]:
    """The job's steps on its instance, in order, in this (fresh) process: each skipped where its
    output is complete (``done``), failed where what it needs is missing (``_missing``), else run
    in its folder (emptied where it ended before: ``_fresh``) with its log (``flow.logs.step_log``:
    every line, the flow's and its tools', in ``<step>/step.log``, each tool's whole output in its
    own log beside its results; the warnings and errors on the console, tagged with the instance
    and step, and counted by tool in ``step.json``'s ``log``). A failure leaves
    the steps after it not run (the page, which takes whatever exists, runs); a characterization
    step's failure (netlist, sim, record) is also the instance's record
    (``flow.sweep.runner.failed_record``), and a layout step's joins it (``_join_layout``), so the
    viewer's table shows it. Each step's outcome, a line each."""
    from flow.logs import step_log
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
        laid = step in (Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX, Step.RECORD)  # joined to the record
        error = None
        with step_log(folder / "step.log", f"[{job.pdk}/{job.name} {step}]") as counts:
            try:
                outputs = _body(step)(job)
            except Exception:  # noqa: BLE001 - every instance reports its own failure
                error = traceback.format_exc(limit=6)[-4000:]
                logging.getLogger("flow.steps").error(error.rstrip(), extra={"counted": False})
        if error is not None:
            _mark(job.out, step, started, error=error, log=counts)
            if step in (Step.NETLIST, Step.SIM, Step.RECORD):
                runner.failed_record(
                    job.block, job.pdk, job.params, job.out, f"{step}: {error}", label=job.label, name=job.name
                )
            if laid:
                _join_layout(job)
            failed.add(step)
            outcomes.append(f"{step} failed: {error.strip().splitlines()[-1]}{_logged(counts)}")
            continue
        _mark(job.out, step, started, log=counts, **outputs)
        if laid:
            _join_layout(job)
        outcomes.append(f"{step} ok in {time.time() - started:.1f} s{_brief(step, outputs)}{_logged(counts)}")
    return outcomes


def _count(number: int, noun: str) -> str:
    """``number`` of ``noun``, plural where it is not one."""
    return f"{number} {noun}{'' if number == 1 else 's'}"
