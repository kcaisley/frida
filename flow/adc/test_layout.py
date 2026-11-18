"""The ADC's own layout flow (``flow.adc.layout.lay_out``): the FRIDA-1 layouts' netlist preparation
(each flavor's source netlist with its capacitor array's frozen LVS source swapped in, and without
it) and each fabricated converter's cells; and a generated converter's OpenROAD flow: its blocks'
abstracts, the kit's layers, the netlist OpenROAD reads, and the whole flow in IHP130 (skipped
without OpenROAD or the blocks' layouts)."""

import io
import json
import shutil
from pathlib import Path

import hdl21 as h
import pytest
from klayout import db

from flow.util.netlist import omit_subcircuit, replace_subcircuit

from . import layout
from .layout import lay_out
from .params import Fabricated, Params

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


# a generated converter: OpenROAD places and routes its blocks' abstracts and its logic's cells


def _block_gds(path: Path) -> Path:
    """A block's layout as ALIGN's step leaves one, in IHP130's layers: its boundary (four sites by
    two rows), a pin label on an M2 bar, its supply's label on an M3 rail, an inner M2 wire and a
    via, and a well past the boundary."""
    tech = pytest.importorskip("pdk.ihp130.layout.tech")
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("BLOCK_0")
    shapes = lambda name: top.shapes(layout.layer(*tech.LAYERS[name]))
    shapes("BND").insert(db.Box(0, 0, 1920, 7560))
    shapes("M2").insert(db.Box(200, 3000, 900, 3200))  # the pin's bar
    top.shapes(layout.layer(*tech.PIN_TEXT["M2"])).insert(db.Text("clk", db.Trans(500, 3100)))
    shapes("M3").insert(db.Box(0, 7340, 1920, 7780))  # the supply's rail
    top.shapes(layout.layer(*tech.PIN_TEXT["M3"])).insert(db.Text("vdd", db.Trans(960, 7560)))
    shapes("M2").insert(db.Box(1200, 1000, 1400, 6000))  # an inner wire
    shapes("V1").insert(db.Box(1210, 1010, 1390, 1190))
    shapes("NW").insert(db.Box(-310, 3780, 2230, 7870))  # the well past the boundary
    gds = path / "BLOCK_0.gds"
    layout.write(str(gds))
    return gds


def test_a_blocks_abstract_is_its_layout_on_the_sites_grid(tmp_path: Path) -> None:
    """A block's abstract: its boundary grown past its every shape and a micrometre more by whole
    sites (left, right) and whole rows (below, above, one at least); a pin for each label, the
    metal under it in the abstract's coordinates; the rest of its metals and cuts obstructions;
    its layout placed where the abstract's origin puts it (FOREIGN)."""
    gds = _block_gds(tmp_path)
    text, info = layout._abstract(gds, "ihp130", "adc_block", ("CoreSite", 0.48, 3.78))
    # left: the well 0.31 past it, + 1 um: three sites; right likewise; one row below and above
    assert info["offset_um"] == pytest.approx((1.44, 3.78))
    assert (info["w_um"], info["h_um"]) == pytest.approx((1.92 + 2 * 1.44, 7.56 + 2 * 3.78))
    assert info["pins"] == ["clk", "vdd"] and info["layers"] == ["M2", "M3"]
    assert "FOREIGN BLOCK_0 -1.4400 -3.7800 ;" in text
    pin = text[text.index("PIN clk") : text.index("END clk")]
    assert "LAYER Metal2 ;" in pin and "RECT 1.6400 6.7800 2.3400 6.9800 ;" in pin
    obstructions = text[text.index("  OBS") :]
    assert "LAYER Metal2 ;" in obstructions and "RECT 2.6400 4.7800 2.8400 9.7800 ;" in obstructions
    assert "LAYER Via1 ;" in obstructions
    assert "1.6400 6.7800 2.3400 6.9800" not in obstructions  # the pin is no obstruction


