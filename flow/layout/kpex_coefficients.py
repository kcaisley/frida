"""A kit's coefficients for KLayout-PEX's 2.5-D engine (kpex's ``process_parasitics``,
``pdk/<pdk>/kpex/parasitics.json``), fitted to direct 2-D field solves of test cross-sections in
the kit's own planar stack, the one FasterCap extracts in (``flow.layout.kpex.technology``:
``stack.json``, each metal's level and the dielectric above it).

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
poly takes the first metal's. On TSMC65 the fit comes within a few percent of the coefficients fitted
to FasterCap's 3-D solves of test structures, and on the capacitive DAC's arrays the 2.5-D engine on
it within a few percent of FasterCap's extraction in every kit FasterCap finished.

    uv run python -m flow.layout.kpex_coefficients <pdk> [--out FILE] [--work DIR] [--workers N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from importlib import import_module
from pathlib import Path

import numpy as np

from flow.layout.kpex import ROOT, technology

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdk")
    parser.add_argument("--out", type=Path, help="default: pdk/<pdk>/kpex/parasitics.json")
    parser.add_argument("--work", type=Path, help="the cross-sections' folder (default: build/kpex_coefficients/<pdk>)")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    out = args.out or ROOT / "pdk" / args.pdk / "kpex" / "parasitics.json"
    table = coefficients(args.pdk, args.work or ROOT / "build" / "kpex_coefficients" / args.pdk, args.workers)
    out.write_text(json.dumps(table, indent=1) + "\n")
    print(out)
