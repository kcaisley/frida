"""The bodies of the CLI's steps over a block's design space (``python -m flow``, ``flow.__main__``).

An instance is its parameters: its id is ``<pdk>__<digest>``, the digest the first 12 hex digits of
the SHA-1 of its flat parameters (``digest``), as ``flow.sweep.lookup`` keys the models' cache. A
run (``new_run``) is ``build/<block>/<run>/``, each instance in ``<pdk>/<name>/`` there (a named
instance by its name, a grid's by its digest), a folder a step.

The characterization's steps: ``write_netlist`` (the circuit as simulated and its size, into
``netlist/``), ``simulate`` (each testbench run of ``runs_of``, or ``circuit_runs``, simulated and
its measurement kept as HDF5, into ``sim/<run>/``) and ``record`` (``sweep.record`` of the kept
measurements: the instance's ``instance.json``, its id, parameters, level, metrics, details and
waves). ``layout``: each instance of the newest run laid out, by its block's own layout flow
(``layout.py``'s ``lay_out``) where it has one, else by ALIGN as its generator places it; signed
off, and its area joins the record. ``table``: each block's newest run in each PDK (a run of some
PDKs alone keeps the others' from the run before) as the viewer's table
(``build/web/data/sweep/<block>.json``: one row per instance, the parameters that differ, then the
metrics) and one file per instance (its details, waves, layout and schematic).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from functools import cache
from importlib import import_module
from importlib.util import find_spec
from multiprocessing import get_context
from pathlib import Path

from flow.sweep import flat_params

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "build"  # a block's runs: build/<block>/<run>/
RUN_STAMP = re.compile(r"\d{8}_\d{6}")  # a run's name (new_run, run)
DATA_DIR = ROOT / "build/web/data/sweep"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")


def sweep_blocks() -> list[str]:
    """Every block with a ``sweep.py``, in name order: a part of a block by its dotted name
    (``<block>.<part>``, ``flow/<block>/<part>``)."""
    flow = ROOT / "flow"
    return sorted(
        ".".join(path.parent.relative_to(flow).parts) for path in (*flow.glob("*/sweep.py"), *flow.glob("*/*/sweep.py"))
    )


def params_key(flat: dict) -> str:
    """A flat parameter row (``flat_params``) as canonical JSON: the key an instance is found by."""
    return json.dumps(flat, sort_keys=True)


def digest(params) -> str:
    """An instance's identity: the first 12 hex digits of the SHA-1 of its flat parameters, from its
    parameter class or the flat row a record holds."""
    flat = params if isinstance(params, dict) else flat_params(params)
    return hashlib.sha1(params_key(flat).encode()).hexdigest()[:12]


def instance_id(pdk: str, params) -> str:
    """``<pdk>__<digest>``: the instance's id in the viewer's tables and its directory in a run."""
    return f"{pdk}__{digest(params)}"


@cache
def design_space(block: str, pdk: str) -> dict:
    """The block's instances in ``pdk``, by digest: a design space may reach the same parameters
    twice (two arrays that come out alike), which are one instance. A block on the pipeline gives
    its grids and named instances (``labelled_space``), another its sweep's ``instances``."""
    sweep = import_module(f"flow.{block}.sweep")
    if hasattr(sweep, "instances"):
        return {digest(params): params for params in sweep.instances(pdk)}
    return {ident: params for ident, (_label, params) in labelled_space(block, pdk).items()}


def _valid(block: str):
    """The block's ``params.valid`` (which designs build in a PDK), where it has one: a block whose
    parameter classes admit only what builds (the ADC's), or without a params module, has none."""
    if find_spec(f"flow.{block}.params") is None:
        return None
    return getattr(import_module(f"flow.{block}.params"), "valid", None)


