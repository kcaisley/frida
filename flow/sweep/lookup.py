"""Block characterizations by the parameters their generator takes, for the behavioral models.

    record = characterized("comp", "tsmc65", FRIDA1)

The record (an ``instance.json``: its metrics and condition sweeps) of the block's instance whose
parameters equal ``params`` in ``pdk``: from the block's newest sweep run where one matches,
else from ``build/models/<block>/<pdk>/<digest>/``, characterized there once, on demand, by the
block's ``sweep.characterize`` in a process of its own, as the sweep runs an instance. The same
parameters that build the block's netlist so fetch the numbers its behavioral model runs on.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from importlib import import_module
from multiprocessing import get_context
from pathlib import Path

from flow.sweep import flat_params
from flow.sweep.runner import ROOT, newest_run, write_record

MODELS_DIR = ROOT / "build/models"


def _key(flat: dict) -> str:
    return json.dumps(flat, sort_keys=True)


@cache
def _sweep_index(block: str) -> dict[tuple[str, str], Path]:
    """The newest sweep run's records of ``block``, by PDK and parameters."""

    try:
        run = newest_run(block)
    except (FileNotFoundError, ValueError):
        return {}
    index = {}
    for path in run.glob("*/*/*/instance.json"):
        record = json.loads(path.read_text())
        if record["error"] is None:
            index[(record["pdk"], _key(record["params"]))] = path
    return index


def _characterize(block: str, pdk: str, params, run_dir: Path) -> dict:
    """One instance characterized in this (fresh) process, as ``flow.sweep.runner.instance_job``
    characterizes a sweep's."""

    import hdl21 as h

    from flow.sweep import geometry

    sweep = import_module(f"flow.{block}.sweep")
    flat = flat_params(params)
    record = {
        "block": block,
        "pdk": pdk,
        "topology": "model",
        "sizing": run_dir.name,
        "params": flat,
        "metrics": {},
        "details": [],
        "waves": {},
        "error": None,
    }
    start = time.time()
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
        result = sweep.characterize(run_dir, pdk, params)
        module = sweep.GENERATOR(params)
        h.pdk.compile(module)
        record["metrics"] = {**geometry(module, pdk), **result.metrics}
        record["details"] = [dataclasses.asdict(detail) for detail in result.details]
        record["waves"] = result.waves
    except Exception:  # noqa: BLE001 - the record carries the failure
        record["error"] = traceback.format_exc(limit=6)[-4000:]
    record["seconds"] = round(time.time() - start, 1)
    write_record(run_dir / "instance.json", record)
    return record


def characterized(block: str, pdk: str, params, *, simulate: bool = True) -> dict:
    """The characterization record of ``block`` with ``params`` in ``pdk``.

    ``simulate=False`` only looks: a missing record raises ``LookupError`` instead of running
    the block's characterization (minutes of SPICE).
    """

    flat = flat_params(params)
    found = _sweep_index(block).get((pdk, _key(flat)))
    if found is not None:
        return json.loads(found.read_text())
    digest = hashlib.sha1(_key(flat).encode()).hexdigest()[:12]
    run_dir = MODELS_DIR / block / pdk / digest
    path = run_dir / "instance.json"
    if not simulate:
        # only looking: never wait on a characterization another process is running
        if not path.exists():
            raise LookupError(f"{block} in {pdk} with {flat} is not characterized ({run_dir})")
    else:
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        # one characterization however many models ask for it at once; the kernel releases a lock
        # whose holder died, so a lock file left behind holds nothing
        with (run_dir.parent / f"{digest}.lock").open("w") as lock:
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
