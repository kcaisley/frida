"""PDK-independent runner contracts and diagnostic prerequisite handling."""

import importlib
import inspect
import sys
from types import SimpleNamespace

import pytest

from . import test_spectre


def test_targets_and_python_contract():
    # the ADC's named runs are its sweep's, beside its sim
    sweep = importlib.import_module("flow.adc.sweep")
    targets = importlib.import_module("flow.adc.targets")
    # the simulation targets: each runs the function of its name there
    runs = {
        name: getattr(sweep, name)
        for name, value in vars(targets).items()
        if inspect.isfunction(value) and value.__module__ == targets.__name__ and hasattr(sweep, name)
    }
    names = list(runs)
    assert names
    assert names == sorted(names, key=lambda name: not name.startswith("hdl21"))
    for name in names:
        assert not inspect.signature(getattr(targets, name)).parameters
        signature = inspect.signature(runs[name])
        assert list(signature.parameters) == ["run_dir", "check"]
        assert signature.parameters["check"].default is False
        assert signature.parameters["check"].kind is inspect.Parameter.KEYWORD_ONLY
    for stage in ("sim", "sweep"):
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

    for selection, expected in (([], "19 deselected"), (["-m", "spectre"], "19 tests collected")):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_spectre.__file__), *selection],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == (0 if selection else 5), result.stdout + result.stderr
        assert expected in result.stdout
