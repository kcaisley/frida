* StrongARM comparator

.subckt comp_strongarm in_p in_n out_p out_n clk clk_b vdd_a vss_a
*.PININFO in_p:I in_n:I out_p:O out_n:O clk:I clk_b:I vdd_a:B vss_a:B

* Input differential pair
MNinn midn in_n tail vss_a nmos
MNinp midp in_p tail vss_a nmos

* Tail transistor (clock-controlled)
MNtail tail clk vss_a vss_a nmos

* Cross-coupled NMOS pair
MNnfbn out_p out_n midn vss_a nmos
MNnfbp out_n out_p midp vss_a nmos

* Reset switches (PMOS - active when clk low)
MPswon out_n clk vdd_a vdd_a pmos
MPswop out_p clk vdd_a vdd_a pmos

* Cross-coupled PMOS pair (latch)
MPpfbn out_n out_p vdd_a vdd_a pmos
MPpfbp out_p out_n vdd_a vdd_a pmos

.ends comp_strongarm

.end
