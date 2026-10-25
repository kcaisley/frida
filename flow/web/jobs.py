"""The layout compiler's side of the viewer's server (``flow/web/server.py``, ``/api/compile/*``):
the PDKs it lays out in and their open checkers, the netlist check as you type, and the jobs
(``flow.layout.compile``, one process each, at most ``MAX_RUNNING`` at a time, the rest queued).

Each job is a directory ``build/compile/<id>/`` (its request, ``status.json``, ALIGN's work, the
reports and the viewer's layout), served under ``/data/compile/<id>/``; the check's netlists and
schematics go to ``build/compile/check/`` by content hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from functools import cache
from pathlib import Path

from flow.web.export import PDKS

ROOT = Path(__file__).resolve().parents[2]
JOBS_DIR = ROOT / "build/compile"
CHECK_DIR = JOBS_DIR / "check"
MAX_RUNNING = 4
MAX_NETLIST = 200_000  # characters
JOB_ID = re.compile(r"[0-9]{8}_[0-9]{6}_[A-Za-z0-9_]+\Z")
STYLES = ("symmetric", "dense")

_lock = threading.Lock()
_queue: list[str] = []
_running: dict[str, subprocess.Popen] = {}
_scheduler: threading.Thread | None = None


@cache
def manifest(pdk: str) -> dict:
    """The PDK's row-transistor models and library cells (``flow.layout.lint.pdk_manifest``)."""

    from flow.layout.pdkproc import in_pdk

    return in_pdk(pdk, "flow.layout.lint", "pdk_manifest")


def _unavailable(pdk: str) -> str | None:
    """Why the compiler cannot lay out in ``pdk`` here, or None."""

    from flow.layout.align.run import ALIGN_HOME

    if not (ROOT / "pdk" / pdk / "layout/tech.py").is_file():
        return "its PDK submodule is not checked out"
    if not (ALIGN_HOME / "general/bin/python").is_file():
        return f"no ALIGN install at {ALIGN_HOME} (ALIGN_HOME)"
    return None


@cache
def pdks() -> dict:
    """``/api/compile/pdks``: each PDK, whether it can be used, its checkers, an example netlist."""

    from flow.layout import lint
    from flow.layout.compile import checks
    from flow.util.mos_models import _assigned

    out, examples = [], {}
    for pdk in PDKS:
        reason = _unavailable(pdk)
        engines = checks(pdk) if reason is None else {"drc": [], "lvs": None}
        if reason is None:
            models = _assigned(ROOT / "pdk" / pdk / "layout/tech.py", "MODELS")
            per_finger = bool(_assigned(ROOT / "pdk" / pdk / "hdl21/pdk_logic.py", "MOS_W_PER_FINGER"))
            examples[pdk] = lint.example({"models": models, "cells": {}, "w_per_finger": per_finger})
        drc = engines["drc"][0] if engines["drc"] else None
        note = f"DRC by {drc}" if drc else "no DRC"
        note += f"; LVS by {engines['lvs']}" if engines["lvs"] else "; no LVS"
        out.append(
            {
                "name": pdk,
                "available": reason is None,
                "reason": reason,
                "drc": engines["drc"],
                "lvs": engines["lvs"],
                "note": note,
            }
        )
    default = next((item["name"] for item in out if item["available"] and item["lvs"] == "KLayout"), None)
    default = default or next((item["name"] for item in out if item["available"]), None)
    return {"pdks": out, "default": default, "example": examples}


def _request(netlist: object, pdk: object) -> tuple[str, str]:
    if not isinstance(netlist, str) or not isinstance(pdk, str):
        raise TypeError("a netlist and a PDK name")
    if len(netlist) > MAX_NETLIST:
        raise ValueError(f"the netlist is longer than {MAX_NETLIST} characters")
    if pdk not in PDKS:
        raise ValueError(f"no PDK {pdk}")
    reason = _unavailable(pdk)
    if reason:
        raise ValueError(f"{pdk}: {reason}")
    return netlist, pdk


def check(body: dict) -> dict:
    """``/api/compile/check``: the netlist's diagnostics and statistics, and its schematic."""

    from flow.layout import lint

    netlist, pdk = _request(body.get("netlist"), body.get("pdk"))
    result = lint.check(netlist, manifest(pdk))
    out = {"ok": result.ok, "top": result.top, "diagnostics": result.diagnostics, "stats": result.stats}
    out["schematic"] = out["netlist"] = None
    if result.top and any(device.kind == "m" for device in result.devices):
        text = lint.normalize(result)
        key = hashlib.sha256(f"{pdk}\n{text}".encode()).hexdigest()[:20]
        CHECK_DIR.mkdir(parents=True, exist_ok=True)
        netlist_path, schematic = CHECK_DIR / f"{key}.sp", CHECK_DIR / f"{key}.svg"
        if not netlist_path.exists():
            netlist_path.write_text(text)
        out["netlist"] = f"compile/check/{key}.sp"
        if not schematic.exists():
            try:
                from flow.util.netlist2image import render

                render(netlist_path, schematic)
            except Exception as error:  # noqa: BLE001 - shown as a note, the check stands
                out["diagnostics"].append(
                    {"severity": "info", "source": "netlist", "message": f"no schematic: {error}"}
                )
        if schematic.exists():
            out["schematic"] = f"compile/check/{key}.svg"
    return out


