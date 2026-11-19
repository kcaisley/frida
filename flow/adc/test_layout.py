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


def _block_gds(path: Path, free: bool = False) -> Path:
    """A block's layout as ALIGN's step leaves one, in IHP130's layers: its boundary (four sites by
    two rows, or six rows, the middle four free), a pin label on an M2 bar, its supply's label on
    an M3 rail, an inner M2 wire and a via, a well past the boundary, and (``free``) the second
    and fourth metals over the free rows, a third-metal run across them."""
    tech = pytest.importorskip("pdk.ihp130.layout.tech")
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("BLOCK_0")
    shapes = lambda name: top.shapes(layout.layer(*tech.LAYERS[name]))
    height = 3780 * (6 if free else 2)
    shapes("BND").insert(db.Box(0, 0, 1920, height))
    shapes("M2").insert(db.Box(200, 1000, 900, 1200))  # the pin's bar
    top.shapes(layout.layer(*tech.PIN_TEXT["M2"])).insert(db.Text("clk", db.Trans(500, 1100)))
    shapes("M3").insert(db.Box(0, height - 220, 1920, height + 220))  # the supply's rail
    top.shapes(layout.layer(*tech.PIN_TEXT["M3"])).insert(db.Text("vdd", db.Trans(960, height)))
    shapes("M2").insert(db.Box(1200, 1000, 1400, 3000))  # an inner wire
    shapes("V1").insert(db.Box(1210, 1010, 1390, 1190))
    shapes("NW").insert(db.Box(-310, 3780, 2230, 7870))  # the well past the boundary
    if free:
        shapes("M2").insert(db.Box(600, 9000, 800, 12000))  # a run over the free rows
        shapes("M4").insert(db.Box(0, 7560, 1920, 18900))  # a capacitor's metal
        shapes("M3").insert(db.Box(1700, 0, 1800, height))  # a wall: a supply run across them
    gds = path / "BLOCK_0.gds"
    layout.write(str(gds))
    return gds


def test_a_blocks_abstract_is_its_layout_in_the_rows(tmp_path: Path) -> None:
    """A block's abstract: its boundary as it is (its rows the cells' rows), its layout's origin
    there; a pin for each label, the metal under it, its supply of its use; the rest of its metals
    and cuts obstructions, its overhang past the boundary among them."""
    text, info = layout._abstract(_block_gds(tmp_path), "ihp130", "adc_block")
    (lef,) = text
    assert info["offset_um"] == (0.0, 0.0) and (info["w_um"], info["h_um"]) == pytest.approx((1.92, 7.56))
    assert info["parts"] == [("", "adc_block", 0.0, ["clk"])] and not info["free"]
    assert "CLASS BLOCK ;" in lef and "FOREIGN BLOCK_0 0.0000 0.0000 ;" in lef
    clk = lef[lef.index("PIN clk") : lef.index("END clk")]
    assert "USE SIGNAL" in clk and "LAYER Metal2 ;" in clk and "RECT 0.2000 1.0000 0.9000 1.2000 ;" in clk
    assert "USE POWER" in lef[lef.index("PIN vdd") : lef.index("END vdd")]
    obstructions = lef[lef.index("  OBS") :]
    assert "RECT 1.2000 1.0000 1.4000 3.0000 ;" in obstructions and "LAYER Via1 ;" in obstructions
    assert "0.2000 1.0000 0.9000 1.2000" not in obstructions  # the pin is no obstruction


def test_a_block_with_free_rows_is_two_bands_and_obstructions(tmp_path: Path) -> None:
    """Rows left free under a block's capacitors: two blocks, its bands below and above them (the
    pins within each; the layout with the lower one, the upper one empty), what it has over them
    from the second metal up routing obstructions, so that the cells may stand there."""
    free = {"y_um": [3.78, 18.9]}
    (lo, hi), info = layout._abstract(_block_gds(tmp_path, free=True), "ihp130", "adc_cap", free)
    assert info["free"] and info["free_um"] == pytest.approx((3.78, 18.9))
    assert [(suffix, macro, y, pins) for suffix, macro, y, pins in info["parts"]] == [
        ("_lo", "adc_cap_lo", 0.0, ["clk"]),
        ("_hi", "adc_cap_hi", pytest.approx(18.9), []),
    ]
    assert "SIZE 1.9200 BY 3.7800 ;" in lo and "FOREIGN BLOCK_0 0.0000 0.0000 ;" in lo
    assert "SIZE 1.9200 BY 3.7800 ;" in hi and "FOREIGN adc_cap_empty" in hi and "PIN vdd" in hi
    layers = {layer for layer, *_box in info["obstructions"]}
    assert layers == {"Metal2", "Metal3", "Metal4"}  # not the first metal: the bands' rails, the cells' own
    assert info["walls"] == [pytest.approx((1.7, 1.8))]
    assert ("Metal2", 0.6, 9.0, 0.8, 12.0) in [(lay, *(round(v, 4) for v in box)) for lay, *box in info["obstructions"]]


