"""PDK-independent runner contracts and diagnostic prerequisite handling."""

import importlib
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import hdl21.sim as hs
import pytest
from vlsirtools.spice import ResultFormat
from vlsirtools.spice.sim_data import AnalysisType

import pdk

from . import test_spectre


@pytest.mark.parametrize("block", ("adc", "samp", "caparray"))
def test_targets_and_python_contract(block):
    module = importlib.import_module(f"flow.{block}.sim")
    targets = importlib.import_module(f"flow.{block}.targets")
    # the simulation targets: each runs the sim function of its name (the block prefix dropped)
    runs = {
        name: getattr(module, name, None) or getattr(module, f"{block}_{name}", None)
        for name, value in vars(targets).items()
        if inspect.isfunction(value) and value.__module__ == targets.__name__ and not name.startswith("_")
    }
    names = [name for name, function in runs.items() if function is not None]
    assert names
    assert names == sorted(names, key=lambda name: (not name.startswith("hdl21"), name.startswith("frida2")))
    for name in names:
        assert not inspect.signature(getattr(targets, name)).parameters
        signature = inspect.signature(runs[name])
        assert list(signature.parameters) == ["run_dir", "check"]
        assert signature.parameters["check"].default is False
        assert signature.parameters["check"].kind is inspect.Parameter.KEYWORD_ONLY
    assert not hasattr(module, "main")
    assert "netlist_only" not in inspect.getsource(module)
    assert not any(name.startswith("frida65") for name in vars(module))


@pytest.fixture
def capture_sim(monkeypatch):
    """Replace site dependencies and execution, keeping real testbench generators."""

    site = SimpleNamespace(
        install=SimpleNamespace(
            include=lambda *_: h.Literal("models"),
            include_pre_simulation=lambda: h.Literal("pre"),
            include_stdcell=lambda: hs.Include(path=Path("/cells/driver.spi")),
        )
    )
    # the logic's unit device sizes the comparator's geometry readbacks
    fake_tsmc65 = SimpleNamespace(site=site, pdk_logic=SimpleNamespace(default_xtor_size={"core": (120e-9, 60e-9)}))
    monkeypatch.setattr(pdk, "tsmc65", fake_tsmc65, raising=False)
    monkeypatch.setitem(sys.modules, "pdk.tsmc65", fake_tsmc65)
    monkeypatch.setitem(sys.modules, "pdk.tsmc65.hdl21", SimpleNamespace(site=site))
    monkeypatch.setitem(sys.modules, "pdk.tsmc65.hdl21.site", site)
    monkeypatch.setattr(h.pdk, "set_default", lambda *_: None)
    monkeypatch.setattr(h.pdk, "compile", lambda *_: None)
    captured = {}

    def build(**kwargs):
        captured.update(kwargs)

        def run(options):
            captured["options"] = options
            if captured.get("fail"):
                raise RuntimeError("simulator/license failure")
            return {AnalysisType.TRAN: SimpleNamespace(data={})}

        return SimpleNamespace(run=run)

    monkeypatch.setattr(hs, "Sim", build)
    from flow.circuit import results

    monkeypatch.setattr(results, "read_raw_transient", lambda path: object())
    return captured


@pytest.mark.parametrize(
    "block,target,short_stop,full_stop,threads",
    (
        ("samp", "frida1_transient", 100e-9, 500e-9, 4),
        ("caparray", "frida1_transfer_curve", 200.1e-9, 2048 * 200e-9 + 2047 * 100e-12, 4),
    ),
)
@pytest.mark.parametrize("check", (False, True))
def test_block_simulation_recipe(block, target, short_stop, full_stop, threads, check, capture_sim, tmp_path):
    runner = getattr(importlib.import_module(f"flow.{block}.sim"), target)
    assert runner(tmp_path, check=check) == tmp_path
    tran = next(attr for attr in capture_sim["attrs"] if isinstance(attr, hs.Tran))
    assert float(tran.tstop) == pytest.approx(short_stop if check else full_stop)
    assert not tran.noise
    assert float(tran.options["strobeperiod"]) == pytest.approx(100e-12)
    assert tran.options["strobeoutput"].text == "strobeonly"
    options = capture_sim["options"]
    assert options.fmt == (ResultFormat.NONE if check else ResultFormat.SIM_DATA)
    assert f"+mt={threads}" in options.simulator_args
    assert ("-ahdllint=warn" in options.simulator_args) == check
    assert options.rundir == tmp_path
    literals = "\n".join(attr.text for attr in capture_sim["attrs"] if isinstance(attr, h.Literal))
    assert ("static_erc" in literals) == check
    assert ("dyn_nodecap" in literals) == check
    capture_sim["fail"] = True
    with pytest.raises(RuntimeError, match="simulator/license failure"):
        runner(tmp_path / "failure", check=check)


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

    for selection, expected in (([], "23 deselected"), (["-m", "spectre"], "23 tests collected")):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_spectre.__file__), *selection],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == (0 if selection else 5), result.stdout + result.stderr
        assert expected in result.stdout
