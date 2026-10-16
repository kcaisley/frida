"""Software-only structural tests for the delay line and ring generator."""

import pytest

from .subckt import CASES, Control, Delay, DelayParams, Stage


def test_default_delay_is_a_five_stage_inverter_chain() -> None:
    Delay.Cache.reset()
    params = DelayParams()
    assert (params.stage, params.control, params.stages, params.ring, params.differential) == (
        Stage.INVERTER,
        Control.NONE,
        5,
        False,
        False,
    )
    m = Delay(params)
    assert m.Minv1_p_n.conns["g"] is m.inp and m.Minv5_p_n.conns["d"] is m.outp
    assert m.Minv2_p_p.conns["g"] is m.p1 and m.Minv2_p_p.conns["s"] is m.vdd
    assert not hasattr(m, "Men1_p_p")


def test_ring_first_stage_is_a_nand_with_enable() -> None:
    m = Delay(CASES["ring5"])
    assert m.Minv1_p_n.conns["g"] is m.outp  # the loop closes
    assert m.Men1_p_n.conns["d"] is m.Minv1_p_n.conns["s"] and m.Men1_p_n.conns["g"] is m.en
    assert m.Men1_p_p.conns["d"] is m.p1 and m.Men1_p_p.conns["g"] is m.en and m.Men1_p_p.conns["s"] is m.vdd


def test_coupled_ring_crosses_its_chains_and_couples_each_stage() -> None:
    m = Delay(CASES["ring4_coupled"])
    assert m.Minv1_p_n.conns["g"] is m.outn and m.Minv1_n_n.conns["g"] is m.outp
    assert m.Mfb2_p_n.conns["g"] is m.n2 and m.Mfb2_p_n.conns["d"] is m.p2
    assert m.Mfb2_n_p.conns["g"] is m.p2 and m.Mfb2_n_p.conns["d"] is m.n2
    assert m.Minj.conns["d"] is m.p1 and m.Minj.conns["s"] is m.n1 and m.Minj.conns["g"] is m.inj
    assert hasattr(m, "Men1_n_n") and not hasattr(m, "Men1_n_p")


def test_starved_stages_and_shared_tail() -> None:
    m = Delay(CASES["ring5_starved"])
    assert m.Mstarve3_p_n.conns["g"] is m.vbn and m.Minv3_p_n.conns["s"] is m.Mstarve3_p_n.conns["d"]
    assert m.Mstarve3_p_p.conns["g"] is m.vbp and m.Minv3_p_p.conns["s"] is m.Mstarve3_p_p.conns["d"]
    t = Delay(CASES["ring4_tail"])
    assert t.Mtail.conns["g"] is t.vctrl and t.Minv3_n_n.conns["s"] is t.tail and t.Mfb3_n_n.conns["s"] is t.vss


@pytest.mark.parametrize(
    "setting",
    (
        {"ring": True, "stages": 4},  # single-ended ring: no inversion around the loop
        {"stage": Stage.COUPLED},  # coupled stages need both chains
        {"inject": True, "differential": True},  # injection belongs to a ring
        {"inv_n_w": 0},
    ),
)
def test_invalid_chains_raise(setting) -> None:
    with pytest.raises(ValueError):
        Delay(DelayParams(**setting))
