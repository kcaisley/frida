"""A capacitance-only extraction read onto the schematic's nets: what the CLI's postsim step
back-annotates (``flow.sweep.runner.simulate``).

KLayout-PEX (``flow.layout.kpex``) names its nets by the layout's labels, and a net without one by
KLayout's number (``$6``: a gate's poly, which its extraction joins to no metal; a cell's inner
net). ``schematic_nets`` finds each in the LVS database by its probes (points on its shapes, by
their GDS layer, ``<stem>.probes.json``): the layout net there under the point, climbed from a
cell's net to its parent's through the cell's pins, and the schematic net LVS paired it with at the
top. ``annotation`` reads the extraction's capacitors onto those nets: a capacitor with an end on a
net that has none (a cell's inner net, one LVS paired with nothing) is left out and counted
unmapped, one whose ends are one schematic net is shorted out, and those between the same two nets
are summed; ground (``0``) stays ground. A cell's inner net is named by its path only where LVS is
flat (the kits' decks); a hierarchical LVS's pinless inner net is unmapped, the climb ending there.
Poly to substrate is taken as extracted (the device models' own capacitances are not taken off), and
capacitance through a floating net (a dummy gate) is left out, not reduced in series.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from klayout import db


@dataclass(frozen=True)
class Annotation:
    """An extraction on the schematic's nets: its capacitors between schematic nets (lower case,
    ``0`` for ground), the extraction's total, the part on schematic nets (those shorted out too),
    the capacitance of each layout net with no schematic net (to everything), and the share of the
    total those, and the nets the simulated DUT lacks (``flow.sweep.runner``), may reach."""

    capacitors: tuple[tuple[str, str, float], ...]
    total_f: float
    mapped_f: float
    unmapped: dict[str, float]
    limit: float = 0.05
    floating: dict[str, float] = field(default_factory=dict)
    floating_f: float = 0.0

    @property
    def unmapped_f(self) -> float:
        """The extraction's capacitance with an end on a net with no schematic net (a floating
        net's left out of it: ``floating_f``)."""
        return self.total_f - self.mapped_f - self.floating_f

    def summary(self) -> dict[str, Any]:
        """The annotation as a record holds it: its totals, the unmapped share and nets."""
        return {
            "capacitors": len(self.capacitors),
            "total_f": self.total_f,
            "mapped_f": self.mapped_f,
            "unmapped_f": self.unmapped_f,
            "unmapped_share": self.unmapped_f / self.total_f if self.total_f else 0.0,
            "unmapped_nets": self.unmapped,
            "floating_f": self.floating_f,
            "floating_nets": self.floating,
        }


def capacitors(netlist: Path) -> list[tuple[str, str, float]]:
    """The extraction's capacitors (``c_<n> ( a b ) capacitor c=<fF>f``): their nets and farads."""
    pattern = r"\s*c_\d+\s*\(\s*(\S+)\s+(\S+)\s*\)\s*capacitor\s+c=([0-9.eE+-]+)f"
    return [(a, b, float(c) * 1e-15) for a, b, c in re.findall(pattern, netlist.read_text())]


# a layout net LVS left out as floating (no device, no pin: a dummy poly, a dummy finger)
FLOATING = "<floating>"


def _probed(lvs: db.LayoutVsSchematic, layers: dict[tuple[int, int], db.Region], probe: list[int]) -> str | None:
    """The schematic net at the top that LVS paired with the layout net under ``probe`` (GDS layer,
    datatype, x, y in database units), climbed through its cells' pins; ``FLOATING`` where LVS kept
    no net there (a floating one it dropped); None where it has none (a layer it does not know, a
    net it did not pair)."""
    layer, datatype, x, y = probe
    if (layer, datatype) not in layers:
        return None
    path: list[db.SubCircuit] = []
    net = lvs.probe_net(layers[layer, datatype], db.Point(x, y), path)
    if net is None:
        return FLOATING
    while net is not None and path:
        pins = list(net.each_pin())
        net = path.pop().net_for_pin(pins[0].pin_id()) if pins else None
    other = lvs.xref().other_net_for(net) if net is not None else None
    return other.expanded_name().lower() if other is not None else None


