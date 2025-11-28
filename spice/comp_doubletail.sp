* Double-tail comparator

.subckt comp_doubletail in_p in_n out_p out_n clk clk_b vdd_a vss_a
*.PININFO in_p:I in_n:I out_p:O out_n:O clk:I clk_b:I vdd_a:B vss_a:B

* First stage (input stage)
* Tail transistor
MNtail1 tail1 clk vss_a vss_a nmos

* Input differential pair
MNinn midn in_n tail1 vss_a nmos
MNinp midp in_p tail1 vss_a nmos

* First stage PMOS loads (reset when clk low)
MPswMN midn clk vdd_a vdd_a pmos
MPswMP midp clk vdd_a vdd_a pmos

* Second stage (output stage with cross-coupled latch)
* Tail transistor for second stage
MNtail2 tail2 clk_b vss_a vss_a nmos

* Cross-coupled NMOS pair
MNnfbn out_p out_n midn vss_a nmos
MNnfbp out_n out_p midp vss_a nmos

* Output reset switches
MPswon out_n clk vdd_a vdd_a pmos
MPswop out_p clk vdd_a vdd_a pmos

* Cross-coupled PMOS latch
MPpfbn out_n out_p vdd_a vdd_a pmos
MPpfbp out_p out_n vdd_a vdd_a pmos

.ends comp_doubletail

.end
