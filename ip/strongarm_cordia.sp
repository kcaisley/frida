************************************************************************
* Library Name: CoRDIA_ADC_01
* Cell Name:    LATCH
* View Name:    schematic
************************************************************************

.SUBCKT LATCH CLK GND INN INP OUTN OUTP VDD
*.PININFO CLK:I INN:I INP:I OUTN:O OUTP:O GND:B VDD:B
MM0 tail CLK GND GND nch_lvt_dnw l=800n w=550.0n m=1
MM2 net037 INN tail GND nch_lvt_dnw l=300n w=1.1u m=4
MM8<3> tail GND GND GND nch_lvt_dnw l=60n w=1.1u m=1
MM8<2> tail GND GND GND nch_lvt_dnw l=60n w=1.1u m=1
MM8<1> tail GND GND GND nch_lvt_dnw l=60n w=1.1u m=1
MM8<0> tail GND GND GND nch_lvt_dnw l=60n w=1.1u m=1
MM1 net031 INP tail GND nch_lvt_dnw l=300n w=1.1u m=4
MM3 OUTN OUTP net031 GND nch_lvt_dnw l=350.0n w=750.0n m=4
MM4 OUTP OUTN net037 GND nch_lvt_dnw l=350.0n w=750.0n m=4
MS2 net037 CLK VDD VDD pch_lvt l=60n w=500n m=2
MS4 OUTP CLK VDD VDD pch_lvt l=60n w=500n m=2
MS1 net031 CLK VDD VDD pch_lvt l=60n w=500n m=2
MM7 tail CLK VDD VDD pch_lvt l=60n w=500n m=1
MM6 OUTP OUTN VDD VDD pch_lvt l=1u w=2u m=2
MM5 OUTN OUTP VDD VDD pch_lvt l=1u w=2u m=2
MS3 OUTN CLK VDD VDD pch_lvt l=60n w=500n m=2
.ENDS
