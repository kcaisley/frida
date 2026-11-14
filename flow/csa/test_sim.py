"""Software-only checks of the amplifier's testbench parameters and testbench (no simulator)."""

from dataclasses import replace
from typing import Any

import hdl21 as h
import pytest
from hdl21.primitives import MosType

from . import params, runs, sim
from .params import Feedback, Stimulus, TbParams


def test_a_run_defaults_to_the_bench_every_amplifier_is_characterized_on() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.stimulus, tb.charge_c) == ("tsmc65", params.Params(), Stimulus.CHARGE, 0.5e-15)
    assert (tb.cdet_f, tb.cinj_f, tb.cload_f) == (100e-15, 1e-15, 10e-15)
    assert (tb.iref_a, tb.ifb_a, tb.vds_in_v, tb.bypass_f) == (4e-6, 10e-9, 0.15, 1e-3)
    assert (tb.reset_time_s, tb.inject_time_s, tb.stop_time_s) == (10e-9, 60e-9, 500e-9)
    assert (tb.fstart_hz, tb.fstop_hz, tb.points_per_decade) == (1.0, 1e12, 50)


def test_the_charge_moves_the_output_away_from_the_input_rail() -> None:
    """Electrons into an NMOS input, holes into a PMOS one: the injection step's sign."""
    assert TbParams(charge_c=1e-15).injection_step_v == pytest.approx(-1.0)
    assert TbParams(params=runs.krum_pmos(), charge_c=1e-15).injection_step_v == pytest.approx(1.0)
    step = sim.testbench(TbParams(charge_c=0.25e-15)).vinj.of.params
    assert float(step.v2) == pytest.approx(-0.25) and float(step.delay) == pytest.approx(60e-9)


def test_the_testbench_loads_and_biases_the_amplifier() -> None:
    bench = sim.testbench(TbParams())
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Csa")
    assert bench.cinj.conns == {"p": bench.inj, "n": bench.inp}
    assert bench.cdet.conns == {"p": bench.inp, "n": bench.vss} and float(bench.cdet.of.params.c) == 100e-15
    assert bench.cload.conns == {"p": bench.out, "n": bench.vss}
    # each bias a diode-connected copy of its device, fed from a supply of its own
    assert bench.mload.conns == {"d": bench.vload, "g": bench.vload, "s": bench.vddb, "b": bench.vddb}
    assert bench.mload.of.params.tp == MosType.PMOS and float(bench.iload.of.params.dc) == 4e-6
    # the cascode's copy stands the drain-source voltage off the input's rail
    assert bench.mcas.conns["s"] is bench.vcas_source and float(bench.vvcas_source.of.params.dc) == 0.15
    # the Krummenacher tail twice the discharge current
    assert bench.mtail.conns["d"] is bench.vfb and float(bench.itail.of.params.dc) == pytest.approx(20e-9)


# The continuous feedback's gate stands on the input's level at rest, which a copy of the amplifier's
# core sets: a copy of the load (gate vload, source on the reference supply), of the cascode (gate
# vcas) and of the input device, its gate tied to the copy's output, as the feedback device ties the
# amplifier's input to its output at rest. No current source feeds that node.
def test_the_continuous_feedback_stands_on_a_copy_of_the_amplifier_s_core() -> None:
    bench = sim.testbench(TbParams(params=runs.continuous()))
    dut = bench.dut.of
    assert bench.mload_rest.conns == {"d": bench.vin_rest, "g": bench.vload, "s": bench.vddb, "b": bench.vddb}
    assert bench.mcas_rest.conns == {"d": bench.vin_rest, "g": bench.vcas, "s": bench.x_rest, "b": bench.vss}
    assert bench.min_rest.conns == {"d": bench.x_rest, "g": bench.vin_rest, "s": bench.vss, "b": bench.vss}
    for copy, device in ((bench.mload_rest, dut.Mload), (bench.mcas_rest, dut.Mcas), (bench.min_rest, dut.Min)):
        assert (copy.of.params.tp, copy.of.params.w, copy.of.params.l) == (
            device.of.params.tp,
            device.of.params.w,
            device.of.params.l,
        )
    assert not hasattr(bench, "iin")
    assert bench.mfb.conns == {"d": bench.vfb, "g": bench.vfb, "s": bench.vin_rest, "b": bench.vss}
    assert float(bench.ifb.of.params.dc) == pytest.approx(10e-9)
    pmos = sim.testbench(TbParams(params=replace(runs.continuous(), input_xtors=MosType.PMOS), charge_c=0.5e-15))
    assert pmos.mload_rest.conns == {"d": pmos.vin_rest, "g": pmos.vload, "s": pmos.vss, "b": pmos.vss}
    assert pmos.min_rest.conns == {"d": pmos.x_rest, "g": pmos.vin_rest, "s": pmos.vddb, "b": pmos.vddb}


