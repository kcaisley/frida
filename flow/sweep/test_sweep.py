"""The sweep framework on a small generator and synthetic instance records."""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import math
from pathlib import Path

import hdl21 as h
import pytest

from flow import capdac, comp
from flow.sweep import ADDED_DEFAULTS, flat_params, geometry, runner


def test_a_parameter_its_class_gained_later_leaves_only_that_classs_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """A parameter added to one class after its instances ran is left out of its rows at the value
    they all had, so their digests hold; another class's parameter of the same name, which its
    instances always held, stays in theirs (the converter's legacy array kept its own weights when
    capdac gained them)."""

    @h.paramclass
    class Gained:
        weights = h.Param(dtype=tuple[int, ...] | None, desc="added later", default=None)

    @h.paramclass
    class Always:
        weights = h.Param(dtype=tuple[int, ...] | None, desc="held from the start", default=None)

    @h.paramclass
    class Both:
        gained = h.Param(dtype=Gained, desc="", default=Gained())
        always = h.Param(dtype=Always, desc="", default=Always())

    monkeypatch.setitem(ADDED_DEFAULTS, (f"{__name__}.{Gained.__qualname__}", "weights"), None)
    assert flat_params(Both()) == {"always.weights": None}
    assert flat_params(Both(gained=Gained(weights=(2, 1)))) == {"gained.weights": "2, 1", "always.weights": None}
    # capdac's 120 records were keyed before it gained its weights
    assert "weights" not in flat_params(capdac.Params())


def test_parameters_flatten_to_one_row() -> None:
    flat = flat_params(comp.Params(latch=comp.Latch.TRIPLE_TAIL, diffpair_w=16))
    assert flat["latch"] == "TRIPLE_TAIL" and flat["diffpair_w"] == 16
    assert all(isinstance(value, (bool, int, float, str)) or value is None for value in flat.values())


def test_geometry_counts_the_compiled_devices_and_their_area() -> None:
    """A leaf (transistors alone) has devices and no child cells; with its output stage as library
    cells the comparator has those for child cells, and their transistors are not its devices."""
    logic = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    # elaborated with TSMC65 the default, as every runner does: each device fingered to its row cells
    manager = importlib.import_module("hdl21.pdk.pdk")._mgr
    previous = manager.default
    h.pdk.set_default(logic)
    try:
        comp.netlist.Cache.reset()
        module = comp.netlist(comp.Params())
        h.pdk.compile(module, logic)
        totals = geometry(module, "tsmc65")
        assert totals["devices"] == len(module.instances) and "child_cells" not in totals
        # the devices' own row cells, unplaced: about 86 um2, several times their gates' W L
        assert 50 < totals["device_area_um2"] < 150
        comp.netlist.Cache.reset()
        cells = comp.netlist(comp.Params(output_stage=comp.OutputStage.STDCELLS))
        h.pdk.compile(cells, logic)
        hierarchy = geometry(cells, "tsmc65")
        assert hierarchy["child_cells"] == 8 and hierarchy["devices"] < totals["devices"]
        assert 0 < hierarchy["device_area_um2"] < totals["device_area_um2"]  # the library cells' own in it
    finally:
        comp.netlist.Cache.reset()
        manager.default = previous
    comp.netlist.Cache.reset()


