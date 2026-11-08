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
size, signoff and extraction), from a layout run of the block or a sweep run's record, whichever ran
last; a block's code names no run and no path under build/, so it finds a layout by its digest.
"""

from __future__ import annotations

import fcntl
import json
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from multiprocessing import get_context
from pathlib import Path

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
                with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as pool:
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
    """The newest layout entry of ``block``'s instance with ``params`` in ``pdk``: from the block's
    layout runs (``python -m flow layout <block> --instance ...``: ``build/<block>/layout/<stamp>/
    <pdk>/<name>/instance.json``, the record ``flow.__main__`` writes, by its id) and its sweep runs'
    records (``build/<block>/<stamp>/<pdk>/<digest>/instance.json``, the ``layout`` that
    ``python -m flow layout <block>`` adds), the newest run first, one whose layout stands (a GDS on
    disk, no error). Raises ``LookupError`` naming the command that lays it out."""

    from flow.sweep import runner

    ident = digest(flat_params(params))
    found = []
    for path in (runner.RUNS_DIR / block / "layout").glob(f"*/{pdk}/*/instance.json"):
        found.append((path.parts[-4], path))
    for path in (runner.RUNS_DIR / block).glob(f"*/{pdk}/{ident}/instance.json"):
        found.append((path.parts[-4], path))
    for stamp, path in sorted(found, key=lambda item: item[0], reverse=True):
        if not runner.RUN_STAMP.fullmatch(stamp):
            continue
        record = json.loads(path.read_text())
        entry = record.get("layout") or {}
        if record.get("id") != f"{pdk}__{ident}" or entry.get("error") or not entry.get("gds"):
            continue
        if (runner.ROOT / entry["gds"]).exists():
            return entry
    raise LookupError(
        f"{block} in {pdk} with these parameters ({ident}) is not laid out: "
        f"python -m flow layout {block} --pdk {pdk} --instance {ident}"
    )
