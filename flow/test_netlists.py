"""Every pipeline block's netlists, pinned: a migrated block that records them
(``flow/<block>/netlists.json``) makes the same circuits for every instance its code makes, so a
refactor of its ``Params`` or ``netlist`` that changes any circuit fails. A block without a record is
skipped until it records one.

The instances (``corpus``): its design space (each grid's, family's and named instance), every
combination of each problem's space's choices (``Problem.space``) at its base, and every other value
of each enumeration no space widens, the rest at their defaults. Two records per instance: its structure before any PDK compile (each
instance's name, primitive, parameters and connections, in order; no PDK needed), and, in each
installed PDK where ``params.valid`` admits it and the block's layout writes netlists
(``layout.write_netlist``), its flat SPICE after the PDK's compile (``site_pdk``). Only hashes are
recorded: the PDKs' netlists stay private.

    uv run python -m flow.test_netlists comp   # (re)record a block's netlists, only after a reviewed change
"""

from __future__ import annotations

import contextlib
import enum
import hashlib
import importlib
import importlib.util
import itertools
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from flow import pipeline
from flow.sweep.runner import PDKS, labelled_space
from flow.test_pipeline import MIGRATED, ROOT

# the PDK whose validity picks the instances recorded before any compile
STRUCTURE_PDK = "tsmc65"


def record_path(block: str) -> Path:
    return ROOT / "flow" / block / "netlists.json"


def corpus(block: str, pdk: str | None) -> dict[str, Any]:
    """Every instance of ``block`` its code makes, by a label stable across refactors: the design
    space's (``family(knob=value, ...)``, named instances by name), each combination of the searched
    choices (``choices(latch=STRONGARM, ...)``) and each held enumeration's other values
    (``held(vth=HIGH)``); in ``pdk``, those ``valid`` admits there."""

    sweep = importlib.import_module(f"flow.{block}.sweep")
    params = importlib.import_module(f"flow.{block}.params")
    Params = params.Params
    instances: dict[str, Any] = {}
    # a grid or a problem made of what this checkout lacks (a PDK's own data: its extracted arrays,
    # its supply) is left out, and the comparison with the record with it (``test_structures_unchanged``)
    with contextlib.suppress(LookupError, ModuleNotFoundError):
        for label, instance in labelled_space(block, pdk or STRUCTURE_PDK).values():
            instances.setdefault(label, instance)
    for name, named in pipeline.names(sweep).items():
        instances.setdefault(name, named())
    # each problem's space: every combination of its choices at its base; and every other value of each
    # enumeration no space widens, at the defaults
    spaces = []
    if importlib.util.find_spec(f"flow.{block}.opt") is not None:
        opt = importlib.import_module(f"flow.{block}.opt")
        with contextlib.suppress(ModuleNotFoundError):
            spaces = [made.space for made in pipeline.problems(opt, pdk or STRUCTURE_PDK).values() if made.space]
    shown = lambda value: getattr(value, "name", value)
    for space in spaces:
        choices = {
            name: widened.values
            for name, widened in space.widened.items()
            if isinstance(widened, pipeline.Values) and widened.when is None
        }
        for combination in itertools.product(*choices.values()):
            knobs = dict(zip(choices, combination, strict=True))
            label = f"choices({', '.join(f'{name}={shown(value)}' for name, value in knobs.items())})"
            instances[label] = Params(**{**space.base.__dict__, **knobs})
    widened = {name for space in spaces for name in space.widened}
    default = Params()
    for name, param in Params.__params__.items():
        dtype = param.dtype
        if name in widened or not (isinstance(dtype, type) and issubclass(dtype, enum.Enum)):
            continue
        for value in dtype:
            if value != getattr(default, name):
                instances[f"held({name}={value.name})"] = Params(**{name: value})
    valid = getattr(params, "valid", None)
    return {label: instance for label, instance in instances.items() if valid is None or valid(instance, pdk)}


