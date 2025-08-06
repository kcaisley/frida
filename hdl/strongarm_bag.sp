************************************************************************
* Library Name: bag_vco_adc
* Cell Name:    comp_strongarm_core
* View Name:    schematic
************************************************************************

.SUBCKT comp_strongarm_core VDD VSS clk inn inp midn midp osn osp outn outp
MNNFBP VSS outp outn midp / nmos4_lvt
MNNFBN VSS outn outp midn / nmos4_lvt
MNINP VSS midn inp tail / nmos4_lvt
MNINN VSS midp inn tail / nmos4_lvt
MNTAIL VSS tail clk VSS / nmos4_lvt
MNOSN VSS midp osn tail / nmos4_lvt
MNOSP VSS midn osp tail / nmos4_lvt
MPBRO VDD net5 clk net6 / pmos4_analog
MPBRM VDD net2 clk net1 / pmos4_analog
MPPFBN VDD outn outp VDD / pmos4_lvt
MPSWON VDD outn clk VDD / pmos4_lvt
MPSWMN VDD midn clk VDD / pmos4_lvt
MPSWMP VDD midp clk VDD / pmos4_lvt
MPPFBP VDD outp outn VDD / pmos4_lvt
MPSWOP VDD outp clk VDD / pmos4_lvt
MP27 VDD outp clk outn / pmos4_lvt
MP28 VDD midp clk midn / pmos4_lvt
.ENDS