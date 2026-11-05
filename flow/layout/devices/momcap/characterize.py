"""Characterize a PDK's MOM capacitors by KLayout-PEX (FasterCap) and write the momcap table
(``pdk/<pdk>/devices/momcap.json``).

Each style the blocks use (``DIFFERENCE`` strips, ``RING`` units) on one to three of the PDK's MOM
metals is drawn by ALIGN's ``MomUnit`` at a few finger lengths and extracted by its labelled
terminals. A finger's capacitance is linear in its length (its ends a constant), so every terminal
pair is fitted as C = a L_main + b L_diff + c (a ring unit: C = a L + c) over short structures,
which extract in minutes where a long one takes an hour, and the fit reaches any length. The
lengths a unit can be drawn at start at ``min_length_nm`` (the shortest finger that holds its
vias, from the PDK's rules) on the grid ``grid_nm``.

    python -m flow.layout.devices.momcap.characterize tsmc65 [tsmc28 ...] [--workers N]
"""

from __future__ import annotations

import argparse
import math
import re
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from klayout import db

from flow.layout.kpex import Extractor
from flow.layout.package import pdk_dir as align_pdk_dir
from flow.layout.pdkproc import access_points, in_pdk, pdk_value
from flow.layout.run import Drawing, draw, drawn_only

from ..device import ROOT, write_table
from .geometry import TERMINALS, MomcapGeometry, MomStyle

# the finger lengths extracted (um): a difference strip's main and difference fingers apart, so the
# two-length fit is determined; a ring unit's inner finger
_STRIP_UM = ((2, 1.5), (4, 3), (6, 4.5), (4, 1.5))
_RING_UM = (2, 4, 6)
_LAYERS = (1, 2, 3)
_STYLES = (MomStyle.DIFFERENCE, MomStyle.RING)


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


def draw_unit(pdk: str, geometry: MomcapGeometry, top_cell: str) -> db.Layout:
    """Draw a unit with ALIGN's ``MomUnit``: its plates on every metal, joined by vias, over its
    shield, every terminal labelled; ALIGN's abstract layers and pin purpose left out, as its
    layouts' post step leaves them out (``flow/layout/post.py``)."""

    hold = mom_rules(pdk, geometry.layers).min_length
    fingers = (
        (geometry.length_nm, geometry.diff_length_nm)
        if geometry.style is MomStyle.DIFFERENCE
        else (geometry.length_nm,)
    )
    if min(fingers) < hold:
        raise ValueError(f"plates shorter than {hold} nm cannot hold their vias")
    arguments = {
        "style": geometry.style.name.lower(),
        "layers": geometry.layers,
        "length": geometry.length_nm,
        "diff_length": geometry.diff_length_nm,
        "space": 0,
    }
    access_points(pdk)  # the ALIGN PDK's standard cells read them at import
    with tempfile.TemporaryDirectory() as scratch:
        drawing = Drawing("MomUnit", "unit", arguments, Path(scratch) / f"{top_cell}.gds", top_cell)
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


def extract(run_dir: Path, pdk: str, geometry: MomcapGeometry) -> dict[tuple[str, str], float]:
    """Draw a unit into ``run_dir`` and extract it by KLayout-PEX: every terminal pair's capacitance."""
    from flow.layout.signoff import run_layout_pex

    run_dir.mkdir(parents=True, exist_ok=True)
    gds = run_dir / "momunit.gds"
    draw_unit(pdk, geometry, "momunit").write(str(gds))
    netlist = run_layout_pex(pdk, gds, "momunit", "momunit", run_dir, Extractor.KLAYOUT)
    return pair_capacitances(netlist.read_text(), TERMINALS[geometry.style])


def _snap(um: float, grid: int, least: int) -> int:
    return max(least, math.ceil(um * 1000 / grid) * grid)


def _geometries(pdk: str) -> list[MomcapGeometry]:
    geometries = []
    for layers in _LAYERS:
        hold = mom_rules(pdk, layers)
        snap = lambda um: _snap(um, hold.grid, hold.min_length)  # noqa: B023 - used at once
        geometries += [MomcapGeometry(MomStyle.DIFFERENCE, layers, snap(m), snap(d)) for m, d in _STRIP_UM]
        geometries += [MomcapGeometry(MomStyle.RING, layers, snap(length)) for length in _RING_UM]
    return geometries


def _extract_one(pdk: str, geometry: MomcapGeometry) -> dict[str, float]:
    name = f"{geometry.style.name.lower()}_{geometry.layers}_{geometry.length_nm}_{geometry.diff_length_nm}"
    pairs = extract(ROOT / "build" / "devices" / "momcap" / pdk / name, pdk, geometry)
    return {"-".join(pair): value for pair, value in pairs.items()}


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


def characterize(pdk: str, workers: int = 8) -> Path:
    """Extract ``pdk``'s structures and write its momcap table."""

    geometries = _geometries(pdk)
    with ProcessPoolExecutor(workers) as pool:
        results = list(pool.map(_extract_one, [pdk] * len(geometries), geometries))
    styles: dict[str, dict[str, dict[str, Any]]] = {}
    for style in _STYLES:
        for layers in _LAYERS:
            points = [
                (g, r) for g, r in zip(geometries, results, strict=True) if g.style is style and g.layers == layers
            ]
            hold = mom_rules(pdk, layers)
            styles.setdefault(style.name, {})[str(layers)] = {
                "grid_nm": hold.grid,
                "min_length_nm": hold.min_length,
                "end_gap_nm": hold.end_gap,
                "lengths_nm": [[g.length_nm, g.diff_length_nm] for g, _ in points],
                "pairs": _fit(points, strip=style is MomStyle.DIFFERENCE),
            }
    return write_table("momcap", pdk, {"styles": styles}, method="KLayout-PEX (FasterCap), finger length fits")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdks", nargs="+")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    for name in args.pdks:
        print(characterize(name, args.workers))
