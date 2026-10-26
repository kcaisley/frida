"""Optimize a block over its parameters' domains (``python -m flow opt <block> --problem P``), as
``flow.sweep.runner`` sweeps it over its families.

A study is one problem of the block (its opt.py's ``@problem``: ``adc(bits=12)``) in one PDK, kept in
``build/opt/<block>/<pdk>/<problem>.db`` (Optuna, sqlite) so that it resumes. Optuna's TPE sampler
proposes designs asynchronously: whenever a worker frees, it asks for the next design, so a slow
evaluation holds no other (a design is about a minute to an hour). The objective is the problem's
cost (``pipeline.objective``), each bound's violation a constraint by name
(``pipeline.violations``): a design that misses a bound is a completed, infeasible trial, from
which the sampler learns; only a broken evaluation (the simulator, a license, ALIGN) fails one.

Each evaluation (``evaluate``, a fresh process) takes the design's identity first, the hash of its
compiled netlist in the PDK: two parameter sets that build the same circuit are one evaluation, kept
in ``build/opt/<block>/<pdk>/evals/<hash>/instance.json`` and shared by every problem of the block,
so that a design asked for again costs nothing. A design ``params.valid`` rejects in the PDK is
infeasible without simulating. Then the screen's runs (``Level.SCREEN``) and, where the problem bounds
the layout area, the layout by the structure's hand-written floorplan (ALIGN, about a minute; a
structure without one has no area, an unmet bound); where these already break a bound, the
evaluation stops there, else the search's runs follow (``Level.SEARCH``). A new study starts from
every evaluation already made, rescored under its problem.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
from enum import Enum
from importlib import import_module
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from flow import pipeline
from flow.sweep import flat_params
from flow.sweep.runner import ROOT, digest, write_record

OPT_DIR = ROOT / "build/opt"
# an ALIGN layout in the loop that has not placed and routed in ten minutes fails (its placer can
# search for hours on the larger sizings); the evaluation is then broken, not the design
ALIGN_TIMEOUT_S = 600
# the largest share of a layout its devices' gates cover: at most 0.24 over the 714 comparator layouts
# of the sweeps (2026-10-26), so a design whose gates over it exceed the area bound cannot meet it
DENSITY = 0.25


def study_dir(block: str, pdk: str) -> Path:
    """Where a block's studies in ``pdk`` and their shared evaluations live."""
    return OPT_DIR / block / pdk


def knobs(cls: Any, pdk: str, problem: pipeline.Problem) -> dict[str, pipeline.Domain]:
    """The searched parameters of ``cls`` for ``problem``: those with a domain, less its fixed."""
    return {name: domain for name, domain in pipeline.domains(cls).items() if name not in problem.fixed}


def distributions(cls: Any, pdk: str, problem: pipeline.Problem) -> dict[str, Any]:
    """Each searched parameter's Optuna distribution (a choice by its values' names)."""
    import optuna

    dtypes = {name: param.dtype for name, param in cls.__params__.items()}
    result: dict[str, Any] = {}
    for name, domain in knobs(cls, pdk, problem).items():
        if isinstance(domain, pipeline.Choice):
            values = pipeline.choices(domain, dtypes[name], pdk)
            result[name] = optuna.distributions.CategoricalDistribution([_name(value) for value in values])
        else:
            low, high = pipeline.bounds(domain, pdk)
            result[name] = optuna.distributions.IntDistribution(low, high, log=domain.log)
    return result


def _name(value: Any) -> Any:
    return value.name if isinstance(value, Enum) else value


