"""Poly resistor row cells in every PDK that has one: the row frame, the pins, the model."""

import pytest
from klayout import db

from flow.layout.pdkproc import pdk_value
from flow.polyres.layout import PDKS, PolyResUnit, polyres_layout, polyres_source


@pytest.mark.parametrize("pdk", PDKS)
def test_a_resistor_is_whole_rows_with_both_rails_and_two_pins(pdk: str) -> None:
    spec = pdk_value(pdk, "tech", "RES")
    layout, info = polyres_layout(PolyResUnit(pdk, spec["width"], 4000))
    cell = layout.top_cell()
    assert cell.name == info["top"]
    labels = {s.text_string for li in layout.layer_indexes() for s in cell.shapes(li).each() if s.is_text()}
    rows = spec.get("rows", 1)
    # an island (rows 0) has its own substrate tap and no rails
    assert ({"PLUS", "MINUS", "vss"} | ({"vdd"} if rows else set())) <= labels
    bnd = db.Region(cell.shapes(layout.layer(*pdk_value(pdk, "tech", "LAYERS")["BND"]))).bbox()
    if rows:
        assert bnd.height() == rows * pdk_value(pdk, "tech", "H")
    # the model: the sheet over the squares and both ends
    squares = info["l"] / (info["w"] - spec["dw"])
    assert info["r"] == pytest.approx(spec["sheet"] * squares + spec["end"] / ((info["w"] - spec["dw"]) / 1000))


def test_longer_is_more_resistive_and_short_bodies_meet_their_marker_area() -> None:
    short = polyres_layout(PolyResUnit("tsmc65", 400, 400))[1]
    long = polyres_layout(PolyResUnit("tsmc65", 400, 8000))[1]
    assert long["r"] > short["r"]
    spec = pdk_value("tsmc65", "tech", "RES")
    for layer, area in spec.get("min_area", {}).items():
        along, across = spec["markers"][layer]
        assert (short["w"] + 2 * across) * (short["l"] + 2 * along) >= area


def test_narrow_resistors_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least"):
        polyres_layout(PolyResUnit("lf150", 400, 4000))


def test_the_lvs_source_names_the_device_where_the_pdk_gives_one() -> None:
    unit = PolyResUnit("tower180", 420, 4000)
    info = polyres_layout(unit)[1]
    assert f"{info['r']:.6g}" in polyres_source(unit, info)  # the deck compares the resistance
    # where the deck compares its own sheet over the squares, the source carries that
    info = polyres_layout(PolyResUnit("tpsc65", 400, 10_000))[1]
    sheet = pdk_value("tpsc65", "tech", "RES")["lvs_sheet"]
    assert f"{sheet * info['l'] / info['w']:.6g}" in polyres_source(PolyResUnit("tpsc65", 400, 10_000), info)
