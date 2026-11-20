"""Software-only checks of the sampler's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import pytest

from flow.circuit import spectre

from . import params, sim
from .params import Stimulus, TbParams


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
    assert float(bench.vvin.of.params.dc) == pytest.approx(0.7)
    # with a step: low for a period, high for the next, each change in mid-hold
    stepped = sim.testbench(TbParams()).vvin.of.params
    assert (float(stepped.v1), float(stepped.v2)) == pytest.approx((0.55, 0.65))
    assert float(stepped.delay) == pytest.approx(7.5e-9) and float(stepped.period) == pytest.approx(20e-9)


def test_a_track_step_adds_a_second_source_stepping_in_mid_track() -> None:
    """With a track step the input is two pulse sources in series: the one stepping in mid-hold on
    top of one stepping in mid-track, low until the clock's high time is half over (the 50 ps edge
    and 2.5 ns of the 5 ns: its own 50 ps edge centred there, so starting at 2.525 ns), then high
    for a period less its edge. With both steps 10 mV about 0.6 V the input is 0.59 V until
    mid-track, 0.6 V until mid-hold, 0.61 V until the next mid-track."""
    bench = sim.testbench(TbParams(input_voltage=0.6, input_step_v=0.01, track_step_v=0.01))
    hold, track = bench.vvin.of.params, bench.vvstep.of.params
    assert bench.vvin.conns["n"] is bench.vstep and bench.vvstep.conns["p"] is bench.vstep
    assert (float(hold.v1), float(hold.v2)) == pytest.approx((0.595, 0.605))
    assert (float(track.v1), float(track.v2)) == pytest.approx((-0.005, 0.005))
    assert float(track.delay) == pytest.approx(2.525e-9) and float(track.period) == pytest.approx(20e-9)
    assert float(track.width) == pytest.approx(10e-9 - 50e-12)
    assert not hasattr(sim.testbench(TbParams()), "vvstep")


def test_a_track_step_comes_where_the_run_puts_it_inside_the_high_time() -> None:
    """The level runs' step, 15 ns into a 20 ns high time of a 25 ns clock: its 50 ps edge centred
    15 ns after the high time starts (itself an edge after the run starts), so starting at
    50 ps / 2 + 15 ns = 15.025 ns and over at 15.075 ns, 4.975 ns before the high time (50 ps to
    20.05 ns) ends. A step half an edge from either end of the high time is inside it; one at or past
    either end is refused."""
    tb = TbParams(
        input_step_v=0.01, track_step_v=0.01, track_step_s=15e-9, clock_period_s=25e-9, clock_high_time_s=20e-9
    )
    track = sim.testbench(tb).vvstep.of.params
    assert float(track.delay) == pytest.approx(15.025e-9) and float(track.period) == pytest.approx(50e-9)
    assert float(track.delay) + float(track.rise) / 2 == pytest.approx(50e-12 + 15e-9)
    for inside in (25e-12, 20e-9 - 25e-12):
        assert TbParams(track_step_s=inside, clock_period_s=25e-9, clock_high_time_s=20e-9).track_step_s == inside
    for outside in (0.0, 20e-9, 21e-9):
        with pytest.raises(ValueError, match="inside the clock's high time"):
            TbParams(track_step_s=outside, clock_period_s=25e-9, clock_high_time_s=20e-9)


def test_an_input_transition_time_slows_the_hold_step_about_mid_hold() -> None:
    """A full-scale step over 63.66 ns in the 87.5 ns hold of a 100 ns period: it starts half its
    length less half a clock edge before the plain step would (56.25 ns - 31.83 ns + 25 ps), so its
    middle stays where the plain step's is, and the next one starts a period later (rise and width
    make a period). The plain step: a 50 ps edge from 7.5 ns, high for 10 ns - 50 ps. The clock is
    low for T - t_high - 2 t_edge and the change is centred half an edge before its middle, so it
    fits up to T - t_high - 3 t_edge: 4.85 ns of the plain 10 ns clock, no more."""
    tb = TbParams(input_step_v=0.94, input_transition_time_s=63.66e-9, clock_period_s=100e-9, clock_high_time_s=12.5e-9)
    step = sim.testbench(tb).vvin.of.params
    assert float(step.rise) == float(step.fall) == pytest.approx(63.66e-9)
    assert float(step.delay) == pytest.approx(56.25e-9 - 31.83e-9 + 25e-12)
    assert float(step.width) + float(step.rise) == pytest.approx(100e-9)
    assert float(step.delay) + float(step.rise) / 2 == pytest.approx(12.5e-9 + 87.5e-9 / 2 + 25e-12)
    plain = sim.testbench(TbParams()).vvin.of.params
    assert (float(plain.rise), float(plain.delay), float(plain.width)) == pytest.approx((50e-12, 7.5e-9, 9.95e-9))
    assert TbParams(input_transition_time_s=4.85e-9).input_transition_time_s == 4.85e-9
    for too_long in (4.9e-9, 6e-9):
        with pytest.raises(ValueError, match="fit the clock's low time"):
            TbParams(input_transition_time_s=too_long)


def test_a_run_saves_the_ports_and_the_supply_and_clock_currents() -> None:
    """The ports, and the current of the supply's and each clock's source (``xtop.v<net>:p``, which
    flow.pipeline.read names ``i[<net>]``)."""
    assert set(sim.SAVES) == {
        "xtop.vin",
        "xtop.vout",
        "xtop.clk",
        "xtop.clk_b",
        "xtop.vvdd:p",
        "xtop.vclk:p",
        "xtop.vclk_b:p",
    }


def test_the_complement_runs_late_by_the_skew() -> None:
    bench = sim.testbench(TbParams(clock_skew_s=50e-12))
    assert float(bench.vclk_b.of.params.delay) == pytest.approx(50e-12)
    assert float(bench.vclk.of.params.delay) == pytest.approx(0.0)


def test_a_sine_drives_the_input() -> None:
    tb = TbParams(stimulus=Stimulus.SINE, input_voltage=0.7, sine_amplitude_v=0.44, sine_frequency_hz=1e6)
    source = sim.testbench(tb).vvin.of.params
    assert (float(source.voff), float(source.vamp), float(source.freq)) == pytest.approx((0.7, 0.44, 1e6))


def test_the_dac_step_drives_half_the_load_by_twice_the_step() -> None:
    """Half the load on a source stepping by 2 s moves the held output by s: -0.6 V from a 1.2 V
    step down, a quarter into the hold (5 ns after the 5 ns track and the two 50 ps edges)."""
    bench = sim.testbench(TbParams(input_step_v=0.0, dac_step_v=-0.6))
    assert float(bench.cload.of.params.c) == float(bench.cdac.of.params.c) == pytest.approx(0.5e-12)
    step = bench.vvdac.of.params
    assert float(step.v2) == pytest.approx(-1.2)
    assert float(step.delay) == pytest.approx(5e-9 + 100e-12 + (10e-9 - 5e-9 - 100e-12) / 4)


@pytest.mark.parametrize("stimulus", list(Stimulus))
def test_every_run_needs_classic_spectre(stimulus: Stimulus, tmp_path) -> None:
    """A run's pedestals, residues and harmonics are small differences or distortion: Spectre X is
    refused for the mark simulate gives (flow.circuit.spectre.refusal)."""
    mark = spectre.Accuracy.DISTORTION if stimulus is Stimulus.SINE else spectre.Accuracy.SMALL_DIFFERENCE
    assert spectre.refusal([], tmp_path, fast=True, args=(), accuracy=mark)
    assert spectre.refusal([], tmp_path, fast=False, args=(), accuracy=mark) is None


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"clock_transition_time_s": float("nan")},
        {"input_voltage": float("inf")},
        {"clock_delay_s": -1e-9},
        {"clock_high_time_s": 20e-9},
        {"periods": 0},
        {"gmin_s": 0.0},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)
