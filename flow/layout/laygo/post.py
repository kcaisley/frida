"""Turn a GDS exported by the hosted laygo server into a layout in the target PDK.

The server writes routing on its layer numbers (server.py) and fills template cells with its
own geometry (or leaves cells it does not know empty). This maps the routing layers to
the PDK's, moves labels onto the PDK's pin-text layers and replaces every template cell
with the PDK cell of the same name from ``<design>_templates.gds`` (written by
rowtemplates.py). The row cells carry complete rails, wells and implants.

    uv run python flow/layout/laygo/post.py tsmc65 raw.gds templates.gds out.gds
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if __name__ == "__main__":  # the PDK's layout directory (tech) first
    sys.path.insert(0, str(ROOT / "pdk" / sys.argv[1] / "layout"))

import klayout.db as kdb
import tech as _tech
from server import server_layers
from tech import LAYERS, M2W, PIN_TEXT, V1, V2

SERVER = {ld[0]: m for m, ld in server_layers().items()}  # the server's metal layer numbers -> our metal names


def post(raw: str, templates: str, out: str) -> None:
    metals = {n: (LAYERS[m], PIN_TEXT[m]) for n, m in SERVER.items() if m in LAYERS and m in PIN_TEXT}
    layout = kdb.Layout()
    layout.read(raw)
    tlib = kdb.Layout()
    tlib.read(templates)
    template_names = {c.name for c in tlib.each_cell()}

    # 0. design pins: the server writes their labels on 0/0; attach each to the metal under it
    label_layer = layout.find_layer(0, 0)
    labels = []
    if label_layer is not None:
        for cell in layout.each_cell():
            for shape in cell.shapes(label_layer).each():
                if shape.is_text():
                    labels.append((cell, shape.text))
            cell.shapes(label_layer).clear()
    for cell, text in labels:
        # a pin's label sits at the centre of its pin rectangle: prefer the metal holding a shape
        # centred there (another metal may cross the same point), else the first metal under it
        p = text.trans.disp
        probe = kdb.Box(p.x - 1, p.y - 1, p.x + 1, p.y + 1)
        layers = [(m, li) for m in (10, 30, 50, 8, 67) if (li := layout.find_layer(m, 0)) is not None]
        centred = [
            m
            for m, li in layers
            for sh in cell.shapes(li).each()
            if not sh.is_text() and sh.bbox().center().distance(p) <= 5
        ]
        under = [
            m for m, li in layers if not kdb.Region(cell.begin_shapes_rec(li)).interacting(kdb.Region(probe)).is_empty()
        ]
        if centred or under:
            cell.shapes(layout.layer((centred or under)[0], 0)).insert(text)

    # 1. routing and labels: server layers -> temporary layers -> the PDK's (avoids number clashes)
    moves = []
    for info in list(layout.layer_infos()):
        src = layout.layer(info)
        if info.layer in metals:
            drawing, text = metals[info.layer]
            moves.append((src, layout.layer(10000 + drawing[0], drawing[1]), layout.layer(10000 + text[0], text[1])))
        else:
            layout.clear_layer(src)  # the server's front-end layers only exist inside template cells
    for cell in layout.each_cell():
        for src, drawing, text in moves:
            for shape in cell.shapes(src).each():
                if shape.is_text():
                    cell.shapes(text).insert(shape.text)
                else:  # drawing and pin purposes both become drawn metal
                    cell.shapes(drawing).insert(shape)
            cell.shapes(src).clear()
    for info in list(layout.layer_infos()):
        if info.layer >= 10000:
            layout.set_info(layout.layer(info), kdb.LayerInfo(info.layer - 10000, info.datatype))

    # 2. template cells: drop server geometry, take the PDK cell of the same name
    for cell in layout.each_cell():
        if cell.name in template_names:
            cell.clear_shapes()
    options = kdb.LoadLayoutOptions()
    options.cell_conflict_resolution = kdb.LoadLayoutOptions.CellConflictResolution.OverwriteCell
    layout.read(templates, options)

    # keep only the design (the cell named as the output file): other top cells are unused
    # templates from either library
    top = layout.cell(Path(out).stem)
    for cell in [c for c in layout.top_cells() if c.cell_index() != top.cell_index()]:
        layout.prune_cell(cell.cell_index(), -1)
    layout.flatten(top.cell_index(), -1, True)
    merge_cuts(layout, top, LAYERS["V1"])
    if getattr(_tech, "VIA_SPACE", None):
        join_cuts(layout, top)
    layout.write(out)


def merge_cuts(layout: kdb.Layout, top: kdb.Cell, cut: tuple[int, int]) -> None:
    """Replace overlapping cuts by one: two rows tying their sources to a shared rail can
    drop VIA1s a few nm apart. Overlapping cuts imply overlapping metal, so one suffices. Larger
    shapes (a library's rectangular vias) stay as they are."""
    li = layout.layer(*cut)
    shapes = top.shapes(li)
    merged = kdb.Region(shapes).merged()
    shapes.clear()
    for poly in merged.each():
        b = poly.bbox()
        if poly.area() < 2 * V1 * V1:
            shapes.insert(kdb.Box(b.left, b.bottom, b.left + V1, b.bottom + V1))
        else:
            shapes.insert(poly)


def join_cuts(layout: kdb.Layout, top: kdb.Cell) -> None:
    """Two VIA2 on one trunk closer than the via space allows (bars on adjacent tracks):
    keep the lower and join the upper one's M2 bar to the lower's with a strap under the trunk.
    Cuts that close sit on one M3 trunk (different nets' segments keep GAP3), so on one net."""
    li, m2 = layout.layer(*LAYERS["V2"]), layout.layer(*LAYERS["M2"])
    limit = V2 + _tech.VIA_SPACE
    cuts = sorted((s.bbox() for s in top.shapes(li).each()), key=lambda b: (b.left, b.bottom))
    kept = []
    for b in cuts:
        low = next((k for k in kept if k.left == b.left and 0 < b.bottom - k.bottom < limit), None)
        if low is None:
            kept.append(b)
        else:
            c = b.center().x
            top.shapes(m2).insert(
                kdb.Box(c - M2W // 2, low.center().y - M2W // 2, c + M2W // 2, b.center().y + M2W // 2)
            )
    top.shapes(li).clear()
    for b in kept:
        top.shapes(li).insert(b)


if __name__ == "__main__":
    post(*sys.argv[2:5])
