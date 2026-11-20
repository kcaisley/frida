"""A block's pins after ALIGN (``flow.layout.pins``), on a kit stood in for (its layers, rules and
landing metals) and a layout drawn here: an edge pin's route to its side and its landing there, a
mirrored pair's landings, a landing metal taken where the lower one is in the way, a signal lifted
in place, its label moved, and the record."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hdl21 as h
import pytest
from klayout import db

from flow.layout import kpex, pins
from flow.layout.hdl21align import Border, EdgePin, Spot, edge_pins, port_plan
from flow.layout.step import with_supplies

METALS = range(1, 6)
LAYERS = {
    "BND": (100, 0),
    **{f"M{k}": (10 * k, 0) for k in METALS},
    **{f"V{k}": (10 * k + 5, 0) for k in range(1, 5)},
    **{f"M{k}.PIN": (10 * k, 2) for k in METALS},
}
RULES = {
    **{f"M{k}": {"width": 100, "space": 100, "area": 40_000} for k in METALS},
    **{f"V{k}": {"cut": 100, "space": 100, "enclosure": (40, 0)} for k in range(1, 5)},
}
TECH = SimpleNamespace(LAYERS=LAYERS, RULES=RULES, MFG_GRID=5, PIN_METALS=(4, 5), PIN_TEXT={})


@pytest.fixture
def kit(monkeypatch):
    """The stood-in kit, ``toykit``: five metals, the converter's routes on M4 and M5."""
    monkeypatch.setitem(sys.modules, "pdk.toykit.layout.tech", TECH)
    joins = {
        "layers": {name: [list(pair)] for name, pair in LAYERS.items() if name[0] in "MV" and "." not in name},
        "labels": {f"M{k}": [list(LAYERS[f"M{k}"]), list(LAYERS[f"M{k}.PIN"])] for k in METALS},
        "vias": [[f"M{k}", f"V{k}", f"M{k + 1}"] for k in range(1, 5)],
    }
    monkeypatch.setattr(kpex, "technology", lambda pdk: ({}, joins))
    return TECH


def _layout(path: Path, wires: dict[str, list[tuple[str, tuple[int, int, int, int]]]], size=(4000, 3000)) -> Path:
    """A layout of ``wires`` (net: its layer and box, nm), each net labelled on its first, inside an
    outline of ``size``."""
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    top.shapes(layout.layer(*LAYERS["BND"])).insert(db.Box(0, 0, *size))
    for net, shapes in wires.items():
        for layer, box in shapes:
            top.shapes(layout.layer(*LAYERS[layer])).insert(db.Box(*box))
        layer, box = shapes[0]
        centre = db.Box(*box).center()
        top.shapes(layout.layer(*LAYERS[f"{layer}.PIN"])).insert(db.Text(net, centre.x, centre.y))
    layout.write(str(path))
    return path


def _labels(gds: Path) -> dict[str, list[tuple[str, int, int]]]:
    layout = db.Layout()
    layout.read(str(gds))
    names = {pair: name for name, pair in LAYERS.items()}
    found: dict[str, list[tuple[str, int, int]]] = {}
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        for shape in layout.top_cell().shapes(index).each():
            if shape.is_text():
                found.setdefault(shape.text.string, []).append(
                    (names[(info.layer, info.datatype)], shape.text.x, shape.text.y)
                )
    return found


def _plan(edges=(), signals=("vin",), supplies=(), grounds=()) -> dict[str, Any]:
    ports = [{"net": n, "use": "signal"} for n in signals] + [{"net": n, "use": "power"} for n in supplies]
    return {"ports": ports + [{"net": n, "use": "ground"} for n in grounds], "edges": list(edges)}


def _port(record: dict[str, Any], net: str) -> dict[str, Any]:
    return next(port for port in record["ports"] if port["net"] == net)


def test_an_edge_pin_lands_on_its_side_from_its_wiring(tmp_path: Path, kit) -> None:
    """A port's M2 bar near the bottom: cuts up to M4 on it, a wire straight up to the outline's top,
    its landing there twice M4's width wide; its label moved there alone; nothing over it."""
    gds = _layout(tmp_path / "a.gds", {"vin": [("M2", (500, 450, 3500, 550))]})
    record = pins.land(gds, "toykit", _plan([{"net": "vin", "side": "top", "spot": "nearest"}]))
    port = _port(record, "vin")
    assert port["made"] == "edge" and port["side"] == "top" and port["layer"] == "M4" and port["route_from"] == "M2"
    x0, y0, x1, y1 = port["box_um"]
    assert y1 == 3.0 and round(x1 - x0, 3) == 0.2 and port["free_above"] == ["M5"]
    assert record["outline_um"] == [4.0, 3.0] and record["origin_um"] == [0.0, 0.0]
    # its one label, at its landing on M4's pin layer
    assert _labels(gds)["vin"] == [("M4.PIN", round((x0 + x1) * 500), round((y0 + y1) * 500))]
    layout = db.Layout()
    layout.read(str(gds))
    cuts = {name: db.Region(layout.top_cell().begin_shapes_rec(layout.layer(*LAYERS[name]))) for name in ("V2", "V3")}
    assert all(region.count() == 1 for region in cuts.values())


