"""Finish an ALIGN layout built from row cells (make_pdk.py's PDK directory) for signoff.

* Standard cells: ALIGN placed abstracts named ``<CELL>_<hash>``; the real library cell goes in
  at the wrapper's offset (``paths.ACCESS_JSON``): between the pads the generator drew (free
  placement), or at the right end with the library filler on the left to the placement grid
  (dense wrapper, standard-cell rows). The library's own text labels are dropped (pin names
  would merge nets after flattening), and so are the router's M2 keep-outs the abstract carried;
  the via pads it left out go in (netcells.align_access).
* Rows: ALIGN places cells on the rows but not always abutted. Like a digital flow's filler and
  decap insertion after routing (no cell added to ALIGN's placement), every gap inside the block
  takes decaps first (``_decaps``, ``fillcell``: the PDK's MOS capacitors as row cells, the widest
  that fit where ALIGN's M1 leaves room, each a device the LVS source gets in ``out.gds.extra.sp``,
  each recorded in ``out.gds.post.json``'s fill, ``Fill``), and in what is left plain filler:
  the rails, taps, tap implant bands and the N-tap well band are drawn as in a row cell
  (rowcell.rails without the device parts), so supplies run through every row; the cells' N-wells
  run across a gap where both neighbours have them, and in a gap narrower than the placement grid
  their device implants, Vt layers and gate markers too (``bridge``); then narrow well gaps are
  closed (netcells.close_wells). A gap's rails keep their space from the M1 no row cell draws
  (``_clear_of``); where that cuts a rail between two cells in a PDK whose rails carry no taps,
  an M2 bar joins it again over the cut (``_rail_bridge``). Where ALIGN routes M1 past the
  cells' outline (its routing room), the row ends move out past it (``_row_ends``). A row no
  cell stands in under capacitors is left empty, no rail, tap, row end or supply pad in it: the
  capacitors' own place beside the rows, or, where they stack over the rows, the place the
  converter keeps for its other circuits (``flow.layout.step.free_rows``).
* Supplies: connected by name, never by straps. Each rail line stays a piece of metal of its own,
  run on to the layout's extent at both ends where its M1 is free, each piece a pin with its
  supply's label (``rail_pins``): the converter's power grid joins them at its top level, as a
  macro's power pins, and LVS joins a supply's labelled pieces by name
  (``flow.layout.klayout_lvs``, ``flow.layout.build.route_opens``). A MOM shield tied to a row's
  VSS rail: by a stack of cuts where it lies over the rail, else by a bar on its metal from its
  edge to the nearest VSS line (``shield_ties``). In a PDK whose M1 keeps a wider space beside a
  wide wire, a rail shaved back from ALIGN's M1 (``clear_rails``).
* Landings: a MOM array's plates' stubs below their channels' bars that no route reached removed
  (``idle_landings``), one a plate left where its route came in.
* Islands (PMOS on a bulk of their own in a well of their own, ``rows/wellcell.py``): in a PDK whose
  rails carry no taps, the library's tie cell at both sides of each island cell's VDD lines' rows,
  in the room it keeps there, as at a row end (``well_ties``).
* Keep-outs: the router's, which ALIGN writes as metal, removed (``drop_keepouts``).
* Labels: ALIGN writes the pin labels on the PDK's pin-text layers itself (make_pdk.py's
  LabelLayerNo, honoured by its writers since ALIGN 24656418); pin shapes,
  blockages and abstract layers (datatypes 251/253, layer 255 unless the PDK draws on it, and the PnR's whole-block
  boundary marker 235/5) are removed; shapes are merged and snapped to the manufacturing grid.
* Cuts and pads: a cut where a via layer's shapes make none or several (``single_cuts``), one of
  two cuts of a net closer than their space (``close_cuts``); in a PDK with M2 landing pads
  (``M2_VIA_PAD``) the notches between pads on one M2 polygon filled (``fill_notches``).
* Option (for any block, in a PDK with a guard ring): ``ring`` wraps the block in the PDK's
  guard ring (its ringcell.py), the ring's N-well on ``ring_net``, the substrate ring on
  ``sub_net`` (a port of its own); ``out.gds.extra.sp`` says so for the LVS source
  (``flow.layout.signoff.add_post_devices``).

Run bound to a PDK (flow/layout/pdkproc.py), with ``ROWS_STD_DENSE`` set as for the ALIGN run;
flow/layout/build.py calls ``post``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import fillcell
import klayout.db as kdb
import netcells
import rowcell
from netcells import drop_labels
from paths import ACCESS_JSON, STD_GDS
from tech import (
    BAR_END,
    EDGE_CUTS,
    EDGE_PAD,
    LAYERS,
    M2_SPACE,
    MFG_GRID,
    PIN_TEXT,
    STD_FILL,
    V1_PAIR,
    XPITCH,
)

GRID = MFG_GRID
BND = LAYERS["BND"]
ACCESS = json.loads(ACCESS_JSON.read_text())
# the library cells ALIGN placed as abstracts: every cell with access points (the row cells and
# any other a netlist named), longest name first so no name matches as another's prefix
CELLS = sorted((c for c in ACCESS if c != STD_FILL), key=len, reverse=True)
STD = re.compile(rf"^({'|'.join(re.escape(c) for c in CELLS)})(_\d+)*$", re.IGNORECASE)
LIB_NAME = {c.upper(): c for c in ACCESS}  # ALIGN upper-cases cell names: back to the library's
LIB = str(STD_GDS)


def drop_keepouts(layout: kdb.Layout, primitives: Path) -> int:
    """The router's keep-outs out of ALIGN's GDS, which writes them as metal: each primitive's
    terminals of type ``blockage`` (its ``2_primitives/<NAME>.json``, ``primitives``) erased from its
    cells (``<NAME>_<n>``), shape for shape (a row cell's free track beside a port's pin,
    ``rowcell.inverter``'s ``port``). Returns how many."""
    if not primitives.is_dir():
        return 0
    blocked: dict[str, list[tuple[str, tuple[int, ...]]]] = {}
    for path in primitives.glob("*.json"):
        try:
            terms = json.loads(path.read_text()).get("terminals", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        boxes = [
            (t["layer"], tuple(t["rect"])) for t in terms if t.get("netType") == "blockage" and t.get("layer") in LAYERS
        ]
        if boxes:
            blocked[path.stem.upper()] = boxes
    n = 0
    for cell in layout.each_cell():
        name = re.sub(r"(_\d+)+$", "", cell.name).upper()
        for layer, rect in blocked.get(name, ()):
            shapes = cell.shapes(layout.layer(*LAYERS[layer]))
            for shape in [
                s for s in shapes.each() if s.is_box() and (s.box.left, s.box.bottom, s.box.right, s.box.top) == rect
            ]:
                shapes.erase(shape)
                n += 1
    return n


def insert_stdcells(layout: kdb.Layout, lib_path: str) -> int:
    lib = kdb.Layout()
    lib.read(lib_path)
    copies: dict[str, kdb.Cell] = {}

    def real(name: str) -> kdb.Cell:
        if name not in copies:
            c = layout.create_cell(name + "_lib")
            c.copy_tree(lib.cell(name))
            drop_labels(layout, c)
            copies[name] = c
        return copies[name]

    n = 0
    for cell in list(layout.each_cell()):
        m = STD.match(cell.name)
        if not m or cell.name.endswith("_lib"):
            continue
        name = LIB_NAME[m.group(1).upper()]
        frame = ACCESS[name] if os.environ.get("ROWS_STD_DENSE") else ACCESS[name]["iso"]
        views, keep = netcells.align_access(frame)
        keep = set(keep)  # the router's keep-outs (stdcell.py), not metal
        m2 = cell.shapes(layout.layer(*LAYERS["M2"]))
        for s in [s for s in m2.each() if s.is_box() and (s.box.left, s.box.bottom, s.box.right, s.box.top) in keep]:
            m2.erase(s)
        for pad, bar in views.values():  # the via pads the abstract left out (they would block their bars)
            if pad and bar:
                m2.insert(kdb.Box(*pad))
        if not os.environ.get("ROWS_STD_DENSE"):  # isolated wrapper: pads drawn by the generator (stdcell.py)
            cell.insert(kdb.CellInstArray(real(name).cell_index(), kdb.Trans(ACCESS[name]["iso"]["offset"], 0)))
        else:  # dense: FILL1 on the left
            off = ACCESS[name]["offset"]
            cell.insert(kdb.CellInstArray(real(name).cell_index(), kdb.Trans(off, 0)))
            for x0, x1 in ((0, off), (off + ACCESS[name]["width"], ACCESS[name]["padded"])):  # fillers both sides
                x = x0
                for fill, w in netcells.fillers(x1 - x0):
                    cell.insert(kdb.CellInstArray(real(fill).cell_index(), kdb.Trans(x, 0)))
                    x += w
        n += 1
    return n


# an island cell's name: ALIGN's for the subcircuit ``flow.circuit.netlists._wells`` makes of the
# PMOS on a bulk of their own (``<module>_well_<bulk>``, upper case, its own suffix)
WELL = re.compile(r"_WELL_", re.IGNORECASE)


def well_ties(layout: kdb.Layout, lib_path: str) -> int:
    """For a PDK whose rails carry no taps (``wellcell.TIE``): the library's tie cell at the tie
    sites of every island cell (``wellcell.tie_sites``: both sides of the row under each of its VDD
    lines), where its island cuts the rows' wells as a row end does. Returns the ties inserted."""
    import wellcell

    if not wellcell.TIE:
        return 0
    lib = kdb.Layout()
    lib.read(lib_path)
    n = 0
    for cell in list(layout.each_cell()):
        if not WELL.search(cell.name) or cell.name.endswith("_lib"):
            continue
        outline = kdb.Region(cell.shapes(layout.layer(*BND))).bbox()
        if outline.empty():
            continue
        tie = netcells._lib_cell(layout, kdb, lib, wellcell.TIE[0])
        for x, y, mirror in wellcell.tie_sites(outline.width(), outline.height() // rowcell.H):
            at = (outline.left + x, outline.bottom + y)
            cell.insert(
                kdb.CellInstArray(tie.cell_index(), kdb.Trans(kdb.Trans.M90, *at) if mirror else kdb.Trans(*at))
            )
            n += 1
    return n


def _lib_cell(lib_path: str, name: str) -> kdb.Cell:
    lib = kdb.Layout()
    lib.read(lib_path)
    c = lib.cell(name)
    drop_labels(lib, c)
    _lib_cell.keep = lib  # the cell lives in this layout
    return c


@dataclass
class Fill:
    """What ``fill_rows`` put in the rows' empty sites: the decaps (``fillcell.Placed``), each
    stretch of plain filler (its width, nm), the rows left empty (no cell in them, under MOM
    units: the capacitors' own, or where they stack over the rows the converter's other
    circuits'), and the gaps not a whole row tall (each its box), left as they are."""

    decaps: list = field(default_factory=list)
    plain: list[int] = field(default_factory=list)
    reserved: set[int] = field(default_factory=set)
    short: list[tuple[int, int, int, int]] = field(default_factory=list)

    def record(self) -> dict:
        """The fill as post.json records it: counts, gate area (um^2) and capacitance (fF) of the
        decaps, the filler's sites (``XPITCH``) and width, the rows left empty."""
        return {
            "decaps": len(self.decaps),
            "decap fingers": sum(d.nf for d in self.decaps),
            "decap gate um2": round(sum(fillcell.gate_um2(d.pol, d.nf) for d in self.decaps), 3),
            "decap ff": round(sum(fillcell.capacitance_ff(d.pol, d.nf) for d in self.decaps), 2),
            "decap nmos": sum(d.pol == "n" for d in self.decaps),
            "decap pmos": sum(d.pol == "p" for d in self.decaps),
            "filler stretches": len(self.plain),
            "filler sites": sum(self.plain) // XPITCH,
            "filler um": round(sum(self.plain) / 1000, 3),
            "rows left empty": sorted(self.reserved),
            "gaps under a row's height": len(self.short),
        }


def _decaps(
    layout: kdb.Layout,
    top: kdb.Cell,
    g: kdb.Box,
    k: int,
    routed: kdb.Region,
    pp: kdb.Region,
    box: kdb.Box,
    cells: dict[tuple[str, int], kdb.Cell],
    fill: Fill,
    near: kdb.Region | None = None,
) -> list[kdb.Box]:
    """Decaps (``fillcell``) in the gap ``g`` of row ``k``: in each stretch of it ALIGN's M1
    (``routed``: another net's) keeps clear of by M1's space beside a rail (a decap's rails and
    strips span the row), on the cell grid, the widest that fit side by side from its left end
    (``fillcell.pack``), of the type of the cell beside the gap (its P+ implant, ``pp``, over a
    PMOS cell's device band, a PMOS; else an NMOS; the cell on its left, or at the rows' left end ``box`` the one on its right),
    so the row's bands run on. Returns what is left of the gap (each a box):
    plain filler's. ``near``: where the kit's rails carry no taps, the stretch of the row within its
    tie cells' reach (``_tied``), the only place a decap's devices may stand."""
    space = _rail_space()
    blocked = kdb.Region(
        [kdb.Box(b.left - space, g.bottom, b.right + space, g.top) for b in (p.bbox() for p in routed.each())]
    )
    free = (kdb.Region(g) - blocked).merged()
    if near is not None:
        free = (free & near).merged()
    # a PMOS cell's device implant's middle in the row's frame (R0 on even rows, mirrored on odd ones)
    lo, hi = rowcell.DEV_IMP["p"]
    mid = (lo + hi) // 2
    y_p = g.bottom + mid if k % 2 == 0 else g.top - mid

    def pmos_at(x: int) -> bool:
        return not (pp & kdb.Region(kdb.Box(x - 1, y_p - 1, x + 1, y_p + 1))).is_empty()

    # the cell on the left, else (the rows' end there) the one on the right
    beside = g.right + 1 if g.left <= box.left else g.left - 1
    pol = "p" if pmos_at(beside) else "n"
    drawn: list[kdb.Box] = []
    for piece in free.each():
        b = piece.bbox()
        x0 = -(-b.left // XPITCH) * XPITCH
        x1 = b.right // XPITCH * XPITCH
        x = x0
        for nf in fillcell.pack(pol, x1 - x0):
            if (pol, nf) not in cells:
                cells[pol, nf] = netcells.draw(layout, kdb, fillcell.decap(pol, nf))
            w = fillcell.width(pol, nf)
            t = kdb.Trans(x, g.bottom) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, x, g.top)
            top.insert(kdb.CellInstArray(cells[pol, nf].cell_index(), t))
            fill.decaps.append(fillcell.Placed(pol, nf, x, g.bottom, k))
            drawn.append(kdb.Box(x, g.bottom, x + w, g.top))
            x += w
    return [p.bbox() for p in (kdb.Region(g) - kdb.Region(drawn)).merged().each()]


def _tied(ties: list[kdb.Box], box: kdb.Box, k: int) -> kdb.Region:
    """Row ``k``'s stretch within its tie cells' reach (``TIE_REACH``, a PDK whose rails carry no
    taps): of the ties ALIGN placed in it (``ties``) and of those at its ends (``edge_ties``, just
    past the rows' extent ``box``)."""
    reach = getattr(netcells._tech, "TIE_REACH", 0)
    y0, y1 = k * rowcell.H, (k + 1) * rowcell.H
    spans = [(box.left, box.left), (box.right, box.right)]
    spans += [(t.left, t.right) for t in ties if t.bottom < y1 and t.top > y0]
    return kdb.Region([kdb.Box(lo - reach, y0, hi + reach, y1) for lo, hi in spans]).merged()


def fill_rows(
    layout: kdb.Layout,
    top: kdb.Cell,
    std_rows: set[int],
    fills: dict[str, kdb.Cell],
    filled: list[kdb.Box] | None = None,
    box: kdb.Box | None = None,
    ends: bool = False,
    routes: kdb.Region | None = None,
    shield: kdb.Region | None = None,
    wires: kdb.Region | None = None,
    capacitors: kdb.Region | None = None,
    fill: Fill | None = None,
    ties: list[kdb.Box] | None = None,
) -> int:
    """Decaps where they fit (``_decaps``), rails, taps and well band across the rest of the
    placement gaps of every row; library fillers in standard-cell rows (their implant bands differ
    from the analog rows'). ``filled`` collects the analog rows' plain stretches (``bridge``);
    ``fill``, where given, gets what was drawn, and only then are decaps drawn. ``box``: the rows'
    extent (the cells' outline unless given:
    ``_row_ends``); ``ends``: row-end cells will stand at its sides (``edge_ties``). Where ALIGN
    routed M1 through a gap (no cell is there, so it is another net's), the fill's M1 and contacts
    keep M1's space from it (``_clear_of``), and from the M1 no row cell draws (``routes``: ALIGN's,
    the MOM units' landings) ending in the next row within that space of the rail they share.
    ``shield``: the MOM shields on M2 (VSS), which a VSS rail's bridge may meet; ``wires``: ALIGN's
    M2 (``_rail_bridge``). A row no cell stands in under MOM units (``capacitors``: their shields)
    is no row: left to the capacitors beside the rows, or, where they stack over the rows, to the
    converter's other circuits (``flow.layout.step.free_rows``), no rail across it."""
    bnd = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged()
    box = box or bnd.bbox()
    m1 = kdb.Region(top.begin_shapes_rec(layout.layer(*rowcell.GLAYERS["M1"])))
    pp = kdb.Region(top.begin_shapes_rec(layout.layer(*rowcell.GLAYERS["PP"]))).merged()
    decaps: dict[tuple[str, int], kdb.Cell] = {}
    # a rail ALIGN's M1 cuts in two between cells is joined again over it (``_rail_bridge``) where
    # the rails carry no taps: no well or substrate tie joins its pieces either
    jumps = None
    if not rowcell.RAIL_TAPS:
        jumps = {name: kdb.Region(top.begin_shapes_rec(layout.layer(*LAYERS[name]))) for name in ("M2", "V1")}
        jumps["shield"] = shield if shield is not None else kdb.Region()
        jumps["wires"] = wires if wires is not None else kdb.Region()
    n = 0
    for k in range(box.bottom // rowcell.H, -(-box.top // rowcell.H)):
        y0 = k * rowcell.H
        band = kdb.Region(kdb.Box(box.left, y0, box.right, y0 + rowcell.H))
        if capacitors is not None and (band & bnd).is_empty() and not (band & capacitors).is_empty():
            if fill is not None:
                fill.reserved.add(k)
            continue
        gaps = (band - bnd).merged()
        for gap in gaps.each():
            g = gap.bbox()
            if g.height() < rowcell.H:
                if fill is not None:
                    fill.short.append((g.left, g.bottom, g.right, g.top))
                continue
            routed = _routed(m1, routes, g)
            if k in std_rows:
                x = g.left
                try:
                    fillers = netcells.fillers(g.width())
                except ValueError:  # narrower than the library's fillers (ALIGN places on a finer grid)
                    pad = netcells.std_fill(g.width())  # the standard cells' profile, as at a row end
                    rowcell.std_pad(pad, 0, g.width(), "left")
                    t = kdb.Trans(x, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, x, y0 + rowcell.H)
                    boxes = [
                        (r.layer, kdb.Box(r.x0, r.y0, r.x1, r.y1).transformed(t))
                        for r in pad.rects
                        if r.layer != "BND" and r.kind != "stub" and rowcell.GLAYERS.get(r.layer)
                    ]
                    for layer, b in _clear_of(boxes, routed, g, _bare(g, box, ends)):
                        top.shapes(layout.layer(*rowcell.GLAYERS[layer])).insert(b)
                    fillers = []
                for name, w in fillers:
                    t = kdb.Trans(x, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, x, y0 + rowcell.H)
                    top.insert(kdb.CellInstArray(fills[name].cell_index(), t))
                    x += w
                n += 1
                continue
            near = _tied(ties, box, k) if ties is not None else None
            pieces = _decaps(layout, top, g, k, routed, pp, box, decaps, fill, near) if fill is not None else [g]
            for piece in pieces:
                _plain(layout, top, piece, k, _routed(m1, routes, piece), box, ends, jumps)
                if fill is not None:
                    fill.plain.append(piece.width())
                if filled is not None:
                    filled.append(piece)
            n += 1
    return n


def _routed(m1: kdb.Region, routes: kdb.Region | None, g: kdb.Box) -> kdb.Region:
    """ALIGN's M1 through the gap ``g``: what reaches inside it past the rails (the rows beside it
    reach into it with their rails' halves alone), and the M1 no row cell draws (``routes``)
    within M1's space beside a rail of the rails it shares with the rows next to it."""
    inside = kdb.Region(kdb.Box(g.left, g.bottom + rowcell.RAIL + 1, g.right, g.top - rowcell.RAIL - 1))
    routed = m1.interacting(inside)
    if routes is not None:
        reach = _rail_space() + rowcell.RAIL
        routed = (routed + (routes & kdb.Region(g.enlarged(0, reach)))).merged()
    return routed


def _plain(
    layout: kdb.Layout,
    top: kdb.Cell,
    g: kdb.Box,
    k: int,
    routed: kdb.Region,
    box: kdb.Box,
    ends: bool,
    jumps: dict[str, kdb.Region] | None,
) -> None:
    """Plain filler across the stretch ``g`` of row ``k``: the rails, taps, tap implant bands and
    N-tap well band (``rowcell.rails`` without the device parts), clear of ALIGN's M1 (``routed``,
    ``_clear_of``), a rail it cuts joined over it in M2 (``_rail_bridge``, ``jumps``)."""
    # orientation: VSS on even rail lines (cells placed R0 on even rows, MX on odd ones)
    t = kdb.Trans(g.left, g.bottom) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, g.left, g.bottom + rowcell.H)
    cell = rowcell.Cell("fill", g.width())
    rowcell.rails(cell, g.width(), "n", m2=False)
    boxes = []
    for r in cell.rects:
        if (
            r.layer in ("BND", *rowcell.VT["n"], *rowcell.VT["p"])
            or r.kind == "stub"
            or not rowcell.GLAYERS.get(r.layer)
        ):
            continue
        if r.layer in ("NP", "PP") and (r.y0, r.y1) == rowcell.DEV_IMP["n"]:
            continue  # no device implant in a gap
        boxes.append((r.layer, kdb.Box(r.x0, r.y0, r.x1, r.y1).transformed(t)))
    kept = _clear_of(boxes, routed, g, _bare(g, box, ends))
    for layer, b in kept:
        top.shapes(layout.layer(*rowcell.GLAYERS[layer])).insert(b)
    joined = (ends or box.left < g.left) and (ends or g.right < box.right)  # a rail at both sides
    if jumps is not None and not routed.is_empty() and joined:
        pieces = kdb.Region([b for layer, b in kept if layer == "M1"])
        for y in (g.bottom, g.top):
            _rail_bridge(layout, top, pieces, g, y, jumps)


def _rail_bridge(
    layout: kdb.Layout, top: kdb.Cell, pieces: kdb.Region, gap: kdb.Box, y: int, jumps: dict[str, kdb.Region]
) -> bool:
    """Join a rail line ``y`` that ALIGN's M1 cuts in a row gap between two cells: from the piece
    of the gap's fill (``pieces``) at its left side to the one at its right, a VIA1 on each, by
    their M1's line-end enclosure, and an M2 bar between, M2's minimum length at least, where the
    bar keeps M2's space and the cuts VIA1's from other shapes (``jumps``: M2 and V1, the drawn
    added; on a VSS line a MOM shield on M2, VSS too, it may run into); between two cells' M2
    rails, the bar alone, joining them. Whether it was drawn."""
    import tech as _tech

    line = pieces & kdb.Region(kdb.Box(gap.left, y - rowcell.RAIL, gap.right, y + rowcell.RAIL))
    left = line.interacting(kdb.Region(kdb.Box(gap.left, y - 1, gap.left + 1, y + 1)))
    right = line.interacting(kdb.Region(kdb.Box(gap.right - 1, y - 1, gap.right, y + 1)))
    if left.is_empty() or right.is_empty() or not (left & right).is_empty():
        return False  # cut off at a side, or one piece
    rule = _tech.RULES["V1"]
    half, end = rule["cut"] // 2, rule["enclosure"][0]
    xl, xr = left.bbox().right - end - half, right.bbox().left + end + half
    reach = max(BAR_END, (getattr(_tech, "M2_MIN_LEN", 0) - (xr - xl)) // 2 + 1)
    bar = kdb.Box(xl - reach, y - _tech.M2W // 2, xr + reach, y + _tech.M2W // 2)
    cuts = [kdb.Box(x - half, y - half, x + half, y + half) for x in (xl, xr)]
    ends = getattr(_tech, "M2_LINE_END", M2_SPACE)  # its ends from other M2 along its track
    # the rows' own M2 on the rail's line is the rail's (an M2 rail over it, rowcell): ALIGN's wires
    # and every other shape are others
    track = kdb.Region(kdb.Box(bar.left - M2_SPACE, y - rowcell.M2_HW, bar.right + M2_SPACE, y + rowcell.M2_HW))
    # the M2 round the bar alone (the whole layout's is large)
    window = kdb.Region(bar.enlarged(2 * (ends + M2_SPACE), 2 * (ends + M2_SPACE)))
    local = jumps["M2"] & window
    others = local - ((local & track) - (jumps["wires"] & window))
    if (y // rowcell.H) % 2 == 0 and not jumps["shield"].is_empty():
        # a shield closer than M2's space: the bar runs on into it, the gap between them filled
        others -= jumps["shield"]
        near = jumps["shield"] & kdb.Region(bar.enlarged(0, M2_SPACE))
        if not near.is_empty():
            reach_to = near.bbox()
            if reach_to.top <= bar.bottom:
                bar = kdb.Box(bar.left, reach_to.top, bar.right, bar.top)
            elif reach_to.bottom >= bar.top:
                bar = kdb.Box(bar.left, bar.bottom, bar.right, reach_to.bottom)
    # cells with M2 rails on both sides (rowcell): the bar joins those, no cut of its own
    rails = (local & track) - (jumps["wires"] & window)
    if all(not (rails & kdb.Region(kdb.Box(x - 1, y - 1, x + 1, y + 1))).is_empty() for x in (gap.left, gap.right)):
        cuts = []
    # a kit whose M2 encloses a VIA1 wider than its wire: a landing pad round each cut (M2_VIA_PAD)
    pad_x, pad_y = getattr(_tech, "M2_VIA_PAD", {}).get("V1", (0, 0))
    pads = [kdb.Box(c.center().x - pad_x, y - pad_y, c.center().x + pad_x, y + pad_y) for c in cuts if pad_y]
    drawn = kdb.Region([bar, *pads])
    if not (others & drawn.sized(ends, M2_SPACE, 2)).is_empty():
        return False
    if not (jumps["V1"] & kdb.Region(cuts).sized(rule["space"])).is_empty():
        return False
    top.shapes(layout.layer(*LAYERS["M2"])).insert(drawn)
    jumps["M2"].insert(drawn)
    if not jumps["shield"].is_empty() and (y // rowcell.H) % 2 == 0:
        # a gap narrower than M2's space between the bar or its cuts' pads and a shield (VSS both)
        # filled (SKY130's pads stood 0.1 um from its shield's M2 beside a bar that ran into it)
        reach = drawn.bbox().enlarged(M2_SPACE, M2_SPACE)
        near = jumps["shield"] & kdb.Region(reach)
        if not near.is_empty():
            both = (drawn + near).merged()
            half = (M2_SPACE - 1) // 2
            fill = (both.sized(half).sized(-half) - both) & kdb.Region(reach)
            fill = fill.interacting(drawn)
            if not fill.is_empty():
                top.shapes(layout.layer(*LAYERS["M2"])).insert(fill)
                jumps["M2"].insert(fill)
    for cut in cuts:
        top.shapes(layout.layer(*LAYERS["V1"])).insert(cut)
        jumps["V1"].insert(cut)
    return True


def _bare(gap: kdb.Box, box: kdb.Box, ends: bool) -> kdb.Region:
    """The sides of a row gap at the rows' bare outline ``box`` (no row-end cell beside it, ``ends``
    False): no rail there for the gap's rails to join."""
    sides = kdb.Region()
    for x, outline in ((gap.left, box.left), (gap.right, box.right)):
        if not ends and x == outline:
            sides.insert(kdb.Box(x - (x == gap.right), gap.bottom, x + (x == gap.left), gap.top))
    return sides


def _rail_space() -> int:
    """M1's space beside a rail: a wide metal's where the PDK gives one (``RULES`` M1
    ``parallel_space``: space, above width, above parallel run length) for a wire as wide as the
    rail facing it along the rail's width."""
    import tech as _tech

    wide = 2 * rowcell.RAIL
    rule = getattr(_tech, "RULES", {}).get("M1", {})
    return max(
        [_tech.M1_SPACE, *(gap for gap, width, run in rule.get("parallel_space", ()) if wide > width and wide > run)]
    )


def _clear_of(
    boxes: list[tuple[str, kdb.Box]], routed: kdb.Region, gap: kdb.Box, bare: kdb.Region | None = None
) -> list:
    """A gap fill's shapes (layer, box) clear of ``routed``, the M1 ALIGN drew through the gap
    (another net's): its M1 cut back to M1's space beside a rail from it (``_rail_space``), across
    the rail's whole width where it would leave a strip narrower than M1's width (cuts nearer
    each other than that joined), of the
    pieces left only those reaching the gap's sides (joined to the rails beside it), at its
    ``bare`` sides (``_bare``) only those meeting M1's width and area alone, a contact only inside
    such a piece by its line-end enclosure and a rail's tap diffusion only under one, holding a
    contact; every other layer as it is. The shapes unchanged where nothing is routed through the gap."""
    if routed.is_empty():
        return boxes
    import tech as _tech

    end = getattr(_tech, "M1_CO_END", 0)
    rule = getattr(_tech, "RULES", {}).get("M1", {})
    narrow = rule.get("width", 0)
    blocked = routed.sized(_rail_space())
    m1 = kdb.Region()
    for layer, rail in boxes:
        if layer != "M1":
            continue
        # each cut through the rail's whole width where what it leaves beside it is narrower than
        # M1's width
        cuts = kdb.Region()
        for piece in (blocked & kdb.Region(rail)).merged().each():
            c = piece.bbox()
            lo = rail.bottom if c.bottom - rail.bottom < narrow else c.bottom
            hi = rail.top if rail.top - c.top < narrow else c.top
            cuts.insert(kdb.Box(c.left, lo, c.right, hi))
        half = (narrow - 1) // 2  # cuts nearer each other than M1's width close up: no sliver between
        m1 += kdb.Region(rail) - cuts.merged().sized(half).sized(-half)
    m1.merge()
    sides = kdb.Region(kdb.Box(gap.left, gap.bottom, gap.left + 1, gap.top)) + kdb.Region(
        kdb.Box(gap.right - 1, gap.bottom, gap.right, gap.top)
    )
    m1 = m1.interacting(sides)
    if bare is not None and not bare.is_empty():
        joined = m1.interacting(sides - bare)
        small = [
            p for p in (m1 - joined).each() if p.bbox().width() < rule.get("width", 0) or p.area() < rule.get("area", 0)
        ]
        m1 -= kdb.Region(small)
    kept = [(layer, b) for layer, b in boxes if layer not in ("M1", "CO", "OD")]
    kept += [("M1", p) for p in m1.each()]
    cos = [b for layer, b in boxes if layer == "CO" and (kdb.Region(b.enlarged(end, 0)) - m1).is_empty()]
    kept += [("CO", b) for b in cos]
    # a rail's tap diffusion only under the rail's pieces kept, and only where it keeps a contact:
    # no tap left without its contacts
    for layer, b in boxes:
        if layer == "OD":
            line = round(b.center().y / rowcell.H) * rowcell.H
            under = m1 & kdb.Region(kdb.Box(b.left, line - rowcell.RAIL, b.right, line + rowcell.RAIL))
            spans = kdb.Region([kdb.Box(p.bbox().left, b.bottom, p.bbox().right, b.top) for p in under.each()])
            taps = (spans & kdb.Region(b)).merged()
            if rowcell.RAIL_TAPS:  # rails with taps: no diffusion left without its contacts
                taps = taps.interacting(kdb.Region(cos))
            kept += [("OD", p) for p in taps.each()]
    return kept


def bridge(layout: kdb.Layout, top: kdb.Cell, g: kdb.Box, block: kdb.Box) -> None:
    """Draw the N-well across the gap ``g`` where the cells on both sides (the row-end cells too)
    carry it at the same height, and in a row's end gap (at the ``block`` outline) as far as its
    one cell carries it (a PMOS cell's well, not only the tap band: no notches between the rows'
    wells); in a column the placement grid left over (narrower than the grid) each device
    implant, Vt layer and gate marker as well (their space rules are wider)."""
    names = {"NW"}
    if g.width() < 2 * XPITCH:
        marks = (rowcell.GATE_MARK["layer"],) if rowcell.GATE_MARK else ()
        names |= {"NP", "PP", *rowcell.VT["n"], *rowcell.VT["p"], *marks}
    for name in names:
        if not rowcell.GLAYERS.get(name):
            continue
        li = layout.layer(*rowcell.GLAYERS[name])
        shapes = kdb.Region(top.begin_shapes_rec(li))
        left, right = (
            [p.bbox() for p in (shapes & kdb.Region(kdb.Box(x - 1, g.bottom, x + 1, g.top))).merged().each()]
            for x in (g.left, g.right)
        )
        if name == "NW" and g.left <= block.left:
            left = right
        elif name == "NW" and g.right >= block.right:
            right = left
        for a in left:
            for b in right:
                lo, hi = max(a.bottom, b.bottom), min(a.top, b.top)
                if lo < hi:
                    top.shapes(li).insert(kdb.Box(g.left, lo, g.right, hi))


def row_ends() -> bool:
    """Whether the PDK puts cells at both ends of every row (``edge_ties``)."""
    return bool(netcells.EDGE_TIE or getattr(netcells._tech, "ALIGN_ROW_ENDS", False))


def _row_ends(block: kdb.Box, routes: kdb.Region, wires: kdb.Region | None = None) -> kdb.Box:
    """The rows' extent in a PDK with row-end cells (``row_ends``): the cells' outline ``block``,
    widened on the placement grid at a side where ALIGN routed M1 past it (its routing room at the
    outline, ``Boundary``) until a row-end cell there keeps M1's space beside a rail from that M1,
    and its M2 (the supply stacks' pads, netcells.edge) M2's from ALIGN's M2 (``wires``); the gaps
    between are filled as any row's (``fill_rows``)."""
    w, space = netcells.EDGE_W, _rail_space()
    left, right = block.left, block.right
    rows = (block.bottom - rowcell.RAIL, block.top + rowcell.RAIL)
    lines = range(block.bottom // rowcell.H, block.top // rowcell.H + 1)

    def zone(x0: int, x1: int, edge: int, inward: int) -> kdb.Region:
        """A row-end cell's footprint from ``x0`` to ``x1`` and its space, and its rails' ends
        at ``edge`` with the space beyond them, ``inward``."""
        a, b = sorted((edge, edge + inward * space))
        ends = [
            kdb.Box(a, k * rowcell.H - rowcell.RAIL - space, b, k * rowcell.H + rowcell.RAIL + space) for k in lines
        ]
        return kdb.Region(kdb.Box(x0, rows[0], x1, rows[1])) + kdb.Region(ends)

    while True:
        hit = routes & zone(left - w - space, left, left, +1)
        if wires is not None:
            hit += wires & kdb.Region(kdb.Box(left - w - M2_SPACE, rows[0], left, rows[1]))
        if hit.is_empty():
            break
        left = min(left - XPITCH, (hit.bbox().left - space) // XPITCH * XPITCH)
    while True:
        hit = routes & zone(right, right + w + space, right, -1)
        if wires is not None:
            hit += wires & kdb.Region(kdb.Box(right, rows[0], right + w + M2_SPACE, rows[1]))
        if hit.is_empty():
            break
        right = max(right + XPITCH, -(-(hit.bbox().right + space) // XPITCH) * XPITCH)
    return kdb.Box(left, block.bottom, right, block.top)


def cut_poly_bridges(layout: kdb.Layout, top: kdb.Cell) -> int:
    """Where the kit's rails carry a cut poly (``RAIL_POLY_CUT``, the library's over each rail), the
    gaps along a rail narrower than the cut's spacing (its ``space``) closed: a row cell's cut and a
    library cell's beside it (a tie cell ALIGN abutted to a driver) meet as two library cells'
    do. Returns how many."""
    cut = rowcell.RAIL_POLY_CUT
    if not cut or not cut.get("space") or "CPO" not in LAYERS:
        return 0
    layer = layout.layer(*LAYERS["CPO"])
    region = kdb.Region(top.shapes(layer)).merged()
    if region.is_empty():
        return 0
    box, n = region.bbox(), 0
    for k in range(box.bottom // rowcell.H, box.top // rowcell.H + 1):
        y0, y1 = k * rowcell.H - cut["half"], k * rowcell.H + cut["half"]
        line = sorted(
            (b.left, b.right)
            for b in (p.bbox() for p in (region & kdb.Region(kdb.Box(box.left, y0, box.right, y1))).each())
            if b.bottom <= y0 and b.top >= y1
        )
        for (_, right), (left, _) in pairwise(line):
            if 0 < left - right < cut["space"]:
                top.shapes(layer).insert(kdb.Box(right, y0, left, y1))
                n += 1
    return n


def edge_ties(
    layout: kdb.Layout,
    top: kdb.Cell,
    std_rows: set[int],
    std_lib,
    box: kdb.Box | None = None,
    empty: set[int] | None = None,
) -> int:
    """For a PDK whose rails carry no taps (netcells.EDGE_TIE): its row-end cells (the library tie
    cell, then library fillers or a pad with the standard cells' profile) at both ends of every
    row, outside the rows' extent ``box`` (the block's outline unless given, ``_row_ends``),
    mirrored like the row (VSS on even rail lines). A PDK with ALIGN_ROW_ENDS (where a generated
    P-well past a PMOS cell at the block side would be too narrow) gets row fillers there instead
    (netcells.filler, library fillers on standard-cell rows). The rows left empty (``empty``,
    ``Fill.reserved``) get none."""
    ends = getattr(netcells._tech, "ALIGN_ROW_ENDS", False)
    if not (netcells.EDGE_TIE or ends):
        return 0
    b = box or kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged().bbox()
    w = netcells.EDGE_W
    make = (
        (lambda std: netcells.edge(std=std))
        if netcells.EDGE_TIE
        else (lambda std: (netcells.std_fill if std else netcells.filler)(w))
    )
    cells = {std: netcells.draw(layout, kdb, make(std), std_lib=std_lib) for std in (False, True)}
    n = 0
    for k in range(b.bottom // rowcell.H, -(-b.top // rowcell.H)):
        if empty and k in empty:
            continue
        cell = cells[k in std_rows]
        y0 = k * rowcell.H
        for x, mirror in ((b.left - w, False), (b.right + w, True)):  # the tie at the block's outer side
            t = kdb.Trans(kdb.Trans.M90, x, 0) if mirror else kdb.Trans(x, 0)
            row = kdb.Trans(0, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, 0, y0 + rowcell.H)
            top.insert(kdb.CellInstArray(cell.cell_index(), row * t))
            n += 1
    return n


def _row_groups(layout: kdb.Layout, top: kdb.Cell) -> list[list[int]]:
    """The block's groups of consecutive rows with cells (more than their row-end cells), each its
    rows' indices: one group but where rows without cells (capacitors) lie between."""
    bnd = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged()
    b = bnd.bbox()
    end = netcells.EDGE_W + 1 if row_ends() else 0
    rows = [
        k
        for k in range(b.bottom // rowcell.H, b.top // rowcell.H)
        if not (
            bnd & kdb.Region(kdb.Box(b.left + end, k * rowcell.H + 1, b.right - end, (k + 1) * rowcell.H - 1))
        ).is_empty()
    ]
    groups: list[list[int]] = []
    for k in rows:
        if groups and groups[-1][-1] == k - 1:
            groups[-1].append(k)
        else:
            groups.append([k])
    return groups


def _rows_apart(layout: kdb.Layout, top: kdb.Cell, shields: list[tuple[int, kdb.Region]]) -> bool:
    """Whether the block's rows stand apart from its capacitors (``shields``, ``mom_shields``, each
    on the metal below its plates): in groups with capacitors between them, or beside capacitors
    whose plates take M3, which then cannot stand over the rows. ALIGN's routing room lies past
    the rows' ends (``_row_ends``)."""
    return len(_row_groups(layout, top)) > 1 or any(metal + 1 <= 3 for metal, _region in shields)


def _unit_layers(cell_name: str, units: dict[str, int]) -> int | None:
    """The plate metals of a MOM unit's cell (``units``: each unit's primitive, upper case, to its
    ``layers``; ALIGN names a cell after its primitive, ``<NAME>_<n>...``); None for another cell."""
    name = cell_name.upper()
    found = [unit for unit in units if name == unit or name.startswith(f"{unit}_")]
    return units[max(found, key=len)] if found else None  # the longest: fmomcap_2f44_1 before fmomcap_2f4


def mom_shields(layout: kdb.Layout, top: kdb.Cell, units: dict[str, int]) -> list[tuple[int, kdb.Region]]:
    """Before flattening: the shields of the MOM array units placed in ``top`` (``units``: each
    unit's primitive to its plate metals, ALIGN's record of them, ``flow.layout.build._mom_units``), each on the
    metal below their plates: its shapes there that no cut up joins to a plate (a channel's bar is
    a plate's), merged, one polygon to an array of abutting units."""
    import tech as _tech

    cells: dict[int, list[int]] = {}
    for cell in layout.each_cell():
        layers = _unit_layers(cell.name, units)
        if layers:
            cells.setdefault(_tech.MOM_LAYERS[-layers] - 1, []).append(cell.cell_index())

    def gather(name: str, within: list[int]) -> kdb.Region:
        it = top.begin_shapes_rec(layout.layer(*LAYERS[name]))
        it.unselect_all_cells()
        it.select_cells(within)
        return kdb.Region(it).merged()

    return [(metal, gather(f"M{metal}", ids).not_interacting(gather(f"V{metal}", ids))) for metal, ids in cells.items()]


def idle_landings(layout: kdb.Layout, top: kdb.Cell, units: dict[str, int]) -> tuple[int, dict[str, kdb.Region]]:
    """Before flattening: the MOM array units' landings (``units``, as ``mom_shields``; each plate's
    stub on the metal below its channel's bar, ``MomUnit._landing``) that no route of ALIGN's
    reaches: none of its wires on the stub's metal touches it, none of its cuts from the metal below
    lands on it. Like a digital flow's unused pin access, they are dead metal under the array, which
    the converter's own rows and routes there would take: the landings drawn, and by layer the idle
    stubs and their cuts up to the bars, to be removed once the layout is flat (``post``)."""
    import tech as _tech

    by_metal: dict[int, list[int]] = {}
    for cell in layout.each_cell():
        layers = _unit_layers(cell.name, units)
        if layers:
            by_metal.setdefault(_tech.MOM_LAYERS[-layers] - 2, []).append(cell.cell_index())

    def within(name: str, ids: list[int]) -> kdb.Region:
        it = top.begin_shapes_rec(layout.layer(*LAYERS[name]))
        it.unselect_all_cells()
        it.select_cells(ids)
        return kdb.Region(it).merged()

    drawn, idle = 0, {}
    for metal, ids in by_metal.items():
        if metal < 1:
            continue
        stubs = within(f"M{metal}", ids)
        drawn += stubs.count()
        routes = kdb.Region(top.shapes(layout.layer(*LAYERS[f"M{metal}"])))
        if metal > 1:
            routes += kdb.Region(top.shapes(layout.layer(*LAYERS[f"V{metal - 1}"])))
        unused = stubs.not_interacting(routes)
        if not unused.is_empty():
            idle[f"M{metal}"] = idle.get(f"M{metal}", kdb.Region()) + unused
            idle[f"V{metal}"] = idle.get(f"V{metal}", kdb.Region()) + within(f"V{metal}", ids).interacting(unused)
    return drawn, idle


def shield_ties(
    layout: kdb.Layout,
    top: kdb.Cell,
    shields: list[tuple[int, kdb.Region]],
    per_shield: int = 2,
    routes: kdb.Region | None = None,
    wires: kdb.Region | None = None,
) -> int:
    """Tie each MOM shield (``mom_shields``) to a row's VSS rail, ``per_shield`` ties a shield.
    Where it lies over the rail (capacitors stacked over the rows): a stack of cuts from the rail up
    to the shield, a pad on every metal between, on the M3 grid, from its lower left. Where it lies
    beside the rows (between or beside their bands): a bar on the shield's metal from its edge to
    the nearest VSS rail line above or below it that the bar reaches past the lines between (an
    M1 shield joins the rail itself, so no VDD line between), the stack of cuts from the rail up to
    the bar's end (an M2 pad there), from the shield's ends inward. Every pad and bar keeps its
    metal's space from other metal (ALIGN's M2, ``wires``, never the rail's own) and every cut its
    cut space; ``routes``: ALIGN's own M1, which crosses a rail's line in a row gap and is no rail.
    No tie reaches past the layout's extent. Returns the ties drawn."""
    import tech as _tech

    if not shields:  # a design without MOM arrays
        return 0
    li = lambda name: layout.layer(*LAYERS[name])
    top_metal = max(metal for metal, _ in shields)
    metals = {k: kdb.Region(top.begin_shapes_rec(li(f"M{k}"))).merged() for k in range(1, top_metal + 1)}
    cuts = {k: kdb.Region(top.begin_shapes_rec(li(f"V{k}"))).merged() for k in range(1, top_metal)}
    b = kdb.Region(top.begin_shapes_rec(li("BND"))).merged().bbox()
    outline = _extent(layout, top)  # a stack keeps inside the layout as it stands: no tie grows it
    lines = [k * rowcell.H for k in range(b.bottom // rowcell.H, b.top // rowcell.H + 1) if k % 2 == 0]
    rails = kdb.Region()
    for y in lines:  # VSS lines are the even ones
        rails.insert(kdb.Box(outline.left, y - rowcell.RAIL, outline.right, y + rowcell.RAIL))
    rails &= metals[1]
    if routes is not None and not routes.is_empty():  # another net's M1 across the rail's line
        rails -= routes.sized(_tech.M1_SPACE)

    def pad(k: int, x: int, y: int) -> kdb.Box:
        rule, cut_below = _tech.RULES[f"M{k}"], _tech.RULES[f"V{k - 1}"]
        cut_above = _tech.RULES[f"V{k}"]
        width = max(rule["width"], max(c["cut"] + 2 * c["enclosure"][1] for c in (cut_below, cut_above)))
        end = max(c["cut"] + 2 * c["enclosure"][0] for c in (cut_below, cut_above))
        length = max(end, -(-rule.get("area", 0) // width))
        length += length % 2
        width += width % 2
        w, h = (length, width) if k % 2 == 0 else (width, length)  # along the metal's direction
        return kdb.Box(x - w // 2, y - h // 2, x + w // 2, y + h // 2)

    def stack(x: int, y: int, metal: int, shield: kdb.Region) -> list[tuple[str, kdb.Box]] | None:
        shapes = []
        for k in range(1, metal):
            rule = _tech.RULES[f"V{k}"]
            half = rule["cut"] // 2
            # on the wide rail EDGE_CUTS cuts a pair apart, else one
            xs = [x + (2 * i - (EDGE_CUTS - 1)) * V1_PAIR // 2 for i in range(EDGE_CUTS)] if k == 1 else [x]
            for cx in xs:
                cut = kdb.Box(cx - half, y - half, cx + half, y + half)
                if not (cuts[k] & kdb.Region(cut).sized(rule["space"])).is_empty():
                    return None
                shapes.append((f"V{k}", cut))
        if not shapes:  # a shield on the rails' own metal: no cut
            return shapes
        rail_cuts = [box for name, box in shapes if name == "V1"]
        highest = shapes[-1][1]
        end = _tech.RULES[f"V{metal - 1}"]["enclosure"][0]
        # each cut on the rail inside it by its enclosure: the end one on two opposite sides
        enclosure = _tech.RULES["V1"].get("enclosure", (0, 0))
        if any(
            all(not (kdb.Region(c.enlarged(dx, dy)) - rails).is_empty() for dx, dy in (enclosure[:2], enclosure[1::-1]))
            for c in rail_cuts
        ):
            return None
        # the top cut enclosed by the shield by its end enclosure on two opposite sides (sized with
        # three arguments: two would read as a size and a sizing mode)
        if all(not (kdb.Region(highest).sized(dx, dy, 2) - shield).is_empty() for dx, dy in ((end, 0), (0, end))):
            return None
        for k in range(2, metal):
            box = (
                kdb.Box(x - EDGE_PAD[0], y - EDGE_PAD[1], x + EDGE_PAD[0], y + EDGE_PAD[1]) if k == 2 else pad(k, x, y)
            )
            if not (metals[k] & kdb.Region(box).sized(_tech.RULES[f"M{k}"]["space"])).is_empty():
                return None
            shapes.append((f"M{k}", box))
        if not all(outline.contains(box.p1) and outline.contains(box.p2) for _, box in shapes):
            return None
        return shapes

    def bar(x: int, line: int, metal: int, piece: kdb.Region) -> list[tuple[str, kdb.Box]] | None:
        """A bar on ``metal`` from ``piece`` (the shield) at ``x`` to the VSS rail on ``line``, and
        the stack of cuts from the rail up to it; None where it does not fit."""
        rule = _tech.RULES[f"M{metal}"]
        hw, space = -(-rule["width"] // 2), rule["space"]
        box = piece.bbox()
        up = line > box.top
        column = piece & kdb.Region(kdb.Box(x - hw, box.bottom, x + hw, box.top))
        if column.is_empty():
            return None
        edge = column.bbox().top if up else column.bbox().bottom
        root = kdb.Box(x - hw, edge - 2 * hw, x + hw, edge) if up else kdb.Box(x - hw, edge, x + hw, edge + 2 * hw)
        if not (kdb.Region(root) - piece).is_empty():  # the bar's root inside the shield
            return None
        site = kdb.Box(x - XPITCH, line - rowcell.RAIL, x + XPITCH, line + rowcell.RAIL)
        band = kdb.Region(kdb.Box(outline.left, line - rowcell.RAIL, outline.right, line + rowcell.RAIL))
        # the rows' own M2 along the rail's line, where the rails carry it (no ALIGN wire), the rail's:
        # the bar's whole width on it, a site to either side
        on_rail = kdb.Region()
        if metal == 2:
            on_rail = ((metals[2] & band) - (wires or kdb.Region())).interacting(kdb.Region(site))
            on_rail = kdb.Region([p for p in on_rail.each() if p.bbox().width() >= 4 * XPITCH])
            if not (kdb.Region(site.enlarged(0, rowcell.M2_HW - rowcell.RAIL)) - on_rail).is_empty():
                on_rail = kdb.Region()
        if on_rail.is_empty() and not (kdb.Region(site) - rails).is_empty():
            return None  # else the rail's whole width a site to either side
        rail = rails.interacting(kdb.Region(site))
        if metal == 1 or not on_rail.is_empty():  # the rail's own metal: the bar runs into it, to its far side
            reach = rowcell.RAIL if metal == 1 else rowcell.M2_HW
            run = kdb.Box(x - hw, edge, x + hw, line + reach) if up else kdb.Box(x - hw, line - reach, x + hw, edge)
            shapes = [(f"M{metal}", run)]
            own = metals[metal].interacting(rail if metal == 1 else on_rail)
        else:
            top_pad = kdb.Box(x - EDGE_PAD[0], line - EDGE_PAD[1], x + EDGE_PAD[0], line + EDGE_PAD[1])
            run = (
                kdb.Box(x - hw, edge, x + hw, top_pad.bottom + 2 * hw)
                if up
                else kdb.Box(x - hw, top_pad.top - 2 * hw, x + hw, edge)
            )
            cut_stack = stack(x, line, metal, kdb.Region(top_pad) + kdb.Region(run))
            if cut_stack is None:
                return None
            shapes = [*cut_stack, (f"M{metal}", run), (f"M{metal}", top_pad)]
            own = kdb.Region()
        drawn_metal = kdb.Region([s for name, s in shapes if name == f"M{metal}"])
        others = metals[metal] - metals[metal].interacting(piece) - own
        if not (others & drawn_metal.sized(space)).is_empty():
            return None
        if not all(outline.contains(s.p1) and outline.contains(s.p2) for _, s in shapes):
            return None
        return shapes

    def draw(shapes: list[tuple[str, kdb.Box]]) -> None:
        for name, shape in shapes:
            top.shapes(li(name)).insert(shape)
            (cuts[int(name[1:])] if name[0] == "V" else metals[int(name[1:])]).insert(shape)

    drawn = 0
    for metal, shield in shields:
        for piece in shield.each():
            region, placed = kdb.Region(piece), 0
            for spot in (region & rails).each():
                box = spot.bbox()
                # the spot's middle; where the shield's edge crosses the rail, the rail's line too
                line = round(box.center().y / rowcell.H) * rowcell.H
                ys = [box.center().y] if box.height() >= 2 * rowcell.RAIL else [box.center().y, line]
                x0 = -(-box.left // XPITCH) * XPITCH
                for x, y in ((x, y) for x in range(x0, box.right + 1, XPITCH) for y in ys):
                    shapes = stack(x, y, metal, region)
                    if shapes is None:
                        continue
                    draw(shapes)
                    placed += 1
                    break
                if placed >= per_shield:
                    break
            if not placed:  # beside the rows: a bar to the nearest VSS rail line it reaches
                box = piece.bbox()
                near = sorted(
                    (y for y in lines if y > box.top or y < box.bottom),
                    key=lambda y: min(abs(y - box.top), abs(y - box.bottom)),
                )
                first = -(-box.left // XPITCH) * XPITCH
                xs = sorted(range(first, box.right + 1, XPITCH), key=lambda x: min(x - box.left, box.right - x))
                ties: list[int] = []
                for line in near:
                    for x in xs:
                        if any(abs(x - t) < 4 * XPITCH for t in ties):
                            continue
                        shapes = bar(x, line, metal, region)
                        if shapes is None:
                            continue
                        draw(shapes)
                        ties.append(x)
                        if len(ties) >= per_shield:
                            break
                    if ties:
                        break
                placed = len(ties)
            drawn += placed
    return drawn


def rail_pins(layout: kdb.Layout, top: kdb.Cell, empty: set[int] | None = None) -> list[dict]:
    """The supplies' rail lines left apart, each connected by name (none on a line between two rows
    left empty, ``empty``): the converter's power grid joins them at its top level, as a macro's
    power pins. Each line's M1 run on to the layout's extent at both ends where it keeps M1's space
    from other M1 (so the top level's row rails abut it), and each piece of it a pin: its supply's
    label (M1 pin text) at its middle. VSS on the even lines. Returns each line's pieces (net, y
    and x extent, nm)."""
    import tech as _tech

    li = lambda name: layout.layer(*LAYERS[name])
    m1 = kdb.Region(top.begin_shapes_rec(li("M1"))).merged()
    b = kdb.Region(top.begin_shapes_rec(li("BND"))).merged().bbox()
    outline = _extent(layout, top)
    rows = set(range(b.bottom // rowcell.H, -(-b.top // rowcell.H))) - (empty or set())
    found = []
    for k in range(b.bottom // rowcell.H, b.top // rowcell.H + 1):
        if not {k - 1, k} & rows:
            continue
        y, net = k * rowcell.H, ("vss", "vdd")[k % 2]
        band = kdb.Region(kdb.Box(outline.left, y - rowcell.RAIL, outline.right, y + rowcell.RAIL))
        # the rail: the line's M1 across its whole width, longer than a site (no wire across it)
        pieces = sorted(
            (
                p.bbox()
                for p in (m1 & band).each()
                if p.bbox().height() >= 2 * rowcell.RAIL and p.bbox().width() >= XPITCH
            ),
            key=lambda p: p.left,
        )
        if not pieces:
            continue
        ends = (
            kdb.Box(outline.left, y - rowcell.RAIL, pieces[0].left, y + rowcell.RAIL),
            kdb.Box(pieces[-1].right, y - rowcell.RAIL, outline.right, y + rowcell.RAIL),
        )
        for run in ends:
            if run.width() <= 0:
                continue
            others = m1 - m1.interacting(kdb.Region([pieces[0], pieces[-1]]))
            if (others & kdb.Region(run).sized(_tech.M1_SPACE)).is_empty():
                top.shapes(li("M1")).insert(run)
                m1.insert(run)
        m1.merge()
        line = sorted(
            (
                p.bbox()
                for p in (m1 & band).each()
                if p.bbox().height() >= 2 * rowcell.RAIL and p.bbox().width() >= XPITCH
            ),
            key=lambda p: p.left,
        )
        for piece in line:
            top.shapes(layout.layer(*PIN_TEXT["M1"])).insert(kdb.Text(net, kdb.Trans(piece.center().x, y)))
        found.append({"net": net, "y": y, "pieces": [[p.left, p.right] for p in line]})
    return found


def _extent(layout: kdb.Layout, top: kdb.Cell) -> kdb.Box:
    """The layout's extent on the PDK's own layers (its drawing, not ALIGN's abstract and
    boundary layers, which ``post`` clears, nor its labels)."""
    drawn = set(LAYERS.values()) - {(235, 5)}
    box = kdb.Box()
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        if (info.layer, info.datatype) in drawn and info.datatype not in (251, 253):
            box += kdb.Region(top.begin_shapes_rec(li)).merged().bbox()  # no zero-area shape
    return box


def single_cuts(layout: kdb.Layout, top: kdb.Cell) -> int:
    """A legal cut wherever a via layer's shapes make none (ALIGN's off-grid router drops a cut at
    each of two wires of one net meeting a column a fraction of a track apart, or one cut stretched
    across both): where cuts overlap the first alone, a cut longer than the PDK's (``RULES``) its
    square at its lower left, in a PDK that takes square cuts alone (``SQUARE_CUTS``; others take the
    router's bar cuts as they are). The metals above and below cover the whole of it, so the net stays
    joined. Returns the shapes changed."""
    import tech as _tech

    square = getattr(_tech, "SQUARE_CUTS", False)
    changed = 0
    for n in range(1, 8):
        layer, size = LAYERS.get(f"V{n}"), getattr(_tech, "RULES", {}).get(f"V{n}", {}).get("cut")
        if not layer:
            continue
        shapes = top.shapes(layout.layer(*layer))
        # every cut's box first, the shapes erased only once all are decided (an erased shape's
        # handle is no longer valid)
        cuts = [(s, s.bbox(), s.is_box()) for s in shapes.each() if not s.is_text()]
        erase, insert = [], []
        for cluster in kdb.Region([box for _, box, _ in cuts]).merged().each():
            inside = [c for c in cuts if cluster.bbox().contains(c[1].center())]
            erase += [shape for shape, _, _ in inside[1:]]
            changed += len(inside) - 1
            if not inside:
                continue
            first, box, is_box = inside[0]
            if (
                square
                and size
                and is_box
                and box.width() >= size
                and box.height() >= size
                and box.width() != box.height()
            ):
                erase.append(first)
                insert.append(kdb.Box(box.left, box.bottom, box.left + size, box.bottom + size))
                changed += 1
        for shape in erase:
            shapes.erase(shape)
        for box in insert:
            shapes.insert(box)
    return changed


def _holder(polygons: list, box: kdb.Box) -> int | None:
    """The index of the polygon holding the centre of ``box``, if any."""
    c = box.center()
    return next((i for i, p in enumerate(polygons) if p.bbox().contains(c) and p.inside(c)), None)


def close_cuts(layout: kdb.Layout, top: kdb.Cell) -> int:
    """Two cuts of a via layer closer than its space (``RULES``) on one net: ALIGN's off-grid router
    drops a cut at each of two parallel wires of a net a fraction of a track apart, where one metal
    polygon (the same net) holds both cuts. The gap between their pads on the other metal, where
    they run side by side, is filled (no wider than that metal's space, over no other shape), and
    the second cut goes; the net stays joined through the filled metal. In a PDK with M2 landing
    pads (``M2_VIA_PAD``) two cuts of a padded via layer are that close while their M2 pads are
    nearer than M2's space (ALIGN's two VIA2 of one net on neighbouring tracks, joined by its M3).
    Returns the cuts removed."""
    import tech as _tech

    rules = getattr(_tech, "RULES", {})
    landings = getattr(_tech, "M2_VIA_PAD", {})
    removed = 0
    for n in range(1, 8):
        via, below, above = LAYERS.get(f"V{n}"), LAYERS.get(f"M{n}"), LAYERS.get(f"M{n + 1}")
        space = rules.get(f"V{n}", {}).get("space")
        if not (via and below and above and space):
            continue
        # where M2 lands a cut on a pad (M2_VIA_PAD), two cuts are as close as their pads are: the
        # pads' extent and M2's space past the cut, along the track (x) and across it (y)
        sx = sy = space
        if f"V{n}" in landings:
            cut, (hx, hy) = rules[f"V{n}"]["cut"], landings[f"V{n}"]
            sx, sy = max(space, 2 * hx + M2_SPACE - cut), max(space, 2 * hy + M2_SPACE - cut)
        cut_shapes = top.shapes(layout.layer(*via))
        cuts = sorted(((c, c.bbox()) for c in cut_shapes.each() if not c.is_text()), key=lambda c: c[1].left)
        metals = {
            m: (layout.layer(*LAYERS[m]), kdb.Region(top.shapes(layout.layer(*LAYERS[m]))).merged())
            for m in (f"M{n}", f"M{n + 1}")
        }
        polys = {m: list(region.each()) for m, (_, region) in metals.items()}

        gone: set[int] = set()
        for i, (_, a) in enumerate(cuts):
            for j in range(i + 1, len(cuts)):
                b = cuts[j][1]
                if b.left >= a.right + sx:  # sorted by left edge: none further on is closer
                    break
                if i in gone or j in gone or a.overlaps(b) or not a.enlarged(sx - 1, sy - 1).overlaps(b):
                    continue
                # the same net on one metal; the other's pads joined across their gap
                for same, other in ((f"M{n}", f"M{n + 1}"), (f"M{n + 1}", f"M{n}")):
                    if _holder(polys[same], a) is None or _holder(polys[same], a) != _holder(polys[same], b):
                        continue
                    pa, pb = _holder(polys[other], a), _holder(polys[other], b)
                    if pa is None or pb is None:
                        continue
                    if pa != pb:
                        gap = rules.get(other, {}).get("space", 0)
                        pads = kdb.Region(polys[other][pa]) + kdb.Region(polys[other][pb])
                        fill = pads.sized(gap // 2).sized(-(gap // 2)) - pads
                        fill &= kdb.Region(polys[other][pa].bbox() + polys[other][pb].bbox())
                        others = metals[other][1] - pads
                        if fill.is_empty() or not (fill & others.sized(gap - 1)).is_empty():
                            continue
                        top.shapes(metals[other][0]).insert(fill)
                    gone.add(j)
                    break
        for j in sorted(gone, reverse=True):
            cut_shapes.erase(cuts[j][0])
        removed += len(gone)
    return removed


def clear_rails(layout: kdb.Layout, top: kdb.Cell, routes: kdb.Region) -> int:
    """In a PDK whose M1 keeps a wider space beside a wide wire (``_rail_space``): each rail shaved
    back where M1 no row cell draws (``routes``: ALIGN's, and the MOM units' landings; not touching
    it) comes nearer than that space, ALIGN's router knowing M1's plain space alone. Returns the
    pieces shaved off."""
    import tech as _tech

    space = _rail_space()
    if space <= _tech.M1_SPACE or routes.is_empty():
        return 0
    shapes = top.shapes(layout.layer(*LAYERS["M1"]))
    m1 = kdb.Region(shapes).merged()
    b = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged().bbox()
    lines = kdb.Region()
    for k in range(b.bottom // rowcell.H, b.top // rowcell.H + 1):
        y = k * rowcell.H
        lines.insert(kdb.Box(b.left - b.width(), y - rowcell.RAIL, b.right + b.width(), y + rowcell.RAIL))
    wires = m1 & routes  # ALIGN's M1 as it stands after the gap fills
    rails = (m1 & lines) - wires
    near = wires.not_interacting(rails.sized(1))
    cut = near.sized(space) & rails
    if cut.is_empty():
        return 0
    # each cut as long along its rail as M1's shortest piece (its notch no step), out to the rail's
    # end where it would end nearer than M1's width (a sliver), and two cuts nearer each other than
    # that joined (the rail between them a sliver)
    least = getattr(_tech, "M1_MIN_LEN", _tech.M1W)
    # the strips the rails' cells run off them (a source's into its rail): a cut stops at one, or
    # takes the rail up to one nearer than M1's width, so that it leaves no step beside it
    strips = [s.bbox() for s in (m1 - lines).interacting(rails).each()]
    boxes = []
    for piece in cut.each():
        c = piece.bbox()
        for rail in rails.interacting(kdb.Region(c)).each():
            r = rail.bbox()
            grow = max(0, least - c.width()) // 2
            left, right = max(r.left, c.left - grow), min(r.right, c.right + grow)
            beside = [s for s in strips if s.top >= c.bottom - 1 and s.bottom <= c.top + 1]
            for s in beside:
                if s.left < c.left + c.width() // 2 <= s.right:  # a strip at the cut's own place: leave it
                    continue
                if s.right <= c.left + c.width() // 2 and s.right > left:
                    left = s.right
                if s.left >= c.left + c.width() // 2 and s.left < right:
                    right = s.left
            for s in beside:
                if 0 < left - s.right < _tech.M1W:
                    left = s.right
                if 0 < s.left - right < _tech.M1W:
                    right = s.left
            left = r.left if left - r.left < _tech.M1W else left
            right = r.right if r.right - right < _tech.M1W else right
            boxes.append(kdb.Box(left, c.bottom, right, c.top))
    boxes.sort(key=lambda b: (b.bottom, b.top, b.left))
    joined: list[kdb.Box] = []
    for box in boxes:
        last = joined[-1] if joined else None
        if last and (last.bottom, last.top) == (box.bottom, box.top) and box.left - last.right < _tech.M1W:
            joined[-1] = kdb.Box(last.left, last.bottom, max(last.right, box.right), last.top)
        else:
            joined.append(box)
    cut = (cut + kdb.Region(joined)).merged() & rails
    kept = kdb.Region(shapes) - cut
    for shape in [s for s in shapes.each() if not s.is_text()]:
        shapes.erase(shape)
    shapes.insert(kept)
    return cut.count()


def fill_notches(layout: kdb.Layout, top: kdb.Cell) -> int:
    """In a PDK with M2 landing pads (``M2_VIA_PAD``): the notches of each M2 polygon narrower than
    M2's space filled, where the fill comes within that space of no other M2 shape (two pads on one
    bar a fraction of a space apart: a via's landing ALIGN drew beside a row cell's pad, beside a
    library pin's pad, or beside another of its own). One polygon is one net, so the fill joins
    nothing. Returns the fills."""
    import tech as _tech

    if not getattr(_tech, "M2_VIA_PAD", None):
        return 0
    layer = layout.layer(*LAYERS["M2"])
    m2 = kdb.Region(top.shapes(layer)).merged()
    half = (M2_SPACE - 1) // 2  # closes every gap narrower than the space, and no legal one
    fills = kdb.Region()
    for polygon in m2.each():
        own = kdb.Region(polygon)
        gaps = (own.sized(half).sized(-half) - own) & kdb.Region(polygon.bbox())
        if gaps.is_empty():
            continue
        near = (m2 - own) & kdb.Region(polygon.bbox().enlarged(M2_SPACE, M2_SPACE))
        for gap in gaps.merged().each():
            if (kdb.Region(gap).sized(M2_SPACE - 1) & near).is_empty():
                fills.insert(gap)
    top.shapes(layer).insert(fills)
    return fills.count()


def post(
    src: str | Path,
    dst: str | Path,
    *,
    ring: bool = False,
    ring_net: str = "vdd",
    sub_net: str = "vsub",
    mom_units: dict[str, int] | None = None,
) -> Path:
    """Finish ALIGN's GDS ``src`` into ``dst`` (and ``<dst>.extra.sp``); returns ``dst``. ``mom_units``:
    the MOM units the netlist defines, their shields tied to ground (``mom_shields``)."""

    src, dst, lib = str(src), str(dst), LIB
    layout = kdb.Layout()
    layout.read(src)
    top = layout.top_cell()
    n_keepouts = drop_keepouts(layout, Path(src).parent / "2_primitives")
    routes = kdb.Region(top.shapes(layout.layer(*LAYERS["M1"])))  # ALIGN's own M1, before flattening
    wires = kdb.Region(top.shapes(layout.layer(*LAYERS["M2"])))  # and its M2
    n_std = insert_stdcells(layout, lib)
    n_well_ties = well_ties(layout, lib)
    shields = mom_shields(layout, top, mom_units or {})  # before flattening: by the units' cells
    landings, idle = idle_landings(layout, top, mom_units or {})
    # rows holding standard cells, from the abstracts' placement
    std_rows = set()
    for inst in top.each_inst():
        m = STD.match(inst.cell.name)
        if m and os.environ.get("ROWS_STD_DENSE"):  # dense wrappers only
            std_rows.add(round(inst.bbox().center().y / rowcell.H - 0.5))
    # the kit's tie cells ALIGN placed in the rows (a PDK whose rails carry no taps): decaps stand
    # within their reach alone (``_tied``)
    ties = None
    if netcells.EDGE_TIE and not rowcell.RAIL_TAPS and getattr(netcells._tech, "TIE_REACH", 0):
        tie = netcells.EDGE_TIE[0].upper()
        ties = [inst.bbox() for inst in top.each_inst() if inst.cell.name.upper().startswith(tie)]
    fills = {}
    for name, _ in netcells.STD_FILLS:
        fills[name] = layout.create_cell(name + "_fill")
        fills[name].copy_tree(_lib_cell(lib, name))
    layout.flatten(top.cell_index(), -1, True)
    filled: list[kdb.Box] = []
    block = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged().bbox()  # before the row ends
    ends = row_ends()
    # ALIGN's M1 along a rail's line, inside its band, is that rail's (its power route), no other net's
    bands = kdb.Region(
        [
            kdb.Box(
                block.left - block.width(),
                k * rowcell.H - rowcell.RAIL,
                block.right + block.width(),
                k * rowcell.H + rowcell.RAIL,
            )
            for k in range(block.bottom // rowcell.H, block.top // rowcell.H + 1)
        ]
    )
    across = routes.not_inside(bands)
    # a block whose rows stand apart from capacitors has ALIGN's routing room past its rows' ends
    apart = _rows_apart(layout, top, shields)
    grouped = ends and apart
    rows = _row_ends(block, across, wires) if grouped else block
    on_m2 = kdb.Region()
    for metal, region in shields:
        if metal == 2:
            on_m2 += region
    # the M1 no row cell draws: ALIGN's, and the MOM units' landings (no outline marks a MOM unit)
    cells = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged()
    foreign = across + kdb.Region(top.begin_shapes_rec(layout.layer(*LAYERS["M1"]))).not_interacting(cells)
    # a row no cell stands in under capacitors (their shields): no row, nothing drawn in it
    under = kdb.Region()
    for _metal, region in shields:
        under += region
    fill = Fill()
    n_fill = fill_rows(
        layout, top, std_rows, fills, filled, rows, ends, foreign, on_m2, wires, under.merged(), fill, ties
    )
    std_lib = kdb.Layout()
    std_lib.read(lib)
    n_ties = edge_ties(layout, top, std_rows, std_lib, rows, fill.reserved)
    layout.flatten(top.cell_index(), -1, True)
    cut_poly_bridges(layout, top)
    for g in filled:
        bridge(layout, top, g, block)
    lines = rail_pins(layout, top, fill.reserved)
    n_shield = shield_ties(layout, top, shields, routes=routes, wires=wires)
    ring_info = ""
    if ring:
        import ringcell  # the PDK's guard ring

        rows, sites = ringcell.wrap(layout, top, kdb, ring_net, sub_net)
        layout.flatten(top.cell_index(), -1, True)
        ring_info = f", guard ring ({rows} rows, {sites} sites)"
    extra = [f"* added by align/post.py{' (ring)' if ring else ''}{' (decaps)' if fill.decaps else ''}"]
    if ring:
        extra.append("*.DNW")  # NMOS in the deep N-well: extracted as the _dnw models
    if ring and sub_net not in ("vss", "vdd"):
        extra.append(f"*.PORTS {sub_net}")
    # the decaps: MOS devices between the supplies, as the PDK's deck reads them (fillcell.lvs_line)
    extra += [fillcell.lvs_line(f"Mdecap_{i}", d.pol, d.nf) for i, d in enumerate(fill.decaps)]
    Path(dst + ".extra.sp").write_text("\n".join(extra) + "\n")

    for info in list(layout.layer_infos()):
        li = layout.layer(info)
        if (
            (info.layer == 255 and (info.layer, info.datatype) not in LAYERS.values())  # abstract, not a PDK layer
            or info.datatype in (251, 253)
            or (info.layer, info.datatype) == (235, 5)
        ):
            layout.clear_layer(li)
    n_cuts = single_cuts(layout, top) + close_cuts(layout, top)
    # beside every M1 no row cell draws: ALIGN's and the MOM units' landings (a kit whose shield is
    # M1 lands its plates there, by the rails of the band beside the array)
    n_shaved = clear_rails(layout, top, foreign)
    n_notches = fill_notches(layout, top)
    netcells.close_wells(layout, kdb, top)
    for c in list(layout.top_cells()):  # an unused helper (the filler copy when no row needed fill)
        if c.cell_index() != top.cell_index():
            layout.prune_cell(c.cell_index(), -1)
    # the landings no route reached removed (``idle_landings``): one a plate is left, where its route came
    removed = {layout.layer(*LAYERS[name]): region for name, region in idle.items()}
    idle_stubs = sum(region.count() for name, region in idle.items() if name[0] == "M")
    for li in layout.layer_indexes():
        shapes = top.shapes(li)
        texts = [s.text for s in shapes.each() if s.is_text()]
        polygons = kdb.Region(shapes).merged()
        if li in removed:
            polygons -= removed[li]
        polygons = polygons.snapped(GRID, GRID)
        shapes.clear()
        shapes.insert(polygons)
        for text in texts:  # a net's label lower case, as the netlist names it (ALIGN writes it upper)
            text.string = text.string.lower()
            shapes.insert(text)
    layout.write(dst)
    done = {
        "standard cells": n_std,
        "row gaps filled": n_fill,
        "fill": fill.record(),
        "supply lines": lines,
        "row-end ties": n_ties,
        **({"island ties": n_well_ties} if n_well_ties else {}),
        **({"shield ties": n_shield} if shields else {}),
        **({"landings": {"drawn": landings, "kept": landings - idle_stubs}} if landings else {}),
        **({"keep-outs dropped": n_keepouts} if n_keepouts else {}),
        "cuts made single": n_cuts,
        **({"M2 notches filled": n_notches} if n_notches else {}),
        **({"rails shaved": n_shaved} if n_shaved else {}),
        **({"guard ring": ring_info.removeprefix(", guard ring ")} if ring else {}),
    }
    Path(dst + ".post.json").write_text(json.dumps(done, indent=1) + "\n")
    return Path(dst)
