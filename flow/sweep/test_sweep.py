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
        sweep = __import__(f"flow.{block}.sweep", fromlist=["params"])
        # four to eight sizings, ten where a block also brackets a fabricated design (comp: FRIDA-1);
        # the converters' sizings are their capacitor arrays, a redundancy scheme each
        most = 30 if block.startswith("adc") else 10
        assert sweep.TOPOLOGIES and 4 <= len(sweep.SIZINGS) <= most, block
        assert callable(sweep.characterize) and sweep.GENERATOR is not None, block
        combos = [
            sweep.params(pdk, topology, sizing)
            for pdk in runner.PDKS
            for topology in sweep.TOPOLOGIES
            for sizing in sweep.SIZINGS
        ]
        assert any(combo is not None for combo in combos), block


def test_the_table_has_a_row_per_instance_and_a_file_each(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "sweep/toy/20261020_000000"
    for pdk, sizing, delay in (("tsmc65", "x1", 1e-10), ("ihp130", "x2", 3e-10)):
        path = run / pdk / "inv" / sizing / "instance.json"
        path.parent.mkdir(parents=True)
        record = {
            "block": "toy",
            "pdk": pdk,
            "topology": "inv",
            "sizing": sizing,
            "params": {"w": 1 if sizing == "x1" else 2, "kind": "inv"},
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
    runner.table(["toy"], 1)
    data = json.loads((tmp_path / "web/data/sweep/toy.json").read_text())
    assert [row["id"] for row in data["rows"]] == ["ihp130__inv__x2", "tsmc65__inv__x1"]
    assert data["params"] == ["w"]  # the kind is the same everywhere
    assert "details" not in data  # each plot is scaled to its own data
    instance = json.loads((tmp_path / "web/data/sweep/toy/tsmc65__inv__x1.json").read_text())
    assert instance["params"] == {"w": 1, "kind": "inv"} and instance["details"][0]["series"]["delay"][1] is None
    assert json.loads((tmp_path / "web/data/sweep/catalog.json").read_text())["toy"]["instances"] == 2


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
