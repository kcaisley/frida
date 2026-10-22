"""Design-space sweeps: every block's circuits at several sizes of their key devices, in every PDK,
each instance characterized at its nominal point and over its conditions, and laid out by ALIGN.

An instance is its parameters (the block generator's parameter class), nothing else: no name. Its
id is ``<pdk>__<digest>``, the digest the first 12 hex digits of the SHA-1 of its flat parameters
(``flat_params`` as canonical JSON: ``flow.sweep.runner.digest``), and it runs in
``build/sweep/<block>/<run>/<pdk>/<digest>/``; the behavioral models look a characterization up by
the same digest (``flow.sweep.lookup``), so a model's parameters find the sweep's instance.

A block takes part with a module ``flow/<block>/sweep.py``:

- ``instances(pdk) -> list[Params]``: its design space in ``pdk`` as parameter values, built from
  unnamed lists of partial parameter dicts (the structures, the sizes), their products and the
  generator's validity filter; an empty list where the block does not run in that PDK. Parameter
  values another block's design space reuses (a comparator in the ADC's) are module constants.
- ``cost(pdk, params) -> float`` (optional): an instance's relative run time; the runner starts
  the longest first.
- ``GENERATOR``: the block's generator, whose compiled devices give the geometry metrics.
- ``characterize(run_dir, pdk, params) -> Record``: simulate the instance in ``run_dir``, in
  under five minutes.
- ``layout_netlist(run_dir, pdk, params) -> Path`` (optional): the netlist ALIGN lays out on its
  own, where the instance has no hand-written floorplan or ALIGN fails by it.
- ``layout_floorplan(run_dir, pdk, params) -> (netlist, floorplan)`` (optional): the netlist ALIGN
  places by a hand-written floorplan, and that floorplan.
- ``STRUCTURE`` (optional, without ``layout_floorplan``): the parameters that make the circuit's
  devices and their wiring. An instance is placed by the floorplan of the block's named case
  (``subckt.CASES``) of the same structure, ``design/layout/<block>_<case>.json``, with the block's
  ``write_netlist`` (``flow.sweep.runner.hand_floorplan``), where both exist.

A ``Record`` holds the instance's scalar ``metrics`` (each name ends in its unit, as the
analyses' fields do: ``_s``, ``_j``, ``_v``, ``_w``, ``_um2``), its ``details`` (plots of its
condition sweeps, each plotted on its own data, or figures drawn by the analysis plots) and ``waves`` (measurement files under ``build/`` holding transient waveforms, by
label).

    uv run python -m flow comp.sweep      # one block: characterize, lay out, tabulate
    uv run python -m flow sweep.run       # every block (sweep.missing, sweep.layout, sweep.tables)
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
    figure: str | None = None  # an SVG under build/ the viewer shows in place of the plot (x, series empty)
    # step lines over x, each {"y": [...], "count": n}: how many records took it (the ADC's decision
    # paths), drawn weighted by their counts beside or instead of the series
    paths: list[dict] = field(default_factory=list)
    # each axis's ticks where its values alone do not say (the viewer's paperLayout infers them
    # otherwise: whole numbers tick at whole numbers, log axes at decades or 1, 2 and 5):
    # "integer" (whole-number ticks, never an exponent), "code" (an output code or a code estimate:
    # as "integer", whatever the values), "step" (a decision or stage index: 0 and at least every
    # even step labelled, every step ticked) or "real" (continuous, though the values are whole)
    x_ticks: str | None = None
    y_ticks: str | None = None
    # the series are a histogram: each y the count in the bin one unit wide centred on its x (an
    # output code), drawn as a step outline without markers or fill, so compared instances overlay
    histogram: bool = False


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
