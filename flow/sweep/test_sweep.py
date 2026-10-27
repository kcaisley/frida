"""The sweep framework on a small generator and synthetic instance records."""

from __future__ import annotations

import ast
import inspect
import json
import math
from pathlib import Path

import hdl21 as h
import pytest

from flow import comp
from flow.sweep import flat_params, geometry, runner


def test_parameters_flatten_to_one_row() -> None:
    flat = flat_params(comp.Params(latch=comp.Latch.TRIPLE_TAIL, diffpair_w=16))
    assert flat["latch"] == "TRIPLE_TAIL" and flat["diffpair_w"] == 16
    assert all(isinstance(value, (bool, int, float, str)) or value is None for value in flat.values())


def test_geometry_counts_the_compiled_devices_and_their_area() -> None:
    """A leaf (transistors alone) has devices and no child cells; with its output stage as library
    cells the comparator has those for child cells, and their transistors are not its devices."""
    logic = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    comp.netlist.Cache.reset()
    module = comp.netlist(comp.Params())
    h.pdk.compile(module, logic)
    totals = geometry(module, "tsmc65")
    assert totals["devices"] == len(module.instances) and "child_cells" not in totals
    assert 0 < totals["device_area_um2"] < 100
    comp.netlist.Cache.reset()
    cells = comp.netlist(comp.Params(output_stage=comp.OutputStage.STDCELLS))
    h.pdk.compile(cells, logic)
    hierarchy = geometry(cells, "tsmc65")
    assert hierarchy["child_cells"] == 8 and hierarchy["devices"] < totals["devices"]
    comp.netlist.Cache.reset()


def test_every_sweep_module_keeps_the_contract() -> None:
    for block in runner.sweep_blocks():
        sweep = __import__(f"flow.{block}.sweep", fromlist=["instances"])
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
        spaces = {pdk: list(runner.design_space(block, pdk).values()) for pdk in runner.PDKS}
        assert any(spaces.values()), block
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


def test_the_comparator_space_is_its_families_within_each_pdks_limits() -> None:
    # each PDK's products of each family, FRIDA-1's comparator by name, each instance once
    labels = [label for label, _params in runner.labelled_space("comp", "tsmc65").values()]
    assert {"frida1", "dynamic_bias(ratio=3.5, k=3)", "reference(topology=strongarm)"} <= set(labels)
    assert {pdk: len(runner.design_space("comp", pdk)) for pdk in runner.PDKS} == {
        "tsmc65": 23,
        "tsmc28": 7,
        "ihp130": 20,
        "tower180": 20,
        "lf150": 16,
        "tpsc65": 20,
    }
    assert comp.frida1() == comp.FRIDA1
    # a family is a function of its knobs: every width times k; TSMC28's at TSMC65's physical widths
    assert comp.base_strongarm(tail_l=34, k=2.5).diffpair_w == 80 and comp.base_strongarm(tail_l=34, k=2.5).tail_w == 10
    space = {pdk: list(runner.design_space("comp", pdk).values()) for pdk in runner.PDKS}
    assert (
        comp.base_strongarm(tail_l=28, k=18) in space["tsmc28"]
        and comp.base_strongarm(tail_l=14, k=3) in space["tsmc65"]
    )
    for pdk in runner.PDKS:
        assert all(comp.valid(params, pdk) for params in space[pdk]), pdk
    # FRIDA-1's long latch decides too late in the older PDKs, a 54-unit tail in IHP130, the dynamic
    # bias in IHP130, and below C_TAIL/C_P of 5 in LF150 (comp.params.LIMITS)
    assert comp.frida1() in space["tsmc28"] and comp.frida1() not in space["ihp130"]
    assert not comp.valid(comp.frida1(), "ihp130") and not comp.valid(comp.base_strongarm(tail_l=54, k=4), "ihp130")
    assert comp.valid(comp.dynamic_bias(ratio=6, k=2), "lf150") and not comp.valid(
        comp.dynamic_bias(ratio=3.5, k=2), "lf150"
    )
    assert not comp.valid(comp.dynamic_bias(ratio=3.5, k=2), "ihp130") and not comp.valid(
        comp.dynamic_bias(ratio=6, k=2), "tower180"
    )
    for pdk in ("ihp130", "tower180", "tsmc28"):
        assert not any(params.bias == comp.Bias.DYNAMIC for params in space[pdk])
    # named but not swept: picked by name, and by label or digest the swept ones
    picked = runner.select(
        "comp", "tsmc65", ["triple_tail", "dynamic_bias(ratio=3.5, k=3)", runner.digest(comp.frida1())]
    )
    assert [label for label, _params in picked.values()] == ["triple_tail", "dynamic_bias(ratio=3.5, k=3)", "frida1"]
    with pytest.raises(LookupError, match="no instance"):
        runner.select("comp", "tsmc65", ["no_such_comparator"])


def test_a_floorplan_is_chosen_by_the_instances_structure() -> None:
    from flow.lvshift import sweep as lvshift
    from flow.lvshift.subckt import LvShiftParams

    # every size of a shifter by its case's floorplan; a structure no case has, none
    assert runner.hand_floorplan("lvshift", LvShiftParams(**lvshift.SIZES[3])).name == "lvshift_core.json"
    buffered = LvShiftParams(input_inverter=True, buffers=True, **lvshift.SIZES[0])
    assert runner.hand_floorplan("lvshift", buffered).name == "lvshift_buffered.json"
    assert runner.hand_floorplan("lvshift", LvShiftParams(buffers=True)) is None
    assert runner.hand_floorplan("capdriver", object()) is None  # no structure named


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
    monkeypatch.setattr(runner, "SWEEP_DIR", tmp_path / "sweep")
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
    monkeypatch.setattr(runner, "SWEEP_DIR", tmp_path / "sweep")
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
