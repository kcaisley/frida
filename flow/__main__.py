r"""The flow's one entry point: one of a block's runs, through its steps.

    python -m flow --block B --run R [--to STEP] [--from STEP] [--dry-run]
    python -m flow web.serve

``--run`` names one of the block's runs (its runs.py, by its function's name): one design
(``@single``, ``frida1``), every design of a grid (``@grid``) or an optimization (``@optimize``,
``adc_12bit``: its study in each of its PDKs, ``flow.opt.runner``). What a run runs in and on is
the run's own (its PDKs, its workers, an optimization's budget), never a flag here.

A step is one tool: it takes its inputs and makes its outputs, and its configuration is the tool's
own, in the block's Python files and the kit's (the runs a run states, a layout's placement,
which signoff a kit takes), never a flag here. An instance's steps are one chain, each after those it needs:

    netlist -> sim -> layout -> drc -> lvs -> pex -> pexsim -> record -> table
               sim -> circuit                                 record -> figures

The record runs after pexsim and takes its measurements where it simulated the extraction (the
post-layout metrics, the pre-layout ones beside them as ``prelayout``, ``evidence`` saying which),
but needs only the netlist and the sim: where the layout fails, or is not extracted or
back-annotated (a kit's extraction with devices, the ADC's), the record holds the pre-layout
metrics alone and the layout's outcome.

``--to`` (``table`` by default: the viewer's table of the run's records) runs the steps that lead from ``--from`` (``netlist`` by default) to
it, both included:
``--to sim`` simulates alone, ``--to record`` lays out, signs off, extracts, simulates the
extraction and records, ``--to lvs`` lays out and signs off without extraction,
``--from table --to table`` exports what the runs hold; with ``record/`` deleted, ``--from record
--to record`` analyses again what ``sim`` kept. ``circuit`` adds the circuit simulator's runs of a
block whose full characterization is behavioral (the ADC's Spectre runs) and records again; it
runs on a ``@single`` alone. ``figures`` draws a record's figures (the lab's captures are drawn by
``flow.scans``, not here). ``layout`` runs the block's own
``lay_out`` where it has a ``layout.py`` (with the signoff it plans, FRIDA-1's Calibre:
``flow.layout.signoff.write_plan``), else ALIGN through the shared step (its netlists and
constraints too: the netlist step's edge to it only orders them); ``drc``, ``lvs`` and ``pex``
run, each in its folder, that plan, else the checker the kit names
(``flow.layout.signoff.checker``: the open tools, else Calibre), on its GDS. ``pexsim`` simulates
the sim step's runs again with the open extractor's capacitances back-annotated onto the schematic
(``flow.layout.annotate``: each layout net found on its schematic net through LVS; each run's DUT
a flat copy with the capacitors, ``flow.sweep.runner.simulate``), which the record step records
(the same metric names, the annotation's totals beside them); it refuses an extraction more than a small share of whose capacitance has no
schematic net or one the DUT lacks, and testbenches none of which holds the DUT, and leaves an extraction with devices and RC (a kit's) to the block's own
simulation of it (the ADC's circuit step). The viewer (``web.serve``) shows each instance's steps
from top to bottom, each with what it made.

Every step logs (``flow.logs``): each tool keeps its whole output in its own log beside its results
(``align``'s ``schematic2layout.log``, ``spectre.log``, ``kpex.log``, ``gdscheck.*.log``,
``calibre.*.log``); every line of the step, the flow's and its tools', at the level the line
states, is in ``<step>/step.log`` (``time tool LEVEL : message``), its warnings and errors
counted by tool in ``step.json``'s ``log``. The run is watched on its dashboard (``flow.dashboard``):
in a terminal, live and in place (the pipeline a row a step, its instances by state, what needs
attention, the running tool's newest lines and the metrics pre- and post-layout, or why designs
left the run and those that passed); elsewhere, a line a step as it ends for a run of a few
instances (``tsmc65/frida1/layout ok in 3.3 s: 3.28 x 3.93 um; align 4 errors, 10 warnings``),
what needs attention and a status line now and then for many; its summary at the end; and
always, beside the run, ``status.txt`` (the dashboard as plain text, every two seconds) and
``events.log`` (each line that needs attention).

A run is ``build/<block>/<run>/<stamp>/``, dated, each design in ``<pdk>/<name>/`` there (a
single's by its name, a grid's by its digest), a folder a step: ``netlist/``, ``sim/<run>/``,
``circuit/<run>/``, ``record/``, ``figures/``, ``layout/``, ``drc/``, ``lvs/``, ``pex/``,
``pexsim/<run>/``; its record, ``instance.json``, beside them, which the viewer's table
reads (the run's older dated folders kept, for the viewer to show). A run from the netlist (the default)
is a new one; ``--from`` a later step works in the run's latest folder, which must exist, and resumes
it: a step skips a design whose output is complete and not older than what it was made from
(make's rule), so a run stopped part way resumes where it stopped; to make a step again, delete its
folder. A step whose inputs are missing fails, naming the command that makes them. A folder of a
design the run no longer names is said and left alone.

``--dry-run`` prints the run, the designs and the steps each would run, with a rough count, and runs
nothing (an optimization: its PDKs and budget). The bare command lists the steps and each block's
runs. ``web.serve`` serves the viewer on http://127.0.0.1:8765.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict
from importlib import import_module
from pathlib import Path
from typing import Any

from flow.dashboard import SMALL, Board
from flow.steps import Job, Outcome, Step, _count, _missing, _report, between, done, key, run_steps


def pipeline_blocks() -> list[str]:
    """The blocks on the pipeline: those whose ``runs.py`` gives ``runs`` (one that no longer
    imports gives none)."""
    from importlib.util import find_spec

    from flow.sweep import runner

    def on_pipeline(block: str) -> bool:
        try:
            return find_spec(f"flow.{block}.runs") is not None and hasattr(runner.runs_module(block), "testbenches")
        except ImportError:
            return False

    return [block for block in runner.sweep_blocks() if on_pipeline(block)]


# ---------------------------------------------------------------- a run's instances


def _run(block: str, run: str):
    """The block's run ``run`` (its runs.py's ``@single``, ``@grid`` or ``@optimize``)."""
    from flow import pipeline
    from flow.sweep import runner

    found = pipeline.runs(runner.runs_module(block))
    if run not in found:
        raise SystemExit(f"{block} has no run {run!r}: {', '.join(found)}")
    return found[run]


def _pdks(block: str, run: str, spec) -> list[str]:
    """The PDKs the run runs in: those it names, else every PDK whose kit is here and in which
    the block admits one of its designs (an optimization: whose kit is here)."""

    from flow import pipeline
    from flow.sweep import runner

    pdks = [pdk.name.lower() for pdk in spec.pdks] if spec.pdks is not None else list(runner.PDKS)
    found = []
    for pdk in pdks:
        try:
            if not _kit(pdk):
                continue
            if isinstance(spec, pipeline.Optimize) or runner.run_instances(block, run, pdk):
                found.append(pdk)
        except (LookupError, ModuleNotFoundError):  # a kit this checkout lacks, or holds no design
            continue
    return found


def _kit(pdk: str) -> bool:
    """Whether this checkout has ``pdk``'s kit (``pdk/<pdk>``, or a module standing in for it)."""
    from importlib.util import find_spec

    try:
        return find_spec(f"pdk.{pdk}") is not None
    except ValueError:  # a module put in place of the kit (a test's), without a spec
        return f"pdk.{pdk}" in sys.modules


