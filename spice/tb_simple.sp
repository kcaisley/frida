* Simple test to check if PDK and basic setup works
.lib '../../asiclab/tech/tsmc65/spice/models/toplevel.l' tt_lib

* Simple voltage sources
vdd vdd 0 1.2
vin in 0 pulse(0 1.2 1n 0.1n 0.1n 4.8n 10n)

* Simple resistor load  
rload out 0 1k

* Simple inverter using transistors
mn out in 0 0 nch_lvt w=240n l=60n m=1
mp out in vdd vdd pch_lvt w=240n l=60n m=1

* Save signals
.save v(in) v(out)

* Control section
.control
tran 0.1n 20n
write ../results/tb_simple.raw
.endc

.tran 0.1n 20n
.end