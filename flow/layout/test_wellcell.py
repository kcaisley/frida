"""Tests for PMOS on a bulk of their own: the ALIGN netlist gathers them by bulk into one primitive
under the MosWell generator, called where they were placed (``flow.circuit.netlists``), and their
island cell (``rows/wellcell.py``) keeps its well on the bulk, apart from every well a neighbour can
have, tapped on the bulk and joined to it, in the open kits (one whose rails carry taps, one whose
rails carry none and ties its wells by tie cells)."""

from __future__ import annotations

import json

import pytest
import vlsir.circuit_pb2 as vckt
import vlsir.utils_pb2 as vutils

from flow.circuit import netlists

from .pdkproc import ROOT, in_pdk


def _package() -> vckt.Package:
    """A module ``top`` (ports vdd, vss, in, out) with two PMOS on the bulk ``boost``, one PMOS and one
    NMOS on the supplies, by the generic model names."""
    pkg = vckt.Package()
    for model in ("pmos", "nmos"):
        ext = pkg.ext_modules.add()
        ext.name.CopyFrom(vutils.QualifiedName(domain="pdk", name=model))
        ext.spicetype = vckt.SpiceType.MOS
        for port in "dgsb":
            ext.signals.add(name=port, width=1)
            ext.ports.add(signal=port, direction=vckt.Port.Direction.NONE)
    top = pkg.modules.add(name="top")
    for net in ("vdd", "vss", "in", "out", "boost", "gate"):
        top.signals.add(name=net, width=1)
    for net in ("vdd", "vss", "in", "out"):
        top.ports.add(signal=net, direction=vckt.Port.Direction.NONE)
    devices = (
        ("pre", "pmos", ("vdd", "gate", "boost", "boost")),
        ("pass", "pmos", ("gate", "in", "boost", "boost")),
        ("up", "pmos", ("out", "in", "vdd", "vdd")),
        ("down", "nmos", ("out", "in", "vss", "vss")),
    )
    for name, model, nets in devices:
        instance = top.instances.add(name=name)
        instance.module.CopyFrom(vutils.Reference(external=vutils.QualifiedName(domain="pdk", name=model)))
        for port, net in zip("dgsb", nets, strict=True):
            c = instance.connections.add(portname=port)
            c.target.sig = net
    return pkg


def test_pmos_on_a_bulk_of_their_own_are_one_primitive_called_where_the_first_was() -> None:
    pkg = _package()
    netlists._wells(pkg, {"top": ({"vdd"}, {"vss"})})
    top = pkg.modules[-1]
    assert top.name == "top"
    assert [i.name for i in top.instances] == ["well_boost", "up", "down"]
    (well,) = [m for m in pkg.modules if m.name == "top_well_boost"]
    assert [i.name for i in well.instances] == ["pre", "pass"]
    assert sorted(p.signal for p in well.ports) == ["boost", "gate", "in", "vdd"]
    assert well.literals == ["* @: Generator(name='MosWell', parameters={'vdd': 'vdd', 'vss': 'vss'})"]
    call = top.instances[0]
    assert call.module.local == "top_well_boost"
    assert {c.portname: c.target.sig for c in call.connections} == {n: n for n in ("boost", "gate", "in", "vdd")}


def test_a_placement_names_the_primitive_once_where_it_named_its_devices() -> None:
    pkg = _package()
    netlists._wells(pkg, {"top": ({"vdd"}, {"vss"})})
    plan = {"rows": [["Mpre", "Mup", "Mpass"], ["Mdown"]], "symmetric": False, "split": {}, "constraints": []}
    const = netlists._constraints(pkg, pkg.modules[-1], None, plan)
    (floorplan,) = [c for c in const if c["constraint"] == "Floorplan"]
    assert floorplan["regions"] == [["Xwell_boost", "Mup"], ["Mdown"]]
    (loose,) = [c for c in const if c["constraint"] == "DoNotIdentify"]
    assert loose["instances"] == ["Mdown", "Mup"]


def test_pmos_on_the_supply_and_nmos_stay_as_they_are() -> None:
    pkg = _package()
    del pkg.modules[-1].instances[:2]  # no PMOS on another bulk left
    netlists._wells(pkg, {"top": ({"vdd"}, {"vss"})})
    assert [m.name for m in pkg.modules] == ["top"]
    assert [i.name for i in pkg.modules[0].instances] == ["up", "down"]


