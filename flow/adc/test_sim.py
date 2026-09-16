"""Software-only checks for the native HDL21 ADC simulation interface."""

import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from threading import Barrier

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest

from flow.util.netlist import subcircuit_ports

from . import sim

PEX_FIXTURES = {view: Path(__file__).parent / "fixtures" / f"{view}_ports.scs" for view in ("frida1", "frida2")}
PEX_PINS = {view: subcircuit_ports(path.read_text(), "adc_12b_17step") for view, path in PEX_FIXTURES.items()}


@pytest.mark.parametrize("fault", ("ideal_capacitor", "changed_pex"))
def test_extracted_simulation_rejects_double_counting_and_changed_signed_input(tmp_path, monkeypatch, fault):
    path = tmp_path / "adc.pex.netlist"
    path.write_text("X0 (a b s) ringfmom_3layer c=1f\n" if fault == "ideal_capacitor" else "C0 (a b) capacitor c=1f\n")
    (tmp_path / "signoff_summary.json").write_text(
        json.dumps({"lvs_correct": True, "pex_netlist": path.name, "pex_sha256": "not-the-current-content"})
    )
    monkeypatch.setattr(h.pdk, "compile", lambda *_: pytest.fail("invalid PEX reached simulation compilation"))
    with pytest.raises(ValueError, match="double-count" if fault == "ideal_capacitor" else "PEX content differs"):
        sim._run_adc_sim(
            tmp_path / "simulation",
            sim.AdcTbParams(view="frida2", pex_cell="adc_12b_17step"),
            pex_netlist=path,
            check=True,
        )


def test_adc_testbench_parameters_are_simulation_only() -> None:
    params = sim.AdcTbParams()

    assert sim.is_valid_adc_tb_params(params) is True
    assert params.view == "hdl21gen"
    assert params.pex_cell == ""
    assert float(params.vin_cm.dc) == pytest.approx(0.7)
    assert not hasattr(params, "temperature_c")
    assert not hasattr(params, "board_id")
    assert not hasattr(params, "campaign")
    assert not hasattr(params, "vdd_io")


@pytest.mark.parametrize(
    "overrides",
    (
        {"view": "unknown"},
        {"view": "frida2", "pex_cell": ""},
        {"pex_cell": "adc_12b_17step"},
        {"dut": sim.AdcParams(cdac=sim.CapArrayConfig(n_extra=4))},
        {"conversions": 0},
        {"symbol_rate": 0},
        {"symbol_rate": h.Literal("rate")},
        {"vdd_a": h.Vdc.Params(dc=None)},
        {"vin_cm": h.Vdc.Params(dc=h.Literal("nan"))},
        {"supply_series_resistance_ohm": -1.0},
        {"supply_series_resistance_ohm": 1.0},
        {"supply_series_inductance_h": float("inf")},
        {"supply_noise_rms_v": (0.0, 0.0)},
        {"supply_noise_rms_v": (0.0, -1.0, 0.0)},
        {"supply_noise_rms_v": (0.0, float("nan"), 0.0)},
        {"supply_noise_bandwidth_hz": 0.0},
        {"en_comp": 2},
        {"dac_astate_p": (0,) * 15},
        {"dac_bstate_n": (2,) * 16},
        {"seq_samp_pattern": ""},
        {"seq_comp_pattern": "x" * len(sim.BASELINE.comp)},
        {"seq_logic_pattern": "01"},
        {
            f"{net.name}_pattern": "010"
            for net in sim.AdcNets.signals.values()
            if net.vis == h.Visibility.PORT and net.usage == h.Usage.CLOCK
        },
        {"vin_diff": hs.LinearSweep(start=0, stop=1, step=0)},
        {"vin_diff": hs.LinearSweep(start=0, stop=1, step=-0.1)},
        {"conversions": 1, "vin_diff": hs.LinearSweep(start=0, stop=1e-12, step=-1)},
        {"conversions": 4, "vin_diff": hs.LinearSweep(start=0, stop=1, step=0.3)},
        {"conversions": 2, "vin_diff": hs.LinearSweep(start=0, stop=1, step=1), "symbol_rate": 1e15},
    ),
)
def test_invalid_params_fail_before_testbench_generation_or_run(overrides, monkeypatch, tmp_path):
    params = sim.AdcTbParams(**overrides)
    assert sim.is_valid_adc_tb_params(params) is False
    monkeypatch.setattr(sim, "testbench_from_ports", lambda *a, **kw: pytest.fail("invalid params reached generation"))
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.AdcTb(params)
    monkeypatch.setattr(sim, "AdcTb", lambda *a, **kw: pytest.fail("runner passed invalid params to AdcTb"))
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim._run_adc_sim(tmp_path / "run", params)
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("view", ("frida1", "hdl21gen"))
def test_adc_testbench_generates_each_view(view: str) -> None:
    tb = sim.AdcTb(
        sim.AdcTbParams(view=view, conversions=1, pex_cell="adc_12b_17step" if view == "frida1" else ""),
        pex_netlist=PEX_FIXTURES.get(view),
    )

    assert isinstance(tb, h.Module)
    assert tb.xadc is not None
    assert tb.dac_astate_p.width == 16
    assert tb.vin_p is not None


