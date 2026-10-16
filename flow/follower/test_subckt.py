"""Software-only structural tests for the follower generator."""

import pytest
from hdl21.primitives import MosType

from .subckt import CASES, Follower, FollowerParams, Topology


def test_source_follower_drain_on_the_far_rail() -> None:
    Follower.Cache.reset()
    m = Follower(FollowerParams())
    assert m.Min.conns == {"d": m.vdd, "g": m.vin, "s": m.vout, "b": m.vss}
    assert m.Mbias.conns == {"d": m.vout, "g": m.vbn, "s": m.vss, "b": m.vss}
    p = Follower(CASES["source_pmos"])
    assert p.Min.conns["d"] is p.vss and p.Min.conns["b"] is p.vdd and p.Mbias.conns["g"] is p.vbp


def test_flipped_follower_feeds_the_input_drain_to_the_shunt() -> None:
    m = Follower(CASES["flipped"])
    assert m.Min.conns["d"] is m.fb and m.Min.conns["s"] is m.vout
    assert m.Mbias.conns["d"] is m.fb and m.Mbias.conns["g"] is m.vbp and m.Mbias.conns["s"] is m.vdd
    assert m.Mfb.conns == {"d": m.vout, "g": m.fb, "s": m.vss, "b": m.vss}
    p = Follower(CASES["flipped_pmos"])
    assert p.Msink.conns["d"] is p.vout and p.Msink.conns["s"] is p.vss and p.Mfb.conns["s"] is p.vdd


@pytest.mark.parametrize("setting", ({"sink": True}, {"in_w": 0}, {"topology": Topology.SOURCE, "fb_l": -1}))
def test_invalid_followers_raise(setting) -> None:
    with pytest.raises(ValueError):
        Follower(FollowerParams(**setting))


def test_types() -> None:
    assert FollowerParams().input_xtors == MosType.NMOS
