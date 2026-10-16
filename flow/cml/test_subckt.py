"""Software-only structural tests for the CML generator."""

from hdl21.primitives import MosType

from .subckt import CASES, Cml


def test_buffer_pair_and_symmetric_loads() -> None:
    Cml.Cache.reset()
    m = Cml(CASES["buffer"])
    assert m.Min_p.conns["g"] is m.inp and m.Min_p.conns["d"] is m.outn and m.Mtail.conns["g"] is m.vbn
    assert m.Mload_p.conns["g"] is m.vbp and m.Mdiode_p.conns["g"] is m.outp


def test_latch_tracks_on_clkp_and_holds_on_clkn() -> None:
    m = Cml(CASES["latch"])
    assert m.Mclk_p.conns["d"] is m.track and m.Min_p.conns["s"] is m.track
    assert m.Mclk_n.conns["d"] is m.hold and m.Mhold_p.conns == {"d": m.outn, "g": m.outp, "s": m.hold, "b": m.vss}
    assert not hasattr(m, "Mdiode_p")  # triode loads


def test_divider_feeds_back_crossed() -> None:
    m = Cml(CASES["divider"])
    assert m.Min_a_p.conns["g"] is m.outn and m.Min_a_n.conns["g"] is m.outp
    assert m.Mclk_a_p.conns["g"] is m.clkn and m.Mclk_b_p.conns["g"] is m.clkp and m.Min_b_p.conns["g"] is m.mp


def test_xor_pulls_outp_low_where_the_inputs_agree() -> None:
    m = Cml(CASES["xor"])
    assert m.Mbot_ap.conns["g"] is m.inp and m.Mtop_ap.conns["g"] is m.clkp and m.Mtop_ap.conns["d"] is m.outp
    assert m.Mtop_bn.conns["g"] is m.inp and m.Mbot_bn.conns["g"] is m.clkn and m.Mtop_bn.conns["d"] is m.outn


def test_pmos_input_mirrors_the_rails() -> None:
    m = Cml(CASES["buffer_pmos"])
    assert m.Mtail.conns["s"] is m.vdd and m.Mtail.conns["g"] is m.vbp and m.Mload_p.conns["s"] is m.vss
    assert CASES["buffer_pmos"].input_xtors == MosType.PMOS
