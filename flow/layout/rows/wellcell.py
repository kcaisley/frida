"""PMOS whose bulk is a net of its own (a bootstrap's boosted node, say), not the row's VDD, in an
N-well of their own: an island in a cell two standard-cell rows tall or more, its own N tap on the
bulk, kept from every well a neighbour can have by the kit's N-well space to a well of another net
(``NW_SPACE_NET``). ALIGN's MosWell primitive (``flow/layout/primitives/mos.py``) draws it, for the
devices ``flow.circuit.netlists`` gathers by bulk.

The cell's frame (R0, VSS at the bottom) has its rail lines at multiples of H, VSS on the even
ones and VDD on the odd ones, as abutted rows have them:

    0       VSS rail and its tap, as every row cell's
    H       VDD rail: its M1 alone, no tap under it (the well under it is the bulk's)
    ...     the devices (``rowcell.mos_array``) hug the VDD line, from below (the devices in the
            first row) or from above (in the second, mirrored), each terminal on VDD tied into its
            rail as in any PMOS cell
    y_t     the bulk's tap (the kit's ``WELL_TAP``, by default the N tap a VDD rail draws) across
            the VDD line from the devices, or above them past the second line, about midway between
            two rail lines; joined to the bulk's S/D bar by an M3 jumper (``mos_array``'s ``taps``)
    k H     the top line: VSS with its tap (k even), or a rail's M1 alone (k odd: VDD; and every
            line between, its taps left out where the island may reach)

The island encloses the devices' diffusion by WELL_OD (EDGE unless the kit says) and the tap's by
the tap's own enclosure. It keeps the space from the wells across the outer lines (a neighbour's
PMOS body NW_P past its VSS line, a library cell's STD_NW; the well band of a VDD line NW_TOP - H
past it) and beside the cell (a neighbour's VDD well band overhangs its side by NW_OH, a PMOS body
reaches it), each a grid step more than the space, so ``netcells.close_wells`` closes no gap
between them. The cell is the fewest rows the devices and the tap fit in (``FRAMES``).

In a kit whose rails carry no taps the island cuts the rows' VDD wells as a row end does, so each
side of the cell is a row end (``_row_ends``: the library's tie under each VDD line, which
``post.py`` inserts at ``tie_sites``, between pads with the library's profile).
"""

from __future__ import annotations

import rowcell
import tech as _tech
from rowcell import (
    CO,
    CO_OD_END,
    EDGE,
    IMP_OH,
    M1_HW,
    M1_SPACE,
    MFG_GRID,
    NP_TAP,
    NW_OH,
    NW_P,
    NW_TOP,
    PP_TAP,
    RAIL,
    RAIL_IMPLANTS,
    RAIL_MARKS,
    STD_NW,
    TAP_OD,
    TAP_PITCH,
    TAP_Y,
    XPITCH,
    Cell,
    Dev,
    H,
    Run,
)

# the kit's N-well space to a well of another net (its deck's different-potential rule; where it has
# one N-well space for every net, that one)
NW_SPACE_NET = getattr(_tech, "NW_SPACE_NET", None)
# the kit's N tap of a well of its own, where its rails carry none ({"od": the diffusion's layer key,
# "half": its half height, "implant", "implant_half", "implant_end": the implant over it, its half
# height and its reach past the diffusion's ends, "marks": [(layer, half height)], "well": the
# well's enclosure of the diffusion, "m1_half": the M1 bar's half height, "pitch": its contacts'})
WELL_TAP = getattr(_tech, "WELL_TAP", None)
NW_AREA = getattr(_tech, "NW_AREA", 0)
# the island's enclosure of the devices' diffusion: EDGE (OD to a cell edge, the PMOS cells' well
# past it), unless the kit's PMOS cells take their enclosure from the well band's overhang
WELL_OD = getattr(_tech, "WELL_OD", EDGE)
# a kit whose rails carry no taps ties its wells by its tie cell (EDGE_TIE: name, width) at every
# row end, in a row-end cell EDGE_W wide (the tie, then a pad with the library's profile towards
# the analog cells, ``netcells.edge``); the island cuts the rows' wells at its sides as a row end
# does, so the cell keeps a tie at both sides of the row under every VDD line it spans, a pad as
# the row end's either side of it (``tie_sites``, where ``post.py`` inserts the library's tie)
TIE = None if rowcell.RAIL_TAPS else getattr(_tech, "EDGE_TIE", None)
PAD = getattr(_tech, "EDGE_W", 0) - TIE[1] if TIE else 0
ROOM = TIE[1] + 2 * PAD if TIE else 0
LINE_END = getattr(_tech, "LINE_END", 0)
# the frames tried, fewest rows first: (rows, the devices below the first VDD line, the tap past
# their second line rather than across the VDD line)
FRAMES = (
    (2, True, False),
    (2, False, False),
    (3, False, False),
    (3, True, False),
    (3, False, True),
    (4, False, True),
    (4, False, False),
    (4, True, False),
)