def suggest(trial: Any, cls: Any, pdk: str, problem: pipeline.Problem) -> Any:
    """The design ``trial`` proposes: its choices first, then each number whose ``when`` holds for
    those choices, the problem's fixed parameters, the rest at their defaults."""

    dtypes = {name: param.dtype for name, param in cls.__params__.items()}
    space = knobs(cls, pdk, problem)
    dists = distributions(cls, pdk, problem)
    values: dict[str, Any] = dict(problem.fixed)
    for name, domain in space.items():
        if isinstance(domain, pipeline.Choice):
            picked = trial.suggest_categorical(name, dists[name].choices)
            values[name] = (
                dtypes[name][picked] if isinstance(dtypes[name], type) and issubclass(dtypes[name], Enum) else picked
            )
    chosen = cls(**{**cls.defaults(), **values})
    for name, domain in space.items():
        if isinstance(domain, pipeline.Int) and pipeline.active(domain, chosen):
            values[name] = trial.suggest_int(name, dists[name].low, dists[name].high, log=dists[name].log)
    return cls(**{**cls.defaults(), **values})


def identity(block: str, pdk: str, params: Any) -> str:
    """The design's identity: the first 16 hex digits of the SHA-256 of its compiled netlist in
    ``pdk`` (its layout hook's ``write_netlist``), else of its canonical parameters."""

    write_netlist = getattr(import_module(f"flow.{block}.layout"), "write_netlist", None)
    if write_netlist is None:
        return digest(flat_params(pipeline.canonical(params)))
    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    with tempfile.TemporaryDirectory() as folder:
        text = write_netlist(pipeline.canonical(params), Path(folder) / "design.sp", logic).read_text()
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def betters(block: str) -> dict[str, pipeline.Better]:
    """Which way is better for each metric a block's record carries: its own and the runner's."""
    return {**pipeline.betters(import_module(f"flow.{block}.types").Metrics), **pipeline.GEOMETRY}


def layout_area(block: str, pdk: str, params: Any, out: Path) -> float:
    """The design's layout area (um^2) by its structure's hand-written floorplan (ALIGN placing and
    routing, no signoff); NaN without a floorplan."""

    from klayout import db

    from flow.layout.align.build import build as align_build
    from flow.sweep.runner import case_floorplan

    os.environ["ALIGN_TIMEOUT"] = str(ALIGN_TIMEOUT_S)
    planned = case_floorplan(block, out / "netlist", pdk, params)
    if planned is None:
        return math.nan
    netlist, floorplan = planned
    gds = align_build(pdk, floorplan, netlist, out / "align_floorplan", name=netlist.stem)
    layout = db.Layout()
    layout.read(str(gds))
    box = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).dbbox()
    return box.width() * box.height()


def simulate(block: str, runs: dict[str, Any], run_dir: Path) -> dict[str, pipeline.Meas]:
    """Each of ``runs`` simulated, one after another in ``run_dir``, and read back."""

    sim = import_module(f"flow.{block}.sim")
    measurements = {}
    for name, tb in runs.items():
        raw = sim.simulate(tb, run_dir / name)
        measurements[name] = pipeline.read(raw, tb)
        raw.unlink()
    return measurements


def unmeasurable(metrics: dict[str, Any]) -> list[str]:
    """The metrics measured but not a number (beyond what the bench resolves, an area without a
    floorplan): a record names them, since its JSON keeps NaN as null, which reads as not measured."""
    return sorted(name for name, value in metrics.items() if isinstance(value, float) and not math.isfinite(value))


def measured(record: dict[str, Any]) -> dict[str, Any]:
    """A record's metrics as measured: its unmeasurable ones NaN again (``unmeasurable``)."""
    return {**record["metrics"], **dict.fromkeys(record.get("unmeasurable", ()), math.nan)}


