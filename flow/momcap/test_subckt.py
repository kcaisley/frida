"""Electrical contract of the ideal FMOM leaf (the capacitor array's too); no layout export."""

from io import StringIO

import hdl21 as h
import pytest
from hdl21.prefix import f

from .subckt import MomCap, MomCapParams


@pytest.mark.parametrize("capacitance", [0.1184 * f, 1 * f, 26.4972 * f])
def test_ideal_leaf_preserves_capacitance_and_open_shield(capacitance):
    leaf = MomCap(MomCapParams(c=capacitance))
    assert tuple(leaf.ports) == ("PLUS", "MINUS", "BULK")
    assert set(leaf.instances) == {"cap"}
    assert leaf.cap.conns == {"p": leaf.PLUS, "n": leaf.MINUS}
    assert float(leaf.cap.of.params.c) == pytest.approx(float(capacitance), rel=1e-12, abs=0)
    output = StringIO()
    h.netlist(leaf, output, fmt="spice")
    assert "PLUS MINUS BULK" in output.getvalue()


def test_a_varying_leaf_reads_the_monte_carlos_variables_and_probes_its_value():
    leaf = MomCap(MomCapParams(c=100 * f, varies=True, x_um=50.0, y_um=-20.0))
    assert set(leaf.instances) == {"cap", "probe"}
    output = StringIO()
    h.netlist(leaf, output, fmt="spectre")
    text = output.getvalue()
    # the value, Pelgrom's term and the gradient's, and the probe's fF above the shield
    assert "c=1e-13*(1 + mom_pelgrom/sqrt(1e-13/1e-15)*mom_mismatch + mom_gradient*(50*mom_gx + -20*mom_gy)" in text
    assert "/1e-15 type=dc" in text and "( drawn BULK )" in text


def test_the_variation_sets_the_conditions_and_the_statistics():
    from hdl21.sim import Literal, Param

    from .subckt import variation

    attrs = variation(pelgrom=0.005, gradient_per_um=1e-7)
    params = {attr.name: attr.val for attr in attrs if isinstance(attr, Param)}
    assert params == {"mom_pelgrom": 0.005, "mom_gradient": 1e-7, "mom_mismatch": 0.0, "mom_gx": 0.0, "mom_gy": 0.0}
    statistics = next(attr.text for attr in attrs if isinstance(attr, Literal))
    assert "vary mom_mismatch dist=gauss std=1" in statistics and "process" in statistics
