* TSMC65nm ADC Testbench
* Full system simulation with timing sequences

* Include TSMC65nm PDK models
.lib '../../asiclab/tech/tsmc65/spice/models/toplevel.l' tt_lib

* Include SPICE master files for standard cells
.include '/home/kcaisley/asiclab/tech/tsmc65/spice/tcbn65lplvt_200a.spi'

* Include custom macro definitions
.include 'sampswitch.cdl'
.include 'comp.cdl'
.include 'caparray.cdl'

* Include ADC netlist
.include 'adc.cdl'

* Supply voltages
vdd_a vdd_a 0 1.2
vss_a vss_a 0 0
vdd_d vdd_d 0 1.2
vss_d vss_d 0 0
vdd_dac vdd_dac 0 1.2
vss_dac vss_dac 0 0

* Clock generation - 5ns period (200MHz)
vclk clk 0 pulse(0 1.2 0 50p 50p 2.45n 5n)

* Differential input signals
* Test case 1: +100mV differential
vin_p vin_p 0 dc 0.65
vin_n vin_n 0 dc 0.55

* DAC state initialization (all high for monotonic switching)
vdac_astate_p0 dac_astate_p[0] 0 1.2
vdac_astate_p1 dac_astate_p[1] 0 1.2
vdac_astate_p2 dac_astate_p[2] 0 1.2
vdac_astate_p3 dac_astate_p[3] 0 1.2
vdac_astate_p4 dac_astate_p[4] 0 1.2
vdac_astate_p5 dac_astate_p[5] 0 1.2
vdac_astate_p6 dac_astate_p[6] 0 1.2
vdac_astate_p7 dac_astate_p[7] 0 1.2
vdac_astate_p8 dac_astate_p[8] 0 1.2
vdac_astate_p9 dac_astate_p[9] 0 1.2
vdac_astate_p10 dac_astate_p[10] 0 1.2
vdac_astate_p11 dac_astate_p[11] 0 1.2
vdac_astate_p12 dac_astate_p[12] 0 1.2
vdac_astate_p13 dac_astate_p[13] 0 1.2
vdac_astate_p14 dac_astate_p[14] 0 1.2
vdac_astate_p15 dac_astate_p[15] 0 1.2

vdac_astate_n0 dac_astate_n[0] 0 1.2
vdac_astate_n1 dac_astate_n[1] 0 1.2
vdac_astate_n2 dac_astate_n[2] 0 1.2
vdac_astate_n3 dac_astate_n[3] 0 1.2
vdac_astate_n4 dac_astate_n[4] 0 1.2
vdac_astate_n5 dac_astate_n[5] 0 1.2
vdac_astate_n6 dac_astate_n[6] 0 1.2
vdac_astate_n7 dac_astate_n[7] 0 1.2
vdac_astate_n8 dac_astate_n[8] 0 1.2
vdac_astate_n9 dac_astate_n[9] 0 1.2
vdac_astate_n10 dac_astate_n[10] 0 1.2
vdac_astate_n11 dac_astate_n[11] 0 1.2
vdac_astate_n12 dac_astate_n[12] 0 1.2
vdac_astate_n13 dac_astate_n[13] 0 1.2
vdac_astate_n14 dac_astate_n[14] 0 1.2
vdac_astate_n15 dac_astate_n[15] 0 1.2

vdac_bstate_p0 dac_bstate_p[0] 0 1.2
vdac_bstate_p1 dac_bstate_p[1] 0 1.2
vdac_bstate_p2 dac_bstate_p[2] 0 1.2
vdac_bstate_p3 dac_bstate_p[3] 0 1.2
vdac_bstate_p4 dac_bstate_p[4] 0 1.2
vdac_bstate_p5 dac_bstate_p[5] 0 1.2
vdac_bstate_p6 dac_bstate_p[6] 0 1.2
vdac_bstate_p7 dac_bstate_p[7] 0 1.2
vdac_bstate_p8 dac_bstate_p[8] 0 1.2
vdac_bstate_p9 dac_bstate_p[9] 0 1.2
vdac_bstate_p10 dac_bstate_p[10] 0 1.2
vdac_bstate_p11 dac_bstate_p[11] 0 1.2
vdac_bstate_p12 dac_bstate_p[12] 0 1.2
vdac_bstate_p13 dac_bstate_p[13] 0 1.2
vdac_bstate_p14 dac_bstate_p[14] 0 1.2
vdac_bstate_p15 dac_bstate_p[15] 0 1.2

