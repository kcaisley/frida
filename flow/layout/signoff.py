"""Technology-dispatched layout DRC, LVS, and PEX orchestration.

Each PDK provides ``pdk/<pdk>/signoff.py`` with keyword functions ``run_drc`` (gdscheck where
installed, then the PDK's DRC; writes ``<run_dir>/drc_violations.json`` and raises unless clean),
``run_lvs`` (whether LVS is correct, and its report) and, where the PDK has extraction,
``run_pex`` (against a schematic) and ``run_layout_pex`` (a layout by its own net names with the
kit's extractor, ``calibre_pex.py``). The provider picks the checker it has (Calibre, Assura or
KLayout). ``run_layout_pex`` here extracts by FasterCap through KLayout-PEX (``flow.layout.kpex``)
unless asked for the kit's (``Extractor.CALIBRE``, its manual check). ``row_signoff`` checks a
standard-cell row layout (flow/layout) with DRC and LVS.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum, auto
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Literal

from klayout import db

from flow.layout import kpex
from flow.layout.kpex import Extractor
from flow.layout.pdkproc import pdk_value


@dataclass(frozen=True)
class SignoffParams:
    """Paths, top cells, and comparison policy for one complete signoff run."""

    technology: str
    gds_path: Path
    layout_top: str
    lvs_source_path: Path
    source_top: str
    output_stem: str
    pex_source_path: Path | None = None
    lvs_expectation: Literal["correct", "incorrect"] = "correct"
    lvs_required_report_fragments: tuple[str, ...] = ()
    pdk_options: Any = None


@dataclass(frozen=True)
class SignoffResult:
    """Persistent reports and status produced by one signoff run."""

    drc_report: Path
    lvs_report: Path
    lvs_correct: bool
    pex_netlist: Path
    warnings: tuple[str, ...] = ()


def _provider(technology: str) -> Any:
    if not technology or not technology.replace("_", "").isalnum():
        raise ValueError(f"invalid technology name {technology!r}")
    provider = import_module(f"pdk.{technology}.signoff")
    for function in ("run_drc", "run_lvs"):
        if not callable(getattr(provider, function, None)):
            raise TypeError(f"pdk.{technology}.signoff does not implement {function}()")
    return provider


def _validate(params: SignoffParams, run_dir: Path) -> None:
    if not params.layout_top or not params.source_top or not params.output_stem:
        raise ValueError("layout top, source top, and output stem must be nonempty")
    if params.lvs_expectation not in ("correct", "incorrect"):
        raise ValueError("lvs_expectation must be 'correct' or 'incorrect'")
    for path in (params.gds_path, params.lvs_source_path, params.pex_source_path or params.lvs_source_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if run_dir.resolve() == Path(__file__).resolve().parents[2]:
        raise ValueError("signoff must run beneath a dedicated result directory")


def run_drc(params: SignoffParams, run_dir: Path) -> Path:
    """Dispatch DRC, including the provider's mandatory fast precheck."""

    _validate(params, run_dir)
    return _provider(params.technology).run_drc(
        run_dir=run_dir,
        gds_path=params.gds_path,
        layout_top=params.layout_top,
        options=params.pdk_options,
    )


def run_lvs(params: SignoffParams, run_dir: Path) -> tuple[bool, Path]:
    """Dispatch LVS and return its raw correctness status and report."""

    _validate(params, run_dir)
    return _provider(params.technology).run_lvs(
        run_dir=run_dir,
        gds_path=params.gds_path,
        source_path=params.lvs_source_path,
        layout_top=params.layout_top,
        source_top=params.source_top,
        options=params.pdk_options,
    )


def run_pex(params: SignoffParams, run_dir: Path) -> Path:
    """Dispatch PEX using its explicit conductive source view."""

    _validate(params, run_dir)
    provider = _provider(params.technology)
    if not callable(getattr(provider, "run_pex", None)):
        raise TypeError(f"pdk.{params.technology}.signoff has no extraction (run_pex)")
    return provider.run_pex(
        run_dir=run_dir,
        gds_path=params.gds_path,
        source_path=params.pex_source_path or params.lvs_source_path,
        layout_top=params.layout_top,
        source_top=params.source_top,
        output_stem=params.output_stem,
        options=params.pdk_options,
    )


