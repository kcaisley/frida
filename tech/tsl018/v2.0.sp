*******************************************************************************
* (c) Caeleste
* TOWER stdcell parameter file
* serves as template for all other technologies
* for use of these parameters see S:\projects\internal projects\schematic\generic\v1.0\stdcell_generic
*
* document history
* 20110509 Nick Witvrouwen creation
* 20120319 Nick Witvrouwen Added std_rnwell model
* 20120219 cleaned up std_Lmin_balanced =0.35u and std_Wmin = 0.3u -Bart 
* 20120606 Nick Witvrouwen  added dummy bond pad model to match updated IO library
* 20121205 Peng add M_=1 and M=M to all subckt
* 20130117 Bart added std_LRpolythin100k and std_WRpolythin100k 
* 20130524 BartD added 2 parameters for the RDAC, as inspired by XFAB layout
* 20130524 PengG standarized the mim cap with W_ L_ and M_
* 20131129 Qiang added the sub terminal to std_cMiM
* 20131209 BartD introduced std_pmos_Ldesignrule etc
* 20131209 BartD cleaned up MIM parameters for stdcells and defined 100fF and 1pF
* 20131211 BartD parameters for logic cells
* 20140130 BartD corrected W_S16 from 5.0 to 4.8�m
* 20140212 BartD clean up
* 20140223 BartD corrected parameters for poly resistors
* 20140410 BartD added parameters ro the rpoly_1meg
* 20140422 BartD created V2.0 and updated many parameters
* 20140512 Gaozhan added NIC capacitor
* 20140821 BartD added model for std_TG
* 20140924 Wei change std_LRdac from 10 to 8um and std_Rdac_Runitcell from 3k to 3.2k
* 20141217 Gaozhan delete v2.0_MC.sp and rh_v2.0.sp, integrate them within v2.0.sp
* 20141219 Gaozhan Corrected this file for LVS
* 20150207 BartD added factor M_ in the extra parasitic capacitance of radhard MOSFETs
* 20150208 BartD added 1/20 parasitic in the MIM capacitor and 1/10 in the POD capacitor
* 20150213 Bart/Peng added low Vth nmosfet device
* 20150213 Koen added .if (lvs) around capacitors to comment out parasitic caps
* 20150220 Koen added .if (lvs) around low Vth nmosfet to remap to std_nmos
* 20150414 Bart/gaozhan added Ctgfd in TG model
* 20150420 Qiang/Bart/Peng updated the name of std_nmos_lowVth from std_nmos_LVT to std_nmos_lowVth
* 20150501 Bart changed L and W for log_cells; added rbalanced PMOS  W
* 20150504 PGao Add nathv (Native Mosfets)  
* 20150702 BD tuners for log option
* 20150803 BD ESD protection revised
* 20150820 Wei added C_param cell
* 20150827 Wei added model for Rshort, Cparasitic
* 20150928 Gaozhan corrected TG model
* 20151028 Gaozhan all parameters are moved to v2.0_common
* 20160308 Wei+Bart devices LOG diodes, also log_nwnmos
* 20161027 Gaozhan Bart Peri add parasitic capacitor to the bottom plate of acccap
* 20170725 Wei modified log transistor to have MC option
* 20180323 Arne modified line 210. placed the comment "typical values in the order of 0.1 to 1fF" on a different line
* 20182327ba added depletion voltage test structure and removed M_ from std_TG
* 20180713 Ahmed added rpoly1Meg model
* 20180919 Gaozhan updated TG model
* 20190130 Bart added Rleakage model
* 20191119 Bart made std_Crg* symmetric
* 20200711 Bart added radhard parasitic in nMOS logic transistor
* 20200902 Gaozhan PPD model is added 
* 20201230 bart small updates related to C_modelWL
* 20210321 bart corrected Cmodel_WL malfunction at least for TLS018
* 20210331 bart added NMOS option in Cmodel_WL
* 20210728 Gaozhan added low Vth nMOS & pMOS
* 20210803 Arne Added the area/perimeter of source/drain estimations to the models. See https://caeleste.atlassian.net/browse/SCIB-176.
* 20210827 Gaozhan correct 'xMstd_nmos' to 'Mstd_nmos' for mx devices
* 20210906 Arne changed 'Mstd_nmos' to 'xMstd_nmos' only for Monte Carlo related models because those are defined in tsl018_mat directly as .subckt and not as .model
* 20211021 Gaozhan remove 'if(mc)' definition, it is unnecessary
* 20211228 Rishabh removed std_Crhgs and Crhgd parameters as they are defined in v2.0_common file and are redundant here
* 20220228 Sampsa added hires poly resistor, 2kohm/sq
* 20220310 Sampsa added a model for high-K capacitor. Capacitance value is based on S:\technologies\tsl018\Tower documents\high-k capacitors\SuperHighOffering_Jan20.pdf
* 20220518 Gaozhan added added hires poly resistor, 10kohm/sq
* 20220615 Arne added quantitative poly_diode model
* 20220720 Sven & Bart added log_only option
* 20221010 Sven added deepnwell_sub_diode
* 20220109 Bilgesu Sezgin fixed .subckt depletion definition (FD PPD inside cell definition is changed to B A)
* 20230413 Gaozhan add new section for in-pixel transistors (not ready for use yet)
* 20230414 Bart addition of parametrizable MOSFET model (not ready for use yet)
* 20230703 Koen added CMIMH (cmim_uhd) and CMIMHS (cmim_uhdstk)

