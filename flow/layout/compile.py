"""One layout compiler job (``flow/web/static/compile.html``): a netlist laid out in a PDK with open
tools only, its progress in ``status.json`` as it goes.

    python -m flow.layout.compile build/compile/<job>   # flow/web/jobs.py starts it

The job directory holds ``request.json`` (the netlist as written, the PDK, the style). The stages:
the netlist check (``flow.layout.lint``) and its schematic (``flow.util.netlist2image``); ALIGN on
its own (``flow.layout.align.build``, no floorplan: constraints, primitives, placement, routing,
followed in its log, then the GDS its post step finishes); DRC by gdscheck, with its own full deck
of an open PDK (``GDSCHECK_PROCESSES``, about a second) or else the repo's precheck; LVS by the PDK's KLayout deck
(``pdk.<pdk>.klayout.lvs``, or the approximate ``klayout_lvs``) against the netlist with its
library cells (``pdk/<pdk>/netlist/lvs_source.py``); and the viewer's layout (``flow.web.export``).
No commercial tool runs. DRC violations and an LVS mismatch are findings, not failures: the job
fails only when a stage cannot run. SIGTERM cancels it and every process it started.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGES = (
    ("check", "Check"),
    ("constraints", "Constraints"),
    ("primitives", "Primitives"),
    ("placement", "Placement"),
    ("routing", "Routing"),
    ("gds", "GDS"),
    ("drc", "DRC"),
    ("lvs", "LVS"),
    ("view", "View"),
)
# ALIGN's log lines that start each of its stages (its INFO lines, in order; either router's)
ALIGN_MARKS = (
    ("constraints", ("Starting topology identification",)),
    ("primitives", ("Completed topology identification",)),
    ("placement", ("Running Place & Route",)),
    ("routing", ("router started", "Starting bottom_up routing")),
    ("gds", ("router ended", "OUTPUT json at")),
)
PERCENT = re.compile(r"\.\.\.\.\. (\d+) %")
# gdscheck's built-in decks of the open PDKs, by frida's PDK name (``gdscheck list-suites -p <process>``)
GDSCHECK_PROCESSES = {"ihp130": "ihp-sg13g2"}
MAX_BOXES = 200  # markers kept per rule
TIMEOUT_S = 1800  # ALIGN's placer can search for hours on its own


def _gdscheck_runs(pdk: str) -> list[tuple[str, str]]:
    """The gdscheck runs (process, suite) that check a layout in ``pdk``: gdscheck's own full deck of
    an open PDK (``GDSCHECK_PROCESSES``; its geometry and antenna suites, not density, which a block
    alone fails), else the repo's precheck (``pdk/<pdk>/gdscheck/pdk.yml``); none without gdscheck."""

    if not shutil.which("gdscheck"):
        return []
    if pdk in GDSCHECK_PROCESSES:
        return [(GDSCHECK_PROCESSES[pdk], "core"), (GDSCHECK_PROCESSES[pdk], "antenna")]
    deck = ROOT / "pdk" / pdk / "gdscheck/pdk.yml"
    return [(str(deck), "precheck")] if deck.is_file() else []


def checks(pdk: str) -> dict:
    """The open checkers a PDK has: the DRC engines (gdscheck's full deck, or its precheck) and the
    LVS engine (None: no LVS)."""

    runs = _gdscheck_runs(pdk)
    drc = []
    if runs:
        drc.append(f"gdscheck {GDSCHECK_PROCESSES[pdk]}" if pdk in GDSCHECK_PROCESSES else "gdscheck precheck")
    lvs = None
    if find_spec(f"pdk.{pdk}.klayout"):
        if find_spec(f"pdk.{pdk}.klayout.lvs"):
            lvs = "KLayout"
        elif find_spec(f"pdk.{pdk}.klayout.klayout_lvs"):
            lvs = "KLayout (approximate)"
    return {"drc": drc, "lvs": lvs}


