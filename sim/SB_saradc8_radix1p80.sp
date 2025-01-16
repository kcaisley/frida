* SPICE export by:      S-Edit 2023.2.0
* Export time:          Fri Jan 17 00:04:36 2025
* Design path:          /users/kcaisley/helena/oa/lib.defs
* Library:              sasc
* Cell:                 SB_saradc8_radixN
* Testbench:            Spice
* View:                 schematic
* Export as:            top-level cell
* Export mode:          hierarchical
* Exclude empty:        yes
* Exclude .model:       no
* Exclude .hdl:         no
* Exclude .end:         no
* Expand paths:         yes
* Wrap lines:           no
* Exclude simulator commands:  no
* Exclude global pins:         no
* Exclude instance locations:  no
* Control property name(s):    SPICE

********* Simulation Settings - General Section *********
.LIB "/users/kcaisley/helena/tech/tsmc65/default_testbench_header_55ulp_linux.lib" tt
*************** Subcircuits ***************
.subckt PAGEFRAME gnd
* Library name: devices
* Cell name: PAGEFRAME
* View name: schematic
* PORT=gnd TYPE=InOut

Rstd_version gnd gnd STDCELL_VERSION_1_0 r=0 $ $x=208 $y=32 $w=416 $h=64
.ends

.subckt Source_v_pulse_differential n p ref del=0 high=1.8 low=0 period=200n risefall=10n width=100n
* Library name: devices
* Cell name: Source_v_pulse_differential
* View name: schematic
* PORT=p TYPE=InOut
* PORT=ref TYPE=InOut
* PORT=n TYPE=InOut

*
* (C) Caeleste
* Cell: Source_v_pulse_differential | Design: devices
* Designed by: Bart Dierickx | Sat Jun  1 11:13:23 2024
* Cell version , rev. 8
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
vSource_v_pulse_1 p ref pulse(low high del risefall risefall width-risefall period) $ $x=352 $y=352 $w=128 $h=192
vSource_v_pulse_2 n ref pulse(high low del risefall risefall width-risefall period) $ $x=544 $y=352 $w=128 $h=192
.ends

.subckt rdivider1__b3 rtap<0> rtap<1> rtap<2> sub vcc vee rladder=100k
* Library name: sasc
* Cell name: rdivider1__b3
* View name: schematic
* PORT=rtap<1> TYPE=InOut
* PORT=rtap<0> TYPE=InOut
* PORT=sub TYPE=Other
* PORT=vee TYPE=Other
* PORT=vcc TYPE=Other
* PORT=rtap<2> TYPE=InOut

*
* (C) Caeleste
* Cell: rdivider1__b3 | Design: sasc
* Designed by: Bart Dierickx | Tue Jun 18 18:49:45 2024
* Cell version , rev. 1
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
RResistor_2 vcc rtap<2> rladder/2 TC=0.0, 0.0 $ $x=480 $y=576 $w=384 $h=48 $r=270
RResistor_3 rtap<2> rtap<1> rladder/4 TC=0.0, 0.0 $ $x=864 $y=576 $w=384 $h=48 $r=270
RResistor_4 rtap<1> rtap<0> rladder/8 TC=0.0, 0.0 $ $x=1248 $y=576 $w=384 $h=48 $r=270
RResistor_5 rtap<0> vee rladder/8 TC=0.0, 0.0 $ $x=1632 $y=576 $w=384 $h=48 $r=270
.ends

.subckt nor2 A B out sub vcc vee S=1
* Library name: logic
* Cell name: nor2
* View name: schematic
* PORT=A TYPE=In
* PORT=vee TYPE=Other
* PORT=vcc TYPE=Other
* PORT=out TYPE=Out
* PORT=sub TYPE=Other
* PORT=B TYPE=In

* 2 input nand gate
* (C) Caeleste
* Cell: nor2 | Design: logic
* Designed by: Nick | Sat Feb 12 23:51:09 2022
* Cell version 1.0, rev. 2
Xstd_versioncheck 0 PAGEFRAME $ $x=576 $y=-416 $w=2176 $h=192
XMn1 out vcc N_1 sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=448 $y=352 $w=128 $h=192
XMn2 N_1 A vee sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=736 $y=96 $w=128 $h=192 $m
XMn3 N_1 B vee sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=448 $y=96 $w=128 $h=192
XMp1 N_2 A vcc vcc log_pmos W_='log_pmos_WS1*2*S' L_='log_pmos_Lmin' M_=1 $ $x=448 $y=832 $w=128 $h=192
XMp2 out B N_2 vcc log_pmos W_='log_pmos_WS1*2*S' L_='log_pmos_Lmin' M_=1 $ $x=448 $y=608 $w=128 $h=192
.ends

.subckt srff Q Q_n R S sub vcc vee
* Library name: logic
* Cell name: srff
* View name: schematic
* PORT=Q_n TYPE=Out
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other
* PORT=Q TYPE=Out
* PORT=R TYPE=In
* PORT=S TYPE=In
* PORT=sub TYPE=Other

*
* (C) Caeleste
* Cell: srff | Design: logic
* Designed by: Nick | Sun Feb 13 01:06:04 2022
* Cell version 1.0, rev. 15
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xnor2_3 Q S Q_n sub vcc vee nor2 S=1 $ $x=1280 $y=896 $w=192 $h=128
Xnor2_4 Q_n R Q sub vcc vee nor2 S=1 $ $x=1280 $y=576 $w=192 $h=128 $r=180 $m
.ends

.subckt latch9_BETA clock D nclock nQ Q sub vcc vee
* Library name: logic
* Cell name: latch9_BETA
* View name: schematic
* PORT=nQ TYPE=Out
* PORT=sub TYPE=Other
* PORT=Q TYPE=Out
* PORT=nclock TYPE=In
* PORT=D TYPE=In
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other
* PORT=clock TYPE=In