def test_adc_transfer_staircase_has_151_codes() -> None:
    params = sim.AdcTbParams(
        symbol_rate=1.6e9,
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )
    tb = sim.AdcTb(params)
    wave = tb.vvin_diff.of.params.wave

    assert isinstance(wave, h.Pwl)
    assert len(wave.points) == 302
    assert float(wave.points[0][1]) == pytest.approx(-0.75)
    assert float(wave.points[1][0]) == pytest.approx(len(params.seq_init_pattern) / float(params.symbol_rate) - 100e-12)
    assert float(wave.points[-1][1]) == pytest.approx(0.75)
    assert float(wave.points[-1][0]) == pytest.approx(
        params.conversions * len(params.seq_init_pattern) / float(params.symbol_rate)
    )


def test_adc_transfer_sweep_must_match_conversion_count() -> None:
    params = sim.AdcTbParams(
        conversions=2,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )

    assert sim.is_valid_adc_tb_params(params) is False
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.AdcTb(params)


@pytest.mark.parametrize("start,stop,step,count", ((-0.75, 0.75, 0.01, 151), (1, -1, -0.1, 21), (0, 0, 1, 1)))
def test_sweep_validation_agrees_with_generated_waveform(start, stop, step, count):
    params = sim.AdcTbParams(conversions=count, vin_diff=hs.LinearSweep(start=start, stop=stop, step=step))
    assert sim.is_valid_adc_tb_params(params) is True
    wave = sim.AdcTb(params).vvin_diff.of.params.wave
    assert len(wave.points) == 2 * count


@pytest.mark.parametrize("view", ("frida1", "frida2"))
def test_extracted_adc_keeps_calibre_port_order(view) -> None:
    tb = sim.AdcTb(sim.AdcTbParams(view=view, pex_cell="adc_12b_17step"), pex_netlist=PEX_FIXTURES[view])
    names = tuple(port.name for port in tb.xadc.of.module.port_list)
    assert names == PEX_PINS[view]
    assert len(names) == 84


def test_pex_header_reordering_changes_instance_order_without_swapping_nets(tmp_path):
    pins = list(PEX_PINS["frida2"])
    pins[0], pins[1] = pins[1], pins[0]
    path = tmp_path / "reordered.scs"
    path.write_text(f"subckt adc_12b_17step ({' '.join(pins)})\nends adc_12b_17step\n")
    tb = sim.AdcTb(sim.AdcTbParams(view="frida2", pex_cell="adc_12b_17step"), pex_netlist=path)
    assert tuple(tb.xadc.of.module.ports) == tuple(pins)
    assert tb.xadc.conns["vin_p"] is tb.vin_p
    assert tb.xadc.conns["vdd_a"] is tb.vdd_a
    path.write_text(path.read_text().replace("dac_astate_p_0", "dac_astate_p<1>"))
    with pytest.raises(ValueError, match="Duplicate external pins"):
        sim.AdcTb(sim.AdcTbParams(view="frida2", pex_cell="adc_12b_17step"), pex_netlist=path)


@pytest.mark.parametrize(
    "pex_cell",
    (
        "adc_1layer_radix17",
        "adc_1layer_radix20",
        "adc_2layer_radix17",
        "adc_2layer_radix20",
        "adc_12b_17step",
    ),
)
def test_extracted_adc_selects_requested_pex_cell(pex_cell: str, tmp_path) -> None:
    path = tmp_path / "input.scs"
    path.write_text(PEX_FIXTURES["frida1"].read_text().replace("adc_12b_17step", pex_cell))
    tb = sim.AdcTb(sim.AdcTbParams(view="frida1", pex_cell=pex_cell, conversions=1), pex_netlist=path)

    assert tb.xadc.of.module.name == pex_cell


