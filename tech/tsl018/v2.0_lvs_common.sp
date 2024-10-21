
*#this file should contain the common part of v2.0_lvs_***
*************************************
*
* (c) Caeleste
* 20110509 Nick Witvrouwen creation
* 20151026 Koen Liekens created this _lvs using the v2.0_common
* 20151113 Bart Dierickx renamed v2.0_lvs_MIM as C-param is MIM
* 20170110 Koen replaced s:/ into /caeleste/, Calibre only runs on Linux machine
*               nhv -> NH , phv -> PH
* 20170118 Koen added pj parameter for std_ndio and std_pdio
* 20170118 Koen added NHW1 device as it is used as lowVt in pixel (and column load)
* 20170119 Koen CMIM_HC_LVS -> cmim_hc
* 20170120 Qiang modified std_rpoly subckt definition.
* 20170131 Koen fixed something strange with the bondpad
* 20170918 Wei updated file with to match hacked lvs runset
* 20171017 Ajit added wrapper for rnmpoly2t
* 20171019 Wei revert previous change of rnmpoly2t to original
* 20180503 Koen fixed inconsequent case use of parameters (l,w,m) -> (W,L,M) in nwcaph2t and nwcap2t
* 20180503 Koen fixed wrong number of ports in std_Cnwnmos (sub added)
* 20180614 Koen added std_TG in lvs deck
* 20181024 Gaozhan change std_nmos_lowVth model definition to nhv since for LVS, this transistor will be recognized as normal transistor 
* 20181107 Koen renamed nhv and phv into NH and PH because that is the way they are called in Calibre decks 
*          (like I did in 2017 already, but somebody apparently changed it back without saying so)
*         for lvt there will probably pop up an issue, I'll solve it when it is encountered, but 
*         I do not agree that lvt transistors are extracted as normal ones, you could start filling in your NCR document right away.
* 20181108 Koen rename again NH, PH into nhv, phv because otherwise the extracted netlists cannot be pex'ed
* 20181126 Koen Added empty stubs for LTB autogen not to crash
* 20181126 Koen log_Cnwnmos has 3 terminals in schematic
* 20210323 Koen default values for parameters should be numbers, not undefined variables W=0 L=0 iso  W='W_' L='L_' for nwcaph2t and nwcap2t
* 20210806 Rishabh temporarily used nhv/phv
* 20220216 Koen removed fancy calculation in log_nmos_lowVth and log_pmos_lowVth because of LVS syntax error: as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)' into as=AS_ ps=PS_ ad=AD_ pd=PD_
* 20220304 Koen removed AS_=0 PS_=0 AD_=0 PD_=0 from subckt def for log_nmos_lowVth and log_pmos_lowVth, they cause errors in LayoutToolbox because they are never filled in by the schematic symbol
* 20220404 Sampsa changed log_n/pmos_lowVt model back to n/p18lvt
* 20220518 Gaozhan added added hires poly resistor, 10kohm/sq
* 20221010 Sven added deep nwell devices
* 20221014 Arne added nwell sub diode
* 20230201 Bilgesu added std_nmos_native and log_nmos_native for monitorset11 LVS
* 20230703 Koen add cmim_uhd and cmim_uhdstk
* 20230705 Bilgesu added MN for monitorset11 LVS
* 20230808 Koen add m for cmim_uhd and cmim_uhdstk
* 20231010 Koen rename subckt cmim_uhd -> uhd_CMiM and cmim_uhdstk -> uhd_stk_CMiM (model name stays as is)
*************************************

*.model STDCELL_VERSION_1_0 r
*Added to avoid auto-declaration warning during lvs - Ankur
.model NH nmos
.model PH pmos
*add as Tower decks do not recognize this in LVS
********************************************************

.include "/caeleste/technologies/tsl018/v2.0/v2.0_common.sp"
*.include "/caeleste/technologies/tsl018/models/hspice/R_extraction/lvs_schematic.txt"

*.include "/caeleste/technologies/tsl018/spice_models/R_extraction/lvs_layout.txt"


********************************************************
* device definition for LVS
********************************************************

.subckt std_nmos D G S B W_=0 L_=0 M_=1
Mstd_nmos D G S B nhv W=W_ L=L_ M=M_
.ends

.subckt std_pmos D G S B W_=0 L_=0 M_=1
Mstd_pmos D G S B phv W=W_ L=L_ M=M_
.ends

*20210728gc 
*low Vth log nMOSFET (no radhard variant)
*20210806 temporarily used nhv
* 20220404 Sampsa changed back to n18lvt
*.subckt log_nmos_lowVth D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
.subckt log_nmos_lowVth D G S B W_=0 L_=0 M_=1
.param AS_=0
.param PS_=0
.param AD_=0
.param PD_=0
Mlog_nmos_lowVth D G S B n18lvt W=W_ L=L_ M=M_ as=AS_ ps=PS_ ad=AD_ pd=PD_
.ends

