"""Software-only checks of the chain's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import pytest

from . import params, runs, sim
from .params import TbParams


def test_a_run_defaults_to_the_bench_every_chain_is_characterized_on() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params) == ("tsmc65", params.Params())
    assert (tb.vdd, tb.vcont_v) == (1.2, 0.8)
    assert (tb.clock_period_s, tb.transition_time_s) == (4e-9, 50e-12)
    assert (tb.enable_delay_s, tb.stop_time_s) == (1e-9, 40e-9)
    # a time point forced every 2 ps
    assert tb.waveform_sample_interval_s == 2e-12


def test_a_starved_ring_is_enabled_biased_by_a_mirror_and_loaded_by_two_stages() -> None:
    tb = TbParams(params=runs.ring5_starved(), vdd=1.0, vcont_v=0.7)
    bench = sim.testbench(tb)
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Delay")
    # the bench's every instance: the chain, its load stages, the two supplies, the enable and the bias
    assert set(bench.instances) == {"dut", "load", "vvdd", "vvddbench", "ven", "vvbn", "mbias_n", "mbias_p"}
    # the enable rises once and stays; nothing else starts the ring
    assert float(bench.ven.of.params.delay) == pytest.approx(1e-9)
    assert float(bench.ven.of.params.width) > float(tb.stop_time_s)
    # vbn at the control; vbp a PMOS diode on the bench supply carrying an NMOS's current at vbn,
    # each sized as the chain's starving devices
    assert float(bench.vvbn.of.params.dc) == pytest.approx(0.7)
    mirror_n, mirror_p = bench.mbias_n, bench.mbias_p
    assert (mirror_n.conns["g"], mirror_n.conns["d"], mirror_n.conns["s"]) == (bench.vbn, bench.vbp, bench.vss)
    assert (mirror_p.conns["g"], mirror_p.conns["d"], mirror_p.conns["s"]) == (bench.vbp, bench.vbp, bench.vddbench)
    design = tb.params
    assert (mirror_n.of.params.w, mirror_p.of.params.w) == (design.starve_n_w, design.starve_p_w)
    # the output loaded by two more of the chain's stages, an open line on the bench supply: the
    # first one's output loaded by the second, as an inner node is
    assert bench.load.conns["inp"] is bench.outp and bench.load.conns["vdd"] is bench.vddbench
    assert bench.load.conns["outp"] is bench.loadp
    assert {name for name in bench.load.of.instances if name.startswith("Minv")} == {
        "Minv1_p_n",
        "Minv1_p_p",
        "Minv2_p_n",
        "Minv2_p_p",
    }
    # the chain alone on vvdd; the ports it has no device on tied to ground
    assert bench.dut.conns["vdd"] is bench.vdd and bench.vvdd.conns["p"] is bench.vdd
    assert all(bench.dut.conns[port] is bench.vss for port in ("inp", "inn", "outn", "inj", "vctrl"))
    assert bench.dut.conns["en"] is bench.en and bench.dut.conns["vbp"] is bench.vbp


def test_a_line_is_driven_through_two_of_its_own_stages() -> None:
    tb = TbParams(params=runs.chain4(), vdd=1.0)
    bench = sim.testbench(tb)
    # the chain, its driving and load stages, the two supplies and the one clock
    assert set(bench.instances) == {"dut", "driver", "load", "vvdd", "vvddbench", "vclockp"}
    # the source's complementary halves, their first edge a quarter period in, into the driver
    clock = bench.vclockp.of.params
    assert (float(clock.v1), float(clock.v2)) == pytest.approx((0.0, 1.0))
    assert float(clock.period) == pytest.approx(4e-9) and float(clock.delay) == pytest.approx(1e-9)
    assert float(clock.width) == pytest.approx(1.95e-9)
    driver = bench.driver
    assert driver.conns["inp"] is bench.clockp and driver.conns["outp"] is bench.inp
    assert driver.conns["vdd"] is bench.vddbench and driver.of.name.startswith("Delay")
    assert bench.dut.conns["inp"] is bench.inp
    # its two load stages the driver's design: one module
    assert bench.load.of is bench.driver.of and bench.load.conns["inp"] is bench.outp
    # single-ended: the n ports, the enable and the controls tied to ground
    assert all(bench.dut.conns[port] is bench.vss for port in ("inn", "outn", "en", "inj", "vbn", "vbp", "vctrl"))


def test_a_differential_line_and_rings_drive_only_their_own_ports() -> None:
    line = sim.testbench(TbParams(params=runs.chain2_coupled()))
    assert set(line.instances) == {"dut", "driver", "load", "vvdd", "vvddbench", "vclockp", "vclockn"}
    assert line.driver.conns["inn"] is line.clockn and line.driver.conns["outn"] is line.inn
    assert line.load.conns["inn"] is line.outn
    coupled = sim.testbench(TbParams(params=runs.ring4_coupled()))
    # the injecting ring's inj tied to ground (no run drives it), its tail-less stages' vctrl too
    assert coupled.dut.conns["inj"] is coupled.vss and coupled.dut.conns["vctrl"] is coupled.vss
    assert coupled.dut.conns["outn"] is coupled.outn
    assert set(coupled.instances) == {"dut", "load", "vvdd", "vvddbench", "ven"}
    tail = sim.testbench(TbParams(params=runs.ring4_tail(), vcont_v=0.6))
    assert set(tail.instances) == {"dut", "load", "vvdd", "vvddbench", "ven", "vvctrl"}
    assert float(tail.vvctrl.of.params.dc) == pytest.approx(0.6)


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"vcont_v": 1.3},  # above the supply
        {"vcont_v": -0.1},
        {"clock_period_s": 100e-12},  # no longer than its two transitions
        {"transition_time_s": 0.0},
        {"enable_delay_s": 40e-9},  # the enable never rises within the transient
        {"waveform_sample_interval_s": 0.0},
        {"stop_time_s": 13e-9},  # a line's run under 3.5 input periods
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)


def test_a_rings_run_is_not_held_to_a_lines_length() -> None:
    assert TbParams(params=runs.ring5(), stop_time_s=13e-9).stop_time_s == 13e-9


def test_every_named_chains_bench_serializes() -> None:
    # a chain that is its own driver (two stages) or load (one) shares its module: hdl21 names a
    # generated module by its parameters and refuses two modules of one name
    for single in (runs.ring5, runs.ring4_coupled, runs.chain4, runs.chain2_coupled, runs.chain4_starved):
        bench = sim.testbench(TbParams(params=single()))
        assert h.to_proto(bench) is not None
    line = sim.testbench(TbParams(params=runs.chain2_coupled()))
    assert line.driver.of is line.dut.of
    assert sim.testbench(TbParams(params=params.Params(stages=1))).load.of is not None
