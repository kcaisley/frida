"""Characterize a PDK's MOM capacitors by KLayout-PEX (FasterCap) and write the momcap table
(``pdk/<pdk>/devices/momcap.json``).

Each style the blocks use (``DIFFERENCE`` strips, ``RING`` units) on one to three of the PDK's MOM
metals is drawn by ALIGN's ``MomUnit`` at a few finger lengths as a layout's array draws it
(``structure``: a strip with its channels, a ring unit in a column array, an inner unit with its
stage's units on every side), its shield and its bottom plates' bars on the metal below as there;
where the array cannot draw a metal count in a PDK (``MomUnit`` refuses it), alone, its shield the
ring again on the metal below. Each structure is DRC-checked as the flow's DRC step checks a layout
(``flow.layout.signoff.drc``) and extracted by its labelled terminals. A finger's capacitance is
linear in its length (its ends a constant), so every terminal pair is fitted as
C = a L_main + b L_diff + c (a ring unit: C = a L + c) over short structures, which extract in
minutes where a long one takes an hour, and the fit reaches any length. The lengths a unit can be
drawn at start at ``min_length_nm`` (the shortest finger that holds its vias, from the PDK's rules)
on the grid ``grid_nm``. A structure FasterCap does not converge on (its log says so or outgrows
``LOG_LIMIT``), or that runs past ``--timeout`` minutes, is stopped and left out of its fit (the
table's ``skipped``); where too few converge to fit, shorter ones are extracted instead
(``_STRIP_FALLBACK_UM``, ``_RING_FALLBACK_UM``).

    python -m flow.layout.devices.momcap.characterize tsmc65 [tsmc28 ...] [--workers N] [--timeout MIN]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import signal
import tempfile
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from klayout import db

from flow.layout import kpex
from flow.layout.package import pdk_dir as align_pdk_dir
from flow.layout.pdkproc import access_points, in_pdk, pdk_value
from flow.layout.run import Drawing, draw, drawn_only

from ..device import ROOT, write_table
from .geometry import PINS, TERMINALS, ArrayKind, MomcapGeometry, MomStyle, Neighbour

# the finger lengths extracted (um): a difference strip's main and difference fingers apart, so the
# two-length fit is determined; a ring unit's inner finger. The fallbacks: shorter, where FasterCap
# does not converge on enough of those
_STRIP_UM = ((2, 1.5), (4, 3), (6, 4.5), (4, 1.5))
_RING_UM = (2, 4, 6)
_STRIP_FALLBACK_UM = ((1.5, 1), (2.5, 2), (3.5, 2.5), (2.5, 1))
_RING_FALLBACK_UM = (1.5, 2.5, 3.5)
_LAYERS = (1, 2, 3)
_STYLES = (MomStyle.DIFFERENCE, MomStyle.RING)
# how each style's units meet in the arrays that place them (capdac: strips in a row with their
# channels, ring units in columns), so a structure is drawn with the array's shield
_ARRAY = {MomStyle.DIFFERENCE: ArrayKind.CHANNELS, MomStyle.RING: ArrayKind.COLUMNS}
# a converging extraction logs some 100 kB; a diverging one gigabytes (GMRES' iterations)
LOG_LIMIT = 100_000_000


def structure(style: MomStyle, layers: int, length_nm: int, diff_length_nm: int = 0) -> MomcapGeometry:
    """The unit a structure extracts: ``style``'s in the array that places it (``_ARRAY``), an inner
    unit there, its stage's units on every side (``JOINED``: its bars and strips run to its outline,
    as most of capdac's pieces have them; a lone unit at the array's edge has no bar long enough for
    the metal's area)."""
    joined = Neighbour.JOINED
    return MomcapGeometry(style, layers, length_nm, diff_length_nm, joined, joined, joined, joined, array=_ARRAY[style])


