"""The ADC's own layout flow (``flow.adc.layout.lay_out``): the FRIDA-1 layouts' netlist preparation
(each flavor's source netlist with its capacitor array's frozen LVS source swapped in, and without
it) and each fabricated converter's cells; and any other converter's blocks side by side, from the
blocks' own layouts (the DAC's one side twice, the second mirrored): one top cell, each block
labelled where the viewer's export finds it, nothing connected (skipped where the blocks are not
laid out)."""

import json
from itertools import pairwise
from pathlib import Path

import pytest
from klayout import db

from flow import capdac
from flow.sweep.runner import ROOT
from flow.util.netlist import omit_subcircuit, replace_subcircuit
from flow.web.export import export_layout

from . import layout, sweep
from .layout import lay_out
from .params import Fabricated

# the FRIDA-1 layouts' netlists


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


def test_a_frida1_flavor_takes_its_frozen_array_by_pin_name(tmp_path: Path) -> None:
    # a two-stage stand-in of a flavor's inputs: its source netlist, the array's frozen LVS source
    # and its pins to the fabricated macro's (stage C0 is the macro's last pin)
    inputs = tmp_path / "frida1"
    inputs.mkdir(parents=True)
    (inputs / "adc_flavor.src.net").write_text(
        ".subckt old_cap cap_botplate_diff<1> cap_botplate_diff<0>\n"
        "+ cap_botplate_main<1> cap_botplate_main<0> cap_shieldplate cap_topplate\n"
        ".ends old_cap\n.subckt adc_flavor top vss\n"
        "Xcap diff_first diff_last main_first main_last vss top old_cap\nXkeep top vss real\n.ends adc_flavor\n"
    )
    (inputs / "old_cap.lvs.cdl").write_text(
        ".SUBCKT unit PLUS MINUS BULK\n.ENDS\n"
        ".SUBCKT old_cap cap_topplate cap_shieldplate cap_botplate_main<0> cap_botplate_main<1>\n"
        "+ cap_botplate_diff<0> cap_botplate_diff<1>\n"
        "xmain_0 cap_topplate cap_botplate_main<0> cap_shieldplate unit\n.ENDS\n"
    )
    pins = {"cap_topplate": "cap_topplate", "cap_shieldplate": "cap_shieldplate"}
    pins |= {
        f"cap_botplate_{kind}<{stage}>": f"cap_botplate_{kind}<{1 - stage}>"
        for kind in ("main", "diff")
        for stage in (0, 1)
    }
    (inputs / "old_cap.pins.json").write_text(json.dumps(pins))
    lvs, pex = layout._frida1_sources(tmp_path, inputs, flavor="adc_flavor", cap_cell="old_cap")

    source = lvs.read_text()
    # stage C0 (the frozen array's first plate) on the macro's last pin (<1>, the call's first
    # argument of each kind), the top renamed
    assert "Xcap top vss main_first main_last diff_first diff_last old_cap" in source
    assert "xmain_0 cap_topplate cap_botplate_main<0>" in source
    assert ".subckt adc_12b_17step top vss" in source.lower()
    conductive = pex.read_text()
    assert "Xcap" not in conductive and "old_cap" not in conductive
    assert "Xkeep top vss real" in conductive
    assert ".subckt adc_12b_17step top vss" in conductive


@pytest.mark.parametrize("member", list(Fabricated), ids=lambda member: member.name.lower())
def test_a_fabricated_converter_is_laid_out_from_its_tape_outs_cells(monkeypatch, tmp_path, member) -> None:
    """``lay_out`` of a fabricated converter: its flavor's cell of the chip's GDS, its source
    netlist, array and MOM unit cells by its layers and radix, from the kit's tape-out folder
    (``site.FRIDA1``); LVS correct with one layer; its GDS named as the member."""
    called = {}
    site = type("Site", (), {"FRIDA1": tmp_path / "frida1"})
    monkeypatch.setattr(layout, "import_module", lambda name: site)

    def run(run_dir, inputs, **options):
        called.update(inputs=inputs, **options)
        return run_dir / f"{options['target_name']}.gds"

    monkeypatch.setattr(layout, "_run_frida1", run)
    gds = lay_out(member.params, "tsmc65", tmp_path / "out")
    layers, radix = member.layers, member.radix
    cells = {"FRIDA1_1LAYER_RADIX17": "adc", "FRIDA1_1LAYER_RADIX20": "adc_0"}
    cells |= {"FRIDA1_2LAYER_RADIX17": "adc_1", "FRIDA1_2LAYER_RADIX20": "adc_2"}
    assert gds == tmp_path / "out" / f"{member.name.lower()}.gds"
    assert called == {
        "inputs": tmp_path / "frida1",
        "target_name": member.name.lower(),
        "source_layout_cell": cells[member.name],
        "flavor": f"adc_{layers}layer_radix{radix}",
        "cap_cell": f"caparray_{layers}layer_radix{radix}",
        "unit_cell_prefix": f"capunit_{layers}layer",
        "active_layers": (6,) if layers == 1 else (6, 7),
        "lvs_expectation": "correct" if layers == 1 else "incorrect",
    }