************************************************************
* label used by Nick to ensure validity of the file
.model STDCELL_VERSION_1_0 r

*******************************************************
* this libary contains the technology invariant devices 
* as in schematic library devices 
**************************************************************

****************************************************************
* all technology dependent parameters are included from following file 
.include "v2.0_common.sp"
****************************************************************

*STD (vdd-vss)  mosfets  

.subckt std_nmos D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	.if (log_only)
		* In case all 3.3V transistors layouts are implanted as 1.8V transistors
		Mlog_nmos D G S B n18 W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
	.else
		Mstd_nmos D G S B nhv W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
	.endif
	.if (rh)
		Cp1 D G 'std_Crhgd*M_'
		Cp2 G S 'std_Crhgs*M_'
	.endif
.ends
	
.subckt std_pmos D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	.if (log_only)
		* In case all 3.3V transistors layouts are implanted as 1.8V transistors
		Mlog_pmos D G S B p18 W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
	.else
		Mstd_pmos D G S B phv W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
	.endif
.ends

* LOGIC (vcc-vee) MOSFET models 
.subckt log_nmos D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	Mlog_nmos D G S B n18 W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
	.if (rh)
		Cp1 D G 'log_Crhgd*M_'
		Cp2 G S 'log_Crhgs*M_'
	.endif
.ends

.subckt log_pmos D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	Mlog_pmos D G S B p18 W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
.ends


*20210728gc 
*low Vth log nMOSFET (no radhard variant)
.subckt log_nmos_lowVth D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	Mlog_nmos_lowVth D G S B n18lvt W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
.ends

*20210728gc 
*low Vth log pMOSFET (no radhard variant)
.subckt log_pmos_lowVth D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	Mlog_pmos_lowVth D G S B p18lvt W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
.ends


*low Vth nMOSFET (no radhard variant yet)
.subckt std_nmos_lowVth D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	Mstd_nmos_lowVth D G S B n33mvt W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
.ends

*native Vth nMOSFET  (no radhard variant yet) 20201230ba 
.subckt std_nmos_native D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0
	Mstd_nmos_native D G S B nathv  W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
.ends


******************************* IN-PIXEL TRANSISTORS ************************ 
******************************* NOT READY FOR USE YET ******************************* 
* 20230413 Gaozhan add new section for in-pixel transistors  ///  will becode obsolete if nmosfet_model will work

