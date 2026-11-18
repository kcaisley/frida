"""The one layout step every block on the pipeline shares, ALIGN's and nothing else: its module
compiled once in a PDK, its netlists from hdl21 and vlsir in ALIGN's and LVS's contexts
(``flow.circuit.netlists``), its generator's own layout intent (``flow.layout.hdl21align``) as
ALIGN's constraint files, and ALIGN (``flow.layout.build``); the signoff is the CLI's drc, lvs and
pex steps' (``flow.layout.signoff``, ``extracted``).

- ``lay_out_align``: one instance laid out by ALIGN (the CLI's layout step).
- ``lay_out_own``: one instance of a block that lays itself out (its ``layout.py``'s ``lay_out``,
  ``own_layout``), in place of ALIGN's.
- ``inputs``: the netlists and ALIGN's design directory of one instance.
- ``extracted``: a layout's extraction (the CLI's pex step).
- ``block_netlist``: an instance's netlist as simulated, as hdl21 and vlsir write it (a design's
  identity: ``flow.opt.runner.identity``, ``flow.netlist_hashes``).

A block is found by name: its ``subckt`` module's ``netlist`` and ``Nets``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from klayout import db

from flow import tools
from flow.layout.build import annealed, build_design, other_router, pdk_router, route_opens, route_shorts
from flow.layout.hdl21align import pnr_input
from flow.layout.kpex import Engine
from flow.layout.signoff import Checker
from flow.layout.stats import layout_stats

ROOT = Path(__file__).resolve().parents[2]


LOG = logging.getLogger("flow.layout")


PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65", "sky130", "gf180")


def _generator(block: str):
    subckt = import_module(f"flow.{block}.subckt")
    return subckt.netlist, subckt.Nets


def cell_um(gds: Path) -> list[float]:
    """Width and height (um) of the GDS's largest top cell."""

    layout = db.Layout()
    layout.read(str(gds))
    box = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).dbbox()
    return [round(box.width(), 3), round(box.height(), 3)]


