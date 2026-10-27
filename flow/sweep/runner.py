"""Run, lay out and tabulate the blocks' design-space sweeps (``python -m flow sweep.<target>``).

An instance is its parameters: its id is ``<pdk>__<digest>``, the digest the first 12 hex digits of
the SHA-1 of its flat parameters (``digest``), as ``flow.sweep.lookup`` keys the models' cache.

``run``: every block's instances (each PDK's ``instances(pdk)``) characterized, one process each,
at most ``workers`` at once; each writes ``instance.json`` (its id, parameters, metrics, details,
waves, its run time or error) in ``build/sweep/<block>/<run>/<pdk>/<digest>/``. ``layout``: ALIGN
places and routes each instance of the newest run whose block gives a layout netlist or a
floorplan, signoff checks it, and its area joins the record. ``table``: each block's newest run in
each PDK (a run of some PDKs alone keeps the others' from the run before) as the viewer's table
(``build/web/data/sweep/<block>.json``: one row per instance, the parameters that differ, then the
metrics) and one file per instance (its details, waves, layout and schematic).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
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
SWEEP_DIR = ROOT / "build/sweep"
DATA_DIR = ROOT / "build/web/data/sweep"
FLOORPLANS = ROOT / "design/layout"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")


def sweep_blocks() -> list[str]:
    """Every block with a ``sweep.py``, in name order."""
    return sorted(path.parent.name for path in (ROOT / "flow").glob("*/sweep.py"))


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
    its families and named instances (``labelled_space``), another its sweep's ``instances``."""
    sweep = import_module(f"flow.{block}.sweep")
    if hasattr(sweep, "instances"):
        return {digest(params): params for params in sweep.instances(pdk)}
    return {ident: params for ident, (_label, params) in labelled_space(block, pdk).items()}


@cache
def labelled_space(block: str, pdk: str) -> dict:
    """A pipeline block's instances in ``pdk`` by digest, each with its label (its family and knobs,
    or its name; the first that reaches it): its sweep's families and swept named instances
    (``flow.pipeline.design``) that its ``params.valid`` admits in ``pdk``."""
    from flow import pipeline

    sweep = import_module(f"flow.{block}.sweep")
    valid = getattr(import_module(f"flow.{block}.params"), "valid", None)
    space: dict = {}
    for label, params in pipeline.design(sweep, pdk):
        if valid is None or valid(params, pdk):
            space.setdefault(digest(params), (label, params))
    return space


def select(block: str, pdk: str, names: list[str]) -> dict:
    """The instances ``names`` pick in ``pdk``, by digest, with their labels: each a named instance
    of the block's sweep (swept or not), the label of one of its instances (``family(knob=value,
    ...)``), or a digest. Those ``params.valid`` does not admit in ``pdk`` are left out."""
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
        valid = getattr(import_module(f"flow.{block}.params"), "valid", None)
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


def characterize(block: str, run_dir: Path, pdk: str, params) -> tuple[dict, list, dict]:
    """One instance's metrics (the geometry of its compiled circuit among them), plots and waves, in
    ``run_dir``. A block on the pipeline (docs/pipeline.md: its sweep gives ``runs`` and ``record``)
    is simulated run by run (``sim.simulate``), each read back (``flow.pipeline.read``) and its raw
    file removed, and recorded from the measurements (``sweep.record``), the runs it names
    (the record's ``waves``) kept as HDF5 for the viewer; another block characterizes itself
    (``sweep.characterize``)."""

    import hdl21 as h

    from flow import pipeline
    from flow.analysis.io import write_measurement
    from flow.sweep import geometry

    h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
    sweep = import_module(f"flow.{block}.sweep")
    if hasattr(sweep, "runs"):
        sim = import_module(f"flow.{block}.sim")
        measurements = {}
        for name, tb in sweep.runs(pdk, params).items():
            raw = sim.simulate(tb, run_dir / name)
            measurements[name] = pipeline.read(raw, tb)
            raw.unlink()
        result = sweep.record(measurements)
        result.waves = {
            label: str(write_measurement(run_dir / name / "result.h5", measurements[name]).relative_to(ROOT))
            for label, name in result.waves.items()
        }
        module = import_module(f"flow.{block}.subckt").netlist(params)
    else:
        result = sweep.characterize(run_dir, pdk, params)
        module = sweep.GENERATOR(params)
    h.pdk.compile(module)
    metrics = {**geometry(module, pdk), **result.metrics}
    return metrics, [dataclasses.asdict(detail) for detail in result.details], result.waves