.subckt pix_nmos D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0 MOStype=1
	.if(MOStype == 1)
		Mpixel_nmos D G S B n33ishvt W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
	.elseif(MOStype == 2)
		Mpixel_nmos D G S B n33ismvt W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'	
	.else
		Mpixel_nmos D G S B n33isulvt W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.6e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.6e-6)' ad='(AD_>0)?AD_:(0.6e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.6e-6)'
	.endif
	.if (rh)
		Cp1 D G 'std_Crhgd*M_'
		Cp2 G S 'std_Crhgs*M_'
	.endif
.ends


* generic NMOSFET with parametrizable modelname 20230414ba created
* possible models: 
*			nhv			normal 3v3 nmosfet (not in pixel)
*			n33mvt		std nmosdet medium vth wihc we use as low Vth
*			nathv			std native mosfet
*			n33ishvt		in pixel normal Vth
*			n33ismvt		in pixel medium vth
*			n33isulvt	in pixel ultra low vth
*			n5v			5Volt nmosfet
*			n18			log nmosfet
*			n18lvt		log nmosfet low Vth
*			...
.subckt nmosfet_model D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0 model=0
	Mnmosfet_model D G S B model W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.5e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.5e-6)' ad='(AD_>0)?AD_:(0.5e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.5e-6)'
.ends
* 20230414ba creation of generic PMOSFET with parametrizable modelname
*.subckt pmosfet_model D G S B W_=0 L_=0 M_=1 AS_=0 PS_=0 AD_=0 PD_=0 model
*	Mpmosfet_model D G S B model W=W_ L=L_ M=M_ as='(AS_>0)?AS_:(0.5e-6*W_)' ps='(PS_>0)?PS_:(2*W_+2*0.5e-6)' ad='(AD_>0)?AD_:(0.5e-6*W_)' pd='(PD_>0)?PD_:(2*W_+2*0.5e-6)'
*.ends

******************************* CAPACITORS ******************************

*** parametrized capacitor old style 20230414ba will be removed at next SCIB cleanup 
.subckt C_param top bottom sub Cmodel=0 W_=0 L_=0 M_=1
	.if(Cmodel == 1)
		*NIC capacitor
		Xstd_Cnpod top bottom sub std_Cnpod W_=W_ L_=L_ M_=M_

	.elseif(Cmodel == 2)
		*accumulation capacitor in thick oxide
		Xstd_Cnwnmos top bottom sub std_Cnwnmos W_=W_ L_=L_ M_=M_

	.else
		*MiM capacitor
		Xstd_CMiM top bottom sub std_CMiM W_=W_ L_=L_ M_=M_
	.endif
.ends


*** parameterized capacitor new style * 20210321ba
.subckt Cmodel_WL top bottom sub Cmodel=0 W_=0 L_=0 M_=1
	.if(Cmodel == CMIM)        *default MiM capacitor
		Xcmim    top bottom sub std_CMiM    W_=W_ L_=L_ M_=M_
	.elseif(Cmodel == CACC)    *std Accumulation capacitor
		Xcacc    top bottom sub std_Cnwnmos W_=W_ L_=L_ M_=M_
	.elseif(Cmodel == LOGCACC) *logic accumulation capacitor
		Xlogcacc top bottom sub log_Cnwnmos W_=W_ L_=L_ M_=M_
	.elseif(Cmodel == CPOD)  	*std POD or NIC capacitor
		Xcpod    top bottom sub std_Cnpod   W_=W_ L_=L_ M_=M_
	.elseif(Cmodel == CNMOS)  	*NMOSFET as capacitor   20210331ba added
	   Xnmos bottom top bottom sub std_nmos W_=W_ L_=L_ M_=M_ 
	.elseif(Cmodel == CIDEAL)  	*ideal SPICE cap 20230421
	   Cideal top bottom  '1E-3*W_*L_*M_'
	* 20230703 Koen added CMIMH (cmim_uhd) and CMIMHS (cmim_uhdstk)
	.elseif(Cmodel == CMIMH)        *uhd MiM capacitor
		Xcmim    top bottom sub uhd_CMiM    W_=W_ L_=L_ M_=M_
	.elseif(Cmodel == CMIMHS)        *stacked uhd MiM capacitor
		Xcmim    top bottom sub uhd_stk_CMiM    W_=W_ L_=L_ M_=M_
	*.else   exception not foreseen.  If not listed, simulation will fail.
	.endif