*20210728gc 
*low Vth log pMOSFET (no radhard variant)
*20210806 temporarily used phv
* 20220404 Sampsa changed back to p18lvt
*.subckt log_pmos_lowVth D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
.subckt log_pmos_lowVth D G S B W_=0 L_=0 M_=1
.param AS_=0
.param PS_=0
.param AD_=0
.param PD_=0
Mlog_pmos_lowVth D G S B p18lvt W=W_ L=L_ M=M_ as=AS_ ps=PS_ ad=AD_ pd=PD_
.ends

**this should be n33mvt
.subckt std_nmos_lowVth D G S B W_=0 L_=0 M_=1
*Mstd_nmos D G S B NHW1 W=W_ L=L_ M=M_
Mstd_nmos D G S B nhv W=W_ L=L_ M=M_
.ends

*this part is divided into seperate header files
*.subckt C_param top bottom sub Cmodel=0 W_=0 L_=0 M_=1
*.if(Cmodel == 1)
*	*NIC capacitor
*	Xstd_Cnpod top bottom sub std_Cnpod W_=W_ L_=L_ M_=M_
*.elseif(Cmodel == 2)
*	*accumulation capacitor
*	Xstd_Cnwnmos top bottom std_Cnwnmos W_=W_ L_=L_ M_=M_
*.else
	*MiM capacitor
	*Xstd_CMiM top bottom sub std_CMiM W_=W_ L_=L_ M_=M_
*.endif
*.ends

*MIM capacitor
.subckt cmim_hc A B l=4u w=4u m=1
.param high_c_mim_a=1.7e-3   
.param high_c_mim_f=0.12e-9  

C1 A B cmim_hc c=high_c_mim_a*(l*w)+high_c_mim_f*(l+l+w+w) l=l w=w
.ends

.subckt std_CMiM top bottom sub W_=0 L_=0 M_=1
Xcmim_hc top bottom cmim_hc w=W_ l=L_ m=M_
*remark that the tower model ignores the bottom plate, so we add it here for all techs:
*Cpar bottom sub  '1.7e-3*L_*W_*M_/20'
.ends

* 20230703 Koen add cmim_uhd and cmim_uhdstk
* 20230808 Koen add m for cmim_uhd and cmim_uhdstk
* 20231010 Koen rename subckt cmim_uhd -> uhd_CMiM and cmim_uhdstk -> uhd_stk_CMiM (model name stays as is)
.subckt uhd_CMiM A B L_=4u M_=1 W_=4u
.param uhd_c_mim_a=2.71e-3   
.param uhd_c_mim_f=0.26e-9  
C1 A B cmim_uhd c=uhd_c_mim_a*(L_*W_)+uhd_c_mim_f*(L_+L_+W_+W_) l=L_ w=W_ m=M_
.ends

.subckt uhd_stk_CMiM A B L_=4u M_=1 W_=4u
.param uhdstk_c_mim_a=5.429e-3
.param uhdstk_c_mim_f=0.53e-9
C1 A B cmim_uhdstk c=uhdstk_c_mim_a*(L_*W_)+uhdstk_c_mim_f*(L_+L_+W_+W_) l=L_ w=W_ m=M_
.ends



*accumulation capacitor
.subckt nwcaph2t VP VM W=0 L=0 M=1
C1 VP VM CH W=W L=L M=M
.ends

.subckt nwcap2t VP VM W=0 L=0 M=1
C1 VP VM CL W=W L=L M=M
.ends

.subckt std_Cnwnmos VP VM sub W_=0 L_=0 M_=1
Xstd_Cnwnmos VP VM nwcaph2t W=W_ L=L_ M=M_
.ends

*20171026 wei added device log_Cnwnmos
* 20181126 Koen log_Cnwnmos has 3 terminals in schematic
*.subckt log_Cnwnmos VP VM W_=0 L_=0 M_=1
.subckt log_Cnwnmos VP VM sub W_=0 L_=0 M_=1
Xlog_Cnwnmos VP VM nwcap2t W=W_ L=L_ M=M_
.ends

*NIC (POD) capacitor
.subckt std_Cnpod top bottom sub W_=0 L_=0 M_=1
Ccnpod top bottom ncapimp332t w=W_ l=L_ m=M_
*remark that the tower model ignores the bottom plate, so we add it here for all tech, as 1/10:
*Cpar bottom sub  '5e-3*L_*W_*M_/10'	
.ends


.subckt std_nmos_nVth D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
Mstd_nmos_nVth D G S B nathv  W=W_ L=L_ M=M_ AS=AS_ PS=PS_ AD=AD_ PD=PD_
.ends
		
