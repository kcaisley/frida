* ========================================================================
* CMOS 2-Input NAND Gate
* ========================================================================

.subckt gate_nand2 a b out vdd_a vss_a
*.PININFO a:I b:I out:O vdd_a:B vss_a:B

* NMOS pull-down network (series - both must be high for low output)
MNa net1 a vss_a vss_a nmos
MNb out b net1 vss_a nmos

* PMOS pull-up network (parallel - either low gives high output)
MPa out a vdd_a vdd_a pmos
MPb out b vdd_a vdd_a pmos

.ends gate_nand2

.end
