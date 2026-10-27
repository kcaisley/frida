"""The CDAC's layout: each side's array (``flow.caparray.layout``, ALIGN's capacitor generators)
with its drivers, the main plates' below it and the difference plates' above it, each bank a row of
the library's cells placed and routed by ALIGN in the order the stages sit in the array
(``layout_bank``), and a channel between bank and array wiring each driver to its bus
(``layout_side``).

A channel runs one horizontal track a net on the metal above the row cells' M3 (M4), and vertical
stubs on M3: from each bus, out of the array on the array's route metal and down (or up) to its
track; from each driver's output bar, through its row to the track. Two stubs on one column never
overlap: a net whose bus stub stands over another's output is given the track nearer the array.
The wires are drawn by ALIGN's ``Wiring`` generator (cell_fabric wires and vias on the PDK's
metals, their widths, spaces and via enclosures the PDK's rules).
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any

import hdl21 as h
from klayout import db

from flow.caparray.layout import ADC_ARRAYS, CapArrayLayout, CapArrayLayoutParams, UnitLengthCapFamilyParams
from flow.caparray.model import EXTRACTIONS
from flow.circuit.devices import instance_lines
from flow.layout.align.build import build
from flow.layout.align.run import Drawing, draw, drawn_only
from flow.layout.pdkproc import in_pdk, pdk_value

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
    the outer row the inverters before them, both in the order the stages sit in the array. Its GDS."""
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
            space = max(metal.get("EndToEnd", 0), rule.get("space", 0))
            out[f"M{n}"] = {
                "width": width,
                "space": space,
                "pitch": max(metal["Pitch"], width + space),
                "length": max(metal.get("MinL") or 0, math.ceil(rule.get("area", 0) / width)),
            }
        if via:
            rule = rules.get(f"V{n}", {})
            enclosure = rule.get("enclosure", (via.get("VencA_L", 0), via.get("VencP_L", 0), 0))
            out[f"V{n}"] = {
                "cut": max(via["WidthX"], rule.get("cut", 0)),
                "along": max(enclosure[0], via.get("VencA_L", 0), via.get("VencA_H", 0)),
                "across": enclosure[1],
            }
    return out


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
    end = {via: rule[via]["cut"] // 2 + rule[via]["along"] for via in ("V1", "V2", "V3")}
    landing = 2 * max(end.values())
    return {
        **{f"end_{via}": value for via, value in end.items()},
        "landing": landing,
        "clearance": 2 * max(rule[f"M{n}"]["pitch"] for n in range(1, 5)) + landing,
        "track": max(rule["M4"]["pitch"], landing + rule["M4"]["space"]),
        "column": rule["M3"]["pitch"] + landing,
    }


def _tracks(nets: list[dict[str, Any]], start: int, direction: int, g: dict[str, int]) -> tuple[dict[str, int], int]:
    """Each net's track in a channel from ``start`` growing in ``direction``, and the channel's far
    edge. A net's near column (``near_x``) runs from the start to its track, its far column
    (``far_x``) from its track out past the far edge: a near column over another net's far column
    takes the track nearer the start."""
    near = lambda a, b: abs(a - b) < g["column"]
    after = {n["name"]: {o["name"] for o in nets if o is not n and near(n["near_x"], o["far_x"])} for n in nets}
    order: list[dict[str, Any]] = []
    placed: set[str] = set()
    while len(order) < len(nets):
        # farthest first: a net whose near column stands over others' far columns waits for them
        ready = [n for n in nets if n["name"] not in placed and after[n["name"]] <= placed]
        if not ready:
            raise RuntimeError("the channel's columns cross: no track order keeps them apart")
        pick = min(ready, key=lambda n: n["near_x"])
        order.append(pick)
        placed.add(pick["name"])
    count = len(order)
    tracks = {
        n["name"]: start + direction * (g["clearance"] + (count - 1 - k) * g["track"]) for k, n in enumerate(order)
    }
    return tracks, start + direction * (2 * g["clearance"] + (count - 1) * g["track"])


class _Wires:
    """The wires of a side as ``Wiring.wires`` takes them, and how they join their pins."""

    def __init__(self, rule: dict[str, dict[str, int]], g: dict[str, int]) -> None:
        self.rule, self.g = rule, g
        self.parts: dict[str, list] = {"segments": [], "cuts": [], "landings": []}

    def segment(self, metal: str, net: str, x0: int, y0: int, x1: int, y1: int) -> None:
        self.parts["segments"].append([metal, net, x0, y0, x1, y1, self.rule[metal]["width"]])

    def cut(self, via: str, net: str, x: int, y: int) -> None:
        self.parts["cuts"].append([via, net, x, y, self.rule[via]["cut"]])

    def stack(self, net: str, x: int, y: int, low: int, high: int) -> None:
        """Vias from M``low`` to M``high`` at (x, y), each metal between a landing of its minimum area."""
        for n in range(low, high):
            self.cut(f"V{n}", net, x, y)
        for n in range(low + 1, high):
            half = max(self.g[f"end_V{n - 1}"], self.g[f"end_V{n}"], self.rule[f"M{n}"]["width"] // 2)
            long = max(half, -(-self.rule[f"M{n}"]["length"] // (4 * half)) * half)
            self.parts["landings"].append([f"M{n}", net, x - half, y - long, x + half, y + long])

    def column(self, net: str, x: int, y0: int, y1: int, ends: tuple[str | None, str | None]) -> None:
        """An M3 column from y0 to y1, past each end by the reach of the via there (None: none)."""
        reach = lambda via: self.g[f"end_{via}"] if via else 0
        sign = 1 if y1 >= y0 else -1
        self.segment("M3", net, x, y0 - sign * reach(ends[0]), x, y1 + sign * reach(ends[1]))

    def track(self, net: str, x0: int, x1: int, y: int) -> None:
        """An M4 track from column x0 to column x1 at y, a V3 at each."""
        lo, hi = sorted((x0, x1))
        self.segment("M4", net, lo - self.g["end_V3"], y, hi + self.g["end_V3"], y)
        self.cut("V3", net, x0, y)
        self.cut("V3", net, x1, y)

    def to_pin(self, net: str, pin: dict[str, Any], track: int) -> None:
        """A column from a track to a bank's pin: onto an M2 bar by a V2, or into an M3 strap."""
        if pin["kind"] == "bar":
            self.column(net, pin["x"], track, pin["y"], ("V3", "V2"))
            self.cut("V2", net, pin["x"], pin["y"])
        else:  # an M3 strap: the column overlaps its end
            self.column(net, pin["x"], track, pin["y"], ("V3", None))

    def out_of_array(self, net: str, x: int, inside: int, exit_y: int, route: int) -> None:
        """From inside a route-metal shape out to ``exit_y`` on the route metal, then onto M3 there."""
        if route == 3:
            return
        leave = f"V{route}" if route < 3 else "V3"
        sign = 1 if exit_y >= inside else -1
        self.segment(f"M{route}", net, x, inside, x, exit_y + sign * self.g[f"end_{leave}"])
        self.stack(net, x, exit_y, min(route, 3), max(route, 3))


def _pins(layout: db.Layout, cell: db.Cell, dx: int, dy: int, layers: dict[str, tuple[int, int]]) -> dict[str, Any]:
    """A placed bank's pins (nm, the block's frame): each output and input on its M2 bar, by its
    net, and its supply straps (M3), left and right, by supply; and its own M3 (keep-outs)."""
    nm = lambda value: round(value * layout.dbu * 1000)
    shift = lambda box: db.Box(nm(box.left) + dx, nm(box.bottom) + dy, nm(box.right) + dx, nm(box.top) + dy)
    m3 = [shift(p.bbox()) for p in db.Region(cell.begin_shapes_rec(layout.layer(*layers["M3"]))).merged().each()]
    v2 = [shift(p.bbox()) for p in db.Region(cell.begin_shapes_rec(layout.layer(*layers["V2"]))).each()]
    pins: dict[str, Any] = {"m3": m3, "v2": v2, "bars": {}, "straps": {}, "columns": []}
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


def _bar_pin(bar: db.Box, toward: int, pins: dict[str, Any], rule: dict, g: dict) -> dict[str, Any]:
    """A column's place on an M2 bar: the x along it farthest from the bank's other M3 (but what a
    via-2 joins to this bar) and from the columns already placed, the column running from the bar
    toward the bank's edge in ``toward``, at least a space clear. The column is added to the
    bank's ``columns``."""
    cuts = [cut for cut in pins["v2"] if cut.overlaps(bar)]
    keepout = [box for box in pins["m3"] if not any(box.overlaps(cut) for cut in cuts)]
    columns = pins["columns"]
    y = (bar.bottom + bar.top) // 2
    half = rule["M3"]["width"] // 2
    reach = g["end_V2"]
    best, gap = None, -1
    for x in range(bar.left + reach, bar.right - reach + 1, 5):
        span = db.Box(x - half, min(y, y + toward * 10**6) - reach, x + half, max(y, y + toward * 10**6) + reach)
        obstacles = keepout + columns
        clear = min((_gap(span, box, rule["M3"]["space"]) for box in obstacles), default=10**6)
        if clear > gap:
            best, gap = x, clear
    if gap < rule["M3"]["space"]:
        raise RuntimeError(f"no column off the bar {bar} keeps clear of the bank's M3")
    columns.append(
        db.Box(best - half, min(y, y + toward * 10**6) - reach, best + half, max(y, y + toward * 10**6) + reach)
    )
    return {"kind": "bar", "x": best, "y": y}


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
        dx = (array_box.left + array_box.right) // 2 - bank_nm((outline.left + outline.right) // 2)
        pins = _pins(bank, cell, dx, dy, {"M2": layers["M2"], "M3": layers["M3"], "V2": layers["V2"]})
        for n in nets:
            pin = _bar_pin(pins["bars"][n["name"]], -direction, pins, rule, g)
            n["far_x"], n["pin"] = pin["x"], pin
        for n in shield:
            strap = pins["straps"]["vss"][-1]
            n["far_x"] = (strap.left + strap.right) // 2
            n["pin"] = {"kind": "strap", "x": n["far_x"], "y": strap.top if direction < 0 else strap.bottom}
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
                wires.column(name, x, exit_y, track, ("V3" if route == 4 else "V2", "V3"))
            wires.track(name, x, n["far_x"], track)
            wires.to_pin(name, n["pin"], track)
        for n in shield:
            name, x, track = n["name"], n["near_x"], tracks[n["name"]]
            tx, ty = n["tap"]
            # the tap's route metal on to the right side's column, onto M3 there, down to the track
            wires.segment(f"M{route}", name, tx, ty, x + g[f"end_V{min(route, 3)}"], ty)
            if route != 3:
                wires.stack(name, x, ty, min(route, 3), max(route, 3))
            wires.column(name, x, ty, track, ("V3" if route == 4 else "V2" if route < 3 else None, "V3"))
            wires.track(name, x, n["far_x"], track)
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
    side_x = {name: left - g["clearance"] - k * g["column"] for k, name in enumerate(reversed(joined))}
    ends = {}
    for kind, bank in banks.items():
        direction, pins = bank["direction"], bank["pins"]
        start = bank["far_edge"]
        nets = []
        for name in joined:
            if name in pins["bars"]:
                pin = _bar_pin(pins["bars"][name], direction, pins, rule, g)
            else:
                strap = pins["straps"][name][0]
                pin = {
                    "kind": "strap",
                    "x": (strap.left + strap.right) // 2,
                    "y": strap.bottom if direction < 0 else strap.top,
                }
            nets.append({"name": name, "near_x": pin["x"], "far_x": side_x[name], "pin": pin})
        tracks, _ = _tracks(nets, start, direction, g)
        for n in nets:
            wires.track(n["name"], n["near_x"], side_x[n["name"]], tracks[n["name"]])
            wires.to_pin(n["name"], n["pin"], tracks[n["name"]])
            ends.setdefault(n["name"], []).append(tracks[n["name"]])
    for name, (y0, y1) in ends.items():
        wires.column(name, side_x[name], y0, y1, ("V3", "V3"))
    with tempfile.TemporaryDirectory() as scratch:
        (gds,) = draw(
            pdk_dir, [Drawing("Wiring", "wires", wires.parts, Path(scratch) / "wiring.gds", f"wiring_{side}")]
        )
        result.read(str(gds))
    combined.insert(db.CellInstArray(result.cell(f"wiring_{side}").cell_index(), db.Trans()))
    drawn_only(result, set(layers.values()))
    _name_pins(result, combined, side)
    return result, {"columns": dict(side_x), "lowest": {name: min(y) for name, y in ends.items()}}


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


def layout_cdac(out_dir: Path, pdk: str, array: str, params: Params) -> db.Layout:
    """The CDAC ``params`` (the ADC array ``array``): its P side (``layout_side``) and its N side
    mirrored to the P side's right, their supplies joined by a track each under both."""
    sides = {side: layout_side(out_dir / side, pdk, array, params, side) for side in ("p", "n")}
    layout = db.Layout()
    layout.dbu = sides["p"][0].dbu
    top = layout.create_cell(f"cdac_{array}")
    boxes, cells = {}, {}
    for side, (source, _info) in sides.items():
        cell = layout.create_cell(f"cdac_{array}_{side}")
        cell.copy_tree(source.cell(f"cdac_{array}_{side}"))
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
        wires.track(f"{name}_dac", xp, xn, y)
    with tempfile.TemporaryDirectory() as scratch:
        (gds,) = draw(pdk_dir, [Drawing("Wiring", "wires", wires.parts, Path(scratch) / "link.gds", "wiring_link")])
        layout.read(str(gds))
    top.insert(db.CellInstArray(layout.cell("wiring_link").cell_index(), db.Trans()))
    drawn_only(layout, set(pdk_value(pdk, "tech", "LAYERS").values()))
    _name_pins(layout, top, "")
    return layout
