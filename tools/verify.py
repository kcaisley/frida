"""Verify a block end to end: one of its runs through the results step, every number its records
hold, and what changed against a baseline.

    python tools/verify.py --block comp --run frida1 --pdks tsmc65 --save build/verify/comp.json
    python tools/verify.py --block comp --run frida1 --pdks tsmc65 --baseline build/verify/comp.json
    python tools/verify.py --block comp --run frida1 --pdks tsmc65 --from results --baseline build/verify/comp.json

The run goes through the flow's own steps (``python -m flow --block B --run R --to results``:
netlist, presim, layout, signoff, extraction, postsim, the record); ``--from`` a later step works
in the run's latest folder, where a step whose output is complete is kept (make's rule):
``--from results`` takes its records as they are, or, its ``results/`` folders deleted, analyses
its kept simulations again. ``--pdks`` keeps the run to those kits; ``--workers`` (else
``PORT_WORKERS``) caps its process pool. Each instance's record (``<pdk>/<name>/instance.json``)
gives its numbers: its metrics, and the pre-layout ones beside post-layout metrics
(``prelayout``), by dotted name. ``--save`` writes them as one JSON; ``--baseline`` lists every
number that changed beyond ``--rtol`` (relative, 1e-6 by default), each added or removed, and each
instance added or removed. The exit status is 0 where nothing changed (or no baseline), 1 where
something did, 2 where an instance failed. ``--folder`` collects a run's folder as it is
(``build/<block>/<run>/<stamp>``, of any checkout: a baseline from before a change), running
nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

if os.environ.get("PORT_WORKERS"):
    # the flow's pool takes min(designs, processors) (flow.pipeline.workers); the run's spawned
    # workers import this file again and take the same cap from the environment
    os.cpu_count = lambda: int(os.environ["PORT_WORKERS"])

# the checkout's flow, run as a script from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def numbers(record: dict[str, Any]) -> dict[str, Any]:
    """An instance record's numbers by dotted name: its ``metrics`` and, beside post-layout ones,
    its ``prelayout`` metrics, nested values flattened (``metrics.delay_s``, ``metrics.codes.3``);
    a number not measured stays None, a string is no number; ``error`` where the instance failed."""
    found: dict[str, Any] = {}

    def flatten(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                flatten(f"{prefix}.{key}", item)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                flatten(f"{prefix}.{index}", item)
        elif value is None or isinstance(value, (bool, int, float)):
            found[prefix] = value

    for part in ("metrics", "prelayout"):
        if isinstance(record.get(part), dict):
            flatten(part, record[part])
    if record.get("error"):
        found["error"] = str(record["error"]).strip().splitlines()[-1]
    return found


def collect(folder: Path) -> dict[str, dict[str, Any]]:
    """Each instance's numbers (``numbers``) in a run's folder, by ``<pdk>/<name>``."""
    return {
        f"{path.parent.parent.name}/{path.parent.name}": numbers(json.loads(path.read_text()))
        for path in sorted(folder.glob("*/*/instance.json"))
    }


class Kind(Enum):
    """What a difference from the baseline is."""

    ADDED = auto()
    REMOVED = auto()
    CHANGED = auto()


@dataclass(frozen=True)
class Change:
    """One difference from the baseline: an instance's number ``name`` (None: the instance itself)
    added, removed or changed from ``before`` to ``after`` (None on the side that lacks it)."""

    instance: str
    name: str | None
    kind: Kind
    before: Any = None
    after: Any = None


def differs(before: Any, after: Any, rtol: float) -> bool:
    """Whether two recorded values differ: numbers by more than ``rtol`` of the larger magnitude
    (NaN alike only to NaN, an infinity only to the same one), anything else (None, a flag, an
    error) by inequality."""
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (before, after)):
        return before != after or isinstance(before, bool) != isinstance(after, bool)
    if math.isnan(before) or math.isnan(after):
        return not (math.isnan(before) and math.isnan(after))
    if math.isinf(before) or math.isinf(after):
        return before != after
    return abs(after - before) > rtol * max(abs(before), abs(after))


def changes(
    baseline: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]], rtol: float
) -> tuple[list[Change], int]:
    """Every change from ``baseline`` to ``current`` (instances by name, each its numbers): an
    instance added or removed, a number added, removed or changed beyond ``rtol``; and how many
    numbers both hold (those compared)."""
    found: list[Change] = []
    compared = 0
    for instance in sorted(set(baseline) | set(current)):
        if instance not in baseline:
            found.append(Change(instance, None, Kind.ADDED))
            continue
        if instance not in current:
            found.append(Change(instance, None, Kind.REMOVED))
            continue
        before, after = baseline[instance], current[instance]
        for name in sorted(set(before) | set(after)):
            if name not in before:
                found.append(Change(instance, name, Kind.ADDED, after=after[name]))
            elif name not in after:
                found.append(Change(instance, name, Kind.REMOVED, before=before[name]))
            else:
                compared += 1
                if differs(before[name], after[name], rtol):
                    found.append(Change(instance, name, Kind.CHANGED, before[name], after[name]))
    return found, compared


def _shown(value: Any) -> str:
    """A recorded value as a line shows it: a float to six significant digits."""
    return f"{value:.6g}" if isinstance(value, float) else str(value)


def report(found: list[Change], compared: int, rtol: float) -> str:
    """The changes as lines, then their count: ``<instance> <name>: <before> -> <after>
    (<relative change>)``, ``<instance> <name>: added <after>`` or ``removed (was <before>)``, an
    instance added or removed on a line of its own."""
    lines = []
    for change in found:
        word = change.kind.name.lower()
        if change.name is None:
            lines.append(f"{change.instance}: {word}")
        elif change.kind is Kind.ADDED:
            lines.append(f"{change.instance} {change.name}: added {_shown(change.after)}")
        elif change.kind is Kind.REMOVED:
            lines.append(f"{change.instance} {change.name}: removed (was {_shown(change.before)})")
        else:
            before, after = change.before, change.after
            measured = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (before, after))
            relative = f" ({(after - before) / abs(before):+.3%})" if measured and before else ""
            lines.append(f"{change.instance} {change.name}: {_shown(before)} -> {_shown(after)}{relative}")
    numbers_changed = sum(1 for change in found if change.name is not None)
    lines.append(f"{numbers_changed} numbers changed beyond rtol {rtol:g} ({compared} compared)")
    return "\n".join(lines)


def run(block: str, name: str, start: str, pdks: list[str] | None) -> tuple[Path, str | None]:
    """The block's run ``name`` from step ``start`` through results (``python -m flow``'s steps,
    in ``pdks`` alone where given); the folder those steps worked in (the one the command line chose,
    not the newest by name, which another session's run may be) and the flow's failure, if any."""
    import flow.__main__ as cli
    from flow.sweep import runner

    if pdks:
        runner.PDKS = tuple(pdks)
        every = cli._pdks
        cli._pdks = lambda block, run, spec: [pdk for pdk in every(block, run, spec) if pdk in pdks]
    chosen: list[Path] = []
    choose = cli._run_dir

    def recorded(*args: Any) -> tuple[Path, str]:
        folder, how = choose(*args)
        chosen.append(folder)
        return folder, how

    cli._run_dir = recorded
    failure = None
    try:
        cli.main(["--block", block, "--run", name, "--from", start, "--to", "results"])
    except SystemExit as stop:
        if stop.code not in (None, 0):
            failure = str(stop.code)
    finally:
        cli._run_dir = choose
    if not chosen or not (chosen[-1] / "run.json").exists():
        raise SystemExit(failure or f"no run of {block}'s {name} made by its steps")
    return chosen[-1], failure


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(prog="python tools/verify.py", description=__doc__.split("\n\n")[0])
    command.add_argument("--block", required=True, help="a block on the pipeline")
    command.add_argument("--run", required=True, help="one of the block's runs")
    command.add_argument("--pdks", help="the kits to run in, comma-separated (the run's own by default)")
    command.add_argument("--from", dest="start", default="netlist", help="the first step (netlist: a new run)")
    command.add_argument("--workers", type=int, help="at most this many processes (else PORT_WORKERS)")
    command.add_argument("--folder", type=Path, help="collect this run's folder as it is, running nothing")
    command.add_argument("--baseline", type=Path, help="a JSON this tool saved, to compare against")
    command.add_argument("--save", type=Path, help="write the numbers here as JSON")
    command.add_argument("--rtol", type=float, default=1e-6, help="relative tolerance of a number (1e-6)")
    args = command.parse_args(argv)
    if args.workers:
        os.environ["PORT_WORKERS"] = str(args.workers)
        os.cpu_count = lambda: args.workers
    pdks = args.pdks.split(",") if args.pdks else None
    folder, failure = (args.folder, None) if args.folder else run(args.block, args.run, args.start, pdks)
    instances = {key: value for key, value in collect(folder).items() if pdks is None or key.split("/", 1)[0] in pdks}
    count = f"{len(instances)} instance{'' if len(instances) == 1 else 's'}"
    print(f"verify: {args.block} {args.run}, {count} in {folder}")
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        saved = {"block": args.block, "run": args.run, "folder": str(folder), "instances": instances}
        args.save.write_text(json.dumps(saved, indent=1, sort_keys=True) + "\n")
        print(f"saved {args.save}")
    status = 0
    if args.baseline:
        baseline = json.loads(args.baseline.read_text())["instances"]
        found, compared = changes(baseline, instances, args.rtol)
        print(f"against {args.baseline}:")
        print(report(found, compared, args.rtol))
        status = 1 if found else 0
    if failure or any("error" in values for values in instances.values()):
        print(f"failed: {failure or 'an instance recorded an error'}")
        status = 2
    return status


if __name__ == "__main__":  # the flow's spawned workers import this file: the cap above, not the run
    sys.exit(main())