def _blocks(free: bool) -> dict:
    """The floorplan's blocks, sizes in TSMC65's grid (0.2 um sites, 1.8 um rows)."""
    cap = {"w_um": 16.4, "h_um": 37.8, "free": free, "parts": [("", "adc_cap", 0.0, [])]}
    if free:
        cap |= {
            "free_um": (5.4, 34.2),
            "parts": [("_lo", "adc_cap_lo", 0.0, []), ("_hi", "adc_cap_hi", 34.2, [])],
            "obstructions": [("M4", 1.0, 6.0, 2.0, 30.0)],
            "walls": [(0.3, 0.4)],
        }
    return {
        "cap": cap,
        "comp": {"w_um": 13.6, "h_um": 10.8, "free": False},
        "samp": {"w_um": 2.8, "h_um": 3.6, "free": False},
    }


@pytest.mark.parametrize("free", (True, False), ids=("stacked", "beside"))
def test_the_floorplan_is_frida1s_on_the_grid(free: bool) -> None:
    """The DAC's sides the outline, the N side mirrored, a column between them as narrow as the
    comparator and its samplers and the cells allow; the comparator at its top, a sampler a site
    either side; every block on the sites and on a row of its own bottom rail; a cell-free halo
    beside each block, in the rails' columns and under the sides' walls; the rails outside the
    sides; the die the DAC's height, the pins on its edges; the sides' obstructions mirrored."""
    site = ("core", 0.2, 1.8)
    plan = layout._floorplan(_blocks(free), 300.0, site)
    blocks = plan["blocks"]
    die_w = plan["die"][2]
    on = lambda value, step: abs(value / step - round(value / step)) < 1e-6
    for name, (x, y, _orient) in blocks.items():
        assert on(x, 0.2) and on(y - plan["core"][1], 1.8)
        # its bottom rail its own (an upper band's starts where its side's rows are)
        assert name.endswith("_hi") or on((y - plan["core"][1]) / 2, 1.8)
    p, n = (blocks["xdac_p_lo" if free else "xdac_p"], blocks["xdac_n_lo" if free else "xdac_n"])
    assert (p[2], n[2]) == ("R0", "MY")
    assert n[0] + 16.4 == pytest.approx(die_w - p[0])  # the N side the P side's mirror image
    comp, samp_p, samp_n = blocks["xcomp"], blocks["xsamp_p"], blocks["xsamp_n"]
    assert comp[0] + 13.6 / 2 == pytest.approx(die_w / 2, abs=0.2)
    assert samp_p[0] + 2.8 + 0.2 == pytest.approx(comp[0]) and samp_n[0] == pytest.approx(comp[0] + 13.6 + 0.2)
    assert samp_p[1] + 3.6 == pytest.approx(comp[1] + 10.8)  # their tops aligned
    assert p[0] + 16.4 < samp_p[0] and samp_n[0] + 2.8 < n[0]  # the column between the sides
    left, right = plan["rails"]
    assert 0 < left < p[0] and n[0] + 16.4 < right < die_w
    assert plan["die"][3] == pytest.approx(37.8) and plan["core"][1] == 0.0  # no margin above or below
    x0, x1 = plan["pins"]["x"]
    assert p[0] + 16.4 < x0 < samp_p[0] and samp_n[0] + 2.8 < x1 < n[0]  # the column's edges
    assert plan["pins"]["y"] == (pytest.approx((5.4, 34.2)) if free else ())
    walls = 2 if free else 0
    assert len(plan["halos"]) == 2 * len(blocks) + 2 + walls
    assert (0.0, 0.0, p[0], 37.8) in plan["halos"]  # the left rails' column
    if free:
        halos = [tuple(round(v, 4) for v in box) for box in plan["halos"]]
        assert (round(p[0], 4), 5.4, round(p[0] + 0.6, 4), 34.2) in halos  # a wall, a site either side
        assert (round(n[0] + 16.4 - 0.6, 4), 5.4, round(n[0] + 16.4, 4), 34.2) in halos  # mirrored
    if free:
        assert ("M4", p[0] + 1.0, plan["core"][1] + 6.0, p[0] + 2.0, plan["core"][1] + 30.0) in plan["obstructions"]
        mirrored = [box for box in plan["obstructions"] if box[1] > die_w / 2]
        assert mirrored == [("M4", n[0] + 16.4 - 2.0, plan["core"][1] + 6.0, n[0] + 16.4 - 1.0, plan["core"][1] + 30.0)]


