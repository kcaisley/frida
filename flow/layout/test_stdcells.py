"""Tests for recognizing standard cells in transistor netlists."""

from .stdcells import library, recognize

LIB = """\
.subckt INVX1 A Y VDD VSS
MN Y A VSS VSS nfet w=0.2u l=0.03u
MP Y A VDD VDD pfet w=0.3u l=0.03u
.ends
.subckt INVX4 A Y VDD VSS
MN0 Y A VSS VSS nfet w=0.4u l=0.03u
MN1 Y A VSS VSS nfet w=0.4u l=0.03u
MP0 Y A VDD VDD pfet w=1.2e-06 l=3e-08
.ends
.subckt NOR2X2 A1 A2 ZN VDD VSS
MN0 ZN A1 VSS VSS nfet w=0.2u l=0.03u
MN1 ZN A2 VSS VSS nfet w=0.2u l=0.03u
MP0 a A2 VDD VDD pfet w=0.3u l=0.03u
MP1 ZN A1 a VDD pfet w=0.3u l=0.03u
MP2 b A2 VDD VDD pfet w=0.3u l=0.03u
MP3 ZN A1 b VDD pfet w=0.3u l=0.03u
.ends
.subckt FILL VDD VSS
.ends
"""
CELLS = ("INVX1", "INVX4", "NOR2X2", "FILL")
LIB_CELLS = library(LIB, CELLS, ("VDD", "VSS"))
NETLIST = """\
.subckt top in out vdd vss
Mbig_n mid in vss vss n w=800n l=30n nf=2 m=1
Mbig_p mid in vdd vdd p w=1200n l=30n nf=2 m=1
Mnor_n_a out mid vss vss n w=400n l=30n nf=1 m=1
Mnor_n_b out in vss vss n w=400n l=30n nf=1 m=1
Mnor_p_a stack in vdd vdd p w=600n l=30n nf=1 m=1
Mnor_p_b out mid stack vdd p w=600n l=30n nf=1 m=1
Mtail_n tail in vss vss n w=200n l=300n nf=1 m=1
Mtail_p tail in vdd vdd p w=300n l=300n nf=1 m=1
.ends top
"""


def test_library_reads_units_and_supplies() -> None:
    pins, devs = LIB_CELLS["INVX4"]
    assert pins == ["A", "Y", "VDD", "VSS"] and LIB_CELLS["FILL"] == (["VDD", "VSS"], [])
    assert [(v.pol, round(v.w), round(v.l)) for v in devs] == [("n", 400, 30), ("n", 400, 30), ("p", 1200, 30)]


def test_gates_become_cells_of_the_closest_drive() -> None:
    text, cells = recognize(NETLIST, LIB_CELLS)
    assert cells == {"Xnor": "NOR2X2", "Xbig": "INVX4"}
    lines = text.splitlines()
    assert "Xbig in mid vdd vss INVX4" in lines
    assert "Xnor mid in out vdd vss NOR2X2" in lines  # A1 drives the PMOS next to the output
    assert not any(line.startswith(("Mbig", "Mnor")) for line in lines)


def test_long_devices_and_ports_inside_a_group_stay_transistors() -> None:
    text, cells = recognize(NETLIST, LIB_CELLS)
    assert "Xtail" not in cells  # an inverter's shape, at ten times the cells' length
    assert sum(line.startswith("Mtail") for line in text.splitlines()) == 2
    # a cell's internal net that is a port of the netlist: no NOR2 there
    exposed = NETLIST.replace(".subckt top in out vdd vss", ".subckt top in out stack vdd vss")
    assert "Xnor" not in recognize(exposed, LIB_CELLS)[1]


def test_mos_width_is_total_in_both_conventions() -> None:
    # 2 copies of 4 fingers of 500 nm: 4 um in all, 8 fingers
    total = library(".subckt C A VDD VSS\nMN A A VSS VSS n w=2u l=30n nf=4 m=2\n.ends\n", ["C"], ("VDD", "VSS"))
    per_finger = library(
        ".subckt C A VDD VSS\nMN A A VSS VSS n w=500n l=30n nf=4 m=2\n.ends\n", ["C"], ("VDD", "VSS"), w_per_finger=True
    )
    for lib in (total, per_finger):
        (mos,) = lib["C"][1]
        assert (round(mos.w), mos.nf) == (4000, 8)


def test_gates_are_found_in_a_per_finger_netlist() -> None:
    # the inverter pair written per finger: Mbig_n is 2 fingers of 400 nm, as INVX4's two 400 nm devices
    netlist = NETLIST.replace("w=800n l=30n nf=2", "w=400n l=30n nf=2").replace(
        "w=1200n l=30n nf=2", "w=600n l=30n nf=2"
    )
    assert recognize(netlist, LIB_CELLS, w_per_finger=True)[1] == {"Xnor": "NOR2X2", "Xbig": "INVX4"}
