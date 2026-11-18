"""The sampling switch's generator (``netlist``), the designs its parameters refuse, and its
placement (``flow.layout.hdl21align``): complete for every instance of its space, and, for the
structures FRIDA lays out, its rows top first."""

import hdl21 as h
import pytest
from pydantic import ValidationError

from flow import pipeline
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import runs
from .params import Params, SwitchType
from .subckt import netlist


def test_the_frida1_switch_is_a_transmission_gate_of_32_units() -> None:
    params = Params()
    m = netlist(params)
    assert params == Params() and params.switch_type is SwitchType.TGATE and params.mos_w == 32
    assert m.MN.of.params.w == 32 and m.MP.of.params.w == 32
    assert m.MN.conns == {"d": m.vout, "g": m.clk, "s": m.vin, "b": m.vss}
    assert m.MP.conns == {"d": m.vout, "g": m.clk_b, "s": m.vin, "b": m.vdd}


def test_dummies_clock_opposite_their_switch() -> None:
    m = netlist(Params(dummy=True))
    assert m.MN_dummy.conns == {"d": m.vout, "g": m.clk_b, "s": m.vout, "b": m.vss}
    assert m.MP_dummy.conns == {"d": m.vout, "g": m.clk, "s": m.vout, "b": m.vdd}
    assert m.MN_dummy.of.params.w == 16


def test_bootstrap_boosts_the_nmos_gate() -> None:
    """[Razavi-ADC] Fig. 3.41(b), p. 48: M5 (Mpre) and M3 (Mgate) PMOS, their n-wells on P
    (Sec. 3.8.2, p. 48); M2 (Mbot_in) an NMOS gated by the boosted node; the gate's pull-down M6
    under the cascode M7 gated by vdd (a second cascode, gated by P, above it); M3's gate at the
    bottom plate while tracking and at vdd while holding."""
    m = netlist(Params(switch_type=SwitchType.BOOTSTRAP))
    assert m.MN.conns["g"] is m.gate and not hasattr(m, "MP") and not hasattr(m, "Mtg_p")
    assert m.Mgate.conns == {"d": m.gate, "g": m.gate_ctl, "s": m.boot_top, "b": m.boot_top}
    assert m.Mpre.conns == {"d": m.vdd, "g": m.gate, "s": m.boot_top, "b": m.boot_top}
    assert m.Mcap.conns == {"d": m.boot_bot, "g": m.boot_top, "s": m.boot_bot, "b": m.vss}
    assert m.Mbot_in.conns == {"d": m.boot_bot, "g": m.gate, "s": m.vin, "b": m.vss}
    assert m.Mbot.conns["d"] is m.boot_bot and m.Mbot.conns["g"] is m.clk_b
    assert m.Mgate_top.conns == {"d": m.gate, "g": m.boot_top, "s": m.gate_mid, "b": m.vss}
    assert m.Mgate_cas.conns == {"d": m.gate_mid, "g": m.vdd, "s": m.gate_off, "b": m.vss}
    assert m.Mgate_off.conns == {"d": m.gate_off, "g": m.clk_b, "s": m.vss, "b": m.vss}
    assert m.Mctl_p.conns == {"d": m.gate_ctl, "g": m.clk, "s": m.vdd, "b": m.vdd}
    assert m.Mctl_n.conns == {"d": m.gate_ctl, "g": m.gate, "s": m.boot_bot, "b": m.vss}
    assert m.Mctl_on.conns == {"d": m.gate_ctl, "g": m.clk, "s": m.boot_bot, "b": m.vss}


def test_every_bootstrap_of_the_space_boosts_its_gate_by_at_least_0_9_vdd_by_area() -> None:
    """[Razavi-ADC] Eq. (3.70), p. 50: V_b' = C_b / (C_b + C_G1 + C_G2 + C_p) V_DD, at least
    0.9 V_DD: every bootstrap the runs name has a boost capacitor of 32 times its switch's gate
    area (C_b over C_G1 alone 32, so C_G1 takes 3 % and leaves the helpers' and the top plate's
    parasitics 7 %)."""
    found = [
        params
        for run in (runs.scaled, runs.long_channel, runs.boost_ladder)
        for space in run.spaces("tsmc65").values()
        for params in [space.base]
        if params.switch_type is SwitchType.BOOTSTRAP
    ] + [runs.bootstrap.build()]
    assert found
    for params in found:
        assert params.cap_w * params.cap_l == 32 * params.mos_w * params.mos_l


def test_the_parameters_refuse_what_does_not_build() -> None:
    """A size below one unit, and a dummy (half its switch) on a switch narrower than two units."""
    for fields in ({"mos_w": 0}, {"cap_l": 0}, {"dummy": True, "mos_w": 1}):
        with pytest.raises(ValidationError):
            Params(**fields)
    assert Params(dummy=True, mos_w=2).mos_w == 2


def _module(params):
    netlist.Cache.reset()
    return netlist(params)


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65", "sky130", "gf180"))
def test_every_instance_states_a_complete_placement_or_none(pdk: str) -> None:
    h.pdk.set_default(pytest.importorskip(f"pdk.{pdk}.hdl21").pdk_logic)  # a PDK-free checkout (CI) has none
    for instance in runs.scaled.instances(pdk) if hasattr(runs.scaled, "instances") else []:
        params = instance[1] if isinstance(instance, tuple) else instance.params
        pnr = pnr_input(_module(params))
        assert pnr is None or issues(pnr) == []


def test_the_named_structures_rows() -> None:
    h.pdk.set_default(pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic)
    named = pipeline.singles(runs)
    rows = {name: module_plan(pnr_input(_module(named[name]())))["rows"] for name in named}
    assert rows == {
        "frida1": [["Mp"], ["Mn"]],
        "tgate_dummy": [["Mp", "Mp_dummy"], ["Mn", "Mn_dummy"]],
        "nmos": [["Mn_a"], ["Mn_b"]],
        "bootstrap": [
            ["Mpre", "Mgate", "Mctl_p"],
            ["Mcap"],
            ["Mgate_top", "Mgate_cas", "Mgate_off", "Mbot", "Mctl_n", "Mctl_on"],
            ["Mn", "Mbot_in"],
        ],
    }
