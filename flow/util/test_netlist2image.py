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
