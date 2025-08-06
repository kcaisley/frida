
.subckt comp_strongarm_core vdd vss clk inn inp midn midp osn osp outn outp
mnnfbp vss outp outn midp nmos
mnnfbn vss outn outp midn nmos
mninp vss midn inp tail nmos
mninn vss midp inn tail nmos
mntail vss tail clk vss nmos
mnosn vss midp osn tail nmos
mnosp vss midn osp tail nmos
mpbro vdd net5 clk net6 pmos
mpbrm vdd net2 clk net1 pmos
mppfbn vdd outn outp vdd pmos
mpswon vdd outn clk vdd pmos
mpswmn vdd midn clk vdd pmos
mpswmp vdd midp clk vdd pmos
mppfbp vdd outp outn vdd pmos
mpswop vdd outp clk vdd pmos
mp27 vdd outp clk outn pmos
mp28 vdd midp clk midn pmos
.ends
