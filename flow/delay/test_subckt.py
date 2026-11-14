"""The delay line and ring generator (``netlist``): its stages' wiring, the designs its parameters
refuse, and its placement (``flow.layout.hdl21align``): complete for every instance of its space,
and each named chain's rows, top first."""

import hdl21 as h
import pytest
from hdl21.primitives import MosType

from flow import pipeline
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import runs
from .params import Control, Params, Stage
from .subckt import netlist


def test_default_delay_is_a_five_stage_inverter_chain() -> None:
    params = Params()
    assert (params.stage, params.control, params.stages, params.ring, params.differential) == (
        Stage.INVERTER,
        Control.NONE,
        5,
        False,
        False,
    )
    m = netlist(params)
    assert m.Minv1_p_n.conns["g"] is m.inp and m.Minv5_p_n.conns["d"] is m.outp
    assert m.Minv2_p_p.conns["g"] is m.p1 and m.Minv2_p_p.conns["s"] is m.vdd
    assert not hasattr(m, "Men1_p_p")


def test_ring_first_stage_is_a_nand_with_enable() -> None:
    m = netlist(runs.ring5())
    assert m.Minv1_p_n.conns["g"] is m.outp  # the loop closes
    assert m.Men1_p_n.conns["d"] is m.Minv1_p_n.conns["s"] and m.Men1_p_n.conns["g"] is m.en
    assert m.Men1_p_p.conns["d"] is m.p1 and m.Men1_p_p.conns["g"] is m.en and m.Men1_p_p.conns["s"] is m.vdd


def test_coupled_ring_crosses_its_chains_and_couples_each_stage() -> None:
    m = netlist(runs.ring4_coupled())
    assert m.Minv1_p_n.conns["g"] is m.outn and m.Minv1_n_n.conns["g"] is m.outp
    assert m.Mfb2_p_n.conns["g"] is m.n2 and m.Mfb2_p_n.conns["d"] is m.p2
    assert m.Mfb2_n_p.conns["g"] is m.p2 and m.Mfb2_n_p.conns["d"] is m.n2
    assert m.Minj.conns["d"] is m.p1 and m.Minj.conns["s"] is m.n1 and m.Minj.conns["g"] is m.inj


def switch_levels(module: h.Module, given: dict[str, int]) -> dict[str, int]:
    """A switch-level evaluation of ``module``'s static state: from the nets of ``given`` levels (the
    rails and the inputs), an NMOS conducts with its gate at 1 and a PMOS at 0; the nets joined by
    conducting devices take the level of the rail among them, until nothing changes. A group joined
    to both rails (two devices fighting) fails; nets never joined to a rail are left out."""
    devices = [(inst.of.params.tp, *(inst.conns[t].name for t in "gds")) for inst in module.instances.values()]
    level = dict(given)
    while True:
        joined = {net: {net} for net in {net for _, _, d, s in devices for net in (d, s)} | set(level)}
        for tp, g, d, s in devices:
            if g in level and level[g] == (1 if tp is MosType.NMOS else 0):
                group = joined[d] | joined[s]
                for net in group:
                    joined[net] = group
        found = dict(given)
        for net, group in joined.items():
            rails = {given[rail] for rail in group & {"vdd", "vss"}}
            assert len(rails) < 2, f"{net} joined to both rails"
            if rails:
                found[net] = rails.pop()
        if found == level:
            return level
        level = found


# A disabled differential ring rests complementary. With en low (enb high): the p chain's first stage
# is a NAND with en, its series NMOS off and Men1_p_p pulling p1 high; the n chain's a NOR with enb,
# its series PMOS off and Men1_n_n pulling n1 low. Then p2..p4 = 0, 1, 0 and n2..n4 = 1, 0, 1, so
# outp = 0 and outn = 1: stage 1's inverters see outn = 1 (p side: its PMOS off, its NMOS cut by the
# series NMOS) and outp = 0 (n side: its NMOS off, its PMOS cut by the series PMOS), and every
# coupling inverter drives the value its output already holds, so no device fights another (the
# evaluation fails on a net joined to both rails). Without the n chain's gating n1 settles high with
# p1, every stage's outputs equal ([Razavi-PLL] Sec. 4.9.3, Fig. 4.36, p. 130: the latched state).
def test_a_disabled_differential_ring_rests_complementary() -> None:
    for ring in (runs.ring4_coupled(), runs.ring4_tail()):
        m = netlist(ring)
        assert m.Men1_p_n.conns["g"] is m.en and m.Minv1_p_n.conns["s"] is m.Men1_p_n.conns["d"]
        assert m.Men1_n_p.conns["g"] is m.enb and m.Minv1_n_p.conns["s"] is m.Men1_n_p.conns["d"]
        assert m.Men1_n_n.conns["d"] is m.n1 and m.Men1_n_n.conns["g"] is m.enb
        # the tail's vctrl off: no NMOS of the chains reaches ground but the coupling inverters'
        level = switch_levels(m, {"vdd": 1, "vss": 0, "en": 0, "inj": 0, "vctrl": 0})
        assert level["enb"] == 1 and (level["outp"], level["outn"]) == (0, 1)
        assert [(level[f"p{k}"], level[f"n{k}"]) for k in (1, 2, 3)] == [(1, 0), (0, 1), (1, 0)]
    # enabled, nothing holds stage 1: its outputs follow the loop, no static level of their own
    assert "p1" not in switch_levels(netlist(runs.ring4_coupled()), {"vdd": 1, "vss": 0, "en": 1, "inj": 0})
    # the single-ended ring keeps its NAND alone: no complement, no n chain
    single = netlist(runs.ring5())
    assert not any(hasattr(single, name) for name in ("enb", "Menb_n", "Men1_n_n", "Men1_n_p"))


