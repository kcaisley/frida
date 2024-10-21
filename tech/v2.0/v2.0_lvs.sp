*******************************************************************************
* (c) Caeleste
* TSMC 65/55 stdcell parameter file

* 20240229 Koen created this file based on existing v2.0.lib file in the same directory
* 20240229 Koen commented out all .if-.else-.endif statements and chose one branch
* 20240619 Koen add transistor subckt stubs for std and log nmos/pmos
* 20240619 Koen add diodes

****************************************************************
* all technology dependent parameters are included from following file 
.include "v2.0_common.sp"
****************************************************************

*******************************************************
* label used by Nick to ensure validity of the file
.model STDCELL_VERSION_1_0 r
*******************************************************

**********************************
* STANDARD (vdd/vss) MOSFET models
**********************************

.subckt std_nmos D G S B W_=0 L_=0 M_=1
	Mstd_nmos D G S B nch_25 W=W_ L=L_ M=M_
.ends
	
.subckt std_pmos D G S B W_=0 L_=0 M_=1
	Mstd_pmos D G S B pch_25 W=W_ L=L_ M=M_ 
.ends

**********************************
* LOGIC (vcc/vee) MOSFET models 
**********************************

.subckt log_nmos D G S B W_=0 L_=0 M_=1
	Mlog_nmos D G S B nch W=W_ L=L_ M=M_
.ends

.subckt log_nmos_lowVth D G S B W_=0 L_=0 M_=1
	Xlog_nmos_lowVth D G S B nch_lvt_mac W=W_ L=L_ M=M_
.ends

.subckt log_pmos D G S B W_=0 L_=0 M_=1
	Mlog_pmos D G S B pch W=W_ L=L_ M=M_
.ends

.subckt log_pmos_lowVth D G S B W_=0 L_=0 M_=1
	Xlog_pmos_lowVth D G S B pch_lvt_mac W=W_ L=L_ M=M_
.ends

**********************************
* DIODE models
**********************************
* N+/Pwell diode with thick oxide layer
.subckt std_ndio a k W_=0 L_=0  M_=1
	D0 a k ndio_25 AREA=W_*L_ PJ=2*(W_+L_)
.ends

* P+/Nwell diode with thick oxide layer
.subckt std_pdio a k W_=0 L_=0 M_=1
	D0 a k pdio_25 AREA=W_*L_ PJ=2*(W_+L_)
.ends

* N+/Pwell diode w/o thick oxide layer
.subckt log_ndio a k W_=0 L_=0  M_=1
	D0 a k ndio AREA=W_*L_ PJ=2*(W_+L_)
.ends

* P+/Nwell diode w/o thick oxide layer
.subckt log_pdio a k W_=0 L_=0 M_=1
	D0 a k pdio AREA=W_*L_ PJ=2*(W_+L_)
.ends

**********************************
* RESISTOR models
**********************************
* N-doped poly resistor without silicide
.subckt std_rpoly a b W_=0 L_=0  M_=1
	Xrstd_poly a b rnpolywo L=L_ W=W_  M=M_
.ends

* NWELL diffusion resistor under active(OD)
.subckt std_rnwell a b W_=0 L_=0 M_=1
	Xrstd_nwell a b rnwod L=L_ W=W_ M=M_
.ends
