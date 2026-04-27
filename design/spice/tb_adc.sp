* SPICE wrapper for co-simulation (spicebind)
*
* HDL_INSTANCE = tb_integration.i_sediff,tb_integration.i_chip.adc_inst
*
* V-source names must match lowercased hierarchical VPI port names
* (spicebind strips leading 'V' and looks up by name).

* PDK transistor models (TSMC 65LP typical corner)
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l' tt_lib
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l' pre_simu

* Standard cell SPICE (TSMC 65LP)
.include '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lp_200a/tcbn65lp_200a.spi'
.include '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lplvt_200a/tcbn65lplvt_200a.spi'

* Design subcircuits (.sp converted from .cdl for ngspice compatibility)
.include 'ths4541.sp'
.include 'sediff.sp'
.include 'comp.sp'
.include 'sampswitch.sp'
.include 'caparray.sp'
.include 'capdriver.sp'
.include 'adc_digital.sp'
.include 'adc.sp'

* =============================================================
* sediff instance
* =============================================================
Vtb_integration.i_sediff.vin_p_ext tb_integration.i_sediff.vin_p_ext 0 0 external
Vtb_integration.i_sediff.vdd tb_integration.i_sediff.vdd 0 0 external
X_sediff tb_integration.i_sediff.vin_p_ext tb_integration.i_sediff.vin_p tb_integration.i_sediff.vin_n tb_integration.i_sediff.vdd sediff

