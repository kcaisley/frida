*******************************************************************************
* (c) Caeleste
* TPSC65 stdcell parameter file

* 20240227 AM Created the file
* 20240418 Koen copied from v2.0.lib and removed all .if-.else-.endif stuff
* 20240418 Koen remove AS, PS, AD, PD parmeters from subckt def of mos, they are not there in schematic either
* 20240418 Koen change transistor types to what comes out of extraction, I no like reverse engineering encrypted scripts
* 20240502 AM change transistor types to match device definition
* 20240708 Koen add [std/log]_[n/p]dio
* 20240730 Koen change diode types to what comes out of extraction
* 20240801 Arne added rpoly subcircuit and created simplified model based on rnps_nm133 model due to RM model extraction in LVS
* 20241003 Koen change transistor types to what comes out of extraction
* 20241017 Mudasir changed the diode models from 	DR and DS to dio_nodpw and dio_podnw, so that hte models are LVS compliant.
****************************************************************
* all technology dependent parameters are included from following file 
.include "v2.0_common.sp"
****************************************************************

*******************************************************
* label used by Nick to ensure validity of the file
.model STDCELL_VERSION_1_0 r
*******************************************************

* STANDARD (vdd/vss) MOSFET models

.subckt std_nmos D G S B W_=0 L_=0 M_=1
	Mstd_nmos D G S B nmos_33v W=W_ L=L_ M=M_ as='(0.6e-6*W_)' ps='(2*W_+2*0.6e-6)' ad='(0.6e-6*W_)' pd='(2*W_+2*0.6e-6)'
.ends

.subckt std_pmos D G S B W_=0 L_=0 M_=1
	Mstd_pmos D G S B pmos_33v W=W_ L=L_ M=M_ as='(0.6e-6*W_)' ps='(2*W_+2*0.6e-6)' ad='(0.6e-6*W_)' pd='(2*W_+2*0.6e-6)'
.ends

* LOGIC (vcc/vee) MOSFET models

.subckt log_nmos D G S B W_=0 L_=0 M_=1
	Mlog_nmos D G S B N3 W=W_ L=L_ M=M_ as='(0.6e-6*W_)' ps='(2*W_+2*0.6e-6)' ad='(0.6e-6*W_)' pd='(2*W_+2*0.6e-6)'
.ends

.subckt log_pmos D G S B W_=0 L_=0 M_=1
	Mlog_pmos D G S B P3 W=W_ L=L_ M=M_ as='(0.6e-6*W_)' ps='(2*W_+2*0.6e-6)' ad='(0.6e-6*W_)' pd='(2*W_+2*0.6e-6)'
.ends

**********************************
* DIODE models
**********************************
* N+/Pwell diode with thick oxide layer
.subckt std_ndio a k W_=0 L_=0  M_=1
	D0 a k dio_nodpw AREA=W_*L_ PJ=2*(W_+L_)
.ends

* P+/Nwell diode with thick oxide layer
.subckt std_pdio a k W_=0 L_=0 M_=1
	D0 a k dio_podnw AREA=W_*L_ PJ=2*(W_+L_)
.ends

* N+/Pwell diode w/o thick oxide layer
.subckt log_ndio a k W_=0 L_=0  M_=1
	*D0 a k ndio AREA=W_*L_ PJ=2*(W_+L_)
.ends

* P+/Nwell diode w/o thick oxide layer
.subckt log_pdio a k W_=0 L_=0 M_=1
	*D0 a k pdio AREA=W_*L_ PJ=2*(W_+L_)
.ends

***************
* RESISTOR models
***************
* We use preferentially an n-doped non-salicided poly resistor (not the HIGHres!!!)
*202450802 ac -  model is based on the LVS extraction file (TPS65ISC_LVS_CALIBRE.rul.encrypt)
.subckt rpoly a b W_=0 L_=0 
+        rsh=std_rpoly_sheet
	Rrpoly a b r='(((rsh)*(L_))/(W_))' $[RM]
.ends