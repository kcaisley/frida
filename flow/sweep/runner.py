"""The bodies of the CLI's steps over a block's design space (``python -m flow``, ``flow.__main__``).

An instance is its parameters: its id is ``<pdk>__<digest>``, the digest the first 12 hex digits of
the SHA-1 of its flat parameters (``digest``), as ``flow.sweep.lookup`` keys the models' cache. A
run (``new_run``) is ``build/<block>/<run>/``, each instance in ``<pdk>/<name>/`` there (a named
instance by its name, a grid's by its digest), a folder a step.

The characterization's steps: ``write_netlist`` (the circuit as simulated and its size, into
``netlist/``), ``simulate`` (each testbench run of ``testbenches_of``, or ``circuit_testbenches``, simulated and
its measurement kept as HDF5, into ``presim/<run>/``) and ``results`` (``search.record`` of the kept
measurements: the instance's ``instance.json``, its id, parameters, level, metrics, details and
waves); the postsim step's ``simulate`` and ``results`` again, into ``postsim/``, each testbench's DUT
a flat copy of it holding its extraction's capacitors (``_back_annotated``). ``table``: the viewer's
tables of a block, each of its runs' own (``export_run``: ``build/web/data/sweep/<block>/runs/<run>/
<stamp>.json``, one row per instance, the parameters that differ, then the metrics, and one file per
instance: its details, waves, layout, schematic and steps).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager, nullcontext
from datetime import datetime
from functools import cache
from importlib import import_module
from importlib.util import find_spec
from multiprocessing import get_context
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flow.sweep import flat_params

if TYPE_CHECKING:
    from flow.layout.annotate import Annotation

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "build"  # a block's runs: build/<block>/<run>/
RUN_STAMP = re.compile(r"\d{8}_\d{6}")  # a run's name (new_run, run)
DATA_DIR = ROOT / "build/web/data/sweep"
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65", "sky130", "gf180")


def sweep_blocks() -> list[str]:
    """Every block with a ``runs.py`` (a block on the pipeline) or a ``sweep.py`` (one not yet),
    in name order: a part of a block by its dotted name (``<block>.<part>``, ``flow/<block>/<part>``)."""
    flow = ROOT / "flow"
    found = {
        ".".join(path.parent.relative_to(flow).parts)
        for name in ("runs.py", "sweep.py")
        for path in (*flow.glob(f"*/{name}"), *flow.glob(f"*/*/{name}"))
    }
    return sorted(found)


def runs_module(block: str):
    """A block's runs and testbenches: its ``runs.py``; a block not on the pipeline, its ``sweep.py``."""
    return import_module(f"flow.{block}.runs" if find_spec(f"flow.{block}.runs") else f"flow.{block}.sweep")


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
    sweep = runs_module(block)
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
    """A block's designs in ``pdk`` by digest, each with its label (its grid and the values that
    vary there, or a single's name; the first that reaches it): every grid's and single's of its
    runs (``flow.pipeline.design``) that its ``params.valid`` admits in ``pdk``."""
    from flow import pipeline

    valid = _valid(block)
    space: dict = {}
    for label, params in pipeline.design(runs_module(block), pdk):
        if valid is None or valid(params, pdk):
            space.setdefault(digest(params), (label, params))
    return space


def run_instances(block: str, run: str, pdk: str) -> dict:
    """The designs the block's run ``run`` names in ``pdk`` (a single's one, a grid's every point), by
    digest, with their labels; those its ``params.valid`` does not admit in ``pdk`` left out."""
    from flow import pipeline

    found = pipeline.runs(runs_module(block))[run]
    valid = _valid(block)
    picked: dict = {}
    for label, params in found.instances(pdk):
        if valid is None or valid(params, pdk):
            picked.setdefault(digest(params), (label, params))
    return picked


