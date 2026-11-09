"""Software-only checks of the ADC's runs (``flow.adc.sim``): the testbench of each top, the Spectre
run's mechanics (Spectre not run), the probes, the reader and the raw decode, and the behavioral
converter (its SAR loop and the stimulus it sees). A test that builds the generated view's
testbench binds TSMC65 (``tsmc65``), as ``sim.simulate`` does; a PDK-free checkout skips it. A
fabricated converter's extraction is the fixture header (``extraction``), or a signed-off layout's
entry stood in for ``flow.sweep.lookup.laid_out``."""

import importlib
import inspect
import json
import math
from dataclasses import fields, replace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest
from vlsirtools.spice.sim_data import TranResult

import flow.capdac.model as capdac_model
import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow import capdac
from flow.analysis.io import read_measurement, write_measurement
from flow.analysis.types import MeasAdc
from flow.circuit.ports import waveform_net_names
from flow.scans.seqgen import convert_params_to_seqgen_fmt
from flow.util.netlist import subcircuit_ports

from . import sim
from .params import (
    DECAP_COVERAGE,
    DRAWN_PERCENTILE,
    DRAWN_RUN,
    Extraction,
    Fabricated,
    Params,
    Probes,
    Quiet,
    Recipe,
    Simulator,
    TbParams,
)
from .subckt import Nets

PEX_FIXTURES = {"frida1": Path(__file__).parent / "fixtures" / "frida1_ports.scs"}
PEX_PINS = {view: subcircuit_ports(path.read_text(), "adc_12b_17step") for view, path in PEX_FIXTURES.items()}

# the recipes of the catalogue (``Recipe``, the historical samp24 one left out of it, last)
_catalogue = tuple(Recipe)[:-1]


def _entry(path: Path, *, lvs_correct: bool = True, warnings: tuple[str, ...] = (), sha256=None) -> dict:
    """A layout entry signed off by its own ``lay_out`` (the layout steps' record of it) whose
    extraction is ``path``."""
    return {
        "gds": "unused.gds",
        "signoff": "lay_out",
        "lvs_correct": lvs_correct,
        "warnings": list(warnings),
        "pex": {"netlist": str(path), "sha256": sha256},
    }


@pytest.fixture
def extraction(monkeypatch):
    """Every fabricated converter's extraction the fixture header, its cell ``adc_12b_17step``."""
    monkeypatch.setattr(sim, "_extraction", lambda tb: (PEX_FIXTURES["frida1"], "adc_12b_17step"))


def _gen(params: Params | None = None, **fields) -> TbParams:
    """A Spectre run of the generated converter (``params``, FRIDA-1's sizing where None) in TSMC65."""
    return TbParams(pdk="tsmc65", params=Params() if params is None else params, simulator=Simulator.SPECTRE, **fields)


def _frida1(
    fabricated: Fabricated = Fabricated.FRIDA1_1LAYER_RADIX17, extraction: Extraction = Extraction.SIGNOFF, **fields
) -> TbParams:
    """A Spectre run of a fabricated converter's extraction (its layout's signoff, cell
    adc_12b_17step, by default)."""
    return TbParams(
        pdk="tsmc65", params=fabricated.params, simulator=Simulator.SPECTRE, extraction=extraction, **fields
    )


@pytest.mark.parametrize("fault", ("ideal_capacitor", "changed_pex"))
def test_extracted_simulation_rejects_double_counting_and_changed_signed_input(tmp_path, monkeypatch, fault):
    pytest.importorskip("pdk.tsmc65.calibre.ringfmom")  # the kit's check of an extracted netlist
    path = tmp_path / "adc.pex.netlist"
    path.write_text("X0 (a b s) ringfmom_3layer c=1f\n" if fault == "ideal_capacitor" else "C0 (a b) capacitor c=1f\n")
    monkeypatch.setattr(sim.lookup, "laid_out", lambda *_: _entry(path, sha256="not-the-current-content"))
    monkeypatch.setattr(h.pdk, "compile", lambda *_: pytest.fail("invalid PEX reached simulation compilation"))
    with pytest.raises(ValueError, match="double-count" if fault == "ideal_capacitor" else "PEX content"):
        sim.simulate(_frida1(check=True), tmp_path / "simulation")


def test_adc_testbench_parameters_are_simulation_only() -> None:
    params = _gen()

    assert sim._runnable(params) is True
    assert params.params.fabricated is None and params.extraction is None
    # FRIDA-1's extracted view switches its difference plates either way
    assert sim._runnable(replace(_frida1(), dac_diffcaps=0)) is True
    assert float(params.vin_cm.dc) == pytest.approx(0.7)
    assert not hasattr(params, "temperature_c")
    assert not hasattr(params, "board_id")
    assert not hasattr(params, "campaign")
    assert not hasattr(params, "vdd_io")


def _rows(**changed: str) -> tuple[str, ...]:
    """The default rows with some (by name: init, samp, comp, logic) changed."""
    rows = dict(zip(("init", "samp", "comp", "logic"), _gen().rows, strict=True)) | changed
    return tuple(rows.values())


@pytest.mark.parametrize(
    "build",
    (
        # an extraction is a fabricated converter's, which a Spectre run of it requires
        lambda: TbParams(pdk="tsmc65", params=Params(), simulator=Simulator.SPECTRE, extraction=Extraction.SIGNOFF),
        lambda: TbParams(pdk="tsmc65", params=Fabricated.FRIDA1_1LAYER_RADIX17.params, simulator=Simulator.SPECTRE),
        lambda: TbParams(pdk="tsmc65", params=Fabricated.FRIDA1_1LAYER_RADIX17.params, extraction=Extraction.TAPEOUT),
        # the behavioral knobs are a behavioral run's, the Spectre options a Spectre run's
        lambda: _gen(unit_mismatch=0.01),
        lambda: _gen(drawn=True),
        lambda: TbParams(pdk="tsmc65", params=Params(), transient_noise=True),
        # a DAC state a capacitor: the array's stage count
        lambda: _gen(params=Params(cdac=capdac.Params(extra=4))),
        lambda: _gen(conversions=0),
        lambda: _gen(symbol_rate=0.0),
        lambda: _gen(symbol_rate=h.Literal("rate")),
        lambda: _gen(vdd_a=h.Vdc.Params(dc=None)),
        lambda: _gen(vin_cm=h.Vdc.Params(dc=h.Literal("nan"))),
        lambda: _gen(supply_series_resistance_ohm=-1.0),
        lambda: _gen(supply_series_resistance_ohm=1.0),
        lambda: _gen(supply_series_inductance_h=float("inf")),
        lambda: _gen(supply_noise_rms_v=(0.0, 0.0)),
        lambda: _gen(supply_noise_rms_v=(0.0, -1.0, 0.0)),
        lambda: _gen(supply_noise_rms_v=(0.0, float("nan"), 0.0)),
        lambda: _gen(supply_noise_bandwidth_hz=0.0),
        lambda: _gen(en_comp=2),
        lambda: _gen(dac_astate_p=(0,) * 15),
        lambda: _gen(dac_bstate_n=(2,) * 16),
        lambda: _gen().sequenced(_rows(samp="")),
        lambda: _gen().sequenced(_rows(comp="x" * len(_gen().seq_comp.data))),
        lambda: _gen().sequenced(_rows(logic="01")),
        lambda: _gen().sequenced(("010",) * 4),
        # a line plays a symbol a period of the run's rate, repeated from the start
        lambda: replace(_gen(), symbol_rate=0.32e9),
        lambda: replace(_gen(), seq_comp=replace(_gen().seq_comp, rpttimes=0)),
        lambda: _gen(vin_diff=hs.LinearSweep(start=0, stop=1, step=0)),
        lambda: _gen(vin_diff=hs.LinearSweep(start=0, stop=1, step=-0.1)),
        lambda: _gen(conversions=1, vin_diff=hs.LinearSweep(start=0, stop=1e-12, step=-1)),
        lambda: _gen(conversions=2, vin_diff=hs.LinearSweep(start=0, stop=1, step=1)).sequenced(symbol_rate=1e15),
    ),
)
def test_invalid_params_are_refused_when_built(build):
    with pytest.raises((ValueError, TypeError)):
        build()