*
* (C) Caeleste
* Cell: latch9_BETA | Design: logic
* Designed by: Amir | Tue Apr 11 15:45:07 2023
* Cell version 1.0, rev. 3
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
XMn4 N_1 clock vee sub log_nmos W_='log_nmos_WS1*2' L_='log_nmos_Lmin' M_=1 $ $x=1344 $y=480 $w=128 $h=192
XMn8 nQ Q N_1 sub log_nmos W_='log_nmos_WS1*2' L_='log_nmos_Lmin' M_=1 $ $x=1408 $y=704 $w=128 $h=192 $m
XMn9 N_4 nQ vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1792 $y=480 $w=128 $h=192
XMn10 N_3 nclock vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=832 $y=480 $w=128 $h=192
XMn11 nQ D N_3 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=832 $y=704 $w=128 $h=192
XMn12 Q vcc N_4 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1792 $y=736 $w=128 $h=192
XMp7 N_2 clock vcc vcc log_pmos W_='log_pmos_WS1*2' L_='log_pmos_Lmin' M_=1 $ $x=832 $y=1184 $w=128 $h=192
XMp9 N_5 nclock vcc vcc log_pmos W_='log_pmos_WS1*4' L_='log_pmos_Lmin' M_=1 $ $x=1344 $y=1184 $w=128 $h=192
XMp10 nQ D N_2 vcc log_pmos W_='log_pmos_WS1*2' L_='log_pmos_Lmin' M_=1 $ $x=832 $y=960 $w=128 $h=192
XMp11 Q nQ vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1792 $y=1024 $w=128 $h=192
XMp12 nQ Q N_5 vcc log_pmos W_='log_pmos_WS1*4' L_='log_pmos_Lmin' M_=1 $ $x=1408 $y=960 $w=128 $h=192 $m
.ends

.subckt dff9 clock D nclock nQ Q sub vcc vee
* Library name: logic
* Cell name: dff9
* View name: schematic
* PORT=sub TYPE=Other
* PORT=vcc TYPE=Other
* PORT=clock TYPE=In
* PORT=vee TYPE=Other
* PORT=nclock TYPE=In
* PORT=Q TYPE=Out
* PORT=nQ TYPE=Out
* PORT=D TYPE=In

*
* (C) Caeleste
* Cell: dff9 | Design: logic
* Designed by:  | Tue Apr 11 15:45:07 2023
* Cell version , rev. 4
Xstd_versioncheck 0 PAGEFRAME $ $x=576 $y=-928 $w=2176 $h=192
Xlatch9_1 clock D nclock N_2 N_1 sub vcc vee latch9_BETA $ $x=160 $y=144 $w=320 $h=352
Xlatch9_2 nclock N_2 clock Q nQ sub vcc vee latch9_BETA $ $x=704 $y=144 $w=320 $h=352
.ends

.subckt sequencer1_unitcell cdacclock clockn clockp D init nset Q sub vcc vee
* Library name: sasc
* Cell name: sequencer1_unitcell
* View name: schematic
* PORT=sub TYPE=Other
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other
* PORT=nset TYPE=Out
* PORT=init TYPE=In
* PORT=clockp TYPE=In
* PORT=clockn TYPE=In
* PORT=D TYPE=In
* PORT=cdacclock TYPE=Out
* PORT=Q TYPE=Out

*
* (C) Caeleste
* Cell: sequencer1_unitcell | Design: sasc
* Designed by:  | Thu Jun 13 16:05:25 2024
* Cell version , rev. 1
Xstd_versioncheck 0 PAGEFRAME $ $x=576 $y=-928 $w=2176 $h=192
Xdff9_13 clockp D clockn cdacclock Q sub vcc vee dff9 $ $x=480 $y=-112 $w=320 $h=352
Xsrff_11 nset N_1 init Q sub vcc vee srff $ $x=480 $y=416 $w=192 $h=128
.ends

.subckt dff9_asr asr clock D nclock nQ Q sub vcc vee
* Library name: logic
* Cell name: dff9_asr
* View name: schematic
* PORT=vcc TYPE=Other
* PORT=D TYPE=In
* PORT=Q TYPE=Out
* PORT=clock TYPE=In
* PORT=asr TYPE=In
* PORT=nclock TYPE=In
* PORT=sub TYPE=Other
* PORT=nQ TYPE=Out
* PORT=vee TYPE=Other

*
* (C) Caeleste
* Cell: dff9_asr | Design: logic
* Designed by:  | Sat Feb 12 23:51:10 2022
* Cell version , rev. 2
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
XMn1 nQ asr N_1 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=2720 $y=1152 $w=128 $h=192
XMn2 Qi vcc N_2 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=992 $y=1152 $w=128 $h=192
XMn3 N_3 nclock vee sub log_nmos W_='log_nmos_WS1*2' L_='log_nmos_Lmin' M_=1 $ $x=2272 $y=672 $w=128 $h=192
XMn4 N_5 clock vee sub log_nmos W_='log_nmos_WS1*2' L_='log_nmos_Lmin' M_=1 $ $x=544 $y=672 $w=128 $h=192
XMn5 Q nQ N_3 sub log_nmos W_='log_nmos_WS1*2' L_='log_nmos_Lmin' M_=1 $ $x=2336 $y=896 $w=128 $h=192 $m
XMn6 N_1 Q vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=2720 $y=928 $w=128 $h=192
XMn7 N_9 clock vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1664 $y=672 $w=128 $h=192
XMn8 N_11 Qi N_5 sub log_nmos W_='log_nmos_WS1*2' L_='log_nmos_Lmin' M_=1 $ $x=608 $y=896 $w=128 $h=192 $m
XMn9 N_2 nQi vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=992 $y=928 $w=128 $h=192
XMn10 N_8 nclock vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=-224 $y=672 $w=128 $h=192
XMn11 N_12 D N_8 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=-224 $y=896 $w=128 $h=192
XMn12 Q nQi N_9 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1664 $y=896 $w=128 $h=192
XMn13 nQi asr N_11 sub log_nmos W_='log_nmos_WS1*2' L_='log_nmos_Lmin' M_=1 $ $x=544 $y=1120 $w=128 $h=192
XMn14 nQi asr N_12 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=-160 $y=1120 $w=128 $h=192 $m
XMp1 nQi asr vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=224 $y=1504 $w=128 $h=192
XMp2 nQ asr vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=3104 $y=1472 $w=128 $h=192
XMp3 N_4 nclock vcc vcc log_pmos W_='log_pmos_WS1*2' L_='log_pmos_Lmin' M_=1 $ $x=1664 $y=1664 $w=128 $h=192
XMp4 N_6 clock vcc vcc log_pmos W_='log_pmos_WS1*4' L_='log_pmos_Lmin' M_=1 $ $x=2272 $y=1664 $w=128 $h=192
XMp5 Q nQi N_4 vcc log_pmos W_='log_pmos_WS1*2' L_='log_pmos_Lmin' M_=1 $ $x=1664 $y=1440 $w=128 $h=192
XMp6 nQ Q vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=2720 $y=1472 $w=128 $h=192
XMp7 N_7 clock vcc vcc log_pmos W_='log_pmos_WS1*2' L_='log_pmos_Lmin' M_=1 $ $x=-224 $y=1664 $w=128 $h=192
XMp8 Q nQ N_6 vcc log_pmos W_='log_pmos_WS1*4' L_='log_pmos_Lmin' M_=1 $ $x=2336 $y=1440 $w=128 $h=192 $m
XMp9 N_10 nclock vcc vcc log_pmos W_='log_pmos_WS1*4' L_='log_pmos_Lmin' M_=1 $ $x=544 $y=1664 $w=128 $h=192
XMp10 nQi D N_7 vcc log_pmos W_='log_pmos_WS1*2' L_='log_pmos_Lmin' M_=1 $ $x=-224 $y=1440 $w=128 $h=192
XMp11 Qi nQi vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=992 $y=1664 $w=128 $h=192
XMp12 nQi Qi N_10 vcc log_pmos W_='log_pmos_WS1*4' L_='log_pmos_Lmin' M_=1 $ $x=608 $y=1440 $w=128 $h=192 $m
.ends

