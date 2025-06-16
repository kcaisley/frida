************************************************************************
* Library Name: bag_vco_adc
* Cell Name:    comp_strongarm_core
* View Name:    schematic
************************************************************************

.SUBCKT comp_strongarm_core VDD VSS clk inn inp midn midp osn osp outn outp
XXNFBP VSS outp outn midp / nmos4_lvt
XXNFBN VSS outn outp midn / nmos4_lvt
XXINP VSS midn inp tail / nmos4_lvt
XXINN VSS midp inn tail / nmos4_lvt
XXTAIL VSS tail clk VSS / nmos4_lvt
XXOSN VSS midp osn tail / nmos4_lvt
XXOSP VSS midn osp tail / nmos4_lvt
XXBRO VDD net5 clk net6 / pmos4_analog
XXBRM VDD net2 clk net1 / pmos4_analog
XXPFBN VDD outn outp VDD / pmos4_lvt
XXSWON VDD outn clk VDD / pmos4_lvt
XXSWMN VDD midn clk VDD / pmos4_lvt
XXSWMP VDD midp clk VDD / pmos4_lvt
XXPFBP VDD outp outn VDD / pmos4_lvt
XXSWOP VDD outp clk VDD / pmos4_lvt
XX27 VDD outp clk outn / pmos4_lvt
XX28 VDD midp clk midn / pmos4_lvt
.ENDS