"""The latch's generator (``netlist``), the designs its parameters refuse, and its placement
(``flow.layout.hdl21align``): complete for every instance of its runs, its rows top first."""

import hdl21 as h
import pytest

from flow import pipeline
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import runs
from .params import Params, Style
from .subckt import netlist


def test_default_latch_is_transparent_while_clk_is_high() -> None:
    m = netlist(Params())
    # forward clocked inverter: data devices on the rails, clocked devices at the inner node qb
    assert m.Mfwd_n.conns["g"] is m.d and m.Mfwd_n.conns["s"] is m.vss
    assert m.Mfwd_nclk.conns["g"] is m.clk and m.Mfwd_nclk.conns["d"] is m.qb
    assert m.Mfwd_pclk.conns["g"] is m.clkb
    # feedback drives qb from q while clk is low
    assert m.Mfb_n.conns["g"] is m.q and m.Mfb_nclk.conns["g"] is m.clkb and m.Mfb_pclk.conns["g"] is m.clk
    assert m.Mout_n.conns["g"] is m.qb and m.Mout_p.conns["d"] is m.q


def test_flop_master_and_slave_take_opposite_clocks() -> None:
    m = netlist(runs.flop_rst())
    assert m.Mfwd_m_nclk.conns["g"] is m.clkb and m.Mfwd_s_nclk.conns["g"] is m.clk
    assert m.Mfwd_s_n.conns["g"] is m.m and m.Mout_m_n.conns["d"] is m.m
    # reset: a NOR at each output
    assert m.Mrst_s_n.conns["g"] is m.rst and m.Mrst_s_n.conns["d"] is m.q
    assert m.Mout_s_p.conns["s"] is m.Mrst_s_p.conns["d"]


def test_divider_feeds_qb_back_to_the_master() -> None:
    m = netlist(runs.div2())
    assert m.Mfwd_m_n.conns["g"] is m.qb and m.Mfwd_m_p.conns["g"] is m.qb


@pytest.mark.parametrize("style", (Style.SR_NAND, Style.SR_NOR))
def test_sr_latches_cross_couple(style) -> None:
    m = netlist(Params(style=style))
    # s sets q: on q's NAND gate (active low), on qb's NOR gate (active high)
    on_q, on_qb = (m.s, m.r) if style is Style.SR_NAND else (m.r, m.s)
    assert m.Mq_n_in.conns["g"] is on_q and m.Mq_n_fb.conns["g"] is m.qb
    assert m.Mqb_n_in.conns["g"] is on_qb and m.Mqb_n_fb.conns["g"] is m.q
    series = m.Mq_n_in if style is Style.SR_NAND else m.Mq_p_in
    assert series.conns["s"] is m.q_stack


def test_tspc_flop_runs_on_clk_alone() -> None:
    m = netlist(runs.flop_tspc())
    assert m.Mt1_n.conns["g"] is m.d and m.Mt1_pclk.conns["g"] is m.clk and m.Mt1_pclk.conns["d"] is m.x
    assert m.Mt2_pclk.conns == {"d": m.y, "g": m.clk, "s": m.vdd, "b": m.vdd}
    assert m.Mt2_n.conns["g"] is m.x and m.Mt3_p.conns["g"] is m.y and m.Mt3_nclk.conns["d"] is m.qb
    assert m.Mout_n.conns["g"] is m.qb and m.Mout_p.conns["d"] is m.q
    assert all(inst.conns["g"] is not m.clkb for inst in m.instances.values())
    divider = netlist(runs.div2_tspc())
    assert divider.Mt1_n.conns["g"] is divider.qb and divider.Mt1_p.conns["g"] is divider.qb


def test_dice_nodes_interlock_and_take_d_while_clk_is_high() -> None:
    m = netlist(runs.latch_dice())
    nodes = [m.x1, m.x2, m.x3, m.x4]
    for index, node in enumerate(nodes, start=1):
        up, down = getattr(m, f"Mx{index}_p"), getattr(m, f"Mx{index}_n")
        assert up.conns["d"] is node and up.conns["g"] is nodes[(index - 2) % 4] and up.conns["s"] is m.vdd
        assert down.conns["d"] is node and down.conns["g"] is nodes[index % 4] and down.conns["s"] is m.vss
        # each node's own clocked inverter: data devices on the rails, clocked devices at the node
        data_n, clock_n = getattr(m, f"Mw{index}_n"), getattr(m, f"Mw{index}_nclk")
        assert data_n.conns["g"] is (m.db if index % 2 == 0 else m.d) and data_n.conns["s"] is m.vss
        assert clock_n.conns["d"] is node and clock_n.conns["g"] is m.clk
        assert getattr(m, f"Mw{index}_pclk").conns["g"] is m.clkb
    assert m.Mout_q_n.conns["g"] is m.x1 and m.Mout_qb_n.conns["g"] is m.x2