.subckt latch5_BETA clock D nclock nD nQ Q sub vcc vee S=1
* Library name: logic
* Cell name: latch5_BETA
* View name: schematic
* PORT=nD TYPE=In
* PORT=sub TYPE=Other
* PORT=clock TYPE=In
* PORT=nclock TYPE=In
* PORT=Q TYPE=Out
* PORT=vee TYPE=Other
* PORT=D TYPE=In
* PORT=nQ TYPE=Out
* PORT=vcc TYPE=Other

*
* (C) Caeleste
* Cell: latch5_BETA | Design: logic
* Designed by:  | Sat Feb 12 23:51:08 2022
* Cell version , rev. 2
Xstd_versioncheck 0 PAGEFRAME $ $x=4160 $y=-416 $w=2176 $h=192
XMn1 N_1 nclock vee sub log_nmos W_='log_nmos_WS1*S*2' L_='log_nmos_Lmin' M_=1 $ $x=4672 $y=0 $w=128 $h=192
XMn2 Q nQ N_1 sub log_nmos W_='log_nmos_WS1*S*2' L_='log_nmos_Lmin' M_=1 $ $x=4544 $y=288 $w=128 $h=192 $m
XMn3 nQ Q N_1 sub log_nmos W_='log_nmos_WS1*S*2' L_='log_nmos_Lmin' M_=1 $ $x=4928 $y=288 $w=128 $h=192
XMn5 N_4 clock vee sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=3520 $y=0 $w=128 $h=192
XMn6 nQ D N_4 sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=3328 $y=288 $w=128 $h=192
XMn7 Q nD N_4 sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=3840 $y=288 $w=128 $h=192 $m
XMp1 N_2 nclock vcc vcc log_pmos W_='log_pmos_WS1*S*2' L_='log_pmos_Lmin' M_=1 $ $x=3552 $y=896 $w=128 $h=192
XMp2 Q nD N_2 vcc log_pmos W_='log_pmos_WS1*S*2' L_='log_pmos_Lmin' M_=1 $ $x=3840 $y=608 $w=128 $h=192 $m
XMp3 N_3 clock vcc vcc log_pmos W_='log_pmos_WS1*S*4' L_='log_pmos_Lmin' M_=1 $ $x=4704 $y=896 $w=128 $h=192
XMp4 nQ D N_2 vcc log_pmos W_='log_pmos_WS1*S*2' L_='log_pmos_Lmin' M_=1 $ $x=3328 $y=608 $w=128 $h=192
XMp5 nQ Q N_3 vcc log_pmos W_='log_pmos_WS1*S*4' L_='log_pmos_Lmin' M_=1 $ $x=4928 $y=608 $w=128 $h=192
XMp6 Q nQ N_3 vcc log_pmos W_='log_pmos_WS1*S*4' L_='log_pmos_Lmin' M_=1 $ $x=4544 $y=608 $w=128 $h=192 $m
.ends

.subckt dff5_BETA clock D nclock nD nQ Q sub vcc vee S=1
* Library name: logic
* Cell name: dff5_BETA
* View name: schematic
* PORT=D TYPE=In
* PORT=Q TYPE=Out
* PORT=sub TYPE=Other
* PORT=nD TYPE=In
* PORT=vcc TYPE=Other
* PORT=nQ TYPE=Out
* PORT=vee TYPE=Other
* PORT=clock TYPE=In
* PORT=nclock TYPE=In

*
* (C) Caeleste
* Cell: dff5_BETA | Design: logic
* Designed by:  | Sun Feb 13 01:06:04 2022
* Cell version , rev. 3
Xstd_versioncheck 0 PAGEFRAME $ $x=576 $y=-928 $w=2176 $h=192
Xlatch9_1 nclock D clock nD N_2 N_1 sub vcc vee latch5_BETA S=S $ $x=256 $y=-304 $w=384 $h=352
Xlatch9_2 clock N_1 nclock N_2 nQ Q sub vcc vee latch5_BETA S=S $ $x=800 $y=-304 $w=384 $h=352
.ends

.subckt cleansync9 clean clock dirtysync nclean nclock ndirtysync sub vcc vee S=1
* Library name: logic
* Cell name: cleansync9
* View name: schematic
* PORT=clean TYPE=Out
* PORT=sub TYPE=Other
* PORT=clock TYPE=In
* PORT=vcc TYPE=Other
* PORT=nclean TYPE=Out
* PORT=vee TYPE=Other
* PORT=nclock TYPE=In
* PORT=dirtysync TYPE=In
* PORT=ndirtysync TYPE=In