@cache
def labelled_space(block: str, pdk: str) -> dict:
    """A block's instances in ``pdk`` by digest, each with its label (its grid and the values that
    vary there, or its name; the first that reaches it): its sweep's grids and swept named instances
    (``flow.pipeline.design``) that its ``params.valid`` admits in ``pdk``."""
    from flow import pipeline

    sweep = import_module(f"flow.{block}.sweep")
    valid = _valid(block)
    space: dict = {}
    for label, params in pipeline.design(sweep, pdk):
        if valid is None or valid(params, pdk):
            space.setdefault(digest(params), (label, params))
    return space


def select(block: str, pdk: str, names: list[str]) -> dict:
    """The instances ``names`` pick in ``pdk``, by digest, with their labels: each a named instance
    of the block's sweep (swept or not), the label of one of its instances (``grid(name,
    parameter=value, ...)``), or a digest. Those ``params.valid`` does not admit in ``pdk`` are left out."""
    from flow import pipeline

    sweep = import_module(f"flow.{block}.sweep")
    named = pipeline.names(sweep)
    labelled = labelled_space(block, pdk)
    by_label = {label: (ident, params) for ident, (label, params) in labelled.items()}
    picked: dict = {}
    for name in names:
        if name in named:
            params = named[name]()
            label = name
        elif name in by_label or name in labelled:
            ident, params = by_label[name] if name in by_label else (name, labelled[name][1])
            label = labelled[ident][0]
        else:
            raise LookupError(
                f"no instance {name!r} of {block} in {pdk}: a name ({', '.join(named)}), a label as "
                "the run's records hold it, or a digest"
            )
        valid = _valid(block)
        if valid is None or valid(params, pdk):
            picked.setdefault(digest(params), (label, params))
        else:
            print(f"{name}: not valid in {pdk}, left out")
    return picked


def instance_params(block: str, pdk: str, ident: str):
    """The parameters of the instance of ``block`` in ``pdk`` with this digest."""
    try:
        return design_space(block, pdk)[ident]
    except KeyError:
        raise LookupError(
            f"no instance of the {block} design space in {pdk} has the digest {ident}: its parameters "
            f"are not among flow.{block}.sweep.instances({pdk!r}) (changed since it ran?)"
        ) from None