@pytest.mark.parametrize(
    "params",
    (
        # the generated ADC wires its subtraction in: no run of it adds the difference plates
        _gen(dac_diffcaps=0),
        # one COMP pulse a decision: an array of 15 stages takes 16
        _gen(
            params=Params(cdac=capdac.Params(extra=4)),
            **{name: (0,) * 15 for name in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n")},
        ),
    ),
)
def test_a_run_its_top_cannot_convert_fails_before_testbench_generation_or_run(params, monkeypatch, tmp_path):
    assert sim._runnable(params) is False
    monkeypatch.setattr(sim, "testbench_from_ports", lambda *a, **kw: pytest.fail("invalid params reached generation"))
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.testbench(params)
    monkeypatch.setattr(sim, "testbench", lambda *a, **kw: pytest.fail("runner passed invalid params to testbench"))
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.simulate(params, tmp_path / "run")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("view", ("frida1", "hdl21gen"))
def test_adc_testbench_generates_each_view(view: str, request: pytest.FixtureRequest, extraction) -> None:
    if view == "hdl21gen":
        request.getfixturevalue("tsmc65")
    tb = sim.testbench(_frida1(conversions=1) if view == "frida1" else _gen(conversions=1))

    assert isinstance(tb, h.Module)
    assert tb.xadc is not None
    assert tb.dac_astate_p.width == 16
    assert tb.vin_p is not None


def test_each_generated_testbench_holds_a_fresh_adc(tsmc65) -> None:
    """The ADC's DAC is resolved to the PDK's devices in place, and a compile swaps a hierarchy's
    devices in place: each testbench holds its own ADC and DAC, so neither touches another's."""
    first, second = sim.testbench(_gen()), sim.testbench(_gen())
    assert first.xadc.of is not second.xadc.of
    assert first.xadc.of.xdac_p.of is not second.xadc.of.xdac_p.of


def test_adc_transfer_staircase_has_151_codes(tsmc65) -> None:
    params = _gen(conversions=151, vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01))
    tb = sim.testbench(params)
    wave = tb.vvin_diff.of.params.wave

    assert isinstance(wave, h.Pwl)
    assert len(wave.points) == 302
    assert float(wave.points[0][1]) == pytest.approx(-0.75)
    assert float(wave.points[1][0]) == pytest.approx(len(params.seq_init.data) / float(params.symbol_rate) - 100e-12)
    assert float(wave.points[-1][1]) == pytest.approx(0.75)
    assert float(wave.points[-1][0]) == pytest.approx(
        params.conversions * len(params.seq_init.data) / float(params.symbol_rate)
    )


def test_adc_transfer_sweep_must_match_conversion_count() -> None:
    """A staircase of other than a level a conversion is refused where its testbench is built; a run
    decoded to its complete conversions alone (``_decode``) holds the staircase it ran."""
    tb = _gen(conversions=2, vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01))
    assert not sim._runnable(tb)
    # nor a step that does not reach its stop in whole levels
    assert not sim._runnable(_gen(conversions=4, vin_diff=hs.LinearSweep(start=0, stop=1, step=0.3)))
    with pytest.raises(ValueError, match="Invalid ADC testbench params"):
        sim.testbench(tb)
    ramp = _gen(conversions=151, vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01))
    assert sim._runnable(ramp) and replace(ramp, conversions=150).conversions == 150


@pytest.mark.parametrize("start,stop,step,count", ((-0.75, 0.75, 0.01, 151), (1, -1, -0.1, 21), (0, 0, 1, 1)))
def test_sweep_validation_agrees_with_generated_waveform(tsmc65, start, stop, step, count):
    params = _gen(conversions=count, vin_diff=hs.LinearSweep(start=start, stop=stop, step=step))
    assert sim._runnable(params) is True
    wave = sim.testbench(params).vvin_diff.of.params.wave
    assert len(wave.points) == 2 * count


def test_extracted_adc_keeps_calibre_port_order(extraction) -> None:
    tb = sim.testbench(_frida1())
    names = tuple(port.name for port in tb.xadc.of.module.port_list)
    assert names == PEX_PINS["frida1"]
    assert len(names) == 84


def test_pex_header_reordering_changes_instance_order_without_swapping_nets(tmp_path, monkeypatch):
    pins = list(PEX_PINS["frida1"])
    pins[0], pins[1] = pins[1], pins[0]
    path = tmp_path / "reordered.scs"
    path.write_text(f"subckt adc_12b_17step ({' '.join(pins)})\nends adc_12b_17step\n")
    monkeypatch.setattr(sim, "_extraction", lambda tb: (path, "adc_12b_17step"))
    tb = sim.testbench(_frida1())
    assert tuple(tb.xadc.of.module.ports) == tuple(pins)
    assert tb.xadc.conns["vin_p"] is tb.vin_p
    assert tb.xadc.conns["vdd_a"] is tb.vdd_a
    path.write_text(path.read_text().replace("dac_astate_p_0", "dac_astate_p<1>"))
    with pytest.raises(ValueError, match="Duplicate external pins"):
        sim.testbench(_frida1())


@pytest.mark.parametrize(
    "fabricated,extraction,pex_cell",
    (
        (Fabricated.FRIDA1_1LAYER_RADIX17, Extraction.TAPEOUT, "adc_1layer_radix17"),
        (Fabricated.FRIDA1_1LAYER_RADIX20, Extraction.TAPEOUT, "adc_1layer_radix20"),
        (Fabricated.FRIDA1_2LAYER_RADIX17, Extraction.TAPEOUT, "adc_2layer_radix17"),
        (Fabricated.FRIDA1_2LAYER_RADIX20, Extraction.TAPEOUT, "adc_2layer_radix20"),
        (Fabricated.FRIDA1_2LAYER_RADIX20, Extraction.SIGNOFF, "adc_12b_17step"),
    ),
)
def test_extracted_adc_selects_its_extractions_cell(
    fabricated, extraction, pex_cell: str, tmp_path, monkeypatch
) -> None:
    """The tape-out's extraction of a flavor is the kit's (``site.FRIDA1``), its cell the flavor's;
    the signoff's is its layout's (``laid_out``), its cell its layout's top."""
    site = pytest.importorskip("pdk.tsmc65.hdl21.site")
    monkeypatch.setattr(site, "FRIDA1", tmp_path)
    path = tmp_path / (f"{pex_cell}.pex.netlist" if extraction is Extraction.TAPEOUT else "signed.pex.netlist")
    path.write_text(PEX_FIXTURES["frida1"].read_text().replace("adc_12b_17step", pex_cell))
    monkeypatch.setattr(sim.lookup, "laid_out", lambda *_: _entry(path))
    tb = _frida1(fabricated, extraction, conversions=1)

    assert sim._extraction(tb) == (path, pex_cell)
    assert sim.testbench(tb).xadc.of.module.name == pex_cell


