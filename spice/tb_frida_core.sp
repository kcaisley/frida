* TSMC65nm frida_core Testbench
* SPI configuration sequence followed by 5 ADC conversions
* SPI: 180 bits clocked at 10MHz (100ns period) = 18us
* ADC: 5 conversions at 10 Msps (100ns period each) = 500ns
* Total: ~18.5us simulation time

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
.include 'adc.cdl'
.include 'core.cdl'

* Supply voltages (1.2V nominal)
vdd_a vdd_a 0 1.2
vss_a vss_a 0 0
vdd_d vdd_d 0 1.2
vss_d vss_d 0 0
vdd_dac vdd_dac 0 1.2
vss_dac vss_dac 0 0

* Reset signal - active low, released after 50ns
vreset_b reset_b 0 pwl(0 0 50n 0 51n 1.2)

* Differential input signals - ramping voltages across all conversions
* vin_p ramps from 1.1V to 1.05V over 19.5us (SPI + 5 conversions)
* vin_n ramps from 0.8V to 0.85V over 19.5us
vin_p vin_p 0 pwl(0 1.1 19.5u 1.05)
vin_n vin_n 0 pwl(0 0.8 19.5u 0.85)

* SPI Configuration Sequence
* 180 bits clocked at 10MHz (100ns period)
* spi_cs_b: active low during entire SPI transaction (0-18us)
* spi_sclk: 100ns period clock (50ns high, 50ns low)
* spi_sdi: data input - for simplicity, all 1's

* SPI chip select - active low from 100ns to 18.1us
vspi_cs_b spi_cs_b 0 pwl(0 1.2 100n 1.2 101n 0 18.1u 0 18.11u 1.2)

* SPI clock - 180 cycles of 100ns period starting at 150ns
* Using pulse source: pulse(v1 v2 td tr tf pw per)
vspi_sclk spi_sclk 0 pulse(0 1.2 150n 0.1n 0.1n 49.8n 100n)

* SPI data input - all 1's (tied high during SPI transaction)
vspi_sdi spi_sdi 0 pwl(0 1.2 100n 1.2)

* ADC Conversion Sequences
* 5 conversions starting at 19us (after SPI completes)
* Each conversion: 100ns period
* Timing per conversion:
*   0-5ns: seq_init high
*   5-15ns: seq_samp high
*   15-100ns: seq_comp and seq_logic alternate (2.5ns high, 2.5ns low)

* seq_init: 5ns pulse at start of each conversion (period 100ns, 5 pulses starting at 19us)
vseq_init seq_init 0 pulse(0 1.2 19u 0.1n 0.1n 4.8n 100n)

* seq_samp: 10ns pulse starting 5ns into conversion (period 100ns, 5 pulses)
vseq_samp seq_samp 0 pulse(0 1.2 19.005u 0.1n 0.1n 9.8n 100n)

* seq_comp: 2.5ns high, 2.5ns low alternating (5ns period, starts at 19.015us)
vseq_comp seq_comp 0 pulse(0 1.2 19.015u 0.1n 0.1n 2.4n 5n)

* seq_logic: 2.5ns high, 2.5ns low alternating (5ns period, starts at 19.0175us, delayed 2.5ns from seq_comp)
vseq_logic seq_logic 0 pulse(0 1.2 19.0175u 0.1n 0.1n 2.4n 5n)

* Comparator output from ADC - treat as input for now (pull down)
* In real operation, this would be driven by the ADC
vcomp_out comp_out 0 0

* frida_core instance
* Port order from core.cdl: comp_out reset_b seq_comp seq_init seq_logic seq_samp spi_cs_b spi_sclk spi_sdi spi_sdo vin_p vin_n vdd_a vss_a vdd_d vss_d vdd_dac vss_dac
xcore comp_out reset_b seq_comp seq_init seq_logic seq_samp
+ spi_cs_b spi_sclk spi_sdi spi_sdo
+ vin_p vin_n
+ vdd_a vss_a vdd_d vss_d vdd_dac vss_dac
+ frida_core

* Save important signals for analysis
.save v(reset_b)
.save v(spi_cs_b) v(spi_sclk) v(spi_sdi) v(spi_sdo)
.save v(seq_init) v(seq_samp) v(seq_comp) v(seq_logic)
.save v(comp_out)
.save v(vin_p) v(vin_n)

* Transient analysis - start with 10ns for quick netlist check
.tran 0.1n 20u

.end