# Every bias gate (vload, vcas and vfb but for the reset's switch) is held to its reference device's
# rail by bypass_f, so its reference device's noise is shunted and the output noise is the
# amplifier's ([Razavi-Analog] Sec. 7.5, p. 254); the reset's vfb is its pulse source alone.
@pytest.mark.parametrize("case", ("krum", "krum_pmos", "continuous"))
def test_every_bias_gate_is_bypassed_to_its_rail(case: str) -> None:
    bench = sim.testbench(TbParams(params=getattr(runs, case)()))
    nmos_input = bench.dut.of.Min.of.params.tp == MosType.NMOS
    n_rail, p_rail = bench.vss, bench.vddb
    rails = {"cvload": p_rail if nmos_input else n_rail, "cvcas": n_rail if nmos_input else p_rail}
    rails["cvfb"] = (p_rail if nmos_input else n_rail) if case != "continuous" else n_rail
    for name, rail in rails.items():
        bypass = getattr(bench, name)
        assert bypass.conns == {"p": getattr(bench, name[1:]), "n": rail}, name
        assert float(bypass.of.params.c) == params.BYPASS_F
    assert not hasattr(sim.testbench(TbParams(params=runs.reset())), "cvfb")


def test_the_reset_opens_before_the_charge() -> None:
    reset = sim.testbench(TbParams(params=runs.reset())).vvfb.of.params
    assert (float(reset.v1), float(reset.v2), float(reset.delay)) == pytest.approx((1.2, 0.0, 10e-9))


def test_the_noise_run_has_no_charge() -> None:
    bench = sim.testbench(TbParams(stimulus=Stimulus.NOISE, charge_c=0.0))
    assert float(bench.vinj.of.params.dc) == 0.0


def test_a_run_saves_the_ports_and_the_supply_current() -> None:
    assert set(sim.SAVES) == {"xtop.inp", "xtop.out", "xtop.vload", "xtop.vcas", "xtop.vref", "xtop.vfb", "xtop.vvdd:p"}


def test_the_runs_of_one_instance() -> None:
    """Each charge and the noise at the PDK's supply, the smallest charge and the noise at the
    other supplies; a reset amplifier without noise runs."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    benches = runs.testbenches("tsmc65", runs.krum())
    assert list(benches) == [
        *("q250", "q500", "q1000", "q2000", "noise"),
        *("supply_90", "supply_90_noise", "supply_110", "supply_110_noise"),
    ]
    vdd = benches["q250"].vdd
    assert [benches[f"q{q}"].charge_c for q in (250, 500, 1000, 2000)] == list(params.CHARGES_C)
    assert benches["noise"].stimulus is Stimulus.NOISE and benches["noise"].charge_c == 0.0
    assert benches["supply_110"].vdd == pytest.approx(1.1 * vdd) and benches["supply_110"].charge_c == 0.25e-15
    assert benches["supply_90_noise"].vref_v == pytest.approx(0.45 * 0.9 * vdd)
    assert max(tb.vdd for tb in benches.values()) <= 1.1 * vdd + 1e-9
    reset = runs.testbenches("tsmc65", runs.reset())
    assert list(reset) == ["q250", "q500", "q1000", "q2000", "supply_90", "supply_110"]


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cinj_f": 0.0},
        {"cdet_f": -1e-15},
        {"iref_a": -1e-6},
        {"bypass_f": 0.0},
        {"vds_in_v": 1.3},
        {"vref_v": 1.3},
        {"reset_time_s": 70e-9},
        {"waveform_sample_interval_s": 0.0},
        {"fstart_hz": 1e13},
        {"points_per_decade": 0},
        {"charge_c": 0.0},
        {"stimulus": Stimulus.NOISE},
        {"stimulus": Stimulus.NOISE, "charge_c": 0.0, "params": params.Params(feedback=Feedback.RESET)},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)
