"""The pipeline contract (docs/pipeline.md), checked on every block that follows it (``MIGRATED``):
its stage files, the names each may define, their signatures, and that its pure stages hold no
helpers and do no file I/O. Reads no data and runs no simulator: a pre-commit hook and CI run it.

The import order of the stages is checked by import-linter (``[tool.importlinter]`` in
pyproject.toml), ``from flow.<block> import ...`` outside a block by Ruff (ICN003).
``KNOWN_VIOLATIONS`` may only shrink.
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import importlib
import inspect
import re
import types
import typing
from collections.abc import Sequence
from pathlib import Path

import hdl21 as h
import pytest

from flow import pipeline

MIGRATED = ("comp", "samp", "cdac")
STAGES = ("params", "subckt", "sim", "types", "analysis", "plots", "sweep")
PURE = ("types", "analysis", "plots")  # no helpers, no file I/O
# Known violations, as "<block>.<stage>: <problem>"; entries may be removed, never added.
KNOWN_VIOLATIONS: set[str] = {
    # the layout runner's shared constants, which 16 blocks still import from comp/layout.py
    *(
        f"comp.layout: module constant {name} outside params.py and sim.py"
        for name in ("BUILD", "ESCAPE", "FLOORPLANS", "FLOORPLAN_CASES", "PDKS", "ROOT")
    ),
}
# beside the stages: layout.py (its layout_<thing> functions and write_netlist) and model.py (Model)
SIDE = {"layout": r"layout_\w+|write_netlist", "model": r"Model"}

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


def _is(annotation, base: type) -> bool:
    """``annotation`` is a ``base`` (a subclass), or a sequence of them."""
    if typing.get_origin(annotation) in (Sequence, list, tuple):
        return all(_is(arg, base) for arg in typing.get_args(annotation) if arg is not Ellipsis)
    return all(isinstance(member, type) and issubclass(member, base) for member in _members(annotation))


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _problems(block: str) -> set[str]:
    problems: set[str] = set()
    folder = Path(importlib.import_module(f"flow.{block}").__file__).parent
    missing = [stage for stage in STAGES if not (folder / f"{stage}.py").is_file()]
    problems |= {f"{block}.{stage}: missing" for stage in missing}
    if missing:
        return problems
    stage = {name: _module(block, name) for name in STAGES}
    params = stage["params"]
    Params, TbParams = getattr(params, "Params", None), getattr(params, "TbParams", None)

    def problem(where: str, text: str) -> None:
        problems.add(f"{block}.{where}: {text}")

    # params.py: the design (Params, an hdl21 paramclass registered as a pipeline.Params), one run
    # (TbParams: a frozen dataclass with its pdk and design), valid(params), enums and constants
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
            or (isinstance(value, type) and issubclass(value, enum.Enum))
            or (UPPER.fullmatch(name) and not callable(value))
        )
        if not allowed:
            problem("params", f"{name} is not Params, TbParams, valid, an enum or a constant")

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

    # types.py: Analysis<Thing> dataclasses deriving pipeline.Analysis, data only (properties allowed)
    for name, value in _defined(stage["types"]).items():
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
            if hints.pop("return") != dict[str, float] or not all(
                _is(hint, pipeline.Analysis) for hint in hints.values()
            ):
                problem("analysis", "metrics does not take Analysis results and return dict[str, float]")
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
        for parameter in parameters[len(positional) :]:
            if parameter.kind is not parameter.KEYWORD_ONLY or not _is(hints[parameter.name], pipeline.Analysis):
                problem("analysis", f"{name}: {parameter.name} is not a keyword-only prior Analysis result")
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

    # sweep.py: its design space as families (``@family``) and named instances (``@named``) of the
    # block's Params, runs(pdk, params) -> dict[str, TbParams] and record(measurements) -> Record;
    # nothing else, no module constants
    sweep = _defined(stage["sweep"])
    expected = {
        "runs": [str, Params, dict[str, TbParams]],
        "record": [dict[str, pipeline.Meas], pipeline.Record],
    }
    for name, signature in expected.items():
        if name not in sweep or list(_hints(sweep[name]).values()) != signature:
            problem("sweep", f"{name} is missing or does not have the signature {signature}")
    for name, value in sweep.items():
        if name in expected:
            continue
        if UPPER.fullmatch(name):
            problem("sweep", f"module constant {name}: a knob's values belong to its family")
        elif (
            not isinstance(value, (pipeline.Family, pipeline.Named)) or _hints(value.build).get("return") is not Params
        ):
            problem("sweep", f"{name} is not a family, a named instance (of Params), runs or record")

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

    # the block runs from the one entry point (``python -m flow <verb> <block>``): no targets of its
    # own; and its code names no run and no input under build/ (a run is a verb's argument)
    if (folder / "targets.py").exists():
        problem("targets", "a block on the pipeline has no targets.py: the CLI's verbs run it")
    for path in sorted(folder.glob("*.py")):
        text = path.read_text()
        if RUN_ID.search(text):
            problem(path.stem, f"names a run ({RUN_ID.search(text).group()})")
        if not path.name.startswith("test_") and any(
            isinstance(node, ast.Constant) and isinstance(node.value, str) and "build/" in node.value
            for node in ast.walk(ast.parse(text))
        ):
            problem(path.stem, "names a path under build/")

    # no nested functions anywhere; in the pure stages no private helpers and no file I/O
    io_calls = {"open", "write_text", "write_bytes", "read_text", "read_bytes", "savetxt", "save", "savez", "to_csv"}
    io_modules = {"csv", "json", "yaml", "pickle", "h5py", "subprocess", "shutil", "flow.analysis.io"}
    for name in STAGES:
        tree = _tree(stage[name])
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            if any(isinstance(node, ast.FunctionDef) and node is not function for node in ast.walk(function)):
                problem(name, f"{function.name} defines a function inside it")
            if name in PURE and function.name.startswith("_"):
                problem(name, f"private helper {function.name}")
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
    return problems


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
    (package / "model.py").write_text('"""A model."""\n\nLIMIT = 3\n\n\nclass Model:\n    pass\n')
    with (package / "plots.py").open("a") as stream:
        stream.write("\n\ndef _helper() -> None:\n    open('x')\n")
    with (package / "types.py").open("a") as stream:
        stream.write("\n\nclass Extra:\n    pass\n")
    with (package / "sweep.py").open("a") as stream:
        stream.write('\n\nSIZES = ("x1", "x2")\nARCHIVE = "build/sweep/badblock/20260101_000000"\n')
    (package / "targets.py").write_text('"""Old targets."""\n')
    import flow

    monkeypatch.setattr(flow, "__path__", [*flow.__path__, str(tmp_path / "flow")])
    problems = _problems("badblock")
    assert "badblock.analysis: summarize is not an analyze_<thing> function or metrics" in problems
    assert "badblock.analysis: analyze_extra is not declared with @analysis" in problems
    assert "badblock.model: module constant LIMIT outside params.py and sim.py" in problems
    assert "badblock.plots: private helper _helper" in problems
    assert "badblock.plots: calls open: file I/O" in problems
    assert "badblock.types: Extra is not an Analysis<Thing> deriving pipeline.Analysis" in problems
    assert "badblock.sweep: module constant SIZES: a knob's values belong to its family" in problems
    assert {"badblock.targets: a block on the pipeline has no targets.py: the CLI's verbs run it"} <= problems
    assert {"badblock.sweep: names a run (20260101_000000)", "badblock.sweep: names a path under build/"} <= problems


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