def layout_hooks(block: str):
    """The module giving the block's layout netlists (``layout_netlist``, ``layout_floorplan``): its
    ``layout`` module on the pipeline, else its sweep."""

    sweep = import_module(f"flow.{block}.sweep")
    if hasattr(sweep, "runs"):
        return import_module(f"flow.{block}.layout")
    return sweep


def instance_batch(jobs: list[tuple]) -> list[dict]:
    """Several instances in one worker process (``instance_job`` each), their records in order."""
    return [instance_job(*job) for job in jobs]


def instance_job(block: str, run_dir: Path, pdk: str, params, label: str | None = None) -> dict:
    """Characterize one instance in this (fresh) process; its record, also as ``instance.json``."""

    record = {
        "block": block,
        "id": instance_id(pdk, params),
        "pdk": pdk,
        "label": label,
        "params": flat_params(params),
        "metrics": {},
        "details": [],
        "waves": {},
        "error": None,
    }
    start = time.time()
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        record["metrics"], record["details"], record["waves"] = characterize(block, run_dir, pdk, params)
    except Exception:  # noqa: BLE001 - every instance reports its own failure
        record["error"] = traceback.format_exc(limit=6)[-4000:]
    record["seconds"] = round(time.time() - start, 1)
    write_record(run_dir / "instance.json", record)
    return record


