"""Software-only checks of the latch's testbench parameters and testbenches (no simulator)."""

from typing import Any

import hdl21 as h
import pytest

from . import runs, sim
from .params import Bench, Params, Style, TbParams


def test_a_run_defaults_to_the_timing_bench_of_the_c2mos_latch() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.bench) == ("tsmc65", Params(), Bench.TIMING)
    assert (tb.clock_period_s, tb.data_offset_s, tb.transition_time_s) == (2e-9, 0.5e-9, 50e-12)
    assert (tb.cload_f, tb.cycles, tb.waveform_sample_interval_s) == (2e-15, 8, 1e-12)
    # the reset and nine clock cycles; an SR latch three set and reset periods; a strike twice its time
    assert tb.stop_s == pytest.approx(0.5e-9 + 9 * 2e-9)
    assert TbParams(params=runs.sr_nand()).stop_s == pytest.approx(3 * 5.2e-9)
    assert TbParams(bench=Bench.UPSET, charge_c=5e-15).stop_s == pytest.approx(4e-9)


def test_the_timing_bench_puts_data_an_offset_before_each_capturing_edge() -> None:
    """A flip-flop captures on the rising edge, a latch on the falling one; data crosses mid-supply
    ``data_offset_s`` before it, in the first cycle after the reset."""
    period, transition = 2e-9, 50e-12
    for params, capture in ((runs.flop_rst(), period / 2 + transition / 2), (Params(), period + 1.5 * transition)):
        bench = sim.testbench(TbParams(params=params, data_offset_s=0.2e-9))
        assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Latch")
        assert float(bench.vclk.of.params.period) == pytest.approx(period)
        assert float(bench.vclk.of.params.delay) == pytest.approx(period / 2)
        data = bench.vd.of.params
        assert float(data.period) == pytest.approx(2 * period)
        assert float(data.delay) + transition / 2 == pytest.approx(capture + period - 0.2e-9)
        assert float(bench.cloadq.of.params.c) == float(bench.cloadqb.of.params.c) == pytest.approx(2e-15)


def test_an_sr_latch_gets_set_and_reset_pulses_active_as_its_gates_take_them() -> None:
    nand = sim.testbench(TbParams(params=runs.sr_nand(), vdd=1.0))
    nor = sim.testbench(TbParams(params=runs.sr_nor(), vdd=1.0))
    assert (float(nand.vs.of.params.v1), float(nand.vs.of.params.v2)) == (1.0, 0.0)
    assert (float(nor.vs.of.params.v1), float(nor.vs.of.params.v2)) == (0.0, 1.0)
    assert float(nor.vs.of.params.delay) == pytest.approx(5.2e-9 / 4)
    assert float(nor.vr.of.params.delay) == pytest.approx(3 * 5.2e-9 / 4)


def test_the_upset_bench_holds_a_one_and_loads_q_alone() -> None:
    bench = sim.testbench(TbParams(params=runs.latch_dice(), bench=Bench.UPSET, charge_c=10e-15))
    assert float(bench.vd.of.params.dc) == pytest.approx(1.2) and float(bench.vrst.of.params.dc) == 0.0
    # open (clk high) for the first nanosecond, then closed
    assert (float(bench.vclk.of.params.v1), float(bench.vclk.of.params.v2)) == (1.2, 0.0)
    assert float(bench.vclk.of.params.delay) == pytest.approx(1e-9)
    assert hasattr(bench, "cloadq") and not hasattr(bench, "cloadqb")


def test_a_run_saves_the_ports_and_the_supply_current() -> None:
    ports = ("d", "s", "r", "rst", "clk", "clkb", "q", "qb")
    assert set(sim.SAVES) == {*(f"xtop.{port}" for port in ports), "xtop.vvdd:p"}


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cload_f": 0.0},
        {"transition_time_s": 0.0},
        {"clock_period_s": 80e-12},
        {"data_offset_s": 1.1e-9},
        {"reset_time_s": -1e-9},
        {"cycles": 2},
        {"charge_c": 5e-15},
        {"bench": Bench.UPSET},
        {"bench": Bench.UPSET, "charge_c": 5e-15, "upset_time_s": 1e-9},
        {"bench": Bench.UPSET, "charge_c": 5e-15, "params": Params(reset=True)},
        {"bench": Bench.UPSET, "charge_c": 5e-15, "params": Params(style=Style.SR_NOR)},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)