vdac_bstate_n0 dac_bstate_n[0] 0 1.2
vdac_bstate_n1 dac_bstate_n[1] 0 1.2
vdac_bstate_n2 dac_bstate_n[2] 0 1.2
vdac_bstate_n3 dac_bstate_n[3] 0 1.2
vdac_bstate_n4 dac_bstate_n[4] 0 1.2
vdac_bstate_n5 dac_bstate_n[5] 0 1.2
vdac_bstate_n6 dac_bstate_n[6] 0 1.2
vdac_bstate_n7 dac_bstate_n[7] 0 1.2
vdac_bstate_n8 dac_bstate_n[8] 0 1.2
vdac_bstate_n9 dac_bstate_n[9] 0 1.2
vdac_bstate_n10 dac_bstate_n[10] 0 1.2
vdac_bstate_n11 dac_bstate_n[11] 0 1.2
vdac_bstate_n12 dac_bstate_n[12] 0 1.2
vdac_bstate_n13 dac_bstate_n[13] 0 1.2
vdac_bstate_n14 dac_bstate_n[14] 0 1.2
vdac_bstate_n15 dac_bstate_n[15] 0 1.2

* DAC mode and diffcaps
vdac_mode dac_mode 0 0
vdac_diffcaps dac_diffcaps 0 0

* ADC Timing sequence generation (5 complete cycles)
* Clock cycle 0: seq_init (reset)
vseq_init seq_init 0 pulse(0 1.2 0.5n 0.1n 0.1n 2.3n 25n)

* Clock cycle 1: seq_samp (sample)  
vseq_samp seq_samp 0 pulse(0 1.2 5.5n 0.1n 0.1n 2.3n 25n)

* Clock cycles 2-18: seq_comp (17 pulses starting at 10.5n with 2.5n period)
vseq_comp seq_comp 0 pulse(0 1.2 10.5n 0.1n 0.1n 2.3n 2.5n)

* Clock cycles 2-17: seq_update (16 pulses starting at 12.5n with 2.5n period)
vseq_update seq_update 0 pulse(0 1.2 12.5n 0.1n 0.1n 2.3n 2.5n)

* Enable signals derived from sequence signals
ven_init en_init 0 pulse(0 1.2 0.5n 0.1n 0.1n 2.3n 25n)
ven_samp_p en_samp_p 0 pulse(0 1.2 5.5n 0.1n 0.1n 2.3n 25n)
ven_samp_n en_samp_n 0 pulse(0 1.2 5.5n 0.1n 0.1n 2.3n 25n)
ven_comp en_comp 0 pulse(0 1.2 10.5n 0.1n 0.1n 2.3n 2.5n)
ven_update en_update 0 pulse(0 1.2 12.5n 0.1n 0.1n 2.3n 2.5n)

* ADC instance
xadc comp_out 
+ dac_astate_n[0] dac_astate_n[1] dac_astate_n[2] dac_astate_n[3]
+ dac_astate_n[4] dac_astate_n[5] dac_astate_n[6] dac_astate_n[7]
+ dac_astate_n[8] dac_astate_n[9] dac_astate_n[10] dac_astate_n[11]
+ dac_astate_n[12] dac_astate_n[13] dac_astate_n[14] dac_astate_n[15]
+ dac_astate_p[0] dac_astate_p[1] dac_astate_p[2] dac_astate_p[3]
+ dac_astate_p[4] dac_astate_p[5] dac_astate_p[6] dac_astate_p[7]
+ dac_astate_p[8] dac_astate_p[9] dac_astate_p[10] dac_astate_p[11]
+ dac_astate_p[12] dac_astate_p[13] dac_astate_p[14] dac_astate_p[15]
+ dac_bstate_n[0] dac_bstate_n[1] dac_bstate_n[2] dac_bstate_n[3]
+ dac_bstate_n[4] dac_bstate_n[5] dac_bstate_n[6] dac_bstate_n[7]
+ dac_bstate_n[8] dac_bstate_n[9] dac_bstate_n[10] dac_bstate_n[11]
+ dac_bstate_n[12] dac_bstate_n[13] dac_bstate_n[14] dac_bstate_n[15]
+ dac_bstate_p[0] dac_bstate_p[1] dac_bstate_p[2] dac_bstate_p[3]
+ dac_bstate_p[4] dac_bstate_p[5] dac_bstate_p[6] dac_bstate_p[7]
+ dac_bstate_p[8] dac_bstate_p[9] dac_bstate_p[10] dac_bstate_p[11]
+ dac_bstate_p[12] dac_bstate_p[13] dac_bstate_p[14] dac_bstate_p[15]
+ dac_diffcaps dac_mode en_comp en_init en_samp_n en_samp_p en_update
+ seq_comp seq_init seq_samp seq_update
+ vdd_a vdd_d vdd_dac vin_n vin_p vss_a vss_d vss_dac
+ adc

* Save all important signals for analysis
.save v(vin_p) v(vin_n) v(comp_out) v(seq_init) v(seq_samp) v(seq_comp) v(seq_update)
.save v(en_init) v(en_samp_p) v(en_samp_n) v(en_comp) v(en_update)
.save v(dac_astate_p[0]) v(dac_astate_p[15]) v(dac_astate_n[0]) v(dac_astate_n[15])

* Simulation control
.control
tran 10p 125n
write ../results/tb_adc_full.raw
.endc

* Legacy tran statement (required by some SPICE variants)
.tran 10p 125n

.end