def instances(block: str, run: str, pdk: str, folder: Path) -> dict[str, tuple[str, Any]]:
    """The designs the run names in ``pdk``, by their folder in the run (a single's name, a
    grid's digests), with their labels and parameters; a folder of the run's that the run no
    longer names is said and left alone."""
    from flow import pipeline
    from flow.sweep import runner

    single = isinstance(_run(block, run), pipeline.Single)
    picked = {
        (label if single else ident): (label, params)
        for ident, (label, params) in runner.run_instances(block, run, pdk).items()
    }
    if (folder / pdk).is_dir():
        for path in sorted(path for path in (folder / pdk).iterdir() if path.is_dir()):
            if path.name not in picked:
                print(f"{runner._shown(path)}: not in {block}'s run {run} any more, left alone")
    return picked


def _pending(job: Job) -> tuple[list[Step], dict[Step, str]]:
    """The job's steps that would run: each whose output is not complete, or that needs one that
    would run (made again after it); and those of them that would fail, with why: what they need
    neither complete nor to run (``_missing``), or a step they need that would fail (not run)."""
    pending: list[Step] = []
    failing: dict[Step, str] = {}
    for step in job.steps:
        if done(job.out, step) and not any(need in pending for need in step.inputs):
            continue
        pending.append(step)
        if any(need in failing for need in step.needs):
            failing[step] = f"not run, as {next(need for need in step.needs if need in failing)} fails"
        elif any(need not in pending and not done(job.out, need) for need in step.needs):
            failing[step] = _missing(job, step) or "a step it needs is not complete"
    return pending, failing