.subckt std_pdio p n W_=0 L_=0 M_=1
Dstd_pdio p n dph Area=L_*W_ pj=2*(L_+W_) M=M_
.ends

.subckt std_ndio p n W_=0 L_=0 M_=1
Dstd_ndio p n dnh Area=L_*W_ pj=2*(L_+W_) M=M_
.ends

.subckt log_pdio p n W_=0 L_=0 M_=1
Dlog_pdio p n dp18 Area=L_*W_  pj=(L_+W_)*2 M=M_
.ends

.subckt log_ndio p n W_=0 L_=0 M_=1
Dlog_ndio p n dn18 Area=L_*W_  pj=(L_+W_)*2 M=M_ 
.ends

* poly resistor
* we use preferentially an n-doped non-salicided poly resistor (not the HIGHres!!!)
.subckt std_rpoly a b W_=0 L_=0  M_=1
*Xrstd_poly a b rnmpoly2t L=L_ W=W_  M=M_
Rrstd_poly a b rnmpoly2t L=L_ W=W_  M=M_
.ends
*.subckt rnmpoly2t a b
*.ends

*** 20220228 Sampsa added hires poly resistor, 2kohm/sq
* new version: [20201230ba]
.subckt rpoly_hires a b W_=0 L_=0  M_=1
Rrhires_poly a b mr22t L=L_ W=W_  M=M_
.ends

*** 20220518 Gaozhan added hires poly resistor, 10kohm/sq
* new version: [20201230ba]
.subckt rpoly_hires10k a b sub W_=0 L_=0  M_=1
Rrstd_poly a b mr33t L=L_ W=W_  M=M_
.ends

* nwell resistor
.subckt std_rnwell a b W_=0 L_=0 M_=1
Xrstd_nwell a b rnwellsti2t L=L_ W=W_ M=M_
.ends

* LOGIC (low VCC) MOSFET models 
.subckt log_nmos D G S B W_=0 L_=0 M_=1
Mlog_nmos D G S B n18 W=W_ L=L_ M=M_
.ends

.subckt log_pmos D G S B W_=0 L_=0 M_=1
Mlog_pmos D G S B p18 W=W_ L=L_ M=M_
.ends

* 20181126 Koen Added empty stubs for LTB autogen not to crash
.subckt poly_diode p n
Cpoly p n Cparasitic C=15f
.ends
.subckt PPD ppd sub
***
.ends
.subckt depletion A B sub  W_=5u L_=5u Vdep=0.7 
***
.ends

*** <--- std_TG

** from simulation files
** * qualitative TG model
** .subckt std_TG PPD TG FD SUB W_=2u L_=0.5u 
** *0.7 is the Vth, 0.026 is the thermal voltage=kT/q, 4e-14 is the diode saturation current
** gt_gate FD PPD  
**       + cur='v(FD,PPD) * min(max((-1e-5)*v(PPD)+1e-5,0), (4e-14)*exp((v(TG,PPD)-0.7)/0.026))'
** *typical values in the order of 0.1 to 1 fF
** captgfd TG FD Ctgfd 
** .ends

** from xfab:
* qualitative TG model
.subckt std_TG fd ppd sub tg  W_=2u L_=0.6u Vdep=0.7 Ctgfd=0.1f
X1 fd tg diode sub LDDN W_=2e-06 L_=6e-07 
.ends 

.subckt LDDN D G S B W=0 L=0 M=1
.ends

*** ---> std_TG

.model bondpadmodel r
.subckt bondpad in out
rpad in out bondpadmodel r = 1m
.ends

.model Rshort r
.model Cparasitic c

*****************************************************************************
* parameters in stdcell_generic and logic_generic                                                  *
*****************************************************************************
* moved to v2.0_common

**** Deep n-well devices ***
.subckt deepnwell_sub_diode p n W_=0 L_=0 M_=1
	DDWNPS18 p n DDWNPS18 AREA=W_*L_ PJ=2*(W_+L_) M=M_
.ends

.subckt deepnwell_pwell_diode p n W_=0 L_=0 M_=1
	DDWNPW18 p n DDWNPW18 AREA=W_*L_ PJ=2*(W_+L_) M=M_
.ends

.subckt nwell_sub_diode p n W_=0 L_=0 M_=1
	DNWELL33 p n DNWELL33 AREA=W_*L_ PJ=2*(W_+L_) M=M_
.ends
****

*************20230201BS for monitorset11****************
.subckt std_nmos_native D G S B W_=0 L_=0 M_=1 
Mstd_nmos_nVth D G S B NB W=W_ L=L_ M=M_ 
.ends

.subckt log_nmos_native D G S B W_=0 L_=0 M_=1 
Mstd_nmos_nVth D G S B NA W=W_ L=L_ M=M_ 
.ends

.subckt MN G S D B
.ends
********************************************************