def free_rows(gds: Path, pdk: str) -> dict[str, Any] | None:
    """The rows a block leaves free under its capacitors, where they stack over the rows
    (``stacked_over_rows``): the widest stretch of whole rows of the PDK's row cells under them
    that no cell stands in (between a band of cells at their bottom and one at their top, say),
    across the capacitors' width, where the converter places its other circuits. Its extent (um,
    the GDS's coordinates: ALIGN's GDS ``<NAME>_0.gds`` beside ``gds``, its placed instances) and
    its row count; None where the block has no such capacitors or no row is free. The capacitors'
    own routes (their plates' runs from their drivers to their channels) may cross it."""
    from flow.layout.build import _mom_units
    from flow.layout.devices.momcap.table import stacked_over_rows
    from flow.layout.devices.mosfet.netlist import row_height_nm

    units = _mom_units(gds.parent)
    placed = gds.parent / f"{gds.stem.upper()}_0.gds"
    if not units or not placed.exists() or any(stacked_over_rows(pdk, n) is None for n in units.values()):
        return None
    layout = db.Layout()
    layout.read(str(placed))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    caps, cells = db.Box(), []
    for inst in top.each_inst():
        name = inst.cell.name.upper()
        if any(name.startswith(unit) for unit in units):
            caps += inst.bbox()
        else:
            cells.append(inst.bbox())
    if caps.empty():
        return None
    h = round(row_height_nm(pdk) / 1000 / layout.dbu)
    # the cells under the capacitors, their rows' rail lines (a cell's outline past its rails by less
    # than a row), and the stretches between them
    under = sorted(
        (-(-b.bottom // h) * h, b.top // h * h)
        for b in cells
        if b.left < caps.right and b.right > caps.left and b.top > caps.bottom and b.bottom < caps.top
    )
    edges, reach = [], -(-caps.bottom // h) * h
    for lo, hi in under:
        if lo > reach:
            edges.append((reach, lo))
        reach = max(reach, hi)
    edges.append((reach, caps.top // h * h))
    y0, y1 = max(edges, key=lambda e: e[1] - e[0])
    if y1 <= y0:
        return None
    um = layout.dbu
    return {
        "x_um": [round(caps.left * um, 3), round(caps.right * um, 3)],
        "y_um": [round(y0 * um, 3), round(y1 * um, 3)],
        "rows": (y1 - y0) // h,
    }


def supply_lines(gds: Path, pdk: str) -> list[dict[str, Any]] | None:
    """The block's supply rail lines as the layout ``gds`` draws them, apart (each a pin the
    converter's power grid joins, ``flow.layout.post.rail_pins``): for each line its supply (by its
    labels), its y and each piece's x extent (um), and whether it runs from the outline's left edge
    to its right (the layout's extent), where the top level's row rails abut it. None where the
    layout has no rail labels."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    m1 = db.Region(top.begin_shapes_rec(layout.layer(*tech.LAYERS["M1"]))).merged()
    texts = top.shapes(layout.layer(*tech.PIN_TEXT["M1"]))
    edge = top.bbox()
    um, rail = layout.dbu, tech.RAIL
    lines: dict[int, dict[str, Any]] = {}
    for shape in texts.each():
        if not shape.is_text() or shape.text.string.lower() not in ("vdd", "vss"):
            continue
        y = shape.text.y
        line = lines.setdefault(y, {"net": shape.text.string.lower(), "y_um": round(y * um, 3), "pieces_um": []})
        band = db.Region(db.Box(edge.left, y - rail, edge.right, y + rail))
        for piece in (
            (m1 & band).interacting(db.Region(db.Box(shape.text.x - 1, y - 1, shape.text.x + 1, y + 1))).each()
        ):
            x = [round(piece.bbox().left * um, 3), round(piece.bbox().right * um, 3)]
            if x not in line["pieces_um"]:
                line["pieces_um"].append(x)
    if not lines:
        return None
    left, right = round(edge.left * um, 3), round(edge.right * um, 3)
    found = []
    for y in sorted(lines):
        line = lines[y]
        line["pieces_um"].sort()
        line["x_um"] = [line["pieces_um"][0][0], line["pieces_um"][-1][1]]
        line["edges"] = len(line["pieces_um"]) == 1 and line["x_um"] == [left, right]
        found.append(line)
    return found


def under_array(gds: Path, pdk: str) -> dict[str, Any] | None:
    """The region under a block's capacitor array that its layout leaves free below the shield, for
    the converter's own rows of standard cells and decaps (its abstract leaves it unobstructed): the
    array's footprint (its MOM units as ALIGN placed them, ``<NAME>_0.gds`` beside ``gds``) less its
    plates' landings at its top and bottom edges (the metal below the shield its units draw) and,
    where the array stands over the rows, less the rows of drivers under it (``free_rows``). Its
    extent (um), the layers below the shield it leaves free and those something occupies there
    (area, um^2); the landings the post step left and those the units drew (their stubs below the
    shield at the array's edges, ``flow.layout.post.idle_landings``);
    ALIGN's routes below the shield inside it (none: every plate's route reaches its landing from
    outside the array). None where the block has no capacitor array."""
    from flow.layout.build import _mom_units

    units = _mom_units(gds.parent)
    placed = gds.parent / f"{gds.stem.upper()}_0.gds"
    if not units or not placed.exists():
        return None
    tech = import_module(f"pdk.{pdk}.layout.tech")
    shield = min(tech.MOM_LAYERS[-n] for n in units.values()) - 1
    raw = db.Layout()
    raw.read(str(placed))
    top = max(raw.top_cells(), key=lambda cell: cell.bbox().area())
    caps, ids = db.Box(), set()
    for inst in top.each_inst():
        if any(inst.cell.name.upper().startswith(unit) for unit in units):
            caps += inst.bbox()
            ids.add(inst.cell_index)
    if caps.empty():
        return None
    below = [f"M{k}" for k in range(1, shield)]

    def cells_layer(name: str) -> db.Region:
        index = raw.find_layer(*tech.LAYERS[name])
        if index is None:
            return db.Region()
        it = top.begin_shapes_rec(index)
        it.unselect_all_cells()
        it.select_cells(list(ids))  # the units and what they hold
        return db.Region(it).merged()

    stubs = db.Region()
    for name in below:
        stubs += cells_layer(name)
    stubs.merge()
    middle = caps.center().y
    low = max((p.bbox().top for p in stubs.each() if p.bbox().center().y < middle), default=caps.bottom)
    high = min((p.bbox().bottom for p in stubs.each() if p.bbox().center().y >= middle), default=caps.top)
    y0, y1 = low, high
    free = free_rows(gds, pdk)
    if free:  # over the rows: the rows of drivers under the array's edges are not the region
        y0, y1 = max(y0, round(free["y_um"][0] / raw.dbu)), min(y1, round(free["y_um"][1] / raw.dbu))
    region = db.Region(db.Box(caps.left, y0, caps.right, y1))
    row = round(tech.H * 0.001 / raw.dbu)  # the kit's row height (nm in its tech)
    edges = db.Region(db.Box(caps.left, y0, caps.right, y0 + 1)) + db.Region(db.Box(caps.left, y1 - 1, caps.right, y1))
    # ALIGN's routes: the top cell's own shapes
    routes = {}
    for name in [*below, *(f"V{k}" for k in range(1, shield))]:
        index = raw.find_layer(*tech.LAYERS[name]) if name in tech.LAYERS else None
        if index is not None:
            inside = db.Region(top.shapes(index)) & region
            if not inside.is_empty():
                routes[name] = inside.count()
    layout = db.Layout()
    layout.read(str(gds))
    final = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    skip = re.compile(r"^(M|V)(\d+)$")
    occupied, empty = {}, []
    for name, pair in sorted(tech.LAYERS.items()):
        level = skip.match(name)
        if pair is None or "." in name or name in ("BND", "TEXT") or "MOM" in name:
            continue
        if level and int(level.group(2)) >= shield:
            continue
        index = layout.find_layer(*pair)
        # what lies within it, not the rows' rails, wells and taps reaching in across its edges
        shapes = db.Region(final.begin_shapes_rec(index)).merged() if index is not None else db.Region()
        cut = shapes & region
        spill = [p for p in cut.interacting(edges).each() if p.bbox().height() < row // 2]
        inside = cut - db.Region(spill)
        if inside.is_empty():
            empty.append(name)
        else:
            occupied[name] = round(inside.area() * layout.dbu**2, 3)
    um = raw.dbu
    done = Path(f"{gds}.post.json")
    post = json.loads(done.read_text()).get("landings", {}) if done.exists() else {}
    return {
        "x_um": [round(caps.left * um, 3), round(caps.right * um, 3)],
        "y_um": [round(y0 * um, 3), round(y1 * um, 3)],
        "below": f"M{shield}",
        "free": empty,
        "occupied": occupied,
        # the landings the post step left (one a plate, where its route came: ``post.idle_landings``)
        "landings": post.get("kept", stubs.count()),
        "landings_drawn": post.get("drawn", stubs.count()),
        "routes_inside": routes,
    }


def row_fill(gds: Path) -> dict[str, Any] | None:
    """What the post step put in the rows' empty sites (``flow.layout.post.Fill``, its record in
    ``<gds>.post.json``): the decaps (count, fingers, gate area um^2, capacitance fF from the PDK's
    moscap table, NMOS and PMOS), the plain filler (stretches, sites, um), the rows left empty and
    the gaps under a row's height; None where the post step recorded none."""
    done = Path(f"{gds}.post.json")
    return json.loads(done.read_text()).get("fill") if done.exists() else None


def net_texts(gds: Path) -> list[tuple[str, int, int, str]]:
    """Every net ALIGN routed in the layout ``gds`` (its placed-and-routed ``3_pnr/<NAME>_0.json``
    beside it: each wire's net, a child module's by its path, ``XDRIVE_MAIN_0/N0``), as a label for
    the extraction: the net's lower-case name at the middle of its widest metal wire (database units,
    as the JSON's nanometres). None where ALIGN wrote no such file."""
    found = sorted(gds.parent.rglob(f"3_pnr/{gds.stem.upper()}_0.json"))
    if not found:
        return []
    best: dict[str, tuple[int, tuple[str, int, int]]] = {}
    for terminal in json.loads(found[0].read_text()).get("terminals", []):
        net, layer = terminal.get("netName"), terminal.get("layer", "")
        if not net or not re.fullmatch(r"M\d+", layer):
            continue
        x0, y0, x1, y1 = terminal["rect"]
        width = min(x1 - x0, y1 - y0)
        if net not in best or width > best[net][0]:
            best[net] = (width, (layer, (x0 + x1) // 2, (y0 + y1) // 2))
    return [(layer, x, y, net.lower()) for net, (_, (layer, x, y)) in sorted(best.items())]


def extracted(
    pdk: str,
    gds: Path,
    name: str,
    run_dir: Path,
    checker: Checker = Checker.OPEN,
    tolerance: float = 0.05,
    engine: Engine = Engine.FASTERCAP,
) -> dict[str, Any]:
    """The layout's extraction into ``run_dir``: through KLayout-PEX (``Checker.OPEN``:
    ``flow.layout.kpex``, every net of the GDS's largest top cell, by its label, ALIGN's route
    (``net_texts``) or KLayout's name, each pair's capacitance and each net's to ground) by its
    ``engine``, FasterCap to a block's parasitics' accuracy (``tolerance``, 5 %: their relative
    sizes, which a Monte Carlo varies) or the 2.5-D engine (the one the kit names for the block,
    ``flow.layout.signoff.engine``), or by the kit's extractor (``Checker.CALIBRE``). Its netlist
    and extractor; KLayout-PEX's also its engine, its nets' probes (``flow.layout.kpex``), its nets
    and capacitors, their total and the nets' own capacitances (to everything else), largest first.
    Raises where the extraction fails."""
    from flow.layout.annotate import capacitors
    from flow.layout.kpex import Extractor
    from flow.layout.signoff import run_layout_pex

    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).name
    if checker is Checker.CALIBRE:
        netlist = run_layout_pex(pdk, gds, top, name, run_dir, extractor=Extractor.CALIBRE)
        LOG.info(f"PEX: {netlist} (the kit's extractor)")
        return {"netlist": str(netlist), "extractor": "the kit's (Calibre)"}
    netlist = run_layout_pex(pdk, gds, top, name, run_dir, tolerance=tolerance, texts=net_texts(gds), engine=engine)
    own: dict[str, float] = {}
    found = capacitors(netlist)
    for a, b, c in found:
        for net in {a, b} - {"0"}:
            own[net] = own.get(net, 0.0) + c
    nets = dict(sorted(own.items(), key=lambda item: -item[1]))
    count, total = len(found), sum(c for _a, _b, c in found)
    made = f"FasterCap, {tolerance:.0%}" if engine is Engine.FASTERCAP else "2.5-D"
    LOG.info(f"PEX: {len(nets)} nets, {count} capacitors, {total * 1e15:.4g} fF in all by {made} ({netlist})")
    return {
        "netlist": str(netlist),
        "probes": str(netlist.with_name(f"{name}.probes.json")),
        "extractor": f"KLayout-PEX ({made})",
        "engine": engine.name.lower(),
        "nets": nets,
        "capacitors": count,
        "total_f": total,
    }


def own_layout(block: str) -> bool:
    """Whether ``block`` lays itself out: its ``layout.py`` gives ``lay_out(params, pdk, run_dir)``
    (docs/pipeline.md), which the layout step runs in place of ALIGN's (``lay_out_align``)."""
    return find_spec(f"flow.{block}.layout") is not None and callable(
        getattr(import_module(f"flow.{block}.layout"), "lay_out", None)
    )


def block_netlist(block: str, params, pdk: str, path: Path) -> Path:
    """``block``'s ``params`` compiled in ``pdk`` as simulated (no layout view), its netlist as hdl21
    and vlsir write it (the LVS context, no library text) at ``path``: a design's identity."""
    from flow.circuit.netlists import Context, compile_block, package, write

    generator, nets = _generator(block)
    return write(package(compile_block(generator, params, pdk, Path(path).stem, nets), Context.LVS), path)


def inputs(
    block: str, out_dir: Path, pdk: str, design: str, params, *, seconds: dict | None = None
) -> tuple[Path, list[str], Path, bool]:
    """What ALIGN and the signoff take for one instance of ``block`` (``lay_out_align``'s, without
    ALIGN): its module compiled once (as its ``params.layout_view`` gives), its netlists in ALIGN's and
    LVS's contexts (``out_dir/netlist/<design>.sp``, ``.cdl``) and ALIGN's design directory
    (``out_dir/align/input/<design>``, a constraint file a module that states its layout). Returns
    the design directory, the library cells it calls, the LVS netlist, and whether its top states
    its placement; ``seconds`` gets each one's."""
    from flow.circuit.netlists import Context, align_design, compile_block, lvs_source, package, write

    seconds = {} if seconds is None else seconds
    LOG.info(f"{block} {design} in {pdk}: the module, its netlists and its constraints")
    generator, nets = _generator(block)
    view = getattr(import_module(f"flow.{block}.params"), "layout_view", None)
    compiled = compile_block(generator, view(params) if view else params, pdk, design, nets, seconds)
    started = time.monotonic()
    netlist = write(package(compiled, Context.ALIGN), out_dir / "netlist" / f"{design}.sp")
    source = lvs_source(compiled, out_dir / "netlist" / f"{design}.cdl")
    LOG.info(f"netlists: {netlist} (ALIGN), {source} (LVS)")
    seconds["netlist"] = round(time.monotonic() - started, 2)
    started = time.monotonic()
    input_dir, cells = align_design(compiled, out_dir / "align" / "input")
    seconds["floorplan"] = round(time.monotonic() - started, 2)
    return input_dir, cells, source, pnr_input(compiled.module) is not None


# a layout's parts under names every layout flow shares (ALIGN's now, OpenROAD's later), in order;
# a part a flow does not have is None (ALIGN has no clock tree, nor a global route apart from its
# detailed one)
PARTS = ("read", "mapping", "floorplan", "placement", "global_route", "detail_route", "cts", "finishing")
# ALIGN's loggers by the part they log: the first record of each starts it
_ALIGN_PARTS = (
    ("align.compiler", "read"),
    ("align.main", "read"),
    ("align.primitive", "mapping"),
    ("align.cell_fabric", "mapping"),
    ("align.pnr.build_pnr_model", "placement"),
    ("align.pnr.placer", "placement"),
    ("align.PnR.placer", "placement"),
    ("align.pnr.router", "detail_route"),
    ("align.PnR.router", "detail_route"),
)


class _AlignParts(logging.Handler):
    """ALIGN's log as it comes, timed: where each of its parts begins (the first record of a logger
    ``_ALIGN_PARTS`` names, in order: a part never starts before the one before it); after the
    routing, its last records and the GDS's finishing."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.starts: dict[str, float] = {}
        self.last = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        self.last = record.created
        part = next((part for prefix, part in _ALIGN_PARTS if record.name.startswith(prefix)), None)
        if (
            part is not None
            and part not in self.starts
            and all(PARTS.index(part) > PARTS.index(seen) for seen in self.starts)
        ):
            self.starts[part] = record.created


def _parts(own: dict[str, float], starts: dict[str, float], begun: float, ended: float) -> dict[str, float | None]:
    """The layout's seconds by part (``PARTS``): the flow's own compilation and netlists as read,
    its constraints as the floorplan, then ALIGN's parts from where each began to the next, the
    time after its routing as finishing."""
    found: dict[str, float | None] = dict.fromkeys(PARTS)
    found["read"] = own.get("parameters", 0.0) + own.get("netlist", 0.0)
    found["floorplan"] = own.get("floorplan", 0.0)
    marks = sorted(starts.items(), key=lambda item: item[1])
    edges = [begun if not index else at for index, (_, at) in enumerate(marks)] + [ended]
    for (part, _), start, end in zip(marks, edges, edges[1:], strict=False):
        found[part] = round((found[part] or 0.0) + max(0.0, end - start), 2)
    return {part: (round(value, 2) if value is not None else None) for part, value in found.items()}


def lay_out_align(block: str, pdk: str, params, out: Path, design: str | None = None) -> dict[str, Any]:
    """One instance of ``block`` in ``pdk`` laid out by ALIGN into ``out``, the design ``design``
    (the block's name by default): its netlists and ALIGN's design directory (``inputs``: a
    constraint file a module that states its layout; ALIGN places one that states nothing), then
    ALIGN by the PDK's router for the block (``out/align/``), by its other router where that one fails
    (``out/align_<router>/``); routed again, its placer's seed another, where ALIGN's route joins two
    nets and its placer annealed (twice at most: a placement the generator states whole is
    enumerated, the same whatever the seed). An attempt that has not placed and routed in half an
    hour fails (``ALIGN_TIMEOUT``). The GDS, its LVS source, ALIGN's netlist, its size, the router,
    the nets its route joins and each part's seconds (``parts``: the module's compilation, the
    netlists, the floorplan, ALIGN)."""
    # ALIGN's placer can search for hours on the larger sizings
    os.environ.setdefault("ALIGN_TIMEOUT", "1800")
    design = design or block
    seconds: dict[str, float] = {}
    input_dir, cells, source, placed = inputs(block, out, pdk, design, params, seconds=seconds)
    router, shorts, gds, work = pdk_router(pdk, block), {}, None, out / "align"
    timed = _AlignParts()
    logging.getLogger("align").addHandler(timed)
    begun = time.time()
    for seed in range(3):
        try:
            work = out / "align"
            gds = build_design(pdk, input_dir, cells, work, placed=placed, seed=seed, router=router)
        except Exception as error:  # noqa: BLE001 - ALIGN failed or stopped: the other router may lay it out
            again = other_router(router)
            LOG.warning(f"ALIGN with the {router} router failed ({error!r}): laid out again by its {again} router")
            work = out / f"align_{again}"
            try:
                gds = build_design(pdk, input_dir, cells, work, placed=placed, seed=seed, router=again)
            except Exception:  # noqa: BLE001 - neither router laid it out: the first one's failure
                raise error from None
            router = again
        shorts = route_shorts(work, design)
        if not shorts or not annealed(work):
            break
        LOG.info(f"ALIGN's route joins {len(shorts)} pairs of nets: routed again, placer seed {seed + 1}")
    assert gds is not None
    # nets the route leaves in pieces (an open LVS's deck may not see: ``route_opens``): laid out
    # again by the other router, the layout with fewer kept
    opens = route_opens(Path(gds), pdk)
    if opens and work == out / "align":
        again = other_router(router)
        LOG.warning(
            f"ALIGN's {router} route leaves {len(opens)} nets in pieces ({', '.join(opens)}): by its {again} router"
        )
        try:
            other = build_design(pdk, input_dir, cells, out / f"align_{again}", placed=placed, router=again)
        except Exception as error:  # noqa: BLE001 - the first router's layout stands
            LOG.warning(f"ALIGN with the {again} router failed ({error!r}): the {router} router's layout kept")
        else:
            fewer = route_opens(Path(other), pdk)
            if len(fewer) < len(opens):
                work = out / f"align_{again}"
                gds, router, opens, shorts = other, again, fewer, route_shorts(work, design)
            LOG.info(f"the {router} router's layout kept: {len(opens)} nets in pieces")
    logging.getLogger("align").removeHandler(timed)
    # the time after ALIGN's last part: its last records, the GDS written and finished (post.py)
    ended = time.time()
    if timed.starts:
        timed.starts.setdefault("finishing", timed.last)
    parts = _parts(seconds, timed.starts, begun, ended)
    size = cell_um(gds)
    LOG.info(f"layout: {gds} ({' × '.join(f'{v:g}' for v in size)} um) by the {router} router")
    laid = {
        "gds": str(gds),
        "source": str(source),
        "netlist": str(out / "netlist" / f"{design}.sp"),
        "cell_um": size,
        "router": router,
        "placed": placed,
        "route_shorts": {"/".join(pair): n for pair, n in shorts.items()} or None,
        "route_opens": opens or None,
        "parts": parts,
        "tool": {"name": "align", "version": tools.align()},
    }
    fill = row_fill(Path(gds))
    if fill:
        laid["fill"] = fill
        LOG.info(
            f"layout: row fill {fill['decaps']} decaps ({fill['decap ff']:g} fF, {fill['decap gate um2']:g} um2 of"
            f" gate), {fill['filler sites']} filler sites, {len(fill['rows left empty'])} rows left empty"
        )
    free = free_rows(Path(gds), pdk)
    if free:
        laid["free_rows"] = free
        LOG.info(f"layout: {free['rows']} rows free under the capacitors, x {free['x_um']} y {free['y_um']} um")
    under = under_array(Path(gds), pdk)
    if under:
        laid["under_array"] = under
        LOG.info(
            f"layout: under the array x {under['x_um']} y {under['y_um']} um, free below {under['below']}:"
            f" {', '.join(under['free'])}; occupied: {under['occupied'] or 'none'}; {under['landings']} landings"
        )
        if under["routes_inside"]:
            LOG.warning(f"layout: ALIGN routes under the array below its shield: {under['routes_inside']}")
    lines = supply_lines(Path(gds), pdk)
    if lines:
        laid["supply_lines"] = lines
        short = [f"{line['net']} {line['y_um']}" for line in lines if not line["edges"]]
        if short:
            LOG.warning(f"layout: supply lines that do not run edge to edge (um): {', '.join(short)}")
    return {**laid, "stats": layout_stats(work, design, Path(gds), pdk, laid)}


def lay_out_own(block: str, pdk: str, params, out: Path) -> dict[str, Any]:
    """One instance of a block that lays itself out (``own_layout``) in ``pdk``, into ``out``: its
    ``lay_out(params, pdk, out)``, which gives the GDS. The GDS and its size, its LVS source (the
    one its signoff plan names, else ``out/source.cdl`` where ``lay_out`` wrote one), and its
    signoff plan where it planned one (``out/signoff.json``, ``flow.layout.signoff.write_plan``),
    which the CLI's drc, lvs and pex steps run."""
    from flow.layout.signoff import read_plan

    LOG.info(f"{block} in {pdk}: its own layout (flow.{block}.layout.lay_out) into {out}")
    gds = Path(import_module(f"flow.{block}.layout").lay_out(params, pdk, out))
    size = cell_um(gds)
    LOG.info(f"layout: {gds} ({' × '.join(f'{v:g}' for v in size)} um)")
    source, plan = out / "source.cdl", out / "signoff.json"
    if plan.exists():
        source = read_plan(plan).lvs_source_path
    return {
        "gds": str(gds),
        "source": str(source) if source.exists() else None,
        "cell_um": size,
        "plan": str(plan) if plan.exists() else None,
    }
