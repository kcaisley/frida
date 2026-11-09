"""A run's live dashboard (``python -m flow``): every instance's steps as they end, from the events
its worker sends (``flow.steps.run_steps``), drawn three ways from one model (``Board``):

- in a terminal, htop-like and in place (Rich's inline live view at the terminal's height, not the
  alternate screen, so the frame stays in the terminal's own buffer: a selection, an editor's
  terminal context, the last frame in scrollback): the run's header; the pipeline, a row a step
  (its instances waiting, running, passed, kept from before, rejected, failed, not run; its
  seconds; its tools' warnings and errors); what needs attention (each failure, each bound's first
  rejection, each kind of warning or error the first time, with how often since); for one instance
  its running tool's newest lines and its metrics, pre- and post-layout; for many, why designs
  left the run and the ones that passed;
- elsewhere (a pipe, a log, an agent's command), as lines: each step's line for a run of a few
  instances (``SMALL``), else what needs attention as it happens and a status line every two
  minutes; the summary at the end either way;
- always, beside the run (``build/<block>/<run>/<stamp>/``): ``status.txt``, the dashboard as plain
  text every two seconds (an agent reads the same view in one file), and ``events.log``, each line
  that needs attention as it comes.

Colours are the terminal's own ANSI ones, which its theme maps (Nord in Ghostty, light or dark
alike): no background, no fixed colour. Errors are never hidden: every failure is a line, every
kind of warning is shown once and counted.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

# the terminal's own colours, which its theme maps
DIM, TEXT, HEAD, RUN, OK, KEPT, REJECT, WARN, BAD, FRAME = (
    "bright_black",
    "default",
    "blue",
    "cyan",
    "green",
    "blue",
    "magenta",
    "yellow",
    "red",
    "bright_black",
)
# a run of at most this many instances prints each step's line where it is not drawn live
SMALL = 8
# how often the plain view says where the run is, and the status file is written (s)
STATUS_EVERY_S, WRITE_EVERY_S = 120.0, 2.0
# a status file's size, as a large terminal's
STATUS_WIDTH, STATUS_HEIGHT = 200, 56
LEVELS = {"ERROR": "error", "CRITICAL": "error", "WARNING": "warning"}


@dataclass
class _Instance:
    """One instance as the board knows it: the step it runs, each step's state and what it found,
    how it ended, and its record's metrics once recorded."""

    key: str
    out: Path
    bounds: tuple[str, ...]
    running: str | None = None
    states: dict[str, str] = field(default_factory=dict)
    found: dict[str, str] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)
    ended: str = ""  # "", passed, rejected, failed
    record: dict[str, Any] = field(default_factory=dict)