.ends

*MIM capacitor
	.subckt std_CMiM top bottom sub W_=0 L_=0 M_=1
		Xcmim_hc top bottom cmim_hc w=W_ l=L_ m=M_
		*the tower model ignores the bottom plate, so we add it here as an arbitrary(?) 1/20th of the real capacitor:
		Cpar bottom sub  '1.7e-3*L_*W_*M_/20'
	.ends

* 20230703 Koen added CMIMH (cmim_uhd) and CMIMHS (cmim_uhdstk)
*UHD MIM capacitor
	.subckt uhd_CMiM top bottom sub W_=0 L_=0 M_=1
		Xcmim_hc top bottom cmim_uhd w=W_ l=L_ m=M_
		*the tower model ignores the bottom plate, so we add it here as an arbitrary(?) 1/20th of the real capacitor:
		Cpar bottom sub  '1.7e-3*L_*W_*M_/20'
	.ends

* 20230703 Koen added CMIMH (cmim_uhd) and CMIMHS (cmim_uhdstk)
*UDH stacked MIM capacitor
	.subckt uhd_stk_CMiM top bottom sub W_=0 L_=0 M_=1
		Xcmim_hc top bottom cmim_uhdstk w=W_ l=L_ m=M_
		*the tower model ignores the bottom plate, so we add it here as an arbitrary(?) 1/16th of the real capacitor (5/4 of 1/20):
		Cpar bottom sub  '1.7e-3*L_*W_*M_/16'
	.ends

*accumulation capacitor in thick oxide (std)
	.subckt std_Cnwnmos VP VM sub W_=0 L_=0 M_=1 * VP is the top, VM is the bottom
		Xcnwnmos VP VM nwcaph2t W=W_ L=L_ M=M_  
		*the tower model ignores the bottom plate, so we add it here as an arbitrary(?) 1/20th of the real capacitor:
		Cpar VM sub  '5e-3*L_*W_*M_/20'
	.ends

*accumulation capacitor in thin oxide  (log) 20190511ba added sub
	.subckt log_Cnwnmos VP VM sub W_=0 L_=0 M_=1   
		* VP is the top, VM is the bottom
		Xlog_cacc VP VM nwcap2t W=W_ L=L_ M=M_
		*the tower model ignores the bottom plate, so we add it here as an arbitrary(?) 1/20th of the real capacitor:
		Cpar VM sub  '5e-3*L_*W_*M_/20'
	.ends

*NIC capacitor
	.subckt std_Cnpod top bottom sub W_=0 L_=0 M_=1
		Xcnpod top bottom ncapimp332t w=W_ l=L_ m=M_
		*remark that the tower model ignores the bottom plate, so we add  here rather arbitrarily 1/10:
		Cpar bottom sub  '5e-3*L_*W_*M_/10'	
	.ends

*high-K capacitor  ////  incompatible way to represent sub M, W and L! 
	.subckt Csmim_hkc top bottom 
		Xsmim_hkc top bottom smim_hkc  
	.ends	

	
.subckt std_pdio p n W_=0 L_=0 M_=1
	Dstd_pdio p n dph Area=L_*W_  M=M_
.ends

.subckt std_ndio p n W_=0 L_=0 M_=1
	Dstd_ndio p n dnh Area=L_*W_  M=M_
.ends

.subckt log_pdio p n W_=0 L_=0 M_=1
	Dlog_pdio p n dp18 Area=L_*W_  M=M_
.ends

.subckt log_ndio p n W_=0 L_=0 M_=1
	Dlog_ndio p n dn18 Area=L_*W_  M=M_
.ends

