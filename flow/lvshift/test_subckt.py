"""Software-only structural tests for the level shifter generator."""

import pytest

from .subckt import CASES, LvShift, LvShiftParams


def test_core_cross_couples_on_vdd() -> None:
    LvShift.Cache.reset()
    m = LvShift(CASES["core"])
    assert m.Min_p.conns["d"] is m.outn and m.Mcross_p.conns == {"d": m.outp, "g": m.outn, "s": m.vdd, "b": m.vdd}


def test_input_inverter_on_vddl_with_its_body_on_vdd() -> None:
    m = LvShift(CASES["single_rst"])
    assert m.Minv_p.conns == {"d": m.inn, "g": m.inp, "s": m.vddl, "b": m.vdd}
    assert m.Mrst.conns["d"] is m.outp and m.Mrst.conns["g"] is m.rst


def test_buffers_follow_their_outputs() -> None:
    m = LvShift(CASES["buffered"])
    assert m.Mbuf_p_n.conns["g"] is m.outn and m.Mbuf_p_n.conns["d"] is m.bufp


def test_invalid_shifters_raise() -> None:
    with pytest.raises(ValueError):
        LvShift(LvShiftParams(in_w=0))
