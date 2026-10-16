"""Software-only tests for the sampler subcircuit generator."""

from .subckt import Samp, SampParams, SwitchType


def test_samp():
    """Use the FRIDA-like complementary switch and power-of-two sizing."""
    params = SampParams()
    m = Samp(params)
    assert m is not None
    assert hasattr(m, "din")
    assert hasattr(m, "dout")
    assert params.switch_type is SwitchType.TGATE
    assert params.mos_w == 32
    assert m.MN.of.params.w == 32
    assert m.MP.of.params.w == 32
    assert m.MN.conns == {"d": m.dout, "g": m.clk, "s": m.din, "b": m.vss}
    assert m.MP.conns == {"d": m.dout, "g": m.clk_b, "s": m.din, "b": m.vdd}


def test_dummies_clock_opposite_their_switch():
    m = Samp(SampParams(dummy=True))
    assert m.MN_dummy.conns == {"d": m.dout, "g": m.clk_b, "s": m.dout, "b": m.vss}
    assert m.MP_dummy.conns == {"d": m.dout, "g": m.clk, "s": m.dout, "b": m.vdd}
    assert m.MN_dummy.of.params.w == 16


def test_bootstrap_boosts_the_nmos_gate():
    m = Samp(SampParams(switch_type=SwitchType.NMOS, bootstrap=True))
    assert m.MN.conns["g"] is m.gate and not hasattr(m, "MP")
    assert m.Mgate.conns == {"d": m.boot_top, "g": m.clk_b, "s": m.gate, "b": m.vdd}
    assert m.Mpre.conns == {"d": m.vdd, "g": m.gate, "s": m.boot_top, "b": m.vdd}
    assert m.Mcap.conns == {"d": m.boot_bot, "g": m.boot_top, "s": m.boot_bot, "b": m.vss}
    assert m.Mtg_n.conns["s"] is m.din and m.Mbot.conns["d"] is m.boot_bot
    assert m.Mgate_cas.conns["d"] is m.gate and m.Mgate_off.conns["s"] is m.vss


def test_bootstrap_needs_the_nmos_switch():
    import pytest

    with pytest.raises(ValueError):
        Samp(SampParams(bootstrap=True))
