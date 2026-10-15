"""A floorplan from ALIGN's placement, so cIcCreator and laygo can lay out a circuit without a
hand-written one.

``align_floorplan`` reads the placement of a run of ALIGN on its own (align/build.py: ALIGN
groups the devices into its primitives, derives their symmetry and places and routes them), and
``placement_to_floorplan`` turns the placement into a floorplan in the format of
design/layout/*.json: rows top first, each left to right, ``split`` for a primitive folded over
several rows, ``groups`` with ALIGN's primitives, ``escape`` and ``netlist`` as given, and
``"symmetric": false``: ALIGN's Floorplan constraint then keeps the rows' order without pairing
mirrored places, which only the hand-written floorplans have.

Placement unit: 1 nm, the GDS database unit. Checked on comp_frida1 in tsmc65: every instance's
``transformation`` in ALIGN's ``3_pnr/__placer_dump__.json`` is where the same run's GDS places
it (``sX = -1`` mirrors about ``oX``, KLayout's m90 there), and a row is the row cells' ``H`` tall.

Each ALIGN instance is a primitive (one device, or a group such as DP, CMC or CCP, in ALIGN's
order, reversed where ALIGN mirrors the primitive) or a standard cell. A primitive ``r`` rows
tall (the array ALIGN chose, align/pdk/mos.py) becomes ``split[device] = r``, its parts ``<device>_a``
(top row), ``_b``, ... in its rows at the same place. The row-cell flows draw a standard cell only
in a row of standard cells (netcells' dense frame), so where ALIGN mixes them into a row of
transistors they move to a row of their own just below it, in the same order.

ALIGN's placement can stack primitives along a symmetry line, one per row, with its outline
padded to the AspectRatio constraint: copied as they are, the rows make a tall block with much
filler. ``pack_rows`` merges them toward a square by the row cells' own widths
(``netcells.widths``), each row nested around the ones above it so the rows stay mirrored about
the centre line; a folded device whose parts land in one row is whole again. The cells ALIGN
centres on the line (the middle one of a row of odd count, self-symmetric) have no mirror
partner, and nesting puts each to the right of the rows merged before it: in a row of standard
cells they are placed anew among the others for the shortest nets (ALIGN stacks a comparator's
output inverters on the line, one per row, and nested they all end up on one side).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations, permutations
from math import comb, factorial, log
from pathlib import Path

from flow.layout.pdkproc import in_pdk, pdk_value


def placement_to_floorplan(
    placement: dict,
    groups: dict[str, tuple[str, list[str]]],
    devices: Iterable[str],
    row_height: int,
    *,
    escape: dict,
    netlist: str,
    widths: dict[str, int] | None = None,
    nets: dict[str, frozenset[str]] | None = None,
) -> dict:
    """The floorplan of ALIGN's ``placement`` (``VerilogJsonTop``: the top module's instances and
    their ``transformation``, each leaf's ``bbox``, in nm).

    ``groups``: ALIGN instance -> (primitive kind, its devices in ALIGN's order), from
    ``1_topology``; an instance outside it is a standard cell. ``devices``: the netlist's instance
    names, whose spelling the floorplan takes (ALIGN upper-cases them). ``widths``: the row cells'
    widths (netcells.widths) the rows are packed by, else ALIGN's (its standard cells are wider).
    ``nets``: each instance's nets, by which ``pack_rows`` places the centred standard cells."""

    name_of = {device.upper(): device for device in devices}
    size = {leaf["concrete_name"]: leaf["bbox"] for leaf in placement["leaves"]}
    placed: dict[int, list[tuple[int, int, str, int]]] = defaultdict(list)  # bottom up: (x, order, cell, width)
    split: dict[str, int] = {}
    for inst in placement["modules"][0]["instances"]:
        name = inst["instance_name"]
        x0, y0, x1, y1 = size[inst["concrete_template_name"]]
        w, h, t = x1 - x0, y1 - y0, inst["transformation"]
        x = t["oX"] - w if t["sX"] < 0 else t["oX"]
        y = t["oY"] - h if t["sY"] < 0 else t["oY"]
        if y % row_height or h % row_height:
            raise ValueError(f"{name}: placed at y {y}, {h} tall, off the {row_height} nm rows")
        kind, members = groups.get(name, ("", [name]))
        unknown = [m for m in members if m.upper() not in name_of]
        if unknown:
            raise ValueError(f"{name}: {', '.join(unknown)} not in the netlist")
        cells = [name_of[m.upper()] for m in members][:: -1 if t["sX"] < 0 else 1]
        n = h // row_height
        if n > 1:
            if not kind:
                raise ValueError(f"{name}: a standard cell {n} rows tall")
            split.update(dict.fromkeys(cells, n))
        for k in range(n):  # part _a in the top row
            part = f"_{chr(ord('a') + n - 1 - k)}" if n > 1 else ""
            # each device's share of the row: its own cell's width over its rows, else ALIGN's
            share = {cell: widths[cell] // n if widths and cell in widths else w // len(cells) for cell in cells}
            placed[y // row_height + k] += [(x, j, cell + part, share[cell]) for j, cell in enumerate(cells)]
    rows = []  # top first: (cells with their widths, standard cells)
    for k in sorted(placed, reverse=True):
        entries = sorted(placed[k])
        for std in (False, True):
            part = [(cell, w) for _, _, cell, w in entries if (cell[0] not in "Mm") == std]
            if part:
                rows.append((part, std))
    out = []
    device = lambda cell: cell[:-2] if cell[-2:-1] == "_" and cell[:-2] in split else None  # its split device
    for cells in pack_rows(rows, row_height, nets):  # a split device whose parts share a row is whole again
        parts = [device(c) for c in cells]
        whole = {d for d in parts if d and parts.count(d) == split[d]}
        seen: set[str] = set()
        row = []
        for cell, part_of in zip(cells, parts, strict=True):
            if part_of in whole:
                if part_of not in seen:
                    row.append(part_of)
                seen.add(part_of)
            else:
                row.append(cell)
        out.append(row)
        for d in whole:
            del split[d]
    named: dict[str, list[str]] = {}
    count: dict[str, int] = defaultdict(int)
    for kind, members in sorted(groups.values()):
        named[f"{kind}_{count[kind]}"] = [name_of[m.upper()] for m in members]
        count[kind] += 1
    return {
        "_comment": "From ALIGN's placement (flow/layout/floorplan.py): rows top first, each left to right.",
        "netlist": netlist,
        "split": split,
        "escape": escape,
        "groups": named,
        "symmetric": False,
        "rows": out,
    }


def pack_rows(
    rows: list[tuple[list[tuple[str, int]], bool]], row_height: int, nets: dict[str, frozenset[str]] | None = None
) -> list[list[str]]:
    """ALIGN's rows (top first: their cells with widths in nm, and whether they are standard cells)
    merged into fewer, wider ones toward a square block. Rows merge with the following rows of their
    own kind (transistors or standard cells, which the row cells keep apart), each added around the
    ones merged so far, its left half on the left and its right half on the right, so a row mirrored
    about the centre line ALIGN placed it on stays mirrored; a merged row takes the place of its
    first row. A row of standard cells wider than the block is split into rows of about equal width,
    as many as it needs. Where no packing fits ALIGN's aspect ratio (a row of transistors wider than
    the block would be tall: a gate-level netlist's logic gates as transistors), a row of transistors
    may split too, into nested rings of its mirror pairs (the outermost first), each mirrored like the
    row; the squarer packing of the two is taken. An odd number of rows becomes even where a row of standard cells can be
    split in two: both block edges are then VSS rails, as in the hand-written floorplans (a VDD rail
    at a block edge leaves its implant and well overhangs bare). Of the row widths tried, an even
    number of rows first, then the least area within ALIGN's aspect ratio (2/3 to 3/2), else the
    squarest. ``nets`` (each cell's nets): in a merged row of standard cells, the centred ones (the
    middle cell of a row of odd count) go anew among the others, which keep their order, where the
    summed span of the nets in the row is least (the row as merged unless strictly shorter), before
    a row is split for an even count."""

    centred = {row[len(row) // 2][0] for row, std in rows if std and len(row) % 2}

    def span(cells: list[str]) -> int:
        at: dict[str, list[int]] = defaultdict(list)
        for k, cell in enumerate(cells):
            for net in (nets or {}).get(cell, ()):
                at[net].append(k)
        return sum(max(ks) - min(ks) for ks in at.values())

    def untangle(cells: list[str]) -> list[str]:
        free = [c for c in cells if c in centred]
        fixed = [c for c in cells if c not in centred]
        if not nets or not free or comb(len(cells), len(free)) * factorial(len(free)) > 20_000:
            return cells
        best, least = cells, span(cells)
        for slots in combinations(range(len(cells)), len(free)):
            for order in permutations(free):
                placed, rest = dict(zip(slots, order, strict=True)), iter(fixed)
                row = [placed[k] if k in placed else next(rest) for k in range(len(cells))]
                if (cost := span(row)) < least:
                    best, least = row, cost
        return best

    def split(cells: list[tuple[str, int]], std: bool, limit: int, rings: bool) -> list[list[tuple[str, int]]]:
        total = sum(w for _, w in cells)
        if total <= limit or not (std or (rings and len(cells) >= 4)):
            return [cells]
        n = -(-total // limit)
        if not std:  # the mirror pairs, outside in, each to the ring its middle falls in; a centre cell innermost
            pairs = [[cells[k], cells[-1 - k]] for k in range(len(cells) // 2)]
            if len(cells) % 2:
                pairs[-1].insert(1, cells[len(cells) // 2])
            nested: list[list[list[tuple[str, int]]]] = [[] for _ in range(n)]
            done = 0
            for pair in pairs:
                w = sum(w for _, w in pair)
                nested[min(n - 1, int((done + w / 2) * n / total))].append(pair)
                done += w
            return [
                [p[0] for p in ring] + [p[1] for p in ring if len(p) == 3] + [p[-1] for p in reversed(ring)]
                for ring in nested
                if ring
            ]
        parts: list[list[tuple[str, int]]] = [[] for _ in range(n)]
        done = 0
        for cell, w in cells:  # each cell to the part its middle falls in, in order
            parts[min(n - 1, int((done + w / 2) * n / total))].append((cell, w))
            done += w
        return [part for part in parts if part]

    def merge(limit: int, rings: bool) -> list[tuple[int, list[str], int]]:
        merged: list[tuple[int, list[str], int]] = []  # (first row, cells, width)
        filling: dict[bool, int] = {}  # per kind: the merged row being filled
        for i, (row, std) in enumerate(rows):
            for part in split(row, std, limit, rings):
                cells, width = [c for c, _ in part], sum(w for _, w in part)
                m = filling.get(std)
                if m is not None and merged[m][2] + width <= limit:
                    first, inner, total = merged[m]
                    h = len(cells) // 2
                    merged[m] = (first, cells[:h] + inner + cells[h:], total + width)
                else:
                    filling[std] = len(merged)
                    merged.append((i, cells, width))
        merged = [(i, untangle(cells) if rows[i][1] else cells, width) for i, cells, width in merged]
        std_rows = [m for m in merged if rows[m[0]][1] and len(m[1]) > 1]
        if len(merged) % 2 and std_rows:  # an even number of rows: the fullest row of standard cells in two
            i, cells, _ = max(std_rows, key=lambda m: len(m[1]))
            k = merged.index(next(m for m in merged if m[0] == i and m[1] == cells))
            half = len(cells) // 2
            share = dict(c for row, _ in rows for c in row)
            merged[k : k + 1] = [
                (i, cells[:half], sum(share[c] for c in cells[:half])),
                (i, cells[half:], sum(share[c] for c in cells[half:])),
            ]
        return sorted(merged, key=lambda m: m[0])

    def cost(merged: list[tuple[int, list[str], int]]) -> tuple:
        width, height = max(w for _, _, w in merged), len(merged) * row_height
        skew = abs(log(width / height))
        fit = (0, width * height, skew) if skew <= log(1.5) else (1, skew, width * height)
        return (len(merged) % 2, *fit)

    widths = [sum(w for _, w in row) for row, _ in rows]
    limits = {
        sum(w for w, (_, std) in zip(widths[i:j], rows[i:j], strict=True) if std == kind)
        for kind in (False, True)
        for i in range(len(rows))
        for j in range(i + 1, len(rows) + 1)
    }

    def best(rings: bool) -> list[tuple[int, list[str], int]]:
        split_ = {
            -(-w // k)
            for w, (row, std) in zip(widths, rows, strict=True)
            if std or rings
            for k in range(1, len(row) + 1)
        }
        # no narrower than a row of transistors (a mirror pair of it where it splits) or a standard cell
        narrowest = [
            max(c for _, c in row)
            if std
            else max(row[k][1] + row[-1 - k][1] for k in range(len(row) // 2))
            if rings and len(row) >= 4
            else w
            for w, (row, std) in zip(widths, rows, strict=True)
        ]
        return min((merge(limit, rings) for limit in sorted(limits | split_) if limit >= max(narrowest)), key=cost)

    packed = best(False)
    if cost(packed)[1]:  # outside the aspect ratio: rows of transistors may split
        packed = min(packed, best(True), key=cost)
    return [cells for _, cells, _ in packed]


def align_floorplan(work: Path, netlist: Path, pdk: str, out_dir: Path, *, name: str, escape: dict) -> Path:
    """The floorplan of the placement in ALIGN's work directory ``work`` (a run of ALIGN on its own
    on ``netlist``, align/build.py): ``out_dir/<name>.json`` as design/layout/*.json, with ALIGN's
    raw placement beside it."""

    out_dir.mkdir(parents=True, exist_ok=True)
    _top, _leaves, alternatives, _metrics = json.loads((work / "3_pnr" / "__placer_dump__.json").read_text())
    placement = alternatives[0][1]  # ALIGN's best
    (out_dir / f"{name}_placement.json").write_text(json.dumps(placement, indent=1) + "\n")
    found = json.loads((work / "1_topology" / f"{name}.const.json").read_text())
    groups = {
        c["instance_name"]: (c["template_name"], c["instances"]) for c in found if c["constraint"] == "GroupBlocks"
    }
    instances = [f for f in map(str.split, netlist.read_text().splitlines()) if f and f[0][0] in "MmXx"]
    devices = [f[0] for f in instances]
    # a transistor's d g s b, a standard cell's nets before its cell name
    nets = {f[0]: frozenset(f[1:5] if f[0][0] in "Mm" else [t for t in f[1:-1] if "=" not in t]) for f in instances}
    floorplan = placement_to_floorplan(
        placement,
        groups,
        devices,
        pdk_value(pdk, "rowcell", "H"),
        escape=escape,
        netlist=str(netlist.resolve()),
        widths=in_pdk(pdk, "netcells", "widths", netlist),
        nets=nets,
    )
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(floorplan, indent=1) + "\n")
    in_pdk(pdk, "netcells", "floorplan_netlist", path, pdk, netlist)  # its split and groups hold
    return path
