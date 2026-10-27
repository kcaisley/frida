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

A ``Record`` (``flow.pipeline.Record``) holds the instance's scalar ``metrics`` (each name ends in
its unit, as the analyses' fields do: ``_s``, ``_j``, ``_v``, ``_w``, ``_um2``), its ``details``
(``flow.pipeline.Plot`` specs of its condition sweeps, each plotted on its own data, or figures
drawn by the analysis plots) and ``waves`` (measurement files under ``build/`` holding transient
waveforms, by label). A block gives its design space as grids and named instances
(``flow.pipeline.grid``, ``named``; a block not yet typed so, its ``params.valid(params, pdk)``
keeps what works in a PDK); a block on the pipeline (docs/pipeline.md) gives ``runs`` and
``record``, another ``characterize`` and ``GENERATOR`` (the ADC's behavioral model); its
``layout.py`` gives the layout hooks.

    uv run python -m flow run comp        # one block on the pipeline (layout comp, table comp)
    uv run python -m flow sweep.run       # every block (sweep.missing, sweep.layout, sweep.tables)
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from importlib import import_module

import hdl21 as h

# Parameters a block's class gained after its instances ran, by name (in a nested class too), with
# the value every earlier instance has: a flat row leaves them out at that value, so the earlier
# instances keep their rows and digests (flow.sweep.runner.digest) and are found as before.
ADDED_DEFAULTS: dict[str, object] = {}  # none since the comparator's parameters were redefined


def flat_params(params, prefix: str = "") -> dict[str, float | int | str | bool | None]:
    """A parameter class as one flat row: nested classes by dotted names, enumerations by name,
    sizes as numbers; a parameter added later (``ADDED_DEFAULTS``) only where it differs from its
    default."""

    flat = {}
    for name, value in vars(params).items():
        if name in ADDED_DEFAULTS and value == ADDED_DEFAULTS[name]:
            continue
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
    """A compiled module's size: where it has any, its child cells, the cells directly in it, custom (a
    submodule: a comparator, a sampling switch) or standard (a library cell), none in a leaf
    (primitives alone); its devices, every primitive through its hierarchy (transistors, capacitors,
    resistors; a library cell's own are not in its netlist); and its device area (um2), every device
    and library cell's own footprint, unplaced: the row cell the layout flows draw for it
    (``netcells.area``, in a process bound to ``pdk``; an ideal element has none)."""

    from flow.circuit.devices import instance_lines
    from flow.layout.pdkproc import access_points, in_pdk

    # a library cell by its name: older wrappers name their domain otherwise (IHP130's "ihp")
    library = set(import_module(f"pdk.{pdk}.hdl21.cells").CELLS)
    totals = {"child_cells": 0.0, "devices": 0.0}

    def walk(module: h.Module, top: bool) -> None:
        for instance in module.instances.values():
            target = instance.of
            if isinstance(target, h.Module) or (
                isinstance(target, h.ExternalModuleCall) and target.module.name in library
            ):
                totals["child_cells"] += top
                if isinstance(target, h.Module):
                    walk(target, False)
                continue
            totals["devices"] += float(getattr(getattr(target, "params", None), "m", 1) or 1)

    walk(module, True)
    if not totals["child_cells"]:
        del totals["child_cells"]
    lines = instance_lines(module)
    if any(line[0] in "Xx" for line in lines):
        access_points(pdk)  # the library cells' footprints, written the first time a PDK needs them
    totals["device_area_um2"] = in_pdk(pdk, "netcells", "area", "\n".join(lines))
    return totals
