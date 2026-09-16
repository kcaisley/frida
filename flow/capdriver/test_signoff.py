"""Software-only export and signoff tests: no private PDK or EDA executables."""

import json
import sys
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace

import hdl21 as h
import pytest
from klayout import db

from flow.util.netlist import _spice_statements, _subcircuit_span, subcircuit_ports

from . import layout as target


@pytest.fixture
def mock_pdk(monkeypatch, tmp_path):
    library = tmp_path / "upstream.spi"
    library.write_text(
        "* mock upstream library\n"
        ".SUBCKT UNUSED A Z\nR1 A Z 1\n.ENDS UNUSED\n"
        ".SUBCKT CKXOR2D2LVT A1 A2 Z VDD VSS\n"
        "M1 Z A1 VSS VSS nch_lvt w=2u l=60n\n.ENDS CKXOR2D2LVT\n"
        ".SUBCKT CKXOR2D4LVT A1 A2 Z VDD VSS\n"
        "M1 Z A1 VSS VSS nch_lvt w=4u l=60n\n.ENDS CKXOR2D4LVT\n"
    )
    compiled_bands = []
    cells = {
        drive: h.ExternalModule(
            name=f"CKXOR2D{drive}LVT",
            port_list=[h.Inout(name=name) for name in ("A1", "A2", "Z", "VDD", "VSS")],
            paramtype=h.HasNoParams,
        )
        for drive in (2, 4)
    }

    class MockCompiler(h.HierarchyWalker):
        def visit_external_module_call(self, call):
            assert call.module.domain == "generic"
            band = call.params.drive_band
            compiled_bands.append(band)
            module = h.Module(name=f"mock_xor_stage_{len(compiled_bands) - 1}_band_{band}")
            for port in ("A", "B", "Y", "VDD", "VSS"):
                module.add(h.Inout(name=port))
            cell = cells[2 if band == 1 else 4]
            for index in range(2 if band == 4 else 1):
                module.add(
                    cell()(A1=module.A, A2=module.B, Z=module.Y, VDD=module.VDD, VSS=module.VSS), name=f"cell_{index}"
                )
            return module

    compiler = ModuleType("pdk.tsmc65")
    monkeypatch.setattr(compiler, "compile", lambda module: MockCompiler().walk(module), raising=False)
    site = ModuleType("pdk.tsmc65.site")
    monkeypatch.setattr(
        site, "install", SimpleNamespace(include_stdcell=lambda: SimpleNamespace(path=library)), raising=False
    )
    provider = ModuleType("pdk.tsmc65.signoff")

    @dataclass(frozen=True)
    class SignoffOptions:
        drc_unselect_checks: tuple[str, ...] = ()

    monkeypatch.setattr(provider, "SignoffOptions", SignoffOptions, raising=False)
    for module in (compiler, site, provider):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    return SimpleNamespace(library=library, bands=compiled_bands, options=SignoffOptions)


@pytest.fixture
def source_gds(tmp_path):
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("capdriver")
    ring = layout.create_cell("guard_ring")
    leaf = layout.create_cell("ring_contact")
    unrelated = layout.create_cell("unrelated")
    dnw = layout.layer(1, 0)
    metal = layout.layer(31, 0)
    text = layout.layer(31, 5)
    top.shapes(dnw).insert(db.Box(-250, 0, 30500, 6900))
    ring.shapes(metal).insert(db.Box(0, 0, 50, 6000))
    leaf.shapes(metal).insert(db.Box(0, 0, 20, 20))
    leaf.shapes(text).insert(db.Text("guard_label", db.Trans(5, 5)))
    ring.insert(db.CellInstArray(leaf.cell_index(), db.Trans(10, 20)))
    top.insert(db.CellInstArray(ring.cell_index(), db.Trans(db.Trans.R90, 7000, 1000)))
    for index, name in enumerate(target.PORTS):
        top.shapes(text).insert(db.Text(name, db.Trans(index * 100, 100)))
    unrelated.shapes(metal).insert(db.Box(0, 0, 100000, 100000))
    path = tmp_path / "source.gds"
    layout.write(str(path))
    return path