def test_an_extraction_without_its_cell_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(sim, "_extraction", lambda tb: (PEX_FIXTURES["frida1"], "adc_1layer_radix17"))
    with pytest.raises(ValueError, match="no .subckt adc_1layer_radix17"):
        sim.testbench(_frida1(extraction=Extraction.TAPEOUT, conversions=1))


def test_a_generated_converter_has_no_extraction() -> None:
    with pytest.raises(ValueError, match="no extraction"):
        sim._extraction(_gen())


def test_a_fabricated_converters_behavioral_testbench_holds_its_black_box() -> None:
    """Outside Spectre its top is its netlist's black box (``subckt._fabricated``): no extraction."""
    tb = TbParams(pdk="tsmc65", params=Fabricated.FRIDA1_2LAYER_RADIX20.params, conversions=1)
    bench = sim.testbench(tb)
    assert bench.xadc.of.module.name == "adc_12b_17step"
    assert tuple(port.name for port in bench.xadc.of.module.port_list) == PEX_PINS["frida1"]


def test_the_fabricated_bus_order_preserves_the_physical_initialization_voltages(extraction) -> None:
    # FRIDA-1's macro is C15 first: its pin <15 - stage> carries stage's state
    for bus in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
        pattern = tuple(int(stage in (0, 3, 8, 14)) for stage in range(16))
        tb = sim.testbench(_frida1(**{bus: pattern}))
        for stage, state in enumerate(pattern):
            assert float(getattr(tb, f"v{bus}_{stage}").of.params.dc) == pytest.approx(1.2 * state)
            net = tb.xadc.conns[f"{bus}_{15 - stage}"]
            assert net.parent is tb.namespace[bus] and net.index == stage


def test_all_adc_views_expose_the_same_analysis_waveforms(tsmc65, extraction):
    observations = []
    for params in (_gen(), _frida1()):
        observations.append(set(sim._probes(sim.testbench(params), params).values()))
    assert observations[0] == observations[1]
    for side in ("p", "n"):
        for kind in ("", "_diff"):
            for stage in range(16):
                assert f"dac_botplate_{side}{kind}[{stage}]" in observations[0]


@pytest.mark.parametrize("fault", ("missing", "duplicate"))
def test_pex_observations_reject_incomplete_or_ambiguous_bindings(monkeypatch, fault, extraction):
    tb = sim.testbench(_frida1())
    aliases = sim._frida1_terminals()
    if fault == "missing":
        del aliases[sim.Nets.vdac_p]
    else:
        aliases[sim.Nets.vdac_p] = aliases[sim.Nets.vdac_n]
    monkeypatch.setattr(sim, "_frida1_terminals", lambda: aliases)
    with pytest.raises((KeyError, ValueError)):
        sim._probes(tb, _frida1())


def test_supply_noise_testbench_repeats_independent_rail_networks(extraction) -> None:
    params = _frida1(
        conversions=1,
        supply_series_resistance_ohm=1.0,
        supply_series_inductance_h=1e-9,
        supply_decoupling_capacitance_f=1e-12,
        supply_noise_rms_v=(1e-3, 0.0, 0.0),
        supply_noise_bandwidth_hz=25e9,
    )
    tb = sim.testbench(params)
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
        "_probes",
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
def pex_input(tmp_path, monkeypatch):
    """A signed-off extraction (the layout's entry, ``laid_out``'s, stood in for)."""
    pex = tmp_path / "frida1_1layer_radix17.pex.netlist"
    ports = " ".join(PEX_PINS["frida1"])
    pex.write_text(f"subckt adc_12b_17step ({ports})\ninternal\nends adc_12b_17step\n")
    monkeypatch.setattr(sim.lookup, "laid_out", lambda *_: _entry(pex))
    return pex


@pytest.mark.parametrize("check", (False, True))
def test_logic_capture_saves_tail_without_changing_noise_bandwidth(check, captured_executor, tmp_path):
    params = _gen(conversions=100, transient_noise=True, check=check).sequenced(
        (
            "1111" + "0" * 156,
            "0000" + "1" * 20 + "0" * 136,
            "0" * 24 + "11111110" * 17,
            "0001" + "0" * 20 + "00000001" * 16 + "0" * 8,
        )
    )
    sim.simulate(params, tmp_path / "run")
    tran = next(attr for attr in captured_executor["attrs"] if isinstance(attr, hs.Tran))
    assert float(tran.tstop) == pytest.approx(100e-9 if check else 10e-6 + 15.625e-9, abs=1e-15)
    if not check:
        assert float(tran.options["noisefmin"]) == pytest.approx(100e3)
        assert "converted" not in captured_executor


@pytest.mark.parametrize("view,threads", (("hdl21gen", 8), ("frida1", 6)))
@pytest.mark.parametrize("check", (False, True))
def test_single_executor_modes(view, threads, check, captured_executor, pex_input, tmp_path):
    params = (_gen if view == "hdl21gen" else _frida1)(conversions=100, transient_noise=True, check=check)
    root = tmp_path / "run"
    sim.simulate(params, root)
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
    assert json.loads((root / "names.json").read_text()) == {
        "time": "time_s",
        "xtop.comp_out": "comp_out_v",
        "xtop.xadc.internal": "internal_v",
    }
    assert metadata["spectre_threads"] == threads
    assert metadata["transient_noise"] == (not check)
    if view != "hdl21gen":
        import hashlib

        assert metadata["pex_sha256"] == hashlib.sha256(pex_input.read_bytes()).hexdigest()


@pytest.mark.parametrize("check", (False, True))
def test_transfer_executor_enforces_waveform_resolution(check, captured_executor, tmp_path):
    params = _gen(conversions=151, vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01), check=check)
    sim.simulate(params, tmp_path / "run")
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
        ("changed", "PEX content"),
    ),
)
def test_executor_rejects_bad_pex(fault, message, captured_executor, pex_input, tmp_path, monkeypatch):
    if fault == "ports":
        pex_input.write_text(pex_input.read_text().replace("vdd_a vin_p", "vdd_typo vin_p"))
    elif fault == "nodes":
        pex_input.write_text(pex_input.read_text().replace("\ninternal\n", "\n"))
    elif fault == "header":
        pex_input.write_text("subckt other ()\nends other\n")
    elif fault == "lvs":
        monkeypatch.setattr(sim.lookup, "laid_out", lambda *_: _entry(pex_input, lvs_correct=False))
    else:
        monkeypatch.setattr(sim.lookup, "laid_out", lambda *_: _entry(pex_input, sha256="0" * 64))
    with pytest.raises(ValueError, match=message):
        sim.simulate(_frida1(check=True), tmp_path / "run")
    assert "options" not in captured_executor


def test_missing_configured_pex_fails(captured_executor, tmp_path, monkeypatch):
    monkeypatch.setattr(sim.lookup, "laid_out", lambda *_: _entry(tmp_path / "missing.pex.netlist"))
    with pytest.raises(FileNotFoundError):
        sim.simulate(_frida1(check=True), tmp_path / "run")
    assert "options" not in captured_executor


def test_diagnostic_simulator_error_propagates(captured_executor, tmp_path):
    captured_executor["fail"] = True
    with pytest.raises(RuntimeError, match="simulator/license failure"):
        sim.simulate(_gen(check=True), tmp_path / "run")