def tap_spec() -> dict:
    """The bulk's N tap: the kit's ``WELL_TAP``, else the N tap its VDD rails draw (their
    diffusion, contacts, implant band and markers, the well past it as the rails' well band)."""
    if WELL_TAP is not None:
        return dict(WELL_TAP)
    assert rowcell.RAIL_TAPS and rowcell.RAIL_OD, "a kit whose rails carry no taps names its well tap (WELL_TAP)"
    return {
        "od": "OD",
        "half": TAP_OD,
        "implant": RAIL_IMPLANTS[1],
        "implant_half": H - NP_TAP,
        "implant_end": IMP_OH,
        "marks": list(RAIL_MARKS),
        "well": NW_TOP - (H - TAP_Y + TAP_OD),
        "m1_half": RAIL,
        "pitch": TAP_PITCH,
    }


def _space() -> int:
    """The island's space to another net's well: the kit's, a grid step more."""
    assert NW_SPACE_NET is not None, "the kit's tech names no N-well space to another net's well (NW_SPACE_NET)"
    return NW_SPACE_NET + MFG_GRID


def _window(rows: int) -> tuple[int, int]:
    """The heights the island may span in a cell ``rows`` tall: off the neighbours' wells across
    its outer lines and off its own outer VSS taps."""
    s, near = _space(), min(NW_P, STD_NW)
    lo = max(NW_P, s - near)
    top = rows * H
    hi = min(top - NW_P, top + near - s) if rows % 2 == 0 else top - (NW_TOP - H) - s
    return lo, hi


def _line_items(rects: list[rowcell.Rect], y: int) -> list[rowcell.Rect]:
    """The rails' shapes of the line at ``y`` (0 or H, R0): its M1 rail, tap diffusion, contacts
    and stubs, implant band and markers (none of the cell's body: well, device implant, VT band)."""
    tap = y + TAP_Y if y == 0 else y - TAP_Y
    out = []
    for r in rects:
        mid = (r.y0 + r.y1) // 2
        if r.layer in ("NW", "BND") or r.y0 < y - H // 2 or r.y1 > y + H // 2:
            continue
        if mid in (y, tap):
            out.append(r)
    return out


def _rails_count(width: int, vss: str | None, vdd: str | None) -> int:
    """How many shapes ``rowcell.rails`` draws first in a PMOS row cell ``width`` wide (the
    ``mos_array`` cell's rails, ahead of its devices)."""
    probe = Cell("probe", width)
    rowcell.rails(probe, width, "p", vss, vdd)
    return len(probe.rects)


def _clipped(r: rowcell.Rect, room: int, width: int) -> list[rowcell.Rect]:
    """``r`` kept ``room`` inside the cell's sides (a band across the cell off its tie sites), none
    where nothing is left of it."""
    x0, x1 = max(r.x0, room), min(r.x1, width - room)
    return [rowcell.Rect(r.layer, x0, r.y0, x1, r.y1, r.net, r.kind, r.term)] if x0 < x1 else []


def tie_sites(width: int, rows: int) -> list[tuple[int, int, bool]]:
    """Where the tie cells stand in an island cell ``width`` wide and ``rows`` tall (``TIE``): at
    both sides of the row under each VDD line, (x, y, mirrored) of its origin in the cell's frame,
    the right one mirrored (its origin the cell's right side); none in a kit whose rails carry taps."""
    if not TIE:
        return []
    sides = ((PAD, False), (width - PAD, True))
    return [(x, (j - 1) * H, mirror) for j in range(1, rows + 1, 2) for x, mirror in sides]


