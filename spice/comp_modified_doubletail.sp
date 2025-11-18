* Comparator Topology Netlists
* Figure 4.13(e): Modified Double-tail Comparator

* ========================================================================
* (e) Modified Double-tail Comparator
* ========================================================================
.SUBCKT comp_modified_doubletail in_p in_n out_p out_n clk clk_b vdd_a vss_a
*.PININFO in_p:I in_n:I out_p:O out_n:O clk:I clk_b:I vdd_a:B vss_a:B

* First stage
* Tail transistor
MNtail1 tail1 clk vss_a vss_a nmos

* Input differential pair
MNinn midn in_n tail1 vss_a nmos
MNinp midp in_p tail1 vss_a nmos

* First stage PMOS loads (reset when clk low)
MPswMN midn clk vdd_a vdd_a pmos
MPswMP midp clk vdd_a vdd_a pmos

* Second stage with multiple clocked tails
* Two separate tail transistors for cross-coupled pair
MNtailCN tailCN clk_b vss_a vss_a nmos
MNtailCP tailCP clk_b vss_a vss_a nmos

* Cross-coupled NMOS pair with separate tails
MNnfbn out_p out_n midn tailCN nmos
MNnfbp out_n out_p midp tailCP nmos

* Output reset switches
MPswon out_n clk vdd_a vdd_a pmos
MPswop out_p clk vdd_a vdd_a pmos

* Cross-coupled PMOS latch
MPpfbn out_n out_p vdd_a vdd_a pmos
MPpfbp out_p out_n vdd_a vdd_a pmos

.ENDS comp_modified_doubletail
