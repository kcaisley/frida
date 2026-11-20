"""The sampling switch's generator (``netlist``), the designs its parameters refuse, and its
placement (``flow.layout.hdl21align``): complete for every instance of its space, and, for the
structures FRIDA lays out, its rows top first."""

import hdl21 as h
import pytest
from hdl21.primitives import MosVth
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
    (Sec. 3.8.2, p. 48); M2 (Mbot_in) an NMOS gated by the boosted node, as long as the design
    says; the gate's pull-down M6 under the cascode M7 gated by vdd and a second cascode above it,
    gated by P, with a diode-connected device between the two and a device gated by vdd across
    that one, all of the switch's threshold and a helper wide; M3's gate at the bottom
    plate while tracking (through a PMOS on the complementary clock) and at vdd while holding; M5
    eight helpers wide; dummies against the clock edges on M3's gate and on M6's drain, none on
    the bottom plate."""
    m = netlist(Params(switch_type=SwitchType.BOOTSTRAP, bot_l=14))
    assert m.MN.conns["g"] is m.gate and not hasattr(m, "MP") and not hasattr(m, "Mtg_p")
    assert m.Mgate.conns == {"d": m.gate, "g": m.gate_ctl, "s": m.boot_top, "b": m.boot_top}
    assert m.Mpre.conns == {"d": m.vdd, "g": m.gate, "s": m.boot_top, "b": m.boot_top}
    assert m.Mcap.conns == {"d": m.boot_bot, "g": m.boot_top, "s": m.boot_bot, "b": m.vss}
    assert m.Mbot_in.conns == {"d": m.boot_bot, "g": m.gate, "s": m.vin, "b": m.vss}
    assert m.Mbot.conns == {"d": m.boot_bot, "g": m.clk_b, "s": m.vss, "b": m.vss}
    assert m.Mgate_top.conns == {"d": m.gate, "g": m.boot_top, "s": m.gate_top, "b": m.vss}
    assert m.Mgate_drop.conns == {"d": m.gate_top, "g": m.gate_top, "s": m.gate_mid, "b": m.vss}
    assert m.Mgate_pass.conns == {"d": m.gate_top, "g": m.vdd, "s": m.gate_mid, "b": m.vss}
    assert m.Mgate_cas.conns == {"d": m.gate_mid, "g": m.vdd, "s": m.gate_off, "b": m.vss}
    assert m.Mgate_off.conns == {"d": m.gate_off, "g": m.clk_b, "s": m.vss, "b": m.vss}
    assert m.Mctl_p.conns == {"d": m.gate_ctl, "g": m.clk, "s": m.vdd, "b": m.vdd}
    assert m.Mctl_on.conns == {"d": m.boot_bot, "g": m.clk_b, "s": m.gate_ctl, "b": m.vdd}
    assert m.Mpre.of.params.w == 8 * 4 and not hasattr(m, "Mctl_n") and not hasattr(m, "Mbot_dummy")
    assert (m.Mbot_in.of.params.w, m.Mbot_in.of.params.l) == (4, 14)
    for name in ("Mgate_top", "Mgate_drop", "Mgate_pass", "Mgate_cas", "Mgate_off"):
        device = getattr(m, name).of.params
        assert (device.w, device.l, device.vth) == (4, 1, MosVth.LOW)
    assert m.Mctl_dummy.conns == {"d": m.gate_ctl, "g": m.clk_b, "s": m.gate_ctl, "b": m.vdd}
    assert m.Mgate_off_dummy.conns == {"d": m.gate_off, "g": m.clk, "s": m.gate_off, "b": m.vss}


def test_every_device_on_the_boosted_nodes_is_one_the_capacitor_rule_counts() -> None:
    """The boosted nodes are ``gate`` (A) and ``boot_top`` (P), joined by Mgate while tracking. The
    rule (``params._boosted_f``) counts MN's and Mbot_in's gates, Mpre's gate and Mgate_top's
    drain; Mcap's gate is C_b itself; Mgate's and Mpre's sources and wells and Mgate_top's gate
    hold no charge the capacitor must give (they sit on the boosted nodes on both sides, or on a
    node that follows them): no other device touches the two nodes."""
    m = netlist(runs.bootstrap.build())
    on = {
        (name, terminal)
        for name, instance in m.instances.items()
        for terminal, net in instance.conns.items()
        if net is m.gate or net is m.boot_top
    }
    assert on == {
        ("MN", "g"),
        ("Mbot_in", "g"),
        ("Mpre", "g"),
        ("Mpre", "s"),
        ("Mpre", "b"),
        ("Mgate", "d"),
        ("Mgate", "s"),
        ("Mgate", "b"),
        ("Mgate_top", "d"),
        ("Mgate_top", "g"),
        ("Mcap", "g"),
    }


def test_the_parameters_refuse_what_does_not_build() -> None:
    """A size below one unit, and a dummy (half its switch) on a switch narrower than two units."""
    for fields in ({"mos_w": 0}, {"cap_l": 0}, {"bot_l": 0}, {"dummy": True, "mos_w": 1}):
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
    plans = {name: module_plan(pnr_input(_module(named[name]()))) for name in named}
    assert {name: plan["rows"] for name, plan in plans.items()} == {
        "frida1": [["Mp"], ["Mn"]],
        "tgate_dummy": [["Mp", "Mp_dummy"], ["Mn", "Mn_dummy"]],
        "nmos": [["Mn_a"], ["Mn_b"]],
        # the PMOS on the boosted node (their own well, two rows tall or more) beside a column of
        # the other helpers' two rows; the switch at its row's right end, by its output's edge pin
        "bootstrap": [["Mpre", "Mgate", "Xcolumn0"], ["Mcap"], ["Mbot_in", "Mn"]],
    }
    (column,) = [c for c in plans["bootstrap"]["constraints"] if c["constraint"] == "GroupBlocks"]
    (floorplan,) = [c for c in column["constraints"] if c["constraint"] == "Floorplan"]
    assert floorplan["regions"] == [
        ["Mctl_p", "Mctl_on", "Mctl_dummy"],
        ["Mgate_top", "Mgate_drop", "Mgate_pass", "Mgate_cas", "Mgate_off", "Mgate_off_dummy", "Mbot", "Mctl_cap"],
    ]
