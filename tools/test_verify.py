"""tools/verify.py's records and its comparison with a baseline, on synthetic records."""

import json
import math

import pytest
import verify
from verify import Change, Kind


def test_a_records_numbers_are_its_metrics_and_prelayout_metrics_by_dotted_name(tmp_path) -> None:
    """Nested values flattened, a number not measured kept as None, strings and the record's other
    parts (its parameters, its figures) left out; a failure's last line as ``error``; each instance
    of a run's folder by ``<pdk>/<name>``, the postsim step's own record not among them."""
    record = {
        "params": {"w": 2},
        "metrics": {"delay_s": 1e-10, "noise_v": None, "ok": True, "codes": [3, 4], "label": "x"},
        "prelayout": {"delay_s": 9e-11},
        "details": [{"name": "figure", "x": [1, 2]}],
        "error": None,
    }
    assert verify.numbers(record) == {
        "metrics.delay_s": 1e-10,
        "metrics.noise_v": None,
        "metrics.ok": True,
        "metrics.codes.0": 3,
        "metrics.codes.1": 4,
        "prelayout.delay_s": 9e-11,
    }
    assert verify.numbers({"error": "Traceback\n  ...\nValueError: no decision"}) == {
        "error": "ValueError: no decision"
    }
    for pdk, name in (("tsmc65", "frida1"), ("ihp130", "frida1")):
        (tmp_path / pdk / name / "postsim").mkdir(parents=True)
        (tmp_path / pdk / name / "instance.json").write_text(json.dumps({"metrics": {"a": 1.0}}))
        (tmp_path / pdk / name / "postsim" / "instance.json").write_text(json.dumps({"metrics": {"b": 2.0}}))
    assert verify.collect(tmp_path) == {"ihp130/frida1": {"metrics.a": 1.0}, "tsmc65/frida1": {"metrics.a": 1.0}}


def test_numbers_differ_beyond_the_relative_tolerance_of_the_larger() -> None:
    """Within rtol of the larger magnitude a number is unchanged; past it, or a sign's flip, or one
    side not measured (None), changed; NaN equals NaN alone, an infinity the same one alone; flags and errors compare as they are."""
    assert not verify.differs(1.0, 1.0 + 0.9e-6, 1e-6)
    assert verify.differs(1.0, 1.0 + 1.1e-6, 1e-6)
    assert not verify.differs(-2e-15, -2e-15 * (1 + 1e-7), 1e-6)
    assert verify.differs(1e-3, -1e-3, 1e-6)
    assert verify.differs(0.0, 1e-30, 1e-6) and not verify.differs(0.0, 0.0, 1e-6)
    assert verify.differs(None, 1.0, 1e-6) and not verify.differs(None, None, 1e-6)
    assert not verify.differs(math.nan, math.nan, 1e-6) and verify.differs(math.nan, 1.0, 1e-6)
    assert verify.differs(1.0, math.inf, 1e-6) and verify.differs(math.inf, -math.inf, 1e-6)
    assert verify.differs(-1.0, -math.inf, 1e-6) and not verify.differs(math.inf, math.inf, 1e-6)
    assert verify.differs(True, 1, 1e-6) and not verify.differs(True, True, 1e-6)
    assert verify.differs(3, 4, 1e-6) and not verify.differs(3, 3.0, 1e-6)


def test_the_changes_from_a_baseline_name_every_number_and_instance_that_moved() -> None:
    """A changed number with its relative change, one beyond a looser tolerance alone, a number
    added and one removed, an instance added and one removed; unchanged numbers counted as
    compared and not listed."""
    baseline = {
        "tsmc65/frida1": {"metrics.delay_s": 1.0e-10, "metrics.noise_v": 2.0e-4, "metrics.gone": 1.0, "metrics.n": 3},
        "tsmc65/old": {"metrics.delay_s": 1.0},
    }
    current = {
        "tsmc65/frida1": {"metrics.delay_s": 1.1e-10, "metrics.noise_v": 2.0e-4 * (1 + 1e-4), "metrics.new": None},
        "ihp130/frida1": {"metrics.delay_s": 2.0},
    }
    current["tsmc65/frida1"]["metrics.n"] = 3
    found, compared = verify.changes(baseline, current, 1e-6)
    assert compared == 3
    assert found == [
        Change("ihp130/frida1", None, Kind.ADDED),
        Change("tsmc65/frida1", "metrics.delay_s", Kind.CHANGED, 1.0e-10, 1.1e-10),
        Change("tsmc65/frida1", "metrics.gone", Kind.REMOVED, before=1.0),
        Change("tsmc65/frida1", "metrics.new", Kind.ADDED, after=None),
        Change("tsmc65/frida1", "metrics.noise_v", Kind.CHANGED, 2.0e-4, pytest.approx(2.0e-4 * (1 + 1e-4))),
        Change("tsmc65/old", None, Kind.REMOVED),
    ]
    loose, _ = verify.changes(baseline, current, 1e-3)
    assert "metrics.noise_v" not in {change.name for change in loose}
    assert verify.changes(baseline, baseline, 1e-6) == ([], 5)
    lines = verify.report(found, compared, 1e-6).splitlines()
    assert lines[0] == "ihp130/frida1: added"
    assert lines[1] == "tsmc65/frida1 metrics.delay_s: 1e-10 -> 1.1e-10 (+10.000%)"
    assert lines[2] == "tsmc65/frida1 metrics.gone: removed (was 1)"
    assert lines[3] == "tsmc65/frida1 metrics.new: added None"
    assert lines[5] == "tsmc65/old: removed"
    assert lines[-1] == "4 numbers changed beyond rtol 1e-06 (3 compared)"


def test_a_run_is_collected_from_the_folder_its_own_steps_chose(monkeypatch, tmp_path) -> None:
    """The folder the command line's steps worked in is the one collected, though another session's
    run of the same block and run is newer by name; a failure of the steps is returned with it."""
    import flow.__main__ as cli
    from flow.sweep import runner

    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)
    mine, theirs = tmp_path / "comp" / "frida1" / "20261118_100000", tmp_path / "comp" / "frida1" / "20261118_100001"
    for folder in (mine, theirs):
        folder.mkdir(parents=True)
        (folder / "run.json").write_text("{}")
    monkeypatch.setattr(cli, "_run_dir", lambda block, run, start: (mine, "new"))

    def steps(argv: list[str]) -> None:
        cli._run_dir("comp", "frida1", None)
        raise SystemExit("1 of 2 instances failed")

    monkeypatch.setattr(cli, "main", steps)
    assert verify.run("comp", "frida1", "netlist", None) == (mine, "1 of 2 instances failed")
    assert cli._run_dir("comp", "frida1", None) == (mine, "new")
