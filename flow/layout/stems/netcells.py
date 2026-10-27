"""Cells of a row design, one per netlist instance, for generators that place fixed cells.

Reads a flat SPICE netlist (MOS lines with w and nf, w total or per finger as the PDK writes
it: mosline.py; X lines naming a library standard cell) and draws every instance as a fixed cell
with its nets already named: transistors through rowcell.mos, standard cells as the library cell
plus the VIA1 / M2 pin bars at their access points (stdcell_access.py). ALIGN draws the same cells
through its own PDK (flow/layout/align), and post.py finishes its layouts with these. The PDK's layout directory
(``tech``, ``paths``) goes on the path ahead of this one.

    netlist = parse("build/layout/netlists/comp_frida1_stdcells.sp")
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import mosline
import rowcell
import tech as _tech
from paths import ACCESS_JSON, STD_GDS  # noqa: F401  (STD_GDS: re-exported to the tool scripts)
from tech import EDGE_CUTS, EDGE_PAD, MODELS, STD_FILL, STD_FILL_W, STD_SUPPLY, STD_TEXT_LAYERS, V1, V1_PAIR, XPITCH

W_PER_FINGER = mosline.w_per_finger()  # the bound PDK's netlists give w per finger with nf
EDGE_TIE = getattr(_tech, "EDGE_TIE", None)  # (library tie cell, its width): in every row end
# a library cell's M2 plate: (space, run length) of wide metal
PLATE_SPACE, PLATE_RUN = getattr(_tech, "M2_PLATE_SPACE", (_tech.M2_SPACE, 0))

# the row end's supply stacks sit EDGE_STEP and 2 EDGE_STEP in: a site step, or more where the M2
# pad would reach past the cell (where two VIA1 on the rail need a wide pad)
EDGE_STEP = -(-EDGE_PAD[0] // XPITCH) * XPITCH
EDGE_W = getattr(_tech, "EDGE_W", 3 * EDGE_STEP)  # row end cell width
STD_FILLS = getattr(_tech, "STD_FILLS", ((STD_FILL, STD_FILL_W),))  # library fillers (name, width)


def fillers(gap: int) -> list[tuple[str, int]]:
    """Library fillers that fill ``gap`` exactly, the fewest cells."""
    best: dict[int, list[tuple[str, int]]] = {0: []}
    for w in range(1, gap + 1):
        options = [best[w - fw] + [(name, fw)] for name, fw in STD_FILLS if fw <= w and w - fw in best]
        if options:
            best[w] = min(options, key=len)
    if gap not in best:
        raise ValueError(f"no library fillers fill {gap} nm")
    return best[gap]


ACCESS = json.loads(ACCESS_JSON.read_text()) if ACCESS_JSON.exists() else {}


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def align_access(frame: dict) -> tuple[dict[str, tuple], list[tuple[int, int, int, int]]]:
    """ALIGN's view of a frame's access bars between its M2 tracks (half-pitch pins), which
    its router cannot use: per such pin the via's M2 pad and an M2 pin bar on one of the tracks beside
    it (the pin ALIGN routes to, touching the pad), and a keep-out on the track on the other side,
    which the pad touches (wires there must end an M2 space past it). The sides are chosen so that
    no bar comes near another pin's metal or keep-out. ``{pin: (pad, bar)}``, ``(None, None)`` for
    a pin with no free side (align/pdk/stdcell.py lifts it to an M3 stub, with keep-outs along the
    whole bar on both tracks), and the keep-outs. Pins on the M2 tracks get ``(None, bar)``: their
    bar, longer where it reaches a second M3 grid point that way. align/post.py removes the keep-outs
    again and draws the pads of the pins between the tracks."""
    pitch, hw, sp, end = _tech.PITCH, _tech.M2W // 2, _tech.M2_SPACE, _tech.BAR_END
    off = {p: a for p, a in frame["access"].items() if (a["bar"][1] + a["bar"][3]) // 2 % pitch}
    fixed = [tuple(b) for p, a in frame["access"].items() if p not in off for b in (a["bar"], a["pad"]) if b]
    pads = {}
    for p, a in off.items():
        xs, y = [x for x, _ in a["cuts"]], (a["bar"][1] + a["bar"][3]) // 2
        pads[p] = (min(xs) - end, y - hw, max(xs) + end, y + hw)

    def attempt(sides):
        taken, keep, views = fixed + list(pads.values()), [], {}
        for (p, a), side in zip(off.items(), sides):
            pad, y = pads[p], (pads[p][1] + pads[p][3]) // 2
            mid, half = (pad[0] + pad[2]) // 2, max(_tech.M2_MIN_LEN, pad[2] - pad[0]) // 2
            x0 = min(max(_tech.M2_EDGE, mid - half), frame["padded"] - _tech.M2_EDGE - 2 * half)
            yt, yk = y + side * pitch // 2, y - side * pitch // 2
            bar = (x0, yt - hw, x0 + 2 * half, yt + hw)
            ko = (pad[0] - sp, yk - hw, pad[2] + sp, yk + hw)
            grown = (bar[0] - sp, bar[1] - sp, bar[2] + sp, bar[3] + sp)
            if (
                pitch <= yt <= rowcell.H - pitch
                and not any(_overlap(grown, t) for t in taken if t != pad)
                and not any(_overlap(bar, k) for k in keep)
                and not any(_overlap(ko, t) for t in taken if t != pad)
            ):
                views[p] = (pad, bar)
                taken.append(bar)
                keep.append(ko)
            else:
                x0, _, x1, _ = a["bar"]
                views[p] = (None, None)
                keep += [(x0 - sp, yy - hw, x1 + sp, yy + hw) for yy in (y - pitch // 2, y + pitch // 2)]
        return views, keep

    tries = [attempt(s) for s in itertools.product((1, -1), repeat=len(off))]
    views, keep = max(tries, key=lambda t: sum(bar is not None for _, bar in t[0].values()))
    # every pin bar ALIGN routes to spans two of its M3 grid points where its track leaves room
    # (with one, a route passing on M3 there cuts the pin off)
    grid, w = getattr(_tech, "M3_PITCH", _tech.XPITCH), frame["padded"]
    bars = {p: tuple(a["bar"]) for p, a in frame["access"].items() if p not in off}
    bars.update({p: bar for p, (_, bar) in views.items() if bar})
    taken = fixed + list(pads.values()) + list(bars.values())
    for p, bar in bars.items():
        x0, y0, x1, y1 = bar
        if len(range(-(-(x0 + end) // grid) * grid, x1 - end + 1, grid)) >= 2:
            continue
        right, left = -(-(x1 - end + 1) // grid) * grid + end, (x0 + end - 1) // grid * grid - end
        own = {bar, pads.get(p), tuple(frame["access"][p]["pad"] or ())}
        for new in sorted(((x0, y0, right, y1), (left, y0, x1, y1)), key=lambda b: b[2] - b[0]):
            grown = (new[0] - sp, y0 - sp, new[2] + sp, y1 + sp)
            if (
                _tech.M2_EDGE <= new[0]
                and new[2] <= w - _tech.M2_EDGE
                and not any(_overlap(grown, t) for t in taken if t not in own)
                and not any(_overlap(new, k) for k in keep)
            ):
                taken[taken.index(bar)] = new
                bars[p] = new
                break
    for p in frame["access"]:
        views[p] = (views.get(p, (None, None))[0], bars.get(p))
    return views, keep


@dataclass
class Inst:
    name: str
    kind: str  # "mos" or a standard cell name
    nets: dict[str, str]
    model: str = ""
    w: int = 0
    l: int = 0
    nf: int = 0

    @property
    def pol(self) -> str:
        return "p" if self.model.lower() == MODELS["p"].lower() else "n"


def split(src: str, parts: dict[str, int]) -> str:
    """``mosline.split`` in the bound PDK's width convention: a floorplan's ``split``."""
    return mosline.split(src, parts, W_PER_FINGER)


def per_finger(src: str) -> str:
    """``mosline.per_finger`` in the bound PDK's width convention: each MOS width per finger and
    all its fingers in nf (as ALIGN reads ``w`` and ``nf``)."""
    return mosline.per_finger(src, W_PER_FINGER)


def floorplan_netlist(floorplan: str | Path, pdk: str, netlist: str | Path | None = None) -> tuple[str, str]:
    """A floorplan's design name (its file name) and its netlist for ``pdk``, with its ``split``
    applied. The netlist is ``netlist`` where given (a runner's own), else the floorplan's
    ``netlist`` path with ``{pdk}`` filled in."""

    floorplan = Path(floorplan)
    fp = json.loads(floorplan.read_text())
    path = Path(netlist) if netlist else floorplan.parent / fp["netlist"].format(pdk=pdk)
    src = path.read_text()
    check_groups(fp, {f[0] for f in map(str.split, src.splitlines()) if f and f[0][0] in "MmXx"})
    return floorplan.stem, split(src, fp.get("split", {}))


def check_groups(fp: dict, devices: set[str]) -> None:
    """Check a floorplan's ``groups`` (ALIGN's primitives, ``<kind>_<n>`` -> devices): every
    device is in the netlist (``devices``: its instance names) and in one group only, and a
    group's devices sit in one row or, split, each part in one row. No ``groups``: valid."""

    parts = fp.get("split", {})
    row_of = {cell: k for k, row in enumerate(fp["rows"]) for cell in row}
    owner: dict[str, str] = {}
    for group, members in fp.get("groups", {}).items():
        for dev in members:
            if dev not in devices:
                raise ValueError(f"group {group}: {dev} is not in the netlist")
            if dev in owner:
                raise ValueError(f"{dev} is in groups {owner[dev]} and {group}")
            owner[dev] = group
        n = {parts.get(dev, 1) for dev in members}
        if len(n) != 1:
            raise ValueError(f"group {group}: its devices are split into different numbers of parts")
        n = n.pop()
        for k in range(n):
            cells = [dev if n == 1 else f"{dev}_{chr(ord('a') + k)}" for dev in members]
            rows = {row_of.get(cell) for cell in cells}
            if None in rows or len(rows) != 1:
                raise ValueError(f"group {group}: {', '.join(cells)} are not placed in one row")


