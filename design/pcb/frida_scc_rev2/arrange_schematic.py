"""Arrange frida_scc_rev2's KiCad schematic: frida-scc-1p1's sheet as page 1, the new parts on pages after it.

The ``pcb`` tool keeps the schematic in ``eda/`` as it is drawn and only repairs what no longer
matches the Zener design, so the drawing is made once and kept:

    python3 arrange_schematic.py link                 # page 1: frida-scc-1p1's sheet, its symbols linked to the parts here
    pcb apply schematic --no-open frida_scc_rev2.zen   # values updated, parts that are gone removed, new parts added
    python3 arrange_schematic.py                      # leftover stubs removed; new parts moved to the pages after, in blocks
    pcb apply schematic --no-open frida_scc_rev2.zen   # connections between the pages restored

``link`` copies ``../frida-scc-1p1.kicad_sch`` and gives each symbol named in
``place_from_1p1.SAME`` the path of the part that replaces it (from the board file), which is all
the tool needs to recognise it. The arranging step never touches a symbol that has such a
counterpart: page 1 stays as it was drawn. Every other part, with the wire stubs, labels and
supply symbols the tool drew on its pins, moves as one piece to the page of its block in ``PAGES``,
packed with the others of its block under the block's title. Parts added to the design later land
beside page 1 again; running this again moves them to new pages after the ones there.
"""

from __future__ import annotations

import collections
import copy
import datetime
import math
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent
OLD = HERE.parent / "frida-scc-1p1.kicad_sch"
ROOT = HERE / "eda" / "frida_scc_rev2.kicad_sch"
BOARD = HERE / "eda" / "frida_scc_rev2.kicad_pcb"
PROJECT = "frida_scc_rev2"
MARK = "f21da2b0"  # the first eight digits of the UUID of everything this script draws

# the pages after page 1, in order: (page title, [(block title, the instance-path prefixes it holds)]);
# a page that fills up continues on another of the same title
PAGES = [
    (
        "Supplies",
        [
            (
                "Power entry, rail select jumpers and monitors",
                ["SUPPLIES.J_", "SUPPLIES.FB_", "SUPPLIES.C_", "SUPPLIES.R_"],
            ),
            ("VDD_A regulator, 1.2 V", ["SUPPLIES.REG_A."]),
            ("VDD_D regulator, 1.2 V", ["SUPPLIES.REG_D."]),
            ("VDD_DAC regulator, 1.2 V", ["SUPPLIES.REG_DAC."]),
            ("VDD_IO regulator, 1.2 V", ["SUPPLIES.REG_IO."]),
            ("V3P3A regulator, 3.3 V analog", ["SUPPLIES.REG_3V3A."]),
            ("V2P5 regulator, 2.5 V logic", ["SUPPLIES.REG_2V5."]),
            ("VS_N regulator, -1 V", ["SUPPLIES.REG_VS_N."]),
        ],
    ),
    (
        "Signal source and second control link",
        [
            ("Signal source: reference, DAC, followers", ["SOURCE."]),
            ("Second control link (RJ45)", ["AUX."]),
            ("COMP_OUT taps, monitor taps, source jumper", ["TAP_COMP_OUT.", "R_MON_", "INPUT."]),
        ],
    ),
    (
        "Probe matrix",
        [
            ("Probe channel 1", ["CH1."]),
            ("Probe channel 2", ["CH2."]),
            ("Probe channel 3", ["CH3."]),
            ("Probe channel 4", ["CH4."]),
        ],
    ),
]
PAPER = (420.0, 297.0)  # A3
AREA = (16.51, 22.86, 403.86, 240.03)  # where blocks go on a page (the title block is below)
LINKS = (20.32, 123.19)  # on page 1, where the boxes that stand for the other pages go (free, below the DisplayPort)
GRID = 1.27
GAP = 2.54  # between the pieces of a block


# ------------------------------------------------------------------------- s-expressions


class Quoted(str):
    """A token that was written in quotes (kept with its escapes)."""


TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+')


def parse(text: str) -> list:
    stack: list[list] = []
    current: list = []
    for match in TOKEN.finditer(text):
        token = match.group(0)
        if token == "(":
            stack.append(current)
            current = []
        elif token == ")":
            done = current
            current = stack.pop()
            current.append(done)
        else:
            current.append(Quoted(token[1:-1]) if token[0] == '"' else token)
    return current[0]


