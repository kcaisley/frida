.subckt comparator_latch clock inn inp outn outp sub vdd vee
mn5 net7 outn outp net1 nmos
mn4 net6 outp outn net3 nmos
mn3 net4 net2 clock net5 nmos
mn2 sub net3 inn net2 nmos
mn1 sub net1 inp net2 nmos
mp5 vdd net1 clock vdd pmos
mp6 vdd outn clock vdd pmos
mp3 vdd net3 clock vdd pmos
mp2 vdd outp clock vdd pmos
mp1 vdd outn outp vdd pmos
mp4 vdd outp outn vdd pmos
.ends
