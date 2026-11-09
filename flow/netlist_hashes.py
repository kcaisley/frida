"""Each pipeline block's netlists as hashes, recorded and compared by hand (not a test: the
netlists still change). Every instance its code makes (``corpus``), two hashes each: its structure
before any PDK compile (each instance's name, primitive, parameters and connections, in order; no
PDK needed), and, in each installed PDK where ``params.valid`` admits it, its netlist compiled
there as hdl21 and vlsir write it (``flow.layout.step.block_netlist``). Records go to
``build/netlists/<block>.json`` (hashes only: the PDKs' netlists stay private).

    uv run python -m flow.netlist_hashes record comp   # record a block's netlists (all blocks: none named)
    uv run python -m flow.netlist_hashes compare comp  # the instances whose hashes changed since
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

from flow import pipeline
from flow.sweep.runner import PDKS, labelled_space
from flow.test_pipeline import MIGRATED, ROOT

# the PDK whose validity picks the instances recorded before any compile
STRUCTURE_PDK = "tsmc65"


def record_path(block: str) -> Path:
    return ROOT / "build" / "netlists" / f"{block}.json"


def corpus(block: str, pdk: str | None) -> dict[str, Any]:
    """Every instance of ``block`` its code makes, by a label stable across refactors: the design
    searches' (``grid(knob=value, ...)``, singles by name), each combination of the searched
    choices (``choices(latch=STRONGARM, ...)``) and each held enumeration's other values
    (``held(vth=HIGH)``); in ``pdk``, those ``valid`` admits there."""

    search = importlib.import_module(f"flow.{block}.search")
    params = importlib.import_module(f"flow.{block}.params")
    Params = params.Params
    instances: dict[str, Any] = {}
    # a grid or a problem made of what this checkout lacks (a PDK's own data: its extracted arrays,
    # its supply) is left out, and so from the record and its comparison
    with contextlib.suppress(LookupError, ModuleNotFoundError):
        for label, instance in labelled_space(block, pdk or STRUCTURE_PDK).values():
            instances.setdefault(label, instance)
    for name, found in pipeline.searches(search).items():
        if isinstance(found, pipeline.Single):
            instances.setdefault(name, found())
    # each problem's space: every combination of its choices at its base; and every other value of each
    # enumeration no space widens, at the defaults
    spaces = []
    with contextlib.suppress(ModuleNotFoundError):
        optimizations = [found for found in pipeline.searches(search).values() if isinstance(found, pipeline.Optimize)]
        spaces = [made.space for made in (found.problem(pdk or STRUCTURE_PDK) for found in optimizations) if made.space]
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


def _net(signal: Any) -> str:
    """A connection by name: a bus bit by its bus and index."""
    if hasattr(signal, "parent") and hasattr(signal, "index"):
        return f"{signal.parent.name}[{signal.index}]"
    return signal.name


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
            conns = " ".join(f"{port}={_net(signal)}" for port, signal in inst.conns.items())
            # a module instantiated as it is (a leaf of the generator's own, the CDAC's plates): by
            # its instances' parameters
            params = getattr(call, "params", None)
            if params is None:
                params = [(leaf, getattr(inner.of, "params", None)) for leaf, inner in call.instances.items()]
            lines.append(f"{name} {getattr(target, 'name', target)} {params!r} {conns}")
        return "\n".join(lines) + "\n"
    finally:
        netlist.Cache.reset()
        manager.default, manager.modules = previous


def compiled(block: str, instance: Any, pdk: str) -> str:
    """The block's netlist compiled in ``pdk``, as hdl21 and vlsir write it (``flow.layout.step.block_netlist``)."""
    from flow.layout.step import block_netlist

    with tempfile.TemporaryDirectory() as folder:
        return block_netlist(block, instance, pdk, Path(folder) / f"{block}.cdl").read_text()


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


def record(block: str) -> dict[str, dict[str, str]]:
    """``block``'s hashes now: its structures, and its compiled netlists in each installed PDK."""
    pdks = installed()
    return {"structure": hashes(block, None), **{pdk: hashes(block, pdk) for pdk in pdks}}


def changed(block: str) -> dict[str, list[str]]:
    """The labels whose hash differs from ``block``'s record (or that one side lacks), by section."""
    before = json.loads(record_path(block).read_text())
    now = record(block)
    return {
        section: sorted(
            label
            for label in set(before.get(section, {})) | set(now.get(section, {}))
            if before.get(section, {}).get(label) != now.get(section, {}).get(label)
        )
        for section in sorted(set(before) | set(now))
    }


if __name__ == "__main__":
    verb, *blocks = sys.argv[1:] or ["record"]
    for block in blocks or MIGRATED:
        if verb == "record":
            path = record_path(block)
            path.parent.mkdir(parents=True, exist_ok=True)
            hashed = record(block)
            path.write_text(json.dumps(hashed, indent=1, sort_keys=True) + "\n")
            print(block, {key: len(value) for key, value in hashed.items()}, path)
        elif verb == "compare":
            print(block, {section: labels for section, labels in changed(block).items() if labels} or "unchanged")
        else:
            raise SystemExit("usage: python -m flow.netlist_hashes record|compare [block ...]")