def _json(value):
    """JSON of a record: non-finite numbers as null."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if hasattr(value, "item"):  # numpy scalars
        return _json(value.item())
    return value


def write_record(path: Path, record: dict) -> None:
    """``instance.json``, replaced whole: the layout step rewrites records others may be reading."""
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(_json(record), indent=1) + "\n")
    temporary.replace(path)


def leveled(block: str) -> bool:
    """Whether the block's ``sweep.runs`` takes the evaluation level (``flow.pipeline.Level``); a
    block whose runs take none characterizes alike at every level."""
    from inspect import signature

    runs = getattr(import_module(f"flow.{block}.sweep"), "runs", None)
    return runs is not None and "level" in signature(runs).parameters


def runs_of(block: str, pdk: str, params, level=None) -> dict:
    """The testbench runs that characterize ``params`` in ``pdk`` at ``level`` (None: ``FULL``), by
    name (``sweep.runs``; a block whose runs take no level, its only runs)."""
    from flow import pipeline

    sweep = import_module(f"flow.{block}.sweep")
    return sweep.runs(pdk, params, level or pipeline.Level.FULL) if leveled(block) else sweep.runs(pdk, params)


def circuit_runs(block: str, pdk: str, params) -> dict:
    """The circuit simulator's runs of a block whose full characterization is behavioral: its runs at
    ``Level.CIRCUIT`` that are not its full ones (none where both are alike, the comparator's)."""
    from flow import pipeline

    if not leveled(block):
        return {}
    full = runs_of(block, pdk, params)
    return {name: tb for name, tb in runs_of(block, pdk, params, pipeline.Level.CIRCUIT).items() if name not in full}


def _compiled(block: str, pdk: str, params, path: Path):
    """The block's ``params`` compiled in ``pdk`` (its requests resolved to the PDK's devices), its
    netlist as simulated written at ``path`` (the LVS context, ``flow.circuit.netlists``); the
    compiled module."""
    from flow.circuit.netlists import Context, compile_block, package, write

    subckt = import_module(f"flow.{block}.subckt")
    compiled = compile_block(subckt.netlist, params, pdk, path.stem, subckt.Nets)
    write(package(compiled, Context.LVS), path)
    return compiled.module


def write_netlist(block: str, pdk: str, params, folder: Path) -> dict:
    """The netlist step's outputs in ``folder``: the circuit as simulated (``<block>.cdl``) and its
    size (``geometry.json``: ``flow.sweep.geometry``'s child cells, devices and device area); the
    size."""
    from flow.sweep import geometry

    folder.mkdir(parents=True, exist_ok=True)
    module = _compiled(block, pdk, params, folder / f"{block}.cdl")
    sizes = geometry(module, pdk)
    (folder / "geometry.json").write_text(json.dumps(_json(sizes), indent=1) + "\n")
    return sizes


def simulate(block: str, pdk: str, runs: dict, folder: Path) -> dict[str, Path]:
    """Each of ``runs`` simulated in ``folder/<run>/`` (``sim.simulate``), read back (its
    ``sim.read`` where it has one, else ``flow.pipeline.read``) and kept as a measurement
    (``result.h5``, ``flow.analysis.io.write_measurement``), its raw file removed; a run whose
    measurement is kept already is not simulated again. Each run's measurement file, by name."""
    import hdl21 as h

    from flow import pipeline
    from flow.analysis.io import write_measurement

    h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
    sim = import_module(f"flow.{block}.sim")
    read = getattr(sim, "read", pipeline.read)
    kept = {}
    for name, tb in runs.items():
        path = folder / name / "result.h5"
        if not path.exists():
            raw = sim.simulate(tb, folder / name)
            write_measurement(path, read(raw, tb))
            raw.unlink()
        kept[name] = path
    return kept


def _base_record(block: str, pdk: str, params, label: str | None, name: str | None) -> dict:
    """A record's identity: its block, id, name in its run, PDK, label and parameters, nothing measured."""
    return {
        "block": block,
        "id": instance_id(pdk, params),
        "name": name,
        "pdk": pdk,
        "label": label,
        "level": None,
        "params": flat_params(params),
        "metrics": {},
        "details": [],
        "waves": {},
        "error": None,
    }


def record(
    block: str,
    pdk: str,
    params,
    out: Path,
    files: dict[str, Path],
    sizes: dict,
    *,
    label: str | None = None,
    name: str | None = None,
    level=None,
    netlist: Path | None = None,
    seconds: float = 0.0,
) -> dict:
    """The instance's record from its kept measurements (``files``, by run: ``simulate``'s) and its
    size (``sizes``: ``write_netlist``'s), written as ``out/instance.json``: its metrics (the size's
    and ``sweep.record``'s), details, the waves of the runs the record names (their measurement
    files from the repository's root), the level its runs ran at (None for a block whose runs take
    no level), its netlist and its seconds (``seconds``, those of the steps before it, and its own)."""
    import hdl21 as h

    from flow import pipeline
    from flow.analysis.io import read_measurement

    start = time.time()
    h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
    sweep = import_module(f"flow.{block}.sweep")
    result = sweep.record({run: read_measurement(path) for run, path in files.items()})
    entry = _base_record(block, pdk, params, label, name)
    entry.update(
        level=(level or pipeline.Level.FULL).value if leveled(block) else None,
        metrics={**sizes, **result.metrics},
        details=[detail.to_json() for detail in result.details],
        waves={wave: _shown(files[run]) for wave, run in result.waves.items()},
        netlist=_shown(netlist) if netlist else None,
        seconds=round(seconds + time.time() - start, 1),
    )
    write_record(out / "instance.json", entry)
    return entry


def failed_record(block: str, pdk: str, params, out: Path, error: str, *, label=None, name=None) -> dict:
    """An instance's record of a characterization that failed (``error``, its step's traceback),
    written as ``out/instance.json``, so the viewer's table shows the failure."""
    entry = {**_base_record(block, pdk, params, label, name), "error": error}
    out.mkdir(parents=True, exist_ok=True)
    write_record(out / "instance.json", entry)
    return entry


def characterize(block: str, run_dir: Path, pdk: str, params) -> dict:
    """One instance characterized in ``run_dir`` as the CLI's netlist, sim and record steps do it
    (``write_netlist``, ``simulate``, ``record``), without their bookkeeping: the models' on-demand
    characterization (``flow.sweep.lookup``). Its record; a failure recorded, not raised."""
    start = time.time()
    try:
        sizes = write_netlist(block, pdk, params, run_dir / "netlist")
        files = simulate(block, pdk, runs_of(block, pdk, params), run_dir / "sim")
        return record(
            block,
            pdk,
            params,
            run_dir,
            files,
            sizes,
            netlist=run_dir / "netlist" / f"{block}.cdl",
            seconds=time.time() - start,
        )
    except Exception:  # noqa: BLE001 - the record carries the failure
        return failed_record(block, pdk, params, run_dir, traceback.format_exc(limit=6)[-4000:])


def run_time(run: Path) -> str:
    """When a run was made, as a stamp that sorts in time (``YYYYmmdd_HHMMSS``, then its microseconds
    where it has them): its ``run.json``'s (``new_run``), or its name where it is a stamp (a run from
    before runs had names)."""
    marker = run / "run.json"
    if marker.exists():
        return json.loads(marker.read_text())["created"]
    return run.name


def new_run(block: str, name: str | None = None, run_dir: Path | None = None) -> Path:
    """A run of ``block``: ``run_dir``, or ``build/<block>/<name>`` (``name``: now's stamp where
    None), made with its ``run.json`` (when it was made) where it is new; an existing one as it is."""
    now = datetime.now().astimezone()
    run = run_dir if run_dir is not None else RUNS_DIR / block / (name or now.strftime("%Y%m%d_%H%M%S"))
    if not (run / "run.json").exists():
        run.mkdir(parents=True, exist_ok=True)
        created = now.strftime("%Y%m%d_%H%M%S.%f")
        (run / "run.json").write_text(json.dumps({"block": block, "created": created}) + "\n")
    return run


def _runs(block: str) -> list[Path]:
    """The block's runs: the directories in ``build/<block>/`` made as runs (``new_run``: a
    ``run.json``) or named by their stamp (the runs from before), not its other outputs there; a
    block not yet characterized, its layout runs (``build/<block>/layout/``), whose instances carry
    their layouts alone."""

    def made(folder: Path) -> list[Path]:
        if not folder.is_dir():
            return []
        return [
            path
            for path in folder.iterdir()
            if path.is_dir() and ((path / "run.json").exists() or RUN_STAMP.fullmatch(path.name))
        ]

    return made(RUNS_DIR / block) or made(RUNS_DIR / block / "layout")


def newest_run(block: str, pdk: str | None = None) -> Path:
    """The block's newest run (by ``run_time``); with ``pdk``, the newest that ran in that PDK (a
    run of some PDKs alone leaves each other PDK's newest records in the run before)."""
    runs = sorted((path for path in _runs(block) if pdk is None or (path / pdk).is_dir()), key=run_time)
    if not runs:
        raise FileNotFoundError(f"no run of {block}{f' in {pdk}' if pdk else ''} in {RUNS_DIR / block}")
    return runs[-1]


def pdk_runs(block: str) -> dict[str, Path]:
    """Each PDK's newest run of the block (``newest_run``), the PDKs in name order."""
    runs = {}
    for run in sorted(_runs(block), key=run_time, reverse=True):
        for pdk in run.iterdir():
            if pdk.is_dir():
                runs.setdefault(pdk.name, run)
    return dict(sorted(runs.items()))


def instance_dirs(run: Path, pdk: str) -> dict[str, Path]:
    """The instances of ``run`` in ``pdk`` by digest: each directory of ``run/<pdk>/`` with a record,
    a named instance's by its name (its record gives its digest), a grid's by its digest."""
    found = {}
    for path in sorted((run / pdk).glob("*/instance.json")):
        ident = path.parent.name
        if not re.fullmatch(r"[0-9a-f]{12}", ident):
            ident = json.loads(path.read_text()).get("id", "").split("__")[-1]
        found.setdefault(ident, path.parent)
    return found


def layout_job(block: str, instance_dir: Path, pdk: str, pex: bool = True) -> dict:
    """One instance's layout and its signoff, into ``instance_dir/layout``: by the block's own flow
    where it lays itself out (``_own_layouts``), else ALIGN's by the shared layout step
    (``_module_layouts``); the record's layout entry (also written into its ``instance.json``);
    ``pex``: each layout extracted (KLayout-PEX)."""

    from flow.layout.step import own_layout

    # an attempt that has not placed and routed in half an hour fails (ALIGN's placer can search
    # for hours on the larger sizings); the next attempt, if any, follows
    os.environ.setdefault("ALIGN_TIMEOUT", "1800")
    record = json.loads((instance_dir / "instance.json").read_text())
    params = instance_params(block, pdk, instance_dir.name)
    start = time.time()
    made = _own_layouts if own_layout(block) else _module_layouts
    results = made(block, instance_dir / "layout", pdk, params, pex)
    clean = [r for r in results if r["error"] is None and r["drc_violations"] == 0 and r["lvs_correct"]]
    entry = {**(clean or [r for r in results if r["error"] is None] or results)[0], "attempts": len(results)}
    return _layout_record(record, instance_dir, entry, start)


def _layout_record(record: dict, instance_dir: Path, entry: dict, start: float) -> dict:
    """The layout entry, its seconds and the record's area metrics, written into ``instance.json``."""
    entry["seconds"] = round(time.time() - start, 1)
    record["layout"] = entry
    if entry.get("w_um"):
        area = entry["w_um"] * entry["h_um"]
        record["metrics"]["layout_area_um2"] = area
        gate = record["metrics"].get("device_area_um2")
        record["metrics"]["density"] = gate / area if gate else None
    write_record(instance_dir / "instance.json", record)
    return entry


def _shown(path) -> str:
    """A path as a record holds it: from the repository root where it is under it, as written or
    once resolved."""
    path = Path(path).absolute()
    path = path if path.is_relative_to(ROOT) else path.resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _shown_pex(pex: dict | None) -> dict | None:
    """An extraction's entry as a record holds it: its netlist's path as ``_shown`` gives one, so a
    copy of the repository (a remote worker's snapshot) reads its own."""
    return {**pex, "netlist": _shown(pex["netlist"])} if pex and pex.get("netlist") else pex


def _own_layouts(block: str, out: Path, pdk: str, params, pex: bool = True) -> list[dict]:
    """The layout of an instance of a block that lays itself out (``flow.layout.step.lay_out_one``,
    in ``out``): its entry, as ``_module_layouts`` gives one, with who signed it off (``signoff``:
    ``lay_out`` itself, the ``shared`` signoff against its source, or ``drc`` alone), in a list."""
    from flow.layout.step import lay_out_one

    result: dict = {"error": None, "floorplan": "lay_out"}
    try:
        try:
            lay_out_one(block, out, pdk, params, pex=pex)
        except RuntimeError:  # a failed signoff: in its summary
            pass
        summary = json.loads((out / "summary.json").read_text())[f"{pdk}/lay_out"]
        if summary.get("error"):
            raise RuntimeError(summary["error"])
        w, h_um = summary["cell_um"]
        result.update(
            gds=_shown(summary["gds"]),
            netlist=_shown(out / "source.cdl") if (out / "source.cdl").exists() else None,
            w_um=w,
            h_um=h_um,
            signoff=summary.get("signoff"),
            drc_violations=summary.get("drc_violations"),
            lvs_correct=summary.get("lvs_correct"),
            warnings=summary.get("warnings"),
            pex=_shown_pex(summary.get("pex")),
        )
    except Exception:  # noqa: BLE001 - every instance reports its own failure
        result["error"] = traceback.format_exc(limit=6)[-4000:]
    return [result]


def _module_layouts(block: str, out: Path, pdk: str, params, pex: bool = True) -> list[dict]:
    """The shared step's layout of an instance (``flow.layout.step.layout_one``, in
    ``out/align_floorplan``): as its generator places it, by ALIGN on its own only where the
    generator states nothing (no second attempt by ALIGN alone: a generator's placement is the
    intent, and ALIGN's own search on a large array runs for hours); routed again, its placer's seed
    another, where ALIGN's route joins two nets and its placer annealed (twice at most: a placement
    the generator states whole is enumerated, the same whatever the seed). Its entry, as
    ``layout_job``'s, in a list."""
    from flow.layout.build import annealed, route_shorts
    from flow.layout.step import layout_one

    work = out / "align_floorplan"
    result: dict = {"error": None, "floorplan": "generator"}
    try:
        for seed in range(3):
            try:
                layout_one(block, work, pdk, block, params, seed=seed, pex=pex)
            except RuntimeError:  # a failed signoff: in its summary
                pass
            # the layout kept (by the PDK's router, or the other one where LVS matched only there)
            kept = json.loads((work / "summary.json").read_text())[f"{pdk}/align"].get("gds")
            routed = Path(kept).parents[1] if kept else work / "align"
            shorts = route_shorts(routed, block)
            if not shorts or not annealed(routed):
                break
        summary = json.loads((work / "summary.json").read_text())[f"{pdk}/align"]
        if summary.get("error"):
            raise RuntimeError(summary["error"])
        w, h_um = summary["cell_um"]
        result.update(
            route_shorts={"/".join(pair): n for pair, n in shorts.items()} or None,
            gds=str(Path(summary["gds"]).resolve().relative_to(ROOT)),
            netlist=str((work / "netlist" / f"{block}.cdl").relative_to(ROOT)),
            w_um=w,
            h_um=h_um,
            router=summary.get("router"),
            drc_violations=summary.get("drc_violations"),
            lvs_correct=summary.get("lvs_correct"),
            pex=_shown_pex(summary.get("pex")),
        )
    except Exception:  # noqa: BLE001 - every instance reports its own failure
        result["error"] = traceback.format_exc(limit=6)[-4000:]
    return [result]


def layout(
    blocks: list[str], workers: int, *, pdks: tuple[str, ...] = PDKS, pex: bool = True, redo: bool = False
) -> None:
    """Lay out every characterized instance of the newest runs of ``blocks`` in ``pdks`` not yet laid
    out DRC clean and LVS correct (or signed off as its own layout flow states: LVS as ``lay_out``
    expected, or DRC alone where it has no source; ``redo``: every one), each extracted where
    ``pex``."""

    jobs = []
    for block in blocks:
        for path in sorted(newest_run(block).glob("*/*/instance.json")):
            record = json.loads(path.read_text())
            if record["pdk"] not in pdks:
                continue
            params = design_space(block, record["pdk"]).get(record["id"].split("__")[-1])
            if params is None:
                print(f"{path.parent.relative_to(RUNS_DIR)}: not in the design space any more, not laid out")
                continue
            entry = record.get("layout") or {}
            done = (
                entry.get("gds")
                and not entry.get("error")
                and entry.get("drc_violations") == 0
                and (entry.get("lvs_correct") or entry.get("signoff") in ("lay_out", "drc"))
            )
            if record["error"] is None and (redo or not done):
                jobs.append((block, path.parent, record["pdk"], pex))
    print(f"{len(jobs)} layouts on {workers} workers")
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1) as pool:
        futures = {pool.submit(layout_job, *job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            _block, path, _pdk, _pex = futures[future]
            try:
                entry = future.result()
            except Exception as error:  # noqa: BLE001 - a worker that died
                entry = {"error": repr(error), "seconds": math.nan}
            status = (
                "failed"
                if entry["error"]
                else f"{entry['w_um']:.1f} x {entry['h_um']:.1f} um, DRC {entry['drc_violations']}, LVS {entry['lvs_correct']}"
                f"{'' if entry.get('floorplan') else ', ALIGN alone'}"
            )
            print(f"[{done}/{len(jobs)}] {path.relative_to(RUNS_DIR)}: {status} in {entry['seconds']} s", flush=True)


def _block_netlist(block: str, ident: str, record: dict, data_dir: Path) -> Path | None:
    """An instance laid out by no one: the netlist its netlist step wrote (its record's ``netlist``),
    or its block's compiled in its PDK (``flow.layout.step.block_netlist``: a record from before),
    else None."""

    from flow.layout.step import block_netlist

    if record["error"] is not None:
        return None
    if record.get("netlist") and (ROOT / record["netlist"]).exists():
        return ROOT / record["netlist"]
    try:
        params = instance_params(block, record["pdk"], ident.split("__")[-1])
        return block_netlist(block, params, record["pdk"], data_dir / block / ident / f"{block}.cdl")
    except Exception:  # noqa: BLE001 - the page shows no netlist rather than no page
        return None


def instance_views(block: str, ident: str, record: dict, data_dir: Path) -> dict:
    """An instance's views for its page, under ``data_dir/<block>/`` (``build/web/data/sweep``): its layout
    flattened onto the PDK's generic layers (``flow.web.export``), its schematic and netlist (its
    layout's, else its block's: ``_block_netlist``), and
    the index of its waveforms (``<ident>/traces.json``, as the waveform panel reads one); the
    files written, by kind."""

    from flow.analysis.io import read_measurement
    from flow.web.export import export_layout, export_schematic, trace_index, wave_entry

    files: dict = {}
    entry = record.get("layout") or {}
    if entry.get("gds"):
        files["file"] = f"sweep/{block}/{ident}.layout.json"
        export_layout(str(ROOT / entry["gds"]), record["pdk"], str(data_dir.parent / files["file"]))
    netlist = ROOT / entry["netlist"] if entry.get("netlist") else _block_netlist(block, ident, record, data_dir)
    if netlist is not None:
        files["netlist_file"] = f"sweep/{block}/{ident}.netlist.sp"
        (data_dir.parent / files["netlist_file"]).write_text(netlist.read_text())
        try:
            files["schematic"] = f"sweep/{block}/{ident}.schematic.svg"
            export_schematic(str(netlist), str(data_dir.parent / files["schematic"]))
        except Exception:  # noqa: BLE001 - the netlist stays readable without its drawing
            del files["schematic"]
    waves = []
    for label, relative in record.get("waves", {}).items():
        path = ROOT / relative
        if path.exists():
            wave = wave_entry(path, read_measurement(path))
            if wave is not None:
                waves.append({**wave, "pdk": record["pdk"], "case": ident, "sweep": label})
    index = data_dir / block / ident / "traces.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(_json(trace_index(waves)), separators=(",", ":")))
    return files


def _current(block: str, pdk: str) -> set[str]:
    """The digests of ``block``'s instances in ``pdk`` as its design is now: its design space's and
    its named instances' (swept or not)."""
    from flow import pipeline

    named = pipeline.names(import_module(f"flow.{block}.sweep"))
    return set(design_space(block, pdk)) | {digest(build()) for build in named.values()}


def table(blocks: list[str], workers: int, run: Path | None = None) -> None:
    """The viewer's table of each block's newest run in each PDK (``run`` for the PDKs it ran in,
    where given), and one detail file per instance."""

    from flow import pipeline
    from flow.web.export import BLOCKS

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog_path = DATA_DIR / "catalog.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
    # a block whose sweep is gone leaves the catalog
    catalog = {block: entry for block, entry in catalog.items() if block in sweep_blocks() or block in blocks}
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        for block in blocks:
            # each PDK's newest run: a run of some PDKs alone keeps the others' rows from the run before
            runs = pdk_runs(block)
            if run is not None:
                runs.update({pdk.name: run for pdk in run.iterdir() if pdk.is_dir()})
            if not runs:
                raise FileNotFoundError(f"no sweep run of {block} in {RUNS_DIR / block}")
            paths = sorted(
                (path for pdk, run in runs.items() for path in (run / pdk).glob("*/instance.json")),
                key=lambda path: path.parts[-3:],  # by PDK, then digest
            )
            records = [json.loads(path.read_text()) for path in paths]
            # a block on the pipeline shows its design as it is: a run's instances since left out of
            # it stay on disk (and for the models' lookup), not in the table
            if find_spec(f"flow.{block}") and hasattr(import_module(f"flow.{block}.sweep"), "runs"):
                current = {pdk: _current(block, pdk) for pdk in runs}
                records = [entry for entry in records if entry["id"].split("__")[-1] in current[entry["pdk"]]]
            # the run, or each run with the PDKs it gives where they differ
            run_name = (
                max(runs.values()).name
                if len(set(runs.values())) == 1
                else ", ".join(
                    f"{run.name} ({', '.join(pdk for pdk, of in runs.items() if of == run)})"
                    for run in sorted(set(runs.values()), reverse=True)
                )
            )
            (DATA_DIR / block).mkdir(parents=True, exist_ok=True)
            rows, views = [], {}
            for record in records:
                ident = record["id"]
                rows.append(
                    {
                        "id": ident,
                        "pdk": record["pdk"],
                        "params": record["params"],
                        "metrics": record["metrics"],
                        "error": ((record["error"] or "").strip().splitlines() or [None])[-1],
                        "seconds": record.get("seconds"),
                    }
                )
                views[ident] = (record, pool.submit(instance_views, block, ident, record, DATA_DIR))
            for row in rows:
                record, future = views[row["id"]]
                try:
                    files = future.result()
                except Exception as error:  # noqa: BLE001 - a missing view is shown as missing
                    print(f"{block}/{row['id']}: {error!r}")
                    files = {}
                entry = record.get("layout")
                instance = {
                    **row,
                    "params": record["params"],
                    "details": record["details"],
                    "waves": record["waves"],
                    # an instance laid out by no one keeps its netlist's views (no gds: no layout)
                    "layout": {**(entry or {}), **files} if entry or files else None,
                    "error": record["error"],
                }
                path = DATA_DIR / block / f"{row['id']}.json"
                path.write_text(json.dumps(_json(instance), separators=(",", ":")))
            # the parameters that tell instances apart, then every metric: the design's size together
            # first (child cells, devices, device and layout area), the rest by name
            names = sorted({name for row in rows for name in row["params"]})
            varying = [name for name in names if len({json.dumps(row["params"].get(name)) for row in rows}) > 1]
            present = {name for row in rows for name in row["metrics"]}
            metrics = [name for name in dict.fromkeys([*pipeline.GEOMETRY, *sorted(present)]) if name in present]
            for row in rows:
                row["params"] = {name: row["params"].get(name) for name in varying}
            title = BLOCKS.get(block, block)
            data = {
                "block": block,
                "title": title,
                "run": run_name,
                "params": varying,
                "metrics": metrics,
                "rows": rows,
            }
            (DATA_DIR / f"{block}.json").write_text(json.dumps(_json(data), separators=(",", ":")))
            # the files of instances no longer in the run (an earlier run's, or under older ids)
            for stale in (DATA_DIR / block).iterdir():
                if stale.name.split(".", 1)[0] not in views:
                    shutil.rmtree(stale) if stale.is_dir() else stale.unlink()
            # its optimizations' tables (flow.opt.runner.table, ``searches``) kept
            catalog[block] = {**catalog.get(block, {}), "title": title, "run": run_name, "instances": len(rows)}
            laid_out = sum(1 for record, _future in views.values() if (record.get("layout") or {}).get("gds"))
            details = len({detail["name"] for record in records for detail in record["details"]})
            print(f"{block}: {len(rows)} instances, {len(metrics)} metrics, {details} details, {laid_out} layouts")
    catalog_path.write_text(json.dumps(dict(sorted(catalog.items())), indent=1) + "\n")