*
* (C) Caeleste
* Cell: cleansync9 | Design: logic
* Designed by:  | Wed Jun  5 17:48:59 2024
* Cell version , rev. 6
Xstd_versioncheck 0 PAGEFRAME $ $x=576 $y=-416 $w=2176 $h=192
Xdff9_asr_1 nclean dirtysync vcc ndirtysync N_2 N_1 sub vcc vee dff9_asr $ $x=224 $y=560 $w=384 $h=352
Xdff9_diff_1 nclock N_1 clock N_2 nclean clean sub vcc vee dff5_BETA S=S $ $x=768 $y=528 $w=384 $h=352
.ends

.subckt inv in out sub vcc vee S=1
* Library name: logic
* Cell name: inv
* View name: schematic
* PORT=in TYPE=In
* PORT=vee TYPE=Other
* PORT=out TYPE=InOut
* PORT=sub TYPE=Other
* PORT=vcc TYPE=Other

* only cascode at n-side
* (C) Caeleste
* Cell: inv | Design: logic
* Designed by: Bart | Sat Feb 12 23:51:08 2022
* Cell version 1.0, rev. 45
Xstd_versioncheck 0 PAGEFRAME $ $x=64 $y=-416 $w=2176 $h=192
XMn1 out vcc N_1 sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=320 $y=320 $w=128 $h=192
XMn2 N_1 in vee sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=320 $y=96 $w=128 $h=192
XMp1 out in vcc vcc log_pmos W_='log_pmos_WS1*S' L_='log_pmos_Lmin' M_=1 $ $x=320 $y=608 $w=128 $h=192
.ends

.subckt sequencer1__b8 cdacclock<0> cdacclock<1> cdacclock<2> cdacclock<3> cdacclock<4> cdacclock<5> cdacclock<6> cdacclock<7> clockn clockp nlatch noffset nset<0> nset<1> nset<2> nset<3> nset<4> nset<5> nset<6> nset<7> sub swref swsig syncn syncp vcc vee
* Library name: sasc
* Cell name: sequencer1__b8
* View name: schematic
* PORT=swref TYPE=Out
* PORT=syncn TYPE=In
* PORT=syncp TYPE=In
* PORT=noffset TYPE=Out
* PORT=nset<4> TYPE=Out
* PORT=cdacclock<4> TYPE=Out
* PORT=nset<3> TYPE=Out
* PORT=cdacclock<3> TYPE=Out
* PORT=nset<2> TYPE=Out
* PORT=cdacclock<2> TYPE=Out
* PORT=cdacclock<7> TYPE=Out
* PORT=nset<1> TYPE=Out
* PORT=nset<6> TYPE=Out
* PORT=cdacclock<6> TYPE=Out
* PORT=nset<5> TYPE=Out
* PORT=cdacclock<5> TYPE=Out
* PORT=nlatch TYPE=Out
* PORT=nset<7> TYPE=Out
* PORT=cdacclock<1> TYPE=Out
* PORT=nset<0> TYPE=Out
* PORT=cdacclock<0> TYPE=Out
* PORT=swsig TYPE=Out
* PORT=sub TYPE=Other
* PORT=clockp TYPE=In
* PORT=clockn TYPE=In
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other

*
* (C) Caeleste
* Cell: sequencer1__b8 | Design: sasc
* Designed by: Bart Dierickx | Thu Jan 16 11:25:25 2025
* Cell version , rev. 4
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xcleansync9_1 cleanp clockn syncp cleann clockp syncn sub vcc vee cleansync9 S=1 $ $x=-2560 $y=912 $w=320 $h=352
Xdff9_1 clockp cleanp clockn N_1 s<0> sub vcc vee dff9 $ $x=-2080 $y=944 $w=320 $h=352
Xdff9_2 clockp s<0> clockn N_2 s<1> sub vcc vee dff9 $ $x=-1248 $y=944 $w=320 $h=352
Xdff9_3 clockp s<1> clockn N_3 s<2> sub vcc vee dff9 $ $x=-800 $y=944 $w=320 $h=352
Xinv_1 cleann nlatch sub vcc vee inv S=1 $ $x=-2176 $y=1536 $w=192 $h=128
Xinv_3 N_1 init sub vcc vee inv S=1 $ $x=-1664 $y=1184 $w=192 $h=128
Xsasc_sequencer1_unitcell_1 cdacclock<5> clockn clockp s<4> init nset<5> s<5> sub vcc vee sequencer1_unitcell $ $x=1088 $y=944 $w=320 $h=352
Xsasc_sequencer1_unitcell_2 cdacclock<4> clockn clockp s<5> init nset<4> N_5 sub vcc vee sequencer1_unitcell $ $x=1600 $y=944 $w=320 $h=352
Xsasc_sequencer1_unitcell_3 cdacclock<3> clockn clockp N_5 init nset<3> N_6 sub vcc vee sequencer1_unitcell $ $x=2112 $y=944 $w=320 $h=352
Xsasc_sequencer1_unitcell_4 cdacclock<2> clockn clockp N_6 init nset<2> N_7 sub vcc vee sequencer1_unitcell $ $x=2624 $y=944 $w=320 $h=352
Xsasc_sequencer1_unitcell_5 cdacclock<1> clockn clockp N_7 init nset<1> N_8 sub vcc vee sequencer1_unitcell $ $x=3136 $y=944 $w=320 $h=352
Xsasc_sequencer1_unitcell_6 cdacclock<0> clockn clockp N_8 init nset<0> N_9 sub vcc vee sequencer1_unitcell $ $x=3648 $y=944 $w=320 $h=352
Xsasc_sequencer1_unitcell_7 cdacclock<6> clockn clockp s<3> init nset<6> s<4> sub vcc vee sequencer1_unitcell $ $x=576 $y=944 $w=320 $h=352
Xsasc_sequencer1_unitcell_8 cdacclock<7> clockn clockp s<2> init nset<7> s<3> sub vcc vee sequencer1_unitcell $ $x=64 $y=944 $w=320 $h=352
Xsrff_1 swref N_4 s<1> init sub vcc vee srff $ $x=-1376 $y=1488 $w=192 $h=128
Xsrff_2 swsig noffset s<2> init sub vcc vee srff $ $x=-1088 $y=1488 $w=192 $h=128
.ends

