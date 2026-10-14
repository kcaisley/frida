"""Finish an ALIGN layout built from row cells (make_pdk.py's PDK directory) for signoff.

* Standard cells: ALIGN placed abstracts named ``<CELL>_<hash>``; the real library cell goes in
  at the wrapper's offset (``paths.ACCESS_JSON``): between the pads the generator drew (free
  placement), or at the right end with the library filler on the left to the placement grid
  (dense wrapper, standard-cell rows). The library's own text labels are dropped (pin names
  would merge nets after flattening), and so are the router's M2 keep-outs the abstract carried;
  the via pads it left out go in (netcells.align_access).
* Rows: ALIGN places cells on the rows but not always abutted. In every gap inside the block
  the rails, taps, tap implant bands and the N-tap well band are drawn as in a row cell
  (rowcell.rails without the device parts), so supplies run through every row; then narrow
  well gaps are closed (NW_SPACE).
* Labels: ALIGN's pin labels (metal/252) move to the PDK's pin-text layers; pin shapes,
  blockages and abstract layers (datatypes 251/253, layer 255 unless the PDK draws on it, and the PnR's whole-block
  boundary marker 235/5) are removed; shapes are merged and snapped to the manufacturing grid.
* Options (additive, for any block, in a PDK with logic cells and a guard ring): ``fill="decap"``
  puts decap cells (logiccell.decap) in the row gaps wide enough, and writes their devices to
  ``out.gds.extra.sp`` for the LVS source (``flow.layout.signoff.add_post_devices``); ``ring``
  wraps the block in the PDK's guard ring (its ringcell.py), the ring's N-well on ``ring_net``,
  the substrate ring on ``sub_net`` (a port of its own).

Run bound to a PDK (flow/layout/pdkproc.py), with ``STEMS_STD_DENSE`` set as for the ALIGN run;
flow/layout/align/build.py calls ``post``.
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
    MODELS,
    NW_SPACE,
    PIN_TEXT,
    STD_CELLS,
    STD_FILL,
    V1,
    V1_PAIR,
    V2,
    XPITCH,
)

GRID = MFG_GRID
BND = LAYERS["BND"]
NW = LAYERS["NW"]
STD = re.compile(rf"^({'|'.join(re.escape(c) for c in STD_CELLS if c != STD_FILL)})(_\d+)*$", re.IGNORECASE)
LIB_NAME = {c.upper(): c for c in STD_CELLS}  # ALIGN upper-cases cell names: back to the library's
LIB = str(STD_GDS)
ACCESS = json.loads(ACCESS_JSON.read_text())
TEXT = {LAYERS[m][0]: PIN_TEXT[m] for m in PIN_TEXT}  # metal GDS layer -> its pin-text layer


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
        frame = ACCESS[name] if os.environ.get("STEMS_STD_DENSE") else ACCESS[name]["iso"]
        views, keep = netcells.align_access(frame)
        keep = set(keep)  # the router's keep-outs (stdcell.py), not metal
        m2 = cell.shapes(layout.layer(*LAYERS["M2"]))
        for s in [s for s in m2.each() if s.is_box() and (s.box.left, s.box.bottom, s.box.right, s.box.top) in keep]:
            m2.erase(s)
        for pad, bar in views.values():  # the via pads the abstract left out (they would block their bars)
            if pad and bar:
                m2.insert(kdb.Box(*pad))
        if not os.environ.get("STEMS_STD_DENSE"):  # isolated wrapper: pads drawn by the generator (stdcell.py)
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


DECAP_L = (100, 200, 300, 500, 1000)  # gate lengths to choose from: the most gate area that fits


def fill_rows(
    layout: kdb.Layout,
    top: kdb.Cell,
    std_rows: set[int],
    fills: dict[str, kdb.Cell],
    decap: bool = False,
    devices: list | None = None,
) -> int:
    """Rails, taps and well band across the placement gaps of every row; library fillers in
    standard-cell rows (their implant bands differ from the analog rows'). With ``decap``, a
    gap wide enough takes a decap cell instead (its devices appended to ``devices``)."""
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
                for name, w in netcells.fillers(g.width()):
                    t = kdb.Trans(x, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, x, y0 + rowcell.H)
                    top.insert(kdb.CellInstArray(fills[name].cell_index(), t))
                    x += w
                n += 1
                continue
            # orientation: VSS on even rail lines (cells placed R0 on even rows, MX on odd ones)
            t = kdb.Trans(g.left, y0) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, g.left, y0 + rowcell.H)
            if decap:
                import logiccell  # a PDK with logic cells
            fits = [l for l in DECAP_L if decap and logiccell.decap_fingers(g.width(), l) >= 1]
            if decap and fits:
                l = max(fits, key=lambda l: logiccell.decap_fingers(g.width(), l) * l)
                name = f"FILL{len(devices or [])}"
                cell, devs = logiccell.decap(name, g.width(), l, hi=f"{name}_hi", lo=f"{name}_lo")
                devices.extend(devs)
                for r in cell.rects:
                    if r.layer != "BND" and r.kind != "stub" and rowcell.GLAYERS.get(r.layer):
                        top.shapes(layout.layer(*rowcell.GLAYERS[r.layer])).insert(
                            kdb.Box(r.x0, r.y0, r.x1, r.y1).transformed(t)
                        )
                n += 1
                continue
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
            n += 1
    return n


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
    Positions on the M3 grid near the ends where the pads and the trunk keep the M2 space from
    other metal. VSS lines are the even ones. Labels vdd/vss go on the trunks (M3 pin text)."""
    li = lambda ld: layout.layer(*ld)
    sp, hw = M2_SPACE, M3W // 2
    m2 = kdb.Region(top.begin_shapes_rec(li(LAYERS["M2"]))).merged()
    m3 = kdb.Region(top.begin_shapes_rec(li(LAYERS["M3"]))).merged()
    b = kdb.Region(top.begin_shapes_rec(li(BND))).merged().bbox()
    lines = range(b.bottom // rowcell.H, b.top // rowcell.H + 1)
    placed = 0
    for net, parity in (("vss", 0), ("vdd", 1)):
        ys = [k * rowcell.H for k in lines if k % 2 == parity]
        # pads inside the block where the cuts stay on the rail (enclosed 10 nm), else on the rail line
        reach = rowcell.RAIL - V1 // 2 - 10
        ys = [min(max(y, b.bottom + EDGE_PAD[1] + 10), b.top - EDGE_PAD[1] - 10) for y in ys]
        ys = [
            y if abs(y - k * rowcell.H) <= reach else k * rowcell.H
            for y, k in zip(ys, (k for k in lines if k % 2 == parity))
        ]
        span = 15 * XPITCH
        for side in (+1, -1):
            xs = (
                range(b.left + XPITCH, b.left + span, XPITCH)
                if side > 0
                else range(b.right - XPITCH, b.right - span, -XPITCH)
            )
            for x in xs:
                # the trunk encloses its outermost VIA2 (by BAR_END - V2 / 2), past the block if need be
                trunk = kdb.Box(x - hw, min(b.bottom, ys[0] - BAR_END), x + hw, max(b.top, ys[-1] + BAR_END))
                pads = [kdb.Box(x - EDGE_PAD[0], y - EDGE_PAD[1], x + EDGE_PAD[0], y + EDGE_PAD[1]) for y in ys]
                if not (m3 & kdb.Region(trunk).sized(sp)).is_empty():
                    continue
                if any(not (m2 & kdb.Region(p).sized(sp)).is_empty() for p in pads):
                    continue
                top.shapes(li(LAYERS["M3"])).insert(trunk)
                m3.insert(trunk.enlarged(sp, 0))
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
                break
    return placed


def close_wells(layout: kdb.Layout, top: kdb.Cell) -> None:
    li = layout.layer(*NW)
    nw = kdb.Region(top.shapes(li))
    half = NW_SPACE // 2
    nw = nw.sized(half).sized(-half).merged()
    top.shapes(li).clear()
    top.shapes(li).insert(nw)


def post(
    src: str | Path,
    dst: str | Path,
    *,
    fill: str = "plain",
    ring: bool = False,
    ring_net: str = "vdd",
    sub_net: str = "vsub",
) -> Path:
    """Finish ALIGN's GDS ``src`` into ``dst`` (and ``<dst>.extra.sp``); returns ``dst``."""

    src, dst, lib = str(src), str(dst), LIB
    layout = kdb.Layout()
    layout.read(src)
    top = layout.top_cell()
    n_std = insert_stdcells(layout, lib)
    # rows holding standard cells, from the abstracts' placement
    std_rows = set()
    for inst in top.each_inst():
        m = STD.match(inst.cell.name)
        if m and os.environ.get("STEMS_STD_DENSE"):  # dense wrappers only
            std_rows.add(round(inst.bbox().center().y / rowcell.H - 0.5))
    fills = {}
    for name, _ in netcells.STD_FILLS:
        fills[name] = layout.create_cell(name + "_fill")
        fills[name].copy_tree(_lib_cell(lib, name))
    layout.flatten(top.cell_index(), -1, True)
    devices = []
    n_fill = fill_rows(layout, top, std_rows, fills, decap=fill == "decap", devices=devices)
    std_lib = kdb.Layout()
    std_lib.read(lib)
    n_ties = edge_ties(layout, top, std_rows, std_lib)
    layout.flatten(top.cell_index(), -1, True)
    n_straps = supply_straps(layout, top)
    ring_info = ""
    if ring:
        import ringcell  # the PDK's guard ring

        rows, sites = ringcell.wrap(layout, top, kdb, ring_net, sub_net)
        layout.flatten(top.cell_index(), -1, True)
        ring_info = f", guard ring ({rows} rows, {sites} sites)"
    extra = [f"* added by align/post.py ({fill} fill{', ring' if ring else ''})"]
    if ring:
        extra.append("*.DNW")  # NMOS in the deep N-well: extracted as the _dnw models
    if ring and sub_net not in ("vss", "vdd"):
        extra.append(f"*.PORTS {sub_net}")
    for name, pol, d, g, s_, b, w, l in devices:
        extra.append(f"M{name} {d} {g} {s_} {b} {MODELS[pol]} w={w / 1000}u l={l / 1000}u")
    Path(dst + ".extra.sp").write_text("\n".join(extra) + "\n")

    for info in list(layout.layer_infos()):
        li = layout.layer(info)
        if info.layer in TEXT and info.datatype == 252:
            pin_layer = layout.layer(*TEXT[info.layer])
            for shape in top.shapes(li).each():
                if shape.is_text():
                    top.shapes(pin_layer).insert(shape.text)
            layout.clear_layer(li)
        elif (
            (info.layer == 255 and (info.layer, info.datatype) not in LAYERS.values())  # abstract, not a PDK layer
            or info.datatype in (251, 253)
            or (info.layer, info.datatype) == (235, 5)
        ):
            layout.clear_layer(li)
    close_wells(layout, top)
    for c in list(layout.top_cells()):  # an unused helper (the filler copy when no row needed fill)
        if c.cell_index() != top.cell_index():
            layout.prune_cell(c.cell_index(), -1)
    for li in layout.layer_indexes():
        shapes = top.shapes(li)
        texts = [s.text for s in shapes.each() if s.is_text()]
        polygons = kdb.Region(shapes).merged().snapped(GRID, GRID)
        shapes.clear()
        shapes.insert(polygons)
        for text in texts:
            shapes.insert(text)
    layout.write(dst)
    print(
        f"{n_std} standard cells, {n_fill} row gaps filled ({len(devices) // 2} decap fingers), "
        f"{n_straps} supply straps, {n_ties} row-end ties{ring_info}"
    )
    return Path(dst)
