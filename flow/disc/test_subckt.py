"""Software-only structural tests for the discriminator generator."""

import pytest
from hdl21.primitives import MosType

from .subckt import CASES, Disc, DiscParams


def test_mirror_load_drives_the_second_stage_from_the_inp_side() -> None:
    Disc.Cache.reset()
    m = Disc(DiscParams())
    assert m.Minp.conns == {"d": m.a, "g": m.inp, "s": m.tail, "b": m.vss}
    assert m.Minn.conns == {"d": m.b, "g": m.inn, "s": m.tail, "b": m.vss}
    assert m.Mtail.conns == {"d": m.tail, "g": m.vbias, "s": m.vss, "b": m.vss}
    assert m.Mload_a.conns == {"d": m.a, "g": m.b, "s": m.vdd, "b": m.vdd}
    assert m.Mload_b.conns == {"d": m.b, "g": m.b, "s": m.vdd, "b": m.vdd}
    assert m.Mout.conns == {"d": m.out, "g": m.a, "s": m.vdd, "b": m.vdd}
    assert m.Msink.conns == {"d": m.out, "g": m.vbias, "s": m.vss, "b": m.vss}
    p = Disc(CASES["pmos"])
    assert p.Mtail.conns["s"] is p.vdd and p.Mout.conns["s"] is p.vss and p.Msink.conns["s"] is p.vdd


def test_hysteresis_cross_couples_the_loads_into_a_differential_second_stage() -> None:
    m = Disc(CASES["nmos_hyst"])
    assert m.Mload_a.conns["g"] is m.a and m.Mload_b.conns["g"] is m.b
    assert m.Mcross_a.conns == {"d": m.a, "g": m.b, "s": m.vdd, "b": m.vdd}
    assert m.Mcross_b.conns == {"d": m.b, "g": m.a, "s": m.vdd, "b": m.vdd}
    assert m.Mout_a.conns == {"d": m.out, "g": m.a, "s": m.vdd, "b": m.vdd}
    assert m.Mout_b.conns == {"d": m.c, "g": m.b, "s": m.vdd, "b": m.vdd}
    assert m.Mmirror_d.conns == {"d": m.c, "g": m.c, "s": m.vss, "b": m.vss}
    assert m.Mmirror_o.conns == {"d": m.out, "g": m.c, "s": m.vss, "b": m.vss}
    assert not hasattr(m, "Msink")


@pytest.mark.parametrize("setting", ({"in_w": 0}, {"cross_l": -1}, {"out_w": 0}))
def test_invalid_discriminators_raise(setting) -> None:
    with pytest.raises(ValueError):
        Disc(DiscParams(**setting))


def test_types() -> None:
    assert DiscParams().input_xtors == MosType.NMOS
