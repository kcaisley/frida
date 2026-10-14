# ruff: noqa  -- adapted from ALIGN's Bulk65nm mock PDK (star imports, ALIGN style)
"""The PDK's standard cells as ALIGN primitives (generic generators, one per cell).

ALIGN sees an abstract: the cell outline, the M1 supply rails (the supply pins), and per
signal pin an M1 patch, VIA1 and an M2 pin bar at the access point from
``paths.ACCESS_JSON``. ``align/post.py`` drops the
real cell (the library GDS, ``paths.STD_GDS``) into the abstract after place and route.

The cell is wrapped for free placement (``iso`` in the access table): pads on both sides
carry the standard cells' implant and well profile up to the outline (``rowcell.std_pad``),
so analog row cells and standard cells abut in any order. With STEMS_STD_DENSE set (a
floorplan that keeps standard cells in rows of their own) the dense wrapper is used:
the library filler on the left to the placement grid. Like the
analog row cells, standard cells are placed on the two-row grid, flipped on odd rows.

The netlist instantiates them as ``X... <pins in .subckt order> CELL`` and defines each
cell by its transistors (from the library SPICE) with a ``Generator`` annotation
(align/make_design.py): ALIGN keeps the cell a leaf drawn here, and its symmetry search
sees which pins are gates (inputs) and which drains (outputs). Pins keep the library's names.
"""

import json
import os
from pathlib import Path

from align.cell_fabric import Pdk, transformation

from .mos import X_GRID, RowCanvas, rowcell
from paths import ACCESS_JSON  # noqa: E402  (on the path through .mos)
import tech  # noqa: E402
from tech import BAR_END, M1W, M2_MIN_LEN, M3W, PITCH, STD_LIB, STD_SUPPLY, V1, V2, XPITCH  # noqa: E402
import netcells  # noqa: E402

M3_GRID = getattr(tech, "M3_PITCH", XPITCH)  # ALIGN's M3 grid (make_pdk.py)
VIA_M1_W = getattr(tech, "VIA_M1_W", M1W)  # the M1 width the pin accesses were found with (stdcell_access.py)
# the M1 stub's half height: the cut's landing, or just the cut where the landing may lie across
# the pin (VIA_EOL_ACROSS), so the stub never pokes out of a short pin
STUB_H = V1 // 2 if getattr(tech, "VIA_EOL_ACROSS", False) else BAR_END

ACCESS = json.loads(ACCESS_JSON.read_text())


class StdCellGenerator(RowCanvas):
    cell = None

    def __init__(self, *args, **kwargs):
        super().__init__(Pdk().load(Path(__file__).resolve().parent / "layers.json"))

    def generate(self, ports, netlist_parameters=None, netlistdir=None, **kwargs):
        data = ACCESS[self.cell]
        assert len(ports) == len(data["pins"]), f"{self.cell}: ports {ports} vs {data['pins']}"
        net = dict(zip(data["pins"], ports))
        frame = data if os.environ.get("STEMS_STD_DENSE") else data["iso"]
        w = frame["padded"]  # dense: library fillers complete the placement grid, see align/post.py
        c = rowcell.Cell(self.cell, w)
        vdd, vss = STD_SUPPLY
        for y, pin in ((0, vss), (rowcell.H, vdd)):
            c.add("M1", 0, y - rowcell.RAIL, w, y + rowcell.RAIL, net[pin], "pin")
        if frame is not data:
            off = frame["offset"]
            rowcell.std_pad(c, 0, off, "right", net[vss], net[vdd])
            rowcell.std_pad(c, off + data["width"], w, "left", net[vss], net[vdd])
        m3_used = []
        views, keep = netcells.align_access(frame)
        for pin, a in frame["access"].items():
            n = net[pin]
            for x, y in a["cuts"]:  # ALIGN bins M1 by centre line: one stub per cut, inside the pin
                c.add("M1", x - VIA_M1_W // 2, y - STUB_H, x + VIA_M1_W // 2, y + STUB_H, n, "stub")
                c.add("V1", x - V1 // 2, y - V1 // 2, x + V1 // 2, y + V1 // 2, n)
            if a["patch"]:
                c.add("M1", *a["patch"], n)
            x0, y0, x1, y1 = a["bar"]
            y = (y0 + y1) // 2
            if y % PITCH == 0:  # on ALIGN's M2 grid: the bar (netcells.align_access) is the pin
                if a["pad"]:  # a pin shape too, so the router sees how far it reaches
                    c.add("M2", *a["pad"], n, "pin")
                c.add("M2", *views[pin][1], n, "pin")
                continue
            # a pin between the M2 tracks (half-pitch tracks): a pin bar on the free track
            # beside the via's pad (netcells.align_access); with neither track free, the bar is
            # drawn and the pin is an M3 stub over it (VIA2) on a free M3 track of ALIGN's grid,
            # nearest the bar's middle
            if a["pad"]:
                c.add("M2", *a["pad"], n)
            pad, bar = views[pin]
            if bar:  # the pad, a bare shape that would block the bar it touches, is drawn by post.py
                c.add("M2", *bar, n, "pin")
                continue
            c.add("M2", *a["bar"], n)
            xs = range(-(-(x0 + BAR_END) // M3_GRID) * M3_GRID, x1 - BAR_END + 1, M3_GRID)
            xm = min((x for x in xs if x not in m3_used), key=lambda x: abs(2 * x - x0 - x1))
            m3_used.append(xm)
            c.add("V2", xm - V2 // 2, y - V2 // 2, xm + V2 // 2, y + V2 // 2, n)
            # the stub reaches the next tracks clear of the bar's keep-outs (netcells.align_access),
            # where the router can land on it, as far as they lie inside the cell
            lo, hi = y - PITCH // 2 - PITCH, y + PITCH // 2 + PITCH
            y0 = lo - BAR_END if lo >= PITCH else y - M2_MIN_LEN // 2
            y1 = hi + BAR_END if hi <= rowcell.H - PITCH else y + M2_MIN_LEN // 2
            c.add("M3", xm - M3W // 2, y0, xm + M3W // 2, y1, n, "pin")
        for box in keep:
            c.add("M2", *box, None, "blockage")
        c.add("BND", 0, 0, w, rowcell.H)
        self.draw(c.rects)
        self.bbox = transformation.Rect(0, 0, w, rowcell.H)
        self.metadata["instances"] = [{"library": STD_LIB, "cell": self.cell, "view": "layout"}]


CELLS = list(ACCESS)  # stable order: the index travels through ALIGN as x_cells
INDEX_BASE = 1000


class RingGenerator(StdCellGenerator):
    """Entry point for standard cells.

    ALIGN's generic-primitive path is broken upstream (``generate_primitives`` leaves
    ``primitive_def`` unset), so gen_param.py hands standard cells to the guard-ring path
    instead, with the cell's index in ``x_cells``: ALIGN then calls
    ``RingGenerator(pdk).addRing(x_cells, y_cells)``. Pins are named as in the library.
    """

    def __init__(self, pdk=None, *args, **kwargs):
        super().__init__()

    def addRing(self, x_cells, y_cells):
        self.cell = CELLS[x_cells - INDEX_BASE]
        self.generate(ACCESS[self.cell]["pins"])


def generator_class(name):
    """ALIGN asks the PDK for a generator by model or primitive name (any case)."""
    if not name:
        return False
    key = name.upper()
    for cell in ACCESS:  # library names in any case
        if key == cell.upper() or key.startswith(cell.upper() + "_"):
            return type(cell, (StdCellGenerator,), {"cell": cell})
    return False