def test_pex_cell_rejects_unknown_and_generated_views() -> None:
    with pytest.raises(ValueError, match="no .subckt adc_unknown"):
        sim.AdcTb(
            sim.AdcTbParams(view="frida1", pex_cell="adc_unknown", conversions=1), pex_netlist=PEX_FIXTURES["frida1"]
        )
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.AdcTb(sim.AdcTbParams(view="hdl21gen", pex_cell="adc_1layer_radix17", conversions=1))


def test_c0_rename_preserves_the_physical_initialization_voltages() -> None:
    for bus in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
        pattern = tuple(int(stage in (0, 3, 8, 14)) for stage in range(16))
        old = sim.AdcTb(
            sim.AdcTbParams(view="frida1", pex_cell="adc_12b_17step", **{bus: pattern}),
            pex_netlist=PEX_FIXTURES["frida1"],
        )
        new = sim.AdcTb(
            sim.AdcTbParams(view="frida2", pex_cell="adc_12b_17step", **{bus: pattern}),
            pex_netlist=PEX_FIXTURES["frida2"],
        )
        for stage, state in enumerate(pattern):
            assert float(getattr(old, f"v{bus}_{stage}").of.params.dc) == pytest.approx(1.2 * state)
            old_net = old.xadc.conns[f"{bus}_{15 - stage}"]
            new_net = new.xadc.conns[f"{bus}_{stage}"]
            assert old_net.parent is old.namespace[bus] and old_net.index == stage
            assert new_net.parent is new.namespace[bus] and new_net.index == stage
            assert float(getattr(new, f"v{bus}_{stage}").of.params.dc) == pytest.approx(1.2 * state)


def test_supply_noise_testbench_repeats_independent_rail_networks() -> None:
    params = sim.AdcTbParams(
        view="frida1",
        pex_cell="adc_12b_17step",
        conversions=1,
        supply_series_resistance_ohm=1.0,
        supply_series_inductance_h=1e-9,
        supply_decoupling_capacitance_f=1e-12,
        supply_noise_rms_v=(1e-3, 0.0, 0.0),
        supply_noise_bandwidth_hz=25e9,
    )
    tb = sim.AdcTb(params, pex_netlist=PEX_FIXTURES["frida1"])
    netlist = StringIO()

    h.netlist(tb, netlist, fmt="spectre")
    text = netlist.getvalue()

    for rail in ("vdd_a", "vdd_d", "vdd_dac"):
        assert float(getattr(tb, f"r{rail}").of.params.r) == pytest.approx(1.0)
        assert float(getattr(tb, f"l{rail}").of.params.l) == pytest.approx(1e-9)
        assert float(getattr(tb, f"c{rail}").of.params.c) == pytest.approx(1e-12)
    assert "vvdd_a (vdd_a_source vss) vsource dc=1.2 noisevec=[0 4e-17 25000000000 4e-17]" in text
    assert tb.vvdd_d.conns["p"] is tb.vdd_d_source
    assert tb.vvdd_dac.conns["p"] is tb.vdd_dac_source
    assert text.count("noisevec=") == 1