def test_starved_stages_and_shared_tail() -> None:
    m = netlist(runs.ring5_starved())
    assert m.Mstarve3_p_n.conns["g"] is m.vbn and m.Minv3_p_n.conns["s"] is m.Mstarve3_p_n.conns["d"]
    assert m.Mstarve3_p_p.conns["g"] is m.vbp and m.Minv3_p_p.conns["s"] is m.Mstarve3_p_p.conns["d"]
    t = netlist(runs.ring4_tail())
    assert t.Mtail.conns["g"] is t.vctrl and t.Minv3_n_n.conns["s"] is t.tail and t.Mfb3_n_n.conns["s"] is t.vss


@pytest.mark.parametrize(
    "setting",
    (
        {"ring": True, "stages": 4},  # single-ended ring: no inversion around the loop
        {"stage": Stage.COUPLED},  # coupled stages need both chains
        {"inject": True, "differential": True},  # injection belongs to a ring
        # two uncoupled chains crossed at the loop: one loop of 2N inverters, which latches
        {"ring": True, "differential": True, "stages": 3},
        {"ring": True, "differential": True, "stages": 4},
        {"inv_n_w": 0},
        {"stages": 0},
    ),
)
def test_the_parameters_refuse_what_does_not_build(setting) -> None:
    with pytest.raises(ValueError):
        Params(**setting)


def _module(params: Params) -> h.Module:
    netlist.Cache.reset()
    return netlist(params)


def test_every_design_places_every_device_once() -> None:
    """Every design the runs name states a complete placement: each device in one row, once."""
    designs = dict(pipeline.design(runs, "tsmc65"))
    assert len(designs) == 48
    for params in designs.values():
        pnr = pnr_input(_module(params))
        assert pnr is not None and issues(pnr) == []


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65", "sky130", "gf180"))
def test_every_named_chain_builds_and_places_in_every_pdk(pdk: str) -> None:
    h.pdk.set_default(pytest.importorskip(f"pdk.{pdk}.hdl21").pdk_logic)  # a PDK-free checkout (CI) has none
    for single in pipeline.singles(runs).values():
        assert issues(pnr_input(_module(single()))) == []


def test_the_named_chains_rows() -> None:
    named = pipeline.singles(runs)
    plans = {name: module_plan(pnr_input(_module(named[name]()))) for name in named}
    # a ring's stages in its folded order, the enable devices at its first stage
    assert plans["ring5"]["rows"] == [
        ["Men1_p_p", "Minv1_p_p", "Minv5_p_p", "Minv2_p_p", "Minv4_p_p", "Minv3_p_p"],
        ["Men1_p_n", "Minv1_p_n", "Minv5_p_n", "Minv2_p_n", "Minv4_p_n", "Minv3_p_n"],
    ]
    # the starving heads above and the feet below the inverters
    assert plans["ring5_starved"]["rows"][0] == [f"Mstarve{k}_p_p" for k in (1, 5, 2, 4, 3)]
    assert plans["ring5_starved"]["rows"][-1] == [f"Mstarve{k}_p_n" for k in (1, 5, 2, 4, 3)]
    assert len(plans["ring5_starved"]["rows"]) == 4
    # each stage's chains side by side, the coupling inverters between the main ones' rows, the
    # injection device across the first stage
    # the enable's inverter at the rows' left end
    stages = [f"{k}_{side}" for k in (1, 4, 2, 3) for side in ("p", "n")]
    assert plans["ring4_coupled"]["rows"] == [
        ["Menb_p", "Men1_p_p", "Minv1_p_p", "Minv1_n_p", "Men1_n_p", *(f"Minv{stage}_p" for stage in stages[2:])],
        [f"Mfb{stage}_p" for stage in stages],
        [f"Mfb{stage}_n" for stage in stages],
        [
            *("Menb_n", "Men1_p_n", "Minv1_p_n", "Minj", "Minv1_n_n", "Men1_n_n"),
            *(f"Minv{stage}_n" for stage in stages[2:]),
        ],
    ]
    # the shared tail in the middle of the inverters' NMOS row
    assert plans["ring4_tail"]["rows"][-1] == [
        *("Menb_n", "Men1_p_n", "Minv1_p_n", "Minv1_n_n", "Men1_n_n", "Minv4_p_n", "Minv4_n_n"),
        "Mtail",
        *("Minv2_p_n", "Minv2_n_n", "Minv3_p_n", "Minv3_n_n"),
    ]
    assert plans["chain4"]["rows"] == [[f"Minv{k}_p_p" for k in range(1, 5)], [f"Minv{k}_p_n" for k in range(1, 5)]]
    # a differential line's rows mirrored about their centre: the p chain left, the n chain right
    assert plans["chain2_coupled"]["symmetric"] and plans["chain2_coupled"]["rows"] == [
        ["Minv1_p_p", "Minv2_p_p", "Minv2_n_p", "Minv1_n_p"],
        ["Mfb1_p_p", "Mfb2_p_p", "Mfb2_n_p", "Mfb1_n_p"],
        ["Mfb1_p_n", "Mfb2_p_n", "Mfb2_n_n", "Mfb1_n_n"],
        ["Minv1_p_n", "Minv2_p_n", "Minv2_n_n", "Minv1_n_n"],
    ]
    assert plans["chain4_starved"]["rows"] == [
        [f"Mstarve{k}_p_p" for k in range(1, 5)],
        [f"Minv{k}_p_p" for k in range(1, 5)],
        [f"Minv{k}_p_n" for k in range(1, 5)],
        [f"Mstarve{k}_p_n" for k in range(1, 5)],
    ]
    assert not any(plans[name]["symmetric"] for name in named if name != "chain2_coupled")
