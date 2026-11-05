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
  closed (netcells.close_wells).
* Labels: ALIGN writes the pin labels on the PDK's pin-text layers itself (make_pdk.py's
  LabelLayerNo, honoured by its writers since ALIGN 24656418); pin shapes,
  blockages and abstract layers (datatypes 251/253, layer 255 unless the PDK draws on it, and the PnR's whole-block
  boundary marker 235/5) are removed; shapes are merged and snapped to the manufacturing grid.
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
) -> int:
    """Rails, taps and well band across the placement gaps of every row; library fillers in
    standard-cell rows (their implant bands differ from the analog rows'). ``filled`` collects the
    analog rows' gaps (``bridge``)."""
    bnd = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged()
    box = bnd.bbox()
    n = 0
    for k in range(box.bottom // rowcell.H, -(-box.top // rowcell.H)):
        y0 = k * rowcell.H
        band = kdb.Region(kdb.Box(box.left, y0, box.right, y0 + rowcell.H))
        gaps = (band - bnd).merged()
        for gap in gaps.each():
            g = gap.bbox()
            if g.height() < rowcell.H:
                continue
            if k in std_rows:
                x = g.left
                try:
                    fillers = netcells.fillers(g.width())
                except ValueError:  # narrower than the library's fillers (ALIGN places on a finer grid)
                    pad = netcells.std_fill(g.width())  # the standard cells' profile, as at a row end
                    rowcell.std_pad(pad, 0, g.width(), "left")
                    t = kdb.Trans(x, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, x, y0 + rowcell.H)
                    for r in pad.rects:
                        if r.layer != "BND" and r.kind != "stub" and rowcell.GLAYERS.get(r.layer):
                            b = kdb.Box(r.x0, r.y0, r.x1, r.y1).transformed(t)
                            top.shapes(layout.layer(*rowcell.GLAYERS[r.layer])).insert(b)
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
            for r in cell.rects:
                if (
                    r.layer in ("BND", *rowcell.VT["n"], *rowcell.VT["p"])
                    or r.kind == "stub"
                    or not rowcell.GLAYERS.get(r.layer)
                ):
                    continue
                if r.layer in ("NP", "PP") and (r.y0, r.y1) == rowcell.DEV_IMP["n"]:
                    continue  # no device implant in a gap
                b = kdb.Box(r.x0, r.y0, r.x1, r.y1).transformed(t)
                top.shapes(layout.layer(*rowcell.GLAYERS[r.layer])).insert(b)
            if filled is not None:
                filled.append(g)
            n += 1
    return n


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


def edge_ties(layout: kdb.Layout, top: kdb.Cell, std_rows: set[int], std_lib) -> int:
    """For a PDK whose rails carry no taps (netcells.EDGE_TIE): its row-end cells (the library tie
    cell, then library fillers or a pad with the standard cells' profile) at both ends of every
    row, outside the block, mirrored like the row (VSS on even rail lines). A PDK with ALIGN_ROW_ENDS
    (where a generated P-well past a PMOS cell at the block side would be too narrow) gets row
    fillers there instead (netcells.filler, library fillers on standard-cell rows)."""
    ends = getattr(netcells._tech, "ALIGN_ROW_ENDS", False)
    if not (netcells.EDGE_TIE or ends):
        return 0
    b = kdb.Region(top.begin_shapes_rec(layout.layer(*BND))).merged().bbox()
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


def supply_straps(layout: kdb.Layout, top: kdb.Cell) -> int:
    """Join each supply's rail lines: at both block ends an M3 trunk with, on every rail line of
    the supply, EDGE_CUTS VIA1 (two where the rail is wide), an M2 pad and a VIA2.
    Positions on the M3 grid, the nearest to each end, where the pads and the trunk keep the M2
    space from other metal and the cuts land on the rails. VSS lines are the even ones. Labels
    vdd/vss go on the trunks (M3 pin text); a supply of one rail line no strap fits gets its label
    on that rail."""
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
    labelled = set()
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
                break
    for net, (rail_ys, _ys) in supplies.items():
        if net not in labelled and len(rail_ys) == 1:
            # no strap fits (the router's M2 runs along the rail line): a supply of one rail line,
            # joined by abutment, is its port where that rail's M1 is labelled
            y = rail_ys[0]
            x = next((p.bbox().center().x for p in m1.each() if p.bbox().bottom <= y <= p.bbox().top), b.center().x)
            top.shapes(li(PIN_TEXT["M1"])).insert(kdb.Text(net, kdb.Trans(x, y)))
    return placed


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


def shield_ties(layout: kdb.Layout, top: kdb.Cell, shields: list[tuple[int, kdb.Region]], per_shield: int = 2) -> int:
    """Tie each MOM shield (``mom_shields``) to VSS where it lies over a row's VSS rail: a stack of
    cuts from the rail up to the shield, a pad on every metal between, on the M3 grid, where every
    pad keeps its metal's space from other metal and every cut its cut space; ``per_shield`` stacks
    a shield, from its lower left. Returns the stacks drawn."""
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
        if any(not (kdb.Region(c) - metals[1]).is_empty() for c in rail_cuts):
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
                y = box.center().y
                x0 = -(-box.left // XPITCH) * XPITCH
                for x in range(x0, box.right + 1, XPITCH):
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
            drawn += placed
    return drawn


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
    the second cut goes; the net stays joined through the filled metal. Returns the cuts removed."""
    import tech as _tech

    rules = getattr(_tech, "RULES", {})
    removed = 0
    for n in range(1, 8):
        via, below, above = LAYERS.get(f"V{n}"), LAYERS.get(f"M{n}"), LAYERS.get(f"M{n + 1}")
        space = rules.get(f"V{n}", {}).get("space")
        if not (via and below and above and space):
            continue
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
                if b.left >= a.right + space:  # sorted by left edge: none further on is closer
                    break
                if i in gone or j in gone or a.overlaps(b) or not a.enlarged(space - 1, space - 1).overlaps(b):
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
    n_fill = fill_rows(layout, top, std_rows, fills, filled)
    std_lib = kdb.Layout()
    std_lib.read(lib)
    n_ties = edge_ties(layout, top, std_rows, std_lib)
    layout.flatten(top.cell_index(), -1, True)
    for g in filled:
        bridge(layout, top, g, block)
    n_straps = supply_straps(layout, top)
    n_shield = shield_ties(layout, top, shields)
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
        **({"guard ring": ring_info.removeprefix(", guard ring ")} if ring else {}),
    }
    Path(dst + ".post.json").write_text(json.dumps(done, indent=1) + "\n")
    return Path(dst)
