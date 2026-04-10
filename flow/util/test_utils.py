"""Tests for flow/utils: netlist conversion, GDS cells, layer reading."""

import textwrap

import pytest

from flow.util.netlist import cdl_to_sp, clean_cdl

# =========================================================================
# Test data — inline netlists
# =========================================================================

SIMPLE_CDL = textwrap.dedent("""\
    *.BUSDELIMITER [

    .SUBCKT myamp inp inn outp outn vdd vss
    *.PININFO inp:I inn:I outp:O outn:O vdd:B vss:B
    MM0 outn inp vdd vdd pch_lvt l=60n w=1u m=1
    MM1 outp inn vdd vdd pch_lvt l=60n w=1u m=1
    .ENDS myamp
""")

CDL_WITH_SEPARATOR = textwrap.dedent("""\
    .SUBCKT wrapper a b vdd vss
    Xinst a b vdd vss / myamp
    .ENDS wrapper
""")

CDL_WITH_CAPACITOR = textwrap.dedent("""\
    .SUBCKT cdac top bot[1] bot[0]
    C1 top bot[1] capacitor c=100f
    C0 top bot[0] capacitor c=50f
    .ENDS cdac
""")

CDL_WITH_DNW = textwrap.dedent("""\
    .SUBCKT driver a z vdd vss
    Xx0 a z vdd vss CKXOR2D2LVT_dnw
    Xx1 a z vdd vss CKXOR2D4LVT_dnw
    .ENDS driver
""")

CDL_WITH_FILLERS = textwrap.dedent("""\
    .SUBCKT digital clk out vdd vss

    Xlogic clk out vdd vss BUFFD2LVT
    XFILLER_0_1 vdd vss DCAPLVT
    XFILLER_0_2 vdd vss DCAP8LVT
    XFILLER_0_3 vdd vss FILL1LVT

    .ENDS digital
""")

CDL_WITH_HIERARCHY = textwrap.dedent("""\
    .SUBCKT flat a b vdd vss

    Xtop/sub\\0/inv a b vdd vss INVLVT
    Xplace.net[3].buf a b vdd vss BUFLVT

    .ENDS flat
""")

VERILOG_MODULE = textwrap.dedent("""\
    module digital (
        input wire clk,
        output wire out,
        inout wire vdd, vss
    );
    endmodule
""")

# Minimal .lyt with a LEFDEF layer map
MINIMAL_LYT = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <technology>
     <name>test</name>
     <reader-options>
      <lefdef>
       <layer-map>layer_map('M1 : 19/0';'M2 : 20/0';'V1 : 21/0';'GATE : 7/0')</layer-map>
       <dbu>0.001</dbu>
      </lefdef>
     </reader-options>
    </technology>