def instance_params(block: str, pdk: str, ident: str):
    """The parameters of the instance of ``block`` in ``pdk`` with this digest."""
    try:
        return design_space(block, pdk)[ident]
    except KeyError:
        raise LookupError(
            f"no instance of the {block} design space in {pdk} has the digest {ident}: its parameters "
            f"are not among flow.{block}.runs's designs in {pdk!r} (changed since it ran?)"
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


def write_results(path: Path, record: dict) -> None:
    """``instance.json``, replaced whole: the layout step rewrites records others may be reading."""
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(_json(record), indent=1) + "\n")
    temporary.replace(path)


def leveled(block: str) -> bool:
    """Whether the block's ``sweep.runs`` takes the evaluation level (``flow.pipeline.Level``); a
    block whose runs take none characterizes alike at every level."""
    from inspect import signature

    runs = getattr(runs_module(block), "testbenches", None)
    return runs is not None and "level" in signature(runs).parameters


def testbenches_of(block: str, pdk: str, params, level=None) -> dict:
    """The testbench runs that characterize ``params`` in ``pdk`` at ``level`` (None: ``FULL``), by
    name (``sweep.runs``; a block whose runs take no level, its only runs)."""
    from flow import pipeline

    module = runs_module(block)
    return (
        module.testbenches(pdk, params, level or pipeline.Level.FULL)
        if leveled(block)
        else module.testbenches(pdk, params)
    )


def circuit_testbenches(block: str, pdk: str, params) -> dict:
    """The circuit simulator's runs of a block whose full characterization is behavioral: its runs at
    ``Level.CIRCUIT`` that are not its full ones (none where both are alike, the comparator's)."""
    from flow import pipeline

    if not leveled(block):
        return {}
    full = testbenches_of(block, pdk, params)
    return {
        name: tb for name, tb in testbenches_of(block, pdk, params, pipeline.Level.CIRCUIT).items() if name not in full
    }


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


def simulate(block: str, pdk: str, runs: dict, folder: Path, annotation: Annotation | None = None) -> dict[str, Path]:
    """Each of ``runs`` simulated in ``folder/<run>/`` (``sim.simulate``), read back (its
    ``sim.read`` where it has one, else ``flow.pipeline.read``) and kept as a measurement
    (``result.h5``, ``flow.analysis.io.write_measurement``), its raw file removed; a run whose
    measurement is kept already is not simulated again. The simulator's log (Spectre's
    ``spectre.log``: each ``*.log`` the run wrote) also goes, a line a record, to the flow's log
    under its name (``flow.logs.relay``), whether the run ended or failed. With ``annotation`` (an extraction on the
    schematic's nets, ``flow.layout.annotate.Annotation``), each run's DUT carries its capacitors
    (``_back_annotated``). Each run's measurement file, by name."""
    import hdl21 as h

    from flow import pipeline
    from flow.analysis.io import write_measurement
    from flow.logs import relay

    h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
    sim = import_module(f"flow.{block}.sim")
    read = getattr(sim, "read", pipeline.read)
    kept = {}
    for name, tb in runs.items():
        path = folder / name / "result.h5"
        if not path.exists():
            try:
                with _back_annotated(block, tb, annotation, folder / name) if annotation else nullcontext():
                    raw = sim.simulate(tb, folder / name)
            finally:
                for log in sorted((folder / name).glob("*.log")):
                    relay(log, log.stem)
            write_measurement(path, read(raw, tb))
            raw.unlink()
        kept[name] = path
    return kept