@pytest.fixture
def mock_checks(monkeypatch, mock_pdk):
    calls = []

    def drc(params, run_dir):
        calls.append("drc")
        assert params.pdk_options == mock_pdk.options()
        assert params.lvs_expectation == "correct"
        assert params.pex_source_path is None
        assert params.layout_top == params.source_top == "capdriver"
        assert run_dir.name == "drc"
        report = run_dir / "calibre.drc.summary"
        report.write_text("clean")
        return report

    def lvs(params, run_dir):
        calls.append("lvs")
        assert params.pdk_options == mock_pdk.options()
        assert run_dir.name == "lvs"
        report = run_dir / "calibre.lvs.report"
        report.write_text("CORRECT")
        return True, report

    monkeypatch.setattr(target.signoff, "run_drc", drc)
    monkeypatch.setattr(target.signoff, "run_lvs", lvs)
    return calls


def _geometry(path, top_name):
    layout = db.Layout()
    layout.read(str(path))
    top = layout.cell(top_name)
    cells = [layout.cell(index) for index in {top.cell_index(), *top.called_cells()}]
    return {
        cell.name: {
            "shapes": sorted(
                (str(layout.get_info(layer)), shape.to_s())
                for layer in layout.layer_indexes()
                for shape in cell.shapes(layer).each()
            ),
            "instances": sorted(
                (inst.cell.name, str(inst.trans), str(inst.a), str(inst.b), inst.na, inst.nb)
                for inst in cell.each_inst()
            ),
        }
        for cell in cells
    }


def test_export_preserves_hierarchy_masks_labels_and_provenance(tmp_path, source_gds, mock_checks):
    original_hash = target._sha256(source_gds)
    run = target.frida1(tmp_path / "run", source_gds=source_gds)
    assert mock_checks == ["drc", "lvs"]
    assert target._sha256(source_gds) == original_hash
    assert _geometry(source_gds, "capdriver") == _geometry(run / "capdriver.gds", "capdriver")
    exported = db.Layout()
    exported.read(str(run / "capdriver.gds"))
    assert sorted(cell.name for cell in exported.each_cell()) == ["capdriver", "guard_ring", "ring_contact"]
    assert [cell.name for cell in exported.top_cells()] == ["capdriver"]
    manifest = json.loads((run / "provenance.json").read_text())
    assert manifest["source_gds"]["sha256"] == original_hash
    assert manifest["export_gds"]["sha256"] == target._sha256(run / "capdriver.gds")
    assert manifest["bbox_um"] == "(-0.25,0;30.5,6.9)"
    assert {label["text"] for label in manifest["labels"]} == {*target.PORTS, "guard_label"}
    assert json.loads((run / "summary.json").read_text())["status"] == "passed"


def test_source_scalar_ports_mapping_bands_and_unmodified_models(tmp_path, mock_pdk):
    metadata = target._generate_source(tmp_path)
    source = (tmp_path / "capdriver.lvs.cdl").read_text()
    assert subcircuit_ports(source, "capdriver") == target.PORTS
    assert sorted(mock_pdk.bands) == sorted([4, 4, 2, 2] + [1] * 12)
    start, end = _subcircuit_span(source, "capdriver")
    instance = next(line.split() for line in _spice_statements(source[start:end]) if line.lower().startswith("x"))
    assert instance[1:-1] == [
        *(f"dac_state<{i}>" for i in range(16)),
        *(f"dac_drive<{i}>" for i in range(16)),
        "dac_drive_invert",
        "vdd_dac",
        "vss_dac",
    ]
    assert instance[-1] == "generated_driver"
    generic = (tmp_path / "generated_driver.generic.cdl").read_text()
    assert "dac_drive_invert dac_state_0 dac_drive_0 vdd vss" in generic
    assert "clock_xor" in generic and "clock_xor" not in source
    assert metadata["index_mapping"] == [
        {"generic_stage": i, "legacy_index": 15 - i, "drive_band": band}
        for i, band in enumerate([4, 4, 2, 2] + [1] * 12)
    ]
    upstream = mock_pdk.library.read_text()
    for name in metadata["library_cells"]:
        a, b = _subcircuit_span(upstream, name)
        c, d = _subcircuit_span(source, name)
        assert source[c:d] == upstream[a:b]
    assert "UNUSED" not in source
    assert "nch_lvt" in source and "nch_lvt_mac" not in source
    assert ".include" not in source.lower()
    assert metadata["upstream_library"]["sha256"] == target._sha256(mock_pdk.library)
    for name, digest in metadata["files"].items():
        assert digest == target._sha256(tmp_path / name)