# any other converter's blocks side by side


def test_the_blocks_sit_side_by_side_in_one_labelled_cell(tmp_path: Path) -> None:
    tech = pytest.importorskip("pdk.tsmc65.layout.tech")  # the kit's layers and standard cells
    # the first converter of the sweep with MSB redistribution of 4 extra cycles and the second
    # comparator of the grid (200 uV, 1 ns)
    params = next(
        p
        for label, p in sweep.converters.instances("tsmc65")
        if p.cdac.extra == 4 and p.cdac.redundancy is capdac.Redundancy.MSB_REDIST and "comp=200uV_1ns" in label
    )
    try:
        gds = lay_out(params, "tsmc65", tmp_path)
    except (FileNotFoundError, LookupError) as error:
        pytest.skip(f"the blocks are not laid out: {error}")

    # nothing connected: no LVS source, so the layout verbs check its DRC alone
    assert gds == tmp_path / "adc_blocks.gds" and not (tmp_path / "source.cdl").exists()
    blocks = json.loads((tmp_path / "blocks.json").read_text())
    names = [block["name"] for block in blocks]
    assert names == ["cap_p", "samp_p", "comp", "samp_n", "cap_n"]
    assert all((ROOT / block["source"]).exists() for block in blocks)
    # each side of the DAC capdac's layout of the converter's array, its drivers with it, the N side
    # the P side's mirror image
    cap_p, cap_n = blocks[0], blocks[-1]
    assert cap_p["source"] == cap_n["source"] and "/capdac/" in cap_p["source"]
    assert (cap_p["mirrored"], cap_n["mirrored"]) == (False, True)
    assert (cap_p["w_um"], cap_p["h_um"]) == (cap_n["w_um"], cap_n["h_um"])
    # in a row, apart, inside the cell's extent
    lefts = [block["x_um"] for block in blocks]
    assert lefts == sorted(lefts)
    for left, right in pairwise(blocks):
        assert left["x_um"] + left["w_um"] < right["x_um"]
    layout = db.Layout()
    layout.read(str(gds))
    assert [cell.name for cell in layout.top_cells()] == ["adc_blocks"]
    # as written: the DAC's two sides one cell, the P side as drawn and the N side mirrored about the
    # vertical axis (x to -x, not about the horizontal), each of its shapes the P side's reflected
    (top,) = layout.top_cells()
    box = top.dbbox()
    assert box.width() > sum(block["w_um"] for block in blocks)
    assert box.height() >= max(block["h_um"] for block in blocks)
    sides = sorted(
        (inst for inst in top.each_inst() if inst.cell.name == Path(cap_p["source"]).stem),
        key=lambda inst: inst.bbox().left,
    )
    assert [inst.trans.rot for inst in sides] == [db.Trans.R0.rot, db.Trans.M90.rot]
    p_box, n_box = (inst.bbox() for inst in sides)
    metal = db.Region(top.begin_shapes_rec(layout.find_layer(*tech.LAYERS["M2"])))
    p_side, n_side = metal & db.Region(p_box), metal & db.Region(n_box)
    assert not p_side.is_empty()
    assert (p_side.transformed(db.Trans(db.Trans.M90, n_box.left + p_box.right, 0)) ^ n_side).is_empty()
    # the viewer's export: the labels on the boundary layer, which it shows
    exported = export_layout(str(gds), "tsmc65", str(tmp_path / "adc_blocks.layout.json"))
    assert {"M1", "OD", "PO", "BND"} <= set(exported["layers"])
    labels = json.loads((tmp_path / "adc_blocks.layout.json").read_text())["labels"]
    assert {label["text"] for label in labels if label["layer"] == "BND"} == set(names)
