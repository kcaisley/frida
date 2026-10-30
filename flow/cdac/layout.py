"""The CDAC's layout: each side's array (``flow.cdac.caparray.layout``, ALIGN's capacitor generators)
with its drivers, the main plates' below it and the difference plates' above it, each bank two
rows of the library's cells placed and routed by ALIGN in the order the stages sit in the array
(``layout_bank``), a channel between bank and array wiring each driver to its bus, and the two
banks' states and supplies joined beside them (``layout_side``); both sides, the N side mirrored
(``layout_cdac``).

A channel runs one horizontal M4 track a net. Its two ends climb to the tracks on different metals,
so no net's column meets another's: from the array, M3 (out of the array on its route metal, onto
M3 past its edge); from the bank, M5 (the bank's cells and ALIGN's routes stay below M4), down a via
stack onto the driver's M2 bar or its M3 supply strap. The wires are drawn by ALIGN's ``Wiring``
generator (cell_fabric wires and vias on the PDK's metals, their widths, spaces and via enclosures
the PDK's).
"""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import hdl21 as h
from klayout import db

from flow.cdac.caparray.layout import (
    ADC_ARRAYS,
    CapArrayLayout,
    CapArrayLayoutParams,
    UnitLengthCapFamilyParams,
    _calc_unit_geometry,
    _mom_fit,
    caparray_spec,
    mom_array_params,
)
from flow.cdac.caparray.model import EXTRACTIONS
from flow.cdac.caparray.subckt import CapArrayParams
from flow.circuit.devices import instance_lines
from flow.layout.align.build import build
from flow.layout.align.run import Drawing, draw, drawn_only
from flow.layout.pdkproc import access_points, in_pdk, pdk_value

from .params import Params
from .subckt import netlist


def _array_params(pdk: str, name: str) -> CapArrayLayoutParams:
    """The ADC array ``name`` as its newest extraction in ``pdk`` drew it (its manifest)."""
    manifests = sorted(EXTRACTIONS.glob(f"*/{name}/{pdk}/3l/geometry_manifest.json"))
    if not manifests:
        raise LookupError(f"no extraction of {name} in {pdk}")
    manifest = json.loads(manifests[-1].read_text())
    stack = manifest["stack"]
    return CapArrayLayoutParams(
        cdac=ADC_ARRAYS[name],
        family=UnitLengthCapFamilyParams(**manifest["unit_family"]),
        technology=pdk,
        route_layer=stack["route_layer"],
        shield_layer=stack["shield_layer"],
        active_layers=tuple(stack["active_layers"]),
        top_cell=manifest["top_cell"],
    )


