"""FMOM unit cells drawn from PDK rules, and the extracted netlist's terminal pairs."""

import pytest
from klayout import db

from flow.momcap.layout import TERMINALS, MomTestParams, MomUnit, mom_geometry, mom_unit_layout
from flow.momcap.pex import pair_capacitances
from flow.momcap.subckt import MomStyle


@pytest.mark.parametrize("pdk", ("tsmc65", "tsmc28", "tower180"))
def test_geometry_holds_a_via_in_a_minimum_finger(pdk: str) -> None:
    for layers in (1, 2, 3):
        geometry = mom_geometry(MomUnit(pdk, MomStyle.RING, layers))
        assert len(geometry.metals) == layers
        assert geometry.shield == geometry.metals[0] - 1
        assert geometry.width % (2 * geometry.grid) == 0
        assert geometry.end_gap >= geometry.space
        if layers > 1:
            assert geometry.min_length >= geometry.via_cut + 2 * geometry.via_end


@pytest.mark.parametrize("style", tuple(MomStyle))
def test_every_terminal_is_labelled_and_every_stack_is_joined(style: MomStyle) -> None:
    unit = MomUnit("tsmc65", style, 3)
    layout = mom_unit_layout(MomTestParams(unit, 4000, 2000), "unit")
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
        mom_unit_layout(MomTestParams(MomUnit("tower180", MomStyle.STRIP, 2), 200), "unit")


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