def parse(src: str | Path) -> tuple[str, list[str], list[Inst]]:
    """Instances of a flat netlist (a path, or SPICE text). MOS lines give ``w`` and the finger
    count ``nf`` (``mosline``: ``w`` total or per finger, as the bound PDK writes it); ``Inst.w``
    is the width per finger."""

    text = Path(src).read_text() if isinstance(src, Path) else src
    name, ports, insts = "", [], []
    for line in text.splitlines():
        f = line.split()
        if not f or f[0].startswith("*"):
            continue
        if f[0].lower() == ".subckt":
            name, ports = f[1], f[2:]
        elif f[0][0] in "Mm":
            p = mosline.params(f)
            insts.append(
                Inst(
                    f[0],
                    "mos",
                    dict(zip("DGSB", f[1:5], strict=True)),
                    f[5],
                    mosline.finger_width(p, W_PER_FINGER),
                    mosline.nm(p["l"]),
                    mosline.fingers(p) * int(p.get("m", 1)),
                )
            )
        elif f[0][0] in "Xx":
            cell = f[-1]
            insts.append(Inst(f[0], cell, dict(zip(ACCESS[cell]["pins"], f[1:-1], strict=True))))
    return name, ports, insts


def mos_cell(inst: Inst, grid: int = XPITCH) -> rowcell.Cell:
    n = inst.nets
    return rowcell.mos(
        inst.name,
        inst.pol,
        inst.l,
        inst.w,
        inst.nf,
        n["D"],
        n["G"],
        n["S"],
        grid=grid,
        dev=inst.name,
        vss="vss",
        vdd="vdd",
    )


