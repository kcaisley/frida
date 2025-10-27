* Generic CMOS Inverter
* Technology-independent schematic using generic device wrappers
* Compatible with 28nm and 65nm via tech_wrapper_*.sp

* Inverter subcircuit
* Ports: in out vdd vss
* Parameters: wp, wn, lp, ln, m (multiplier)
.subckt inverter in out vdd vss wp='WP_UNIT' wn='WN_UNIT' lp='LMIN' ln='LMIN' m=1

* PMOS pull-up: out = vdd when in = low
xmp out in vdd vdd pch_generic w=wp l=lp m=m

* NMOS pull-down: out = vss when in = high
xmn out in vss vss nch_generic w=wn l=ln m=m

.ends inverter