def dump(node: list | str, depth: int = 0) -> str:
    if not isinstance(node, list):
        return f'"{node}"' if isinstance(node, Quoted) else node
    if all(not isinstance(child, list) for child in node):
        return "(" + " ".join(dump(child) for child in node) + ")"
    pad = "\t" * (depth + 1)
    head = [dump(child) for child in node if not isinstance(child, list)]
    body = [pad + dump(child, depth + 1) for child in node if isinstance(child, list)]
    return "(" + " ".join(head) + "\n" + "\n".join(body) + "\n" + "\t" * depth + ")"


def kids(node: list, key: str) -> list[list]:
    return [child for child in node if isinstance(child, list) and child and child[0] == key]


def prop(symbol: list, name: str) -> str | None:
    return next((p[2] for p in kids(symbol, "property") if p[1] == name), None)


def mark_uuid(*parts: object) -> Quoted:
    return Quoted(MARK + str(uuid.uuid5(uuid.NAMESPACE_URL, "/".join(map(str, parts))))[8:])


# ------------------------------------------------------------------------------ geometry


def key(x: float, y: float) -> tuple[int, int]:
    return round(x * 100), round(y * 100)


def turned(px: float, py: float, quarter: int, mirror: str | None) -> tuple[float, float]:
    """A library point (y up) about a symbol's origin on the sheet (y down)."""

    x, y = px, -py
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    for _ in range(quarter % 4):
        x, y = y, -x
    return x, y


def outline(node: list, pins: list[tuple[float, float]], points: list[tuple[float, float]]) -> None:
    """Collect a library symbol's pin connection points and the points of its drawing."""

    for child in node:
        if not isinstance(child, list) or not child:
            continue
        if child[0] == "pin":
            at = kids(child, "at")[0]
            x, y, angle = float(at[1]), float(at[2]), math.radians(float(at[3]) if len(at) > 3 else 0)
            length = float(kids(child, "length")[0][1])
            pins.append((x, y))
            points.extend([(x, y), (x + length * math.cos(angle), y + length * math.sin(angle))])
        elif child[0] == "rectangle":
            points.extend((float(kids(child, k)[0][1]), float(kids(child, k)[0][2])) for k in ("start", "end"))
        elif child[0] in ("polyline", "bezier"):
            points.extend((float(p[1]), float(p[2])) for p in kids(kids(child, "pts")[0], "xy"))
        elif child[0] == "circle":
            c, r = kids(child, "center")[0], float(kids(child, "radius")[0][1])
            points.extend([(float(c[1]) - r, float(c[2]) - r), (float(c[1]) + r, float(c[2]) + r)])
        elif child[0] == "arc":
            points.extend((float(kids(child, k)[0][1]), float(kids(child, k)[0][2])) for k in ("start", "mid", "end"))
        elif child[0] == "symbol":
            outline(child, pins, points)


def library(root: list) -> dict[str, tuple[list[tuple[float, float]], list[tuple[float, float]]]]:
    """Library symbol name -> (its pins' connection points, the points of its drawing)."""

    out = {}
    for symbol in kids(kids(root, "lib_symbols")[0], "symbol"):
        pins: list[tuple[float, float]] = []
        points: list[tuple[float, float]] = []
        outline(symbol, pins, points)
        out[str(symbol[1])] = (pins, points or pins or [(0.0, 0.0)])
    return out


def text_box(
    x: float, y: float, angle: float, text: str, justify: list[str], size: float = 1.27
) -> tuple[float, float, float, float]:
    """A rough box around a text at (x, y)."""

    length = len(text) * size * 0.9
    lo, hi = (-length, 0.0) if "right" in justify else (0.0, length) if "left" in justify else (-length / 2, length / 2)
    if round(angle) % 180 == 0:
        if round(angle) % 360 == 180:
            lo, hi = -hi, -lo
        return (x + lo, y - size, x + hi, y + size)
    if round(angle) % 360 == 90:
        lo, hi = -hi, -lo
    return (x - size, y + lo, x + size, y + hi)