def _bank_netlist(pdk: str, params: Params, kind: str, side: str, path: Path) -> tuple[Path, list[list[str]]]:
    """One ``side``'s ``kind`` drivers (main or diff) as a flat netlist of the library's cells, its
    supplies vdd and vss as ALIGN names them, and its floorplan's rows: every stage's chain in the
    order the stages sit in the array (the lightest left; of two alike, the later)."""
    h.pdk.set_default(__import__(f"pdk.{pdk}", fromlist=["pdk_logic"]).pdk_logic)
    module = netlist(params)
    h.pdk.compile(module)
    prefix = f"x{kind}_{side}_"
    lines = [
        line.replace("vdd_dac", "vdd").replace("vss_dac", "vss")
        for line in instance_lines(module)
        if line.startswith(prefix)
    ]
    nets = sorted({net for line in lines for net in line.split()[1:-1] if not net.startswith(prefix)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f".subckt {path.stem} {' '.join(nets)}\n" + "\n".join(lines) + f"\n.ends {path.stem}\n")
    stages = range(params.dac.driver.n_stages)
    order = sorted(stages, key=lambda stage: (params.dac.weights[stage], -stage))
    chains = [[line.split()[0] for line in lines if line.split()[0].startswith(f"{prefix}{stage}_")] for stage in order]
    return path, chains


def layout_bank(out_dir: Path, pdk: str, params: Params, kind: str, side: str) -> Path:
    """One ``side``'s ``kind`` drivers in two rows, placed and routed by ALIGN (``flow.layout.align``):
    the row facing the array each chain's last inverters (its outputs, and a lone inverter's input),
    the outer row the inverters before them, both in the order the stages sit in the array; so an
    output's column leaves toward the array, an input's away from it, neither through the other's
    row. Its GDS."""
    name = f"drivers_{kind}"
    path, chains = _bank_netlist(pdk, params, kind, side, out_dir / f"{name}.sp")
    outputs = [cell for chain in chains for cell in chain if "_out" in cell]
    earlier = [cell for chain in chains for cell in chain if "_out" not in cell]
    # ALIGN's floorplan lists rows top first: the main bank sits below the array, the difference bank above
    rows = [outputs, earlier] if kind == "main" else [earlier, outputs]
    floorplan = out_dir / f"{name}.json"
    floorplan.write_text(json.dumps({"rows": [row for row in rows if row], "symmetric": False}))
    return build(pdk, floorplan, path, out_dir, name=name)


def _rules(pdk: str, pdk_dir: Path) -> dict[str, dict[str, int]]:
    """Each metal's wire (width, space, pitch, minimum length) and each via's cut and enclosures
    (along and across a wire), from ALIGN's layers and the PDK's rules, the stricter."""
    layers = {entry["Layer"]: entry for entry in json.loads((pdk_dir / "layers.json").read_text())["Abstraction"]}
    rules = pdk_value(pdk, "tech", "RULES")
    out: dict[str, dict[str, int]] = {}
    for n in range(1, 8):
        metal, via = layers.get(f"M{n}"), layers.get(f"V{n}")
        if metal:
            rule = rules.get(f"M{n}", {})
            width = max(metal["Width"], rule.get("width", 0))
            # side to side: the PDK's spacing (ALIGN's EndToEnd is its line ends', larger)
            space = rule.get("space") or metal.get("EndToEnd", 0)
            out[f"M{n}"] = {
                "width": width,
                "space": space,
                "pitch": max(metal["Pitch"], width + space),
                "length": max(metal.get("MinL") or 0, math.ceil(rule.get("area", 0) / width)),
            }
            # (above width, space): the wide-metal space, at any run; (above width, cuts): the vias a
            # wide landing asks of the via below it
            parallel = rule.get("parallel_space", ())
            if parallel:
                out[f"M{n}"]["wide"] = tuple((above, space) for space, above, _run in parallel)
            if rule.get("wide_vias"):
                out[f"M{n}"]["wide_vias"] = rule["wide_vias"]
        if via:
            rule = rules.get(f"V{n}", {})
            enclosure = rule.get("enclosure", (via.get("VencA_L", 0), via.get("VencP_L", 0), 0))
            out[f"V{n}"] = {
                "cut": max(via["WidthX"], rule.get("cut", 0)),
                "space": max(via.get("SpaceX", 0), rule.get("space", 0)),
                "along": max(enclosure[0], via.get("VencA_L", 0), via.get("VencA_H", 0)),
                "across": enclosure[1],
            }
    out["grid"] = {"size": pdk_value(pdk, "tech", "MFG_GRID")}
    return out


def _up(value: int, grid: int) -> int:
    """``value`` rounded up to the manufacturing ``grid``."""
    return -(-value // grid) * grid


def _labels(layout: db.Layout, cell: db.Cell) -> list[tuple[str, int, int, tuple[int, int]]]:
    """Every label under ``cell``: its text, place (dbu) and layer."""
    found = []
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        it = cell.begin_shapes_rec(index)
        while not it.at_end():
            if it.shape().is_text():
                text = it.shape().text.transformed(it.trans())
                found.append((text.string, text.x, text.y, (info.layer, info.datatype)))
            it.next()
    return found


def _shape_at(layout: db.Layout, cell: db.Cell, layer: tuple[int, int], x: int, y: int) -> db.Box:
    """The bounding box of ``layer``'s merged shape under ``cell`` at (x, y)."""
    region = db.Region(cell.begin_shapes_rec(layout.layer(*layer))).merged()
    found = [p.bbox() for p in region.each() if p.bbox().contains(db.Point(x, y))]
    if not found:
        raise LookupError(f"nothing on {layer} at ({x}, {y})")
    return found[0]


def _geometry(rule: dict[str, dict[str, int]]) -> dict[str, int]:
    """The channels' spacings (nm): a via's reach past its cut along a wire (``end``), the widest
    landing, the clearance a channel keeps from a block and the track pitch."""
    grid = rule["grid"]["size"]
    end = {via: _up(rule[via]["cut"] // 2 + rule[via]["along"], grid) for via in ("V1", "V2", "V3", "V4")}
    landing = 2 * max(end.values())
    return {
        **{f"end_{via}": value for via, value in end.items()},
        "grid": grid,
        "landing": landing,
        "clearance": _up(2 * max(rule[f"M{n}"]["pitch"] for n in range(1, 6)) + landing, grid),
        "track": _up(max(rule["M4"]["pitch"], landing + rule["M4"]["space"]), grid),
        "column": _up(max(rule["M3"]["pitch"], landing + rule["M3"]["space"]), grid),
    }


def _tracks(nets: list[dict[str, Any]], start: int, direction: int, g: dict[str, int]) -> tuple[dict[str, int], int]:
    """Each net's track in a channel from ``start`` growing in ``direction``, in the order of the
    nets' columns from the start (``near_x``), and the channel's far edge. A channel's two ends
    climb to its tracks on different metals (M3 from the start, M5 from the far side), so no
    column meets another net's whatever the order."""
    order = sorted(nets, key=lambda n: n["near_x"])
    tracks = {n["name"]: start + direction * (g["clearance"] + k * g["track"]) for k, n in enumerate(order)}
    return tracks, start + direction * (2 * g["clearance"] + (len(order) - 1) * g["track"])


def _cuts(rule: dict, g: dict, low: int, high: int, cuts: int) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    """A via stack's cuts from M``low`` to M``high``, by via level: how many (``cuts``, or as many as
    the landing above asks where it is wide), how far apart (the cuts asked for a pitch of the
    stack's, a wide landing's at their own via's pitch, as near as the rule wants them), and how far
    the outermost lies from the stack's centre."""
    pitch = _up(max(rule[f"V{n}"]["cut"] + rule[f"V{n}"]["space"] for n in range(low, high)), 2 * g["grid"])
    count, step = {}, {}
    for n in range(low, high):
        count[n], step[n] = cuts, pitch
        wide = rule[f"M{n + 1}"].get("wide_vias")
        if wide and n + 1 < high:
            across, _ = _landing(rule, g, f"M{n + 1}", (f"V{n}", f"V{n + 1}"))
            if 2 * across > wide[0] and wide[1] > cuts:
                count[n] = wide[1]
                step[n] = _up(rule[f"V{n}"]["cut"] + rule[f"V{n}"]["space"], 2 * g["grid"])
    return count, step, {n: round((count[n] - 1) / 2 * step[n]) for n in count}


class _Wires:
    """The wires of a side as ``Wiring.wires`` takes them, and how they join their pins."""

    def __init__(self, rule: dict[str, dict[str, int]], g: dict[str, int]) -> None:
        self.rule, self.g = rule, g
        self.parts: dict[str, list] = {"segments": [], "cuts": [], "landings": []}

    def segment(self, metal: str, net: str, x0: int, y0: int, x1: int, y1: int) -> None:
        self.parts["segments"].append([metal, net, x0, y0, x1, y1, self.rule[metal]["width"]])

    def cut(self, via: str, net: str, x: int, y: int) -> None:
        self.parts["cuts"].append([via, net, x, y, self.rule[via]["cut"]])

    def pad(self, metal: str, net: str, x: int, y: int, via: str, vertical: bool, spread: int = 0) -> None:
        """``metal``'s pad over a ``via`` at (x, y) on a wire running ``vertical``ly or across: the
        cut and its side enclosure across the wire, its end enclosure along it, ``spread`` more in y
        (a column of cuts). A wire as wide as its cut has no side enclosure of its own."""
        across = max(
            self.rule[metal]["width"] // 2, _up(self.rule[via]["cut"] // 2 + self.rule[via]["across"], self.g["grid"])
        )
        along = self.g[f"end_{via}"]
        half_x, half_y = (across, along + spread) if vertical else (along, across + spread)
        self.parts["landings"].append([metal, net, x - half_x, y - half_y, x + half_x, y + half_y])

    def stack(
        self, net: str, x: int, y: int, low: int, high: int, cuts: int = 1, vertical: tuple[bool, bool] = (False, True)
    ) -> None:
        """Vias from M``low`` to M``high`` at (x, y), ``cuts`` of each in a column a via pitch apart,
        each metal between a landing: its vias' cuts and their side enclosures across, their end
        enclosures along y, its minimum area; the end metals a pad each, on wires running
        ``vertical``ly or across (an M2 bar across, an M5 column up, by default)."""
        count, step, spread = _cuts(self.rule, self.g, low, high, cuts)
        for n in range(low, high):
            for k in range(count[n]):
                self.cut(f"V{n}", net, x, y + round((k - (count[n] - 1) / 2) * step[n]))
        for n in range(low + 1, high):
            vias = (f"V{n - 1}", f"V{n}")
            across, along = _landing(self.rule, self.g, f"M{n}", vias)
            along += max(spread[n - 1], spread[n])
            self.parts["landings"].append([f"M{n}", net, x - across, y - along, x + across, y + along])
        self.pad(f"M{low}", net, x, y, f"V{low}", vertical[0], spread[low])
        self.pad(f"M{high}", net, x, y, f"V{high - 1}", vertical[1], spread[high - 1])

    def jog(self, net: str, x0: int, x1: int, y: int) -> None:
        """Vias from an M3 strap at x0 up to an M5 column at x1, both at y: the via-3 cuts at x0, the
        via-4 cuts at x1, their M4 landing drawn from one to the other; ``stack`` from M3 to M5 where
        x0 is x1."""
        count, step, spread = _cuts(self.rule, self.g, 3, 5, 1)
        for n, x in ((3, x0), (4, x1)):
            for k in range(count[n]):
                self.cut(f"V{n}", net, x, y + round((k - (count[n] - 1) / 2) * step[n]))
        across, along = _landing(self.rule, self.g, "M4", ("V3", "V4"))
        along += max(spread[3], spread[4])
        lo, hi = sorted((x0, x1))
        self.parts["landings"].append(["M4", net, lo - across, y - along, hi + across, y + along])
        self.pad("M3", net, x0, y, "V3", True, spread[3])
        self.pad("M5", net, x1, y, "V4", True, spread[4])

    def column(
        self, net: str, x: int, y0: int, y1: int, ends: tuple[str | None, str | None], metal: str = "M3"
    ) -> None:
        """A column from y0 to y1, past each end by the reach of the via there (None: none)."""
        reach = lambda via: self.g[f"end_{via}"] if via else 0
        sign = 1 if y1 >= y0 else -1
        self.segment(metal, net, x, y0 - sign * reach(ends[0]), x, y1 + sign * reach(ends[1]))

    def track(self, net: str, x0: int, via0: str, x1: int, via1: str, y: int) -> None:
        """An M4 track from the column at x0 to the one at x1 at y, joined by ``via0`` and ``via1``
        (V3 to an M3 column, V4 to an M5 one)."""
        lo, hi = sorted((x0, x1))
        reach = max(self.g[f"end_{via0}"], self.g[f"end_{via1}"])
        self.segment("M4", net, lo - reach, y, hi + reach, y)
        for x, via in ((x0, via0), (x1, via1)):
            self.cut(via, net, x, y)
            self.pad("M4", net, x, y, via, False)
            self.pad("M3" if via == "V3" else "M5", net, x, y, via, True)

    def to_pin(self, net: str, pin: dict[str, Any], track: int) -> None:
        """An M5 column from a track to a bank's pin (the bank draws nothing above M3), down a via
        stack: onto an M2 bar (V2, V3, V4) or into an M3 strap past its end (V3, V4, along M4 where the
        column jogs off the strap)."""
        x, y = pin["x"], pin["y"]
        self.column(net, x, track, y, ("V4", "V4"), "M5")
        if pin["kind"] == "bar":
            self.stack(net, x, y, 2, 5, vertical=(False, True))
        else:
            self.jog(net, pin["strap_x"], x, y)
        for b in pin.get("extension", ()):  # the bar drawn on to the via-2 past its end, or off it
            self.parts["landings"].append(["M2", net, b.left, b.bottom, b.right, b.top])

    def out_of_array(self, net: str, x: int, inside: int, exit_y: int, route: int) -> None:
        """From inside a route-metal shape out to ``exit_y`` on the route metal, then onto M3 there."""
        if route == 3:
            return
        leave = f"V{route}" if route < 3 else "V3"
        sign = 1 if exit_y >= inside else -1
        # two cuts a via: the array's buses beside are wide plates (a lone via near one is refused)
        low, high = min(route, 3), max(route, 3)
        pitch = _up(
            max(self.rule[f"V{n}"]["cut"] + self.rule[f"V{n}"]["space"] for n in range(low, high)), 2 * self.g["grid"]
        )
        self.segment(f"M{route}", net, x, inside, x, exit_y + sign * (self.g[f"end_{leave}"] + pitch // 2))
        self.stack(net, x, exit_y, low, high, cuts=2, vertical=(True, True))


def _pins(layout: db.Layout, cell: db.Cell, dx: int, dy: int, layers: dict[str, tuple[int, int]]) -> dict[str, Any]:
    """A placed bank's pins (nm, the block's frame): each output and input on its M2 bar, by its
    net, and its supply straps (M3), left and right, by supply; and its own M3 (keep-outs)."""
    nm = lambda value: round(value * layout.dbu * 1000)
    shift = lambda box: db.Box(nm(box.left) + dx, nm(box.bottom) + dy, nm(box.right) + dx, nm(box.top) + dy)
    m3 = [shift(p.bbox()) for p in db.Region(cell.begin_shapes_rec(layout.layer(*layers["M3"]))).merged().each()]
    v2 = [shift(p.bbox()) for p in db.Region(cell.begin_shapes_rec(layout.layer(*layers["V2"]))).each()]
    m2 = [shift(p.bbox()) for p in db.Region(cell.begin_shapes_rec(layout.layer(*layers["M2"]))).merged().each()]
    outline = cell.bbox()
    pins: dict[str, Any] = {
        "m3": m3,
        "m2": m2,
        "v2": v2,
        "box": shift(outline),
        "bars": {},
        "straps": {},
        "landings": [],
        "m4": [],
        "columns": [],
    }
    for text, x, y, _layer in _labels(layout, cell):
        name = text.lower()
        if name in ("vdd", "vss"):
            strap = shift(_shape_at(layout, cell, layers["M3"], x, y))
            pins["straps"].setdefault(name, []).append(strap)
        else:
            pins["bars"][name] = shift(_shape_at(layout, cell, layers["M2"], x, y))
    for straps in pins["straps"].values():
        straps.sort(key=lambda box: box.left)
    return pins


def _landing(rule: dict, g: dict, metal: str, vias: tuple[str, str]) -> tuple[int, int]:
    """A via stack's landing on ``metal`` between its ``vias``: half across (x: the cuts and their
    side enclosure, the metal's width) and half along (y: their end enclosure, the metal's area)."""
    grid = g["grid"]
    across = _up(max(rule[metal]["width"] // 2, *(rule[via]["cut"] // 2 + rule[via]["across"] for via in vias)), grid)
    area = rule[metal]["length"] * rule[metal]["width"]
    return across, _up(max(*(g[f"end_{via}"] for via in vias), -(-area // (4 * across))), grid)


def _spacing(rule: dict, layer: str, a: db.Box, b: db.Box) -> int:
    """The space ``layer`` asks between two shapes: the widest class's (the PDK's parallel-run rules,
    taken at any run) either is wider than, else its space."""
    width = max(min(a.width(), a.height()), min(b.width(), b.height()))
    return max([rule[layer]["space"], *(space for above, space in rule[layer].get("wide", ()) if width > above)])


def _clearance(box: db.Box, obstacles: list[db.Box], rule: dict, layer: str, wide: bool = True) -> int:
    """How much more than its space ``box`` keeps from the nearest of ``obstacles`` (negative: too
    close), each at the space the pair asks (``wide``: by their widths; else the plain space)."""
    space = lambda other: _spacing(rule, layer, box, other) if wide else rule[layer]["space"]
    return min((_gap(box, other, space(other)) - space(other) for other in obstacles), default=10**6)


def _touching(box: db.Box, same: list[db.Box], space: int, join: bool = True) -> int:
    """-1 where ``box`` comes within ``space`` of a shape of its own net without joining it (two
    shapes of one net are spaced as any two; ``join``: overlapping joins them, else, as two cuts,
    only the same cut does), else 0."""
    for other in same:
        if box == other or (join and box.overlaps(other)):
            continue
        dx = max(other.left - box.right, box.left - other.right)
        dy = max(other.bottom - box.top, box.bottom - other.top)
        if dx < space and dy < space:
            return -1
    return 0


def _stack(x: int, y: int, toward: int, rule: dict, g: dict) -> dict[str, db.Box]:
    """A bar pin's stack at (x, y): its via-2 cut and M2 pad, its M3 and M4 landings, its M5
    column out ``toward`` the bank's edge from its pad's far end."""
    grid, cut = g["grid"], rule["V2"]["cut"] // 2
    a2 = max(rule["M2"]["width"] // 2, _up(cut + rule["V2"]["across"], grid))
    a3, l3 = _landing(rule, g, "M3", ("V2", "V3"))
    a4, l4 = _landing(rule, g, "M4", ("V3", "V4"))
    _, _, spread = _cuts(rule, g, 2, 5, 1)
    l3, l4 = l3 + max(spread[2], spread[3]), l4 + max(spread[3], spread[4])
    half = _up(max(rule["M5"]["width"], rule["V4"]["cut"] + 2 * rule["V4"]["across"]) // 2, grid)
    back = y - toward * g["end_V4"]
    return {
        "v2": db.Box(x - cut, y - cut, x + cut, y + cut),
        "m2": db.Box(x - g["end_V2"], y - a2, x + g["end_V2"], y + a2),
        "m3": db.Box(x - a3, y - l3, x + a3, y + l3),
        "m4": db.Box(x - a4, y - l4, x + a4, y + l4),
        "m5": db.Box(x - half, min(back, y + toward * 10**6), x + half, max(back, y + toward * 10**6)),
    }


def _stack_clear(
    stack: dict[str, db.Box], m2: list[db.Box], pins: dict[str, Any], rule: dict, own: dict[str, list[db.Box]]
) -> int:
    """How clear a bar pin's stack (``_stack``) and its M2 pieces ``m2`` keep: of the bank's other
    M2 and M3 (its ``own`` net's apart: joined or a space away), of the landings and columns already
    placed (another stack's landings twice a space away: its vias a different net's via space), its
    via-2 of the bank's others."""
    double = lambda box, metal: box.enlarged(rule[metal]["space"], rule[metal]["space"])
    return min(
        _clearance(stack["m3"], own["keep3"], rule, "M3"),
        _touching(stack["m3"], own["same3"], rule["M3"]["space"]),
        _clearance(double(stack["m3"], "M3"), pins["landings"], rule, "M3", wide=False),
        _clearance(double(stack["m4"], "M4"), pins["m4"], rule, "M4", wide=False),
        _clearance(stack["m5"], pins["columns"], rule, "M5"),
        _touching(stack["v2"], own["v2"], rule["V2"]["space"], join=False),
        *(_clearance(piece, own["others"], rule, "M2") for piece in m2),
    )


def _place(stack: dict[str, db.Box], m2: list[db.Box], pins: dict[str, Any]) -> None:
    """A placed stack's shapes join the bank's, for the stacks after it."""
    pins["landings"].append(stack["m3"])
    pins["m4"].append(stack["m4"])
    pins["columns"].append(stack["m5"])
    pins["m2"] += m2
    pins["v2"].append(stack["v2"])


def _bar_pin(bar: db.Box, toward: int, pins: dict[str, Any], rule: dict, g: dict) -> dict[str, Any]:
    """A pin on an M2 bar: an M5 column (the bank draws nothing above M3) from the bar out toward
    the bank's edge in ``toward``, down a via-2, via-3 and via-4 on the bar, or just past its end
    with the bar drawn on to it. Its x: one whose stack keeps clear (``_stack_clear``: at least a
    space, up to a margin the more the better), then on the bar, then nearest its middle; where
    there is none, a dogleg off the bar (``_dogleg``). Its shapes join the bank's own."""
    cuts = [cut for cut in pins["v2"] if cut.overlaps(bar)]
    own = {
        "keep3": [box for box in pins["m3"] if not any(box.overlaps(cut) for cut in cuts)],
        "same3": [box for box in pins["m3"] if any(box.overlaps(cut) for cut in cuts)],
        "v2": [
            cut for cut in pins["v2"] if cut.overlaps(bar.enlarged(4 * rule["M2"]["pitch"], 4 * rule["M2"]["pitch"]))
        ],
        "others": [box for box in pins["m2"] if not box.overlaps(bar)],
    }
    y = (bar.bottom + bar.top) // 2 // g["grid"] * g["grid"]
    reach = g["end_V2"]
    # clearance past a margin buys nothing: then a landing on the bar itself, nearest its middle
    # (its ends left to the stacks of the bars beside it)
    margin = 2 * rule["M3"]["pitch"]
    best, best_key = None, None
    start = (bar.left - 2 * rule["M2"]["pitch"]) // g["grid"] * g["grid"]
    for x in range(start, bar.right + 2 * rule["M2"]["pitch"] + 1, g["grid"]):
        stack = _stack(x, y, toward, rule, g)
        # the bar drawn on past its end to hold the via-2, where it lies beyond; the pad where it
        # stands out of the bar
        m2 = []
        if x - reach < bar.left or x + reach > bar.right:
            m2.append(db.Box(min(bar.left, x - reach), bar.bottom, max(bar.right, x + reach), bar.top))
        if not bar.contains(stack["m2"].p1) or not bar.contains(stack["m2"].p2):
            m2.append(stack["m2"])
        clear = _stack_clear(stack, m2, pins, rule, own)
        key = (min(clear, margin), not m2, -abs(2 * x - bar.left - bar.right))
        if best_key is None or key > best_key:
            best, best_key = (x, y, stack, m2), key
    if best_key is None or best_key[0] < 0:
        # another net's M3 over the bar and its ends: a dogleg on M2 off the bar, out of the row of
        # bars, to a landing between that M3
        best = _dogleg(bar, toward, pins, rule, g, own)
    x, y, stack, m2 = best
    _place(stack, m2, pins)
    return {"kind": "bar", "x": x, "y": y, "extension": m2}


def _dogleg(
    bar: db.Box, toward: int, pins: dict[str, Any], rule: dict, g: dict, own: dict[str, list[db.Box]]
) -> tuple[int, int, dict[str, db.Box], list[db.Box]]:
    """A via-2 off the M2 bar ``bar`` where none on or by it keeps clear (``_bar_pin``): a stub of M2
    from the bar across (in y) and a run along (in x) to the via, the run as wide as the via's
    enclosure asks, the whole stack clear (``_stack_clear``). The shortest such: its x, its y, its
    stack and its two pieces."""
    pitch, grid = rule["M2"]["pitch"], g["grid"]
    width = 2 * _up(max(rule["M2"]["width"], rule["V2"]["cut"] + 2 * rule["V2"]["across"]) // 2, grid)
    reach = g["end_V2"]
    y_bar = (bar.bottom + bar.top) // 2 // grid * grid
    near = bar.enlarged(12 * pitch, 15 * pitch)
    local = {key: [box for box in boxes if box.overlaps(near)] for key, boxes in own.items()}
    nearby = {key: [box for box in pins[key] if box.overlaps(near)] for key in ("landings", "m4", "columns")}
    best, best_key = None, None
    step = max(grid, rule["M2"]["width"] // 4 // grid * grid)
    # as far as past a row's other bars (a one-row bank's outputs beside its states)
    for dy in range(-12 * pitch // step * step, 12 * pitch + 1, step):
        y = y_bar + dy
        if bar.bottom <= y <= bar.top:
            continue
        for x in range((bar.left - 8 * pitch) // grid * grid, bar.right + 8 * pitch + 1, step):
            # the stub nearest the via, or from the bar's middle (clear of the bars beside it)
            middle = (bar.left + bar.right) // 2 // grid * grid
            for stub_x in {min(max(x, bar.left + width // 2), bar.right - width // 2), middle}:
                stub = db.Box(
                    stub_x - width // 2, min(y, y_bar) - width // 2, stub_x + width // 2, max(y, y_bar) + width // 2
                )
                run = db.Box(min(x, stub_x) - reach, y - width // 2, max(x, stub_x) + reach, y + width // 2)
                stack = _stack(x, y, toward, rule, g)
                # the run joins its bar or keeps a space from it (no notch between them)
                clear = min(
                    _stack_clear(stack, [stub, run, stack["m2"]], nearby, rule, local),
                    _touching(run, [bar], _spacing(rule, "M2", run, bar)),
                )
                # clear of everything, then the shortest dogleg
                key = (clear >= 0, -abs(dy) - abs(x - stub_x), clear)
                if best_key is None or key > best_key:
                    best, best_key = (x, y, stack, [stub, run, stack["m2"]]), key
    if best is None or not best_key[0]:
        raise RuntimeError(f"no place on, by or off the bar {bar} keeps its landings clear of the bank's M3")
    return best


def _strap_pin(strap: db.Box, toward: int, pins: dict[str, Any], rule: dict, g: dict) -> dict[str, Any]:
    """A pin on an M3 supply strap: its via-3 inside the strap's end facing ``toward``, its M5 column
    (from its pad) over the strap where that keeps clear of the columns and the M4 placed, else at
    the nearest x that does along an M4 jog (``_Wires.jog``) reaching no other strap (a strap's
    neighbours can be closer than two landings: the PDK's thick top via); how clear it keeps
    (``clear``; the column over the strap where none does)."""
    grid = g["grid"]
    end = strap.top if toward > 0 else strap.bottom
    sx = (strap.left + strap.right) // 2 // grid * grid
    y = end - toward * g["end_V3"]
    half = _up(max(rule["M5"]["width"], rule["V4"]["cut"] + 2 * rule["V4"]["across"]) // 2, grid)
    back = y - toward * g["end_V4"]
    across, along = _landing(rule, g, "M4", ("V3", "V4"))
    _, _, spread = _cuts(rule, g, 3, 5, 1)
    along += max(spread[3], spread[4])
    reach = across + rule["M4"]["space"]
    # the straps a jog may not reach: all but those its landing over the strap already covers
    others = [
        s
        for straps in pins["straps"].values()
        for s in straps
        if s != strap and not (s.left < sx + reach and sx - reach < s.right)
    ]
    first = None
    for x in [sx, *(sx + sign * k * half for k in range(1, 40) for sign in (-1, 1))]:
        lo, hi = min(sx, x), max(sx, x)
        if any(s.left < hi + reach and lo - reach < s.right for s in others):
            continue
        column = db.Box(x - half, min(back, y + toward * 10**6), x + half, max(back, y + toward * 10**6))
        m4 = db.Box(lo - across, y - along, hi + across, y + along)
        clear = min(_clearance(column, pins["columns"], rule, "M5"), _clearance(m4, pins["m4"], rule, "M4"))
        pin = {"kind": "strap", "x": x, "strap_x": sx, "y": y, "column": column, "m4": m4, "clear": clear}
        first = first or pin
        if clear >= 0:
            return pin
    return first


def _supply_pin(straps: list[db.Box], toward: int, pins: dict[str, Any], rule: dict, g: dict) -> dict[str, Any]:
    """A supply's pin on the first of its ``straps`` whose pin keeps clear of those placed, jogging
    where it must (``_strap_pin``; none: an error); its column and its M4 join the bank's."""
    candidates = [_strap_pin(strap, toward, pins, rule, g) for strap in straps]
    pin = next((pin for pin in candidates if pin["clear"] >= 0), None)
    if pin is None:  # a column on another net's would join them
        raise RuntimeError(f"no strap of {straps} keeps a supply's column clear of the bank's")
    pins["columns"].append(pin["column"])
    pins["m4"].append(pin["m4"])
    return pin


def _gap(a: db.Box, b: db.Box, space: int) -> int:
    """How far apart two boxes are across x where they come within ``space`` of each other in y
    (else infinite): what a metal's spacing asks of two shapes side by side or corner to corner."""
    if max(b.bottom - a.top, a.bottom - b.top) >= space:
        return 10**6
    return max(b.left - a.right, a.left - b.right)


def layout_side(out_dir: Path, pdk: str, array: str, params: Params, side: str) -> tuple[db.Layout, dict[str, Any]]:
    """One ``side`` (p or n) of the CDAC ``params`` (the ADC array ``array``): the array, its main
    drivers' bank below, its difference drivers' above, the channels between; the states and
    supplies of both banks joined by a column left of all, the array's shield onto the main bank's
    ground. Its layout, and its supplies' columns (x) and lowest ends (y), nm."""
    out_dir.mkdir(parents=True, exist_ok=True)
    array_params = _array_params(pdk, array)
    route = array_params.route_layer
    layout = CapArrayLayout(array_params)
    top = layout.cell(array_params.top_cell)
    nm = lambda value: round(value * layout.dbu * 1000)
    layers = pdk_value(pdk, "tech", "LAYERS")
    route_layer = layers[f"M{route}"]
    box = top.bbox()
    array_box = db.Box(nm(box.left), nm(box.bottom), nm(box.right), nm(box.top))
    pdk_dir = in_pdk(pdk, "flow.layout.align.make_pdk", "build", pdk, out_dir / "pdk")
    rule = _rules(pdk, pdk_dir)
    g = _geometry(rule)
    wires = _Wires(rule, g)
    labels = _labels(layout, top)
    result = db.Layout()
    result.dbu = layout.dbu
    combined = result.create_cell(f"cdac_{array}_{side}")
    combined.copy_tree(top)
    banks: dict[str, dict[str, Any]] = {}
    for kind, direction in (("main", -1), ("diff", 1)):
        bank = db.Layout()
        bank.read(str(layout_bank(out_dir / kind, pdk, params, kind, side)))
        cell = max(bank.top_cells(), key=lambda c: c.bbox().area())
        local = _pins(bank, cell, 0, 0, {"M2": layers["M2"], "M3": layers["M3"], "V2": layers["V2"]})
        outline = cell.bbox()
        bank_nm = lambda value, unit=bank.dbu: round(value * unit * 1000)
        # the buses of this bank's plates, and its outputs
        nets = []
        for text, x, y, _layer in labels:
            if not text.startswith(f"cap_botplate_{kind}<"):
                continue
            stage = int(text[text.index("<") + 1 : -1])
            bus = _shape_at(layout, top, route_layer, x, y)
            net = f"dac_botplate_{side}_{stage}" if kind == "main" else f"dac_botplate_{side}_diff_{stage}"
            nets.append({"name": net, "near_x": nm(x), "bus": (nm(bus.bottom) if direction < 0 else nm(bus.top))})
        edge = array_box.bottom if direction < 0 else array_box.top
        exit_y = edge + direction * g["clearance"]
        # place the bank: centred on the array, its facing edge past the channel (outputs' far columns
        # first set to the bars' centres, refined once placed)
        for n in nets:
            bar = local["bars"][n["name"]]
            n["far_x"] = (bar.left + bar.right) // 2
        shield = []
        if kind == "main":
            # the shield's tap on the array's right edge, down the right side to the bank's ground
            tap = next((x, y) for text, x, y, _ in labels if text == "cap_shieldplate")
            right = max(array_box.right, 0) + g["clearance"]
            shield = [{"name": "vss_dac", "near_x": right, "far_x": 0, "tap": (nm(tap[0]), nm(tap[1]))}]
        _, far = _tracks(nets + shield, exit_y, direction, g)
        dy = far - bank_nm(outline.top if direction < 0 else outline.bottom)
        dy = dy // g["grid"] * g["grid"] if direction < 0 else _up(dy, g["grid"])
        dx = (
            ((array_box.left + array_box.right) // 2 - bank_nm((outline.left + outline.right) // 2))
            // g["grid"]
            * g["grid"]
        )
        pins = _pins(bank, cell, dx, dy, {"M2": layers["M2"], "M3": layers["M3"], "V2": layers["V2"]})
        # the shield's strap first (its column where the strap is), the outputs' about it
        for n in shield:
            n["pin"] = _supply_pin(pins["straps"]["vss"][::-1], -direction, pins, rule, g)
            n["far_x"] = n["pin"]["x"]
        for n in nets:
            pin = _bar_pin(pins["bars"][n["name"]], -direction, pins, rule, g)
            n["far_x"], n["pin"] = pin["x"], pin
        tracks, far2 = _tracks(nets + shield, exit_y, direction, g)
        if far2 != far:
            raise RuntimeError("the channel's tracks moved once the bank was placed")
        for n in nets:
            name, x, track = n["name"], n["near_x"], tracks[n["name"]]
            inside = n["bus"] - direction * rule[f"M{route}"]["width"]
            if route == 3:
                wires.column(name, x, inside, track, (None, "V3"))
            else:
                wires.out_of_array(name, x, inside, exit_y, route)
                # from past the exit's farther cut (its vias a pair: ``out_of_array``)
                half = (
                    _up(
                        max(rule[f"V{k}"]["cut"] + rule[f"V{k}"]["space"] for k in range(min(route, 3), max(route, 3))),
                        2 * g["grid"],
                    )
                    // 2
                )
                wires.column(name, x, exit_y - direction * half, track, ("V3" if route == 4 else "V2", "V3"))
            wires.track(name, x, "V3", n["far_x"], "V4", track)
            wires.to_pin(name, n["pin"], track)
        for n in shield:
            name, x, track = n["name"], n["near_x"], tracks[n["name"]]
            tx, ty = n["tap"]
            # the tap's route metal on to the right side's column, onto M3 there, down to the track
            wires.segment(f"M{route}", name, tx, ty, x + g[f"end_V{min(route, 3)}"], ty)
            if route != 3:
                wires.stack(name, x, ty, min(route, 3), max(route, 3), vertical=(route > 3, route < 3))
            wires.column(name, x, ty, track, ("V3" if route == 4 else "V2" if route < 3 else None, "V3"))
            wires.track(name, x, "V3", n["far_x"], "V4", track)
            wires.to_pin(name, n["pin"], track)
        placed = result.create_cell(f"drivers_{kind}_{side}")
        placed.copy_tree(cell)
        combined.insert(db.DCellInstArray(placed.cell_index(), db.DTrans(dx / 1000, dy / 1000)))
        placed_box = db.Box(
            bank_nm(outline.left) + dx,
            bank_nm(outline.bottom) + dy,
            bank_nm(outline.right) + dx,
            bank_nm(outline.top) + dy,
        )
        banks[kind] = {
            "pins": pins,
            "box": placed_box,
            "far_edge": placed_box.bottom if direction < 0 else placed_box.top,
            "direction": direction,
        }
    # the states and supplies: from each bank's far side, along a column left of everything
    joined = sorted(name for name in banks["main"]["pins"]["bars"] if name.startswith("dac_state")) + ["vdd", "vss"]
    left = min(array_box.left, *(b["box"].left for b in banks.values()))
    side_x, ends = _side_columns(wires, banks, joined, left, rule, g)
    with tempfile.TemporaryDirectory() as scratch:
        (gds,) = draw(
            pdk_dir, [Drawing("Wiring", "wires", wires.parts, Path(scratch) / "wiring.gds", f"wiring_{side}")]
        )
        result.read(str(gds))
    combined.insert(db.CellInstArray(result.cell(f"wiring_{side}").cell_index(), db.Trans()))
    drawn_only(result, set(layers.values()))
    _name_pins(result, combined, side)
    return result, {"columns": side_x, "lowest": ends}


def _joined_pins(
    order: list[str], pins: dict[str, Any], direction: int, side_x: dict[str, int], rule: dict, g: dict
) -> list[dict[str, Any]]:
    """A bank's pins of the nets ``order`` names (a state's on its bar, a supply's on a strap), in
    that order, each net with its pin and its two ends' x (``_side_columns``)."""
    nets = []
    for name in order:
        if name in pins["bars"]:
            pin = _bar_pin(pins["bars"][name], direction, pins, rule, g)
        else:
            straps = pins["straps"][name]
            pin = _supply_pin(straps if name == "vdd" else straps[::-1], direction, pins, rule, g)
        nets.append({"name": name, "near_x": pin["x"], "far_x": side_x[name], "pin": pin})
    return nets


def _side_columns(
    wires: _Wires, banks: dict[str, dict[str, Any]], joined: list[str], left: int, rule: dict, g: dict
) -> tuple[dict[str, int], dict[str, int]]:
    """The nets ``joined`` (states, supplies) from each bank's far side along a channel there, to a
    column each left of ``left``, the columns joining the banks' tracks. Each net's column (x) and
    its lowest track (y), nm."""
    side_x = {name: left - g["clearance"] - k * g["column"] for k, name in enumerate(reversed(joined))}
    ends: dict[str, list[int]] = {}
    for bank in banks.values():
        direction, pins = bank["direction"], bank["pins"]
        # the states first, then each supply on a strap whose column keeps clear of theirs (vdd's
        # from the left, vss's from the right: their columns a bank apart); where a dense bank's
        # states leave a supply no strap, the supplies first
        states_first = sorted(joined, key=lambda name: name not in pins["bars"])
        placed = {key: list(value) for key, value in pins.items() if isinstance(value, list)}
        try:
            nets = _joined_pins(states_first, pins, direction, side_x, rule, g)
        except RuntimeError:
            for key, value in placed.items():
                pins[key][:] = value
            nets = _joined_pins(states_first[::-1], pins, direction, side_x, rule, g)
        tracks, _ = _tracks(nets, bank["far_edge"], direction, g)
        for n in nets:
            wires.track(n["name"], n["near_x"], "V4", side_x[n["name"]], "V3", tracks[n["name"]])
            wires.to_pin(n["name"], n["pin"], tracks[n["name"]])
            ends.setdefault(n["name"], []).append(tracks[n["name"]])
    for name, ys in ends.items():
        if len(ys) > 1:
            wires.column(name, side_x[name], min(ys), max(ys), ("V3", "V3"))
    return side_x, {name: min(ys) for name, ys in ends.items()}


def _name_pins(layout: db.Layout, top: db.Cell, side: str) -> None:
    """Every label at the top, named as the CDAC's nets: the banks' supplies ``vdd_dac`` and
    ``vss_dac``, the array's top plate ``vdac_<side>`` and its shield ``vss_dac``, its buses unlabelled
    (their drivers' outputs name them)."""
    rename = {"vdd": "vdd_dac", "vss": "vss_dac", "cap_topplate": f"vdac_{side}", "cap_shieldplate": "vss_dac"}
    for index in layout.layer_indexes():
        found = []
        it = top.begin_shapes_rec(index)
        while not it.at_end():
            if it.shape().is_text():
                found.append(it.shape().text.transformed(it.trans()))
            it.next()
        for cell in [top, *(layout.cell(i) for i in top.called_cells())]:
            for shape in [s for s in cell.shapes(index).each() if s.is_text()]:
                cell.shapes(index).erase(shape)
        for text in found:
            name = text.string.lower()
            if name.startswith("cap_botplate_"):
                continue
            top.shapes(index).insert(db.Text(rename.get(name, name), text.trans))


def layout_instance(out_dir: Path, pdk: str, params: Params, array: str) -> Path:
    """A sweep instance's CDAC (``layout_cdac``) as ``out_dir/<top>.gds``: ``params``, the ADC array
    ``array`` its space names, for the sweep's layout step and the viewer."""
    layout = layout_cdac(out_dir, pdk, array, params)
    top = max(layout.top_cells(), key=lambda cell: cell.bbox().area())
    path = out_dir / f"{top.name}.gds"
    save = db.SaveLayoutOptions()
    save.add_cell(top.cell_index())
    layout.write(str(path), save)
    return path


def layout_cdac(out_dir: Path, pdk: str, array: str, params: Params) -> db.Layout:
    """The CDAC ``params`` (the ADC array ``array``): its P side (``layout_side``, or with no split
    ``layout_units``) and its N side mirrored to the P side's right, their supplies joined by a
    track each under both."""
    units = params.dac.split is None
    name = f"cdac_units_{array}" if units else f"cdac_{array}"
    builder = layout_units if units else layout_side
    sides = {side: builder(out_dir / side, pdk, array, params, side) for side in ("p", "n")}
    layout = db.Layout()
    layout.dbu = sides["p"][0].dbu
    top = layout.create_cell(name)
    boxes, cells = {}, {}
    for side, (source, _info) in sides.items():
        cell = layout.create_cell(f"{name}_{side}")
        cell.copy_tree(source.cell(f"{name}_{side}"))
        cells[side] = cell
        b = cell.bbox()
        boxes[side] = (
            round(b.left * layout.dbu * 1000),
            round(b.bottom * layout.dbu * 1000),
            round(b.right * layout.dbu * 1000),
        )
    pdk_dir = in_pdk(pdk, "flow.layout.align.make_pdk", "build", pdk, out_dir / "pdk")
    rule = _rules(pdk, pdk_dir)
    g = _geometry(rule)
    # the N side mirrored about x = 0, its left edge a clearance past the P side's right
    offset = boxes["p"][2] + g["clearance"] + boxes["n"][2]
    top.insert(db.CellInstArray(cells["p"].cell_index(), db.Trans()))
    top.insert(db.DCellInstArray(cells["n"].cell_index(), db.DTrans(db.DTrans.M90, db.DVector(offset / 1000, 0))))
    # the supplies: from each side's column down to a track under both
    wires = _Wires(rule, g)
    bottom = min(boxes["p"][1], boxes["n"][1])
    for k, name in enumerate(("vdd", "vss")):
        y = bottom - g["clearance"] - k * g["track"]
        xp = sides["p"][1]["columns"][name]
        xn = offset - sides["n"][1]["columns"][name]
        for x, lowest in ((xp, sides["p"][1]["lowest"][name]), (xn, sides["n"][1]["lowest"][name])):
            wires.column(f"{name}_dac", x, lowest, y, ("V3", "V3"))
        wires.track(f"{name}_dac", xp, "V3", xn, "V3", y)
    with tempfile.TemporaryDirectory() as scratch:
        (gds,) = draw(pdk_dir, [Drawing("Wiring", "wires", wires.parts, Path(scratch) / "link.gds", "wiring_link")])
        layout.read(str(gds))
    top.insert(db.CellInstArray(layout.cell("wiring_link").cell_index(), db.Trans()))
    drawn_only(layout, set(pdk_value(pdk, "tech", "LAYERS").values()))
    _name_pins(layout, top, "")
    return layout


def _unit_params(pdk: str, array: str, unit_f: float) -> CapArrayLayoutParams:
    """The ADC array ``array``'s stack with every unit a ring around one finger (a unary row of
    weight one) of ``unit_f``: its length the PDK's FMOM model's for that capacitance, the ring
    just tall enough to hold it, its shield open under the finger (the bottom plate's) so the
    mesh's holes are short."""
    base = _array_params(pdk, array)
    # a tall probe of the family: its spacing, tail and grid (none of which its height sets)
    probe = replace(
        base,
        family=UnitLengthCapFamilyParams(
            coarse_weight=1, weight_step=20000, edge_dummy_units=0, tied_dummies=True, shield_strip=False
        ),
    )
    g = _calc_unit_geometry(probe)
    slope, intercept = _mom_fit(probe, g.gap)  # fF/um, fF
    length = max(g.tail_length, -(-round((unit_f * 1e15 - intercept) / slope * 1000) // g.grid) * g.grid)
    # the ring holds the finger (2 nominal + end gap past it, the nominal the tail and one weight
    # step), and is no shorter than its shield's bridges and the finger's access need
    step = max(g.grid, -(-((length - g.end_gap + 1) // 2 - g.tail_length) // g.grid) * g.grid)
    family = replace(probe.family, unary_length=length)
    # a track taller until it fits, then the shortest step on the grid within that track
    while not _fits(base, family, step):
        step += g.track_pitch
    low = max(g.grid, step - g.track_pitch)
    while step - low > g.grid:
        middle = low + (step - low) // (2 * g.grid) * g.grid
        low, step = (low, middle) if _fits(base, family, middle) else (middle, step)
    return replace(base, family=replace(family, weight_step=step), top_cell=f"units_{array}")


def _fits(base: CapArrayLayoutParams, family: UnitLengthCapFamilyParams, step: int) -> bool:
    """The ``family`` at weight step ``step`` is tall enough for its shield, its plate's access and
    its unary finger inside the ring (``MomUnit.unit``'s own check)."""
    try:
        g = _calc_unit_geometry(replace(base, family=replace(family, weight_step=step)))
    except ValueError:
        return False
    return (family.unary_length or 0) <= g.outer_height - 2 * (g.ring_width + g.end_gap)


def _rows(weights: list[int], per_row: int) -> tuple[list[list[tuple[int, int, int]]], dict[int, int]]:
    """The stages' units in rows of ``per_row``, and each stage's column (its line's, below its
    pieces). Each stage its whole rows first, the heaviest first (nearest the drivers); then each
    stage's rest, the heaviest first, in a row where it covers the stage's own column, the columns
    spread across the width, so no two stages' lines share one. A row's pieces: (stage, first
    column, units)."""
    rows: list[list[tuple[int, int, int]]] = []
    rest: list[tuple[int, int]] = []
    for stage in sorted(range(len(weights)), key=lambda k: -weights[k]):
        rows += [[(stage, 0, per_row)] for _ in range(weights[stage] // per_row)]
        if weights[stage] % per_row:
            rest.append((stage, weights[stage] % per_row))
    if len(weights) > per_row:
        raise ValueError(f"{len(weights)} stages' lines do not fit {per_row} columns")
    # every stage a column of its own, spread across the row
    columns = {
        stage: (k * per_row) // len(weights) + per_row // (2 * len(weights))
        for k, stage in enumerate(sorted(range(len(weights)), key=lambda k: -weights[k]))
    }
    partial: list[list[tuple[int, int, int]]] = []
    for stage, count in sorted(rest, key=lambda item: -item[1]):
        column = columns[stage]
        start = min(max(0, column - count // 2), per_row - count)  # the piece about its column
        for row in partial:
            if all(start + count <= first or first + n <= start for _, first, n in row):
                row.append((stage, start, count))
                break
        else:
            partial.append([(stage, start, count)])
    return rows + [sorted(row, key=lambda piece: piece[1]) for row in partial], columns


def _unit_grid(out_dir: Path, pdk: str, array: str, params: Params, side: str) -> tuple[db.Layout, dict[str, Any]]:
    """One ``side``'s units of a CDAC with no split (every stage in unit capacitors), each a ring of
    the array's unit capacitance (its switched capacitance over its total weight), in rows
    (``_rows``) stacked about twice as tall as wide, each row an array of its own (``ArrayWiring``:
    its buses a segment a stage, its shield's taps on its right). Its layout and its geometry."""
    out_dir.mkdir(parents=True, exist_ok=True)
    weights = list(params.dac.weights)
    switched = sum(params.dac.main_f) - sum(params.dac.diff_f)
    unit = _unit_params(pdk, array, switched / sum(weights))
    route = unit.route_layer
    if route < 2:
        raise ValueError(f"{pdk}'s array routes on M{route}: no metal below it for the stages' lines")
    g = asdict(_calc_unit_geometry(unit))
    # units a row: the rows' stack about twice as tall as wide
    row_pitch = g["outer_height"] - g["ring_width"] + g["via_landing"]
    per_row = max(1, round(math.sqrt(sum(weights) * row_pitch / (2 * g["unit_pitch"]))))
    rows, columns = _rows(weights, per_row)
    dummies = unit.family.edge_dummy_units
    layers = pdk_value(pdk, "tech", "LAYERS")
    pdk_dir = in_pdk(pdk, "flow.layout.align.make_pdk", "build", pdk, out_dir / "pdk")
    rule = _rules(pdk, pdk_dir)
    geo = _geometry(rule)
    # each row as an array of its own (``ArrayWiring`` over its units), its buses a segment a stage
    specs = []
    for r, segments in enumerate(rows):
        # a row's pieces at their columns, fillers between them (no edge dummies)
        order = [0] * (per_row + 2 * dummies)
        groups = []
        for stage, first, count in segments:
            groups.append((f"cap_botplate_main<{stage}>", f"cap_botplate_diff<{stage}>", dummies + first, count))
            order[dummies + first : dummies + first + count] = [1] * count
        specs.append(
            {
                **{key: value for key, value in caparray_spec(unit).items() if key not in ("order", "groups", "top")},
                "top": f"units_{array}_{side}_row{r}",
                "order": order,
                "groups": groups,
            }
        )
    # every row's units (a partial row's gaps its fillers)
    plan = in_pdk(
        pdk, "capcell", "caparray_plan", {**specs[0], "order": sorted({w for s in specs for w in s["order"]})}
    )
    access_points(pdk)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        stack = {"route": route, "shield": unit.shield_layer, "active": list(unit.active_layers)}
        drawings = [
            Drawing(
                "DifferenceUnit",
                "unit",
                {
                    "g": plan["geometry"],
                    **stack,
                    **{key: u[key] for key in ("weight", "tied", "unary_length")},
                    **{key: plan[key] for key in ("strip", "marks")},
                },
                work / f"{u['name']}.gds",
                u["name"],
            )
            for u in plan["units"]
        ]
        drawings += [
            Drawing("ArrayWiring", "wiring", {"g": plan["geometry"], "spec": s}, work / f"{s['top']}.gds", s["top"])
            for s in specs
        ]
        layout = db.Layout()
        for path in draw(pdk_dir, drawings):
            layout.read(str(path))
    names = {weight: u["name"] for weight, u in zip((u["weight"] for u in plan["units"]), plan["units"], strict=True)}
    grid = layout.create_cell(f"units_{array}_{side}")
    for r, s in enumerate(specs):
        row = layout.cell(s["top"])
        for position, weight in enumerate(s["order"]):
            row.insert(
                db.DCellInstArray(
                    layout.cell(names[weight]).cell_index(), db.DTrans(position * g["unit_pitch"] / 1000, 0)
                )
            )
        grid.insert(db.DCellInstArray(row.cell_index(), db.DTrans(0, r * row_pitch / 1000)))
    return layout, {
        "rows": rows,
        "columns": columns,
        "per_row": per_row,
        "row_pitch": row_pitch,
        "geometry": g,
        "unit": unit,
        "rule": rule,
        "geo": geo,
        "pdk_dir": pdk_dir,
        "layers": layers,
    }


def layout_units(out_dir: Path, pdk: str, array: str, params: Params, side: str) -> tuple[db.Layout, dict[str, Any]]:
    """One ``side`` of a CDAC with no split: its unit grid (``_unit_grid``), a line a stage under the
    rows (on the metal below the route metal, up onto M3 past the array where it is lower) joining
    the stage's bus segments down to the main drivers' bank below (no difference plates: no difference drivers), through a channel as ``layout_side``'s;
    the rows' shield taps joined on the right, down to the bank's ground; the bank's supplies out to
    a column each on the left. Its layout, and its supplies' columns (x) and lowest ends (y), nm."""
    layout, info = _unit_grid(out_dir, pdk, array, params, side)
    g, rule, geo, unit = info["geometry"], info["rule"], info["geo"], info["unit"]
    route = unit.route_layer
    lines = route - 1  # the stages' lines' metal, below the route metal (``_unit_grid`` keeps one)
    if lines > 3:
        raise ValueError(f"{pdk}'s stages' lines would run on M{lines}: the channel's columns are M3")
    grid = layout.cell(f"units_{array}_{side}")
    box = grid.bbox()
    nm = lambda value: round(value * layout.dbu * 1000)
    array_box = db.Box(nm(box.left), nm(box.bottom), nm(box.right), nm(box.top))
    pitch, row_pitch = g["unit_pitch"], info["row_pitch"]
    x_local = g["ring_width"] + g["gap"] + g["finger_width"] // 2
    bus_y = g["ring_width"] + g["end_gap"] + g["via_landing"] // 2 + (g["landing_long"] - g["via_landing"]) // 2
    dummies = unit.family.edge_dummy_units
    # each stage's pieces (row, first column, units) and its line's column (the packing's)
    segments: dict[int, list[tuple[int, int, int]]] = {}
    for r, row in enumerate(info["rows"]):
        for stage, first, count in row:
            segments.setdefault(stage, []).append((r, dummies + first, count))
    columns = {stage: dummies + column for stage, column in info["columns"].items()}
    wires = _Wires(rule, geo)
    exit_y = array_box.bottom - geo["clearance"]
    nets = []
    for stage, column in columns.items():
        name = f"dac_botplate_{side}_{stage}"
        x = column * pitch + x_local
        taps = [r * row_pitch + bus_y for r, first, count in segments[stage]]
        for y in taps:  # two cuts: the bus beside is a wide plate
            wires.stack(name, x, y, lines, route, cuts=2, vertical=(True, False))
        # the line from past its topmost pair's upper cut
        pair = _up(rule[f"V{lines}"]["cut"] + rule[f"V{lines}"]["space"], 2 * geo["grid"]) // 2
        nets.append({"name": name, "near_x": x, "top": max(taps) + pair})
    # the shield: every row's tap (the middle one at its right) joined by a route-metal strap there
    right = array_box.right - g["ring_width"] // 2
    shield_taps = [y for y in _shield_tap_ys(layout, grid)]
    wires.segment(f"M{route}", "vss_dac", right, min(shield_taps), right, max(shield_taps))
    shield = [{"name": "vss_dac", "near_x": array_box.right + geo["clearance"], "tap": (right, min(shield_taps))}]
    # the main drivers' bank below, its outputs and the shield's ground along the channel
    bank = db.Layout()
    bank.read(str(layout_bank(out_dir / "main", pdk, params, "main", side)))
    cell = max(bank.top_cells(), key=lambda c: c.bbox().area())
    outline = cell.bbox()
    bank_nm = lambda value, unit=bank.dbu: round(value * unit * 1000)
    for n in nets + shield:
        n["far_x"] = 0
    _, far = _tracks(nets + shield, exit_y, -1, geo)
    dy = (far - bank_nm(outline.top)) // geo["grid"] * geo["grid"]
    dx = (
        ((array_box.left + array_box.right) // 2 - bank_nm((outline.left + outline.right) // 2))
        // geo["grid"]
        * geo["grid"]
    )
    pins = _pins(bank, cell, dx, dy, {key: info["layers"][key] for key in ("M2", "M3", "V2")})
    for n in shield:
        n["pin"] = _supply_pin(pins["straps"]["vss"][::-1], 1, pins, rule, geo)
        n["far_x"] = n["pin"]["x"]
    for n in nets:
        pin = _bar_pin(pins["bars"][n["name"]], 1, pins, rule, geo)
        n["far_x"], n["pin"] = pin["x"], pin
    tracks, _ = _tracks(nets + shield, exit_y, -1, geo)
    for n in nets:
        if lines == 3:
            wires.column(n["name"], n["near_x"], n["top"], tracks[n["name"]], ("V3", "V3"))
        else:  # down on its own metal past the array, up onto M3 there, on to the track
            wires.column(n["name"], n["near_x"], n["top"], exit_y, (f"V{lines}", f"V{lines}"), f"M{lines}")
            wires.stack(n["name"], n["near_x"], exit_y, lines, 3, vertical=(True, True))
            wires.column(n["name"], n["near_x"], exit_y, tracks[n["name"]], (f"V{3 - 1}", "V3"))
        wires.track(n["name"], n["near_x"], "V3", n["far_x"], "V4", tracks[n["name"]])
        wires.to_pin(n["name"], n["pin"], tracks[n["name"]])
    for n in shield:
        tx, ty = n["tap"]
        x = n["near_x"]
        wires.segment(f"M{route}", n["name"], tx, ty, x + geo["end_V3"], ty)
        if route != 3:
            wires.stack(n["name"], x, ty, min(3, route), max(3, route), vertical=(True, False))
        wires.column(n["name"], x, ty, tracks[n["name"]], ("V3", "V3"))
        wires.track(n["name"], x, "V3", n["far_x"], "V4", tracks[n["name"]])
        wires.to_pin(n["name"], n["pin"], tracks[n["name"]])
    # the supplies from the bank's far side to a column each on the left
    placed_box = db.Box(
        bank_nm(outline.left) + dx, bank_nm(outline.bottom) + dy, bank_nm(outline.right) + dx, bank_nm(outline.top) + dy
    )
    banks = {"main": {"pins": pins, "box": placed_box, "far_edge": placed_box.bottom, "direction": -1}}
    side_x, ends = _side_columns(wires, banks, ["vdd", "vss"], min(array_box.left, placed_box.left), rule, geo)
    result = db.Layout()
    result.dbu = layout.dbu
    top = result.create_cell(f"cdac_units_{array}_{side}")
    top.copy_tree(grid)
    placed = result.create_cell(f"drivers_main_{side}")
    placed.copy_tree(cell)
    top.insert(db.DCellInstArray(placed.cell_index(), db.DTrans(dx / 1000, dy / 1000)))
    with tempfile.TemporaryDirectory() as scratch:
        (gds,) = draw(
            info["pdk_dir"], [Drawing("Wiring", "wires", wires.parts, Path(scratch) / "w.gds", f"wiring_{side}")]
        )
        result.read(str(gds))
    top.insert(db.CellInstArray(result.cell(f"wiring_{side}").cell_index(), db.Trans()))
    drawn_only(result, set(info["layers"].values()))
    _name_pins(result, top, side)
    return result, {"columns": side_x, "lowest": ends}


def _shield_tap_ys(layout: db.Layout, grid: db.Cell) -> list[int]:
    """Each row's shield pin (its label ``cap_shieldplate``): its y (nm), at the grid's right."""
    return sorted(
        round(y * layout.dbu * 1000) for text, _x, y, _layer in _labels(layout, grid) if text == "cap_shieldplate"
    )


def _unit_array_params(unit: CapArrayLayoutParams) -> CapArrayParams:
    """The all-unit array's netlist parameters (``flow.cdac.caparray.subckt.CapArray``) for LVS: every
    unit one finger of the unit length, at the PDK's FMOM model there (its slope over the length,
    its intercept once), not the production arrays' logical unit of two weight steps."""
    g = _calc_unit_geometry(unit)
    slope, intercept = _mom_fit(unit, g.gap)
    return replace(mom_array_params(unit), unit_cap=(slope * unit.family.unary_length / 1000 + intercept) * 1e-15)
