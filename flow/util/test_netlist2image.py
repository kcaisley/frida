"""Stage and symmetry structure of the netlist schematic renderer."""

import xml.etree.ElementTree as ET
from pathlib import Path

from flow.util.netlist2image import render

# A StrongARM core followed by two inverters: one dynamic stage, then one static stack.
NETLIST = """
.subckt sa inp inn outp outn clk vdd vss
Mdiff_p xn inp tail vss nmos
Mdiff_n xp inn tail vss nmos
Mtail tail clk vss vss nmos
Mrst_p xn clk vdd vdd pmos
Mrst_n xp clk vdd vdd pmos
Mcross_on_p lp ln xp vss nmos
Mcross_on_n ln lp xn vss nmos
Mcross_init_p lp ln vdd vdd pmos
Mcross_init_n ln lp vdd vdd pmos
Minner_p lp clk vdd vdd pmos
Minner_n ln clk vdd vdd pmos
Minv_p_n outn lp vss vss nmos
Minv_p_p outn lp vdd vdd pmos
Minv_n_n outp ln vss vss nmos
Minv_n_p outp ln vdd vdd pmos
.ends
"""


def test_strongarm_is_one_stage_and_the_inverters_one_stack(tmp_path: Path) -> None:
    netlist = tmp_path / "sa.sp"
    netlist.write_text(NETLIST)
    svg = tmp_path / "sa.svg"
    stacks = render(netlist, svg)
    assert len(stacks) == 2
    assert {name for name in stacks[0]} == {
        "Mdiff_p",
        "Mdiff_n",
        "Mtail",
        "Mrst_p",
        "Mrst_n",
        "Mcross_on_p",
        "Mcross_on_n",
        "Mcross_init_p",
        "Mcross_init_n",
        "Minner_p",
        "Minner_n",
    }
    assert set(stacks[1]) == {"Minv_p_n", "Minv_p_p", "Minv_n_n", "Minv_n_p"}
    root = ET.parse(svg).getroot()
    texts = {t.text for t in root.iter("{http://www.w3.org/2000/svg}text")}
    # single-gate inputs get flags, the outputs flags at the trunk ends, clk a label per gate
    assert {"inp", "inn", "outp", "outn", "clk"} <= texts


# A CML latch: the input and hold pairs both on the clock pair's drains, side by side.
CML_LATCH = """
.subckt latch inp inn clkp clkn outp outn vbn vbp vdd vss
Mtail tail vbn vss vss nmos
Mclk_p track clkp tail vss nmos
Mclk_n hold clkn tail vss nmos
Min_p outn inp track vss nmos
Min_n outp inn track vss nmos
Mhold_p outn outp hold vss nmos
Mhold_n outp outn hold vss nmos
Mload_p outp vbp vdd vdd pmos
Mload_n outn vbp vdd vdd pmos
.ends
"""


# A CML XOR: four two-device branches, both outputs on loads above and branches below.
CML_XOR = """
.subckt xor inp inn clkp clkn outp outn vbn vbp vdd vss
Mtail tail vbn vss vss nmos
Mbot_ap xap inp tail vss nmos
Mtop_ap outp clkp xap vss nmos
Mbot_an xan inn tail vss nmos
Mtop_an outp clkn xan vss nmos
Mbot_bp xbp clkp tail vss nmos
Mtop_bp outn inn xbp vss nmos
Mbot_bn xbn clkn tail vss nmos
Mtop_bn outn inp xbn vss nmos
Mload_p outp vbp vdd vdd pmos
Mdiode_p outp outp vdd vdd pmos
Mload_n outn vbp vdd vdd pmos
Mdiode_n outn outn vdd vdd pmos
.ends
"""


def _junctions_apart(svg: Path) -> None:
    """No two junctions in one column within two tracks: two nets' wires there read as one (the
    outputs drawn tied together, where a load's drain ran through the other output's trunk)."""
    from flow.util.netlist2image import TRACK

    dots = [
        (float(c.get("cx")), float(c.get("cy")))
        for c in ET.parse(svg).getroot().iter("{http://www.w3.org/2000/svg}circle")
        if c.get("fill") == "#000"  # junctions, not the symbols' gate bubbles
    ]
    assert dots
    for i, (x, y) in enumerate(dots):
        for x2, y2 in dots[i + 1 :]:
            assert not (abs(x - x2) < 1 and abs(y - y2) <= 2 * TRACK), (x, y, x2, y2)