""")


# =========================================================================
# cdl_to_sp
# =========================================================================


def test_cdl_to_sp_strips_busdelimiter(tmp_path):
    (tmp_path / "in.cdl").write_text(SIMPLE_CDL)
    cdl_to_sp(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert "BUSDELIMITER" not in text


def test_cdl_to_sp_strips_pininfo(tmp_path):
    (tmp_path / "in.cdl").write_text(SIMPLE_CDL)
    cdl_to_sp(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert "PININFO" not in text


def test_cdl_to_sp_removes_separator(tmp_path):
    (tmp_path / "in.cdl").write_text(CDL_WITH_SEPARATOR)
    cdl_to_sp(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert " / " not in text
    assert "myamp" in text


def test_cdl_to_sp_fixes_capacitor_syntax(tmp_path):
    (tmp_path / "in.cdl").write_text(CDL_WITH_CAPACITOR)
    cdl_to_sp(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert "capacitor c=" not in text
    assert "100f" in text
    assert "50f" in text


def test_cdl_to_sp_replaces_dnw_cells(tmp_path):
    (tmp_path / "in.cdl").write_text(CDL_WITH_DNW)
    cdl_to_sp(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert "_dnw" not in text
    assert "CKXOR2D2LVT" in text
    assert "CKXOR2D4LVT" in text


def test_cdl_to_sp_preserves_subckt_structure(tmp_path):
    (tmp_path / "in.cdl").write_text(SIMPLE_CDL)
    cdl_to_sp(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert ".SUBCKT myamp" in text
    assert ".ENDS myamp" in text
    assert "MM0" in text


# =========================================================================
# clean_cdl
# =========================================================================


def test_clean_cdl_removes_fillers(tmp_path):
    (tmp_path / "in.cdl").write_text(CDL_WITH_FILLERS)
    clean_cdl(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert "XFILLER" not in text
    assert "BUFFD2LVT" in text


def test_clean_cdl_cleans_hierarchy_separators(tmp_path):
    (tmp_path / "in.cdl").write_text(CDL_WITH_HIERARCHY)
    clean_cdl(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert "\\" not in text
    # instance line should have no forward slashes
    inst_lines = [l for l in text.splitlines() if l.startswith("X")]
    for l in inst_lines:
        assert "/" not in l


def test_clean_cdl_applies_base_transforms(tmp_path):
    combined = CDL_WITH_SEPARATOR + CDL_WITH_CAPACITOR
    (tmp_path / "in.cdl").write_text(combined)
    clean_cdl(tmp_path / "in.cdl", tmp_path / "out.sp")
    text = (tmp_path / "out.sp").read_text()
    assert " / " not in text
    assert "capacitor c=" not in text


def test_clean_cdl_verilog_port_reorder(tmp_path):
    (tmp_path / "in.cdl").write_text(CDL_WITH_FILLERS)
    (tmp_path / "mod.v").write_text(VERILOG_MODULE)
    clean_cdl(
        tmp_path / "in.cdl",
        tmp_path / "out.sp",
        verilog=tmp_path / "mod.v",
        module="digital",
    )
    text = (tmp_path / "out.sp").read_text()
    subckt_line = [l for l in text.splitlines() if l.startswith(".SUBCKT")][0]
    ports = subckt_line.split()[2:]
    assert ports == ["clk", "out", "vdd", "vss"]
    assert "*.PININFO" in text


def test_clean_cdl_bad_module_raises(tmp_path):
    (tmp_path / "in.cdl").write_text(CDL_WITH_FILLERS)
    (tmp_path / "mod.v").write_text(VERILOG_MODULE)
    with pytest.raises(ValueError, match="not found"):
        clean_cdl(
            tmp_path / "in.cdl",
            tmp_path / "out.sp",
            verilog=tmp_path / "mod.v",
            module="nonexistent",
        )


# =========================================================================
# gds — list_cells
# =========================================================================


def test_list_cells(tmp_path):
    import klayout.db as db

    ly = db.Layout()
    l1 = ly.layer(1, 0)

    inv = ly.create_cell("INV")
    inv.shapes(l1).insert(db.DBox(0, 0, 1, 2))

    buf = ly.create_cell("BUF")
    buf.shapes(l1).insert(db.DBox(0, 0, 2, 2))

    top = ly.create_cell("TOP")
    top.insert(db.DCellInstArray(inv.cell_index(), db.DTrans()))
    top.insert(db.DCellInstArray(buf.cell_index(), db.DTrans(db.DVector(5, 0))))

    gds = tmp_path / "test.gds"
    ly.write(str(gds))

    from flow.util.gds import list_cells

    cells = list_cells(gds)
    assert cells == ["BUF", "INV", "TOP"]


def test_list_cells_empty(tmp_path):
    import klayout.db as db

    ly = db.Layout()
    ly.create_cell("ONLY")
    gds = tmp_path / "single.gds"
    ly.write(str(gds))

    from flow.util.gds import list_cells

    assert list_cells(gds) == ["ONLY"]


# =========================================================================
# gds — list_layers
# =========================================================================


def test_gds_list_layers(tmp_path):
    import klayout.db as db

    ly = db.Layout()
    l1 = ly.layer(19, 0)
    l2 = ly.layer(20, 0)
    l3 = ly.layer(21, 0)

    cell = ly.create_cell("TOP")
    cell.shapes(l1).insert(db.DBox(0, 0, 1, 1))
    cell.shapes(l2).insert(db.DBox(0, 0, 2, 2))
    cell.shapes(l3).insert(db.DBox(0, 0, 3, 3))

    gds = tmp_path / "layers.gds"
    ly.write(str(gds))

    from flow.util.gds import list_layers

    layers = list_layers(gds)
    assert layers["19/0"] == (19, 0)
    assert layers["20/0"] == (20, 0)
    assert layers["21/0"] == (21, 0)
    assert len(layers) == 3


# =========================================================================
# lyt — list_layers
# =========================================================================


def test_lyt_list_layers(tmp_path):
    lyt_path = tmp_path / "test.lyt"
    lyt_path.write_text(MINIMAL_LYT)

    from flow.util.lyt import list_layers

    layers = list_layers(lyt_path)
    assert layers["M1"] == (19, 0)
    assert layers["M2"] == (20, 0)
    assert layers["V1"] == (21, 0)
    assert layers["GATE"] == (7, 0)
    assert len(layers) == 4


def test_list_layers_same_value_format(tmp_path):
    """Both gds.list_layers() and lyt.list_layers() return dict[str, tuple[int, int]]."""
    import klayout.db as db

    ly = db.Layout()
    cell = ly.create_cell("TOP")
    cell.shapes(ly.layer(19, 0)).insert(db.DBox(0, 0, 1, 1))
    gds = tmp_path / "fmt.gds"
    ly.write(str(gds))

    lyt_path = tmp_path / "fmt.lyt"
    lyt_path.write_text(MINIMAL_LYT)

    from flow.util.gds import list_layers as gds_list_layers
    from flow.util.lyt import list_layers as lyt_list_layers

    gds_layers = gds_list_layers(gds)
    lyt_layers = lyt_list_layers(lyt_path)

    # Both should have (19, 0) as a value for some key
    assert (19, 0) in gds_layers.values()
    assert (19, 0) in lyt_layers.values()

    # Values are all tuple[int, int]
    for v in gds_layers.values():
        assert isinstance(v, tuple) and len(v) == 2
    for v in lyt_layers.values():
        assert isinstance(v, tuple) and len(v) == 2
