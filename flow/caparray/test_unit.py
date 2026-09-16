"""Electrical contract of the array's ideal capacitor leaf; no layout export."""

from io import StringIO

import hdl21 as h
import pytest
from hdl21.prefix import f

from .unit import MomCap, MomCapParams


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
