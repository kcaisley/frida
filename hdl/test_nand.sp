* CMOS NAND Gate
.SUBCKT nand a b out vdd vss
M1 out a vss vss NMOS
M2 out b vss vss NMOS
M3 out a vdd vdd PMOS
M4 out b vdd vdd PMOS
.ENDS
