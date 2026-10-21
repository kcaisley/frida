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