def evaluate(block: str, pdk: str, params: Any, problem: pipeline.Problem) -> dict[str, Any]:
    """One design's evaluation for ``problem`` (in a fresh process): its record, from the shared
    evaluations where it was made before and measured enough, else made now (module docstring)."""

    import hdl21 as h

    from flow.sweep import geometry

    start = time.time()
    better = betters(block)
    h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
    ident = identity(block, pdk, params)
    folder = study_dir(block, pdk) / "evals" / ident
    path = folder / "instance.json"
    if path.exists():
        cached = json.loads(path.read_text())
        stopped = any(value > 0 for value in pipeline.violations(problem, measured(cached), better).values())
        if cached["level"] >= pipeline.Level.SEARCH.value or stopped or not cached["valid"]:
            return {**cached, "cached": True}
    record: dict[str, Any] = {
        "block": block,
        "id": ident,
        "pdk": pdk,
        "params": flat_params(pipeline.canonical(params)),
        "valid": bool(import_module(f"flow.{block}.params").valid(params, pdk)),
        "level": 0,
        "metrics": {},
        "error": None,
    }
    folder.mkdir(parents=True, exist_ok=True)
    met = lambda metrics: not any(value > 0 for value in pipeline.violations(problem, metrics, better).values())
    if record["valid"]:
        sweep = import_module(f"flow.{block}.sweep")
        module = import_module(f"flow.{block}.subckt").netlist(params)
        h.pdk.compile(module)
        extra = geometry(module, pdk)
        bounded = "layout_area_um2" in problem.bound
        # no layout has its gates cover more than DENSITY of it: where the gates over DENSITY exceed
        # the area bound, the design is out without simulating, its area estimated so
        if bounded and extra["gate_area_um2"] / DENSITY > problem.bound["layout_area_um2"]:
            record.update(
                metrics={**extra, "layout_area_um2": extra["gate_area_um2"] / DENSITY}, estimated=["layout_area_um2"]
            )
            record["seconds"] = round(time.time() - start, 1)
            write_record(path, record)
            return record
        measurements = simulate(block, sweep.runs(pdk, params, pipeline.Level.SCREEN), folder / "runs")
        metrics = {**sweep.record(measurements).metrics, **extra}
        record.update(metrics=metrics, level=pipeline.Level.SCREEN.value)
        # the layout only for a design the screen keeps: a minute of ALIGN
        if bounded and met(metrics):
            extra["layout_area_um2"] = layout_area(block, pdk, params, folder / "layout")
            metrics = {**metrics, **extra}
            record.update(metrics=metrics)
        if met(metrics):
            # the search's runs include the screen's: only the rest are simulated, one record of all
            more = {n: tb for n, tb in sweep.runs(pdk, params, pipeline.Level.SEARCH).items() if n not in measurements}
            measurements.update(simulate(block, more, folder / "runs"))
            metrics = {**sweep.record(measurements).metrics, **extra}
            record.update(metrics=metrics, level=pipeline.Level.SEARCH.value)
    record["seconds"] = round(time.time() - start, 1)
    record["unmeasurable"] = unmeasurable(record["metrics"])
    write_record(path, record)
    return record


def score(
    problem: pipeline.Problem, record: dict[str, Any], better: dict[str, pipeline.Better]
) -> tuple[float, dict[str, float]]:
    """A record's objective and constraints under ``problem``: an invalid design every bound
    violated, its objective 0 (the sampler ranks infeasible trials by their violations)."""
    if not record["valid"]:
        return 0.0, {name: 1.0 for name in problem.bound}
    metrics = measured(record)
    value = pipeline.objective(problem, metrics)
    violations = pipeline.violations(problem, metrics, better)
    # a bound on an estimate (an area from the gates alone) is broken by at least 1, the estimate
    # being a best case: the sampler must not take such a design for nearly met
    for name in record.get("estimated", ()):
        if name in violations:
            violations[name] = 1.0 + max(violations[name], 0.0)
    return (value if math.isfinite(value) else 0.0), violations


