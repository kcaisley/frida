"""The flow's one entry point: ``python -m flow`` lists what it runs.

A block on the pipeline (docs/pipeline.md) is run by verbs, each over the block's design space and
named instances (its ``sweep.py``):

    python -m flow run <block> [--pdk P ...] [--instance I ...] [--missing] [--workers N]
    python -m flow layout <block> [--pdk P ...] [--instance I ... [--auto] [--plan]] [--list] [--no-pex] [--redo] [--workers N]
    python -m flow table <block> [--workers N]
    python -m flow plot <block> [FIGURE ...] --from DIR [--from DIR ...] [--backend matplotlib|web]
    python -m flow opt <block> --problem P [--pdk P] [--budget N] [--workers N] [--best N] [--finalists N]
    python -m flow page <block> [--pdk P ...] [--instance I ...] [--run-dir DIR]

An instance ``I`` is a named instance, an instance's label (``grid(name, parameter=value, ...)``) or its
digest; ``--list`` prints the design space's, digest and label. ``layout`` takes any block with a
``params``, a ``subckt`` and a ``sweep``, on the pipeline or not: without ``--instance`` it lays
out the newest run's instances by ALIGN into their records; with it, each instance picked by
ALIGN, placed as its generator (or its hand-written floorplan) states, or, with ``--auto``, by
ALIGN on its own, into ``build/<block>/layout/<stamp>/<pdk>/<name>/``: the netlist, the
constraints, the GDS and its signoff. ``--plan`` stops after the netlist and the constraints (ALIGN's design directory).
``plot`` draws a sweep run's records' figures, or the figures of a directory of captures.

A block not yet on the pipeline, and the flow's own tools, keep their targets: ``python -m flow
<module>.<target>`` runs a public function without arguments of that ``targets.py``, which makes its
own run directory under ``build/``.
"""

from __future__ import annotations

import argparse
import inspect
import sys
import time
from importlib import import_module
from pathlib import Path

# each block's targets module, imported when it is listed or run: a block that no longer imports
# (one not yet ported to the shared layout step) fails alone, when it is run
BLOCKS = (
    *("adc", "bias", "clkgen", "cml", "csa", "delay", "disc", "follower", "idac", "latch", "layout"),
    *("lvshift", "ota", "pi", "ringamp", "schmitt", "sweep", "web"),
)


def block_targets(block: str):
    """A block's targets module (``flow.<block>.targets``)."""
    return import_module(f"flow.{block}.targets")


def targets(module) -> dict:
    """The targets a ``targets.py`` defines, by name, in source order."""
    return {
        name: function
        for name, function in vars(module).items()
        if inspect.isfunction(function) and function.__module__ == module.__name__ and not name.startswith("_")
    }


VERBS = ("run", "layout", "table", "plot", "opt", "page")


def layout_blocks() -> list[str]:
    """The blocks the layout verb takes: those with a ``params``, a ``subckt`` and a ``sweep`` (by
    their files: a block that no longer imports is one still, and fails when it is laid out)."""
    from flow.sweep import runner

    folder = Path(__file__).resolve().parent
    return [
        block
        for block in runner.sweep_blocks()
        if all((folder / block.replace(".", "/") / f"{stage}.py").is_file() for stage in ("params", "subckt"))
    ]


def pipeline_blocks() -> list[str]:
    """The blocks on the pipeline: those whose ``sweep.py`` gives ``runs`` (one that no longer
    imports, a block not yet ported, gives none)."""
    from flow.sweep import runner

    def on_pipeline(block: str) -> bool:
        try:
            return hasattr(import_module(f"flow.{block}.sweep"), "runs")
        except ImportError:
            return False

    return [block for block in runner.sweep_blocks() if on_pipeline(block)]