@pytest.mark.parametrize(
    "target,warning,accepted",
    (
        ("frida1_2layer_radix17", "expected LVS mismatch: disconnected historical MOM layer", True),
        ("frida1_2layer_radix20", "expected LVS mismatch: disconnected historical MOM layer", True),
        ("frida1_1layer_radix17", "expected LVS mismatch: disconnected historical MOM layer", False),
        ("frida1_2layer_radix17", "unrelated mismatch", False),
    ),
)
def test_historical_lvs_exception_is_narrow(
    target, warning, accepted, captured_executor, pex_input, tmp_path, monkeypatch
):
    renamed = pex_input.with_name(f"{target}.pex.netlist")
    pex_input.rename(renamed)
    monkeypatch.setattr(sim.lookup, "laid_out", lambda *_: _entry(renamed, lvs_correct=False, warnings=(warning,)))
    # the two-layer flavors' signoff keeps the historical disconnect (TbParams.expected_disconnect)
    params = _frida1(Fabricated[target.upper()], check=True)
    if accepted:
        sim.simulate(params, tmp_path / "run")
        assert captured_executor["options"]
    else:
        with pytest.raises(ValueError, match="unaccepted LVS"):
            sim.simulate(params, tmp_path / "run")


def test_sim_holds_no_private_wrapper_and_no_main():
    """The executor is ``simulate`` itself, and the runs that call it are the sweep's
    (``flow.adc.runs``): no flavor-specific private wrapper, no command line of its own; its private
    functions find a run's top and probes, decode a run's raw output (``_decode``) and make up the
    behavioral converter."""
    functions = [
        name
        for name, value in vars(sim).items()
        if callable(value)
        and getattr(value, "__module__", None) == sim.__name__
        and name.startswith("_")
        and not isinstance(value, type)
    ]
    assert sorted(functions) == [
        "_bit_value",
        "_capture",
        "_checked",
        "_complete",
        "_convert",
        "_converter",
        "_decision_times",
        "_decision_windows",
        "_decode",
        "_extraction",
        "_interface_wave",
        "_probes",
        "_pwl_value",
        "_rising",
        "_runnable",
        "_salogic",
        "_sequence_times",
        "_signed_off",
        "_source_value",
    ]
    assert not hasattr(sim, "main")


# the sequencer's rows: the testbench's bit sources and the serializer play the same


