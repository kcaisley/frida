"""MOM units drawn from a PDK's rules, and the extracted netlist's terminal pairs."""

import pytest
from klayout import db

from flow.layout.devices.momcap.characterize import draw_unit, mom_rules, pair_capacitances, structure
from flow.layout.devices.momcap.geometry import TERMINALS, MomcapGeometry, MomStyle


@pytest.mark.parametrize("pdk", ("tsmc65", "tsmc28", "tower180"))
def test_a_minimum_finger_holds_its_via(pdk: str) -> None:
    for layers in (1, 2, 3):
        rules = mom_rules(pdk, layers)
        assert len(rules.metals) == layers
        assert rules.shield == rules.metals[0] - 1
        assert rules.width % (2 * rules.grid) == 0
        assert rules.end_gap >= rules.space
        if layers > 1:
            assert rules.min_length >= rules.via_cut + 2 * rules.via_end


@pytest.mark.parametrize("style", tuple(MomStyle))
def test_every_terminal_is_labelled_and_every_stack_is_joined(style: MomStyle) -> None:
    # a strip and a ring unit as their arrays draw them (channels, columns); a plain strip alone
    geometry = MomcapGeometry(style, 3, 4000, 2000) if style is MomStyle.STRIP else structure(style, 3, 4000, 2000)
    layout = draw_unit("tsmc65", geometry, "unit")
    cell = layout.top_cell()
    labels = {
        shape.text_string for layer in layout.layer_indexes() for shape in cell.shapes(layer).each() if shape.is_text()
    }
    assert labels == {*TERMINALS[style], "SHIELD"}
    # one via per terminal on each of the two via layers between three metals
    tech = __import__("pdk.tsmc65.layout.tech", fromlist=["LAYERS"])
    vias = sum(cell.shapes(layout.layer(db.LayerInfo(*tech.LAYERS[f"V{metal}"]))).size() for metal in (5, 6))
    assert vias == 2 * len(TERMINALS[style])


def test_plates_shorter_than_their_via_landing_are_rejected() -> None:
    with pytest.raises(ValueError, match="cannot hold their vias"):
        draw_unit("tower180", MomcapGeometry(MomStyle.STRIP, 2, 200), "unit")


def test_pairs_sum_split_nodes_and_name_ground() -> None:
    netlist = """
cc_1 ( TOP INNER ) capacitor c=2.0f
cc_2 ( N_TOP_1 INNER:2 ) capacitor c=0.5f
c_3 ( TOP 0 ) capacitor c=0.25f
cc_4 ( INNER 4 ) capacitor c=1e-16
r_5 ( TOP N_TOP_1 ) resistor r=3
"""
    pairs = pair_capacitances(netlist, ("TOP", "INNER"))
    assert pairs[("INNER", "TOP")] == pytest.approx(2.5e-15)
    assert pairs[("GROUND", "TOP")] == pytest.approx(0.25e-15)
    assert pairs[("GROUND", "INNER")] == pytest.approx(0.1e-15)
