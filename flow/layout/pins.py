"""A block's pins as the converter's top level takes them, drawn after ALIGN: each signal reached
from above on an upper metal, the ports its generator lands on its outline at known places, and
the record of where each one is (the layout step's ``pins``).

- An edge pin (``flow.layout.hdl21align.edge_pins``: a port on a side of the outline, at a spot
  along it or mirrored with another port about the outline's centre line across the side) is
  wiring, never placement: from a point of the port's own wiring a stack of cuts up to the landing
  metal and on it a wire straight to the side, as wide as the converter's routes (twice the
  metal's width), its end the landing, a square of that width (longer where the metal's area asks)
  flush with the side.
- Every other signal is lifted: at a point of its wiring (its label's first, so a capacitor array's
  inputs stay centred on their tracks) a stack of cuts up to the landing metal and a landing pad
  there; where none fits (wiring under a capacitor array's shield) it stays as ALIGN drew it,
  recorded with the metals free over it.
- A landing's metal is the lowest of the kit's ``PIN_METALS`` (its ``layout/tech.py``: the metals
  the converter's double-width routes take) on which the route and the landing keep their space
  from every other net, with nothing of the block over the landing on any metal above: the lowest
  above everything the block draws there. Every pad and wire keeps its metal's space from other
  nets' metal and, where the kit gives its metal a line-end rule (``end_of_line`` in its
  ``RULES``), its line-end space both ways: every line end around it from it, and every line end
  it makes from every other shape; every cut its space from every other cut. A shielded edge pin (``EdgePin.shield``:
  a top plate's, whose wire would couple to the plates' routes it runs over) lands within
  ``SHIELD_WITHIN_NM`` of its spot on the highest landing metal whose metal under the wire is free
  of other signals, and where another signal's metal lies under the wire on any metal, a strip of
  the block's ground on that metal under it, as far past the wire's sides as the wire stands over
  the highest of them (its fringe's reach), a stack of cuts tying it down to the ground's metal
  (recorded beside the pin, ``shield``); where none fits, it lands as any edge pin, with a warning.
- A net's label moves to its landing, the only one it keeps, so the top level reaches it there.

``land`` draws them into the layout's GDS and gives the record: the outline (its boundary layer's
box: the frame every box is in, its lower left the origin), the kit's landing metals, and each
port's net, use, layer, box (um), side (as drawn: the converter mirrors a block's second copy,
which flips its left and right), the metals free over it, how it was made (``edge``, ``lifted``,
``as laid out``, ``not in the layout``), the metal its route leaves the port's wiring on, its
mirror, and a shielded one's shield (its net, layer, box and the metal its tie leaves the ground's
wiring on); one left as drawn also the site of a cut up from it nearest its label with room on the
metal above, and the metals free over that site; a supply's is its rail lines (the layout step adds
them, ``flow.layout.step.supply_lines``), each a pin the converter's power grid joins.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from klayout import db

LOG = logging.getLogger("flow.layout.pins")

SUPPLY_USES = ("power", "ground")
# the frame a side's landing is found in, its side the top (KLayout's rotations about the origin)
_TO_TOP = {"top": db.Trans.R0, "right": db.Trans.R90, "bottom": db.Trans.R180, "left": db.Trans.R270}
LOWEST = 2  # the lowest metal a route leaves a port's wiring on: its routes', above the devices' M1
_TRIES = 4000  # the points tried for an edge pin on one metal, in their order
_LIFT_TRIES = 600  # and for a lifted one, nearest its label first
# how far along its side from its spot a shielded edge pin may land (nm, the layouts' database unit)
SHIELD_WITHIN_NM = 2000


@dataclass
class Kit:
    """A kit's numbers a landing takes (database units, its grid's): its layers, each metal's width,
    space and area, each cut's size, space and enclosures, and its landing metals."""

    tech: Any
    grid: int
    metals: list[int]
    landing: tuple[int, ...]
    # its conductors' heights and thicknesses (um; its ``kpex/stack.json``), where it gives them
    stack: dict[str, dict[str, float]] = field(default_factory=dict)

    def label_layer(self, metal: int) -> tuple[int, int]:
        """Where a metal's labels go: its pin text, else its pin layer, else the metal."""
        name = f"M{metal}"
        found = getattr(self.tech, "PIN_TEXT", {}).get(name) or self.tech.LAYERS.get(f"{name}.PIN")
        return found or self.tech.LAYERS[name]

    def label_layers(self, metal: int) -> set[tuple[int, int]]:
        """Every layer a metal's labels may be on (``flow.layout.kpex.technology``'s)."""
        name = f"M{metal}"
        found = (
            self.tech.LAYERS[name],
            self.tech.LAYERS.get(f"{name}.PIN"),
            getattr(self.tech, "PIN_TEXT", {}).get(name),
        )
        return {tuple(pair) for pair in found if pair}

    def width(self, metal: int) -> int:
        return self.tech.RULES[f"M{metal}"]["width"]

    def ends(self, metal: int) -> tuple[tuple[int, int, int], ...]:
        """Metal ``metal``'s line-end rules (its ``end_of_line``): each (space, below, extension), a
        line end (an edge shorter than ``below`` between two convex corners) keeping ``space`` from
        every other edge in front of it, as wide as the end and ``extension`` past either side."""
        return tuple(tuple(rule) for rule in self.tech.RULES.get(f"M{metal}", {}).get("end_of_line", ()))

    def height(self, upper: int, lower: int) -> int | None:
        """How far metal ``upper``'s bottom stands over metal ``lower``'s top (database units, whole
        grid steps); None where the kit gives no stack."""
        a, b = self.stack.get(f"M{upper}"), self.stack.get(f"M{lower}")
        if not a or not b:
            return None
        return self.up(round((a["z"] - b["z"] - b["thickness"]) * 1000))

    def space(self, metal: int) -> int:
        return self.tech.RULES[f"M{metal}"]["space"]

    def area(self, metal: int) -> int:
        return self.tech.RULES[f"M{metal}"].get("area") or 0

    def cut(self, below: int) -> tuple[int, int, int, int]:
        """The cut between metal ``below`` and the next: its size, its space, its enclosure on two
        opposite sides and on the other two (a cut the kit gives none the largest it gives)."""
        rule = self.tech.RULES[f"V{below}"]
        enclosure = rule.get("enclosure")
        if not enclosure:
            known = [r["enclosure"] for key, r in self.tech.RULES.items() if key[0] == "V" and r.get("enclosure")]
            enclosure = max(known, default=(0, 0))
        end, side = enclosure[0], enclosure[1] if len(enclosure) > 1 else enclosure[0]
        return rule["cut"], rule["space"], self.up(end), self.up(side)

    def up(self, value: int) -> int:
        """``value`` up to the grid."""
        return -(-value // self.grid) * self.grid

    def half_wide(self, metal: int) -> int:
        """Half the width of a route the converter takes on ``metal``: twice the metal's width, and
        no narrower than a cut from below and its enclosure; whole grid steps."""
        cut, _space, end, _side = self.cut(metal - 1)
        return self.up(max(self.width(metal), (cut + 2 * end + 1) // 2))

    def length(self, metal: int) -> int:
        """A landing's length on ``metal``: its route's width, longer where the metal's area asks; a
        whole number of grid steps either side of its middle."""
        wide = 2 * self.half_wide(metal)
        return max(wide, 2 * self.up(-(-self.area(metal) // (2 * wide))))


def kit(pdk: str) -> Kit:
    """``pdk``'s numbers (its ``pdk.<pdk>.layout.tech``)."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    metals = sorted(int(key[1:]) for key in tech.LAYERS if re.fullmatch(r"M\d+", key) and tech.LAYERS[key])
    where = getattr(tech, "__file__", None)
    stack = Path(where).parents[1] / "kpex" / "stack.json" if where else None
    conductors = json.loads(stack.read_text())["conductors"] if stack and stack.is_file() else {}
    return Kit(tech, getattr(tech, "MFG_GRID", 5), metals, tuple(getattr(tech, "PIN_METALS", ())), conductors)


class _Index:
    """A region's pieces as boxes in a box tree, found by place."""

    def __init__(self, region: db.Region) -> None:
        self._layout = db.Layout()
        self._cell = self._layout.create_cell("index")
        self._layer = self._layout.layer(1, 0)
        shapes = self._cell.shapes(self._layer)
        for polygon in region.each():
            for piece in polygon.decompose_trapezoids():
                shapes.insert(piece)

    def touching(self, box: db.Box) -> db.Region:
        found = db.Region()
        it = self._cell.begin_shapes_rec_touching(self._layer, box)
        while not it.at_end():
            found.insert(it.shape().polygon.transformed(it.trans()))
            it.next()
        return found

    def near(self, box: db.Box, space: int) -> bool:
        """Whether a piece lies closer to ``box`` than ``space`` (over it, where ``space`` is 0)."""
        query = box.enlarged(space - 1) if space > 0 else box.enlarged(-1)
        found = self.touching(query)
        if found.is_empty():
            return False
        return not (found & db.Region(box).sized(space) if space > 0 else found & db.Region(box)).is_empty()


class _Space:
    """The layout's metals and cuts (the actual frame), each net's own, and what the landings drew."""

    def __init__(self, regions: dict[str, db.Region], own: dict[str, dict[str, db.Region]]) -> None:
        self.regions, self.own = regions, own
        self.drawn: list[tuple[str, str, db.Box]] = []  # net, layer, box
        self.supplies: tuple[str, ...] = ()  # the supplies' nets, by the ports' uses
        self.grounds: tuple[str, ...] = ()  # and the grounds' among them
        self.ends: dict[str, tuple[tuple[int, int, int], ...]] = {}  # each metal's line-end rules (Kit.ends)
        self._all: dict[str, _Index] = {}
        self._others: dict[tuple[str, str], _Index] = {}
        self._own: dict[tuple[str, str], _Index] = {}

    def own_region(self, net: str, layer: str) -> db.Region:
        return self.own.get(net, {}).get(layer, db.Region())

    def _index(self, net: str | None, layer: str, mine: bool = False) -> _Index:
        if net is None:
            if layer not in self._all:
                self._all[layer] = _Index(self.regions.get(layer, db.Region()))
            return self._all[layer]
        store = self._own if mine else self._others
        if (net, layer) not in store:
            own = self.own_region(net, layer)
            store[(net, layer)] = _Index(own if mine else self.regions.get(layer, db.Region()) - own)
        return store[(net, layer)]

    def clear(self, net: str, layer: str, box: db.Box, space: int) -> bool:
        """Whether ``box`` on ``layer`` keeps ``space`` from every other net's shapes (a cut layer's:
        from every other cut, its net's own too)."""
        cut = layer.startswith("V")
        if self._index(None if cut else net, layer).near(box, space):
            return False
        reach = db.Region(box).sized(space)
        for n, name, other in self.drawn:
            if name == layer and (cut or n != net) and not (reach & db.Region(other)).is_empty():
                return False
        return True

    def fits(self, net: str, layer: str, box: db.Box, space: int) -> bool:
        """Whether ``box``, a new shape of ``net`` on metal ``layer``, keeps ``space`` from every other
        net's shapes (``clear``) and its metal's line-end space (``ends``) both ways: every line end
        around it (another net's, or the net's own on a piece it does not touch) from it, and every
        line end it makes with the net's own metal from every other shape."""
        if not self.clear(net, layer, box, space):
            return False
        rules = self.ends.get(layer)
        if not rules:
            return True
        reach = max(gap + below + extension for gap, below, extension in rules)
        window = box.enlarged(reach, reach)
        others = self._index(net, layer).touching(window)
        mine = self._index(net, layer, mine=True).touching(window)
        for n, name, other in self.drawn:
            if name == layer and other.touches(window):
                (mine if n == net else others).insert(other)
        # clipped to the window: a cut piece's new edge lies on its border, its front outward
        frame, added = db.Region(window), db.Region(box)
        mine = (mine & frame).merged()
        others = ((others & frame) + mine.not_interacting(added)).merged()
        if not (_end_zones(_line_ends(others), rules) & added).is_empty():
            return False
        before = set(_line_ends(mine))
        made = [end for end in _line_ends((mine + added).merged()) if end not in before]
        return (_end_zones(made, rules) & others).is_empty()

    def beyond(self, net: str, layer: str, box: db.Box) -> db.Region:
        """What of ``box`` on ``layer`` lies outside ``net``'s own shapes there: what a new shape adds."""
        own = self._index(net, layer, mine=True).touching(box)
        return db.Region(box) - own

    def clear_beyond(self, net: str, layer: str, box: db.Box, space: int) -> bool:
        """Whether what ``box`` adds to ``net``'s shapes on ``layer`` (``beyond``) keeps ``space`` from
        every other net's (``fits``): where it lies on the net's own metal, the net's own space holds."""
        added = self.beyond(net, layer, box)
        return all(self.fits(net, layer, piece.bbox(), space) for piece in added.each())

    def notches(self, net: str, layer: str, box: db.Box, space: int) -> list[db.Box]:
        """What fills the gaps narrower than ``space`` that ``box`` leaves with ``net``'s own shapes on
        ``layer`` (a notch between a pad and the end of the wire it joins), as boxes."""
        reach = box.enlarged(space, space)
        near = self._index(net, layer, mine=True).touching(reach)
        for n, name, other in self.drawn:
            if n == net and name == layer and other.touches(reach):
                near.insert(other)
        joined = (near + db.Region(box)).merged()
        half = -(-space // 2)
        filled = (joined.sized(half).sized(-half) - joined) & db.Region(reach)
        return [trap.bbox() for polygon in filled.each() for trap in polygon.decompose_trapezoids()]

    def jogs(self, net: str, layer: str, added: list[db.Box], least: int) -> bool:
        """Whether ``added`` joined to ``net``'s own shapes on ``layer`` makes a jog the own shapes
        have not: a corner between a horizontal and a vertical edge both shorter than ``least`` (a
        pad a few grid steps wider than the wire it joins, its step a kit's small-jog rule finds)."""
        if not added:
            return False
        reach = db.Region(added).bbox().enlarged(least, least)
        own = self._index(net, layer, mine=True).touching(reach)
        for n, name, other in self.drawn:
            if n == net and name == layer and other.touches(reach):
                own.insert(other)

        def corners(region: db.Region) -> int:
            short = [e for e in region.merged().edges().each() if e.length() < least]
            ends = {}
            for e in short:
                for point in (e.p1, e.p2):
                    ends.setdefault((point.x, point.y), set()).add(e.dx() == 0)
            return sum(1 for kinds in ends.values() if len(kinds) == 2)

        return corners(own + db.Region(added)) > corners(own)

    def over(self, layer: str, box: db.Box) -> bool:
        """Whether anything lies over ``box`` on ``layer``."""
        return self._index(None, layer).near(box, 0) or any(
            name == layer and not (db.Region(other) & db.Region(box)).is_empty() for _n, name, other in self.drawn
        )

    def under(self, nets: tuple[str, ...], layer: str, box: db.Box, space: int) -> bool:
        """Whether any net but ``nets`` has a shape on ``layer`` within ``space`` of ``box``."""
        near = db.Region(box.enlarged(space, space)) & self.regions.get(layer, db.Region())
        for net in nets:
            near -= self.own_region(net, layer)
        return not near.is_empty()

    def held(self, net: str, layer: str, box: db.Box) -> bool:
        """Whether ``net``'s own shapes on ``layer`` cover ``box``."""
        own = self._index(net, layer, mine=True).touching(box)
        for n, name, other in self.drawn:
            if n == net and name == layer:
                own.insert(other)
        return (db.Region(box) - own).is_empty()


def _line_ends(region: db.Region) -> list[tuple[int, int, int, int]]:
    """The edges of ``region``'s polygons (merged) between two convex corners, each from its hull's
    point to the next (clockwise, KLayout's: outside on the left), where it is horizontal or
    vertical: the ends a line-end rule may hold (``Kit.ends``, by their length)."""
    found = []
    for polygon in region.each():
        points = [(p.x, p.y) for p in polygon.each_point_hull()]
        count = len(points)
        turns = []
        for index in range(count):
            (x0, y0), (x1, y1), (x2, y2) = points[index - 1], points[index], points[(index + 1) % count]
            turns.append((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1) < 0)  # convex: a right turn
        for index in range(count):
            (x1, y1), (x2, y2) = points[index], points[(index + 1) % count]
            if (x1 == x2 or y1 == y2) and turns[index] and turns[(index + 1) % count]:
                found.append((x1, y1, x2, y2))
    return found


def _end_zones(ends: list[tuple[int, int, int, int]], rules: tuple[tuple[int, int, int], ...]) -> db.Region:
    """What line ``ends`` (``_line_ends``) keep clear by ``rules`` (``Kit.ends``): in front of each
    end shorter than a rule's ``below``, as far as its space, as wide as the end and its extension
    past either side."""
    zones = db.Region()
    for x1, y1, x2, y2 in ends:
        length = abs(x2 - x1) + abs(y2 - y1)
        for gap, below, extension in rules:
            if length >= below:
                continue
            if y1 == y2:  # its outside up where it runs right
                lo, hi = min(x1, x2) - extension, max(x1, x2) + extension
                zones.insert(db.Box(lo, y1, hi, y1 + gap) if x2 > x1 else db.Box(lo, y1 - gap, hi, y1))
            else:  # and left where it runs up
                lo, hi = min(y1, y2) - extension, max(y1, y2) + extension
                zones.insert(db.Box(x1 - gap, lo, x1, hi) if y2 > y1 else db.Box(x1, lo, x1 + gap, hi))
    return zones


def _connectivity(layout: db.Layout, top: db.Cell, pdk: str, nets: list[str]) -> _Space:
    """Every metal's and cut's shapes, and ``nets``' own (by their labels), the layers joined
    through their cuts as the extraction joins them (``flow.layout.kpex.technology``)."""
    from flow.layout.kpex import technology
    from flow.layout.lint import SUPPLIES

    joins = technology(pdk)[1]
    l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(layout, top, []))
    made, regions = {}, {}
    for name, pairs in joins["layers"].items():
        indexes = [index for pair in pairs if (index := layout.find_layer(*pair)) is not None]
        made[name] = l2n.make_layer(indexes[0], name) if indexes else l2n.make_layer(name)
        l2n.connect(made[name])
        if re.fullmatch(r"[MV]\d+", name):
            regions[name] = db.Region(top.begin_shapes_rec(indexes[0])).merged() if indexes else db.Region()
    for below, via, above in joins["vias"]:
        l2n.connect(made[below], made[via])
        l2n.connect(made[via], made[above])
    for name, pairs in joins["labels"].items():
        for pair in {tuple(pair) for pair in pairs}:
            index = layout.find_layer(*pair)
            if name in made and index is not None:
                l2n.connect(made[name], l2n.make_text_layer(index, f"{name}_{pair[0]}_{pair[1]}_text"))
    for supply in SUPPLIES:
        l2n.join_net_names(supply)
    l2n.extract_netlist()
    circuit = l2n.netlist().circuit_by_name(top.name)
    own: dict[str, dict[str, db.Region]] = {}
    for net in nets:
        found = circuit.net_by_name(net) if circuit is not None else None
        if found is not None:
            own[net] = {name: l2n.shapes_of_net(found, made[name], True).merged() for name in regions}
    return _Space(regions, own)


def _labels(layout: db.Layout, top: db.Cell, net: str) -> list[tuple[int, db.Point]]:
    """Every label of ``net`` in the top cell: its layer index and place."""
    found = []
    for index in layout.layer_indexes():
        for shape in top.shapes(index).each():
            if shape.is_text() and shape.text.string.lower() == net:
                found.append((index, shape.text.position()))
    return found


@dataclass
class _Landing:
    net: str
    metal: int  # the landing metal
    attach: int  # the metal of the port's wiring its route leaves
    shapes: list[tuple[str, db.Box]]  # the actual frame
    box: db.Box  # the landing, the actual frame
    side: str | None = None
    mirror: str | None = None
    # its shield (``EdgePin.shield``): the ground's strip under its wire and the cuts tying it down,
    # the actual frame; the metal the tie leaves the ground's wiring on
    shield: list[tuple[str, db.Box]] = field(default_factory=list)
    shield_from: int | None = None
    shield_net: str | None = None
    shield_box: db.Box | None = None  # the strip's bounding box


@dataclass
class _Search:
    """One pin's search on one landing metal: its net, the frame its side is the top of (``trans``,
    its outline ``outline`` there), whether it lands on the side or in place."""

    kit: Kit
    space: _Space
    net: str
    metal: int
    trans: db.Trans
    outline: db.Box  # the frame's
    edge: bool
    # the nets its wire may run over on the metal just below the landing metal (its own, the
    # supplies'), where it keeps that metal free of every other's for its shield
    # (``EdgePin.shield``); None: anything
    below: tuple[str, ...] | None = None

    def points(self, at_x: int | None = None, anchor: tuple[int, int] | None = None) -> list[tuple[int, int, int]]:
        """The points of the net's wiring (metal, x, y in the frame) a landing may leave from: on each
        of its metals up to the landing metal (only below it in place), along each piece's middle line,
        a cut inside its ends, a step apart from the ``anchor`` (its label: a capacitor array's inputs
        centred on their tracks); ``at_x``: at that place across the side alone."""
        kit, found = self.kit, []
        step = max(kit.grid, kit.up(min(kit.width(self.metal), 200)))
        for metal in kit.metals:
            if metal < LOWEST or metal > self.metal or (metal == self.metal and not self.edge):
                continue
            own = self.space.own_region(self.net, f"M{metal}")
            if own.is_empty():
                continue
            inset = (
                self.kit.half_wide(self.metal) if metal == self.metal else kit.cut(metal)[0] // 2 + kit.cut(metal)[2]
            )
            for polygon in own.transformed(self.trans).each():
                for piece in polygon.decompose_trapezoids():
                    box = piece.bbox()
                    found += [(metal, *point) for point in self._along(box, inset, step, at_x, anchor)]
        return [(m, self._snap(x), self._snap(y)) for m, x, y in found]

    @staticmethod
    def _steps(lo: int, hi: int, step: int, start: int | None) -> list[int]:
        """Places from ``lo`` to ``hi`` ``step`` apart, on ``start``'s grid where given."""
        if start is None:
            return list(range(lo, hi + 1, step))
        first = start - (start - lo) // step * step
        return list(range(first, hi + 1, step))

    @classmethod
    def _along(
        cls, box: db.Box, inset: int, step: int, at_x: int | None, anchor: tuple[int, int] | None = None
    ) -> list[tuple[int, int]]:
        if box.width() >= box.height():
            lo, hi, y = box.left + inset, box.right - inset, box.center().y
            if at_x is not None:
                return [(at_x, y)] if lo <= at_x <= hi else []
            if hi < lo:
                return [(box.center().x, y)]
            return [(x, y) for x in cls._steps(lo, hi, step, anchor[0] if anchor else None)]
        lo, hi, x = box.bottom + inset, box.top - inset, box.center().x
        if at_x is not None:
            if abs(x - at_x) > 1:
                return []
            x = at_x
        if hi < lo:
            return [(x, box.center().y)]
        return [(x, y) for y in reversed(cls._steps(lo, hi, step, anchor[1] if anchor else None))]

    def _snap(self, value: int) -> int:
        return round(value / self.kit.grid) * self.kit.grid

    def attempt(self, attach: int, x: int, y: int) -> _Landing | None:
        """The landing from the wiring on ``attach`` at (x, y): its shapes and box (the actual frame),
        None where something is in the way: the landing first (nothing over it, its route clear of
        other nets), then the stack of cuts."""
        kit, space, net = self.kit, self.space, self.net
        back = self.trans.inverted()
        half, length = kit.half_wide(self.metal), kit.length(self.metal)
        if attach < self.metal:
            size, _gap, end, _side = kit.cut(self.metal - 1)
            start = y - size // 2 - end
        else:  # on the wiring's own metal: from the middle line of its piece, where it overlaps it
            start = y
        if self.edge:
            top = self.outline.top
            if (
                x - half < self.outline.left
                or x + half > self.outline.right
                or min(start, top - length) < self.outline.bottom
            ):
                return None
            options = [
                (
                    db.Box(x - half, min(start, top - length), x + half, top),
                    db.Box(x - half, top - length, x + half, top),
                )
            ]
        else:
            options = []
            for w, h in ((length, 2 * half), (2 * half, length)):
                pad = db.Box(x - w // 2, y - h // 2, x - w // 2 + w, y - h // 2 + h)
                if self.outline.contains(pad.p1) and self.outline.contains(pad.p2):
                    options.append((pad, pad))
        clearance = kit.up(kit.space(self.metal) * 3 // 2)
        above = [k for k in kit.metals if k > self.metal]
        landed = None
        for wire, box in options:
            wire, box = wire.transformed(back), box.transformed(back)
            if any(space.over(f"M{k}", box) for k in above):
                continue
            if self.below is not None and space.under(
                self.below, f"M{self.metal - 1}", wire, kit.space(self.metal - 1)
            ):
                continue
            if space.clear_beyond(net, f"M{self.metal}", wire, clearance):
                landed = (wire, box)
                break
        if landed is None:
            return None
        shapes: list[tuple[str, db.Box]] = []
        if attach < self.metal:
            for below in range(attach, self.metal):
                size, gap, _end, _side = kit.cut(below)
                cut = db.Box(x - size // 2, y - size // 2, x - size // 2 + size, y - size // 2 + size).transformed(back)
                if not space.clear(net, f"V{below}", cut, gap):
                    return None
                shapes.append((f"V{below}", cut))
            for metal in range(attach, self.metal):
                held = [kit.cut(c)[2:] for c in (metal - 1, metal) if attach <= c < self.metal]
                cut = next(box for name, box in shapes if name == f"V{metal}")
                if metal == attach and any(
                    space.held(net, f"M{metal}", cut.enlarged(ex, ey)) for ex, ey in (held[-1], held[-1][::-1])
                ):
                    continue
                pads = self._pads(metal, cut, held)
                pad = next((p for p in pads if space.fits(net, f"M{metal}", p, kit.space(metal))), None)
                if pad is None:
                    return None
                shapes.append((f"M{metal}", pad))
        wire, box = landed
        shapes.append((f"M{self.metal}", wire))
        joined = _joined(kit, space, net, shapes)
        return None if joined is None else _Landing(net, self.metal, attach, joined, box)

    def _pads(self, metal: int, cut: db.Box, held: list[tuple[int, int]]) -> list[db.Box]:
        """The pads on ``metal`` that hold ``cut`` by the enclosures ``held`` ((two sides, the other
        two) of the cuts on it), as wide as the metal and as large as its area: long one way, long
        the other, and square."""
        kit, found = self.kit, []
        width, area = kit.width(metal), kit.area(metal)
        for along_x in (True, False):
            ex = max(end if along_x else side for end, side in held)
            ey = max(side if along_x else end for end, side in held)
            box = cut.enlarged(ex, ey)
            if along_x:
                box = box.enlarged(0, kit.up(-(-max(0, width - box.height()) // 2)))
                grow = max(0, -(-area // box.height()) - box.width())
                box = box.enlarged(kit.up(-(-grow // 2)), 0)
            else:
                box = box.enlarged(kit.up(-(-max(0, width - box.width()) // 2)), 0)
                grow = max(0, -(-area // box.width()) - box.height())
                box = box.enlarged(0, kit.up(-(-grow // 2)))
            found.append(box)
        reach = max(end for end, _side in held)
        side = max(cut.width() + 2 * reach, width, math.isqrt(max(area - 1, 0)) + 1)
        grow = kit.up(-(-(side - cut.width()) // 2))
        found.append(cut.enlarged(grow, grow))
        return found


def _shield(kit: Kit, space: _Space, landing: _Landing, outline: db.Box) -> None:
    """``landing``'s shield (``EdgePin.shield``), where another signal's metal lies under its wire on
    any metal: a strip of the block's ground on the metal under the wire, as far past the wire's
    sides as the wire stands over the highest of those metals (its fringe's reach there; a metal's
    width in a kit with no stack), where it keeps twice the metal's space from every other shape
    (the landing's own net's too: a long strip is a wide metal, whose space is wider than the least)
    and the outline; tied down by a stack of cuts to the ground's own metal under it, the nearest
    first; none where no strip or tie fits (a warning)."""
    wire = max((box for name, box in landing.shapes if name == f"M{landing.metal}"), key=lambda box: box.area())
    metal, own = landing.metal - 1, (landing.net, *space.supplies)
    under = [k for k in kit.metals if k < metal and space.under(own, f"M{k}", wire, 0)]
    if not under:
        return
    taken = space.regions.get(f"M{metal}", db.Region()).dup()
    for _net, name, box in space.drawn:
        if name == f"M{metal}":
            taken.insert(box)
    gap = kit.space(metal)
    reach = kit.height(landing.metal, max(under)) or kit.width(metal)
    wider = (wire.enlarged(reach, 0) if wire.height() >= wire.width() else wire.enlarged(0, reach)) & outline.enlarged(
        -gap, -gap
    )
    rules = kit.ends(metal)
    room = db.Region(wider) - taken.sized(max([2 * gap, *(end for end, _below, _extension in rules)]))
    if rules:  # and every line end around it its line-end space
        around = max(end + below + extension for end, below, extension in rules)
        room -= _end_zones(_line_ends((taken & db.Region(wider.enlarged(around, around))).merged()), rules)
    half = kit.width(metal) // 2
    room = room.sized(-half).sized(half) & room  # none of it narrower than the metal
    best = max(room.each(), key=lambda piece: (db.Region(piece) & db.Region(wire)).area(), default=None)
    strip = db.Region(best) if best is not None else db.Region()
    for ground in space.grounds if not (strip & db.Region(wire)).is_empty() else ():
        tie = _tie(kit, space, ground, strip, metal)
        if tie is not None:
            pieces = [(f"M{metal}", trap.bbox()) for trap in best.decompose_trapezoids()]
            landing.shield, landing.shield_from, landing.shield_net = [*pieces, *tie[0]], tie[1], ground
            landing.shield_box = strip.bbox()
            space.drawn += [(ground, name, box) for name, box in landing.shield]
            return
    LOG.warning(f"pins: {landing.net}'s landing runs over other signals' metal: no shield fits under it")


def _tie(
    kit: Kit, space: _Space, ground: str, strip: db.Region, metal: int
) -> tuple[list[tuple[str, db.Box]], int] | None:
    """A stack of cuts from ``ground``'s own metal under ``strip`` up to it on ``metal``: the foot's
    cut on that metal, a pad on each metal from it to the one under ``metal`` that holds its cuts by
    their enclosures (as a landing's: the foot's over the ground's own or clear of the others; each
    joined to the ground's own metal, ``_joined``), the top cut inside the strip by its own; its
    shapes and the metal it leaves from, the nearest first; None where none fits."""
    finder = _Search(kit, space, ground, metal, db.Trans.R0, db.Box(), False)
    for foot in sorted((k for k in kit.metals if k < metal), reverse=True):
        own = space.own_region(ground, f"M{foot}") & strip
        pieces = (t.bbox() for p in own.each() for t in p.decompose_trapezoids())
        for x, y in (point for piece in pieces for point in _middle_first(finder, piece, kit.cut(foot)[0] // 2)):
            cuts = []
            for below in range(foot, metal):
                size, gap, _end, _side = kit.cut(below)
                cut = db.Box(x - size // 2, y - size // 2, x - size // 2 + size, y - size // 2 + size)
                if not space.clear(ground, f"V{below}", cut, gap):
                    break
                cuts.append(cut)
            if len(cuts) < metal - foot or not space.held(ground, f"M{foot}", cuts[0]):
                continue
            top_end = kit.cut(metal - 1)[2:]
            if not any(_inside(cuts[-1].enlarged(a, b), strip) for a, b in (top_end, top_end[::-1])):
                continue
            pads = []
            for m in range(foot, metal):
                held = [kit.cut(c)[2:] for c in (m - 1, m) if foot <= c < metal]
                pads.append(
                    next(
                        (
                            pad
                            for pad in finder._pads(m, cuts[m - foot], held)
                            if space.fits(ground, f"M{m}", pad, kit.space(m))
                        ),
                        None,
                    )
                )
            if all(pad is not None for pad in pads):
                vias = [(f"V{m}", cut) for m, cut in zip(range(foot, metal), cuts, strict=True)]
                joined = _joined(
                    kit, space, ground, [(f"M{m}", pad) for m, pad in zip(range(foot, metal), pads, strict=True)]
                )
                if joined is not None:
                    return vias + joined, foot
    return None


def _joined(kit: Kit, space: _Space, net: str, shapes: list[tuple[str, db.Box]]) -> list[tuple[str, db.Box]] | None:
    """``shapes`` (``net``'s new pads and wires) joined to the net's own metal: every gap one leaves
    with it narrower than the metal's space filled, the fill keeping its space from every other
    net (``fits``), and no step shorter than the metal's width where they join it; None where either
    fails."""
    shapes = list(shapes)
    for name, added in [shape for shape in shapes if shape[0].startswith("M")]:
        gap = kit.space(int(name[1:]))
        for fill in space.notches(net, name, added, gap):
            if not space.fits(net, name, fill, gap):
                return None
            shapes.append((name, fill))
    for name in {name for name, _box in shapes if name.startswith("M")}:
        if space.jogs(net, name, [b for n, b in shapes if n == name], kit.width(int(name[1:]))):
            return None
    return shapes


def _middle_first(finder: _Search, piece: db.Box, step: int) -> list[tuple[int, int]]:
    """Points on the grid along ``piece``'s middle line, ``step`` apart, the nearest its middle first."""
    middle = piece.center()
    points = finder._along(piece, 0, max(step, finder.kit.grid), None, (middle.x, middle.y))
    snapped = {(finder._snap(x), finder._snap(y)) for x, y in points}
    return sorted(snapped, key=lambda point: abs(point[0] - middle.x) + abs(point[1] - middle.y))


def _inside(box: db.Box, outer: db.Region) -> bool:
    return (db.Region(box) - outer).is_empty()


def _order(
    points: list[tuple[int, int, int]],
    spot: str,
    edge_y: int | None,
    anchor: tuple[int, int] | None,
    along: Callable[[int, int], int] | None,
) -> list[tuple[int, int, int]]:
    """``points`` (metal, x, y) in the order tried: an edge pin's on the highest metal of its wiring
    first (the fewest cuts), nearest its side, then nearest its label (a spot's end before all of
    them: ``along``, a point's place along the side as drawn); a lifted pin's nearest its label."""

    def key(point: tuple[int, int, int]) -> tuple[int, ...]:
        metal, x, y = point
        near = abs(x - anchor[0]) + abs(y - anchor[1]) if anchor else 0
        if edge_y is None:
            return (near, -metal)
        run = edge_y - y
        if spot == "first" and along is not None:
            return (along(x, y), -metal, run)
        if spot == "last" and along is not None:
            return (-along(x, y), -metal, run)
        return (-metal, run, near)

    return sorted(points, key=key)


def _thinned(points: list[tuple[int, int, int]], edge_y: int, step: int, keep: int = 3) -> list[tuple[int, int, int]]:
    """An edge pin's ``points`` in their order, at most ``keep`` of each metal at each place across
    the side (within ``step``): those nearest the side, a route from further back crossing what
    theirs crosses."""
    kept: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for point in sorted(points, key=lambda p: edge_y - p[2]):
        group = kept.setdefault((point[0], point[1] // step), [])
        if len(group) < keep:
            group.append(point)
    chosen = {point for group in kept.values() for point in group}
    return [point for point in points if point in chosen]


def _search(
    search: _Search, spot: str, anchor, along, at_x: int | None = None, within: int | None = None
) -> _Landing | None:
    """The first point of ``search`` that lands, in their order (a lifted pin's nearest its label
    alone, ``_LIFT_TRIES``); ``within``: only those that far along the side from the first."""
    points = _order(search.points(at_x, anchor), spot, search.outline.top if search.edge else None, anchor, along)
    if search.edge:
        points = _thinned(points, search.outline.top, search.kit.half_wide(search.metal))
    if within is not None and points:
        first = along(points[0][1], points[0][2])
        points = [point for point in points if abs(along(point[1], point[2]) - first) <= within]
    for attach, x, y in points[: _TRIES if search.edge else _LIFT_TRIES]:
        found = search.attempt(attach, x, y)
        if found is not None:
            return found
    return None


def _edge(kit: Kit, space: _Space, intent: dict[str, Any], outline: db.Box, anchor_of) -> list[_Landing]:
    """An edge pin's landing (and its mirror's) on the lowest landing metal both fit on; a shielded
    one (``shield``) as the module's docstring says."""
    net, side, spot, mirror = intent["net"], intent["side"], intent.get("spot", "nearest"), intent.get("mirror")
    below = (net, *space.supplies) if intent.get("shield") else None
    trans = _TO_TOP[side]
    back = trans.inverted()
    frame = outline.transformed(trans)

    def along(x: int, y: int) -> int:
        point = back * db.Point(x, y)
        return point.x if side in ("top", "bottom") else point.y

    if mirror is None and below is not None:
        # at its spot (within SHIELD_WITHIN_NM of it), the highest landing metal first whose metal
        # under the wire is free for the shield; where none is, as any edge pin, unshielded
        for metal in reversed(kit.landing):
            one = _Search(kit, space, net, metal, trans, frame, True, below)
            found = _search(one, spot, anchor_of(net, trans), along, within=SHIELD_WITHIN_NM)
            if found is not None:
                found.side = side
                _shield(kit, space, found, outline)
                return [found]
        LOG.warning(f"pins: no landing of {net} with room for its shield under it: drawn unshielded")
    for metal in kit.landing:
        one = _Search(kit, space, net, metal, trans, frame, True)
        if mirror is None:
            found = _search(one, spot, anchor_of(net, trans), along)
            if found is not None:
                found.side = side
                return [found]
            continue
        other = _Search(kit, space, mirror, metal, trans, frame, True)
        centre = frame.left + frame.right
        anchor = anchor_of(net, trans)
        points = _thinned(
            _order(one.points(None, anchor), spot, frame.top, anchor, along), frame.top, kit.half_wide(metal)
        )
        for attach, x, y in points[:_TRIES]:
            first = one.attempt(attach, x, y)
            if first is None:
                continue
            space.drawn += [(net, name, box) for name, box in first.shapes]
            second = _search(other, "nearest", None, along, at_x=centre - x)
            del space.drawn[-len(first.shapes) :]
            if second is not None:
                first.side, second.side = side, side
                first.mirror, second.mirror = mirror, net
                return [first, second]
    return []


def land(gds: Path, pdk: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Draw ``plan``'s pins (``flow.layout.hdl21align.port_plan``: the module's ports, their uses,
    its edge pins) into the layout ``gds`` (its largest top cell, written back) and give the record
    (the module's docstring)."""
    kit_ = kit(pdk)
    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    um = layout.dbu
    boundary = layout.find_layer(*kit_.tech.LAYERS["BND"])
    outline = db.Region(top.begin_shapes_rec(boundary)).bbox() if boundary is not None else db.Box()
    outline = top.bbox() if outline.empty() else outline
    ports = plan.get("ports", [])
    signals = [port["net"] for port in ports if port["use"] not in SUPPLY_USES]
    supplies = [port["net"] for port in ports if port["use"] in SUPPLY_USES]
    space = _connectivity(layout, top, pdk, signals + supplies)
    space.supplies = tuple(supplies)
    space.grounds = tuple(port["net"] for port in ports if port["use"] == "ground")
    space.ends = {f"M{m}": kit_.ends(m) for m in kit_.metals if kit_.ends(m)}

    def anchor_of(net: str, trans: db.Trans) -> tuple[int, int] | None:
        labels = _labels(layout, top, net)
        if not labels:
            return None
        point = trans * labels[0][1]
        return point.x, point.y

    landings: dict[str, _Landing] = {}
    for intent in plan.get("edges", []):
        if intent["net"] not in space.own:
            LOG.warning(f"pins: {intent['net']} is not in the layout: no landing on its {intent['side']} side")
            continue
        found = _edge(kit_, space, intent, outline, anchor_of)
        if not found:
            LOG.warning(
                f"pins: no landing of {intent['net']} on the {intent['side']} side on any landing metal"
                f" ({', '.join(f'M{m}' for m in kit_.landing) or 'the kit names none'})"
            )
        for landing in found:
            landings[landing.net] = landing
            space.drawn += [(landing.net, name, box) for name, box in landing.shapes]
    for net in signals:  # every other signal lifted where a landing pad fits
        if net in landings or net not in space.own:
            continue
        for metal in kit_.landing:
            found = _search(
                _Search(kit_, space, net, metal, db.Trans.R0, outline, False),
                "nearest",
                anchor_of(net, db.Trans.R0),
                None,
            )
            if found is not None:
                landings[net] = found
                space.drawn += [(net, name, box) for name, box in found.shapes]
                break
    for landing in landings.values():
        for name, box in landing.shapes + landing.shield:
            top.shapes(layout.layer(*kit_.tech.LAYERS[name])).insert(box)
        for index, _point in _labels(layout, top, landing.net):
            shapes = top.shapes(index)
            for shape in [s for s in shapes.each() if s.is_text() and s.text.string.lower() == landing.net]:
                shapes.erase(shape)
        centre = landing.box.center()
        top.shapes(layout.layer(*kit_.label_layer(landing.metal))).insert(db.Text(landing.net, centre.x, centre.y))
    layout.write(str(gds))

    def framed(box: db.Box) -> list[float]:
        return [
            round((box.left - outline.left) * um, 4),
            round((box.bottom - outline.bottom) * um, 4),
            round((box.right - outline.left) * um, 4),
            round((box.top - outline.bottom) * um, 4),
        ]

    def free_above(metal: int, box: db.Box) -> list[str]:
        return [f"M{k}" for k in kit_.metals if k > metal and not space.over(f"M{k}", box)]

    entries = []
    for port in ports:
        net, use = port["net"], port["use"]
        entry: dict[str, Any] = {"net": net, "use": use}
        landing = landings.get(net)
        if use in SUPPLY_USES:
            entry["made"] = "rail lines"
        elif landing is not None:
            entry.update(
                layer=f"M{landing.metal}",
                box_um=framed(landing.box),
                side=landing.side,
                free_above=free_above(landing.metal, landing.box),
                made="edge" if landing.side else "lifted",
                route_from=f"M{landing.attach}",
            )
            if landing.mirror:
                entry["mirror"] = landing.mirror
            if landing.shield:
                entry["shield"] = {
                    "net": landing.shield_net,
                    "layer": landing.shield[0][0],
                    "box_um": framed(landing.shield_box),
                    "tied_from": f"M{landing.shield_from}",
                }
        else:
            entry.update(_as_drawn(kit_, layout, top, space, net, framed))
        entries.append(entry)
    return {
        "frame": "the outline (its boundary layer's box), its lower left the origin",
        "outline_um": [round(outline.width() * um, 4), round(outline.height() * um, 4)],
        "origin_um": [round(outline.left * um, 4), round(outline.bottom * um, 4)],
        "landing_metals": [f"M{m}" for m in kit_.landing],
        "ports": entries,
    }


def _as_drawn(kit_: Kit, layout: db.Layout, top: db.Cell, space: _Space, net: str, framed) -> dict[str, Any]:
    """A signal no landing fits, as ALIGN drew it: the metal under its label, its piece there and the
    metals no other net's metal crosses over it; and the site of a cut up from it nearest its label
    (a capacitor array's input centred on its track) whose pad on the metal above keeps its space
    from other nets, with the metals free over that site; none where the layout has no label of it."""

    def free(metal: int, box: db.Box) -> list[str]:
        return [f"M{k}" for k in kit_.metals if k > metal and space.clear(net, f"M{k}", box, 0)]

    for index, point in _labels(layout, top, net):
        info = layout.get_info(index)
        for metal in kit_.metals:
            if (info.layer, info.datatype) not in kit_.label_layers(metal):
                continue
            piece = space.own_region(net, f"M{metal}").interacting(db.Region(db.Box(point, point).enlarged(1)))
            if piece.is_empty():
                continue
            box = next(p.bbox() for p in piece.each())
            entry: dict[str, Any] = {
                "layer": f"M{metal}",
                "box_um": framed(box),
                "side": None,
                "free_above": free(metal, box),
            }
            if metal + 1 in kit_.metals and f"V{metal}" in kit_.tech.RULES:
                size, gap, end, _side = kit_.cut(metal)
                step = size + gap
                along = box.width() >= box.height()
                places = _Search._steps(
                    (box.left if along else box.bottom) + size // 2,
                    (box.right if along else box.top) - size // 2,
                    step,
                    point.x if along else point.y,
                )
                places.sort(key=lambda v: abs(v - (point.x if along else point.y)))
                for value in places:
                    x, y = (value, box.center().y) if along else (box.center().x, value)
                    cut = db.Box(x - size // 2, y - size // 2, x - size // 2 + size, y - size // 2 + size)
                    if space.fits(net, f"M{metal + 1}", cut.enlarged(end, end), kit_.space(metal + 1)):
                        entry.update(site_um=framed(cut), site_free_above=free(metal, cut))
                        break
            return {**entry, "made": "as laid out"}
    return {"layer": None, "made": "not in the layout"}


def plan_path(netlist_dir: Path, design: str) -> Path:
    """Where the layout step keeps a design's port plan (``flow.layout.step.inputs``)."""
    return Path(netlist_dir) / f"{design}.pins.json"


def read_plan(path: Path) -> dict[str, Any] | None:
    """A design's port plan, None where it has none."""
    return json.loads(Path(path).read_text()) if Path(path).exists() else None