def warm_start(study: Any, block: str, pdk: str, problem: pipeline.Problem, cls: Any) -> int:
    """Add every evaluation already made in ``pdk`` that a design of ``problem`` could be (its fixed
    parameters, every searched value inside its domain) to an empty study, rescored under the
    problem; how many."""

    import optuna

    if study.trials:
        return 0
    dists = distributions(cls, pdk, problem)
    better = betters(block)
    added = 0
    for path in sorted((study_dir(block, pdk) / "evals").glob("*/instance.json")):
        record = json.loads(path.read_text())
        flat = record["params"]
        if any(flat.get(name) != _name(value) for name, value in problem.fixed.items()):
            continue
        params = {name: flat[name] for name in dists if name in flat}
        inside = (
            value in dist.choices if hasattr(dist, "choices") else dist.low <= value <= dist.high
            for value, dist in ((value, dists[name]) for name, value in params.items())
        )
        if not all(inside):
            continue
        value, constraints = score(problem, record, better)
        trial = optuna.trial.create_trial(
            params=params,
            distributions={name: dists[name] for name in params},
            value=value,
            constraints=constraints,
            user_attrs={"id": record["id"], "metrics": record["metrics"]},
        )
        study.add_trial(trial)
        added += 1
    return added


def optimize(block: str, pdk: str, label: str, budget: int, workers: int) -> Path:
    """Run ``label``'s study of ``block`` in ``pdk`` on to ``budget`` trials on ``workers``
    processes; the study's database. Each completed trial prints one line."""

    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")
    problems = pipeline.problems(import_module(f"flow.{block}.opt"), pdk)
    if label not in problems:
        raise SystemExit(f"no problem {label} of {block} in {pdk}: {', '.join(problems)}")
    problem = problems[label]
    cls = import_module(f"flow.{block}.params").Params
    better = betters(block)
    folder = study_dir(block, pdk)
    folder.mkdir(parents=True, exist_ok=True)
    database = folder / f"{label}.db"
    sampler = optuna.samplers.TPESampler(
        multivariate=True, group=True, constant_liar=True, n_startup_trials=max(10, workers), seed=0
    )
    study = optuna.create_study(
        storage=f"sqlite:///{database}", study_name=label, direction="minimize", sampler=sampler, load_if_exists=True
    )
    print(
        f"{label} of {block} in {pdk}: {warm_start(study, block, pdk, problem, cls)} evaluations rescored", flush=True
    )
    log = (folder / f"{label}.log").open("a")
    # trials a stopped run left running: failed, their designs asked again
    for stale in study.get_trials(deepcopy=False, states=(optuna.trial.TrialState.RUNNING,)):
        study.tell(stale.number, state=optuna.trial.TrialState.FAIL, skip_if_finished=True)
        study.enqueue_trial(stale.params, skip_if_exists=True)
    running: dict[Any, tuple[Any, Any]] = {}
    pool = _pool(workers)
    while running or len(study.trials) < budget:
        while len(running) < workers and len(study.trials) < budget:
            trial = study.ask()
            params = suggest(trial, cls, pdk, problem)
            running[pool.submit(evaluate, block, pdk, params, problem)] = (trial, params)
        done, _ = wait(running, return_when=FIRST_COMPLETED)
        broken = False
        for future in done:
            trial, params = running.pop(future)
            try:
                record = future.result()
            except BrokenProcessPool:
                broken = True
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                study.enqueue_trial(trial.params, skip_if_exists=True)
                continue
            except Exception:  # noqa: BLE001 - a broken evaluation fails its trial, not the study
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                print(f"[{trial.number}] failed: {traceback.format_exc(limit=3)[-600:]}", file=log, flush=True)
                continue
            value, constraints = score(problem, record, better)
            for name, violation in constraints.items():
                trial.set_constraint(name, violation)
            trial.set_user_attr("id", record["id"])
            trial.set_user_attr("metrics", record["metrics"])
            study.tell(trial, value)
            line = _line(trial.number, params, record, value, constraints)
            print(line, flush=True)
            print(line, file=log, flush=True)
        if broken:
            # a worker killed from outside breaks the whole pool: its other trials are lost with it,
            # failed and asked again, and a new pool takes over
            for trial, _params in running.values():
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                study.enqueue_trial(trial.params, skip_if_exists=True)
            running.clear()
            pool.shutdown(wait=False, cancel_futures=True)
            pool = _pool(workers)
            print(f"{datetime.now().astimezone():%H:%M:%S} a worker died: a new pool", file=log, flush=True)
    pool.shutdown()
    log.close()
    return database


