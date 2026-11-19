"""Software-only checks of the comparator's testbench parameters and testbench (no simulator)."""

from typing import Any

import hdl21 as h
import numpy as np
import pytest

from flow.circuit import spectre

from . import params, sim
from .params import ClockDrive, InputOrder, TbParams


def test_a_run_defaults_to_the_clock_every_comparator_is_tested_at() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.conversions) == ("tsmc65", params.Params(), 1)
    assert (tb.input_order, tb.noise) == (InputOrder.BLOCKED, False)
    assert (tb.reset_time_s, tb.evaluation_time_s) == (params.RESET_S, params.EVALUATION_S) == (1e-9, 4e-9)
    assert tb.cycle_s == pytest.approx(5e-9)
    # Spectre's output every 2 ps, Spectre X, the typical corner at 25 C, the clocks' own chains
    assert tb.waveform_sample_interval_s == params.STROBE_S == 2e-12
    assert (tb.accuracy, tb.corner, tb.temperature_c) == (None, h.pdk.Corner.TYP, 25.0)
    assert tb.clock_drive is ClockDrive.CHAINS and not tb.device_values


def test_an_order_given_by_its_name_is_its_member_and_a_cycled_run_keeps_the_order_given() -> None:
    assert TbParams(input_order="shuffled").input_order is InputOrder.SHUFFLED
    cycled = TbParams(vin_diff_values_v=(-1.0, 1e-3), conversions=3, input_order=InputOrder.CYCLED)
    assert cycled.trial_point.tolist() == [0, 1, 0, 1, 0, 1]


def test_the_converters_clocks_make_clkb_from_clk_through_one_inverter_on_the_comparators_supply() -> None:
    """``ClockDrive.CONVERTER``: clk's chain on a supply of its own, clkb clk inverted by the
    converter's 10-unit inverter on vdd; no chain of clkb's."""
    bench = sim.testbench(TbParams(clock_drive=ClockDrive.CONVERTER))
    names = set(bench.instances)
    assert {"mclkb_inverter_pmos", "mclkb_inverter_nmos", "vvdd_clock", "vclk"} <= names
    assert "vclkb" not in names and not any(name.startswith("mclkb_0") for name in names)
    pmos = bench.instances["mclkb_inverter_pmos"]
    assert pmos.conns["g"] is bench.clk and pmos.conns["d"] is bench.clkb and pmos.conns["s"] is bench.vdd
    first = next(inst for name, inst in bench.instances.items() if name.startswith("mclk_") and name.endswith("pmos"))
    assert first.conns["s"] is bench.vdd_clock


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


@pytest.mark.parametrize(
    ("interval", "noise", "accuracy"),
    [
        (None, False, None),
        (10e-12, False, None),
        (5e-12, True, spectre.Accuracy.S_CURVE),
        (2e-12, False, spectre.Accuracy.TIMING),
    ],
)
def test_a_run_is_one_spectre_transient_in_nutbin(monkeypatch, tmp_path, interval, noise, accuracy) -> None:
    """The output strobed where the run asks (by default), Spectre's own steps where not; transient
    noise where the run has it; the raw output in nutbin (what flow.pipeline.read parses), at
    +preset=mx on one thread, or, where the run needs accuracy, in classic Spectre at its
    conservative preset with its step bounded to the strobe (a timing run at Razavi's tolerances)."""
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
    tb = TbParams(pdk="fake", noise=noise, waveform_sample_interval_s=interval, accuracy=accuracy)
    assert sim.simulate(tb, tmp_path) == tmp_path / "netlist.raw"
    tran = next(attr for attr in captured["attrs"] if isinstance(attr, hs.Tran))
    assert float(tran.tstop) == pytest.approx(tb.stop_s) and bool(tran.noise) == noise
    assert ("strobeperiod" in tran.options) == (interval is not None)
    assert ("maxstep" in tran.options) == (accuracy is not None) == ("errpreset" in tran.options)
    assert ("noiseseed" in tran.options) == noise
    if noise:
        assert float(tran.options["noisefmax"]) == tb.noise_fmax_hz >= 100e9
    arguments = captured["options"].simulator_args
    assert arguments[:2] == ("-format", "nutbin")
    assert ({"+preset=mx", "+mt=1"} <= set(arguments)) == (accuracy is None)
    assert not any(argument.startswith("+preset") for argument in arguments) or accuracy is None
    tolerances = {attr.name: attr.value for attr in captured["attrs"] if isinstance(attr, hs.Options)}
    assert ("reltol" in tolerances) == (accuracy is spectre.Accuracy.TIMING)
    if accuracy is spectre.Accuracy.TIMING:
        # [Razavi-ADC] Sec. 7.6, p. 136: reltol 1e-6, vabstol 1e-6, iabstol 1e-12
        assert {name: tolerances[name] for name in ("reltol", "vabstol", "iabstol")} == {
            "reltol": 1e-6,
            "vabstol": 1e-6,
            "iabstol": 1e-12,
        }
    assert captured["options"].rundir == tmp_path
    # the supply's charge meter: the supply source's current onto a capacitor, saved
    meter = next(attr.text for attr in captured["attrs"] if isinstance(attr, h.Literal) and "cccs" in attr.text)
    assert "cccs probe=xtop.vvdd" in meter and f"c={params.CHARGE_METER_F}" in meter
    save = next(attr for attr in captured["attrs"] if isinstance(attr, hs.Save))
    assert params.CHARGE_METER in save.targ
