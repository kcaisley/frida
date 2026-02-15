* TSMC65nm frida_top Testbench
* Top-level chip testbench with pad ring and LVDS I/O
* Timing sequence:
*   0-50ns: Reset active
*   50ns-550ns: LVDS smoke test (5 cycles of all clocks)
*   600ns-18.6us: SPI configuration (180 bits at 10MHz)
*   19us-19.5us: 5 ADC conversions at 10 Msps (100ns each)
* Total: ~20us simulation time

* Simulator language
simulator lang=spice

* Include TSMC65nm PDK models for transistors, diodes, and resistors
* The tt_lib section includes all necessary device models
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' tt_lib

* Define missing device models as simple wrappers to standard PDK models
* This allows the netlist to use custom device names while mapping to standard models

* rm2 resistor (used in padring) - maps to rm2l (length-parameterized metal2 resistor)
.subckt rm2 n1 n2 l=1u w=1u m=1
xrm2 n1 n2 rm2l l=l w=w m=m
.ends

* nch_dnw transistor (used in DNW decap cells) - maps to standard nch
* Deep N-well devices behave electrically like standard nch with isolated substrate
.subckt nch_dnw d g s b l=120n w=1u m=1
mn d g s b nch l=l w=w m=m
.ends

* nch_lvt_dnw transistor (used in DNW standard cells) - maps to standard nch_lvt
.subckt nch_lvt_dnw d g s b l=120n w=1u m=1
mn d g s b nch_lvt l=l w=w m=m
.ends

* Include top-level chip netlist (includes all padrings, standard cells, decaps, etc.)
.include '/users/kcaisley/frida/spice/frida_top.cdl'

* Supply voltages
* Core supplies (1.2V nominal)
vdd_a vdd_a 0 1.2
vss_a vss_a 0 0
vdd_d vdd_d 0 1.2
vss_d vss_d 0 0
vdd_dac vdd_dac 0 1.2
vss_dac vss_dac 0 0

* I/O supply (1.2V nominal, same as core)
vdd_io vdd_io 0 1.2
vss_io vss_io 0 0

* Reset signal - active low, released after 50ns (single-ended pad input)
vreset_b rst_b_pad 0 pwl(0 0 50n 0 51n 1.2)

* Differential analog input signals - ramping voltages across all conversions
* vin_p ramps from 1.1V to 1.05V over 19.5us (SPI + 5 conversions)
* vin_n ramps from 0.8V to 0.85V over 19.5us
* These go to analog input pads
vin_p vin_p_pad 0 pwl(0 1.1 19.5u 1.05)
vin_n vin_n_pad 0 pwl(0 0.8 19.5u 0.85)

* SPI Configuration Sequence (single-ended signals)
* 180 bits clocked at 10MHz (100ns period)
* spi_cs_b: active low during entire SPI transaction (600ns-18.6us)
* spi_sclk: 100ns period clock (50ns high, 50ns low)
* spi_sdi: data input - for simplicity, all 1's

* SPI chip select - active low from 600ns to 18.6us
vspi_cs_b spi_cs_b_pad 0 pwl(0 1.2 600n 1.2 601n 0 18.6u 0 18.61u 1.2)

* SPI clock - 180 cycles of 100ns period starting at 650ns
* Using pulse source: pulse(v1 v2 td tr tf pw per)
vspi_sclk spi_sclk_pad 0 pulse(0 1.2 650n 0.1n 0.1n 49.8n 100n)

* SPI data input - all 1's (tied high during SPI transaction)
vspi_sdi spi_sdi_pad 0 pwl(0 1.2 600n 1.2)

* LVDS Clock Inputs (4 differential clock pairs)
* Each LVDS pair has common-mode voltage of 0.9V with differential swing of ±0.3V
* V+ = Vcm + Vdiff = 0.9V + 0.3V = 1.2V (high) or 0.9V - 0.3V = 0.6V (low)
* V- = Vcm - Vdiff = 0.9V - 0.3V = 0.6V (high) or 0.9V + 0.3V = 1.2V (low)
* Signals swing from 0.6V to 1.2V
*
* Smoke test: 5 cycles starting at 50ns (after reset)
* Then actual ADC operation: 5 conversions starting at 19us

* clk_init: 5ns pulse at start of each conversion
* Smoke test: 5 cycles at 100ns period starting at 50ns (50ns-550ns)
* ADC operation: 5 pulses at 100ns period starting at 19us
vclk_init_p clk_init_p_pad 0 pwl(0 0.6 50n 0.6 51n 1.2 55n 1.2 56n 0.6
+ 150n 0.6 151n 1.2 155n 1.2 156n 0.6
+ 250n 0.6 251n 1.2 255n 1.2 256n 0.6
+ 350n 0.6 351n 1.2 355n 1.2 356n 0.6
+ 450n 0.6 451n 1.2 455n 1.2 456n 0.6
+ 550n 0.6 19u 0.6 19.001u 1.2 19.005u 1.2 19.006u 0.6
+ 19.1u 0.6 19.101u 1.2 19.105u 1.2 19.106u 0.6
+ 19.2u 0.6 19.201u 1.2 19.205u 1.2 19.206u 0.6
+ 19.3u 0.6 19.301u 1.2 19.305u 1.2 19.306u 0.6
+ 19.4u 0.6 19.401u 1.2 19.405u 1.2 19.406u 0.6)
vclk_init_n clk_init_n_pad 0 pwl(0 1.2 50n 1.2 51n 0.6 55n 0.6 56n 1.2
+ 150n 1.2 151n 0.6 155n 0.6 156n 1.2
+ 250n 1.2 251n 0.6 255n 0.6 256n 1.2
+ 350n 1.2 351n 0.6 355n 0.6 356n 1.2
+ 450n 1.2 451n 0.6 455n 0.6 456n 1.2
+ 550n 1.2 19u 1.2 19.001u 0.6 19.005u 0.6 19.006u 1.2
+ 19.1u 1.2 19.101u 0.6 19.105u 0.6 19.106u 1.2
+ 19.2u 1.2 19.201u 0.6 19.205u 0.6 19.206u 1.2
+ 19.3u 1.2 19.301u 0.6 19.305u 0.6 19.306u 1.2
+ 19.4u 1.2 19.401u 0.6 19.405u 0.6 19.406u 1.2)

