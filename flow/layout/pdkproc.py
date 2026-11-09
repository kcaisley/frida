"""Run a layout step in a child process bound to one PDK.

The row-cell engine (``flow/layout/rows``) and the tool drivers read the PDK at import time:
``import tech`` and ``from paths import ...`` resolve to ``pdk/<pdk>/layout``. One Python process
can therefore only serve one PDK. ``in_pdk`` calls a function in a fresh spawned process whose
import path puts ``pdk/<pdk>/layout`` and ``flow/layout/rows`` first, so a runner can lay out
several PDKs in turn without the engine passing ``tech`` around. Arguments and return values
must be picklable (paths, strings, numbers, dicts).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from importlib import import_module
from pathlib import Path
from typing import Any

from flow.logs import spawned

ROOT = Path(__file__).resolve().parents[2]


def pdk_paths(pdk: str) -> list[str]:
    """The import path entries that bind the engine to one PDK: its layout values, then the row engine."""

    layout = ROOT / "pdk" / pdk / "layout"
    if not (layout / "tech.py").is_file():
        raise FileNotFoundError(f"pdk/{pdk}/layout/tech.py is missing; is the PDK submodule checked out?")
    return [str(layout), str(ROOT / "flow" / "layout" / "rows")]


def _bind(paths: list[str], environ: dict[str, str]) -> None:
    sys.path[:0] = paths
    os.environ.update(environ)


def _call(module: str, function: str, args: tuple, kwargs: dict) -> Any:
    return getattr(import_module(module), function)(*args, **kwargs)


def _value(module: str, name: str, default: Any) -> Any:
    return getattr(import_module(module), name, default)


def in_pdk(
    pdk: str, module: str, function: str, *args: Any, environ: dict[str, str] | None = None, **kwargs: Any
) -> Any:
    """Call ``module.function(*args, **kwargs)`` in a fresh process bound to ``pdk``.

    ``environ`` adds environment variables in the child only (e.g. ``ROWS_STD_DENSE``). What the
    child logs is logged here (``flow.logs.spawned``). An exception in the child is raised here; a child that
    dies raises ``BrokenProcessPool``.
    """

    with spawned(1, initializer=_bind, initargs=(pdk_paths(pdk), dict(environ or {}))) as pool:
        return pool.submit(_call, module, function, args, kwargs).result()


def pdk_value(pdk: str, module: str, name: str, default: Any = None) -> Any:
    """One value of a PDK's layout module (``tech`` or ``paths``), read in a process bound to it."""

    return in_pdk(pdk, __name__, "_value", module, name, default)


def access_points(pdk: str, cells: Iterable[str] = ()) -> Path:
    """The PDK's standard-cell access points (its ``paths.ACCESS_JSON``), which the row cells
    read at import: its row cells' and ``cells'``, library cells a netlist names;
    ``rows/stdcell_access.py`` adds a cell's the first time a build needs them."""

    path = Path(pdk_value(pdk, "paths", "ACCESS_JSON"))
    cells = tuple(cells)
    if not path.exists() or not set(cells) <= set(json.loads(path.read_text())):
        in_pdk(pdk, "stdcell_access", "write_access", pdk, cells)
    return path