def parser() -> argparse.ArgumentParser:
    """The verbs' arguments."""
    from flow.sweep import runner

    verbs = argparse.ArgumentParser(prog="python -m flow", description=__doc__.split("\n\n")[0])
    commands = verbs.add_subparsers(dest="verb", required=True)
    for verb, workers, text in (
        ("run", 36, "characterize the block's instances in a fresh run"),
        ("layout", 28, "lay out the newest run's instances, or named instances, by ALIGN"),
        ("table", 16, "export the newest runs as the viewer's tables"),
        ("plot", 0, "draw a sweep run's or captures' figures"),
        ("page", 0, "write a laid-out instance's page: its metrics, netlist, schematic, 2-D and 3-D views"),
    ):
        command = commands.add_parser(verb, help=text, description=text)
        # the table: a block on the pipeline, or one laid out before it is characterized
        laid_out = sorted({*pipeline_blocks(), *layout_blocks()})
        blocks = {"layout": layout_blocks(), "table": laid_out, "page": laid_out}
        command.add_argument("block", choices=blocks.get(verb) or pipeline_blocks())
        if verb == "plot":
            command.add_argument("figures", nargs="*", metavar="FIGURE", help="the figures, by name (default: all)")
            command.add_argument("--from", dest="sources", type=Path, action="append", required=True)
            command.add_argument("--backend", choices=("matplotlib", "web"), default="matplotlib")
        if verb != "table":
            command.add_argument("--pdk", action="append", choices=runner.PDKS, dest="pdks")
            command.add_argument("--instance", action="append", dest="instances", metavar="I")
        if verb == "run":
            command.add_argument("--missing", action="store_true", help="the newest run's failed or missing ones")
        if verb == "page":
            command.add_argument("--run-dir", type=Path, help="an instance's layout directory (<run>/<pdk>/<name>)")
        if verb == "layout":
            floorplan = command.add_mutually_exclusive_group()
            floorplan.add_argument("--manual", action="store_true", help="as its generator places it (default)")
            floorplan.add_argument("--auto", action="store_true", help="from ALIGN's placement")
            command.add_argument("--plan", action="store_true", help="the netlist and constraints only, no ALIGN")
            command.add_argument("--list", action="store_true", help="print the design space's instances, no layout")
            command.add_argument("--quiet", action="store_true", help="the flow's steps alone: no tool's own output")
            command.add_argument(
                "--signoff",
                choices=("open", "calibre"),
                default="open",
                help="DRC and LVS by the open tools (gdscheck, KLayout: the default) or the kit's Calibre",
            )
            command.add_argument(
                "--no-pex", action="store_true", help="no extraction (KLayout-PEX, FasterCap: minutes a block)"
            )
            if verb == "layout":
                command.add_argument(
                    "--redo", action="store_true", help="lay out a run's instances already laid out clean too"
                )
        if workers:
            command.add_argument("--workers", type=int, default=workers)
    text = "optimize the block over its parameters for one of its problems (its opt.py)"
    command = commands.add_parser("opt", help=text, description=text)
    command.add_argument("block", choices=[block for block in pipeline_blocks() if _has_opt(block)])
    command.add_argument("--problem", required=True, help='a problem by its label, as "adc(bits=12)"')
    command.add_argument("--pdk", choices=runner.PDKS, default="tsmc65")
    command.add_argument("--budget", type=int, default=500, help="trials in the study, those before included")
    command.add_argument("--workers", type=int, default=48)
    command.add_argument("--best", type=int, metavar="N", help="print the study's N best feasible designs, run none")
    command.add_argument(
        "--finalists", type=int, metavar="N", help="characterize the study's N best feasible designs in full"
    )
    command.add_argument("--table", action="store_true", help="export the study as the viewer's table, run none")
    return verbs


def _has_opt(block: str) -> bool:
    """Whether a block on the pipeline gives optimization problems (an opt.py)."""
    from importlib.util import find_spec

    return find_spec(f"flow.{block}.opt") is not None