@pytest.mark.parametrize("family,count", (("frida1", 4), ("frida2", 3)))
@pytest.mark.parametrize("check", (False, True))
def test_fixed_input_campaigns(family, count, check, tmp_path, monkeypatch):
    calls = []
    started = Barrier(count)

    def pool(*, max_workers, mp_context):
        assert max_workers == count
        assert mp_context.get_start_method() == "spawn"
        return ThreadPoolExecutor(max_workers=max_workers)

    def capture(directory, params, **options):
        calls.append((directory, params, options))
        started.wait(timeout=10)
        return directory / "netlist.raw", {}

    monkeypatch.setattr(sim, "ProcessPoolExecutor", pool)
    from flow.analysis import io
    from flow.circuit import results

    monkeypatch.setattr(results, "read_raw_transient", lambda path: object())
    monkeypatch.setattr(results, "convert_raw_adc_to_measurement", lambda *args, **kwargs: object())
    monkeypatch.setattr(io, "write_measurement", lambda *args: None)
    monkeypatch.setattr(sim, "_run_adc_sim", capture)
    root = tmp_path / "campaign"
    assert getattr(sim, f"{family}_sequence")(root, check=check) == root
    timing_count = 4
    assert len(calls) == timing_count * count
    assert len({directory for directory, *_ in calls}) == timing_count * count
    assert len({directory.parent.name for directory, *_ in calls}) == count
    expected_timings = {"continuous_100ns_comp7of8"}
    expected_timings |= {"original", "extended_comp", "continuous_100ns"}
    assert {directory.name for directory, *_ in calls} == expected_timings
    for directory, params, options in calls:
        flavor = directory.parent.name
        assert directory.parent.parent == root
        assert params.conversions == (1 if check else 100)
        assert params.pex_cell == "adc_12b_17step"
        assert params.view == ("frida2" if family == "frida2" else "frida1")
        assert float(params.symbol_rate) == 1.6e9
        assert float(params.vin_diff.dc) == 0.05
        assert float(params.vin_cm.dc) == pytest.approx(0.7)
        assert options["check"] == check
        assert options["noise"] is True
        assert options["pex_netlist"].name == f"{flavor}.pex.netlist"
        assert options["pex_netlist"].parent.name.startswith("20260905_")
        assert options.get("expected_disconnect", False) == (family == "frida1" and "2layer" in flavor)
        assert sum(sim.get_caparray_weights(params.dut.cdac)) == (2303 if "radix20" in flavor else 2047)
        comp = np.array([int(bit) for bit in params.seq_comp_pattern])
        logic = np.asarray([int(bit) for bit in params.seq_logic_pattern])
        comp_rises = np.flatnonzero(np.diff(comp) == 1) + 1
        comp_falls = np.flatnonzero(np.diff(np.r_[comp, 0]) == -1) + 1
        logic_rises = (np.flatnonzero(np.diff(logic) == 1) + 1)[1:]
        logic_falls = (np.flatnonzero(np.diff(logic) == -1) + 1)[1:]
        if directory.name == "continuous_100ns_comp7of8":
            assert len(comp) == len(logic) == len(params.seq_init_pattern) == len(params.seq_samp_pattern) == 160
            assert len(comp) / float(params.symbol_rate) == pytest.approx(100e-9)
            np.testing.assert_array_equal(comp_rises, 24 + 8 * np.arange(17))
            np.testing.assert_array_equal(comp_falls, comp_rises + 7)
            np.testing.assert_array_equal(logic_rises, comp_rises[:-1] + 7)
            np.testing.assert_array_equal(logic_falls, comp_rises[1:])
            np.testing.assert_array_equal(np.flatnonzero(logic[:24]), [3])
            np.testing.assert_array_equal(np.flatnonzero([int(bit) for bit in params.seq_init_pattern]), np.arange(4))
            np.testing.assert_array_equal(
                np.flatnonzero([int(bit) for bit in params.seq_samp_pattern]), np.arange(4, 24)
            )
            assert comp_falls[-1] / float(params.symbol_rate) == pytest.approx(99.375e-9)
            assert not comp[-1] and not logic[-1]
            assert sim.AdcTb(params, pex_netlist=PEX_FIXTURES[family]).name == f"AdcTb_{family}"
            continue
        if directory.name == "continuous_100ns":
            assert len(comp) == len(logic) == len(params.seq_init_pattern) == len(params.seq_samp_pattern) == 160
            assert len(comp) / float(params.symbol_rate) == pytest.approx(100e-9)
            np.testing.assert_array_equal(comp_rises, 28 + 8 * np.arange(17))
            np.testing.assert_array_equal(comp_falls, np.r_[comp_rises[:-1] + 6, 160])
            np.testing.assert_array_equal(logic_rises, comp_rises[:-1] + 6)
            np.testing.assert_array_equal(logic_falls, logic_rises + 1)
            np.testing.assert_array_equal(np.flatnonzero(logic[:28]), [3])
            np.testing.assert_array_equal(np.flatnonzero([int(bit) for bit in params.seq_init_pattern]), np.arange(4))
            np.testing.assert_array_equal(
                np.flatnonzero([int(bit) for bit in params.seq_samp_pattern]), np.arange(4, 28)
            )
            # Exercise the generator's validation with the shorter whole-word record.
            assert sim.AdcTb(params, pex_netlist=PEX_FIXTURES[family]).name == f"AdcTb_{family}"
            continue
        assert len(comp) == len(logic) == len(params.seq_init_pattern) == 256
        np.testing.assert_array_equal(comp_rises, 36 + 8 * np.arange(17))
        np.testing.assert_array_equal(logic_rises, comp_rises[:-1] + 6)
        if directory.name == "original":
            assert params.seq_comp_pattern == sim.AdcTbParams().seq_comp_pattern
            assert params.seq_logic_pattern == sim.ORIGINAL.logic
            np.testing.assert_array_equal(comp_falls, comp_rises + 4)
            np.testing.assert_array_equal(logic_falls, logic_rises + 4)
        else:
            np.testing.assert_array_equal(comp_falls, comp_rises + 6)
            np.testing.assert_array_equal(logic_rises, comp_falls[:-1])
            np.testing.assert_array_equal(logic_falls, logic_rises + 1)
            np.testing.assert_array_equal(comp_rises[1:] - logic_falls, np.ones(16))
        assert params.seq_samp_pattern == sim.AdcTbParams().seq_samp_pattern
        assert params.seq_init_pattern == sim.AdcTbParams().seq_init_pattern


