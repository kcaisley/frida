# ruff: noqa  -- an ALIGN PDK generator (ALIGN style), run in ALIGN's own Python
"""Wires and vias between placed blocks, drawn on cell_fabric grids: ``Wiring.wires`` draws each
straight segment (a metal, its net, its centre line's ends, its width) as a wire on a centre-line
grid of that metal and width, each cut as a via on the nanometre grid, each landing (a via's
metal past a wire's end) as a region. The route itself, which segment goes where, is the caller's
(``flow.cdac.layout``: a driver bank's outputs to an array's buses).

    Wiring().wires(segments=[["M3", "a", 100, 0, 100, 2000, 100]], cuts=[["V3", "a", 100, 2000, 100]])
"""

from align.cell_fabric.generators import Via, Wire
from align.cell_fabric.grid import CenterLineGrid

from .mom import _Fabric


class Wiring(_Fabric):
    """Straight wires, vias and landings by their coordinates (nm)."""

    def wires(self, segments=(), cuts=(), landings=(), pins=()):
        """``segments``: [metal, net, x0, y0, x1, y1, width], vertical (x0 == x1) or horizontal;
        ``cuts``: [via, net, x, y, size]; ``landings``: [metal, net, x0, y0, x1, y1] rectangles;
        ``pins``: [metal, net, x0, y0, x1, y1], a terminal's pin and its label."""

        by_line = {}  # (metal, direction, width) -> the centre lines its segments use
        for metal, _net, x0, y0, x1, y1, width in segments:
            vertical = x0 == x1
            by_line.setdefault((metal, "v" if vertical else "h", width), set()).add(x0 if vertical else y0)
        generators = {}
        for (metal, direction, width), centres in by_line.items():
            grid = CenterLineGrid()
            for centre in sorted(centres):
                grid.addCenterLine(centre, width)
            if len(centres) == 1:  # a grid is its lines' period: one more past the only one
                grid.addCenterLine(max(centres) + width, width)
            index = {centre: k for k, centre in enumerate(sorted(centres))}
            gen = self.addGen(Wire(f"wire_{metal}_{direction}_{width}", metal, direction, clg=grid, spg=self.nm))
            generators[(metal, direction, width)] = (gen, index)
        for metal, net, x0, y0, x1, y1, width in segments:
            vertical = x0 == x1
            gen, index = generators[(metal, "v" if vertical else "h", width)]
            if vertical:
                self.addWire(gen, net, index[x0], min(y0, y1), max(y0, y1))
            else:
                self.addWire(gen, net, index[y0], min(x0, x1), max(x0, x1))
        for via, net, x, y, size in cuts:
            name = f"cut_{via}_{size}"
            if name not in self.generators:
                self.addGen(Via(name, via, h_clg=self.nm, v_clg=self.nm, WidthX=size, WidthY=size))
            self.addVia(self.generators[name], net, x, y)
        for metal, net, x0, y0, x1, y1 in landings:
            self.rect(metal, net, x0, y0, x1, y1)
        for metal, net, x0, y0, x1, y1 in pins:
            self.rect(metal, net, x0, y0, x1, y1, "pin")
        self.computeBbox()
        return self