def std_abstract(inst: Inst) -> rowcell.Cell:
    """The routing view of a standard cell instance: outline, M1 rails as supply pins, pin
    access (VIA1, M2 bar). The library filler pads the cell on its left to the placement grid
    (drawn by ``draw``)."""
    data = ACCESS[inst.kind]
    w = data["padded"]
    c = rowcell.Cell(inst.name, w)
    for y, pin in ((0, STD_SUPPLY[1]), (rowcell.H, STD_SUPPLY[0])):
        c.add("M1", 0, y - rowcell.RAIL, w, y + rowcell.RAIL, inst.nets[pin], "pin")
    for pin, a in data["access"].items():
        net = inst.nets[pin]
        if a["patch"]:
            c.add("M1", *a["patch"], net)
        for x, y in a["cuts"]:
            c.add("V1", x - V1 // 2, y - V1 // 2, x + V1 // 2, y + V1 // 2, net)
        if a["pad"]:  # a pseudo pin, so routers see it (it reaches across the neighbouring tracks)
            c.add("M2", *a["pad"], net + "__pad", "pin")
        c.add("M2", *a["bar"], net, "pin")
    off = data["offset"]
    for x0, y0, x1, y1, plate in data.get("m2", ()):  # the library cell's own M2: a keep-out for the routers
        # (a stub: drawn by none, blocked by all); a plate grown by the wide-metal space beyond the
        # routers' M2 space across its sides longer than the run length
        gx = PLATE_SPACE - _tech.M2_SPACE if plate and y1 - y0 > PLATE_RUN else 0
        gy = PLATE_SPACE - _tech.M2_SPACE if plate and x1 - x0 > PLATE_RUN else 0
        c.add("M2", x0 + off - gx, y0 - gy, x1 + off + gx, y1 + gy, f"{inst.name}__keep", "stub")
    c.add("BND", 0, 0, w, rowcell.H)
    return c


def std_fill(w: int) -> rowcell.Cell:
    """Standard-cell row filler: the library's filler cells (drawn by ``draw``)."""
    c = rowcell.Cell(f"stdfill_{w}", w)
    for y, net in ((0, "vss"), (rowcell.H, "vdd")):
        c.add("M1", 0, y - rowcell.RAIL, w, y + rowcell.RAIL, net, "pin")
    c.add("BND", 0, 0, w, rowcell.H)
    return c


def edge(w: int = EDGE_W, std: bool = False) -> rowcell.Cell:
    """Row end with the supply via stacks: VSS (y = 0) to an M3 trunk at x = EDGE_STEP, VDD (y = H)
    at x = 2 EDGE_STEP. EDGE_CUTS VIA1 per rail (two where the rail is wide), an M2
    pad, one VIA2 under the trunk. ``std``: for standard-cell rows (library fillers inside, see ``draw``).
    A PDK whose rails carry no taps (EDGE_TIE) gets its library tie cell at the outer end (x = 0,
    drawn by ``draw``), then library fillers (``std``) or a pad with the standard cells' profile
    towards the analog cells."""
    if EDGE_TIE:
        tie_w = EDGE_TIE[1]
        c = std_fill(w)
        if not std:
            rowcell.std_pad(c, tie_w, w, "left")
    else:
        c = std_fill(w) if std else filler(w)
    c.name = f"{'std' if std else ''}edge_{w}"
    for y, x, net in ((0, EDGE_STEP, "vss"), (rowcell.H, 2 * EDGE_STEP, "vdd")):
        for k in range(EDGE_CUTS):
            cx = x + (2 * k - (EDGE_CUTS - 1)) * V1_PAIR // 2
            c.add("V1", cx - V1 // 2, y - V1 // 2, cx + V1 // 2, y + V1 // 2, net)
        c.add("M2", x - EDGE_PAD[0], y - EDGE_PAD[1], x + EDGE_PAD[0], y + EDGE_PAD[1], net)
    return c


def filler(w: int) -> rowcell.Cell:
    """Rails, taps and well band only: closes an analog row up to the block width."""
    c = rowcell.Cell(f"fill_{w}", w)
    rowcell.rails(c, w, "n")  # NMOS-type: only the N-tap well band; the device implant and VT are dropped
    c.rects = [
        r
        for r in c.rects
        if not (r.layer in rowcell.VT["n"] or (r.layer == "NP" and (r.y0, r.y1) == rowcell.DEV_IMP["n"]))
    ]
    return c


def cell_of(inst: Inst, grid: int = XPITCH) -> rowcell.Cell:
    return mos_cell(inst, grid) if inst.kind == "mos" else std_abstract(inst)


def widths(src: str | Path) -> dict[str, int]:
    """Each instance's row cell width (nm): what a floorplan places for it."""

    return {inst.name: cell_of(inst).width for inst in parse(src)[2]}


def area(src: str | Path) -> float:
    """The instances' own area (um2), unplaced: each one's row cell, its width (``widths``) by the
    row height."""

    return sum(widths(src).values()) * _tech.H * 1e-6


STD_DROP_LAYERS = getattr(_tech, "STD_DROP_LAYERS", set())  # (layer, datatype) of the library cells not placed
# layer -> (y0, y1): library cells' layers cut back to the rows' own bands (where the library's well and
# implants reach 1.37 um into the next row, where an analog row's devices may be)
STD_CLIP = getattr(_tech, "STD_CLIP", {})


def drop_labels(layout, cell) -> None:
    """A library cell without its labels (pin names would merge nets once flattened): the
    PDK's label layers cleared, every text object on any other layer removed, the layers
    the PDK leaves out of placed library cells (STD_DROP_LAYERS) cleared, and those it clips
    (STD_CLIP) cut to their band."""
    import klayout.db as kdb

    cells = [cell] + [layout.cell(i) for i in cell.called_cells()]
    clip = {rowcell.GLAYERS[name]: band for name, band in STD_CLIP.items()}
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        label_layer = info.layer in STD_TEXT_LAYERS or (info.layer, info.datatype) in STD_DROP_LAYERS
        band = clip.get((info.layer, info.datatype))
        for cc in cells:
            shapes = cc.shapes(li)
            if label_layer:
                shapes.clear()
                continue
            for s in [s for s in shapes.each() if s.is_text()]:
                shapes.erase(s)
            if band:
                kept = kdb.Region(shapes) & kdb.Region(kdb.Box(-(10**9), band[0], 10**9, band[1]))
                shapes.clear()
                shapes.insert(kept)


def _lib_cell(layout, kdb, std_lib, name):
    lib_cell = layout.cell(name + "_lib")
    if lib_cell is None:
        lib_cell = layout.create_cell(name + "_lib")
        lib_cell.copy_tree(std_lib.cell(name))
        drop_labels(layout, lib_cell)
    return lib_cell


def close_wells(layout, kdb, top) -> None:
    """Close the N-well gaps and notches of a flat ``top`` no wider than the well space (NW_SPACE):
    a row padded by a filler narrower than it leaves a notch between a PMOS cell's well and the
    row end's (a library profile, EDGE_TIE)."""
    li = layout.layer(*_tech.LAYERS["NW"])
    half = _tech.NW_SPACE // 2
    nw = kdb.Region(top.shapes(li)).sized(half).sized(-half).merged()
    top.shapes(li).clear()
    top.shapes(li).insert(nw)


def draw(layout, kdb, cell: rowcell.Cell, inst: Inst | None = None, std_lib=None):
    """Draw a cell into a klayout Layout; standard cells and std fillers get the library cells inside."""
    kc = rowcell.to_klayout(cell, layout, kdb)
    end = cell.width
    if EDGE_TIE and cell.name.startswith(("edge_", "stdedge_")):  # the tie cell at the outer end
        kc.insert(kdb.CellInstArray(_lib_cell(layout, kdb, std_lib, EDGE_TIE[0]).cell_index(), kdb.Trans(0, 0)))
        if cell.name.startswith("edge_"):
            return kc
        _fill(layout, kdb, kc, std_lib, EDGE_TIE[1], end)
        return kc
    if inst is not None and inst.kind != "mos":
        data = ACCESS[inst.kind]
        end = data["offset"]
        kc.insert(kdb.CellInstArray(_lib_cell(layout, kdb, std_lib, inst.kind).cell_index(), kdb.Trans(end, 0)))
        _fill(layout, kdb, kc, std_lib, end + data["width"], data["padded"])  # fillers right of it, if any
    elif not cell.name.startswith(("stdfill_", "stdedge_")):
        return kc
    _fill(layout, kdb, kc, std_lib, 0, end)
    return kc


def _fill(layout, kdb, kc, std_lib, x0: int, x1: int) -> None:
    """Library fillers from x0 to x1 in the klayout cell kc."""
    x = x0
    for name, w in fillers(x1 - x0):
        kc.insert(kdb.CellInstArray(_lib_cell(layout, kdb, std_lib, name).cell_index(), kdb.Trans(x, 0)))
        x += w