.subckt deepnwell_sub_diode p n W_=0 L_=0 M_=1
	Ddwnps18 p n ddwnps18 Area='L_*W_' M=M_
.ends

.subckt deepnwell_pwell_diode p n W_=0 L_=0 M_=1
	Ddwnpw18 p n ddwnpw18 Area='L_*W_' M=M_
.ends

.subckt nwell_sub_diode p n W_=0 L_=0 M_=1
	DNWELL33 p n DNWELL33 Area='L_*W_' M=M_
.ends

* poly resistor
* we use preferentially an n-doped non-salicided poly resistor (not the HIGHres!!!)
* 202012130ba obsoleting:
.subckt std_rpoly a b W_=0 L_=0  M_=1
	Xrstd_poly a b rnmpoly2t L=L_ W=W_  M=M_
.ends
* new version: [20201230ba]
.subckt rpoly a b W_=0 L_=0  M_=1
	Xrstd_poly a b rnmpoly2t L=L_ W=W_  M=M_
.ends

*** 20220228 Sampsa added hires poly resistor, 2kohm/sq
* new version: [20201230ba]
.subckt rpoly_hires a b W_=0 L_=0  M_=1
	Xrstd_poly a b mr22t L=L_ W=W_  M=M_
.ends

*** 20220518 Gaozhan added hires poly resistor, 10kohm/sq
* new version: [20201230ba]
.subckt rpoly_hires10k a b sub W_=0 L_=0  M_=1
	Xrstd_poly a b sub mr33t L=L_ W=W_  M=M_
.ends

* nwell resistor
.subckt std_rnwell a b W_=0 L_=0 M_=1
	Xrstd_nwell a b rnwellsti2t L=L_ W=W_ M=M_
.ends

* rpoly1Meg
* .subckt rpoly1Meg a b  M_=1
* Xstd_rpoly a b std_rpoly L= W='0.2u'  M=M_
* .ends

* qualitative TG model
.subckt std_TG PPD TG FD SUB W_=2u L_=0.6u Vdep=0.7 Ctgfd=0.1f
	*0.7 is the Vth, 0.026 is the thermal voltage=kT/q, 4e-14 is the diode saturation current
	vdep  dep  0  Vdep
	gt_gate        FD     PPD  
		+ cur='v(FD,PPD) * min(max((-1e-5)*(v(PPD)-v(dep)),0), (4e-14)*exp((v(TG,PPD)-0.7)/0.026))'
	captgfd TG FD Ctgfd 
	*typical values in the order of 0.1 to 1 fF
.ends

* qualitative PPD
* Vdep is (our approach) property of the TG not of the PPD 
* this capacitance is just representing the Vpinning drop versus amount of charge contained.
.subckt PPD PPD SUB W_=5u L_=5u
	cppd SUB PPD 'W_*L_*0.3e-3' 
	* the last factor calibrate it versus measurements
.ends

* qualitative depletion voltage test structure
.subckt depletion A B SUB W_=5u L_=5u 
	*0.026 is the thermal voltage=kT/q, 4e-14 is a saturation current, value to be updated after simulation
	gt_gate B A  
	+ cur='v(B,A) * W_/L_ * min(max((-1e-5)*v(A)+1e-5,0),(4e-14))'
.ends

* qualitative poly_diode
.subckt poly_diode p n W_=5u
	Xdio p n_int low_pdio  W_='W_'  L_=0.1u
	* the above is done as the real polydiode model does not exist
	Rseries n_int n '1000/(W_/0.9u)'
	Rleak p n '1G/W_'
	* the 1G may need to be fine tuned
.ends

*************************************************************
* 20220915ba OBSOLETE the following bondpadmodel is  replaced by a simple rshort  from devices  obsolete
.model bondpadmodel r 
.subckt bondpad in out
	rpad in out r = 1m
.ends

*not clear if the following are really needed
.model Rshort r
.model Cparasitic c
.model Rleakage r
.model Lparasitic l

**********************************************************
* parameters used in stdcell and logic                                                  *
**********************************************************
* are in v2.0_common
