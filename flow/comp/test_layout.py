"""Software-only tests for the comparator layout runner."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from klayout import db

from flow.comp import layout
from flow.layout.signoff import RowSignoff

CASES = (
    "comp_frida1_manual",
    "comp_c040_manual",
    "comp_strongarm",
    "comp_triple_tail",
    "comp_double_tail",
    "comp_double_tail_self_timed",
    "comp_double_tail_modified",
    "comp_double_tail_modified_self_timed",
    "comp_frida1_auto",
    "comp_c040_auto",
    "mos_inv",
)


def test_main_registers_every_target() -> None:
    tree = ast.parse(Path(layout.__file__).read_text())
    public = {node.name for node in tree.body if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")}
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    registry = next(node for node in main.body if isinstance(node, ast.Assign))
    assert isinstance(registry.value, ast.DictComp)
    entries = registry.value.generators[0].iter
    assert isinstance(entries, ast.Tuple)
    listed = {ast.unparse(node) for node in entries.elts}
    targets = (listed - {"*ALL_PDKS"}) | {target.__name__ for target in layout.ALL_PDKS}
    per_pdk = {f"{case}_{pdk}" for case in CASES for pdk in layout.PDKS}
    assert targets == public - {"main"}
    assert targets == per_pdk | {f"{case}_all_pdks" for case in CASES} | {"all_comp_layouts"}
    assert len(per_pdk) == 66 and len(targets) == 78


def test_c040_is_the_sweeps_topology_40_at_half_size() -> None:
    assert layout.C040.diffpair_w == 19 and layout.C040.latch_init_l == 17


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
    def case_tsmc65(run_dir: Path) -> Path:
        run_dir.mkdir()
        return layout._finish(run_dir, {"tsmc65/cic": {"drc_violations": 0}}, {})

    def case_ihp130(run_dir: Path) -> Path:
        run_dir.mkdir()
        return layout._finish(run_dir, {"ihp130/cic": {"error": "x"}}, {"ihp130/cic": "x"})

    with pytest.raises(RuntimeError, match="1 layouts failed"):
        layout._all_pdks(tmp_path, (case_tsmc65, case_ihp130))
    assert set(json.loads((tmp_path / "summary.json").read_text())) == {"tsmc65/cic", "ihp130/cic"}
    assert json.loads((tmp_path / "failures.json").read_text()) == {"ihp130/cic": "x"}
