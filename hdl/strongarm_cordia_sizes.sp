
.subckt latch clk gnd inn inp outn outp vdd
m0 tail clk gnd gnd nmos l=800n w=550.n m=1
m2 net037 inn tail gnd nmos l=300n w=1.u1u m=4
m8 tail gnd gnd gnd nmos l=60n w=1.u1u m=4
m1 net031 inp tail gnd nmos l=300n w=1.u1u m=4
m3 outn outp net031 gnd nmos l=350.n w=750.n m=4
m4 outp outn net037 gnd nmos l=350.n w=750.n m=4
ms2 net037 clk vdd vdd pmos l=60n w=500n m=2
ms4 outp clk vdd vdd pmos l=60n w=500n m=2
ms1 net031 clk vdd vdd pmos l=60n w=500n m=2
m7 tail clk vdd vdd pmos l=60n w=500n m=1
m6 outp outn vdd vdd pmos l=1u w=2u m=2
m5 outn outp vdd vdd pmos l=1u w=2u m=2
ms3 outn clk vdd vdd pmos l=60n w=500n m=2
.ends
