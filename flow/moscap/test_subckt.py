"""Software-only structural tests for the MOS capacitor generator."""

import pytest

from .subckt import CASES, Devices, Mode, MosCap, MosCapParams


def test_decaps_put_each_gate_on_the_other_rail() -> None:
    MosCap.Cache.reset()
    m = MosCap(CASES["decap_np"])
    assert m.Mcap0_n.conns == {"d": m.vss, "g": m.vdd, "s": m.vss, "b": m.vss}
    assert m.Mcap0_p.conns == {"d": m.vdd, "g": m.vss, "s": m.vdd, "b": m.vdd}


def test_two_net_capacitors_and_units() -> None:
    m = MosCap(CASES["cap_p"])
    assert set(m.instances) == {"Mcap0_p", "Mcap1_p"}
    assert m.Mcap1_p.conns == {"d": m.bot, "g": m.top, "s": m.bot, "b": m.vdd}


def test_invalid_capacitors_raise() -> None:
    with pytest.raises(ValueError):
        MosCap(MosCapParams(units=0))
    assert MosCapParams().mode == Mode.DECAP and MosCapParams().devices == Devices.NMOS
