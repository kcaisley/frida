* Comparator clock-to-output delay measurement using Spectre SPICE compatibility.
* Run with:
*   . /users/kcaisley/asiclab/tech/tsmc65/cds/workspace.sh
*   spectre tb_comp_delay_spectre.sp +escchars +log tb_comp_delay_spectre.log

simulator lang=spice

.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' tt_lib
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' pre_simu
.include '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lp_200a/tcbn65lp_200a.spi'
.include '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lplvt_200a/tcbn65lplvt_200a.spi'
.include 'comp.sp'

VDD vdd_a 0 1.2
VSS vss_a 0 0
* First decision: vin_p < vin_n. Second decision: vin_p > vin_n.
VINP vin_p 0 pwl(0 0.55 15n 0.55 15.1n 0.65)
VINN vin_n 0 0.60
VCLK clk 0 pulse(0 1.2 2n 0.1n 0.1n 4n 20n)

XCOMP vin_p vin_n dout_p dout_n clk vdd_a vss_a comp

.nodeset v(dout_p)=0 v(dout_n)=1.2 v(xcomp.COMP_P)=1.2 v(xcomp.COMP_N)=0
.tran 0.002n 36n

.measure tran doutp_min MIN v(dout_p)
.measure tran doutp_max MAX v(dout_p)
.measure tran doutn_min MIN v(dout_n)
.measure tran doutn_max MAX v(dout_n)
.measure tran comp_p_min MIN v(xcomp.COMP_P)
.measure tran comp_p_max MAX v(xcomp.COMP_P)
.measure tran comp_n_min MIN v(xcomp.COMP_N)
.measure tran comp_n_max MAX v(xcomp.COMP_N)
.measure tran t_clk WHEN v(clk)=0.6 RISE=2
.measure tran t_doutp_r WHEN v(dout_p)=0.6 RISE=1
.measure tran t_doutp_f WHEN v(dout_p)=0.6 FALL=1
.measure tran t_doutn_r WHEN v(dout_n)=0.6 RISE=1
.measure tran t_doutn_f WHEN v(dout_n)=0.6 FALL=1
.measure tran t_comp_p_r WHEN v(xcomp.COMP_P)=0.6 RISE=1
.measure tran t_comp_p_f WHEN v(xcomp.COMP_P)=0.6 FALL=1
.measure tran t_comp_n_r WHEN v(xcomp.COMP_N)=0.6 RISE=1
.measure tran t_comp_n_f WHEN v(xcomp.COMP_N)=0.6 FALL=1
.measure tran td_doutp_r PARAM='t_doutp_r - t_clk'
.measure tran td_doutp_f PARAM='t_doutp_f - t_clk'
.measure tran td_doutn_r PARAM='t_doutn_r - t_clk'
.measure tran td_doutn_f PARAM='t_doutn_f - t_clk'
.measure tran td_comp_p_r PARAM='t_comp_p_r - t_clk'
.measure tran td_comp_p_f PARAM='t_comp_p_f - t_clk'
.measure tran td_comp_n_r PARAM='t_comp_n_r - t_clk'
.measure tran td_comp_n_f PARAM='t_comp_n_f - t_clk'

simulator lang=spectre
saveOptions options save=allpub rawfmt=nutascii
save clk vin_p vin_n dout_p dout_n XCOMP.COMP_P XCOMP.COMP_N