.subckt inv_MHthreshold in out sub vcc vee S=1
* Library name: logic
* Cell name: inv_MHthreshold
* View name: schematic
* PORT=in TYPE=In
* PORT=vee TYPE=Other
* PORT=out TYPE=Out
* PORT=sub TYPE=Other
* PORT=vcc TYPE=Other

* only cascode at n-side
* (C) Caeleste
* Cell: inv_MHthreshold | Design: logic
* Designed by: Bart | Sat Feb 12 23:51:07 2022
* Cell version 1.0, rev. 45
Xstd_versioncheck 0 PAGEFRAME $ $x=64 $y=-416 $w=2176 $h=192
XMn1 out vcc N_1 sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin*2' M_=1 $ $x=320 $y=320 $w=128 $h=192
XMn2 N_1 in vee sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=320 $y=96 $w=128 $h=192
XMp1 out in vcc vcc log_pmos W_='log_pmos_WS1*2*S' L_='log_pmos_Lmin' M_=1 $ $x=320 $y=608 $w=128 $h=192
.ends

.subckt comparator_latch clock inn inp outn outp sub vcc vee S=4
* Library name: logic
* Cell name: comparator_latch
* View name: schematic
* PORT=outp TYPE=Out
* PORT=outn TYPE=Out
* PORT=vcc TYPE=Other
* PORT=inp TYPE=In
* PORT=vee TYPE=Other
* PORT=sub TYPE=Other
* PORT=inn TYPE=In
* PORT=clock TYPE=In

*
* (C) Caeleste
* Cell: comparator_latch | Design: logic
* Designed by: Bart | Tue Jan 14 16:29:27 2025
* Cell version 1.0, rev. 6
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
XMn1 N_3 inp N_1 sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=1248 $y=544 $w=128 $h=192 $m
XMn2 N_2 inn N_1 sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=800 $y=544 $w=128 $h=192
XMn3 N_1 clock vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1056 $y=352 $w=128 $h=192 $m
XMn4 outp outn N_2 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=864 $y=928 $w=128 $h=192 $m
XMn5 outn outp N_3 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1184 $y=928 $w=128 $h=192
XMp1 outn outp vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1184 $y=1184 $w=128 $h=192
XMp2 outp clock vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=448 $y=1184 $w=128 $h=192
XMp3 N_2 clock vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=256 $y=1184 $w=128 $h=192 $m
XMp4 outp outn vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=864 $y=1184 $w=128 $h=192 $m
XMp5 N_3 clock vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1792 $y=1184 $w=128 $h=192
XMp6 outn clock vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1600 $y=1184 $w=128 $h=192 $m
.ends

.subckt comparator1 clockn inn inp outn outp sub vcc vee zero S=4
* Library name: sasc
* Cell name: comparator1
* View name: schematic
* PORT=inp TYPE=In
* PORT=inn TYPE=In
* PORT=clockn TYPE=In
* PORT=sub TYPE=Other
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other
* PORT=zero TYPE=In
* PORT=outp TYPE=Out
* PORT=outn TYPE=Out

*
* (C) Caeleste
* Cell: comparator1 | Design: sasc
* Designed by: Bart | Tue Jan 14 17:09:17 2025
* Cell version 1.0, rev. 3
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xcomparator_latch_1 clockn inn inp compout_n compout_p sub vcc vee comparator_latch S=S $ $x=464 $y=640 $w=352 $h=320
Xinv_MHthreshold_1 compout_p outn sub vcc vee inv_MHthreshold S=S $ $x=736 $y=800 $w=192 $h=128
Xinv_MHthreshold_2 compout_n outp sub vcc vee inv_MHthreshold S=S $ $x=736 $y=480 $w=192 $h=128
.ends

.subckt switch_np_fast_core mid nmos pmos sub swN swP vcc vee S=1
* Library name: logic
* Cell name: switch_np_fast_core
* View name: schematic
* PORT=mid TYPE=InOut
* PORT=vcc TYPE=Other
* PORT=sub TYPE=Other
* PORT=nmos TYPE=InOut
* PORT=swN TYPE=In
* PORT=swP TYPE=In
* PORT=vee TYPE=Other
* PORT=pmos TYPE=InOut

*
* (C) Caeleste
* Cell: switch_np_fast_core | Design: logic
* Designed by: Nick | Thu Jan 26 10:34:52 2023
* Cell version 1.0, rev. 1
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
XMn3 nmos swN mid sub log_nmos W_='log_nmos_WS1*S' L_='log_nmos_Lmin' M_=1 $ $x=1088 $y=640 $w=192 $h=128 $r=270
XMp2 pmos swP mid vcc log_pmos W_='log_pmos_WS1*S*2' L_='log_pmos_Lmin' M_=1 $ $x=1088 $y=896 $w=192 $h=128 $r=90
.ends

.subckt switch_np_fast A B sub swN swP vcc vee S=1
* Library name: logic
* Cell name: switch_np_fast
* View name: schematic
* PORT=swP TYPE=In
* PORT=swN TYPE=In
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other
* PORT=sub TYPE=Other
* PORT=A TYPE=InOut
* PORT=B TYPE=InOut

*
* (C) Caeleste
* Cell: switch_np_fast | Design: logic
* Designed by: Nick | Thu Jan 26 16:22:06 2023
* Cell version 1.0, rev. 4
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xswitch_np_fast_core_1 B A A sub swN swP vcc vee switch_np_fast_core S=S $ $x=1056 $y=640 $w=384 $h=384
.ends

.subckt switch_fast A B select sub vcc vee Ssw=1
* Library name: logic
* Cell name: switch_fast
* View name: schematic
* PORT=sub TYPE=Other
* PORT=vee TYPE=Other
* PORT=vcc TYPE=Other
* PORT=A TYPE=InOut
* PORT=B TYPE=InOut
* PORT=select TYPE=In