def _simulations(job: Job, pending: list[Step]) -> int:
    """How many testbench runs the job's pending steps would simulate (those kept already not)."""
    from flow.sweep import runner

    runs = {}
    if Step.SIM in pending:
        runs |= {f"sim/{n}": tb for n, tb in runner.testbenches_of(job.block, job.pdk, job.params).items()}
    if Step.CIRCUIT in pending:
        runs |= {f"circuit/{n}": tb for n, tb in runner.circuit_testbenches(job.block, job.pdk, job.params).items()}
    if Step.PEXSIM in pending:
        runs |= {f"pexsim/{n}": tb for n, tb in runner.testbenches_of(job.block, job.pdk, job.params).items()}
    return sum(not (job.out / name / "result.h5").exists() for name in runs)


def _pool(workers: int):
    """A pool of fresh processes, one an instance: hdl21 compiles a generated module in place, for
    one PDK."""
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context

    return ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1)


def steps(args: argparse.Namespace) -> None:
    """Run ``args``' steps (``parser``) over the designs its run names, or print them
    (``--dry-run``); an optimization runs its study in each PDK (``flow.opt.runner``)."""
    from flow import pipeline
    from flow.sweep import runner

    spec = _run(args.block, args.run)
    if isinstance(spec, pipeline.Optimize):
        _optimize(args.block, args.run, spec, args.dry_run)
        return
    start, stop = Step[args.start.upper()], Step[args.to.upper()]
    chosen = between(start, stop)
    if Step.CIRCUIT in chosen and not isinstance(spec, pipeline.Single):
        raise SystemExit("the circuit step runs the circuit simulator: run it on a @single design")
    run, found = _run_dir(args.block, args.run, start)
    jobs = []
    for pdk in _pdks(args.block, args.run, spec):
        each = tuple(step for step in chosen if step is not Step.TABLE)
        picked = instances(args.block, args.run, pdk, run)
        bounds = tuple(spec.bounds(pdk))
        jobs += [
            Job(args.block, pdk, n, label, params, run / pdk / n, each, args.run, bounds)
            for n, (label, params) in picked.items()
        ]
    if not jobs:
        raise SystemExit(f"{args.block}'s run {args.run} names no design in a PDK whose kit is here")
    if Step.CIRCUIT in chosen and not any(runner.circuit_testbenches(j.block, j.pdk, j.params) for j in jobs):
        raise SystemExit(f"{args.block} has no circuit simulator runs beyond its full ones: its sim step runs them")
    workers = pipeline.workers(spec)
    print(f"{args.block}: {found} run {runner._shown(run)}; steps {', '.join(map(str, chosen))}")
    if args.dry_run:
        _dry_run(jobs, chosen)
        return
    if found == "new":
        runner.new_run(args.block, run_dir=run)
    board = Board(
        args.block,
        args.run,
        type(spec).__name__.lower(),
        tuple(dict.fromkeys(job.pdk for job in jobs)),
        min(workers, len(jobs)),
        run,
        tuple(str(step) for step in chosen if step is not Step.TABLE),
    )
    failures = _run_jobs(jobs, workers, board) if jobs[0].steps else []
    if Step.TABLE in chosen:
        unrecorded = [job for job in jobs if not (job.out / "instance.json").exists()]
        if unrecorded:
            raise SystemExit(
                f"table needs every instance's record, {len(unrecorded)} of {len(jobs)} have none: "
                f"python -m flow --block {args.block} --run {args.run} --to record"
            )
        runner.table([args.block], workers, run=run)
    if failures:
        raise SystemExit(f"{len(failures)} of {len(jobs)} instances failed; the first: {failures[0]}")