def test_every_sweep_module_keeps_the_contract() -> None:
    from flow.test_pipeline import NOT_MIGRATED

    for block in runner.sweep_blocks():
        try:
            sweep = __import__(f"flow.{block}.sweep", fromlist=["instances"])
        except ImportError:
            # a legacy block (flow/test_pipeline.py's NOT_MIGRATED) may no longer import: it waits on
            # its port, and fails where it is run; a block on the pipeline imports
            assert block in NOT_MIGRATED, block
            continue
        # a block on the pipeline gives its runs and its record (flow/test_pipeline.py checks the
        # rest), the others their characterization and generator
        if hasattr(sweep, "runs"):
            assert callable(sweep.runs) and callable(sweep.record), block
        else:
            assert callable(sweep.characterize) and sweep.GENERATOR is not None, block
        # no tables of topologies or sizings of its own (a block's params may name its topologies)
        defined = {
            target.id
            for node in ast.parse(inspect.getsource(sweep)).body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)
        }
        assert not {"TOPOLOGIES", "SIZINGS"} & defined, block
        spaces, unavailable = {}, set()
        for pdk in runner.PDKS:
            try:
                spaces[pdk] = list(runner.design_space(block, pdk).values())
            except (LookupError, ModuleNotFoundError):
                # a design space of the PDK's own (its devices, its extracted arrays), which this
                # checkout does not have (CI: no PDK, no build)
                spaces[pdk] = []
                unavailable.add(pdk)
        assert any(spaces.values()) or unavailable == set(runner.PDKS), block
        for pdk, instances in spaces.items():
            # an instance is its parameters: each class the generator takes, none twice but where two
            # ways reach the same parameters
            assert all(type(params) is type(instances[0]) for params in instances), (block, pdk)
            if hasattr(sweep, "cost"):
                assert all(sweep.cost(pdk, params) > 0 for params in instances), (block, pdk)
            # a floorplan chosen by structure names parameters the instances have
            for name in getattr(sweep, "STRUCTURE", ()):
                assert all(hasattr(params, name) for params in instances), (block, name)


def test_an_instance_is_its_parameters() -> None:
    a, b = list(runner.design_space("comp", "tsmc65").values())[:2]
    assert runner.digest(a) == runner.digest(flat_params(a)) == runner.digest(comp.Params(**vars(a)))
    assert runner.digest(a) != runner.digest(b) and len(runner.digest(a)) == 12
    assert runner.instance_id("ihp130", a) == f"ihp130__{runner.digest(a)}"
    # the models' cache and the sweep's runs key an instance alike
    assert runner.design_space("comp", "tsmc65")[runner.digest(a)] == a


def test_the_comparator_space_is_its_grid_and_the_adcs_comparators() -> None:
    # in every PDK the grid (every latch with either tail, three pair widths, C_P twice with a dynamic
    # bias: 54) and FRIDA-1's comparator by name; and the ADC's comparators, the PDK's StrongARM
    # ladders (TSMC65's 20 with its dynamic biases, TSMC28's 4, IHP130's and Tower180's 20, LF150's 14
    # and TPSC65's 12, with their dynamic biases: 2 and 8); each once
    labels = [label for label, _params in runner.labelled_space("comp", "tsmc65").values()]
    grid_point = "topologies(latch=STRONGARM, bias=SWITCHED, diffpair_w=128)"
    assert {"frida1", "dynamic_bias(ratio=3.5, k=3)", "base_strongarm(tail_l=14, k=3)", grid_point} <= set(labels)
    assert {pdk: len(runner.design_space("comp", pdk)) for pdk in runner.PDKS} == {
        "tsmc65": 75,
        "tsmc28": 59,
        "ihp130": 75,
        "tower180": 75,
        "lf150": 71,
        "tpsc65": 75,
    }
    assert comp.frida1() == comp.FRIDA1
    # the ADC's StrongARM: every width times k but the tail's, 4 k wide
    strongarm = comp.base_strongarm.spaces("lf150")["tail_l=34, k=1.5"].base
    assert strongarm.diffpair_w == 48 and strongarm.tail_w == 6
    # named but not swept: picked by name, and by label or digest the swept ones
    picked = runner.select(
        "comp", "tsmc65", ["triple_tail", "dynamic_bias(ratio=3.5, k=3)", runner.digest(comp.frida1())]
    )
    assert [label for label, _params in picked.values()] == ["triple_tail", "dynamic_bias(ratio=3.5, k=3)", "frida1"]
    with pytest.raises(LookupError, match="no instance"):
        runner.select("comp", "tsmc65", ["no_such_comparator"])


