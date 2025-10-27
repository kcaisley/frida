* Technology Wrapper for TSMC 28nm HPC+
* Maps generic device names to TSMC 28nm PDK models
* Compatible with Spectre, HSPICE, and Solido/AFS

* Generic NMOS wrapper: nch_generic -> nch_lvt (28nm LVT)
* Usage: xn d g s b nch_generic w=<w> l=<l> m=<m>
.subckt nch_generic d g s b w=120n l=30n m=1
mn d g s b nch_lvt w=w l=l m=m
.ends nch_generic

* Generic PMOS wrapper: pch_generic -> pch_lvt (28nm LVT)
* Usage: xp d g s b pch_generic w=<w> l=<l> m=<m>
.subckt pch_generic d g s b w=240n l=30n m=1
mp d g s b pch_lvt w=w l=l m=m
.ends pch_generic

* Technology parameters
.param VDD_NOM=0.9
.param VSS_NOM=0
.param LMIN=30n
.param WN_UNIT=120n
.param WP_UNIT=240n
.param TEMP_NOM=27