def _moved(r: rowcell.Rect, flip: int | None) -> rowcell.Rect:
    """``r`` mirrored about the line at ``flip`` (None: as it is)."""
    y0, y1 = (r.y0, r.y1) if flip is None else (2 * flip - r.y1, 2 * flip - r.y0)
    return rowcell.Rect(r.layer, r.x0, y0, r.x1, y1, r.net, r.kind, r.term)


def _m1_space() -> int:
    """M1's space beside a rail: a wide metal's where the kit gives one (``RULES`` M1
    ``parallel_space``: space, above width, above parallel run length) for a bar as wide as the
    rail, else the end-of-line space where larger than the plain one."""
    rule = getattr(_tech, "RULES", {}).get("M1", {})
    wide = 2 * RAIL
    spaces = [gap for gap, width, run in rule.get("parallel_space", ()) if wide > width and wide > run]
    return max([M1_SPACE, LINE_END, *spaces])


def _band(rows: int, below: bool, line: int) -> tuple[str, int] | None:
    """The implant band (its layer, half height) the island cell draws about the rail ``line``:
    the bottom VSS line's and the VDD line's as every cell's, the second line's where it is the
    top one or the mirrored inner cell's VSS line, none about the others (their rails' M1 alone)."""
    if line == 0 or line == 2 and (rows == 2 or not below):
        return RAIL_IMPLANTS[0], PP_TAP
    if line == 1:
        return RAIL_IMPLANTS[1], H - NP_TAP
    return None