def test_a_mirrored_pair_lands_at_mirror_images_of_each_other(tmp_path: Path, kit) -> None:
    """Two inputs' bars mirrored about the outline's middle: their landings on its top too."""
    gds = _layout(
        tmp_path / "pair.gds",
        {"inp": [("M2", (400, 2000, 1600, 2100))], "inn": [("M2", (2400, 2000, 3600, 2100))]},
    )
    edge = {"net": "inp", "side": "top", "spot": "nearest", "mirror": "inn"}
    record = pins.land(gds, "toykit", _plan([edge], signals=("inp", "inn")))
    inp, inn = _port(record, "inp"), _port(record, "inn")
    assert inp["mirror"] == "inn" and inn["mirror"] == "inp" and inn["side"] == "top"
    assert round(inp["box_um"][0] + inn["box_um"][2], 4) == 4.0 and inp["box_um"][1] == inn["box_um"][1]


def test_a_landing_takes_the_next_metal_where_the_block_has_the_first(tmp_path: Path, kit) -> None:
    """Another net's M4 across the way to the side: the landing on M5, the lowest metal free there."""
    gds = _layout(
        tmp_path / "b.gds",
        {"vin": [("M3", (1950, 400, 2050, 1200))], "other": [("M4", (0, 2000, 4000, 2100))]},
    )
    record = pins.land(gds, "toykit", _plan([{"net": "vin", "side": "top", "spot": "nearest"}], ("vin", "other")))
    port = _port(record, "vin")
    assert port["layer"] == "M5" and port["route_from"] == "M3" and port["free_above"] == []
    # the other net lifted from its M4 to a pad on M5 beside vin's route
    other = _port(record, "other")
    assert other["made"] == "lifted" and other["layer"] == "M5" and other["route_from"] == "M4"


def test_a_right_side_pin_and_one_at_its_sides_end(tmp_path: Path, kit) -> None:
    """A right side's landing flush with it; a top plate's at its top side's last end."""
    gds = _layout(
        tmp_path / "c.gds",
        {"vout": [("M3", (1000, 300, 1100, 2700))], "vdac": [("M4", (300, 2600, 3700, 2700))]},
    )
    edges = [
        {"net": "vdac", "side": "top", "spot": "last"},
        {"net": "vout", "side": "right", "spot": "nearest"},
    ]
    record = pins.land(gds, "toykit", _plan(edges, ("vout", "vdac")))
    vout, vdac = _port(record, "vout"), _port(record, "vdac")
    assert vout["side"] == "right" and vout["box_um"][2] == 4.0 and vout["layer"] == "M4"
    assert vdac["route_from"] == "M4" and vdac["box_um"][3] == 3.0 and vdac["box_um"][2] > 3.4


def test_a_top_plates_landing_is_shielded_from_the_plates_routes_under_it(tmp_path: Path, kit, monkeypatch) -> None:
    """A top plate's bar on M4 at its side's last end, a plate's route on M3 under that end, the
    ground's rail on M2 across the top: shielded (``EdgePin.shield``), the landing at the end on M5,
    the highest landing metal, with a strip of the ground on M4 under its wire tied down to the rail
    by a stack of cuts, recorded beside the pin; unshielded, on M4 over the route. In a kit with a
    stack, the strip reaches past the wire's sides as far as the wire stands over the route."""
    wires = {
        "vdac": [("M4", (300, 1600, 3700, 1700))],
        "plate": [("M3", (3450, 1800, 3550, 2500))],
        "vss": [("M2", (0, 2800, 4000, 3000))],
    }
    edge = {"net": "vdac", "side": "top", "spot": "last"}
    plan = _plan([edge], ("vdac", "plate"), grounds=("vss",))
    plain = _port(pins.land(_layout(tmp_path / "plain.gds", wires), "toykit", plan), "vdac")
    assert plain["layer"] == "M4" and plain["box_um"][0] < 3.55 < plain["box_um"][2] and "shield" not in plain
    gds = _layout(tmp_path / "shielded.gds", wires)
    port = _port(pins.land(gds, "toykit", {**plan, "edges": [{**edge, "shield": True}]}), "vdac")
    assert port["layer"] == "M5" and port["box_um"][2] > 3.7 - 0.5
    shield = port["shield"]
    assert shield["net"] == "vss" and shield["layer"] == "M4" and shield["tied_from"] == "M2"
    x0, y0, x1, y1 = shield["box_um"]
    assert x0 < 3.55 < x1 and y0 < 1.8 + 0.2 and y1 > 2.8  # over the route, down to the rail
    layout = db.Layout()
    layout.read(str(gds))
    cuts = {name: db.Region(layout.top_cell().begin_shapes_rec(layout.layer(*LAYERS[name]))) for name in ("V2", "V3")}
    assert all(region.count() >= 1 for region in cuts.values())
    # a kit with a stack: the strip as far past the wire's sides as M5's bottom stands over M3's top
    stack = {"M3": {"z": 1.0, "thickness": 0.2}, "M5": {"z": 1.8, "thickness": 0.3}}
    plain_kit = pins.kit
    monkeypatch.setattr(pins, "kit", lambda pdk: replace(plain_kit(pdk), stack=stack))
    wide = _port(
        pins.land(_layout(tmp_path / "wide.gds", wires), "toykit", {**plan, "edges": [{**edge, "shield": True}]}),
        "vdac",
    )
    wire = wide["box_um"][2] - wide["box_um"][0]
    assert wide["shield"]["box_um"][2] - wide["shield"]["box_um"][0] > wire + 0.6  # past one side at least


