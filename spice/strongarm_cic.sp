
.subckt sarcmphx1_ev ci ck co vmr n1 n2 vdd vss
mn0 n1 ck vss vss nmos
mn1 n2 ci n1  vss nmos
mn2 n1 ci n2  vss nmos
mn3 n2 ci n1  vss nmos
mn4 n1 ci n2  vss nmos
mn5 n2 ci n1  vss nmos
mn6 co vmr n2  vss nmos

mp0 vdd ck n1 vdd pmos
mp1 n2 ck vdd vdd pmos
mp2 vdd vdd n2 vdd pmos
mp3 co ck vdd vdd pmos
mp4 vdd vmr co vdd pmos
mp5 co vmr vdd vdd pmos
mp6 vdd vmr co vdd pmos
.ends sarcmphx1_ev

.subckt sarkickhx1_ev ci ck ckn vdd vss
mn0 n1 ckn vss vss nmos
mn1 n1 ci n1  vss nmos
mn2 n1 ci n1  vss nmos
mn3 n1 ci n1  vss nmos
mn4 n1 ci n1  vss nmos
mn5 n1 ci n1  vss nmos
mn6 vdd ck n1  vss nmos

mp0 vdd ckn n1 vdd pmos
mp1_dmy vdd vdd vdd vdd pmos
mp2_dmy vdd vdd vdd vdd pmos
mp3_dmy vdd vdd vdd vdd pmos
mp4_dmy vdd vdd vdd vdd pmos
mp5_dmy vdd vdd vdd vdd pmos
mp6 vdd vdd vdd vdd pmos
.ends sarkickhx1_ev

.subckt sarcmpx1_ev cpi cni cpo cno ck_cmp ck_sample done vdd vss
xa1 cpi ck_b ck_n vdd vss sarkickhx1_ev
xa2 cpi ck_b cno_i cpo_i n1 nc1 vdd vss sarcmphx1_ev
xa3 cni ck_b cpo_i cno_i n1 nc2 vdd vss sarcmphx1_ev
xa2a cpo_i cpo vdd vss ivx4_ev
xa3a cno_i cno vdd vss ivx4_ev
xa4 cni ck_b ck_n vdd vss sarkickhx1_ev
xa9 ck_n ck_b vdd vss ivx1_ev
xa10 done_n ck_a ck_n vdd vss ndx1_ev
xa11 ck_sample done done_n vdd vss nrx1_ev
xa12 ck_cmp ck_a vdd vss ivx1_ev
.ends