def run_layout_pex(
    technology: str,
    gds_path: Path,
    layout_top: str,
    output_stem: str,
    run_dir: Path,
    extractor: Extractor = Extractor.KLAYOUT,
    tolerance: float | None = None,
    texts: list[tuple[str, int, int, str]] = (),
) -> Path:
    """A layout-only extraction (3D, by the layout's own net names, nothing compared): FasterCap
    through KLayout-PEX (``flow.layout.kpex``), or the kit's extractor (``Extractor.CALIBRE``).

    For primitives' test structures and arrays: plain metal with labelled terminals has no device to
    recognize and no schematic; and a block's parasitics, at a looser ``tolerance`` (KLayout-PEX's
    FasterCap; None: ``kpex.TOLERANCE``), its nets named by ``texts`` where the layout has no label
    (KLayout-PEX). Returns the extracted Spectre netlist.
    """

    if not gds_path.is_file():
        raise FileNotFoundError(gds_path)
    if extractor is Extractor.KLAYOUT:
        return kpex.run_layout_pex(
            technology, gds_path, layout_top, output_stem, run_dir, tolerance=tolerance or kpex.TOLERANCE, texts=texts
        )
    provider = _provider(technology)
    if not callable(getattr(provider, "run_layout_pex", None)):
        raise TypeError(f"pdk.{technology}.signoff has no layout-only extraction (run_layout_pex)")
    return provider.run_layout_pex(run_dir=run_dir, gds_path=gds_path, layout_top=layout_top, output_stem=output_stem)


