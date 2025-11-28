* Self-timed modified double-tail comparator

.subckt comp_selfmoddoubletail in_p in_n out_p out_n clk clk_b vdd_a vss_a
*.PININFO in_p:I in_n:I out_p:O out_n:O clk:I clk_b:I vdd_a:B vss_a:B

* First stage (input stage)
* Tail transistor
MNtail1 tail1 clk vss_a vss_a nmos

* Input differential pair
MNinn xn in_n tail1 vss_a nmos
MNinp xp in_p tail1 vss_a nmos

* First stage intermediate nodes
MNxn midn xn vss_a vss_a nmos
MNxp midp xp vss_a vss_a nmos

* First stage cross-coupled PMOS loads
MPldMN midn xp vdd_a vdd_a pmos
MPldMP midp xn vdd_a vdd_a pmos

* Reset switches for intermediate nodes
MPswMN xn clk vdd_a vdd_a pmos
MPswMP xp clk vdd_a vdd_a pmos

* Second stage with self-timed separate tails
* Two tail transistors controlled by first stage outputs
MNtailCN tailCN midn vss_a vss_a nmos
MNtailCP tailCP midp vss_a vss_a nmos

* Cross-coupled NMOS pair with separate tails
MNnfbn out_p out_n midp tailCN nmos
MNnfbp out_n out_p midn tailCP nmos

* Output reset switches
MPswon out_n clk vdd_a vdd_a pmos
MPswop out_p clk vdd_a vdd_a pmos

* Cross-coupled PMOS latch
MPpfbn out_n out_p vdd_a vdd_a pmos
MPpfbp out_p out_n vdd_a vdd_a pmos

.ends comp_selfmoddoubletail

.end
