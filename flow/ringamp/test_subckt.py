"""Software-only structural tests for the ring amplifier generator."""

import pytest

from .subckt import CASES, Ringamp, RingampParams


def test_ring_amplifier_stages() -> None:
    Ringamp.Cache.reset()
    m = Ringamp(CASES["se"])
    assert len(m.instances) == 19
    assert m.Min_p.conns["s"] is m.vtop and m.Min_n.conns["s"] is m.vbot and m.Mfb.conns["g"] is m.midn
    assert m.Mbias_p.conns["d"] is m.ctrln and m.Mbias_n.conns["g"] is m.dzn
    assert m.Mout_p.conns["g"] is m.ctrlp and m.Mout_n.conns["g"] is m.ctrln and m.Mout_n.conns["d"] is m.out


def test_invalid_amplifiers_raise() -> None:
    with pytest.raises(ValueError):
        Ringamp(RingampParams(out_w=0))
