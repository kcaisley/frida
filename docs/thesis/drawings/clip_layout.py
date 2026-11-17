"""A small piece of a large layout, for the thesis's 3-D stack-up scenes: the hierarchy clipped to
a box (KLayout's clip, so a whole chip's matrix yields a few pixels) and written as its own GDS.
The sources (other chips' layouts) are named only on the command line: nothing of them, their
paths or their cells, is written here, and the pieces go to gitignored build/ folders.

    uv run python docs/thesis/drawings/clip_layout.py GDS --find PATTERN [--top CELL]
    uv run python docs/thesis/drawings/clip_layout.py GDS --around PATTERN [--grow UM] OUT.gds
    uv run python docs/thesis/drawings/clip_layout.py GDS --box X0,Y0,X1,Y1 OUT.gds

``--find`` lists the cells whose names match PATTERN (a regex), each with its size, how often it
is placed under the top cell, and its placement nearest the top cell's centre (µm). ``--around``
clips around that nearest placement of the first matching cell, grown by UM on every side;
``--box`` clips to a box in the top cell's coordinates (µm). The piece keeps the top cell's
coordinates, so a box found in one piece can be cut again from the whole.
"""

from __future__ import annotations

import argparse
import re
import time

import klayout.db as kdb


def read(path: str, top: str | None) -> tuple[kdb.Layout, kdb.Cell]:
    start = time.time()
    layout = kdb.Layout()
    layout.read(path)
    cell = layout.cell(top) if top else layout.top_cells()[0]
    if cell is None:
        raise SystemExit(f"no cell {top}")
    print(flush=True, end="")
    print(f"read {path} in {time.time() - start:.0f} s: top {cell.name}, {layout.cells()} cells, {cell.dbbox()}")
    return layout, cell


def placements(layout: kdb.Layout, top: kdb.Cell, target: kdb.Cell, limit: int = 20000) -> list[kdb.DBox]:
    """Placements of target under top, as boxes in top's coordinates (µm): every one when there
    are few, else one per path up to the top, each through the middle member of every array on
    the way (a whole chip's matrix has its pixels by the hundred thousand)."""

    paths: list[kdb.ICplxTrans] = []

    def up(cell: kdb.Cell, trans: kdb.ICplxTrans, depth: int) -> None:
        if cell.cell_index() == top.cell_index():
            paths.append(trans)
            return
        if depth > 64 or len(paths) >= limit:
            return
        for parent in cell.each_parent_inst():
            inst = parent.child_inst()
            member = inst.cplx_trans
            if inst.is_regular_array():
                member = kdb.ICplxTrans(kdb.Trans(inst.a * (inst.na // 2) + inst.b * (inst.nb // 2))) * member
            up(layout.cell(parent.parent_cell_index()), member * trans, depth + 1)

    up(target, kdb.ICplxTrans(), 0)
    return [target.bbox().transformed(trans).to_dtype(layout.dbu) for trans in paths]


def nearest(boxes: list[kdb.DBox], centre: kdb.DPoint) -> kdb.DBox:
    return min(boxes, key=lambda box: box.center().distance(centre))


def clip(layout: kdb.Layout, top: kdb.Cell, box: kdb.DBox, out: str) -> None:
    start = time.time()
    index = layout.clip(top.cell_index(), box.to_itype(layout.dbu))
    piece = layout.cell(index)
    piece.name = f"{top.name}_clip"
    options = kdb.SaveLayoutOptions()
    options.select_cell(index)
    layout.write(out, options)
    print(f"clipped {box} into {out} ({piece.name}) in {time.time() - start:.0f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gds")
    parser.add_argument("out", nargs="?")
    parser.add_argument("--top")
    parser.add_argument("--find")
    parser.add_argument("--around")
    parser.add_argument("--grow", type=float, default=0.0)
    parser.add_argument("--box")
    args = parser.parse_args()
    layout, top = read(args.gds, args.top)
    centre = top.dbbox().center()
    if args.find:
        pattern = re.compile(args.find)
        for cell in layout.each_cell():
            if not pattern.search(cell.name):
                continue
            boxes = placements(layout, top, cell)
            where = nearest(boxes, centre) if boxes else None
            print(flush=True, end="")
            print(
                f"{cell.name:48s} {cell.dbbox().width():9.2f} x {cell.dbbox().height():9.2f}  placed {len(boxes):6d}  nearest {where}"
            )
        return
    if not args.out:
        raise SystemExit("an output GDS is needed")
    if args.around:
        pattern = re.compile(args.around)
        cell = next((cell for cell in layout.each_cell() if pattern.search(cell.name)), None)
        if cell is None:
            raise SystemExit(f"no cell matches {args.around}")
        boxes = placements(layout, top, cell)
        if not boxes:
            raise SystemExit(f"{cell.name} is not placed under {top.name}")
        box = nearest(boxes, centre).enlarged(args.grow, args.grow)
        print(f"around {cell.name}: {len(boxes)} placements, the nearest the centre at {box}")
    elif args.box:
        x0, y0, x1, y1 = (float(value) for value in args.box.split(","))
        box = kdb.DBox(x0, y0, x1, y1)
    else:
        raise SystemExit("--around or --box is needed")
    clip(layout, top, box, args.out)


if __name__ == "__main__":
    main()