* =============================================================
* adc instance
* =============================================================
Vtb_integration.i_chip.adc_inst.seq_init tb_integration.i_chip.adc_inst.seq_init 0 0 external
Vtb_integration.i_chip.adc_inst.seq_samp tb_integration.i_chip.adc_inst.seq_samp 0 0 external
Vtb_integration.i_chip.adc_inst.seq_comp tb_integration.i_chip.adc_inst.seq_comp 0 0 external
Vtb_integration.i_chip.adc_inst.seq_update tb_integration.i_chip.adc_inst.seq_update 0 0 external
Vtb_integration.i_chip.adc_inst.en_init tb_integration.i_chip.adc_inst.en_init 0 0 external
Vtb_integration.i_chip.adc_inst.en_samp_p tb_integration.i_chip.adc_inst.en_samp_p 0 0 external
Vtb_integration.i_chip.adc_inst.en_samp_n tb_integration.i_chip.adc_inst.en_samp_n 0 0 external
Vtb_integration.i_chip.adc_inst.en_comp tb_integration.i_chip.adc_inst.en_comp 0 0 external
Vtb_integration.i_chip.adc_inst.en_update tb_integration.i_chip.adc_inst.en_update 0 0 external
Vtb_integration.i_chip.adc_inst.dac_mode tb_integration.i_chip.adc_inst.dac_mode 0 0 external
Vtb_integration.i_chip.adc_inst.dac_diffcaps tb_integration.i_chip.adc_inst.dac_diffcaps 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[15] tb_integration.i_chip.adc_inst.dac_astate_p[15] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[14] tb_integration.i_chip.adc_inst.dac_astate_p[14] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[13] tb_integration.i_chip.adc_inst.dac_astate_p[13] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[12] tb_integration.i_chip.adc_inst.dac_astate_p[12] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[11] tb_integration.i_chip.adc_inst.dac_astate_p[11] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[10] tb_integration.i_chip.adc_inst.dac_astate_p[10] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[9] tb_integration.i_chip.adc_inst.dac_astate_p[9] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[8] tb_integration.i_chip.adc_inst.dac_astate_p[8] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[7] tb_integration.i_chip.adc_inst.dac_astate_p[7] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[6] tb_integration.i_chip.adc_inst.dac_astate_p[6] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[5] tb_integration.i_chip.adc_inst.dac_astate_p[5] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[4] tb_integration.i_chip.adc_inst.dac_astate_p[4] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[3] tb_integration.i_chip.adc_inst.dac_astate_p[3] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[2] tb_integration.i_chip.adc_inst.dac_astate_p[2] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[1] tb_integration.i_chip.adc_inst.dac_astate_p[1] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_p[0] tb_integration.i_chip.adc_inst.dac_astate_p[0] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[15] tb_integration.i_chip.adc_inst.dac_bstate_p[15] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[14] tb_integration.i_chip.adc_inst.dac_bstate_p[14] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[13] tb_integration.i_chip.adc_inst.dac_bstate_p[13] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[12] tb_integration.i_chip.adc_inst.dac_bstate_p[12] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[11] tb_integration.i_chip.adc_inst.dac_bstate_p[11] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[10] tb_integration.i_chip.adc_inst.dac_bstate_p[10] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[9] tb_integration.i_chip.adc_inst.dac_bstate_p[9] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[8] tb_integration.i_chip.adc_inst.dac_bstate_p[8] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[7] tb_integration.i_chip.adc_inst.dac_bstate_p[7] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[6] tb_integration.i_chip.adc_inst.dac_bstate_p[6] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[5] tb_integration.i_chip.adc_inst.dac_bstate_p[5] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[4] tb_integration.i_chip.adc_inst.dac_bstate_p[4] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[3] tb_integration.i_chip.adc_inst.dac_bstate_p[3] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[2] tb_integration.i_chip.adc_inst.dac_bstate_p[2] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[1] tb_integration.i_chip.adc_inst.dac_bstate_p[1] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_p[0] tb_integration.i_chip.adc_inst.dac_bstate_p[0] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[15] tb_integration.i_chip.adc_inst.dac_astate_n[15] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[14] tb_integration.i_chip.adc_inst.dac_astate_n[14] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[13] tb_integration.i_chip.adc_inst.dac_astate_n[13] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[12] tb_integration.i_chip.adc_inst.dac_astate_n[12] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[11] tb_integration.i_chip.adc_inst.dac_astate_n[11] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[10] tb_integration.i_chip.adc_inst.dac_astate_n[10] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[9] tb_integration.i_chip.adc_inst.dac_astate_n[9] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[8] tb_integration.i_chip.adc_inst.dac_astate_n[8] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[7] tb_integration.i_chip.adc_inst.dac_astate_n[7] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[6] tb_integration.i_chip.adc_inst.dac_astate_n[6] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[5] tb_integration.i_chip.adc_inst.dac_astate_n[5] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[4] tb_integration.i_chip.adc_inst.dac_astate_n[4] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[3] tb_integration.i_chip.adc_inst.dac_astate_n[3] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[2] tb_integration.i_chip.adc_inst.dac_astate_n[2] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[1] tb_integration.i_chip.adc_inst.dac_astate_n[1] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_astate_n[0] tb_integration.i_chip.adc_inst.dac_astate_n[0] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[15] tb_integration.i_chip.adc_inst.dac_bstate_n[15] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[14] tb_integration.i_chip.adc_inst.dac_bstate_n[14] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[13] tb_integration.i_chip.adc_inst.dac_bstate_n[13] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[12] tb_integration.i_chip.adc_inst.dac_bstate_n[12] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[11] tb_integration.i_chip.adc_inst.dac_bstate_n[11] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[10] tb_integration.i_chip.adc_inst.dac_bstate_n[10] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[9] tb_integration.i_chip.adc_inst.dac_bstate_n[9] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[8] tb_integration.i_chip.adc_inst.dac_bstate_n[8] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[7] tb_integration.i_chip.adc_inst.dac_bstate_n[7] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[6] tb_integration.i_chip.adc_inst.dac_bstate_n[6] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[5] tb_integration.i_chip.adc_inst.dac_bstate_n[5] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[4] tb_integration.i_chip.adc_inst.dac_bstate_n[4] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[3] tb_integration.i_chip.adc_inst.dac_bstate_n[3] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[2] tb_integration.i_chip.adc_inst.dac_bstate_n[2] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[1] tb_integration.i_chip.adc_inst.dac_bstate_n[1] 0 0 external
Vtb_integration.i_chip.adc_inst.dac_bstate_n[0] tb_integration.i_chip.adc_inst.dac_bstate_n[0] 0 0 external
Vtb_integration.i_chip.adc_inst.vin_p tb_integration.i_chip.adc_inst.vin_p 0 0 external
Vtb_integration.i_chip.adc_inst.vin_n tb_integration.i_chip.adc_inst.vin_n 0 0 external
Vtb_integration.i_chip.adc_inst.vdd_a tb_integration.i_chip.adc_inst.vdd_a 0 1.2
Vtb_integration.i_chip.adc_inst.vss_a tb_integration.i_chip.adc_inst.vss_a 0 0
Vtb_integration.i_chip.adc_inst.vdd_d tb_integration.i_chip.adc_inst.vdd_d 0 1.2
Vtb_integration.i_chip.adc_inst.vss_d tb_integration.i_chip.adc_inst.vss_d 0 0
Vtb_integration.i_chip.adc_inst.vdd_dac tb_integration.i_chip.adc_inst.vdd_dac 0 1.2
Vtb_integration.i_chip.adc_inst.vss_dac tb_integration.i_chip.adc_inst.vss_dac 0 0