@pytest.mark.parametrize("family,count", (("frida1", 4), ("frida2", 3)))
def test_concurrent_campaign_propagates_case_failure(family, count, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        sim, "ProcessPoolExecutor", lambda **kwargs: ThreadPoolExecutor(max_workers=kwargs["max_workers"])
    )

    def fail_one(directory, *_args, **_kwargs):
        calls.append(directory)
        if "1layer_radix17" in directory.parent.name:
            raise RuntimeError("simulator failed")
        return directory / "netlist.raw", {}

    monkeypatch.setattr(sim, "_run_adc_sim", fail_one)
    with pytest.raises(RuntimeError, match="simulator failed"):
        getattr(sim, f"{family}_sequence")(tmp_path)
    assert len(calls) == 4 * count


@pytest.mark.parametrize(
    "target,count,workers",
    (
        ("hdl21_sample_rate", 3, 3),
        ("frida1_sample_rate", 12, 4),
        ("frida1_supply_noise", 15, 4),
        ("hdl21_transfer_curve", 1, None),
        ("frida1_transfer_curve", 1, None),
    ),
)
@pytest.mark.parametrize("check", (False, True))
def test_other_campaign_recipes(target, count, workers, check, tmp_path, monkeypatch):
    calls = []

    def pool(*, max_workers, mp_context):
        assert max_workers == workers
        assert mp_context.get_start_method() == "spawn"
        return ThreadPoolExecutor(max_workers=max_workers)

    def capture(directory, params, **options):
        calls.append((directory, params, options))
        return directory / "netlist.raw", {}

    monkeypatch.setattr(sim, "ProcessPoolExecutor", pool)
    from flow.analysis import io
    from flow.circuit import results

    monkeypatch.setattr(results, "read_raw_transient", lambda path: object())
    monkeypatch.setattr(results, "convert_raw_adc_to_measurement", lambda *args, **kwargs: object())
    monkeypatch.setattr(io, "write_measurement", lambda *args: None)
    monkeypatch.setattr(sim, "_run_adc_sim", capture)
    assert getattr(sim, target)(tmp_path, check=check) == tmp_path
    assert len(calls) == count
    assert len({directory for directory, *_ in calls}) == count
    for directory, params, options in calls:
        assert options["check"] == check
        assert params.view == ("hdl21gen" if target.startswith("hdl21") else "frida1")
        if "transfer_curve" in target:
            assert params.conversions == 151
            assert params.vin_diff == hs.LinearSweep(start=-0.75, stop=0.75, step=0.01)
            assert not options.get("noise", False)
        else:
            assert params.conversions == (1 if check else 100)
            assert float(params.vin_diff.dc) == 0.05
        if "supply_noise" in target:
            assert params.supply_series_resistance_ohm == 1.0
            assert params.supply_series_inductance_h == 1e-9
            assert params.supply_decoupling_capacitance_f == 1e-12
            assert params.supply_noise_bandwidth_hz == 25e9
            assert set(params.supply_noise_rms_v) <= {0.0, 1e-3}
            # Preserve the original supply recipe; do not enable device noise
            # as an incidental effect of consolidating the executors.
            assert not options.get("noise", False)
        elif "fixed_input_noise" in target:
            assert options["noise"] is True
    if "vs_rate" in target:
        assert {float(params.symbol_rate) for _, params, _ in calls} == {320e6, 960e6, 1.6e9}