*
* (C) Caeleste
* Cell: switch_fast | Design: logic
* Designed by: Nick | Sun Feb 13 01:06:04 2022
* Cell version 1.0, rev. 3
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xinv_1 select N_1 sub vcc vee inv S=1 $ $x=800 $y=672 $w=192 $h=128
Xswitch_np_1 A B sub select N_1 vcc vee switch_np_fast S=Ssw $ $x=1344 $y=512 $w=192 $h=192
.ends

.subckt sample_passive cnode_n cnode_p ntuner reference signal sub swref swsig vcc vee S=4
* Library name: sasc
* Cell name: sample_passive
* View name: schematic
* PORT=vcc TYPE=Other
* PORT=sub TYPE=Other
* PORT=vee TYPE=Other
* PORT=reference TYPE=In
* PORT=signal TYPE=In
* PORT=ntuner TYPE=In
* PORT=cnode_p TYPE=Out
* PORT=cnode_n TYPE=Out
* PORT=swsig TYPE=In
* PORT=swref TYPE=In

*
* (C) Caeleste
* Cell: sample_passive | Design: sasc
* Designed by: Bart | Wed Jan 15 16:12:37 2025
* Cell version 1.0, rev. 4
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xswitch_fast_3 signal cnode_p swsig sub vcc vee switch_fast Ssw='S/4' $ $x=1056 $y=992 $w=192 $h=192
Xswitch_fast_4 reference cnode_n swref sub vcc vee switch_fast Ssw='S/4' $ $x=1056 $y=480 $w=192 $h=192
.ends

.subckt and2nor2 A B C out sub vcc vee
* Library name: logic
* Cell name: and2nor2
* View name: schematic
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other
* PORT=C TYPE=In
* PORT=out TYPE=Out
* PORT=A TYPE=In
* PORT=B TYPE=In
* PORT=sub TYPE=Other

*
* (C) Caeleste
* Cell: and2nor2 | Design: logic
* Designed by: Nick | Sat Feb 12 23:51:10 2022
* Cell version 1.0, rev. 27
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
XMn1 out C N_1 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1088 $y=864 $w=128 $h=192
XMn2 N_1 B vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1088 $y=544 $w=128 $h=192
XMn3 N_2 A vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1440 $y=544 $w=128 $h=192 $m
XMn4 out vcc N_2 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1440 $y=864 $w=128 $h=192 $m
XMp1 N_3 C vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=992 $y=1568 $w=128 $h=192
XMp3 N_3 B vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1536 $y=1568 $w=128 $h=192 $m
XMp6 out A N_3 vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1312 $y=1248 $w=128 $h=192 $m
.ends

.subckt latch_th clock D Q Q_n sub vcc vee
* Library name: logic
* Cell name: latch_th
* View name: schematic
* PORT=Q TYPE=Out
* PORT=sub TYPE=Other
* PORT=clock TYPE=In
* PORT=vcc TYPE=Other
* PORT=Q_n TYPE=Out
* PORT=D TYPE=In
* PORT=vee TYPE=Other

* Transparent high
* (C) Caeleste
* Cell: latch_th | Design: logic
* Designed by: Nick | Tue Dec 27 12:52:41 2022
* Cell version 1.0, rev. 1
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xand2nor2_1 Q clock D Q_n sub vcc vee and2nor2 $ $x=1344 $y=752 $w=384 $h=160
Xand2nor2_2 Q_n clock N_1 Q sub vcc vee and2nor2 $ $x=1280 $y=496 $w=384 $h=160
Xinv_1 D N_1 sub vcc vee inv S=1 $ $x=896 $y=544 $w=192 $h=128
.ends

.subckt or2nand3 A B C D out sub vcc vee
* Library name: logic
* Cell name: or2nand3
* View name: schematic
* PORT=B TYPE=In
* PORT=sub TYPE=Other
* PORT=vcc TYPE=Other
* PORT=vee TYPE=Other
* PORT=A TYPE=In
* PORT=D TYPE=In
* PORT=C TYPE=In
* PORT=out TYPE=Out

*
* (C) Caeleste
* Cell: or2nand3 | Design: logic
* Designed by: Nick | Sat Feb 12 23:51:08 2022
* Cell version 1.0, rev. 26
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
XMn1 N_3 D N_1 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1120 $y=896 $w=128 $h=192
XMn2 N_1 B vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1024 $y=608 $w=128 $h=192
XMn3 N_1 C vee sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1312 $y=608 $w=128 $h=192 $m
XMn5 out A N_3 sub log_nmos W_='log_nmos_WS1' L_='log_nmos_Lmin' M_=1 $ $x=1120 $y=1120 $w=128 $h=192
XMp1 out A vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1024 $y=1344 $w=128 $h=192
XMp2 out B N_2 vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1408 $y=1344 $w=128 $h=192 $m
XMp3 N_2 C vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=1408 $y=1568 $w=128 $h=192 $m
XMp5 out D vcc vcc log_pmos W_='log_pmos_WS1' L_='log_pmos_Lmin' M_=1 $ $x=640 $y=1344 $w=128 $h=192
.ends

.subckt latch_nset clock D nD nQ nset Q sub vcc vee
* Library name: logic
* Cell name: latch_nset
* View name: schematic
* PORT=nset TYPE=In
* PORT=sub TYPE=Other
* PORT=vee TYPE=Other
* PORT=vcc TYPE=Other
* PORT=nQ TYPE=Out
* PORT=Q TYPE=Out
* PORT=clock TYPE=In
* PORT=D TYPE=In
* PORT=nD TYPE=In

*
* (C) Caeleste
* Cell: latch_nset | Design: logic
* Designed by: Bart | Sun Feb 25 18:00:55 2024
* Cell version 1.0, rev. 4
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xor2nand3_1 Q clock D nset nQ sub vcc vee or2nand3 $ $x=1152 $y=944 $w=384 $h=160
Xor2nand3_2 nQ clock nD nset Q sub vcc vee or2nand3 $ $x=1152 $y=688 $w=384 $h=160 $r=180 $m
.ends