* clk_samp: 10ns pulse starting 5ns into conversion
* Smoke test: 5 cycles with 10ns pulse, starting at 55ns
* ADC operation: 5 pulses at 100ns period starting at 19.005us
vclk_samp_p clk_samp_p_pad 0 pwl(0 0.6 55n 0.6 56n 1.2 65n 1.2 66n 0.6
+ 155n 0.6 156n 1.2 165n 1.2 166n 0.6
+ 255n 0.6 256n 1.2 265n 1.2 266n 0.6
+ 355n 0.6 356n 1.2 365n 1.2 366n 0.6
+ 455n 0.6 456n 1.2 465n 1.2 466n 0.6
+ 550n 0.6 19.005u 0.6 19.006u 1.2 19.015u 1.2 19.016u 0.6
+ 19.105u 0.6 19.106u 1.2 19.115u 1.2 19.116u 0.6
+ 19.205u 0.6 19.206u 1.2 19.215u 1.2 19.216u 0.6
+ 19.305u 0.6 19.306u 1.2 19.315u 1.2 19.316u 0.6
+ 19.405u 0.6 19.406u 1.2 19.415u 1.2 19.416u 0.6)
vclk_samp_n clk_samp_n_pad 0 pwl(0 1.2 55n 1.2 56n 0.6 65n 0.6 66n 1.2
+ 155n 1.2 156n 0.6 165n 0.6 166n 1.2
+ 255n 1.2 256n 0.6 265n 0.6 266n 1.2
+ 355n 1.2 356n 0.6 365n 0.6 366n 1.2
+ 455n 1.2 456n 0.6 465n 0.6 466n 1.2
+ 550n 1.2 19.005u 1.2 19.006u 0.6 19.015u 0.6 19.016u 1.2
+ 19.105u 1.2 19.106u 0.6 19.115u 0.6 19.116u 1.2
+ 19.205u 1.2 19.206u 0.6 19.215u 0.6 19.216u 1.2
+ 19.305u 1.2 19.306u 0.6 19.315u 0.6 19.316u 1.2
+ 19.405u 1.2 19.406u 0.6 19.415u 0.6 19.416u 1.2)

* clk_comp: 2.5ns high, 2.5ns low alternating (5ns period)
* Smoke test: Multiple toggles for 100ns starting at 65ns
* ADC operation: starts at 19.015us
vclk_comp_p clk_comp_p_pad 0 pulse(0.6 1.2 65n 0.1n 0.1n 2.4n 5n)
vclk_comp_n clk_comp_n_pad 0 pulse(1.2 0.6 65n 0.1n 0.1n 2.4n 5n)

* clk_logic: 2.5ns high, 2.5ns low alternating (5ns period, delayed 2.5ns from seq_comp)
* Smoke test: Multiple toggles for 100ns starting at 67.5ns
* ADC operation: starts at 19.0175us
vclk_logic_p clk_logic_p_pad 0 pulse(0.6 1.2 67.5n 0.1n 0.1n 2.4n 5n)
vclk_logic_n clk_logic_n_pad 0 pulse(1.2 0.6 67.5n 0.1n 0.1n 2.4n 5n)

* frida_top instance
* Port order from frida_top.cdl:
* clk_comp_n_pad clk_comp_p_pad clk_init_n_pad clk_init_p_pad
* clk_logic_n_pad clk_logic_p_pad clk_samp_n_pad clk_samp_p_pad comp_out_n_pad
* comp_out_p_pad rst_b_pad spi_cs_b_pad spi_sclk_pad spi_sdi_pad spi_sdo_pad
* vdd_a vdd_d vdd_dac vdd_io vin_n_pad vin_p_pad vss_a vss_d vss_dac vss_io
xtop clk_comp_n_pad clk_comp_p_pad clk_init_n_pad clk_init_p_pad
+ clk_logic_n_pad clk_logic_p_pad clk_samp_n_pad clk_samp_p_pad
+ comp_out_n_pad comp_out_p_pad
+ rst_b_pad spi_cs_b_pad spi_sclk_pad spi_sdi_pad spi_sdo_pad
+ vdd_a vdd_d vdd_dac vdd_io
+ vin_n_pad vin_p_pad
+ vss_a vss_d vss_dac vss_io
+ frida_top

* Save important signals for analysis
.save v(rst_b_pad)
.save v(spi_cs_b_pad) v(spi_sclk_pad) v(spi_sdi_pad) v(spi_sdo_pad)
.save v(clk_init_p_pad) v(clk_init_n_pad)
.save v(clk_samp_p_pad) v(clk_samp_n_pad)
.save v(clk_comp_p_pad) v(clk_comp_n_pad)
.save v(clk_logic_p_pad) v(clk_logic_n_pad)
.save v(comp_out_p_pad) v(comp_out_n_pad)
.save v(vin_p_pad) v(vin_n_pad)
.save v(vdd_a) v(vdd_d) v(vdd_dac) v(vdd_io)
.save v(vss_a) v(vss_d) v(vss_dac) v(vss_io)

* Transient analysis - 20us to cover full SPI + ADC sequence
.tran 0.1n 20u

.end
