* SPICE wrapper for co-simulation (spicebind)
*
* This file is loaded by spicebind via SPICE_NETLIST. It declares external
* sources for signals driven from Verilog, includes all subcircuit
* definitions, and instantiates both analog blocks:
*
*   1. sediff  — PCB front-end (THS4541 SE-to-diff amplifier)
*   2. adc     — FRIDA ADC (comparator, sampling switches, cap arrays, digital)
*
* HDL_INSTANCE should be set to:
*   tb_integration.i_sediff,tb_integration.i_chip.adc_inst
*
* Port names must match the Verilog stub module ports exactly.

* =====================================================================
* Subcircuit includes
* =====================================================================
.include 'sediff.sp'
.include 'comp.cdl'
.include 'caparray.cdl'
.include 'capdriver.cdl'
.include 'adc_digital.cdl'
.include 'adc.cdl'

* =====================================================================
* sediff: external sources for Verilog-driven inputs
* =====================================================================

* Single-ended input from AWG (driven by cocotb via real variable)
Vvin_p_ext tb_integration.i_sediff.vin_p_ext 0 0 external

* VDD supply for VOCM divider (driven by cocotb via real variable)
Vvdd_sediff tb_integration.i_sediff.vdd 0 0 external

* =====================================================================
* adc: external sources for Verilog-driven inputs
* =====================================================================

* Sequencing clocks (digital, from daq_core via frida_core_1chan)
Vseq_init  tb_integration.i_chip.adc_inst.seq_init  0 0 external
Vseq_samp  tb_integration.i_chip.adc_inst.seq_samp  0 0 external
Vseq_comp  tb_integration.i_chip.adc_inst.seq_comp  0 0 external
Vseq_update tb_integration.i_chip.adc_inst.seq_update 0 0 external

* Per-ADC enable signals (from SPI register via frida_core_1chan)
Ven_init   tb_integration.i_chip.adc_inst.en_init   0 0 external
Ven_samp_p tb_integration.i_chip.adc_inst.en_samp_p 0 0 external
Ven_samp_n tb_integration.i_chip.adc_inst.en_samp_n 0 0 external
Ven_comp   tb_integration.i_chip.adc_inst.en_comp   0 0 external
Ven_update tb_integration.i_chip.adc_inst.en_update  0 0 external
Vdac_mode  tb_integration.i_chip.adc_inst.dac_mode  0 0 external
Vdac_diffcaps tb_integration.i_chip.adc_inst.dac_diffcaps 0 0 external

* DAC state buses (16 bits each, from SPI register)
Vdac_astate_p0  tb_integration.i_chip.adc_inst.dac_astate_p[0]  0 0 external
Vdac_astate_p1  tb_integration.i_chip.adc_inst.dac_astate_p[1]  0 0 external
Vdac_astate_p2  tb_integration.i_chip.adc_inst.dac_astate_p[2]  0 0 external
Vdac_astate_p3  tb_integration.i_chip.adc_inst.dac_astate_p[3]  0 0 external
Vdac_astate_p4  tb_integration.i_chip.adc_inst.dac_astate_p[4]  0 0 external
Vdac_astate_p5  tb_integration.i_chip.adc_inst.dac_astate_p[5]  0 0 external
Vdac_astate_p6  tb_integration.i_chip.adc_inst.dac_astate_p[6]  0 0 external
Vdac_astate_p7  tb_integration.i_chip.adc_inst.dac_astate_p[7]  0 0 external
Vdac_astate_p8  tb_integration.i_chip.adc_inst.dac_astate_p[8]  0 0 external
Vdac_astate_p9  tb_integration.i_chip.adc_inst.dac_astate_p[9]  0 0 external
Vdac_astate_p10 tb_integration.i_chip.adc_inst.dac_astate_p[10] 0 0 external
Vdac_astate_p11 tb_integration.i_chip.adc_inst.dac_astate_p[11] 0 0 external
Vdac_astate_p12 tb_integration.i_chip.adc_inst.dac_astate_p[12] 0 0 external
Vdac_astate_p13 tb_integration.i_chip.adc_inst.dac_astate_p[13] 0 0 external
Vdac_astate_p14 tb_integration.i_chip.adc_inst.dac_astate_p[14] 0 0 external
Vdac_astate_p15 tb_integration.i_chip.adc_inst.dac_astate_p[15] 0 0 external

Vdac_bstate_p0  tb_integration.i_chip.adc_inst.dac_bstate_p[0]  0 0 external
Vdac_bstate_p1  tb_integration.i_chip.adc_inst.dac_bstate_p[1]  0 0 external
Vdac_bstate_p2  tb_integration.i_chip.adc_inst.dac_bstate_p[2]  0 0 external
Vdac_bstate_p3  tb_integration.i_chip.adc_inst.dac_bstate_p[3]  0 0 external
Vdac_bstate_p4  tb_integration.i_chip.adc_inst.dac_bstate_p[4]  0 0 external
Vdac_bstate_p5  tb_integration.i_chip.adc_inst.dac_bstate_p[5]  0 0 external
Vdac_bstate_p6  tb_integration.i_chip.adc_inst.dac_bstate_p[6]  0 0 external
Vdac_bstate_p7  tb_integration.i_chip.adc_inst.dac_bstate_p[7]  0 0 external
Vdac_bstate_p8  tb_integration.i_chip.adc_inst.dac_bstate_p[8]  0 0 external
Vdac_bstate_p9  tb_integration.i_chip.adc_inst.dac_bstate_p[9]  0 0 external
Vdac_bstate_p10 tb_integration.i_chip.adc_inst.dac_bstate_p[10] 0 0 external
Vdac_bstate_p11 tb_integration.i_chip.adc_inst.dac_bstate_p[11] 0 0 external
Vdac_bstate_p12 tb_integration.i_chip.adc_inst.dac_bstate_p[12] 0 0 external
Vdac_bstate_p13 tb_integration.i_chip.adc_inst.dac_bstate_p[13] 0 0 external
Vdac_bstate_p14 tb_integration.i_chip.adc_inst.dac_bstate_p[14] 0 0 external
Vdac_bstate_p15 tb_integration.i_chip.adc_inst.dac_bstate_p[15] 0 0 external

