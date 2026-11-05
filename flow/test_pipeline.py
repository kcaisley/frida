"""The pipeline contract (docs/pipeline.md), checked on every block that follows it (``MIGRATED``:
every block with a sweep, a new one too, unless ``NOT_MIGRATED`` names it): its stage files, the
names each may define, their signatures (an analysis's prior optional as ``X | None = None``), that
its pure stages do no file I/O (their private helpers pure functions too), and that it states its
layout one way at most: its ALIGN placement in subckt.py or its own layout.py, not both. Reads no
data and runs no simulator: a pre-commit hook and CI run it.

The import order of the stages is checked by import-linter (``[tool.importlinter]`` in
pyproject.toml: one contract over every migrated block, held to them here), ``from flow.<block>
import ...`` outside a block by Ruff (ICN003), the stages' types by ty over ``typed()`` (CI), their
netlists by ``flow/netlist_hashes.py`` (by hand). ``KNOWN_VIOLATIONS`` and ``NOT_MIGRATED`` may only shrink.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import importlib
import importlib.util
import inspect
import itertools
import re
import tomllib
import types
import typing
from collections.abc import Sequence
from pathlib import Path

import hdl21 as h
import pytest

from flow import pipeline
from flow.sweep.runner import sweep_blocks

ROOT = Path(__file__).resolve().parents[1]
# The blocks not on the pipeline yet; every other block with a sweep follows it, a new one too.
# Entries may be removed (a block migrated), never added.
NOT_MIGRATED = (
    *("adc", "bias", "cdac.caparray", "cdac.capdriver", "clkgen", "cml", "csa", "delay", "disc", "follower"),
    *("idac", "latch", "lvshift", "ota", "pi", "ringamp", "schmitt"),
)
MIGRATED = tuple(block for block in sweep_blocks() if block not in NOT_MIGRATED)
STAGES = ("params", "subckt", "sim", "types", "analysis", "plots", "sweep")
PURE = ("types", "analysis", "plots")  # no file I/O; a private helper there is a pure function too
# Known violations, as "<block>.<stage>: <problem>"; entries may be removed, never added.
KNOWN_VIOLATIONS: set[str] = set()
# beside the stages: model.py (Model), and layout.py (lay_out) in a block assembled by its own
# OpenROAD flow (the ADC; later the SAR logic) instead of the shared step (flow.layout.step: its
# generator's ALIGN placement, flow.layout.hdl21align.place); never both
SIDE = {"model": r"Model", "layout": r"lay_out"}
# a block's folder: the stages and its model (the eight a designer writes), opt.py where it is
# optimized, layout.py where it lays itself out, and nothing else but its package's __init__.py,
# its readme.md and a test_<file>.py a file
FILES = (*STAGES, "model")
OPTIONAL = ("opt", "layout")

UPPER = re.compile(r"[A-Z][A-Z0-9_]*")
RUN_ID = re.compile(r"\d{8}_\d{6}")


def _module(block: str, stage: str):
    return importlib.import_module(f"flow.{block}.{stage}")


def _tree(module) -> ast.Module:
    return ast.parse(Path(typing.cast(str, module.__file__)).read_text())


def _defined(module) -> dict[str, object]:
    """The public names a stage defines itself: its functions, classes and module constants (not
    what it imports)."""
    tree = _tree(module)
    names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    for node in tree.body:
        targets = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        names |= {target.id for target in targets if isinstance(target, ast.Name)}
    return {name: getattr(module, name) for name in sorted(names) if not name.startswith("_")}


def _hints(function) -> dict[str, object]:
    function = getattr(function, "func", function)  # an hdl21 generator's function
    return typing.get_type_hints(function, globalns=vars(inspect.getmodule(function)))


def _members(annotation) -> tuple[object, ...]:
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        return tuple(member for arg in typing.get_args(annotation) for member in _members(arg))
    return (annotation,)


def _is(annotation, base: type, *, optional: bool = False) -> bool:
    """``annotation`` is a ``base`` (a subclass, a union of them), or a sequence of them;
    ``optional``, or None as well (beside at least one of them)."""
    sequences = (Sequence, list, tuple)
    if typing.get_origin(annotation) in sequences:
        return all(_is(arg, base) for arg in typing.get_args(annotation) if arg is not Ellipsis)
    members = [member for member in _members(annotation) if not (optional and member is type(None))]
    return bool(members) and all(
        _is(member, base)
        if typing.get_origin(member) in sequences
        else isinstance(member, type) and issubclass(member, base)
        for member in members
    )


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _places(module) -> bool:
    """Whether a block's subckt.py states its layout for ALIGN: it calls ``place`` of
    ``flow.layout.hdl21align`` (imported from it, or through the module), in ``netlist`` or a
    helper of it. Read from its source: no PDK, no build of the circuit."""
    tree = _tree(module)
    called = {"flow.layout.hdl21align.place"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "flow.layout.hdl21align":
            called |= {alias.asname or alias.name for alias in node.names if alias.name == "place"}
        elif isinstance(node, ast.ImportFrom) and node.module == "flow.layout":
            called |= {f"{alias.asname or alias.name}.place" for alias in node.names if alias.name == "hdl21align"}
        elif isinstance(node, ast.Import):
            called |= {
                f"{alias.asname}.place"
                for alias in node.names
                if alias.name == "flow.layout.hdl21align" and alias.asname
            }
    return any(isinstance(node, ast.Call) and ast.unparse(node.func) in called for node in ast.walk(tree))


def _problems(block: str) -> set[str]:
    problems: set[str] = set()
    folder = Path(importlib.import_module(f"flow.{block}").__file__).parent
    # its files: FILES, OPTIONAL, __init__.py, readme.md, test_<file>.py; a targets.py named for
    # what replaced it
    known = {*FILES, *OPTIONAL}
    replaced = {"targets": "a block on the pipeline has no targets.py: the CLI's verbs run it"}
    for path in sorted(p for p in folder.iterdir() if p.is_file()):
        stem = path.stem
        if path.name in ("__init__.py", "readme.md") or path.suffix == ".py" and stem in known:
            continue
        if path.suffix == ".py" and stem.startswith("test_") and stem.removeprefix("test_") in known:
            continue
        problems.add(f"{block}.{stem}: {replaced.get(stem, f'{path.name} is none of the block files {sorted(known)}')}")
    missing = [stage for stage in FILES if not (folder / f"{stage}.py").is_file()]
    problems |= {f"{block}.{stage}: missing" for stage in missing}
    if missing:
        return problems
    stage = {name: _module(block, name) for name in STAGES}
    params = stage["params"]
    Params, TbParams = getattr(params, "Params", None), getattr(params, "TbParams", None)

    def problem(where: str, text: str) -> None:
        problems.add(f"{block}.{where}: {text}")

    # params.py: the design (Params, an hdl21 paramclass registered as a pipeline.Params), one run
    # (TbParams: a frozen dataclass with its pdk and design), valid(params), layout_view(params)
    # (the design as the shared layout step draws it), enums and constants
    if Params is None or not h.isparamclass(Params) or not issubclass(Params, pipeline.Params):
        problem("params", "Params is not an hdl21 paramclass registered as a pipeline.Params")
    if TbParams is None or not issubclass(TbParams, pipeline.TbParams) or not dataclasses.is_dataclass(TbParams):
        problem("params", "TbParams is not a pipeline.TbParams dataclass")
    elif not TbParams.__dataclass_params__.frozen or not {"pdk", "params"} <= {
        f.name for f in dataclasses.fields(TbParams)
    }:
        problem("params", "TbParams is not frozen, or lacks pdk and params")
    for name, value in _defined(params).items():
        allowed = (
            name in ("Params", "TbParams")
            or (name == "valid" and _hints(value).get("return") is bool)
            or (name == "layout_view" and list(_hints(value).values()) == [Params, Params])
            or (isinstance(value, type) and issubclass(value, enum.Enum))
            or (UPPER.fullmatch(name) and not callable(value))
        )
        if not allowed:
            problem("params", f"{name} is not Params, TbParams, valid, layout_view, an enum or a constant")

    # subckt.py: the nets (Nets, an hdl21 bundle) and the generator netlist(params) -> h.Module
    defined = _defined(stage["subckt"])
    if set(defined) - {"Nets", "netlist"}:
        problem("subckt", f"defines {sorted(set(defined) - {'Nets', 'netlist'})} beside Nets and netlist")
    if not isinstance(defined.get("Nets"), h.Bundle):
        problem("subckt", "Nets is not an hdl21 bundle")
    netlist = defined.get("netlist")
    if (
        netlist is None
        or _hints(netlist) != {"param": Params, "return": h.Module}
        and list(_hints(netlist).values()) != [Params, h.Module]
    ):
        problem("subckt", "netlist does not take the block's Params and return an h.Module")

    # sim.py: testbench(tb) -> h.Module and simulate(tb, run_dir) -> Path, constants
    defined = _defined(stage["sim"])
    extra = {name for name in defined if name not in ("testbench", "simulate") and not UPPER.fullmatch(name)}
    if extra:
        problem("sim", f"defines {sorted(extra)} beside testbench, simulate and constants")
    if list(_hints(defined.get("testbench", lambda: None)).values()) != [TbParams, h.Module]:
        problem("sim", "testbench does not take TbParams and return an h.Module")
    if list(_hints(defined.get("simulate", lambda: None)).values()) != [TbParams, Path, Path]:
        problem("sim", "simulate does not take TbParams and a run directory and return the raw file's Path")

    # types.py: Analysis<Thing> dataclasses deriving pipeline.Analysis, and at most the block's
    # Metrics deriving pipeline.Metrics (each field declared with its better-direction), data only
    # (properties allowed)
    for name, value in _defined(stage["types"]).items():
        if name == "Metrics" and isinstance(value, type) and issubclass(value, pipeline.Metrics):
            if not dataclasses.is_dataclass(value) or set(pipeline.betters(value)) != {
                f.name for f in dataclasses.fields(value)
            }:
                problem("types", "Metrics is not a dataclass whose every field is a pipeline.metric")
            continue
        if not (
            re.fullmatch(r"Analysis[A-Z]\w+", name) and isinstance(value, type) and issubclass(value, pipeline.Analysis)
        ):
            problem("types", f"{name} is not an Analysis<Thing> deriving pipeline.Analysis")
            continue
        if not dataclasses.is_dataclass(value) or not value.__dataclass_params__.frozen:
            problem("types", f"{name} is not a frozen dataclass")
        methods = [key for key, item in vars(value).items() if inspect.isfunction(item) and not key.startswith("__")]
        if methods:
            problem("types", f"{name} has methods {methods}: results are data")

    # analysis.py: analyze_<thing>(input, *, prior results) -> Analysis<Thing>, and metrics
    for name, value in _defined(stage["analysis"]).items():
        if name == "metrics":
            hints = _hints(value)
            result = hints.pop("return")
            typed = isinstance(result, type) and issubclass(result, pipeline.Metrics)
            if not (result == dict[str, float] or typed) or not all(
                _is(hint, pipeline.Analysis, optional=True) for hint in hints.values()
            ):
                problem("analysis", "metrics does not take Analysis results and return Metrics or dict[str, float]")
            continue
        if not name.startswith("analyze_") or not inspect.isfunction(value):
            problem("analysis", f"{name} is not an analyze_<thing> function or metrics")
            continue
        if pipeline.STAGE_FUNCTIONS.get(value) != "analysis":
            problem("analysis", f"{name} is not declared with @analysis")
        hints = _hints(value)
        result = hints.pop("return", None)
        parameters = list(inspect.signature(value).parameters.values())
        positional = [p for p in parameters if p.kind is p.POSITIONAL_OR_KEYWORD]
        if len(positional) != 1 or not (
            _is(hints[positional[0].name], pipeline.Meas) or _is(hints[positional[0].name], pipeline.Analysis)
        ):
            problem("analysis", f"{name} does not take one measurement (Meas, or the trials as an Analysis)")
        # each prior by keyword, a result, or an optional one (a result or None, None unless given)
        for parameter in parameters[len(positional) :]:
            hint = hints[parameter.name]
            optional = parameter.default is None
            if (
                parameter.kind is not parameter.KEYWORD_ONLY
                or optional != (type(None) in _members(hint))
                or not _is(hint, pipeline.Analysis, optional=optional)
            ):
                problem(
                    "analysis",
                    f"{name}: {parameter.name} is not a keyword-only prior Analysis result (optional: X | None = None)",
                )
        if not (isinstance(result, type) and issubclass(result, pipeline.Analysis)) or result.__name__ != (
            "Analysis" + _camel(name.removeprefix("analyze_"))
        ):
            problem("analysis", f"{name} does not return its own Analysis{_camel(name.removeprefix('analyze_'))}")

    # plots.py: plot_<thing>(results) -> Plot, nothing else
    for name, value in _defined(stage["plots"]).items():
        hints = _hints(value) if inspect.isfunction(value) else {}
        if not name.startswith("plot_") or hints.pop("return", None) is not pipeline.Plot:
            problem("plots", f"{name} is not a plot_<thing> returning a Plot")
        elif pipeline.STAGE_FUNCTIONS.get(value) != "plot":
            problem("plots", f"{name} is not declared with @plot")
        elif not all(_is(hint, pipeline.Analysis) for hint in hints.values()):
            problem("plots", f"{name} draws other than Analysis results")

    # sweep.py: its design space as grids (``@grid``) and named instances (``@named``) of the
    # block's Params, runs(pdk, params) -> dict[str, TbParams] and record(measurements) -> Record;
    # nothing else, no module constants
    sweep = _defined(stage["sweep"])
    expected = {
        "runs": [str, Params, dict[str, TbParams]],
        "record": [dict[str, pipeline.Meas], pipeline.Record],
    }
    # runs may take the evaluation level (pipeline.Level), the third of its arguments
    leveled = {"runs": [str, Params, pipeline.Level, dict[str, TbParams]]}
    for name, signature in expected.items():
        hints = list(_hints(sweep[name]).values()) if name in sweep else None
        if hints not in (signature, leveled.get(name)):
            problem("sweep", f"{name} is missing or does not have the signature {signature}")
    for name, value in sweep.items():
        if name in expected:
            continue
        if UPPER.fullmatch(name):
            problem("sweep", f"module constant {name}: a parameter's values belong to its grid")
        elif not isinstance(value, (pipeline.Grid, pipeline.Named)) or _hints(value.build).get("return") not in (
            Params,
            list[Params],
            dict[str, Params],
        ):
            problem("sweep", f"{name} is not a grid, a named instance (of Params), runs or record")

    # the side files beside the stages: their own names only, and no module constant (a block's
    # constants live in params.py, a testbench's in sim.py)
    for name, allowed in SIDE.items():
        if not (folder / f"{name}.py").is_file():
            continue
        for defined_name in _defined(_module(block, name)):
            if UPPER.fullmatch(defined_name):
                problem(name, f"module constant {defined_name} outside params.py and sim.py")
            elif not re.fullmatch(allowed, defined_name):
                problem(name, f"{defined_name} is not one of {name}.py's names ({allowed})")

    # its layout, stated one way: its generator's ALIGN placement (subckt.py calls place: the shared
    # step lays it out) or its own flow (layout.py: lay_out(params, pdk, run_dir) -> the GDS's Path,
    # which the shared signoff checks and extracts), not both; neither: ALIGN places it alone
    if (folder / "layout.py").is_file():
        if _places(stage["subckt"]):
            problem("layout", "a layout.py beside a subckt.py that places its instances for ALIGN: one or the other")
        entry = getattr(_module(block, "layout"), "lay_out", None)
        if not callable(entry) or list(_hints(entry).values()) != [Params, str, Path, Path]:
            problem("layout", "lay_out does not take the block's Params, a PDK and a run directory and return a Path")

    # the block runs from the one entry point (``python -m flow <verb> <block>``): no targets of its
    # own (above); and its code names no run and no input under build/ (a run is a verb's argument)
    for path in sorted(folder.glob("*.py")):
        text = path.read_text()
        if RUN_ID.search(text):
            problem(path.stem, f"names a run ({RUN_ID.search(text).group()})")
        if not path.name.startswith("test_") and any(
            isinstance(node, ast.Constant) and isinstance(node.value, str) and "build/" in node.value
            for node in ast.walk(ast.parse(text))
        ):
            problem(path.stem, "names a path under build/")

    # no nested functions anywhere; in the pure stages no file I/O, in their private helpers (``_``)
    # either: a pure stage's helper is a pure function
    io_calls = {"open", "write_text", "write_bytes", "read_text", "read_bytes", "savetxt", "save", "savez", "to_csv"}
    io_modules = {"csv", "json", "yaml", "pickle", "h5py", "subprocess", "shutil", "flow.analysis.io"}
    for name in STAGES:
        tree = _tree(stage[name])
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            if any(isinstance(node, ast.FunctionDef) and node is not function for node in ast.walk(function)):
                problem(name, f"{function.name} defines a function inside it")
        if name not in PURE:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and {alias.name for alias in node.names} & io_modules:
                problem(name, "imports a file format or process module")
            elif isinstance(node, ast.ImportFrom) and node.module in io_modules:
                problem(name, f"imports {node.module}")
            elif isinstance(node, ast.Call):
                callee = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if callee in io_calls or callee.startswith(("read_", "write_")):
                    problem(name, f"calls {callee}: file I/O")
    if (folder / "opt.py").is_file():
        problems |= _optimizable(block, Params, stage)
    return problems


def _optimizable(block: str, Params, stage: dict) -> set[str]:
    """The contract of a block with problems (its opt.py, ``python -m flow opt``): opt.py gives
    problems alone, each naming metrics, bounding only those with a direction, and searching a space
    of the block's ``Params`` (``Problem.space``: ``pipeline.widen``) in which every combination of
    its choices builds and a range that does not apply (``when``) leaves the circuit as it is; its
    metrics are typed (``types.Metrics``)."""

    problems: set[str] = set()
    problem = lambda where, text: problems.add(f"{block}.{where}: {text}")
    opt = _module(block, "opt")
    metrics_class = getattr(stage["types"], "Metrics", None)
    if metrics_class is None:
        problem("types", "no Metrics: a block with problems types its metrics")
        return problems
    for name, value in _defined(opt).items():
        if not isinstance(value, pipeline.ProblemFamily):
            problem("opt", f"{name} is not a @problem")
    better = {**pipeline.betters(metrics_class), **pipeline.GEOMETRY}
    netlist = stage["subckt"].netlist

    def built(design) -> list[tuple[str, str]]:
        netlist.Cache.reset()
        return [(n, repr(i.of.params)) for n, i in netlist(design).instances.items()]

    from flow.sweep.runner import PDKS

    for pdk in PDKS:
        installed = importlib.util.find_spec(f"pdk.{pdk}.hdl21") is not None
        for label, made in (pipeline.problems(opt, pdk) if installed else {}).items():
            for name in [*made.cost, *made.bound]:
                if name not in better:
                    problem("opt", f"{label} names {name}, not a metric")
            for name, limit in made.bound.items():
                if better.get(name) == "none" or (better.get(name) == "true") != isinstance(limit, bool):
                    problem("opt", f"{label} bounds {name} against its direction")
            space = made.space
            if not isinstance(space, pipeline.Space) or not isinstance(space.base, Params):
                problem("opt", f"{label} searches no space of its Params (Problem.space: pipeline.widen)")
                continue
            # every combination of the space's choices builds
            choices = {
                name: widened.values
                for name, widened in space.widened.items()
                if isinstance(widened, pipeline.Values) and widened.when is None
            }
            designs = []
            for combination in itertools.product(*choices.values()):
                design = Params(**{**space.base.__dict__, **dict(zip(choices, combination, strict=True))})
                try:
                    built(design)
                    designs.append(design)
                except Exception as error:  # noqa: BLE001 - the contract reports what does not build
                    problem("opt", f"{label}: the choices {combination} do not build ({type(error).__name__})")
            # a range that does not apply to a design leaves its circuit as it is
            for name, widened in space.widened.items():
                design = next((d for d in designs if widened.when and not pipeline.holds(widened.when, d)), None)
                if design is None:
                    continue
                other = widened.values[-1] if isinstance(widened, pipeline.Values) else round(widened.high)
                if built(design) != built(Params(**{**design.__dict__, name: other})):
                    problem("opt", f"{label}: {name} changes the circuit where it does not apply")
    return problems


def typed() -> list[str]:
    """The files ty checks for the pipeline (CI): every migrated block's stages, its opt.py and its
    layout.py."""
    return [
        f"flow/{block}/{stage}.py"
        for block in MIGRATED
        for stage in (*STAGES, *OPTIONAL)
        if (ROOT / "flow" / block / f"{stage}.py").is_file()
    ]


def test_the_blocks_not_migrated_are_blocks() -> None:
    """Every name ``NOT_MIGRATED`` gives is a block with a sweep: one migrated or gone leaves it."""
    assert set(NOT_MIGRATED) <= set(sweep_blocks())


def test_one_import_contract_orders_every_migrated_block() -> None:
    """import-linter's layers contract covers exactly the migrated blocks, a block's opt.py and
    layout.py optional in it."""
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["importlinter"]["contracts"]
    layers = [contract for contract in contracts if contract["type"] == "layers"]
    assert len(layers) == 1
    assert sorted(layers[0]["containers"]) == sorted(f"flow.{block}" for block in MIGRATED)


@pytest.mark.parametrize("block", MIGRATED)
def test_a_migrated_block_follows_the_pipeline(block: str) -> None:
    assert _problems(block) <= KNOWN_VIOLATIONS


def test_the_known_violations_only_shrink() -> None:
    """Every known violation still exists: fixed ones leave the list."""
    found = {problem for block in MIGRATED for problem in _problems(block)}
    assert KNOWN_VIOLATIONS <= found


def test_the_contract_catches_what_it_forbids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A block that breaks the contract in each stage is caught there."""
    package = tmp_path / "flow" / "badblock"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = Path(importlib.import_module("flow.comp").__file__).parent
    for name in STAGES:
        text = (source / f"{name}.py").read_text()
        (package / f"{name}.py").write_text(text)
    with (package / "analysis.py").open("a") as stream:
        stream.write("\n\ndef summarize(meas: Meas) -> AnalysisTiming:\n    return meas\n")
    with (package / "analysis.py").open("a") as stream:
        stream.write("\n\ndef analyze_extra(meas: Meas) -> AnalysisTiming:\n    return meas\n")
        # a prior that may be None without defaulting to it, and one that defaults to None as a result
        # alone (@analysis refuses both, so these are left undeclared to import)
        for name, prior in (("unset", "AnalysisTiming | None"), ("plain", "AnalysisTiming = None")):
            stream.write(
                f"\n\ndef analyze_{name}(meas: Meas, *, timing: {prior}) -> AnalysisTiming:\n    return meas\n"
            )
        stream.write("\n\ndef _outer() -> None:\n    def inner() -> None:\n        pass\n")
    (package / "model.py").write_text('"""A model."""\n\nLIMIT = 3\n\n\nclass Model:\n    pass\n')
    with (package / "plots.py").open("a") as stream:
        # a private helper, which reads a file: a pure stage's helper is a pure function
        stream.write("\n\ndef _helper() -> None:\n    open('x')\n")
    with (package / "types.py").open("a") as stream:
        stream.write("\n\nclass Extra:\n    pass\n")
    with (package / "sweep.py").open("a") as stream:
        stream.write('\n\nSIZES = ("x1", "x2")\nARCHIVE = "build/badblock/20260101_000000"\n')
    (package / "targets.py").write_text('"""Old targets."""\n')
    (package / "helpers.py").write_text('"""Helpers."""\n')
    (package / "test_helpers.py").write_text('"""Helper tests."""\n')
    # a layout.py beside the comparator's subckt.py, which places its instances for ALIGN
    (package / "layout.py").write_text('"""Its own layout."""\n\nGAP_UM = 2.0\n\n\ndef assemble() -> None:\n    pass\n')
    import flow

    monkeypatch.setattr(flow, "__path__", [*flow.__path__, str(tmp_path / "flow")])
    problems = _problems("badblock")
    assert "badblock.analysis: summarize is not an analyze_<thing> function or metrics" in problems
    assert "badblock.analysis: analyze_extra is not declared with @analysis" in problems
    for name in ("unset", "plain"):
        assert (
            f"badblock.analysis: analyze_{name}: timing is not a keyword-only prior Analysis result "
            "(optional: X | None = None)"
        ) in problems
    assert "badblock.analysis: _outer defines a function inside it" in problems
    assert "badblock.model: module constant LIMIT outside params.py and sim.py" in problems
    # the helper's file I/O alone, not the helper
    assert {problem for problem in problems if problem.startswith("badblock.plots:")} == {
        "badblock.plots: calls open: file I/O"
    }
    assert "badblock.types: Extra is not an Analysis<Thing> deriving pipeline.Analysis" in problems
    assert "badblock.sweep: module constant SIZES: a parameter's values belong to its grid" in problems
    assert {"badblock.targets: a block on the pipeline has no targets.py: the CLI's verbs run it"} <= problems
    files = sorted({*FILES, *OPTIONAL})
    assert f"badblock.helpers: helpers.py is none of the block files {files}" in problems
    assert f"badblock.test_helpers: test_helpers.py is none of the block files {files}" in problems
    assert {"badblock.sweep: names a run (20260101_000000)", "badblock.sweep: names a path under build/"} <= problems
    assert {
        "badblock.layout: a layout.py beside a subckt.py that places its instances for ALIGN: one or the other",
        "badblock.layout: lay_out does not take the block's Params, a PDK and a run directory and return a Path",
        "badblock.layout: module constant GAP_UM outside params.py and sim.py",
        "badblock.layout: assemble is not one of layout.py's names (lay_out)",
    } <= problems