def test_cml_latch_keeps_its_outputs_apart(tmp_path: Path) -> None:
    from flow.util.netlist2image import levels, parse, stages, symmetry

    netlist = tmp_path / "latch.sp"
    netlist.write_text(CML_LATCH)
    ports, devs = parse(netlist)
    row, _ = levels(devs, stages(ports, devs, symmetry(devs, None)[2]))
    # parallel pairs share a row: one on another's common source does not push it down a row
    assert row["Min_p"] == row["Min_n"] == row["Mhold_p"] == row["Mhold_n"]
    assert row["Mclk_p"] == row["Mclk_n"]
    svg = tmp_path / "latch.svg"
    render(netlist, svg)
    _junctions_apart(svg)


def test_cml_xor_breaks_a_wire_where_the_other_output_crosses(tmp_path: Path) -> None:
    netlist = tmp_path / "xor.sp"
    netlist.write_text(CML_XOR)
    svg = tmp_path / "xor.svg"
    render(netlist, svg)
    _junctions_apart(svg)
    # the outputs must cross (loads above and branches below in interleaved order): each crossing
    # a break in the wire, a move within its path, so it does not read as a second junction
    # wires are the drawing's own paths; the symbols' sit in groups of their own
    wires = [e.get("d") for e in ET.parse(svg).getroot().findall("{http://www.w3.org/2000/svg}path")]
    broken = [d for d in wires if " M" in d]
    assert len(broken) >= 2


def test_a_block_of_inverters_and_capacitor_units_draws_its_chains(tmp_path: Path) -> None:
    """A block's top of cells (no transistor): each chain from its input's flag through NOT gates,
    their supplies drawn, to its stage's pieces as one capacitor (×N) on the top plate's bus."""
    netlist = tmp_path / "block.sp"
    netlist.write_text(
        ".subckt inv_2n2p1f A Y VDD VSS\n"
        "mn Y A VSS VSS nmos w=240n l=100n nf=1\n"
        "mp Y A VDD VDD pmos w=240n l=100n nf=1\n"
        ".ends inv_2n2p1f\n"
        ".subckt unit_a INNER TOP SHIELD\n"
        "X0 INNER TOP SHIELD fmomcap style=ring length=4230\n"
        ".ends unit_a\n"
        ".subckt block in0 in1 top vdd vss\n"
        "Xi0 in0 n0 vdd vss inv_2n2p1f\n"
        "Xi1 n0 plate0 vdd vss inv_2n2p1f\n"
        "Xc0 plate0 top vss unit_a\n"
        "Xc1 plate0 top vss unit_a\n"
        "Xi2 in1 plate1 vdd vss inv_2n2p1f\n"
        "Xc2 plate1 top vss unit_a\n"
        ".ends block\n"
    )
    out = tmp_path / "block.svg"
    render(netlist, out)
    svg = out.read_text()
    assert svg.count("M8,2 L30,15 L8,28 Z") == 3  # three NOT gates
    assert "×2" in svg and "Xc2" in svg  # stage 0's two pieces as one, stage 1's alone
    assert ">top<" in svg and "4.23 µm" in svg  # the top plate's flag, the pieces' length
    assert svg.count("M2,0 H14 M8,0 V10") == 3  # each gate's vdd
    assert svg.count("Wn/Wp 0.24/0.24") == 3  # each gate's widths, in um


def test_a_top_of_subcircuits_draws_what_they_hold(tmp_path: Path) -> None:
    """Instances of subcircuits that are not cells (a side, a driver) stand as what they hold, two
    levels down: ports by position (a bus bit), their own nets and names scoped by the instance, an
    inverter and a device called with its parameters (fmomcap) kept whole; drawn as a column per top
    plate, each chain as many gates as its driver holds inverters."""
    from flow.util.netlist2image import _expanded, _subcircuits

    text = (
        ".subckt inv A Y VDD VSS\n"
        "mn Y A VSS VSS nmos w=240n l=100n nf=1\n"
        "mp Y A VDD VDD pmos w=480n l=100n nf=1\n"
        ".ends inv\n"
        ".subckt buf a y vdd vss\n"
        "Xinv0 a n0 vdd vss inv\n"
        "Xinv1 n0 y vdd vss inv\n"
        ".ends buf\n"
        ".subckt side state_1 state_0 vdac vdd vss\n"
        "Xdrive_0 state_0 main_0 vdd vss buf\n"
        "Xdrive_1 state_1 main_1 vdd vss inv\n"
        "Xc_0_0 main_0 vdac vss fmomcap c=2f style=ring layers=3 length=4230\n"
        "Xc_0_1 main_0 vdac vss fmomcap c=2f style=ring layers=3 length=4230\n"
        "Xc_1_0 main_1 vdac vss fmomcap c=1f style=ring layers=3 length=2030\n"
        ".ends side\n"
        ".subckt top st_p_1 st_p_0 st_n_1 st_n_0 vdac_p vdac_n vdd vss\n"
        "Xside_p st_p_1 st_p_0 vdac_p vdd vss side\n"
        "Xside_n st_n_1 st_n_0 vdac_n vdd vss side\n"
        ".ends top\n"
    )
    subs = _subcircuits(text)
    defs = {name.lower(): (ports, elements) for name, ports, elements in subs[:-1]}
    flat = {f[0]: f[1:] for f in _expanded(subs[-1][2], defs)}
    assert len(flat) == 2 * (2 + 1 + 3)
    assert flat["Xside_p.drive_0.inv0"][:2] == ["st_p_0", "side_p.drive_0.n0"]  # bit 0 by position
    assert flat["Xside_p.drive_0.inv1"][:2] == ["side_p.drive_0.n0", "side_p.main_0"]
    assert flat["Xside_n.drive_1"] == ["st_n_1", "side_n.main_1", "vdd", "vss", "inv"]  # a cell stays whole
    assert flat["Xside_n.c_1_0"] == ["side_n.main_1", "vdac_n", "vss", "fmomcap",
                                     "c=1f", "style=ring", "layers=3", "length=2030"]  # fmt: skip
    netlist = tmp_path / "top.sp"
    netlist.write_text(text)
    out = tmp_path / "top.svg"
    render(netlist, out)
    svg = out.read_text()
    assert svg.count("M8,2 L30,15 L8,28 Z") == 2 * (2 + 1)  # per side: the buffer's two gates, the inverter
    assert all(f">{net}<" in svg for net in ("st_p_0", "st_p_1", "st_n_0", "st_n_1", "vdac_p", "vdac_n"))
    assert svg.count('class="nodelabel">×2<') == 2  # each side's stage 0, its two pieces as one
    assert ">Xside_p.c_1_0<" in svg and "4.23 µm" in svg and "2.03 µm" in svg