@pytest.fixture
def captured_executor(monkeypatch):
    from types import SimpleNamespace

    from flow.analysis import io
    from flow.circuit import results
    from pdk import tsmc65
    from pdk.tsmc65 import site

    captured = {}
    monkeypatch.setattr(h.pdk, "set_default", lambda *_: None)
    monkeypatch.setattr(h.pdk, "compile", lambda *_: None)
    monkeypatch.setattr(tsmc65, "pdk_logic", object())
    monkeypatch.setattr(site, "STANDARD_CELL_SPICE_NETLISTS", (Path("/cells/regular.spi"), Path("/cells/driver.spi")))
    monkeypatch.setattr(
        site,
        "install",
        SimpleNamespace(
            include=lambda *_: h.Literal("models"),
            include_pre_simulation=lambda: h.Literal("pre"),
            include_stdcell=lambda: hs.Include(path=Path("/cells/driver.spi")),
        ),
    )
    monkeypatch.setattr(
        sim,
        "adc_signal_names",
        lambda *args, **kwargs: {"time": "time_s", "xtop.comp_out": "comp_out_v", "xtop.xadc.internal": "internal_v"},
    )
    monkeypatch.setattr(
        results, "convert_raw_adc_to_measurement", lambda *args, **kwargs: captured.update(converted=kwargs)
    )
    monkeypatch.setattr(io, "write_measurement", lambda path, value: captured.update(hdf5=path))

    def build(**kwargs):
        captured.update(kwargs)

        def run(options):
            captured["options"] = options
            if captured.get("fail"):
                raise RuntimeError("simulator/license failure")
            return object()

        return SimpleNamespace(run=run)

    monkeypatch.setattr(hs, "Sim", build)
    return captured


@pytest.fixture
def pex_input(tmp_path):
    pex = tmp_path / "frida2_2layer_radix17.pex.netlist"
    ports = " ".join(PEX_PINS["frida2"])
    pex.write_text(f"subckt adc_12b_17step ({ports})\ninternal\nends adc_12b_17step\n")
    (tmp_path / "signoff_summary.json").write_text(
        json.dumps(
            {
                "lvs_correct": True,
                "pex_netlist": str(pex),
                "warnings": [],
            }
        )
    )
    return pex


@pytest.mark.parametrize("check", (False, True))
def test_logic_capture_saves_tail_without_changing_noise_bandwidth(check, captured_executor, tmp_path):
    params = sim.AdcTbParams(
        conversions=100,
        seq_init_pattern="1111" + "0" * 156,
        seq_samp_pattern="0000" + "1" * 20 + "0" * 136,
        seq_comp_pattern="0" * 24 + "11111110" * 17,
        seq_logic_pattern="0001" + "0" * 20 + "00000001" * 16 + "0" * 8,
    )
    sim._run_adc_sim(tmp_path / "run", params, noise=True, check=check)
    tran = next(attr for attr in captured_executor["attrs"] if isinstance(attr, hs.Tran))
    assert float(tran.tstop) == pytest.approx(100e-9 if check else 10e-6 + 15.625e-9, abs=1e-15)
    if not check:
        assert float(tran.options["noisefmin"]) == pytest.approx(100e3)
        assert "converted" not in captured_executor


@pytest.mark.parametrize("view,threads", (("hdl21gen", 8), ("frida2", 8), ("frida1", 6)))
@pytest.mark.parametrize("check", (False, True))
def test_single_executor_modes(view, threads, check, captured_executor, pex_input, tmp_path):
    if view == "frida1":
        ports = " ".join(PEX_PINS["frida1"])
        pex_input.write_text(f"subckt adc_12b_17step ({ports})\ninternal\nends adc_12b_17step\n")
    params = sim.AdcTbParams(
        view=view,
        pex_cell="" if view == "hdl21gen" else "adc_12b_17step",
        conversions=100,
    )
    root = tmp_path / "run"
    sim._run_adc_sim(
        root,
        params,
        pex_netlist=None if view == "hdl21gen" else pex_input,
        noise=True,
        check=check,
    )
    captured = captured_executor
    tran = next(attr for attr in captured["attrs"] if isinstance(attr, hs.Tran))
    assert tran.noise == (not check)
    assert float(tran.tstop) == pytest.approx(100e-9 if check else 16e-6 + 23.125e-9, abs=1e-15)
    assert float(tran.options["strobeperiod"]) == pytest.approx(params.waveform_sample_interval_s, abs=1e-18)
    if not check:
        assert tran.options["noisefmax"].text == "25G"
        assert float(tran.options["noiseseed"]) == 1
    assert f"+mt={threads}" in captured["options"].simulator_args
    assert ("-ahdllint=warn" in captured["options"].simulator_args) == check
    assert captured["options"].rundir == root
    literals = "\n".join(attr.text for attr in captured["attrs"] if isinstance(attr, h.Literal))
    assert ("check_setuphold" in literals) == check
    assert ("simulator lang=spice" in literals) == (view == "hdl21gen")
    driver_includes = [
        attr for attr in captured["attrs"] if isinstance(attr, hs.Include) and attr.path == Path("/cells/driver.spi")
    ]
    assert len(driver_includes) == (1 if view == "hdl21gen" else 0)
    assert "/cells/driver.spi" not in literals
    assert ("/cells/regular.spi" in literals) == (view == "hdl21gen")
    assert ("adc_digital.sp" in literals) == (view == "hdl21gen")
    assert "models" in literals and "pre" in literals
    assert "converted" not in captured and "hdf5" not in captured
    metadata = json.loads((root / "input.json").read_text())
    assert metadata["spectre_threads"] == threads
    assert metadata["transient_noise"] == (not check)
    if view != "hdl21gen":
        import hashlib

        assert metadata["pex_sha256"] == hashlib.sha256(pex_input.read_bytes()).hexdigest()


