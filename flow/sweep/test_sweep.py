"""The sweep framework on a small generator and synthetic instance records."""

from __future__ import annotations

import json
import math
from pathlib import Path

import hdl21 as h
import pytest

from flow.comp.subckt import Comp, CompParams, Stages
from flow.sweep import flat_params, geometry, runner


def test_parameters_flatten_to_one_row() -> None:
    flat = flat_params(CompParams(comp_stages=Stages.TRIPLE, diffpair_w=16))
    assert flat["comp_stages"] == "TRIPLE" and flat["diffpair_w"] == 16
    assert all(isinstance(value, (bool, int, float, str)) or value is None for value in flat.values())


def test_geometry_counts_the_compiled_devices_and_their_gate_area() -> None:
    logic = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    module = Comp(CompParams())
    h.pdk.compile(module, logic)
    totals = geometry(module, "tsmc65")
    assert totals["devices"] == len(Comp(CompParams()).instances) or totals["devices"] > 0
    assert 0 < totals["gate_area_um2"] < 100 and totals["cells"] == 0


def test_every_sweep_module_keeps_the_contract() -> None:
    for block in runner.sweep_blocks():
        sweep = __import__(f"flow.{block}.sweep", fromlist=["instances"])
        assert callable(sweep.characterize) and sweep.GENERATOR is not None, block
        assert not hasattr(sweep, "TOPOLOGIES") and not hasattr(sweep, "SIZINGS"), block
        spaces = {pdk: sweep.instances(pdk) for pdk in runner.PDKS}
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
    from flow.comp import sweep as comp

    a, b = comp.instances("tsmc65")[:2]
    assert runner.digest(a) == runner.digest(flat_params(a)) == runner.digest(CompParams(**vars(a)))
    assert runner.digest(a) != runner.digest(b) and len(runner.digest(a)) == 12
    assert runner.instance_id("ihp130", a) == f"ihp130__{runner.digest(a)}"
    # the models' cache and the sweep's runs key an instance alike
    assert runner.design_space("comp", "tsmc65")[runner.digest(a)] == a


def test_a_floorplan_is_chosen_by_the_instances_structure() -> None:
    from flow.samp import sweep as samp
    from flow.samp.subckt import SampParams, SwitchType

    # every size of a switch by its case's floorplan; a structure no case has, none
    assert runner.hand_floorplan("samp", SampParams(**samp.X4)).name == "samp_frida1.json"
    bootstrap = SampParams(switch_type=SwitchType.NMOS, bootstrap=True, **samp.BOOST_X2)
    assert runner.hand_floorplan("samp", bootstrap).name == "samp_bootstrap.json"
    assert runner.hand_floorplan("samp", SampParams(switch_type=SwitchType.PMOS)) is None
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


def test_the_sweep_targets_call_the_library_on_every_block(monkeypatch) -> None:
    from flow.comp import targets as comp
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
    calls.clear()
    comp.sweep()  # one block: a fresh run, laid out, tabulated
    assert calls == [("run", ["comp"], 36, {}), ("layout", ["comp"], 28), ("table", ["comp"], 16)]


def test_a_lookup_without_simulation_never_waits_on_a_lock(tmp_path: Path, monkeypatch) -> None:
    import fcntl
    import hashlib

    from flow.sweep import lookup

    monkeypatch.setattr(lookup, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(lookup, "_sweep_record", lambda block, pdk, ident: None)
    params = CompParams()
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