class Status:
    """The job's ``status.json``, rewritten whole (atomically) at every change."""

    def __init__(self, job_dir: Path, request: dict) -> None:
        self.path = job_dir / "status.json"
        self.lock = threading.RLock()  # the SIGTERM handler may write while the main thread holds it
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.data.update(
            id=job_dir.name,
            cell=request.get("cell"),
            pdk=request["pdk"],
            style=request["style"],
            created=request["created"],
            state="running",
            started=time.time(),
            message=None,
            error=None,
            diagnostics=[],
            stats=[],
            files={
                "layout": None,
                "schematic": None,
                "netlist": None,
                "gds": None,
                "log": f"compile/{job_dir.name}/job.log",
            },
            checks={"drc": None, "lvs": None},
        )
        self.data["stages"] = [
            {
                "key": key,
                "label": label,
                "state": "pending",
                "start": None,
                "end": None,
                "progress": None,
                "message": None,
            }
            for key, label in STAGES
        ]
        self.save()

    def stage(self, key: str) -> dict:
        return next(stage for stage in self.data["stages"] if stage["key"] == key)

    def set(self, key: str, state: str, message: str | None = None, progress: float | None = None) -> None:
        with self.lock:
            stage = self.stage(key)
            now = time.time()
            if state == "running" and stage["state"] != "running":
                stage["start"], stage["end"] = now, None
            if state in ("done", "failed", "skipped"):
                stage["start"] = stage["start"] or now
                stage["end"] = now
            if state == "pending":
                stage["start"] = stage["end"] = None
            stage.update(state=state, progress=progress, message=message)
            if message and state in ("running", "failed"):
                self.data["message"] = message
            self.save()

    def update(self, **values) -> None:
        with self.lock:
            for key, value in values.items():
                if key in ("diagnostics", "stats"):
                    self.data[key] += value
                elif isinstance(value, dict) and isinstance(self.data.get(key), dict):
                    self.data[key].update(value)
                else:
                    self.data[key] = value
            self.save()

    def save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, separators=(",", ":")))
        os.replace(temporary, self.path)

    def running(self) -> str | None:
        return next((stage["key"] for stage in self.data["stages"] if stage["state"] == "running"), None)