@dataclass(frozen=True)
class MomRules:
    """The dimensions (nm) the PDK's rules give a unit on some metals: the grid, the metals and the
    shield's, the fingers' width and space, the line-end gap, the via, and the shortest finger that
    holds its via (``min_length``)."""

    grid: int
    metals: tuple[int, ...]
    shield: int
    width: int
    min_space: int
    space: int
    end_gap: int
    via_cut: int
    via_end: int
    min_length: int


def mom_rules(pdk: str, layers: int) -> MomRules:
    """The dimensions of a unit on ``layers`` of ``pdk``'s MOM metals, at the minimum spacing."""
    return MomRules(**in_pdk(pdk, "capcell", "mom_geometry", layers, 0))


def draw_unit(pdk: str, geometry: MomcapGeometry, top_cell: str, *, alone: bool = False) -> db.Layout:
    """Draw a unit with ALIGN's ``MomUnit`` as a layout's netlist element has ALIGN draw it
    (``MomUnit.generate`` on ``geometry.align_parameters()``): its plates on every metal, joined by
    vias, over the shield its array gives it (``geometry.array``, its sides), every terminal
    labelled; ``alone``, as a unit no array places (its shield the ring again on the metal below).
    ALIGN's abstract layers and pin purpose left out, as its layouts' post step leaves them out
    (``flow/layout/post.py``)."""

    hold = mom_rules(pdk, geometry.layers).min_length
    fingers = (
        (geometry.length_nm, geometry.diff_length_nm)
        if geometry.style is MomStyle.DIFFERENCE
        else (geometry.length_nm,)
    )
    if min(fingers) < hold:
        raise ValueError(f"plates shorter than {hold} nm cannot hold their vias")
    parameters = {**geometry.align_parameters(), **({"abut": 0} if alone else {})}
    arguments = {"ports": list(PINS[geometry.style]), "netlist_parameters": parameters}
    access_points(pdk)  # the ALIGN PDK's standard cells read them at import
    with tempfile.TemporaryDirectory() as scratch:
        drawing = Drawing("MomUnit", "generate", arguments, Path(scratch) / f"{top_cell}.gds", top_cell)
        (gds,) = draw(align_pdk_dir(pdk), [drawing])
        layout = db.Layout()
        layout.read(str(gds))
    drawn_only(layout, set(pdk_value(pdk, "tech", "LAYERS").values()))
    return layout


_CAPACITOR = re.compile(r"^\s*\S+\s+\(\s*(\S+)\s+(\S+)\s*\)\s+capacitor\s+c=([-+0-9.eE]+)([a-zA-Z]?)", re.MULTILINE)
_SCALE = {"": 1.0, "f": 1e-15, "a": 1e-18, "p": 1e-12, "n": 1e-9}


def pair_capacitances(netlist: str, terminals: tuple[str, ...]) -> dict[tuple[str, str], float]:
    """Sum an extracted netlist's capacitors between labelled terminals (and ``GROUND``: node 0 or
    the substrate), pair by pair; a terminal's split nodes (``N_TOP_1``, ``TOP:2``) count as it."""

    names = (*terminals, "SHIELD")
    node = re.compile(r"^(?:N_)?(" + "|".join(names) + r")(?:[:#_].*)?$", re.IGNORECASE)
    totals: dict[tuple[str, str], float] = {}
    for first, second, value, unit in _CAPACITOR.findall(netlist):
        ends = []
        for name in (first, second):
            match = node.match(name)
            ends.append(match.group(1).upper() if match else "GROUND")
        if ends[0] == ends[1]:
            continue
        low, high = sorted(ends)
        totals[(low, high)] = totals.get((low, high), 0.0) + float(value) * _SCALE[unit.lower()]
    return totals


