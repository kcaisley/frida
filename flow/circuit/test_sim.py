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

    for selection, expected in (([], "13 deselected"), (["-m", "spectre"], "13 tests collected")):
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
