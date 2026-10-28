"""Enforce the analysis contract in ``readme.md`` by inspecting signatures and source.

These tests read no data and render no figures, so they also run as a
pre-commit hook. Each known-violation list may only shrink.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import re
import types
import typing
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from flow.adc.sequences import AdcSequence
from flow.adc.sim import AdcTbParams
from flow.adc.subckt import AdcParams
from flow.analysis import types as analysis_types
from flow.cdac.caparray.sim import CapArrayTbParams
from flow.cdac.caparray.subckt import CapArrayConfig, CapArrayParams
from flow.scans.params import AdcScanParams

ANALYSIS_DIR = Path(__file__).resolve().parent
# Building blocks keep their measurement and result types, analyses, and plots in their own
# folder (flow/<block>/analysis.py and plots.py) under the same contract. The blocks on the pipeline
# (flow/test_pipeline.py: MIGRATED) follow its contract instead (docs/pipeline.md).
BLOCKS = (
    "cdac.caparray",
    "momcap",
    "delay",
    "latch",
    "ota",
    "follower",
    "moscap",
    "idac",
    "cml",
    "pi",
    "clkgen",
    "lvshift",
    "ringamp",
    "cdac.capdriver",
    "csa",
    "disc",
    "schmitt",
    "bias",
    "mosfet",
)
BLOCK_ANALYSES = tuple(f"flow.{block}.analysis" for block in BLOCKS)
BLOCK_PLOTS = tuple(f"flow.{block}.plots" for block in BLOCKS)
CONTRACT_MODULES = ("adc", "cdac", "calibration1", "calibration2", "calibration3", *BLOCK_ANALYSES)
PURE_MODULES = (*CONTRACT_MODULES, "calc")
# Names that annotations in flow.analysis.types refer to only under TYPE_CHECKING.
TYPE_NAMESPACE = {
    "AdcSequence": AdcSequence,
    "AdcTbParams": AdcTbParams,
    "AdcParams": AdcParams,
    "CapArrayTbParams": CapArrayTbParams,
    "CapArrayConfig": CapArrayConfig,
    "CapArrayParams": CapArrayParams,
    "AdcScanParams": AdcScanParams,
}


@pytest.fixture(autouse=True)
def _resolve_type_checking_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let lazily evaluated type aliases such as DutParams resolve their names."""

    for name, value in TYPE_NAMESPACE.items():
        monkeypatch.setattr(analysis_types, name, value, raising=False)


# Known violations; entries may be removed but never added.
KNOWN_SIGNATURE_VIOLATIONS: set[str] = set()
KNOWN_SOURCE_VIOLATIONS: set[str] = set()


def _module(name: str):
    return importlib.import_module(name if "." in name else f"flow.analysis.{name}")


def _path(name: str) -> Path:
    return Path(typing.cast(str, _module(name).__file__))


def _hints(function) -> dict[str, object]:
    return typing.get_type_hints(function, globalns=vars(inspect.getmodule(function)), localns=TYPE_NAMESPACE)


def _unalias(annotation):
    while isinstance(annotation, typing.TypeAliasType):
        annotation = annotation.__value__
    return annotation


def _members(annotation) -> tuple[object, ...]:
    """Split a union into its members."""

    annotation = _unalias(annotation)
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        return tuple(member for arg in typing.get_args(annotation) for member in _members(arg))
    return (annotation,)


def _is_class(annotation, predicate) -> bool:
    return isinstance(annotation, type) and predicate(annotation)


def _is_measurement(annotation) -> bool:
    return _is_class(
        annotation, lambda value: value.__name__.startswith("Meas") and issubclass(value, analysis_types.Meas)
    )


def _is_analysis(annotation) -> bool:
    return _is_class(annotation, lambda value: issubclass(value, analysis_types.Analysis))


def _sequence_of(annotation, predicate) -> bool:
    origin = typing.get_origin(annotation)
    return origin in (Sequence, tuple, list) and all(
        all(predicate(member) for member in _members(arg)) for arg in typing.get_args(annotation) if arg is not Ellipsis
    )


