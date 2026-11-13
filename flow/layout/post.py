"""Finish an ALIGN layout built from row cells (make_pdk.py's PDK directory) for signoff.

* Standard cells: ALIGN placed abstracts named ``<CELL>_<hash>``; the real library cell goes in
  at the wrapper's offset (``paths.ACCESS_JSON``): between the pads the generator drew (free
  placement), or at the right end with the library filler on the left to the placement grid
  (dense wrapper, standard-cell rows). The library's own text labels are dropped (pin names
  would merge nets after flattening), and so are the router's M2 keep-outs the abstract carried;
  the via pads it left out go in (netcells.align_access).
* Rows: ALIGN places cells on the rows but not always abutted. In every gap inside the block
  the rails, taps, tap implant bands and the N-tap well band are drawn as in a row cell
  (rowcell.rails without the device parts), so supplies run through every row; the cells' N-wells
  run across a gap where both neighbours have them, and in a gap narrower than the placement grid
  their device implants, Vt layers and gate markers too (``bridge``); then narrow well gaps are
  closed (netcells.close_wells). A gap's rails keep their space from the M1 no row cell draws
  (``_clear_of``); where that cuts a rail between two cells in a PDK whose rails carry no taps,
  an M2 bar joins it again over the cut (``_rail_bridge``). Where ALIGN routes M1 past the
  cells' outline (its routing room), the row ends move out past it (``_row_ends``).
* Supplies: each supply's rail lines joined by M3 trunks at the block's ends (``supply_straps``);
  where capacitors take the block's M3 across its height, trunks outside the rows
  (``outside_trunk``) and one in each group of rows (``group_trunks``); a MOM shield tied to
  VSS from a rail under it, else from a VSS trunk's pad (``shield_ties``). In a PDK whose M1
  keeps a wider space beside a wide wire, a rail shaved back from ALIGN's M1 (``clear_rails``).
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
from pathlib import Path

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
    M3W,
    MFG_GRID,
    PIN_TEXT,
    STD_FILL,
    V1,
    V1_PAIR,
    V2,
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


def _lib_cell(lib_path: str, name: str) -> kdb.Cell:
    lib = kdb.Layout()
    lib.read(lib_path)
    c = lib.cell(name)
    drop_labels(lib, c)
    _lib_cell.keep = lib  # the cell lives in this layout
    return c


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
) -> int:
    """Rails, taps and well band across the placement gaps of every row; library fillers in
    standard-cell rows (their implant bands differ from the analog rows'). ``filled`` collects the
    analog rows' gaps (``bridge``). ``box``: the rows' extent (the cells' outline unless given:
    ``_row_ends``); ``ends``: row-end cells will stand at its sides (``edge_ties``). Where ALIGN
    routed M1 through a gap (no cell is there, so it is another net's), the fill's M1 and contacts
    keep M1's space from it (``_clear_of``), and from the M1 no row cell draws (``routes``: ALIGN's,
    the MOM units' landings) ending in the next row within that space of the rail they share.
    ``shield``: the MOM shields on M2 (VSS), which a VSS rail's bridge may meet; ``wires``: ALIGN's
    M2 (``_rail_bridge``)."""
    bnd = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged()
    box = box or bnd.bbox()
    m1 = kdb.Region(top.begin_shapes_rec(layout.layer(*rowcell.GLAYERS["M1"])))
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
        gaps = (band - bnd).merged()
        for gap in gaps.each():
            g = gap.bbox()
            if g.height() < rowcell.H:
                continue
            # ALIGN's M1 through the gap: what reaches inside it past the rails (the rows beside it
            # reach into it with their rails' halves alone)
            inside = kdb.Region(kdb.Box(g.left, g.bottom + rowcell.RAIL + 1, g.right, g.top - rowcell.RAIL - 1))
            routed = m1.interacting(inside)
            if routes is not None:
                reach = _rail_space() + rowcell.RAIL
                routed = (routed + (routes & kdb.Region(g.enlarged(0, reach)))).merged()
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
            # orientation: VSS on even rail lines (cells placed R0 on even rows, MX on odd ones)
            t = kdb.Trans(g.left, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, g.left, y0 + rowcell.H)
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
            if filled is not None:
                filled.append(g)
            n += 1
    return n


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
    if not (others & kdb.Region(bar).sized(ends, M2_SPACE, 2)).is_empty():
        return False
    # cells with M2 rails on both sides (rowcell): the bar joins those, no cut of its own
    rails = (local & track) - (jumps["wires"] & window)
    if all(not (rails & kdb.Region(kdb.Box(x - 1, y - 1, x + 1, y + 1))).is_empty() for x in (gap.left, gap.right)):
        cuts = []
    if not (jumps["V1"] & kdb.Region(cuts).sized(rule["space"])).is_empty():
        return False
    top.shapes(layout.layer(*LAYERS["M2"])).insert(bar)
    jumps["M2"].insert(bar)
    if not jumps["shield"].is_empty() and (y // rowcell.H) % 2 == 0:
        # a gap narrower than M2's space between the bar and a shield (VSS both) filled
        near = jumps["shield"] & kdb.Region(bar.enlarged(M2_SPACE, M2_SPACE))
        if not near.is_empty():
            both = (kdb.Region(bar) + near).merged()
            half = (M2_SPACE - 1) // 2
            fill = (both.sized(half).sized(-half) - both) & kdb.Region(bar.enlarged(M2_SPACE, M2_SPACE))
            fill = fill.interacting(kdb.Region(bar))
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


def edge_ties(layout: kdb.Layout, top: kdb.Cell, std_rows: set[int], std_lib, box: kdb.Box | None = None) -> int:
    """For a PDK whose rails carry no taps (netcells.EDGE_TIE): its row-end cells (the library tie
    cell, then library fillers or a pad with the standard cells' profile) at both ends of every
    row, outside the rows' extent ``box`` (the block's outline unless given, ``_row_ends``),
    mirrored like the row (VSS on even rail lines). A PDK with ALIGN_ROW_ENDS (where a generated
    P-well past a PMOS cell at the block side would be too narrow) gets row fillers there instead
    (netcells.filler, library fillers on standard-cell rows)."""
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
        cell = cells[k in std_rows]
        y0 = k * rowcell.H
        for x, mirror in ((b.left - w, False), (b.right + w, True)):  # the tie at the block's outer side
            t = kdb.Trans(kdb.Trans.M90, x, 0) if mirror else kdb.Trans(x, 0)
            row = kdb.Trans(0, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, 0, y0 + rowcell.H)
            top.insert(kdb.CellInstArray(cell.cell_index(), row * t))
            n += 1
    return n


def supply_straps(
    layout: kdb.Layout,
    top: kdb.Cell,
    outer: tuple[int, int] | None = None,
    trunks: list[tuple[str, int, list[kdb.Box]]] | None = None,
    wires: kdb.Region | None = None,
) -> int:
    """Join each supply's rail lines: at both block ends an M3 trunk with, on every rail line of
    the supply, EDGE_CUTS VIA1 (two where the rail is wide), an M2 pad and a VIA2.
    Positions on the M3 grid, the nearest to each end, where the pads and the trunk keep the M2
    space from other metal and the cuts land on the rails. VSS lines are the even ones. Labels
    vdd/vss go on the trunks (M3 pin text); a supply of one rail line no strap fits gets its label
    on that rail. In a block whose rows stand in groups (capacitors between them, their M3 taken
    across the block's height), a supply of several lines gets a trunk outside the rows (``outer``,
    their ends' x) at an end no trunk inside the block came near (``outside_trunk``), and then a
    trunk in each group of rows (``group_trunks``; ``wires``: ALIGN's M2). ``trunks`` gets each trunk's net, x and pads."""
    li = lambda ld: layout.layer(*ld)
    sp, hw = M2_SPACE, M3W // 2
    m1 = kdb.Region(top.begin_shapes_rec(li(LAYERS["M1"]))).merged()
    m2 = kdb.Region(top.begin_shapes_rec(li(LAYERS["M2"]))).merged()
    m3 = kdb.Region(top.begin_shapes_rec(li(LAYERS["M3"]))).merged()
    b = kdb.Region(top.begin_shapes_rec(li(BND))).merged().bbox()
    lines = range(b.bottom // rowcell.H, b.top // rowcell.H + 1)
    placed = 0
    supplies = {}  # net -> (its rail lines, its pads' y)
    for net, parity in (("vss", 0), ("vdd", 1)):
        ys = [k * rowcell.H for k in lines if k % 2 == parity]
        rail_ys = list(ys)
        # pads inside the block where the cuts stay on the rail (enclosed 10 nm), else on the rail line
        reach = rowcell.RAIL - V1 // 2 - 10
        ys = [min(max(y, b.bottom + EDGE_PAD[1] + 10), b.top - EDGE_PAD[1] - 10) for y in ys]
        ys = [
            y if abs(y - k * rowcell.H) <= reach else k * rowcell.H
            for y, k in zip(ys, (k for k in lines if k % 2 == parity))
        ]
        supplies[net] = (rail_ys, ys)
    import tech as _tech

    # a VIA1's M1 enclosure: its line-end one on two opposite sides, its side one on the others
    enclosure = tuple(_tech.RULES.get("V1", {}).get("enclosure", (0, 0))[:2])
    grouped = outer is not None and len(_row_groups(layout, top)) > 1  # capacitors between rows
    labelled = set()
    outside = False  # a trunk outside the rows drawn
    covered: set[tuple[str, int]] = set()  # (supply, the block's half its inside trunk stands in)
    # from each end inwards, as far as the other end (a narrow block's ends may all be taken); each
    # end in turn for both supplies, as where the routes leave few free M3 columns the first supply
    # would otherwise take one at both ends and leave the second none
    for side in (+1, -1):
        for net, (_rail_ys, ys) in supplies.items():
            xs = (
                range(b.left + XPITCH, b.right - XPITCH + 1, XPITCH)
                if side > 0
                else range(b.right - XPITCH, b.left + XPITCH - 1, -XPITCH)
            )
            # the pads keep the routers' line-end gap (two M2 spaces) from wires ending beside them
            # where a position allows it, else the M2 space
            for gap, x in ((gap, x) for gap in (2 * sp, sp) for x in xs):
                # the trunk encloses its outermost VIA2 (by BAR_END - V2 / 2), past the block if need be
                trunk = kdb.Box(x - hw, min(b.bottom, ys[0] - BAR_END), x + hw, max(b.top, ys[-1] + BAR_END))
                pads = [kdb.Box(x - EDGE_PAD[0], y - EDGE_PAD[1], x + EDGE_PAD[0], y + EDGE_PAD[1]) for y in ys]
                if not (m3 & kdb.Region(trunk).sized(sp)).is_empty():
                    continue
                if any(not (m2 & kdb.Region(p).sized(gap, sp)).is_empty() for p in pads):
                    continue
                cuts = [
                    kdb.Box(c - V1 // 2, y - V1 // 2, c + V1 // 2, y + V1 // 2)
                    for y in ys
                    for c in (x + (2 * k - (EDGE_CUTS - 1)) * V1_PAIR // 2 for k in range(EDGE_CUTS))
                ]
                if any(not (kdb.Region(c) - m1).is_empty() for c in cuts):  # past the rails' ends (the
                    continue  # block outline may reach beyond them): the cuts would have no M1
                # in a block of row groups (ALIGN's M1 across the rails' lines at its ends): the cuts
                # inside the rail by its enclosure, on the rail itself (its whole width a site to
                # either side), not on a wire across its line
                if grouped and any(
                    all(not (kdb.Region(c.enlarged(dx, dy)) - m1).is_empty() for dx, dy in (enclosure, enclosure[::-1]))
                    for c in cuts
                ):
                    continue
                lines_at = [round(y / rowcell.H) * rowcell.H for y in ys]
                span = [
                    kdb.Box(
                        x - XPITCH, max(y - rowcell.RAIL + 1, b.bottom), x + XPITCH, min(y + rowcell.RAIL - 1, b.top)
                    )
                    for y in lines_at
                ]
                if grouped and any(not (kdb.Region(box) - m1).is_empty() for box in span):
                    continue

                top.shapes(li(LAYERS["M3"])).insert(trunk)
                m3.insert(trunk)  # a candidate is sized by the space: one M3 space between trunks
                for p, y in zip(pads, ys):
                    top.shapes(li(LAYERS["M2"])).insert(p)
                    m2.insert(p)
                    top.shapes(li(LAYERS["V2"])).insert(kdb.Box(x - V2 // 2, y - V2 // 2, x + V2 // 2, y + V2 // 2))
                    for k in range(EDGE_CUTS):
                        cx = x + (2 * k - (EDGE_CUTS - 1)) * V1_PAIR // 2
                        top.shapes(li(LAYERS["V1"])).insert(
                            kdb.Box(cx - V1 // 2, y - V1 // 2, cx + V1 // 2, y + V1 // 2)
                        )
                top.shapes(li(PIN_TEXT["M3"])).insert(kdb.Text(net, kdb.Trans(x, (b.top + b.bottom) // 2)))
                placed += 1
                labelled.add(net)
                covered.add((net, -1 if 2 * x < b.left + b.right else +1))
                if trunks is not None:
                    trunks.append((net, x, pads))
                break
    # rows in groups (capacitors between them): an end no trunk inside the block came near (both
    # found from one end, or none) gets a trunk outside
    for net, (rail_ys, _ys) in supplies.items():
        if grouped and len(rail_ys) > 1:
            for side, x in ((-1, outer[0]), (+1, outer[1])):
                if (net, side) not in covered and outside_trunk(
                    layout, top, net, rail_ys, side, x, (m1, m2, m3), trunks
                ):
                    placed += 1
                    labelled.add(net)
                    outside = True
    if outside:
        # the block's M3 taken across its height: a line's rail meets the trunks at the ends only
        # where it runs on to them, so each group of rows (the rows between capacitors) gets a
        # trunk of each supply of its own
        for net, (rail_ys, _ys) in supplies.items():
            placed += group_trunks(layout, top, net, rail_ys, (m1, m2, m3), enclosure, wires or kdb.Region())
    for net, (rail_ys, _ys) in supplies.items():
        if net not in labelled and len(rail_ys) == 1:
            # no strap fits (the router's M2 runs along the rail line): a supply of one rail line,
            # joined by abutment, is its port where that rail's M1 is labelled
            y = rail_ys[0]
            x = next((p.bbox().center().x for p in m1.each() if p.bbox().bottom <= y <= p.bbox().top), b.center().x)
            top.shapes(li(PIN_TEXT["M1"])).insert(kdb.Text(net, kdb.Trans(x, y)))
    return placed


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


def group_trunks(
    layout: kdb.Layout,
    top: kdb.Cell,
    net: str,
    rail_ys: list[int],
    metals: tuple[kdb.Region, kdb.Region, kdb.Region],
    enclosure: tuple[int, int],
    wires: kdb.Region,
) -> int:
    """For each group of rows with cells (consecutive rows; capacitors between groups), an M3 trunk
    across ``net``'s rail lines in the group (two at least) inside the block, as ``supply_straps``
    draws its own: EDGE_CUTS VIA1 on each rail, its whole width a site to either side and the cuts
    enclosed, an M2 pad and a VIA2; the column on the M3 grid nearest the block's middle where the
    trunk, the pads and the cuts keep their spaces (``metals``: M1, M2, M3, the drawn added; the
    rows' M2 rails joined, ALIGN's M2, ``wires``, kept from). Its label on it. Returns the trunks
    drawn."""
    li = lambda ld: layout.layer(*ld)
    m1, m2, m3 = metals
    sp, hw = M2_SPACE, M3W // 2
    b = kdb.Region(top.begin_shapes_rec(li(BND))).merged().bbox()
    groups = _row_groups(layout, top)
    middle = (b.left + b.right) // 2 // XPITCH * XPITCH
    first = -(-(b.left + XPITCH) // XPITCH) * XPITCH
    columns = sorted(range(first, b.right - XPITCH + 1, XPITCH), key=lambda x: abs(x - middle))
    drawn = 0
    for group in groups:
        lo, hi = group[0] * rowcell.H, (group[-1] + 1) * rowcell.H
        ys = [y for y in rail_ys if lo <= y <= hi]
        if len(ys) < 2:
            continue
        for x in columns:
            trunk = kdb.Box(x - hw, ys[0] - BAR_END, x + hw, ys[-1] + BAR_END)
            if not (m3 & kdb.Region(trunk).sized(sp)).is_empty():
                continue
            pads = [kdb.Box(x - EDGE_PAD[0], y - EDGE_PAD[1], x + EDGE_PAD[0], y + EDGE_PAD[1]) for y in ys]
            # the rows' own M2 on a rail's line is that rail's (an M2 rail, rowcell), ALIGN's wires others'
            reach = kdb.Region([pad.enlarged(sp, sp) for pad in pads])
            own = kdb.Region(
                [kdb.Box(x - 2 * EDGE_PAD[0], y - rowcell.M2_HW, x + 2 * EDGE_PAD[0], y + rowcell.M2_HW) for y in ys]
            )
            others = m2 - ((m2 & own) - wires)
            if not (others & reach).is_empty():
                continue
            xs = [x + (2 * k - (EDGE_CUTS - 1)) * V1_PAIR // 2 for k in range(EDGE_CUTS)]
            cuts = [kdb.Box(c - V1 // 2, y - V1 // 2, c + V1 // 2, y + V1 // 2) for y in ys for c in xs]
            if any(
                all(not (kdb.Region(c.enlarged(dx, dy)) - m1).is_empty() for dx, dy in (enclosure, enclosure[::-1]))
                for c in cuts
            ):
                continue
            span = [kdb.Box(x - XPITCH, y - rowcell.RAIL + 1, x + XPITCH, y + rowcell.RAIL - 1) for y in ys]
            if any(not (kdb.Region(box) - m1).is_empty() for box in span):
                continue
            top.shapes(li(LAYERS["M3"])).insert(trunk)
            m3.insert(trunk)
            for pad, y in zip(pads, ys, strict=True):
                top.shapes(li(LAYERS["M2"])).insert(pad)
                m2.insert(pad)
                top.shapes(li(LAYERS["V2"])).insert(kdb.Box(x - V2 // 2, y - V2 // 2, x + V2 // 2, y + V2 // 2))
            for cut in cuts:
                top.shapes(li(LAYERS["V1"])).insert(cut)
            top.shapes(li(PIN_TEXT["M3"])).insert(kdb.Text(net, kdb.Trans(x, (trunk.top + trunk.bottom) // 2)))
            drawn += 1
            break
    return drawn


def outside_trunk(
    layout: kdb.Layout,
    top: kdb.Cell,
    net: str,
    rail_ys: list[int],
    side: int,
    end: int,
    metals: tuple[kdb.Region, kdb.Region, kdb.Region],
    trunks: list[tuple[str, int, list[kdb.Box]]] | None = None,
) -> bool:
    """An M3 trunk of ``net`` past the rows' end ``end`` (x) on ``side`` (-1 left, +1 right): each of
    its rail lines ``rail_ys`` whose rail reaches the end runs on in M1 to the trunk, where
    EDGE_CUTS VIA1, an M2 pad and a VIA2 join it, as inside (``supply_straps``). The nearest
    position on the M3 grid where the trunk, the pads and the rails' runs keep their metals' spaces
    from other metal (``metals``: M1, M2, M3, the drawn shapes added); its label on it (M3 pin
    text); ``trunks`` gets its net, x and pads. Whether it was drawn (a rail line reached it)."""
    li = lambda ld: layout.layer(*ld)
    m1, m2, m3 = metals
    sp, hw, gap1 = M2_SPACE, M3W // 2, _rail_space()
    # the rails ending at the rows' end: M1 there across the rail line's whole width
    probe = lambda y: kdb.Box(  # a site's length of rail inward from the end, not a wire across its line
        end - (XPITCH if side > 0 else 0), y - rowcell.RAIL + 1, end + (XPITCH if side < 0 else 0), y + rowcell.RAIL - 1
    )
    lines = [y for y in rail_ys if (kdb.Region(probe(y)) - m1).is_empty()]
    if not lines:
        return False
    import tech as _tech

    area = getattr(_tech, "RULES", {}).get("M3", {}).get("area", 0)
    v1_end = getattr(_tech, "RULES", {}).get("V1", {}).get("enclosure", (0,))[0]
    least = max(getattr(_tech, "M2_MIN_LEN", 0), -(-area // M3W))
    near = end + side * (EDGE_PAD[0] + sp)
    first = -(-near // XPITCH) * XPITCH if side > 0 else near // XPITCH * XPITCH
    for x in range(first, first + side * 8 * XPITCH, side * XPITCH):
        # the rail's run past the trunk's outer cut by the cut's end enclosure, and past its pad
        past = max(EDGE_PAD[0], (EDGE_CUTS - 1) * V1_PAIR // 2 + V1 // 2 + v1_end)
        lo, hi = min(x - past, end), max(x + past, end)
        runs = [kdb.Box(lo, y - rowcell.RAIL, hi, y + rowcell.RAIL) for y in lines]
        rails = m1.interacting(kdb.Region([probe(y) for y in lines]))
        if not ((m1 - rails) & kdb.Region(runs).sized(gap1)).is_empty():
            continue
        pads = [kdb.Box(x - EDGE_PAD[0], y - EDGE_PAD[1], x + EDGE_PAD[0], y + EDGE_PAD[1]) for y in lines]
        if not (m2 & kdb.Region(pads).sized(sp)).is_empty():
            continue
        trunk = kdb.Box(x - hw, lines[0] - BAR_END, x + hw, lines[-1] + BAR_END)
        short = (least - trunk.height() + 1) // 2  # a trunk of few lines: M3's minimum length and area
        if short > 0:
            trunk = trunk.enlarged(0, short)
        if not (m3 & kdb.Region(trunk).sized(sp)).is_empty():
            continue
        for run, pad, y in zip(runs, pads, lines, strict=True):
            top.shapes(li(LAYERS["M1"])).insert(run)
            m1.insert(run)
            top.shapes(li(LAYERS["M2"])).insert(pad)
            m2.insert(pad)
            top.shapes(li(LAYERS["V2"])).insert(kdb.Box(x - V2 // 2, y - V2 // 2, x + V2 // 2, y + V2 // 2))
            for k in range(EDGE_CUTS):
                cx = x + (2 * k - (EDGE_CUTS - 1)) * V1_PAIR // 2
                top.shapes(li(LAYERS["V1"])).insert(kdb.Box(cx - V1 // 2, y - V1 // 2, cx + V1 // 2, y + V1 // 2))
        top.shapes(li(LAYERS["M3"])).insert(trunk)
        m3.insert(trunk)
        top.shapes(li(PIN_TEXT["M3"])).insert(kdb.Text(net, kdb.Trans(x, (trunk.top + trunk.bottom) // 2)))
        if trunks is not None:
            trunks.append((net, x, pads))
        return True
    return False


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


def shield_ties(
    layout: kdb.Layout,
    top: kdb.Cell,
    shields: list[tuple[int, kdb.Region]],
    per_shield: int = 2,
    routes: kdb.Region | None = None,
    trunks: list[tuple[str, int, list[kdb.Box]]] | None = None,
) -> int:
    """Tie each MOM shield (``mom_shields``) to VSS where it lies over a row's VSS rail: a stack of
    cuts from the rail up to the shield, a pad on every metal between, on the M3 grid, where every
    pad keeps its metal's space from other metal and every cut its cut space; ``per_shield`` stacks
    a shield, from its lower left. ``routes``: ALIGN's own M1, which crosses a rail's line in a row
    gap and is no rail. A shield on M2 over no rail a stack reaches (ALIGN's M1 cuts the rails
    under it) runs on along a VSS line to an M2 pad of a VSS trunk outside the rows (``trunks``,
    ``outside_trunk``) where M2 is free. Returns the ties drawn."""
    import tech as _tech

    if not shields:  # a design without MOM arrays
        return 0
    li = lambda name: layout.layer(*LAYERS[name])
    top_metal = max(metal for metal, _ in shields)
    metals = {k: kdb.Region(top.begin_shapes_rec(li(f"M{k}"))).merged() for k in range(1, top_metal + 1)}
    cuts = {k: kdb.Region(top.begin_shapes_rec(li(f"V{k}"))).merged() for k in range(1, top_metal)}
    b = kdb.Region(top.begin_shapes_rec(li("BND"))).merged().bbox()
    rails = kdb.Region()
    for k in range(b.bottom // rowcell.H, b.top // rowcell.H + 1):
        if k % 2 == 0:  # VSS lines are the even ones
            rails.insert(kdb.Box(b.left, k * rowcell.H - rowcell.RAIL, b.right, k * rowcell.H + rowcell.RAIL))
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
            # on the wide rail EDGE_CUTS cuts a pair apart (as the supply straps), else one
            xs = [x + (2 * i - (EDGE_CUTS - 1)) * V1_PAIR // 2 for i in range(EDGE_CUTS)] if k == 1 else [x]
            for cx in xs:
                cut = kdb.Box(cx - half, y - half, cx + half, y + half)
                if not (cuts[k] & kdb.Region(cut).sized(rule["space"])).is_empty():
                    return None
                shapes.append((f"V{k}", cut))
        rail_cuts = [box for name, box in shapes if name == "V1"]
        highest = shapes[-1][1]
        end = _tech.RULES[f"V{metal - 1}"]["enclosure"][0]
        # each cut on the rail inside it by its enclosure: the end one on two opposite sides
        enclosure = _tech.RULES["V1"].get("enclosure", (0, 0))
        if any(
            all(
                not (kdb.Region(c.enlarged(dx, dy)) - metals[1]).is_empty()
                for dx, dy in (enclosure[:2], enclosure[1::-1])
            )
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
        return shapes

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
                    for name, shape in shapes:
                        top.shapes(li(name)).insert(shape)
                        (cuts[int(name[1:])] if name[0] == "V" else metals[int(name[1:])]).insert(shape)
                    placed += 1
                    break
                if placed >= per_shield:
                    break
            if not placed and metal == 2:
                placed = _trunk_tie(layout, top, region, trunks or [], metals[2])
            drawn += placed
    return drawn


def _trunk_tie(
    layout: kdb.Layout, top: kdb.Cell, shield: kdb.Region, trunks: list[tuple[str, int, list[kdb.Box]]], m2: kdb.Region
) -> int:
    """A bar on M2 from a VSS trunk's pad (``trunks``: net, x, pads) along its line to ``shield``,
    the nearest where it keeps M2's space from other M2 (``m2``, the bar added). 1 where drawn."""
    import tech as _tech

    hw, box = _tech.M2W // 2, shield.bbox()
    for net, x, pads in trunks:
        for pad in pads if net == "vss" else ():
            y = pad.center().y
            if not box.bottom + hw <= y <= box.top - hw:
                continue
            reach = shield & kdb.Region(kdb.Box(box.left, y - hw, box.right, y + hw))
            if reach.is_empty():
                continue
            ends = reach.bbox()
            bar = (
                kdb.Box(pad.right, y - hw, ends.left, y + hw)
                if x < box.left
                else kdb.Box(ends.right, y - hw, pad.left, y + hw)
            )
            if bar.width() <= 0:
                continue
            others = m2 - kdb.Region(pad) - shield
            if not (others & kdb.Region(bar).sized(M2_SPACE)).is_empty():
                continue
            top.shapes(layout.layer(*LAYERS["M2"])).insert(bar)
            m2.insert(bar)
            return 1
    return 0


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
    back where ALIGN's M1 (``routes``, another net's: not touching it) comes nearer than that
    space, ALIGN's router knowing M1's plain space alone. Returns the pieces shaved off."""
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
    routes = kdb.Region(top.shapes(layout.layer(*LAYERS["M1"])))  # ALIGN's own M1, before flattening
    wires = kdb.Region(top.shapes(layout.layer(*LAYERS["M2"])))  # and its M2
    n_std = insert_stdcells(layout, lib)
    shields = mom_shields(layout, top, mom_units or {})  # before flattening: by the units' cells
    # rows holding standard cells, from the abstracts' placement
    std_rows = set()
    for inst in top.each_inst():
        m = STD.match(inst.cell.name)
        if m and os.environ.get("ROWS_STD_DENSE"):  # dense wrappers only
            std_rows.add(round(inst.bbox().center().y / rowcell.H - 0.5))
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
    # a block of row groups (capacitors between them) has ALIGN's routing room past its rows' ends
    grouped = ends and len(_row_groups(layout, top)) > 1
    rows = _row_ends(block, across, wires) if grouped else block
    on_m2 = kdb.Region()
    for metal, region in shields:
        if metal == 2:
            on_m2 += region
    # the M1 no row cell draws: ALIGN's, and the MOM units' landings (no outline marks a MOM unit)
    cells = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged()
    foreign = across + kdb.Region(top.begin_shapes_rec(layout.layer(*LAYERS["M1"]))).not_interacting(cells)
    n_fill = fill_rows(layout, top, std_rows, fills, filled, rows, ends, foreign, on_m2, wires)
    std_lib = kdb.Layout()
    std_lib.read(lib)
    n_ties = edge_ties(layout, top, std_rows, std_lib, rows)
    layout.flatten(top.cell_index(), -1, True)
    for g in filled:
        bridge(layout, top, g, block)
    outer = (rows.left - netcells.EDGE_W, rows.right + netcells.EDGE_W) if ends else (rows.left, rows.right)
    trunks: list[tuple[str, int, list[kdb.Box]]] = []
    n_straps = supply_straps(layout, top, outer, trunks, wires)
    n_shield = shield_ties(layout, top, shields, routes=routes, trunks=trunks)
    ring_info = ""
    if ring:
        import ringcell  # the PDK's guard ring

        rows, sites = ringcell.wrap(layout, top, kdb, ring_net, sub_net)
        layout.flatten(top.cell_index(), -1, True)
        ring_info = f", guard ring ({rows} rows, {sites} sites)"
    extra = [f"* added by align/post.py{' (ring)' if ring else ''}"]
    if ring:
        extra.append("*.DNW")  # NMOS in the deep N-well: extracted as the _dnw models
    if ring and sub_net not in ("vss", "vdd"):
        extra.append(f"*.PORTS {sub_net}")
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
    n_shaved = clear_rails(layout, top, routes)
    n_notches = fill_notches(layout, top)
    netcells.close_wells(layout, kdb, top)
    for c in list(layout.top_cells()):  # an unused helper (the filler copy when no row needed fill)
        if c.cell_index() != top.cell_index():
            layout.prune_cell(c.cell_index(), -1)
    for li in layout.layer_indexes():
        shapes = top.shapes(li)
        texts = [s.text for s in shapes.each() if s.is_text()]
        polygons = kdb.Region(shapes).merged().snapped(GRID, GRID)
        shapes.clear()
        shapes.insert(polygons)
        for text in texts:  # a net's label lower case, as the netlist names it (ALIGN writes it upper)
            text.string = text.string.lower()
            shapes.insert(text)
    layout.write(dst)
    done = {
        "standard cells": n_std,
        "row gaps filled": n_fill,
        "supply straps": n_straps,
        "row-end ties": n_ties,
        **({"shield ties": n_shield} if shields else {}),
        "cuts made single": n_cuts,
        **({"M2 notches filled": n_notches} if n_notches else {}),
        **({"rails shaved": n_shaved} if n_shaved else {}),
        **({"guard ring": ring_info.removeprefix(", guard ring ")} if ring else {}),
    }
    Path(dst + ".post.json").write_text(json.dumps(done, indent=1) + "\n")
    return Path(dst)