def _run_dir(block: str, run: str, start: Step) -> tuple[Path, str]:
    """The run the steps work in, and how it was found: a new one, dated, where they start at the
    netlist (``build/<block>/<run>/<stamp>/``), else the run's latest, which must exist."""
    from flow.sweep import runner

    folder = runner.RUNS_DIR / block / run
    if start is Step.NETLIST:
        return folder / _stamp(), "new"
    dated = sorted(path for path in folder.glob("*") if (path / "run.json").exists()) if folder.is_dir() else []
    if not dated:
        raise SystemExit(f"no run of {block}'s {run} yet: python -m flow --block {block} --run {run}")
    return dated[-1], "the latest"


def _stamp() -> str:
    """Now, as a new run's folder: ``YYYYmmdd_HHMMSS``."""
    from datetime import datetime

    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def _optimize(block: str, run: str, spec, dry_run: bool) -> None:
    """An optimization's study in each of its PDKs (``flow.opt.runner.optimize``): its budget's
    trials, on its workers."""
    from flow import pipeline
    from flow.opt import runner as opt

    workers = pipeline.workers(spec)
    for pdk in _pdks(block, run, spec):
        print(f"{block}: optimization {run} in {pdk}, {spec.budget} trials on {_count(workers, 'worker')}")
        if not dry_run:
            print(opt.optimize(block, pdk, run, spec.budget, workers))


def _run_jobs(jobs: list[Job], workers: int, board) -> list[str]:
    """Each job's steps in a process of its own, at most ``workers`` at once, their events onto the
    run's dashboard (``flow.dashboard``: live in a terminal, else each step's line for a few
    instances, what needs attention for many; ``status.txt`` and ``events.log`` beside the run), its
    summary at the end; the lines of those that failed."""
    from concurrent.futures import FIRST_COMPLETED, wait
    from queue import Empty

    from flow.dashboard import View
    from flow.sweep import runner

    # one BLAS thread a worker (the spawned workers inherit it): numpy's pool of a thread a core in
    # every worker oversubscribes the machine many times over
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(variable, "1")
    print(f"{_count(len(jobs), 'instance')} on {_count(min(workers, len(jobs)), 'worker')}", flush=True)
    by_key = {key(job): job for job in jobs}
    for job in jobs:
        board.add(key(job), job.out, [bound.metric for bound in job.bounds])
    failures: list[str] = []
    ended = 0

    def line(event: dict[str, Any]) -> None:  # a step's line, as the step runner prints it
        outcome = Outcome(event["step"], event["state"], event["seconds"], event["found"], event["counts"])
        _report(by_key[event["key"]], outcome)

    with _pool(workers) as pool, _channel(pool) as channel, View(board, line) as view:

        def drain() -> None:
            while True:
                try:
                    view.take(channel.get_nowait())
                except Empty:
                    return

        futures = {pool.submit(run_steps, job, channel): job for job in jobs}
        pending = set(futures)
        while pending:
            finished, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            drain()
            for future in finished:
                job = futures[future]
                try:
                    outcomes = future.result()
                except Exception as error:  # noqa: BLE001 - a worker that died
                    outcomes = [Outcome("worker", "failed", None, repr(error), {})]
                    view.take({"key": key(job), **asdict(outcomes[0]), "step": "worker"})
                ended += 1
                board.end(key(job), [outcome.state for outcome in outcomes])
                stopped = [outcome.step for outcome in outcomes if outcome.state == "failed"]
                if view.live is None and len(jobs) <= SMALL:
                    states = [outcome.state for outcome in outcomes]
                    tally = ", ".join(f"{states.count(s)} {s}" for s in dict.fromkeys(states))
                    shown = f" ({', '.join(stopped)})" if stopped else ""
                    print(f"[{ended}/{len(jobs)}] {key(job)}: {tally}{shown}", flush=True)
                if stopped:
                    failures.append(f"{runner._shown(job.out)}: {', '.join(stopped)} failed")
            view.refresh()
    return failures


