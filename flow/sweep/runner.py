"""Run, lay out and tabulate the blocks' design-space sweeps (``python -m flow.sweep``).

``run``: every block's instances (PDK x topology x sizing) characterized, one process each, at
most ``--workers`` at once; each writes ``instance.json`` (its parameters, metrics, details,
waves, its run time or error) in ``build/sweep/<block>/<run>/<pdk>/<topology>/<sizing>/``.
``layout``: ALIGN places and routes each instance of the newest run whose block gives a layout
netlist, signoff checks it, and its area joins the record. ``table``: the newest run of each
block as the viewer's table (``build/web/data/sweep/<block>.json``: one row per instance, the
parameters that differ, then the metrics; each detail's axis limits over all instances) and one
file per instance (its details, waves, layout and schematic).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from importlib import import_module
from multiprocessing import get_context
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWEEP_DIR = ROOT / "build/sweep"
DATA_DIR = ROOT / "build/web/data/sweep"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")


def sweep_blocks() -> list[str]:
    """Every block with a ``sweep.py``, in name order."""
    return sorted(path.parent.name for path in (ROOT / "flow").glob("*/sweep.py"))


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


def instance_job(block: str, run_dir: Path, pdk: str, topology: str, sizing: str) -> dict:
    """Characterize one instance in this (fresh) process; its record, also as ``instance.json``."""

    import hdl21 as h

    from flow.sweep import flat_params, geometry

    sweep = import_module(f"flow.{block}.sweep")
    params = sweep.params(pdk, topology, sizing)
    record = {
        "block": block,
        "pdk": pdk,
        "topology": topology,
        "sizing": sizing,
        "params": flat_params(params),
        "metrics": {},
        "details": [],
        "waves": {},
        "error": None,
    }
    start = time.time()
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
        result = sweep.characterize(run_dir, pdk, params)
        module = sweep.GENERATOR(params)
        h.pdk.compile(module)
        record["metrics"] = {**geometry(module, pdk), **result.metrics}
        record["details"] = [dataclasses.asdict(detail) for detail in result.details]
        record["waves"] = result.waves
    except Exception:  # noqa: BLE001 - every instance reports its own failure
        record["error"] = traceback.format_exc(limit=6)[-4000:]
    record["seconds"] = round(time.time() - start, 1)
    (run_dir / "instance.json").write_text(json.dumps(_json(record), indent=1) + "\n")
    return record


def run(blocks: list[str], pdks: tuple[str, ...], workers: int, *, failed: bool = False) -> dict[str, Path]:
    """Characterize every instance of ``blocks`` in ``pdks``; each block's run directory.
    ``failed``: only the instances of each block's newest run that failed (or never ran), again,
    into that run."""

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    jobs, runs = [], {}
    for block in blocks:
        sweep = import_module(f"flow.{block}.sweep")
        runs[block] = newest_run(block) if failed else SWEEP_DIR / block / stamp
        for pdk in pdks:
            for topology in sweep.TOPOLOGIES:
                for sizing in sweep.SIZINGS:
                    if sweep.params(pdk, topology, sizing) is None:
                        continue
                    path = runs[block] / pdk / topology / sizing
                    record = path / "instance.json"
                    if failed and record.exists() and json.loads(record.read_text())["error"] is None:
                        continue
                    jobs.append((block, path, pdk, topology, sizing))
    print(f"{len(jobs)} instances of {', '.join(blocks)} on {workers} workers")
    failed = 0
    # a fresh process per instance: hdl21 compiles a generated module in place, for one PDK
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"), max_tasks_per_child=1) as pool:
        futures = {pool.submit(instance_job, *job): job for job in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            block, path, *_ = futures[future]
            try:
                record = future.result()
            except Exception as error:  # noqa: BLE001 - a worker that died
                record = {"error": repr(error), "seconds": math.nan}
            failed += record["error"] is not None
            status = "failed" if record["error"] else "ok"
            print(f"[{done}/{len(jobs)}] {path.relative_to(SWEEP_DIR)}: {status} in {record['seconds']} s", flush=True)
    print(f"{len(jobs) - failed} instances characterized, {failed} failed: {', '.join(map(str, runs.values()))}")
    return runs


def newest_run(block: str) -> Path:
    runs = sorted(path for path in (SWEEP_DIR / block).iterdir() if path.is_dir())
    if not runs:
        raise FileNotFoundError(f"no sweep run of {block} in {SWEEP_DIR / block}")
    return runs[-1]


def layout_job(block: str, instance_dir: Path, pdk: str) -> dict:
    """ALIGN's layout of one instance and its signoff, into ``instance_dir/layout``; the record's
    layout entry (also written into its ``instance.json``)."""

    from klayout import db

    from flow.layout.align.build import build as align_build
    from flow.layout.signoff import row_signoff

    record = json.loads((instance_dir / "instance.json").read_text())
    sweep = import_module(f"flow.{block}.sweep")
    params = sweep.params(pdk, record["topology"], record["sizing"])
    out = instance_dir / "layout"
    entry: dict = {"error": None}
    start = time.time()
    try:
        netlist = sweep.layout_netlist(out / "netlist", pdk, params)
        name = netlist.stem
        gds = align_build(pdk, None, netlist, out / "align", name=name)
        layout = db.Layout()
        layout.read(str(gds))
        box = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).dbbox()
        entry.update(
            gds=str(gds.relative_to(ROOT)), netlist=str(netlist.relative_to(ROOT)), w_um=box.width(), h_um=box.height()
        )
        check = row_signoff(pdk, gds, netlist, None, out / "signoff")
        entry.update(drc_violations=check.drc_violations, lvs_correct=check.lvs_correct)
    except Exception:  # noqa: BLE001 - every instance reports its own failure
        entry["error"] = traceback.format_exc(limit=6)[-4000:]
    entry["seconds"] = round(time.time() - start, 1)
    record["layout"] = entry
    if entry.get("w_um"):
        area = entry["w_um"] * entry["h_um"]
        record["metrics"]["layout_area_um2"] = area
        gate = record["metrics"].get("gate_area_um2")
        record["metrics"]["density"] = gate / area if gate else None
    (instance_dir / "instance.json").write_text(json.dumps(_json(record), indent=1) + "\n")
    return entry


def layout(blocks: list[str], workers: int) -> None:
    """Lay out every characterized instance of the newest runs of ``blocks``."""

    jobs = []
    for block in blocks:
        if not hasattr(import_module(f"flow.{block}.sweep"), "layout_netlist"):
            print(f"{block}: no layout netlist")
            continue
        for path in sorted(newest_run(block).glob("*/*/*/instance.json")):
            record = json.loads(path.read_text())
            if record["error"] is None:
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
            )
            print(f"[{done}/{len(jobs)}] {path.relative_to(SWEEP_DIR)}: {status} in {entry['seconds']} s", flush=True)


def instance_views(block: str, ident: str, record: dict) -> dict:
    """An instance's views for its page, under ``build/web/data/sweep/<block>/``: its layout
    flattened onto the PDK's generic layers (``flow.web.export``), its schematic and netlist, and
    the index of its waveforms (``<ident>/traces.json``, as the waveform panel reads one); the
    files written, by kind."""

    from flow.analysis.io import read_measurement
    from flow.web.export import export_layout, export_schematic, trace_index, wave_entry

    files: dict = {}
    entry = record.get("layout") or {}
    if entry.get("gds"):
        files["file"] = f"sweep/{block}/{ident}.layout.json"
        export_layout(str(ROOT / entry["gds"]), record["pdk"], str(DATA_DIR.parent / files["file"]))
    if entry.get("netlist"):
        files["netlist_file"] = f"sweep/{block}/{ident}.netlist.sp"
        (DATA_DIR.parent / files["netlist_file"]).write_text((ROOT / entry["netlist"]).read_text())
        try:
            files["schematic"] = f"sweep/{block}/{ident}.schematic.svg"
            export_schematic(str(ROOT / entry["netlist"]), str(DATA_DIR.parent / files["schematic"]))
        except Exception:  # noqa: BLE001 - the netlist stays readable without its drawing
            del files["schematic"]
    waves = []
    for label, relative in record.get("waves", {}).items():
        path = ROOT / relative
        if path.exists():
            wave = wave_entry(path, read_measurement(path))
            if wave is not None:
                waves.append({**wave, "pdk": record["pdk"], "case": ident, "sweep": label})
    index = DATA_DIR / block / ident / "traces.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(_json(trace_index(waves)), separators=(",", ":")))
    return files


def table(blocks: list[str], workers: int) -> None:
    """The viewer's table of each block's newest run, and one detail file per instance."""

    from flow.web.export import BLOCKS

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog_path = DATA_DIR / "catalog.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        for block in blocks:
            run_dir = newest_run(block)
            records = [json.loads(path.read_text()) for path in sorted(run_dir.glob("*/*/*/instance.json"))]
            rows, details, views = [], {}, {}
            for record in records:
                ident = f"{record['pdk']}__{record['topology']}__{record['sizing']}"
                rows.append(
                    {
                        "id": ident,
                        "pdk": record["pdk"],
                        "topology": record["topology"],
                        "sizing": record["sizing"],
                        "params": record["params"],
                        "metrics": record["metrics"],
                        "error": ((record["error"] or "").strip().splitlines() or [None])[-1],
                        "seconds": record.get("seconds"),
                    }
                )
                for detail in record["details"]:
                    limits = details.setdefault(
                        detail["name"],
                        {k: detail[k] for k in ("title", "x_label", "y_label", "x_log", "y_log")}
                        | {"x": [math.inf, -math.inf], "y": [math.inf, -math.inf]},
                    )
                    xs = [x for x in detail["x"] if x is not None and (x > 0 or not detail["x_log"])]
                    ys = [
                        y
                        for values in detail["series"].values()
                        for y in values
                        if y is not None and (y > 0 or not detail["y_log"])
                    ]
                    if xs:
                        limits["x"] = [min(limits["x"][0], *xs), max(limits["x"][1], *xs)]
                    if ys:
                        limits["y"] = [min(limits["y"][0], *ys), max(limits["y"][1], *ys)]
                views[ident] = (record, pool.submit(instance_views, block, ident, record))
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
            # the parameters that tell instances apart, then every metric
            names = sorted({name for row in rows for name in row["params"]})
            varying = [name for name in names if len({json.dumps(row["params"].get(name)) for row in rows}) > 1]
            metrics = sorted({name for row in rows for name in row["metrics"]})
            for row in rows:
                row["params"] = {name: row["params"].get(name) for name in varying}
            title = BLOCKS.get(block, block)
            data = {
                "block": block,
                "title": title,
                "run": run_dir.name,
                "params": varying,
                "metrics": metrics,
                "details": details,
                "rows": rows,
            }
            (DATA_DIR / f"{block}.json").write_text(json.dumps(_json(data), separators=(",", ":")))
            catalog[block] = {"title": title, "run": run_dir.name, "instances": len(rows)}
            laid_out = sum(1 for record, _future in views.values() if (record.get("layout") or {}).get("gds"))
            print(f"{block}: {len(rows)} instances, {len(metrics)} metrics, {len(details)} details, {laid_out} layouts")
    catalog_path.write_text(json.dumps(dict(sorted(catalog.items())), indent=1) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("run", "layout", "table"))
    parser.add_argument("--blocks", nargs="*", default=None, help="blocks (default: every block with a sweep.py)")
    parser.add_argument("--pdks", nargs="*", default=list(PDKS))
    parser.add_argument("--workers", type=int, default=56)
    parser.add_argument("--failed", action="store_true", help="run: only the newest run's failed instances, again")
    args = parser.parse_args()
    blocks = args.blocks or sweep_blocks()
    if args.step == "run":
        run(blocks, tuple(args.pdks), args.workers, failed=args.failed)
    elif args.step == "layout":
        layout(blocks, args.workers)
    else:
        table(blocks, min(args.workers, 16))


if __name__ == "__main__":
    main()
