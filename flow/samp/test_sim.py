"""Software-only checks of the sampler's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import pytest

from . import params, sim
from .params import TbParams


def test_a_run_defaults_to_the_bench_every_switch_is_characterized_on() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params) == ("tsmc65", params.Params())
    assert (tb.cload, tb.clock_period_s, tb.clock_high_time_s) == (params.LOAD_F, params.PERIOD_S, params.TRACK_S)
    assert (tb.clock_transition_time_s, tb.periods) == (params.TRANSITION_S, params.PERIODS) == (50e-12, 6)
    # Spectre's output every 5 ps, its step no longer; the run six periods of 10 ns
    assert tb.waveform_sample_interval_s == params.STROBE_S == 5e-12
    assert tb.stop_s == pytest.approx(60e-9)


def test_the_testbench_clocks_steps_and_loads_the_switch() -> None:
    tb = TbParams(clock_period_s=80e-9, clock_high_time_s=30e-9, input_voltage=0.7, input_step_v=0.0)
    bench = sim.testbench(tb)
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Samp")
    assert float(bench.vclk.of.params.period) == pytest.approx(80e-9)
    assert float(bench.vclk.of.params.width) == pytest.approx(30e-9)
    assert float(bench.vdin.of.params.dc) == pytest.approx(0.7)
    # with a step: low for a period, high for the next, each change in mid-hold
    stepped = sim.testbench(TbParams()).vdin.of.params
    assert (float(stepped.v1), float(stepped.v2)) == pytest.approx((0.55, 0.65))
    assert float(stepped.delay) == pytest.approx(7.5e-9) and float(stepped.period) == pytest.approx(20e-9)


def test_a_run_saves_the_ports_and_the_supply_current() -> None:
    assert set(sim.SAVES) == {"xtop.din", "xtop.dout", "xtop.clk", "xtop.clk_b", "xtop.vvdd:p"}


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"clock_transition_time_s": float("nan")},
        {"input_voltage": float("inf")},
        {"clock_delay_s": -1e-9},
        {"clock_high_time_s": 20e-9},
        {"periods": 0},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)
