"""The shared layout step's runner: a design laid out and signed off in one PDK, and in every PDK."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from klayout import db

from flow.layout import step
from flow.layout.signoff import RowSignoff


def _gds(path: Path) -> Path:
    layout_ = db.Layout()
    layout_.dbu = 0.001
    layout_.create_cell("TOP").shapes(layout_.layer(1, 0)).insert(db.Box(0, 0, 2000, 1000))
    path.parent.mkdir(parents=True, exist_ok=True)
    layout_.write(str(path))
    return path


def test_a_layout_records_its_cell_and_signoff_and_a_failure_its_drc(tmp_path: Path, monkeypatch) -> None:
    """ALIGN's layout of a design in one PDK: its GDS, size, signoff, extraction and each step's
    seconds in the summary; a failed one (as after DRC ran) its error and the violations DRC found, in
    ``failures.json``."""

    monkeypatch.setattr(step, "pdk_router", lambda pdk: "astar")
    monkeypatch.setattr(
        step, "build_design", lambda pdk, design, cells, out, placed, seed=0, router=None: _gds(out / "align.gds")
    )
    monkeypatch.setattr(
        step,
        "signoff",
        lambda pdk, gds, source, run_dir, checker: RowSignoff(run_dir / "r.json", 0, run_dir, True, 1.5, 2.5),
    )
    monkeypatch.setattr(step, "extracted", lambda pdk, gds, name, run_dir: {"nets": {"a": 1e-15}, "total_f": 1e-15})
    design, source = tmp_path / "input" / "inv", tmp_path / "inv.cdl"
    step.signed_off_design(tmp_path / "ok", "tsmc65", "inv", design, [], source, True, {"netlist": 0.2})
    entry = json.loads((tmp_path / "ok" / "summary.json").read_text())["tsmc65/align"]
    seconds = entry.pop("seconds")
    assert entry == {
        "gds": str(tmp_path / "ok" / "align" / "align.gds"),
        "cell_um": [2.0, 1.0],
        "router": "astar",
        "drc_violations": 0,
        "lvs_correct": True,
        "pex": {"nets": {"a": 1e-15}, "total_f": 1e-15},
    }
    assert set(seconds) == {"netlist", "layout", "drc", "lvs", "pex"}
    assert (seconds["netlist"], seconds["drc"], seconds["lvs"]) == (0.2, 1.5, 2.5)

    def broken(pdk, design, cells, out, placed, seed=0, router=None):
        report = out / "signoff" / "drc_violations.json"  # as if DRC ran before the failure
        report.parent.mkdir(parents=True)
        report.write_text('{"violations": {"spacing": 3}}')
        raise RuntimeError("router gave up")

    monkeypatch.setattr(step, "build_design", broken)
    with pytest.raises(RuntimeError, match="1 layouts failed"):
        step.signed_off_design(tmp_path / "bad", "tsmc65", "inv", design, [], source, True)
    # a layout that does not match its netlist (by either router) is not extracted
    monkeypatch.setattr(
        step, "build_design", lambda pdk, design, cells, out, placed, seed=0, router=None: _gds(out / "align.gds")
    )
    monkeypatch.setattr(
        step,
        "signoff",
        lambda pdk, gds, source, run_dir, checker: RowSignoff(run_dir / "r.json", 0, run_dir, False, 1.5, 2.5),
    )
    with pytest.raises(RuntimeError, match="1 layouts failed"):
        step.signed_off_design(tmp_path / "open", "tsmc65", "inv", design, [], source, True)
    assert json.loads((tmp_path / "open" / "summary.json").read_text())["tsmc65/align"]["pex"] == {
        "skipped": "LVS did not match"
    }
    assert json.loads((tmp_path / "bad" / "summary.json").read_text())["tsmc65/align"]["drc_violations"] == 3
    assert "router gave up" in json.loads((tmp_path / "bad" / "failures.json").read_text())["tsmc65/align"]


def test_a_layout_not_matching_is_routed_again_by_the_other_router(tmp_path: Path, monkeypatch) -> None:
    """Where LVS does not match the PDK's router's layout, ALIGN's other router lays it out again
    (``align_<router>/``), and its layout is kept where its LVS matches: the summary names it."""

    monkeypatch.setattr(step, "pdk_router", lambda pdk: "astar")
    routers = []

    def build(pdk, design, cells, out, placed, seed=0, router=None):
        routers.append(router)
        return _gds(out / "inv" / "inv.gds")

    monkeypatch.setattr(step, "build_design", build)
    # the first router's layout does not match, the other's does
    monkeypatch.setattr(
        step,
        "signoff",
        lambda pdk, gds, source, run_dir, checker: RowSignoff(
            run_dir / "r.json", 0, run_dir, "align_hanan" in str(gds), 1.5, 2.5
        ),
    )
    monkeypatch.setattr(step, "extracted", lambda pdk, gds, name, run_dir: {"total_f": 1e-15, "at": str(run_dir)})
    design, source = tmp_path / "input" / "inv", tmp_path / "inv.cdl"
    step.signed_off_design(tmp_path / "run", "tsmc65", "inv", design, [], source, True)
    entry = json.loads((tmp_path / "run" / "summary.json").read_text())["tsmc65/align"]
    assert routers == ["astar", "hanan"]
    assert entry["router"] == "hanan" and entry["lvs_correct"] is True
    assert entry["gds"] == str(tmp_path / "run" / "align_hanan" / "inv" / "inv.gds")
    assert entry["pex"]["at"] == str(tmp_path / "run" / "align_hanan" / "pex")
    assert "layout_hanan" in entry["seconds"]


def test_all_pdks_merges_summaries_and_failures(tmp_path: Path) -> None:
    def case(run_dir: Path, pdk: str, name: str) -> Path:
        run_dir.mkdir()
        if pdk == "ihp130":
            return step.finish(run_dir, {f"{pdk}/{name}": {"error": "x"}}, {f"{pdk}/{name}": "x"})
        return step.finish(run_dir, {f"{pdk}/{name}": {"drc_violations": 0}}, {})

    with pytest.raises(RuntimeError, match="1 layouts failed"):
        step.all_pdks(tmp_path, case, "align")
    assert set(json.loads((tmp_path / "summary.json").read_text())) == {f"{pdk}/align" for pdk in step.PDKS}
    assert json.loads((tmp_path / "failures.json").read_text()) == {"ihp130/align": "x"}


def test_a_layout_the_first_router_cannot_draw_is_drawn_by_the_other(tmp_path: Path, monkeypatch) -> None:
    """Where ALIGN fails (or stops) with the PDK's router, the other router lays the design out; where
    both fail, the first router's failure is the layout's."""

    monkeypatch.setattr(step, "pdk_router", lambda pdk: "astar")

    def build(pdk, design, cells, out, placed, seed=0, router=None):
        if router == "astar":
            raise RuntimeError("ALIGN stopped after 1800 s")
        return _gds(out / "inv" / "inv.gds")

    monkeypatch.setattr(step, "build_design", build)
    monkeypatch.setattr(
        step,
        "signoff",
        lambda pdk, gds, source, run_dir, checker: RowSignoff(run_dir / "r.json", 0, run_dir, True, 1.5, 2.5),
    )
    design, source = tmp_path / "input" / "inv", tmp_path / "inv.cdl"
    step.signed_off_design(tmp_path / "run", "tsmc65", "inv", design, [], source, True, pex=False)
    entry = json.loads((tmp_path / "run" / "summary.json").read_text())["tsmc65/align"]
    assert entry["router"] == "hanan" and entry["lvs_correct"] is True
    assert entry["gds"] == str(tmp_path / "run" / "align_hanan" / "inv" / "inv.gds")

    def neither(pdk, design, cells, out, placed, seed=0, router=None):
        raise RuntimeError(f"{router} gave up")

    monkeypatch.setattr(step, "build_design", neither)
    (tmp_path / "none").mkdir()  # the step's netlists are there before ALIGN runs
    with pytest.raises(RuntimeError, match="1 layouts failed"):
        step.signed_off_design(tmp_path / "none", "tsmc65", "inv", design, [], source, True, pex=False)
    assert "astar gave up" in json.loads((tmp_path / "none" / "failures.json").read_text())["tsmc65/align"]


def test_a_layout_with_drc_violations_is_routed_again_and_the_cleaner_one_kept(tmp_path: Path, monkeypatch) -> None:
    """A layout matching LVS but with DRC violations is laid out by the other router too, and the
    one with fewer violations (its LVS matching) kept."""

    monkeypatch.setattr(step, "pdk_router", lambda pdk: "astar")
    monkeypatch.setattr(
        step, "build_design", lambda pdk, design, cells, out, placed, seed=0, router=None: _gds(out / "inv" / "inv.gds")
    )
    monkeypatch.setattr(
        step,
        "signoff",
        lambda pdk, gds, source, run_dir, checker: RowSignoff(
            run_dir / "r.json", 0 if "align_hanan" in str(gds) else 4, run_dir, True, 1.5, 2.5
        ),
    )
    design, source = tmp_path / "input" / "inv", tmp_path / "inv.cdl"
    step.signed_off_design(tmp_path / "run", "tsmc65", "inv", design, [], source, True, pex=False)
    entry = json.loads((tmp_path / "run" / "summary.json").read_text())["tsmc65/align"]
    assert (entry["router"], entry["drc_violations"], entry["lvs_correct"]) == ("hanan", 0, True)