def check(run_dir: Path, pdk: str, geometry: MomcapGeometry) -> tuple[Path, str | None, dict[str, Any]]:
    """Draw a unit into ``run_dir`` as its array draws it, or alone where the array cannot
    (``MomUnit`` refuses it: no channel metal on the routing tracks, a finger too narrow for its
    access), and DRC it as the flow's DRC step does (``signoff.drc``, the open checker): its GDS,
    why the array could not draw it (None: drawn as the array does), and the check's report."""
    from flow.layout.signoff import drc

    run_dir.mkdir(parents=True, exist_ok=True)
    gds, refused = run_dir / "momunit.gds", None
    try:
        layout = draw_unit(pdk, geometry, "momunit")
    except RuntimeError as error:
        lines = [line for line in str(error).splitlines() if "ValueError:" in line]
        if not lines:
            raise
        refused = lines[-1].split("ValueError:", 1)[1].strip()
        layout = draw_unit(pdk, geometry, "momunit", alone=True)
    layout.write(str(gds))
    report = Path(drc(pdk, gds, run_dir / "drc")["report"])
    return gds, refused, json.loads(report.read_text())


class Diverged(RuntimeError):
    """FasterCap did not converge on a structure: its log says so, or outgrew ``LOG_LIMIT``."""


def _watch(log: Path, stop: threading.Event, tripped: threading.Event) -> None:
    """Stop the extraction this process started, once its log passes ``LOG_LIMIT``: its children's
    process groups (``run_logged`` starts each tool in a session of its own)."""
    while not stop.wait(10):
        if log.is_file() and log.stat().st_size > LOG_LIMIT:
            tripped.set()
            for task in Path(f"/proc/{os.getpid()}/task").iterdir():
                for child in (task / "children").read_text().split():
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.killpg(int(child), signal.SIGKILL)
            return


def extract(
    run_dir: Path, pdk: str, geometry: MomcapGeometry, timeout_s: float | None = None
) -> tuple[dict[tuple[str, str], float], str | None, dict[str, Any]]:
    """Draw a unit into ``run_dir`` and DRC it (``check``), and extract it by KLayout-PEX
    (FasterCap; stopped after ``timeout_s``, or where it diverges, ``Diverged``): every terminal
    pair's capacitance, why its array could not draw it, and the DRC's report."""
    gds, refused, drc = check(run_dir, pdk, geometry)
    log = run_dir / "kpex" / "kpex.log"
    log.unlink(missing_ok=True)  # an earlier run's
    stop, tripped = threading.Event(), threading.Event()
    threading.Thread(target=_watch, args=(log, stop, tripped), daemon=True).start()
    try:
        netlist = kpex.run_layout_pex(pdk, gds, "momunit", "momunit", run_dir, timeout=timeout_s)
    except RuntimeError as error:
        if tripped.is_set():
            raise Diverged(f"FasterCap diverged: its log passed {LOG_LIMIT // 1_000_000} MB") from error
        raise
    finally:
        stop.set()
    with log.open(errors="replace") as lines:
        if any("not converging" in line for line in lines):
            raise Diverged("FasterCap diverged: not converging")
    return pair_capacitances(netlist.read_text(), TERMINALS[geometry.style]), refused, drc


def _snap(um: float, grid: int, least: int) -> int:
    return max(least, math.ceil(um * 1000 / grid) * grid)


def _geometries(pdk: str, style: MomStyle, layers: int, fallback: bool = False) -> list[MomcapGeometry]:
    """``style``'s structures on ``layers`` metals: at the lengths each fit extracts, or
    (``fallback``) the shorter ones extracted where too few of those converge."""
    hold = mom_rules(pdk, layers)
    if style is MomStyle.DIFFERENCE:
        lengths = _STRIP_FALLBACK_UM if fallback else _STRIP_UM
    else:
        lengths = tuple((um, 0) for um in (_RING_FALLBACK_UM if fallback else _RING_UM))
    snap = lambda um: _snap(um, hold.grid, hold.min_length) if um else 0
    return [structure(style, layers, snap(main), snap(diff)) for main, diff in lengths]


def _name(geometry: MomcapGeometry) -> str:
    return f"{geometry.style.name.lower()}_{geometry.layers}_{geometry.length_nm}_{geometry.diff_length_nm}"


