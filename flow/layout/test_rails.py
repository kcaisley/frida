"""A block's rail lines made reachable for the converter's top level (``flow.layout.rails``), on a
kit stood in for (its layers, rules, rows and landing metals) and rail lines drawn here: a cut
bridged on M2 along its line, on M3 where another net's M2 lies over it, a piece no bridge reaches
joined to the next line of its supply, a strap's site where nothing else fits, and the check of
each piece's reach."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from klayout import db

from flow.layout import kpex, rails

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
# rails 200 nm high on lines 1 um apart, a site 200 nm wide; the converter's routes on M4 and M5
TECH = SimpleNamespace(
    LAYERS=LAYERS, RULES=RULES, MFG_GRID=5, PIN_METALS=(4, 5), PIN_TEXT={}, RAIL=100, H=1000, XPITCH=200
)
WIDE = 4000  # the layout's width (nm)


@pytest.fixture
def kit(monkeypatch):
    """The stood-in kit, ``toykit``."""
    monkeypatch.setitem(sys.modules, "pdk.toykit.layout.tech", TECH)
    joins = {
        "layers": {name: [list(pair)] for name, pair in LAYERS.items() if name[0] in "MV" and "." not in name},
        "labels": {f"M{k}": [list(LAYERS[f"M{k}"]), list(LAYERS[f"M{k}.PIN"])] for k in METALS},
        "vias": [[f"M{k}", f"V{k}", f"M{k + 1}"] for k in range(1, 5)],
    }
    monkeypatch.setattr(kpex, "technology", lambda pdk: ({}, joins))
    return TECH


def _line(net: str, y: int, pieces: list[tuple[int, int]]) -> list[tuple[str, str, tuple[int, int, int, int]]]:
    """A rail line's pieces on M1, each labelled with its supply."""
    return [(net, "M1", (a, y - 100, b, y + 100)) for a, b in pieces]


def _layout(path: Path, shapes: list[tuple[str, str, tuple[int, int, int, int]]]) -> Path:
    """A layout of ``shapes`` (net, layer, box in nm), each supply's M1 piece labelled at its middle."""
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    for net, layer, box in shapes:
        top.shapes(layout.layer(*LAYERS[layer])).insert(db.Box(*box))
        if net in rails.SUPPLIES:
            centre = db.Box(*box).center()
            top.shapes(layout.layer(*LAYERS["M1.PIN"])).insert(db.Text(net, centre.x, centre.y))
    layout.write(str(path))
    return path


# a vdd line at 1 um cut twice by another net's M1 across it: its middle piece touches neither edge
CUT = [
    *_line("vdd", 1000, [(0, 1300), (1500, 2500), (2700, WIDE)]),
    ("a", "M1", (1350, 700, 1450, 1300)),
    ("b", "M1", (2550, 700, 2650, 1300)),
]


def _count(gds: Path, layer: str) -> int:
    layout = db.Layout()
    layout.read(str(gds))
    return db.Region(layout.top_cell().begin_shapes_rec(layout.layer(*LAYERS[layer]))).count()


def test_each_cut_is_bridged_on_m2_along_its_line(tmp_path: Path, kit) -> None:
    """Before: the middle piece out of reach. After ``join``: each cut bridged by an M2 bar on the
    line, a cut in each piece beside it; the line one conductor from edge to edge, every piece in reach."""
    gds = _layout(tmp_path / "cut.gds", CUT)
    (before,) = rails.check(gds, "toykit") or []
    assert before["reach"] == ["edge", None, "edge"] and before["edges"] is False
    joined = rails.join(gds, "toykit")
    (line,) = joined
    assert [bridge["metal"] for bridge in line["bridges"]] == ["M2", "M2"] and "joins" not in line
    x0, y0, x1, y1 = line["bridges"][0]["box_um"]
    assert x0 < 1.3 and x1 > 1.5 and y0 < 1.0 < y1  # across the first cut, on the line
    assert _count(gds, "V1") == 4
    (after,) = rails.check(gds, "toykit", joined) or []
    assert after["reach"] == ["edge", "joined", "edge"] and after["edges"] is True
    assert after["pieces_um"] == [[0.0, 1.3], [1.5, 2.5], [2.7, 4.0]] and after["bridges"] == line["bridges"]


