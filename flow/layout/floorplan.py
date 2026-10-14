"""A floorplan from ALIGN's placement, so cIcCreator and laygo can lay out a circuit without a
hand-written one.

``align_floorplan`` runs ALIGN on the netlist up to placement, free (ALIGN groups the devices
into its primitives and places them by its symmetry, on one axis: align/run.py), and
``placement_to_floorplan`` turns the placement into a floorplan in the format of
design/layout/*.json: rows top first, each left to right, ``split`` for a primitive folded over
several rows, ``groups`` with ALIGN's primitives, ``escape`` and ``netlist`` as given, and
``"symmetric": false``: ALIGN's Floorplan constraint then keeps the rows' order without pairing
mirrored places, which only the hand-written floorplans have.

Placement unit: 1 nm, the GDS database unit. Checked on comp_frida1 in tsmc65: every instance's
``transformation`` in ALIGN's ``3_pnr/__placer_dump__.json`` is where the same run's GDS places
it (``sX = -1`` mirrors about ``oX``, KLayout's m90 there), and a row is the row cells' ``H`` tall.

Each ALIGN instance is a primitive (one device, or a pair such as DP, CMC or CCP: device A left
of B, swapped where ALIGN mirrors the primitive) or a standard cell. A primitive ``r`` rows tall
(align/pdk/gen_param.py ``fold_rows``) becomes ``split[device] = r``, its parts ``<device>_a``
(top row), ``_b``, ... in its rows at the same place. The row-cell flows draw a standard cell only
in a row of standard cells (netcells' dense frame), so where ALIGN mixes them into a row of
transistors they move to a row of their own just below it, in the same order.

ALIGN's single-axis placement stacks the primitives along the centre line, mostly one per row,
with its outline padded to the AspectRatio constraint: copied as they are, the rows make a tall
block with much filler. ``pack_rows`` merges them toward a square by the row cells' own widths
(``netcells.widths``), each row nested around the ones above it so the rows stay mirrored about
the centre line; a folded device whose parts land in one row is whole again.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from math import log
from pathlib import Path

from flow.layout.align.run import run_align
from flow.layout.pdkproc import access_points, in_pdk, pdk_value


def placement_to_floorplan(
    placement: dict,
    groups: dict[str, tuple[str, list[str]]],
    devices: Iterable[str],
    row_height: int,
    *,
    escape: dict,
    netlist: str,
    widths: dict[str, int] | None = None,
) -> dict:
    """The floorplan of ALIGN's ``placement`` (``VerilogJsonTop``: the top module's instances and
    their ``transformation``, each leaf's ``bbox``, in nm).

    ``groups``: ALIGN instance -> (primitive kind, its devices in ALIGN's order), from
    ``1_topology``; an instance outside it is a standard cell. ``devices``: the netlist's instance
    names, whose spelling the floorplan takes (ALIGN upper-cases them). ``widths``: the row cells'
    widths (netcells.widths) the rows are packed by, else ALIGN's (its standard cells are wider)."""

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
    rows = []  # top first: (cells, width, standard cells)
    for k in sorted(placed, reverse=True):
        entries = sorted(placed[k])
        for std in (False, True):
            part = [(cell, w) for _, _, cell, w in entries if (cell[0] not in "Mm") == std]
            if part:
                rows.append(([cell for cell, _ in part], sum(w for _, w in part), std))
    out = []
    device = lambda cell: cell[:-2] if cell[-2:-1] == "_" and cell[:-2] in split else None  # its split device
    for cells in pack_rows(rows, row_height):  # a split device whose parts share a row is whole again
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


def pack_rows(rows: list[tuple[list[str], int, bool]], row_height: int) -> list[list[str]]:
    """ALIGN's rows (top first: cells, width in nm, whether standard cells) merged into fewer, wider
    ones toward a square block. Rows merge with the following rows of their own kind (transistors
    or standard cells, which the row cells keep apart), each added around the ones merged so far,
    its left half on the left and its right half on the right, so a row mirrored about the centre
    line ALIGN placed it on stays mirrored. A merged row takes the place of its first row. Of the
    row widths tried, the one whose block (widest row by rows) has ALIGN's aspect ratio (2/3 to
    3/2) in the least area, else the squarest."""

    def merge(limit: int) -> list[tuple[int, list[str], int]]:
        merged: list[tuple[int, list[str], int]] = []  # (first row, cells, width)
        filling: dict[bool, int] = {}  # per kind: the merged row being filled
        for i, (cells, width, std) in enumerate(rows):
            m = filling.get(std)
            if m is not None and merged[m][2] + width <= limit:
                first, inner, total = merged[m]
                h = len(cells) // 2
                merged[m] = (first, cells[:h] + inner + cells[h:], total + width)
            else:
                filling[std] = len(merged)
                merged.append((i, list(cells), width))
        return sorted(merged)

    def cost(merged: list[tuple[int, list[str], int]]) -> tuple:
        width, height = max(w for _, _, w in merged), len(merged) * row_height
        skew = abs(log(width / height))
        return (0, width * height, skew) if skew <= log(1.5) else (1, skew, width * height)

    limits = {
        sum(w for _, w, std in rows[i:j] if std == kind)
        for kind in (False, True)
        for i in range(len(rows))
        for j in range(i + 1, len(rows) + 1)
    }
    widest = max(w for _, w, _ in rows)
    best = min((merge(limit) for limit in sorted(limits) if limit >= widest), key=cost)
    return [cells for _, cells, _ in best]


def align_floorplan(netlist: Path, pdk: str, out_dir: Path, *, name: str, escape: dict) -> Path:
    """Run ALIGN up to placement on ``netlist`` in ``pdk`` and write ``out_dir/<name>.json``,
    a floorplan as design/layout/*.json, with ALIGN's raw placement beside it."""

    access_points(pdk)
    pdk_dir = in_pdk(pdk, "flow.layout.align.make_pdk", "build", pdk, out_dir / "pdk")
    design = in_pdk(pdk, "flow.layout.align.make_design", "make_design", pdk, netlist, out_dir / "input", name=name)
    work = run_align(design, pdk_dir, out_dir / "align", flow_stop="3_pnr:place", one_axis=True)
    _top, _leaves, alternatives, _metrics = json.loads((work / "3_pnr" / "__placer_dump__.json").read_text())
    placement = alternatives[0][1]  # ALIGN's best
    (out_dir / f"{name}_placement.json").write_text(json.dumps(placement, indent=1) + "\n")
    found = json.loads((work / "1_topology" / f"{name}.const.json").read_text())
    groups = {
        c["instance_name"]: (c["template_name"], c["instances"]) for c in found if c["constraint"] == "GroupBlocks"
    }
    devices = [f[0] for f in map(str.split, netlist.read_text().splitlines()) if f and f[0][0] in "MmXx"]
    floorplan = placement_to_floorplan(
        placement,
        groups,
        devices,
        pdk_value(pdk, "rowcell", "H"),
        escape=escape,
        netlist=str(netlist.resolve()),
        widths=in_pdk(pdk, "netcells", "widths", netlist),
    )
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(floorplan, indent=1) + "\n")
    in_pdk(pdk, "netcells", "floorplan_netlist", path, pdk, netlist)  # its split and groups hold
    return path