def test_the_technology_layers_follow_the_kits_metals() -> None:
    """frida's metals and cuts are the technology LEF's routing and cut layers in order."""
    pytest.importorskip("pdk.ihp130.layout.tech")
    _init, lefs = layout._technology("ihp130")
    layers = layout._lef_layers(lefs[0])
    assert {name: layers[name][0] for name in ("CO", "M1", "V1", "M2", "M5", "V5", "M7")} == {
        "CO": "Cont",
        "M1": "Metal1",
        "V1": "Via1",
        "M2": "Metal2",
        "M5": "Metal5",
        "V5": "TopVia1",
        "M7": "TopMetal2",
    }
    assert layers["M2"][1] == "VERTICAL"
    assert layout._rails(lefs[1], {name for name, _ in layers.values()}) == ("Metal1", 0.44)
    assert layout._site(lefs[1]) == ("CoreSite", 0.48, 3.78)


def test_openroads_netlist_holds_the_kits_cells_and_the_blocks_abstracts() -> None:
    """The converter as OpenROAD reads it: its generic cells the kit's library cells, their signal
    pins alone (an input the generic cell lacks on the library's tie cell); a block its abstract,
    a scalar pin for each bus bit; no supply pin on an instance; the hierarchy kept."""
    library = pytest.importorskip("pdk.ihp130.hdl21.cells")
    from flow.circuit.cells import cell

    Inner = h.Module(name="Inner")
    Inner.a, Inner.y = h.Input(), h.Output()
    Inner.vdd_d, Inner.vss_d = h.Inout(), h.Inout()
    Inner.Xinv = cell("inv", 1)(A=Inner.a, Y=Inner.y, VDD=Inner.vdd_d, VSS=Inner.vss_d)
    Top = h.Module(name="Top")
    Top.state = h.Signal(width=2)
    Top.vdd_d, Top.vss_d, Top.a = h.Inout(), h.Inout(), h.Input()
    Top.xinner = Inner(a=Top.a, y=Top.state[1], vdd_d=Top.vdd_d, vss_d=Top.vss_d)
    Block = h.ExternalModule(name="Block", port_list=[h.Input(name="dac_state", width=2), h.Inout(name="vdd")])
    Top.xblock = Block()(dac_state=Top.state, vdd=Top.vdd_d)
    view = layout._verilog_view(Top, "ihp130", {"xblock": ("adc_block", ["dac_state_0", "dac_state_1", "vdd"])})
    assert view.name == "adc"
    block = view.instances["xblock"]
    assert block.of.module.name == "adc_block"
    assert [port.name for port in block.of.module.port_list] == ["dac_state_0", "dac_state_1", "vdd"]
    assert block.conns["dac_state_1"].index == 1 and block.conns["vdd"] is view.vdd_d
    inverter = view.instances["xinner"].of.instances["Xinv"]
    target, _pins, _high, _low = library.GENERIC["inv_x1"]
    assert inverter.of.module.name == target and set(inverter.conns) == {"A", "Y"}
    text = io.StringIO()
    h.netlist(view, text, fmt="verilog")
    assert "VDD" not in text.getvalue() and "module adc" in text.getvalue()


def test_a_generated_converter_is_placed_and_routed_by_openroad(tmp_path: Path) -> None:
    """FRIDA-1's converter in IHP130 (its blocks as laid out): its blocks in a row on the sites'
    grid above its cells' rows, the N side's DAC mirrored, routed without a violation of the
    abstracts, its layout its blocks', its cells' and its routes', DRC clean (skipped without
    OpenROAD or the blocks' layouts)."""
    pytest.importorskip("pdk.ihp130.hdl21")
    if shutil.which("openroad") is None:
        pytest.skip("OpenROAD is not on the PATH")
    try:
        gds = lay_out(Params(), "ihp130", tmp_path)
    except LookupError as error:
        pytest.skip(f"the blocks are not laid out: {error}")
    log = (tmp_path / "openroad.log").read_text()
    assert "drc violations: 0" in log
    record = json.loads((tmp_path / "blocks.json").read_text())
    plan = record["plan"]
    site_w, row_h = 0.48, 3.78
    for entry in plan["blocks"].values():
        assert entry["x"] / site_w == pytest.approx(round(entry["x"] / site_w))
        assert entry["y"] / row_h == pytest.approx(round(entry["y"] / row_h))
        assert entry["y"] > plan["cells"][3]
    assert [entry["mirrored"] for entry in plan["blocks"].values()] == [False, False, False, False, True]
    built = db.Layout()
    built.read(str(gds))
    names = {cell.name for cell in built.each_cell()}
    assert {record["blocks"][block]["cell"] for block in ("comp", "samp", "cap")} <= names
    assert any(name.startswith("sg13g2_dfrbp") for name in names)