class Sheet:
    """One schematic file's items, grouped into pieces that are wired together."""

    def __init__(self, root: list) -> None:
        self.root = root
        self.lib = library(root)
        self.items = [c for c in root if isinstance(c, list) and c and c[0] in MOVABLE]
        points: set[tuple[int, int]] = set()
        for item in self.items:
            if item[0] == "wire":
                points.update(key(float(p[1]), float(p[2])) for p in kids(kids(item, "pts")[0], "xy"))
            elif item[0] != "symbol":
                at = kids(item, "at")[0]
                points.add(key(float(at[1]), float(at[2])))
        self.pins: dict[int, list[tuple[float, float]]] = {}
        self.boxes: dict[int, tuple[float, float, float, float]] = {}
        for item in self.items:
            if item[0] == "symbol":
                self._place(item, points)

    def _place(self, symbol: list, points: set[tuple[int, int]]) -> None:
        """Find how the symbol is turned (the way most of its pins meet something) and its box."""

        name = str(kids(symbol, "lib_name")[0][1] if kids(symbol, "lib_name") else kids(symbol, "lib_id")[0][1])
        pins, drawing = self.lib[name]
        at = kids(symbol, "at")[0]
        x0, y0 = float(at[1]), float(at[2])
        quarter = round(float(at[3]) / 90) if len(at) > 3 else 0
        mirror = str(kids(symbol, "mirror")[0][1]) if kids(symbol, "mirror") else None
        ways = [(quarter, mirror)] + [(q, m) for q in range(4) for m in (None, "x", "y")]
        best = max(
            ways,
            key=lambda way: sum(
                key(x0 + dx, y0 + dy) in points for dx, dy in (turned(px, py, *way) for px, py in pins)
            ),
        )
        self.pins[id(symbol)] = [(x0 + dx, y0 + dy) for dx, dy in (turned(px, py, *best) for px, py in pins)]
        xs, ys = zip(*((x0 + dx, y0 + dy) for dx, dy in (turned(px, py, *best) for px, py in drawing)))
        box = [min(xs), min(ys), max(xs), max(ys)]
        for field in kids(symbol, "property"):
            effects = kids(field, "effects")
            hidden = any(kids(e, "hide") and kids(e, "hide")[0][1] == "yes" for e in effects) or kids(field, "hide")
            if hidden or not field[2]:
                continue
            fat = kids(field, "at")[0]
            justify = [str(j) for e in effects for jj in kids(e, "justify") for j in jj[1:]]
            tb = text_box(float(fat[1]), float(fat[2]), float(fat[3]) if len(fat) > 3 else 0, str(field[2]), justify)
            box = [min(box[0], tb[0]), min(box[1], tb[1]), max(box[2], tb[2]), max(box[3], tb[3])]
        self.boxes[id(symbol)] = (box[0], box[1], box[2], box[3])

    def box(self, item: list) -> tuple[float, float, float, float]:
        if item[0] == "symbol":
            return self.boxes[id(item)]
        if item[0] == "wire":
            xs, ys = zip(*((float(p[1]), float(p[2])) for p in kids(kids(item, "pts")[0], "xy")))
            return (min(xs), min(ys), max(xs), max(ys))
        at = kids(item, "at")[0]
        x, y = float(at[1]), float(at[2])
        if item[0] in ("label", "global_label"):
            justify = [str(j) for e in kids(item, "effects") for jj in kids(e, "justify") for j in jj[1:]] or ["left"]
            extra = 4.0 if item[0] == "global_label" else 0.0
            b = text_box(x, y, float(at[3]) if len(at) > 3 else 0, str(item[1]) + " " * round(extra), justify)
            return (min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y))
        return (x - 0.7, y - 0.7, x + 0.7, y + 0.7)

    def pieces(self) -> list[list[list]]:
        """The items in groups joined by wires, pins, junctions and labels on them."""

        parent: dict[object, object] = {}

        def find(node: object) -> object:
            while parent.setdefault(node, node) != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def join(a: object, b: object) -> None:
            parent[find(a)] = find(b)

        special: dict[tuple[int, int], None] = {}
        wires = []
        for item in self.items:
            if item[0] == "symbol":
                for x, y in self.pins[id(item)]:
                    join(id(item), key(x, y))
                    special[key(x, y)] = None
                if not self.pins[id(item)]:
                    find(id(item))
            elif item[0] == "wire":
                (x0, y0), (x1, y1) = ((float(p[1]), float(p[2])) for p in kids(kids(item, "pts")[0], "xy"))
                join(id(item), key(x0, y0))
                join(id(item), key(x1, y1))
                wires.append((item, x0, y0, x1, y1))
            else:
                at = kids(item, "at")[0]
                join(id(item), key(float(at[1]), float(at[2])))
                special[key(float(at[1]), float(at[2]))] = None
        for item, x0, y0, x1, y1 in wires:  # what sits on a wire between its ends
            lo = (min(x0, x1) * 100 - 1, min(y0, y1) * 100 - 1)
            hi = (max(x0, x1) * 100 + 1, max(y0, y1) * 100 + 1)
            for px, py in special:
                if lo[0] <= px <= hi[0] and lo[1] <= py <= hi[1]:
                    cross = (px / 100 - x0) * (y1 - y0) - (py / 100 - y0) * (x1 - x0)
                    if abs(cross) < 0.02 * max(1.0, math.hypot(x1 - x0, y1 - y0)):
                        join(id(item), (px, py))
        groups: dict[object, list[list]] = collections.defaultdict(list)
        for item in self.items:
            groups[find(id(item))].append(item)
        return list(groups.values())