def test_a_transmission_gate_is_drawn_on_its_side(tmp_path: Path) -> None:
    """A pass device (drain and source off the rails, one of them a port) lies on its side, drain and
    source on one line: the PMOS above with its gate up, the NMOS below with its gate down, the
    earlier port (vin) on the left, its flag pointing out; a StrongARM keeps its upright devices."""
    from flow.util.netlist2image import Skin, parse, passes

    netlist = tmp_path / "tgate.sp"
    netlist.write_text(
        ".subckt samp vin vout clk clk_b vdd vss\nMn vout clk vin vss nmos\nMp vout clk_b vin vdd pmos\n.ends\n"
    )
    ports, devs = parse(netlist)
    passes(ports, devs)
    # the source (vin) is the earlier port: on the left
    assert devs["Mn"]["pass"] is True and devs["Mp"]["pass"] is True
    svg = tmp_path / "tgate.svg"
    render(netlist, svg)
    text = svg.read_text()
    skin = Skin()
    assert {"mos_n_down", "mos_p_up", "moscap_n", "moscap_p"} <= set(skin.types)
    shapes = {
        kind: "".join(ET.tostring(e, encoding="unicode") for e in skin.types[kind][1])
        for kind in ("mos_n_down", "mos_p_up")
    }
    assert "M16,36 H48 M32,36 V48" in shapes["mos_n_down"] and "M32,16 V28" in shapes["mos_p_up"]
    assert "M16,36 H48 M32,36 V48" in text and "M32,16 V28" in text
    # the PMOS's symbol above the NMOS's, in one column
    groups = text.split('<g transform="translate(')[1:]
    places = {
        name: tuple(float(v) for v in next(g for g in groups if f">{name}</text>" in g).split(")")[0].split(","))
        for name in ("Mn", "Mp")
    }
    assert places["Mp"][0] == places["Mn"][0] and places["Mp"][1] < places["Mn"][1]
    # a PMOS whose drain the netlist puts on vdd: drawn turned, vdd on top (its source)
    pre = tmp_path / "pre.sp"
    pre.write_text(".subckt p top gate vdd\nMpre vdd gate top vdd pmos\n.ends\n")
    found = parse(pre)
    passes(*found)
    assert (found[1]["Mpre"]["s"], found[1]["Mpre"]["d"]) == ("vdd", "top")
    # a MOS capacitor (drain and source one net): gate up, its legs tied below, an NMOS's too
    cap = tmp_path / "cap.sp"
    cap.write_text(".subckt c top bot vss\nMcap bot top bot vss nmos\n.ends\n")
    found = parse(cap)
    passes(*found)
    assert found[1]["Mcap"].get("cap") and "pass" not in found[1]["Mcap"]
    render(cap, tmp_path / "cap.svg")
    assert "V58 H0 V48 M32,58 V64" in (tmp_path / "cap.svg").read_text()
    sa = tmp_path / "sa.sp"
    sa.write_text(NETLIST)
    found = parse(sa)
    passes(*found)
    assert not any("pass" in d for d in found[1].values())
