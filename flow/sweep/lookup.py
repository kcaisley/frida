"""Block characterizations by the parameters their generator takes, for the behavioral models.

    record = characterized("comp", "tsmc65", FRIDA1)

The record (an ``instance.json``: its metrics and condition sweeps) of the block's instance whose
parameters equal ``params`` in ``pdk``: an instance is its parameters, so it is found by their
digest (``flow.sweep.runner.digest``): in the newest of the block's runs in that PDK that holds it
(``build/<block>/<run>/<pdk>/<name>/``; a run of some PDKs or instances alone leaves the others' in
the runs before) where it ran there, else in ``build/models/<block>/<pdk>/<digest>/``,
characterized there once, on demand, in a process of its own, by the CLI's netlist, sim and record
steps (``flow.sweep.runner.characterize``). The same parameters
that build the block's netlist so fetch the numbers its behavioral model runs on.

    entry = laid_out("adc", "tsmc65", params)

The newest layout of the instance with these parameters (``laid_out``): its layout entry (its GDS,
size, signoff and extraction), from the newest of the block's runs whose record of it has one (the
CLI's layout steps join it there), or a layout run from before them
(``build/<block>/layout/<stamp>/``); a block's code names no run and no path under build/, so it
finds a layout by its digest.
"""

from __future__ import annotations

import fcntl
import json
import re
from functools import cache
from pathlib import Path

from flow.logs import spawned
from flow.sweep import flat_params
from flow.sweep.runner import ROOT, digest

MODELS_DIR = ROOT / "build/models"


@cache
def _pdk_runs(block: str, pdk: str) -> tuple[Path, ...]:
    """The block's runs that ran in ``pdk``, the newest first."""
    from flow.sweep import runner

    return tuple(
        sorted((run for run in runner._runs(block) if (run / pdk).is_dir()), key=runner.run_time, reverse=True)
    )


@cache
def _run_instances(run: Path, pdk: str) -> dict[str, Path]:
    from flow.sweep import runner

    return runner.instance_dirs(run, pdk)


def _sweep_record(block: str, pdk: str, ident: str) -> dict | None:
    """The record of ``block``'s instance with this digest from the newest run in ``pdk`` that
    holds it (a run of some instances alone leaves the others' in the runs before), where it ran
    there without error."""

    for run in _pdk_runs(block, pdk):
        folder = _run_instances(run, pdk).get(ident)
        if folder is not None:
            record = json.loads((folder / "instance.json").read_text())
            if not record["metrics"] and record["error"] is None:  # a record of its layout alone
                continue
            return record if record["error"] is None else None
    return None


def _characterize(block: str, pdk: str, params, run_dir: Path) -> dict:
    """One instance characterized in this (fresh) process, as the CLI's netlist, sim and record
    steps characterize a run's (``flow.sweep.runner.characterize``)."""

    from flow.sweep.runner import characterize

    return characterize(block, run_dir, pdk, params)


def characterized(block: str, pdk: str, params, *, simulate: bool = True) -> dict:
    """The characterization record of ``block`` with ``params`` in ``pdk``.

    ``simulate=False`` only looks: a missing record raises ``LookupError`` instead of running
    the block's characterization (minutes of SPICE).
    """

    ident = digest(flat_params(params))
    found = _sweep_record(block, pdk, ident)
    if found is not None:
        return found
    run_dir = MODELS_DIR / block / pdk / ident
    path = run_dir / "instance.json"
    if not simulate:
        # only looking: never wait on a characterization another process is running
        if not path.exists():
            raise LookupError(f"{block} in {pdk} with {flat_params(params)} is not characterized ({run_dir})")
    else:
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        # one characterization however many models ask for it at once; the kernel releases a lock
        # whose holder died, so a lock file left behind holds nothing
        with (run_dir.parent / f"{ident}.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not path.exists():
                with spawned(1) as pool:  # its log is the caller's (a step's, where a step looks it up)
                    pool.submit(_characterize, block, pdk, params, run_dir).result()
    record = json.loads(path.read_text())
    if record["error"] is not None:
        raise RuntimeError(f"{block} in {pdk} failed its characterization ({path}):\n{record['error']}")
    return record


def detail(record: dict, name: str) -> dict:
    """One condition sweep of a record, by its name."""

    for entry in record["details"]:
        if entry["name"] == name:
            return entry
    raise KeyError(f"{record['block']} record has no detail {name!r}")


def laid_out(block: str, pdk: str, params) -> dict:
    """The newest layout entry of ``block``'s instance with ``params`` in ``pdk``: from the record
    of it (by its id: ``<run>/<pdk>/<name>/instance.json``, a named instance's by its name, a
    grid's by its digest) in the block's runs and its layout runs from before the CLI's steps
    (``build/<block>/layout/<stamp>/``), the newest run first, one whose layout stands (a GDS on
    disk, no error). Raises ``LookupError`` naming the command that lays it out."""

    from flow.sweep import runner

    ident = digest(flat_params(params))
    history = runner.RUNS_DIR / block / "layout"
    runs = {*runner._runs(block), *(path for path in history.glob("*") if runner.RUN_STAMP.fullmatch(path.name))}
    for run in sorted(runs, key=runner.run_time, reverse=True):
        folders = sorted(path for path in (run / pdk).glob("*") if not re.fullmatch(r"[0-9a-f]{12}", path.name))
        for path in (folder / "instance.json" for folder in [run / pdk / ident, *folders]):
            if not path.is_file():
                continue
            record = json.loads(path.read_text())
            entry = record.get("layout") or {}
            if record.get("id") != f"{pdk}__{ident}" or entry.get("error") or not entry.get("gds"):
                continue
            if (runner.ROOT / entry["gds"]).exists():
                return entry
    raise LookupError(
        f"{block} in {pdk} with these parameters ({ident}) is not laid out: "
        f"python -m flow {block} --to pex --pdk {pdk} --instance {ident}"
    )
