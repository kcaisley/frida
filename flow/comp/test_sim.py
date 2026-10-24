"""Software-only checks of the comparator's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import numpy as np
import pytest

from . import params, sim
from .params import TbParams


def test_a_run_defaults_to_the_clock_every_comparator_is_tested_at() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.conversions) == ("tsmc65", params.Params(), 1)
    assert (tb.input_order, tb.noise) == ("blocked", False)
    assert (tb.reset_time_s, tb.evaluation_time_s) == (params.RESET_S, params.EVALUATION_S) == (1e-9, 4e-9)
    assert tb.cycle_s == pytest.approx(5e-9)
    # Spectre's output every 2 ps, its step no longer
    assert tb.waveform_sample_interval_s == params.STROBE_S == 2e-12


def test_the_testbench_consumes_an_explicit_sweep() -> None:
    tb = TbParams(vin_diff_values_v=(-1e-3, 0.0, 1e-3), conversions=2)
    bench = sim.testbench(tb)

    assert isinstance(bench, h.Module)
    assert bench.dut.of.name.startswith("Comp")
    assert len(bench.vvin_diff.of.params.wave.points) == 6
    assert tb.stop_s == pytest.approx(6 * tb.cycle_s)
    assert np.allclose(tb.decision_time_s, tb.trial_start_s + tb.cycle_s - 2 * tb.transition_time_s)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"vin_diff_values_v": (0.0, 0.0)}, "unique"),
        ({"input_order": "sorted"}, "order"),
        ({"conversions": 0}, "positive"),
        ({"evaluation_time_s": 10e-12}, "shorter"),
    ],
)
def test_a_run_rejects_an_impossible_schedule(change: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        TbParams(**change)


def test_a_shuffled_sweep_steps_through_every_input_each_pass() -> None:
    inputs = (-1e-3, 0.0, 1e-3, 2e-3)
    blocked = TbParams(vin_diff_values_v=inputs, conversions=3).trial_point
    assert blocked.tolist() == np.repeat(np.arange(4), 3).tolist()
    tb = TbParams(vin_diff_values_v=inputs, conversions=3, input_order="shuffled")
    shuffled = tb.trial_point
    # each pass a permutation of the inputs, the passes in different orders, the same every time
    assert all(sorted(shuffled[i : i + 4]) == [0, 1, 2, 3] for i in range(0, 12, 4))
    assert len({tuple(shuffled[i : i + 4]) for i in range(0, 12, 4)}) > 1
    assert np.array_equal(shuffled, tb.trial_point)
    # the testbench's input steps every cycle where the input changes
    levels = [float(value) for _, value in sim.testbench(tb).vvin_diff.of.params.wave.points[::2]]
    assert levels[:4] == [inputs[point] for point in shuffled[:4]]


def test_a_run_saves_the_ports_the_saved_internal_nets_and_the_supply_current() -> None:
    assert {"xtop.clk", "xtop.inp", "xtop.inn", "xtop.outp", "xtop.outn"} <= set(sim.SAVES)
    assert {"xtop.dut.latch_p", "xtop.dut.latch_n"} <= set(sim.SAVES)
    assert "xtop.vvdd:p" in sim.SAVES
    assert not {"xtop.vdd", "xtop.vss"} & set(sim.SAVES)


@pytest.mark.parametrize(("interval", "noise"), [(None, False), (None, True), (10e-12, False)])
def test_a_run_is_one_spectre_transient_in_nutbin(monkeypatch, tmp_path, interval, noise) -> None:
    """The output strobed where the run asks (by default), Spectre's own steps where not; transient noise where the run has it;
    the raw output in nutbin (what flow.pipeline.read parses), at +preset=mx on one thread."""
    import sys
    from types import SimpleNamespace

    import hdl21.sim as hs

    install = SimpleNamespace(include=lambda corner: h.Literal("models"))
    fake = SimpleNamespace(pdk_logic=None)
    monkeypatch.setitem(sys.modules, "pdk.fake", fake)
    monkeypatch.setitem(sys.modules, "pdk.fake.hdl21.site", SimpleNamespace(install=install))
    monkeypatch.setattr(h.pdk, "set_default", lambda *_: None)
    monkeypatch.setattr(h.pdk, "compile", lambda *_: None)
    captured = {}
    monkeypatch.setattr(
        hs,
        "Sim",
        lambda **kwargs: SimpleNamespace(run=lambda options: captured.update(kwargs, options=options)),
    )
    tb = TbParams(pdk="fake", noise=noise, waveform_sample_interval_s=interval)
    assert sim.simulate(tb, tmp_path) == tmp_path / "netlist.raw"
    tran = next(attr for attr in captured["attrs"] if isinstance(attr, hs.Tran))
    assert float(tran.tstop) == pytest.approx(tb.stop_s) and bool(tran.noise) == noise
    assert ("strobeperiod" in tran.options) == (interval is not None) == ("maxstep" in tran.options)
    assert ("noiseseed" in tran.options) == noise
    arguments = captured["options"].simulator_args
    assert arguments[:2] == ("-format", "nutbin") and {"+preset=mx", "+mt=1"} <= set(arguments)
    assert captured["options"].rundir == tmp_path
