"""Software-only checks for the native HDL21 ADC simulation interface. A test that builds the
generated view's testbench binds TSMC65 (``tsmc65``), as ``sim.simulate`` does; a PDK-free checkout
skips it."""

import inspect
import json
from dataclasses import fields
from io import StringIO
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest
from vlsirtools.spice.sim_data import TranResult

from flow import capdac
from flow.analysis.io import read_measurement, write_measurement
from flow.analysis.types import MeasAdc
from flow.circuit.ports import waveform_net_names
from flow.scans.seqgen import convert_params_to_seqgen_fmt
from flow.util.netlist import subcircuit_ports

from . import sim
from .params import Params, TbParams
from .subckt import AdcNets

PEX_FIXTURES = {"frida1": Path(__file__).parent / "fixtures" / "frida1_ports.scs"}
PEX_PINS = {view: subcircuit_ports(path.read_text(), "adc_12b_17step") for view, path in PEX_FIXTURES.items()}

timing_sequences = tuple(
    sequence for name, sequence in sim.SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")
)

duty_sequences = tuple(
    (name, sequence)
    for name, sequence in sim.SEQUENCES
    if name.startswith(("symbol160_init4_samp20_", "symbol256_init4_samp20_"))
    and name != "symbol160_init4_samp20_comp11111100_logic00000010"
)


@pytest.mark.parametrize("fault", ("ideal_capacitor", "changed_pex"))
def test_extracted_simulation_rejects_double_counting_and_changed_signed_input(tmp_path, monkeypatch, fault):
    path = tmp_path / "adc.pex.netlist"
    path.write_text("X0 (a b s) ringfmom_3layer c=1f\n" if fault == "ideal_capacitor" else "C0 (a b) capacitor c=1f\n")
    (tmp_path / "signoff_summary.json").write_text(
        json.dumps({"lvs_correct": True, "pex_netlist": path.name, "pex_sha256": "not-the-current-content"})
    )
    monkeypatch.setattr(h.pdk, "compile", lambda *_: pytest.fail("invalid PEX reached simulation compilation"))
    with pytest.raises(ValueError, match="double-count" if fault == "ideal_capacitor" else "PEX content differs"):
        sim.simulate(
            TbParams(view="frida1", pex_cell="adc_12b_17step"),
            tmp_path / "simulation",
            pex_netlist=path,
            check=True,
        )


def test_adc_testbench_parameters_are_simulation_only() -> None:
    params = TbParams()

    assert sim.is_valid_adc_tb_params(params) is True
    assert params.view == "hdl21gen"
    assert params.pex_cell == ""
    # FRIDA-1's extracted view switches its difference plates either way
    frida1 = TbParams(view="frida1", pex_cell="adc_12b_17step")
    assert sim.is_valid_adc_tb_params(TbParams(**{**frida1.__dict__, "dac_diffcaps": 0})) is True
    assert float(params.vin_cm.dc) == pytest.approx(0.7)
    assert not hasattr(params, "temperature_c")
    assert not hasattr(params, "board_id")
    assert not hasattr(params, "campaign")
    assert not hasattr(params, "vdd_io")


