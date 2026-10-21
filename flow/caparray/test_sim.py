"""Software-only checks for the native HDL21 capacitor-array interface."""

import io
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import hdl21.sim as hs
import pytest

import pdk

from . import sim


def test_caparray_testbench_uses_typed_timing() -> None:
    params = sim.CapArrayTbParams(code_dwell_s=250e-9, transition_time_s=50e-12)
    tb = sim.CapArrayTb(params)

    assert isinstance(tb, h.Module)
    assert len(tb.dut.of.ports) == 2 + 2 * (params.cdac.n_dac + params.cdac.n_extra)
    assert float(tb.vmain_15.of.params.wave.points[1][0]) == pytest.approx(250e-9)
    assert not hasattr(params, "temperature_c")


def test_caparray_testbench_packs_code_with_c0_as_highest_stage() -> None:
    tb = sim.CapArrayTb(sim.CapArrayTbParams())

    # The 11-bit baseline ramp leaves the five earliest/largest redundant
    # stages low and toggles C15 fastest.
    assert len(tb.vmain_0.of.params.wave.points) == 2
    assert len(tb.vmain_4.of.params.wave.points) == 2
    assert len(tb.vmain_5.of.params.wave.points) == 4
    assert len(tb.vmain_15.of.params.wave.points) == 4096


def test_targets_own_only_experiment_targets() -> None:
    # its source alone: importing the targets imports the layout's TSMC65 signoff, which the
    # PDK-independent tests do not have
    source = Path(__file__).with_name("targets.py").read_text()
    assert "frida1_transfer_curve" in source
    assert re.search(r"\b_check\b|check=", source) is None  # no diagnostic runs
    assert "TARGETS" not in vars(sim) and not hasattr(sim, "main")


@pytest.mark.parametrize("check", [False, True])
def test_runner_uses_passive_array_without_standard_cells(monkeypatch, tmp_path, check) -> None:
    site = SimpleNamespace(
        install=SimpleNamespace(
            include=lambda *_: hs.Lib(path=Path("/models/mos.lib"), section="tt"),
            include_pre_simulation=lambda: h.Literal("pre"),
            include_stdcell=lambda: hs.Include(path=Path("/cells/driver.spi")),
        ),
    )
    stub_pdk = SimpleNamespace(site=site, pdk_logic=object())
    monkeypatch.setitem(sys.modules, "pdk.tsmc65", stub_pdk)
    monkeypatch.setitem(sys.modules, "pdk.tsmc65.hdl21", SimpleNamespace(site=site))
    monkeypatch.setitem(sys.modules, "pdk.tsmc65.hdl21.site", site)
    # Without the private submodule an earlier test may already have bound an empty
    # pdk.tsmc65 namespace to the pdk package, which `from pdk import tsmc65` prefers.
    monkeypatch.setattr(pdk, "tsmc65", stub_pdk, raising=False)
    monkeypatch.setattr(h.pdk, "set_default", lambda *_: None)
    monkeypatch.setattr(h.pdk, "compile", lambda *_: None)
    captured = {}

    def build(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run=lambda options: captured.update(options=options))

    monkeypatch.setattr(hs, "Sim", build)
    sim.frida1_transfer_curve(tmp_path, check=check)
    attrs = captured["attrs"]
    assert [attr.path for attr in attrs if isinstance(attr, hs.Lib)] == [Path("/models/mos.lib")]
    assert [attr.path for attr in attrs if isinstance(attr, hs.Include)] == []
    assert any(isinstance(attr, h.Literal) and attr.text == "pre" for attr in attrs)


def test_array_testbench_spectre_escapes_scalar_plate_connections() -> None:
    tb = sim.CapArrayTb(sim.CapArrayTbParams(cdac=sim.CapArrayConfig(n_dac=3, n_extra=0, weights=(4, 2, 1))))
    source = io.StringIO()
    h.netlist(tb, source, fmt="spectre")
    spectre = source.getvalue()
    statements = " ".join(re.sub(r"\n\s*\+", " ", re.sub(r"//[^\n]*", "", spectre)).split())
    escaped_bottoms = [rf"cap_botplate_{kind}\<{stage}\>" for kind in ("main", "diff") for stage in range(3)]
    assert f"dut ( cap_topplate vss {' '.join(escaped_bottoms)} )" in statements
    assert re.search(r"(?<!\\)[<>]|\\\\[<>]", spectre) is None
    for kind in ("main", "diff"):
        for stage in range(3):
            canonical = f"cap_botplate_{kind}<{stage}>"
            escaped = rf"cap_botplate_{kind}\<{stage}\>"
            assert f"v{kind}_{stage} ( {escaped} vss ) vsource" in statements
            assert tb.dut.conns[canonical] is tb.namespace[canonical]
            assert tb.namespace[canonical].name == canonical
            assert tb.namespace[canonical].width == 1


def test_array_testbench_drives_main_and_diff_branches_separately():
    tb = sim.CapArrayTb(sim.CapArrayTbParams(cdac=sim.CapArrayConfig(n_dac=3, n_extra=0, weights=(4, 2, 1))))
    assert tb.dut.conns["cap_shieldplate"] is tb.vss
    assert tb.dut.conns["cap_topplate"] is tb.cap_topplate
    for stage in range(3):
        main = tb.instances[f"vmain_{stage}"]
        diff = tb.instances[f"vdiff_{stage}"]
        assert main.conns["p"] is tb.dut.conns[f"cap_botplate_main<{stage}>"]
        assert diff.conns["p"] is tb.dut.conns[f"cap_botplate_diff<{stage}>"]
        for main_point, diff_point in zip(main.of.params.wave.points, diff.of.params.wave.points, strict=True):
            assert float(main_point[0]) == float(diff_point[0])
            assert float(main_point[1]) + float(diff_point[1]) == pytest.approx(1.2)
