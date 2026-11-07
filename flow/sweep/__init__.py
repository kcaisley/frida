"""Design-space sweeps: every block's circuits at several sizes of their key devices, in every PDK,
each instance characterized at its nominal point and over its conditions, and laid out by ALIGN.

An instance is its parameters (the block generator's parameter class), nothing else: no name. Its
id is ``<pdk>__<digest>``, the digest the first 12 hex digits of the SHA-1 of its flat parameters
(``flat_params`` as canonical JSON: ``flow.sweep.runner.digest``), and it runs in
``build/<block>/<run>/<pdk>/<digest>/``; the behavioral models look a characterization up by
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

A ``Record`` (``flow.pipeline.Record``) holds the instance's scalar ``metrics`` (each name ends in
its unit, as the analyses' fields do: ``_s``, ``_j``, ``_v``, ``_w``, ``_um2``), its ``details``
(``flow.pipeline.Plot`` specs of its condition sweeps, each plotted on its own data, or figures
drawn by the analysis plots) and ``waves`` (measurement files under ``build/`` holding transient
waveforms, by label). A block gives its design space as grids and named instances
(``flow.pipeline.grid``, ``named``; a block not yet typed so, its ``params.valid(params, pdk)``
keeps what works in a PDK); a block on the pipeline (docs/pipeline.md) gives ``runs`` and
``record``, another ``characterize`` and ``GENERATOR``. Its layout is its generator's to state; the
shared layout step lays it out (``flow.layout.step``), or, a block assembled from laid-out blocks
(the ADC), its own ``layout.py``.

    uv run python -m flow run comp        # one block on the pipeline (layout comp, table comp)
    uv run python -m flow sweep.run       # every block (sweep.missing, sweep.layout, sweep.tables)
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from importlib import import_module

import hdl21 as h

# Parameters a class gained after its instances ran, by the class (its module and name, a nested
# one too) and the parameter, with the value every earlier instance has: a flat row leaves them out
# at that value, so the earlier instances keep their rows and digests (flow.sweep.runner.digest) and
# are found as before. Only that class's: another class's parameter of the same name, which its
# instances always held, stays in their rows.
ADDED_DEFAULTS: dict[tuple[str, str], object] = {
    ("flow.capdac.params.Params", "weights"): None,  # an array's own weights (a fabricated one's)
}


def flat_params(params, prefix: str = "") -> dict[str, float | int | str | bool | None]:
    """A parameter class as one flat row: nested classes by dotted names, enumerations by name,
    sizes as numbers; a parameter its class gained later (``ADDED_DEFAULTS``) only where it differs
    from its default."""

    flat = {}
    owner = f"{type(params).__module__}.{type(params).__qualname__}"
    for name, value in vars(params).items():
        if (owner, name) in ADDED_DEFAULTS and value == ADDED_DEFAULTS[owner, name]:
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
    submodule: a comparator, a sampling switch), standard (a library cell) or opaque (an external
    cell written as a subcircuit that is neither the library's nor a device: a netlist included from
    a file, the ADC's digital block or a fabricated converter's black box, whose contents its netlist
    does not hold), none in a leaf (primitives alone); its devices, every primitive through its
    hierarchy (transistors, capacitors, resistors; a library cell's or an opaque cell's own are not
    in its netlist); and its device area (um2), every device and library cell's own footprint,
    unplaced: the row cell the layout flows draw for it (``netcells.area``, in a process bound to
    ``pdk``; an ideal element and an opaque cell have none)."""

    from io import StringIO

    import vlsirtools
    from hdl21.flatten import flatten

    from flow.circuit.netlists import Block, Context, package
    from flow.layout.pdkproc import access_points, in_pdk

    # a library cell by its name: older wrappers name their domain otherwise (IHP130's "ihp")
    library = set(import_module(f"pdk.{pdk}.hdl21.cells").CELLS)
    totals = {"child_cells": 0.0, "devices": 0.0}
    # each external cell's instances but the library's, (at the top, multiplicity): a device's, or
    # an opaque cell's (``opaque``, below)
    externals: dict[str, list[tuple[bool, float]]] = {}

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
            count = float(getattr(getattr(target, "params", None), "m", 1) or 1)
            totals["devices"] += count
            if isinstance(target, h.ExternalModuleCall):
                externals.setdefault(target.module.name, []).append((top, count))

    walk(module, True)
    # every device once, flat (hdl21's flatten), as vlsir writes it before the LVS deck's rules
    out = StringIO()
    vlsirtools.netlist(package(Block(flatten(module), pdk, module.name, []), Context.LVS), out, fmt="cdl")
    # each statement as written, its continuation lines ("+") with it
    statements: list[list[str]] = []
    for line in out.getvalue().splitlines():
        if line.startswith("+") and statements:
            statements[-1].append(line)
        else:
            statements.append([line])

    def called(statement: list[str]) -> str | None:
        """The cell a subcircuit instance calls (its last field); None for any other statement."""
        fields = " ".join(line.lstrip("+") for line in statement).split()
        return fields[-1] if fields and fields[0][:1] in "Xx" else None

    # an opaque cell: an external one written as a subcircuit instance (a device is a primitive's
    # line), not the library's; a child cell, nothing of it counted
    opaque = {name for name in map(called, statements) if name is not None} & set(externals)
    for name in opaque:
        for top, count in externals[name]:
            totals["devices"] -= count
            totals["child_cells"] += top
    if not totals["child_cells"]:
        del totals["child_cells"]
    # the netlist as written, without an opaque cell's instances
    text = "".join(line + "\n" for statement in statements if called(statement) not in opaque for line in statement)
    if any(line[:1] in "Xx" for line in text.splitlines()):
        access_points(pdk)  # the library cells' footprints, written the first time a PDK needs them
    totals["device_area_um2"] = in_pdk(pdk, "netcells", "area", text)
    return totals