@contextmanager
def _back_annotated(block: str, tb, annotation: Annotation, run_dir: Path):
    """While a run simulates, each testbench it compiles to the PDK (``hdl21.pdk.compile``, which
    every block's ``sim.simulate`` calls on its testbench before Spectre runs it) first has its DUT
    back-annotated: each of its instances of the block's module of ``tb.params``
    (``subckt.netlist``; the converter's two sides alike) takes a flat copy of it
    (``_flattened``) that holds the extraction's capacitors (``_add_capacitors``). What it added is
    ``run_dir/annotation.json``; a testbench without the DUT (the capacitive DAC's plates alone)
    simulates as it is and says so there."""
    import hdl21 as h

    dut = import_module(f"flow.{block}.subckt").netlist(tb.params).name
    compile_ = h.pdk.compile

    def annotated(src, *args, **kwargs):
        duts = [inst for inst in getattr(src, "instances", {}).values() if getattr(inst.of, "name", None) == dut]
        entry: dict[str, Any] = {"dut": dut, "instances": [inst.name for inst in duts]}
        if duts:
            flat = _flattened(duts[0].of)
            entry.update(_add_capacitors(flat, annotation))
            off = annotation.unmapped_f + sum(entry["unsimulated"].values())
            if off > annotation.limit * annotation.total_f:
                nets = ", ".join(f"{net} {c * 1e15:.3g} fF" for net, c in entry["unsimulated"].items())
                raise ValueError(
                    f"{off * 1e15:.4g} fF of the extraction's {annotation.total_f * 1e15:.4g} fF (over "
                    f"{annotation.limit:.0%}) is on no net of {dut}, unmapped or unsimulated: {nets}"
                )
            for inst in duts:
                inst.of = flat
        if duts or not (run_dir / "annotation.json").exists():  # a run's other compiles keep its DUT's
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "annotation.json").write_text(json.dumps(_json(entry), indent=1) + "\n")
        return compile_(src, *args, **kwargs)

    h.pdk.compile = annotated  # ty: ignore[invalid-assignment]
    try:
        yield
    finally:
        h.pdk.compile = compile_


def _flattened(module):
    """A flat copy of ``module`` (hdl21's ``flatten``), a net or device inside a cell named by its
    path joined by ``_`` (Spectre's names take no ``:``), its ports and its own nets as they are:
    a module of its own, to which the extraction's capacitors are added."""
    import hdl21 as h
    from hdl21.flatten import walk

    flat = h.Module(name=f"{module.name}_pex")
    for port in module.ports.values():
        flat.add(h.Port(name=port.name, width=port.width, usage=port.usage, direction=port.direction))

    def net(connection):
        if isinstance(connection, h.Slice):
            return net(connection.parent)[connection.index]
        if isinstance(connection, h.Concat):
            return h.Concat(*(net(part) for part in connection.parts))
        name = connection.name.replace(":", "_")
        found = flat.ports.get(name, flat.signals.get(name))
        return found if found is not None else flat.add(h.Signal(width=connection.width), name=name)  # ty: ignore[unknown-argument]

    for signal in h.elaborate(module).signals.values():
        net(signal)
    for node in walk(module, parents=[]):
        name = node.make_name().replace(":", "_")
        flat.add(node.inst.of(**{port: net(connection) for port, connection in node.conns.items()}), name=name)
    return flat