def _public_functions(module_name: str):
    module = _module(module_name)
    return [
        (name, function)
        for name, function in inspect.getmembers(module, inspect.isfunction)
        if function.__module__ == module.__name__ and not name.startswith("_")
    ]


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _contract_problems() -> set[str]:
    problems = set()
    for module_name in CONTRACT_MODULES:
        for name, function in _public_functions(module_name):
            label = f"{module_name}.{name}"
            if not re.fullmatch(
                rf"analyze_(adc|comp|cdac|{'|'.join(block.rpartition('.')[2] for block in BLOCKS)})_\w+", name
            ):
                problems.add(f"{label}: public function is not analyze_<block>_*")
                continue
            parameters = list(inspect.signature(function).parameters.values())
            hints = _hints(function)
            positional = [p for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            if len(positional) != 1:
                problems.add(f"{label}: needs exactly one positional measurement input")
            else:
                annotation = hints[positional[0].name]
                if not (
                    all(_is_measurement(member) for member in _members(annotation))
                    or _sequence_of(annotation, _is_measurement)
                ):
                    problems.add(f"{label}: positional input is not Meas* or Sequence[Meas*]")
            for parameter in parameters:
                if parameter in positional:
                    continue
                if parameter.kind is not parameter.KEYWORD_ONLY:
                    problems.add(f"{label}: {parameter.name} is not keyword-only")
                    continue
                members = [member for member in _members(hints[parameter.name]) if member is not type(None)]
                if not members or not all(
                    _is_analysis(member) or _sequence_of(member, _is_analysis) for member in members
                ):
                    problems.add(f"{label}: {parameter.name} is a setting, not a prior Analysis result")
            result = hints.get("return")
            if not _is_analysis(result):
                problems.add(f"{label}: does not return an Analysis subclass")
                continue
            # its own result type, or another block's of the same thing (the CDAC's switching curves
            # as the comparator's decisions: analyze_cdac_decisions -> comp.AnalysisDecisions)
            own = typing.cast(type, result).__name__.removeprefix("Analysis")
            thing = name.removeprefix("analyze_")
            if not (
                _camel(thing).startswith(own)
                or (result.__module__.startswith("flow.") and _camel(thing.split("_", 1)[1]).startswith(own))
            ):
                problems.add(f"{label}: returns {typing.cast(type, result).__name__}, not its own result type")
            prior_types = {
                member
                for parameter in parameters[1:]
                for annotation in _members(hints[parameter.name])
                for member in (annotation, *typing.get_args(annotation))
            }
            if result in prior_types:
                problems.add(f"{label}: returns the type of one of its prior results")
    return problems


def test_analysis_functions_follow_the_contract() -> None:
    assert _contract_problems() <= KNOWN_SIGNATURE_VIOLATIONS


def _analysis_classes() -> list[type]:
    return [
        value
        for module in (analysis_types, *map(_module, BLOCK_ANALYSES))
        for name, value in vars(module).items()
        if name.startswith("Analysis")
        and isinstance(value, type)
        and value is not analysis_types.Analysis
        and value.__module__ == module.__name__
    ]


def test_every_result_class_derives_from_the_analysis_base() -> None:
    assert _analysis_classes()
    assert [cls.__name__ for cls in _analysis_classes() if not issubclass(cls, analysis_types.Analysis)] == []


def _field_hints(cls: type) -> dict[str, object]:
    return typing.get_type_hints(cls, localns=TYPE_NAMESPACE)


def _contains_analysis(annotation) -> bool:
    annotation = _unalias(annotation)
    if _is_analysis(annotation):
        return True
    return any(_contains_analysis(arg) for arg in typing.get_args(annotation) if arg is not Ellipsis)


def test_results_never_contain_other_results() -> None:
    nested = {
        f"{cls.__name__}.{name}"
        for cls in _analysis_classes()
        for name, annotation in _field_hints(cls).items()
        if _contains_analysis(annotation)
    }
    assert nested == set()


def _persistable(annotation) -> bool:
    """Return whether the native HDF5 writer in io.py can store a value of this type."""

    annotation = _unalias(annotation)
    origin = typing.get_origin(annotation)
    if annotation in (int, float, bool, str, type(None)) or annotation is np.ndarray:
        return True
    if origin is np.ndarray or origin is typing.Literal:
        return True
    if isinstance(annotation, types.UnionType) or origin is typing.Union:
        return all(_persistable(member) for member in typing.get_args(annotation))
    if origin is tuple:
        return all(_persistable(arg) for arg in typing.get_args(annotation) if arg is not Ellipsis)
    if origin is dict:
        key, value = typing.get_args(annotation)
        return key is str and _persistable(value)
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return True
    return isinstance(annotation, type) and hasattr(annotation, "__dataclass_fields__")


def test_every_result_field_is_persistable() -> None:
    # the identity's design parameters are any block's (flow.pipeline.Analysis.dut), stored by type
    identity = {data_field.name for data_field in dataclasses.fields(analysis_types.Analysis)}
    unsupported = {
        f"{cls.__name__}.{name}: {annotation}"
        for cls in _analysis_classes()
        for name, annotation in _field_hints(cls).items()
        if not _persistable(annotation) and not (name in identity and annotation is typing.Any)
    }
    assert unsupported == set()


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _source_problems() -> set[str]:
    problems = set()
    forbidden_imports = {"csv", "json", "yaml", "pickle", "h5py", "subprocess"}
    forbidden_attribute_calls = {"write_text", "write_bytes", "open", "to_csv", "savetxt", "save", "savez"}
    analysis_names = {name for module_name in CONTRACT_MODULES for name, _function in _public_functions(module_name)}
    for module_name in PURE_MODULES:
        tree = _tree(_path(module_name))
        for node in tree.body:
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
                if isinstance(node, ast.AnnAssign)
                else []
            )
            for target in targets:
                if isinstance(target, ast.Name) and re.fullmatch(r"[A-Z][A-Z0-9_]*", target.id):
                    problems.add(f"{module_name}: module constant {target.id}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                problems |= {
                    f"{module_name}: imports {alias.name}"
                    for alias in node.names
                    if alias.name.split(".")[0] in forbidden_imports
                }
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in forbidden_imports:
                problems.add(f"{module_name}: imports {node.module}")
            elif isinstance(node, ast.ImportFrom) and node.module == "flow.scans.params":
                problems.add(f"{module_name}: reads scan configuration files")
            elif isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name) and function.id == "open":
                    problems.add(f"{module_name}: calls open")
                if isinstance(function, ast.Attribute) and function.attr in forbidden_attribute_calls:
                    problems.add(f"{module_name}: calls .{function.attr}")
        if module_name not in CONTRACT_MODULES:
            continue
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            for node in ast.walk(function):
                if isinstance(node, ast.Call):
                    callee = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                    if callee in analysis_names:
                        problems.add(f"{module_name}.{function.name}: calls analysis {callee}")
    return problems


