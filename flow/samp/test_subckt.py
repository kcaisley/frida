"""The sampling switch's generator (``netlist``), the designs its parameters refuse, and its
placement (``flow.layout.hdl21align``): complete for every instance of its space, and, for the
structures FRIDA lays out, its rows top first."""

import hdl21 as h
import pytest
from pydantic import ValidationError

from flow import pipeline
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import search
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


def _module(params):
    netlist.Cache.reset()
    return netlist(params)


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65"))
def test_every_instance_states_a_complete_placement_or_none(pdk: str) -> None:
    h.pdk.set_default(pytest.importorskip(f"pdk.{pdk}.hdl21").pdk_logic)  # a PDK-free checkout (CI) has none
    for instance in search.scaled.instances(pdk) if hasattr(search.scaled, "instances") else []:
        params = instance[1] if isinstance(instance, tuple) else instance.params
        pnr = pnr_input(_module(params))
        assert pnr is None or issues(pnr) == []


def test_the_named_structures_rows() -> None:
    h.pdk.set_default(pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic)
    named = pipeline.singles(search)
    rows = {name: module_plan(pnr_input(_module(named[name]())))["rows"] for name in named}
    assert rows == {
        "frida1": [["Mp"], ["Mn"]],
        "tgate_dummy": [["Mp", "Mp_dummy"], ["Mn", "Mn_dummy"]],
        "nmos": [["Mn_a"], ["Mn_b"]],
        "bootstrap": [["Mpre", "Mgate", "Mtg_p"], ["Mcap"], ["Mgate_cas", "Mgate_off", "Mbot"], ["Mn", "Mtg_n"]],
    }
