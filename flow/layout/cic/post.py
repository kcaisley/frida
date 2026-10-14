"""Finish a cicpy layout of gen.py's placeholders: the real cells in, flat.

gen.py's placeholders (``PH_<cell>``) are routing views turned R270 into the transposed frame
cicpy draws in; ``<design>_cells.gds`` holds a cell of the same name with the real cell (a
row cell, or a standard cell with its library cell and fillers) in the same turn, so the R90
of the top cell brings it upright. Then the top cell is flattened and shapes are merged and
snapped to the grid; the cells' tap bands and well bands already overhang the block's outline.

    uv run python flow/layout/cic/post.py tsmc65 raw.gds cells.gds out.gds TOP
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if __name__ == "__main__":  # the PDK's layout directory (tech, paths) first, then the stems engine
    sys.path[:0] = [str(ROOT / "pdk" / sys.argv[1] / "layout"), str(ROOT / "flow/layout/stems")]

import klayout.db as kdb
from tech import MFG_GRID


def main(src: str, cells: str, dst: str, top_name: str) -> None:
    layout = kdb.Layout()
    layout.read(src)
    for cell in layout.each_cell():
        if cell.name.startswith("PH_"):
            cell.clear_shapes()
    options = kdb.LoadLayoutOptions()
    options.cell_conflict_resolution = kdb.LoadLayoutOptions.CellConflictResolution.OverwriteCell
    layout.read(cells, options)
    top = layout.cell(top_name)
    for c in list(layout.top_cells()):
        if c.cell_index() != top.cell_index():
            layout.prune_cell(c.cell_index(), -1)
    layout.flatten(top.cell_index(), -1, True)
    for li in layout.layer_indexes():  # merge, snap to the grid; keep text
        shapes = top.shapes(li)
        texts = [s.text for s in shapes.each() if s.is_text()]
        polys = kdb.Region(shapes).merged().snapped(MFG_GRID, MFG_GRID)
        shapes.clear()
        shapes.insert(polys)
        for t in texts:
            shapes.insert(t)
    layout.write(dst)


if __name__ == "__main__":
    main(*sys.argv[2:6])