def island(l: int, w: int) -> dict:
    """Run bound to a PDK: a precharge PMOS (its drain on vdd) and a pass PMOS, ``l`` long, fingers
    ``w`` wide, on the bulk ``boost``; their island cell's measures: its rows and width, the island
    well, the cell's other wells, the space the kit asks between them, its tap's contacts, the bulk's
    M3 jumper, the M1 rails and the diffusion at the VDD line, the devices' diffusion, the tie sites."""
    import rowcell
    import tech
    import wellcell

    devs = [rowcell.Dev("pre", l, w, 4, "vdd", "gate", "boost"), rowcell.Dev("pass", l, w, 2, "gate", "ctl", "boost")]
    runs = [rowcell.Run(0, 4), rowcell.Run(1, 2)]
    cell = wellcell.mos_well("WELL", devs, runs, "boost", grid=2 * tech.XPITCH, vss=None, vdd="vdd")
    rows = max(r.y1 for r in cell.rects if r.layer == "BND") // tech.H
    wells = [(r.x0, r.y0, r.x1, r.y1) for r in cell.rects if r.layer == "NW"]
    x0, y0, x1, y1 = box = max(wells, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    inside = lambda r: x0 <= r.x0 and r.x1 <= x1 and y0 <= r.y0 and r.y1 <= y1
    on_line = lambda r: any(r.y0 <= j * tech.H <= r.y1 for j in range(rows + 1))
    tap_layer = wellcell.tap_spec()["od"]
    held = lambda r: {
        c.net for c in cell.rects if c.layer == "CO" and r.x0 <= c.x0 and c.x1 <= r.x1 and r.y0 <= c.y0 and c.y1 <= r.y1
    }
    taps = [r for r in cell.rects if r.layer == tap_layer and inside(r) and held(r) == {"boost"}]  # a tap's alone
    devices = [r for r in cell.rects if r.layer == "OD" and not on_line(r) and r not in taps]
    return {
        "rows": rows,
        "width": cell.width,
        "H": tech.H,
        "island": box,
        "wells": wells,
        "space": tech.NW_SPACE_NET,
        "near": min(tech.NW_P, tech.STD_NW),
        "nw_oh": tech.NW_OH,
        "taps": len(taps),
        "jumper": sorted({r.net for r in cell.rects if r.layer == "M3"}),
        "vdd_rail": any(
            r.layer == "M1" and r.y0 < tech.H < r.y1 and r.net == "vdd" and r.x1 - r.x0 == cell.width
            for r in cell.rects
        ),
        "vdd_line_taps": [
            r.layer for r in cell.rects if r.layer in ("OD", "CO") and r.y0 <= tech.H <= r.y1 and inside(r)
        ],
        "devices_inside": bool(devices) and all(inside(r) for r in devices if x0 - tech.EDGE < r.x0),
        "ties": wellcell.tie_sites(cell.width, rows),
        "room": wellcell.ROOM,
    }


@pytest.mark.parametrize(
    ("pdk", "l", "w"), [("ihp130", 130, 700), ("sky130", 150, 420)], ids=["rail-taps", "tie-cells"]
)
def test_the_island_keeps_its_well_on_the_bulk_apart_and_tapped(pdk: str, l: int, w: int) -> None:
    if not (ROOT / "pdk" / pdk / "layout" / "tech.py").is_file():
        pytest.skip(f"{pdk} is not checked out")
    m = in_pdk(pdk, "flow.layout.test_wellcell", "island", l, w)
    x0, y0, x1, y1 = m["island"]
    s, near, rows, h = m["space"], m["near"], m["rows"], m["H"]
    assert rows >= 2
    # beside the cell: a neighbour's well band overhangs its side, a row end (tie) stands inside it
    assert x0 > s + m["nw_oh"] + m["room"] and m["width"] - x1 > s + m["nw_oh"] + m["room"]
    # across the outer lines: a neighbour's PMOS body a row cell's distance past the line
    assert y0 > s - near and y0 >= 0
    if rows % 2 == 0:
        assert rows * h - y1 > s - near
    # the cell's own wells (its row ends') kept apart from the island
    for b in m["wells"]:
        if b != m["island"]:
            assert max(b[0] - x1, x0 - b[2], b[1] - y1, y0 - b[3]) > s, (b, m["island"])
    assert m["taps"] == 1  # the bulk's tap, in the island
    assert "boost" in m["jumper"]  # the bulk's bar joined to its tap on M3
    assert m["vdd_rail"]  # the VDD rail runs on across the cell
    assert m["vdd_line_taps"] == []  # no VDD tap inside the island
    assert m["devices_inside"]
    assert bool(m["ties"]) == (pdk == "sky130")


def test_the_committed_files_name_the_well_tap_layer_where_a_kit_has_one() -> None:
    layout = ROOT / "pdk" / "sky130" / "layout"
    if not (layout / "rows.json").is_file():
        pytest.skip("sky130 is not checked out")
    assert "TAP" in json.loads((layout / "rows.json").read_text())["extra"]