def test_a_cut_under_another_nets_m2_is_bridged_on_m3(tmp_path: Path, kit) -> None:
    """Another net's M2 over the first cut and half a row about it: that cut's bridge on M3 (a pad on
    M2 at each side, clear of that M2), the other on M2."""
    gds = _layout(tmp_path / "m2.gds", [*CUT, ("c", "M2", (1100, 900, 1700, 1100))])
    (line,) = rails.join(gds, "toykit")
    assert [bridge["metal"] for bridge in line["bridges"]] == ["M3", "M2"]
    (after,) = rails.check(gds, "toykit") or []
    assert after["reach"] == ["edge", "joined", "edge"] and after["edges"] is True


# another net's M2 and M3 over both cuts, as far as half a row each side: no bridge fits
BLOCKED = [
    *CUT,
    *(
        (net, layer, (x0, 500, x1, 1500))
        for net, x0, x1 in (("c", 1100, 1700), ("d", 2300, 2900))
        for layer in ("M2", "M3")
    ),
]


def test_a_piece_no_bridge_reaches_is_joined_to_the_next_line_of_its_supply(tmp_path: Path, kit) -> None:
    """With vss's line between, vdd's next line 2 um up: the middle piece joined to it by a wire on M2
    straight up across the rows, recorded with the line it joins; the line not one conductor."""
    gds = _layout(tmp_path / "join.gds", [*BLOCKED, *_line("vss", 2000, [(0, WIDE)]), *_line("vdd", 3000, [(0, WIDE)])])
    joined = rails.join(gds, "toykit")
    line = next(entry for entry in joined if entry["y_um"] == 1.0)
    assert "bridges" not in line
    (join,) = line["joins"]
    assert join["piece_um"] == [1.5, 2.5] and join["joined_to"] == 3.0 and join["metal"] == "M2"
    x0, y0, x1, y1 = join["box_um"]
    assert 1.7 < x0 < x1 < 2.3 and y0 < 1.0 and y1 > 3.0
    lines = {entry["y_um"]: entry for entry in rails.check(gds, "toykit", joined) or []}
    assert lines[1.0]["reach"] == ["edge", "joined", "edge"] and lines[1.0]["edges"] is False
    assert lines[1.0]["joins"] == line["joins"] and lines[2.0]["reach"] == ["edge"]


def test_a_piece_nothing_reaches_gets_a_strap_site_or_a_warning(tmp_path: Path, kit, caplog) -> None:
    """No other line of its supply: the middle piece's strap site recorded (a cut on it, the metals
    free over it), its reach ``site``; with another net's M4 over all of it, the site's metals stop
    below the landing metals: out of reach, a warning naming it."""
    gds = _layout(tmp_path / "site.gds", BLOCKED)
    with caplog.at_level(logging.WARNING, logger="flow.layout.rails"):
        joined = rails.join(gds, "toykit")
    (line,) = joined
    (site,) = line["sites"]
    assert site["free_above"] == ["M2", "M3", "M4", "M5"] and 1.5 < site["site_um"][0] < site["site_um"][2] < 2.5
    assert "a strap's site" in caplog.text
    (after,) = rails.check(gds, "toykit", joined) or []
    assert after["reach"] == ["edge", "site", "edge"] and after["sites"] == line["sites"]

    covered = _layout(tmp_path / "covered.gds", [*BLOCKED, ("e", "M4", (1400, 0, 2600, 2000))])
    joined = rails.join(covered, "toykit")
    assert joined[0]["sites"][0]["free_above"] == ["M2", "M3"]
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="flow.layout.rails"):
        (after,) = rails.check(covered, "toykit", joined) or []
    assert after["reach"] == ["edge", None, "edge"]
    assert "out of the top level's reach" in caplog.text and "vdd 1 [1.5, 2.5]" in caplog.text


def test_a_layout_without_rail_labels_has_no_lines(tmp_path: Path, kit) -> None:
    gds = _layout(tmp_path / "none.gds", [("a", "M1", (0, 0, 1000, 200))])
    assert rails.join(gds, "toykit") == [] and rails.check(gds, "toykit") is None