def _add_capacitors(module, annotation: Annotation) -> dict[str, Any]:
    """The extraction's capacitors added to the DUT's flat ``module``, each between its nets (by
    name: a bus's bit as ``<bus>_<bit>``, as netlists write it; a net inside a cell by its path
    joined by ``_``, KLayout's ``.``; ground, ``0``, the module's ground port), less the module's
    own capacitors between them (hdl21's ideal ones: a drawn capacitor's view, which the
    extraction measured as metal too); what it added and what it took off."""
    import hdl21 as h
    from hdl21.primitives import C, IdealCapacitor

    nets: dict[str, Any] = {}
    for signal in (*module.ports.values(), *module.signals.values()):
        nets[signal.name.lower()] = signal
        if signal.width > 1:
            nets.update({f"{signal.name}_{bit}".lower(): signal[bit] for bit in range(signal.width)})
    ground = next(port.name.lower() for port in module.ports.values() if port.usage == h.Usage.GROUND)

    def named(net: str) -> str:
        return ground if net == "0" else net.replace(".", "_")

    summed: dict[tuple[str, ...], float] = {}  # a net's to ground (``0``) and to the ground port are one
    for a, b, c in annotation.capacitors:
        ends = tuple(sorted((named(a), named(b))))
        summed[ends] = summed.get(ends, 0.0) + c
    drawn: dict[tuple[str, ...], float] = {}
    for instance in module.instances.values():
        if getattr(instance.of, "prim", None) is not IdealCapacitor:
            continue
        try:
            value = float(instance.of.params.c)
        except (TypeError, ValueError):  # a Monte Carlo's expression
            continue
        ends = tuple(sorted(_net(instance.conns[terminal]) for terminal in ("p", "n")))
        drawn[ends] = drawn.get(ends, 0.0) + value
    added = taken = 0.0
    unsimulated: dict[str, float] = {}  # nets LVS compared that the simulated module lacks
    for index, (ends, c) in enumerate(sorted(summed.items())):
        if ends[0] == ends[1]:
            continue
        if absent := [net for net in ends if net not in nets]:
            for net in absent:
                unsimulated[net] = unsimulated.get(net, 0.0) + c
            continue
        own = min(c, drawn.get(ends, 0.0))
        if c > own:
            module.add(C(c=c - own)(p=nets[ends[0]], n=nets[ends[1]]), name=f"cpex_{index}")
            added += c - own
        taken += own
    return {"added_f": added, "drawn_f": taken, "unsimulated": unsimulated}


def _net(connection) -> str:
    """A flat module's connection by its net's name, lower case: a bus's bit as ``<bus>_<bit>``."""
    if hasattr(connection, "parent"):
        return f"{connection.parent.name}_{connection.index}".lower()
    return connection.name.lower()


def _base_results(block: str, pdk: str, params, label: str | None, name: str | None) -> dict:
    """A record's identity: its block, id, name in its run, PDK, label and parameters (none where
    ``params`` is: an instance known by its folder alone), nothing measured."""
    return {
        "block": block,
        "id": instance_id(pdk, params) if params is not None else f"{pdk}__{name}",
        "name": name,
        "pdk": pdk,
        "label": label,
        "level": None,
        "params": flat_params(params) if params is not None else {},
        "metrics": {},
        "details": [],
        "waves": {},
        "error": None,
    }


def results(
    block: str,
    pdk: str,
    params,
    out: Path | None,
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
    size (``sizes``: ``write_netlist``'s), written as ``out/instance.json`` (not written where ``out``
    is None: the CLI's results step writes the record it composes): its metrics (the size's
    and ``sweep.results``'s), details, the waves of the runs the record names (their measurement
    files from the repository's root), the level its runs ran at (None for a block whose runs take
    no level), its netlist and its seconds (``seconds``, those of the steps before it, and its own)."""
    import hdl21 as h

    from flow import pipeline
    from flow.analysis.io import read_measurement

    start = time.time()
    h.pdk.set_default(import_module(f"pdk.{pdk}").pdk_logic)
    result = runs_module(block).results({run: read_measurement(path) for run, path in files.items()})
    entry = _base_results(block, pdk, params, label, name)
    entry.update(
        level=(level or pipeline.Level.FULL).value if leveled(block) else None,
        metrics={**sizes, **result.metrics},
        details=[detail.to_json() for detail in result.details],
        waves={wave: _shown(files[run]) for wave, run in result.waves.items()},
        netlist=_shown(netlist) if netlist else None,
        seconds=round(seconds + time.time() - start, 1),
    )
    if out is not None:
        write_results(out / "instance.json", entry)
    return entry


def betters(block: str) -> dict:
    """Which way is better for each metric a block's record carries (``flow.pipeline.Better`` by
    name): its own (its ``types.Metrics``) and the runner's (``flow.pipeline.GEOMETRY``)."""
    from flow import pipeline

    return {**pipeline.betters(import_module(f"flow.{block}.types").Metrics), **pipeline.GEOMETRY}