def run(
    blocks: list[str],
    pdks: tuple[str, ...],
    workers: int,
    *,
    failed: bool = False,
    names: list[str] | None = None,
) -> dict[str, Path]:
    """Characterize every instance of ``blocks`` in ``pdks``, or those ``names`` pick (``select``);
    each block's run directory. ``failed``: only the instances of each block's newest run that
    failed (or never ran), again, into that run."""

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    ranked, runs = [], {}
    for block in blocks:
        rank = getattr(import_module(f"flow.{block}.sweep"), "cost", None)
        runs[block] = newest_run(block) if failed else SWEEP_DIR / block / stamp
        for pdk in pdks:
            if names:
                space = select(block, pdk, names)
            elif hasattr(import_module(f"flow.{block}.sweep"), "instances"):
                space = {ident: (None, params) for ident, params in design_space(block, pdk).items()}
            else:
                space = labelled_space(block, pdk)
            for ident, (label, params) in space.items():
                path = runs[block] / pdk / ident
                record = path / "instance.json"
                if failed and record.exists() and json.loads(record.read_text())["error"] is None:
                    continue
                ranked.append((rank(pdk, params) if rank else 0.0, (block, path, pdk, params, label)))
    # the longest first where a block ranks its instances (``cost``), so the pool does not end on
    # one long instance alone
    jobs = [job for _cost, job in sorted(ranked, key=lambda item: item[0], reverse=True)]
    print(f"{len(jobs)} instances of {', '.join(blocks)} on {workers} workers")
    failed = 0
    # one BLAS thread a worker (the spawned workers inherit it): numpy's pool of a thread a core in
    # every worker oversubscribes the machine many times over
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")
    # a fresh process per task: hdl21 compiles a generated module in place, for one PDK. A block that
    # compiles nothing (its sweep's ``tasks_per_worker``: the ADC's behavioral converters) runs that
    # many instances as one task, which pays its imports (seconds) once, not per instance. (Not by
    # the pool's max_tasks_per_child: once every worker has run its share and exited, the pool starts
    # no new ones and waits forever.)
    tasks = min((getattr(import_module(f"flow.{block}.sweep"), "tasks_per_worker", 1) for block in blocks), default=1)
    batches = [jobs[start : start + tasks] for start in range(0, len(jobs), tasks)]
    done = 0
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1) as pool:
        futures = {pool.submit(instance_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                records = future.result()
            except Exception as error:  # noqa: BLE001 - a worker that died
                records = [{"error": repr(error), "seconds": math.nan}] * len(batch)
            for (_block, path, *_), record in zip(batch, records, strict=True):
                done += 1
                failed += record["error"] is not None
                status = "failed" if record["error"] else "ok"
                print(
                    f"[{done}/{len(jobs)}] {path.relative_to(SWEEP_DIR)}: {status} in {record['seconds']} s", flush=True
                )
    print(f"{len(jobs) - failed} instances characterized, {failed} failed: {', '.join(map(str, runs.values()))}")
    return runs


def newest_run(block: str, pdk: str | None = None) -> Path:
    """The block's newest run; with ``pdk``, the newest that ran in that PDK (a run of some PDKs
    alone leaves each other PDK's newest records in the run before)."""
    runs = sorted(
        path for path in (SWEEP_DIR / block).iterdir() if path.is_dir() and (pdk is None or (path / pdk).is_dir())
    )
    if not runs:
        raise FileNotFoundError(f"no sweep run of {block}{f' in {pdk}' if pdk else ''} in {SWEEP_DIR / block}")
    return runs[-1]


def pdk_runs(block: str) -> dict[str, Path]:
    """Each PDK's newest run of the block (``newest_run``), the PDKs in name order."""
    runs = {}
    for run in sorted((path for path in (SWEEP_DIR / block).iterdir() if path.is_dir()), reverse=True):
        for pdk in run.iterdir():
            if pdk.is_dir():
                runs.setdefault(pdk.name, run)
    return dict(sorted(runs.items()))


def hand_floorplan(block: str, params, cases: dict | None = None) -> Path | None:
    """The hand-written floorplan an instance is placed by: that of the first of the block's named
    cases (``cases``, else its subckt's ``CASES``) whose structure is the instance's (the values of
    the parameters its sweep's ``STRUCTURE`` names: those that make its devices and their wiring,
    not their sizes) and that has one, ``design/layout/<block>_<case>.json``; None where the block
    names no structure or no such case has a floorplan."""

    structure = getattr(import_module(f"flow.{block}.sweep"), "STRUCTURE", None)
    if structure is None:
        return None
    if cases is None:
        cases = getattr(import_module(f"flow.{block}.subckt"), "CASES", {})
    for name, case in cases.items():
        floorplan = FLOORPLANS / f"{block}_{name}.json"
        if all(getattr(case, field) == getattr(params, field) for field in structure) and floorplan.exists():
            return floorplan
    return None


def case_floorplan(block: str, out_dir: Path, pdk: str, params) -> tuple[Path, Path] | None:
    """The instance's hand-written floorplan (``hand_floorplan``) with the netlist its layout
    runner places by it (``write_netlist`` of the block's subckt, at the instance's sizes); None
    without one. A sweep module may give its own (``layout_floorplan``)."""

    hooks = layout_hooks(block)
    if hasattr(hooks, "layout_floorplan"):
        return hooks.layout_floorplan(out_dir, pdk, params)
    floorplan = hand_floorplan(block, params)
    write_netlist = getattr(import_module(f"flow.{block}.subckt"), "write_netlist", None)
    if floorplan is None or write_netlist is None:
        return None
    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    return write_netlist(params, out_dir / f"{floorplan.stem}.sp", logic), floorplan


def layout_job(block: str, instance_dir: Path, pdk: str) -> dict:
    """ALIGN's layout of one instance and its signoff, into ``instance_dir/layout``; the record's
    layout entry (also written into its ``instance.json``). ALIGN places by the instance's
    hand-written floorplan where it has one (a minute or two, the same rows the floorplan's other
    tools draw); without one, or where that fails, ALIGN derives its constraints and places and
    routes on its own (ten minutes or more, and its router fails on some IHP130 designs)."""

    import os

    from klayout import db

    from flow.layout.align.build import build as align_build
    from flow.layout.signoff import row_signoff

    # an attempt that has not placed and routed in half an hour fails (ALIGN's placer can search
    # for hours on the larger sizings); the next attempt, if any, follows
    os.environ.setdefault("ALIGN_TIMEOUT", "1800")
    record = json.loads((instance_dir / "instance.json").read_text())
    hooks = layout_hooks(block)
    params = instance_params(block, pdk, instance_dir.name)
    out = instance_dir / "layout"
    entry: dict = {"error": None}
    start = time.time()
    attempts = []
    try:
        planned = case_floorplan(block, out / "netlist", pdk, params)
        if planned is not None:
            attempts.append(planned)
    except Exception:  # noqa: BLE001 - ALIGN on its own instead
        entry["floorplan_error"] = traceback.format_exc(limit=4)[-2000:]
    if hasattr(hooks, "layout_netlist"):
        attempts.append((None, None))
    results = []  # each attempt's entry; the first clean one is kept, else the first laid out
    for netlist, floorplan in attempts:
        result: dict = {"error": None}
        try:
            if netlist is None:
                netlist = hooks.layout_netlist(out / "netlist", pdk, params)
            work = out / ("align_floorplan" if floorplan else "align")
            gds = align_build(pdk, floorplan, netlist, work, name=netlist.stem)
            layout = db.Layout()
            layout.read(str(gds))
            box = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).dbbox()
            result.update(
                floorplan=str(floorplan.relative_to(ROOT)) if floorplan else None,
                gds=str(gds.relative_to(ROOT)),
                netlist=str(netlist.relative_to(ROOT)),
                w_um=box.width(),
                h_um=box.height(),
            )
            check = row_signoff(pdk, gds, netlist, floorplan, work / "signoff")
            result.update(drc_violations=check.drc_violations, lvs_correct=check.lvs_correct)
        except Exception:  # noqa: BLE001 - every instance reports its own failure
            result["error"] = traceback.format_exc(limit=6)[-4000:]
        results.append(result)
        if result["error"] is None and result["drc_violations"] == 0 and result["lvs_correct"]:
            break
    clean = [r for r in results if r["error"] is None and r["drc_violations"] == 0 and r["lvs_correct"]]
    laid_out = [r for r in results if r["error"] is None]
    if results:
        entry.update((clean or laid_out or results)[0])
        entry["attempts"] = len(results)
    if not attempts:
        return {"error": "no floorplan and no layout netlist", "seconds": 0.0}
    entry["seconds"] = round(time.time() - start, 1)
    record["layout"] = entry
    if entry.get("w_um"):
        area = entry["w_um"] * entry["h_um"]
        record["metrics"]["layout_area_um2"] = area
        gate = record["metrics"].get("device_area_um2")
        record["metrics"]["density"] = gate / area if gate else None
    write_record(instance_dir / "instance.json", record)
    return entry


def layout(blocks: list[str], workers: int, *, pdks: tuple[str, ...] = PDKS) -> None:
    """Lay out every characterized instance of the newest runs of ``blocks`` in ``pdks`` not yet laid
    out DRC clean and LVS correct."""

    jobs = []
    for block in blocks:
        hooks = layout_hooks(block)
        own = hasattr(hooks, "layout_netlist") or hasattr(hooks, "layout_floorplan")
        for path in sorted(newest_run(block).glob("*/*/instance.json")):
            record = json.loads(path.read_text())
            if record["pdk"] not in pdks:
                continue
            params = design_space(block, record["pdk"]).get(path.parent.name)
            if params is None:
                print(f"{path.parent.relative_to(SWEEP_DIR)}: not in the design space any more, not laid out")
                continue
            # a block drawn otherwise (the capacitor array) or of standard cells alone has nothing to place
            if not own and hand_floorplan(block, params) is None:
                continue
            entry = record.get("layout") or {}
            done = (
                entry.get("gds")
                and not entry.get("error")
                and entry.get("drc_violations") == 0
                and entry.get("lvs_correct")
            )
            if record["error"] is None and not done:
                jobs.append((block, path.parent, record["pdk"]))
    print(f"{len(jobs)} layouts on {workers} workers")
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1) as pool:
        futures = {pool.submit(layout_job, *job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            _block, path, _pdk = futures[future]
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
            print(f"[{done}/{len(jobs)}] {path.relative_to(SWEEP_DIR)}: {status} in {entry['seconds']} s", flush=True)


def instance_views(block: str, ident: str, record: dict, data_dir: Path) -> dict:
    """An instance's views for its page, under ``data_dir/<block>/`` (``build/web/data/sweep``): its layout
    flattened onto the PDK's generic layers (``flow.web.export``), its schematic and netlist, and
    the index of its waveforms (``<ident>/traces.json``, as the waveform panel reads one); the
    files written, by kind."""

    from flow.analysis.io import read_measurement
    from flow.web.export import export_layout, export_schematic, trace_index, wave_entry

    files: dict = {}
    entry = record.get("layout") or {}
    if entry.get("gds"):
        files["file"] = f"sweep/{block}/{ident}.layout.json"
        export_layout(str(ROOT / entry["gds"]), record["pdk"], str(data_dir.parent / files["file"]))
    if entry.get("netlist"):
        files["netlist_file"] = f"sweep/{block}/{ident}.netlist.sp"
        (data_dir.parent / files["netlist_file"]).write_text((ROOT / entry["netlist"]).read_text())
        try:
            files["schematic"] = f"sweep/{block}/{ident}.schematic.svg"
            export_schematic(str(ROOT / entry["netlist"]), str(data_dir.parent / files["schematic"]))
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


def table(blocks: list[str], workers: int) -> None:
    """The viewer's table of each block's newest run, and one detail file per instance."""

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
            if not runs:
                raise FileNotFoundError(f"no sweep run of {block} in {SWEEP_DIR / block}")
            paths = sorted(
                (path for pdk, run in runs.items() for path in (run / pdk).glob("*/instance.json")),
                key=lambda path: path.parts[-3:],  # by PDK, then digest
            )
            # a block on the pipeline shows its design space as it is: a run's instances since left
            # out of it stay on disk (and for the models' lookup), not in the table
            if find_spec(f"flow.{block}") and hasattr(import_module(f"flow.{block}.sweep"), "runs"):
                paths = [path for path in paths if path.parent.name in design_space(block, path.parts[-3])]
            records = [json.loads(path.read_text()) for path in paths]
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
                    "layout": {**entry, **files} if entry else None,
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
