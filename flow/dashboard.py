"""A run's live dashboard (``python -m flow``): every instance's steps as they end, from the events
its worker sends (``flow.steps.run_steps``), drawn three ways from one model (``Board``):

- in a terminal, htop-like on the alternate screen (each frame drawn over the last, at once:
  Rich's live screen in the terminal's synchronized output; the summary left in the terminal's
  own buffer when the run ends), its boxes stacked: the run (block, run, kind, designs, workers,
  PDKs, its time and its designs started, passed, rejected, failed); the pipeline, a row a step
  (its instances waiting, running, ok, kept from before, rejected, failed, not run; its seconds;
  its tools' warnings and errors); the logging, a row a notice (time, notice, step and tool,
  count, message: each failure, each kind of rejection and of warning or error the first time,
  counted after); the rejections (each bound by the step that caught it, the failures); the
  results (one instance's metrics pre- and post-layout, or the designs that passed);
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
# how often the live view is drawn (s): a spinner's step, and seldom enough not to flicker
DRAW_EVERY_S = 0.5
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
    # what needs attention: (time, notice, step, tool, instance, message, kind)
    attention: deque[tuple[str, str, str, str, str, str, Any]] = field(default_factory=lambda: deque(maxlen=200))
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
            self._say("FAILED", step, "", item.key, f"{item.found[step]}  ({_shown(item.out / step / 'step.log')})")
        if state == "rejected":
            kind = (step, re.sub(r"[-+.\deE]+(?=\s|$|\))", "#", item.found[step]))
            self.rejections[(step, _bounds_of(item.found[step]))] += 1
            self.kinds[kind] += 1
            if self.kinds[kind] == 1:
                self._say("REJECTED", step, "", item.key, item.found[step].removeprefix(f"rejected at {step} "), kind)
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
            tool, level, message = parts[2], parts[3], " ".join(parts[4].removeprefix(": ").split())
            # one kind however its paths, quotes and numbers differ (the same warning in each PDK)
            kind = (tool, level, re.sub(r"\d+", "#", re.sub(r'"[^"]*"|\S*/\S*', "…", message))[:160])
            self.kinds[kind] += 1
            if self.kinds[kind] == 1:
                self._say(level, step, tool, item.key, _clean(message), kind)

    def _say(self, notice: str, step: str, tool: str, instance: str, text: str, kind: Any = None) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.attention.append((stamp, notice, step, tool, instance, text, kind))
        self.fresh.append(f"{stamp} {notice} {step}{f' ({tool})' if tool else ''} {instance}: {text}")
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


def _clean(message: str) -> str:
    """A tool's message as the logging table shows it: its own level word left out (the notice
    column says it: ``WARNING (SPECTRE-592): ...`` is ``SPECTRE-592: ...``), each path cut to its
    file's name (``…/FasterCap_Input_.lst``)."""
    message = re.sub(r"^(?:WARNING|Warning|ERROR|Error|warning|error)\b\s*:?\s*", "", message)
    message = re.sub(r"^\(([A-Z]+-\d+)\)\s*:?", r"\1:", message)
    return re.sub(r"(?:/[^\s\"/]+)+/([^\s\"/]+)", r"…/\1", message)


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
    """Seconds, a decimal below 100 alone: ``12.3``, ``154``."""
    return f"{seconds:.1f}" if seconds < 100 else f"{seconds:.0f}"


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


def _panel(body: Any, title: str) -> Panel:
    return Panel(body, title=title, title_align="left", border_style=FRAME)


def runs_panel(board: Board) -> Panel:
    """The run: its block, name, kind, designs, PDKs and workers, its folder; how long it has run,
    and its designs started, passed, rejected and failed."""
    ended, many = board.ended(), len(board.instances)
    first = Text.assemble(
        (board.block, f"bold {HEAD}"),
        " ",
        (board.run, "bold"),
        (f"  {board.kind} · {many} design{'s' if many != 1 else ''} · {board.workers} workers · ", DIM),
        ", ".join(board.pdks),
    )
    second = Text.assemble(
        (f"{_seconds(time.monotonic() - board.began)} s   ", DIM),
        (f"{many - ended['waiting']}/{many} started   ", TEXT),
        (f"{ended['passed']} passed   ", OK),
        (f"{ended['rejected']} rejected   ", REJECT),
        (f"{ended['failed']} failed   ", BAD),
        (_shown(board.folder), DIM),
    )
    return _panel(Group(first, second), "run")


