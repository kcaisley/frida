* Comparator Topology Netlists
* Figure 4.13(b): Triple-tail Comparator

* ========================================================================
* (b) Triple-tail Comparator
* ========================================================================
.SUBCKT comp_tripletail in_p in_n out_p out_n clk clk_b vdd_a vss_a
*.PININFO in_p:I in_n:I out_p:O out_n:O clk:I clk_b:I vdd_a:B vss_a:B

* Left tail transistor
MNtailL tailL clk vss_a vss_a nmos

* Input differential pair (left side)
MNinnL xn in_n tailL vss_a nmos
MNinpL xp in_p tailL vss_a nmos

* Center cross-coupled pair with dedicated tails
MNtailCN tailCN clk_b vss_a vss_a nmos
MNtailCP tailCP clk_b vss_a vss_a nmos
MNxcn yn xn tailCN vss_a nmos
MNxcp yp xp tailCP vss_a nmos

* Right tail transistor
MNtailR tailR clk vss_a vss_a nmos

* Cross-coupled output pair
MNnfbn out_p out_n yp vss_a nmos
MNnfbp out_n out_p yn vss_a nmos

* Reset switches
MPswon out_n clk vdd_a vdd_a pmos
MPswop out_p clk vdd_a vdd_a pmos

* PMOS latch
MPpfbn out_n out_p vdd_a vdd_a pmos
MPpfbp out_p out_n vdd_a vdd_a pmos

.ENDS comp_tripletail