@dataclass
class Board:
    """What the dashboard shows of a run: its block, run, kind, PDKs, workers, folder and steps, and
    each instance (``take`` an event, ``end`` an instance)."""

    block: str
    run: str
    kind: str
    pdks: tuple[str, ...]
    workers: int
    folder: Path
    steps: tuple[str, ...]
    instances: dict[str, _Instance] = field(default_factory=dict)
    counts: dict[str, Counter[tuple[str, str]]] = field(default_factory=dict)
    attention: deque[tuple[str, str, str, str, Any]] = field(default_factory=lambda: deque(maxlen=200))
    kinds: Counter[Any] = field(default_factory=Counter)
    rejections: Counter[tuple[str, str]] = field(default_factory=Counter)
    began: float = field(default_factory=time.monotonic)
    fresh: list[str] = field(default_factory=list)  # attention lines not yet written to events.log
    unprinted: list[str] = field(default_factory=list)  # nor printed, where the run is not drawn live

    def add(self, key: str, out: Path, bounds: Iterable[str]) -> None:
        self.instances[key] = _Instance(key, out, tuple(bounds))

    def take(self, event: dict[str, Any]) -> None:
        """A worker's event: a step started (``running``) or ended (its state, seconds, what it found
        and its log's warnings and errors by tool)."""
        item, step, state = self.instances[event["key"]], event["step"], event["state"]
        if state == "running":
            item.running = step
            item.states[step] = "running"
            return
        item.running = None if item.running == step else item.running
        item.states[step], item.found[step] = state, event.get("found", "")
        if event.get("seconds") is not None:
            item.seconds[step] = float(event["seconds"])
        for tool, levels in (event.get("counts") or {}).items():
            for level, n in levels.items():
                self.counts.setdefault(step, Counter())[(tool, level)] += n
        if state == "ok" and event.get("counts"):
            self._kinds(item, step)
        if state == "failed":
            self._say("FAILED", f"{item.key}/{step}: {item.found[step]}", _shown(item.out / step / "step.log"))
        if state == "rejected":
            kind = (step, re.sub(r"[-+.\deE]+(?=\s|$|\))", "#", item.found[step]))
            self.rejections[(step, _bounds_of(item.found[step]))] += 1
            self.kinds[kind] += 1
            if self.kinds[kind] == 1:
                self._say("REJECTED", f"{item.key}/{step}: {item.found[step]}", "the first of its kind", kind)
        if step == "record" and state in ("ok", "done"):
            item.record = _read(item.out / "instance.json")

    def end(self, key: str, states: Iterable[str]) -> None:
        """An instance's worker ended: failed where a step failed, else rejected where one rejected
        it, else passed."""
        item, seen = self.instances[key], set(states)
        item.running = None
        item.ended = "failed" if "failed" in seen else "rejected" if "rejected" in seen else "passed"

    def _kinds(self, item: _Instance, step: str) -> None:
        """Each kind of warning and error in the step's log (its digits left out) said the first time
        it is seen in the run, counted after."""
        path = item.out / step / "step.log"
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            return
        for line in lines:
            parts = line.split(" ", 4)  # date time tool LEVEL : message
            if len(parts) < 5 or parts[3] not in LEVELS:
                continue
            tool, level, message = parts[2], parts[3], parts[4].removeprefix(": ")
            kind = (tool, level, re.sub(r"\d+", "#", message)[:160])
            self.kinds[kind] += 1
            if self.kinds[kind] == 1:
                self._say(level, f"{tool}: {message}", f"first in {item.key}/{step}", kind)

    def _say(self, level: str, text: str, where: str, kind: Any = None) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.attention.append((stamp, level, text, where, kind))
        self.fresh.append(f"{stamp} {level} {text}  [{where}]")
        self.unprinted.append(self.fresh[-1])

    # ------------------------------------------------------------ what the views count

    def by_step(self, step: str) -> Counter[str]:
        """Each state's instances at ``step``: waiting (not reached), running, ok, done (kept from
        before), rejected, failed, not run."""
        found: Counter[str] = Counter()
        for item in self.instances.values():
            found[item.states.get(step, "not run" if item.ended else "waiting")] += 1
        return found

    def ended(self) -> Counter[str]:
        return Counter(item.ended or ("running" if item.states else "waiting") for item in self.instances.values())


def _bounds_of(found: str) -> str:
    """The metrics a rejection names: ``rejected at sim (prelayout): delay_s 2e-09 > 1e-09`` gives
    ``delay_s``."""
    said = found.split(": ", 1)[-1]
    return ", ".join(part.split(" ", 1)[0] for part in said.split(", "))


def _read(path: Path) -> dict[str, Any]:
    import json

    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _shown(path: Path) -> str:
    from flow.sweep import runner

    return runner._shown(path)


def _seconds(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.1f} s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


# a metric's unit by its name's last word, and its SI prefixes
_UNITS = {"s": "s", "j": "J", "v": "V", "w": "W", "hz": "Hz", "ohm": "Ω", "f": "F", "a": "A"}
_PREFIXES = (
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "µ"),
    (1e-9, "n"),
    (1e-12, "p"),
    (1e-15, "f"),
    (1e-18, "a"),
)


def value(name: str, number: Any) -> str:
    """A metric's value as the dashboard shows it: a flag yes or no, a number in its unit (its name's
    last word: ``_s``, ``_j``, ``_v``, ``_hz``, ``_ohm``, ``_um2`` ...) with an SI prefix, three
    significant digits; not measured, a dash."""
    if number is None:
        return "–"
    if isinstance(number, bool):
        return "yes" if number else "no"
    if not isinstance(number, (int, float)):
        return str(number)
    unit = name.rsplit("_", 1)[-1] if "_" in name else ""
    if unit == "um2":
        return f"{number:.3g} µm²"
    if unit in _UNITS and number:
        scale, prefix = next(((s, p) for s, p in _PREFIXES if abs(number) >= s), _PREFIXES[-1])
        return f"{number / scale:.3g} {prefix}{_UNITS[unit]}"
    return f"{number:.4g}"