def schematic_nets(lvsdb: Path, probes: dict[str, list[list[int]]], gds: Path | None = None) -> dict[str, str | None]:
    """Each extracted net's schematic net (``_probed``, its first probe that finds one), by its
    layout name; None for one that has none. A probe's GDS layer is the database's layer of that
    number, else, given the layout (``gds``), the database's layer of the same shapes
    (``_matched``: a deck's derived layer, which the saved database keeps without its number)."""
    lvs = db.LayoutVsSchematic()
    lvs.read(str(lvsdb))
    layers: dict[tuple[int, int], db.Region] = {}
    for index in lvs.layer_indexes():
        info = lvs.layer_info(index)
        if info.layer >= 0:
            layers.setdefault((info.layer, info.datatype), lvs.layer_by_index(index))
    wanted = {(layer, datatype) for points in probes.values() for layer, datatype, *_ in points}
    if gds is not None and wanted - set(layers):
        layers |= _matched(lvs, gds, wanted - set(layers))
    found = {}
    for name, points in probes.items():
        nets = [_probed(lvs, layers, probe) for probe in points]
        # a schematic net where any probe finds one, else floating where one finds it so
        found[name] = next((n for n in nets if n not in (None, FLOATING)), FLOATING if FLOATING in nets else None)
    return found


def _matched(lvs: db.LayoutVsSchematic, gds: Path, wanted: set[tuple[int, int]]) -> dict[tuple[int, int], db.Region]:
    """Each of the ``wanted`` GDS layers matched to the LVS database's unnumbered layer of the same
    shapes: the one whose difference from the layer's own shapes in the layout's top (the database's
    top cell) is least, at most ``MATCHED_SHARE`` of their area; a layer none matches is left out."""
    layout = db.Layout()
    layout.read(str(gds))
    name = lvs.internal_top_cell().name
    top = layout.cell(name) if layout.has_cell(name) else max(layout.top_cells(), key=lambda c: c.bbox().area())
    unnumbered = [lvs.layer_by_index(i) for i in lvs.layer_indexes() if lvs.layer_info(i).layer < 0]
    found: dict[tuple[int, int], db.Region] = {}
    for layer, datatype in sorted(wanted):
        index = layout.find_layer(layer, datatype)
        if index is None:
            continue
        own = db.Region(top.begin_shapes_rec(index)).merged()
        if own.is_empty() or not unnumbered:
            continue
        best = min(unnumbered, key=lambda region: (region ^ own).area())
        if (best ^ own).area() <= MATCHED_SHARE * own.area():
            found[layer, datatype] = best
    return found


# how far a deck's derived layer may differ from the GDS layer it stands for (its pins, a cut)
MATCHED_SHARE = 0.05


def annotation(netlist: Path, probes: Path, lvsdb: Path, limit: float = 0.05, gds: Path | None = None) -> Annotation:
    """The extraction at ``netlist`` on the schematic's nets, its nets found by their ``probes``
    in the LVS database ``lvsdb`` (``schematic_nets``). A capacitor on a net LVS dropped as floating
    (a dummy poly, a dummy finger) is left out and counted apart (``floating``); raises where more
    than ``limit`` of the capacitance is on nets with no schematic net otherwise (unpaired, or on a
    layer the database does not know: the mapping failed)."""
    found = {"0": "0", **schematic_nets(lvsdb, json.loads(probes.read_text()), gds)}
    summed: dict[tuple[str, str], float] = {}
    unmapped: dict[str, float] = {}
    floating: dict[str, float] = {}
    total = mapped = floated = 0.0
    for a, b, c in capacitors(netlist):
        total += c
        first, second = found.get(a), found.get(b)
        if first is None or second is None:
            for net, end in ((a, first), (b, second)):
                if end is None:
                    unmapped[net] = unmapped.get(net, 0.0) + c
            continue
        if FLOATING in (first, second):  # through a floating net: left out, not reduced in series
            floated += c
            for net, end in ((a, first), (b, second)):
                if end == FLOATING:
                    floating[net] = floating.get(net, 0.0) + c
            continue
        mapped += c
        if first != second:
            pair = (first, second) if first < second else (second, first)
            summed[pair] = summed.get(pair, 0.0) + c
    result = Annotation(
        capacitors=tuple((a, b, c) for (a, b), c in sorted(summed.items())),
        total_f=total,
        mapped_f=mapped,
        unmapped=dict(sorted(unmapped.items(), key=lambda item: -item[1])),
        limit=limit,
        floating=dict(sorted(floating.items(), key=lambda item: -item[1])),
        floating_f=floated,
    )
    if result.unmapped_f > limit * total:
        nets = ", ".join(f"{net} {c * 1e15:.3g} fF" for net, c in result.unmapped.items())
        raise ValueError(
            f"{result.unmapped_f * 1e15:.4g} fF of the extraction's {total * 1e15:.4g} fF "
            f"({result.unmapped_f / total:.1%}, over {limit:.0%}) is on nets with no schematic net: {nets}"
        )
    return result