def failed_results(block: str, pdk: str, params, out: Path, error: str, *, label=None, name=None) -> dict:
    """An instance's record of a characterization that failed (``error``, its step's traceback),
    written as ``out/instance.json``, so the viewer's table shows the failure."""
    entry = {**_base_results(block, pdk, params, label, name), "error": error}
    out.mkdir(parents=True, exist_ok=True)
    write_results(out / "instance.json", entry)
    return entry


def characterize(block: str, run_dir: Path, pdk: str, params) -> dict:
    """One instance characterized in ``run_dir`` as the CLI's netlist, sim and record steps do it
    (``write_netlist``, ``simulate``, ``results``), without their bookkeeping: the models' on-demand
    characterization (``flow.sweep.lookup``). Its record; a failure recorded, not raised."""
    start = time.time()
    try:
        sizes = write_netlist(block, pdk, params, run_dir / "netlist")
        files = simulate(block, pdk, testbenches_of(block, pdk, params), run_dir / "presim")
        return results(
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
        return failed_results(block, pdk, params, run_dir, traceback.format_exc(limit=6)[-4000:])


def run_time(run: Path) -> str:
    """When a run was made, as a stamp that sorts in time (``YYYYmmdd_HHMMSS``, then its microseconds
    where it has them): its ``run.json``'s (``new_run``), or its name where it is a stamp (a run from
    before runs had names)."""
    marker = run / "run.json"
    if marker.exists():
        return json.loads(marker.read_text())["created"]
    return run.name


def new_run(block: str, name: str | None = None, run_dir: Path | None = None) -> Path:
    """A run of ``block``: ``run_dir`` (a run's: ``build/<block>/<run>/<stamp>``), or
    ``build/<block>/<name>`` (``name``: now's stamp where None), made with its ``run.json`` (when it
    was made) where it is new; an existing one as it is."""
    now = datetime.now().astimezone()
    run = run_dir if run_dir is not None else RUNS_DIR / block / (name or now.strftime("%Y%m%d_%H%M%S"))
    if not (run / "run.json").exists():
        run.mkdir(parents=True, exist_ok=True)
        created = now.strftime("%Y%m%d_%H%M%S.%f")
        (run / "run.json").write_text(json.dumps({"block": block, "created": created}) + "\n")
    return run


def _runs(block: str) -> list[Path]:
    """The block's runs: each run's dated folders (``build/<block>/<run>/<stamp>/``, ``new_run``:
    a ``run.json``), and the directories in ``build/<block>/`` made as runs before runs.py named
    them, or named by their stamp, not its other outputs there; a block not yet characterized, its
    layout runs (``build/<block>/layout/``), whose instances carry their layouts alone."""

    def run(path: Path) -> bool:
        return path.is_dir() and ((path / "run.json").exists() or bool(RUN_STAMP.fullmatch(path.name)))

    def made(folder: Path) -> list[Path]:
        if not folder.is_dir():
            return []
        found = []
        for path in folder.iterdir():
            if run(path):
                found.append(path)
            elif path.is_dir():  # a run's folder: its dated runs
                found += [dated for dated in path.iterdir() if (dated / "run.json").exists()]
        return found

    return made(RUNS_DIR / block) or made(RUNS_DIR / block / "layout")


def run_label(block: str, run: Path) -> str:
    """A run as the viewer and the command line name it: ``<run>/<stamp>``, or a run's own name
    from before runs.py named them."""
    return run.relative_to(RUNS_DIR / block).as_posix() if run.is_relative_to(RUNS_DIR / block) else run.name


def newest_run(block: str, pdk: str | None = None) -> Path:
    """The block's newest run (by ``run_time``); with ``pdk``, the newest that ran in that PDK (a
    run of some PDKs alone leaves each other PDK's newest records in the run before)."""
    runs = sorted((path for path in _runs(block) if pdk is None or (path / pdk).is_dir()), key=run_time)
    if not runs:
        raise FileNotFoundError(f"no run of {block}{f' in {pdk}' if pdk else ''} in {RUNS_DIR / block}")
    return runs[-1]


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


def _block_netlist(block: str, ident: str, record: dict, out: Path) -> Path | None:
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
        return block_netlist(block, params, record["pdk"], out / ident / f"{block}.cdl")
    except Exception:  # noqa: BLE001 - the page shows no netlist rather than no page
        return None


def instance_views(
    block: str, ident: str, record: dict, data_dir: Path, *, table: str | None = None, folder: Path | None = None
) -> dict:
    """An instance's views for its page, under ``data_dir/<table>/`` (``build/web/data/sweep``; ``table``
    the block's by default, a run's ``run_file``): its layout flattened onto the PDK's generic layers
    (``flow.web.export``), its schematic and netlist (its layout's, else its block's:
    ``_block_netlist``), and the index of its waveforms (``<ident>/traces.json``, as the waveform panel
    reads one); where its record's are its postsim step's and ``folder`` (its directory in a run) is
    given, the index of their pre-layout twins too (``<ident>/traces.sim.json``, ``traces_sim``). The
    files written, by kind."""

    from flow.analysis.io import read_measurement
    from flow.web.export import export_layout, export_schematic, trace_index, wave_entry, wave_kinds

    table = table or block
    files: dict = {}
    entry = record.get("layout") or {}
    if entry.get("gds"):
        files["file"] = f"sweep/{table}/{ident}.layout.json"
        export_layout(str(ROOT / entry["gds"]), record["pdk"], str(data_dir.parent / files["file"]))
    netlist = (
        ROOT / entry["netlist"] if entry.get("netlist") else _block_netlist(block, ident, record, data_dir / table)
    )
    if netlist is None and folder is not None:  # a failed record's: the netlist its netlist step wrote
        netlist = next(iter(sorted((folder / "netlist").glob("*.cdl"))), None)
    if netlist is not None:
        files["netlist_file"] = f"sweep/{table}/{ident}.netlist.sp"
        (data_dir.parent / files["netlist_file"]).write_text(netlist.read_text())
        try:
            files["schematic"] = f"sweep/{table}/{ident}.schematic.svg"
            export_schematic(str(netlist), str(data_dir.parent / files["schematic"]))
        except Exception:  # noqa: BLE001 - the netlist stays readable without its drawing
            del files["schematic"]

    def index(waves: dict[str, str], name: str) -> None:
        found = []
        for label, relative in waves.items():
            path = ROOT / relative
            if path.exists():
                wave = wave_entry(path, read_measurement(path))
                if wave is not None:
                    found.append({**wave, "pdk": record["pdk"], "case": ident, "sweep": label})
        path = data_dir / table / ident / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_json(trace_index(found)), separators=(",", ":")))

    waves = record.get("waves", {})
    index(waves, "traces.json")
    kinds = wave_kinds(waves)
    if folder is not None and kinds["postsim"] and kinds["sim"]:
        index(kinds["sim"], "traces.sim.json")
        files["traces_sim"] = f"sweep/{table}/{ident}/traces.sim.json"
    return files