# ---------------------------------------------------------------- the panels


def _table(*columns: tuple[str, str, int]) -> Table:
    """A table of these columns (name, justification, width), the last taking what room is left."""
    found = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, header_style=f"bold {HEAD}", border_style=FRAME)
    for place, (name, justify, width) in enumerate(columns):
        last = place == len(columns) - 1
        found.add_column(
            name,
            justify=justify,  # ty: ignore[invalid-argument-type]
            no_wrap=True,
            overflow="ellipsis",
            width=None if last else width,
            min_width=width if last else None,
            ratio=1 if last else None,
        )
    return found


def _count(n: int, style: str) -> Text:
    return Text(str(n) if n else "·", style=style if n else DIM)


def pipeline_table(board: Board) -> Table:
    """A row a step: its instances in each state, its seconds summed, its tools' warnings and errors."""
    found = _table(
        ("step", "left", 9),
        ("waiting", "right", 7),
        ("running", "right", 7),
        ("ok", "right", 5),
        ("kept", "right", 5),
        ("rejected", "right", 8),
        ("failed", "right", 6),
        ("not run", "right", 7),
        ("time", "right", 8),
        ("warnings · errors", "left", 20),
    )
    for step in board.steps:
        c = board.by_step(step)
        seconds = sum(item.seconds.get(step, 0.0) for item in board.instances.values())
        said = Text()
        for (tool, level), n in sorted(board.counts.get(step, Counter()).items()):
            said.append(f"{tool} {n} {LEVELS.get(level, level.lower())}  ", style=BAD if level != "WARNING" else WARN)
        label = Text(step, style=f"bold {RUN}" if c["running"] else TEXT)
        found.add_row(
            Spinner("dots", text=label, style=RUN) if c["running"] else Text.assemble("  ", label),
            _count(c["waiting"], DIM),
            _count(c["running"], RUN),
            _count(c["ok"], OK),
            _count(c["done"], KEPT),
            _count(c["rejected"], REJECT),
            _count(c["failed"], BAD),
            _count(c["not run"], DIM),
            Text(_seconds(seconds) if seconds else "", style=DIM),
            said,
        )
    return found


def attention_panel(board: Board, rows: int | None = None) -> Panel:
    """What needs attention, the newest first: each failure with its log, each kind of rejection and
    of warning or error the first time, with how often since."""
    found = Table.grid(padding=(0, 2), expand=True)
    found.add_column(style=DIM, no_wrap=True, min_width=8)
    found.add_column(no_wrap=True, min_width=8)
    found.add_column(overflow="fold", ratio=1)
    style = {
        "ERROR": f"bold {BAD}",
        "CRITICAL": f"bold {BAD}",
        "WARNING": WARN,
        "FAILED": f"bold {BAD}",
        "REJECTED": REJECT,
    }
    shown = list(reversed(board.attention))[: rows or None]
    for stamp, level, text, where, kind in shown:
        times = (
            Text(f"  ×{board.kinds[kind]}", style=f"bold {style[level]}") if kind and board.kinds[kind] > 1 else Text()
        )
        found.add_row(stamp, Text(level, style=style[level]), Text(text) + times + Text(f"  {where}", style=DIM))
    if not board.attention:
        found.add_row("", "", Text("nothing yet", style=DIM))
    return Panel(found, title="needs attention (newest first)", title_align="left", border_style=FRAME)


def tool_panel(board: Board, rows: int = 18) -> Panel:
    """The running step's newest log lines (its ``step.log``), at their levels, the newest first."""
    item = next((i for i in board.instances.values() if i.running), None) or next(iter(board.instances.values()))
    step = item.running or next(reversed(item.states), board.steps[0])
    found = Table.grid(expand=True)
    found.add_column(overflow="fold")
    try:
        lines = (item.out / step / "step.log").read_text(errors="replace").splitlines()[-rows:]
    except OSError:
        lines = []
    for line in reversed(lines):
        level = line.split(" ", 4)[3] if len(line.split(" ", 4)) > 4 else ""
        found.add_row(Text(line, style={"ERROR": BAD, "CRITICAL": BAD, "WARNING": WARN}.get(level, DIM)))
    title = f"{item.key}/{step} · step.log" + ("" if item.running else f" ({item.states.get(step, '')})")
    return Panel(found, title=title, title_align="left", border_style=FRAME)