def test_the_contract_admits_what_it_allows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CDAC's files (its generator places nothing for ALIGN) with what the contract admits beside
    them: a layout.py of its own (``lay_out``), a private pure helper in each pure stage, and an
    analysis with an optional prior (``X | None = None``)."""
    package = tmp_path / "flow" / "goodblock"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = Path(importlib.import_module("flow.cdac").__file__).parent
    for name in FILES:
        (package / f"{name}.py").write_text((source / f"{name}.py").read_text())
    for name in PURE:
        with (package / f"{name}.py").open("a") as stream:
            stream.write("\n\ndef _twice(value: float) -> float:\n    return 2 * value\n")
    analysis = (package / "analysis.py").read_text()
    plain = "def analyze_mismatch(meas: Meas) -> AnalysisMismatch:"
    optional = "def analyze_mismatch(meas: Meas, *, settling: AnalysisSettling | None = None) -> AnalysisMismatch:"
    assert plain in analysis
    (package / "analysis.py").write_text(analysis.replace(plain, optional))
    (package / "layout.py").write_text(
        '"""Its own layout."""\n\nfrom pathlib import Path\n\nfrom .params import Params\n\n\n'
        'def lay_out(params: Params, pdk: str, run_dir: Path) -> Path:\n    return run_dir / "block.gds"\n'
    )
    import flow

    monkeypatch.setattr(flow, "__path__", [*flow.__path__, str(tmp_path / "flow")])
    assert _problems("goodblock") == set()


def test_a_stage_with_the_wrong_signature_does_not_import() -> None:
    """``@analysis`` and ``@plot`` check their function when its module is imported."""

    def summary(meas: pipeline.Meas) -> dict[str, float]:
        return {}

    def figure(meas: pipeline.Meas) -> pipeline.Plot:
        raise NotImplementedError

    def positional_prior(meas: pipeline.Meas, prior: pipeline.Analysis) -> pipeline.Analysis:
        return prior

    with pytest.raises(TypeError, match="returns an Analysis"):
        pipeline.analysis(summary)
    with pytest.raises(TypeError, match="not an Analysis result"):
        pipeline.plot(figure)
    with pytest.raises(TypeError, match="positionally"):
        pipeline.analysis(positional_prior)


def test_an_analysis_may_take_an_optional_prior(monkeypatch: pytest.MonkeyPatch) -> None:
    """A prior an analysis does without where it was not measured is ``X | None = None`` (a result,
    a sequence of them, or None); a prior that may be None without defaulting to it, a None default
    on a result alone, a None alone and a figure's optional input are refused."""
    monkeypatch.setattr(pipeline, "STAGE_FUNCTIONS", {})  # this test's functions declared here alone

    def optional(meas: pipeline.Meas, *, prior: pipeline.Analysis | None = None) -> pipeline.Analysis:
        raise NotImplementedError

    def optional_trials(meas: pipeline.Meas, *, trials: Sequence[pipeline.Analysis] | None = None) -> pipeline.Analysis:
        raise NotImplementedError

    def unset(meas: pipeline.Meas, *, prior: pipeline.Analysis | None) -> pipeline.Analysis:
        raise NotImplementedError

    def plain(meas: pipeline.Meas, *, prior: pipeline.Analysis = None) -> pipeline.Analysis:  # ty: ignore[invalid-parameter-default]
        raise NotImplementedError

    def nothing(meas: pipeline.Meas, *, prior: None = None) -> pipeline.Analysis:
        raise NotImplementedError

    def figure(result: pipeline.Analysis | None = None) -> pipeline.Plot:
        raise NotImplementedError

    for function in (optional, optional_trials):
        assert pipeline.analysis(function) is function
        assert pipeline.STAGE_FUNCTIONS[function] == "analysis"
    for function in (unset, plain):
        with pytest.raises(TypeError, match=r"optional prior only as X \| None = None"):
            pipeline.analysis(function)
    with pytest.raises(TypeError, match="not an Analysis result by keyword"):
        pipeline.analysis(nothing)
    with pytest.raises(TypeError, match="not an Analysis result"):
        pipeline.plot(figure)


