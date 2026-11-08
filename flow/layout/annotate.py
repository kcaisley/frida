"""A capacitance-only extraction read onto the schematic's nets: what the CLI's pexsim step
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
from dataclasses import dataclass
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

    @property
    def unmapped_f(self) -> float:
        """The extraction's capacitance with an end on a net with no schematic net."""
        return self.total_f - self.mapped_f

    def summary(self) -> dict[str, Any]:
        """The annotation as a record holds it: its totals, the unmapped share and nets."""
        return {
            "capacitors": len(self.capacitors),
            "total_f": self.total_f,
            "mapped_f": self.mapped_f,
            "unmapped_f": self.unmapped_f,
            "unmapped_share": self.unmapped_f / self.total_f if self.total_f else 0.0,
            "unmapped_nets": self.unmapped,
        }


def capacitors(netlist: Path) -> list[tuple[str, str, float]]:
    """The extraction's capacitors (``c_<n> ( a b ) capacitor c=<fF>f``): their nets and farads."""
    pattern = r"\s*c_\d+\s*\(\s*(\S+)\s+(\S+)\s*\)\s*capacitor\s+c=([0-9.eE+-]+)f"
    return [(a, b, float(c) * 1e-15) for a, b, c in re.findall(pattern, netlist.read_text())]


def _probed(lvs: db.LayoutVsSchematic, layers: dict[tuple[int, int], db.Region], probe: list[int]) -> str | None:
    """The schematic net at the top that LVS paired with the layout net under ``probe`` (GDS layer,
    datatype, x, y in database units), climbed through its cells' pins; None where it has none."""
    layer, datatype, x, y = probe
    if (layer, datatype) not in layers:
        return None
    path: list[db.SubCircuit] = []
    net = lvs.probe_net(layers[layer, datatype], db.Point(x, y), path)
    while net is not None and path:
        pins = list(net.each_pin())
        net = path.pop().net_for_pin(pins[0].pin_id()) if pins else None
    other = lvs.xref().other_net_for(net) if net is not None else None
    return other.expanded_name().lower() if other is not None else None


def schematic_nets(lvsdb: Path, probes: dict[str, list[list[int]]]) -> dict[str, str | None]:
    """Each extracted net's schematic net (``_probed``, its first probe that finds one), by its
    layout name; None for one that has none."""
    lvs = db.LayoutVsSchematic()
    lvs.read(str(lvsdb))
    layers: dict[tuple[int, int], db.Region] = {}
    for index in lvs.layer_indexes():
        info = lvs.layer_info(index)
        if info.layer >= 0:
            layers.setdefault((info.layer, info.datatype), lvs.layer_by_index(index))
    return {
        name: next((net for probe in points if (net := _probed(lvs, layers, probe)) is not None), None)
        for name, points in probes.items()
    }


def annotation(netlist: Path, probes: Path, lvsdb: Path, limit: float = 0.05) -> Annotation:
    """The extraction at ``netlist`` on the schematic's nets, its nets found by their ``probes``
    in the LVS database ``lvsdb`` (``schematic_nets``). Raises where more than ``limit`` of its
    capacitance is on nets with no schematic net (a share a few unconnected dummy gates reach)."""
    found = {"0": "0", **schematic_nets(lvsdb, json.loads(probes.read_text()))}
    summed: dict[tuple[str, str], float] = {}
    unmapped: dict[str, float] = {}
    total = mapped = 0.0
    for a, b, c in capacitors(netlist):
        total += c
        first, second = found.get(a), found.get(b)
        if first is None or second is None:
            for net, end in ((a, first), (b, second)):
                if end is None:
                    unmapped[net] = unmapped.get(net, 0.0) + c
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
    )
    if result.unmapped_f > limit * total:
        nets = ", ".join(f"{net} {c * 1e15:.3g} fF" for net, c in result.unmapped.items())
        raise ValueError(
            f"{result.unmapped_f * 1e15:.4g} fF of the extraction's {total * 1e15:.4g} fF "
            f"({result.unmapped_f / total:.1%}, over {limit:.0%}) is on nets with no schematic net: {nets}"
        )
    return result