def metrics_panel(board: Board, rows: int = 16) -> Panel:
    """One instance's record: each metric pre- and post-layout and how it moved (its bounds' metrics
    first)."""
    item = next(iter(board.instances.values()))
    record = item.record
    found = _table(
        ("metric", "left", 16), ("pre-layout", "right", 11), ("post-layout", "right", 11), ("change", "right", 7)
    )
    post = record.get("metrics") or {}
    pre = record.get("prelayout") or (post if record.get("evidence") != "postlayout" else {})
    names = [*item.bounds, *(name for name in post if name not in item.bounds)]
    for name in names[:rows]:
        a, b = pre.get(name), post.get(name) if record.get("evidence") == "postlayout" else None
        moved = ""
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and a:
            moved = f"{b / a - 1:+.1%}"
        found.add_row(value(name, a), value(name, b), moved, name)
    title = f"{item.key} · {record.get('evidence', 'not recorded yet')}"
    if record.get("rejected"):
        title += f" · rejected at {record['rejected']['step']}"
    return Panel(found, title=title, title_align="left", border_style=FRAME)


def left_panel(board: Board) -> Panel:
    """Why designs left the run: each bound by the step that caught them, and the failures by step."""
    found = _table(("caught at", "left", 9), ("designs", "right", 7), ("bound", "left", 18))
    for (step, bounds), n in sorted(board.rejections.items(), key=lambda kn: board.steps.index(kn[0][0])):
        found.add_row(step, Text(str(n), style=REJECT), bounds)
    failed = Counter(step for item in board.instances.values() for step, s in item.states.items() if s == "failed")
    for step, n in failed.items():
        found.add_row(step, Text(str(n), style=BAD), Text("failed", style=BAD))
    if not board.rejections and not failed:
        found.add_row("", "", Text("none yet", style=DIM))
    return Panel(found, title="rejected and failed", title_align="left", border_style=FRAME)


def passed_panel(board: Board, rows: int = 30) -> Panel:
    """The instances that passed every step, the latest first: their bounds' metrics (or their
    record's first), as their record states them."""
    passed = [item for item in board.instances.values() if item.ended == "passed" and item.record]
    names = list(next(iter(board.instances.values())).bounds) if board.instances else []
    if not names and passed:
        names = [n for n, v in (passed[0].record.get("metrics") or {}).items() if isinstance(v, (int, float))][:4]
    width = max((len(item.key) for item in passed), default=8)
    found = _table(
        ("instance", "left", width), *((n, "right", max(9, len(n))) for n in names), ("evidence", "left", 10)
    )
    for item in reversed(passed[-rows:]):
        metrics = item.record.get("metrics") or {}
        found.add_row(item.key, *(value(n, metrics.get(n)) for n in names), item.record.get("evidence", ""))
    title = f"{len(passed)} passed (the latest first)" if passed else "nothing has passed yet"
    return Panel(found, title=title, title_align="left", border_style=FRAME)


def header(board: Board) -> Text:
    ended = board.ended()
    many = len(board.instances)
    return Text.assemble(
        (f" {board.block} ", f"bold {HEAD}"),
        (board.run, f"bold {TEXT}"),
        (f" · {board.kind} · {many} design{'s' if many != 1 else ''}", DIM),
        f" · {', '.join(board.pdks)}",
        (f" · {board.workers} workers · {_seconds(time.monotonic() - board.began)}", DIM),
        "     ",
        (f"{many - ended['waiting']}/{many} started   ", TEXT),
        (f"{ended['passed']} passed   ", OK),
        (f"{ended['rejected']} rejected   ", REJECT),
        (f"{ended['failed']} failed", BAD),
    )