def test_the_outside_rails_fit_the_tracks(tmp_path: Path) -> None:
    """A rail's middle on a track, the next free track a wire's spacing from it (the spacing table's
    longest run for the rail's width), as near the nominal width as the tracks allow; the pair's
    second rail on a track too."""
    lef = tmp_path / "tech.lef"
    lef.write_text(
        "MANUFACTURINGGRID 0.005 ;\nLAYER M2\n  TYPE ROUTING ;\n  DIRECTION VERTICAL ;\n"
        "  PITCH 0.25 ;\n  WIDTH 0.1 ;\n  SPACINGTABLE\n    PARALLELRUNLENGTH 0.00 1.00\n"
        "    WIDTH 0.00 0.1 0.1\n    WIDTH 0.50 0.1 0.2 ;\nEND M2\n"
    )
    width, space = layout._straps(lef, "M2")
    # a wide rail (the second row's spacing): three tracks from its middle to the next free one
    assert (width, space) == (pytest.approx(1.0), pytest.approx(0.5))
    assert width / 2 + 0.2 + 0.05 == pytest.approx(3 * 0.25)
    assert ((width + space) / 0.25) == pytest.approx(round((width + space) / 0.25))


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
    assert layout._site(lefs) == ("CoreSite", 0.48, 3.78)


def test_openroads_netlist_holds_the_kits_cells_and_the_blocks_abstracts() -> None:
    """The converter as OpenROAD reads it: its generic cells the kit's library cells, their signal
    pins alone; a block each of its abstracts, a scalar pin for each bus bit; no supply pin on an
    instance; its supplies one vdd and one vss; the hierarchy kept."""
    library = pytest.importorskip("pdk.ihp130.hdl21.cells")
    from flow.circuit.cells import cell

    Inner = h.Module(name="Inner")
    Inner.a, Inner.y = h.Input(), h.Output()
    Inner.vdd_d, Inner.vss_d = h.Inout(), h.Inout()
    Inner.Xinv = cell("inv", 1)(A=Inner.a, Y=Inner.y, VDD=Inner.vdd_d, VSS=Inner.vss_d)
    Top = h.Module(name="Top")
    Top.state = h.Signal(width=2)
    Top.vdd_d, Top.vdd_a = h.Power(direction=h.PortDir.INOUT), h.Power(direction=h.PortDir.INOUT)
    Top.vss_d = h.Ground(direction=h.PortDir.INOUT)
    Top.a = h.Input()
    Top.xinner = Inner(a=Top.a, y=Top.state[1], vdd_d=Top.vdd_d, vss_d=Top.vss_d)
    Block = h.ExternalModule(
        name="Block", port_list=[h.Input(name="dac_state", width=2), h.Inout(name="vdac"), h.Inout(name="vdd")]
    )
    Top.xblock = Block()(dac_state=Top.state, vdac=Top.a, vdd=Top.vdd_a)
    view = layout._verilog_view(
        Top,
        "ihp130",
        {"xblock": [("_lo", "adc_block_lo", ["dac_state_0", "dac_state_1"]), ("_hi", "adc_block_hi", ["vdac"])]},
    )
    assert view.name == "adc" and {"vdd", "vss", "a"} <= set(view.ports) and "vdd_a" not in view.ports
    lo, hi = view.instances["xblock_lo"], view.instances["xblock_hi"]
    assert lo.of.module.name == "adc_block_lo" and lo.conns["dac_state_1"].index == 1
    assert hi.of.module.name == "adc_block_hi" and hi.conns["vdac"] is view.a
    inverter = view.instances["xinner"].of.instances["Xinv"]
    target, _pins, _high, _low = library.GENERIC["inv_x1"]
    assert inverter.of.module.name == target and set(inverter.conns) == {"A", "Y"}
    assert view.instances["xinner"].conns["vdd_d"] is view.ports["vdd"]
    text = io.StringIO()
    h.netlist(view, text, fmt="verilog")
    assert "VDD" not in text.getvalue() and "module adc" in text.getvalue()


def test_a_generated_converter_is_placed_and_routed_by_openroad(tmp_path: Path) -> None:
    """FRIDA-1's converter in TSMC65 (its blocks as laid out): its DAC's sides the outline, each
    two bands with its free rows between them for the cells, the comparator and its samplers at
    the top of the column between them, the flow through to a routed DEF, its layout its blocks',
    its cells' and its routes', every supply label reached from its supply pins (skipped without
    the kit, OpenROAD or the blocks' layouts)."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    if shutil.which("openroad") is None:
        pytest.skip("OpenROAD is not on the PATH")
    try:
        gds = lay_out(Params(), "tsmc65", tmp_path)
    except LookupError as error:
        pytest.skip(f"the blocks are not laid out: {error}")
    assert "drc violations:" in (tmp_path / "openroad.log").read_text()
    record = json.loads((tmp_path / "blocks.json").read_text())
    # every cell's and block's supply label reached from the converter's own supply pins
    supplies = record["supplies"]
    assert set(supplies) == {"vdd", "vss"} and all("cells" in counts for counts in supplies.values())
    assert {holder: missed for counts in supplies.values() for holder, (_hit, missed) in counts.items() if missed} == {}
    plan = record["plan"]
    assert plan["stacked"] and plan["obstructions"]
    assert set(plan["blocks"]) == {"xdac_p_lo", "xdac_p_hi", "xdac_n_lo", "xdac_n_hi", "xcomp", "xsamp_p", "xsamp_n"}
    built = db.Layout()
    built.read(str(gds))
    names = {cell.name for cell in built.each_cell()}
    assert {record["blocks"][block]["cell"] for block in ("comp", "samp", "cap")} <= names
