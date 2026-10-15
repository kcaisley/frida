"""Run a layout step in a child process bound to one PDK.

The row-cell engine (``flow/layout/stems``) and the tool drivers read the PDK at import time:
``import tech`` and ``from paths import ...`` resolve to ``pdk/<pdk>/layout``. One Python process
can therefore only serve one PDK. ``in_pdk`` calls a function in a fresh spawned process whose
import path puts ``pdk/<pdk>/layout`` and ``flow/layout/stems`` first, so a runner can lay out
several PDKs in turn without the engine passing ``tech`` around. Arguments and return values
must be picklable (paths, strings, numbers, dicts).
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def pdk_paths(pdk: str) -> list[str]:
    """The import path entries that bind the engine to one PDK: its layout values, then stems."""

    layout = ROOT / "pdk" / pdk / "layout"
    if not (layout / "tech.py").is_file():
        raise FileNotFoundError(f"pdk/{pdk}/layout/tech.py is missing; is the PDK submodule checked out?")
    return [str(layout), str(ROOT / "flow" / "layout" / "stems")]


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

    ``environ`` adds environment variables in the child only (e.g. ``STEMS_STD_DENSE``). An
    exception in the child is raised here; a child that dies raises ``BrokenProcessPool``.
    """

    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        1, mp_context=context, initializer=_bind, initargs=(pdk_paths(pdk), dict(environ or {}))
    ) as pool:
        return pool.submit(_call, module, function, args, kwargs).result()


def pdk_value(pdk: str, module: str, name: str, default: Any = None) -> Any:
    """One value of a PDK's layout module (``tech`` or ``paths``), read in a process bound to it."""

    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(1, mp_context=context, initializer=_bind, initargs=(pdk_paths(pdk), {})) as pool:
        return pool.submit(_value, module, name, default).result()


def access_points(pdk: str) -> Path:
    """The PDK's standard-cell access points (its ``paths.ACCESS_JSON``), which the row cells
    read at import; ``stems/stdcell_access.py`` writes them the first time a build needs them."""

    path = Path(pdk_value(pdk, "paths", "ACCESS_JSON"))
    if not path.exists():
        in_pdk(pdk, "stdcell_access", "write_access", pdk)
    return path
