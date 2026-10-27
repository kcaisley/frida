"""The sampling switch's generator (``netlist``), and the designs its parameters refuse."""

import pytest
from pydantic import ValidationError

from .params import Params, SwitchType
from .subckt import netlist


def test_the_frida1_switch_is_a_transmission_gate_of_32_units() -> None:
    params = Params()
    m = netlist(params)
    assert params == Params() and params.switch_type is SwitchType.TGATE and params.mos_w == 32
    assert m.MN.of.params.w == 32 and m.MP.of.params.w == 32
    assert m.MN.conns == {"d": m.dout, "g": m.clk, "s": m.din, "b": m.vss}
    assert m.MP.conns == {"d": m.dout, "g": m.clk_b, "s": m.din, "b": m.vdd}


def test_dummies_clock_opposite_their_switch() -> None:
    m = netlist(Params(dummy=True))
    assert m.MN_dummy.conns == {"d": m.dout, "g": m.clk_b, "s": m.dout, "b": m.vss}
    assert m.MP_dummy.conns == {"d": m.dout, "g": m.clk, "s": m.dout, "b": m.vdd}
    assert m.MN_dummy.of.params.w == 16


def test_bootstrap_boosts_the_nmos_gate() -> None:
    m = netlist(Params(switch_type=SwitchType.BOOTSTRAP))
    assert m.MN.conns["g"] is m.gate and not hasattr(m, "MP")
    assert m.Mgate.conns == {"d": m.boot_top, "g": m.clk_b, "s": m.gate, "b": m.vdd}
    assert m.Mpre.conns == {"d": m.vdd, "g": m.gate, "s": m.boot_top, "b": m.vdd}
    assert m.Mcap.conns == {"d": m.boot_bot, "g": m.boot_top, "s": m.boot_bot, "b": m.vss}
    assert m.Mtg_n.conns["s"] is m.din and m.Mbot.conns["d"] is m.boot_bot
    assert m.Mgate_cas.conns["d"] is m.gate and m.Mgate_off.conns["s"] is m.vss


def test_the_parameters_refuse_what_does_not_build() -> None:
    """A size below one unit, and a dummy (half its switch) on a switch narrower than two units."""
    for fields in ({"mos_w": 0}, {"cap_l": 0}, {"dummy": True, "mos_w": 1}):
        with pytest.raises(ValidationError):
            Params(**fields)
    assert Params(dummy=True, mos_w=2).mos_w == 2
