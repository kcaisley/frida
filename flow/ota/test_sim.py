"""Checks of the amplifier's testbench parameters and testbench: software-only (no simulator), and
opt-in Spectre checks (``-m spectre``): the bias network keeps every bench-biased transistor
saturated and the tail at its current, and the unity-gain sine runs at an error below its
harmonics."""

import math
import shutil
from dataclasses import replace
from typing import Any

import hdl21 as h
import numpy as np
import pytest
from hdl21.primitives import MosType

from flow import pipeline

from . import params, runs, sim
from .analysis import analyze_ac, analyze_distortion
from .params import Bench, Params, TbParams, Topology


def test_a_run_defaults_to_the_bench_every_amplifier_is_characterized_on() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.bench, tb.vin_cm_v) == ("tsmc65", Params(), Bench.AC, None)
    assert (
        (tb.cload_f, tb.iss_a, tb.cmfb_gain)
        == (params.LOAD_F, params.ISS_A, params.CMFB_GAIN)
        == (50e-15, 40e-6, 100.0)
    )
    assert (tb.fstart_hz, tb.fstop_hz, tb.points_per_decade) == (1e3, 1e11, 20)
    # the common-mode sweep from rail to rail; the unity-gain benches: one 20 ns step period every
    # 5 ps, ten periods of 10 MHz
    assert (params.CM_SWEEP[0], params.CM_SWEEP[-1], len(params.CM_SWEEP)) == (0.0, 1.0, 13)
    assert tb.single_ended and TbParams(bench=Bench.STEP).stop_s == pytest.approx(20e-9)
    assert tb.waveform_sample_interval_s == params.STROBE_S == 5e-12
    assert TbParams(bench=Bench.SINE).stop_s == pytest.approx(1e-6)


def test_the_small_signal_bench_drives_a_balun_and_biases_from_the_network() -> None:
    bench = sim.testbench(TbParams())
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Ota")
    # at the nominal point the balun rides on the network's input common mode, half the AC
    # stimulus on each input with opposite signs; at a swept one it stands on ground
    assert bench.vinp.conns["n"] is bench.vcm and bench.vinn.conns["n"] is bench.vcm
    assert (float(bench.vinp.of.params.dc), float(bench.vinn.of.params.dc)) == (0.0, 0.0)
    assert (float(bench.vinp.of.params.ac), float(bench.vinn.of.params.ac)) == pytest.approx((0.5, -0.5))
    swept = sim.testbench(TbParams(vin_cm_v=0.5))
    assert swept.vinp.conns["n"] is swept.vss and float(swept.vinp.of.params.dc) == pytest.approx(0.5)
    # an NMOS input: the tail's reference current into a replica of the pair on a copy of the tail,
    # from the network's own supply; the tail's gate on the replica's drains
    assert float(bench.itail.of.params.dc) == pytest.approx(40e-6) and bench.itail.conns["p"] is bench.vddb
    assert bench.Mtail_in_p.conns["d"] is bench.vbn and bench.Mtail_in_p.conns["g"] is bench.vcm
    assert bench.Mtail_tail.conns["g"] is bench.vbn and bench.dut.conns["vbn"] is bench.vbn
    # a five-transistor amplifier leaves its load bias and cascodes unused (on ground), and its outn
    # floating: on ground, no load capacitor
    assert all(bench.dut.conns[name] is bench.vss for name in ("vbp", "vcasn", "vcasp", "outn"))
    assert float(bench.cloadp.of.params.c) == pytest.approx(50e-15) and not hasattr(bench, "cloadn")
    assert not hasattr(bench, "ecmfb")
    # a PMOS input's tail sits on vbp, its reference drawn into ground
    pmos = sim.testbench(TbParams(params=Params(input_xtors=MosType.PMOS)))
    assert pmos.dut.conns["vbp"] is pmos.vbp and pmos.itail.conns["n"] is pmos.vss
    # the self-biased amplifier biases itself: the bench holds its inputs at mid-supply alone
    own = sim.testbench(TbParams(params=Params(topology=Topology.SELF_BIASED)))
    assert float(own.ecm.of.params.gain) == pytest.approx(0.5) and not hasattr(own, "itail")


