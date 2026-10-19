"""Software-only structural tests for the Schmitt trigger generator."""

import pytest

from .subckt import CASES, Schmitt, SchmittParams


def test_stacks_and_feedback_to_the_opposite_rails() -> None:
    Schmitt.Cache.reset()
    m = Schmitt(SchmittParams())
    assert m.Mn1.conns == {"d": m.nmid, "g": m.inp, "s": m.vss, "b": m.vss}
    assert m.Mn2.conns == {"d": m.out, "g": m.inp, "s": m.nmid, "b": m.vss}
    assert m.Mp1.conns == {"d": m.pmid, "g": m.inp, "s": m.vdd, "b": m.vdd}
    assert m.Mp2.conns == {"d": m.out, "g": m.inp, "s": m.pmid, "b": m.vdd}
    assert m.Mnf.conns == {"d": m.vdd, "g": m.out, "s": m.nmid, "b": m.vss}
    assert m.Mpf.conns == {"d": m.vss, "g": m.out, "s": m.pmid, "b": m.vdd}


def test_buffer_inverts_the_trigger_once_more() -> None:
    m = Schmitt(CASES["buffer"])
    assert m.Mn2.conns["d"] is m.trig and m.Mnf.conns["g"] is m.trig
    assert m.Mout_n.conns == {"d": m.out, "g": m.trig, "s": m.vss, "b": m.vss}
    assert m.Mout_p.conns == {"d": m.out, "g": m.trig, "s": m.vdd, "b": m.vdd}


@pytest.mark.parametrize("setting", ({"n_w": 0}, {"fb_p_w": -1}, {"l": 0}))
def test_invalid_triggers_raise(setting) -> None:
    with pytest.raises(ValueError):
        Schmitt(SchmittParams(**setting))