def _current(block: str, pdk: str) -> set[str]:
    """The digests of ``block``'s designs in ``pdk`` as its runs are now (every grid's and
    single's)."""
    return set(design_space(block, pdk))


# the format of a run's export (``export_run``): an export in another is made again
VIEW_FORMAT = 4


def run_file(block: str, run: Path) -> str:
    """A run's table in the viewer's data, under ``build/web/data/sweep/``: ``<block>/runs/<label>``
    (``run_label``: ``<run>/<stamp>``), its instances' files in the folder of that name."""
    return f"{block}/runs/{run_label(block, run)}"


def run_folders(run: Path) -> list[tuple[str, Path]]:
    """A run's instance directories (``<pdk>/<name>/``, each with its record or a step's
    ``step.json``: a run stopped before its records has the latter alone), by PDK then name."""
    found = []
    for pdk in sorted(path for path in run.iterdir() if path.is_dir()):
        for folder in sorted(path for path in pdk.iterdir() if path.is_dir()):
            if (folder / "instance.json").exists() or any(folder.glob("*/step.json")):
                found.append((pdk.name, folder))
    return found


def _stand_in(block: str, pdk: str, folder: Path) -> dict[str, Any]:
    """An instance's record where its run stopped before making one: its name, nothing measured."""
    return {
        **_base_results(block, pdk, None, folder.name, folder.name),
        "error": "no record: the run stopped before this instance's results step",
    }


