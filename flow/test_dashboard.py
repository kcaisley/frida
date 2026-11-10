"""The run's dashboard (``flow.dashboard``): its model of a run from the workers' events, and what
it draws of it, live or as plain text into the run's ``status.txt`` and ``events.log``."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from flow import dashboard
from flow.dashboard import Board, View


def _board(tmp_path: Path, names: list[str]) -> Board:
    board = Board("comp", "grid1", "grid", ("tsmc65",), 4, tmp_path, ("netlist", "sim", "layout", "record"))
    for name in names:
        (tmp_path / name).mkdir(parents=True)
        board.add(f"tsmc65/{name}", tmp_path / name, ["delay_s"])
    return board


def _shown(found) -> str:
    console = Console(width=200, height=56, color_system=None, record=True, file=open("/dev/null", "w"))  # noqa: SIM115
    console.print(found)
    return console.export_text()


def test_the_board_counts_each_steps_instances_and_says_what_needs_attention(tmp_path: Path) -> None:
    """Events in: a step running, ended, kept, rejected, failed; each step's instances by state, each
    failure said with its log, a bound's rejections said once and counted, a step log's kind of
    warning said the first time."""
    board = _board(tmp_path, ["a", "b", "c"])
    (tmp_path / "a" / "sim").mkdir()
    (tmp_path / "a" / "sim" / "step.log").write_text(
        "2026-11-10 00:00:00 spectre WARNING : WARNING (SFE-106): parameter 3 ignored\n"
        "2026-11-10 00:00:01 spectre INFO : tran done\n"
    )
    for key in ("a", "b", "c"):
        board.take(
            {"key": f"tsmc65/{key}", "step": "netlist", "state": "done", "seconds": 0.5, "found": "", "counts": {}}
        )
    board.take({"key": "tsmc65/a", "step": "sim", "state": "running"})
    assert board.by_step("sim")["running"] == 1 and board.by_step("sim")["waiting"] == 2
    board.take(
        {
            "key": "tsmc65/a",
            "step": "sim",
            "state": "ok",
            "seconds": 30.0,
            "found": "14 runs",
            "counts": {"spectre": {"WARNING": 1}},
        }
    )
    why = "rejected at sim (prelayout): delay_s 2.1e-09 > 2e-09"
    for key in ("b", "c"):
        board.take(
            {"key": f"tsmc65/{key}", "step": "sim", "state": "rejected", "seconds": None, "found": why, "counts": {}}
        )
    board.take(
        {
            "key": "tsmc65/a",
            "step": "layout",
            "state": "failed",
            "seconds": 4.0,
            "found": "align: no route",
            "counts": {},
        }
    )
    for key, states in (("a", ["done", "ok", "failed"]), ("b", ["done", "rejected"]), ("c", ["done", "rejected"])):
        board.end(f"tsmc65/{key}", states)
    assert board.by_step("netlist")["done"] == 3 and board.by_step("sim")["rejected"] == 2
    assert board.ended() == {"failed": 1, "rejected": 2}
    assert board.rejections == {("sim", "delay_s"): 2}
    levels = [notice for _, notice, *_ in board.attention]
    assert levels == ["WARNING", "REJECTED", "FAILED"]  # the rejection once, its kind counted
    text = _shown(dashboard.dashboard(board))
    assert "comp grid1  grid · 3 designs" in text and "0 passed   2 rejected   1 failed" in text
    # each box stacked, in order
    titles = ["─ run ─", "─ pipeline ─", "─ logging ─", "─ results "]
    assert all(title in text for title in titles) and sorted(titles, key=text.index) == titles
    # a row a notice: time, notice, step, tool, count, the message without its level word
    rows = [line for line in text.splitlines() if "SFE-106: parameter 3 ignored" in line]
    assert rows and "warning" in rows[0] and " sim " in rows[0] and " spectre " in rows[0] and "WARNING" not in rows[0]
    assert any("rejected" in line and "sim" in line and " 2 " in line for line in text.splitlines())
    assert "align: no route" in text and "delay_s" in text
    # the results a column each design that ended: the step and bound that stopped it, or its failure
    results = _shown(dashboard.results_panel(board))
    assert results.count("rejected at sim: delay_s") == 2
    assert "failed at layout" in results
    assert "status:" in dashboard.status_line(board) and "2 by delay_s at sim" in dashboard.status_line(board)


def test_one_instance_shows_its_metrics_pre_and_post_layout(tmp_path: Path) -> None:
    board = _board(tmp_path, ["a"])
    record = {
        "evidence": "postlayout",
        "metrics": {"delay_s": 1.2e-9, "ok": True},
        "prelayout": {"delay_s": 1e-9, "ok": True},
    }
    (tmp_path / "a" / "instance.json").write_text(json.dumps(record))
    board.take({"key": "tsmc65/a", "step": "record", "state": "ok", "seconds": 1.0, "found": "", "counts": {}})
    text = _shown(dashboard.dashboard(board))
    assert "results · tsmc65/a · postlayout" in text and "1 ns" in text and "1.2 ns" in text and "+20.0%" in text


def test_a_metric_is_shown_in_its_unit() -> None:
    assert dashboard.value("delay_0p5mv_s", 2.1e-9) == "2.1 ns"
    assert dashboard.value("energy_j", 6.2e-13) == "620 fJ"
    assert dashboard.value("layout_area_um2", 277.0) == "277 µm²"
    assert dashboard.value("droop_v_s", -0.5) == "-500 mV/s" and dashboard.value("delay_s", 2e-9) == "2 ns"
    assert dashboard.value("decides_in_time", True) == "yes" and dashboard.value("x", None) == "–"


def test_the_view_writes_the_status_and_events_beside_the_run(tmp_path: Path, capsys) -> None:
    """Not a terminal: a small run's step lines are the step runner's own (``line``); the summary at the
    end; ``status.txt`` the dashboard as plain text, ``events.log`` each line that needs attention."""
    board = _board(tmp_path, ["a"])
    lines = []
    with View(board, lines.append) as view:
        view.take({"key": "tsmc65/a", "step": "sim", "state": "failed", "seconds": 1.0, "found": "boom", "counts": {}})
        view.refresh()
    assert [event["state"] for event in lines] == ["failed"]
    assert "comp grid1" in (tmp_path / "status.txt").read_text()
    assert "FAILED sim tsmc65/a: boom" in (tmp_path / "events.log").read_text()
    out = capsys.readouterr().out
    assert "logging" in out and "viewer  http://localhost:8765/#block=comp&run=grid1/" in out


def test_a_known_warning_keeps_its_level_and_its_reason_is_a_note(tmp_path: Path) -> None:
    board = _board(tmp_path, ["a"])
    (tmp_path / "a" / "sim").mkdir()
    (tmp_path / "a" / "sim" / "step.log").write_text(
        "2026-11-10 00:00:00 spectre WARNING : WARNING (SPECTRE-592): Following parameters are disabled\n"
    )
    board.take(
        {
            "key": "tsmc65/a",
            "step": "sim",
            "state": "ok",
            "seconds": 1.0,
            "found": "",
            "counts": {"spectre": {"KNOWN": 1}},
        }
    )
    [row] = board.attention
    # the notice the tool's own level, the message the tool's alone, why it is left in the notes
    assert row.notice == "WARNING" and row.known and row.instance == "tsmc65/a"
    assert row.text == "SPECTRE-592: Following parameters are disabled" and row.note.startswith("the foundry")
    shown = _shown(dashboard.logging_panel(board))
    assert "notes" in shown and "known" not in shown.replace("unknown", "")
    assert "spectre 1 known" in _shown(dashboard.pipeline_panel(board))


def test_a_tools_message_loses_its_level_word_and_its_paths() -> None:
    assert dashboard._clean("WARNING (SPECTRE-592): Following parameters") == "SPECTRE-592: Following parameters"
    assert dashboard._clean("Warning: dummy interface") == "dummy interface"
    assert dashboard._clean('line 3 of "/a/b/c/FasterCap_Input_.lst"') == 'line 3 of "…/FasterCap_Input_.lst"'
    assert dashboard._seconds(12.34) == "12.3" and dashboard._seconds(154.2) == "154"


def test_a_running_steps_spinner_turns_a_frame_each_drawing(monkeypatch) -> None:
    """The spinner beside a running step is the clock's frame, so a board built anew each drawing
    still turns (a Rich Spinner made each frame stays on its first)."""
    from flow import dashboard

    frames = []
    for tick in range(3):
        monkeypatch.setattr(dashboard.time, "monotonic", lambda tick=tick: 100.0 + tick * dashboard.DRAW_EVERY_S)
        frames.append(dashboard._spun())
    assert len(set(frames)) == 3


def test_the_last_line_points_at_the_runs_page_in_the_viewer_and_says_whether_it_is_up(tmp_path: Path) -> None:
    board = _board(tmp_path, ["a"])
    url = dashboard.viewer_url(board)
    assert url == f"http://localhost:8765/#block=comp&run=grid1/{tmp_path.name}"
    board.viewer = False
    assert "not running: python -m flow web.serve" in _shown(dashboard.viewer_line(board))
    board.viewer = True
    assert _shown(dashboard.viewer_line(board)).rstrip().endswith("up")


def test_a_design_that_passed_says_how_many_of_its_bounds_it_met(tmp_path: Path) -> None:
    board = _board(tmp_path, ["a", "b"])
    (tmp_path / "a" / "instance.json").write_text(json.dumps({"evidence": "postlayout", "metrics": {"delay_s": 1e-9}}))
    board.take({"key": "tsmc65/a", "step": "record", "state": "ok", "seconds": 1.0, "found": "", "counts": {}})
    board.end("tsmc65/a", ["ok"])
    results = _shown(dashboard.results_panel(board))
    assert "passed 1/1" in results and "1 ns" in results and "tsmc65/b" not in results
    assert dashboard.outcome(board.instances["tsmc65/a"]).plain == "passed · 1/1 bounds"