MOVABLE = ("symbol", "wire", "label", "global_label", "junction", "no_connect")


def shift(item: list, dx: float, dy: float) -> None:
    """Move an item, and everything in it that carries a place of its own."""

    def number(value: float) -> str:
        return f"{value:.4f}".rstrip("0").rstrip(".")

    def walk(node: list) -> None:
        for child in node:
            if not isinstance(child, list) or not child:
                continue
            if child[0] in ("at", "xy") and len(child) >= 3:
                child[1], child[2] = number(float(child[1]) + dx), number(float(child[2]) + dy)
            elif child[0] not in ("instances", "pin", "effects", "uuid"):
                walk(child)

    walk(item)


def managed(symbol: list) -> str | None:
    """A part's instance path, for a symbol the tool manages (not a supply symbol)."""

    path = prop(symbol, "Path")
    return path.rsplit(".", 1)[0] if path else None


# --------------------------------------------------------------------------------- steps


def same_paths() -> dict[str, str]:
    """frida-scc-1p1 reference -> the full path of the part that replaces it."""

    table = (HERE / "place_from_1p1.py").read_text()
    block = table[table.index("SAME = {") : table.index("\n}\n", table.index("SAME = {"))]
    full = {path.rsplit(".", 1)[0]: path for path in re.findall(r'\(property "Path" "([^"]+)"', BOARD.read_text())}
    return {reference: full[instance] for reference, instance in re.findall(r'"([A-Z]+\d+)": "([^"]+)"', block)}


