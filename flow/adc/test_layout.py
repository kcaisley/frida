"""The ADC's layouts (``flow.adc.layout``): the strict block replacement FRIDA-2's are assembled with
(``AdcLayout``); the FRIDA layouts' netlist preparation (a test that needs the TSMC65 kit skips
without it); and the sweep's blocks side by side, from the blocks' layouts under build/: one top
cell, each block labelled where the viewer's export finds it, nothing signed off (skipped where the
blocks are not laid out)."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import pytest
from hdl21.prefix import f
from klayout import db

from flow.cdac.caparray.layout import CapArrayLayoutParams, UnitLengthCapFamilyParams
from flow.cdac.caparray.subckt import CapArray, CapArrayConfig, CapArrayParams, RedunStrat
from flow.sweep.runner import ROOT
from flow.util.netlist import omit_subcircuit, replace_subcircuit
from flow.web.export import export_layout

from . import sweep
from .layout import AdcLayout, AdcLayoutParams, assemble_blocks, is_valid_adc_layout_params


def _layout(*, top: str, block: str, pin_x: int = 50, boundary_right: int = 100) -> db.Layout:
    layout = db.Layout()
    layout.dbu = 0.001
    parent = layout.create_cell(top)
    child = layout.create_cell(block)
    pin = layout.layer(db.LayerInfo(201, 0))
    boundary = layout.layer(db.LayerInfo(200, 0))
    child.shapes(pin).insert(db.Box(pin_x - 5, 0, pin_x + 5, 10))
    child.shapes(pin).insert(db.Text("cap_topplate", db.Trans(pin_x, 5)))
    child.shapes(boundary).insert(db.Box(0, 0, boundary_right, 100))
    parent.insert(db.CellInstArray(child.cell_index(), db.Trans(1000, 2000)))
    parent.insert(db.CellInstArray(child.cell_index(), db.Trans(db.Trans.M90, 3000, 2000)))
    return layout


def _replacement(*, pin_x: int = 50, boundary_right: int = 100) -> db.Layout:
    layout = db.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("replacement")
    pin = layout.layer(db.LayerInfo(201, 0))
    boundary = layout.layer(db.LayerInfo(200, 0))
    cell.shapes(pin).insert(db.Box(pin_x - 5, 0, pin_x + 5, 10))
    cell.shapes(pin).insert(db.Text("cap_topplate", db.Trans(pin_x, 5)))
    cell.shapes(boundary).insert(db.Box(0, 0, boundary_right, 100))
    return layout


def test_adc_layout_ignores_unreferenced_unit_library_cells() -> None:
    replacement = _replacement()
    replacement.create_cell("unused_unit")

    result = AdcLayout(
        AdcLayoutParams("adc"),
        template=_layout(top="adc", block="placeholder"),
        replacements={"placeholder": replacement},
    )

    assert [instance.cell.name for instance in result.cell("adc").each_inst()] == ["replacement", "replacement"]


def test_adc_layout_replaces_compatible_blocks_and_preserves_transforms() -> None:
    result = AdcLayout(
        AdcLayoutParams("adc"),
        template=_layout(top="adc", block="placeholder"),
        replacements={"placeholder": _replacement()},
    )
    instances = list(result.cell("adc").each_inst())
    assert [instance.cell.name for instance in instances] == ["replacement", "replacement"]
    assert tuple(instance.trans for instance in instances) == (
        db.Trans(1000, 2000),
        db.Trans(db.Trans.M90, 3000, 2000),
    )
    assert result.cell("placeholder") is None


def test_adc_layout_rejects_boundary_changes() -> None:
    with pytest.raises(ValueError, match="pin-and-boundary compatible"):
        AdcLayout(
            AdcLayoutParams("adc"),
            template=_layout(top="adc", block="placeholder"),
            replacements={"placeholder": _replacement(boundary_right=105)},
        )


def test_adc_layout_allows_annotation_locations_layers_and_duplicates() -> None:
    replacement = _replacement(pin_x=55)
    cell = replacement.top_cell()
    old_pin = replacement.layer(201, 0)
    new_pin = replacement.layer(202, 0)
    cell.shapes(new_pin).insert(cell.shapes(old_pin))
    cell.shapes(old_pin).clear()
    cell.shapes(new_pin).insert(db.Text("cap_topplate", db.Trans(60, 5)))
    result = AdcLayout(
        AdcLayoutParams("adc"),
        template=_layout(top="adc", block="placeholder"),
        replacements={"placeholder": replacement},
    )
    assert result.cell("replacement") is not None


def test_adc_layout_rejects_changed_terminal_names() -> None:
    replacement = _replacement()
    cell = replacement.top_cell()
    cell.shapes(replacement.layer(201, 0)).insert(db.Text("wrong_net", db.Trans(50, 5)))
    with pytest.raises(ValueError, match="pin-and-boundary compatible"):
        AdcLayout(
            AdcLayoutParams("adc"),
            template=_layout(top="adc", block="placeholder"),
            replacements={"placeholder": replacement},
        )


def test_adc_layout_params_require_a_top_cell() -> None:
    assert is_valid_adc_layout_params(AdcLayoutParams("adc"))
    assert not is_valid_adc_layout_params(AdcLayoutParams(""))


# the FRIDA layouts' netlists


def test_replace_subcircuit_renames_block_calls_and_top() -> None:
    source = ".subckt old_cap a b\n.ends old_cap\n.subckt old_adc a b\nXcap a b old_cap\n.ends old_adc\n"
    result = replace_subcircuit(
        source,
        old_top="old_adc",
        new_top="adc_12b_17step",
        old_block="old_cap",
        new_block=".subckt new_cap a b\nC0 a b 1f\n.ends new_cap\n",
    )
    assert ".subckt adc_12b_17step a b" in result
    assert "Xcap a b new_cap" in result
    assert "old_cap" not in result


def test_omit_subcircuit_removes_multiline_calls() -> None:
    source = ".subckt empty a b\n.ends empty\n.subckt top a b\nXkeep a b real\nXremove a\n+ b empty\n.ends top\n"
    result = omit_subcircuit(source, "empty")
    assert "empty" not in result
    assert "Xremove" not in result
    assert "Xkeep a b real" in result


def test_historical_mom_source_translates_pin15_to_stage_c0() -> None:
    signoff = pytest.importorskip("pdk.tsmc65.calibre.signoff")  # the kit's MOM device for LVS
    params = CapArrayParams(
        cdac=CapArrayConfig(n_dac=2, n_extra=0, weights=(64, 1)),
        unit_cap=0.8 * f,
        active_layers=(6,),
        unit_models=(signoff.mom_lvs_device(6, 5),),
    )
    module = CapArray(params)
    module.name = "caparray"
    netlist = io.StringIO()
    h.netlist(module, netlist, fmt="spice")
    reference = (
        ".subckt old_cap cap_botplate_diff<1> cap_botplate_diff<0>\n"
        "+ cap_botplate_main<1> cap_botplate_main<0> cap_shieldplate cap_topplate\n"
        ".ends old_cap\n.subckt old_adc top vss\n"
        "Xcap diff_first diff_last main_first main_last vss top old_cap\n.ends old_adc\n"
    )
    mapping = {name: name for name in module.ports}
    mapping.update(
        {
            f"cap_botplate_{kind}<{stage}>": f"cap_botplate_{kind}<{1 - stage}>"
            for kind in ("main", "diff")
            for stage in range(2)
        }
    )
    legacy = replace_subcircuit(
        reference,
        old_top="old_adc",
        new_top="adc",
        old_block="old_cap",
        new_block=netlist.getvalue(),
        pin_map=mapping,
    )
    assert "Xcap top vss main_first main_last diff_first diff_last caparray" in legacy
    assert module.main_0_0_m6.conns["MINUS"].name == "cap_botplate_main<0>"


@pytest.mark.parametrize("active,shield", [((6,), 5), ((6, 7), 5), ((5, 6, 7), 4)])
def test_frida2_runner_uses_c0_first_paired_template_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, active: tuple[int, ...], shield: int
) -> None:
    from flow.adc import layout

    # the runner's signoff options and ring-MOM library, and the MOM fits the array follows: the kit's
    pytest.importorskip("pdk.tsmc65.calibre.signoff")
    fits = pytest.importorskip("pdk.tsmc65.layout.tech").MOM_FITS
    reference = (
        ".subckt caparray_2layer_radix17 cap_botplate_diff<1> cap_botplate_diff<0>\n"
        "+ cap_botplate_main<1> cap_botplate_main<0> cap_shieldplate cap_topplate\n"
        ".ends caparray_2layer_radix17\n.subckt adc_12b_17step top vss\n"
        "Xcap diff_first diff_last main_first main_last vss top caparray_2layer_radix17\n"
        ".ends adc_12b_17step\n"
    )
    read_text = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, **kwargs: reference if path.name == "frida-2-template-c0.cdl" else read_text(path, **kwargs),
    )
    # Exercise netlist orchestration without reading or modifying a real template.
    monkeypatch.setattr(layout.db, "Layout", lambda: SimpleNamespace(read=lambda _path: None))
    monkeypatch.setattr(layout, "CapArrayLayout", lambda _params: None)
    monkeypatch.setattr(layout, "AdcLayout", lambda _params, **kwargs: None)
    monkeypatch.setattr(layout, "_write_top", lambda *_args: None)
    monkeypatch.setattr(layout, "run_signoff", lambda *_args: None)
    arrays = []

    def generate_array(params):
        module = CapArray(params)
        arrays.append(module)
        return module

    monkeypatch.setattr(layout, "CapArray", generate_array)
    result = layout._run_frida2(
        tmp_path / "run",
        target_name="frida2_test",
        params=CapArrayLayoutParams(
            cdac=CapArrayConfig(n_dac=2, n_extra=0, weights=(64, 1)),
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=shield,
            active_layers=active,
            top_cell="new_caparray",
        ),
    )
    source = (result / "source.lvs.cdl").read_text()
    assert "Xcap top vss main_last main_first diff_last diff_first new_caparray" in source
    assert (result / "source.ideal.cdl").read_text() == source
    assert "ringfmom.cdl" in source
    assert f"ringfmom_{len(active)}layer" in source
    slope, intercept = fits["difference", len(active)]
    assert float(arrays[0].main_0_0.of.params.c) == pytest.approx((slope * 51.72 + intercept) * 1e-15, abs=1e-27)
    assert float(arrays[0].diff_0_0.of.params.c) == pytest.approx((slope * 0.52 + intercept) * 1e-15, abs=1e-27)
    assert (result / "ringfmom.cdl").is_file()
    conductive = (result / "source.pex.cdl").read_text()
    assert "Xcap" not in conductive
    assert "ringfmom" not in conductive


# the sweep's blocks side by side


def test_the_blocks_sit_side_by_side_in_one_labelled_cell(tmp_path: Path) -> None:
    pytest.importorskip("pdk.tsmc65.layout.tech")  # the kit's layers and standard cells
    # the first converter of the sweep with MSB redistribution of 4 extra cycles and the second
    # comparator of the grid (200 uV, 1 ns)
    params = next(
        p
        for label, p in sweep.converters.instances("tsmc65")
        if p.cdac.n_extra == 4 and p.cdac.redun_strat == RedunStrat.MSB_REDIST and "comp=200uV_1ns" in label
    )
    try:
        entry = assemble_blocks("tsmc65", params, tmp_path)
    except (FileNotFoundError, LookupError) as error:
        pytest.skip(f"the blocks are not laid out under build/: {error}")

    assert entry["error"] is None and entry["drc_violations"] is None and entry["lvs_correct"] is None
    names = [block["name"] for block in entry["blocks"]]
    assert {"comp", "samp_p", "samp_n", "cap_p", "cap_n"} <= set(names)
    assert all((ROOT / block["source"]).exists() for block in entry["blocks"])
    # in a row, apart, inside the cell's extent
    lefts = [block["x_um"] for block in entry["blocks"]]
    assert lefts == sorted(lefts)
    for left, right in zip(entry["blocks"], entry["blocks"][1:]):
        assert left["x_um"] + left["w_um"] < right["x_um"]
    assert entry["w_um"] > sum(block["w_um"] for block in entry["blocks"])
    assert entry["h_um"] >= max(block["h_um"] for block in entry["blocks"])

    gds = ROOT / entry["gds"]
    layout = db.Layout()
    layout.read(str(gds))
    assert [cell.name for cell in layout.top_cells()] == ["adc_blocks"]
    # the viewer's export: the labels on the boundary layer, which it shows
    exported = export_layout(str(gds), "tsmc65", str(tmp_path / "adc_blocks.layout.json"))
    assert {"M1", "OD", "PO", "BND"} <= set(exported["layers"])
    labels = json.loads((tmp_path / "adc_blocks.layout.json").read_text())["labels"]
    assert {label["text"] for label in labels if label["layer"] == "BND"} == set(names)