.subckt cdac1_unitcell capn capp clock comp_n comp_p latched nlatch nset sub vcc vee
* Library name: sasc
* Cell name: cdac1_unitcell
* View name: schematic
* PORT=nlatch TYPE=In
* PORT=vee TYPE=Other
* PORT=sub TYPE=Other
* PORT=vcc TYPE=Other
* PORT=clock TYPE=In
* PORT=comp_p TYPE=In
* PORT=comp_n TYPE=In
* PORT=capn TYPE=Out
* PORT=latched TYPE=Out
* PORT=capp TYPE=Out
* PORT=nset TYPE=In

*
* (C) Caeleste
* Cell: cdac1_unitcell | Design: sasc
* Designed by: Bart Dierickx | Thu Jun 13 16:07:17 2024
* Cell version , rev. 1
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
Xlatch_nset_enable clock comp_n comp_p capn nset capp sub vcc vee latch_nset $ $x=480 $y=704 $w=320 $h=320
Xlatch_th nlatch capp latched N_1 sub vcc vee latch_th $ $x=480 $y=1248 $w=320 $h=320
.ends

.subckt cdac1__nb8_radix clock<0> clock<1> clock<2> clock<3> clock<4> clock<5> clock<6> clock<7> cnode_n cnode_p comp_n comp_p latched<0> latched<1> latched<2> latched<3> latched<4> latched<5> latched<6> latched<7> nlatch noffset nset<0> nset<1> nset<2> nset<3> nset<4> nset<5> nset<6> nset<7> rtap<0> rtap<1> rtap<2> sub vcc vee cap=100f radix=2
* Library name: sasc
* Cell name: cdac1__nb8_radix
* View name: schematic
* PORT=latched<0> TYPE=Out
* PORT=nset<0> TYPE=In
* PORT=clock<0> TYPE=In
* PORT=nset<7> TYPE=In
* PORT=nset<6> TYPE=In
* PORT=nset<5> TYPE=In
* PORT=nset<4> TYPE=In
* PORT=rtap<0> TYPE=In
* PORT=latched<7> TYPE=Out
* PORT=latched<6> TYPE=Out
* PORT=latched<5> TYPE=Out
* PORT=latched<4> TYPE=Out
* PORT=latched<3> TYPE=Out
* PORT=latched<2> TYPE=Out
* PORT=latched<1> TYPE=Out
* PORT=nset<3> TYPE=In
* PORT=nset<2> TYPE=In
* PORT=nset<1> TYPE=In
* PORT=clock<7> TYPE=In
* PORT=clock<6> TYPE=In
* PORT=clock<5> TYPE=In
* PORT=clock<4> TYPE=In
* PORT=clock<3> TYPE=In
* PORT=clock<1> TYPE=In
* PORT=noffset TYPE=In
* PORT=rtap<2> TYPE=In
* PORT=rtap<1> TYPE=In
* PORT=vee TYPE=Other
* PORT=cnode_n TYPE=InOut
* PORT=cnode_p TYPE=InOut
* PORT=sub TYPE=Other
* PORT=nlatch TYPE=In
* PORT=vcc TYPE=Other
* PORT=comp_p TYPE=In
* PORT=comp_n TYPE=In
* PORT=clock<2> TYPE=In

*
* (C) Caeleste
* Cell: cdac1__nb8_radix | Design: sasc
* Designed by: Bart Dierickx | Thu Jan 16 13:46:18 2025
* Cell version , rev. 2
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
CCapacitor_3 cnode_p vee cap/4 $ $x=-256 $y=1344 $w=64 $h=192
CCapacitor_4 offset cnode_n cap/4 $ $x=-256 $y=1024 $w=64 $h=192
CCapacitor_19 cnode_p vee cap/2 $ $x=-640 $y=1344 $w=64 $h=192
CCapacitor_20 vee cnode_n cap/2 $ $x=-640 $y=1024 $w=64 $h=192
CCapacitor_21 cnode_p N_2 cap/2/radix^5 $ $x=3040 $y=1344 $w=64 $h=192
CCapacitor_22 N_1 cnode_n cap/2/radix^5 $ $x=3040 $y=1024 $w=64 $h=192
CCapacitor_23 cnode_p N_11 cap/2 $ $x=416 $y=1344 $w=64 $h=192
CCapacitor_24 N_4 cnode_n cap/2 $ $x=416 $y=1024 $w=64 $h=192
CCapacitor_25 cnode_p N_10 cap/2/radix $ $x=992 $y=1344 $w=64 $h=192
CCapacitor_26 N_3 cnode_n cap/2/radix $ $x=992 $y=1024 $w=64 $h=192
CCapacitor_27 cnode_p N_12 cap/2/radix^2 $ $x=1504 $y=1344 $w=64 $h=192
CCapacitor_28 N_5 cnode_n cap/2/radix^2 $ $x=1504 $y=1024 $w=64 $h=192
CCapacitor_29 cnode_p N_13 cap/2/radix^3 $ $x=2016 $y=1344 $w=64 $h=192
CCapacitor_30 N_6 cnode_n cap/2/radix^3 $ $x=2016 $y=1024 $w=64 $h=192
CCapacitor_31 cnode_p N_14 cap/2/radix^4 $ $x=2528 $y=1344 $w=64 $h=192
CCapacitor_32 N_7 cnode_n cap/2/radix^4 $ $x=2528 $y=1024 $w=64 $h=192
CCapacitor_33 cnode_p N_15 cap/2/radix^6 $ $x=3552 $y=1344 $w=64 $h=192
CCapacitor_34 N_8 cnode_n cap/2/radix^6 $ $x=3552 $y=1024 $w=64 $h=192
CCapacitor_35 cnode_p N_16 cap/2/radix^7 $ $x=4064 $y=1344 $w=64 $h=192
CCapacitor_36 N_9 cnode_n cap/2/radix^7 $ $x=4064 $y=1024 $w=64 $h=192
Xinv_2 noffset offset sub vcc vee inv S=1 $ $x=-256 $y=704 $w=192 $h=128
Xsasc_cdacunitcell_1_9 N_1 N_2 clock<2> comp_n comp_p latched<2> nlatch nset<2> sub vcc vee cdac1_unitcell $ $x=2784 $y=1184 $w=320 $h=320
Xsasc_cdacunitcell_1_10 N_3 N_10 clock<6> comp_n comp_p latched<6> nlatch nset<6> sub vcc vee cdac1_unitcell $ $x=736 $y=1184 $w=320 $h=320
Xsasc_cdacunitcell_1_11 N_4 N_11 clock<7> comp_n comp_p latched<7> nlatch nset<7> sub vcc vee cdac1_unitcell $ $x=160 $y=1184 $w=320 $h=320
Xsasc_cdacunitcell_1_12 N_5 N_12 clock<5> comp_n comp_p latched<5> nlatch nset<5> sub vcc vee cdac1_unitcell $ $x=1248 $y=1184 $w=320 $h=320
Xsasc_cdacunitcell_1_13 N_6 N_13 clock<4> comp_n comp_p latched<4> nlatch nset<4> sub vcc vee cdac1_unitcell $ $x=1760 $y=1184 $w=320 $h=320
Xsasc_cdacunitcell_1_14 N_7 N_14 clock<3> comp_n comp_p latched<3> nlatch nset<3> sub vcc vee cdac1_unitcell $ $x=2272 $y=1184 $w=320 $h=320
Xsasc_cdacunitcell_1_15 N_8 N_15 clock<1> comp_n comp_p latched<1> nlatch nset<1> sub vcc vee cdac1_unitcell $ $x=3296 $y=1184 $w=320 $h=320
Xsasc_cdacunitcell_1_16 N_9 N_16 clock<0> comp_n comp_p latched<0> nlatch nset<0> sub vcc vee cdac1_unitcell $ $x=3808 $y=1184 $w=320 $h=320
.ends


