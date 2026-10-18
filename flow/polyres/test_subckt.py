"""The poly resistor's ideal view."""

import hdl21 as h

from flow.polyres.subckt import PolyRes, PolyResParams


def test_ideal_resistor_has_two_heads() -> None:
    module = PolyRes(PolyResParams(r=1000 * h.prefix.UNIT))
    assert set(module.ports) == {"PLUS", "MINUS"}