def test_analysis_modules_are_pure_and_never_nest_analyses() -> None:
    assert _source_problems() <= KNOWN_SOURCE_VIOLATIONS


# the studies: the *_study targets in the blocks' targets.py, and what they share
STUDY_MODULES = (ANALYSIS_DIR / "studies.py", *sorted(ANALYSIS_DIR.parent.glob("*/targets.py")))


def test_studies_write_only_analysis_results_and_figures() -> None:
    problems = set()
    for node in (node for path in STUDY_MODULES for node in ast.walk(_tree(path))):
        if isinstance(node, ast.Import):
            problems |= {
                alias.name
                for alias in node.names
                if alias.name in {"csv", "json", "yaml", "pickle", "subprocess", "h5py"}
            }
        elif isinstance(node, ast.ImportFrom) and node.module in {
            "csv",
            "json",
            "yaml",
            "pickle",
            "subprocess",
            "h5py",
        }:
            problems.add(node.module)
        elif isinstance(node, ast.Call):
            function = node.func
            name = function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")
            if name in {"open", "write_text", "write_bytes", "to_csv", "savetxt", "write_measurement"}:
                problems.add(name)
    assert problems == set()


# FRIDA's current architecture: 16 capacitors, 17 decisions, 12-bit codes,
# and the reference comparator recipe of the sequence study.
ARCHITECTURE_LITERALS = {15, 16, 17, 4095, 4096}
ARCHITECTURE_STRINGS = {"comp11110000"}
# Allowed literals, each with its reason: (module, value) pairs.
ARCHITECTURE_ALLOWLIST: set[tuple[str, object]] = set()