********* Simulation Settings - Parameters *********
.param simtime = 2000u
.param convtime = 0.1u
.param rladder = 100k
.param radix = 1.80
.param cap = 100f
********* Simulation Settings - Options *********
.option csv = 2
***** Top Level *****
*
* (C) Caeleste
* Cell: SB_saradc8_radixN | Design: sasc
* Designed by: Bart Dierickx | Fri Jan 17 00:03:00 2025
* Cell version , rev. 42
Xstd_versioncheck 0 PAGEFRAME $ $x=1088 $y=96 $w=2176 $h=192
RResistor_1 vcc ntuner 100k TC=0.0, 0.0 $ $x=-1120 $y=1760 $w=24 $h=192
Rshort_1 gnd sub Rshort R=1m $ $x=832 $y=480 $w=24 $h=192 $r=180
Rshort_13 gnd vee Rshort R=1m $ $x=1024 $y=480 $w=24 $h=192 $r=180
vanalog vcca gnd log_VCC $ $x=416 $y=480 $w=320 $h=192
vcomparator vccc gnd log_VCC $ $x=-992 $y=480 $w=320 $h=192
vinput vcci gnd log_VCC $ $x=-288 $y=480 $w=320 $h=192
vresistor vccr gnd log_VCC $ $x=-640 $y=480 $w=320 $h=192
vsequencer vcc gnd log_VCC $ $x=64 $y=480 $w=320 $h=192
vSource_v_dc_2 reference gnd log_VCC $ $x=-704 $y=1536 $w=320 $h=192
vSource_v_pwl_1 signal gnd pwl(0 log_VCC simtime 0.5*log_VCC) $ $x=-704 $y=1888 $w=128 $h=192
Xcdac1__nb8_radix_1 clo<0> clo<1> clo<2> clo<3> clo<4> clo<5> clo<6> clo<7> cnode3n cnode3p comz_n comz_p data<0> data<1> data<2> data<3> data<4> data<5> data<6> data<7> nlatch noffset3 nset<0> nset<1> nset<2> nset<3> nset<4> nset<5> nset<6> nset<7> Unknown_Pin_rtap<0>_29 Unknown_Pin_rtap<1>_29 Unknown_Pin_rtap<2>_29 sub vcca vee cdac1__nb8_radix cap=cap radix=radix $ $x=1056 $y=1727 $w=640 $h=321
Xlog_nmos_1 ntuner ntuner vee sub log_nmos W_='log_Wmin' L_='log_Lntune' M_=1 $ $x=-1152 $y=1568 $w=128 $h=192
Xsasc_comparator_1_2 clockn cnode3n cnode3p comz_n comz_p sub vccc vee N_1 comparator1 S=4 $ $x=1936 $y=1728 $w=352 $h=320
Xsasc_rdivider1_1 rtap<0> rtap<1> rtap<2> sub vccr vee rdivider1__b3 rladder=100k $ $x=736 $y=2240 $w=320 $h=320
Xsasc_sample1_1 cnode3n cnode3p ntuner reference signal sub swref swsig vcci vee sample_passive S=4 $ $x=288 $y=1728 $w=320 $h=320
Xsasc_sequencer1_8steps_1 clo<0> clo<1> clo<2> clo<3> clo<4> clo<5> clo<6> clo<7> clockn clockp nlatch noffset3 nset<0> nset<1> nset<2> nset<3> nset<4> nset<5> nset<6> nset<7> sub swref swsig syncn syncp vcc vee sequencer1__b8 $ $x=1056 $y=1216 $w=640 $h=320
XSource_v_pulse_differential_1 clockn clockp gnd Source_v_pulse_differential del=0 high=log_VCC low=0 period='convtime/12' risefall=100p width='convtime/24' $ $x=2304 $y=544 $w=128 $h=192
XSource_v_pulse_differential_2 syncn syncp gnd Source_v_pulse_differential del='-convtime/48' high=log_VCC low=0 period=convtime risefall=100p width='convtime/24' $ $x=1536 $y=544 $w=128 $h=192

********* Simulation Settings - Analysis Section *********
.TRAN/POWERUP 0.1n simtime START=0
.OPTION prtdel=0.1n

********* Simulation Settings - Signals to Save *********
.plot v(signal)
.plot v(reference)
.plot v(cnode3p)
.plot v(cnode3n)
.plot v(comz_p)
.plot v(comz_n)
.plot v(syncp)
.print v(clockp)
.print v(data<0>)
.print v(data<1>)
.print v(data<2>)
.print v(data<3>)
.print v(data<4>)
.print v(data<5>)
.print v(data<6>)
.print v(data<7>)

.end