def test_the_table_has_a_row_per_instance_and_a_file_each(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "sweep/toy/20261020_000000"
    idents = []
    for pdk, w, delay in (("tsmc65", 1, 1e-10), ("ihp130", 2, 3e-10)):
        params = {"w": w, "kind": "inv"}
        ident = runner.instance_id(pdk, params)
        idents.append(ident)
        path = run / pdk / runner.digest(params) / "instance.json"
        path.parent.mkdir(parents=True)
        record = {
            "block": "toy",
            "id": ident,
            "pdk": pdk,
            "params": params,
            "metrics": {"delay_s": delay},
            "details": [
                {
                    "name": "delay_supply",
                    "title": "Delay",
                    "x_label": "Supply (V)",
                    "y_label": "Delay (s)",
                    "x": [1.0, 1.2],
                    "series": {"delay": [delay, math.nan]},
                    "x_log": False,
                    "y_log": True,
                }
            ],
            "waves": {},
            "error": None,
            "seconds": 1.0,
        }
        path.write_text(json.dumps(runner._json(record)))
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "sweep")
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path / "web/data/sweep")
    # an instance file of an earlier run's, under an older id
    (tmp_path / "web/data/sweep/toy").mkdir(parents=True)
    (tmp_path / "web/data/sweep/toy/tsmc65__inv__x1.json").write_text("{}")
    # and a block whose sweep is gone
    (tmp_path / "web/data/sweep/catalog.json").write_text(json.dumps({"gone": {"title": "Gone", "instances": 1}}))
    runner.table(["toy"], 1)
    data = json.loads((tmp_path / "web/data/sweep/toy.json").read_text())
    assert [row["id"] for row in data["rows"]] == sorted(idents)
    assert all(set(row) == {"id", "pdk", "params", "metrics", "error", "seconds"} for row in data["rows"])
    assert data["params"] == ["w"]  # the kind is the same everywhere
    assert "details" not in data  # each plot is scaled to its own data
    instance = json.loads((tmp_path / f"web/data/sweep/toy/{idents[0]}.json").read_text())
    assert instance["params"] == {"w": 1, "kind": "inv"} and instance["details"][0]["series"]["delay"][1] is None
    assert not (tmp_path / "web/data/sweep/toy/tsmc65__inv__x1.json").exists()
    catalog = json.loads((tmp_path / "web/data/sweep/catalog.json").read_text())
    assert catalog["toy"]["instances"] == 2 and "gone" not in catalog


def test_a_run_of_some_pdks_keeps_the_others_from_the_run_before(tmp_path: Path, monkeypatch) -> None:
    from flow.sweep import lookup

    params = {"w": 1, "kind": "inv"}
    ident = runner.digest(params)
    # an earlier run in two PDKs, a later one in TSMC65 alone
    for run, pdk, delay in (
        ("20261020_000000", "tsmc65", 1e-10),
        ("20261020_000000", "ihp130", 3e-10),
        ("20261021_000000", "tsmc65", 2e-10),
    ):
        path = tmp_path / "sweep/toy" / run / pdk / ident / "instance.json"
        path.parent.mkdir(parents=True)
        record = {
            "block": "toy",
            "id": runner.instance_id(pdk, params),
            "pdk": pdk,
            "params": params,
            "metrics": {"delay_s": delay},
            "details": [],
            "waves": {},
            "error": None,
            "seconds": 1.0,
        }
        path.write_text(json.dumps(record))
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "sweep")
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path / "web/data/sweep")
    assert runner.newest_run("toy").name == runner.newest_run("toy", "tsmc65").name == "20261021_000000"
    assert runner.newest_run("toy", "ihp130").name == "20261020_000000"
    assert {pdk: run.name for pdk, run in runner.pdk_runs("toy").items()} == {
        "ihp130": "20261020_000000",
        "tsmc65": "20261021_000000",
    }
    # the table: each PDK's newest run
    runner.table(["toy"], 1)
    data = json.loads((tmp_path / "web/data/sweep/toy.json").read_text())
    assert {row["pdk"]: row["metrics"]["delay_s"] for row in data["rows"]} == {"tsmc65": 2e-10, "ihp130": 3e-10}
    assert data["run"] == "20261021_000000 (tsmc65), 20261020_000000 (ihp130)"
    # and the models' lookup alike
    lookup._newest_run.cache_clear()
    try:
        assert lookup._sweep_record("toy", "tsmc65", ident)["metrics"]["delay_s"] == 2e-10
        assert lookup._sweep_record("toy", "ihp130", ident)["metrics"]["delay_s"] == 3e-10
        assert lookup._sweep_record("toy", "tower180", ident) is None
    finally:
        lookup._newest_run.cache_clear()


