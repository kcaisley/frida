"""The amplifier's generator (``netlist``), the designs its parameters refuse, and its placement
(``flow.layout.hdl21align``): complete for every instance of its space, and, for the named
designs, its rows top first."""

import hdl21 as h
import pytest
from hdl21.prefix import f
from hdl21.primitives import MosType

from flow import pipeline
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import runs
from .params import Params, Topology
from .subckt import Nets, netlist


def test_five_t_mirror_makes_outp_follow_inp() -> None:
    m = netlist(Params())
    assert m.Min_p.conns["d"] is m.mirror and m.Mload_d.conns["g"] is m.mirror and m.Mload_d.conns["d"] is m.mirror
    assert m.Min_n.conns["d"] is m.outp and m.Mload.conns["d"] is m.outp
    assert m.Mtail.conns["g"] is m.vbn and m.Mtail.conns["s"] is m.vss


def test_pmos_input_mirrors_between_the_rails() -> None:
    m = netlist(runs.five_t_pmos())
    assert m.Mtail.conns["s"] is m.vdd and m.Mtail.conns["g"] is m.vbp
    assert m.Mload.conns["s"] is m.vss


def test_telescopic_and_folded_cascodes() -> None:
    t = netlist(runs.telescopic())
    assert t.Mcas_in_p.conns["s"] is t.Min_p.conns["d"] and t.Mcas_in_p.conns["d"] is t.outn
    assert t.Mcas_load_n.conns["d"] is t.outp and t.Mload_n.conns["g"] is t.vbp
    fo = netlist(runs.folded())
    assert fo.Mtop_p.conns["d"] is fo.Min_p.conns["d"] and fo.Mcas_fold_p.conns["s"] is fo.fold_p
    assert fo.Mcas_bottom_p.conns["d"] is fo.outn and fo.Mbottom_p.conns["g"] is fo.vbn


def test_self_biased_tails_follow_the_inp_drains() -> None:
    m = netlist(runs.self_biased())
    assert m.Mtail_n.conns["g"] is m.tail_g and m.Mtail_p.conns["g"] is m.tail_g
    assert m.Min_p_n.conns["d"] is m.tail_g and m.Min_n_p.conns["d"] is m.outp


def test_two_stage_drives_the_outputs_from_the_first_stage() -> None:
    m = netlist(runs.two_stage())
    assert m.Mcas_in_n.conns["d"] is m.out1p and m.Mstage2_n.conns["g"] is m.out1n
    assert m.Mstage2_p.conns["d"] is m.outp and m.Mstage2_p.conns["s"] is m.vdd
    assert not hasattr(m, "Cmiller_p")
    c = netlist(Params(topology=Topology.TELESCOPIC, two_stage=True, miller=50 * f))
    assert c.Cmiller_p.conns["p"] is c.outp and c.Cmiller_p.conns["n"] is c.out1p


@pytest.mark.parametrize(
    "setting",
    (
        {"topology": Topology.SELF_BIASED, "input_xtors": MosType.PMOS},
        {"miller": 10 * f},  # a Miller capacitor without a second stage
        {"tail_w": 0},
    ),
)
def test_the_parameters_refuse_what_does_not_build(setting) -> None:
    with pytest.raises(ValueError):
        Params(**setting)


def test_the_runs_name_six_designs_at_seven_sizings() -> None:
    named = pipeline.singles(runs)
    assert set(named) == {"five_t", "five_t_pmos", "telescopic", "folded", "self_biased", "two_stage"}
    sized = dict(runs.sizes.instances("tsmc65"))
    assert len(sized) == 6 * 7 and len(set(map(repr, sized.values()))) == 42
    # every width scaled together; the defaults' sizing is the named design itself
    assert sized["sizes(telescopic_w16)"] == runs.telescopic()
    half = sized["sizes(two_stage_w8)"]
    assert (half.in_w, half.tail_w, half.load_w, half.cas_w, half.stage2_w) == (8, 8, 8, 8, 8) and half.two_stage
    assert sized["sizes(folded_in_l4)"].in_l == 4 and sized["sizes(folded_in_w32)"].in_w == 32
    long = sized["sizes(self_biased_source_l8)"]
    assert (long.tail_l, long.load_l) == (8, 8) and long.topology is Topology.SELF_BIASED


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65", "sky130", "gf180"))
def test_every_instance_states_a_complete_placement(pdk: str) -> None:
    h.pdk.set_default(pytest.importorskip(f"pdk.{pdk}.hdl21").pdk_logic)  # a PDK-free checkout (CI) has none
    for _label, params in pipeline.design(runs, pdk):
        pnr = pnr_input(netlist(params))
        assert pnr is not None and issues(pnr) == []
    # a device the rows do not know leaves the amplifier to ALIGN
    assert pnr_input(netlist(Params(two_stage=True))) is None
    assert pnr_input(netlist(Params(topology=Topology.TELESCOPIC, two_stage=True, miller=50 * f))) is None


def test_the_named_designs_rows() -> None:
    """Each named design's rows, top first: the loads above the cascodes above the input pair and
    its tail, each pair's devices at mirrored places; a PMOS input's pair on top."""
    h.pdk.set_default(pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic)
    named = pipeline.singles(runs)
    plans = {name: module_plan(pnr_input(netlist(named[name]()))) for name in named}
    assert all(plan["symmetric"] for plan in plans.values())
    assert {name: plan["rows"] for name, plan in plans.items()} == {
        "five_t": [["Mload_d", "Mload"], ["Min_p", "Mtail", "Min_n"]],
        "five_t_pmos": [["Min_p", "Mtail", "Min_n"], ["Mload_d", "Mload"]],
        "telescopic": [
            ["Mload_p", "Mload_n"],
            ["Mcas_load_p", "Mcas_load_n"],
            ["Mcas_in_p", "Mcas_in_n"],
            ["Min_p", "Mtail", "Min_n"],
        ],
        "folded": [
            ["Mtop_p", "Mtop_n"],
            ["Mcas_fold_p", "Mcas_fold_n"],
            ["Mcas_bottom_p", "Mcas_bottom_n"],
            ["Mbottom_p", "Min_p", "Mtail", "Min_n", "Mbottom_n"],
        ],
        "self_biased": [["Min_p_p", "Mtail_p", "Min_n_p"], ["Min_p_n", "Mtail_n", "Min_n_n"]],
        "two_stage": [
            ["Mstage2_p", "Mload_p", "Mload_n", "Mstage2_n"],
            ["Mcas_load_p", "Mcas_load_n"],
            ["Mcas_in_p", "Mcas_in_n"],
            ["Mstage2_src_p", "Min_p", "Mtail", "Min_n", "Mstage2_src_n"],
        ],
    }


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65", "sky130", "gf180"))
def test_every_pdk_compiles_every_named_design(pdk: str) -> None:
    pytest.importorskip(f"pdk.{pdk}.hdl21")
    from flow.circuit.netlists import compile_block

    for name, design in pipeline.singles(runs).items():
        block = compile_block(netlist, design(), pdk, name, Nets)
        assert [port.name for port in block.ports] == [
            net.name for net in Nets.signals.values() if net.vis == h.Visibility.PORT
        ]
        assert block.module.instances