def submit(body: dict) -> str:
    """``POST /api/compile/jobs``: a new job, queued; its id. Raises ``ValueError`` (with the
    diagnostics as its second argument) for a netlist with errors."""

    from flow.layout import lint
    from flow.layout.compile import STAGES

    netlist, pdk = _request(body.get("netlist"), body.get("pdk"))
    style = body.get("style", "symmetric")
    if style not in STYLES:
        raise ValueError(f"style is one of {', '.join(STYLES)}")
    result = lint.check(netlist, manifest(pdk))
    if not result.ok:
        raise ValueError("the netlist has errors", result.diagnostics)
    created = time.time()
    stem = f"{time.strftime('%Y%m%d_%H%M%S', time.localtime(created))}_{result.top}"
    job_id, n = stem, 1
    while (JOBS_DIR / job_id).exists():
        n += 1
        job_id = f"{stem}_{n}"
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)
    request = {"netlist": netlist, "pdk": pdk, "style": style, "cell": result.top, "created": created}
    (job_dir / "request.json").write_text(json.dumps(request, indent=1) + "\n")
    (job_dir / "source.sp").write_text(netlist)  # as written, for the page to reopen
    stages = [
        {"key": key, "label": label, "state": "pending", "start": None, "end": None, "progress": None, "message": None}
        for key, label in STAGES
    ]
    status = {
        "id": job_id, "cell": result.top, "pdk": pdk, "style": style, "created": created, "state": "queued",
        "stages": stages, "message": "Queued", "error": None, "diagnostics": result.diagnostics,
        "stats": result.stats, "checks": {"drc": None, "lvs": None},
        "files": {
            "layout": None, "schematic": None, "netlist": None, "gds": None,
            "source": f"compile/{job_id}/source.sp", "log": f"compile/{job_id}/job.log",
        },
    }  # fmt: skip
    (job_dir / "status.json").write_text(json.dumps(status, separators=(",", ":")))
    with _lock:
        _queue.append(job_id)
    _ensure_scheduler()
    return job_id


def _job_dir(job_id: str) -> Path:
    if not JOB_ID.match(job_id or "") or not (JOBS_DIR / job_id / "request.json").is_file():
        raise KeyError(f"no job {job_id}")
    return JOBS_DIR / job_id


def status(job_id: str) -> dict:
    """``/api/compile/jobs/<id>``: the job's ``status.json``; a job that is neither queued nor
    running here but says so (the server restarted under it) has failed."""

    job_dir = _job_dir(job_id)
    data = json.loads((job_dir / "status.json").read_text())
    with _lock:
        alive = job_id in _queue or job_id in _running
    if data["state"] in ("queued", "running") and not alive:
        data.update(state="failed", message="Interrupted: the server stopped while it ran")
    if data["state"] == "queued":
        with _lock:
            ahead = _queue.index(job_id) if job_id in _queue else 0
        data["message"] = f"Queued ({ahead} ahead)" if ahead else "Queued: starting"
    return data


def jobs() -> dict:
    """``/api/compile/jobs``: the latest 50 jobs, newest first."""

    out = []
    for job_dir in sorted((p for p in JOBS_DIR.glob("*") if JOB_ID.match(p.name)), reverse=True)[:50]:
        try:
            data = status(job_dir.name)
        except (KeyError, OSError, ValueError):
            continue
        out.append({key: data.get(key) for key in ("id", "cell", "pdk", "style", "state", "created", "seconds")})
    return {"jobs": out}


def cancel(job_id: str) -> None:
    """``POST /api/compile/jobs/<id>/cancel``: a queued job leaves the queue; a running one is
    stopped (SIGTERM: it stops what it started and says so; SIGKILL after five seconds)."""

    job_dir = _job_dir(job_id)
    with _lock:
        queued = job_id in _queue
        if queued:
            _queue.remove(job_id)
        process = _running.get(job_id)
    if queued:
        data = json.loads((job_dir / "status.json").read_text())
        data.update(state="cancelled", message="Cancelled")
        (job_dir / "status.json").write_text(json.dumps(data, separators=(",", ":")))
    elif process is not None and process.poll() is None:
        process.send_signal(signal.SIGTERM)

        def reap() -> None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)

        threading.Thread(target=reap, daemon=True).start()


def _start(job_id: str) -> subprocess.Popen:
    job_dir = JOBS_DIR / job_id
    environment = dict(
        os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONUNBUFFERED="1"
    )
    with (job_dir / "job.log").open("w") as log:
        return subprocess.Popen(
            [sys.executable, "-m", "flow.layout.compile", str(job_dir)],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _schedule() -> None:
    """Reap finished jobs and start queued ones, forever (the server's daemon thread)."""

    while True:
        with _lock:
            for job_id, process in list(_running.items()):
                if process.poll() is not None:
                    del _running[job_id]
            while _queue and len(_running) < MAX_RUNNING:
                job_id = _queue.pop(0)
                _running[job_id] = _start(job_id)
        time.sleep(0.5)


def _ensure_scheduler() -> None:
    global _scheduler
    with _lock:
        if _scheduler is None:
            _scheduler = threading.Thread(target=_schedule, name="compile-jobs", daemon=True)
            _scheduler.start()