def test_drc_failure_still_attempts_lvs(tmp_path, source_gds, mock_checks, monkeypatch):
    def fail_drc(params, run_dir):
        mock_checks.append("drc")
        (run_dir / "gdscheck.log").write_text("violations")
        raise RuntimeError("DRC violations")

    monkeypatch.setattr(target.signoff, "run_drc", fail_drc)
    run = tmp_path / "run"
    with pytest.raises(RuntimeError, match="DRC violations"):
        target.frida1(run, source_gds=source_gds)
    assert mock_checks == ["drc", "lvs"]
    summary = json.loads((run / "summary.json").read_text())
    assert summary["status"] == summary["drc"]["status"] == "failed"
    assert summary["lvs"]["status"] == "passed"
    assert summary["drc"]["artifacts"] == [str(run / "drc/gdscheck.log")]
    assert summary["errors"]


@pytest.mark.parametrize("raises", [False, True])
def test_lvs_failure_is_not_waived(tmp_path, source_gds, mock_checks, monkeypatch, raises):
    def fail_lvs(params, run_dir):
        if raises:
            raise RuntimeError("LVS tool unavailable")
        report = run_dir / "calibre.lvs.report"
        report.write_text("INCORRECT")
        return False, report

    monkeypatch.setattr(target.signoff, "run_lvs", fail_lvs)
    run = tmp_path / "run"
    with pytest.raises(RuntimeError, match="LVS"):
        target.frida1(run, source_gds=source_gds)
    summary = json.loads((run / "summary.json").read_text())
    assert summary["status"] == summary["lvs"]["status"] == "failed"
    assert summary["drc"]["status"] == "passed"
    if not raises:
        assert summary["lvs"]["correct"] is False
        assert summary["lvs"]["report"] == str(run / "lvs/calibre.lvs.report")


def test_missing_source_and_cell_fail_before_pdk_import(tmp_path):
    with pytest.raises(FileNotFoundError):
        target.frida1(tmp_path / "missing_run", source_gds=tmp_path / "missing.gds")
    layout = db.Layout()
    layout.create_cell("other")
    source = tmp_path / "other.gds"
    layout.write(str(source))
    with pytest.raises(ValueError, match="no cell 'capdriver'"):
        target.frida1(tmp_path / "missing_cell_run", source_gds=source)
    assert not (tmp_path / "missing_run").exists()
    assert not (tmp_path / "missing_cell_run").exists()


def test_source_failure_writes_summary(tmp_path, source_gds, mock_checks, mock_pdk):
    mock_pdk.library.write_text("* missing required standard cells\n")
    run = tmp_path / "run"
    with pytest.raises(RuntimeError, match="no .subckt"):
        target.frida1(run, source_gds=source_gds)
    summary = json.loads((run / "summary.json").read_text())
    assert summary["status"] == "failed"
    assert summary["drc"]["status"] == summary["lvs"]["status"] == "not_run"
    assert mock_checks == []
    assert (run / "provenance.json").is_file()


def test_cli_explicit_and_default_paths(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(target, "ROOT", tmp_path)
    monkeypatch.setattr(target, "frida1", lambda run_dir, **kwargs: calls.append((run_dir, kwargs)) or run_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["layout", "frida1", "--output-dir", str(tmp_path / "run"), "--source-gds", str(tmp_path / "input.gds")],
    )
    target.main()
    assert calls[-1] == (tmp_path / "run", {"source_gds": tmp_path / "input.gds"})
    monkeypatch.setattr(sys, "argv", ["layout", "frida1"])
    target.main()
    assert calls[-1][0].parent == tmp_path / "build/layout/capdriver/frida1"
    assert calls[-1][1] == {"source_gds": None}
