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
    search = importlib.import_module("flow.adc.search")
    assert "level" in inspect.signature(search.runs).parameters
    assert importlib.util.find_spec("flow.adc.targets") is None
    for stage in ("sim", "search"):
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
