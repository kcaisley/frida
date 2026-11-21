"""A block's supply rail lines as the converter's top level reaches them: drawn after ALIGN, the post
step (``flow.layout.post.rail_pins``: each line apart, each piece of it a pin with its supply's label)
and the pins (``flow.layout.pins``, which keep their places), and the layout step's check of them
(``flow.layout.step.supply_lines``).

The top level reaches a piece of a rail line where it touches the layout's left or right edge (its
own row rails abut it there), or from above, where metal is free over it. ALIGN routes M1 across a
line where its view has no rail (a gap between cells, which the post step fills after it, the gap's
rails cut back from ALIGN's M1, ``post._clear_of``), and past a row's last cell; a piece between two
such cuts touches neither edge, and where other nets' metal, a shield or a capacitor array lies over
it, nothing reaches it from above.

- ``join`` makes every piece reachable, in this order: each cut in a line bridged on the line
  itself, a stack of cuts on the pieces at either side of it and a bar between them along the line,
  on the lowest metal it fits on below the kit's landing metals (the converter's routes): the line
  continuous, no strap; where no bridge fits, a piece out of reach (none it is joined to touches an
  edge) joined to the nearest line of its supply with a piece in reach, a short wire across the rows
  between them on the lowest metal it fits on (the least exception to supplies joined by name alone,
  ``post``); else a strap's site on it recorded, a cut's place and the metals free over it.
- ``reach`` is the check: each piece's reach, ``edge`` (it touches an edge), ``joined`` (its metal
  joins it to a piece that does), ``site`` (a site on it with every metal free over it up to the
  kit's lowest landing metal), else None: out of reach.

Every shape keeps its metal's space and line-end space from other nets' and every cut its space
from other cuts, as a landing's (``flow.layout.pins``: its ``_Space``, ``_Search._pads``,
``_joined``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from klayout import db

from flow.layout.pins import Kit, _connectivity, _joined, _Search, _Space, kit

LOG = logging.getLogger("flow.layout.rails")

SUPPLIES = ("vdd", "vss")
TRIES = 8  # the places tried for a bridge's stack on each piece beside a cut, nearest the cut first
DETOUR_PAIRS = 9  # the pairs of them a bridge beside the line is tried from, the shortest first
JOIN_TRIES = 80  # and for a join's wire along the pieces it may leave from


@dataclass
class Line:
    """A rail line: its supply, its y and its pieces on M1 (database units), left to right."""

    net: str
    y: int
    pieces: list[db.Box]


def rail_lines(layout: db.Layout, top: db.Cell, tech: Any) -> list[Line]:
    """The layout's rail lines: each y a supply's label stands at on M1's pin text (``post.rail_pins``
    labels every piece), and the line's pieces, its M1 across the rail's whole height (``RAIL``) and
    at least a site wide (``XPITCH``: no wire crossing it), labelled or not."""
    text = getattr(tech, "PIN_TEXT", {}).get("M1") or tech.LAYERS.get("M1.PIN") or tech.LAYERS["M1"]
    ys: dict[int, str] = {}
    labels = layout.find_layer(*text)
    for shape in top.shapes(labels).each() if labels is not None else ():
        if shape.is_text() and shape.text.string.lower() in SUPPLIES:
            ys.setdefault(shape.text.y, shape.text.string.lower())
    if not ys:
        return []
    index = layout.find_layer(*tech.LAYERS["M1"])
    m1 = db.Region(top.begin_shapes_rec(index)).merged() if index is not None else db.Region()
    edge, rail = top.bbox(), tech.RAIL
    least = getattr(tech, "XPITCH", 2 * rail)
    found = []
    for y, net in sorted(ys.items()):
        band = db.Region(db.Box(edge.left, y - rail, edge.right, y + rail))
        pieces = [
            box
            for box in (p.bbox() for p in (m1 & band).merged().each())
            if box.height() >= 2 * rail and box.width() >= least
        ]
        found.append(Line(net, y, sorted(pieces, key=lambda box: box.left)))
    return found


def _cut(kit_: Kit, below: int, x: int, y: int) -> db.Box:
    size = kit_.cut(below)[0]
    return db.Box(x - size // 2, y - size // 2, x - size // 2 + size, y - size // 2 + size)


def _stack(kit_: Kit, space: _Space, net: str, x: int, y: int, metal: int) -> list[tuple[str, db.Box]] | None:
    """A stack of cuts at (x, y) from the net's M1 up to ``metal`` and a pad on each metal between
    that holds its cuts by their enclosures (a landing's, ``pins._Search``); None where a cut keeps
    no space from another, the M1 holds no cut, or a pad keeps no space from another net."""
    shapes: list[tuple[str, db.Box]] = []
    for below in range(1, metal):
        cut = _cut(kit_, below, x, y)
        if not space.clear(net, f"V{below}", cut, kit_.cut(below)[1]):
            return None
        shapes.append((f"V{below}", cut))
    end, side = kit_.cut(1)[2:]
    first = shapes[0][1]
    if not any(space.held(net, "M1", first.enlarged(a, b)) for a, b in ((end, side), (side, end))):
        return None
    finder = _Search(kit_, space, net, metal, db.Trans.R0, db.Box(), False)
    for m in range(2, metal):
        held = [kit_.cut(c)[2:] for c in (m - 1, m)]
        cut = next(box for name, box in shapes if name == f"V{m}")
        pad = next((p for p in finder._pads(m, cut, held) if space.fits(net, f"M{m}", p, kit_.space(m))), None)
        if pad is None:
            return None
        shapes.append((f"M{m}", pad))
    return shapes


def _bar(kit_: Kit, metal: int, a: tuple[int, int], b: tuple[int, int]) -> db.Box:
    """A bar on ``metal`` from the cut below it at ``a`` to the one at ``b`` (on one horizontal or
    vertical line): as wide as the metal and as the cut and its enclosure, past each cut by its
    enclosure, as long as the metal's area asks."""
    size, _gap, end, side = kit_.cut(metal - 1)
    half = kit_.up(-(-max(kit_.width(metal), size + 2 * side) // 2))
    along_x = a[1] == b[1]
    lo, hi = (min(a[0], b[0]), max(a[0], b[0])) if along_x else (min(a[1], b[1]), max(a[1], b[1]))
    lo, hi = lo - size // 2 - end, hi - size // 2 + size + end
    short = -(-kit_.area(metal) // (2 * half)) - (hi - lo)
    if short > 0:
        grow = kit_.up(-(-short // 2))
        lo, hi = lo - grow, hi + grow
    if along_x:
        return db.Box(lo, a[1] - half, hi, a[1] + half)
    return db.Box(a[0] - half, lo, a[0] + half, hi)


def _detour(kit_: Kit, metal: int, a: tuple[int, int], b: tuple[int, int], dy: int) -> list[db.Box]:
    """A bridge's bar on ``metal`` beside the line, ``dy`` from it, where something lies on the line
    between the cuts at ``a`` and ``b`` (on the line): a stub from each cut to the bar, the corners
    flush, and the bar between."""
    size, _gap, end, side = kit_.cut(metal - 1)
    half = kit_.up(-(-max(kit_.width(metal), size + 2 * side) // 2))
    (xa, y), (xb, _) = sorted((a, b))
    lo, hi = y - size // 2 - end, y - size // 2 + size + end
    lo, hi = (lo, y + dy + half) if dy > 0 else (y + dy - half, hi)
    stubs = [db.Box(x - half, lo, x + half, hi) for x in (xa, xb)]
    return [db.Box(xa - half, y + dy - half, xb + half, y + dy + half), *stubs]


def _drawn(
    kit_: Kit, space: _Space, net: str, metal: int, a: tuple[int, int], b: tuple[int, int], wires: list[db.Box]
) -> list[tuple[str, db.Box]] | None:
    """A stack at ``a`` and at ``b`` up to ``metal`` (``_stack``) and the ``wires`` on it between them
    (``_bar``, ``_detour``), every gap they leave with the net's own metal narrower than its space
    filled (``pins._joined``); None where any of it does not fit."""
    layer, gap, drawn = f"M{metal}", kit_.space(metal), len(space.drawn)
    try:
        for wire in wires:
            if not space.clear_beyond(net, layer, wire, gap):
                return None
            space.drawn.append((net, layer, wire))
        shapes = [(layer, wire) for wire in wires]
        for x, y in (a, b):
            stack = _stack(kit_, space, net, x, y, metal)
            if stack is None:
                return None
            space.drawn += [(net, name, box) for name, box in stack]
            shapes = [*stack, *shapes]
    finally:
        del space.drawn[drawn:]
    return _joined(kit_, space, net, shapes)


def _places(kit_: Kit, piece: db.Box, toward: int, count: int) -> list[int]:
    """Where a cut from M1 may stand along ``piece``'s middle line (inside it by its enclosure), on
    the grid, a cut and its space apart, the nearest ``toward`` first; ``count`` of them."""
    size, gap, end, _side = kit_.cut(1)
    lo, hi = piece.left + size // 2 + end, piece.right - size + size // 2 - end
    lo, hi = kit_.up(lo), hi // kit_.grid * kit_.grid
    if hi < lo:
        return []
    step = kit_.up(size + gap)
    if toward >= hi:
        return list(range(hi, lo - 1, -step))[:count]
    if toward <= lo:
        return list(range(lo, hi + 1, step))[:count]
    start = min(kit_.up(toward), hi)
    found = sorted(range(start - (start - lo) // step * step, hi + 1, step), key=lambda x: abs(x - toward))
    return found[:count]


def _metals(kit_: Kit) -> list[int]:
    """The metals a bridge or a join may take: above M1, below the kit's landing metals."""
    cap = min(kit_.landing) if kit_.landing else max(kit_.metals) + 1
    return [m for m in kit_.metals if 1 < m < cap]


def _bridge(
    kit_: Kit, space: _Space, line: Line, left: db.Box, right: db.Box
) -> tuple[int, list[tuple[str, db.Box]], list[db.Box]] | None:
    """The bridge of the cut between ``left`` and ``right`` (``join``): on the lowest metal it fits on,
    a bar along the line (the shortest first), else one beside it where something lies on the line
    (``_detour``: the nearest the line first, within half a row of it, from the places nearest the
    cut); its metal, shapes and wires, None where none fits."""
    xs = _places(kit_, left, left.right, TRIES)
    xr = _places(kit_, right, right.left, TRIES)
    pairs = sorted(((a, b) for a in xs for b in xr), key=lambda pair: pair[1] - pair[0])
    rows = getattr(kit_.tech, "H", 0)
    for metal in _metals(kit_):
        for a, b in pairs:
            wires = [_bar(kit_, metal, (a, line.y), (b, line.y))]
            shapes = _drawn(kit_, space, line.net, metal, (a, line.y), (b, line.y), wires)
            if shapes is not None:
                return metal, shapes, wires
        pitch = kit_.up(kit_.width(metal) + kit_.space(metal))
        half = kit_.up(-(-max(kit_.width(metal), kit_.cut(metal - 1)[0] + 2 * kit_.cut(metal - 1)[3]) // 2))
        offsets = sorted(
            (sign * k * pitch for k in range(1, max(1, (rows // 2 - half) // pitch) + 1) for sign in (1, -1)), key=abs
        )
        for dy in offsets:
            for a, b in pairs[:DETOUR_PAIRS]:
                wires = _detour(kit_, metal, (a, line.y), (b, line.y), dy)
                shapes = _drawn(kit_, space, line.net, metal, (a, line.y), (b, line.y), wires)
                if shapes is not None:
                    return metal, shapes, wires
    return None


def _join(
    kit_: Kit, space: _Space, line: Line, piece: db.Box, targets: list[tuple[Line, db.Box]]
) -> tuple[int, Line, list[tuple[str, db.Box]], list[db.Box]] | None:
    """A join of ``piece`` (``join``) to one of ``targets`` (a piece in reach of another line of its
    supply), the nearest line first, on the lowest metal it fits on: a stack on each and a wire
    straight across between them; its metal, the line it joins, its shapes and wire, None where
    none fits."""
    for other, box in sorted(targets, key=lambda target: abs(target[0].y - line.y)):
        lo, hi = max(piece.left, box.left), min(piece.right, box.right)
        if hi <= lo:
            continue
        shared = db.Box(lo, piece.bottom, hi, piece.top)
        xs = _places(kit_, shared, (lo + hi) // 2, JOIN_TRIES)
        for metal in _metals(kit_):
            for x in xs:
                wires = [_bar(kit_, metal, (x, line.y), (x, other.y))]
                shapes = _drawn(kit_, space, line.net, metal, (x, line.y), (x, other.y), wires)
                if shapes is not None:
                    return metal, other, shapes, wires
    return None


def _site(kit_: Kit, space: _Space, line: Line, piece: db.Box) -> tuple[db.Box, list[str]] | None:
    """A strap's site on ``piece``: a cut up from it whose pad on M2 keeps its space from other nets,
    with the most metals free over it from M2 up; its cut and those metals, None where no cut fits."""
    best: tuple[db.Box, list[str]] | None = None
    end = kit_.cut(1)[2]
    for x in _places(kit_, piece, piece.center().x, JOIN_TRIES):
        cut = _cut(kit_, 1, x, line.y)
        if not space.clear(line.net, "V1", cut, kit_.cut(1)[1]):
            continue
        if not space.fits(line.net, "M2", cut.enlarged(end, end), kit_.space(2)):
            continue
        free = _free(kit_, space, cut)
        if best is None or len(free) > len(best[1]):
            best = (cut, free)
    return best


def _free(kit_: Kit, space: _Space, box: db.Box) -> list[str]:
    """The metals from M2 up with nothing over ``box``, up to the first that has something."""
    free = []
    for metal in kit_.metals:
        if metal < 2:
            continue
        if space.over(f"M{metal}", box):
            break
        free.append(f"M{metal}")
    return free


def _boxes(boxes: list[db.Box]) -> db.Region:
    region = db.Region()
    for box in boxes:
        region.insert(box)
    return region


def _um(box: db.Box, um: float) -> list[float]:
    return [round(box.left * um, 4), round(box.bottom * um, 4), round(box.right * um, 4), round(box.top * um, 4)]


def join(gds: Path, pdk: str) -> list[dict[str, Any]]:
    """Make every rail piece of the layout ``gds`` reachable (the module's docstring), drawn into it
    (its largest top cell, written back). Returns each line's record (GDS coordinates, um): its supply
    and y, its bridges (each its metal and its bar's box), its joins (each the piece, the line it
    joins, its metal and its wire's box) and its sites (each a cut's box and the metals free over it);
    empty where the layout has no rail lines."""
    kit_ = kit(pdk)
    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    lines = rail_lines(layout, top, kit_.tech)
    if not lines:
        return []
    um = layout.dbu
    space = _connectivity(layout, top, pdk, list(SUPPLIES))
    space.ends = {f"M{m}": kit_.ends(m) for m in kit_.metals if kit_.ends(m)}
    record: dict[tuple[str, int], dict[str, Any]] = {
        (line.net, line.y): {"net": line.net, "y_um": round(line.y * um, 4)} for line in lines
    }
    count = len(space.drawn)

    def draw(net: str, shapes: list[tuple[str, db.Box]]) -> None:
        space.drawn += [(net, name, box) for name, box in shapes]
        for name, box in shapes:
            top.shapes(layout.layer(*kit_.tech.LAYERS[name])).insert(box)

    half = getattr(kit_.tech, "H", 4 * kit_.tech.RAIL) // 2
    for line in lines:
        # the metal along the line (within half a row of it): a cut a bridge already spans (the post
        # step's, ``post._rail_bridge``) is left as it is
        edge = top.bbox()
        window = _regions(layout, top, kit_, db.Box(edge.left, line.y - half, edge.right, line.y + half))
        for left, right in pairwise(line.pieces):
            if not (_flood(window, kit_.metals, db.Region(left)) & db.Region(right)).is_empty():
                continue
            found = _bridge(kit_, space, line, left, right)
            if found is None:
                continue
            metal, shapes, wires = found
            draw(line.net, shapes)
            for name, box in shapes:
                window[name].insert(box)
                window[name].merge()
            bar = _boxes(wires).bbox()
            record[(line.net, line.y)].setdefault("bridges", []).append({"metal": f"M{metal}", "box_um": _um(bar, um)})
    how = reach(layout, top, kit_, lines)
    for line in lines:
        for index, piece in enumerate(line.pieces):
            if how[(line.net, line.y)][index] is not None:
                continue
            targets = [
                (other, box)
                for other in lines
                if other.net == line.net and other.y != line.y
                for box, there in zip(other.pieces, how[(other.net, other.y)], strict=True)
                if there in ("edge", "joined")
            ]
            joined = _join(kit_, space, line, piece, targets)
            entry = record[(line.net, line.y)]
            if joined is not None:
                metal, other, shapes, wires = joined
                draw(line.net, shapes)
                wire = wires[0]
                entry.setdefault("joins", []).append(
                    {
                        "piece_um": [round(piece.left * um, 4), round(piece.right * um, 4)],
                        "joined_to": round(other.y * um, 4),
                        "metal": f"M{metal}",
                        "box_um": _um(wire, um),
                    }
                )
                how = reach(layout, top, kit_, lines)
                continue
            site = _site(kit_, space, line, piece)
            where = f"{line.net} {line.y * um:g} [{piece.left * um:g}, {piece.right * um:g}] um"
            if site is None:
                LOG.warning(f"rails: {where} out of reach: no bridge, join or strap site fits")
                continue
            cut, free = site
            entry.setdefault("sites", []).append({"site_um": _um(cut, um), "free_above": free})
            LOG.warning(
                f"rails: {where}: no bridge or join fits; a strap's site, free above: {', '.join(free) or 'none'}"
            )
    if len(space.drawn) > count:
        layout.write(str(gds))
    return list(record.values())


def _regions(layout: db.Layout, top: db.Cell, kit_: Kit, window: db.Box | None = None) -> dict[str, db.Region]:
    """Each metal's and cut's shapes (merged), within ``window`` where given."""
    regions = {}
    for metal in kit_.metals:
        for name in (f"M{metal}", f"V{metal}"):
            pair = kit_.tech.LAYERS.get(name)
            index = layout.find_layer(*pair) if pair else None
            region = db.Region(top.begin_shapes_rec(index)).merged() if index is not None else db.Region()
            regions[name] = region & db.Region(window) if window is not None else region
    return regions


def _flood(regions: dict[str, db.Region], metals: list[int], start: db.Region) -> db.Region:
    """The M1 joined through metal (each metal through its cuts to the next) to the M1 ``start``."""
    got = {f"M{m}": db.Region() for m in metals}
    got["M1"] = regions["M1"].interacting(start)
    counts = None
    while counts != (now := tuple(region.count() for region in got.values())):
        counts = now
        for below, above in pairwise(metals):
            cuts = regions[f"V{below}"].interacting(got[f"M{below}"]) + regions[f"V{below}"].interacting(
                got[f"M{above}"]
            )
            got[f"M{above}"] = regions[f"M{above}"].interacting(cuts) + got[f"M{above}"]
            got[f"M{below}"] = regions[f"M{below}"].interacting(cuts) + got[f"M{below}"]
            got[f"M{above}"].merge()
            got[f"M{below}"].merge()
    return got["M1"]


def reach(
    layout: db.Layout,
    top: db.Cell,
    kit_: Kit,
    lines: list[Line],
    sites: dict[tuple[str, int], list[db.Box]] | None = None,
) -> dict[tuple[str, int], list[str | None]]:
    """Each line's pieces' reach (the module's docstring), by the metal as drawn: ``edge``, ``joined``,
    ``site`` (one of ``sites``, cut boxes by line, on it with every metal free over it from M2 up to
    the kit's lowest landing metal) or None."""
    edge = top.bbox()
    regions = _regions(layout, top, kit_)
    found: dict[tuple[str, int], list[str | None]] = {}
    for net in SUPPLIES:
        mine = [line for line in lines if line.net == net]
        touching = _boxes([p for line in mine for p in line.pieces if p.left <= edge.left or p.right >= edge.right])
        reached = _flood(regions, kit_.metals, touching) if not touching.is_empty() else db.Region()
        for line in mine:
            how: list[str | None] = []
            for piece in line.pieces:
                if piece.left <= edge.left or piece.right >= edge.right:
                    how.append("edge")
                elif not (reached & db.Region(piece)).is_empty():
                    how.append("joined")
                elif any(
                    db.Region(piece).interacting(db.Region(cut)).count() and _clear_up(kit_, regions, cut)
                    for cut in (sites or {}).get((line.net, line.y), [])
                ):
                    how.append("site")
                else:
                    how.append(None)
            found[(line.net, line.y)] = how
    return found


def continuous(layout: db.Layout, top: db.Cell, kit_: Kit, line: Line) -> bool:
    """Whether ``line`` runs from the layout's left edge to its right as one conductor along it: its
    pieces joined by the metal within half a row of it (its bridges; not a join to another line)."""
    edge = top.bbox()
    if not line.pieces or line.pieces[0].left > edge.left or line.pieces[-1].right < edge.right:
        return False
    if len(line.pieces) == 1:
        return True
    half = getattr(kit_.tech, "H", 4 * kit_.tech.RAIL) // 2
    window = db.Box(edge.left, line.y - half, edge.right, line.y + half)
    reached = _flood(_regions(layout, top, kit_, window), kit_.metals, db.Region(line.pieces[0]))
    return all(not (reached & db.Region(piece)).is_empty() for piece in line.pieces)


def check(gds: Path, pdk: str, joined: list[dict[str, Any]] | None = None) -> list[dict[str, Any]] | None:
    """The layout ``gds``'s rail lines (GDS coordinates, um): each its supply, y and pieces' x extents
    (``rail_lines``), its extent, whether it runs edge to edge as one conductor (``continuous``) and
    each piece's reach (``reach``), with what ``join`` drew on it (``joined``: its bridges, joins and
    strap sites); None where the layout has no rail lines. A piece out of reach a warning."""
    kit_ = kit(pdk)
    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    lines = [line for line in rail_lines(layout, top, kit_.tech) if line.pieces]
    if not lines:
        return None
    um = layout.dbu
    drawn = {(entry["net"], round(entry["y_um"] / um)): entry for entry in joined or []}
    sites = {
        key: [db.Box(*(round(v / um) for v in site["site_um"])) for site in entry.get("sites", [])]
        for key, entry in drawn.items()
    }
    found = reach(layout, top, kit_, lines, sites)
    records, out = [], []
    for line in lines:
        pieces = [[round(p.left * um, 4), round(p.right * um, 4)] for p in line.pieces]
        how = found[(line.net, line.y)]
        entry = {
            "net": line.net,
            "y_um": round(line.y * um, 4),
            "pieces_um": pieces,
            "x_um": [pieces[0][0], pieces[-1][1]],
            "edges": continuous(layout, top, kit_, line),
            "reach": how,
            **{key: value for key, value in drawn.get((line.net, line.y), {}).items() if key not in ("net", "y_um")},
        }
        records.append(entry)
        out += [
            f"{line.net} {entry['y_um']:g} {piece}" for piece, there in zip(pieces, how, strict=True) if there is None
        ]
    if out:
        LOG.warning(f"rails: supply pieces out of the top level's reach (um): {'; '.join(out)}")
    return records


def _clear_up(kit_: Kit, regions: dict[str, db.Region], cut: db.Box) -> bool:
    """Whether every metal from M2 up to the kit's lowest landing metal is free over ``cut``."""
    cap = min(kit_.landing) if kit_.landing else max(kit_.metals)
    return all((regions[f"M{m}"] & db.Region(cut)).is_empty() for m in kit_.metals if 2 <= m <= cap)