def _pool(workers: int) -> ProcessPoolExecutor:
    """A fresh process per evaluation (hdl21 compiles a generated module in place, for one PDK)."""
    return ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1)


def _line(number: int, params: Any, record: dict[str, Any], value: float, constraints: dict[str, float]) -> str:
    """One completed trial: what it was, whether it met every bound, its cost and main metrics."""
    m = record["metrics"]
    feasible = record["valid"] and all(v <= 0 for v in constraints.values())
    fmt = lambda key, scale, unit: f"{m[key] * scale:.3g}{unit}" if isinstance(m.get(key), (int, float)) else "-"
    return (
        f"{datetime.now().astimezone():%H:%M:%S} [{number}] {'FEASIBLE' if feasible else 'infeasible'} cost={value:.3f} "
        f"{getattr(params, 'latch', '')} E={fmt('energy_0p5mv_j', 1e15, 'fJ')} A={fmt('layout_area_um2', 1, 'um2')} "
        f"noise={fmt('noise_v', 1e6, 'uV')} delay={fmt('delay_0p5mv_s', 1e9, 'ns')} "
        f"level={record['level']}{' cached' if record.get('cached') else ''} {record.get('seconds', 0)}s"
    )


def characterize_full(block: str, pdk: str, params: Any) -> dict[str, Any]:
    """A design's metrics from all its runs (``Level.FULL``: every common mode's S-curve), in its
    evaluation's folder (``full``), kept beside its record as ``metrics_full``."""

    import hdl21 as h

    h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
    folder = study_dir(block, pdk) / "evals" / identity(block, pdk, params)
    sweep = import_module(f"flow.{block}.sweep")
    metrics = sweep.record(simulate(block, sweep.runs(pdk, params, pipeline.Level.FULL), folder / "full")).metrics
    path = folder / "instance.json"
    record = json.loads(path.read_text())
    record["metrics_full"] = metrics
    write_record(path, record)
    return metrics


def finalize(block: str, pdk: str, label: str, count: int, workers: int) -> list[dict[str, Any]]:
    """The study's ``count`` best feasible designs characterized in full (``characterize_full``),
    each with its search-level and full metrics."""

    import optuna

    problem = pipeline.problems(import_module(f"flow.{block}.opt"), pdk)[label]
    cls = import_module(f"flow.{block}.params").Params
    finalists = best(block, pdk, label)[:count]
    designs = [suggest(optuna.trial.FixedTrial(entry["params"]), cls, pdk, problem) for entry in finalists]
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1) as pool:
        fulls = list(pool.map(characterize_full, [block] * len(designs), [pdk] * len(designs), designs))
    return [{**entry, "metrics_full": full} for entry, full in zip(finalists, fulls, strict=True)]


def best(block: str, pdk: str, label: str) -> list[dict[str, Any]]:
    """The study's feasible trials, cheapest first: each one's number, cost, parameters and metrics."""
    import optuna

    database = study_dir(block, pdk) / f"{label}.db"
    study = optuna.load_study(storage=f"sqlite:///{database}", study_name=label)
    feasible = [
        trial
        for trial in study.trials
        if trial.state == optuna.trial.TrialState.COMPLETE and all(v <= 0 for v in trial.constraints.values())
    ]
    return [
        {"number": t.number, "cost": t.value, "params": t.params, "metrics": t.user_attrs.get("metrics", {})}
        for t in sorted(feasible, key=lambda trial: trial.value)
    ]