@pytest.mark.parametrize("recipe", _catalogue, ids=lambda recipe: recipe.name.lower())
@pytest.mark.parametrize("symbol_rate", (0.32e9, 0.96e9, 1.6e9))
def test_voltage_sources_and_serializer_consume_identical_rows(tsmc65, recipe, symbol_rate):
    params = _gen().sequenced(recipe.rows, symbol_rate=symbol_rate)
    tb = sim.testbench(params)
    word_count = len(recipe.rows[0]) // 8
    memory = convert_params_to_seqgen_fmt(params, "0" * word_count)
    assert len(memory) == word_count * 8
    assert len(recipe.rows[0]) == (256 if recipe.name.startswith("SYMBOL256_") else 160)
    for lane, (signal, row) in enumerate(zip(("init", "samp", "comp", "logic"), recipe.rows, strict=True)):
        source = getattr(tb, f"vseq_{signal}").of.params
        assert source == getattr(params, f"seq_{signal}")
        assert source.data == row
        assert float(source.period) == pytest.approx(1 / symbol_rate)
        assert float(source.delay) == 0
        assert source.rptstart == 1 and source.rpttimes == -1
        recovered = "".join(str((memory[word * 8 + lane] >> bit) & 1) for word in range(word_count) for bit in range(8))
        assert recovered == row
    assert not any("phase" in field.name for field in fields(params))


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

    raw_wave_names = waveform_net_names(Nets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
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

    params = _gen(waveform_sample_interval_s=50e-12, conversions=2)
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
    names = waveform_net_names(Nets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
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
        params=_gen(waveform_sample_interval_s=50e-12, conversions=1),
        raw_path=raw_path,
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    assert result.bout[0, 0] == expected_bit
    np.testing.assert_array_equal(result.bout[0, 1:], np.zeros(16, dtype=np.uint8))


def test_adc_logic_capture_includes_last_conversion_tail(tmp_path: Path) -> None:
    (tmp_path / "original.raw").touch()
    times = np.arange(8626) * 25e-12
    names = waveform_net_names(Nets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
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
        params=_gen(waveform_sample_interval_s=50e-12, conversions=2),
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
        params=_gen(waveform_sample_interval_s=50e-12, conversions=2),
        raw_path=tmp_path / "truncated.raw",
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    np.testing.assert_array_equal(truncated.bout, result.bout)


def test_adc_continuous_records_require_next_init_logic(tmp_path: Path) -> None:
    """Sample B16 at next INIT LOGIC and exclude the final unavailable capture."""
    params = _gen(waveform_sample_interval_s=50e-12, conversions=2).sequenced(
        (
            "1111" + "0" * 156,
            "0000" + "1" * 24 + "0" * 132,
            "0" * 28 + "11111100" * 16 + "1111",
            "0001" + "0" * 24 + "00000010" * 16 + "0000",
        ),
        symbol_rate=1.6e9,
    )
    ticks = np.arange(16_001)
    times_s = ticks * 12.5e-12
    raw_names = waveform_net_names(Nets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times_s) for name in raw_names}
    values["time"] = times_s
    for name in ("init", "samp", "comp", "logic"):
        pattern = np.array([int(bit) for bit in getattr(params, f"seq_{name}").data])
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
    params = (_gen if view == "hdl21gen" else _frida1)(waveform_sample_interval_s=50e-12)
    return sim._probes(sim.testbench(params), params)


def test_frida1_rc_waveforms_use_device_terminal_nodes(extraction) -> None:
    names = {alias: raw for raw, alias in _adc_names("frida1").items()}
    assert names["vdac_p"] == "xtop.xadc.N_VDAC_P_XXsampswitch_p/MM0_d"
    # the fabricated macro is C15 first
    assert names["dac_state_p[0]"].startswith("xtop.xadc.N_DAC_STATE_P_MAIN<15>_")


def test_extracted_waveforms_cover_every_dac_stage_and_comparator_nodes(extraction):
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
    DAC's sides (``subckt._generated_aliases``); TSMC65 bound, as the runner binds it before it builds
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
        sim._decode(result, params=_gen(), raw_path=tmp_path / "unused.raw", signal_names=names)


def test_conversion_bodies_contain_no_inline_raises():
    import ast

    source = inspect.getsource(sim._decode)
    assert not any(isinstance(node, ast.Raise) for node in ast.walk(ast.parse(source)))


def test_adc_conversion_requires_one_complete_record():
    times = np.tile(np.arange(17, dtype=float), (2, 1))
    times[1, -1] = np.nan
    np.testing.assert_array_equal(sim._complete(times), [True, False])
    times[0, -1] = np.nan
    with pytest.raises(ValueError, match="No complete ADC conversions"):
        sim._complete(times)


# The behavioral converter's SAR loop (``sim._convert``) on its blocks' physics, at FRIDA-1's array and
# its continuous recipe at 1.6 GBd

_TB = TbParams(pdk="tsmc65", params=Params(adc_bits=12, cdac=capdac.Params())).sequenced(
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111.rows, symbol_rate=1.6e9
)


def _with_tb(**fields) -> sim._Behavioral:
    return sim._Behavioral(tb=TbParams(**{**_TB.__dict__, **fields}))


def _ideal_codes(params: sim._Behavioral, points: int = 2001) -> tuple[np.ndarray, np.ndarray]:
    tb = params.tb
    main_f, diff_f = capdac.Model.plates(tb.params.cdac, float(tb.vdd_dac.dc))
    full_scale_v = float(tb.vdd_dac.dc) * np.sum(main_f - diff_f) / np.sum(main_f + diff_f)
    vin_v = np.linspace(-full_scale_v, full_scale_v, points)
    code_weights = np.append(2 * np.asarray(capdac.Model.weights(tb.params.cdac)), 1)
    code_max = (1 << tb.params.adc_bits) - 1
    bout = sim._convert(params, vin_v).bout
    code = np.rint((bout @ code_weights) * code_max / code_weights.sum())
    ideal_code = np.clip(np.floor((vin_v / full_scale_v + 1) / 2 * (code_max + 1)), 0, code_max)
    return code, ideal_code


@pytest.mark.parametrize("astate", [(0, 1) * 8, (0,) * 16, (1,) * 16, (1, 1, 0, 0) * 4])
def test_ideal_transfer_is_independent_of_the_initial_state(astate) -> None:
    code, ideal_code = _ideal_codes(_with_tb(dac_astate_p=astate, dac_astate_n=astate))
    assert np.max(np.abs(code - ideal_code)) <= 1


@pytest.mark.parametrize("bits, extra", [(10, 3), (14, 6)])
def test_other_resolutions_convert_and_scale_logic_energy(bits: int, extra: int) -> None:
    cdac = capdac.Params(bits=bits, extra=extra)
    stages = len(capdac.Model.weights(cdac))
    params = sim._Behavioral(
        tb=TbParams(
            pdk="tsmc65",
            params=Params(adc_bits=bits, cdac=cdac),
            dac_astate_p=(0, 1) * (stages // 2) + (0,) * (stages % 2),
            dac_astate_n=(0, 1) * (stages // 2) + (0,) * (stages % 2),
            dac_bstate_p=(0,) * stages,
            dac_bstate_n=(0,) * stages,
        ).continuous(stages),
        salogic=sim._Salogic(clock_energy_j=1e-15),
    )
    code, ideal_code = _ideal_codes(params, points=501)
    assert np.max(np.abs(code - ideal_code)) <= 1
    # Every one of the 3 * stages registers is clocked on all stages + 1 LOGIC edges.
    result = sim._convert(params, np.zeros(4))
    np.testing.assert_allclose(result.energy_j["vdd_d"], 3 * stages * (stages + 1) * 1e-15)


def test_static_bottom_plates_draw_no_reference_charge() -> None:
    params = _with_tb(dac_mode=0, dac_bstate_p=_TB.dac_astate_p, dac_bstate_n=_TB.dac_astate_n)
    np.testing.assert_allclose(sim._convert(params, np.full(8, 0.1)).energy_j["vdd_dac"], 0.0, atol=1e-30)


def test_differential_caps_double_their_weight_without_diffcaps() -> None:
    # With dac_diffcaps=0 the diff plates move with the main plates, so each
    # step is (main + diff) instead of (main - diff): a small input resolves
    # to a code nearer mid-scale.
    vin_v = np.asarray([0.2])
    code_weights = np.append(2 * np.asarray(capdac.Model.weights(_TB.params.cdac)), 1)
    differential = sim._convert(_with_tb(dac_diffcaps=1), vin_v).bout @ code_weights
    common = sim._convert(_with_tb(dac_diffcaps=0), vin_v).bout @ code_weights
    assert abs(common[0] - code_weights.sum() / 2) < abs(differential[0] - code_weights.sum() / 2)


def reference_codes(vin_v: float, conversions: int = 400, **reference) -> np.ndarray:
    """The output codes at a DC input with the reference's departure (``capdac.Model.Behavioral``'s
    ``reference_*``) the only impairment."""
    params = sim._Behavioral(
        tb=_TB,
        comp=comp_model.Model.Behavioral(noise_v=0.0),
        cdac=capdac.Model.Behavioral(**reference),
        seed=3,
    )
    code_weights = np.append(2 * np.asarray(capdac.Model.weights(_TB.params.cdac)), 1)
    bout = sim._convert(params, np.full(conversions, vin_v)).bout
    return (bout @ code_weights) * ((1 << _TB.params.adc_bits) - 1) / code_weights.sum()


def _full_scale_and_lsb() -> tuple[float, float]:
    main_f, diff_f = capdac.Model.plates(_TB.params.cdac, float(_TB.vdd_dac.dc))
    full_scale_v = float(_TB.vdd_dac.dc) * np.sum(main_f - diff_f) / np.sum(main_f + diff_f)
    return full_scale_v, 2 * full_scale_v / (1 << _TB.params.adc_bits)


def test_reference_noise_cancels_at_mid_scale_and_grows_toward_the_ends() -> None:
    full_scale_v, lsb_v = _full_scale_and_lsb()
    # off the first threshold by a third of an LSB: noiseless, every conversion gives one code
    middle, near_top, near_bottom = 0.33 * lsb_v, 0.9 * full_scale_v, -0.9 * full_scale_v
    assert np.std(reference_codes(near_top)) == 0.0
    # 2 mV at the reference: the sides' plates at it differ by about vin / VDD_DAC near the ends
    sigma = {
        vin: float(np.std(reference_codes(vin, reference_noise_v=2e-3))) for vin in (middle, near_top, near_bottom)
    }
    assert sigma[middle] < 0.3
    assert sigma[near_top] > 1.0 and sigma[near_bottom] > 1.0


def test_the_reference_kickback_needs_both_a_slow_driver_and_a_small_decap() -> None:
    full_scale_v, _ = _full_scale_and_lsb()
    vin_v = 0.6 * full_scale_v
    ideal = reference_codes(vin_v, 50)
    # 10 pF of decoupling behind 1 kohm: the dip (a switch's charge over 10 pF) has not recovered
    # by the next comparison, so the code moves; a strong driver (1 ohm) restores it in time
    slow = reference_codes(vin_v, 50, reference_r_ohm=1e3, reference_c_f=10e-12)
    fast = reference_codes(vin_v, 50, reference_r_ohm=1.0, reference_c_f=10e-12)
    assert abs(float(np.mean(slow)) - float(np.mean(ideal))) >= 1.0
    assert np.array_equal(fast, ideal)
    # either part alone is an ideal reference
    assert np.array_equal(reference_codes(vin_v, 50, reference_r_ohm=1e3), ideal)
    assert np.array_equal(reference_codes(vin_v, 50, reference_c_f=10e-12), ideal)


def test_a_drawn_arrays_exact_transfer_is_the_noise_free_converters() -> None:
    """The decision paths of a drawn array (``calc_paths``, with each stage's A state) give the
    decisions the behavioral converter makes, ideal sampler and comparator, at every input: a stage
    held at 1 moves the other side's capacitor."""
    from flow.analysis.calc import calc_decision_steps, calc_paths

    stages = len(capdac.Model.weights(_TB.params.cdac))
    astate = (0, 1) * (stages // 2) + (0,) * (stages % 2)
    tb = TbParams(**{**_TB.__dict__, "dac_astate_p": astate, "dac_astate_n": astate})
    rng = np.random.default_rng(5)
    main_f, diff_f = capdac.Model.plates(tb.params.cdac, float(tb.vdd_dac.dc))
    drawn = {
        side: (capdac.Model.draw(main_f, pelgrom=0.01, rng=rng), capdac.Model.draw(diff_f, pelgrom=0.01, rng=rng))
        for side in ("p", "n")
    }
    cdac = capdac.Model.Behavioral(
        **{
            f"{kind}_{side}_f": tuple(drawn[side][index])
            for side in drawn
            for index, kind in enumerate(("main", "diff"))
        }
    )
    params = sim._Behavioral(tb=tb, comp=comp_model.Model.Behavioral(noise_v=0.0), cdac=cdac)
    code_max = (1 << tb.params.adc_bits) - 1
    full_scale_v, lsb_v = _full_scale_and_lsb()
    # an even count: no input on the first threshold, 0 V, a tie the comparator (overdrive > 0) and
    # the paths (an input on a threshold above it) break apart
    vin_v = np.linspace(-full_scale_v, full_scale_v, 20_010)
    bout = sim._convert(params, vin_v).bout
    weights = np.append(2 * np.asarray(capdac.Model.weights(tb.params.cdac), dtype=np.float64), 1.0)
    a, b = calc_decision_steps(
        (drawn["p"], drawn["n"]), 0.0, code_max, diffcaps=bool(tb.dac_diffcaps), nominal=(main_f, diff_f), astate=astate
    )
    paths = calc_paths(a, b, weights, code_max)
    exact = paths.decisions[np.searchsorted(paths.lower, vin_v / lsb_v, side="right") - 1]
    assert np.array_equal(exact, bout)


def test_the_reference_noise_leaves_the_other_sources_draws_alike() -> None:
    """The reference's noise draws from a stream of its own: a negligible one changes no decision
    the comparator's noise makes."""
    _, lsb_v = _full_scale_and_lsb()

    def bout(**reference) -> np.ndarray:
        params = sim._Behavioral(
            tb=_TB, comp=comp_model.Model.Behavioral(noise_v=lsb_v), cdac=capdac.Model.Behavioral(**reference), seed=3
        )
        return sim._convert(params, np.full(200, 0.33 * lsb_v)).bout

    assert np.array_equal(bout(reference_noise_v=1e-12), bout())


# A run's raw output read back (``sim.read``), the probes a codes-only run saves, and the stimulus as
# the behavioral converter sees it


def test_a_behavioral_run_writes_its_capture_and_read_reads_it_back(tmp_path, monkeypatch) -> None:
    """``simulate`` of a behavioral run writes the converter's conversions (``capture.h5``) with the
    converter's numbers among its readbacks; ``read`` returns that measurement, arrays as written."""
    from flow.adc.test_analysis import adc_measurement

    measurement = adc_measurement([1, 2047, 4095], internal=True)
    converter = SimpleNamespace(capture=lambda tb, path: measurement, numbers=lambda: {"full_scale_v": 0.9})
    monkeypatch.setattr(sim, "_converter", lambda pdk, params: converter)
    tb = TbParams(pdk="tsmc65", params=Params(), conversions=1)
    raw = sim.simulate(tb, tmp_path / "run")
    assert raw == tmp_path / "run" / "capture.h5" and raw.is_file()
    read = sim.read(raw, tb)
    assert isinstance(read, MeasAdc)
    np.testing.assert_array_equal(read.bout, measurement.bout)
    np.testing.assert_array_equal(read.dout, measurement.dout)
    assert read.info.readbacks["full_scale_v"] == 0.9
    assert {key: read.info.readbacks[key] for key in measurement.info.readbacks} == measurement.info.readbacks


def test_read_decodes_a_spectre_run_by_the_probes_it_left(tmp_path, monkeypatch) -> None:
    """A Spectre run's raw file is decoded through the probes' map beside it (``names.json``)."""
    raw = tmp_path / "netlist.raw"
    raw.touch()
    (tmp_path / "names.json").write_text(json.dumps({"time": "time", "xtop.comp_out": "comp_out"}))
    seen = {}
    monkeypatch.setattr(sim, "read_raw_transient", lambda path: seen.setdefault("raw", path))
    monkeypatch.setattr(sim, "_decode", lambda result, **kwargs: seen.update(kwargs) or "decoded")
    tb = _gen()
    assert sim.read(raw, tb) == "decoded"
    assert seen["raw"] == raw and seen["params"] is tb and seen["raw_path"] == raw
    assert seen["signal_names"] == {"time": "time", "xtop.comp_out": "comp_out"}


def test_a_codes_only_run_saves_what_its_conversions_need(tsmc65, extraction) -> None:
    """``Probes.CODES``: the sequencer's lines, the comparator's output, the input and the supplies'
    currents, the same raw names as with every node probed; what the decode reads."""
    for params in (_gen(), _frida1()):
        nodes = sim._probes(sim.testbench(params), params)
        codes = sim._probes(sim.testbench(replace(params, probes=Probes.CODES)), replace(params, probes=Probes.CODES))
        assert set(codes.values()) == {
            "time",
            *(f"seq_{line}" for line in ("init", "samp", "comp", "logic")),
            "comp_out",
            "vin_p",
            "vin_n",
            "i(vdd_a)",
            "i(vdd_d)",
            "i(vdd_dac)",
        }
        assert all(nodes[raw] == label for raw, label in codes.items())


def test_a_spectre_run_of_the_adc_is_tsmc65s(tmp_path) -> None:
    with pytest.raises(ValueError, match="TSMC65's alone"):
        sim.simulate(replace(_gen(), pdk="ihp130"), tmp_path / "run")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("recipe", _catalogue[:3] + _catalogue[-3:], ids=lambda recipe: recipe.name.lower())
def test_a_sequencer_line_reads_as_its_rows_bits(recipe) -> None:
    """A line (``h.Vbit``) as the behavioral converter sees it: each symbol its row's bit, between
    ground and the digital supply, at the symbol's start and anywhere inside it, repeated."""
    tb = _gen().sequenced(recipe.rows, symbol_rate=0.96e9)
    period_s = 1 / 0.96e9
    for line, row in zip((tb.seq_init, tb.seq_samp, tb.seq_comp, tb.seq_logic), recipe.rows, strict=True):
        bits = 1.2 * np.fromiter(map(int, row), dtype=float)
        symbols = np.arange(2 * len(row))
        for offset in (0.0, 0.25, 0.999):
            value = sim._source_value(line, (symbols + offset) * period_s)
            np.testing.assert_array_equal(value, np.tile(bits, 2))
    assert sim._source_value(tb.seq_init, np.asarray([-period_s]))[0] == 0.0


def test_the_behavioral_interface_record_is_one_complete_conversion() -> None:
    params = TbParams(pdk="tsmc65", params=Params(), conversions=1)
    wave = sim._interface_wave(params, [1] * 17, samples_per_symbol=2)

    assert wave.record_index.tolist() == [0]
    assert wave.v["vin_diff"].shape == (1, 2 * len(params.seq_init.data))
    assert wave.v["seq_comp"].shape == wave.v["vin_diff"].shape
    np.testing.assert_array_equal(
        wave.v["seq_comp"][0], 1.2 * np.repeat(np.fromiter(map(int, params.seq_comp.data), dtype=float), 2)
    )
    assert np.count_nonzero(np.diff(wave.v["comp_out"][0])) <= 1


@pytest.mark.spectre
@pytest.mark.parametrize(
    "extraction", (None, Extraction.TAPEOUT, Extraction.SIGNOFF), ids=("generated", "tapeout", "signoff")
)
def test_each_top_passes_spectres_checks(extraction, tmp_path) -> None:
    """Each kind of top through its run's short static and dynamic checks (``simulate`` of a run with
    ``check``), in Spectre: the generated netlist, and a fabricated converter's tape-out extraction
    and its layout's signoff (skipped where it is not laid out, ``flow.sweep.lookup.laid_out``)."""
    import shutil

    from flow.sweep import lookup

    if shutil.which("spectre") is None:
        pytest.skip("Spectre binary is not on PATH; source the Cadence environment")
    pytest.importorskip("pdk.tsmc65.hdl21.site")
    params = Params() if extraction is None else Fabricated.FRIDA1_1LAYER_RADIX17.params
    if extraction is Extraction.SIGNOFF:
        try:
            lookup.laid_out("adc", "tsmc65", params)
        except LookupError as error:
            pytest.skip(str(error))
    tb = TbParams(
        pdk="tsmc65", params=params, simulator=Simulator.SPECTRE, extraction=extraction, conversions=1, check=True
    )
    run_dir = tmp_path / "run"
    assert sim.simulate(tb, run_dir) == run_dir / "netlist.raw"
    assert (run_dir / "netlist.scs").is_file()
    assert "completes with 0 errors" in (run_dir / "spectre.log").read_text(errors="replace")
    assert json.loads((run_dir / "names.json").read_text())["time"] == "time"


# ---- the behavioral converter (``_Converter``) on stand-in blocks and a stand-in characterization
# of its DAC (``behavioral``, ``capture``), and the DAC's characterization it composes or its design
# where there is none (``of``)


TB = TbParams(pdk="tsmc65", params=Params(adc_bits=12, cdac=capdac.Params())).sequenced(
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111.rows, symbol_rate=1.6e9
)


def _dac(params: Params, *, gain: float = 1.0, settling_meas: Path | None = None) -> capdac.Model:
    """A stand-in characterization of the converter's DAC: its plates designed at 1.2 V, its drawn
    gain, each stage's driver 20 ps late and its step settling with a time constant of its own, one
    side's layout of 1000 um^2."""
    stages = len(capdac.Model.weights(params.cdac))
    return capdac.Model(
        pdk="none",
        params=params.cdac,
        reference_v=1.2,
        settling_s=(300e-12,) * stages,
        delay_s=(20e-12,) * stages,
        tau_s=tuple(10e-12 * (stage + 1) for stage in range(stages)),
        lsb_v=1e-3,
        gain=gain,
        area_um2=1000.0,
        settling_meas=settling_meas,
    )


class _Model(sim._Converter):
    """The converter in a PDK of a 1.2 V supply, without its kit."""

    supply_v = 1.2


def _stand_in(dac: capdac.Model) -> sim._Converter:
    """The model on stand-in blocks: a comparator and a sampler of known impairments, and ``dac``."""
    return _Model(
        pdk="none",
        params=TB.params,
        comp=SimpleNamespace(
            behavioral=lambda vin_cm_v: comp_model.Model.Behavioral(
                noise_v=1e-4, delay_table_v=(1e-6, 1e-3), delay_table_s=(200e-12, 50e-12)
            )
        ),
        samp=SimpleNamespace(
            behavioral=lambda load_f: samp_model.Model.Behavioral(
                noise_v=1e-4, jitter_s=2e-12, ron_table_v=(0.2, 1.0), ron_table_ohm=(100.0, 300.0)
            )
        ),
        cdac=dac,
    )


def test_the_model_switches_its_dacs_design_plates_as_characterized() -> None:
    """The DAC's plates are its design's at its reference, its top plates loaded beyond them by the
    parasitic of its drawn gain; its delays and time constants are its characterization's, and its
    drivers draw no energy. The full scale is the switched plates' share of that load; a capture's
    extracted weights name the measurement the DAC's settling run keeps, none where it is designed."""
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, 1.2)
    model = _stand_in(_dac(TB.params, gain=0.8, settling_meas=Path("/runs/settling/result.h5")))
    dac = model.behavioral(TB).cdac
    assert dac.main_p_f == dac.main_n_f == tuple(main_f) and dac.diff_p_f == dac.diff_n_f == tuple(diff_f)
    plates_f = float(np.sum(main_f) + np.sum(diff_f))
    assert plates_f / (plates_f + dac.parasitic_f) == pytest.approx(0.8, rel=1e-12)
    assert model.load_f == pytest.approx(plates_f / 0.8, rel=1e-12)
    assert model.full_scale_v == pytest.approx(1.2 * 0.8 * float(np.sum(main_f - diff_f)) / plates_f, rel=1e-12)
    assert dac.stage_tau_s == model.stage_tau_s == model.cdac.tau_s and dac.settling_tau_s == model.cdac.tau_s[-1]
    assert dac.stage_delay_s == model.stage_delay_s == (20e-12,) * len(main_f)
    assert dac.driver_energy_j == 0.0 and dac.driver_static_w == 0.0
    tb = TbParams(**{**TB.__dict__, "conversions": 4})
    assert model.capture(tb, None).info.readbacks["cap_table"] == "/runs/settling/result.h5"
    assert _stand_in(_dac(TB.params)).capture(tb, None).info.readbacks["cap_table"] == ""


def test_the_model_converts_on_its_dacs_array_as_drawn() -> None:
    """A DAC whose measured steps are not its design's (a unit drawn other than designed, at the
    PDK's smallest): its top plate's load is the design's plates at the drawn gain, and each stage's
    switched plate gives its measured step at that load (each side half the differential step), so
    the steps the conversion switches are the decoding's extracted weights and the full scale is
    half their sum; a Pelgrom draw is of the design's plates, as the DAC's Monte Carlo draws them,
    and drawn so too."""
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, 1.2)
    plates_f = float(np.sum(main_f + diff_f))
    # the design's steps at a gain of 0.8, the last stage drawn three times as heavy, the first 2 %
    # light
    steps = 2 * 1.2 * 0.8 * (main_f - diff_f) / plates_f
    steps[-1] *= 3.0
    steps[0] *= 0.98
    model = _stand_in(replace(_dac(TB.params, gain=0.8), step_v=tuple(steps)))
    dac = model.behavioral(TB).cdac
    switched = np.asarray(dac.main_p_f) - np.asarray(dac.diff_p_f)
    assert dac.main_n_f == dac.main_p_f and dac.diff_p_f == dac.diff_n_f == tuple(diff_f)
    assert model.load_f == pytest.approx(plates_f / 0.8, rel=1e-12)
    np.testing.assert_allclose(2 * 1.2 * switched / model.load_f, steps, rtol=1e-12)
    assert model.full_scale_v == pytest.approx(steps.sum() / 2, rel=1e-12)
    rng = np.random.default_rng(7)
    expected = [capdac.Model.draw(plate, pelgrom=0.01, rng=rng) for _side in "pn" for plate in (main_f, diff_f)]
    seeded = model.behavioral(replace(TB, mismatch_seed=7, unit_mismatch=0.01)).cdac
    excess_f = np.asarray(dac.main_p_f) - main_f
    np.testing.assert_allclose(seeded.main_p_f, expected[0] + excess_f, rtol=1e-12)
    np.testing.assert_allclose(seeded.main_n_f, expected[2] + excess_f, rtol=1e-12)
    assert (seeded.diff_p_f, seeded.diff_n_f) == (tuple(expected[1]), tuple(expected[3]))


def test_the_model_quiets_each_source_alone_and_scales_the_settling() -> None:
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, float(TB.vdd_dac.dc))
    model = _stand_in(_dac(TB.params))
    # the DAC's SPICE draw where a capture asks for it, the nominal plates where none is characterized
    heavy = (main_f * 1.01, diff_f)
    drawn = replace(model, drawn=(heavy, (main_f, diff_f))).behavioral(replace(TB, drawn=True)).cdac
    assert drawn.main_p_f == tuple(heavy[0]) and drawn.main_n_f == tuple(main_f)
    assert model.behavioral(replace(TB, drawn=True)).cdac.main_p_f == tuple(main_f)
    # a Pelgrom draw from the seed, the P side's main and difference plates, then the N side's;
    # none without mismatch, which takes nothing from the seed's stream
    rng = np.random.default_rng(7)
    expected = [capdac.Model.draw(plate, pelgrom=0.01, rng=rng) for _side in "pn" for plate in (main_f, diff_f)]
    seeded = model.behavioral(replace(TB, mismatch_seed=7, unit_mismatch=0.01)).cdac
    assert [seeded.main_p_f, seeded.diff_p_f, seeded.main_n_f, seeded.diff_n_f] == [tuple(e) for e in expected]
    assert model.behavioral(replace(TB, mismatch_seed=7)).cdac.main_p_f == tuple(main_f)
    # the reference is ideal unless one is given (the reference study's)
    ideal = model.behavioral(TB).cdac
    assert ideal.reference_r_ohm == ideal.reference_c_f == ideal.reference_noise_v == 0.0
    given = model.behavioral(replace(TB, reference_r_ohm=3.0, reference_c_f=200e-12, reference_noise_v=1e-4)).cdac
    assert (given.reference_r_ohm, given.reference_c_f, given.reference_noise_v) == (3.0, 200e-12, 1e-4)
    # the comparator's noise alone: its delay stays, so a late decision still holds
    noiseless = model.behavioral(replace(TB, quiet=frozenset({Quiet.COMPARATOR_NOISE}))).comp
    assert noiseless.noise_v == 0.0 and noiseless.delay_table_v == (1e-6, 1e-3)
    ideal = model.behavioral(replace(TB, quiet=frozenset({Quiet.COMPARATOR}))).comp
    assert ideal.noise_v == 0.0 and ideal.delay_table_v is None
    # a perfect track-and-hold: no on-resistance (so no tracking lag), its noise and jitter kept
    sampler = model.behavioral(replace(TB, quiet=frozenset({Quiet.SAMPLER}))).samp
    assert sampler.ron_table_v is None and sampler.n_conductance_s_per_v == sampler.p_conductance_s_per_v == 0.0
    assert sampler.noise_v == 1e-4 and sampler.jitter_s == 2e-12
    resistance = samp_model.Model.resistance(TB.params.samp, sampler, np.asarray([0.2, 0.6, 1.0]), 1.2)
    assert not np.any(resistance)
    quiet = model.behavioral(replace(TB, quiet=frozenset({Quiet.SAMPLING}))).samp
    assert quiet.noise_v == quiet.jitter_s == 0.0 and quiet.ron_table_v == (0.2, 1.0)
    with pytest.raises(ValueError, match="quiet takes Quiet members"):
        replace(TB, quiet=frozenset({"samplers"}))
    # the settling time constants scale, the drivers' delays do not; at 0 settling is ideal, the
    # drivers' delay gone too
    nominal, slower = model.behavioral(TB).cdac, model.behavioral(replace(TB, tau_scale=4.0)).cdac
    np.testing.assert_allclose(slower.stage_tau_s, 4 * np.asarray(nominal.stage_tau_s))
    assert slower.stage_delay_s == nominal.stage_delay_s == (20e-12,) * len(main_f)
    settled = model.behavioral(replace(TB, tau_scale=0.0)).cdac
    assert not any(settled.stage_tau_s) and not any(settled.stage_delay_s) and settled.settling_tau_s == 0.0


def test_the_model_composes_its_dacs_characterization_or_else_its_design(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Model.of``: the DAC's characterization of the same parameters, looked up and never
    simulated, and its Monte Carlo draw the converter calibrates on (``DRAWN_RUN`` at
    ``DRAWN_PERCENTILE``); where there is none, the DAC as designed and its draws nominal, each with
    a warning."""
    asked = []
    characterized = _dac(TB.params, gain=0.8)
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, 1.2)
    draw = ((main_f, diff_f), (main_f, diff_f))

    def of(cls, pdk, params, *, simulate=True):
        asked.append(("of", pdk, params, simulate))
        return characterized

    def drawn(cls, pdk, params, run, percentile):
        asked.append(("drawn", pdk, params, run, percentile))
        return draw

    monkeypatch.setattr(capdac.Model, "of", classmethod(of))
    monkeypatch.setattr(capdac.Model, "drawn", classmethod(drawn))
    for block in (comp_model, samp_model):
        monkeypatch.setattr(block.Model, "of", classmethod(lambda cls, pdk, params, *, simulate=True: None))
    model = sim._Converter.of("tsmc65", TB.params)
    assert model.cdac is characterized and model.drawn is draw
    assert asked == [
        ("of", "tsmc65", TB.params.cdac, False),
        ("drawn", "tsmc65", TB.params.cdac, DRAWN_RUN, DRAWN_PERCENTILE),
    ]

    def missing(cls, *args, **kwargs):
        raise LookupError("not characterized")

    monkeypatch.setattr(capdac.Model, "of", classmethod(missing))
    monkeypatch.setattr(capdac.Model, "drawn", classmethod(missing))
    monkeypatch.setattr(capdac_model, "_supply_v", lambda pdk: 1.2)
    with pytest.warns(UserWarning) as warned:
        designed = sim._Converter.of("tsmc65", TB.params)
    assert [str(warning.message).split(" (")[0] for warning in warned] == [
        "the DAC is not characterized",
        "the DAC's Monte Carlo is not characterized",
    ]
    assert designed.cdac == capdac.Model.design("tsmc65", TB.params.cdac) and designed.drawn is None
    assert designed.cdac.gain == 1.0 and designed.cdac.settling_meas is None

    # a record whose kept settling run (or Monte Carlo) cannot be read converts as designed too
    def unreadable(cls, *args, **kwargs):
        raise FileNotFoundError("build/capdac/run/tsmc65/digest/settling/result.h5")

    monkeypatch.setattr(capdac.Model, "of", classmethod(unreadable))
    monkeypatch.setattr(capdac.Model, "drawn", classmethod(unreadable))
    with pytest.warns(UserWarning) as warned:
        unread = sim._Converter.of("tsmc65", TB.params)
    assert [str(warning.message).split(" (")[0] for warning in warned] == [
        "the DAC is not characterized",
        "the DAC's Monte Carlo is not characterized",
    ]
    assert unread.cdac == designed.cdac and unread.drawn is None


def test_the_decoupling_is_the_decap_share_of_both_dac_sides_to_one_figure(monkeypatch) -> None:
    pdk = SimpleNamespace(pdk_logic=SimpleNamespace(DECAP_FF_PER_UM2=4.0))
    monkeypatch.setattr(importlib, "import_module", lambda name: pdk)
    # both sides' 2000 um^2 at 4 fF/um^2, 30 % of it: 2.4 pF, to one figure
    assert DECAP_COVERAGE == 0.30
    # the property of a stand-in model: its PDK and one side's layout area, its drivers with it;
    # none where the DAC is not laid out
    decoupling_f = sim._Converter.decoupling_f.fget
    assert decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=1000.0))) == 2e-12
    assert math.isnan(decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=0.0))))
    assert math.isnan(decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=math.nan))))
