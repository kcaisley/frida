"""The flow's log (``flow/logs.py``): a tool's lines at the levels they state, a step's log, its
console lines and its counts."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from flow.logs import level, run_logged, step_log


@pytest.mark.parametrize(
    ("line", "name", "at"),
    [
        (
            "\x1b[33malign.compiler.preprocess WARNING : changing source drain: MPRE\x1b[0m",
            "align.compiler.preprocess",
            "WARNING",
        ),
        ("PnR.placer.SeqPair.SeqPair INFO : Enumerated search", "PnR.placer.SeqPair.SeqPair", "INFO"),
        ("[11:49:34] INFO     DBU: 0.001                  fastercap_model_generator.py:120", None, "INFO"),
        ("           WARNING  no layer M9                  fastercap_input_builder.py:12", None, "WARNING"),
        ("Warning from spectre during topology check.", None, "INFO"),
        ("    WARNING (SPECTRE-690): No DC path from current source node `qmeter' to ground.", None, "WARNING"),
        ("spectre completes with 0 errors, 3 warnings, and 7 notices.", None, "INFO"),
        ("Warning: dummy dielectric-dielectric interface found in the input file, skipping", None, "WARNING"),
        ("//  WARNING: a license will expire", None, "WARNING"),
        ("LVS ABORT ON SUPPLY ERROR        NO", None, "INFO"),
        ("ERROR: no such layer", None, "ERROR"),
        ("RuntimeError: no room", None, "ERROR"),
    ],
)
def test_a_tool_line_takes_the_level_it_states(line: str, name: str | None, at: str) -> None:
    found, level_at, _message, _continued = level(line)
    assert (found, logging.getLevelName(level_at)) == (name, at)


def test_an_indented_line_continues_the_message_before() -> None:
    assert level("        its next line", logging.WARNING)[1:] == (logging.WARNING, "        its next line", True)
    assert level("a line of its own", logging.WARNING)[1] == logging.INFO


def test_a_step_log_holds_every_line_and_counts_the_warnings_by_tool(tmp_path: Path, capsys) -> None:
    """Every line goes to the step's log, none to the console (the step's outcome line is the console's)."""
    script = tmp_path / "tool.py"
    script.write_text(
        "print('starting')\n"
        "for row in range(3): print(f'Warning: odd matrix element at row {row}')\n"
        "print('ERROR: no such layer')\n"
        "print('    and its detail')\n"
    )
    with step_log(tmp_path / "step" / "step.log") as counts:
        run_logged([sys.executable, str(script)], cwd=tmp_path, log=tmp_path / "tool.log", name="toy")
        logging.getLogger("flow.toy").warning("the flow's own")
    text = (tmp_path / "step" / "step.log").read_text()
    assert "toy INFO : starting" in text and "toy ERROR :     and its detail" in text
    assert (tmp_path / "tool.log").read_text().count("Warning: odd") == 3
    assert counts == {"toy": {"WARNING": 3, "ERROR": 1}, "flow": {"WARNING": 1}}
    assert capsys.readouterr().out == ""


def test_a_tool_that_fails_or_runs_too_long_raises_with_its_log(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"toy failed with status 3 .*\n.*last words"):
        run_logged(
            [sys.executable, "-c", "print('last words'); raise SystemExit(3)"],
            cwd=tmp_path,
            log=tmp_path / "a.log",
            name="toy",
        )
    with pytest.raises(RuntimeError, match="toy stopped after 0.5 s"):
        run_logged(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path,
            log=tmp_path / "b.log",
            name="toy",
            timeout=0.5,
        )


def _child_warns(text: str) -> int:
    logging.getLogger("toy.child").warning(text)
    return 7


def test_a_spawned_process_logs_into_the_step(tmp_path: Path) -> None:
    from flow.logs import spawned

    with step_log(tmp_path / "step.log") as counts, spawned(1) as pool:
        assert pool.submit(_child_warns, "from the child").result() == 7
    assert "toy.child WARNING : from the child" in (tmp_path / "step.log").read_text()
    assert counts == {"toy": {"WARNING": 1}}


def test_a_python_tool_streams_its_lines_as_it_writes_them(tmp_path: Path) -> None:
    """A Python tool's output piped to the flow is unbuffered: a line comes before the tool ends."""
    script = tmp_path / "slow.py"
    script.write_text("import time\nprint('first')\ntime.sleep(3)\nprint('last')\n")
    seen: list[float] = []

    class Clock(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            import time

            seen.append(time.monotonic())

    handler = Clock()
    logging.getLogger("slowtool").addHandler(handler)
    logging.getLogger("slowtool").setLevel(logging.INFO)
    try:
        import time

        began = time.monotonic()
        run_logged([sys.executable, str(script)], cwd=tmp_path, log=tmp_path / "slow.log", name="slowtool")
    finally:
        logging.getLogger("slowtool").removeHandler(handler)
    assert len(seen) == 3 and seen[1] - began < 2.5  # the command, then 'first' well before 'last'


def test_a_known_warning_is_counted_apart_and_a_new_one_is_not(tmp_path: Path) -> None:
    """A warning the flow knows and cannot fix at its source (``KNOWN``: a foundry model's) is
    still logged, counted as ``KNOWN``; a new one (a device past its safe operating area) stays a
    warning; every known entry says why."""
    from flow.logs import KNOWN, known

    with step_log(tmp_path / "step.log") as counts:
        spectre = logging.getLogger("spectre")
        spectre.warning("WARNING (SPECTRE-592): Following parameters are disabled")
        spectre.warning("WARNING (CMI-2753): xtop.dut.MN: Vgb(=1.08 V) has exceeded vgb_max(=990 mV).")
    assert counts == {"spectre": {"KNOWN": 1, "WARNING": 1}}
    assert "SPECTRE-592" in (tmp_path / "step.log").read_text()
    assert known("align.pnr.main", "2 LVS / DRC errors found !!!") is not None
    assert known("kpex", "Warning: capacitance matrix has a non-negative off-diagonal element at row 1 col") is not None
    assert known("spectre", "Vgb has exceeded vgb_max") is None
    assert all(entry.reason for entry in KNOWN)
