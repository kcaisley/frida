"""The flow's one entry point: ``python -m flow`` lists what it runs.

A block on the pipeline (docs/pipeline.md) is run by verbs, each over the block's design space and
named instances (its ``sweep.py``):

    python -m flow run <block> [--pdk P ...] [--instance I ...] [--missing] [--workers N]
    python -m flow layout <block> [--pdk P ...] [--instance I ... [--auto]] [--workers N]
    python -m flow table <block> [--workers N]
    python -m flow plot <block> [FIGURE ...] --from DIR [--from DIR ...] [--backend matplotlib|web]
    python -m flow opt <block> --problem P [--pdk P] [--budget N] [--workers N] [--best N] [--finalists N]

An instance ``I`` is a named instance, an instance's label (``grid(name, parameter=value, ...)``) or its
digest. ``layout`` without ``--instance`` lays out the newest run's instances by ALIGN into their
records; with it, each named instance by ALIGN from its hand-written floorplan (or, with
``--auto``, from ALIGN's placement) into ``build/layout/<block>/<name>/``. ``plot`` draws a sweep
run's records' figures, or the figures of a directory of captures.

A block not yet on the pipeline, and the flow's own tools, keep their targets: ``python -m flow
<module>.<target>`` runs a public function without arguments of that ``targets.py``, which makes its
own run directory under ``build/``.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from importlib import import_module
from pathlib import Path

from flow.adc import targets as adc
from flow.bias import targets as bias
from flow.caparray import targets as caparray
from flow.capdriver import targets as capdriver
from flow.clkgen import targets as clkgen
from flow.cml import targets as cml
from flow.csa import targets as csa
from flow.delay import targets as delay
from flow.disc import targets as disc
from flow.follower import targets as follower
from flow.idac import targets as idac
from flow.latch import targets as latch
from flow.layout import targets as layout
from flow.lvshift import targets as lvshift
from flow.momcap import targets as momcap
from flow.moscap import targets as moscap
from flow.mosfet import targets as mosfet
from flow.ota import targets as ota
from flow.pi import targets as pi
from flow.polyres import targets as polyres
from flow.ringamp import targets as ringamp
from flow.schmitt import targets as schmitt
from flow.sweep import targets as sweep
from flow.web import targets as web

BLOCKS = {
    "adc": adc,
    "bias": bias,
    "caparray": caparray,
    "capdriver": capdriver,
    "clkgen": clkgen,
    "cml": cml,
    "csa": csa,
    "delay": delay,
    "disc": disc,
    "follower": follower,
    "idac": idac,
    "latch": latch,
    "layout": layout,
    "lvshift": lvshift,
    "momcap": momcap,
    "moscap": moscap,
    "mosfet": mosfet,
    "ota": ota,
    "pi": pi,
    "polyres": polyres,
    "ringamp": ringamp,
    "schmitt": schmitt,
    "sweep": sweep,
    "web": web,
}


def targets(module) -> dict:
    """The targets a ``targets.py`` defines, by name, in source order."""
    return {
        name: function
        for name, function in vars(module).items()
        if inspect.isfunction(function) and function.__module__ == module.__name__ and not name.startswith("_")
    }


VERBS = ("run", "layout", "table", "plot", "opt")


def pipeline_blocks() -> list[str]:
    """The blocks on the pipeline: those whose ``sweep.py`` gives ``runs``."""
    from flow.sweep import runner

    return [block for block in runner.sweep_blocks() if hasattr(import_module(f"flow.{block}.sweep"), "runs")]


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
    ):
        command = commands.add_parser(verb, help=text, description=text)
        command.add_argument("block", choices=pipeline_blocks())
        if verb == "plot":
            command.add_argument("figures", nargs="*", metavar="FIGURE", help="the figures, by name (default: all)")
            command.add_argument("--from", dest="sources", type=Path, action="append", required=True)
            command.add_argument("--backend", choices=("matplotlib", "web"), default="matplotlib")
        if verb != "table":
            command.add_argument("--pdk", action="append", choices=runner.PDKS, dest="pdks")
            command.add_argument("--instance", action="append", dest="instances", metavar="I")
        if verb == "run":
            command.add_argument("--missing", action="store_true", help="the newest run's failed or missing ones")
        if verb == "layout":
            floorplan = command.add_mutually_exclusive_group()
            floorplan.add_argument("--manual", action="store_true", help="from the hand-written floorplan (default)")
            floorplan.add_argument("--auto", action="store_true", help="from ALIGN's placement")
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
    from flow import new_run, pipeline
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
    elif not args.instances:
        runner.layout([args.block], args.workers, pdks=pdks)
    else:
        named = pipeline.names(import_module(f"flow.{args.block}.sweep"))
        layout_named = import_module(f"flow.{args.block}.layout").layout_named
        for name in list(named) if args.instances == ["all"] else args.instances:
            if name not in named:
                raise SystemExit(f"no named instance {name} of {args.block}: {', '.join(named)}")
            run_dir = new_run("layout", args.block, f"{name}_auto" if args.auto else name)
            print(layout_named(run_dir, name, named[name](), auto=args.auto, pdks=pdks))


def main() -> None:
    if len(sys.argv) < 2:
        for line in (__doc__ or "").splitlines():
            if line.startswith("    python -m flow "):
                print(line.strip())
        print(f"(blocks on the pipeline: {', '.join(pipeline_blocks())})")
        for block, module in BLOCKS.items():
            for name in targets(module):
                print(f"{block}.{name}")
        return
    if sys.argv[1] in VERBS:
        verb(sys.argv[1:])
        return
    block, _, name = sys.argv[1].partition(".")
    module = BLOCKS.get(block)
    if module is None or name not in targets(module):
        raise SystemExit(f"no target {sys.argv[1]}: python -m flow lists them")
    targets(module)[name]()


if __name__ == "__main__":
    main()
