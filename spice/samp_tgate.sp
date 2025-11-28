* ========================================================================
* Transmission Gate Sample-and-Hold
* ========================================================================

.subckt samp_tgate in out clk clk_b vdd_a vss_a
*.PININFO in:I out:O clk:I clk_b:I vdd_a:B vss_a:B

* NMOS pass transistor (conducts when clk is high)
MN out clk in vss_a nmos

* PMOS pass transistor (conducts when clk_b is low)
MP out clk_b in vdd_a pmos

.ends samp_tgate

.end
