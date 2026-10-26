"""The comparator's netlists, pinned: every instance its code makes (each family's and named
instance, each topology with a PMOS input pair and with a dynamic bias) gives the netlists recorded
in ``netlists.json``, so a refactor of ``Params`` or ``netlist`` that changes any circuit fails.

Two records per instance: its structure before any PDK compile (each instance's name, primitive,
parameters and connections, in order; no PDK needed), and, in each installed PDK where
``params.valid`` admits it, the flat SPICE of both output stages after the PDK's compile
(``layout.write_netlist``; ``site_pdk``). Only hashes are recorded: the PDKs' netlists stay private.

    uv run python -m flow.comp.test_netlists   # rewrite netlists.json (only after a reviewed change)
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import tempfile
from pathlib import Path

import pytest
from hdl21.primitives import MosType

from flow import pipeline

from . import sweep
from .layout import PDKS, write_netlist
from .params import TOPOLOGIES, TOPOLOGY_SIZES, Bias, OutputStage, Params, valid
from .subckt import netlist

RECORD = Path(__file__).with_name("netlists.json")


def corpus(pdk: str | None) -> dict[str, Params]:
    """Every comparator the code makes, by a label stable across refactors: the design space's
    instances (``family(knob=value, ...)``), the named instances, and each topology at the
    characterization's sizes with a PMOS input pair (``<topology>+pmos``) and with a dynamic bias
    (``<topology>+dynamic``); in ``pdk``, those ``valid`` admits there."""

    from flow.sweep.runner import labelled_space

    instances: dict[str, Params] = {}
    for label, params in labelled_space("comp", pdk or "tsmc65").values():
        instances.setdefault(label, params)
    for name, named in pipeline.names(sweep).items():
        instances.setdefault(name, named())
    for topology, structure in TOPOLOGIES.items():
        base = {**structure, **TOPOLOGY_SIZES}
        instances[f"{topology}+pmos"] = Params(**{**base, "input_pair": MosType.PMOS})
        instances[f"{topology}+dynamic"] = Params(**{**base, "bias": Bias.DYNAMIC, "preamp_c_ff": 60})
    return {label: params for label, params in instances.items() if valid(params, pdk)}


def structure(params: Params) -> str:
    """The comparator before any PDK compile, as text: each instance's name, what it instantiates
    with which parameters, and its connections, in the generator's order."""

    manager = importlib.import_module("hdl21.pdk.pdk")._mgr
    previous = manager.default
    manager.default = None
    try:
        netlist.Cache.reset()
        module = netlist(params)
        lines = [f"ports {' '.join(module.ports)}"]
        for name, inst in module.instances.items():
            call = inst.of
            target = getattr(call, "prim", None) or getattr(call, "module", None)
            conns = " ".join(f"{port}={signal.name}" for port, signal in inst.conns.items())
            lines.append(f"{name} {getattr(target, 'name', target)} {call.params!r} {conns}")
        return "\n".join(lines) + "\n"
    finally:
        netlist.Cache.reset()
        manager.default = previous


def compiled(params: Params, pdk: str) -> str:
    """Both output stages' flat SPICE after ``pdk``'s compile."""

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    texts = []
    with tempfile.TemporaryDirectory() as folder:
        for stage in (OutputStage.TRANSISTORS, OutputStage.STDCELLS):
            path = write_netlist(Params(**{**params.__dict__, "output_stage": stage}), Path(folder) / "comp.sp", logic)
            texts.append(path.read_text())
    return "".join(texts)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def hashes(pdk: str | None) -> dict[str, str]:
    """Each instance's hash in ``pdk`` (None: its structure before any compile); a generator that
    raises records its error's type."""

    record = {}
    for label, params in corpus(pdk).items():
        try:
            record[label] = digest(structure(params) if pdk is None else compiled(params, pdk))
        except Exception as error:  # noqa: BLE001 - an error is part of what is pinned
            record[label] = f"error: {type(error).__name__}"
    return record


def installed() -> list[str]:
    return [pdk for pdk in PDKS if importlib.util.find_spec(f"pdk.{pdk}.hdl21") is not None]


def test_structures_unchanged() -> None:
    assert hashes(None) == json.loads(RECORD.read_text())["structure"]


@pytest.mark.site_pdk
@pytest.mark.parametrize("pdk", PDKS)
def test_compiled_netlists_unchanged(pdk: str) -> None:
    if pdk not in installed():
        pytest.skip(f"{pdk} is not installed")
    assert hashes(pdk) == json.loads(RECORD.read_text())[pdk]


if __name__ == "__main__":
    record = {"structure": hashes(None), **{pdk: hashes(pdk) for pdk in installed()}}
    RECORD.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    print({key: len(value) for key, value in record.items()})