def _run_dir(pdk: str, geometry: MomcapGeometry) -> Path:
    return ROOT / "build" / "devices" / "momcap" / pdk / _name(geometry)


def _extract_one(pdk: str, geometry: MomcapGeometry, timeout_s: float | None) -> dict[str, Any]:
    """One structure's terminal pairs (F), why its array could not draw it, its DRC and its time;
    where the extraction is stopped (``timeout_s``), diverges or fails, why, and no pairs."""
    started = time.monotonic()
    try:
        pairs, refused, drc = extract(_run_dir(pdk, geometry), pdk, geometry, timeout_s)
    except RuntimeError as error:
        report = _run_dir(pdk, geometry) / "drc" / "drc_violations.json"
        drc = json.loads(report.read_text()) if report.is_file() else {}
        return {"pairs": None, "drc": drc, "error": str(error).splitlines()[0], "s": time.monotonic() - started}
    return {
        "pairs": {"-".join(pair): value for pair, value in pairs.items()},
        "refused": refused,
        "drc": drc,
        "s": time.monotonic() - started,
    }


def _fit(points: list[tuple[MomcapGeometry, dict[str, float]]], strip: bool) -> dict[str, dict[str, float]]:
    """Each terminal pair's fit (fF and fF/um) over the extracted ``points``."""
    rows = [
        [g.length_nm / 1000, g.diff_length_nm / 1000, 1.0] if strip else [g.length_nm / 1000, 1.0] for g, _ in points
    ]
    fits = {}
    for pair in sorted({pair for _, values in points for pair in values}):
        c_ff = np.array([values.get(pair, 0.0) * 1e15 for _, values in points])
        coef, *_ = np.linalg.lstsq(np.array(rows), c_ff, rcond=None)
        worst = float(np.max(np.abs(np.array(rows) @ coef - c_ff)))
        if strip:
            fits[pair] = {"main_ff_per_um": coef[0], "diff_ff_per_um": coef[1], "ff": coef[2], "worst_ff": worst}
        else:
            fits[pair] = {"ff_per_um": coef[0], "ff": coef[1], "worst_ff": worst}
    return {pair: {key: float(value) for key, value in fit.items()} for pair, fit in fits.items()}


def _determined(style: MomStyle, results: list[tuple[MomcapGeometry, dict[str, Any]]]) -> bool:
    """Whether the structures extracted of ``results`` determine their fit: a strip's three
    coefficients, a ring unit's two."""
    rows = [
        (g.length_nm, g.diff_length_nm, 1) if style is MomStyle.DIFFERENCE else (g.length_nm, 1)
        for g, r in results
        if r["pairs"] is not None
    ]
    return bool(rows) and int(np.linalg.matrix_rank(np.array(rows, dtype=float))) == len(rows[0])


METHOD = (
    "KLayout-PEX (FasterCap), finger length fits; each unit drawn as its array draws it (MomUnit.generate: "
    "a strip with its channels, a ring unit in a column array, joined on every side), alone where the "
    "array cannot draw it (drawn: alone, its shield the ring on the metal below)"
)


def _entry(pdk: str, style: MomStyle, layers: int, mine: list[tuple[MomcapGeometry, dict[str, Any]]]) -> dict:
    """One style and metal count's table entry: the fit over its structures extracted, how they
    were drawn (``drawn``: ``array``, or ``alone`` and why the array could not), and those stopped
    or failed (``skipped``)."""
    points = [(g, r["pairs"]) for g, r in mine if r["pairs"] is not None]
    refused = {r["refused"] for _, r in mine if r["pairs"] is not None}
    if len(refused) != 1:
        raise RuntimeError(f"{pdk}: {style.name} on {layers} metals drawn both as its array draws it and alone")
    (why,) = refused
    hold = mom_rules(pdk, layers)
    entry: dict[str, Any] = {
        "grid_nm": hold.grid,
        "min_length_nm": hold.min_length,
        "end_gap_nm": hold.end_gap,
        "drawn": "array" if why is None else f"alone: {why}",
        "lengths_nm": [[g.length_nm, g.diff_length_nm] for g, _ in points],
        "pairs": _fit(points, strip=style is MomStyle.DIFFERENCE),
    }
    skipped = [[g.length_nm, g.diff_length_nm, r["error"]] for g, r in mine if r["pairs"] is None]
    if skipped:
        entry["skipped"] = skipped
    return entry