X_adc tb_integration.i_chip.adc_inst.seq_init
+ tb_integration.i_chip.adc_inst.seq_samp
+ tb_integration.i_chip.adc_inst.seq_comp
+ tb_integration.i_chip.adc_inst.seq_update
+ tb_integration.i_chip.adc_inst.comp_out
+ tb_integration.i_chip.adc_inst.en_init
+ tb_integration.i_chip.adc_inst.en_samp_p
+ tb_integration.i_chip.adc_inst.en_samp_n
+ tb_integration.i_chip.adc_inst.en_comp
+ tb_integration.i_chip.adc_inst.en_update
+ tb_integration.i_chip.adc_inst.dac_mode
+ tb_integration.i_chip.adc_inst.dac_diffcaps
+ tb_integration.i_chip.adc_inst.dac_astate_p[15]
+ tb_integration.i_chip.adc_inst.dac_astate_p[14]
+ tb_integration.i_chip.adc_inst.dac_astate_p[13]
+ tb_integration.i_chip.adc_inst.dac_astate_p[12]
+ tb_integration.i_chip.adc_inst.dac_astate_p[11]
+ tb_integration.i_chip.adc_inst.dac_astate_p[10]
+ tb_integration.i_chip.adc_inst.dac_astate_p[9]
+ tb_integration.i_chip.adc_inst.dac_astate_p[8]
+ tb_integration.i_chip.adc_inst.dac_astate_p[7]
+ tb_integration.i_chip.adc_inst.dac_astate_p[6]
+ tb_integration.i_chip.adc_inst.dac_astate_p[5]
+ tb_integration.i_chip.adc_inst.dac_astate_p[4]
+ tb_integration.i_chip.adc_inst.dac_astate_p[3]
+ tb_integration.i_chip.adc_inst.dac_astate_p[2]
+ tb_integration.i_chip.adc_inst.dac_astate_p[1]
+ tb_integration.i_chip.adc_inst.dac_astate_p[0]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[15]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[14]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[13]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[12]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[11]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[10]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[9]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[8]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[7]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[6]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[5]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[4]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[3]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[2]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[1]
+ tb_integration.i_chip.adc_inst.dac_bstate_p[0]
+ tb_integration.i_chip.adc_inst.dac_astate_n[15]
+ tb_integration.i_chip.adc_inst.dac_astate_n[14]
+ tb_integration.i_chip.adc_inst.dac_astate_n[13]
+ tb_integration.i_chip.adc_inst.dac_astate_n[12]
+ tb_integration.i_chip.adc_inst.dac_astate_n[11]
+ tb_integration.i_chip.adc_inst.dac_astate_n[10]
+ tb_integration.i_chip.adc_inst.dac_astate_n[9]
+ tb_integration.i_chip.adc_inst.dac_astate_n[8]
+ tb_integration.i_chip.adc_inst.dac_astate_n[7]
+ tb_integration.i_chip.adc_inst.dac_astate_n[6]
+ tb_integration.i_chip.adc_inst.dac_astate_n[5]
+ tb_integration.i_chip.adc_inst.dac_astate_n[4]
+ tb_integration.i_chip.adc_inst.dac_astate_n[3]
+ tb_integration.i_chip.adc_inst.dac_astate_n[2]
+ tb_integration.i_chip.adc_inst.dac_astate_n[1]
+ tb_integration.i_chip.adc_inst.dac_astate_n[0]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[15]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[14]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[13]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[12]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[11]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[10]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[9]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[8]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[7]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[6]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[5]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[4]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[3]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[2]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[1]
+ tb_integration.i_chip.adc_inst.dac_bstate_n[0]
+ tb_integration.i_chip.adc_inst.vin_p tb_integration.i_chip.adc_inst.vin_n
+ tb_integration.i_chip.adc_inst.vdd_a tb_integration.i_chip.adc_inst.vss_a
+ tb_integration.i_chip.adc_inst.vdd_d tb_integration.i_chip.adc_inst.vss_d
+ tb_integration.i_chip.adc_inst.vdd_dac
+ tb_integration.i_chip.adc_inst.vss_dac adc

* Output format and analysis
.options filetype=ascii
.options reltol=1e-3 vabstol=1u iabstol=1p gmin=1e-12 method=gear maxord=2 itl1=500 itl4=200 cshunt=1e-15
.nodeset v(tb_integration.i_chip.adc_inst.comp_out)=1.2
.nodeset v(x_adc.comp_out_p)=1.2 v(x_adc.comp_out_n)=1.2
.nodeset v(x_adc.xcomp.COMP_P)=1.2 v(x_adc.xcomp.COMP_N)=1.2
.nodeset v(x_adc.xcomp.xi3.net35)=1.2 v(x_adc.xcomp.xi3.net38)=0
.nodeset v(x_adc.xcomp.xi3.net41)=0 v(x_adc.xcomp.xi3.net42)=1.2
.nodeset v(x_adc.xcomp.xlatch.net031)=1.2 v(x_adc.xcomp.xlatch.net037)=1.2
.tran 0.1n 500n
.end
