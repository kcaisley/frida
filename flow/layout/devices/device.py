"""Precharacterized devices: what each kind of device is in each PDK, measured once and looked up.

A kind of device (``mosfet``, ``momcap``) is a package of this folder with one file a role:

- ``geometry.py``: what is drawn, the parameters its ALIGN primitive (``flow/layout/primitives``) takes;
- ``characterize.py``: draws or netlists geometries in a PDK, simulates (Spectre) or extracts them
  (KLayout-PEX), and writes the kind's table, ``pdk/<pdk>/devices/<kind>.json``, kept with the PDK;
- ``table.py``: the table read back, and its lookups: a request's value to a geometry, a geometry
  to its value;
- ``netlist.py``: the requests a block's generator makes, each an hdl21 module of ideal devices
  carrying its request as a Property (so a netlist simulates before any PDK), and each request's
  view in a PDK, its body made of the geometry the table gives.

A block's generator states what it needs (a capacitance, a drive resistance); ``resolve`` swaps
every request for its view in a PDK. The generator holds no PDK's dimensions; the result is the
PDK's own devices. Every table records the PDK, the corner, the method and the hash of the code
that made it (``provenance``), so a test finds a table older than its characterization.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import hdl21 as h

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

# the hdl21 Properties a request's module carries, and a view its geometry
_REQUEST = "frida.request"
_GEOMETRY = "frida.geometry"
_FLOOR = "frida.floor"


class FloorError(Exception):
    """A request below the smallest device a PDK draws, drawn at that smallest instead. ``resolve``
    returns these rather than raising them: the netlist carries what was drawn, and the caller
    decides whether to record the difference or stop."""


class Request(Protocol):
    """A device a generator asks for: resolved in a PDK to the module of its view there."""

    def resolve(self, pdk: str) -> h.Module: ...


@runtime_checkable
class AlignDrawn(Protocol):
    """A geometry ALIGN draws with a generator of the PDK's (``flow/layout/primitives``): the
    generator's name and the parameters it reads."""

    @property
    def align_generator(self) -> str: ...

    def align_parameters(self) -> dict[str, Any]: ...


def active_pdk() -> str | None:
    """The name of the PDK hdl21 is bound to (``h.pdk.default()``), or None."""
    pdk = h.pdk.default()
    return pdk.__name__.split(".")[1] if pdk is not None else None


def table_path(kind: str, pdk: str) -> Path:
    """Where ``pdk`` keeps the table of ``kind``: ``pdk/<pdk>/devices/<kind>.json``."""
    return ROOT / "pdk" / pdk / "devices" / f"{kind}.json"


def code_sha(kind: str) -> str:
    """The hash of the code that makes ``kind``'s numbers: its ``geometry.py`` and ``characterize.py``."""
    digest = hashlib.sha1()
    for name in ("geometry.py", "characterize.py"):
        digest.update((HERE / kind / name).read_bytes())
    return digest.hexdigest()[:12]


def write_table(kind: str, pdk: str, data: dict[str, Any], *, method: str) -> Path:
    """Write ``kind``'s table in ``pdk``: ``data`` under its provenance."""
    path = table_path(kind, pdk)
    path.parent.mkdir(parents=True, exist_ok=True)
    provenance = {
        "pdk": pdk,
        "kind": kind,
        "corner": "TYPICAL",
        "temperature_c": 25,
        "method": method,
        "code_sha": code_sha(kind),
        "date": datetime.now(UTC).date().isoformat(),
    }
    path.write_text(json.dumps({"provenance": provenance, **data}, indent=1) + "\n")
    return path


def read_table(kind: str, pdk: str) -> dict[str, Any]:
    """``kind``'s table in ``pdk``; a missing one names the command that makes it."""
    path = table_path(kind, pdk)
    if not path.is_file():
        raise FileNotFoundError(f"{path}: run python -m flow.layout.devices.{kind}.characterize {pdk}")
    return json.loads(path.read_text())


def mark(module: h.Module, request: Request) -> h.Module:
    """Give ``module`` the Property that says which request it stands for."""
    module.props.set(_REQUEST, request)
    return module


def place(module: h.Module, geometry: object, floor: FloorError | None = None) -> h.Module:
    """Give a view the Properties of the geometry it is drawn as and, where it is drawn at a PDK's
    smallest instead of its request, of that ``FloorError``."""
    module.props.set(_GEOMETRY, geometry)
    if floor is not None:
        module.props.set(_FLOOR, floor)
    return module


def geometry_of(module: object) -> object | None:
    """The geometry a view is drawn as, or None."""
    props = getattr(module, "props", None)
    return props.get(_GEOMETRY) if props is not None else None


def request_of(module: object) -> Request | None:
    """The request a module stands for, or None."""
    props = getattr(module, "props", None)
    return props.get(_REQUEST) if props is not None else None


_LOGGED: set[tuple[str, str]] = set()  # the views logged, each once a process


def _brief(request: object) -> str:
    """A request as one short line: its fields, floats to four digits, enumerations by name."""
    import dataclasses
    from enum import Enum

    if not dataclasses.is_dataclass(request):
        return str(request)
    shown = []
    for field in dataclasses.fields(request):
        value = getattr(request, field.name)
        text = value.name if isinstance(value, Enum) else f"{value:.4g}" if isinstance(value, float) else str(value)
        shown.append(f"{field.name}={text}")
    return f"{type(request).__name__}({', '.join(shown)})"


def resolve(module: h.Module, pdk: str) -> list[FloorError]:
    """Swap every request in ``module``'s hierarchy for its view in ``pdk``, in place, a request's
    view made once a PDK and shared by its instances, and requests whose views share a name (their
    content) sharing one; return the requests drawn at the PDK's smallest instead
    (``FloorError``), one for each instance."""
    h.pdk.set_default(import_module(f"pdk.{pdk}.hdl21").pdk_logic)  # the views' devices are the PDK's
    views: dict[int, h.Module] = {}
    named: dict[str, h.Module] = {}  # a view's name is its content: one module a name (hdl21's export holds to it)
    done: set[int] = set()
    floors: list[FloorError] = []

    def walk(parent: h.Module) -> None:
        if id(parent) in done:
            return
        done.add(id(parent))
        for name, instance in parent.instances.items():
            request = request_of(instance.of)
            if request is not None:
                key = id(instance.of)
                if key not in views:
                    view = request.resolve(pdk)
                    views[key] = named.setdefault(view.name, view)
                    if (pdk, views[key].name) not in _LOGGED:
                        _LOGGED.add((pdk, views[key].name))
                        logging.getLogger("flow.devices").info(f"{_brief(request)} -> {views[key].name}")
                instance.of = views[key]
                floor = views[key].props.get(_FLOOR)
                if floor is not None:
                    floors.append(FloorError(f"{parent.name}.{name}: {floor}"))
            elif isinstance(instance.of, h.Module):
                walk(instance.of)

    walk(module)
    return floors