def test_a_signal_is_lifted_in_place_or_recorded_as_drawn(tmp_path: Path, kit) -> None:
    """A clock's bar lifted to an M4 pad near its label; one under another net's M4 and M5 (a
    shield) stays as drawn, the metals free over it named; a supply is its rail lines."""
    gds = _layout(
        tmp_path / "d.gds",
        {
            "clk": [("M2", (500, 500, 1500, 600))],
            "state": [("M2", (2500, 500, 3500, 600))],
            "shield": [("M4", (2000, 0, 4000, 1500)), ("M5", (2000, 0, 4000, 1500))],
        },
    )
    record = pins.land(gds, "toykit", _plan(signals=("clk", "state"), supplies=("vdd",)))
    clk, state = _port(record, "clk"), _port(record, "state")
    assert clk["made"] == "lifted" and clk["layer"] == "M4" and clk["side"] is None
    assert state["made"] == "as laid out" and state["layer"] == "M2" and state["free_above"] == ["M3"]
    assert state["site_free_above"] == ["M3"]
    assert _port(record, "vdd")["made"] == "rail lines"
    lines = [{"net": "vdd", "y_um": 1.8, "pieces_um": [[-0.2, 4.2]], "x_um": [-0.2, 4.2], "edges": True}]
    supply = _port(with_supplies(record, lines), "vdd")
    assert supply["side"] == "left and right" and supply["lines_um"] == [
        {"y": 1.8, "pieces": [[-0.2, 4.2]], "edges": True}
    ]


def test_a_generators_edge_pins_ride_on_its_module() -> None:
    """``edge_pins`` on the module's own ports, its plan by name, a bus a net a bit; a signal not its
    port refused."""

    @h.module
    class Block:
        vin, vout = h.Input(), h.Output()
        state = h.Input(width=2)
        vdd = h.Power()

    edge_pins(Block, EdgePin(Block.vin, Border.TOP, Spot.LAST, mirror=Block.vout))
    plan = port_plan(Block)
    assert plan["edges"] == [{"net": "vin", "side": "top", "spot": "last", "mirror": "vout"}]
    assert {"net": "state_1", "use": "signal"} in plan["ports"] and {"net": "vdd", "use": "power"} in plan["ports"]
    with pytest.raises(ValueError, match="already"):
        edge_pins(Block, EdgePin(Block.vout, Border.RIGHT))

    @h.module
    class Other:
        a = h.Input()

    with pytest.raises(ValueError, match="not its port"):
        edge_pins(Other, EdgePin(h.Input(name="b"), Border.LEFT))


def test_a_pad_keeps_the_line_end_space_both_ways() -> None:
    """On a metal with a line-end rule (150 nm in front of an end under 150 nm, 50 nm past its
    sides): a pad 120 nm beside another net's line end does not fit (its plain space, 100 nm, it
    keeps), nor a narrow pad whose own end stands 120 nm from another's wire; 150 nm off, or a pad
    as wide as the rule's edge length, they fit."""
    other = db.Region(db.Box(0, 0, 1000, 100)) + db.Region(db.Box(1500, 520, 3000, 820))
    space = pins._Space({"M3": other}, {"a": {"M3": db.Region()}})
    space.ends = {"M3": ((150, 150, 50),)}
    beside = db.Box(1120, -200, 1220, 300)  # facing the line end at x = 1000
    assert space.clear("a", "M3", beside, 100) and not space.fits("a", "M3", beside, 100)
    assert space.fits("a", "M3", beside.moved(30, 0), 100)
    below = db.Box(2000, 0, 2100, 400)  # its top end 120 nm under the wide wire
    assert space.clear("a", "M3", below, 100) and not space.fits("a", "M3", below, 100)
    assert space.fits("a", "M3", below.moved(0, -30), 100)
    assert space.fits("a", "M3", db.Box(2000, 0, 2150, 400), 100)  # no line end: as wide as the rule's edge