def test_the_sweep_targets_call_the_library_on_every_block(monkeypatch) -> None:
    from flow.sweep import targets

    calls = []
    monkeypatch.setattr(runner, "run", lambda blocks, pdks, workers, **kw: calls.append(("run", blocks, workers, kw)))
    monkeypatch.setattr(runner, "layout", lambda blocks, workers: calls.append(("layout", blocks, workers)))
    monkeypatch.setattr(runner, "table", lambda blocks, workers: calls.append(("table", blocks, workers)))
    blocks = runner.sweep_blocks()
    targets.run()
    targets.missing()
    targets.layout()
    targets.tables()
    assert calls == [
        ("run", blocks, 36, {}),
        ("run", blocks, 36, {"failed": True}),
        ("layout", blocks, 28),
        ("table", blocks, 16),
    ]


def test_a_lookup_without_simulation_never_waits_on_a_lock(tmp_path: Path, monkeypatch) -> None:
    import fcntl
    import hashlib

    from flow.sweep import lookup

    monkeypatch.setattr(lookup, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(lookup, "_sweep_record", lambda block, pdk, ident: None)
    params = comp.Params()
    digest = hashlib.sha1(json.dumps(flat_params(params), sort_keys=True).encode()).hexdigest()[:12]
    assert digest == runner.digest(params)
    lock = tmp_path / "comp/tsmc65" / f"{digest}.lock"
    lock.parent.mkdir(parents=True)
    # another process's characterization, running
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        with pytest.raises(LookupError):
            lookup.characterized("comp", "tsmc65", params, simulate=False)
        record = {"error": None, "metrics": {"delay_s": 1e-10}}
        (lock.parent / digest).mkdir()
        (lock.parent / digest / "instance.json").write_text(json.dumps(record))
        assert lookup.characterized("comp", "tsmc65", params, simulate=False) == record


# ---- a toy block on the pipeline, for the runner's own contract: its reader (sim.read), the
# levels a record runs at, and a layout of its own (layout.py's lay_out)

_TOY = {
    "__init__.py": '"""A toy block."""\n',
    "params.py": '''"""A toy design: how its own layout signs itself off."""

from dataclasses import dataclass

import hdl21 as h

from flow import pipeline


@h.paramclass
class Params:
    mode = h.Param(dtype=int, desc="0: no LVS source; 1: an LVS source; 2: signed off by lay_out", default=0)


@dataclass(frozen=True)
class TbParams(pipeline.TbParams):
    pdk: str
    params: Params
    name: str
''',
    "subckt.py": '''"""Nothing."""

import hdl21 as h

from .params import Params


@h.generator
def netlist(params: Params) -> h.Module:
    return h.Module()
''',
    "sim.py": '''"""A run writes its name; the block reads it back itself."""

from datetime import datetime, timezone
from pathlib import Path

from flow import pipeline

from .params import TbParams


def simulate(tb: TbParams, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    raw = run_dir / "raw.txt"
    raw.write_text(tb.name)
    return raw


def read(raw: Path, tb: TbParams) -> pipeline.Meas:
    info = pipeline.MeasInfo(backend="behavioral", timestamp_utc=datetime.now(timezone.utc), readbacks={"text": raw.read_text()})
    return pipeline.Meas(group=None, index=None, dut=tb.params, info=info, param=tb)
''',
    "sweep.py": '''"""One named instance; a run a level."""

from flow.pipeline import Level, Meas, Record, named

from .params import Params, TbParams


@named
def one() -> Params:
    return Params()


def runs(pdk: str, params: Params, level: Level = Level.FULL) -> dict[str, TbParams]:
    names = [name for name in Level if name.value <= level.value]
    return {name.name.lower(): TbParams(pdk=pdk, params=params, name=name.name.lower()) for name in names}


def record(measurements: dict[str, Meas]) -> Record:
    return Record(metrics={f"read_{name}": meas.info.readbacks["text"] == name for name, meas in measurements.items()})
''',
    "layout.py": '''"""Its own layout: a box, and what its mode says it signs off."""

import json
from pathlib import Path

from klayout import db

from .params import Params


def lay_out(params: Params, pdk: str, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    layout = db.Layout()
    top = layout.create_cell("toy")
    top.shapes(layout.layer(1, 0)).insert(db.Box(0, 0, 2000, 1000))
    gds = run_dir / "toy.gds"
    layout.write(str(gds))
    if params.mode == 1:
        (run_dir / "source.cdl").write_text(".subckt toy\\n.ends\\n")
    if params.mode == 2:
        (run_dir / "drc_violations.json").write_text(json.dumps({"violations": {}}))
        summary = {
            "drc_report": str(run_dir / "drc_violations.json"),
            "lvs_correct": False,
            "warnings": ["an accepted mismatch"],
            "pex_netlist": str(run_dir / "toy.pex.netlist"),
            "pex_sha256": "0" * 64,
        }
        (run_dir / "signoff_summary.json").write_text(json.dumps(summary))
    return gds
''',
}


class _NowPool:
    """A process pool that runs each task at once, in this process (where the toy block imports)."""

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def submit(self, function, *args, **kwargs):
        from concurrent.futures import Future

        future = Future()
        future.set_result(function(*args, **kwargs))
        return future


@pytest.fixture
def toy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The toy block, ``flow.toyblock``, in a PDK of no devices (``toypdk``), its runs under
    ``tmp_path/build`` and characterized in this process."""
    import sys
    from types import SimpleNamespace

    import flow
    from flow import sweep
    from flow.layout.devices import device

    package = tmp_path / "flow" / "toyblock"
    package.mkdir(parents=True)
    for name, text in _TOY.items():
        (package / name).write_text(text)
    monkeypatch.setattr(flow, "__path__", [*flow.__path__, str(tmp_path / "flow")])
    monkeypatch.setitem(sys.modules, "pdk.toypdk", SimpleNamespace(pdk_logic=None))
    monkeypatch.setattr(h.pdk, "set_default", lambda logic: None)
    monkeypatch.setattr(h.pdk, "compile", lambda module, *args: None)
    monkeypatch.setattr(device, "resolve", lambda module, pdk: None)
    monkeypatch.setattr(sweep, "geometry", lambda module, pdk: {})
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "build")
    monkeypatch.setattr(runner, "ProcessPoolExecutor", _NowPool)
    for cached in (runner.design_space, runner.labelled_space):
        cached.cache_clear()
    yield importlib.import_module("flow.toyblock")
    for cached in (runner.design_space, runner.labelled_space):
        cached.cache_clear()
    for name in [name for name in sys.modules if name.startswith("flow.toyblock")]:
        del sys.modules[name]


def _toy_record(run: Path) -> dict:
    (path,) = run.glob("toypdk/*/instance.json")
    return json.loads(path.read_text())


def test_a_block_reads_its_raw_output_itself_at_each_level(toy, capsys) -> None:
    """The runner reads a run by the block's ``sim.read`` (raw file removed), its record keeps the
    level it ran at, and ``failed`` (``--missing``) re-runs a record below the level asked for into
    the same run, and only that; the circuit level takes picked instances alone."""
    from flow import pipeline

    run = runner.run(["toyblock"], ("toypdk",), 1, names=["one"])["toyblock"]
    record = _toy_record(run)
    assert record["error"] is None, record["error"]
    assert record["level"] == pipeline.Level.FULL.value
    assert record["metrics"] == {"read_screen": True, "read_search": True, "read_full": True}
    assert not list(run.rglob("raw.txt"))
    # FULL again: nothing below it, nothing run
    capsys.readouterr()
    assert runner.run(["toyblock"], ("toypdk",), 1, failed=True, names=["one"])["toyblock"] == run
    assert capsys.readouterr().out.startswith("0 instances")
    # the circuit level: the record below it, re-run into the same run
    level = pipeline.Level.CIRCUIT
    assert runner.run(["toyblock"], ("toypdk",), 1, failed=True, names=["one"], level=level)["toyblock"] == run
    assert sorted(path.name for path in (runner.RUNS_DIR / "toyblock").iterdir()) == [run.name]
    record = _toy_record(run)
    assert record["level"] == level.value and record["metrics"]["read_circuit"] is True
    # a record from before records carried their level ran at FULL
    (path,) = run.glob("toypdk/*/instance.json")
    path.write_text(json.dumps({key: value for key, value in record.items() if key != "level"}))
    capsys.readouterr()
    runner.run(["toyblock"], ("toypdk",), 1, failed=True, names=["one"])
    assert capsys.readouterr().out.startswith("0 instances")
    runner.run(["toyblock"], ("toypdk",), 1, failed=True, names=["one"], level=level)
    assert _toy_record(run)["level"] == level.value
    with pytest.raises(ValueError, match="pick the instances"):
        runner.run(["toyblock"], ("toypdk",), 1, level=level)


def test_a_block_without_levels_is_never_below_one(toy) -> None:
    """A block whose ``runs`` takes no level records none, and no level re-runs it."""
    from flow import pipeline

    sweep = importlib.import_module("flow.toyblock.sweep")
    leveled = sweep.runs
    sweep.runs = lambda pdk, params: leveled(pdk, params, pipeline.Level.SCREEN)
    run = runner.run(["toyblock"], ("toypdk",), 1, names=["one"])["toyblock"]
    record = _toy_record(run)
    assert record["level"] is None and set(record["metrics"]) == {"read_screen"}
    assert not runner._level_below(record, pipeline.Level.CIRCUIT)


def test_a_block_with_its_own_layout_is_signed_off_as_it_states(toy, tmp_path: Path, monkeypatch) -> None:
    """``lay_out_one`` runs the block's ``lay_out``: a signoff it ran itself is recorded as it is
    (an accepted LVS mismatch is no failure); its LVS source is checked by the shared signoff; with
    none, DRC alone. The runner's layout step and the layout verb take it in place of ALIGN's."""
    from flow import __main__ as cli
    from flow.layout import logs, step
    from flow.layout.signoff import RowSignoff

    calls = []

    def shared(pdk, gds, source, run_dir, checker):
        calls.append(("signoff", Path(source).name))
        return RowSignoff(run_dir / "drc_violations.json", 0, None, True)

    def drc_only(pdk, gds, run_dir, checker):
        calls.append(("drc", gds.name))
        return RowSignoff(run_dir / "drc_violations.json", 0, None, None)

    monkeypatch.setattr(step, "signoff", shared)
    monkeypatch.setattr(step, "drc", drc_only)
    monkeypatch.setattr(step, "extracted", lambda pdk, gds, name, run_dir: {"netlist": "x"})
    assert step.own_layout("toyblock") and not step.own_layout("comp")
    entries = {}
    for mode in (0, 1, 2):
        out = tmp_path / f"mode{mode}"
        step.lay_out_one("toyblock", out, "toypdk", toy.params.Params(mode=mode), pex=mode == 1)
        entries[mode] = json.loads((out / "summary.json").read_text())["toypdk/lay_out"]
    assert calls == [("drc", "toy.gds"), ("signoff", "source.cdl")]
    assert [entries[mode]["signoff"] for mode in (0, 1, 2)] == ["drc", "shared", "lay_out"]
    assert entries[0]["cell_um"] == [2.0, 1.0] and entries[0]["lvs_correct"] is None
    assert entries[1]["pex"] == {"netlist": "x"}
    assert entries[2]["lvs_correct"] is False and entries[2]["warnings"] == ["an accepted mismatch"]
    assert entries[2]["drc_violations"] == 0 and entries[2]["pex"]["sha256"] == "0" * 64
    # DRC violations fail it
    monkeypatch.setattr(step, "drc", lambda pdk, gds, run_dir, checker: RowSignoff(run_dir / "d.json", 3, None, None))
    with pytest.raises(RuntimeError, match="failed"):
        step.lay_out_one("toyblock", tmp_path / "dirty", "toypdk", toy.params.Params())
    monkeypatch.setattr(step, "drc", drc_only)
    # the runner's layout step: the record gains the entry and its area
    instance = tmp_path / "build/toyblock/20261101_000000/toypdk/abc"
    instance.mkdir(parents=True)
    (instance / "instance.json").write_text(json.dumps({"error": None, "metrics": {"device_area_um2": 1.0}}))
    monkeypatch.setattr(runner, "instance_params", lambda block, pdk, ident: toy.params.Params())
    entry = runner.layout_job("toyblock", instance, "toypdk", pex=False)
    assert entry["error"] is None and entry["signoff"] == "drc" and entry["floorplan"] == "lay_out"
    assert json.loads((instance / "instance.json").read_text())["metrics"]["layout_area_um2"] == 2.0
    # the layout verb, by name: its own flow, no ALIGN plan
    layout_runs = tmp_path / "build/toyblock/layout"
    monkeypatch.setattr(
        importlib.import_module("flow"), "new_run", lambda *parts: (layout_runs / "20261102_000000").resolve()
    )
    monkeypatch.setattr(logs, "console", lambda: None)
    cli.layout_instances("toyblock", ["one"], ("toypdk",), auto=False, plan_only=False)
    record = json.loads((layout_runs / "20261102_000000/toypdk/one/instance.json").read_text())
    assert record["layout"]["w_um"] == 2.0 and record["layout"]["error"] in ("", None)
    with pytest.raises(SystemExit, match="lays itself out"):
        cli.layout_instances("toyblock", ["one"], ("toypdk",), auto=False, plan_only=True)


def test_a_layouts_extraction_is_recorded_from_the_repositorys_root(tmp_path: Path) -> None:
    """An extraction's netlist inside the repository is recorded from its root, as the GDS is, by
    the runner's layout step and the layout verb alike, so a copy of the repository reads its own;
    one outside it as it is."""
    from flow import __main__ as cli

    inside = {"netlist": str(runner.ROOT / "build/adc/layout/x/adc.pex.netlist"), "sha256": "0" * 64}
    outside = {"netlist": str(tmp_path / "adc.pex.netlist")}
    for shown in (runner._shown_pex, cli._shown_pex):
        assert shown(inside) == {"netlist": "build/adc/layout/x/adc.pex.netlist", "sha256": "0" * 64}
        assert shown(outside) == outside
        assert shown(None) is None and shown({"skipped": "LVS did not match"}) == {"skipped": "LVS did not match"}


def test_a_layout_is_found_by_its_digest_newest_first(tmp_path: Path, monkeypatch) -> None:
    """``lookup.laid_out``: the newest layout entry of the instance with these parameters that
    stands (its GDS on disk, no error), from a layout run or a sweep run's record; none raises,
    naming the command that lays it out."""
    from flow.sweep import lookup

    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "build")
    params = comp.Params()
    ident = runner.digest(params)
    gds = tmp_path / "a.gds"
    gds.write_text("")

    def write(path: Path, layout: dict, ident: str = ident) -> None:
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"id": f"tsmc65__{ident}", "layout": layout}))

    root = tmp_path / "build/toy"
    write(root / "layout/20261101_000000/tsmc65/frida1/instance.json", {"gds": str(gds), "w_um": 1})
    write(root / f"20261102_000000/tsmc65/{ident}/instance.json", {"gds": str(gds), "w_um": 2})
    write(root / "layout/20261103_000000/tsmc65/frida1/instance.json", {"gds": str(gds), "error": "failed"})
    write(root / "layout/20261104_000000/tsmc65/frida1/instance.json", {"gds": str(tmp_path / "gone.gds")})
    write(root / "layout/20261105_000000/tsmc65/other/instance.json", {"gds": str(gds), "w_um": 5}, "0" * 12)
    assert lookup.laid_out("toy", "tsmc65", params)["w_um"] == 2
    with pytest.raises(LookupError, match=f"python -m flow layout toy --pdk ihp130 --instance {ident}"):
        lookup.laid_out("toy", "ihp130", params)


def test_the_comparators_circuit_level_runs_its_full_runs() -> None:
    """The comparator's characterization is SPICE already: its circuit level is its full one."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    from flow.pipeline import Level

    sweep = importlib.import_module("flow.comp.sweep")
    assert sweep.runs("tsmc65", comp.FRIDA1, Level.CIRCUIT) == sweep.runs("tsmc65", comp.FRIDA1, Level.FULL)