@pytest.mark.parametrize("check", (False, True))
def test_transfer_executor_enforces_waveform_resolution(check, captured_executor, tmp_path):
    params = sim.AdcTbParams(
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )
    sim._run_adc_sim(tmp_path / "run", params, check=check)
    tran = next(attr for attr in captured_executor["attrs"] if isinstance(attr, hs.Tran))
    assert not tran.noise
    assert float(tran.options["strobeperiod"]) == pytest.approx(params.waveform_sample_interval_s, abs=1e-18)
    assert float(tran.tstop) == pytest.approx(100e-9 if check else 151 * 160e-9 + 23.125e-9, abs=1e-15)
    if not check:
        assert "converted" not in captured_executor


@pytest.mark.parametrize(
    "fault,message",
    (
        ("ports", "External interface.*unknown"),
        ("nodes", "PEX waveform nodes missing"),
        ("header", "no .subckt adc_12b_17step"),
        ("lvs", "unaccepted LVS result"),
        ("wrong_file", "PEX input differs"),
    ),
)
def test_executor_rejects_bad_pex(fault, message, captured_executor, pex_input, tmp_path):
    if fault == "ports":
        pex_input.write_text(pex_input.read_text().replace("vdd_a vin_p", "vdd_typo vin_p"))
    elif fault == "nodes":
        pex_input.write_text(pex_input.read_text().replace("\ninternal\n", "\n"))
    elif fault == "header":
        pex_input.write_text("subckt other ()\nends other\n")
    else:
        summary = json.loads((tmp_path / "signoff_summary.json").read_text())
        if fault == "lvs":
            summary["lvs_correct"] = False
        else:
            summary["pex_netlist"] = "wrong.pex.netlist"
        (tmp_path / "signoff_summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match=message):
        sim._run_adc_sim(
            tmp_path / "run",
            sim.AdcTbParams(view="frida2", pex_cell="adc_12b_17step"),
            pex_netlist=pex_input,
            check=True,
        )
    assert "options" not in captured_executor


def test_missing_configured_pex_fails(captured_executor, tmp_path):
    with pytest.raises(FileNotFoundError):
        sim._run_adc_sim(
            tmp_path / "run",
            sim.AdcTbParams(view="frida2", pex_cell="adc_12b_17step"),
            pex_netlist=tmp_path / "missing.pex.netlist",
            check=True,
        )
    assert "options" not in captured_executor


def test_diagnostic_simulator_error_propagates(captured_executor, tmp_path):
    captured_executor["fail"] = True
    with pytest.raises(RuntimeError, match="simulator/license failure"):
        sim._run_adc_sim(tmp_path / "run", sim.AdcTbParams(), check=True)


@pytest.mark.parametrize(
    "view,target,warning,accepted",
    (
        ("frida1", "frida1_2layer_radix17", "expected LVS mismatch: disconnected historical MOM layer", True),
        ("frida1", "frida1_2layer_radix20", "expected LVS mismatch: disconnected historical MOM layer", True),
        ("frida1", "frida1_1layer_radix17", "expected LVS mismatch: disconnected historical MOM layer", False),
        ("frida2", "frida2_2layer_radix17", "expected LVS mismatch: disconnected historical MOM layer", False),
        ("frida1", "frida1_2layer_radix17", "unrelated mismatch", False),
    ),
)
def test_historical_lvs_exception_is_narrow(view, target, warning, accepted, captured_executor, pex_input, tmp_path):
    renamed = pex_input.with_name(f"{target}.pex.netlist")
    pex_input.rename(renamed)
    if view == "frida1":
        ports = " ".join(PEX_PINS["frida1"])
        renamed.write_text(f"subckt adc_12b_17step ({ports})\ninternal\nends adc_12b_17step\n")
    (tmp_path / "signoff_summary.json").write_text(
        json.dumps(
            {
                "lvs_correct": False,
                "pex_netlist": f"/worker/{renamed.name}",
                "warnings": [warning],
            }
        )
    )
    kwargs = {"pex_netlist": renamed, "expected_disconnect": True, "check": True}
    params = sim.AdcTbParams(view=view, pex_cell="adc_12b_17step")
    if accepted:
        sim._run_adc_sim(tmp_path / "run", params, **kwargs)
        assert captured_executor["options"]
    else:
        with pytest.raises(ValueError, match="unaccepted LVS"):
            sim._run_adc_sim(tmp_path / "run", params, **kwargs)


def test_adc_main_lists_only_experiment_targets_in_family_order(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["sim"])
    sim.main()
    assert capsys.readouterr().out.splitlines()[1:] == [
        "  hdl21_sample_rate",
        "  hdl21_transfer_curve",
        "  frida1_sequence",
        "  frida1_sample_rate",
        "  frida1_transfer_curve",
        "  frida1_supply_noise",
        "  frida2_sequence",
    ]
    functions = [
        name
        for name, value in vars(sim).items()
        if inspect.isfunction(value) and value.__module__ == sim.__name__ and name.startswith("_")
    ]
    assert functions == ["_run_adc_sim"]


def test_main_runs_full_experiment(tmp_path, monkeypatch):
    calls = []

    def frida2_sequence(directory, **options):
        calls.append((directory, options))

    monkeypatch.setattr(sim, "frida2_sequence", frida2_sequence)
    monkeypatch.setattr(sim, "__file__", str(tmp_path / "flow/adc/sim.py"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "sim",
            "frida2_sequence",
        ],
    )
    sim.main()
    directory, options = calls[0]
    assert directory.parent == tmp_path / "build/sim/adc"
    assert directory.name.endswith("_frida2_sequence")
    assert directory.is_dir()
    assert options == {}


def test_all_campaign_patterns_and_phases_are_preserved(monkeypatch, tmp_path):
    """Independent literal expectations cover every clock of all 28 configurations."""
    from concurrent.futures import Future

    expected = {
        "original": (
            "0" * 8 + "1" * 8 + "0" * 240,
            "0" * 16 + "1" * 16 + "0" * 224,
            "0" * 32 + "00001111" * 17 + "0" * 88,
            "0" * 8 + "00001111" + "0" * 24 + "11110000" * 16 + "0" * 88,
            2.0,
        ),
        "extended_comp": (
            "0" * 8 + "1" * 8 + "0" * 240,
            "0" * 16 + "1" * 16 + "0" * 224,
            "0" * 36 + "11111100" * 17 + "0" * 84,
            "0" * 8 + "00001111" + "0" * 24 + "10000000" * 16 + "0" * 88,
            2.0,
        ),
        "continuous_100ns": (
            "1111" + "0" * 156,
            "0000" + "1" * 24 + "0" * 132,
            "0" * 28 + "11111100" * 16 + "1111",
            "0001" + "0" * 24 + "00000010" * 16 + "0000",
            0.0,
        ),
        "continuous_100ns_comp7of8": (
            "1111" + "0" * 156,
            "0000" + "1" * 20 + "0" * 136,
            "0" * 24 + "11111110" * 17,
            "0001" + "0" * 20 + "00000001" * 16 + "0" * 8,
            0.0,
        ),
    }
    cases = []

    class CaptureExecutor:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, function, directory, params, **kwargs):
            cases.append((directory, params))
            future = Future()
            future.set_result((directory / "netlist.raw", {}))
            return future

    from flow.analysis import io
    from flow.circuit import results

    monkeypatch.setattr(results, "read_raw_transient", lambda path: object())
    monkeypatch.setattr(results, "convert_raw_adc_to_measurement", lambda *args, **kwargs: object())
    monkeypatch.setattr(io, "write_measurement", lambda *args: None)
    monkeypatch.setattr(sim, "ProcessPoolExecutor", CaptureExecutor)
    sim.frida1_sequence(tmp_path)
    sim.frida2_sequence(tmp_path)
    assert len(cases) == len({path for path, _ in cases}) == 28
    for path, params in cases:
        init, samp, comp, logic, phase = expected[path.name]
        assert (
            params.seq_init_pattern,
            params.seq_samp_pattern,
            params.seq_comp_pattern,
            params.seq_logic_pattern,
        ) == (init, samp, comp, logic[-int(phase) :] + logic[: -int(phase)] if phase else logic)
        assert float(params.symbol_rate) == 1.6e9
