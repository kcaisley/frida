* CMOS nand gate with mistakes in connections to check for topology differences.
.SUBCKT nand in out vdd vss
M1 out a vss vss NMOS
M2 out a vss vss NMOS
M3 out a vdd vdd PMOS
M4 out b vdd vdd PMOS
.ENDS
