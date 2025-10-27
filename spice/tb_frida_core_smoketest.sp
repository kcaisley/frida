* TSMC65nm frida_core Smoke Test
* Quick ADC test with pre-initialized SPI register (all 1's = all ADCs enabled, ADC 15 selected)
* No reset, immediate ADC operation followed by SPI shift test
* Timing:
*   0-300ns: 3 complete ADC conversion cycles (100ns each)
*   300-500ns: SPI shift-in test (~20 bits at 100MHz = 10ns period)
* Total: 500ns simulation time

* Simulator language
simulator lang=spice

* Include TSMC65nm PDK models for transistors
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' tt_lib

* Include standard cell library (LVT cells only - all cells in core.cdl are LVT)
.include '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lplvt_200a/tcbn65lplvt_200a.spi'

* Include ADC sub-module netlists (in dependency order)
.include '/users/kcaisley/frida/spice/sampswitch.cdl'
.include '/users/kcaisley/frida/spice/comp.cdl'
.include '/users/kcaisley/frida/spice/capdriver.cdl'
.include '/users/kcaisley/frida/spice/caparray.cdl'
.include '/users/kcaisley/frida/spice/adc_digital.cdl'
.include '/users/kcaisley/frida/spice/adc.cdl'
.include '/users/kcaisley/frida/spice/core.cdl'
.include '/users/kcaisley/frida/spice/dnw.sp'

* Supply voltages (1.2V nominal)
vdd_a vdd_a 0 1.2
vss_a vss_a 0 0
vdd_d vdd_d 0 1.2
vss_d vss_d 0 0
vdd_dac vdd_dac 0 1.2
vss_dac vss_dac 0 0

* Reset signal - keep high (inactive) for entire test
vreset_b reset_b 0 1.2

* Differential input signals - ramping voltages
* vin_p ramps from 1.1V to 1.05V over 300ns (during ADC operation)
* vin_n ramps from 0.8V to 0.85V over 300ns
vin_p vin_p 0 pwl(0 1.1 300n 1.05)
vin_n vin_n 0 pwl(0 0.8 300n 0.85)

* SPI signals
* spi_cs_b: high (inactive) for first 300ns, then low for shift operation
vspi_cs_b spi_cs_b 0 pwl(0 1.2 300n 1.2 301n 0)

* SPI clock - 100MHz (10ns period), starts at 305ns, ~20 cycles fit in 200ns
vspi_sclk spi_sclk 0 pulse(0 1.2 305n 0.1n 0.1n 4.8n 10n)

* SPI data input - pattern: 10100110100110010101 (20 bits)
* This pattern will be shifted in from 300ns-500ns
* Each bit lasts 10ns aligned with 100MHz clock
vspi_sdi spi_sdi 0 pwl(0 0 300n 0
+ 305n 1.2 314n 1.2
+ 315n 0 324n 0
+ 325n 1.2 334n 1.2
+ 335n 0 344n 0
+ 345n 0 354n 0
+ 355n 1.2 364n 1.2
+ 365n 1.2 374n 1.2
+ 375n 0 384n 0
+ 385n 1.2 394n 1.2
+ 395n 0 404n 0
+ 405n 0 414n 0
+ 415n 1.2 424n 1.2
+ 425n 1.2 434n 1.2
+ 435n 0 444n 0
+ 445n 0 454n 0
+ 455n 1.2 464n 1.2
+ 465n 0 474n 0
+ 475n 1.2 484n 1.2
+ 485n 0 494n 0
+ 495n 1.2 500n 1.2)

* ADC Conversion Sequences
* 3 conversions in first 300ns (0-100ns, 100-200ns, 200-300ns)
* Each conversion: 100ns period
* Timing per conversion:
*   0-5ns: seq_init high
*   5-15ns: seq_samp high
*   15-100ns: seq_comp and seq_logic alternate (2.5ns high, 2.5ns low)

* seq_init: 5ns pulse at start of each conversion (period 100ns, 3 pulses: 0ns, 100ns, 200ns)
vseq_init seq_init 0 pwl(0 0 1n 1.2 5n 1.2 6n 0
+ 100n 0 101n 1.2 105n 1.2 106n 0
+ 200n 0 201n 1.2 205n 1.2 206n 0
+ 300n 0)

* seq_samp: 10ns pulse starting 5ns into conversion (period 100ns, 3 pulses)
vseq_samp seq_samp 0 pwl(0 0 5n 0 6n 1.2 15n 1.2 16n 0
+ 105n 0 106n 1.2 115n 1.2 116n 0
+ 205n 0 206n 1.2 215n 1.2 216n 0
+ 300n 0)

* seq_comp: 2.5ns high, 2.5ns low alternating (5ns period)
* Runs during ADC operation (0-300ns), stops after that
vseq_comp seq_comp 0 pulse(0 1.2 15n 0.1n 0.1n 2.4n 5n)

* seq_logic: 2.5ns high, 2.5ns low alternating (5ns period, delayed 2.5ns from seq_comp)
* Runs during ADC operation (0-300ns), stops after that
vseq_logic seq_logic 0 pulse(0 1.2 17.5n 0.1n 0.1n 2.4n 5n)


* frida_core instance
* Port order from core.cdl: seq_init seq_samp seq_comp seq_logic spi_sclk spi_sdi spi_sdo spi_cs_b reset_b comp_out vin_p vin_n vdd_a vss_a vdd_d vss_d vdd_dac vss_dac
xcore seq_init seq_samp seq_comp seq_logic
+ spi_sclk spi_sdi spi_sdo spi_cs_b reset_b comp_out
+ vin_p vin_n
+ vdd_a vss_a vdd_d vss_d vdd_dac vss_dac
+ frida_core

* Initialize all 180 SPI register bits to 1.2V (all ADCs enabled, ADC 15 selected)
* These are the Q outputs of the shift register flip-flops
.ic v(xcore.spi_bits[0])=1.2
.ic v(xcore.spi_bits[1])=1.2
.ic v(xcore.spi_bits[2])=1.2
.ic v(xcore.spi_bits[3])=1.2
.ic v(xcore.spi_bits[4])=1.2
.ic v(xcore.spi_bits[5])=1.2
.ic v(xcore.spi_bits[6])=1.2
.ic v(xcore.spi_bits[7])=1.2
.ic v(xcore.spi_bits[8])=1.2
.ic v(xcore.spi_bits[9])=1.2
.ic v(xcore.spi_bits[10])=1.2
.ic v(xcore.spi_bits[11])=1.2
.ic v(xcore.spi_bits[12])=1.2
.ic v(xcore.spi_bits[13])=1.2
.ic v(xcore.spi_bits[14])=1.2
.ic v(xcore.spi_bits[15])=1.2
.ic v(xcore.spi_bits[16])=1.2
.ic v(xcore.spi_bits[17])=1.2
.ic v(xcore.spi_bits[18])=1.2
.ic v(xcore.spi_bits[19])=1.2
.ic v(xcore.spi_bits[20])=1.2
.ic v(xcore.spi_bits[21])=1.2
.ic v(xcore.spi_bits[22])=1.2
.ic v(xcore.spi_bits[23])=1.2
.ic v(xcore.spi_bits[24])=1.2
.ic v(xcore.spi_bits[25])=1.2
.ic v(xcore.spi_bits[26])=1.2
.ic v(xcore.spi_bits[27])=1.2
.ic v(xcore.spi_bits[28])=1.2
.ic v(xcore.spi_bits[29])=1.2
.ic v(xcore.spi_bits[30])=1.2
.ic v(xcore.spi_bits[31])=1.2
.ic v(xcore.spi_bits[32])=1.2
.ic v(xcore.spi_bits[33])=1.2
.ic v(xcore.spi_bits[34])=1.2
.ic v(xcore.spi_bits[35])=1.2
.ic v(xcore.spi_bits[36])=1.2
.ic v(xcore.spi_bits[37])=1.2
.ic v(xcore.spi_bits[38])=1.2
.ic v(xcore.spi_bits[39])=1.2
.ic v(xcore.spi_bits[40])=1.2
.ic v(xcore.spi_bits[41])=1.2
.ic v(xcore.spi_bits[42])=1.2
.ic v(xcore.spi_bits[43])=1.2
.ic v(xcore.spi_bits[44])=1.2
.ic v(xcore.spi_bits[45])=1.2
.ic v(xcore.spi_bits[46])=1.2
.ic v(xcore.spi_bits[47])=1.2
.ic v(xcore.spi_bits[48])=1.2
.ic v(xcore.spi_bits[49])=1.2
.ic v(xcore.spi_bits[50])=1.2
.ic v(xcore.spi_bits[51])=1.2
.ic v(xcore.spi_bits[52])=1.2
.ic v(xcore.spi_bits[53])=1.2
.ic v(xcore.spi_bits[54])=1.2
.ic v(xcore.spi_bits[55])=1.2
.ic v(xcore.spi_bits[56])=1.2
.ic v(xcore.spi_bits[57])=1.2
.ic v(xcore.spi_bits[58])=1.2
.ic v(xcore.spi_bits[59])=1.2
.ic v(xcore.spi_bits[60])=1.2
.ic v(xcore.spi_bits[61])=1.2
.ic v(xcore.spi_bits[62])=1.2
.ic v(xcore.spi_bits[63])=1.2
.ic v(xcore.spi_bits[64])=1.2
.ic v(xcore.spi_bits[65])=1.2
.ic v(xcore.spi_bits[66])=1.2
.ic v(xcore.spi_bits[67])=1.2
.ic v(xcore.spi_bits[68])=1.2
.ic v(xcore.spi_bits[69])=1.2
.ic v(xcore.spi_bits[70])=1.2
.ic v(xcore.spi_bits[71])=1.2
.ic v(xcore.spi_bits[72])=1.2
.ic v(xcore.spi_bits[73])=1.2
.ic v(xcore.spi_bits[74])=1.2
.ic v(xcore.spi_bits[75])=1.2
.ic v(xcore.spi_bits[76])=1.2
.ic v(xcore.spi_bits[77])=1.2
.ic v(xcore.spi_bits[78])=1.2
.ic v(xcore.spi_bits[79])=1.2
.ic v(xcore.spi_bits[80])=1.2
.ic v(xcore.spi_bits[81])=1.2
.ic v(xcore.spi_bits[82])=1.2
.ic v(xcore.spi_bits[83])=1.2
.ic v(xcore.spi_bits[84])=1.2
.ic v(xcore.spi_bits[85])=1.2
.ic v(xcore.spi_bits[86])=1.2
.ic v(xcore.spi_bits[87])=1.2
.ic v(xcore.spi_bits[88])=1.2
.ic v(xcore.spi_bits[89])=1.2
.ic v(xcore.spi_bits[90])=1.2
.ic v(xcore.spi_bits[91])=1.2
.ic v(xcore.spi_bits[92])=1.2
.ic v(xcore.spi_bits[93])=1.2
.ic v(xcore.spi_bits[94])=1.2
.ic v(xcore.spi_bits[95])=1.2
.ic v(xcore.spi_bits[96])=1.2
.ic v(xcore.spi_bits[97])=1.2
.ic v(xcore.spi_bits[98])=1.2
.ic v(xcore.spi_bits[99])=1.2
.ic v(xcore.spi_bits[100])=1.2
.ic v(xcore.spi_bits[101])=1.2
.ic v(xcore.spi_bits[102])=1.2
.ic v(xcore.spi_bits[103])=1.2
.ic v(xcore.spi_bits[104])=1.2
.ic v(xcore.spi_bits[105])=1.2
.ic v(xcore.spi_bits[106])=1.2
.ic v(xcore.spi_bits[107])=1.2
.ic v(xcore.spi_bits[108])=1.2
.ic v(xcore.spi_bits[109])=1.2
.ic v(xcore.spi_bits[110])=1.2
.ic v(xcore.spi_bits[111])=1.2
.ic v(xcore.spi_bits[112])=1.2
.ic v(xcore.spi_bits[113])=1.2
.ic v(xcore.spi_bits[114])=1.2
.ic v(xcore.spi_bits[115])=1.2
.ic v(xcore.spi_bits[116])=1.2
.ic v(xcore.spi_bits[117])=1.2
.ic v(xcore.spi_bits[118])=1.2
.ic v(xcore.spi_bits[119])=1.2
.ic v(xcore.spi_bits[120])=1.2
.ic v(xcore.spi_bits[121])=1.2
.ic v(xcore.spi_bits[122])=1.2
.ic v(xcore.spi_bits[123])=1.2
.ic v(xcore.spi_bits[124])=1.2
.ic v(xcore.spi_bits[125])=1.2
.ic v(xcore.spi_bits[126])=1.2
.ic v(xcore.spi_bits[127])=1.2
.ic v(xcore.spi_bits[128])=1.2
.ic v(xcore.spi_bits[129])=1.2
.ic v(xcore.spi_bits[130])=1.2
.ic v(xcore.spi_bits[131])=1.2
.ic v(xcore.spi_bits[132])=1.2
.ic v(xcore.spi_bits[133])=1.2
.ic v(xcore.spi_bits[134])=1.2
.ic v(xcore.spi_bits[135])=1.2
.ic v(xcore.spi_bits[136])=1.2
.ic v(xcore.spi_bits[137])=1.2
.ic v(xcore.spi_bits[138])=1.2
.ic v(xcore.spi_bits[139])=1.2
.ic v(xcore.spi_bits[140])=1.2
.ic v(xcore.spi_bits[141])=1.2
.ic v(xcore.spi_bits[142])=1.2
.ic v(xcore.spi_bits[143])=1.2
.ic v(xcore.spi_bits[144])=1.2
.ic v(xcore.spi_bits[145])=1.2
.ic v(xcore.spi_bits[146])=1.2
.ic v(xcore.spi_bits[147])=1.2
.ic v(xcore.spi_bits[148])=1.2
.ic v(xcore.spi_bits[149])=1.2
.ic v(xcore.spi_bits[150])=1.2
.ic v(xcore.spi_bits[151])=1.2
.ic v(xcore.spi_bits[152])=1.2
.ic v(xcore.spi_bits[153])=1.2
.ic v(xcore.spi_bits[154])=1.2
.ic v(xcore.spi_bits[155])=1.2
.ic v(xcore.spi_bits[156])=1.2
.ic v(xcore.spi_bits[157])=1.2
.ic v(xcore.spi_bits[158])=1.2
.ic v(xcore.spi_bits[159])=1.2
.ic v(xcore.spi_bits[160])=1.2
.ic v(xcore.spi_bits[161])=1.2
.ic v(xcore.spi_bits[162])=1.2
.ic v(xcore.spi_bits[163])=1.2
.ic v(xcore.spi_bits[164])=1.2
.ic v(xcore.spi_bits[165])=1.2
.ic v(xcore.spi_bits[166])=1.2
.ic v(xcore.spi_bits[167])=1.2
.ic v(xcore.spi_bits[168])=1.2
.ic v(xcore.spi_bits[169])=1.2
.ic v(xcore.spi_bits[170])=1.2
.ic v(xcore.spi_bits[171])=1.2
.ic v(xcore.spi_bits[172])=1.2
.ic v(xcore.spi_bits[173])=1.2
.ic v(xcore.spi_bits[174])=1.2
.ic v(xcore.spi_bits[175])=1.2
.ic v(xcore.spi_bits[176])=1.2
.ic v(xcore.spi_bits[177])=1.2
.ic v(xcore.spi_bits[178])=1.2
.ic v(xcore.spi_bits[179])=1.2

* Save important signals for analysis
.save v(reset_b)
.save v(spi_cs_b) v(spi_sclk) v(spi_sdi) v(spi_sdo)
.save v(seq_init) v(seq_samp) v(seq_comp) v(seq_logic)
.save v(comp_out)
.save v(vin_p) v(vin_n)
* Save some SPI register bits to verify initialization
.save v(xcore.spi_bits[0]) v(xcore.spi_bits[1]) v(xcore.spi_bits[2]) v(xcore.spi_bits[3])
.save v(xcore.spi_bits[176]) v(xcore.spi_bits[177]) v(xcore.spi_bits[178]) v(xcore.spi_bits[179])

* Transient analysis - 500ns smoke test
.tran 0.1n 500n

.end
