"""A kit's coefficients for KLayout-PEX's 2.5-D engine (kpex's ``process_parasitics``,
``pdk/<pdk>/kpex/parasitics.json``), fitted to direct 2-D field solves of test cross-sections in
the kit's own planar stack, the one FasterCap extracts in (``flow.layout.kpex.technology``:
``stack.json``, each metal's level and the dielectric above it), then the MOM metals' sidewall
and line ends fitted to FasterCap's 3-D solves of the capacitive DAC's strips (``calibrate``).

The solver is capiche's ``solve2d`` (``CAPICHE``: its ``src`` folder): a fixed mesh graded toward
every corner, solved directly, so a cross-section takes about a second and no convergence test can
stop it early (FasterCap's 3-D solves of the same structures took hours). The forms are kpex's:

- substrate: each conductor's area capacitance analytic (the slabs from the substrate to it in
  series); its perimeter capacitance the mean over two widths of a wire's (c - area W) / 2;
- sidewall: two minimum-width wires at one to five minimum spaces, c = K / (s + o) fitted as 1/c
  linear in s, kpex's capacitance 2 K (it counts each wire's edge apart) and its offset o;
- overlap: analytic (the slabs between the two conductors in series); side overlap the mean over two
  widths of (c - overlap W) / 2 of a wire on one conductor over (or under) a plate on another.

The structures take the kit's minimum width and space of each metal (its layout tech's ``RULES``);
poly takes the first metal's.

A lone pair of wires is not a MOM strip: its plates stack on two or three metals at their minimum
space, their own net above and below each finger, and the pair's sidewall counts the fringe over
and under each finger that the stack's neighbours take. ``calibrate`` draws the strips as the
kit's arrays draw them (``flow.layout.devices.momcap``: a difference unit on each metal count its
arrays draw, its channels, at ``CALIBRATION_UM``), extracts each by FasterCap and by the 2.5-D
engine with its capacitances by coefficient (``flow.layout.kpex_extract.parts``), and fits two
things per MOM metal to FasterCap: the sidewall's scale to the slope of a plate's coupling to the
top plate over its finger's length, which leaves the finger's ends out; then the length a line
end's fringe reaches past the tip (``flow.layout.kpex_extract.line_ends``: kpex's sidewall ends
with the edge, where FasterCap's field wraps round a finger's tip) to the strips' plates, main
finger and difference stub, their errors relative least squares (a strip's weight, main less
difference finger, is the same whatever the length: both have a tip at the ring and one at their
gap). The table's provenance
holds each strip's couplings by both engines, the scales and lengths, and each metal count's
lines before and after them.

    uv run python -m flow.layout.kpex_coefficients <pdk> [--out FILE] [--work DIR] [--workers N] [--timeout MIN]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from importlib import import_module
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from flow.layout.devices.momcap.characterize import extract
from flow.layout.devices.momcap.geometry import ArrayKind, MomcapGeometry, MomStyle, Neighbour
from flow.layout.devices.momcap.table import momcap_table
from flow.layout.kpex import ROOT, TOLERANCE, Engine, run_layout_pex, technology

CAPICHE = Path(os.environ.get("CAPICHE", "~/Documents/libs/capiche/src")).expanduser()
# the vacuum permittivity, aF/um
EPS0 = 8.8541878
# the spaces (in minimum spaces) the sidewall is fitted on, the widths (in minimum widths) of the
# substrate's and the side overlap's wires, and the plate's half width (um) a wire crosses
SPACES = (1.0, 1.4, 2.0, 3.0, 5.0)
SUBSTRATE_WIDTHS = (2, 10)
OVERLAP_WIDTHS = (2, 20)
PLATE_UM = 20.0
# a dielectric's slabs past the top metal (um) and the solver's span of the interfaces (um)
TOP_SPAN_UM = 5.0
SPAN_UM = 60.0
# the calibration's main finger lengths (um), up to about the arrays' longest pieces, and its first
# guess of a line end's reach (um), which it fits
CALIBRATION_UM = (4.0, 12.0, 24.0)
LINE_END_GUESS_UM = 0.25


def slabs(pdk: str) -> tuple[list[tuple[float, float, float]], dict[str, tuple[float, float]]]:
    """The kit's planar stack as frida's kpex technology has it: its slabs (bottom, top,
    permittivity: the field oxide, each metal's level, the dielectric above it) and each
    conductor's bottom and thickness (um)."""
    layers = technology(pdk)[0]["process_stack"]["layers"]
    fox = next(entry["field_oxide_layer"]["dielectric_k"] for entry in layers if entry["name"] == "fox")
    metals = [
        (entry["name"], entry["metal_layer"]["z"], entry["metal_layer"]["thickness"])
        for entry in layers
        if entry["layer_type"] == "LAYER_TYPE_METAL"
    ]
    level = {
        e["name"][6:]: e["conformal_dielectric_layer"]["dielectric_k"] for e in layers if e["name"].startswith("level_")
    }
    above = {
        e["name"][5:]: e["simple_dielectric_layer"]["dielectric_k"] for e in layers if e["name"].startswith("diel_")
    }
    found = [(0.0, metals[0][1], fox)]
    for index, (name, z, t) in enumerate(metals):
        top = metals[index + 1][1] if index + 1 < len(metals) else z + t + TOP_SPAN_UM
        found += [(z, z + t, level[name]), (z + t, top, above[name])]
    return found, {name: (z, t) for name, z, t in metals}


def area_f(stack: list[tuple[float, float, float]], bottom: float, top: float) -> float:
    """The area capacitance (aF/um^2) between two heights: the slabs between them in series."""
    # not in the reference texts: a parallel plate's capacitance per area, the permittivity over
    # the spacing, each slab's in series
    return EPS0 / sum((min(b, top) - max(a, bottom)) / k for a, b, k in stack if min(b, top) > max(a, bottom))


def sidewall_fit(spaces: np.ndarray, coupling: np.ndarray, least_space: float) -> tuple[float, float]:
    """``K`` and ``o`` of c = K / (s + o) through two wires' couplings (aF/um) at ``spaces`` (um):
    1/c fitted linear in s; with no offset where the fit puts its pole among the spaces (poly at
    the first metal's space)."""
    # not in the reference texts: kpex's 2.5-D sidewall form, K / (s + o), fitted to the solves
    slope, intercept = np.polyfit(spaces, 1 / coupling, 1)
    k, o = 1 / slope, intercept / slope
    if o <= -0.8 * least_space:
        k, o = float(np.dot(coupling, 1 / spaces) / np.dot(1 / spaces, 1 / spaces)), 0.0
    return float(k), float(o)


def _k_at(stack: list[tuple[float, float, float]], y: float) -> float:
    return next((k for a, b, k in stack if a <= y < b), stack[-1][2])


def _lst(stack: list[tuple[float, float, float]], geometry: dict, rects: list[tuple[str, str, float, float]]) -> str:
    """A 2-D cross-section in FasterCap's list format: each wire (net, conductor, x0, x1) its bottom,
    top and sides at their dielectrics' permittivities, a ground plane at the substrate, and every
    interface between slabs, cut where a wire's face lies on it."""
    lines, files = ["* calibration cross-section"], {}
    nets = list(dict.fromkeys(rect[0] for rect in rects))
    for net in nets:
        items = []
        for index, (_net, metal, x0, x1) in enumerate(rect for rect in rects if rect[0] == net):
            z, t = geometry[metal]
            base = f"{net}_{metal}_{index}"
            files[f"{base}_b"] = [(net, x0, z, x1, z)]
            files[f"{base}_t"] = [(net, x1, z + t, x0, z + t)]
            files[f"{base}_s"] = [(net, x1, z, x1, z + t), (net, x0, z + t, x0, z)]
            items += [(f"{base}_b", _k_at(stack, z - 1e-4)), (f"{base}_t", _k_at(stack, z + t + 1e-4))]
            items.append((f"{base}_s", _k_at(stack, z + t / 2)))
        lines += [f"C {name} {k} 0 0" + (" +" if i < len(items) - 1 else "") for i, (name, k) in enumerate(items)]
    lines.append("C plane 1.0 0 0")
    files["plane"] = [("ground", -SPAN_UM - 20, 0.0, SPAN_UM + 20, 0.0)]
    for y in sorted({round(edge, 6) for a, b, _k in stack for edge in (a, b)}):
        below, above = _k_at(stack, y - 1e-4), _k_at(stack, y + 1e-4)
        if y <= 0 or abs(below - above) < 1e-9:
            continue
        faces = sorted(
            (x0, x1) for _n, m, x0, x1 in rects if any(abs(e - y) < 1e-9 for e in (geometry[m][0], sum(geometry[m])))
        )
        cuts, x = [], -SPAN_UM
        for x0, x1 in faces:
            if x0 > x:
                cuts.append(("d", x, y, x0, y))
            x = max(x, x1)
        cuts.append(("d", x, y, SPAN_UM, y))
        files[f"interface_{len(files)}"] = cuts
        lines.append(f"D interface_{len(files) - 1} {above} {below} 0 0 {-SPAN_UM + 0.123} {y + 0.05}")
    lines.append("End")
    for name, segments in files.items():
        lines += [f"File {name}", *("S {} {:.6f} {:.6f} {:.6f} {:.6f}".format(*s) for s in segments), "End"]
    return "\n".join(lines) + "\n"


def _solve(job: tuple[str, str, list, Path]) -> tuple[str, dict[str, float]]:
    """One cross-section solved (``work/<name>.json`` kept, reused): each pair's capacitance
    (aF/um), a net's to the ground plane and infinity as ``<net>-GROUND``."""
    pdk, name, rects, work = job
    done = work / f"{name}.json"
    if done.is_file():
        return name, json.loads(done.read_text())
    sys.path.insert(0, str(CAPICHE))
    from capiche.solve2d import solve_lst

    stack, geometry = slabs(pdk)
    lst = work / f"{name}.lst"
    lst.write_text(_lst(stack, geometry, rects))
    matrix = solve_lst(str(lst))[0] * 1e12
    nets = list(dict.fromkeys(rect[0] for rect in rects))
    pairs = {f"{a}-GROUND": float(matrix[i].sum()) for i, a in enumerate(nets)}
    for i, a in enumerate(nets):
        for j in range(i + 1, len(nets)):
            pairs[f"{a}-{nets[j]}"] = float(-0.5 * (matrix[i, j] + matrix[j, i]))
    done.write_text(json.dumps(pairs))
    return name, pairs


def coefficients(pdk: str, work: Path, workers: int = 8) -> dict:
    """The kit's 2.5-D coefficients (kpex's ``process_parasitics``) from its cross-sections, solved
    in ``work``."""
    rules = import_module(f"pdk.{pdk}.layout.tech").RULES
    stack, geometry = slabs(pdk)
    names = list(geometry)

    def rule(name: str, key: str) -> float:
        return (rules.get(name, {}).get(key) or rules["M1"][key]) / 1000

    jobs = []
    for x in names:
        w, s = rule(x, "width"), rule(x, "space")
        jobs += [(f"sub_{x}_{m}", [("a", x, -m * w / 2, m * w / 2)]) for m in SUBSTRATE_WIDTHS]
        jobs += [
            (f"sw_{x}_{m}", [("a", x, -m * s / 2 - w, -m * s / 2), ("b", x, m * s / 2, m * s / 2 + w)]) for m in SPACES
        ]
        for y in (y for y in names if y != x):
            jobs += [
                (f"ov_{x}_{y}_{m}", [("a", x, -m * w / 2, m * w / 2), ("b", y, -PLATE_UM, PLATE_UM)])
                for m in OVERLAP_WIDTHS
            ]
    work.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(workers) as pool:
        solved = dict(pool.map(_solve, [(pdk, name, rects, work) for name, rects in jobs]))
    capacitance: dict[str, list] = {"substrates": [], "overlaps": [], "sidewalls": [], "sideoverlaps": []}
    for x in names:
        w, s = rule(x, "width"), rule(x, "space")
        area = area_f(stack, 0.0, geometry[x][0])
        # not in the reference texts: kpex's perimeter capacitance, a wire's c(W) = area W + 2 perimeter
        perimeter = np.mean([(solved[f"sub_{x}_{m}"]["a-GROUND"] - area * m * w) / 2 for m in SUBSTRATE_WIDTHS])
        capacitance["substrates"].append(
            {"layer_name": x, "area_capacitance": round(area, 4), "perimeter_capacitance": round(float(perimeter), 4)}
        )
        k, o = sidewall_fit(np.array(SPACES) * s, np.array([solved[f"sw_{x}_{m}"]["a-b"] for m in SPACES]), s)
        capacitance["sidewalls"].append({"layer_name": x, "capacitance": round(2 * k, 4), "offset": round(o, 4)})
    for x in names:
        w = rule(x, "width")
        for y in (y for y in names if y != x):
            top, bottom = (x, y) if geometry[x][0] > geometry[y][0] else (y, x)
            overlap = area_f(stack, sum(geometry[bottom]), geometry[top][0])
            if x == top:
                capacitance["overlaps"].append(
                    {"top_layer_name": top, "bottom_layer_name": bottom, "capacitance": round(overlap, 4)}
                )
            # not in the reference texts: kpex's side overlap, a wire's c(W) = overlap W + 2 fringe
            fringe = np.mean([(solved[f"ov_{x}_{y}_{m}"]["a-b"] - overlap * m * w) / 2 for m in OVERLAP_WIDTHS])
            capacitance["sideoverlaps"].append(
                {"in_layer_name": x, "out_layer_name": y, "capacitance": round(max(float(fringe), 0.0), 4)}
            )
    return {"side_halo": 8.0, "capacitance": capacitance, "resistance": {}}


def calibration_strips(pdk: str) -> list[MomcapGeometry]:
    """The strips ``calibrate`` extracts: on each metal count the kit's arrays draw (its momcap
    table's difference units drawn as the array draws them), the main finger at each of
    ``CALIBRATION_UM`` and the difference finger at its shortest, apart from their neighbours on
    both sides (most of the capacitive DAC's pieces); and at the middle length joined on both sides
    and apart on one and the array's edge on the other (its last piece)."""
    table = momcap_table(pdk)
    found = []
    apart, joined, edge = Neighbour.APART, Neighbour.JOINED, Neighbour.EDGE
    for count, entry in table.styles[MomStyle.DIFFERENCE.name].items():
        if entry["drawn"] != "array":
            continue
        least, grid = table.shortest_nm(int(count)), entry["grid_nm"]
        lengths = [max(least, round(um * 1000 / grid) * grid) for um in CALIBRATION_UM]
        sides = [(apart, apart, length) for length in lengths] + [
            (joined, joined, lengths[1]),
            (apart, edge, lengths[1]),
        ]
        found += [
            MomcapGeometry(MomStyle.DIFFERENCE, int(count), length, least, left, right, array=ArrayKind.CHANNELS)
            for left, right, length in sides
        ]
    return found


def _apart(geometry: MomcapGeometry) -> bool:
    """Whether a strip is apart from its neighbours on both sides: one of the lines' strips."""
    return geometry.left is geometry.right is Neighbour.APART


def _strip_name(geometry: MomcapGeometry) -> str:
    return f"strip_{geometry.layers}_{geometry.length_nm}_{geometry.diff_length_nm}_{geometry.sides}"


def _fastercap(job: tuple[str, MomcapGeometry, Path, float | None]) -> tuple[str, dict[str, float] | None]:
    """A strip drawn into ``work/<name>/`` and extracted as the momcap table's structures are
    (``flow.layout.devices.momcap.characterize.extract``: drawn as its array draws it, DRC-checked,
    FasterCap at the units' tolerance, stopped after ``timeout_s`` seconds or where it diverges):
    its terminal pairs' capacitances (fF), kept (``fastercap.json``) and reused; None where
    FasterCap did not finish."""
    pdk, geometry, work, timeout_s = job
    folder = work / _strip_name(geometry)
    done = folder / "fastercap.json"
    if done.is_file():
        return _strip_name(geometry), json.loads(done.read_text())
    try:
        found, _refused, _drc = extract(folder, pdk, geometry, timeout_s)
    except RuntimeError as error:
        print(f"{pdk} {_strip_name(geometry)}: {str(error).splitlines()[0]}", flush=True)
        return _strip_name(geometry), None
    pairs = {"-".join(pair): c * 1e15 for pair, c in found.items()}
    done.write_text(json.dumps(pairs, indent=1) + "\n")
    return _strip_name(geometry), pairs


def _rcx25(pdk: str, geometry: MomcapGeometry, work: Path, table: dict, label: str) -> list[list]:
    """A strip (drawn by ``_fastercap``) extracted by the 2.5-D engine on ``table``: its
    capacitances by coefficient (``flow.layout.kpex_extract.parts``), in ``work/<name>/<label>``."""
    folder = work / _strip_name(geometry)
    parts = folder / label / "parts.json"
    run_layout_pex(
        pdk,
        folder / "momunit.gds",
        "momunit",
        "momunit",
        folder / label,
        engine=Engine.RCX25,
        parts=parts,
        parasitics=table,
    )
    return json.loads(parts.read_text())


def coupling(parts: list[list], pair: tuple[str, str], metals: set[str] | None = None, kind: str = "sidewall") -> float:
    """The 2.5-D capacitance (fF) between two terminals of a structure, from its capacitances by
    coefficient (``flow.layout.kpex_extract.parts``, ``line_ends``): all of it, or (``metals``)
    only the ``kind`` (``sidewall``, ``line_end``) on those conductors."""
    return sum(
        value
        for found, a, _b, net1, net2, value in parts
        if {net1, net2} == set(pair) and (metals is None or (found == kind and a in metals))
    )


def slope(lengths_um: list[float], values: list[float]) -> tuple[float, float]:
    """A plate's coupling over its finger's length: the slope (fF/um) and the ends' constant (fF)
    of the line through ``values`` at ``lengths_um``."""
    # not in the reference texts: a least-squares line
    per_um, ends = np.polyfit(np.asarray(lengths_um), np.asarray(values), 1)
    return float(per_um), float(ends)


def nested_fit(terms: dict[int, list[tuple[float, dict[str, float], float]]]) -> dict[str, float]:
    """Each MOM metal's coefficient that brings the 2.5-D engine to FasterCap, by metal count: its
    values (FasterCap's, each metal's part of the 2.5-D engine's at a coefficient of 1, and the rest
    of it: a line's slope, its sidewalls; a strip's plate, its line ends). The fewest metals
    first, a count's metals not yet fitted one coefficient between them, its values' errors
    relative to FasterCap's least squares (a count takes the top metals of the fewer counts and
    more): a count of one value comes out FasterCap's."""
    fitted: dict[str, float] = {}
    for count in sorted(terms):
        rows = terms[count]
        new = sorted({metal for _fc, parts, _rest in rows for metal, part in parts.items() if part > 0} - set(fitted))
        if not new:
            continue
        # not in the reference texts: x * (the new metals' part) + the rest = FasterCap's, the
        # errors relative to FasterCap's least squares in x
        own = [sum(parts.get(metal, 0.0) for metal in new) for _fc, parts, _rest in rows]
        left = [
            fastercap - rest - sum(fitted[metal] * part for metal, part in parts.items() if metal in fitted)
            for fastercap, parts, rest in rows
        ]
        weight = [1 / fastercap**2 for fastercap, _parts, _rest in rows]
        coefficient = sum(w * y * a for w, y, a in zip(weight, left, own, strict=True)) / sum(
            w * a * a for w, a in zip(weight, own, strict=True)
        )
        fitted.update(dict.fromkeys(new, coefficient))
    return fitted


def scaled(table: dict, scales: dict[str, float]) -> dict:
    """``table`` with each metal's sidewall capacitance times its scale (``scales``)."""
    out = json.loads(json.dumps(table))
    for entry in out["capacitance"]["sidewalls"]:
        if entry["layer_name"] in scales:
            entry["capacitance"] = round(entry["capacitance"] * scales[entry["layer_name"]], 4)
    return out


def calibrate(pdk: str, table: dict, work: Path, workers: int = 8, timeout_s: float | None = None) -> dict:
    """``table`` (the 2-D fit) with the MOM metals' sidewall fitted to FasterCap's coupling per
    length of the kit's strips (``calibration_strips``; each FasterCap run stopped after
    ``timeout_s`` seconds, and a strip it does not finish left out), and its provenance: each
    strip's terminal pairs by FasterCap and by the 2.5-D engine on the result, the scales, and each
    metal count's line (slope and ends) by FasterCap and by the 2.5-D engine before and after them.
    Raises where too few of a metal count's strips finish to draw its line."""
    work.mkdir(parents=True, exist_ok=True)
    every = calibration_strips(pdk)
    # the longest first; each FasterCap run takes KPEX_THREADS cores. Spawned, not forked: the
    # strips' lengths came from the PDK's process (``flow.layout.pdkproc``), whose pool a fork
    # copies mid-call, and a worker's next call there waits on it for good
    jobs = [(pdk, g, work, timeout_s) for g in sorted(every, key=lambda g: -g.length_nm)]
    with ProcessPoolExecutor(workers, mp_context=get_context("spawn")) as pool:
        fastercap = {name: pairs for name, pairs in pool.map(_fastercap, jobs) if pairs is not None}
    strips = [g for g in every if _strip_name(g) in fastercap]
    for count in {g.layers for g in every}:
        if sum(g.layers == count and _apart(g) for g in strips) < 2:
            raise RuntimeError(f"{pdk}: too few strips on {count} metals finished by FasterCap to draw their line")
    mom = import_module(f"pdk.{pdk}.layout.tech").MOM_LAYERS
    metals = {f"M{metal}" for g in strips for metal in mom[-g.layers :]}
    before = {_strip_name(g): _rcx25(pdk, g, work, table, "rcx25_2d") for g in strips}
    counts = sorted({g.layers for g in strips})

    def line(count: int, values: dict[str, float]) -> tuple[float, float]:
        group = [g for g in strips if g.layers == count and _apart(g)]
        return slope([g.length_nm / 1000 for g in group], [values[_strip_name(g)] for g in group])

    def by_pair(found: dict[str, list], pair: str, only: set[str] | None = None, kind: str = "sidewall") -> dict:
        return {name: coupling(parts, tuple(pair.split("-")), only, kind) for name, parts in found.items()}

    main = {name: pairs["MAIN-TOP"] for name, pairs in fastercap.items()}
    slopes = {}
    for count in counts:
        sidewalls = {metal: line(count, by_pair(before, "MAIN-TOP", {metal}))[0] for metal in sorted(metals)}
        rest = line(count, by_pair(before, "MAIN-TOP"))[0] - sum(sidewalls.values())
        slopes[count] = [(line(count, main)[0], sidewalls, rest)]
    scales = nested_fit(slopes)
    out = scaled(table, scales)
    # the line ends: each apart strip's plates (its main finger, its difference stub) by FasterCap
    # against the 2.5-D engine's and its line ends' (linear in their length, but which polygon a
    # side faces past its tip with it: twice, from a guess; none shorter than nothing, where the
    # 2.5-D engine's ends already reach FasterCap's)
    lengths = dict.fromkeys(sorted(metals), LINE_END_GUESS_UM)
    for _ in range(2):
        reach = {metal: max(length, LINE_END_GUESS_UM / 5) for metal, length in lengths.items()}
        probe = {_strip_name(g): _rcx25(pdk, g, work, {**out, "line_ends_um": reach}, "rcx25_ends") for g in strips}
        ends = {}
        for count in counts:
            ends[count] = []
            for g in (g for g in strips if g.layers == count and _apart(g)):
                for pair in ("MAIN-TOP", "DIFF-TOP"):
                    parts, terminals = probe[_strip_name(g)], tuple(pair.split("-"))
                    per_um = {m: coupling(parts, terminals, {m}, "line_end") / reach[m] for m in sorted(metals)}
                    rest = coupling(parts, terminals) - sum(per_um[m] * reach[m] for m in per_um)
                    ends[count].append((fastercap[_strip_name(g)][pair], per_um, rest))
        lengths = {metal: round(max(length, 0.0), 4) for metal, length in nested_fit(ends).items()}
    out["line_ends_um"] = lengths
    after = {_strip_name(g): _rcx25(pdk, g, work, out, "rcx25") for g in strips}
    lines = {
        str(count): {
            pair: {
                "fastercap": line(count, {name: pairs.get(pair, 0.0) for name, pairs in fastercap.items()}),
                "rcx25_2d": line(count, by_pair(before, pair)),
                "rcx25": line(count, by_pair(after, pair)),
            }
            for pair in ("MAIN-TOP", "DIFF-TOP")
        }
        for count in counts
    }
    out["provenance"] = {
        "method": METHOD,
        "code_sha": _code_sha(),
        "date": datetime.now(UTC).date().isoformat(),
        "fastercap_tolerance": TOLERANCE,
        "sidewall_scales": {metal: round(scale, 5) for metal, scale in sorted(scales.items())},
        "line_ends_um": lengths,
        "lines_ff_per_um_and_ff": lines,
        "strips_ff": {
            name: {
                pair: {
                    "fastercap": round(fastercap[name].get(pair, 0.0), 5),
                    "rcx25": round(by_pair(after, pair)[name], 5),
                }
                for pair in ("MAIN-TOP", "DIFF-TOP", "DIFF-MAIN")
            }
            for name in after
        },
    }
    return out


METHOD = (
    "kpex's forms fitted to 2-D cross-sections (capiche solve2d) in the kit's stack; the MOM metals' sidewall "
    "scaled to FasterCap's 3-D coupling per finger length of the capacitive DAC's strips, and their line ends' "
    "reach to its ends (flow.layout.kpex_coefficients)"
)


def _code_sha() -> str:
    """The hash of the code that makes the coefficients: this file and the extraction's."""
    digest = hashlib.sha1()
    for path in (Path(__file__), Path(__file__).with_name("kpex_extract.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdk")
    parser.add_argument("--out", type=Path, help="default: pdk/<pdk>/kpex/parasitics.json")
    parser.add_argument("--work", type=Path, help="the cross-sections' folder (default: build/kpex_coefficients/<pdk>)")
    parser.add_argument("--workers", type=int, default=8, help="the solves at once (FasterCap's: KPEX_THREADS each)")
    parser.add_argument("--timeout", type=float, default=60, help="minutes FasterCap may take on a strip (0: no limit)")
    args = parser.parse_args()
    out = args.out or ROOT / "pdk" / args.pdk / "kpex" / "parasitics.json"
    work = args.work or ROOT / "build" / "kpex_coefficients" / args.pdk
    table = coefficients(args.pdk, work, args.workers)
    table = calibrate(args.pdk, table, work / "strips", args.workers, args.timeout * 60 or None)
    out.write_text(json.dumps(table, indent=1) + "\n")
    print(out)