def structure(block: str, instance: Any) -> str:
    """The block's circuit before any PDK compile, as text: each instance's name, what it
    instantiates with which parameters, and its connections, in the generator's order."""

    netlist = importlib.import_module(f"flow.{block}.subckt").netlist
    # no PDK at all: hdl21 takes the one PDK registered, if one is, for the default, so whichever PDK
    # another block's instances imported would size these
    manager = importlib.import_module("hdl21.pdk.pdk")._mgr
    previous = manager.default, manager.modules
    manager.default, manager.modules = None, set()
    try:
        netlist.Cache.reset()
        module = netlist(instance)
        lines = [f"ports {' '.join(module.ports)}"]
        for name, inst in module.instances.items():
            call = inst.of
            target = getattr(call, "prim", None) or getattr(call, "module", None)
            conns = " ".join(f"{port}={signal.name}" for port, signal in inst.conns.items())
            lines.append(f"{name} {getattr(target, 'name', target)} {call.params!r} {conns}")
        return "\n".join(lines) + "\n"
    finally:
        netlist.Cache.reset()
        manager.default, manager.modules = previous


def writer(block: str):
    """The block's layout's ``write_netlist`` (its flat SPICE after a PDK's compile), if it has one."""
    if importlib.util.find_spec(f"flow.{block}.layout") is None:
        return None
    return getattr(importlib.import_module(f"flow.{block}.layout"), "write_netlist", None)


def compiled(block: str, instance: Any, pdk: str) -> str:
    """The block's flat SPICE after ``pdk``'s compile."""

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    with tempfile.TemporaryDirectory() as folder:
        return writer(block)(instance, Path(folder) / f"{block}.sp", logic).read_text()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def hashes(block: str, pdk: str | None) -> dict[str, str]:
    """Each instance's hash in ``pdk`` (None: its structure before any compile); a generator that
    raises records its error's type."""

    record = {}
    for label, instance in corpus(block, pdk).items():
        try:
            record[label] = digest(structure(block, instance) if pdk is None else compiled(block, instance, pdk))
        except Exception as error:  # noqa: BLE001 - an error is part of what is pinned
            record[label] = f"error: {type(error).__name__}"
    return record


def installed() -> list[str]:
    return [pdk for pdk in PDKS if importlib.util.find_spec(f"pdk.{pdk}.hdl21") is not None]


def recorded(block: str) -> dict[str, dict[str, str]]:
    path = record_path(block)
    if not path.is_file():
        pytest.skip(f"{block} records no netlists: uv run python -m flow.test_netlists {block}")
    return json.loads(path.read_text())


@pytest.mark.parametrize("block", MIGRATED)
def test_structures_unchanged(block: str) -> None:
    """Every instance the block makes is recorded and its structure unchanged; all of the record's
    where the checkout has what they are made of (the PDKs and the build's extractions), else those
    it can make (CI's checkout has neither)."""
    record = recorded(block)
    current = hashes(block, None)
    if all(importlib.util.find_spec(f"pdk.{pdk}.hdl21") for pdk in PDKS) and (ROOT / "build").is_dir():
        assert current == record["structure"]
    # without them: each instance as recorded, by its label, or, where the record reached its circuit
    # under another (a searched choice's, made of a PDK's supply), by its circuit
    for label, value in current.items():
        assert record["structure"].get(label, value if value in record["structure"].values() else None) == value, label


@pytest.mark.site_pdk
@pytest.mark.parametrize("pdk", PDKS)
@pytest.mark.parametrize("block", MIGRATED)
def test_compiled_netlists_unchanged(block: str, pdk: str) -> None:
    record = recorded(block)
    if writer(block) is None:
        pytest.skip(f"{block}'s layout writes no netlists")
    if pdk not in installed():
        pytest.skip(f"{pdk} is not installed")
    assert hashes(block, pdk) == record[pdk]


if __name__ == "__main__":
    for block in sys.argv[1:] or MIGRATED:
        pdks = installed() if writer(block) is not None else []
        record = {"structure": hashes(block, None), **{pdk: hashes(block, pdk) for pdk in pdks}}
        record_path(block).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
        print(block, {key: len(value) for key, value in record.items()})
