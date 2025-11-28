* ========================================================================
* PMOS Sample Device
* ========================================================================

.subckt samp_pmos in out clk clk_b vdd_a vss_a
*.PININFO in:I out:O clk:I clk_b:I vdd_a:B vss_a:B

* PMOS pass transistor (conducts when clk_b is low)
* Note: clk pin unused (left floating for interface compatibility)
MP out clk_b in vdd_a pmos

.ends samp_pmos

.end
