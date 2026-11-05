"""The one layout step every block on the pipeline shares: its module compiled once in a PDK, its
netlists from hdl21 and vlsir in ALIGN's and LVS's contexts (``flow.circuit.netlists``), its
generator's own layout intent (``flow.layout.hdl21align``) as ALIGN's constraint files, ALIGN
(``flow.layout.build``) and the signoff (``flow.layout.signoff``).

- ``inputs``: the netlists and ALIGN's design directory of one instance (``python -m flow layout
  --plan``).
- ``layout_one``: one instance laid out and signed off; ``layout_named``: in every PDK.
- ``block_netlist``: an instance's netlist as simulated, as hdl21 and vlsir write it (a design's
  identity: ``flow.opt.runner.identity``, ``flow.netlist_hashes``).

A block is found by name: its ``subckt`` module's ``netlist`` and ``Nets``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

from klayout import db

from flow.layout.build import build_design, other_router, pdk_router
from flow.layout.hdl21align import pnr_input
from flow.layout.signoff import Checker, RowSignoff, signoff

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


def finish(run_dir: Path, summary: dict[str, dict[str, Any]], failures: dict[str, str]) -> Path:
    """Write ``summary.json`` (and ``failures.json``, or remove an earlier run's where nothing
    failed); raise when anything failed."""

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    path = run_dir / "failures.json"
    if failures:
        path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} layouts failed; see {path}")
    path.unlink(missing_ok=True)
    return run_dir


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


def extracted(pdk: str, gds: Path, name: str, run_dir: Path, tolerance: float = 0.05) -> dict[str, Any]:
    """The layout's extraction by FasterCap through KLayout-PEX (``flow.layout.kpex``: every net of
    the GDS's largest top cell, by its label or KLayout's name, each pair's capacitance and each
    net's to ground) to a block's parasitics' accuracy (``tolerance``, 5 %: their relative sizes,
    which a Monte Carlo varies), in ``run_dir``: its netlist, its nets and capacitors, their total, and the
    nets' own capacitances (to everything else), largest first; or the error where it failed."""
    from flow.layout.signoff import run_layout_pex

    layout = db.Layout()
    layout.read(str(gds))
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).name
    try:
        netlist = run_layout_pex(pdk, gds, top, name, run_dir, tolerance=tolerance, texts=net_texts(gds))
    except Exception as error:  # noqa: BLE001 - recorded with the layout, which stands
        LOG.warning(f"PEX: {error}")
        return {"error": repr(error)}
    own: dict[str, float] = {}
    count = 0
    for line in netlist.read_text().splitlines():
        found = re.match(r"\s*c_\d+\s*\(\s*(\S+)\s+(\S+)\s*\)\s*capacitor\s+c=([0-9.eE+-]+)f", line)
        if found:
            a, b, c_ff = found.group(1), found.group(2), float(found.group(3))
            count += 1
            for net in {a, b} - {"0"}:
                own[net] = own.get(net, 0.0) + c_ff * 1e-15
    nets = dict(sorted(own.items(), key=lambda item: -item[1]))
    total = (
        sum(float(found.group(1)) for found in re.finditer(r"capacitor\s+c=([0-9.eE+-]+)f", netlist.read_text()))
        * 1e-15
    )
    LOG.info(f"PEX: {len(nets)} nets, {count} capacitors, {total * 1e15:.4g} fF in all ({netlist})")
    return {
        "netlist": str(netlist),
        "extractor": f"KLayout-PEX (FasterCap, {tolerance:.0%})",
        "nets": nets,
        "capacitors": count,
        "total_f": total,
    }


def all_pdks(run_dir: Path, case: Callable[..., Path], *args: Any, pdks: tuple[str, ...] = PDKS) -> Path:
    """``case(run_dir / pdk, pdk, *args)`` in every PDK (or ``pdks``); every failure collected, the
    summaries merged."""

    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    for pdk in pdks:
        sub = run_dir / pdk
        try:
            case(sub, pdk, *args)
        except Exception as error:  # noqa: BLE001 - report every PDK
            found = sub / "failures.json"
            failures.update(json.loads(found.read_text()) if found.exists() else {pdk: repr(error)})
        if (sub / "summary.json").exists():
            summary.update(json.loads((sub / "summary.json").read_text()))
    return finish(run_dir, summary, failures)


