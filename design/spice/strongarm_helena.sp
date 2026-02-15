.subckt latch clock inn inp outn outp sub vdd vss
mn5 outn outp net1 net7 NMOS
mn4 outp outn net3 net6 NMOS
mn3 net2 clock net5 net4 NMOS
mn2 net3 inn net2 sub NMOS
mn1 net1 inp net2 sub NMOS
mp5 net1 clock vdd vdd PMOS
mp6 outn clock vdd vdd PMOS
mp3 net3 clock vdd vdd PMOS
mp2 outp clock vdd vdd PMOS
mp1 outn outp vdd vdd PMOS
mp4 outp outn vdd vdd PMOS
.ends

.end