@pytest.mark.parametrize(
    "setting",
    (
        {"divider": True},
        {"style": Style.SR_NAND, "reset": True},
        {"style": Style.SR_NOR, "flop": True},
        {"l": 0},
        {"style": Style.TSPC},
        {"style": Style.TSPC, "flop": True, "reset": True},
        {"style": Style.DICE, "flop": True},
    ),
)
def test_the_parameters_refuse_what_does_not_build(setting) -> None:
    with pytest.raises(ValueError):
        Params(**setting)


def test_the_runs_name_nine_designs_at_six_sizes() -> None:
    """The nine single designs, and the grids' fifty instances: each of the nine at four scales
    and at twice its length, the five with feedback devices with those doubled."""
    named = pipeline.singles(runs)
    assert list(named) == [
        *("latch", "latch_rst", "flop_rst", "div2", "flop_tspc", "div2_tspc", "latch_dice", "sr_nand", "sr_nor"),
    ]
    counts = {
        name: len(list(run.instances("tsmc65"))) for name, run in pipeline.runs(runs).items() if name not in named
    }
    assert counts == {"scaled": 36, "strong_feedback": 5, "long_channel": 9}
    assert dict(runs.scaled.instances("tsmc65"))["scaled(latch_x1)"] == Params()
    half = dict(runs.scaled.instances("tsmc65"))["scaled(latch_x0.5)"]
    assert (half.n_w, half.p_w, half.fb_n_w, half.fb_p_w) == (2, 4, 1, 2)


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65", "sky130", "gf180"))
def test_every_instance_states_a_complete_placement(pdk: str) -> None:
    h.pdk.set_default(pytest.importorskip(f"pdk.{pdk}.hdl21").pdk_logic)  # a PDK-free checkout (CI) has none
    for _label, params in pipeline.design(runs, pdk):
        pnr = pnr_input(netlist(params))
        assert pnr is not None and issues(pnr) == []


def test_the_named_designs_rows() -> None:
    h.pdk.set_default(pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic)
    named = pipeline.singles(runs)
    rows = {name: module_plan(pnr_input(netlist(named[name]())))["rows"] for name in named}
    clocked = [
        ["Mfwd_p", "Mfwd_pclk", "Mfb_pclk", "Mfb_p", "Mout_p"],
        ["Mfwd_n", "Mfwd_nclk", "Mfb_nclk", "Mfb_n", "Mout_n"],
    ]
    master = [
        ["Mfwd_m_p", "Mfwd_m_pclk", "Mfb_m_pclk", "Mfb_m_p", "Mrst_m_p", "Mout_m_p"],
        ["Mfwd_m_n", "Mfwd_m_nclk", "Mfb_m_nclk", "Mfb_m_n", "Mout_m_n", "Mrst_m_n"],
    ]
    slave = [[name.replace("_m_", "_s_") for name in row] for row in reversed(master)]
    tspc = [
        ["Mt1_p", "Mt1_pclk", "Mt2_pclk", "Mt3_p", "Mout_p"],
        ["Mt1_n", "Mt2_n", "Mt2_nclk", "Mt3_nclk", "Mt3_n", "Mout_n"],
    ]
    sr = [["Mq_p_in", "Mq_p_fb", "Mqb_p_fb", "Mqb_p_in"], ["Mq_n_in", "Mq_n_fb", "Mqb_n_fb", "Mqb_n_in"]]
    assert rows["latch"] == clocked
    assert rows["latch_rst"] == [[*clocked[0][:4], "Mrst_p", "Mout_p"], [*clocked[1], "Mrst_n"]]
    assert rows["flop_rst"] == rows["div2"] == [*master, *slave]
    assert rows["flop_tspc"] == rows["div2_tspc"] == tspc
    assert rows["sr_nand"] == rows["sr_nor"] == sr
    writers = [f"Mw{index}_{{}}{clocked}" for index in (1, 2, 3, 4) for clocked in ("", "clk")]
    assert rows["latch_dice"] == [
        ["Mdb_p", *(name.format("p") for name in writers), "Mout_q_p", "Mout_qb_p"],
        ["Mdb_n", *(name.format("n") for name in writers), "Mout_q_n", "Mout_qb_n"],
        ["Mx1_n", "Mx2_n", "Mx3_n", "Mx4_n"],
        ["Mx1_p", "Mx2_p", "Mx3_p", "Mx4_p"],
    ]