def _tap_line(rows: int, below: bool, past: bool, spec: dict) -> int | None:
    """The tap's line (the cell's frame) in a frame ``rows`` tall, its devices below the VDD line
    (``below``) or above it, the tap across the VDD line from them or, above them, past the second
    line (``past``): between the two rail lines about it, its M1 off their rails (a wide metal's
    space), its implant off their bands where another implant, its well inside the island's window
    (``_window``), as near midway between the lines as that leaves; None where it does not fit."""
    m1, ih, reach = spec["m1_half"], spec["implant_half"], spec["half"] + spec["well"]
    a = 1 if below else 0 if not past else 2  # the line below the tap, the next above it
    if a + 1 > rows:
        return None
    gap = _m1_space()
    lo, hi = _window(rows)
    y_lo = max(a * H + RAIL + gap + m1, lo + reach)
    y_hi = min((a + 1) * H - RAIL - gap - m1, hi - reach)
    for line, side in ((a, 1), (a + 1, -1)):
        band = _band(rows, below, line)
        if band and band[0] != spec["implant"]:
            edge = line * H + side * (band[1] + ih)
            y_lo, y_hi = (max(y_lo, edge), y_hi) if side > 0 else (y_lo, min(y_hi, edge))
    y_lo, y_hi = -(-y_lo // MFG_GRID) * MFG_GRID, y_hi // MFG_GRID * MFG_GRID
    if y_lo > y_hi:
        return None
    mid = (2 * a + 1) * H // 2 // MFG_GRID * MFG_GRID
    return min(max(mid, y_lo), y_hi)


def mos_well(
    name: str,
    devs: list[Dev],
    runs: list[Run],
    bulk: str,
    grid: int = XPITCH,
    vss: str | None = "vss",
    vdd: str | None = "vdd",
    ties: frozenset[str] | None = None,
) -> Cell:
    """PMOS ``devs`` (their fingers in the order ``runs`` gives, ``rowcell.mos_array``) on the
    bulk net ``bulk`` in an N-well of their own (module docstring); ``vss`` and ``vdd`` the rails'
    nets, None where the cell has no such port (the rail unnamed). Raises AssertionError where no
    frame of up to four rows holds them."""
    spec = tap_spec()
    enclose = max(WELL_OD, spec["well"])  # the island past the devices' diffusion and the tap's
    # the island to the cell's sides: a neighbour's well band overhangs them, a tie stands inside
    margin = _space() + NW_OH + ROOM
    failures: list[str] = []
    for widen in range(0, 9 * grid, grid):
        extra = -(-2 * (enclose + margin - EDGE) // grid) * grid + widen
        narrow = False
        for rows, below, past in FRAMES:
            frame = f"{rows} rows, devices {'below' if below else 'above'}, the tap {'past' if past else 'across'}"
            y_t = _tap_line(rows, below, past, spec)
            if y_t is None:
                failures.append(f"{frame}: no line for the tap")
                continue
            flip = None if below else H  # above: the inner cell mirrored about the VDD line
            local = y_t if below else 2 * H - y_t
            inner = rowcell.mos_array(name, "p", devs, runs, grid, vss, vdd, extra=extra, ties=ties, taps={bulk: local})
            body = inner.rects[_rails_count(inner.width, vss, vdd) :]
            od = [_moved(r, flip) for r in body if r.layer == "OD"]  # the devices' diffusion
            ox0, ox1 = min(r.x0 for r in od), max(r.x1 for r in od)
            oy0, oy1 = min(r.y0 for r in od), max(r.y1 for r in od)
            reach = spec["half"] + spec["well"]
            island = (ox0 - enclose, min(oy0 - WELL_OD, y_t - reach), ox1 + enclose, max(oy1 + WELL_OD, y_t + reach))
            lo, hi = _window(rows)
            if island[1] < lo or island[3] > hi:
                failures.append(f"{frame}: the island {island[1]}..{island[3]} not in {lo}..{hi}")
                continue
            area = (island[2] - island[0]) * (island[3] - island[1])
            if island[0] < margin or island[2] > inner.width - margin or area < NW_AREA:
                narrow = True  # too narrow: wider, centred
                break
            return _draw(name, inner, rows, below, bulk, spec, island, y_t, vss, vdd)
        if not narrow:
            raise AssertionError(f"{name}: no frame holds the devices and their tap ({'; '.join(failures)})")
    raise AssertionError(f"{name}: its island stays too close to the cell's sides")


def _draw(
    name: str,
    inner: Cell,
    rows: int,
    below: bool,
    bulk: str,
    spec: dict,
    island: tuple[int, int, int, int],
    y_t: int,
    vss: str | None,
    vdd: str | None,
) -> Cell:
    """The island cell from the inner PMOS row cell ``inner`` (``mos_well``)."""
    width = inner.width
    c = Cell(name, width)
    n_rails = _rails_count(width, vss, vdd)
    rail_rects, body = inner.rects[:n_rails], inner.rects[n_rails:]
    flip = None if below else H
    # a line's taps: their diffusion, contacts and stubs, and the markers over them
    marks = {layer for layer, _ in RAIL_MARKS}
    tap = lambda r: r.layer in ("OD", "CO", *marks) or r.kind == "stub"
    vdd_tap = {id(r) for r in _line_items(rail_rects, H) if tap(r)}
    bottom = _line_items(rail_rects, 0)
    # mirrored, the inner cell's VSS line is the second line: inside a frame taller than two rows,
    # its taps left out (the island may reach it)
    inside = {id(r) for r in bottom if tap(r)} if not below and rows > 2 else set()
    for r in rail_rects:
        if r.layer in ("NW", "BND") or id(r) in vdd_tap or id(r) in inside:
            continue
        c.rects.append(_moved(r, flip))
    for r in body:
        c.rects.append(_moved(r, flip))
    if not below:  # the bottom VSS line, as the inner cell has it
        c.rects += [_moved(r, None) for r in bottom]
    # the lines above: their M1 rails; the top one, where VSS, with its taps
    first = 2 if below else 3
    for j in range(first, rows + 1):
        net = vss if j % 2 == 0 else vdd
        if j == rows and j % 2 == 0:
            c.rects += [_moved(r, rows * H // 2) for r in bottom]
        else:
            c.add("M1", 0, j * H - RAIL, width, j * H + RAIL, net, "pin" if net else "drawing")
    # the island and its tap
    ix0, iy0, ix1, iy1 = island
    c.add("NW", ix0, iy0, ix1, iy1)
    tx0, tx1 = ix0 + spec["well"], ix1 - spec["well"]
    half, pitch = spec["half"], spec["pitch"]
    c.add(spec["od"], tx0, y_t - half, tx1, y_t + half)
    end, ih = spec["implant_end"], spec["implant_half"]
    c.add(spec["implant"], tx0 - end, y_t - ih, tx1 + end, y_t + ih)
    for layer, mark in spec.get("marks", ()):
        c.add(layer, tx0 - end, y_t - mark, tx1 + end, y_t + mark)
    joined = any(r.layer == "V1" and (r.y0 + r.y1) // 2 == y_t and r.net == bulk for r in c.rects)
    inset = max(pitch // 2, CO // 2 + CO_OD_END)  # the outer contacts' centres from the diffusion's ends
    xs = list(range(tx0 + inset, tx1 - inset + 1, pitch))
    assert xs, f"{name}: no room for the tap's contacts"
    for x in xs:
        c.add("CO", x - CO // 2, y_t - CO // 2, x + CO // 2, y_t + CO // 2, bulk)
        c.add("M1", x - M1_HW, y_t - spec["m1_half"], x + M1_HW, y_t + spec["m1_half"], bulk, "stub")
    # the M1 bar under the jumper's landing (``mos_array``'s taps): over the tap, on to the landing
    landing = [r for r in c.rects if r.layer == "V1" and (r.y0 + r.y1) // 2 == y_t and r.net == bulk]
    bx0 = min([tx0, *(r.x0 - M1_HW for r in landing)])
    bx1 = max([tx1, *(r.x1 + M1_HW for r in landing)])
    c.add("M1", bx0, y_t - spec["m1_half"], bx1, y_t + spec["m1_half"], bulk, "drawing" if joined else "pin")
    _row_ends(c, width, rows)
    c.add("BND", 0, 0, width, rows * H)
    return c


def _row_ends(c: Cell, width: int, rows: int) -> None:
    """The rows' ends at the cell's sides (``ROOM`` wide, where a kit's rails carry no taps): there
    the cell's rails' M1 alone and pads with the library's profile (``rowcell.std_pad``, as the
    row-end cell's, ``netcells.edge``), which a row cell abuts outside: in the row under each VDD
    line either side of the tie site (``tie_sites``), the library tie's overhangs ending in them,
    in every other row across the whole row end; everything else of the cell (each shape by its
    middle) cut back to the row ends' inner edges, where their well ends with no overhang (none of
    the cell's rows has a well band there for one to join)."""
    sites = tie_sites(width, rows)
    if not sites:
        return
    kept = []
    for r in c.rects:
        inside = 0 <= (r.y0 + r.y1) // 2 < rows * H
        kept += _clipped(r, ROOM, width) if r.layer != "M1" and inside else [r]
    c.rects[:] = kept
    tie = TIE[1]
    pieces = {
        True: (
            (0, PAD, "right"),
            (PAD + tie, ROOM, "left"),
            (width - ROOM, width - PAD - tie, "right"),
            (width - PAD, width, "left"),
        ),
        False: ((0, ROOM, "right"), (width - ROOM, width, "left")),
    }
    tied = {y // H for _, y, _ in sites}
    for k in range(rows):  # each row's, mirrored on the odd rows as the rows are
        pad = Cell("pad", width)
        for x0, x1, side in pieces[k in tied]:
            rowcell.std_pad(pad, x0, x1, side)
        for r in pad.rects:
            if r.layer == "NW" and r.x0 >= ROOM and r.x1 <= width - ROOM:
                continue  # a well band's overhang past a row end's inner edge
            if r.layer == "OD" and (r.y0 + r.y1) // 2 == H - TAP_Y:  # the VDD rail's diffusion, where
                # the rails have some: the well's overhang short of the inner edge, inside the well
                x0 = r.x0 + NW_OH if r.x0 == width - ROOM else r.x0
                r = rowcell.Rect(r.layer, x0, r.y0, r.x1 - NW_OH if r.x1 == ROOM else r.x1, r.y1)
            y0, y1 = (k * H + r.y0, k * H + r.y1) if k % 2 == 0 else ((k + 1) * H - r.y1, (k + 1) * H - r.y0)
            c.rects.append(rowcell.Rect(r.layer, r.x0, y0, r.x1, y1, r.net, r.kind, r.term))