class _channel:
    """The queue a run's workers send their steps' events on: a manager's, across the processes of a
    real pool; a plain one where the pool runs its tasks in this process (the tests')."""

    def __init__(self, pool) -> None:
        from concurrent.futures import ProcessPoolExecutor

        self.manager = None
        if isinstance(pool, ProcessPoolExecutor):
            from multiprocessing import get_context

            self.manager = get_context("spawn").Manager()
            self.queue = self.manager.Queue()
        else:
            from queue import SimpleQueue

            self.queue = SimpleQueue()

    def __enter__(self):
        return self.queue

    def __exit__(self, *exc: object) -> None:
        if self.manager is not None:
            self.manager.shutdown()


def _dry_run(jobs: list[Job], chosen: list[Step]) -> None:
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
    """The command line (``python -m flow --block B --run R ...``): which block, which of its
    runs, which steps; everything else is in the block's runs.py."""
    words = [str(step) for step in Step]
    command = argparse.ArgumentParser(prog="python -m flow", description=(__doc__ or "").split("\n\n")[0])
    command.add_argument("--block", required=True, choices=pipeline_blocks(), help="a block on the pipeline")
    command.add_argument("--run", required=True, metavar="RUN", help="one of the block's runs, by its name")
    shown = ", ".join(words)
    command.add_argument("--to", default="table", choices=words, metavar="STEP", help=f"the last step (table): {shown}")
    command.add_argument("--from", dest="start", default="netlist", choices=words, metavar="STEP", help="the first")
    command.add_argument("--dry-run", dest="dry_run", action="store_true", help="print what would run, run nothing")
    return command


def usage() -> None:
    """The commands, the steps (each with those it needs and those it runs after) and each block's
    runs."""
    from flow import pipeline
    from flow.sweep import runner

    for line in (__doc__ or "").splitlines():
        if line.startswith("    python -m flow"):
            print(line.strip())
    print("steps:")
    for step in Step:
        said = [f"needs {', '.join(map(str, step.needs))}"] if step.needs else []
        said += [f"after {', '.join(map(str, step.after))}"] if step.after else []
        print(f"  {step}{f' ({"; ".join(said)})' if said else ''}")
    print("blocks and their runs (--run):")
    kind = {pipeline.Single: "single", pipeline.Grid: "grid", pipeline.Optimize: "optimize"}
    for block in pipeline_blocks():
        found = pipeline.runs(runner.runs_module(block))
        print(f"  {block}: {', '.join(f'{name} ({kind[type(spec)]})' for name, spec in found.items())}")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        usage()
    elif argv[0] == "web.serve":
        from flow.web import server

        server.serve(8765, "127.0.0.1")
    else:
        steps(parser().parse_args(argv))


if __name__ == "__main__":
    # the module by its name, not as __main__: the jobs it sends its spawned workers name their
    # functions by its module, which a worker imports (it never runs a package's __main__)
    import_module("flow.__main__").main()
