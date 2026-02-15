.SUBCKT latch CLK vss INN INP OUTN OUTP vdd
*.PININFO CLK:I INN:I INP:I OUTN:O OUTP:O vss:B vdd:B
MM0 tail CLK vss vss nmos 
MM2 net037 INN tail vss nmos
MM1 net031 INP tail vss nmos
MM3 OUTN OUTP net031 vss nmos
MM4 OUTP OUTN net037 vss nmos
MS2 net037 CLK vdd vdd pmos
MS4 OUTP CLK vdd vdd pmos
MS1 net031 CLK vdd vdd pmos
MM7 tail CLK vdd vdd pmos
MM6 OUTP OUTN vdd vdd pmos
MM5 OUTN OUTP vdd vdd pmos
MS3 OUTN CLK vdd vdd pmos
.ENDS latch