Vdac_astate_n0  tb_integration.i_chip.adc_inst.dac_astate_n[0]  0 0 external
Vdac_astate_n1  tb_integration.i_chip.adc_inst.dac_astate_n[1]  0 0 external
Vdac_astate_n2  tb_integration.i_chip.adc_inst.dac_astate_n[2]  0 0 external
Vdac_astate_n3  tb_integration.i_chip.adc_inst.dac_astate_n[3]  0 0 external
Vdac_astate_n4  tb_integration.i_chip.adc_inst.dac_astate_n[4]  0 0 external
Vdac_astate_n5  tb_integration.i_chip.adc_inst.dac_astate_n[5]  0 0 external
Vdac_astate_n6  tb_integration.i_chip.adc_inst.dac_astate_n[6]  0 0 external
Vdac_astate_n7  tb_integration.i_chip.adc_inst.dac_astate_n[7]  0 0 external
Vdac_astate_n8  tb_integration.i_chip.adc_inst.dac_astate_n[8]  0 0 external
Vdac_astate_n9  tb_integration.i_chip.adc_inst.dac_astate_n[9]  0 0 external
Vdac_astate_n10 tb_integration.i_chip.adc_inst.dac_astate_n[10] 0 0 external
Vdac_astate_n11 tb_integration.i_chip.adc_inst.dac_astate_n[11] 0 0 external
Vdac_astate_n12 tb_integration.i_chip.adc_inst.dac_astate_n[12] 0 0 external
Vdac_astate_n13 tb_integration.i_chip.adc_inst.dac_astate_n[13] 0 0 external
Vdac_astate_n14 tb_integration.i_chip.adc_inst.dac_astate_n[14] 0 0 external
Vdac_astate_n15 tb_integration.i_chip.adc_inst.dac_astate_n[15] 0 0 external

Vdac_bstate_n0  tb_integration.i_chip.adc_inst.dac_bstate_n[0]  0 0 external
Vdac_bstate_n1  tb_integration.i_chip.adc_inst.dac_bstate_n[1]  0 0 external
Vdac_bstate_n2  tb_integration.i_chip.adc_inst.dac_bstate_n[2]  0 0 external
Vdac_bstate_n3  tb_integration.i_chip.adc_inst.dac_bstate_n[3]  0 0 external
Vdac_bstate_n4  tb_integration.i_chip.adc_inst.dac_bstate_n[4]  0 0 external
Vdac_bstate_n5  tb_integration.i_chip.adc_inst.dac_bstate_n[5]  0 0 external
Vdac_bstate_n6  tb_integration.i_chip.adc_inst.dac_bstate_n[6]  0 0 external
Vdac_bstate_n7  tb_integration.i_chip.adc_inst.dac_bstate_n[7]  0 0 external
Vdac_bstate_n8  tb_integration.i_chip.adc_inst.dac_bstate_n[8]  0 0 external
Vdac_bstate_n9  tb_integration.i_chip.adc_inst.dac_bstate_n[9]  0 0 external
Vdac_bstate_n10 tb_integration.i_chip.adc_inst.dac_bstate_n[10] 0 0 external
Vdac_bstate_n11 tb_integration.i_chip.adc_inst.dac_bstate_n[11] 0 0 external
Vdac_bstate_n12 tb_integration.i_chip.adc_inst.dac_bstate_n[12] 0 0 external
Vdac_bstate_n13 tb_integration.i_chip.adc_inst.dac_bstate_n[13] 0 0 external
Vdac_bstate_n14 tb_integration.i_chip.adc_inst.dac_bstate_n[14] 0 0 external
Vdac_bstate_n15 tb_integration.i_chip.adc_inst.dac_bstate_n[15] 0 0 external

* Analog input (from sediff output, driven through Verilog real variables)
Vvin_p tb_integration.i_chip.adc_inst.vin_p 0 0 external
Vvin_n tb_integration.i_chip.adc_inst.vin_n 0 0 external

* Fixed supplies for ADC (not external — avoids 0V startup issue)
Vvdd_a  tb_integration.i_chip.adc_inst.vdd_a  0 1.2
Vvss_a  tb_integration.i_chip.adc_inst.vss_a  0 0
Vvdd_d  tb_integration.i_chip.adc_inst.vdd_d  0 1.2
Vvss_d  tb_integration.i_chip.adc_inst.vss_d  0 0
Vvdd_dac tb_integration.i_chip.adc_inst.vdd_dac 0 1.2
Vvss_dac tb_integration.i_chip.adc_inst.vss_dac 0 0

* =====================================================================
* Output format and analysis
* =====================================================================
.options filetype=ascii

.tran 0.1n 500n

.end