def layout_named(
    block: str, run_dir: Path, name: str, params, *, auto: bool = False, pdks: tuple[str, ...] = PDKS
) -> Path:
    """The named instance ``name`` of ``block`` in each of ``pdks`` by ALIGN, into
    ``run_dir/<pdk>/``: placed as its generator states, or (``auto``, or where it states nothing)
    by ALIGN on its own."""

    design = f"{block}_{name}"

    def case(sub: Path, pdk: str) -> Path:
        return layout_one(block, sub, pdk, design, params, auto=auto)

    return all_pdks(run_dir, case, pdks=pdks)


def layout_one(
    block: str,
    out_dir: Path,
    pdk: str,
    design: str,
    params,
    *,
    auto: bool = False,
    checker: Checker = Checker.OPEN,
    seed: int = 0,
    pex: bool = True,
) -> Path:
    """One instance of ``block`` in ``pdk``, the design ``design``, into ``out_dir``: its module
    compiled once (``flow.circuit.netlists``), its netlists from hdl21 and vlsir in ALIGN's and LVS's
    contexts (``out_dir/netlist/<design>.sp``, ``.cdl``), ALIGN's design directory (a constraint file
    a module that states its layout; none where ``auto``: ALIGN places it), ALIGN's layout (its
    placer's ``seed``), its signoff against the LVS netlist and, with ``pex``, its extraction by
    KLayout-PEX (``out_dir/align``, ``out_dir/summary.json``). The block is laid out as its
    ``params.layout_view`` gives, where it has one (the comparator's output stage as the PDK's
    library cells)."""
    seconds: dict[str, float] = {}
    design_input = inputs(block, out_dir, pdk, design, params, auto=auto, seconds=seconds)
    return signed_off_design(out_dir, pdk, design, *design_input, seconds, checker, seed, pex)


def block_netlist(block: str, params, pdk: str, path: Path) -> Path:
    """``block``'s ``params`` compiled in ``pdk`` as simulated (no layout view), its netlist as hdl21
    and vlsir write it (the LVS context, no library text) at ``path``: a design's identity."""
    from flow.circuit.netlists import Context, compile_block, package, write

    generator, nets = _generator(block)
    return write(package(compile_block(generator, params, pdk, Path(path).stem, nets), Context.LVS), path)


def inputs(
    block: str, out_dir: Path, pdk: str, design: str, params, *, auto: bool = False, seconds: dict | None = None
) -> tuple[Path, list[str], Path, bool]:
    """What ALIGN and the signoff take for one instance of ``block`` (``layout_one``'s, without
    ALIGN): its module compiled once (as its ``params.layout_view`` gives), its netlists in ALIGN's and
    LVS's contexts (``out_dir/netlist/<design>.sp``, ``.cdl``) and ALIGN's design directory
    (``out_dir/align/input/<design>``, a constraint file a module that states its layout; none where
    ``auto``). Returns the design directory, the library cells it calls, the LVS netlist, and
    whether its top states its placement; ``seconds`` gets each one's."""
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
    seconds["netlist"] = round(time.monotonic() - started, 1)
    started = time.monotonic()
    input_dir, cells = align_design(compiled, out_dir / "align" / "input", placed=not auto)
    seconds["floorplan"] = round(time.monotonic() - started, 1)
    return input_dir, cells, source, not auto and pnr_input(compiled.module) is not None


def _signed_off_better(new: RowSignoff, old: RowSignoff) -> bool:
    """Whether the signoff ``new`` is better than ``old``: its LVS matching where the other's does
    not, else as matching and fewer DRC violations."""

    def rank(check: RowSignoff) -> tuple[bool, float]:
        return check.lvs_correct is not False, -(check.drc_violations or 0)

    return rank(new) > rank(old)


