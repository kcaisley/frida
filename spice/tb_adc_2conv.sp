* TSMC65nm ADC Testbench - 2 Conversions
* Simulates 2 complete ADC conversions at 10 Msps (100ns per conversion)
* 10ns settling + 2x 100ns conversions = 210ns total

* Simulator language
simulator lang=spice

* Include TSMC65nm PDK models
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' tt_lib

* Include SPICE master files for standard cells
.include '/users/kcaisley/asiclab/tech/tsmc65/spice/tcbn65lplvt_200a.spi'
.include '/users/kcaisley/asiclab/tech/tsmc65/spice/comp_stdcells.cdl'

* Include ADC sub-module netlists (in dependency order)
.include 'caparray.cdl'
.include 'capdriver.cdl'
.include 'sampswitch.cdl'
.include 'comp.cdl'
.include 'adc_digital.cdl'

* Include ADC top-level netlist
.include 'adc.cdl'

* Supply voltages
vdd_a vdd_a 0 1.2
vss_a vss_a 0 0
vdd_d vdd_d 0 1.2
vss_d vss_d 0 0
vdd_dac vdd_dac 0 1.2
vss_dac vss_dac 0 0

* Differential input signals - ramping voltages
* vin_p ramps from 1.1V to 1.05V over 200ns
* vin_n ramps from 0.8V to 0.85V over 200ns
vin_p vin_p 0 pwl(0 1.1 210n 1.05)
vin_n vin_n 0 pwl(0 0.8 210n 0.85)

* Timing sequence for 2 conversions (10 Msps = 100ns period)
* 0-10ns: settling time
* Each conversion (100ns):
*   0-5ns: seq_init high
*   5-15ns: seq_samp high
*   15-100ns: seq_comp and seq_update alternate (2.5ns high, 2.5ns low)
*     seq_comp: 17 pulses starting at 15ns
*     seq_update: 16 pulses starting at 17.5ns (2.5ns after seq_comp)

* seq_init: 5ns pulse at start of each conversion (period 100ns)
vseq_init seq_init 0 pulse(0 1.2 10n 0.1n 0.1n 4.8n 100n)

* seq_samp: 10ns pulse starting 5ns into conversion (period 100ns)
vseq_samp seq_samp 0 pulse(0 1.2 15n 0.1n 0.1n 9.8n 100n)

* seq_comp: 2.5ns high, 2.5ns low alternating (5ns period, starts at 25ns)
vseq_comp seq_comp 0 pulse(0 1.2 25n 0.1n 0.1n 2.4n 5n)

* seq_update: 2.5ns high, 2.5ns low alternating (5ns period, starts at 27.5ns)
vseq_update seq_update 0 pulse(0 1.2 27.5n 0.1n 0.1n 2.4n 5n)

* Enable signals - tied high for normal operation
ven_init en_init 0 1.2
ven_samp_p en_samp_p 0 1.2
ven_samp_n en_samp_n 0 1.2
ven_comp en_comp 0 1.2
ven_update en_update 0 1.2

* DAC mode control signals - tied to appropriate levels
vdac_mode dac_mode 0 1.2
vdac_diffcaps dac_diffcaps 0 1.2

* DAC state initialization - all tied high (1.2V) for normal operation
* dac_astate_p[15:0]
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

* dac_astate_n[15:0]
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

* dac_bstate_p[15:0]
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

* dac_bstate_n[15:0]
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

* ADC instance
xadc seq_init seq_samp seq_comp seq_update comp_out en_init en_samp_p en_samp_n en_comp en_update dac_mode dac_diffcaps
+ dac_astate_p[15] dac_astate_p[14] dac_astate_p[13] dac_astate_p[12]
+ dac_astate_p[11] dac_astate_p[10] dac_astate_p[9] dac_astate_p[8]
+ dac_astate_p[7] dac_astate_p[6] dac_astate_p[5] dac_astate_p[4]
+ dac_astate_p[3] dac_astate_p[2] dac_astate_p[1] dac_astate_p[0]
+ dac_bstate_p[15] dac_bstate_p[14] dac_bstate_p[13] dac_bstate_p[12]
+ dac_bstate_p[11] dac_bstate_p[10] dac_bstate_p[9] dac_bstate_p[8]
+ dac_bstate_p[7] dac_bstate_p[6] dac_bstate_p[5] dac_bstate_p[4]
+ dac_bstate_p[3] dac_bstate_p[2] dac_bstate_p[1] dac_bstate_p[0]
+ dac_astate_n[15] dac_astate_n[14] dac_astate_n[13] dac_astate_n[12]
+ dac_astate_n[11] dac_astate_n[10] dac_astate_n[9] dac_astate_n[8]
+ dac_astate_n[7] dac_astate_n[6] dac_astate_n[5] dac_astate_n[4]
+ dac_astate_n[3] dac_astate_n[2] dac_astate_n[1] dac_astate_n[0]
+ dac_bstate_n[15] dac_bstate_n[14] dac_bstate_n[13] dac_bstate_n[12]
+ dac_bstate_n[11] dac_bstate_n[10] dac_bstate_n[9] dac_bstate_n[8]
+ dac_bstate_n[7] dac_bstate_n[6] dac_bstate_n[5] dac_bstate_n[4]
+ dac_bstate_n[3] dac_bstate_n[2] dac_bstate_n[1] dac_bstate_n[0]
+ vin_p vin_n
+ vdd_a vss_a vdd_d vss_d vdd_dac vss_dac
+ adc

* Save important signals for analysis
.save v(vin_p) v(vin_n) v(comp_out)
.save v(seq_init) v(seq_samp) v(seq_comp) v(seq_update)
.save v(en_init) v(en_samp_p) v(en_samp_n) v(en_comp) v(en_update)

* Transient analysis - 15ns for quick debugging
.tran 0.1n 210n

.end