def verb(argv: list[str]) -> None:
    """Run one verb (``parser``)."""
    from flow.sweep import runner

    args = parser().parse_args(argv)
    if args.verb == "opt":
        from flow.opt import runner as opt

        if args.table:
            print(opt.table(args.block, args.pdk, args.problem, args.workers))
        elif args.best:
            for entry in opt.best(args.block, args.pdk, args.problem)[: args.best]:
                print(entry)
        elif args.finalists:
            for entry in opt.finalize(args.block, args.pdk, args.problem, args.finalists, args.workers):
                print(entry)
        else:
            print(opt.optimize(args.block, args.pdk, args.problem, args.budget, args.workers))
        return
    if args.verb == "page":
        from flow.web.page import newest, page

        if args.run_dir:
            print(page(args.run_dir))
            return
        if not args.instances:
            raise SystemExit("a page takes --instance (its name or digest) or --run-dir")
        written = []
        for pdk in args.pdks or runner.PDKS:
            for name in args.instances:
                try:
                    written.append(page(newest(args.block, pdk, name)))
                except LookupError:  # not laid out in this PDK
                    continue
        if not written:
            raise SystemExit(f"no layout of {', '.join(args.instances)} under build/{args.block}/layout/")
        print(*written, sep="\n")
        return
    pdks = tuple(args.pdks or runner.PDKS) if args.verb != "table" else runner.PDKS
    if args.verb == "run":
        runner.run([args.block], pdks, args.workers, failed=args.missing, names=args.instances)
    elif args.verb == "table":
        runner.table([args.block], args.workers)
    elif args.verb == "plot":
        for path in __import__("flow.plot", fromlist=["figures"]).figures(
            args.block,
            args.sources,
            args.figures,
            backend=args.backend,
            pdks=args.pdks or (),
            instances=args.instances or (),
        ):
            print(path)
    elif args.list:
        for pdk in pdks:
            for ident, (label, _params) in runner.labelled_space(args.block, pdk).items():
                print(pdk, ident, label)
    elif not args.instances:
        if args.block not in pipeline_blocks():
            raise SystemExit(
                f"{args.block} has no characterization runs to lay out: pick instances with --instance "
                f"(a name, a label or a digest; python -m flow layout {args.block} --list prints them)"
            )
        runner.layout([args.block], args.workers, pdks=pdks, pex=not args.no_pex, redo=args.redo)
    else:
        layout_instances(
            args.block,
            args.instances,
            pdks,
            auto=args.auto,
            plan_only=args.plan,
            quiet=args.quiet,
            signoff=args.signoff,
            pex=not args.no_pex,
        )


def layout_instances(
    block: str,
    names: list[str],
    pdks: tuple[str, ...],
    *,
    auto: bool,
    plan_only: bool,
    quiet: bool = False,
    signoff: str = "open",
    pex: bool = True,
) -> None:
    """Lay out the instances ``names`` pick (``runner.select``; ``all``: every named one) of
    ``block`` in each of ``pdks``, one run a call, ``build/<block>/layout/<stamp>/`` (not a
    characterization run of the block, ``build/<block>/<stamp>/``): each instance into
    ``<pdk>/<name>/`` there, a named instance by its name, a grid's by its digest; by the shared
    step (``flow.layout.step.layout_one``), or by the block's own ``layout.py``'s ``layout_named``
    into ``<name>/`` where it has one. ``plan_only``: the netlist and the constraints alone (ALIGN's
    design directory). The console is the flow's log (``flow.layout.logs``: its steps as Python's
    logging has them, in ALIGN's format) with ALIGN's own output and the checkers' as they run,
    unless ``quiet``; each instance's ``flow.log`` keeps the flow's lines, ALIGN and every tool their
    own logs; an instance ends with its steps, a line each (its time, state and statistics, as its
    page has them)."""
    from flow import new_run, pipeline
    from flow.layout import run as align_run
    from flow.layout.step import layout_one
    from flow.sweep import runner

    named = pipeline.names(import_module(f"flow.{block}.sweep"))
    names = list(named) if names == ["all"] else names
    import logging

    from flow.layout import logs
    from flow.layout.signoff import Checker

    logs.console()
    if quiet:  # the tools' own lines in their logs alone
        for tool in ("gdscheck", "calibre", "klayout"):
            logging.getLogger(tool).setLevel(logging.WARNING)
    log = logging.getLogger("flow")
    align_run.ECHO = not quiet  # ALIGN's output on the terminal as well as in its log
    run_dir = new_run(block, "layout")
    log.info(f"{block}: run {_shown(run_dir)}")
    failed: list[str] = []
    for pdk in pdks:
        try:
            picked = runner.select(block, pdk, names)
        except LookupError as error:
            raise SystemExit(str(error)) from None
        for ident, (label, params) in picked.items():
            name = label if label in named else ident  # a named instance by its name, a grid's by its digest
            name = f"{name}_auto" if auto else name
            out = run_dir / pdk / name
            log.info(f"{block} {name} in {pdk}: {label}: {_shown(out)}")
            if plan_only:
                print(*plan_design(block, params, pdk, out, f"{block}_{name}"), sep="\n")
                continue
            started = time.monotonic()
            with logs.instance_log(out / "flow.log"):
                try:
                    layout_one(
                        block, out, pdk, f"{block}_{name}", params, auto=auto, checker=Checker[signoff.upper()], pex=pex
                    )
                except RuntimeError as error:  # a failed signoff: reported, the other instances laid out
                    failed.append(f"{block} {name} in {pdk}: {_reason(out) or error}")
                _record(block, pdk, ident, params, out, time.monotonic() - started, name)
                _page(out)
    if failed:
        raise SystemExit(f"{len(failed)} of the layouts failed signoff:\n" + "\n".join(failed))