@h.paramclass
class _Knobs:
    """A design of two whole numbers, for the grids' own tests."""

    width = h.Param(dtype=int, desc="a width", default=1)
    length = h.Param(dtype=int, desc="a length", default=1)


def test_a_grid_labels_named_values_and_named_spaces_by_their_names() -> None:
    """``values`` of a mapping labels each point by its value's name; a grid of spaces by name labels
    each point by its space's name too, and gives the spaces by name."""

    @pipeline.grid
    def ladder() -> dict[str, _Knobs]:
        short, long = pipeline.widen(_Knobs()), pipeline.widen(_Knobs(length=4))
        short.width = pipeline.values({"narrow": 2, "wide": 8})
        return {"short": short, "long": long}

    labels = dict(ladder.instances(pipeline.Pdk.TSMC65))
    assert set(labels) == {"ladder(short, width=narrow)", "ladder(short, width=wide)", "ladder(long)"}
    assert labels["ladder(short, width=wide)"] == _Knobs(width=8)
    assert labels["ladder(long)"] == _Knobs(length=4)
    assert ladder.spaces(pipeline.Pdk.TSMC65)["long"].base == _Knobs(length=4)
    # a grid of unnamed spaces keeps its labels, and gives the spaces by place
    plain = pipeline.grid(lambda: [ladder.spaces(pipeline.Pdk.TSMC65)["short"]])
    assert {label.split("(", 1)[1] for label, _ in plain.instances("tsmc65")} == {"width=narrow)", "width=wide)"}
    assert set(plain.spaces("tsmc65")) == {"0"}
