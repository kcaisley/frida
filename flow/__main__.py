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

Every step logs (``flow.logs``): each tool keeps its whole output in its own log beside its results
(``align``'s ``schematic2layout.log``, ``spectre.log``, ``kpex.log``, ``gdscheck.*.log``,
``calibre.*.log``); every line of the step, the flow's and its tools', at the level the line
states, is in ``<step>/step.log`` (``time tool LEVEL : message``), its warnings and errors
counted by tool in ``step.json``'s ``log``. The console has a line a step as it ends (its folder
in the run, its state, seconds, what it found and those counts: ``tsmc65/frida1/layout ok in
3.3 s: 3.28 x 3.93 um; align 4 errors, 10 warnings``), a line an instance, and at the end the
run's table (one instance's steps a row each, with their folders; over several, each step's
states counted and its seconds and warnings summed).

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
import os
import sys
import time
import traceback
from importlib import import_module
from pathlib import Path
from typing import Any

from flow.steps import Job, Outcome, Step, _count, _ended, _fresh, _mark, _missing, between, done, logged, run_steps


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
    """Each job's steps in a process of its own, at most ``workers`` at once (each step's line as it
    ends, ``flow.steps._report``), a line each job as it ends, then the run's table (``_table``);
    the lines of those that failed."""
    from concurrent.futures import as_completed

    from flow.sweep import runner

    # one BLAS thread a worker (the spawned workers inherit it): numpy's pool of a thread a core in
    # every worker oversubscribes the machine many times over
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(variable, "1")
    print(f"{_count(len(jobs), 'instance')} on {_count(min(workers, len(jobs)), 'worker')}", flush=True)
    failures, ended = [], {}
    with _pool(workers) as pool:
        futures = {pool.submit(run_steps, job): job for job in jobs}
        for count, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                outcomes = future.result()
            except Exception as error:  # noqa: BLE001 - a worker that died
                outcomes = [Outcome("worker", "failed", None, repr(error), {})]
            ended[job] = outcomes
            states = [outcome.state for outcome in outcomes]
            tally = ", ".join(f"{states.count(s)} {s}" for s in dict.fromkeys(states))
            stopped = [outcome.step for outcome in outcomes if outcome.state == "failed"]
            line = f"[{count}/{len(jobs)}] {job.pdk}/{job.name}: {tally}" + (
                f" ({', '.join(stopped)})" if stopped else ""
            )
            print(line, flush=True)
            if stopped:
                failures.append(f"{runner._shown(job.out)}: {', '.join(stopped)} failed")
    print(_table(ended))
    return failures


def _table(ended: dict[Job, list[Outcome]]) -> str:
    """The run's table: one instance's steps a row each (its state, seconds, what it found, its
    log's warnings and errors by tool, its folder, where its results and ``step.log`` are); over
    several instances, each step's states counted, its seconds summed, its warnings and errors
    summed by tool."""
    from tabulate import tabulate

    from flow.sweep import runner

    if len(ended) == 1:
        [(job, outcomes)] = ended.items()
        rows = [
            [
                o.step,
                o.state,
                "" if o.seconds is None else f"{o.seconds:.1f} s",
                o.found,
                logged(o.counts),
                runner._shown(job.out / o.step),
            ]
            for o in outcomes
        ]
        return tabulate(rows, ["step", "state", "time", "result", "warnings, errors", "folder"])
    states = ("ok", "failed", "done", "not run")
    rows = []
    for step in dict.fromkeys(o.step for outcomes in ended.values() for o in outcomes):
        each = [o for outcomes in ended.values() for o in outcomes if o.step == step]
        counts: dict[str, dict[str, int]] = {}
        for o in each:
            for tool, levels in o.counts.items():
                for level, n in levels.items():
                    counts.setdefault(tool, {})[level] = counts.get(tool, {}).get(level, 0) + n
        seconds = sum(o.seconds or 0.0 for o in each)
        rows.append([step, *(sum(o.state == s for o in each) for s in states), f"{seconds:.1f} s", logged(counts)])
    return tabulate(rows, ["step", *states, "time (sum)", "warnings, errors"])


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
