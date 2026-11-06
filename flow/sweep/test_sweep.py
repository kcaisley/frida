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