def _table(pdk: str, done: dict[tuple[MomStyle, int], list[tuple[MomcapGeometry, dict[str, Any]]]]) -> Path:
    """Write ``pdk``'s momcap table from its structures' results, every structure's DRC in its
    provenance."""
    styles: dict[str, dict[str, dict[str, Any]]] = {}
    for style in _STYLES:
        for layers in _LAYERS:
            mine = sorted(done[(style, layers)], key=lambda item: (item[0].length_nm, item[0].diff_length_nm))
            styles.setdefault(style.name, {})[str(layers)] = _entry(pdk, style, layers, mine)
    every = [item for items in done.values() for item in items]
    violations = {}
    for g, r in every:
        for rule, count in r["drc"].get("violations", {}).items():
            violations[f"{_name(g)}: {rule}"] = count
    deck = next((r["drc"]["checker"] for _, r in every if r["drc"].get("checker")), "gdscheck")
    path = write_table("momcap", pdk, {"styles": styles}, method=METHOD)
    table = json.loads(path.read_text())
    table["provenance"]["drc"] = {"checker": deck, "structures": len(every), "violations": violations}
    path.write_text(json.dumps(table, indent=1) + "\n")
    return path


def characterize(pdks: list[str], workers: int = 8, timeout_s: float | None = None) -> list[Path]:
    """Extract every structure of ``pdks`` in one pool of ``workers`` (the longest first: three
    metals, the strips), a style and metal count's fallback structures where too few of its own
    converge, and write each PDK's momcap table once its structures are done."""
    entries = [(pdk, style, layers) for layers in reversed(_LAYERS) for style in _STYLES for pdk in pdks]
    done: dict[str, dict[tuple[MomStyle, int], list]] = {pdk: {} for pdk in pdks}
    pending = dict.fromkeys(entries, 0)
    fallen_back: set[tuple[str, MomStyle, int]] = set()
    written = []
    with ProcessPoolExecutor(workers) as pool:
        futures: dict[Any, tuple[tuple[str, MomStyle, int], MomcapGeometry]] = {}

        def submit(entry: tuple[str, MomStyle, int], fallback: bool) -> None:
            for g in _geometries(*entry, fallback):
                futures[pool.submit(_extract_one, entry[0], g, timeout_s)] = (entry, g)
                pending[entry] += 1

        for entry in entries:
            submit(entry, False)
        while futures:
            finished, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in finished:
                entry, g = futures.pop(future)
                pdk, style, layers = entry
                result = future.result()
                done[pdk].setdefault((style, layers), []).append((g, result))
                pending[entry] -= 1
                drc = sum(result["drc"].get("violations", {}).values())
                state = result.get("error") or ("extracted" + (" alone" if result.get("refused") else ""))
                print(f"{pdk} {_name(g)}: {state}, {drc} DRC violations, {result['s'] / 60:.1f} min", flush=True)
                if pending[entry]:
                    continue
                if not _determined(style, done[pdk][(style, layers)]):
                    if entry in fallen_back:
                        raise RuntimeError(f"{pdk}: too few {style.name} structures on {layers} metals converge")
                    fallen_back.add(entry)
                    print(f"{pdk} {style.name} on {layers} metals: too few converged, its fallback lengths", flush=True)
                    submit(entry, True)
                    continue
                if not any(pending[e] for e in entries if e[0] == pdk):
                    written.append(_table(pdk, done[pdk]))
                    print(written[-1], flush=True)
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdks", nargs="+")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=0, help="minutes a structure may extract (0: no limit)")
    args = parser.parse_args()
    characterize(args.pdks, args.workers, args.timeout * 60 or None)
