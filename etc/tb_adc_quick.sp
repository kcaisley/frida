* TSMC65nm ADC Quick Test - Short simulation

* Include TSMC65nm PDK models
.lib '/home/kcaisley/asiclab/tech/tsmc65/spice/models/toplevel.l' tt_lib

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

* Simple test inputs
vin_p vin_p 0 dc 0.65
vin_n vin_n 0 dc 0.55

* All other signals tied to appropriate levels
vseq_init seq_init 0 0
vseq_samp seq_samp 0 0
vseq_comp seq_comp 0 0
vseq_update seq_update 0 0
ven_init en_init 0 0
ven_samp_p en_samp_p 0 0
ven_samp_n en_samp_n 0 0
ven_comp en_comp 0 0
ven_update en_update 0 0

* DAC states all high (monotonic switching)
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

vdac_mode dac_mode 0 0
vdac_diffcaps dac_diffcaps 0 0

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

* Save just key signals
.save v(vin_p) v(vin_n) v(comp_out)

* Very short simulation - just DC operating point + tiny transient
.control
op
tran 0.1n 1n
write ../src/results/tb_adc_quick.raw
.endc

.op
.tran 0.1n 1n

.end