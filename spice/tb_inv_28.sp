* TSMC28nm Inverter Test
* Test inverter using nch_lvt and pch_lvt devices

* Include TSMC28nm PDK models (NOTE: TSMC28 PDK not available in this setup)
.lib '/home/kcaisley/asiclab/tech/tsmc28/spice/models/toplevel.l' TOP_TT

* Supply voltage
vdd vdd 0 1.2

* Input signal - pulse from 0 to 1.2V
vin in 0 pulse(0 1.2 0.1n 0.1n 0.1n 0.9n 2n)

* Inverter circuit
* NMOS transistor
mn out in 0 0 nch_lvt w=240n l=60n m=1

* PMOS transistor  
mp out in vdd vdd pch_lvt w=480n l=60n m=1

* Load capacitor
cl out 0 10f

* Save signals for output
.save v(in) v(out)

* Analysis
.tran 10p 2n

* Output
.control
run
write ../results/tb_inv_28.raw
.endc

.end
