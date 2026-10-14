"""Convert a cIcCreator ``.cic`` file to GDS with KLayout.

cicpy (>= 0.1.5 of ciccreator) writes layout only as ``.cic`` JSON and
transpiles to SKILL/Magic, not GDS.  This walks the JSON (cells, rectangles,
nested route objects and instances) and writes one GDS cell per ``.cic`` cell.
Coordinates are in angstrom; GDS is written with a 1 nm database unit.
Top-cell ports become text labels on the layer named by the tech file's
``pin`` entry (the PDK's pin-text layer of that metal), which the LVS deck attaches to metal.

    uv run python flow/layout/cic/cic2gds.py DESIGN.cic TECH.tech out.gds [TOP]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import klayout.db as kdb

A_PER_NM = 10
ORIENT = {
    "": kdb.Trans.R0,
    "R0": kdb.Trans.R0,
    "R90": kdb.Trans.R90,
    "R180": kdb.Trans.R180,
    "R270": kdb.Trans.R270,
    "MX": kdb.Trans.M0,
    "MY": kdb.Trans.M90,
}


def load_tech(path: str) -> dict:
    text = re.sub(r"^\s*//.*$", "", Path(path).read_text(), flags=re.MULTILINE)
    return json.loads(text)["layers"]


def convert(cic_path: str, tech_path: str, gds_path: str, top: str | None = None) -> None:
    layers = load_tech(tech_path)
    design = json.loads(Path(cic_path).read_text())
    cells = {c["name"]: c for c in design["cells"]}
    layout = kdb.Layout()
    layout.dbu = 0.001
    kcells = {name: layout.create_cell(name) for name in cells}
    top = top or design["cells"][-1]["name"]

    def layer(name: str) -> int | None:
        info = layers.get(name)
        return None if info is None else layout.layer(info["number"], info["datatype"])

    def box(obj: dict) -> kdb.Box:
        return kdb.Box(*(obj[k] // A_PER_NM for k in ("x1", "y1", "x2", "y2")))

    def emit(kcell: kdb.Cell, children: list[dict], label_ports: bool, placed: list | None = None) -> list:
        placed = [] if placed is None else placed
        for child in children:
            kind = child.get("class")
            if kind == "Rect":
                li = layer(child["layer"])
                if li is not None and child["x2"] > child["x1"] and child["y2"] > child["y1"]:
                    kcell.shapes(li).insert(box(child))
            elif kind == "Port":
                if label_ports and child.get("spicePort", True):
                    pin = layers.get(child["layer"], {}).get("pin")
                    li = layer(pin) if pin else None
                    if li is not None:
                        center = box(child).center()
                        kcell.shapes(li).insert(kdb.Text(child["name"], kdb.Trans(center.x, center.y)))
            elif kind == "Instance":
                sub = cells.get(child["cell"])
                if sub is None:
                    continue
                x1, y1 = child["x1"] // A_PER_NM, child["y1"] // A_PER_NM
                sx1, sy1, sx2, sy2 = (sub[k] // A_PER_NM for k in ("x1", "y1", "x2", "y2"))
                angle = child.get("angle", "") or ""
                if angle not in ORIENT:
                    raise ValueError(f"unsupported instance angle {angle!r} for {child['cell']}")
                # the instance's bounding box lands with its lower left corner at (x1, y1)
                rot = kdb.Trans(ORIENT[angle], 0, 0)
                bb = rot * kdb.Box(sx1, sy1, sx2, sy2)
                trans = kdb.Trans(ORIENT[angle], x1 - bb.left, y1 - bb.bottom)
                placed.append((child["cell"], trans))
                kcell.insert(kdb.CellInstArray(kcells[child["cell"]].cell_index(), trans))
            elif "children" in child:
                emit(kcell, child["children"], label_ports, placed)
        return placed

    def ports(cell: dict) -> list[dict]:
        out = []
        for child in cell.get("children", []):
            if child.get("class") == "Port" and child.get("spicePort", True):
                out.append(child)
            elif child.get("class") != "Instance" and "children" in child:
                out += ports(child)
        return out

    for name, cell in cells.items():
        placed = emit(kcells[name], cell.get("children", []), label_ports=(name == top))
        # a wrapper top cell (LayoutRotateCell) has no ports of its own: label its instance's
        if name == top and not ports(cell) and len(placed) == 1:
            sub, trans = placed[0]
            for port in ports(cells[sub]):
                pin = layers.get(port["layer"], {}).get("pin")
                if pin:
                    kcells[name].shapes(layer(pin)).insert(
                        kdb.Text(port["name"], trans * kdb.Trans(box(port).center()))
                    )

    layout.write(gds_path)


if __name__ == "__main__":
    convert(*sys.argv[1:4], *(sys.argv[4:5] or [None]))
