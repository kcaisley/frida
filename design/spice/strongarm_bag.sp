
.subckt latch vdd vss clk inn inp midn midp osn osp outn outp
mnnfbp outp outn midp vss NMOS
mnnfbn outn outp midn vss NMOS
mninp midn inp tail vss NMOS
mninn midp inn tail vss NMOS
mntail tail clk vss vss NMOS
mnosn midp osn tail vss NMOS
mnosp midn osp tail vss NMOS
mpbro net5 clk net6 vdd PMOS
mpbrm net2 clk net1 vdd PMOS
mppfbn outn outp vdd vdd PMOS
mpswon outn clk vdd vdd PMOS
mpswmn midn clk vdd vdd PMOS
mpswmp midp clk vdd vdd PMOS
mppfbp outp outn vdd vdd PMOS
mpswop outp clk vdd vdd PMOS
mp27 outp clk outn vdd PMOS
mp28 midp clk midn vdd PMOS
.ends

.end
