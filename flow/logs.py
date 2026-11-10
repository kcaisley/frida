"""The flow's log, kept as ALIGN keeps its own (``align/config/logging.ini``): Python's logging, a
logger a module (``flow.layout.step``, ``flow.netlist`` ...) or a tool (``align``, ``spectre``,
``kpex``, ``gdscheck``, ``calibre.drc`` ...), each line ``name LEVEL : message``.

A tool the flow runs keeps its whole output, as it writes it, in its own log file beside its results
(``run_logged``, or ``relay`` for one a library runs: Spectre's ``spectre.log``), and each of its
lines is also a record of the tool's logger, at the level the line states (``level``: ALIGN's
``name LEVEL :``, kpex's rich columns, Spectre's ``WARNING (SPECTRE-...)``, ``Warning:``/``ERROR:``
elsewhere; INFO where it states none). While a step runs on an instance (``step_log``), every record,
the flow's and its tools', goes with its time into the step's ``step.log``, and the warnings and errors are counted by tool,
for the step's ``step.json``. Nothing is filtered out: what a tool says it says in its log and the
step's. The console has a line a step as it ends (``flow.steps``): its folder, its state, its
seconds and those counts.

    with step_log(out / "layout" / "step.log") as counts: ...
    run_logged(["gdscheck", ...], cwd=run_dir, log=run_dir / "gdscheck.log", name="gdscheck")
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import get_context
from pathlib import Path
from typing import Any

FORMAT = "%(name)s %(levelname)s : %(message)s"  # ALIGN's console format
FILE_FORMAT = "%(asctime)s %(name)s %(levelname)s : %(message)s"  # its log file's
DATE = "%Y-%m-%d %H:%M:%S"

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_LEVELS = "DEBUG|INFO|WARNING|ERROR|CRITICAL"
# ALIGN's (and the flow's) own lines: ``align.pnr.main WARNING : message``
_NAMED = re.compile(rf"^(\S+) ({_LEVELS}) : (.*)$")
# kpex's (rich's columns): ``[11:49:34] WARNING  message    module.py:120``
# (its time left out where the line before's is the same; its level padded to eight columns)
_RICH = re.compile(rf"^\s*(?:\[[\d:]+\]\s+)?({_LEVELS})(?:\s{{2,}}|(?<=CRITICAL)\s)(.*?)(?:\s{{2,}}[\w.]+\.py:\d+)?$")
# a simulator's heading over the lines that state the level themselves: Spectre's ``Warning from
# spectre during topology check.`` above ``    WARNING (SPECTRE-690): ...``
_HEADING = re.compile(r"^(Warning|Error|Notice) from \w+ (at|during|in)\b")
# elsewhere a message's level is a word before a colon or its code: ``ERROR:``, ``//  WARNING:``,
# ``WARNING (SPECTRE-690):``, ``Router-Warning:``, Python's ``RuntimeError:``; not the word alone (a
# deck's echoed option, ``LVS ABORT ON SUPPLY ERROR  NO``)
_ERROR = re.compile(r"(\b(ERROR|Error|FATAL|Fatal|CRITICAL)|^\w*(Error|Exception))\s*[:(]")
_WARNING = re.compile(r"\b(WARNING|Warning|WARN)\s*[:(]")


@dataclass(frozen=True)
class Known:
    """A warning or error the flow knows and cannot fix at its source (a foundry's model files, a
    tool's own check another step contradicts): the tool whose logger says it (its name or its
    name's start: ``align`` for ``align.pnr.main``), a pattern its message matches, and why it is
    not fixed. Still logged and counted; the dashboard shows it at its own level, dimmed, the
    reason as its note, so a new one stands out (``flow.dashboard``). A warning the flow causes is
    fixed, never listed here."""

    tool: str
    pattern: str
    reason: str

    def matches(self, tool: str, message: str) -> bool:
        return (tool == self.tool or tool.startswith(f"{self.tool}.")) and re.search(self.pattern, message) is not None


KNOWN = (
    Known(
        "spectre",
        r"SPECTRE-592\b",
        "the foundry's model cards set parameters Spectre X ignores; the models are the kit's, not ours to edit",
    ),
    Known(
        "spectre",
        r"SFE-1131\b.*scalefactor",
        "TSMC28's model files set scalefactor twice (its toplevel and its usage file)",
    ),
    Known(
        "spectre",
        r"CMI-9000\b.*Rgate",
        "IHP's models add a gate resistance below Spectre's MinR, which Spectre then drops",
    ),
    Known(
        "kpex",
        r"capacitance matrix (has a non-negative off-diagonal element|is not diagonally dominant)",
        "FasterCap's check of the matrix it solved: near-zero couplings between distant nets come out"
        " with the wrong sign; a tighter tolerance does not lessen them (measured at 5, 2 and 1 %), and"
        " 5 % is kept for speed, its nets' capacitances a few percent high",
    ),
    Known(
        "align",
        r"LVS / DRC errors found|Found errors: SHORT: 0 OPEN|feasible path might not be found",
        "ALIGN's own checks of its output; the lvs step's KLayout LVS of the same layout decides",
    ),
)


def known(tool: str, message: str) -> Known | None:
    """The known warning ``tool``'s ``message`` is (``KNOWN``), else None."""
    return next((entry for entry in KNOWN if entry.matches(tool, message)), None)


def level(line: str, previous: int = logging.INFO) -> tuple[str | None, int, str, bool]:
    """A tool's output line as a record: the logger name it states (ALIGN's), else None; its level;
    its message (ANSI colour left out); whether it continues the line before's message. A line that
    states no level, indented under one (a message continued), takes that one's (``previous``)."""
    text = _ANSI.sub("", line).rstrip()
    named = _NAMED.match(text)
    if named:
        return named[1], logging.getLevelName(named[2]), named[3], False
    rich = _RICH.match(text)
    if rich:
        return None, logging.getLevelName(rich[1]), rich[2], False
    if _HEADING.match(text):
        return None, logging.INFO, text, False
    if _ERROR.search(text):
        return None, logging.ERROR, text, False
    if _WARNING.search(text):
        return None, logging.WARNING, text, False
    continued = text[:1].isspace()
    return None, previous if continued else logging.INFO, text, continued


class _Relay:
    """A tool's lines, one at a time, as records of its logger (``tool``, or ``tool.<name>`` where a
    line names its own logger: ALIGN's ``align.pnr.main``, ``PnR.placer`` as ``align.PnR.placer``)."""

    def __init__(self, tool: str) -> None:
        self.tool, self.previous = tool, logging.INFO

    def __call__(self, line: str) -> None:
        name, at, message, continued = level(line, self.previous)
        self.previous = at
        if not message.strip():
            return
        if name is None:
            name = self.tool
        elif name != self.tool and not name.startswith(f"{self.tool}."):
            name = f"{self.tool}.{name}"
        logging.getLogger(name).log(at, message, extra={"counted": not continued})


def run_logged(
    command: list[str],
    *,
    cwd: Path,
    log: Path,
    name: str,
    env: dict[str, str] | None = None,
    allowed: tuple[int, ...] = (0,),
    timeout: float | None = None,
) -> str:
    """Run ``command`` in ``cwd``: its output (stdout and stderr) as it writes it into ``log`` and,
    a line at a time, as records of the logger ``name`` (``_Relay``); its whole output returned.
    Stopped, with every process it started, after ``timeout`` seconds or where this one is
    interrupted. Raises where it exits with a code not ``allowed``, or is stopped. A Python tool
    (ALIGN, kpex) runs unbuffered, so its lines come as it writes them, not when it ends."""
    logger = logging.getLogger(name)
    logger.info(" ".join(command))
    relay, lines = _Relay(name), []
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as out:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env={**(os.environ if env is None else env), "PYTHONUNBUFFERED": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,  # its own process group: stopped whole
        )
        stopped = threading.Event()

        def stop() -> None:
            stopped.set()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        timer = threading.Timer(timeout, stop) if timeout else None
        if timer:
            timer.start()
        try:
            assert process.stdout is not None
            for line in process.stdout:
                out.write(line)
                lines.append(line)
                relay(line)
            code = process.wait()
        except BaseException:
            stop()
            process.wait()
            raise
        finally:
            if timer:
                timer.cancel()
    if stopped.is_set():
        raise RuntimeError(f"{name} stopped after {timeout:g} s ({log})")
    if code not in allowed:
        tail = _ANSI.sub("", "".join(lines[-15:])).rstrip()
        raise RuntimeError(f"{name} failed with status {code} ({log}):\n{tail}")
    return "".join(lines)


def relay(log: Path, name: str) -> None:
    """A finished tool's log (one a library ran: Spectre's, through vlsirtools), each line a record
    of the logger ``name`` (``_Relay``), as ``run_logged`` streams one; nothing where it wrote none."""
    if not log.is_file():
        return
    logging.getLogger(name).info(f"its log: {log}")
    each = _Relay(name)
    with log.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            each(line)


class _Counts(logging.Handler):
    """The warnings and errors logged, by tool (a logger's first name: ``align``, ``spectre``,
    ``flow`` ...; Python's warnings as ``python``) and level, a known one (``KNOWN``) as ``KNOWN``:
    ``{"align": {"WARNING": 4, "KNOWN": 2}}``; a
    record marked ``counted=False`` not (a message's continued lines, ``level``; a step's own
    failure, which its outcome states)."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.counts: dict[str, dict[str, int]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if not getattr(record, "counted", True):
            return
        tool = record.name.split(".")[0]
        tool = "python" if tool == "py" else tool
        levels = self.counts.setdefault(tool, {})
        # a known warning or error (``KNOWN``) counted as known, apart from the new ones
        level = "KNOWN" if known(record.name, record.getMessage()) else record.levelname
        levels[level] = levels.get(level, 0) + 1


class _Here(logging.Handler):
    """A spawned process's record logged in this one, by its logger (``spawned``)."""

    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


def _forwarding(records, initializer: Callable[..., None] | None, initargs: tuple) -> None:
    """A spawned process's log records (INFO and above) sent to its parent (``records``: a queue),
    then its own ``initializer``."""
    root = logging.getLogger()
    root.handlers[:] = [QueueHandler(records)]
    root.setLevel(logging.INFO)
    logging.captureWarnings(True)
    if initializer is not None:
        initializer(*initargs)


@contextmanager
def spawned(
    workers: int = 1, initializer: Callable[..., None] | None = None, initargs: tuple = (), **options: Any
) -> Iterator[ProcessPoolExecutor]:
    """A pool of ``workers`` spawned processes (``ProcessPoolExecutor``, its ``options`` too) whose
    log records are logged here, by their loggers (into a step's log, the console), as this
    process's own are: a characterization a lookup starts, a layout bound to its PDK."""
    context = get_context("spawn")
    records = context.Queue()
    listener = QueueListener(records, _Here())
    listener.start()
    try:
        with ProcessPoolExecutor(
            workers, mp_context=context, initializer=_forwarding, initargs=(records, initializer, initargs), **options
        ) as pool:
            yield pool
    finally:
        listener.stop()


def _trimmed(record: logging.LogRecord) -> bool:
    """A record's message without the line end it may carry (Python's warnings')."""
    if isinstance(record.msg, str):
        record.msg = record.msg.rstrip()
    return True


@contextmanager
def step_log(path: Path) -> Iterator[dict[str, dict[str, int]]]:
    """While a step runs: every record (INFO and above, the flow's and its tools', Python's warnings
    too) into ``path`` (the step's ``step.log``) with its time, and nowhere else (a library's
    console handler set aside meanwhile: the step's outcome is the console's line, ``flow.steps``);
    the warnings and errors counted by tool (the dict yielded, filled as they come: ``_Counts``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    file = logging.FileHandler(path, mode="w", encoding="utf-8")
    file.setFormatter(logging.Formatter(FILE_FORMAT, DATE))
    file.setLevel(logging.INFO)
    file.addFilter(_trimmed)
    counts = _Counts()
    aside = [handler for handler in root.handlers if type(handler) is logging.StreamHandler]
    for handler in aside:
        root.removeHandler(handler)
    level_before = root.level
    root.setLevel(logging.INFO)
    root.addHandler(file)
    root.addHandler(counts)
    logging.captureWarnings(True)
    try:
        yield counts.counts
    finally:
        logging.captureWarnings(False)
        for handler in (file, counts):
            root.removeHandler(handler)
        for handler in aside:
            root.addHandler(handler)
        file.close()
        root.setLevel(level_before)
