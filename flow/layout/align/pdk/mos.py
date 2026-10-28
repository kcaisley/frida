# ruff: noqa  -- adapted from ALIGN's Bulk65nm mock PDK (star imports, ALIGN style)
"""Row-cell MOS primitives for ALIGN: one transistor or a matched pair per cell, one or more standard-cell rows tall.

The geometry is the stems engine's (flow/layout/stems/rowcell.py; pairs such as ALIGN's DP, CMC
and CCP are ``rowcell.mos_row``), drawn with
the PDK's ``tech`` (this generated PDK directory's ``stems.json`` says where it is): VSS rail
and P+ tap at the bottom, VDD rail and N+ tap at the top, so NMOS, PMOS and the library's
standard cells abut in any order and supplies connect by abutment. Each primitive asks the
placer for standard-cell rows (``PlaceOnGrid``: y on a two-row pitch, flipped on the odd
rows), so VSS lands on even rail lines and VDD on odd ones.
The supply pins are the M2 straps over the rails; the design leaves vdd/vss unrouted
(``DoNotRoute``), and ``align/post.py`` closes the rails across placement gaps.

ALIGN's connectivity check bins every metal by its centre line (M1 vertical, M2
horizontal) and needs each via on such a line, hence the M1 stubs under the rail vias.
Its grid DRC does not apply to these off-grid cells (Calibre signs off), so it is off.

The cell is drawn with ALIGN's layout API (``RowCanvas``): its metals as wires on centre-line
grids, its contacts and vias as vias, its other layers as regions, all on the nanometre grid;
the comparators' layouts are mask- and label-identical to those of the cells' rectangles added
as terminals (2026-10-28, two a PDK in all six).
"""

import json
import logging
import os
import sys
from pathlib import Path

from align.cell_fabric import transformation
from align.cell_fabric.generators import Region, Via, Wire
from align.cell_fabric.grid import CenterLineGrid, SingleGrid
from align.primitive.default.canvas import DefaultCanvas
from align.schema.constraint import OffsetsScalings, PlaceOnGrid

_STEMS = json.loads((Path(__file__).resolve().parent / "stems.json").read_text())  # written by make_pdk.py
sys.path[:0] = [_STEMS["layout"], _STEMS["stems"]]  # the PDK's tech and paths, then the engine
import rowcell
import tech
from tech import BAR_END, M2_EDGE, M2_SPACE, XPITCH

logger = logging.getLogger(__name__)

LAYERS = {
    "OD": "Active",
    "PO": "Poly",
    "CO": "V0",
    "M1": "M1",
    "V1": "V1",
    "M2": "M2",
    "V2": "V2",
    "M3": "M3",
    "NW": "Nwell",
    "PP": "Pselect",
    "NP": "Nselect",
    "VTN": "Lvt",
    "VTP": "Slvt",
    "BND": "Boundary",
    **_STEMS.get("extra", {}),  # the PDK's own markers on spare ALIGN layers (make_pdk.py)
}
X_GRID = 2 * XPITCH  # two M3 pitches: symmetric pairs need widths of equal parity on the placement grid


def row_constraints():
    return [
        PlaceOnGrid(
            direction="H", pitch=2 * rowcell.H, ored_terms=[OffsetsScalings(offsets=[0], scalings=[1, -1])]
        ).dict()
    ]


# the row cells' cut layers and metals, by ALIGN's names: a cut is a via, a metal a wire
CUTS = ("V0", "V1", "V2")
METALS = ("M1", "M2", "M3")


