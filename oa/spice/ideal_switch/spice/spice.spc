.model swmod sw ron=1e-6 roff=1e100 vt=1.65

.subckt ideal_switch a b control
s1 a b control gnd swmod 
.ends


