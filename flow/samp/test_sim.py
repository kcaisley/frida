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
