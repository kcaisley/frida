"""Software-only structural tests for the latch generator."""

import pytest

from .subckt import CASES, Latch, LatchParams, Style


def test_default_latch_is_transparent_while_clk_is_high() -> None:
    Latch.Cache.reset()
    m = Latch(LatchParams())
    # forward clocked inverter: data devices on the rails, clocked devices at the inner node qb
    assert m.Mfwd_n.conns["g"] is m.d and m.Mfwd_n.conns["s"] is m.vss
    assert m.Mfwd_nclk.conns["g"] is m.clk and m.Mfwd_nclk.conns["d"] is m.qb
    assert m.Mfwd_pclk.conns["g"] is m.clkb
    # feedback drives qb from q while clk is low
    assert m.Mfb_n.conns["g"] is m.q and m.Mfb_nclk.conns["g"] is m.clkb and m.Mfb_pclk.conns["g"] is m.clk
    assert m.Mout_n.conns["g"] is m.qb and m.Mout_p.conns["d"] is m.q


def test_flop_master_and_slave_take_opposite_clocks() -> None:
    m = Latch(CASES["flop_rst"])
    assert m.Mfwd_m_nclk.conns["g"] is m.clkb and m.Mfwd_s_nclk.conns["g"] is m.clk
    assert m.Mfwd_s_n.conns["g"] is m.m and m.Mout_m_n.conns["d"] is m.m
    # reset: a NOR at each output
    assert m.Mrst_s_n.conns["g"] is m.rst and m.Mrst_s_n.conns["d"] is m.q
    assert m.Mout_s_p.conns["s"] is m.Mrst_s_p.conns["d"]


def test_divider_feeds_qb_back_to_the_master() -> None:
    m = Latch(CASES["div2"])
    assert m.Mfwd_m_n.conns["g"] is m.qb and m.Mfwd_m_p.conns["g"] is m.qb


@pytest.mark.parametrize("style", (Style.SR_NAND, Style.SR_NOR))
def test_sr_latches_cross_couple(style) -> None:
    m = Latch(LatchParams(style=style))
    # s sets q: on q's NAND gate (active low), on qb's NOR gate (active high)
    on_q, on_qb = (m.s, m.r) if style == Style.SR_NAND else (m.r, m.s)
    assert m.Mq_n_in.conns["g"] is on_q and m.Mq_n_fb.conns["g"] is m.qb
    assert m.Mqb_n_in.conns["g"] is on_qb and m.Mqb_n_fb.conns["g"] is m.q
    series = m.Mq_n_in if style == Style.SR_NAND else m.Mq_p_in
    assert series.conns["s"] is m.q_stack


def test_tspc_flop_runs_on_clk_alone() -> None:
    m = Latch(CASES["flop_tspc"])
    assert m.Mt1_n.conns["g"] is m.d and m.Mt1_pclk.conns["g"] is m.clk and m.Mt1_pclk.conns["d"] is m.x
    assert m.Mt2_pclk.conns == {"d": m.y, "g": m.clk, "s": m.vdd, "b": m.vdd}
    assert m.Mt2_n.conns["g"] is m.x and m.Mt3_p.conns["g"] is m.y and m.Mt3_nclk.conns["d"] is m.qb
    assert m.Mout_n.conns["g"] is m.qb and m.Mout_p.conns["d"] is m.q
    assert all(inst.conns["g"] is not m.clkb for inst in m.instances.values())
    divider = Latch(CASES["div2_tspc"])
    assert divider.Mt1_n.conns["g"] is divider.qb and divider.Mt1_p.conns["g"] is divider.qb


def test_dice_nodes_interlock_and_take_d_while_clk_is_high() -> None:
    m = Latch(CASES["latch_dice"])
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
def test_invalid_latches_raise(setting) -> None:
    with pytest.raises(ValueError):
        Latch(LatchParams(**setting))