def _record(block: str, pdk: str, ident: str, params, out: Path, seconds: float, name: str) -> None:
    """A laid-out instance's record for the viewer's table (``flow table``), ``out/instance.json``,
    as a characterization run writes one: its parameters, no metrics, and its layout (GDS, netlist,
    size, signoff), so a block laid out before it is characterized shows its layouts. ``name``: the
    instance's name in the run (a named instance's, a grid's digest), as its page titles it."""
    import dataclasses
    import json

    from flow.web.export import json_value

    root = Path(__file__).resolve().parents[1]
    summary = out / "summary.json"
    entry = next(iter(json.loads(summary.read_text()).values()), {}) if summary.exists() else {}
    netlist = next((out / "netlist").glob("*.sp"), None)
    width, height = entry.get("cell_um", (None, None))
    layout = {
        "gds": str(Path(entry["gds"]).relative_to(root)) if entry.get("gds") else None,
        "netlist": str(netlist.relative_to(root)) if netlist else None,
        "w_um": width,
        "h_um": height,
        "drc_violations": entry.get("drc_violations"),
        "lvs_correct": entry.get("lvs_correct"),
        "error": _reason(out) or entry.get("error"),
        "seconds": round(seconds, 1),
        "steps": entry.get("seconds", {}),  # each step's seconds: netlist, layout, DRC, LVS
    }
    record = {
        "block": block,
        "id": f"{pdk}__{ident}",
        "name": name,
        "pdk": pdk,
        "params": {field.name: json_value(getattr(params, field.name)) for field in dataclasses.fields(params)},
        "metrics": {},
        "details": [],
        "waves": {},
        "error": None,
        "seconds": round(seconds, 1),
        "layout": layout,
    }
    (out / "instance.json").write_text(json.dumps(record, indent=1) + "\n")


def _page(out: Path) -> None:
    """The laid-out instance's page (``flow.web.page``, ``out/page.html``) and its steps, a line
    each, the error that stopped it under them; a page that cannot be written is reported, never
    the layout's failure."""
    import json
    import logging

    from flow.web.page import page, step_lines

    log = logging.getLogger("flow.steps")
    try:
        written = page(out)
    except Exception as error:  # noqa: BLE001 - the layout stands without its page
        log.warning(f"page not written ({error!r})")
        return
    for line in step_lines(out):
        log.info(line)
    for entry in json.loads((out / "summary.json").read_text()).values() if (out / "summary.json").exists() else ():
        if entry.get("error"):
            log.error(entry["error"][:300])
    log.info(f"page {_shown(written)}")


def _shown(path: Path) -> str:
    """A path as the console shows it: from the repository's root where it is inside."""
    root = Path(__file__).resolve().parents[1]
    path = Path(path).resolve()
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def _reason(run_dir: Path) -> str:
    """Why an instance failed signoff, as its ``failures.json`` records it ("" where it has none)."""
    import json

    path = run_dir / "failures.json"
    return "; ".join(f"{key}: {why}" for key, why in json.loads(path.read_text()).items()) if path.exists() else ""


def plan_design(block: str, params, pdk: str, out_dir: Path, design: str) -> tuple[Path, ...]:
    """The netlists and ALIGN's design directory of ``block``'s ``params`` in ``pdk``, without ALIGN
    (``flow.layout.step.inputs``): the ALIGN and LVS netlists, the design directory."""
    from flow.layout.step import inputs

    input_dir, _cells, source, _placed = inputs(block, out_dir, pdk, design, params)
    return out_dir / "netlist" / f"{design}.sp", source, input_dir


def main() -> None:
    if len(sys.argv) < 2:
        for line in (__doc__ or "").splitlines():
            if line.startswith("    python -m flow "):
                print(line.strip())
        print(f"(blocks on the pipeline: {', '.join(pipeline_blocks())})")
        for block in BLOCKS:
            try:
                module = block_targets(block)
            except ImportError as error:
                print(f"{block}: does not import ({error})")
                continue
            for name in targets(module):
                print(f"{block}.{name}")
        return
    if sys.argv[1] in VERBS:
        verb(sys.argv[1:])
        return
    block, _, name = sys.argv[1].rpartition(".")
    module = block_targets(block) if block in BLOCKS else None
    if module is None or name not in targets(module):
        raise SystemExit(f"no target {sys.argv[1]}: python -m flow lists them")
    targets(module)[name]()


if __name__ == "__main__":
    main()
