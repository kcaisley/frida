"""Design-space sweeps: every block's topologies at several sizings of their key devices, in every
PDK, each instance characterized at its nominal point and over its conditions, and laid out by
ALIGN.

A block takes part with a module ``flow/<block>/sweep.py``:

- ``TOPOLOGIES``: topology name -> the parameters that make it.
- ``SIZINGS``: sizing name -> the key devices' sizes (four to eight of them).
- ``GENERATOR``: the block's generator, whose compiled devices give the geometry metrics.
- ``params(pdk, topology, sizing)``: the block's parameters, or None where the two do not combine.
- ``characterize(run_dir, pdk, params) -> Record``: simulate the instance in ``run_dir``, in
  under five minutes.
- ``layout_netlist(run_dir, pdk, params) -> Path`` (optional): the netlist ALIGN lays out on its
  own, where the topology has no hand-written floorplan or ALIGN fails by it.
- ``layout_floorplan(run_dir, pdk, topology, params) -> (netlist, floorplan)`` (optional): the
  netlist ALIGN places by a floorplan; without it, ``design/layout/<block>_<topology>.json`` with
  the block's ``write_netlist``, where both exist.

A ``Record`` holds the instance's scalar ``metrics`` (each name ends in its unit, as the
analyses' fields do: ``_s``, ``_j``, ``_v``, ``_w``, ``_um2``), its ``details`` (plots of its
condition sweeps, whose axes the viewer fixes across a block's instances) and ``waves``
(measurement files under ``build/`` holding transient waveforms, by label).

    uv run python -m flow.sweep run [--blocks comp] [--pdks tsmc65] [--workers 36] [--failed]
    uv run python -m flow.sweep layout [--blocks comp] [--workers 28]
    uv run python -m flow.sweep table [--blocks comp]
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from enum import Enum
from importlib import import_module

import hdl21 as h


@dataclass
class Detail:
    """One condition sweep of an instance: each series' y over the shared x."""

    name: str  # stable key, the same for every instance of a block
    title: str
    x_label: str  # with its unit: "Common mode (V)"
    y_label: str
    x: list[float]
    series: dict[str, list[float]]  # label -> y at each x (NaN where the point failed)
    x_log: bool = False
    y_log: bool = False


@dataclass
class Record:
    """What one instance's characterization gives."""

    metrics: dict[str, float]
    details: list[Detail] = field(default_factory=list)
    waves: dict[str, str] = field(default_factory=dict)  # label -> measurement path under build/


def flat_params(params, prefix: str = "") -> dict[str, float | int | str | bool | None]:
    """A parameter class as one flat row: nested classes by dotted names, enumerations by name,
    sizes as numbers."""

    flat = {}
    for name, value in vars(params).items():
        key = f"{prefix}{name}"
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            flat |= flat_params(value, f"{key}.")
        elif isinstance(value, Enum):
            flat[key] = value.name
        elif isinstance(value, (bool, int, str)) or value is None:
            flat[key] = value
        elif isinstance(value, tuple):
            flat[key] = ", ".join(str(item.name if isinstance(item, Enum) else item) for item in value)
        else:
            try:
                flat[key] = float(value)
            except (TypeError, ValueError):
                flat[key] = str(value)
    return flat


def geometry(module: h.Module, pdk: str) -> dict[str, float]:
    """A compiled module's device count, total gate area (W L, um2) and standard-cell count."""

    xtors = {m.name for m in import_module(f"pdk.{pdk}.hdl21.primitives.prim_dicts").xtors.values()}
    # a library cell by its name: older wrappers name their domain otherwise (IHP130's "ihp")
    library = set(import_module(f"pdk.{pdk}.hdl21.cells").CELLS)
    totals = {"devices": 0.0, "gate_area_um2": 0.0, "cells": 0.0}

    def walk(module: h.Module, multiplier: float) -> None:
        for instance in module.instances.values():
            target = instance.of
            if isinstance(target, h.Module):
                walk(target, multiplier)
            elif isinstance(target, h.ExternalModuleCall) and target.module.name in xtors:
                params = target.params
                count = multiplier * float(getattr(params, "m", 1) or 1)
                width, length = float(getattr(params, "w", math.nan)), float(getattr(params, "l", math.nan))
                totals["devices"] += count
                totals["gate_area_um2"] += count * width * length * 1e12
            elif isinstance(target, h.ExternalModuleCall) and target.module.name in library:
                totals["cells"] += multiplier

    walk(module, 1.0)
    return totals