def test_a_differential_output_gets_an_ideal_common_mode_feedback() -> None:
    bench = sim.testbench(TbParams(params=Params(topology=Topology.TELESCOPIC)))
    # the outputs' average against the target steers the load bias from the network's
    assert bench.ecm_p.conns["cp"] is bench.outp and bench.ecm_n.conns["cp"] is bench.outn
    assert bench.ecmfb.conns["p"] is bench.vbp_free and bench.ecmfb.conns["n"] is bench.vbp_copy
    assert bench.evbp_copy.conns["cp"] is bench.Mload.conns["g"]
    # vbp the sum held between the rails: the feedback saturates there as a real one would
    clamp = bench.ecmfb_clamp
    assert clamp.conns["p"] is bench.vbp and clamp.conns["ps"] is bench.vbp_free
    assert (clamp.of.params.min, clamp.of.params.max) == (0.0, 1.2)
    assert bench.ecmfb.conns["cn"] is bench.evocm.conns["p"] and float(bench.ecmfb.of.params.gain) == pytest.approx(
        100.0
    )
    # the cascodes from diode copies on the network's drain levels, a load capacitor on each output
    assert bench.dut.conns["vcasn"] is bench.vcasn and bench.Mcas_in.conns["d"] is bench.vcasn
    assert bench.dut.conns["vcasp"] is bench.vcasp and bench.Mcas_load.conns["d"] is bench.vcasp
    assert bench.cloadn.conns["p"] is bench.outn
    # through a second stage a higher load bias raises the output common mode: the feedback's sign
    # turns, its target mid-supply
    two_stage = sim.testbench(TbParams(params=Params(topology=Topology.TELESCOPIC, two_stage=True)))
    assert float(two_stage.ecmfb.of.params.gain) == pytest.approx(-100.0)
    assert float(two_stage.evocm.of.params.gain) == pytest.approx(0.5)
    # a folded cascode's top sources' copy carries the fold's half tail current besides
    folded = sim.testbench(TbParams(params=Params(topology=Topology.FOLDED)))
    assert float(folded.iload_drawn.of.params.dc) == pytest.approx(20e-6)
    assert float(folded.iload.of.params.dc) == pytest.approx(40e-6)


def test_the_unity_gain_benches_feed_outp_back_and_step_or_swing_inp() -> None:
    step = sim.testbench(TbParams(bench=Bench.STEP, vin_step_v=0.2))
    assert step.vinn.conns == {"p": step.inn, "n": step.outp} and float(step.vinn.of.params.dc) == 0.0
    # an NMOS input steps up from the nominal input common mode and back, a quarter of the period in
    # and three quarters in
    pulse = step.vinp.of.params
    assert step.vinp.conns["n"] is step.vcm and (float(pulse.v1), float(pulse.v2)) == pytest.approx((0.0, 0.2))
    assert float(pulse.delay) == pytest.approx(5e-9) and float(pulse.width) == pytest.approx(10e-9 - 10e-12)
    # a PMOS input steps up to it, the self-biased amplifier about it
    pmos = sim.testbench(TbParams(params=Params(input_xtors=MosType.PMOS), bench=Bench.STEP, vin_step_v=0.2))
    assert (float(pmos.vinp.of.params.v1), float(pmos.vinp.of.params.v2)) == pytest.approx((-0.2, 0.0))
    own = TbParams(params=Params(topology=Topology.SELF_BIASED), bench=Bench.STEP, vin_step_v=0.2)
    assert (float(sim.testbench(own).vinp.of.params.v1), own.vin_low_offset_v) == pytest.approx((-0.1, -0.1))
    sine = sim.testbench(TbParams(bench=Bench.SINE, vin_amplitude_v=0.06)).vinp.of.params
    assert (float(sine.voff), float(sine.vamp), float(sine.freq)) == pytest.approx((0.06, 0.06, 10e6))


def test_a_run_saves_the_ports_it_has_and_the_supply_current() -> None:
    ports = {"inp", "inn", "outp", "outn", "vbn", "vbp", "vcasn", "vcasp"}
    assert set(sim.SAVES) == {f"xtop.{port}" for port in ports} | {"xtop.dut.out1p", "xtop.dut.out1n", "xtop.vvdd:p"}
    # a single-ended amplifier leaves outn floating, a five-transistor one its load bias and
    # cascodes unused; only a second stage has first-stage outputs. The small-signal run saves each
    # transistor's V_DS and V_D,sat and the tail's current, a transient none.
    devices = {
        f"xtop.dut.{device}:{value}"
        for device in ("Mtail", "Min_p", "Min_n", "Mload_d", "Mload")
        for value in sim.DEVICE_SAVES
    }
    expected = {"xtop.inp", "xtop.inn", "xtop.outp", "xtop.vbn", "xtop.vvdd:p"} | devices | {"xtop.dut.Mtail:ids"}
    assert set(sim._saves(TbParams())) == expected
    assert set(sim._saves(TbParams(bench=Bench.STEP))) == {
        "xtop.inp",
        "xtop.inn",
        "xtop.outp",
        "xtop.vbn",
        "xtop.vvdd:p",
    }
    differential = sim._saves(TbParams(params=Params(topology=Topology.TELESCOPIC)))
    assert {f"xtop.{port}" for port in ports} | {"xtop.vvdd:p"} <= set(differential)
    two_stage = TbParams(params=Params(topology=Topology.TELESCOPIC, two_stage=True))
    assert set(sim.SAVES) <= set(sim._saves(two_stage))
    own = set(sim._saves(TbParams(params=Params(topology=Topology.SELF_BIASED))))
    assert {"xtop.dut.Mtail_n:ids", "xtop.dut.Mtail_p:ids"} <= own and "xtop.vbn" not in own


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cload_f": 0.0},
        {"iss_a": -1e-6},
        {"vin_cm_v": 1.3},
        {"vin_amplitude_v": -0.1},
        {"fstart_hz": 1e12},
        {"points_per_decade": 0},
        {"bench": Bench.STEP, "params": Params(topology=Topology.TELESCOPIC)},  # no unity gain of a differential output
        {"bench": Bench.STEP, "vin_cm_v": 0.6},  # the stimulus starts from the nominal input common mode
        {"bench": Bench.STEP, "transition_time_s": 6e-9},
        {"bench": Bench.SINE, "sine_periods": 2},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)


