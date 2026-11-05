"""Pin access for the standard cells used next to the analog row cells, from the PDK's ``tech``.

Each signal pin gets one access point on an M2 track (y = PITCH k) with VIA1 and an M2
pin bar. The cells have M1 pins only, and the rules decide the access (the PDK's ``tech`` values):

  * the VIA1 needs M1 at least M1W wide (100 nm) and enclosed BAR_END - V1 / 2 (40 nm) on the
    two ends of the strip. A pin rectangle narrower than that is widened over its whole length
    (an M1 patch M1W wide), so no short jogs appear (G.4);
  * the patch stays M1_SPACE from all other M1 of the cell (the M1 space);
  * on a plate wider than STD_WIDE two cuts are needed (the wide-metal via rules), placed
    V1_PAIR apart along the track;
  * the pins of a cell get distinct tracks, or bars far enough apart.

A cell is padded with the library's filler (STD_FILL, one site) on its left to a multiple of
two sites, the ALIGN placement grid: mirrored pairs then meet cell to cell. Coordinates
below are in the padded cell, the library cell sits at x = ``offset``. The bars stay M2_EDGE
inside the padded outline so neighbours keep the M2 space, and enclose their cuts along the track.

Fillers sit left of the cell (``offset``) and, where a pin would otherwise need a pad, right of it
too (``padded - width - offset``). ``iso`` is the same for a cell that may land next to analog row cells (free placement): at
least ISO_PAD on both sides, where the standard cells' implant and well profile is drawn up
to the outline and stops there (``rowcell.std_pad``). The library cell's own overhangs end
inside the pads, and an analog neighbour sees the profile at its device margin like it sees
another analog cell. No pin comes near the outline, so no access needs a pad.

Writes ``paths.ACCESS_JSON`` (under ``build/``):
{cell: {"width": library width, "padded": padded width, "offset": x of the library cell, "pins": [names in .subckt
order], "access": {pin: {"cuts": [[x, y], ...], "patch": [x0,y0,x1,y1] or null, "bar": [x0,y0,x1,y1],
"pad": [x0,y0,x1,y1] or null}}, "iso": {"padded", "offset", "access"}}}

Run bound to a PDK (flow/layout/pdkproc.py); ``pdkproc.access_points`` calls ``write_access``
when a build needs the file and it is missing.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import sys
from pathlib import Path

import klayout.db as kdb
import tech as _tech
from paths import ACCESS_JSON, STD_GDS, STD_LEF, STD_SPICE
from tech import (
    BAR_END,
    ISO_PAD,
    LAYERS,
    M1_MIN_W,
    M1_SPACE,
    M1W,
    M2_EDGE,
    M2_MIN_LEN,
    M2_SPACE,
    M2W,
    MFG_GRID,
    PITCH,
    STD_CELLS,
    STD_SUPPLY,
    STD_TRACKS,
    STD_WIDE,
    TAP_PITCH,
    V1,
    V1_PAIR,
    XPITCH,
)

PAD = getattr(_tech, "STD_PAD", 2 * XPITCH)  # padded widths: a multiple of this (ALIGN's grid: two M3 pitches)
VIA_M1_W = getattr(_tech, "VIA_M1_W", M1W)  # M1 width a via needs inside a long pin (no line end beside it)
# a library cell's own M2 at least this wide both ways is a plate (output pins, the wide-metal via rule: a
# via near one needs a second): no access touches it; thinner M2 of a pin is joined directly
M2_PLATE = getattr(_tech, "M2_PLATE", None)
# wide metal (a plate) to M2 running along it further than a length: (space, length)
M2_PLATE_SPACE = getattr(_tech, "M2_PLATE_SPACE", (M2_SPACE, 0))


def plate_keep(b: kdb.Box) -> kdb.Box:
    """A plate grown by M2_PLATE_SPACE across each side longer than its run length (else M2_SPACE)."""
    space, run = M2_PLATE_SPACE
    gx = space if b.height() > run else M2_SPACE
    gy = space if b.width() > run else M2_SPACE
    return kdb.Box(b.left - gx, b.bottom - gy, b.right + gx, b.top + gy)


VIA_SPACE = getattr(_tech, "VIA_SPACE", None)  # cut to cut where it exceeds what the M2 pitch leaves
TRACKS = STD_TRACKS  # preferred order: middle of the cell first
WIDE = STD_WIDE  # a plate wider than this needs two cuts (None: never)
M1_HW, M2_HW = VIA_M1_W // 2, M2W // 2
# the M1 a cut lands on, (half width, half height): its line-end enclosure along the track's
# normal (y); where the PDK allows it on either pair of sides (VIA_EOL_ACROSS: VIA1
# enclosure 0 / 0.05), also along x, so a pin shorter than the landing takes the cut without a patch
LANDINGS = [(M1_HW, BAR_END)] + ([(BAR_END, V1 // 2)] if getattr(_tech, "VIA_EOL_ACROSS", False) else [])


def subckt_pins(spice: str, cell: str) -> list[str]:
    """The .subckt pin order of a library cell (continuation lines joined); supplies alone if absent."""
    text = re.sub(r"\n\+", " ", spice)
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+([^\n]*)$", text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).split() if m else list(STD_SUPPLY)


def lef_pins(lef: str, cell: str, layers: bool = False) -> dict[str, list[list[tuple[int, int]]]]:
    """Each pin's port shapes (RECT and POLYGON) as point lists in nm; with ``layers``, as
    (LEF layer, points)."""
    body = re.search(
        rf"^MACRO {re.escape(cell)}\s*\n(.*?)^END {re.escape(cell)}\s*$", lef, re.DOTALL | re.MULTILINE
    ).group(1)
    pins = {}
    for name, pin in re.findall(r"^\s*PIN (\S+)\s*\n(.*?)^\s*END \1\s*$", body, re.DOTALL | re.MULTILINE):
        shapes = []
        for layer, port in re.findall(r"LAYER\s+(\S+)\s*;(.*?)(?=LAYER\s|\Z)", pin, re.DOTALL):
            for kind, nums in re.findall(r"(RECT|POLYGON)\s+([-\d.\s]+?)\s*;", port):
                v = [round(float(n) * 1000) for n in nums.split()]
                if kind == "RECT":
                    x0, y0, x1, y1 = v
                    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                else:
                    pts = list(zip(v[0::2], v[1::2]))
                shapes.append((layer, pts) if layers else pts)
        pins[name] = shapes
    return pins


def candidates(y, own: kdb.Region, other: kdb.Region, *, local: bool = False):
    """Access points on the pin's M1 at track y, best first: (cuts, patch). A cut fits where its
    landing (cut + 40 nm along the strip) lies inside the pin's M1, whatever the pin's outline;
    pins narrower than a cut get a patch; plates wider than 300 nm take two cuts. ``local``: a
    plate is wide where the metal around the cut is (a square WIDE across), not where its band
    along the track is (a thin column joined to a long bar is no plate)."""
    out = []
    for hw, hh in LANDINGS:
        band = (own & kdb.Region(kdb.Box(-(10**6), y - hh, 10**6, y + hh))).merged()
        for p in band.each():
            b = p.bbox()
            if b.height() < 2 * hh or b.width() < M1_MIN_W:
                continue
            if b.width() < VIA_M1_W:  # narrow: widen the whole straight run
                got = _candidate(own, other, b, (b.left + b.right) // 2 // 5 * 5, y) if hh == BAR_END else None
                if got:
                    out.append(got)
                continue
            centre = (b.left + b.right) // 2 // MFG_GRID * MFG_GRID
            piece = own.interacting(kdb.Region(b)).bbox()  # across: the M1's width is its smaller side
            wide = WIDE is not None and (b.width() if hh == BAR_END else min(piece.width(), piece.height())) > WIDE
            for xc in [centre] + [x for x in range(b.left + hw, b.right - hw + 1, 10) if x != centre]:
                if local and WIDE is not None:
                    square = kdb.Box(xc - WIDE // 2, y - WIDE // 2, xc + WIDE // 2, y + WIDE // 2)
                    wide = (kdb.Region(square) - own).is_empty()
                half = V1_PAIR // 2 + hw if wide else hw
                need = kdb.Box(xc - half, y - hh, xc + half, y + hh)
                if (kdb.Region(need) - own).is_empty():
                    out.append((False, [(xc - V1_PAIR // 2, y), (xc + V1_PAIR // 2, y)] if wide else [(xc, y)], None))
        if out:  # the usual landing first
            break
    return [(c, p) for _, c, p in sorted(out, key=lambda o: o[0])]


def _candidate(own, other, b, xc, y):
    """One access point: the cut(s) at xc (and a patch if the M1 is narrower than the cut)."""
    if True:
        patch = None
        if b.width() < VIA_M1_W:  # widen the whole straight run of this column
            column = (own & kdb.Region(kdb.Box(b.left, -(10**6), b.right, 10**6))).merged()
            run = next(q.bbox() for q in column.each() if q.bbox().contains(kdb.Point(xc, y)))
            patch = kdb.Box(xc - M1_HW, run.bottom, xc + M1_HW, run.top)
            if not (kdb.Region(patch).sized(M1_SPACE - 1) & other).is_empty():
                return None
        cuts = [(xc, y)]
        if WIDE is not None and b.width() > WIDE:  # two cuts on a wide plate, both inside it
            cuts = [(xc - V1_PAIR // 2, y), (xc + V1_PAIR // 2, y)]
        return (b.width() < VIA_M1_W, cuts, patch)


FILL_WIDTHS = [w for _, w in getattr(_tech, "STD_FILLS", ((None, getattr(_tech, "STD_FILL_W", XPITCH)),))]


def _fillable(gap: int) -> bool:
    """The library fillers (STD_FILLS) fill ``gap`` exactly."""
    ok = {0}
    for g in range(1, gap + 1):
        if any(g - w in ok for w in FILL_WIDTHS):
            ok.add(g)
    return gap in ok


def iso_frame(width: int, extra: int = 0) -> tuple[int, int]:
    """(padded, offset) of the isolated wrapper: ISO_PAD or more on both sides, on the PAD grid;
    ``extra`` more on the left. The offset is a multiple of TAP_PITCH: the library cell's rail
    contacts must coincide with those of the cells in the neighbouring row, which share the rail."""
    off = -(-ISO_PAD // TAP_PITCH) * TAP_PITCH + extra
    return -(-(off + width + ISO_PAD) // PAD) * PAD, off


def access(gds: kdb.Layout, lef: str, cell: str, pin_order: list[str]) -> dict:
    c = gds.cell(cell)
    m1 = kdb.Region(c.begin_shapes_rec(gds.layer(*LAYERS["M1"]))).merged()
    m2 = kdb.Region(c.begin_shapes_rec(gds.layer(*LAYERS["M2"]))).merged()  # the library's own M2, if any
    width = kdb.Region(c.begin_shapes_rec(gds.layer(*LAYERS["BND"]))).bbox().width()
    pins = lef_pins(lef, cell)
    # a pin only on M2 (output plates): its M1 is what the library's own VIA1 joins to it
    by_layer = lef_pins(lef, cell, layers=True)
    m1_name = by_layer[STD_SUPPLY[1]][0][0]  # the rails are M1
    v1 = kdb.Region(c.begin_shapes_rec(gds.layer(*LAYERS["V1"])))
    plates = kdb.Region(
        [p for p in m2.each() if M2_PLATE is None or not kdb.Region(p).sized(-(M2_PLATE // 2)).is_empty()]
    )
    direct, own2 = {}, {}
    for pin, shapes in by_layer.items():
        if pin not in STD_SUPPLY and all(layer != m1_name for layer, _ in shapes):
            pm2 = kdb.Region([kdb.Polygon([kdb.Point(x, y) for x, y in pts]) for _, pts in shapes])
            pins[pin] = [
                [(b.left, b.bottom), (b.right, b.bottom), (b.right, b.top), (b.left, b.top)]
                for b in (p.bbox() for p in (v1 & pm2).each())
            ]
            own2[pin] = (m2 & pm2) - plates  # its own M2, where it is no plate
            direct[pin] = [p.bbox() for p in own2[pin].each()]
    signal = [p for p in pin_order if p not in STD_SUPPLY]

    def frame(padded, off):
        for patches in (False, True):  # direct accesses where they suffice, else patches for any pin
            for order in itertools.permutations(signal):  # a pin at the cell edge may need its track first
                keep = lambda r: (
                    (r - plates).sized(M2_SPACE - 1)
                    + kdb.Region([plate_keep(p.bbox()).enlarged(-1, -1) for p in (r & plates).each()])
                )
                lib2 = {p: keep(m2 - own2.get(p, kdb.Region())).moved(off, 0) for p in signal}
                got = _assign(order, pins, m1, padded, off, patches, lib2, direct)
                if got:
                    return got
        raise AssertionError(f"{cell}: no access for all pins")

    padded = -(-width // PAD) * PAD
    while not _fillable(padded - width):  # the library fillers must fill the padding exactly
        padded += PAD
    # the dense frame: fillers on the left; where a pin then needs a pad (it reaches across the
    # neighbouring tracks), the first frame with fillers on both sides, or one PAD wider, that
    # needs none
    offset = padded - width
    dense = frame(padded, offset)
    if any(a["pad"] for a in dense.values()):
        for wide in (padded, padded + PAD):
            for off in range(wide - width, -1, -XPITCH):
                if (wide, off) == (padded, offset) or not (_fillable(off) and _fillable(wide - width - off)):
                    continue
                try:
                    got = frame(wide, off)
                except AssertionError:
                    continue
                if not any(a["pad"] for a in got.values()):
                    padded, offset, dense = wide, off, got
                    break
            else:
                continue
            break
    iso = None  # the isolated wrapper (ALIGN's free placement): none where no padding gives access
    for extra in range(0, 4 * TAP_PITCH + 1, TAP_PITCH):  # a cell with M2 of its own may need room beside it
        iso_padded, iso_off = iso_frame(width, extra)
        try:
            iso = frame(iso_padded, iso_off)
            break
        except AssertionError:
            continue
    if iso is None:
        print(f"{cell}: no isolated access (free placement cannot use it)", file=sys.stderr)
    rest = m2 - sum(own2.values(), kdb.Region())  # the library's M2 no access joins: kept clear by routers
    return {
        "width": width,
        "padded": padded,
        "offset": offset,
        "pins": pin_order,
        "access": dense,
        "iso": {"padded": iso_padded, "offset": iso_off, "access": iso},
        **(
            {
                "m2": [
                    [b.left, b.bottom, b.right, b.top, int(not (plates & kdb.Region(b)).is_empty())]
                    for b in (p.bbox() for p in rest.each())
                ]
            }
            if not m2.is_empty()
            else {}
        ),
    }


def reach(y, own: kdb.Region, other: kdb.Region):
    """Access for a pin no track crosses with room for a cut: an M1 patch from the pin out to
    track y (VIA_M1_W wide, at the first position along the pin, from its centre, that keeps
    M1_SPACE to the cell's other M1)."""
    out = []
    for p in own.merged().each():
        b = p.bbox()
        if b.bottom + BAR_END <= y <= b.top - BAR_END or min(abs(y - b.bottom), abs(y - b.top)) > 2 * PITCH:
            continue
        centre = (b.left + b.right) // 2 // MFG_GRID * MFG_GRID
        for xc in [centre] + [x for x in range(b.left + M1_HW, b.right - M1_HW + 1, 10) if x != centre]:
            patch = kdb.Box(xc - M1_HW, min(b.bottom, y - BAR_END), xc + M1_HW, max(b.top, y + BAR_END))
            if (kdb.Region(patch) & own).is_empty() or not (kdb.Region(patch).sized(M1_SPACE - 1) & other).is_empty():
                continue
            out.append(([(xc, y)], patch))
            break
    return out


def _off_m2(got, keep: kdb.Region) -> bool:
    """An access's M2 (bar, pad) stays out of ``keep`` (the library cell's own M2 grown by its space)."""
    return keep.is_empty() or keep.interacting(kdb.Region([kdb.Box(*b) for b in got if b])).is_empty()


def _sides(got, xs: list[int], width: int):
    """A minimum-length bar grown from the cuts to the left, then to the right, inside the cell."""
    (lo, y0, hi, y1), pad = got
    for a in (max(xs) + BAR_END - (hi - lo), min(xs) - BAR_END):
        if M2_EDGE <= a and a + (hi - lo) <= width - M2_EDGE:
            yield [a, y0, a + (hi - lo), y1], pad


def _options(pin, pins, m1, padded, off, patches=False, m2=None, direct=None):
    """Every access of one pin: (y, cuts, patch, bar, pad), preferred first. A pin no track crosses
    reaches one through an M1 patch; with ``patches`` every pin may (after its direct accesses).
    ``m2``: per pin, the library cell's own M2 it keeps clear of (padded frame); ``direct``: per
    pin, its own thin M2 (cell frame), which it may join without a cut."""
    own = m1.interacting(kdb.Region([kdb.Polygon([kdb.Point(x, y) for x, y in s]) for s in pins[pin]]))
    other = m1 - own
    out = []
    for b in (direct or {}).get(pin, ()):  # the pin's own (thin) M2: a bar along it, no cut
        for y in TRACKS:
            if b.bottom <= y - M2_HW and y + M2_HW <= b.top:
                lo, hi = b.left + off, b.right + off
                if hi - lo < M2_MIN_LEN:
                    lo = max(M2_EDGE, min((lo + hi - M2_MIN_LEN) // 2, padded - M2_EDGE - M2_MIN_LEN))
                    hi = lo + M2_MIN_LEN
                out.append((y, [], None, [lo, y - M2_HW, hi, y + M2_HW], None))
    for finder in (candidates, reach):
        for y in TRACKS:
            for cuts, patch in finder(y, own, other):
                got = _bar([x + off for x, _ in cuts], y, padded)
                obstacle = (m2 or {}).get(pin)
                if (
                    got and obstacle is not None and not obstacle.is_empty()
                ):  # past the library's own M2: grown to one side
                    got = next(
                        (g for g in (got, *_sides(got, [x + off for x, _ in cuts], padded)) if _off_m2(g, obstacle)),
                        None,
                    )
                if got:
                    out.append((y, cuts, patch, *got))
        if out and not patches:
            break
    if not out:  # no access at all: a wide plate where the metal around the cut is (``candidates``)
        for y in TRACKS:
            for cuts, patch in candidates(y, own, other, local=True):
                got = _bar([x + off for x, _ in cuts], y, padded)
                obstacle = (m2 or {}).get(pin)
                if got and obstacle is not None and not obstacle.is_empty():
                    got = next(
                        (g for g in (got, *_sides(got, [x + off for x, _ in cuts], padded)) if _off_m2(g, obstacle)),
                        None,
                    )
                if got:
                    out.append((y, cuts, patch, *got))
    # accesses without a pad first: a pad reaches across the neighbouring tracks, which a router
    # that books only along its tracks (ALIGN) does not see
    return sorted(out, key=lambda o: o[4] is not None)


def _clash(a, b) -> bool:
    """Two accesses' M2 too close: bars on one track, or a pad against anything on a neighbouring track."""
    ya, cuts_a, _, bar_a, pad_a = a
    yb, cuts_b, _, bar_b, pad_b = b
    if VIA_SPACE and any(
        abs(p[0] - q[0]) < V1 + VIA_SPACE and abs(p[1] - q[1]) < V1 + VIA_SPACE for p in cuts_a for q in cuts_b
    ):
        return True
    apart = lambda p, q: p[2] + M2_SPACE <= q[0] or q[2] + M2_SPACE <= p[0]
    shapes_a = [bar_a] + ([pad_a] if pad_a else [])
    shapes_b = [bar_b] + ([pad_b] if pad_b else [])
    if ya == yb or abs(ya - yb) < M2W + M2_SPACE:  # one track, or bars too close across (half-pitch pin tracks)
        return any(not apart(p, q) for p in shapes_a for q in shapes_b)
    if abs(ya - yb) == PITCH and (pad_a or pad_b):
        near = [pad_a] if pad_a else []
        return any(not apart(p, q) for p in near for q in shapes_b) or any(
            not apart(p, q) for p in ([pad_b] if pad_b else []) for q in shapes_a
        )
    return False


def _assign(order, pins, m1, padded, off, patches=False, m2=None, direct=None):
    """Depth-first over the pins' accesses (a greedy pick can leave a later pin without a track)."""
    opts = {pin: _options(pin, pins, m1, padded, off, patches, m2, direct) for pin in order}

    def search(i, chosen):
        if i == len(order):
            return chosen
        for o in opts[order[i]]:
            if not any(_clash(o, c) for c in chosen):
                got = search(i + 1, chosen + [o])
                if got:
                    return got
        return None

    picked = search(0, [])
    if not picked:
        return None
    out = {}
    for pin, (y, cuts, patch, bar, pad) in zip(order, picked):
        out[pin] = {
            "cuts": [[x + off, yy] for x, yy in cuts],
            "patch": [patch.left + off, patch.bottom, patch.right + off, patch.top] if patch else None,
            "bar": bar,
            "pad": pad,
        }
    return out


def _bar(xs: list[int], y: int, width: int):
    """M2 for the cuts at track y: (bar, pad). The bar encloses the cuts by BAR_END - V1 / 2 along
    the track; near a cell edge it ends at the cut instead and a pad 2 BAR_END tall over the cut
    gives the enclosure across the track (VIA1 enclosure by M2 on two opposite sides)."""
    lo, hi = min(xs) - BAR_END, max(xs) + BAR_END
    pad = None
    if lo < M2_EDGE:
        lo, pad = min(xs) - M2_HW, [min(xs) - M2_HW, y - BAR_END, max(xs) + M2_HW, y + BAR_END]
    if hi > width - M2_EDGE:
        hi, pad = max(xs) + M2_HW, [min(xs) - M2_HW, y - BAR_END, max(xs) + M2_HW, y + BAR_END]
    if lo < 0 or hi > width:
        return None
    if hi - lo < M2_MIN_LEN:  # minimum area, kept inside the padded cell
        if pad and hi == max(xs) + M2_HW:
            lo = hi - M2_MIN_LEN
        elif pad:
            hi = lo + M2_MIN_LEN
        else:
            mid = (lo + hi) // 2
            lo = max(M2_EDGE, min(mid - M2_MIN_LEN // 2, width - M2_EDGE - M2_MIN_LEN))
            hi = lo + M2_MIN_LEN
        if lo < 0 or hi > width:
            return None
    return [lo, y - M2_HW, hi, y + M2_HW], pad


def write_access(pdk: str, cells: tuple[str, ...] = ()) -> Path:
    """Write the access points of ``pdk``'s standard cells (this process is bound to it) to
    ``paths.ACCESS_JSON`` and return that path: its row cells (``STD_CELLS``) and ``cells``, any
    other of its library's a netlist names. A cell the file already holds keeps its entry (and its
    place: the order indexes the cells through ALIGN); the file is replaced whole."""

    gds = kdb.Layout()
    gds.read(str(STD_GDS))
    lef = STD_LEF.read_text()
    spice = STD_SPICE.read_text()
    data = json.loads(ACCESS_JSON.read_text()) if ACCESS_JSON.exists() else {}
    for cell in dict.fromkeys((*STD_CELLS, *cells)):
        if cell in data or gds.cell(cell) is None:  # known, or no library cell (a netlist's own subcircuit)
            continue
        pins = subckt_pins(spice, cell)
        if any(p not in STD_SUPPLY for p in pins):
            data[cell] = access(gds, lef, cell, pins)
        else:
            w = kdb.Region(gds.cell(cell).begin_shapes_rec(gds.layer(*LAYERS["BND"]))).bbox().width()
            iso_padded, iso_off = iso_frame(w)
            data[cell] = {
                "width": w,
                "padded": w,
                "offset": 0,
                "pins": pins,
                "access": {},
                "iso": {"padded": iso_padded, "offset": iso_off, "access": {}},
            }
    out = ACCESS_JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(f".{out.name}.{os.getpid()}")
    temporary.write_text(json.dumps(data, indent=1) + "\n")
    temporary.replace(out)  # readers see the old file or the new one, never part of one
    for cell, d in data.items():
        print(cell, d["width"], d["padded"], {p: (a["cuts"], a["patch"] is not None) for p, a in d["access"].items()})
    print(f"{pdk}: wrote {out}")
    return out
