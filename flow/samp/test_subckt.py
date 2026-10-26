"""The sampling switch's generator (``netlist``) and which designs it builds (``valid``)."""

import pytest

from .params import CASES, Params, SwitchType, valid
from .subckt import netlist


def test_the_frida1_switch_is_a_transmission_gate_of_32_units() -> None:
    params = Params(**CASES["frida1"])
    m = netlist(params)
    assert params == Params() and params.switch_type is SwitchType.TGATE and params.mos_w == 32
    assert m.MN.of.params.w == 32 and m.MP.of.params.w == 32
    assert m.MN.conns == {"d": m.dout, "g": m.clk, "s": m.din, "b": m.vss}
    assert m.MP.conns == {"d": m.dout, "g": m.clk_b, "s": m.din, "b": m.vdd}


def test_dummies_clock_opposite_their_switch() -> None:
    m = netlist(Params(**CASES["tgate_dummy"]))
    assert m.MN_dummy.conns == {"d": m.dout, "g": m.clk_b, "s": m.dout, "b": m.vss}
    assert m.MP_dummy.conns == {"d": m.dout, "g": m.clk, "s": m.dout, "b": m.vdd}
    assert m.MN_dummy.of.params.w == 16


def test_bootstrap_boosts_the_nmos_gate() -> None:
    m = netlist(Params(**CASES["bootstrap"]))
    assert m.MN.conns["g"] is m.gate and not hasattr(m, "MP")
    assert m.Mgate.conns == {"d": m.boot_top, "g": m.clk_b, "s": m.gate, "b": m.vdd}
    assert m.Mpre.conns == {"d": m.vdd, "g": m.gate, "s": m.boot_top, "b": m.vdd}
    assert m.Mcap.conns == {"d": m.boot_bot, "g": m.boot_top, "s": m.boot_bot, "b": m.vss}
    assert m.Mtg_n.conns["s"] is m.din and m.Mbot.conns["d"] is m.boot_bot
    assert m.Mgate_cas.conns["d"] is m.gate and m.Mgate_off.conns["s"] is m.vss


def test_valid_is_the_generators_rule() -> None:
    assert all(valid(Params(**case), pdk) for case in CASES.values() for pdk in (None, "tsmc65", "ihp130"))
    for params in (Params(bootstrap=True), Params(mos_w=0), Params(dummy=True, mos_w=1)):
        assert not valid(params)
        with pytest.raises(ValueError):
            netlist(params)
