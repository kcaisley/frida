"""The flow's log, kept as ALIGN keeps its own (``align/config/logging.ini``): Python's logging, a
logger a module (``flow.layout.step``, ``flow.netlist`` ...) or a tool (``align``, ``spectre``,
``kpex``, ``gdscheck``, ``calibre.drc`` ...), each line ``name LEVEL : message``.

A tool the flow runs keeps its whole output, as it writes it, in its own log file beside its results
(``run_logged``, or ``relay`` for one a library runs: Spectre's ``spectre.log``), and each of its
lines is also a record of the tool's logger, at the level the line states (``level``: ALIGN's
``name LEVEL :``, kpex's rich columns, Spectre's ``WARNING (SPECTRE-...)``, ``Warning:``/``ERROR:``
elsewhere; INFO where it states none). While a step runs on an instance (``step_log``), every record,
the flow's and its tools', goes with its time into the step's ``step.log``; each warning and error
also goes to the console, tagged with the instance; and the warnings and errors are counted by tool,
for the step's ``step.json``. Nothing is filtered out: what a tool says it says in its log and the
step's; the console shows each of its warnings and errors once (``_Once``: a license's warning
repeated for each of its features, a line), how many it repeats too.

    with step_log(out / "layout" / "step.log", "samp/tsmc65/frida1") as counts: ...
    run_logged(["gdscheck", ...], cwd=run_dir, log=run_dir / "gdscheck.log", name="gdscheck")
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import get_context
from pathlib import Path
from typing import Any

FORMAT = "%(name)s %(levelname)s : %(message)s"  # ALIGN's console format
FILE_FORMAT = "%(asctime)s %(name)s %(levelname)s : %(message)s"  # its log file's
DATE = "%Y-%m-%d %H:%M:%S"
_CONSOLE = "flow-console"

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
_DIGITS = re.compile(r"\d+")


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
    ``flow`` ...; Python's warnings as ``python``) and level: ``{"align": {"WARNING": 4}}``; a
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
        levels[record.levelname] = levels.get(record.levelname, 0) + 1


class _Once(logging.Filter):
    """Each message once on the console: one like it shown (the same logger, the same words, its
    numbers aside: a license's serial, a matrix's row), its repeats counted, not shown."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: set[tuple[str, str]] = set()
        self.repeats = 0

    def filter(self, record: logging.LogRecord) -> bool:
        key = (record.name, _DIGITS.sub("#", record.getMessage()))
        if key in self.seen:
            self.repeats += 1
            return False
        self.seen.add(key)
        return True


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


def console(level: int = logging.INFO, tag: str = "") -> logging.Handler:
    """The console's handler on the root logger (one only: another's, a library's basicConfig,
    replaced), ``tag`` (an instance) before each line: ALIGN's format, coloured where colorlog is."""
    root = logging.getLogger()
    for found in [h for h in root.handlers if h.get_name() == _CONSOLE or type(h) is logging.StreamHandler]:
        root.removeHandler(found)
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_CONSOLE)
    shown = f"{tag} {FORMAT}" if tag else FORMAT
    try:
        import colorlog

        handler.setFormatter(colorlog.ColoredFormatter("%(log_color)s" + shown))
    except ImportError:
        handler.setFormatter(logging.Formatter(shown))
    handler.setLevel(level)
    root.addHandler(handler)
    root.setLevel(min(root.level or logging.WARNING, level))
    return handler


def _trimmed(record: logging.LogRecord) -> bool:
    """A record's message without the line end it may carry (Python's warnings')."""
    if isinstance(record.msg, str):
        record.msg = record.msg.rstrip()
    return True


@contextmanager
def step_log(path: Path, instance: str) -> Iterator[dict[str, dict[str, int]]]:
    """While a step runs on an instance: every record (INFO and above, the flow's and its tools',
    Python's warnings too) into ``path`` (the step's ``step.log``) with its time; each warning and
    error on the console, ``instance`` before it; the warnings and errors counted by tool (the dict
    yielded, filled as they come: ``_Counts``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    file = logging.FileHandler(path, mode="w", encoding="utf-8")
    file.setFormatter(logging.Formatter(FILE_FORMAT, DATE))
    file.setLevel(logging.INFO)
    file.addFilter(_trimmed)
    counts, once = _Counts(), _Once()
    shown = console(logging.WARNING, instance)
    shown.addFilter(_trimmed)
    shown.addFilter(once)
    level_before = root.level
    root.setLevel(logging.INFO)
    root.addHandler(file)
    root.addHandler(counts)
    logging.captureWarnings(True)
    try:
        yield counts.counts
    finally:
        if once.repeats:
            print(f"{instance} {once.repeats} warnings and errors like those above not shown again; all in {path}")
        logging.captureWarnings(False)
        for handler in (file, counts, shown):
            root.removeHandler(handler)
        file.close()
        root.setLevel(level_before)