def run_signoff(params: SignoffParams, run_dir: Path) -> SignoffResult:
    """Run DRC, LVS, and PEX and enforce the declared LVS expectation."""

    run_dir.mkdir(parents=True, exist_ok=True)
    drc_report = run_drc(params, run_dir)
    lvs_correct, lvs_report = run_lvs(params, run_dir)
    report_text = lvs_report.read_text(encoding="utf-8", errors="replace")
    expected_correct = params.lvs_expectation == "correct"
    if lvs_correct != expected_correct:
        raise RuntimeError(f"LVS was expected to be {params.lvs_expectation}; see {lvs_report}")
    missing = [fragment for fragment in params.lvs_required_report_fragments if fragment not in report_text]
    if missing:
        raise RuntimeError(f"expected LVS mismatch signature is missing {missing}; see {lvs_report}")
    warnings = () if lvs_correct else ("expected LVS mismatch: disconnected historical MOM layer",)
    pex_netlist = run_pex(params, run_dir)
    result = SignoffResult(
        drc_report=drc_report,
        lvs_report=lvs_report,
        lvs_correct=lvs_correct,
        pex_netlist=pex_netlist,
        warnings=warnings,
    )
    (run_dir / "signoff_summary.json").write_text(
        json.dumps(
            {
                "technology": params.technology,
                "layout_top": params.layout_top,
                "source_top": params.source_top,
                "drc_report": str(drc_report),
                "lvs_report": str(lvs_report),
                "lvs_correct": lvs_correct,
                "pex_netlist": str(pex_netlist),
                "pex_sha256": hashlib.sha256(pex_netlist.read_bytes()).hexdigest(),
                "pdk_options": asdict(params.pdk_options) if is_dataclass(params.pdk_options) else None,
                "lvs_source_sha256": hashlib.sha256(params.lvs_source_path.read_bytes()).hexdigest(),
                "gds_sha256": hashlib.sha256(params.gds_path.read_bytes()).hexdigest(),
                "warnings": list(warnings),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


@dataclass(frozen=True)
class RowSignoff:
    """DRC and LVS of a row layout: the rule counts (``drc_violations.json``) and the LVS report;
    ``lvs_correct`` None where the PDK has no LVS deck for the checkers asked for."""

    drc_report: Path
    drc_violations: int
    lvs_report: Path | None
    lvs_correct: bool | None
    drc_seconds: float = 0.0
    lvs_seconds: float = 0.0  # its source's preparation with it
    drc_checker: str = ""
    lvs_checker: str = ""


ROOT = Path(__file__).resolve().parents[2]
# gdscheck's built-in decks of the open PDKs, by frida's PDK name (``gdscheck list-suites -p <process>``)
GDSCHECK_PROCESSES = {"ihp130": "ihp-sg13g2"}
MAX_BOXES = 200  # markers kept per rule


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


class Checker(Enum):
    """Who checks a layout: the open tools (the default: gdscheck's DRC, the kit's KLayout LVS), or
    the kit's Calibre signoff (``pdk.<pdk>.signoff``), where the kit has it."""

    OPEN = auto()
    CALIBRE = auto()


def open_drc(pdk: str, gds: Path, top: str, run_dir: Path) -> tuple[dict[str, int], str]:
    """gdscheck on ``gds``: its own full deck of an open PDK, else the repo's precheck
    (``flow.layout.compile._gdscheck_runs``), its output streamed to the log; the violations by
    rule, and which deck ran."""
    from flow.layout.logs import run_logged

    runs = _gdscheck_runs(pdk)
    if not runs:
        raise RuntimeError(f"no gdscheck deck for {pdk} (or gdscheck is not installed)")
    violations: dict[str, int] = {}
    for process, suite in runs:
        report = run_dir / f"gdscheck.{suite}.lyrdb"
        command = ["gdscheck", "run", "-i", str(gds), "-p", process, "-t", top, "-s", suite, "-r", str(report)]
        run_logged(
            command, cwd=run_dir, log=run_dir / f"gdscheck.{suite}.log", name="gdscheck", allowed=tuple(range(256))
        )
        if not report.exists():
            raise RuntimeError(f"gdscheck ({suite}) wrote no report; see {run_dir / f'gdscheck.{suite}.log'}")
        for rule, entry in _markers(report, top).items():
            violations[rule] = violations.get(rule, 0) + entry["count"]
    deck = f"gdscheck {GDSCHECK_PROCESSES[pdk]}" if pdk in GDSCHECK_PROCESSES else "gdscheck precheck"
    return violations, deck


def open_lvs(
    pdk: str, gds: Path, top: str, source: Path, source_top: str, run_dir: Path
) -> tuple[bool | None, Path | None, str]:
    """The kit's KLayout LVS of ``gds`` against ``source``: its full deck (``pdk.<pdk>.klayout.lvs``)
    or its approximate one (``klayout_lvs``); the verdict (None: the kit has neither), the LVS
    database and which deck ran. Its first mismatches are logged."""
    log = logging.getLogger("klayout.lvs")
    if find_spec(f"pdk.{pdk}.klayout.lvs"):
        correct, _found = import_module(f"pdk.{pdk}.klayout.lvs").lvs(gds, top, source, source_top, run_dir)
        reports, deck = sorted(run_dir.rglob("*.lvsdb")), "KLayout"
    elif find_spec(f"pdk.{pdk}.klayout.klayout_lvs"):
        correct = import_module(f"pdk.{pdk}.klayout.klayout_lvs").lvs(str(gds), top, str(source), source_top)
        reports, deck = [Path(f"{gds}.lvsdb")], "KLayout (approximate deck)"
    else:
        log.warning(f"{pdk} has no KLayout LVS deck: LVS not run")
        return None, None, ""
    report = next((r for r in reports if r.exists()), None)
    log.info(f"{deck}: {'netlists match' if correct else 'netlists do not match'}" + (f"; {report}" if report else ""))
    if not correct and report is not None:
        try:
            lines = _lvs_findings(report)
        except Exception as error:  # noqa: BLE001 - the verdict stands
            lines = [f"(the LVS database did not read: {error})"]
        for line in lines[:20]:
            log.warning(line)
        if len(lines) > 20:
            log.warning(f"... {len(lines) - 20} more mismatches in {report}")
    return bool(correct), report, deck


def add_post_devices(pdk: str, source: Path, extra: Path, top: str) -> None:
    """Merge what a post step added to a layout (``<gds>.extra.sp``, written by align/post.py:
    devices, ``*.PORTS``, ``*.DNW``) into the LVS ``source`` in place: the devices go into the
    subcircuit ``top``, the ports onto its .subckt line, and with ``*.DNW`` (a deep N-well under
    the block) every NMOS model becomes the variant the PDK's LVS deck extracts over a deep N-well
    (``tech.DNW_MODELS``)."""

    text = extra.read_text().splitlines()
    add = [line for line in text if line.strip() and not line.startswith("*")]
    ports = [port for line in text if line.upper().startswith("*.PORTS") for port in line.split()[1:]]
    dnw = any(line.upper().startswith("*.DNW") for line in text)
    out, inside = [], False
    for line in source.read_text().splitlines():
        f = line.split()
        if f and f[0].lower() == ".subckt" and f[1].lower() == top.lower():
            inside = True
            line = " ".join([line, *ports])
        elif inside and f and f[0].lower() == ".ends":
            out += add
            inside = False
        out.append(line)
    if dnw:
        models = {k.lower(): v for k, v in pdk_value(pdk, "tech", "DNW_MODELS", {}).items()}
        out = [
            " ".join(
                models.get(t.lower(), t) if i > 0 and line.split()[0][0] in "Mm" else t
                for i, t in enumerate(line.split())
            )
            if line.split()
            else line
            for line in out
        ]
    source.write_text("\n".join(out) + "\n")


def _block_options(pdk: str, source: Path) -> Any:
    """A PDK's options for a standalone block: for its LVS source where the PDK reads one (a
    recognized device in it, say), else its fixed ``BLOCK_OPTIONS``."""
    provider = _provider(pdk)
    if callable(getattr(provider, "block_options", None)):
        return provider.block_options(source)
    return getattr(provider, "BLOCK_OPTIONS", None)


def signoff(
    pdk: str,
    gds: Path,
    lvs_source: Path,
    run_dir: Path,
    checker: Checker = Checker.OPEN,
    *,
    name: str | None = None,
    started: float | None = None,
) -> RowSignoff:
    """DRC and LVS (no PEX) of a layout against its LVS source (``lvs_source``: the netlist in the
    LVS context, ``flow.circuit.netlists.lvs_source``, its library text ahead), both run whatever
    the other finds: by the open tools (``Checker.OPEN``, the default: ``open_drc``, ``open_lvs``)
    or the kit's Calibre signoff. The source checked is ``run_dir/source.cdl``: it with the devices
    a post step added (``<gds>.extra.sp``). Source top: its last subcircuit; layout top: the GDS's
    largest top cell. Writes ``row_signoff.json``; raises only when a checker fails to run."""
    started = time.monotonic() if started is None else started
    name = name or Path(gds).stem
    run_dir.mkdir(parents=True, exist_ok=True)
    source = run_dir / "source.cdl"
    if Path(lvs_source).resolve() != source.resolve():
        source.write_text(Path(lvs_source).read_text())
    used = source.read_text()
    source_top = [f[1] for f in map(str.split, used.splitlines()) if f and f[0].lower() == ".subckt"][-1]
    extra = Path(f"{gds}.extra.sp")
    if extra.exists():
        add_post_devices(pdk, source, extra, source_top)
    layout = db.Layout()
    layout.read(str(gds))
    layout_top = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).name
    log = logging.getLogger("flow.layout.signoff")
    log.info(f"{checker.name.lower()} signoff; LVS source {source} (top {source_top}); layout {gds} (top {layout_top})")
    drc_report = run_dir / "drc_violations.json"
    prepared = time.monotonic()
    if checker is Checker.OPEN:
        violations, drc_checker = open_drc(pdk, gds, layout_top, run_dir)
        drc_report.write_text(
            json.dumps({"checker": drc_checker, "violations": violations, "waived": {}}, indent=1) + "\n"
        )
        checked = time.monotonic()
        log.info(f"DRC: {sum(violations.values())} violations ({drc_checker})")
        lvs_correct, lvs_report, lvs_checker = open_lvs(pdk, gds, layout_top, source, source_top, run_dir)
    else:
        params = SignoffParams(
            technology=pdk,
            gds_path=gds,
            layout_top=layout_top,
            lvs_source_path=source,
            source_top=source_top,
            output_stem=name,
            pdk_options=_block_options(pdk, source),
        )
        try:
            run_drc(params, run_dir)
        except RuntimeError:
            if not drc_report.exists():  # the checker did not run to the end
                raise
        checked = time.monotonic()
        drc_checker = json.loads(drc_report.read_text()).get("checker", "calibre")
        log.info(f"DRC: {sum(json.loads(drc_report.read_text())['violations'].values())} violations ({drc_checker})")
        lvs_correct, lvs_report = run_lvs(params, run_dir)
        lvs_checker = "calibre"
    log.info(
        f"LVS: {'not run' if lvs_correct is None else 'correct' if lvs_correct else 'not correct'} ({lvs_checker or '-'})"
    )
    result = RowSignoff(
        drc_report,
        sum(json.loads(drc_report.read_text())["violations"].values()),
        lvs_report,
        lvs_correct,
        drc_seconds=round(checked - prepared, 1),
        lvs_seconds=round(time.monotonic() - checked + prepared - started, 1),
        drc_checker=drc_checker,
        lvs_checker=lvs_checker,
    )
    (run_dir / "row_signoff.json").write_text(
        json.dumps(
            {"gds": str(gds), "layout_top": layout_top, "source_top": source_top, **asdict(result)},
            indent=2,
            default=str,
        )
        + "\n"
    )
    return result
