"""The layout flow's log, kept as ALIGN keeps its own (``align/config/logging.ini``): Python's
logging, a logger a module (``flow.layout.step``, ``flow.netlist`` ...), each line
``name LEVEL : message`` on the console (coloured, as ALIGN's) and with its time in an instance's
``flow.log``. A tool the flow runs (gdscheck, Calibre) logs under a name of its own (``gdscheck``,
``calibre.drc`` ...), its output streamed a line at a time as it writes it, all of it into the
tool's own log file beside its results.

    with instance_log(out / "layout" / "step.log"): ...   # a layout step's log (flow.__main__)
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

FORMAT = "%(name)s %(levelname)s : %(message)s"  # ALIGN's console format
FILE_FORMAT = "%(asctime)s %(name)s %(levelname)s : %(message)s"  # its log file's
DATE = "%Y-%m-%d %H:%M:%S"
_CONSOLE = "flow-console"


def console(level: int = logging.INFO) -> None:
    """The console's handler on the root logger, once: ALIGN's format, coloured where colorlog is."""
    root = logging.getLogger()
    if any(handler.get_name() == _CONSOLE for handler in root.handlers):
        return
    for found in [h for h in root.handlers if type(h) is logging.StreamHandler]:  # a library's basicConfig
        root.removeHandler(found)
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_CONSOLE)
    try:
        import colorlog

        handler.setFormatter(colorlog.ColoredFormatter("%(log_color)s" + FORMAT))
    except ImportError:
        handler.setFormatter(logging.Formatter(FORMAT))
    handler.setLevel(level)
    root.addHandler(handler)
    root.setLevel(min(root.level or logging.WARNING, level))


@contextmanager
def instance_log(path: Path) -> Iterator[None]:
    """Every record logged meanwhile also in ``path`` (an instance's ``flow.log``), with its time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE))
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(min(root.level or logging.WARNING, logging.INFO))
    try:
        yield
    finally:
        root.removeHandler(handler)
        handler.close()


# Calibre's lines worth reading as it runs: its modules' starts and ends, its totals, its verdicts,
# its warnings and errors, any rule check with results; the rest (rule files echoed, environment,
# every rule check's zero) stays in its log
_CALIBRE = re.compile(
    r"^--- CALIBRE::|MODULE COMPLETED|^--- TOTAL|^--- GRAND TOTAL|^LVS (started|completed)|CORRECT|"
    r"Result Count = [1-9]|^//\s+(WARNING|ERROR)|^(WARNING|ERROR)\b"
)


def calibre_line(line: str) -> bool:
    """Whether a line of Calibre's output is one the console shows (``_CALIBRE``)."""
    return bool(_CALIBRE.search(line))


def run_logged(
    command: list[str],
    *,
    cwd: Path,
    log: Path,
    name: str,
    env: dict[str, str] | None = None,
    keep: Callable[[str], bool] | None = None,
    allowed: tuple[int, ...] = (0,),
) -> str:
    """Run ``command`` in ``cwd``, its output (stdout and stderr) into ``log`` and, a line at a time
    as it writes it, to the logger ``name`` (the lines ``keep`` passes, every line without one);
    its whole output returned. Raises where it exits with a code not ``allowed``."""
    logger = logging.getLogger(name)
    logger.info(" ".join(command))
    lines: list[str] = []
    with log.open("w", encoding="utf-8") as out:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
        )
        assert process.stdout is not None
        for line in process.stdout:
            out.write(line)
            lines.append(line)
            text = line.rstrip("\n")
            if text.strip() and (keep is None or keep(text)):
                logger.info(text)
        code = process.wait()
    if code not in allowed:
        raise RuntimeError(f"{' '.join(command)} failed with status {code}; see {log}")
    return "".join(lines)