@pytest.mark.parametrize(
    "overrides",
    (
        {"view": "unknown"},
        {"view": "frida2", "pex_cell": "adc_12b_17step"},  # retired: FRIDA-2 is generated
        {"pex_cell": "adc_12b_17step"},
        # the generated ADC wires its subtraction in: no run of it adds the difference plates
        {"dac_diffcaps": 0},
        {"dut": Params(cdac=capdac.Params(extra=4))},
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
        {"seq_comp_pattern": "x" * len(sim.symbol256_init8_samp16_comp11110000_logic00001111.comp)},
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
    params = TbParams(**overrides)
    assert sim.is_valid_adc_tb_params(params) is False
    monkeypatch.setattr(sim, "testbench_from_ports", lambda *a, **kw: pytest.fail("invalid params reached generation"))
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.testbench(params)
    monkeypatch.setattr(sim, "testbench", lambda *a, **kw: pytest.fail("runner passed invalid params to testbench"))
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.simulate(params, tmp_path / "run")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("view", ("frida1", "hdl21gen"))
def test_adc_testbench_generates_each_view(view: str, request: pytest.FixtureRequest) -> None:
    if view == "hdl21gen":
        request.getfixturevalue("tsmc65")
    tb = sim.testbench(
        TbParams(view=view, conversions=1, pex_cell="adc_12b_17step" if view == "frida1" else ""),
        pex_netlist=PEX_FIXTURES.get(view),
    )

    assert isinstance(tb, h.Module)
    assert tb.xadc is not None
    assert tb.dac_astate_p.width == 16
    assert tb.vin_p is not None


def test_each_generated_testbench_holds_a_fresh_adc(tsmc65) -> None:
    """The ADC's DAC is resolved to the PDK's devices in place, and a compile swaps a hierarchy's
    devices in place: each testbench holds its own ADC and DAC, so neither touches another's."""
    first, second = sim.testbench(TbParams()), sim.testbench(TbParams())
    assert first.xadc.of is not second.xadc.of
    assert first.xadc.of.xdac_p.of is not second.xadc.of.xdac_p.of


def test_adc_transfer_staircase_has_151_codes(tsmc65) -> None:
    params = TbParams(
        symbol_rate=1.6e9,
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )
    tb = sim.testbench(params)
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
    params = TbParams(
        conversions=2,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )

    assert sim.is_valid_adc_tb_params(params) is False
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.testbench(params)


@pytest.mark.parametrize("start,stop,step,count", ((-0.75, 0.75, 0.01, 151), (1, -1, -0.1, 21), (0, 0, 1, 1)))
def test_sweep_validation_agrees_with_generated_waveform(tsmc65, start, stop, step, count):
    params = TbParams(conversions=count, vin_diff=hs.LinearSweep(start=start, stop=stop, step=step))
    assert sim.is_valid_adc_tb_params(params) is True
    wave = sim.testbench(params).vvin_diff.of.params.wave
    assert len(wave.points) == 2 * count


def test_extracted_adc_keeps_calibre_port_order() -> None:
    tb = sim.testbench(TbParams(view="frida1", pex_cell="adc_12b_17step"), pex_netlist=PEX_FIXTURES["frida1"])
    names = tuple(port.name for port in tb.xadc.of.module.port_list)
    assert names == PEX_PINS["frida1"]
    assert len(names) == 84


def test_pex_header_reordering_changes_instance_order_without_swapping_nets(tmp_path):
    pins = list(PEX_PINS["frida1"])
    pins[0], pins[1] = pins[1], pins[0]
    path = tmp_path / "reordered.scs"
    path.write_text(f"subckt adc_12b_17step ({' '.join(pins)})\nends adc_12b_17step\n")
    tb = sim.testbench(TbParams(view="frida1", pex_cell="adc_12b_17step"), pex_netlist=path)
    assert tuple(tb.xadc.of.module.ports) == tuple(pins)
    assert tb.xadc.conns["vin_p"] is tb.vin_p
    assert tb.xadc.conns["vdd_a"] is tb.vdd_a
    path.write_text(path.read_text().replace("dac_astate_p_0", "dac_astate_p<1>"))
    with pytest.raises(ValueError, match="Duplicate external pins"):
        sim.testbench(TbParams(view="frida1", pex_cell="adc_12b_17step"), pex_netlist=path)


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
    tb = sim.testbench(TbParams(view="frida1", pex_cell=pex_cell, conversions=1), pex_netlist=path)

    assert tb.xadc.of.module.name == pex_cell


def test_pex_cell_rejects_unknown_and_generated_views() -> None:
    with pytest.raises(ValueError, match="no .subckt adc_unknown"):
        sim.testbench(
            TbParams(view="frida1", pex_cell="adc_unknown", conversions=1), pex_netlist=PEX_FIXTURES["frida1"]
        )
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.testbench(TbParams(view="hdl21gen", pex_cell="adc_1layer_radix17", conversions=1))


def test_the_fabricated_bus_order_preserves_the_physical_initialization_voltages() -> None:
    # FRIDA-1's macro is C15 first: its pin <15 - stage> carries stage's state
    for bus in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
        pattern = tuple(int(stage in (0, 3, 8, 14)) for stage in range(16))
        tb = sim.testbench(
            TbParams(view="frida1", pex_cell="adc_12b_17step", **{bus: pattern}),
            pex_netlist=PEX_FIXTURES["frida1"],
        )
        for stage, state in enumerate(pattern):
            assert float(getattr(tb, f"v{bus}_{stage}").of.params.dc) == pytest.approx(1.2 * state)
            net = tb.xadc.conns[f"{bus}_{15 - stage}"]
            assert net.parent is tb.namespace[bus] and net.index == stage


def test_all_adc_views_expose_the_same_analysis_waveforms(tsmc65):
    observations = []
    for view in ("hdl21gen", "frida1"):
        pex = PEX_FIXTURES.get(view)
        tb = sim.testbench(TbParams(view=view, pex_cell="adc_12b_17step" if pex else ""), pex_netlist=pex)
        observations.append(set(sim.adc_signal_names(tb, view).values()))
    assert observations[0] == observations[1]
    for side in ("p", "n"):
        for kind in ("", "_diff"):
            for stage in range(16):
                assert f"dac_botplate_{side}{kind}[{stage}]" in observations[0]


@pytest.mark.parametrize("fault", ("missing", "duplicate"))
def test_pex_observations_reject_incomplete_or_ambiguous_bindings(monkeypatch, fault):
    tb = sim.testbench(TbParams(view="frida1", pex_cell="adc_12b_17step"), pex_netlist=PEX_FIXTURES["frida1"])
    aliases = sim.frida1_net_aliases()
    if fault == "missing":
        del aliases[sim.AdcNets.vdac_p]
    else:
        aliases[sim.AdcNets.vdac_p] = aliases[sim.AdcNets.vdac_n]
    monkeypatch.setattr(sim, "frida1_net_aliases", lambda: aliases)
    with pytest.raises((KeyError, ValueError)):
        sim.adc_signal_names(tb, "frida1")


def test_supply_noise_testbench_repeats_independent_rail_networks() -> None:
    params = TbParams(
        view="frida1",
        pex_cell="adc_12b_17step",
        conversions=1,
        supply_series_resistance_ohm=1.0,
        supply_series_inductance_h=1e-9,
        supply_decoupling_capacitance_f=1e-12,
        supply_noise_rms_v=(1e-3, 0.0, 0.0),
        supply_noise_bandwidth_hz=25e9,
    )
    tb = sim.testbench(params, pex_netlist=PEX_FIXTURES["frida1"])
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


@pytest.fixture
def captured_executor(monkeypatch, tsmc65):
    from types import SimpleNamespace

    from flow.analysis import io
    from pdk import tsmc65 as kit
    from pdk.tsmc65.hdl21 import site

    captured = {}
    monkeypatch.setattr(h.pdk, "set_default", lambda *_: None)
    monkeypatch.setattr(h.pdk, "compile", lambda *_: None)
    monkeypatch.setattr(kit, "pdk_logic", object())
    monkeypatch.setattr(site, "STANDARD_CELL_SPICE_NETLISTS", (Path("/cells/regular.spi"), Path("/cells/driver.spi")))
    monkeypatch.setattr(
        site,
        "install",
        SimpleNamespace(
            include=lambda *_: h.Literal("models"),
            include_pre_simulation=lambda: h.Literal("pre"),
            include_stdcell=lambda: hs.Include(path=Path("/cells/driver.spi")),
            # the generated ADC's DAC takes its reference from the PDK's typical supply
            supply_voltage=site.install.supply_voltage,
        ),
    )
    monkeypatch.setattr(
        sim,
        "adc_signal_names",
        lambda *args, **kwargs: {"time": "time_s", "xtop.comp_out": "comp_out_v", "xtop.xadc.internal": "internal_v"},
    )
    monkeypatch.setattr(sim, "_decode", lambda *args, **kwargs: captured.update(converted=kwargs))
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
    pex = tmp_path / "frida1_1layer_radix17.pex.netlist"
    ports = " ".join(PEX_PINS["frida1"])
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
    params = TbParams(
        conversions=100,
        seq_init_pattern="1111" + "0" * 156,
        seq_samp_pattern="0000" + "1" * 20 + "0" * 136,
        seq_comp_pattern="0" * 24 + "11111110" * 17,
        seq_logic_pattern="0001" + "0" * 20 + "00000001" * 16 + "0" * 8,
    )
    sim.simulate(params, tmp_path / "run", noise=True, check=check)
    tran = next(attr for attr in captured_executor["attrs"] if isinstance(attr, hs.Tran))
    assert float(tran.tstop) == pytest.approx(100e-9 if check else 10e-6 + 15.625e-9, abs=1e-15)
    if not check:
        assert float(tran.options["noisefmin"]) == pytest.approx(100e3)
        assert "converted" not in captured_executor


@pytest.mark.parametrize("view,threads", (("hdl21gen", 8), ("frida1", 6)))
@pytest.mark.parametrize("check", (False, True))
def test_single_executor_modes(view, threads, check, captured_executor, pex_input, tmp_path):
    params = TbParams(
        view=view,
        pex_cell="" if view == "hdl21gen" else "adc_12b_17step",
        conversions=100,
    )
    root = tmp_path / "run"
    sim.simulate(
        params,
        root,
        pex_netlist=None if view == "hdl21gen" else pex_input,
        noise=True,
        check=check,
    )
    captured = captured_executor
    tran = next(attr for attr in captured["attrs"] if isinstance(attr, hs.Tran))
    assert tran.noise == (not check)
    assert float(tran.tstop) == pytest.approx(100e-9 if check else 16e-6 + 18.125e-9, abs=1e-15)
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
    params = TbParams(
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )
    sim.simulate(params, tmp_path / "run", check=check)
    tran = next(attr for attr in captured_executor["attrs"] if isinstance(attr, hs.Tran))
    assert not tran.noise
    assert float(tran.options["strobeperiod"]) == pytest.approx(params.waveform_sample_interval_s, abs=1e-18)
    assert float(tran.tstop) == pytest.approx(100e-9 if check else 151 * 160e-9 + 18.125e-9, abs=1e-15)
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
        sim.simulate(
            TbParams(view="frida1", pex_cell="adc_12b_17step"),
            tmp_path / "run",
            pex_netlist=pex_input,
            check=True,
        )
    assert "options" not in captured_executor


def test_missing_configured_pex_fails(captured_executor, tmp_path):
    with pytest.raises(FileNotFoundError):
        sim.simulate(
            TbParams(view="frida1", pex_cell="adc_12b_17step"),
            tmp_path / "run",
            pex_netlist=tmp_path / "missing.pex.netlist",
            check=True,
        )
    assert "options" not in captured_executor


def test_diagnostic_simulator_error_propagates(captured_executor, tmp_path):
    captured_executor["fail"] = True
    with pytest.raises(RuntimeError, match="simulator/license failure"):
        sim.simulate(TbParams(), tmp_path / "run", check=True)


@pytest.mark.parametrize(
    "target,warning,accepted",
    (
        ("frida1_2layer_radix17", "expected LVS mismatch: disconnected historical MOM layer", True),
        ("frida1_2layer_radix20", "expected LVS mismatch: disconnected historical MOM layer", True),
        ("frida1_1layer_radix17", "expected LVS mismatch: disconnected historical MOM layer", False),
        ("frida1_2layer_radix17", "unrelated mismatch", False),
    ),
)
def test_historical_lvs_exception_is_narrow(target, warning, accepted, captured_executor, pex_input, tmp_path):
    renamed = pex_input.with_name(f"{target}.pex.netlist")
    pex_input.rename(renamed)
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
    params = TbParams(view="frida1", pex_cell="adc_12b_17step")
    if accepted:
        sim.simulate(params, tmp_path / "run", **kwargs)
        assert captured_executor["options"]
    else:
        with pytest.raises(ValueError, match="unaccepted LVS"):
            sim.simulate(params, tmp_path / "run", **kwargs)


def test_sim_holds_no_private_wrapper_and_no_main():
    """The executor is ``simulate`` itself, and the named runs that call it are the sweep's
    (``flow.adc.sweep``): no flavor-specific private wrapper, no command line of its own; its private
    functions decode a run's raw output (``_decode``)."""
    functions = [
        name
        for name, value in vars(sim).items()
        if inspect.isfunction(value) and value.__module__ == sim.__name__ and name.startswith("_")
    ]
    assert sorted(functions) == ["_complete", "_decision_times", "_decode"]
    assert not hasattr(sim, "main")


# the sequencer's rows: simulator, serializer and saved-data timing


def test_continuous_sequence_reproduces_the_catalog_recipe() -> None:
    assert sim.AdcSequence.continuous(16) == sim.symbol160_init4_samp20_comp11110000_logic00001111


def test_rows_accept_whitespace_and_validate_lengths():
    row = "00001111 11110000\n01010101"
    sequence = sim.AdcSequence(row, row, row, row)
    assert sequence.comp == "000011111111000001010101"
    assert len(sequence.comp) == 24
    for bad in ("", "0000000", "0000000x", "0000000000000000"):
        with pytest.raises(ValueError):
            sim.AdcSequence("00000000", bad, "00000000", "00000000")


@pytest.mark.parametrize("name,sequence", sim.SEQUENCES)
@pytest.mark.parametrize("symbol_rate", (0.32e9, 0.96e9, 1.6e9))
def test_voltage_sources_and_serializer_consume_identical_rows(tsmc65, name, sequence, symbol_rate):
    params = TbParams(
        view="hdl21gen",
        symbol_rate=symbol_rate,
        seq_init_pattern=sequence.init,
        seq_samp_pattern=sequence.samp,
        seq_comp_pattern=sequence.comp,
        seq_logic_pattern=sequence.logic,
    )
    tb = sim.testbench(params)
    word_count = len(sequence.init) // 8
    memory = convert_params_to_seqgen_fmt(params, "0" * word_count)
    assert len(memory) == word_count * 8
    assert len(sequence.init) == (256 if name.startswith("symbol256_") else 160)
    for lane, signal in enumerate(("init", "samp", "comp", "logic")):
        row = getattr(sequence, signal)
        source = getattr(tb, f"vseq_{signal}").of.params
        assert source.data == row
        assert float(source.period) == pytest.approx(1 / symbol_rate)
        assert float(source.delay) == 0
        assert source.rptstart == 1 and source.rpttimes == -1
        recovered = "".join(str((memory[word * 8 + lane] >> bit) & 1) for word in range(word_count) for bit in range(8))
        assert recovered == row
    assert not any("phase" in field.name for field in fields(params))


@pytest.mark.parametrize("symbols,sequence", enumerate(timing_sequences, start=1))
def test_library_logic_rows_have_explicit_edge_separations(symbols, sequence):
    assert sequence.init == sim.symbol256_init8_samp16_comp11110000_logic00001111.init
    assert sequence.samp == sim.symbol256_init8_samp16_comp11110000_logic00001111.samp
    assert sequence.comp == sim.symbol256_init8_samp16_comp11110000_logic00001111.comp
    assert sequence.logic_timing == (8, symbols)


@pytest.mark.parametrize("name,sequence", duty_sequences)
def test_duty_rows_preserve_conversion_boundaries_and_pulse_edges(name, sequence):
    comp_word, logic_word = name.split("_comp")[1].split("_logic")
    symbols = int(name.split("_")[0].removeprefix("symbol"))
    assert sequence.init == "1111" + "0" * (symbols - 4)
    assert sequence.samp == "0000" + "1" * 20 + "0" * (symbols - 24)
    assert sequence.comp == "0" * 24 + comp_word * 17 + "0" * (symbols - 160)
    start = next(i for i in range(8) if logic_word[i] == "1" and logic_word[i - 1] == "0")
    width = logic_word.count("1")
    bits = np.array([int(bit) for bit in sequence.logic])
    rises = np.flatnonzero((bits == 1) & (np.roll(bits, 1) == 0))
    falls = np.flatnonzero((bits == 0) & (np.roll(bits, 1) == 1))
    init_logic_rise, init_logic_fall = (2, 6) if symbols == 160 else (3, 4)
    assert rises.tolist() == [init_logic_rise] + [24 + 8 * bit + start for bit in range(16)]
    assert falls.tolist() == [init_logic_fall] + [24 + 8 * bit + start + width for bit in range(16)]
    assert sequence.logic_timing == (8, start)


def test_duty_matrix_covers_every_pair_and_preserves_pause_only_changes():
    recipes = dict(duty_sequences)
    assert len(recipes) == len(duty_sequences) == 56
    assert set(recipes) == {
        f"symbol{symbols}_init4_samp20_comp{comp}_logic{logic}"
        for symbols in (160, 256)
        for comp in ("11110000", "11111000", "11111100", "11111110")
        for logic in ("00001111", "00000111", "00000011", "00000001", "10000111", "11000011", "11100001")
    }
    for name, short in duty_sequences[:28]:
        long = recipes[name.replace("symbol160_", "symbol256_")]
        for signal in ("init", "samp", "comp"):
            assert getattr(long, signal) == getattr(short, signal) + "0" * 96
        assert short.logic[:8] == "00111100"
        assert long.logic == "00010000" + short.logic[8:] + "0" * 96


def test_all_160_symbol_init_logic_pulses_span_symbols_two_through_five():
    short = tuple(sequence for name, sequence in sim.SEQUENCES if name.startswith("symbol160_init4_")) + (
        sim.symbol160_init4_samp24_comp11111100_logic00000010,
    )
    assert len(short) == 30
    for sequence in short:
        assert sequence.init[:8] == "11110000"
        assert sequence.logic[:8] == "00111100"


@pytest.mark.parametrize("name,sequence", sim.SEQUENCES)
def test_conversion_duration_uses_comp_word_and_survives_phase_advance(name, sequence):
    expected = 168 if name == "symbol256_init8_samp16_comp11111100_logic00000010" else 160
    assert sequence.conversion_symbols == expected
    for shift in range(len(sequence.init)):
        advanced = sequence.advance(shift)
        assert advanced.conversion_symbols == expected
        assert advanced.relative_to_init() == sequence.relative_to_init()
        assert advanced.advance(-shift) == sequence
    params = TbParams(**sequence.as_tb_fields())
    assert sim.AdcSequence.from_tb_params(params) == sequence


def test_conversion_rate_ignores_logic_and_idle_padding():
    assert {sequence.conversion_symbols for sequence in timing_sequences} == {160}
    for _, sequence in duty_sequences:
        assert 1.6e9 / sequence.conversion_symbols == 10e6
        assert len(sequence.init) / 1.6e9 == pytest.approx(100e-9 if len(sequence.init) == 160 else 160e-9)


def test_flat_catalogue_preserves_all_reviewed_channel_rows():
    import hashlib

    assert len(sim.SEQUENCES) == len(dict(sim.SEQUENCES)) == 65
    assert len({sequence for _, sequence in sim.SEQUENCES}) == 65
    for name, sequence in sim.SEQUENCES:
        assert getattr(sim, name) is sequence
        assert sequence.init[0] == "1" and sequence.init[-1] == "0"
    # Fingerprint of all reviewed relative timings, normalized to INIT rising.
    rows = "\n".join(
        name
        + ":"
        + ":".join(getattr(sequence.relative_to_init(), channel) for channel in ("init", "samp", "comp", "logic"))
        for name, sequence in sorted(sim.SEQUENCES)
    )
    assert (
        hashlib.sha256(rows.encode()).hexdigest() == "785b4bb014a0bbf5955edcef7dc7900e7fea4158c74d776a9eac6c7c687ba957"
    )


def test_continuous_catalogue_keeps_complete_terminal_comp_word():
    continuous = tuple(
        (name, sequence) for name, sequence in sim.SEQUENCES if name.startswith("symbol160_init4_samp20_")
    )
    assert len(continuous) == 29
    name, repaired = continuous[-1]
    assert name == "symbol160_init4_samp20_comp11111100_logic00000010"
    assert repaired.samp == sim.SEQUENCES[21][1].samp
    assert repaired.comp == sim.SEQUENCES[21][1].comp
    assert [index for index, bit in enumerate(repaired.logic) if bit == "1" and repaired.logic[index - 1] == "0"] == [
        2,
        *(30 + 8 * index for index in range(16)),
    ]
    for _name, sequence in continuous:
        last_rise = max(
            index for index, bit in enumerate(sequence.comp) if bit == "1" and sequence.comp[index - 1] == "0"
        )
        assert last_rise == 152
        assert sequence.comp[-8:] in {"11110000", "11111000", "11111100", "11111110"}


# A Spectre run's raw output decoded as conversions (``sim._decode``), and the probes it binds


def test_adc_waveform_conversion_writes_shared_hdf5(tmp_path: Path) -> None:
    expected_bout = "10110100101100101"
    time_step_s = 0.05e-9
    conversion_offsets_s = np.asarray([0.0, 170.0e-9])
    times_s = np.arange(0.0, 345.0e-9 + time_step_s / 2, time_step_s)
    comp_edge_times_s = np.concatenate(
        [offset_s + 5.0e-9 + np.arange(17) * 8.0e-9 for offset_s in conversion_offsets_s]
    )
    logic_edge_times_s = np.concatenate(
        [offset_s + 5.0e-9 + np.arange(16) * 8.0e-9 + 3.0e-9 for offset_s in conversion_offsets_s]
    )

    # The ADC has 17 comparator decisions but only 16 DAC-update/ LOGIC edges:
    # its final decision does not update the CDAC. Put each decision transition
    # at 97% of the COMP-to-LOGIC interval. The production LOGIC-edge sample
    # must decode the new bit, whereas an earlier 95% sample still sees the
    # preceding decision. B16 is retained until the next INIT LOGIC pulse.
    seq_comp_v = np.zeros_like(times_s)
    seq_logic_v = np.zeros_like(times_s)
    for edge_s in comp_edge_times_s:
        seq_comp_v[(times_s >= edge_s) & (times_s < edge_s + 0.5e-9)] = 1.2
    for edge_s in logic_edge_times_s:
        seq_logic_v[(times_s >= edge_s) & (times_s < edge_s + 0.5e-9)] = 1.2
    for edge_s in (1.5e-9, 171.5e-9, 341.5e-9):
        seq_logic_v[(times_s >= edge_s) & (times_s < edge_s + 0.25e-9)] = 1.2

    comp_out_v = np.zeros_like(times_s)
    repeated_bout = expected_bout * len(conversion_offsets_s)
    for decision_index, bit in enumerate(repeated_bout):
        transition_s = comp_edge_times_s[decision_index] + 0.97 * 3.0e-9
        stop_s = (
            comp_edge_times_s[decision_index + 1] + 0.97 * 3.0e-9
            if decision_index + 1 < len(repeated_bout)
            else times_s[-1] + time_step_s
        )
        comp_out_v[(times_s >= transition_s) & (times_s < stop_s)] = 1.2 * int(bit)

    raw_wave_names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times_s) for name in raw_wave_names}
    values.update(
        {
            "vin_p": np.full_like(times_s, 0.650),
            "vin_n": np.full_like(times_s, 0.600),
            "seq_init": np.where(
                ((times_s >= 1.0e-9) & (times_s < 2.0e-9))
                | ((times_s >= 171.0e-9) & (times_s < 172.0e-9))
                | ((times_s >= 341.0e-9) & (times_s < 342.0e-9)),
                1.2,
                0.0,
            ),
            "seq_comp": seq_comp_v,
            "seq_logic": seq_logic_v,
            "comp_out": comp_out_v,
            # Spectre voltage-source current is into the source positive
            # terminal, hence negative while each rail delivers current.
            "i(vdd_a)": np.full_like(times_s, -2.0e-6),
            "i(vdd_d)": np.full_like(times_s, -40.0e-6),
            "i(vdd_dac)": np.full_like(times_s, -20.0e-6),
        }
    )
    values = {
        "time": times_s,
        **values,
    }
    signal_names = {"time": "time", **{name: name for name in raw_wave_names}}
    signal_names["comp.latch_p"] = "latch_internal"
    values["latch_internal"] = np.full_like(times_s, 0.875)
    raw_path = tmp_path / "netlist.raw"
    raw_path.touch()

    params = TbParams(waveform_sample_interval_s=50e-12, conversions=2)
    h5_path = tmp_path / "adc.h5"
    expected = sim._decode(
        TranResult("tran", values, {}),
        params=params,
        raw_path=raw_path,
        signal_names={raw: alias for alias, raw in signal_names.items()},
    )
    write_measurement(h5_path, expected)
    raw_path.unlink()  # Newly written measurements must not need the original raw file.
    measurement = read_measurement(h5_path)
    assert measurement.wave is not None

    assert isinstance(measurement, MeasAdc)
    assert measurement.info.backend == "spice"
    assert measurement.info.readbacks["raw_format"] == "spectre_nutbin"
    assert measurement.info.readbacks["raw_max_timestep_s"] == pytest.approx(time_step_s)
    assert measurement.info.readbacks["waveform_sample_interval_s"] == pytest.approx(50e-12)
    assert measurement.info.readbacks["waveform_interpolated_from_coarser_raw"] is False
    assert measurement.info.readbacks["decision_sample_fraction"] == pytest.approx(1.0)
    assert measurement.info.readbacks["decision_time_reference"] == "seq_logic_rising_threshold_B0_B15"
    assert measurement.info.readbacks["final_decision_sample_fraction"] == pytest.approx(1.0)
    assert measurement.info.readbacks["final_decision_time_reference"] == "next_init_seq_logic_rising_threshold"
    assert measurement.info.readbacks["supply_power_available"] is True
    assert measurement.info.readbacks["supply_current_convention"] == "positive_current_draw"
    assert measurement.info.readbacks["vdd_d_active_average_power_w"] == pytest.approx(48.0e-6)
    assert len(measurement.conversion_index) == 2
    assert all("".join(str(bit) for bit in row) == expected_bout for row in measurement.bout)
    np.testing.assert_array_equal(measurement.bout[0, -2:], [0, 1])
    assert measurement.dout_raw[0] > 0
    assert measurement.dout[0] > 0
    assert measurement.vin_diff_v[0] == pytest.approx(0.050)
    np.testing.assert_array_equal(measurement.wave.record_index, [0, 1])
    assert measurement.wave.v["comp_out"].shape == (2, len(measurement.wave.time_s))
    np.testing.assert_allclose(np.diff(measurement.wave.time_s), 50e-12)
    assert measurement.wave.v["seq_init"][0, 0] == pytest.approx(0.0)
    np.testing.assert_allclose(measurement.wave.i["vdd_a"], 2.0e-6)
    np.testing.assert_allclose(measurement.wave.i["vdd_d"], 40.0e-6)
    np.testing.assert_allclose(measurement.wave.i["vdd_dac"], 20.0e-6)
    np.testing.assert_allclose(measurement.wave.v["comp.latch_p"], 0.875)
    assert measurement.wave.v["comp.latch_p"].shape == measurement.wave.v["comp_out"].shape


