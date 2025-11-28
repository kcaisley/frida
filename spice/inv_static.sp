* ========================================================================
* CMOS Inverter
* ========================================================================

.subckt gate_inv in out vdd_a vss_a
*.PININFO in:I out:O vdd_a:B vss_a:B

* NMOS pull-down (conducts when in is high)
MN out in vss_a vss_a nmos

* PMOS pull-up (conducts when in is low)
MP out in vdd_a vdd_a pmos

.ends gate_inv

.end