def dashboard(board: Board) -> Layout:
    """The whole terminal: the header; the pipeline, what needs attention below it; on the right the
    running tool and the metrics (one instance), or why designs left and those that passed (many)."""
    root = Layout()
    root.split_column(Layout(header(board), size=1), Layout(name="body"))
    root["body"].split_row(Layout(name="left", ratio=3), Layout(name="right", ratio=2))
    pipeline = Panel(pipeline_table(board), title="pipeline", title_align="left", border_style=FRAME)
    root["body"]["left"].split_column(Layout(pipeline, size=len(board.steps) + 5), Layout(attention_panel(board, 60)))
    if len(board.instances) == 1:
        root["body"]["right"].split_column(Layout(tool_panel(board)), Layout(metrics_panel(board), size=20))
    else:
        size = max(6, len(board.rejections) + 6)
        root["body"]["right"].split_column(Layout(left_panel(board), size=size), Layout(passed_panel(board)))
    return root


def summary(board: Board) -> Group:
    """What stays once the run ends: the header, the pipeline, the metrics (one instance) or why designs
    left (many), and what needs attention."""
    right = [metrics_panel(board)] if len(board.instances) == 1 else [left_panel(board)]
    pipeline = Panel(pipeline_table(board), title="pipeline", title_align="left", border_style=FRAME)
    return Group(header(board), pipeline, *right, attention_panel(board, 40))


def status_line(board: Board) -> str:
    """Where the run is, in a line: started, passed, rejected (by which bound), failed, and the steps
    running."""
    ended = board.ended()
    running = Counter(item.running for item in board.instances.values() if item.running)
    why = ", ".join(f"{n} by {bounds} at {step}" for (step, bounds), n in board.rejections.items())
    return (
        f"{time.strftime('%H:%M:%S')} status: {len(board.instances) - ended['waiting']}/{len(board.instances)} started, "
        f"{ended['passed']} passed, {ended['rejected']} rejected{f' ({why})' if why else ''}, {ended['failed']} failed; "
        f"running: {'; '.join(f'{step} {n}' for step, n in running.items()) or 'nothing'}"
    )


class View:
    """The board drawn where the run is watched: live in a terminal, as lines elsewhere (``SMALL``),
    and into the run's ``status.txt`` and ``events.log`` either way."""

    def __init__(self, board: Board, line) -> None:
        self.board, self.line = board, line
        self.console = Console(file=sys.stdout)
        self.live: Live | None = None
        self.written = self.said = -1e9

    def __enter__(self) -> Self:
        if self.console.is_terminal:
            self.live = Live(
                dashboard(self.board),
                console=self.console,
                refresh_per_second=4,
                screen=False,
                transient=True,
                vertical_overflow="crop",
            )
            self.live.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        if self.live is not None:
            self.live.__exit__(None, None, None)
        self.write(force=True)
        console = self.console if self.console.is_terminal else Console(file=sys.stdout, width=160)
        console.print(summary(self.board))

    def take(self, event: dict[str, Any]) -> None:
        """An event onto the board, and, where the run is not drawn live and is small, its line
        (``line``: the step runner's own)."""
        self.board.take(event)
        if self.live is None and len(self.board.instances) <= SMALL and event["state"] != "running":
            self.line(event)

    def refresh(self) -> None:
        """The live view drawn again; elsewhere what needs attention printed as it came (a large
        run's), and a status line now and then; the status files every two seconds."""
        now = time.monotonic()
        if self.live is not None:
            self.live.update(dashboard(self.board))
        if len(self.board.instances) > SMALL and self.live is None:
            for line in self.board.unprinted:
                print(line, flush=True)
            if now - self.said >= STATUS_EVERY_S:
                print(status_line(self.board), flush=True)
                self.said = now
        self.board.unprinted.clear()
        self.write()

    def write(self, force: bool = False) -> None:
        """The dashboard as plain text into ``status.txt`` (written whole, then renamed: a reader never
        sees half of it), and the new attention lines onto ``events.log``."""
        now = time.monotonic()
        if not force and now - self.written < WRITE_EVERY_S:
            return
        self.written = now
        folder = self.board.folder
        if not folder.is_dir():
            return
        part = folder / "status.txt.part"
        with part.open("w") as out:
            plain = Console(file=out, width=STATUS_WIDTH, height=STATUS_HEIGHT, color_system=None, force_terminal=False)
            plain.print(dashboard(self.board))
        part.replace(folder / "status.txt")
        if self.board.fresh:
            with (folder / "events.log").open("a") as out:
                out.writelines(line + "\n" for line in self.board.fresh)
            self.board.fresh.clear()