@pytest.mark.parametrize("before_v,after_v,expected_bit", [(0.3, 1.2, 1), (0.0, 0.9, 0)])
def test_adc_capture_uses_logic_threshold_not_early_fraction_or_later_sample(
    tmp_path: Path, before_v: float, after_v: float, expected_bit: int
) -> None:
    ticks = np.arange(4001)
    times_s = ticks * 0.05e-9
    names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times_s) for name in names}
    values["time"] = times_s
    values["seq_init"][20:40] = 1.2
    values["seq_init"][3000:3020] = 1.2
    values["seq_logic"][3030:3040] = 1.2
    for bit in range(17):
        start = 100 + 160 * bit
        values["seq_comp"][start : start + 10] = 1.2
        if bit < 16:
            values["seq_logic"][start + 60 : start + 70] = 1.2
    # First LOGIC threshold is halfway between ticks 159 and 160 (7.975 ns).
    # The first case resolves after the former 98% read but before LOGIC.
    # The second resolves after LOGIC but before the first above-threshold
    # clock sample, and must therefore still decode zero at the LOGIC edge.
    values["comp_out"][159] = before_v
    values["comp_out"][160:170] = after_v
    raw_path = tmp_path / "netlist.raw"
    raw_path.touch()
    result = sim._decode(
        TranResult("tran", values, {}),
        params=TbParams(waveform_sample_interval_s=50e-12, conversions=1),
        raw_path=raw_path,
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    assert result.bout[0, 0] == expected_bit
    np.testing.assert_array_equal(result.bout[0, 1:], np.zeros(16, dtype=np.uint8))


def test_adc_logic_capture_includes_last_conversion_tail(tmp_path: Path) -> None:
    (tmp_path / "original.raw").touch()
    times = np.arange(8626) * 25e-12
    names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times) for name in names}
    values["time"] = times
    for cycle in range(3):
        start = cycle * 4000
        values["seq_init"][start : start + 100] = 1.2
        values["seq_logic"][start + 75 : start + 100] = 1.2
        for bit in range(17 if cycle < 2 else 1):
            comp = start + 600 + bit * 200
            values["seq_comp"][comp : comp + 175] = 1.2
            if cycle < 2 and bit < 16:
                values["seq_logic"][comp + 175 : comp + 200] = 1.2
    for cycle in range(2):
        # Final output resolves after next INIT LOGIC, then changes at next B0.
        # Production decode must retain the earlier LOGIC value.
        begin = (cycle + 1) * 4000 + 200
        end = (cycle + 1) * 4000 + 600
        values["comp_out"][begin:end] = 1.2
        values["comp_out"][end] = 0.3
    result = sim._decode(
        TranResult("tran", values, {}),
        params=TbParams(waveform_sample_interval_s=50e-12, conversions=2),
        raw_path=tmp_path / "original.raw",
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    assert result.wave is not None
    assert result.param.conversions == 2
    np.testing.assert_array_equal(result.bout[:, :16], np.zeros((2, 16)))
    np.testing.assert_array_equal(result.bout[:, 16], [0, 0])
    np.testing.assert_array_equal(result.wave.record_index, [0, 1])
    assert result.info.readbacks["final_decision_time_reference"] == "next_init_seq_logic_rising_threshold"
    (tmp_path / "truncated.raw").touch()
    # Next COMP is unnecessary for production decode once next INIT LOGIC is saved.
    truncated = sim._decode(
        TranResult("tran", {name: value[:8400] for name, value in values.items()}, {}),
        params=TbParams(waveform_sample_interval_s=50e-12, conversions=2),
        raw_path=tmp_path / "truncated.raw",
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    np.testing.assert_array_equal(truncated.bout, result.bout)


def test_adc_continuous_records_require_next_init_logic(tmp_path: Path) -> None:
    """Sample B16 at next INIT LOGIC and exclude the final unavailable capture."""
    params = TbParams(
        waveform_sample_interval_s=50e-12,
        conversions=2,
        symbol_rate=1.6e9,
        seq_init_pattern="1111" + "0" * 156,
        seq_samp_pattern="0000" + "1" * 24 + "0" * 132,
        seq_comp_pattern="0" * 28 + "11111100" * 16 + "1111",
        seq_logic_pattern="0001" + "0" * 24 + "00000010" * 16 + "0000",
    )
    ticks = np.arange(16_001)
    times_s = ticks * 12.5e-12
    raw_names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times_s) for name in raw_names}
    values["time"] = times_s
    for name in ("init", "samp", "comp", "logic"):
        pattern = np.array([int(bit) for bit in getattr(params, f"seq_{name}_pattern")])
        values[f"seq_{name}"] = 1.2 * pattern[(ticks // 50) % 160]
    # B16 only resolves late in its shortened evaluation. Its output changes
    # after reset, before the old extrapolated 101.175 ns capture point.
    for offset in (0, 8_000):
        values["comp_out"][(ticks >= offset + 7_994) & (ticks < offset + 8_020)] = 1.2
    raw_path = tmp_path / "netlist.raw"
    raw_path.touch()
    measurement = sim._decode(
        TranResult("tran", values, {}),
        params=params,
        raw_path=raw_path,
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    assert measurement.wave is not None
    assert measurement.param.conversions == 1
    np.testing.assert_array_equal(measurement.bout[:, :16], np.zeros((1, 16)))
    np.testing.assert_array_equal(measurement.bout[:, 16], [0])
    np.testing.assert_array_equal(measurement.wave.record_index, [0])
    assert measurement.info.readbacks["unavailable_logic_conversions_json"] == "[1]"
    assert measurement.wave.v["comp_out"].shape == (1, len(measurement.wave.time_s))
    assert measurement.wave.time_s[-1] > 100e-9


def _adc_names(view):
    path = None if view == "hdl21gen" else Path(__file__).parent / "fixtures" / f"{view}_ports.scs"
    params = TbParams(
        waveform_sample_interval_s=50e-12, view=view, pex_cell="" if view == "hdl21gen" else "adc_12b_17step"
    )
    return sim.adc_signal_names(sim.testbench(params, pex_netlist=path), view)


def test_frida1_rc_waveforms_use_device_terminal_nodes() -> None:
    names = {alias: raw for raw, alias in _adc_names("frida1").items()}
    assert names["vdac_p"] == "xtop.xadc.N_VDAC_P_XXsampswitch_p/MM0_d"
    # the fabricated macro is C15 first
    assert names["dac_state_p[0]"].startswith("xtop.xadc.N_DAC_STATE_P_MAIN<15>_")


def test_extracted_waveforms_cover_every_dac_stage_and_comparator_nodes():
    names = {alias: raw for raw, alias in _adc_names("frida1").items()}
    assert len(names) == len(set(names.values()))
    for side in ("p", "n"):
        for kind in ("", "_diff"):
            for stage in range(16):
                for family in ("state", "botplate"):
                    node = names[f"dac_{family}_{side}{kind}[{stage}]"]
                    assert f"<{15 - stage}>_" in node
    assert names["comp.latch_p"].endswith("XXLATCH/MMM4_d")
    assert names["comp.latch_n"].endswith("XXLATCH/MMM3_d")
    assert names["comp.input_p_drain"].endswith("XXLATCH/MMM1_d")
    assert names["comp.input_n_drain"].endswith("XXLATCH/MMM2_d")


def test_generated_adc_map_covers_all_sixteen_capacitor_stages(tsmc65):
    """Every stage's state and both its bottom plates, which are the plates of the generated ADC's
    DAC's sides (``generated_net_aliases``); TSMC65 bound, as the runner binds it before it builds
    the testbench."""
    names = _adc_names("hdl21gen")
    for side in ("p", "n"):
        for stage in range(16):
            assert names[f"xtop.xadc.dac_state_{side}_{stage}"] == f"dac_state_{side}[{stage}]"
            assert names[f"xtop.xadc.xdac_{side}.main_{stage}"] == f"dac_botplate_{side}[{stage}]"
            assert names[f"xtop.xadc.xdac_{side}.diff_{stage}"] == f"dac_botplate_{side}_diff[{stage}]"
    assert not any("c16_" in alias for alias in names.values())


@pytest.mark.parametrize("fault", ("coarse", "nonfinite", "shape", "duplicate_alias", "unmapped", "missing"))
def test_converters_reject_invalid_transients_before_decoding(tmp_path, fault):
    times = np.arange(4) * 10e-12
    data = {"time": times, "raw": np.zeros(4)}
    names = {"time": "time", "raw": "vin_p"}
    if fault == "coarse":
        data["time"] = times * 2
    elif fault == "nonfinite":
        data["raw"][1] = np.nan
    elif fault == "shape":
        data["raw"] = np.zeros(3)
    elif fault == "duplicate_alias":
        names["raw"] = "time"
    elif fault == "unmapped":
        data["extra"] = np.zeros(4)
    else:
        names["missing"] = "vin_n"
    result = TranResult("tran", data, {})
    with pytest.raises(ValueError, match="Invalid transient"):
        sim._decode(result, params=TbParams(), raw_path=tmp_path / "unused.raw", signal_names=names)


def test_conversion_bodies_contain_no_inline_raises():
    import ast
    import inspect

    source = inspect.getsource(sim._decode)
    assert not any(isinstance(node, ast.Raise) for node in ast.walk(ast.parse(source)))


def test_adc_conversion_requires_one_complete_record():
    times = np.tile(np.arange(17, dtype=float), (2, 1))
    times[1, -1] = np.nan
    np.testing.assert_array_equal(sim._complete(times), [True, False])
    times[0, -1] = np.nan
    with pytest.raises(ValueError, match="No complete ADC conversions"):
        sim._complete(times)