@pytest.mark.parametrize("module_name", (*CONTRACT_MODULES, "types"))
def test_no_current_architecture_literals_remain(module_name: str) -> None:
    tree = _tree(_path(module_name))
    found = {
        (module_name, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and not isinstance(node.value, bool)
        and (
            (isinstance(node.value, int) and node.value in ARCHITECTURE_LITERALS)
            or (isinstance(node.value, str) and any(text in node.value for text in ARCHITECTURE_STRINGS))
        )
    }
    assert found <= ARCHITECTURE_ALLOWLIST


# Only these modules may define private helper functions or classes. Analysis,
# plotting, and study code keep their logic inside their public functions.
HELPER_MODULES = {"types", "io", "calc"}


@pytest.mark.parametrize(
    "module_path",
    sorted(
        [
            *(
                path
                for path in ANALYSIS_DIR.glob("*.py")
                if not path.name.startswith("test_") and path.stem not in {*HELPER_MODULES, "__init__"}
            ),
            *map(_path, (*BLOCK_ANALYSES, *BLOCK_PLOTS)),
        ]
    ),
    ids=lambda path: f"{path.parent.name}.{path.stem}",
)
def test_only_types_io_and_calc_define_helpers_or_classes(module_path: Path) -> None:
    tree = _tree(module_path)
    problems = {
        f"{node.name} (private helper)"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_")
    }
    # a block's analysis module holds its own Meas* and Analysis* result types, nothing else
    block_types = module_path.stem == "analysis" and module_path.parent.name in {
        block.rpartition(".")[2] for block in BLOCKS
    }
    problems |= {
        f"{node.name} (class)"
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and not (block_types and node in tree.body and re.fullmatch(r"(Meas|Analysis)[A-Z]\w+", node.name))
    }
    problems |= {
        f"{function.name}.{node.name} (nested function)"
        for function in tree.body
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(function)
        if node is not function and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert problems == set()


def _measurement_classes() -> list[type]:
    """Every Meas subclass its module exports, found by inheritance alone."""

    pending, found = [analysis_types.Meas], []
    while pending:
        for subclass in pending.pop().__subclasses__():
            pending.append(subclass)
            # dataclass(slots=True) replaces each class; skip the discarded originals.
            if getattr(importlib.import_module(subclass.__module__), subclass.__qualname__, None) is subclass:
                found.append(subclass)
    return found


def test_every_measurement_class_follows_the_meas_base() -> None:
    """A measurement class adds only per-record readback arrays to the base fields.

    The HDF5 reader finds a class by its stored type name, so a new class needs
    no registration; this test is what holds every one of them to one shape.
    """

    base = {data_field.name for data_field in dataclasses.fields(analysis_types.Meas)}
    problems = set()
    assert _measurement_classes()
    for cls in _measurement_classes():
        params = getattr(cls, "__dataclass_params__", None)
        if not cls.__name__.startswith("Meas") or params is None:
            problems.add(f"{cls.__name__}: not a Meas* dataclass")
            continue
        if not (params.frozen and params.kw_only and "__slots__" in vars(cls)):
            problems.add(f"{cls.__name__}: not a frozen, slotted, keyword-only dataclass")
        for name, annotation in _field_hints(cls).items():
            if name in base:
                continue
            if not all(member is np.ndarray or member is type(None) for member in _members(annotation)):
                problems.add(f"{cls.__name__}.{name}: readback fields must be arrays, got {annotation}")
    assert problems == set()


# The only functions the plotting and study modules may define.
PUBLIC_FUNCTION_NAMES = {
    "plots": r"plot_\w+|style_\w+|save_figure",
    # the studies themselves are targets in the blocks' targets.py
    "studies": r"(?!)",
}


@pytest.mark.parametrize("module_name", sorted([*PUBLIC_FUNCTION_NAMES, *BLOCK_PLOTS]))
def test_plots_and_studies_define_only_their_public_kinds_of_function(module_name: str) -> None:
    tree = _tree(_path(module_name))
    pattern = (
        PUBLIC_FUNCTION_NAMES[module_name]
        if module_name in PUBLIC_FUNCTION_NAMES
        else rf"plot_{module_name.split('.')[-2]}_\w+"
    )
    unexpected = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not re.fullmatch(pattern, node.name)
    }
    assert unexpected == set()
