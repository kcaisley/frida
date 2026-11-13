"""PDK-independent runner contracts and diagnostic prerequisite handling."""

import importlib
import importlib.util
import inspect
import sys
from types import SimpleNamespace

import pytest

from . import test_spectre


def test_the_adcs_circuit_runs_are_its_sweeps():
    # the ADC's circuit simulator's runs are its sweep's runs at the circuit level: it has no targets
    runs = importlib.import_module("flow.adc.runs")
    assert "level" in inspect.signature(runs.testbenches).parameters
    assert importlib.util.find_spec("flow.adc.targets") is None
    for stage in ("sim", "runs"):
        source = importlib.import_module(f"flow.adc.{stage}")
        assert not hasattr(source, "main")
        assert "netlist_only" not in inspect.getsource(source)
        assert not any(name.startswith("frida65") for name in vars(source))


def test_missing_spectre_skips_before_pdk_import(monkeypatch):
    monkeypatch.setattr(test_spectre.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        test_spectre.importlib.util, "find_spec", lambda _: pytest.fail("PDK imported before binary check")
    )
    with pytest.raises(pytest.skip.Exception, match="Spectre binary"):
        inspect.unwrap(test_spectre.spectre_installation)()


@pytest.mark.parametrize("spec", (None, SimpleNamespace(origin=None)))
def test_missing_pdk_package_skips(spec, monkeypatch):
    monkeypatch.setattr(test_spectre.shutil, "which", lambda _: "/mock/spectre")
    monkeypatch.setattr(test_spectre.importlib.util, "find_spec", lambda _: spec)
    with pytest.raises(pytest.skip.Exception, match="PDK Python package"):
        inspect.unwrap(test_spectre.spectre_installation)()


def test_missing_installation_skips_but_missing_collateral_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(test_spectre.shutil, "which", lambda _: "/mock/spectre")
    monkeypatch.setattr(test_spectre.importlib.util, "find_spec", lambda _: SimpleNamespace(origin="site.py"))
    site = SimpleNamespace(install=SimpleNamespace(pdk_path=tmp_path / "missing"), MODEL_FILES=(tmp_path / "model",))
    monkeypatch.setitem(sys.modules, "pdk.tsmc65.hdl21", SimpleNamespace(site=site))
    with pytest.raises(pytest.skip.Exception, match="installation is unavailable"):
        inspect.unwrap(test_spectre.spectre_installation)()
    site.install.pdk_path = tmp_path
    with pytest.raises(FileNotFoundError):
        inspect.unwrap(test_spectre.spectre_installation)()


def test_spectre_marker_is_opt_in():
    import subprocess

    for selection, expected in (([], "16 deselected"), (["-m", "spectre"], "16 tests collected")):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_spectre.__file__), *selection],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == (0 if selection else 5), result.stdout + result.stderr
        assert expected in result.stdout


def test_a_runs_operating_point_gives_each_nets_device_capacitance(tmp_path) -> None:
    """Spectre's operating point (``OPPOINT``) as each net's device capacitance: a gate's total, a
    drain's and source's intrinsic and junction ones, the testbench's prefixes left out, ground as vss."""
    from flow.circuit.spectre import device_capacitance

    path = tmp_path / "oppoint.txt"
    path.write_text(
        "Instance: xtop.dut.MN of Samp\nModel: nch\nPrimitive: bsim4\n"
        "          d : V(xtop.vout) = 541 mV\n          g : V(xtop.clk) = 0 V\n"
        "          s : V(xtop.dut.mid) = 550 mV\n          b : val(0) = 0 \n"
        "        cjd = 800 aF\n        cjs = 976.224 aF\n        cgg = 2.5 fF\n"
        "        cgd = -1.1 fF\n        cdd = 1.1 fF\n        cds = -525.08e-24 F\n        css = 1 fF\n"
    )
    found = device_capacitance(path)
    assert set(found) == {"vout", "clk", "mid"}
    assert abs(found["clk"] - 2.5e-15) < 1e-20 and abs(found["vout"] - 1.9e-15) < 1e-20
    assert abs(found["mid"] - 1.976224e-15) < 1e-20


@pytest.mark.parametrize(("noise", "expected"), [(False, "nutbin"), (True, "psfascii")])
def test_a_run_writes_nutbin_or_psf_ascii_where_it_has_a_noise_analysis(monkeypatch, tmp_path, noise, expected) -> None:
    """Spectre's raw format first on its command line, by the run's analyses: PSF ASCII (a file an
    analysis, which ``flow.pipeline.read`` reads as a directory) where one is a noise analysis."""
    import hdl21 as h
    import hdl21.sim as hs

    from flow.circuit import spectre

    bench = h.Module(name="Bench")
    bench.VSS = h.Port()
    bench.out, bench.inp = h.Signal(), h.Signal()
    bench.vinp = h.primitives.Vdc(dc=0.5, ac=1.0)(p=bench.inp, n=bench.VSS)
    sweep = hs.LogSweep(start=1e3, stop=1e9, npts=5)
    attrs = [hs.Op(name="op"), hs.Ac(sweep=sweep, name="ac")]
    if noise:
        attrs.append(hs.Noise(output=bench.out, input_source=bench.vinp, sweep=sweep, name="noise"))
    assert spectre.raw_format(attrs) == expected
    captured = {}
    monkeypatch.setattr(
        hs, "Sim", lambda **kwargs: SimpleNamespace(run=lambda options: captured.update(kwargs, options=options))
    )
    spectre.run(bench, attrs, tmp_path / "run")
    arguments = captured["options"].simulator_args
    assert arguments[:2] == ("-format", expected) and arguments.count("-format") == 1
    assert {"+escchars", "+preset=mx", "+mt=1"} <= set(arguments) and captured["attrs"] is attrs


def test_a_run_of_literals_alone_is_refused(monkeypatch, tmp_path) -> None:
    """hdl21 calls no simulator for a run without an analysis of its own, and the flow's operating
    point, a DC sweep and the transfer functions are literals: ``run`` refuses such a run by its
    directory, naming the operating point that makes it one, and runs it with that."""
    import hdl21 as h
    import hdl21.sim as hs

    from flow.circuit import spectre

    bench = h.Module(name="Bench")
    bench.VSS = h.Port()
    literals = [
        *spectre.options(),
        hs.Save(["xtop.outn", "xtop.voutn:p"]),
        h.Literal("sweep_n dc dev=xtop.voutn param=dc start=0 stop=1.2 step=0.3"),
    ]
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: pytest.fail("a run without an analysis reached hdl21"))
    with pytest.raises(ValueError, match=r'run_n has no hdl21 analysis .* add hs\.Op\(name="op"\)'):
        spectre.run(bench, literals, tmp_path / "run_n")
    assert not (tmp_path / "run_n").exists()
    ran = []
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: SimpleNamespace(run=lambda options: ran.append(kwargs["attrs"])))
    spectre.run(bench, [*literals, hs.Op(name="op")], tmp_path / "run_n")
    assert len(ran) == 1
