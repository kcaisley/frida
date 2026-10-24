"""Software-only tests for the comparator layout runner."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from klayout import db

from flow import pipeline
from flow.layout.signoff import RowSignoff

from . import layout, sweep


def test_a_named_instance_is_laid_out_by_its_floorplan_or_alignss(tmp_path: Path, monkeypatch) -> None:
    """``python -m flow layout comp --instance NAME [--auto]``: every named instance of the sweep has a
    hand-written floorplan; the three tools in each PDK asked for, from it or from ALIGN's."""
    public = {
        name
        for name, value in vars(layout).items()
        if inspect.isfunction(value) and value.__module__ == layout.__name__ and not name.startswith("_")
    }
    # the named instances' layout, and the hooks the sweep's layout runner calls (flow.sweep.runner.layout_hooks)
    assert public == {"layout_named", "write_netlist", "layout_netlist", "layout_floorplan"}
    named = pipeline.names(sweep)
    assert set(named) == {
        "frida1",
        "c040",
        "strongarm",
        "double_tail",
        "triple_tail",
        "double_tail_self_timed",
        "double_tail_modified",
        "double_tail_modified_self_timed",
    }
    assert all((layout.FLOORPLANS / f"comp_{name}.json").exists() for name in named)
    calls = []
    monkeypatch.setattr(layout, "_comp", lambda run_dir, pdk, *args: calls.append((pdk, *args)) or run_dir)
    monkeypatch.setattr(layout, "_finish", lambda run_dir, summary, failures: run_dir)
    layout.layout_named(tmp_path, "c040", named["c040"](), pdks=("tsmc65", "ihp130"))
    layout.layout_named(tmp_path, "c040", named["c040"](), auto=True, pdks=("tsmc65",))
    assert [(pdk, name, floorplan.name if floorplan else None) for pdk, name, _params, floorplan in calls] == [
        ("tsmc65", "comp_c040", "comp_c040.json"),
        ("ihp130", "comp_c040", "comp_c040.json"),
        ("tsmc65", "comp_c040", None),
    ]
    with pytest.raises(FileNotFoundError, match="no hand-written floorplan"):
        layout.layout_named(tmp_path, "dynamic", sweep.dynamic_bias(ratio=3.5, k=2))


def test_c040_is_the_retired_size_sweeps_topology_40_at_half_size() -> None:
    assert sweep.c040().diffpair_w == 19 and sweep.c040().latch_init_l == 17


def _gds(path: Path) -> Path:
    layout_ = db.Layout()
    layout_.dbu = 0.001
    layout_.create_cell("TOP").shapes(layout_.layer(1, 0)).insert(db.Box(0, 0, 2000, 1000))
    path.parent.mkdir(parents=True, exist_ok=True)
    layout_.write(str(path))
    return path


def test_one_failing_tool_does_not_stop_the_others(tmp_path: Path, monkeypatch) -> None:
    def broken(pdk, fp, netlist, out):
        report = out / "signoff" / "drc_violations.json"  # as if DRC ran before the failure
        report.parent.mkdir(parents=True)
        report.write_text('{"violations": {"spacing": 3}}')
        raise RuntimeError("router gave up")

    builds = {
        "cic": lambda pdk, fp, netlist, out: _gds(out / "cic.gds"),
        "laygo": broken,
        "align": lambda pdk, fp, netlist, out, name=None: _gds(out / "align.gds"),
    }
    monkeypatch.setattr(layout, "BUILD", builds)

    def signoff(pdk, gds, netlist, floorplan, run_dir):
        report = run_dir / "drc_violations.json"
        return RowSignoff(report, 2 if gds.name == "align.gds" else 0, report, True)

    monkeypatch.setattr(layout, "row_signoff", signoff)
    with pytest.raises(RuntimeError, match="2 layouts failed"):
        layout._run(tmp_path, "tsmc65", "mos_inv", tmp_path / "n.sp", tmp_path / "fp.json")
    summary = json.loads((tmp_path / "summary.json").read_text())
    failures = json.loads((tmp_path / "failures.json").read_text())
    assert summary["tsmc65/cic"] == {
        "gds": str(tmp_path / "cic" / "cic.gds"),
        "cell_um": [2.0, 1.0],
        "drc_violations": 0,
        "lvs_correct": True,
    }
    assert summary["tsmc65/laygo"]["drc_violations"] == 3
    assert set(failures) == {"tsmc65/laygo", "tsmc65/align"}
    assert "router gave up" in failures["tsmc65/laygo"] and failures["tsmc65/align"].startswith("DRC 2 violations")


def test_all_pdks_merges_summaries_and_failures(tmp_path: Path) -> None:
    def case(run_dir: Path, pdk: str, name: str) -> Path:
        run_dir.mkdir()
        if pdk == "ihp130":
            return layout._finish(run_dir, {f"{pdk}/{name}": {"error": "x"}}, {f"{pdk}/{name}": "x"})
        return layout._finish(run_dir, {f"{pdk}/{name}": {"drc_violations": 0}}, {})

    with pytest.raises(RuntimeError, match="1 layouts failed"):
        layout._all_pdks(tmp_path, case, "cic")
    assert set(json.loads((tmp_path / "summary.json").read_text())) == {f"{pdk}/cic" for pdk in layout.PDKS}
    assert json.loads((tmp_path / "failures.json").read_text()) == {"ihp130/cic": "x"}
