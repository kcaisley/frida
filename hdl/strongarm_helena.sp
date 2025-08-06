************************************************************************
* Library Name: logic
* Cell Name:    comparator_latch
* View Name:    schematic
************************************************************************

.SUBCKT comparator_latch clock inn inp outn outp sub vcc vee
*.PININFO clock:I inn:I inp:I sub:I vcc:I vee:I outn:O outp:O
Mn5 net7 outn outp net1 log_nmos
Mn4 net6 outp outn net3 log_nmos
Mn3 net4 net2 clock net5 log_nmos
Mn2 sub net3 inn net2 log_nmos
Mn1 sub net1 inp net2 log_nmos
Mp5 vcc net1 clock vcc log_pmos
Mp6 vcc outn clock vcc log_pmos
Mp3 vcc net3 clock vcc log_pmos
Mp2 vcc outp clock vcc log_pmos
Mp1 vcc outn outp vcc log_pmos
Mp4 vcc outp outn vcc log_pmos
.ENDS