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
from flow.layout.build import annealed, build_design, other_router, pdk_router, route_shorts
from flow.layout.hdl21align import pnr_input
from flow.layout.kpex import Engine
from flow.layout.signoff import Checker
from flow.layout.stats import layout_stats

ROOT = Path(__file__).resolve().parents[2]


LOG = logging.getLogger("flow.layout")


PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")


def _generator(block: str):
    subckt = import_module(f"flow.{block}.subckt")
    return subckt.netlist, subckt.Nets


def cell_um(gds: Path) -> list[float]:
    """Width and height (um) of the GDS's largest top cell."""

    layout = db.Layout()
    layout.read(str(gds))
    box = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).dbbox()
    return [round(box.width(), 3), round(box.height(), 3)]


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
    ALIGN by the PDK's router (``out/align/``), by its other router where that one fails
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
    router, shorts, gds, work = pdk_router(pdk), {}, None, out / "align"
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
        "parts": parts,
        "tool": {"name": "align", "version": tools.align()},
    }
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
