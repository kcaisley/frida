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
    record, pex -> page

``--to`` runs the steps that lead from ``--from`` (``netlist`` by default) to it, both included:
``--to record`` simulates and records, ``--from record --to record`` analyses again what ``sim``
kept. ``circuit`` adds the circuit simulator's runs of a block whose full characterization is
behavioral (the ADC's Spectre runs) and records again; it takes picked instances alone.

A run is ``build/<block>/<run>/``, each instance in ``<pdk>/<name>/`` there (a named instance by its
name, a grid's by its digest), a folder a step: ``netlist/``, ``sim/<run>/``, ``circuit/<run>/``,
``record/``, ``figures/``, ``layout/``, ``drc/``, ``lvs/``, ``pex/``, ``page/``; its record,
``instance.json``, beside them, which the viewer's table reads. ``--from netlist`` makes a new run
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
            case Step.CIRCUIT | Step.RECORD:
                return (Step.SIM,)
            case Step.FIGURES | Step.TABLE:
                return (Step.RECORD,)
            case Step.DRC:
                return (Step.LAYOUT,)
            case Step.LVS:
                return (Step.DRC,)
            case Step.PEX:
                return (Step.LVS,)
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
    step it needs that has ended, each of those complete too (make's rule: made again where what it
    was made from, or what that was made from, is newer)."""
    ended = _ended(out, step)
    if ended is None:
        return False
    for need in step.needs:
        made = _ended(out, need)
        if made is not None and (made["finished"] > ended["finished"] or not done(out, need)):
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
    None where it has all it needs."""
    for need in step.needs:
        if not done(job.out, need):
            return f"{step} needs its {need} step's output: {_command(job, need)}"
    return None


def _netlist(job: Job) -> dict:
    """The circuit as simulated and its size (``flow.sweep.runner.write_netlist``)."""
    from flow.sweep import runner

    runner.write_netlist(job.block, job.pdk, job.params, job.out / "netlist")
    return {}


def _sim(job: Job) -> dict:
    """Each of the instance's testbench runs simulated and its measurement kept (``sim/<run>/``)."""
    from flow.sweep import runner

    runs = runner.runs_of(job.block, job.pdk, job.params)
    runner.simulate(job.block, job.pdk, runs, _fresh(job.out, Step.SIM))
    return {"runs": list(runs)}


def _fresh(out: Path, step: Step) -> Path:
    """The step's folder, emptied where the step ended before (its output out of date, made again
    whole); a step that failed or stopped part way keeps what it made, which it then reuses."""
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
    files = runner.simulate(job.block, job.pdk, runs, _fresh(job.out, Step.CIRCUIT))
    started = time.time()
    _mark(job.out, Step.RECORD, started, **_record(job, files))
    return {"runs": list(runs)}


def _body(step: Step):
    """The function that runs ``step`` on one instance, None for a step the CLI does not run yet or
    that runs over a run (``TABLE``)."""
    return {Step.NETLIST: _netlist, Step.SIM: _sim, Step.CIRCUIT: _circuit, Step.RECORD: _record}.get(step)


def run_steps(job: Job) -> list[str]:
    """The job's steps on its instance, in order, in this (fresh) process: each skipped where its
    output is complete (``done``), failed where what it needs is missing (``_missing``), else run;
    a failure ends the instance's steps, and one of its characterization records the failure as its
    record (``flow.sweep.runner.failed_record``), so the viewer's table shows it. Each step's
    outcome, a line each."""
    from flow.sweep import runner

    outcomes = []
    for step in job.steps:
        if done(job.out, step):
            outcomes.append(f"{step} done")
            continue
        missing = _missing(job, step)
        if missing:
            outcomes.append(f"{step} failed: {missing}")
            break
        started = time.time()
        try:
            outputs = _body(step)(job)
        except Exception:  # noqa: BLE001 - every instance reports its own failure
            error = traceback.format_exc(limit=6)[-4000:]
            _mark(job.out, step, started, error=error)
            if step in (Step.NETLIST, Step.SIM, Step.RECORD):
                runner.failed_record(
                    job.block, job.pdk, job.params, job.out, f"{step}: {error}", label=job.label, name=job.name
                )
            outcomes.append(f"{step} failed: {error.strip().splitlines()[-1]}")
            break
        _mark(job.out, step, started, **outputs)
        outcomes.append(f"{step} ok in {time.time() - started:.1f} s")
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
    if reused and not names:
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
        picked = {}
        folders = (run / pdk).iterdir() if (run / pdk).is_dir() else ()
        for folder in sorted(path for path in folders if path.is_dir()):
            try:
                picked |= runner.select(block, pdk, [folder.name])
            except LookupError:
                print(f"{folder}: not in {block}'s design any more, left out")
    else:
        picked = runner.labelled_space(block, pdk)
    return {(label if label in named else ident): (label, params) for ident, (label, params) in picked.items()}


def _pending(job: Job) -> list[Step]:
    """The job's steps that would run: each whose output is not complete, or that needs one that
    would run (made again after it)."""
    pending: list[Step] = []
    for step in job.steps:
        if not done(job.out, step) or any(need in pending for need in step.needs):
            pending.append(step)
    return pending


def _simulations(job: Job, pending: list[Step]) -> int:
    """How many testbench runs the job's pending steps would simulate (those kept already not)."""
    from flow.sweep import runner

    runs = {}
    if Step.SIM in pending:
        runs |= {f"sim/{n}": tb for n, tb in runner.runs_of(job.block, job.pdk, job.params).items()}
    if Step.CIRCUIT in pending:
        runs |= {f"circuit/{n}": tb for n, tb in runner.circuit_runs(job.block, job.pdk, job.params).items()}
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
    unbuilt = [step for step in chosen if step is not Step.TABLE and _body(step) is None]
    if unbuilt:
        raise SystemExit(f"python -m flow runs no {', '.join(map(str, unbuilt))} step yet")
    if Step.CIRCUIT in chosen and not args.instances:
        raise SystemExit("the circuit step runs the circuit simulator: pick the instances (--instance I ...)")
    run, found = _run_dir(args.block, args.run, start)
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
    if found == "new" or not (run / "run.json").exists():
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
    """Each job's pending steps (``_pending``) and simulator runs, a line each, then the totals."""
    total_steps = total_runs = complete = 0
    for job in jobs:
        pending = _pending(job)
        runs = _simulations(job, pending)
        total_steps += len(pending)
        total_runs += runs
        complete += len(job.steps) - len(pending)
        shown = ", ".join(map(str, pending)) or "nothing (complete)"
        print(f"{job.pdk} {job.name} ({job.label}): {shown}{f'; {_count(runs, "simulator run")}' if runs else ''}")
    pdks = len({job.pdk for job in jobs})
    table = "; then the table" if Step.TABLE in chosen else ""
    print(
        f"{_count(len(jobs), 'instance')} in {_count(pdks, 'PDK')}: {_count(total_steps, 'step')} to run, "
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
    command.add_argument("--to", required=True, choices=words, metavar="STEP", help="the last step to run")
    command.add_argument("--from", dest="start", default="netlist", choices=words, metavar="STEP")
    command.add_argument("--run", metavar="NAME|DIR", help="the run (default: new from netlist, else the latest)")
    command.add_argument("--instance", action="append", dest="instances", metavar="I", help="a name, label or digest")
    command.add_argument("--pdk", action="append", choices=runner.PDKS, dest="pdks", metavar="P")
    # a Spectre X run holds 3 of the server's 120 licences: 36 at once leaves others theirs
    command.add_argument("--workers", type=int, default=36)
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


# ---------------------------------------------------------------- the layout steps' helpers


def layout_instances(
    block: str,
    names: list[str],
    pdks: tuple[str, ...],
    *,
    auto: bool,
    plan_only: bool,
    quiet: bool = False,
    signoff: str = "open",
    pex: bool = True,
) -> None:
    """Lay out the instances ``names`` pick (``runner.select``; ``all``: every named one) of
    ``block`` in each of ``pdks``, one run a call, ``build/<block>/layout/<stamp>/`` (not a
    characterization run of the block, ``build/<block>/<stamp>/``): each instance into
    ``<pdk>/<name>/`` there, a named instance by its name, a grid's by its digest; by the shared
    step (``flow.layout.step.layout_one``), or, a block that lays itself out (its ``layout.py``'s
    ``lay_out``), by its own flow (``flow.layout.step.lay_out_one``; no ``auto``, no ``plan_only``).
    ``plan_only``: the netlist and the constraints alone (ALIGN's design directory). The console is the flow's log (``flow.layout.logs``: its steps as Python's
    logging has them, in ALIGN's format) with ALIGN's own output and the checkers' as they run,
    unless ``quiet``; each instance's ``flow.log`` keeps the flow's lines, ALIGN and every tool their
    own logs; an instance ends with its steps, a line each (its time, state and statistics, as its
    page has them)."""
    from flow import new_run, pipeline
    from flow.layout import run as align_run
    from flow.layout.step import lay_out_one, layout_one, own_layout
    from flow.sweep import runner

    own = own_layout(block)
    if own and (auto or plan_only):
        raise SystemExit(f"{block} lays itself out (its layout.py's lay_out): no ALIGN placement or plan")
    named = pipeline.names(import_module(f"flow.{block}.sweep"))
    names = list(named) if names == ["all"] else names
    import logging

    from flow.layout import logs
    from flow.layout.signoff import Checker

    logs.console()
    if quiet:  # the tools' own lines in their logs alone
        for tool in ("gdscheck", "calibre", "klayout"):
            logging.getLogger(tool).setLevel(logging.WARNING)
    log = logging.getLogger("flow")
    align_run.ECHO = not quiet  # ALIGN's output on the terminal as well as in its log
    run_dir = new_run(block, "layout")
    log.info(f"{block}: run {_shown(run_dir)}")
    failed: list[str] = []
    for pdk in pdks:
        try:
            picked = runner.select(block, pdk, names)
        except LookupError as error:
            raise SystemExit(str(error)) from None
        for ident, (label, params) in picked.items():
            name = label if label in named else ident  # a named instance by its name, a grid's by its digest
            name = f"{name}_auto" if auto else name
            out = run_dir / pdk / name
            log.info(f"{block} {name} in {pdk}: {label}: {_shown(out)}")
            if plan_only:
                print(*plan_design(block, params, pdk, out, f"{block}_{name}"), sep="\n")
                continue
            started = time.monotonic()
            with logs.instance_log(out / "flow.log"):
                try:
                    if own:
                        lay_out_one(block, out, pdk, params, checker=Checker[signoff.upper()], pex=pex)
                    else:
                        layout_one(
                            block,
                            out,
                            pdk,
                            f"{block}_{name}",
                            params,
                            auto=auto,
                            checker=Checker[signoff.upper()],
                            pex=pex,
                        )
                except RuntimeError as error:  # a failed signoff: reported, the other instances laid out
                    failed.append(f"{block} {name} in {pdk}: {_reason(out) or error}")
                _layout_record(block, pdk, ident, params, out, time.monotonic() - started, name)
                _page(out)
    if failed:
        raise SystemExit(f"{len(failed)} of the layouts failed signoff:\n" + "\n".join(failed))


def _layout_record(block: str, pdk: str, ident: str, params, out: Path, seconds: float, name: str) -> None:
    """A laid-out instance's record for the viewer's table (``flow table``), ``out/instance.json``,
    as a characterization run writes one: its parameters, no metrics, and its layout (GDS, netlist,
    size, signoff), so a block laid out before it is characterized shows its layouts. ``name``: the
    instance's name in the run (a named instance's, a grid's digest), as its page titles it."""
    import dataclasses
    import json

    from flow.web.export import json_value

    summary = out / "summary.json"
    entry = next(iter(json.loads(summary.read_text()).values()), {}) if summary.exists() else {}
    netlist = next((out / "netlist").glob("*.sp"), None)
    width, height = entry.get("cell_um", (None, None))
    layout = {
        "gds": _shown(Path(entry["gds"])) if entry.get("gds") else None,
        "netlist": _shown(netlist) if netlist else None,
        "w_um": width,
        "h_um": height,
        "drc_violations": entry.get("drc_violations"),
        "lvs_correct": entry.get("lvs_correct"),
        "error": _reason(out) or entry.get("error"),
        "seconds": round(seconds, 1),
        "steps": entry.get("seconds", {}),  # each step's seconds: netlist, layout, DRC, LVS
        # who signed it off, what it accepted and its extraction, where its flow gives them (a block
        # that lays itself out: ``lay_out_one``'s entry), so ``flow.sweep.lookup.laid_out`` hands them on
        **{key: entry[key] for key in ("signoff", "warnings") if key in entry},
        # its extraction's netlist from the repository's root, as the GDS
        **({"pex": _shown_pex(entry["pex"])} if "pex" in entry else {}),
    }
    record = {
        "block": block,
        "id": f"{pdk}__{ident}",
        "name": name,
        "pdk": pdk,
        "params": {field.name: json_value(getattr(params, field.name)) for field in dataclasses.fields(params)},
        "metrics": {},
        "details": [],
        "waves": {},
        "error": None,
        "seconds": round(seconds, 1),
        "layout": layout,
    }
    (out / "instance.json").write_text(json.dumps(record, indent=1) + "\n")


def _page(out: Path) -> None:
    """The laid-out instance's page (``flow.web.page``, ``out/page.html``) and its steps, a line
    each, the error that stopped it under them; a page that cannot be written is reported, never
    the layout's failure."""
    import json
    import logging

    from flow.web.page import page, step_lines

    log = logging.getLogger("flow.steps")
    try:
        written = page(out)
    except Exception as error:  # noqa: BLE001 - the layout stands without its page
        log.warning(f"page not written ({error!r})")
        return
    for line in step_lines(out):
        log.info(line)
    for entry in json.loads((out / "summary.json").read_text()).values() if (out / "summary.json").exists() else ():
        if entry.get("error"):
            log.error(entry["error"][:300])
    log.info(f"page {_shown(written)}")


def _shown(path: Path) -> str:
    """A path as the console shows it: from the repository's root where it is inside."""
    root = Path(__file__).resolve().parents[1]
    path = Path(path).resolve()
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _shown_pex(pex: dict | None) -> dict | None:
    """An extraction's entry with its netlist's path as ``_shown`` gives one."""
    return {**pex, "netlist": _shown(Path(pex["netlist"]))} if pex and pex.get("netlist") else pex


def _reason(run_dir: Path) -> str:
    """Why an instance failed signoff, as its ``failures.json`` records it ("" where it has none)."""
    import json

    path = run_dir / "failures.json"
    return "; ".join(f"{key}: {why}" for key, why in json.loads(path.read_text()).items()) if path.exists() else ""


def plan_design(block: str, params, pdk: str, out_dir: Path, design: str) -> tuple[Path, ...]:
    """The netlists and ALIGN's design directory of ``block``'s ``params`` in ``pdk``, without ALIGN
    (``flow.layout.step.inputs``): the ALIGN and LVS netlists, the design directory."""
    from flow.layout.step import inputs

    input_dir, _cells, source, _placed = inputs(block, out_dir, pdk, design, params)
    return out_dir / "netlist" / f"{design}.sp", source, input_dir


if __name__ == "__main__":
    # the module by its name, not as __main__: the jobs it sends its spawned workers name their
    # functions by its module, which a worker imports (it never runs a package's __main__)
    import_module("flow.__main__").main()