def _row(record: dict[str, Any]) -> dict[str, Any]:
    """An instance's row in a table: its id, PDK, parameters, metrics, error's last line, seconds."""
    return {
        "id": record["id"],
        "pdk": record["pdk"],
        "params": record["params"],
        "metrics": record["metrics"],
        "error": ((record["error"] or "").strip().splitlines() or [None])[-1],
        "seconds": record.get("seconds"),
    }


def _table(block: str, run_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """A table of ``rows`` (``_row``'s, narrowed in place to the parameters that tell them apart):
    the parameters that differ, then every metric (the design's size first: child cells, devices,
    device and layout area; the rest by name), and the parameter that is the block's topology
    where it differs (``flow.web.export.topology``), which the scatter marks a point by."""
    from flow import pipeline
    from flow.web.export import BLOCKS, topology

    names = sorted({name for row in rows for name in row["params"]})
    varying = [name for name in names if len({json.dumps(row["params"].get(name)) for row in rows}) > 1]
    present = {name for row in rows for name in row["metrics"]}
    metrics = [name for name in dict.fromkeys([*pipeline.GEOMETRY, *sorted(present)]) if name in present]
    for row in rows:
        row["params"] = {name: row["params"].get(name) for name in varying}
    data = {
        "block": block,
        "title": BLOCKS.get(block, block),
        "run": run_name,
        "params": varying,
        "metrics": metrics,
        "rows": rows,
    }
    shape = topology(block, rows, varying)
    return {**data, "topology": shape} if shape else data


def instance_export(block: str, ident: str, record: dict[str, Any], folder: Path, table: str) -> dict[str, Any]:
    """An instance's file in a run's table (``export_run``): its row, parameters, analyses, waves,
    layout (with its views: ``instance_views``), error, the record's evidence, pre-layout metrics,
    back-annotation, rejection and unjudged bounds, and its steps as the viewer tells them
    (``flow.web.export.steps_view``)."""
    from flow.web.export import steps_view

    try:
        files = instance_views(block, ident, record, DATA_DIR, table=table, folder=folder)
    except Exception as error:  # noqa: BLE001 - a missing view is shown as missing
        print(f"{table}/{ident}: {error!r}")
        files = {}
    entry = record.get("layout")
    return {
        **_row(record),
        "label": record.get("label"),
        "name": record.get("name"),
        "details": record.get("details", []),
        "waves": record.get("waves", {}),
        # an instance laid out by no one keeps its netlist's views (no gds: no layout)
        "layout": {**(entry or {}), **files} if entry or files else None,
        "error": record["error"],
        **{
            key: record.get(key)
            for key in ("evidence", "prelayout", "prelayout_details", "annotation", "rejected", "unjudged")
        },
        "steps": steps_view(folder, record),
    }


def export_run(block: str, run: Path, pool: ProcessPoolExecutor, force: bool = False) -> dict[str, Any]:
    """A run's table in the viewer's data (``run_file``: a row per instance it holds, as a table step
    makes one, and a file per instance, ``instance_export``), made again where a record or step of
    the run is newer than it, its format another or ``force``; the run's entry in the catalog (its
    label, file, instances, failures and when it was made)."""
    file = run_file(block, run)
    path = DATA_DIR / f"{file}.json"
    folders = run_folders(run)
    made = [
        marker.stat().st_mtime
        for _pdk, folder in folders
        for marker in (folder / "instance.json", *folder.glob("*/step.json"))
        if marker.exists()
    ]
    data: dict[str, Any] | None = json.loads(path.read_text()) if path.exists() else None
    if force or data is None or data.get("format") != VIEW_FORMAT or path.stat().st_mtime <= max(made, default=0.0):
        found: dict[str, tuple[Path, dict[str, Any]]] = {}
        for pdk, folder in folders:
            marker = folder / "instance.json"
            record = json.loads(marker.read_text()) if marker.exists() else _stand_in(block, pdk, folder)
            found.setdefault(record["id"], (folder, record))
        shutil.rmtree(DATA_DIR / file, ignore_errors=True)
        (DATA_DIR / file).mkdir(parents=True)
        futures = {
            ident: pool.submit(instance_export, block, ident, record, folder, file)
            for ident, (folder, record) in found.items()
        }
        for ident, future in futures.items():
            instance = future.result()
            (DATA_DIR / file / f"{ident}.json").write_text(json.dumps(_json(instance), separators=(",", ":")))
        data = {**_table(block, run_label(block, run), [_row(record) for _folder, record in found.values()])}
        data["format"] = VIEW_FORMAT
        path.write_text(json.dumps(_json(data), separators=(",", ":")))
    return {
        "label": run_label(block, run),
        "file": file,
        "instances": len(data["rows"]),
        "failed": sum(1 for row in data["rows"] if row["error"]),
        "created": run_time(run),
    }


def table(blocks: list[str], workers: int, run: Path | None = None) -> None:
    """The viewer's tables of each block (``build/web/data/sweep/``): each of its runs' own
    (``export_run``: ``run``'s made again, the others where their records changed), and the catalog's
    entry of each block, its runs newest first and the one the viewer opens on (``default``: ``run``,
    else the newest)."""

    from flow.web.export import BLOCKS

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog_path = DATA_DIR / "catalog.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
    # a block whose sweep is gone leaves the catalog
    catalog = {block: entry for block, entry in catalog.items() if block in sweep_blocks() or block in blocks}
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        for block in blocks:
            runs = sorted(_runs(block), key=run_time, reverse=True)
            if not runs:
                raise FileNotFoundError(f"no run of {block} in {RUNS_DIR / block}")
            entries = [export_run(block, each, pool, force=each == run) for each in runs]
            # the files of runs gone, and of the exports before runs had tables of their own
            (DATA_DIR / f"{block}.json").unlink(missing_ok=True)
            for stale in (DATA_DIR / block).iterdir() if (DATA_DIR / block).is_dir() else ():
                if stale.name != "runs":
                    shutil.rmtree(stale) if stale.is_dir() else stale.unlink()
            kept = {DATA_DIR / entry["file"] for entry in entries}
            for stale in sorted((DATA_DIR / block / "runs").rglob("*.json")):
                if stale.exists() and stale.with_suffix("") not in kept and not any(map(stale.is_relative_to, kept)):
                    stale.unlink()
                    shutil.rmtree(stale.with_suffix(""), ignore_errors=True)
            for folder in sorted((DATA_DIR / block / "runs").rglob("*"), reverse=True):
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
            # its optimizations' tables (flow.opt.runner.table, ``searches``) kept
            default = next(entry for entry in entries if run is None or entry["label"] == run_label(block, run))
            catalog[block] = {
                **catalog.get(block, {}),
                "title": BLOCKS.get(block, block),
                "run": default["label"],
                "instances": default["instances"],
                "runs": entries,
                "default": default["label"],
            }
            print(f"{block}: {len(entries)} runs, {default['label']} first: {default['instances']} instances")
    catalog_path.write_text(json.dumps(dict(sorted(catalog.items())), indent=1) + "\n")
