"""Software-only checks of the follower's testbench parameters and testbench (no simulator)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hdl21 as h
import hdl21.sim as hs
import pytest

from . import params, runs, sim
from .params import Stimulus, TbParams


def test_a_run_defaults_to_the_bench_every_follower_is_characterized_on() -> None:
    tb = TbParams(vdd=1.2, vin_v=0.9)
    assert (tb.pdk, tb.params, tb.stimulus) == ("tsmc65", params.Params(), Stimulus.INPUT)
    assert (tb.step_v, tb.dc_step_v) == (0.0, 0.0)
    assert (tb.cload_f, tb.iref_a) == (params.LOAD_F, params.IREF_A)
    assert (tb.fstart_hz, tb.fstop_hz, tb.points_per_decade) == (1e3, 1e11, 20)
    assert (tb.step_period_s, tb.transition_time_s, tb.waveform_sample_interval_s) == (20e-9, 10e-12, 5e-12)


def test_the_testbench_biases_loads_and_drives_the_follower() -> None:
    bench = sim.testbench(TbParams(vdd=1.2, vin_v=0.7, iref_a=30e-6))
    assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Follower")
    assert float(bench.vvin.of.params.dc) == pytest.approx(0.7) and float(bench.vvin.of.params.ac) == 1.0
    assert float(bench.cload.of.params.c) == pytest.approx(100e-15)
    # each bias a diode-connected copy of the current-source device, fed the reference current
    # from a supply of its own
    assert bench.mbn.conns == {"d": bench.vbn, "g": bench.vbn, "s": bench.vss, "b": bench.vss}
    assert bench.mbp.conns == {"d": bench.vbp, "g": bench.vbp, "s": bench.vddb, "b": bench.vddb}
    assert bench.mbn.of.params.w == 8 and bench.mbn.of.params.l == 4
    assert float(bench.ibn.of.params.dc) == pytest.approx(30e-6) and bench.ibn.conns["p"] is bench.vddb
    # the output test current: 0 A from ground into the output, read through xf alone
    assert bench.itest.conns == {"p": bench.vss, "n": bench.vout} and float(bench.itest.of.params.dc) == 0.0


def test_the_step_drives_no_output_test_current() -> None:
    assert not hasattr(sim.testbench(TbParams(stimulus=Stimulus.STEP, vdd=1.2, vin_v=0.9, step_v=0.3)), "itest")


def test_the_step_rises_a_quarter_period_in_and_falls_three_quarters_in() -> None:
    stepped = sim.testbench(TbParams(stimulus=Stimulus.STEP, vdd=1.2, vin_v=0.9, step_v=0.3)).vvin.of.params
    assert (float(stepped.v1), float(stepped.v2)) == pytest.approx((0.75, 1.05))
    assert float(stepped.delay) == pytest.approx(5e-9) and float(stepped.period) == pytest.approx(20e-9)
    assert float(stepped.delay) + float(stepped.rise) + float(stepped.width) == pytest.approx(15e-9)
    # the record runs half a period past the fall, as past the rise
    assert TbParams(stimulus=Stimulus.STEP, vdd=1.2, vin_v=0.9, step_v=0.3).tran_stop_s == pytest.approx(25e-9)


def test_a_run_saves_the_ports_and_the_supply_current() -> None:
    assert set(sim.SAVES) == {"xtop.vin", "xtop.vout", "xtop.vbn", "xtop.vbp", "xtop.vvdd:p"}


def test_the_runs_of_one_instance() -> None:
    """Each input level with the AC on the input; at each level the nominal input may take (2/12
    to 10/12 of the supply) the other supplies, the input held relative to the rail its input
    device's source rides, and the step and its half; the reference current in proportion to the
    current source's width."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    benches = runs.testbenches("tsmc65", runs.scaled.spaces("tsmc65")["flipped_pmos_x2"].base)
    assert len(benches) == 13 + 9 * 4
    assert [name for name in benches if not name.startswith("input_vin_")] == [
        name
        for k in range(2, 11)
        for name in (f"supply_90_vin_{k}", f"supply_110_vin_{k}", f"step_vin_{k}", f"step_half_vin_{k}")
    ]
    vdd = benches["input_vin_12"].vdd
    assert {tb.stimulus for name, tb in benches.items() if not name.startswith("step")} == {Stimulus.INPUT}
    assert benches["input_vin_0"].vin_v == 0.0 and benches["input_vin_12"].vin_v == vdd
    for k in range(2, 11):
        step, half = benches[f"step_vin_{k}"], benches[f"step_half_vin_{k}"]
        assert step.stimulus is Stimulus.STEP and step.vin_v == benches[f"input_vin_{k}"].vin_v
        # a flipped follower's step: an eighth of the supply; its half exactly half of it
        assert step.step_v == pytest.approx(vdd / 8) and half.step_v == step.step_v / 2
        assert half.stimulus is Stimulus.STEP and half.vin_v == step.vin_v
    assert runs.testbenches("tsmc65", runs.source())["step_vin_9"].step_v == pytest.approx(vdd / 4)
    # a PMOS input held at its distance below the supply (0.9 V below 1.2 V at 3/12), an NMOS one
    # at its level
    assert benches["supply_110_vin_3"].vdd == pytest.approx(1.1 * vdd)
    assert benches["supply_110_vin_3"].vin_v == pytest.approx(1.1 * vdd - 0.75 * vdd)
    assert benches["supply_90_vin_3"].vin_v == pytest.approx(0.9 * vdd - 0.75 * vdd)
    source = runs.testbenches("tsmc65", runs.source())
    assert source["supply_90_vin_10"].vin_v == source["supply_110_vin_10"].vin_v == pytest.approx(10 / 12 * vdd)
    assert max(tb.vdd for tb in benches.values()) <= 1.1 * vdd + 1e-9
    assert all(tb.iref_a == pytest.approx(40e-6) for tb in benches.values())
    # the middle level's run alone sweeps the input in DC, by a 480th of the supply
    assert [name for name, tb in benches.items() if tb.dc_step_v] == ["input_vin_6"]
    assert benches["input_vin_6"].dc_step_v == pytest.approx(vdd / 480)
    # the step runs alone step the input
    assert all(name.startswith("step") for name, tb in benches.items() if tb.step_v)


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cload_f": 0.0},
        {"iref_a": -1e-6},
        {"vin_v": 1.3},
        {"fstart_hz": 1e12},
        {"points_per_decade": 0},
        {"dc_step_v": -0.0025},
        {"dc_step_v": 1.2},
        {"stimulus": Stimulus.STEP, "step_v": 0.3, "dc_step_v": 0.0025},
        {"stimulus": Stimulus.STEP, "vin_v": 1.1, "step_v": 0.3},
        {"stimulus": Stimulus.STEP, "step_v": 0.0},
        {"stimulus": Stimulus.STEP, "step_v": -0.3},
        {"step_v": 0.3},
        {"stimulus": Stimulus.STEP, "step_v": 0.3, "transition_time_s": 6e-9},
        {"stimulus": Stimulus.STEP, "step_v": 0.3, "waveform_sample_interval_s": 0.0},
        {"stimulus": Stimulus.STEP, "step_v": 0.3, "waveform_sample_interval_s": 1e-9},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**{"vdd": 1.2, "vin_v": 0.9, **change})