def _descendants(pid: int) -> list[int]:
    """Every process below ``pid`` (ALIGN runs in a session of its own, so not its group)."""

    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            parent = int((entry / "stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            continue
        children.setdefault(parent, []).append(int(entry.name))
    out, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            out.append(child)
            todo.append(child)
    return out


def _watch_align(log: Path, status: Status, stop: threading.Event) -> None:
    """Follow ALIGN's log into the stages: each mark starts its stage and ends the ones before it;
    the placer's percentages are the placement's progress. A log that shrinks is a new attempt
    (build.py retries in any outline, or with ALIGN's own router)."""

    order = [key for key, _ in ALIGN_MARKS]
    size, reached = 0, -1
    while not stop.wait(0.5):
        if not log.exists():
            continue
        text = log.read_text(errors="replace")
        if len(text) < size:  # a new attempt: build.py printed why to the job's log
            reached = -1
            for key in order:
                status.set(key, "pending")
            said = (log.parents[2] / "job.log").read_text(errors="replace").splitlines()
            last = next((line for line in reversed(said) if "; any outline" in line or "default router" in line), "")
            why = "with ALIGN's default router" if "default router" in last else "in any outline"
            status.set("constraints", "running", f"ALIGN again, {why}")
        size = len(text)
        now = max(
            (index for index, (_, marks) in enumerate(ALIGN_MARKS) if any(mark in text for mark in marks)), default=-1
        )
        if now > reached:
            for key in order[max(reached, 0) : now]:
                status.set(key, "done")
            status.set(order[now], "running", f"ALIGN: {dict(STAGES)[order[now]].lower()}")
            reached = now
        if order[max(reached, 0)] == "placement":
            percents = PERCENT.findall(text)
            if percents:
                status.set("placement", "running", f"ALIGN: placement {percents[-1]} %", int(percents[-1]) / 100)


def _markers(report: Path, top: str) -> dict[str, dict]:
    """A KLayout report database's violations per rule: count, description and their boxes (µm,
    in the top cell, through each item's cell references)."""

    from klayout import db, rdb  # db binds the geometry types the report's values return

    del db
    database = rdb.ReportDatabase("")
    database.load(str(report))
    rules: dict[str, dict] = {}
    for item in database.each_item():
        category = database.category_by_id(item.category_id())
        entry = rules.setdefault(category.path(), {"count": 0, "description": category.description, "boxes": []})
        entry["count"] += 1
        if len(entry["boxes"]) >= MAX_BOXES:
            continue
        cell = database.cell_by_id(item.cell_id())
        trans = None
        if cell is not None and cell.name() != top:
            reference = next(iter(cell.each_reference()), None)
            trans = reference.trans() if reference is not None else None
        for value in item.each_value():
            box = None
            if value.is_box():
                box = value.box()
            elif value.is_polygon():
                box = value.polygon().bbox()
            elif value.is_edge():
                box = value.edge().bbox()
            elif value.is_edge_pair():
                box = value.edge_pair().bbox()
            elif value.is_path():
                box = value.path().bbox()
            if box is None:
                continue
            if trans is not None:
                box = box.transformed(trans)
            entry["boxes"].append([round(box.left, 4), round(box.bottom, 4), round(box.right, 4), round(box.top, 4)])
    return rules


def _drc(pdk: str, gds: Path, top: str, run_dir: Path) -> list[dict]:
    """gdscheck's runs (``_gdscheck_runs``): one diagnostic per violated rule."""

    out = []
    work = run_dir / "gdscheck"
    work.mkdir(parents=True, exist_ok=True)
    for process, suite in _gdscheck_runs(pdk):
        report = work / f"{suite}.lyrdb"
        command = [
            "gdscheck", "run", "-i", str(gds), "-p", process, "-t", top, "-s", suite, "-r", str(report),
            "--threads", "4",
        ]  # fmt: skip
        done = subprocess.run(command, capture_output=True, text=True, check=False)
        (work / f"{suite}.log").write_text(done.stdout + done.stderr)
        if not report.exists():
            raise RuntimeError(f"gdscheck ({suite}) wrote no report: {(done.stdout + done.stderr)[-600:]}")
        out += [_violation("gdscheck", rule, entry) for rule, entry in _markers(report, top).items()]
    return out


def _violation(engine: str, rule: str, entry: dict) -> dict:
    description = entry["description"] if entry["description"] and entry["description"] != rule else ""
    return {
        "severity": "error",
        "source": "drc",
        "engine": engine,
        "rule": rule,
        "count": entry["count"],
        "message": f"{rule}: {description}" if description else rule,
        "boxes": entry["boxes"],
    }


def _lvs_findings(report: Path) -> list[str]:
    """The mismatched nets, devices and pins of a KLayout LVS database, as lines."""

    from klayout import db

    lvs = db.LayoutVsSchematic()
    lvs.read(str(report))
    xref = lvs.xref()
    match = db.NetlistCrossReference.Match
    lines = []

    def name(thing) -> str:
        return thing.expanded_name() if thing is not None else "(none)"

    for circuit in xref.each_circuit_pair():
        for pair in xref.each_net_pair(circuit):
            if pair.status() != match:
                lines.append(f"net {name(pair.first())} (layout) / {name(pair.second())} (netlist): {pair.status()}")
        for pair in xref.each_device_pair(circuit):
            if pair.status() != match:
                lines.append(f"device {name(pair.first())} (layout) / {name(pair.second())} (netlist): {pair.status()}")
        for pair in xref.each_pin_pair(circuit):
            if pair.status() != match:
                lines.append(f"pin {name(pair.first())} (layout) / {name(pair.second())} (netlist): {pair.status()}")
    return lines


def _lvs(
    pdk: str, gds: Path, top: str, netlist: Path, cell: str, run_dir: Path, engine: str
) -> tuple[bool, list[dict]]:
    """LVS of the layout against the netlist with its library cells and what the post step added."""

    from flow.layout.pdkproc import in_pdk
    from flow.layout.signoff import add_post_devices

    run_dir.mkdir(parents=True, exist_ok=True)
    source = run_dir / "source.cdl"
    in_pdk(pdk, f"pdk.{pdk}.netlist.lvs_source", "lvs_source", netlist, source)
    extra = Path(f"{gds}.extra.sp")
    if extra.exists():
        add_post_devices(pdk, source, extra, cell)
    if engine == "KLayout":
        correct, _log = import_module(f"pdk.{pdk}.klayout.lvs").lvs(gds, top, source, cell, run_dir)
        reports = sorted(run_dir.rglob("*.lvsdb"))
    else:
        correct = import_module(f"pdk.{pdk}.klayout.klayout_lvs").lvs(str(gds), top, str(source), cell)
        reports = [Path(f"{gds}.lvsdb")]
    findings = []
    if not correct:
        lines = []
        for report in reports:
            if report.exists():
                try:
                    lines += _lvs_findings(report)
                except Exception as error:  # noqa: BLE001 - the summary still stands
                    lines.append(f"(the LVS database did not read: {error})")
        findings = [{"severity": "error", "source": "lvs", "engine": engine, "message": line} for line in lines[:60]]
        findings = findings or [
            {"severity": "error", "source": "lvs", "engine": engine, "message": "the layout does not match the netlist"}
        ]
    return correct, findings


def run(job_dir: Path) -> None:
    """The job in ``job_dir``, start to end."""

    from flow.layout import lint
    from flow.layout.pdkproc import in_pdk

    request = json.loads((job_dir / "request.json").read_text())
    pdk, style = request["pdk"], request["style"]
    status = Status(job_dir, request)
    rel = f"compile/{job_dir.name}"

    def cancel(_signum, _frame) -> None:
        for pid in _descendants(os.getpid()):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        current = status.running()
        if current:
            status.set(current, "failed", "cancelled")
        status.update(state="cancelled", message="Cancelled", seconds=round(time.time() - status.data["started"], 1))
        os._exit(1)

    signal.signal(signal.SIGTERM, cancel)
    try:
        status.set("check", "running", "Checking the netlist")
        manifest = in_pdk(pdk, "flow.layout.lint", "pdk_manifest")
        result = lint.check(request["netlist"], manifest)
        status.update(diagnostics=result.diagnostics, stats=result.stats, cell=result.top)
        if not result.ok:
            status.set("check", "failed", "The netlist has errors")
            status.update(state="failed")
            return
        cell = result.top
        netlist = job_dir / "input.sp"
        netlist.write_text(lint.normalize(result))
        (job_dir / "source.sp").write_text(request["netlist"])
        status.update(files={"netlist": f"{rel}/input.sp", "source": f"{rel}/source.sp"})
        if any(device.kind == "m" for device in result.devices):
            try:
                from flow.util.netlist2image import render

                render(netlist, job_dir / "schematic.svg")
                status.update(files={"schematic": f"{rel}/schematic.svg"})
            except Exception as error:  # noqa: BLE001 - the layout does not need it
                status.update(
                    diagnostics=[{"severity": "info", "source": "netlist", "message": f"no schematic: {error}"}]
                )
        status.set("check", "done")

        from flow.layout.align.build import build

        os.environ.setdefault("ALIGN_TIMEOUT", str(TIMEOUT_S))
        status.set("constraints", "running", "ALIGN: its PDK and design directories")
        stop = threading.Event()
        watcher = threading.Thread(
            target=_watch_align, args=(job_dir / "align" / cell / "schematic2layout.log", status, stop), daemon=True
        )
        watcher.start()
        try:
            gds = build(pdk, None, netlist, job_dir / "align", name=cell, symmetric=style == "symmetric")
        except Exception as error:  # noqa: BLE001 - ALIGN's failure is the job's finding
            stop.set()
            watcher.join()
            text = str(error)
            status.update(diagnostics=[{"severity": "error", "source": "align", "message": text.splitlines()[0][:400]}])
            status.set(status.running() or "placement", "failed", "ALIGN failed")
            status.update(state="failed", error=text[-3000:])
            return
        stop.set()
        watcher.join()
        for key, _ in ALIGN_MARKS:
            if status.stage(key)["state"] != "done":
                status.set(key, "done")
        status.update(files={"gds": f"{rel}/align/{cell}/{gds.name}"})

        from klayout import db

        layout = db.Layout()
        layout.read(str(gds))
        top_cell = max(layout.top_cells(), key=lambda item: item.bbox().area())
        top, box = top_cell.name, top_cell.dbbox()
        engines = checks(pdk)

        status.set("drc", "running", f"DRC: {', '.join(engines['drc']) or 'none'}")
        if engines["drc"]:
            violations = _drc(pdk, gds, top, job_dir / "drc")
            total = sum(item["count"] for item in violations)
            status.update(
                diagnostics=violations,
                checks={"drc": {"engines": engines["drc"], "violations": total, "clean": total == 0}},
                stats=[{"group": "DRC", "label": engines["drc"][0], "value": total}],
            )
            status.set("drc", "done", "DRC clean" if not total else f"DRC: {total} violations")
        else:
            status.set("drc", "skipped", "no open DRC deck for this PDK")

        if engines["lvs"]:
            status.set("lvs", "running", f"LVS: {engines['lvs']}")
            correct, findings = _lvs(pdk, gds, top, netlist, cell, job_dir / "lvs", engines["lvs"])
            status.update(
                diagnostics=findings,
                checks={"lvs": {"engine": engines["lvs"], "correct": correct}},
                stats=[{"group": "LVS", "label": engines["lvs"], "value": "correct" if correct else "incorrect"}],
            )
            status.set("lvs", "done", "LVS correct" if correct else "LVS incorrect")
        else:
            status.set("lvs", "skipped", "no open LVS deck for this PDK")

        status.set("view", "running", "Writing the viewer's layout")
        from flow.web.export import export_layout

        summary = export_layout(str(gds), pdk, str(job_dir / "layout.json"))
        gate = next((item["value"] for item in result.stats if item["label"] == "Gate area"), 0)
        area = box.width() * box.height()
        status.update(
            files={"layout": f"{rel}/layout.json"},
            stats=[
                {"group": "Layout", "label": "Width", "value": round(box.width(), 3), "unit": "µm"},
                {"group": "Layout", "label": "Height", "value": round(box.height(), 3), "unit": "µm"},
                {"group": "Layout", "label": "Area", "value": round(area, 2), "unit": "µm²"},
                {"group": "Layout", "label": "Gate area / area", "value": round(gate / area, 4) if area else None},
                {"group": "Layout", "label": "Layers", "value": len(summary["layers"])},
                {"group": "Layout", "label": "Style", "value": style},
            ],
        )
        status.set("view", "done")
        drc, lvs = status.data["checks"]["drc"], status.data["checks"]["lvs"]
        parts = [
            "DRC clean" if drc and drc["clean"] else f"DRC: {drc['violations']} violations" if drc else "no DRC",
            ("LVS correct" if lvs["correct"] else "LVS incorrect") if lvs else "no LVS",
        ]
        status.update(state="done", message=" · ".join(parts))
    except Exception:  # noqa: BLE001 - the page shows why
        text = traceback.format_exc()
        status.set(status.running() or "check", "failed", text.strip().splitlines()[-1][:300])
        status.update(state="failed", error=text[-4000:])
    finally:
        status.update(seconds=round(time.time() - status.data["started"], 1))


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