@pytest.fixture(scope="module")
def tsmc65() -> None:
    """Skip without Spectre or the TSMC65 kit."""
    if shutil.which("spectre") is None:
        pytest.skip("Spectre binary is not on PATH; source the Cadence environment")
    pytest.importorskip("pdk.tsmc65.hdl21")


# The bias network on every named design in TSMC65, at the nominal input common mode and at 90, 100
# and 110 % of the supply ([Razavi-Analog] Example 2.2, p. 18: a device is saturated while V_DS >=
# V_D,sat): every bench-biased transistor saturated, and the tail at its reference current to 2 %
# (the replica of Example 5.6, Fig. 5.20(b), p. 145: the reference at the tail's V_DS). The
# exception is the two-stage amplifier at 90 %: its second stage pins its first stage's output a
# V_GS below the supply, under the input cascodes' saturation; that design's limit, not the bench's.
@pytest.mark.spectre
def test_the_bias_network_keeps_every_source_saturated(tsmc65, tmp_path) -> None:
    for name, design in pipeline.singles(runs).items():
        nominal = runs.testbenches("tsmc65", design())
        for run in ("nominal", "supply_90", "supply_110"):
            tb = nominal[run]
            raw = sim.simulate(tb, tmp_path / name / run)
            result = analyze_ac([pipeline.read(raw, tb)])
            margin = float(result.saturation_margin_v[0])
            assert margin < 0 if (name, run) == ("two_stage", "supply_90") else margin >= 0, (name, run, margin)
            if tb.params.topology is not Topology.SELF_BIASED:
                assert float(result.iss_a[0]) == pytest.approx(tb.iss_a, rel=2e-2), (name, run)


# A differential amplifier's figures do not move with the bench's feedback gain (100 and 1000): its
# gain and bandwidth hold, and it reports no rejections (a symmetric output's, perfect without
# mismatch).
@pytest.mark.spectre
def test_a_differential_amplifier_does_not_depend_on_the_feedback_gain(tsmc65, tmp_path) -> None:
    tb = runs.testbenches("tsmc65", runs.telescopic())["nominal"]
    found = [
        analyze_ac([pipeline.read(sim.simulate(replace(tb, cmfb_gain=gain), tmp_path / str(gain)), tb)])
        for gain in (100.0, 1000.0)
    ]
    assert found[0].gain_dc_db[0] == pytest.approx(found[1].gain_dc_db[0], abs=0.05)
    assert found[0].unity_gain_bandwidth_hz[0] == pytest.approx(found[1].unity_gain_bandwidth_hz[0], rel=1e-2)
    assert all(math.isnan(result.psrr_dc_db[0]) and math.isnan(result.cmrr_dc_db[0]) for result in found)


# The unity-gain sine runs in Spectre at conservative error control, its step bounded to the strobe
# interval: the log carries no Spectre X notice that maxstep is disabled (SPECTRE-592), and the
# five-transistor buffer's harmonics past the third, which a looser error would set, lie more than
# 95 dB below the input.
@pytest.mark.spectre
def test_the_unity_gain_sine_is_simulated_at_conservative_error_control(tsmc65, tmp_path) -> None:
    tb = runs.testbenches("tsmc65", runs.five_t())["sine"]
    raw = sim.simulate(tb, tmp_path)
    assert "SPECTRE-592" not in (tmp_path / "spectre.log").read_text(errors="replace")
    distortion = analyze_distortion([pipeline.read(raw, tb)])
    tone = float(distortion.vin_frequency_hz[0])
    for order in range(4, params.SPECTRUM_HARMONICS + 1):
        index = int(np.argmin(np.abs(distortion.frequency_hz - order * tone)))
        assert distortion.spectrum_db[0][index] < -95.0, order
