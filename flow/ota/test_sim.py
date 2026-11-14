"""Software-only checks of the amplifier's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import pytest
from hdl21.primitives import MosType

from . import params, sim
from .params import Bench, Params, TbParams, Topology


def test_a_run_defaults_to_the_bench_every_amplifier_is_characterized_on() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.bench) == ("tsmc65", Params(), Bench.AC)
    assert (
        (tb.cload_f, tb.iss_a, tb.cmfb_gain)
        == (params.LOAD_F, params.ISS_A, params.CMFB_GAIN)
        == (50e-15, 40e-6, 100.0)
    )
    assert (tb.fstart_hz, tb.fstop_hz, tb.points_per_decade) == (1e3, 1e11, 20)
    # the cascodes an eighth of the supply off its middle, the output common mode at it
    assert (tb.vcasn_v, tb.vcasp_v, tb.vout_cm_v) == pytest.approx(
        (params.VCASN * tb.vdd, params.VCASP * tb.vdd, params.VOUT_CM * tb.vdd)
    )
    # the unity-gain benches: one 20 ns step period every 5 ps, ten periods of 10 MHz
    assert tb.single_ended and TbParams(bench=Bench.STEP).stop_s == pytest.approx(20e-9)
    assert tb.waveform_sample_interval_s == params.STROBE_S == 5e-12
    assert TbParams(bench=Bench.SINE).stop_s == pytest.approx(1e-6)


def test_the_small_signal_bench_drives_a_balun_and_biases_from_references() -> None:
    bench = sim.testbench(TbParams(vin_cm_v=0.5))
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Ota")
    # the common mode on both inputs, half the AC stimulus on each with opposite signs
    assert (float(bench.vinp.of.params.dc), float(bench.vinn.of.params.dc)) == pytest.approx((0.5, 0.5))
    assert (float(bench.vinp.of.params.ac), float(bench.vinn.of.params.ac)) == pytest.approx((0.5, -0.5))
    # an NMOS input: the tail's reference carries the bias current, the load's half of it, from a supply of their own
    assert float(bench.ibn.of.params.dc) == pytest.approx(40e-6) and float(bench.ibp.of.params.dc) == pytest.approx(
        20e-6
    )
    assert (
        bench.mbn.conns["d"] is bench.vbn and bench.mbp.conns["s"] is bench.vddb and bench.ibn.conns["p"] is bench.vddb
    )
    # a single-ended amplifier sits open loop: its load bias is the reference's own
    assert bench.mbp.conns["d"] is bench.vbp and not hasattr(bench, "ecmfb")
    assert float(bench.cloadp.of.params.c) == pytest.approx(50e-15) and bench.cloadn.conns["p"] is bench.outn
    # a PMOS input's tail sits on vbp; a folded cascode's top sources carry one and a half bias currents
    pmos = sim.testbench(TbParams(params=Params(input_xtors=MosType.PMOS)))
    assert float(pmos.ibp.of.params.dc) == pytest.approx(40e-6) and float(pmos.ibn.of.params.dc) == pytest.approx(20e-6)
    folded = sim.testbench(TbParams(params=Params(topology=Topology.FOLDED)))
    assert float(folded.ibp.of.params.dc) == pytest.approx(60e-6)


def test_a_differential_output_gets_an_ideal_common_mode_feedback() -> None:
    bench = sim.testbench(TbParams(params=Params(topology=Topology.TELESCOPIC), vout_cm_v=0.55))
    # the outputs' average against the target steers the load bias from the reference's
    assert bench.ecm_p.conns["cp"] is bench.outp and bench.ecm_n.conns["cp"] is bench.outn
    assert bench.ecmfb.conns["p"] is bench.vbp and bench.ecmfb.conns["n"] is bench.vbp_start
    assert bench.mbp.conns["d"] is bench.vbp_start and float(bench.vvocm.of.params.dc) == pytest.approx(0.55)
    assert float(bench.ecmfb.of.params.gain) == pytest.approx(100.0)
    # through a second stage a higher load bias raises the output common mode: the feedback's sign turns
    two_stage = sim.testbench(TbParams(params=Params(topology=Topology.TELESCOPIC, two_stage=True)))
    assert float(two_stage.ecmfb.of.params.gain) == pytest.approx(-100.0)


def test_the_unity_gain_benches_feed_outp_back_and_step_or_swing_inp() -> None:
    step = sim.testbench(TbParams(bench=Bench.STEP, vin_cm_v=0.6, vin_step_v=0.3))
    assert step.vinn.conns == {"p": step.inn, "n": step.outp} and float(step.vinn.of.params.dc) == 0.0
    pulse = step.vinp.of.params
    assert (float(pulse.v1), float(pulse.v2)) == pytest.approx((0.45, 0.75))
    # up a quarter of the period in, down three quarters in
    assert float(pulse.delay) == pytest.approx(5e-9) and float(pulse.width) == pytest.approx(10e-9 - 10e-12)
    sine = sim.testbench(TbParams(bench=Bench.SINE, vin_amplitude_v=0.12)).vinp.of.params
    assert (float(sine.voff), float(sine.vamp), float(sine.freq)) == pytest.approx((0.6, 0.12, 10e6))


def test_a_run_saves_the_ports_it_has_and_the_supply_current() -> None:
    ports = {"inp", "inn", "outp", "outn", "vbn", "vbp", "vcasn", "vcasp"}
    assert set(sim.SAVES) == {f"xtop.{port}" for port in ports} | {"xtop.dut.out1p", "xtop.dut.out1n", "xtop.vvdd:p"}
    # a single-ended amplifier leaves outn floating; only a second stage has first-stage outputs
    assert set(sim._saves(TbParams())) == {f"xtop.{port}" for port in ports - {"outn"}} | {"xtop.vvdd:p"}
    differential = TbParams(params=Params(topology=Topology.TELESCOPIC))
    assert set(sim._saves(differential)) == {f"xtop.{port}" for port in ports} | {"xtop.vvdd:p"}
    two_stage = TbParams(params=Params(topology=Topology.TELESCOPIC, two_stage=True))
    assert set(sim._saves(two_stage)) == set(sim.SAVES)
    assert "xtop.dut.out1p" in sim._saves(TbParams(params=Params(two_stage=True)))
    assert "xtop.dut.out1n" not in sim._saves(TbParams(params=Params(two_stage=True)))


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cload_f": 0.0},
        {"iss_a": -1e-6},
        {"vin_cm_v": 1.3},
        {"vcasn_v": -0.1},
        {"fstart_hz": 1e12},
        {"points_per_decade": 0},
        {"bench": Bench.STEP, "params": Params(topology=Topology.TELESCOPIC)},  # no unity gain of a differential output
        {"bench": Bench.STEP, "vin_cm_v": 0.1},  # the step leaves the rails
        {"bench": Bench.SINE, "vin_amplitude_v": 0.7},
        {"bench": Bench.STEP, "transition_time_s": 6e-9},
        {"bench": Bench.SINE, "sine_periods": 2},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)
