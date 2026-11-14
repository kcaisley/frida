"""Software-only checks of the chain's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import pytest

from . import params, runs, sim
from .params import TbParams


def test_a_run_defaults_to_the_bench_every_chain_is_characterized_on() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params) == ("tsmc65", params.Params())
    assert (tb.vdd, tb.vcont_v, tb.cload_f, tb.vinj_v) == (1.2, 0.8, 2e-15, 0.0)
    assert (tb.clock_period_s, tb.transition_time_s) == (4e-9, 50e-12)
    assert (tb.enable_delay_s, tb.kick_time_s, tb.stop_time_s) == (1e-9, 1e-9, 40e-9)
    # Spectre's output every 2 ps, its step no longer
    assert tb.waveform_sample_interval_s == 2e-12


def test_the_testbench_clocks_enables_kicks_and_biases_the_chain() -> None:
    tb = TbParams(params=runs.ring5_starved(), vdd=1.0, vcont_v=0.7)
    bench = sim.testbench(tb)
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Delay")
    # one control voltage: vbn and vctrl at it, vbp the supply minus it
    assert float(bench.vvbn.of.params.dc) == pytest.approx(0.7)
    assert float(bench.vvctrl.of.params.dc) == pytest.approx(0.7)
    assert float(bench.vvbp.of.params.dc) == pytest.approx(0.3)
    # complementary input clocks, their first edge a quarter period in
    inp, inn = bench.vinp.of.params, bench.vinn.of.params
    assert (float(inp.v1), float(inp.v2), float(inn.v1), float(inn.v2)) == pytest.approx((0.0, 1.0, 1.0, 0.0))
    assert float(inp.period) == pytest.approx(4e-9) and float(inp.delay) == pytest.approx(1e-9)
    assert float(inp.width) == pytest.approx(1.95e-9)
    # the enable rises once; the kick-start follows it by two transitions and holds for kick_time_s
    assert float(bench.ven.of.params.delay) == pytest.approx(1e-9)
    assert float(bench.vkick.of.params.delay) == pytest.approx(1.1e-9)
    assert float(bench.vkick.of.params.width) == pytest.approx(1e-9)
    # the kick-start switches: twice the output inverter's devices, outp to vdd and outn to vss
    assert bench.mkickp.conns["d"] is bench.outp and bench.mkickp.conns["s"] is bench.vdd
    assert bench.mkickn.conns["d"] is bench.outn and bench.mkickn.conns["s"] is bench.vss
    assert (bench.mkickp.of.params.w, bench.mkickn.of.params.w) == (16, 8)
    assert float(bench.cloadp.of.params.c) == float(bench.cloadn.of.params.c) == pytest.approx(2e-15)


def test_a_run_saves_the_ports_and_the_supply_current() -> None:
    assert set(sim.SAVES) == {
        *(f"xtop.{net}" for net in ("inp", "inn", "outp", "outn", "en", "inj", "vbn", "vbp", "vctrl")),
        "xtop.vvdd:p",
    }


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cload_f": 0.0},
        {"kick_time_s": 0.0},
        {"vcont_v": 1.3},  # above the supply
        {"vcont_v": -0.1},
        {"clock_period_s": 100e-12},  # no longer than its two transitions
        {"transition_time_s": 0.0},
        {"enable_delay_s": 40e-9},  # the enable never rises within the transient
        {"waveform_sample_interval_s": 0.0},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)
