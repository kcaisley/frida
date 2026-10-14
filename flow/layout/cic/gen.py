"""cIcCreator (cicpy) object file for a design in standard-cell rows, from a floorplan.

cicpy places and assembles: every netlist instance is drawn by the stems engine
(netcells: transistors as row cells, logic as the PDK's standard cells) and handed to cicpy
as a placeholder cell (outline, rails, pins: the routing view), and cicpy's placer stacks
a group's cells into a column (``Layout::LayoutDigitalCell``, ``alternateGroup`` mirrors every
other column so they share rails). The block is built transposed and wrapped in a
``LayoutRotateCell`` R90: columns become rows. route.py adds the routes, post.py swaps the
real cells (``<design>_cells.gds``, written here) into the placeholders.

Floorplan: e.g. design/layout/comp_frida1.json (rows top first, each mirrored about the
centre: the right half's cells are drawn mirrored, as cicpy's placer takes no instance
orientation), netlist: the one it names for the PDK, split as it says. Every row is padded
to one length with fillers (one XPITCH each) and ends in edge cells, which drop the rails to
the supply trunks.

    uv run python flow/layout/cic/gen.py tsmc65 design/layout/comp_frida1.json build/layout/cic/tsmc65
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if __name__ == "__main__":  # the PDK's layout directory (tech, paths) first, then the stems engine
    sys.path[:0] = [str(ROOT / "pdk" / sys.argv[1] / "layout"), str(ROOT / "flow/layout/stems")]

import klayout.db as kdb
import netcells
import rowcell
from tech import XPITCH

A = 10  # .cic units: angstrom
H = rowcell.H
LAYER = {"M1": "M1", "V1": "VIA1", "M2": "M2", "BND": "PR"}
EDGE_W = netcells.EDGE_W


@dataclass
class Slot:
    """One placed cell in a column (transposed frame: y along the column)."""

    inst: str
    cell: str
    nets: list[str]
    y0: int
    h: int
    dev: str = ""  # netlist instance it is
    mirror: bool = False  # drawn mirrored (MY in the final frame)
    pins: dict[str, str] = field(default_factory=dict)  # port -> net


def mirrored(cell: rowcell.Cell) -> rowcell.Cell:
    """The cell flipped about its vertical centre line (final frame MY)."""
    out = rowcell.Cell(cell.name + "_MY", cell.width)
    for r in cell.rects:
        out.add(r.layer, cell.width - r.x1, r.y0, cell.width - r.x0, r.y1, r.net, r.kind, r.term)
    return out


def placeholder(name: str, cell: rowcell.Cell, nodes: list[str], ports: dict[str, str]) -> dict:
    """A cell's routing view as a .cic cell, turned R270 into the transposed frame.
    ``ports``: pin net -> port name (the .subckt node it is)."""
    w = cell.width
    children = []
    for r in cell.rects:
        if r.layer not in LAYER or r.kind == "stub":
            continue
        # R270 + shift; clipped to the row (the rails reach past it, the next row brings them back);
        # cicpy places by the children's extent
        box = {"x1": max(r.y0, 0) * A, "y1": (w - r.x1) * A, "x2": min(r.y1, H) * A, "y2": (w - r.x0) * A}
        if r.kind == "pin" and r.layer == "M2" and r.net in ports:
            children.append({"class": "Port", "layer": "M2", "name": ports[r.net], "net": "", "spicePort": True, **box})
        children.append({"class": "Rect", "layer": LAYER[r.layer], "net": "", **box})
    return {
        "ckt": {"class": "", "devices": [], "instances": [], "name": name, "nodes": nodes, "properties": {}},
        "class": "LayoutCell",
        "has_pr": True,
        "layer": "PR",
        "name": name,
        "net": "",
        "x1": 0,
        "y1": 0,
        "x2": H * A,
        "y2": w * A,
        "children": children,
    }


def generate(pdk: str, floorplan: Path, out_root: Path) -> Path:
    fp = json.loads(floorplan.read_text())
    name, src = netcells.floorplan_netlist(floorplan, pdk)
    _, ports, insts = netcells.parse(src)
    by_name = {i.name: i for i in insts}
    out = out_root / name
    out.mkdir(parents=True, exist_ok=True)
    top, inner = name.upper(), name.upper() + "_T"
    rows = list(reversed(fp["rows"]))  # column 0 = bottom row

    cells: dict[str, tuple[rowcell.Cell, netcells.Inst | None, bool]] = {}  # placeholder -> (cell, instance, mirror)
    lib = []

    def use(ph: str, cell: rowcell.Cell, inst=None, mirror=False, nodes=None, pins=None) -> None:
        if ph not in cells:
            cells[ph] = (cell, inst, mirror)
            lib.append(placeholder(ph, mirrored(cell) if mirror else cell, nodes or ["vdd", "vss"], pins or {}))

    # ---- columns: cells bottom up in the transposed frame (= final right to left)
    columns: list[list[Slot]] = []
    for c, row in enumerate(rows):
        letter = chr(ord("A") + c)
        std_row = all(by_name[n].kind != "mos" for n in row)
        slots: list[Slot] = []
        edge = netcells.edge(EDGE_W, std=std_row)
        use(f"PH_{edge.name}", edge)
        use(f"PH_{edge.name}_MY", edge, mirror=True)
        slots.append(Slot("E", f"PH_{edge.name}_MY", ["vdd", "vss"], 0, EDGE_W))  # final right end
        half = len(row) // 2
        for j, n in reversed(list(enumerate(row))):
            i = by_name[n]
            mirror = j >= len(row) - half
            cell = netcells.cell_of(i)
            ph = f"PH_{n}{'_MY' if mirror else ''}"
            nets = sorted({r.net for r in cell.rects if r.kind == "pin" and r.net and "__" not in r.net})
            use(ph, cell, i, mirror, nets, {net: net for net in nets})
            slots.append(Slot("X", ph, nets, 0, cell.width, n, mirror, {net: net for net in nets}))
        slots.append(Slot("E", f"PH_{edge.name}", ["vdd", "vss"], 0, EDGE_W))  # final left end
        columns.append(slots)

    # ---- one length for every column: fillers split around the cells
    length = lambda slots: sum(s.h for s in slots)
    target = max(length(s) for s in columns)
    for c, slots in enumerate(columns):
        std = all(by_name[s.dev].kind != "mos" for s in slots if s.dev)
        fill = netcells.std_fill(XPITCH) if std else netcells.filler(XPITCH)
        ph = f"PH_{fill.name}"
        use(ph, fill)
        n_fill = (target - length(slots)) // XPITCH
        assert length(slots) + n_fill * XPITCH == target, (c, length(slots), target)
        lo, hi = n_fill // 2, n_fill - n_fill // 2
        mk = lambda ph=ph: Slot("F", ph, ["vdd", "vss"], 0, XPITCH)
        columns[c] = slots[:1] + [mk() for _ in range(lo)] + slots[1:-1] + [mk() for _ in range(hi)] + slots[-1:]
        letter = chr(ord("A") + c)
        y = 0
        for k, s in enumerate(columns[c]):  # names: the group is the leading letters, the rest numbers
            s.inst = f"X{letter}{k:03d}"
            s.y0 = y
            y += s.h

    # ---- netlist (the placer reads the instance order as the floorplan)
    spi = [
        f"* {name} in {pdk} standard-cell rows, generated by flow/layout/cic/gen.py",
        f".SUBCKT {inner} {' '.join(ports)}",
    ]
    for slots in columns:
        for s in slots:
            spi.append(f"{s.inst} {' '.join(s.nets)} {s.cell}")
    spi.append(f".ENDS {inner}")

    # ---- the real cells, turned R270 into the transposed frame like their placeholders
    layout = kdb.Layout()
    layout.dbu = 0.001
    std_lib = kdb.Layout()
    std_lib.read(str(netcells.STD_GDS))
    drawn = {}
    for ph, (cell, inst, mirror) in cells.items():
        if cell.name not in drawn:
            drawn[cell.name] = netcells.draw(layout, kdb, cell, inst, std_lib)
        turn = kdb.Trans(3, False, 0, cell.width)  # R270: final (x, y) -> transposed (y, w - x)
        if mirror:
            turn = turn * kdb.Trans(kdb.Trans.M90, cell.width, 0)  # MY about the cell's centre first
        wrap = layout.create_cell(ph)
        wrap.insert(kdb.CellInstArray(drawn[cell.name].cell_index(), turn))
    layout.write(str(out / f"{name}_cells.gds"))

    lib_path = out / f"{name}_lib.cic"
    lib_path.write_text(json.dumps({"cells": lib, "info": {"library": f"{name}_lib"}}) + "\n")
    (out / f"{name}.spi").write_text("\n".join(spi) + "\n")
    (out / f"{name}_place.json").write_text(
        json.dumps({"columns": [[s.__dict__ for s in col] for col in columns], "length": target}, indent=0) + "\n"
    )
    obj = {
        "library": [lib_path.name],
        "cells": [
            {"name": inner, "class": "Layout::LayoutDigitalCell", "alternateGroup": 1},
            {
                "name": top,
                "class": "Layout::LayoutRotateCell",
                "rotateAngle": "R90",
                "spice": [f".subckt {top} {' '.join(ports)}", f"XA1 {' '.join(ports)} {inner}", ".ends"],
            },
        ],
    }
    path = out / f"{name}.json"
    path.write_text(json.dumps(obj, indent=1) + "\n")
    print(f"{name}: {len(columns)} rows of {target} nm, {sum(len(c) for c in columns)} cells")
    return path


if __name__ == "__main__":
    generate(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
