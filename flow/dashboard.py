"""A run's live dashboard (``python -m flow``): every instance's steps as they end, from the events
its worker sends (``flow.steps.run_steps``), drawn three ways from one model (``Board``):

- in a terminal, htop-like on the alternate screen (each frame drawn over the last, at once:
  Rich's live screen in the terminal's synchronized output; the summary left in the terminal's
  own buffer when the run ends), its boxes stacked: the run (block, run, kind, designs, workers,
  PDKs, its time and its designs started, passed, rejected, failed); the pipeline, a row a step
  (its instances waiting, running, ok, kept from before, rejected, failed, not run; its seconds;
  its tools' warnings and errors); the logging, a row a notice (time, notice, step, tool,
  instance, count, the tool's message, notes: each failure, each kind of rejection and of warning
  or error the first time, counted after); the results (one instance's metrics pre- and
  post-layout, or each design that ended: passed with the bounds it met, rejected with the step
  and bound, or failed with the step); the viewer's page of the run;
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
from typing import Any, NamedTuple, Self
from urllib.request import urlopen

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from flow.logs import known
from flow.logs import level as level_of
from flow.web import PORT

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
# a running step's spinner, a frame a drawing: picked by the clock, as each drawing builds the board
# anew (a Rich Spinner made each frame would stay on its first)
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# a status file's size, as a large terminal's
STATUS_WIDTH, STATUS_HEIGHT = 200, 56
# the results' most metrics (rows) and, of several instances, the most instances (columns)
RESULT_ROWS, COLUMNS = 24, 8
LEVELS = {"ERROR": "error", "CRITICAL": "error", "WARNING": "warning", "KNOWN": "known"}


class Notice(NamedTuple):
    """A row of what needs attention: when, the notice (a tool's level, ``FAILED``, ``REJECTED``),
    the step, its tool, the instance it came from first, the message as the tool said it, a note
    (why a known one is left: ``flow.logs.KNOWN``; a failure's log) and its kind (counted)."""

    stamp: str
    notice: str
    step: str
    tool: str
    instance: str
    text: str
    note: str = ""
    kind: Any = None
    known: bool = False


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
    # what needs attention, a row each
    attention: deque[Notice] = field(default_factory=lambda: deque(maxlen=200))
    kinds: Counter[Any] = field(default_factory=Counter)
    rejections: Counter[tuple[str, str]] = field(default_factory=Counter)
    began: float = field(default_factory=time.monotonic)
    viewer: bool | None = None  # whether the viewer answered when last asked (None: not asked)
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
            self._say(Notice("", "FAILED", step, "", item.key, item.found[step], _shown(item.out / step / "step.log")))
        if state == "rejected":
            kind = (step, re.sub(r"[-+.\deE]+(?=\s|$|\))", "#", item.found[step]))
            self.rejections[(step, _bounds_of(item.found[step]))] += 1
            self.kinds[kind] += 1
            if self.kinds[kind] == 1:
                text = item.found[step].removeprefix(f"rejected at {step} ")
                self._say(Notice("", "REJECTED", step, "", item.key, text, kind=kind))
        if step == "results" and state in ("ok", "done"):
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
            raw = parts[4].removeprefix(": ")
            if level_of(raw)[3]:
                continue  # a message's continued line, which the step's counts leave out too
            tool, level, message = parts[2], parts[3], " ".join(raw.split())
            entry = known(tool, message)
            # one kind however its paths, quotes and numbers differ (the same warning in each PDK)
            # (a kind a step's: the same warning in sim and pexsim counted apart, as their counts are)
            kind = (
                step,
                tool,
                level,
                entry is not None,
                re.sub(r"\d+", "#", re.sub(r'"[^"]*"|\S*/\S*', "…", message))[:160],
            )
            self.kinds[kind] += 1
            if self.kinds[kind] == 1:
                note = entry.reason if entry else ""
                self._say(Notice("", level, step, tool, item.key, _clean(message), note, kind, entry is not None))

    def _say(self, notice: Notice) -> None:
        notice = notice._replace(stamp=time.strftime("%H:%M:%S"))
        self.attention.append(notice)
        tool = f" ({notice.tool})" if notice.tool else ""
        note = f"  [{'known: ' if notice.known else ''}{notice.note}]" if notice.note else ""
        self.fresh.append(f"{notice.stamp} {notice.notice} {notice.step}{tool} {notice.instance}: {notice.text}{note}")
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


def _spun() -> str:
    """The spinner's frame now: the next one each drawing."""
    return SPIN[int(time.monotonic() / DRAW_EVERY_S) % len(SPIN)]


def _seconds(seconds: float) -> str:
    """Seconds, a decimal below 100 alone: ``12.3``, ``154``."""
    return f"{seconds:.1f}" if seconds < 100 else f"{seconds:.0f}"


# a metric's unit by its name's last word, and its SI prefixes
_UNITS = {"s": "s", "j": "J", "v": "V", "w": "W", "hz": "Hz", "ohm": "Ω", "f": "F", "a": "A"}
# a rate's unit, its name's last two words (``droop_v_s``: volts a second)
_RATES = {"v_s": "V/s", "a_s": "A/s"}
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
    last word: ``_s``, ``_j``, ``_v``, ``_hz``, ``_ohm``, ``_um2`` ...; a rate's its last two,
    ``_v_s``) with an SI prefix, three
    significant digits; not measured, a dash."""
    if number is None:
        return "–"
    if isinstance(number, bool):
        return "yes" if number else "no"
    if not isinstance(number, (int, float)):
        return str(number)
    rate = "_".join(name.split("_")[-2:])
    if rate in _RATES and name.count("_") >= 2:
        scale, prefix = next(((s, p) for s, p in _PREFIXES if abs(number) >= s), _PREFIXES[-1])
        return f"{number / scale:.3g} {prefix}{_RATES[rate]}" if number else f"0 {_RATES[rate]}"
    unit = name.rsplit("_", 1)[-1] if "_" in name else ""
    if unit == "um2":
        return f"{number:.3g} µm²"
    if unit in _UNITS and number:
        scale, prefix = next(((s, p) for s, p in _PREFIXES if abs(number) >= s), _PREFIXES[-1])
        return f"{number / scale:.3g} {prefix}{_UNITS[unit]}"
    return f"{number:.4g}"


# ---------------------------------------------------------------- the panels


def _table(*columns: tuple[str, str, int], plain: bool = False) -> Table:
    """A table of these columns (name, justification, width), the last taking what room is left
    (``plain``: only its content's, for the summary left in the terminal's buffer)."""
    found = Table(
        box=box.SIMPLE_HEAD, expand=not plain, pad_edge=False, header_style=f"bold {HEAD}", border_style=FRAME
    )
    for place, (name, justify, width) in enumerate(columns):
        last = place == len(columns) - 1
        found.add_column(
            name,
            justify=justify,  # ty: ignore[invalid-argument-type]
            no_wrap=True,
            overflow="ellipsis",
            width=None if last else width,
            min_width=width if last else None,
            ratio=1 if last and not plain else None,
        )
    return found


def _count(n: int, style: str) -> Text:
    return Text(str(n) if n else "·", style=style if n else DIM)


def _panel(body: Any, title: str, plain: bool = False) -> Any:
    """A box of the live view; ``plain``, a heading over the content alone (the summary left in the
    terminal's buffer: no border, no line wider than its content, so a narrower window rewraps
    nothing but long messages)."""
    if plain:
        return Group(Text(title, style=f"bold {HEAD}"), Padding(body, (0, 0, 1, 2), expand=False))
    return Panel(body, title=title, title_align="left", border_style=FRAME)


def runs_panel(board: Board, plain: bool = False) -> Any:
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
    return _panel(Group(first, second), "run", plain)


def pipeline_panel(board: Board, plain: bool = False) -> Any:
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
        plain=plain,
    )
    for step in board.steps:
        c = board.by_step(step)
        seconds = sum(item.seconds.get(step, 0.0) for item in board.instances.values())
        said = Text()
        for (tool, level), n in sorted(board.counts.get(step, Counter()).items()):
            style = {"WARNING": WARN, "KNOWN": DIM}.get(level, BAD)
            said.append(f"{tool} {n} {LEVELS.get(level, level.lower())}  ", style=style)
        label = Text(step, style=f"bold {RUN}" if c["running"] else TEXT)
        found.add_row(
            Text.assemble((_spun(), RUN), " ", label) if c["running"] else Text.assemble("  ", label),
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
    return _panel(found, "pipeline", plain)


NOTICES = {
    "ERROR": f"bold {BAD}",
    "CRITICAL": f"bold {BAD}",
    "WARNING": WARN,
    "KNOWN": DIM,
    "FAILED": f"bold {BAD}",
    "REJECTED": REJECT,
}


def logging_panel(board: Board, rows: int | None = None, plain: bool = False) -> Any:
    """What needs attention, the newest first, a row each: when, the notice (a tool's error or
    warning, a failure, a rejection), the step, its tool (the logger's full name), the instance it
    came from first, how often it came (each kind counted once it was said), the message as the
    tool said it, and a note: why a known one is left (``flow.logs.KNOWN``; its row dimmed, so a
    new one stands out), a failure's log."""
    found = Table(
        box=box.SIMPLE_HEAD, expand=not plain, pad_edge=False, header_style=f"bold {HEAD}", border_style=FRAME
    )
    found.add_column("time", style=DIM, no_wrap=True, width=8)
    found.add_column("notice", no_wrap=True, width=8)
    found.add_column("step", no_wrap=True)
    found.add_column("tool", style=DIM, no_wrap=True)
    found.add_column("instance", style=DIM, no_wrap=True)
    found.add_column("count", justify="right", no_wrap=True, width=5)
    found.add_column("message", overflow="fold", ratio=None if plain else 3, max_width=90 if plain else None)
    found.add_column("notes", style=DIM, overflow="fold", ratio=None if plain else 2, max_width=60 if plain else None)
    for row in list(reversed(board.attention))[: rows or None]:
        count = board.kinds[row.kind] if row.kind else 1
        style = DIM if row.known else NOTICES.get(row.notice, TEXT)
        found.add_row(
            row.stamp,
            Text(LEVELS.get(row.notice, row.notice.lower()), style=style),
            row.step,
            row.tool,
            row.instance,
            Text(str(count), style=style if count > 1 else DIM),
            Text(row.text, style=DIM if row.known else TEXT),
            row.note,
        )
    if not board.attention:
        found.add_row("", "", "", "", "", "", Text("nothing yet", style=DIM), "")
    return _panel(found, "logging", plain)


def outcome(item: _Instance, short: bool = False) -> Text:
    """How an instance came out: passed, with how many of its bounds it met (``7/7 bounds``; those
    its evidence could not judge named apart), rejected with the step and the bounds it missed, or
    failed with the step; nothing while it runs. ``short``: a table cell's (``passed 7/7``, the
    rejection's step and bounds without their values)."""
    if item.ended == "passed":
        total, unjudged = len(item.bounds), len(item.record.get("unjudged") or [])
        if short:
            return Text(f"passed {total - unjudged}/{total}" if total else "passed", style=OK)
        met = f"{total - unjudged}/{total} bounds" if total else "no bounds"
        return Text.assemble(("passed", OK), f" · {met}", (f", {unjudged} unjudged" if unjudged else "", DIM))
    if item.ended == "rejected":
        step = next(step for step, state in item.states.items() if state == "rejected")
        said = f"rejected at {step}: {_bounds_of(item.found[step])}" if short else item.found[step]
        return Text(said, style=REJECT)
    if item.ended == "failed":
        steps = [step for step, state in item.states.items() if state == "failed"]
        return Text(f"failed at {', '.join(steps) or 'worker'}", style=BAD)
    return Text("")


def results_panel(board: Board, rows: int = RESULT_ROWS, plain: bool = False) -> Any:
    """The results: one instance's metrics pre- and post-layout and how each moved (its bounds'
    metrics first), its outcome in the title; several instances' as the viewer's table, a column
    each that ended (those that passed, then those rejected, then those failed; the first
    ``COLUMNS``), a row its outcome (``outcome``), each metric (every one their records hold, the
    bounds' first) and its evidence."""
    if len(board.instances) == 1:
        item = next(iter(board.instances.values()))
        record = item.record
        found = _table(
            ("pre-layout", "right", 11),
            ("post-layout", "right", 11),
            ("change", "right", 7),
            ("metric", "left", 16),
            plain=plain,
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
        said = outcome(item).plain
        return _panel(found, f"{title} · {said}" if said else title, plain)
    ended = _ended(board)[:COLUMNS]
    names = _metric_names(board)[:rows]
    found = Table(box=box.SIMPLE_HEAD, expand=False, pad_edge=False, header_style=f"bold {HEAD}", border_style=FRAME)
    found.add_column("metric", no_wrap=True)
    said = [outcome(item, short=True) for item in ended]
    for item, text in zip(ended, said, strict=True):
        wide = max(len(item.key), len(text.plain))
        found.add_column(
            item.key, justify="right", overflow="fold", min_width=min(32, wide), max_width=max(32, len(item.key))
        )
    found.add_row(Text("outcome", style=DIM), *said)
    for name in names:
        found.add_row(name, *(value(name, (item.record.get("metrics") or {}).get(name)) for item in ended))
    found.add_row(Text("evidence", style=DIM), *(Text(item.record.get("evidence", ""), style=DIM) for item in ended))
    if not ended:
        found.add_row(Text("none ended yet", style=DIM))
    many = sum(bool(item.ended) for item in board.instances.values())
    shown = f" · the first {COLUMNS} of {many}" if many > COLUMNS else ""
    return _panel(found, f"results{shown}", plain)


def _ended(board: Board) -> list[_Instance]:
    """The instances that ended: those that passed, then those rejected, then those failed."""
    order = {"passed": 0, "rejected": 1, "failed": 2}
    return sorted((item for item in board.instances.values() if item.ended), key=lambda item: order[item.ended])


def _metric_names(board: Board) -> list[str]:
    """Every metric the ended instances' records hold (a number or a flag), the bounds' first."""
    names = dict.fromkeys(next(iter(board.instances.values())).bounds if board.instances else ())
    for item in _ended(board):
        for name, number in (item.record.get("metrics") or {}).items():
            if isinstance(number, (int, float)):
                names.setdefault(name)
    return list(names)


def _results_rows(board: Board, rows: int = RESULT_ROWS) -> int:
    if len(board.instances) == 1:
        item = next(iter(board.instances.values()))
        return max(1, min(rows, len(item.record.get("metrics") or {})))
    return max(1, min(rows, len(_metric_names(board))) + 2)


def dashboard(board: Board) -> Layout:
    """The whole terminal, its boxes stacked: the run, the pipeline, the logging (the room left) and
    the results; the viewer's page last."""
    root = Layout()
    root.split_column(
        Layout(runs_panel(board), size=4),
        Layout(pipeline_panel(board), size=len(board.steps) + 5),
        Layout(logging_panel(board, 60)),
        Layout(results_panel(board), size=_results_rows(board) + 5),
        Layout(Padding(viewer_line(board), (0, 1)), size=1),
    )
    return root


def summary(board: Board) -> Group:
    """What stays in the terminal's buffer once the run ends: the same boxes, plain (headings, no
    borders, no line wider than its content: a narrower window rewraps only long messages), the
    logging's newest 40 rows."""
    return Group(
        runs_panel(board, plain=True),
        pipeline_panel(board, plain=True),
        logging_panel(board, 40, plain=True),
        results_panel(board, plain=True),
        viewer_line(board),
    )


def viewer_url(board: Board) -> str:
    """The viewer's page of this run (its table, once the table step has written it)."""
    return f"http://localhost:{PORT}/#block={board.block}&run={board.run}/{board.folder.name}"


def viewer_up() -> bool:
    """Whether the viewer answers on this machine: its catalog served (``python -m flow web.serve``)."""
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/data/sweep/catalog.json", timeout=0.5) as answer:
            return answer.status == 200
    except OSError:
        return False


def viewer_line(board: Board) -> Text:
    """The last line: the run's page in the viewer, and whether the viewer is up (checked as the run
    starts and as it ends: ``Board.viewer``)."""
    state = (
        ("up", OK)
        if board.viewer
        else ("not running: python -m flow web.serve", WARN)
        if board.viewer is False
        else ("", DIM)
    )
    return Text.assemble(("viewer  ", f"bold {HEAD}"), (viewer_url(board), TEXT), "  ", state)


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
        self.board.viewer = viewer_up()
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
        self.board.viewer = viewer_up()
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
