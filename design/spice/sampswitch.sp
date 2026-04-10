* Sampling switch — CMOS transmission gate
* Derived from frida_complete.cdl, nch_lvt_dnw replaced with nch_lvt
* (deep-nwell only affects substrate isolation, not electrical behavior)

.SUBCKT sampswitch vin vout clk clk_b vdd_a vss_a

Mp1 vout clk_b vin vdd_a pch_lvt l=60n w=5u m=1
Mn1 vout clk vin vss_a nch_lvt l=60n w=4u m=1

.ENDS sampswitch
