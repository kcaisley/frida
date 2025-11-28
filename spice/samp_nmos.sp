* ========================================================================
* NMOS Sample Device
* ========================================================================

.subckt samp_nmos in out clk clk_b vdd_a vss_a
*.PININFO in:I out:O clk:I clk_b:I vdd_a:B vss_a:B

* NMOS pass transistor (conducts when clk is high)
* Note: clk_b pin unused (left floating for interface compatibility)
MN out clk in vss_a nmos

.ends samp_nmos

.end
