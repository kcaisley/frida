"""Software-only checks of the follower's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import pytest

from . import params, runs, sim
from .params import Stimulus, TbParams


def test_a_run_defaults_to_the_bench_every_follower_is_characterized_on() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.stimulus) == ("tsmc65", params.Params(), Stimulus.INPUT)
    assert (tb.cload_f, tb.iref_a, tb.test_resistance_ohm) == (params.LOAD_F, params.IREF_A, params.TEST_OHM)
    assert (tb.fstart_hz, tb.fstop_hz, tb.points_per_decade) == (1e3, 1e11, 20)
    assert (tb.step_period_s, tb.transition_time_s, tb.waveform_sample_interval_s) == (20e-9, 10e-12, 5e-12)


def test_the_testbench_biases_loads_and_drives_the_follower() -> None:
    bench = sim.testbench(TbParams(vin_v=0.7, iref_a=30e-6))
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Follower")
    assert float(bench.vvin.of.params.dc) == pytest.approx(0.7) and float(bench.vvin.of.params.ac) == 1.0
    assert float(bench.cload.of.params.c) == pytest.approx(100e-15)
    # each bias a diode-connected copy of the current-source device, fed the reference current
    # from a supply of its own
    assert bench.mbn.conns == {"d": bench.vbn, "g": bench.vbn, "s": bench.vss, "b": bench.vss}
    assert bench.mbp.conns == {"d": bench.vbp, "g": bench.vbp, "s": bench.vddb, "b": bench.vddb}
    assert bench.mbn.of.params.w == 8 and bench.mbn.of.params.l == 4
    assert float(bench.ibn.of.params.dc) == pytest.approx(30e-6) and bench.ibn.conns["p"] is bench.vddb
    assert not hasattr(bench, "vtest")


def test_the_output_stimulus_is_a_test_current_into_the_output() -> None:
    bench = sim.testbench(TbParams(stimulus=Stimulus.OUTPUT))
    assert float(bench.vvin.of.params.ac) == 0.0 and float(bench.vtest.of.params.ac) == 1.0
    assert bench.ctest.conns == {"p": bench.test, "n": bench.test_dc}
    assert bench.rtest.conns == {"p": bench.test_dc, "n": bench.vout}
    assert float(bench.rtest.of.params.r) == pytest.approx(1e6)


def test_the_step_rises_a_quarter_period_in_and_falls_three_quarters_in() -> None:
    stepped = sim.testbench(TbParams(stimulus=Stimulus.STEP, vin_v=0.9, step_v=0.3)).vvin.of.params
    assert (float(stepped.v1), float(stepped.v2)) == pytest.approx((0.75, 1.05))
    assert float(stepped.delay) == pytest.approx(5e-9) and float(stepped.period) == pytest.approx(20e-9)
    assert float(stepped.delay) + float(stepped.rise) + float(stepped.width) == pytest.approx(15e-9)


def test_a_run_saves_the_ports_and_the_supply_current() -> None:
    assert set(sim.SAVES) == {"xtop.vin", "xtop.vout", "xtop.vbn", "xtop.vbp", "xtop.vvdd:p"}


def test_the_runs_of_one_instance() -> None:
    """Each input level with the AC on the input and on the output, the other supplies and the
    step at the nominal input, the reference current in proportion to the current source's width."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    benches = runs.testbenches("tsmc65", runs.scaled.spaces("tsmc65")["flipped_pmos_x2"].base)
    assert len(benches) == 29
    assert [name for name in benches if not name.startswith(("input_vin_", "output_vin_"))] == [
        "supply_90",
        "supply_110",
        "step",
    ]
    vdd = benches["step"].vdd
    assert {tb.stimulus for name, tb in benches.items() if name.startswith("output")} == {Stimulus.OUTPUT}
    assert benches["input_vin_0"].vin_v == 0.0 and benches["output_vin_12"].vin_v == vdd
    # a PMOS flipped follower's nominal input: a quarter of the supply
    assert benches["step"].stimulus is Stimulus.STEP and benches["step"].vin_v == pytest.approx(vdd / 4)
    assert benches["step"].step_v == pytest.approx(vdd / 4)
    assert benches["supply_110"].vdd == pytest.approx(1.1 * vdd)
    assert benches["supply_110"].vin_v == pytest.approx(1.1 * vdd / 4)
    assert max(tb.vdd for tb in benches.values()) <= 1.1 * vdd + 1e-9
    assert all(tb.iref_a == pytest.approx(40e-6) for tb in benches.values())


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cload_f": 0.0},
        {"iref_a": -1e-6},
        {"vin_v": 1.3},
        {"fstart_hz": 1e12},
        {"points_per_decade": 0},
        {"stimulus": Stimulus.STEP, "vin_v": 1.1, "step_v": 0.3},
        {"stimulus": Stimulus.STEP, "step_v": 0.0},
        {"stimulus": Stimulus.STEP, "transition_time_s": 6e-9},
        {"stimulus": Stimulus.STEP, "waveform_sample_interval_s": 0.0},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)