class RowCanvas(DefaultCanvas):
    """A canvas that draws a stems row cell (``rowcell.Cell``) with ALIGN's generators on the
    nanometre grid: each metal rectangle a wire on a centre-line grid of its layer, direction and
    width, each contact and via a via of its size, every other layer (diffusion, poly, implants,
    wells, the boundary) a region. The canvas's generators are ALIGN's for each layer as before
    (its routing metals' wires, a via for the contacts, a region for each other layer), so ALIGN
    merges, names and checks each layer's shapes as it would a row cell's: a metal or a cut of an
    odd size, which no centre-line grid holds exactly, is the one shape added as it is."""

    def __init__(self, pdk):
        super().__init__(pdk)
        self.nm = SingleGrid(pitch=1)
        for layer in (
            "Active",
            "Poly",
            "Nselect",
            "Pselect",
            "Nwell",
            "Lvt",
            "Slvt",
            *_STEMS.get("extra", {}).values(),
        ):
            self.addGen(Region(layer.lower(), layer, h_grid=self.nm, v_grid=self.nm))
        self.addGen(
            Via(
                "v0",
                "V0",
                h_clg=self.m2.clg,
                v_clg=self.m1.clg,
                WidthX=self.pdk["V0"]["WidthX"],
                WidthY=self.pdk["V0"]["WidthY"],
            )
        )
        self.metadata = {"constraints": [] if os.environ.get("STEMS_NO_GRID") else row_constraints()}

    def gen_data(self, *, run_drc=True, **kwargs):
        # ALIGN's grid DRC does not apply to these off-grid cells (Calibre signs off); keep an
        # error list, ALIGN's checker appends router findings to it
        data = super().gen_data(run_drc=False, **kwargs)
        if self.drc is None:
            self.drc = type("NoDRC", (), {"errors": [], "num_errors": property(lambda s: len(s.errors))})()
        return data

    def computeBbox(self):
        if self.bbox is None:
            super().computeBbox()

    def _generator(self, name, make):
        if name not in self.generators:
            self.addGen(make(name))
        return self.generators[name]

    def draw(self, rects, net_map=lambda n: n):
        shapes = []
        for r in rects:
            net = r.term if r.term else net_map(r.net)
            pin = r.kind == "pin" and net is not None and ":" not in net
            kind = "pin" if pin else "blockage" if r.kind == "blockage" else "drawing"
            shapes.append((LAYERS[r.layer], net, r.x0, r.y0, r.x1, r.y1, kind))
        # each metal's wires: a centre-line grid per layer, direction and width, holding every
        # centre line its rectangles of that width run on (two at least: a grid is its lines' period)
        lines = {}
        for layer, _net, x0, y0, x1, y1, _kind in shapes:
            if layer in METALS and _even(x0, y0, x1, y1):
                _layer, direction, width, centre = _line(x0, y0, x1, y1, layer)
                lines.setdefault((layer, direction, width), set()).add(centre)
        wires = {}
        for (layer, direction, width), centres in lines.items():
            grid = CenterLineGrid()
            for centre in sorted(centres):
                grid.addCenterLine(centre, width)
            if len(centres) == 1:
                grid.addCenterLine(max(centres) + width, width)
            gen = self._generator(
                f"row_{layer}_{direction}_{width}", lambda n: Wire(n, layer, direction, clg=grid, spg=self.nm)
            )
            wires[(layer, direction, width)] = (gen, {centre: k for k, centre in enumerate(sorted(centres))})
        for layer, net, x0, y0, x1, y1, kind in shapes:
            if layer in METALS and _even(x0, y0, x1, y1):
                _layer, direction, width, centre = _line(x0, y0, x1, y1, layer)
                gen, index = wires[(layer, direction, width)]
                lo, hi = (y0, y1) if direction == "v" else (x0, x1)
                self.addWire(gen, net, index[centre], lo, hi, netType=kind)
            elif layer in CUTS and kind == "drawing" and (x1 - x0) % 2 == 0 and (y1 - y0) % 2 == 0:
                gen = self._generator(
                    f"cut_{layer}_{x1 - x0}_{y1 - y0}",
                    lambda n: Via(n, layer, h_clg=self.nm, v_clg=self.nm, WidthX=x1 - x0, WidthY=y1 - y0),
                )
                self.addVia(gen, net, (x0 + x1) // 2, (y0 + y1) // 2)
            elif layer in METALS or layer in CUTS:
                # an odd size: on no centre-line grid exactly, the shape as it is
                self.terminals.append({"netName": net, "layer": layer, "rect": [x0, y0, x1, y1], "netType": kind})
            else:
                region = self._generator(f"row_{layer}", lambda n: Region(n, layer, h_grid=self.nm, v_grid=self.nm))
                self.transform_and_add(region.segment(net, x0, y0, x1, y1, netType=kind))


def _line(x0, y0, x1, y1, layer=None):
    """A metal rectangle as a wire: (its layer, its direction, its width, its centre line)."""
    vertical = y1 - y0 >= x1 - x0
    return (
        (layer, "v" if vertical else "h", x1 - x0, (x0 + x1) // 2)
        if vertical
        else (layer, "h", y1 - y0, (y0 + y1) // 2)
    )


def _even(x0, y0, x1, y1):
    """A metal rectangle whose width across is even: a wire on a centre-line grid draws it exactly."""
    return (x1 - x0 if y1 - y0 >= x1 - x0 else y1 - y0) % 2 == 0


def _reach_two_tracks(cell) -> None:
    """Stretch each signal pin bar (M2) over at least two of ALIGN's M3 tracks where the M2 space
    allows: ALIGN's router drops a via only on a track over a pin and never jogs in M2, so a bar
    over one track loses its net when another net's trunk takes that track."""

    pitch = getattr(tech, "M3_PITCH", XPITCH)
    m2 = [r for r in cell.rects if r.layer == "M2"]
    for r in m2:
        if r.kind != "pin" or r.net in (None, "vdd", "vss") or ":" in r.net:
            continue
        lo, hi = -(-(r.x0 + BAR_END) // pitch), (r.x1 - BAR_END) // pitch  # the tracks a via fits on
        for _ in range(2):
            if hi - lo + 1 >= 2:
                break
            others = [
                o for o in m2 if o is not r and o.net != r.net and o.y0 < r.y1 + M2_SPACE and r.y0 < o.y1 + M2_SPACE
            ]
            right = (hi + 1) * pitch + BAR_END
            left = (lo - 1) * pitch - BAR_END
            if right <= cell.width - M2_EDGE and all(
                o.x1 + M2_SPACE <= r.x0 or o.x0 >= right + M2_SPACE for o in others
            ):
                r.x1, hi = right, hi + 1
            elif left >= M2_EDGE and all(o.x0 >= r.x1 + M2_SPACE or o.x1 + M2_SPACE <= left for o in others):
                r.x0, lo = left, lo - 1


def _rows(cell) -> int:
    """The rows a stems cell spans (its boundary)."""
    return max(r.y1 for r in cell.rects if r.layer == "BND") // rowcell.H


class MOSGenerator(RowCanvas):
    """ALIGN's MOS primitive generator (the interface of its mock PDKs' ``MOSGenerator``). ALIGN
    chooses the array, ``x_cells`` units per row and ``y_cells`` rows, and the pattern (single
    device, common centroid, interdigitated, ratio, non common centroid, or the Generator
    constraint's ``exact_patterns``); each unit takes its device as the mock generator's
    ``_addMOSArray`` does. The units' fingers are drawn as stems row cells (``rowcell.mos_grid``),
    one row cell per array row, neighbouring units of a device merged into one run."""

    def __init__(self, pdk, height, fin, gate, gateDummy, shared_diff, stack, bodyswitch, **kwargs):
        self.primitive_parameters = kwargs.get("primitive_parameters") or {}
        self.primitive_constraints = kwargs.get("primitive_constraints", [])
        super().__init__(pdk)
        self.exact_patterns = None
        for const in self.primitive_constraints:
            if const.constraint == "Generator" and (const.parameters or {}).get("exact_patterns"):
                self.exact_patterns = const.parameters["exact_patterns"][0]

    def addNMOSArray(self, x_cells, y_cells, pattern, vt_type, connections, **parameters):
        self._build("n", x_cells, y_cells, pattern, connections)

    def addPMOSArray(self, x_cells, y_cells, pattern, vt_type, connections, **parameters):
        self._build("p", x_cells, y_cells, pattern, connections)

    def _units(self, names, x_cells, y_cells, pattern):
        """The device of each unit, row by row: the mock generator's patterns."""
        size = lambda n: int(self.primitive_parameters[n].get("NF", 1)) * int(self.primitive_parameters[n].get("M", 1))
        if len(names) == 2 and size(names[0]) != size(names[1]):  # a ratio: the mock's current mirror
            pattern = 3
            small = min(size(n) for n in names)
            x_left, x_right = x_cells // 2 - small // 2, x_cells // 2 + small // 2
        elif pattern == 3:  # devices of one size but other parameters (W, L): side by side
            pattern = 4
        if len(names) > 2 and not self.exact_patterns:  # beyond the mock's patterns: each device in turn
            return [[n for n in names for _ in range(max(1, x_cells // len(names)))] for _ in range(y_cells)]
        pick = {
            0: lambda x, y: names[0],
            1: lambda x, y: names[((x // 2) % 2 + x % 2 + (y % 2)) % 2],  # A B B A / B A A B
            2: lambda x, y: names[((x % 2) + (y % 2)) % 2],  # A B A B / B A B A
            3: lambda x, y: names[0 if x_left <= x < x_right else 1],  # B B A A B B
            4: lambda x, y: names[0 if x < x_cells // 2 else 1],  # A A B B
        }
        if self.exact_patterns:
            return [[names[ord(c.upper()) - ord("A")] for c in row] for row in self.exact_patterns]
        return [[pick[pattern](x, y) for x in range(x_cells)] for y in range(y_cells)]

    def _build(self, pol, x_cells, y_cells, pattern, connections):
        devs = sorted({d for conn in connections.values() for d, _ in conn})  # the mock's order: M1, M2, ...
        nets = {dev: {pin: n for n, conn in connections.items() for d, pin in conn if d == dev} for dev in devs}
        nm = lambda v: int(round(float(v) * 1e9 / 5)) * 5
        devices, bulk, ties = [], set(), set()
        for dev in devs:
            par = self.primitive_parameters[dev]
            inst = f"{dev}_X0_Y0"
            self.subinsts[inst].parameters.update(par)
            nf = int(par.get("NF", 1)) * int(par.get("M", 1))
            n = nets[dev]
            devices.append(rowcell.Dev(inst, nm(par["L"]), nm(par["W"]), nf, n["D"], n["G"], n["S"]))
            bulk.add(n["B"])
            # terminals on the other type's rail (make_design.py's far): tied to it inside the cell
            far = int(float(par.get("FAR", 0)))
            ties |= {n[term] for term, bit in (("D", 1), ("G", 2), ("S", 4)) if far & bit}
        assert len(bulk) == 1, f"{devs}: the bulk is the cell's rail, got {bulk}"
        b = bulk.pop()
        rails = dict(vss=b if pol == "n" else None, vdd=b if pol == "p" else None, ties=frozenset(ties))
        units = self._units(devs, x_cells, y_cells, pattern)
        # each device's fingers shared out over its units in order; units left without one are dropped
        count = {d: sum(row.count(d) for row in units) for d in devs}
        given = {d: 0 for d in devs}
        rows = []
        for row in units:
            runs = []
            for d in row:
                k, v = devs.index(d), devices[devs.index(d)]
                nf = v.nf // count[d] + (1 if given[d] < v.nf % count[d] else 0)
                given[d] += 1
                if nf and runs and runs[-1].dev == k:
                    runs[-1] = rowcell.Run(k, runs[-1].nf + nf)
                elif nf:
                    runs.append(rowcell.Run(k, nf))
            if runs:
                rows.append(runs)
        name = devs[0] if len(devs) == 1 else "_".join(devs)
        try:
            cell = rowcell.mos_grid(name, pol, devices, rows, grid=X_GRID, **rails)
        except AssertionError as error:  # the pattern does not fit (tracks, columns): side by side
            logger.warning(f"{name}: {error}; its devices side by side instead")
            folds = len(rows) if all(v.nf % len(rows) == 0 for v in devices) else 1
            try:
                cell = rowcell.mos_rows(name, pol, devices, folds, grid=X_GRID, **rails)
            except AssertionError:  # nor folded over the rows ALIGN asked for: one row
                cell = rowcell.mos_rows(name, pol, devices, 1, grid=X_GRID, **rails)
        _reach_two_tracks(cell)
        self.draw(cell.rects)
        self.bbox = transformation.Rect(0, 0, cell.width, _rows(cell) * rowcell.H)