def signed_off_design(
    run_dir: Path,
    pdk: str,
    name: str,
    input_dir: Path,
    cells: list[str],
    source: Path,
    placed: bool,
    seconds: dict[str, float] | None = None,
    checker: Checker = Checker.OPEN,
    seed: int = 0,
    pex: bool = True,
) -> Path:
    """ALIGN's layout of the design directory ``input_dir`` (``flow.circuit.netlists.align_design``)
    into ``run_dir/align/``, by the PDK's router, signed off in ``run_dir/align/signoff/`` against
    ``source`` (the LVS netlist); where LVS did not match, laid out again by ALIGN's other router
    (``run_dir/align_<router>/``) and that layout kept where its LVS matches (the two routers fail
    on different designs). With ``pex``, extracted (``<align dir>/pex/``, ``extracted``; not where
    LVS did not match: a layout other than its netlist; an extraction that fails is recorded, the
    layout not failed); ``summary.json`` with each step's seconds and the router that drew the
    layout, as far as the steps ran (``finish``: and ``failures.json``, raising, where it failed)."""
    summary: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    out = run_dir / "align"
    seconds = dict(seconds or {})
    entry: dict[str, Any] = {"seconds": seconds}
    summary[f"{pdk}/align"] = entry
    try:
        started = time.monotonic()
        router, check, failed = pdk_router(pdk), None, None
        try:
            gds = build_design(pdk, input_dir, cells, out, placed=placed, seed=seed, router=router)
        except Exception as error:  # noqa: BLE001 - ALIGN failed or stopped: the other router may lay it out
            failed = error
            LOG.warning(f"ALIGN with the {router} router failed ({error!r})")
        else:
            entry.update(gds=str(gds), cell_um=cell_um(gds), router=router)
            LOG.info(f"layout: {gds} ({' × '.join(f'{v:g}' for v in entry['cell_um'])} um)")
            check = signoff(pdk, gds, source, out / "signoff", checker)
            seconds.update(drc=check.drc_seconds, lvs=check.lvs_seconds)
        seconds["layout"] = round(time.monotonic() - started, 1)
        if check is None or check.lvs_correct is False or check.drc_violations:  # the other router's, if better
            again, started = other_router(router), time.monotonic()
            why = "no layout" if check is None else f"LVS correct {check.lvs_correct}, DRC {check.drc_violations}"
            LOG.info(f"laid out again by ALIGN's {again} router ({why})")
            try:
                other = build_design(pdk, input_dir, cells, run_dir / f"align_{again}", placed=placed, router=again)
                checked = signoff(pdk, other, source, run_dir / f"align_{again}" / "signoff", checker)
            except Exception as error:  # noqa: BLE001 - the first layout stands, if there is one
                LOG.warning(f"the {again} router's layout failed: {error!r}")
                if check is None:
                    raise failed from None  # neither router laid it out: the first one's failure
            else:
                seconds[f"layout_{again}"] = round(time.monotonic() - started, 1)
                if check is None or _signed_off_better(checked, check):
                    out, gds, check = other.parent.parent, other, checked
                    entry.update(gds=str(gds), cell_um=cell_um(gds), router=again)
                    seconds.update(drc=checked.drc_seconds, lvs=checked.lvs_seconds)
                    LOG.info(f"layout: {gds} by the {again} router")
        entry.update(drc_violations=check.drc_violations, lvs_correct=check.lvs_correct)
        if check.drc_violations or check.lvs_correct is False:
            failures[f"{pdk}/align"] = f"DRC {check.drc_violations} violations, LVS correct {check.lvs_correct}"
        if pex and check.lvs_correct is False:  # a layout other than its netlist: nothing to extract
            entry["pex"] = {"skipped": "LVS did not match"}
        elif pex:  # LVS matched, or no deck checked it
            started = time.monotonic()
            entry["pex"] = extracted(pdk, gds, name, out / "pex")
            seconds["pex"] = round(time.monotonic() - started, 1)
    except Exception as error:  # noqa: BLE001 - report the failure with every other PDK's
        entry["error"] = failures[f"{pdk}/align"] = repr(error)
        drc = out / "signoff" / "drc_violations.json"
        if drc.exists():  # DRC ran before the failure
            entry["drc_violations"] = sum(json.loads(drc.read_text())["violations"].values())
    return finish(run_dir, summary, failures)