def link() -> None:
    root = parse(OLD.read_text())
    paths = same_paths()
    linked = 0
    for symbol in kids(root, "symbol"):
        path = paths.get(prop(symbol, "Reference") or "")
        if path:
            field = ["property", Quoted("Path"), Quoted(path), ["at", "0", "0", "0"]]
            field.append(["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]])
            symbol.insert(
                next(i for i, c in enumerate(symbol) if isinstance(c, list) and c[0] in ("pin", "instances")), field
            )
            linked += 1
        for project in (p for inst in kids(symbol, "instances") for p in kids(inst, "project")):
            project[1] = Quoted(PROJECT)
    ROOT.write_text(dump(root) + "\n")
    print(f"page 1 is frida-scc-1p1's sheet; {linked} of its symbols linked to the parts that replace them")


def arrange(plan_only: bool = False) -> None:
    root = parse(ROOT.read_text())
    sheet = Sheet(root)
    kept = {path.rsplit(".", 1)[0] for path in same_paths().values()}
    stay, move, stubs = [], collections.defaultdict(list), []
    rails: dict[str, list] = collections.defaultdict(list)
    blocks = [(page, title, prefixes) for page, entries in PAGES for title, prefixes in entries]
    for piece in sheet.pieces():
        parts = [managed(item) for item in piece if item[0] == "symbol" and managed(item)]
        if not parts:
            (stubs if any(item[0] == "wire" for item in piece) or len(piece) == 1 else stay).append(piece)
        elif any(part in kept for part in parts):
            stay.append(piece)
        else:
            home = collections.Counter(
                next((i for i, (_, _, prefixes) in enumerate(blocks) if part.startswith(tuple(prefixes))), -1)
                for part in parts
            ).most_common(1)[0][0]
            leaves = [prop(item, "Path") or "" for item in piece if item[0] == "symbol" and managed(item)]
            if len(leaves) >= 3 and all(leaf.endswith(".C") for leaf in leaves):
                rails[blocks[0][0]].append(piece)  # capacitors the tool wired along a rail: with the supplies
            else:
                move[home].append(piece)

    def extent(piece: list[list]) -> tuple[float, float, float, float]:
        boxes = [sheet.box(item) for item in piece]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))

    moving = sum(map(len, move.values())) + sum(map(len, rails.values()))
    print(f"pieces: {len(stay)} stay on page 1, {moving} move, {len(stubs)} leftover stubs")
    for index, pieces in sorted(move.items()):
        title = blocks[index][1] if index >= 0 else "(no block)"
        sizes = sorted(((e[2] - e[0], e[3] - e[1]) for e in map(extent, pieces)), key=lambda s: -s[0] * s[1])
        area = sum(w * h for w, h in sizes)
        print(
            f"  {title}: {len(pieces)} pieces, {area / 100:.0f} cm2, largest {sizes[0][0]:.0f} x {sizes[0][1]:.0f} mm"
        )
    if plan_only:
        return

    # page 1: the stubs go, and so does everything that moves
    gone = {id(item) for piece in stubs for item in piece}
    gone |= {id(item) for pieces in [*move.values(), *rails.values()] for piece in pieces for item in piece}
    root[:] = [child for child in root if id(child) not in gone]
    root_uuid = str(kids(root, "uuid")[0][1])
    for block in kids(root, "title_block"):
        for entry in block[1:]:
            if entry[0] == "rev":
                entry[1] = Quoted("2.0")
            elif entry[0] == "date":
                entry[1] = Quoted(datetime.date.today().isoformat())

    # each block: its pieces packed in rows under its title, as narrow as keeps it under half a page
    full = AREA[2] - AREA[0] - 5.08
    queue = []
    for index, (page, title, _) in enumerate(blocks):
        pieces = move.get(index, []) + (move.get(-1, []) if index == len(blocks) - 1 else [])
        if pieces:
            queue.append((page, title, pieces))
        if (index + 1 == len(blocks) or blocks[index + 1][0] != page) and rails.get(page):
            queue.append((page, "Decoupling capacitors, along each rail", rails[page]))
    packed = []  # (page title, block title, width, height, [(piece, x, y, its box)])
    for page, title, pieces in queue:
        extents = {id(piece): extent(piece) for piece in pieces}
        pieces.sort(key=lambda piece: -(extents[id(piece)][3] - extents[id(piece)][1]))
        widest = max(e[2] - e[0] for e in extents.values())
        best = None
        for target in (full / 4 - 8, full / 3 - 7, full / 2 - 5, full * 3 / 4, full):
            if target < widest and target < full:
                continue
            spots, px, py, shelf, width = [], 0.0, 0.0, 0.0, 0.0
            for piece in pieces:
                e = extents[id(piece)]
                w, h = e[2] - e[0], e[3] - e[1]
                if px and px + w > target:
                    px, py, shelf = 0.0, py + shelf + GAP, 0.0
                spots.append((piece, px, py, e))
                px, shelf, width = px + w + GAP, max(shelf, h), max(width, px + w)
            best = (page, title, max(width, len(title) * 2.3), py + shelf, spots)
            if py + shelf <= (AREA[3] - AREA[1]) / 2 - 12:
                break
        packed.append(best)

    # blocks flow across each page and on to the next
    existing = len(kids(root, "sheet"))
    sheets: list[tuple[str, list]] = []  # (page title, items)
    x = y = row = 0.0
    for page, title, width, height, spots in packed:
        new_row = bool(sheets) and sheets[-1][0] == page and x + width > AREA[2]
        if new_row:
            x, y, row = AREA[0], y + row + 10.16, 0.0
        if not sheets or sheets[-1][0] != page or y + height + 7.62 > AREA[3]:
            sheets.append((page, []))
            x, y, row = AREA[0], AREA[1], 0.0
        number = existing + len(sheets) + 1
        sheet_uuid = mark_uuid("sheet", number)
        for piece, px, py, e in spots:
            dx = round((x + px - e[0]) / GRID) * GRID
            dy = round((y + 5.08 + py - e[1]) / GRID) * GRID
            for item in piece:
                shift(item, dx, dy)
                for inst in kids(item, "instances"):
                    for project in kids(inst, "project"):
                        for route in kids(project, "path"):
                            route[1] = Quoted(f"/{root_uuid}/{sheet_uuid}")
                sheets[-1][1].append(item)
        font = ["effects", ["font", ["size", "2.54", "2.54"], ["bold", "yes"]], ["justify", "left", "bottom"]]
        place = ["at", f"{x:.2f}", f"{y + 2.0:.2f}", "0"]
        sheets[-1][1].append(
            ["text", Quoted(title), ["exclude_from_sim", "no"], place, font, ["uuid", mark_uuid("title", title)]]
        )
        frame = ["rectangle", ["start", f"{x - 2.54:.2f}", f"{y - 2.54:.2f}"]]
        frame += [["end", f"{x + width + 2.54:.2f}", f"{y + height + 7.62:.2f}"]]
        frame += [
            ["stroke", ["width", "0.15"], ["type", "dash"]],
            ["fill", ["type", "none"]],
            ["uuid", mark_uuid("frame", title)],
        ]
        sheets[-1][1].append(frame)
        x, row = x + width + 10.16, max(row, height + 10.16)

    counts = collections.Counter(page for page, _ in sheets)
    seen: collections.Counter[str] = collections.Counter()
    for offset, (page, items) in enumerate(sheets):
        number = existing + offset + 2
        seen[page] += 1
        page_title = page if counts[page] == 1 else f"{page} ({seen[page]} of {counts[page]})"
        sheet_uuid = mark_uuid("sheet", number)
        path = ROOT.with_name(f"{PROJECT}_p{number}.kicad_sch")
        head = (c for c in root if isinstance(c, list) and c[0] in ("version", "generator", "generator_version"))
        child = ["kicad_sch", *head, ["uuid", mark_uuid("page", number)], ["paper", Quoted("A3")]]
        for block in kids(root, "title_block"):
            block = copy.deepcopy(block)
            for entry in block[1:]:
                if entry[0] == "title":
                    entry[1] = Quoted(f"{entry[1]}: {page_title}")
            child.append(block)
        child.append(copy.deepcopy(kids(root, "lib_symbols")[0]))
        child += items
        child.append(["embedded_fonts", "no"])
        path.write_text(dump(child) + "\n")
        top = LINKS[1] + (number - 2) * 7.62
        box = ["sheet", ["at", f"{LINKS[0]}", f"{top}"], ["size", "40.64", "5.08"]]
        box += [["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"]]
        box += [["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0000"]]]
        box += [["uuid", sheet_uuid]]
        font = ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]
        name = ["property", Quoted("Sheetname"), Quoted(f"Page {number}: {page_title}")]
        box.append([*name, ["at", f"{LINKS[0]}", f"{top - 0.7}", "0"], font])
        font = ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"], ["hide", "yes"]]
        box.append(
            ["property", Quoted("Sheetfile"), Quoted(path.name), ["at", f"{LINKS[0]}", f"{top + 5.5}", "0"], font]
        )
        box.append(
            [
                "instances",
                ["project", Quoted(PROJECT), ["path", Quoted(f"/{root_uuid}"), ["page", Quoted(str(number))]]],
            ]
        )
        root.insert(next(i for i, c in enumerate(root) if isinstance(c, list) and c[0] == "sheet_instances"), box)
        parts = sum(1 for item in items if item[0] == "symbol" and managed(item))
        print(f"  page {number}, {page_title}: {parts} parts ({path.name})")
    ROOT.write_text(dump(root) + "\n")


if __name__ == "__main__":
    if sys.argv[1:] == ["link"]:
        link()
    else:
        arrange(plan_only=sys.argv[1:] == ["plan"])