def test_the_transfer_functions_sweep_the_ac_responses_frequencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """xf's limits are written in full, as hs.Ac writes its own, so a start or stop that is not
    round (1234567.89 Hz, which ``:g`` writes as 1.23457e+06) sweeps the same points in both."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    taken: list[Any] = []
    monkeypatch.setattr(sim.spectre, "run", lambda bench, attrs, run_dir: taken.extend(attrs))
    sim.simulate(TbParams(vdd=1.2, vin_v=0.9, fstart_hz=1234567.89, fstop_hz=98765432109.87), tmp_path)
    (ac,) = (attr for attr in taken if isinstance(attr, hs.Ac))
    (xf,) = (attr for attr in taken if isinstance(attr, h.Literal) and attr.text.startswith("xf "))
    written = dict(field.split("=") for field in xf.text.split() if "=" in field)
    swept = (float(ac.sweep.start), float(ac.sweep.stop))
    assert (float(written["start"]), float(written["stop"])) == swept == (1234567.89, 98765432109.87)


def test_a_run_sweeps_its_input_in_dc_where_it_asks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The input's DC sweep (``dc``) from ground to the supply by ``dc_step_v``, in that run alone."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    for step, expected in ((0.0, []), (0.0025, ["dc dc dev=xtop.vvin param=dc start=0 stop=1.2 step=0.0025"])):
        taken: list[Any] = []
        monkeypatch.setattr(sim.spectre, "run", lambda bench, attrs, run_dir, into=taken: into.extend(attrs))
        sim.simulate(TbParams(vdd=1.2, vin_v=0.9, dc_step_v=step), tmp_path)
        assert [attr.text for attr in taken if isinstance(attr, h.Literal) and attr.text.startswith("dc ")] == expected


def test_the_step_is_written_at_its_strobes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The step's transient is written at its strobes alone, every waveform_sample_interval_s; no
    maxstep, which Spectre X disables (SPECTRE-592)."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    taken: list[Any] = []
    monkeypatch.setattr(sim.spectre, "run", lambda bench, attrs, run_dir: taken.extend(attrs))
    sim.simulate(TbParams(stimulus=Stimulus.STEP, vdd=1.2, vin_v=0.9, step_v=0.3), tmp_path)
    (tran,) = (attr for attr in taken if isinstance(attr, hs.Tran))
    assert set(tran.options) == {"strobeperiod", "strobeoutput"}
    assert float(tran.options["strobeperiod"]) == 5e-12 and tran.options["strobeoutput"].text == "strobeonly"


def test_the_half_step_is_half_the_step_in_a_09_v_kit(monkeypatch: pytest.MonkeyPatch) -> None:
    """In a 0.9 V kit a flipped follower's step is an eighth of the supply, 0.1125 V; its half is
    0.05625 V exactly, the step divided by two, not the half step rounded on its own (0.0563)."""
    kit = SimpleNamespace(install=SimpleNamespace(supply_voltage=lambda corner: 0.9))
    monkeypatch.setattr(runs.importlib, "import_module", lambda name: kit)
    benches = runs.testbenches("tsmc28", runs.flipped())
    assert benches["step_vin_6"].step_v == 0.1125 and benches["step_half_vin_6"].step_v == 0.05625
