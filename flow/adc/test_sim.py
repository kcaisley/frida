"""Software-only checks for the native HDL21 ADC simulation interface."""

import inspect
import json
from dataclasses import fields
from io import StringIO
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest

from flow import capdac
from flow.scans.seqgen import convert_params_to_seqgen_fmt
from flow.util.netlist import subcircuit_ports

from . import sim
from .params import Params, TbParams

PEX_FIXTURES = {view: Path(__file__).parent / "fixtures" / f"{view}_ports.scs" for view in ("frida1", "frida2")}
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
            TbParams(view="frida2", pex_cell="adc_12b_17step"),
            tmp_path / "simulation",
            pex_netlist=path,
            check=True,
        )


def test_adc_testbench_parameters_are_simulation_only() -> None:
    params = TbParams()

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
def test_adc_testbench_generates_each_view(view: str) -> None:
    tb = sim.testbench(
        TbParams(view=view, conversions=1, pex_cell="adc_12b_17step" if view == "frida1" else ""),
        pex_netlist=PEX_FIXTURES.get(view),
    )

    assert isinstance(tb, h.Module)
    assert tb.xadc is not None
    assert tb.dac_astate_p.width == 16
    assert tb.vin_p is not None


def test_adc_transfer_staircase_has_151_codes() -> None:
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
def test_sweep_validation_agrees_with_generated_waveform(start, stop, step, count):
    params = TbParams(conversions=count, vin_diff=hs.LinearSweep(start=start, stop=stop, step=step))
    assert sim.is_valid_adc_tb_params(params) is True
    wave = sim.testbench(params).vvin_diff.of.params.wave
    assert len(wave.points) == 2 * count


@pytest.mark.parametrize("view", ("frida1", "frida2"))
def test_extracted_adc_keeps_calibre_port_order(view) -> None:
    tb = sim.testbench(TbParams(view=view, pex_cell="adc_12b_17step"), pex_netlist=PEX_FIXTURES[view])
    names = tuple(port.name for port in tb.xadc.of.module.port_list)
    assert names == PEX_PINS[view]
    assert len(names) == 84


def test_pex_header_reordering_changes_instance_order_without_swapping_nets(tmp_path):
    pins = list(PEX_PINS["frida2"])
    pins[0], pins[1] = pins[1], pins[0]
    path = tmp_path / "reordered.scs"
    path.write_text(f"subckt adc_12b_17step ({' '.join(pins)})\nends adc_12b_17step\n")
    tb = sim.testbench(TbParams(view="frida2", pex_cell="adc_12b_17step"), pex_netlist=path)
    assert tuple(tb.xadc.of.module.ports) == tuple(pins)
    assert tb.xadc.conns["vin_p"] is tb.vin_p
    assert tb.xadc.conns["vdd_a"] is tb.vdd_a
    path.write_text(path.read_text().replace("dac_astate_p_0", "dac_astate_p<1>"))
    with pytest.raises(ValueError, match="Duplicate external pins"):
        sim.testbench(TbParams(view="frida2", pex_cell="adc_12b_17step"), pex_netlist=path)


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


def test_c0_rename_preserves_the_physical_initialization_voltages() -> None:
    for bus in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
        pattern = tuple(int(stage in (0, 3, 8, 14)) for stage in range(16))
        old = sim.testbench(
            TbParams(view="frida1", pex_cell="adc_12b_17step", **{bus: pattern}),
            pex_netlist=PEX_FIXTURES["frida1"],
        )
        new = sim.testbench(
            TbParams(view="frida2", pex_cell="adc_12b_17step", **{bus: pattern}),
            pex_netlist=PEX_FIXTURES["frida2"],
        )
        for stage, state in enumerate(pattern):
            assert float(getattr(old, f"v{bus}_{stage}").of.params.dc) == pytest.approx(1.2 * state)
            old_net = old.xadc.conns[f"{bus}_{15 - stage}"]
            new_net = new.xadc.conns[f"{bus}_{stage}"]
            assert old_net.parent is old.namespace[bus] and old_net.index == stage
            assert new_net.parent is new.namespace[bus] and new_net.index == stage
            assert float(getattr(new, f"v{bus}_{stage}").of.params.dc) == pytest.approx(1.2 * state)


def test_all_adc_views_expose_the_same_analysis_waveforms():
    observations = []
    for view in ("hdl21gen", "frida1", "frida2"):
        pex = PEX_FIXTURES.get(view)
        tb = sim.testbench(TbParams(view=view, pex_cell="adc_12b_17step" if pex else ""), pex_netlist=pex)
        observations.append(set(sim.adc_signal_names(tb, view).values()))
    assert observations[0] == observations[1] == observations[2]
    for side in ("p", "n"):
        for kind in ("", "_diff"):
            for stage in range(16):
                assert f"dac_botplate_{side}{kind}[{stage}]" in observations[0]


@pytest.mark.parametrize("fault", ("missing", "duplicate"))
def test_pex_observations_reject_incomplete_or_ambiguous_bindings(monkeypatch, fault):
    tb = sim.testbench(TbParams(view="frida2", pex_cell="adc_12b_17step"), pex_netlist=PEX_FIXTURES["frida2"])
    aliases = sim.frida2_net_aliases()
    if fault == "missing":
        del aliases[sim.AdcNets.vdac_p]
    else:
        aliases[sim.AdcNets.vdac_p] = aliases[sim.AdcNets.vdac_n]
    monkeypatch.setattr(sim, "frida2_net_aliases", lambda: aliases)
    with pytest.raises((KeyError, ValueError)):
        sim.adc_signal_names(tb, "frida2")


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
def captured_executor(monkeypatch):
    from types import SimpleNamespace

    from flow.analysis import io
    from flow.circuit import results
    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

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


@pytest.mark.parametrize("view,threads", (("hdl21gen", 8), ("frida2", 8), ("frida1", 6)))
@pytest.mark.parametrize("check", (False, True))
def test_single_executor_modes(view, threads, check, captured_executor, pex_input, tmp_path):
    if view == "frida1":
        ports = " ".join(PEX_PINS["frida1"])
        pex_input.write_text(f"subckt adc_12b_17step ({ports})\ninternal\nends adc_12b_17step\n")
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
            TbParams(view="frida2", pex_cell="adc_12b_17step"),
            tmp_path / "run",
            pex_netlist=pex_input,
            check=True,
        )
    assert "options" not in captured_executor


def test_missing_configured_pex_fails(captured_executor, tmp_path):
    with pytest.raises(FileNotFoundError):
        sim.simulate(
            TbParams(view="frida2", pex_cell="adc_12b_17step"),
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
    params = TbParams(view=view, pex_cell="adc_12b_17step")
    if accepted:
        sim.simulate(params, tmp_path / "run", **kwargs)
        assert captured_executor["options"]
    else:
        with pytest.raises(ValueError, match="unaccepted LVS"):
            sim.simulate(params, tmp_path / "run", **kwargs)


def test_sim_holds_no_private_function_and_no_main():
    """The executor is ``simulate`` itself, and the named runs that call it are the sweep's
    (``flow.adc.sweep``): no flavor-specific private wrapper, no command line of its own."""
    functions = [
        name
        for name, value in vars(sim).items()
        if inspect.isfunction(value) and value.__module__ == sim.__name__ and name.startswith("_")
    ]
    assert functions == []
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
def test_voltage_sources_and_serializer_consume_identical_rows(name, sequence, symbol_rate):
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