def pipeline_panel(board: Board) -> Panel:
    """A row a step: its instances in each state, its seconds summed, its tools' warnings and errors."""
    found = _table(
        ("step", "left", 9),
        ("waiting", "right", 7),
        ("running", "right", 7),
        ("ok", "right", 4),
        ("kept", "right", 4),
        ("rejected", "right", 8),
        ("failed", "right", 6),
        ("not run", "right", 7),
        ("time (s)", "right", 8),
        ("notices", "left", 18),
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
    return _panel(found, "pipeline")


NOTICES = {
    "ERROR": f"bold {BAD}",
    "CRITICAL": f"bold {BAD}",
    "WARNING": WARN,
    "FAILED": f"bold {BAD}",
    "REJECTED": REJECT,
}


def logging_panel(board: Board, rows: int | None = None) -> Panel:
    """What needs attention, the newest first, a row each: when, the notice (a tool's error or
    warning, a failure, a rejection), the step and its tool, how often it came (each kind of
    warning counted once it was said), and the message, the instance it came first from after it."""
    found = Table(box=box.SIMPLE_HEAD, expand=True, pad_edge=False, header_style=f"bold {HEAD}", border_style=FRAME)
    found.add_column("time", style=DIM, no_wrap=True, width=8)
    found.add_column("notice", no_wrap=True, width=8)
    found.add_column("step (tool)", no_wrap=True, max_width=24)
    found.add_column("count", justify="right", no_wrap=True, width=5)
    found.add_column("message", overflow="fold", ratio=1)
    for stamp, notice, step, tool, instance, text, kind in list(reversed(board.attention))[: rows or None]:
        count = board.kinds[kind] if kind else 1
        found.add_row(
            stamp,
            Text(notice.lower(), style=NOTICES.get(notice, TEXT)),
            Text.assemble(step, (f" ({tool})" if tool else "", DIM)),
            Text(str(count), style=NOTICES.get(notice, TEXT) if count > 1 else DIM),
            Text.assemble(text, (f"  {instance}", DIM)),
        )
    if not board.attention:
        found.add_row("", "", "", "", Text("nothing yet", style=DIM))
    return _panel(found, "logging (newest first)")


def rejections_panel(board: Board) -> Panel:
    """Why designs left the run: each bound by the step that caught them, and the failures by step."""
    found = _table(("caught at", "left", 9), ("designs", "right", 7), ("bound", "left", 18))
    # a resumed run's rejection may be a step before the ones it runs: first
    order = {step: place for place, step in enumerate(board.steps)}
    for (step, bounds), n in sorted(board.rejections.items(), key=lambda kn: order.get(kn[0][0], -1)):
        found.add_row(step, Text(str(n), style=REJECT), bounds)
    failed = Counter(step for item in board.instances.values() for step, s in item.states.items() if s == "failed")
    for step, n in failed.items():
        found.add_row(step, Text(str(n), style=BAD), Text("failed", style=BAD))
    if not board.rejections and not failed:
        found.add_row("", "", Text("none", style=DIM))
    return _panel(found, "rejections")


def _rejection_rows(board: Board) -> int:
    failed = {step for item in board.instances.values() for step, s in item.states.items() if s == "failed"}
    return max(1, len(board.rejections) + len(failed))


def results_panel(board: Board, rows: int = 14) -> Panel:
    """The results: one instance's metrics pre- and post-layout and how each moved (its bounds'
    metrics first); several instances' that passed, the latest first, by their bounds' metrics (or
    their record's first)."""
    if len(board.instances) == 1:
        item = next(iter(board.instances.values()))
        record = item.record
        found = _table(
            ("pre-layout", "right", 11), ("post-layout", "right", 11), ("change", "right", 7), ("metric", "left", 16)
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
        title = f"results · {item.key} · {record.get('evidence', 'not recorded yet')}"
        if record.get("rejected"):
            title += f" · rejected at {record['rejected']['step']}"
        return _panel(found, title)
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
    return _panel(found, f"results · {len(passed)} passed (the latest first)")


def _results_rows(board: Board, rows: int = 14) -> int:
    if len(board.instances) == 1:
        item = next(iter(board.instances.values()))
        return max(1, min(rows, len(item.record.get("metrics") or {})))
    return max(1, min(rows, sum(item.ended == "passed" and bool(item.record) for item in board.instances.values())))


def dashboard(board: Board) -> Layout:
    """The whole terminal, its boxes stacked: the run, the pipeline, the logging (the room left), the
    rejections and the results."""
    root = Layout()
    root.split_column(
        Layout(runs_panel(board), size=4),
        Layout(pipeline_panel(board), size=len(board.steps) + 5),
        Layout(logging_panel(board, 60)),
        Layout(rejections_panel(board), size=_rejection_rows(board) + 5),
        Layout(results_panel(board), size=_results_rows(board) + 5),
    )
    return root


def summary(board: Board) -> Group:
    """What stays once the run ends: the same boxes, the logging's newest 40 rows."""
    return Group(
        runs_panel(board),
        pipeline_panel(board),
        logging_panel(board, 40),
        rejections_panel(board),
        results_panel(board),
    )


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
        self.written = self.said = self.drawn = -1e9

    def __enter__(self) -> Self:
        if self.console.is_terminal:
            # the alternate screen, as htop: each frame overwrites the last in place, nothing scrolled
            # or cleared first (an inline view redraws by clearing lines: it flickers); the summary
            # goes into the terminal's own buffer at the end
            self.live = Live(
                dashboard(self.board),
                console=self.console,
                auto_refresh=False,
                screen=True,
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
        if self.live is not None and now - self.drawn >= DRAW_EVERY_S:
            self.draw()
            self.drawn = now
        if len(self.board.instances) > SMALL and self.live is None:
            for line in self.board.unprinted:
                print(line, flush=True)
            if now - self.said >= STATUS_EVERY_S:
                print(status_line(self.board), flush=True)
                self.said = now
        self.board.unprinted.clear()
        self.write()

    def draw(self) -> None:
        """The live view drawn again whole, as one frame: inside the terminal's synchronized output
        (mode 2026: Ghostty, recent GNOME Terminal, iTerm2 show it at once; others ignore it), so a
        half-drawn frame never shows."""
        assert self.live is not None
        self.console.file.write("\x1b[?2026h")
        self.live.update(dashboard(self.board), refresh=True)
        self.console.file.write("\x1b[?2026l")
        self.console.file.flush()

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
