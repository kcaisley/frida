"""An instance's story as the viewer tells it (``flow.web.export``): its netlist's statistics, each
step's state from its ``step.json``, its waves by the step that simulated them, a table's topology,
and the server's step logs."""

import json
from pathlib import Path

import pytest

from flow.web import export, server

NETLIST = """\
* a made-up block
.subckt inv A Y VDD VSS
mn Y A VSS VSS nmos_x w=240n l=60n nf=1
mp Y A VDD VDD pmos_x w=240n l=60n nf=1
.ends inv
.subckt top IN OUT VDD VSS
Xa IN mid VDD VSS inv
Xb mid OUT VDD VSS inv
Xc OUT VSS cap_cell length=4230
C1 OUT VSS 1f
.ends top
"""


def test_netlist_stats():
    stats = export.netlist_stats(NETLIST)
    assert stats["top"] == "top"
    assert (stats["ports"], stats["instances"], stats["subcircuits"]) == (4, 4, 2)
    assert stats["nets"] == 5  # in, out, mid, vdd, vss
    assert stats["leaves"] == {"MOS nmos_x": 2, "MOS pmos_x": 2, "capacitor": 1, "cell cap_cell": 1}


def _mark(folder: Path, step: str, finished: float, seconds: float, error=None, **outputs) -> None:
    (folder / step).mkdir(parents=True, exist_ok=True)
    entry = {"step": step, "finished": finished, "seconds": seconds, "error": error, "log": {}, **outputs}
    (folder / step / "step.json").write_text(json.dumps(entry))


def test_each_step_has_its_state(tmp_path: Path):
    """A step the bounds rejected the design after is rejected (the steps after it not run, but the
    record), a failure leaves the steps that need it not run, and a run without steps has its
    record's story alone."""
    rejected = {"step": "presim", "evidence": "prelayout", "bounds": {"delay_s": [2e-9, 1e-9]}}
    _mark(tmp_path, "netlist", 1000.0, 0.5)
    _mark(tmp_path, "presim", 1010.0, 9.0, runs=["a", "b"])
    _mark(tmp_path, "results", 5000.0, 0.5, evidence="prelayout", rejected=rejected)
    (tmp_path / "netlist" / "toy.cdl").write_text(NETLIST)
    steps = {step["step"]: step for step in export.steps_view(tmp_path, {"rejected": rejected}, root=tmp_path) or []}
    assert [steps[key]["state"] for key in ("netlist", "presim", "layout", "postsim", "results")] == [
        "ok",
        "rejected",
        "not run",
        "not run",
        "ok",
    ]
    assert steps["layout"]["why"] == "rejected at presim" and steps["presim"]["rejected"] == rejected
    assert steps["presim"]["outputs"] == {"runs": ["a", "b"]} and steps["netlist"]["netlist"]["top"] == "top"
    # a layout that failed: what needs it is not run, the record (which does without) ran
    failed = tmp_path / "failed"
    _mark(failed, "netlist", 1000.0, 0.5)
    _mark(failed, "layout", 1004.0, 3.0, error="Traceback ...\nValueError: no room")
    _mark(failed, "results", 1005.0, 0.5)
    steps = {step["step"]: step for step in export.steps_view(failed, {}, root=tmp_path) or []}
    assert steps["layout"]["state"] == "failed" and steps["layout"]["error"].endswith("no room")
    assert (steps["drc"]["state"], steps["drc"]["why"]) == ("not run", "after layout failed")
    assert steps["netlist"]["state"] == steps["results"]["state"] == "ok"
    assert export.steps_view(tmp_path / "none", {}, root=tmp_path) is None


def test_waves_by_the_step_that_simulated_them(tmp_path: Path):
    post = "build/b/r/tsmc65/x/postsim/vin_1/result.h5"
    (tmp_path / "build/b/r/tsmc65/x/presim/vin_1").mkdir(parents=True)
    (tmp_path / "build/b/r/tsmc65/x/presim/vin_1/result.h5").write_text("")
    kinds = export.wave_kinds({"low": post, "gone": "build/b/r/tsmc65/x/postsim/vin_2/result.h5"}, tmp_path)
    assert kinds["postsim"] == {"low": post, "gone": "build/b/r/tsmc65/x/postsim/vin_2/result.h5"}
    assert kinds["sim"] == {"low": "build/b/r/tsmc65/x/presim/vin_1/result.h5"}  # the twin kept alone
    assert export.wave_kinds({"low": "build/b/r/tsmc65/x/presim/vin_1/result.h5"}, tmp_path)["postsim"] == {}


def test_a_tables_topology():
    rows = [{"params": {"latch": "STRONGARM", "w": 1}}, {"params": {"latch": "DOUBLE_TAIL", "w": 2}}]
    assert export.topology("comp", rows, ["latch", "w"]) == "latch"
    assert export.topology("comp", rows, ["w"]) is None  # the same everywhere
    assert export.topology("toy", rows, ["w", "latch"]) == "latch"  # its first enumeration's


def test_the_server_serves_a_steps_log_alone(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(server, "BUILD_DIR", tmp_path / "build")
    log = tmp_path / "build/b/r/tsmc65/x/layout/step.log"
    log.parent.mkdir(parents=True)
    log.write_text("one\ntwo\n")
    assert server.log_body("build/b/r/tsmc65/x/layout/step.log") == b"one\ntwo\n"
    (tmp_path / "secret.log").write_text("no")
    for path in ("secret.log", "build/../secret.log", "build/b/r/tsmc65/x/layout/step.json"):
        with pytest.raises(ValueError):
            server.log_body(path)


def test_drcs_markers_by_rule(tmp_path: Path):
    """DRC's markers read from a KLayout marker database, by rule: its count, description and boxes
    (µm), a rule's boxes capped."""
    from klayout import db, rdb

    report = rdb.ReportDatabase("drc")
    top = report.create_cell("TOP")
    rule = report.create_category("M1_a")
    rule.description = "Minimum width"
    for k in range(export.MAX_MARKERS + 5):
        item = report.create_item(top.rdb_id(), rule.rdb_id())
        item.add_value(db.DBox(k, 0, k + 0.5, 0.25))
    report.save(str(tmp_path / "gdscheck.core.lyrdb"))
    markers = export.drc_markers(tmp_path, "TOP")
    assert list(markers) == ["M1_a"] and markers["M1_a"]["count"] == export.MAX_MARKERS + 5
    assert markers["M1_a"]["description"] == "Minimum width" and len(markers["M1_a"]["boxes"]) == export.MAX_MARKERS
    assert markers["M1_a"]["boxes"][1] == [1.0, 0.0, 1.5, 0.25]
    assert export.drc_markers(tmp_path / "none", "TOP") == {}
