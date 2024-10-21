** Python v2.0_common export from source: S:\technologies\setup\v2common\v2common.xlsx

** DO NOT MODIFY FILE (unless you know very well what you're doing.)

*******************************************************************************
** (c) Caeleste
** Stdcell parameter file for all technologies under v2.0
.param tsl018 = 1
.param umc018 = 2
.param xc018 = 3
.param lf11is = 4
.param tsmc018 = 5
.param tpsc65 = 6
.param tsmc65 = 7
.param technology_name = tsmc65
*******************************************************************************
** nominal supply voltages                           
.param std_VDD = 3.3
.param log_VCC = 1.2
******************************************************************************
** MOSFET Device dimensions 
** the HV (=std) true design rule limits, try to keep  small if these rules are too relaxed.  Relaxing is for yield not for matching!
.param std_nmos_Ldesignrule = 0.5u
.param std_nmos_Wdesignrule = 0.4u
.param std_pmos_Ldesignrule = 0.4u
.param std_pmos_Wdesignrule = 0.4u
** the LV (=log) true design rule limits, for logic library
.param log_nmos_Ldesignrule = 0.06u
.param log_nmos_Wdesignrule = 0.12u
.param log_pmos_Ldesignrule = 0.06u
.param log_pmos_Wdesignrule = 0.12u
** the "relaxed" or "safe" rules for analog design and yield
.param std_nmos_Lmin = 0.5u
.param std_pmos_Lmin = 0.4u
**W  to create Strenght 1 resistive-balanced single cascoded inv and switch, in combination with the Lmin.
.param std_pmos_WS1 = 0.5u
.param std_nmos_WS1 = 0.4u
** Lmin for lowVth mosfets
* MISSING VALUE (or obsolete param).param std_nmos_lowVth_Lmin = 
* MISSING VALUE (or obsolete param).param std_pmos_lowVth_Lmin = 
** the effective W/L ratios between PMOS/NMOS single mosfets.  Is effective ratio of mobilities (20221219ba used in switch_np_rcbalanced)
.param std_ratio_rcbalanced = 3.6
** sqrt of the above
.param std_sqrt_rcbalanced = 1.9
** the "relaxed" or "safe" rules for (low voltage) logic design
.param log_nmos_Lmin = 0.1u
.param log_nmos_WS1 = 0.15u
.param log_pmos_Lmin = 0.1u
**value for LF11 not sure; value for XFAB should increase to 0.5u
.param log_pmos_WS1 = 0.25u
** the effective W/L ratios between PMOS/NMOS single mosfets.  Is effective ratio of mobilities (20221219ba used in switch_np_rcbalanced)
.param log_ratio_rcbalanced = 3.6
** sqrt of the above
.param log_sqrt_rcbalanced = 1.9

** RELAXED MOSFET rules for IDENTICAL  nMOSFET and pMOSFET size, e.g. use in C-balanced switches
** minimum L applicable to both N and P
.param std_Lmin = 0.5u
** minimum W applicable to both N and P
.param std_Wmin = 0.4u
** minimum L applicable to both N and P
.param log_Lmin = 0.1u
** minimum W applicable to both N and P
.param log_Wmin = 0.15u

*******************************************************************
*TUNER (current mirror according to BP011) dimensions
**algorithm to define see BP011 20240320baac
.param std_Lptune = (std_pmos_Lmin*2)
**algorithm to define see BP011 20240320baac
.param std_Lntune = (std_nmos_Lmin*3)
**algorithm to define see BP011 20240320baac
.param std_Wtune = (std_Wmin*32  )
**algorithm to define see BP011 20240320baac
.param log_Lptune = (log_pmos_Lmin*2)
**algorithm to define see BP011 20240320baac
.param log_Lntune = (log_nmos_Lmin*3)
**algorithm to define see BP011 20240320baac
.param log_Wtune = (log_Wmin*32  )
*******************************************************************
**RH (radhard) parasitics for H-shaped nMOSFETs  //  these need to be estimated for each technology 
* MISSING VALUE (or obsolete param).param std_Crhgs = 
* MISSING VALUE (or obsolete param).param std_Crhgd = 
* MISSING VALUE (or obsolete param).param log_Crhgs = 
* MISSING VALUE (or obsolete param).param log_Crhgd = 
*******************************************************************
*DIODES
*minimum antenna protection diode
* .param q: is the below set of parameters still in use? = 
*20240919ba obsoleting
.param std_Ldiode = 0.5u
*20240919ba obsoleting
.param std_Wdiode = 0.5u
*20240919ba obsoleting
.param log_Ldiode = 0.25u
*20240919ba obsoleting
.param log_Wdiode = 0.25u
*new parameter names
.param std_WLantennadiode = 0.5u
.param log_WLantennadiode = 0.25u
*DFF_POZ diode
.param std_LPOZdiode = 2.35u
.param std_WPOZdiode = 0.5u
.param log_LPOZdiode = 1u
.param log_WPOZdiode = 0.2u
*p-in-nwell temperature diode
**20180914 increased  to >5 u
.param std_LTempDiode = 6u
**20180914 increased  to >5 u
.param std_WTempDiode = 6u

*******************************************************************
*POLY RESISTORS
*for several reasons we use as baseline highly doped n-type, not salicided, typical corner
*sheet resistance
.param std_rpoly_sheet = ?
*strong advice to use unsalicided N+ poly. WARNING: XFAB: uses both RSRNP1 and RSENP1SB! 
*effective W = design W + delta
* .param std_deltaW_sheet = 
*effective L = design L + delta
* .param std_deltaL_sheet = 
*this is the minimum relaxed L
.param std_Lrpoly10 = ?
* MISSING VALUE (or obsolete param).param std_Wrpoly10 = 
* MISSING VALUE (or obsolete param).param std_Lrpoly100 = 
*values optimized by simulation  for xs tt +25deg
* .param std_Wrpoly100 = 
* MISSING VALUE (or obsolete param).param std_Lrpoly1k = 
* MISSING VALUE (or obsolete param).param std_Wrpoly1k = 
* MISSING VALUE (or obsolete param).param std_Lrpoly10k = 
* MISSING VALUE (or obsolete param).param std_Wrpoly10k = 
* MISSING VALUE (or obsolete param).param std_Lrpoly100k = 
* MISSING VALUE (or obsolete param).param std_Wrpoly100k = 
* MISSING VALUE (or obsolete param).param std_Lrpoly1Meg = 
*this is the minimum relaxed W
.param std_Wrpoly1Meg = 0.1u


*******************************************************************
*CAPACITORS
*in device Cmodel_WL the constants CMIM, CPOD, CACC, CMIMH etc are used.
*actual cap values in standard cell layout can be derived from the 1pF versions, with fixed L (height) and variable W
*20210321ba IN THE FUTURE one will only use C*_ffperum2 to calculate C value. Perhaps a fringe C must be introduced too.
*The convention is W is direction of the VSS VDD rail, L is orthogonal to the VSS VDD rails
*basic MIM capacitor 
* .param CMIM = 
*model name (experimental)
* .param CMIM_model = 
*new naming
* .param CMIM_1pF_W = 
*new naming
* .param CMIM_1pF_L = 
* MISSING VALUE (or obsolete param).param CMIM_ffperum2 = 
*POD or NIC capacitor
* .param CPOD = 
*model name (experimental)
* .param CPOD_model = 
* MISSING VALUE (or obsolete param).param CPOD_1pF_W = 
* MISSING VALUE (or obsolete param).param CPOD_1pF_L = 
* MISSING VALUE (or obsolete param).param CPOD_ffperum2 = 
*std accumulation capacitor
* .param CACC = 
* MISSING VALUE (or obsolete param).param CACC_1pF_W = 
* MISSING VALUE (or obsolete param).param CACC_1pF_L = 
* MISSING VALUE (or obsolete param).param CACC_ffperum2 = 
*high density MIMH
* .param CMIMH = 
*model name
* .param CMIMH_model = 
*20221104ba high K removed
* .param CMIMH_1pF_W = 
*20221104ba high K removed
* .param CMIMH_1pF_L = 
*20221104ba high K removed
* .param CMIMH_ffperum2 = 
*NMOS capacitor STANDARD
.param CNMOS = 4
.param CNMOS_ffperum2 = 5
*accumulation caps in the logic transistor scope
* .param CLOGACC = 
* MISSING VALUE (or obsolete param).param CLOGACC_1pF_W = 
* MISSING VALUE (or obsolete param).param CLOGACC_1pF_L = 
* MISSING VALUE (or obsolete param).param CLOGACC_ffperum2 = 
*POD or NIC capacitor in the LOG environment
* .param CLOGPOD = 
* MISSING VALUE (or obsolete param).param CLOGPOD_1pF_W = 
* MISSING VALUE (or obsolete param).param CLOGPOD_1pF_L = 
* MISSING VALUE (or obsolete param).param CLOGPOD_ffperum2 = 
*NMOS capacitor LOG
* .param CLOGNMOS = 
* MISSING VALUE (or obsolete param).param CLOGNMOS_ffperum2 = 
*double layer MIM2
* .param CMIM2 = 
*double layer MIM2 model name (INFO only)
* .param CMIM2_model = 
* MISSING VALUE (or obsolete param).param CMIM2_1pF_W = 
* MISSING VALUE (or obsolete param).param CMIM2_1pF_L = 
* MISSING VALUE (or obsolete param).param CMIM2_ffperum2 = 
*triple layer MIM3
* .param CMIM3 = 
* MISSING VALUE (or obsolete param).param CMIM3_1pF_W = 
* MISSING VALUE (or obsolete param).param CMIM3_1pF_L = 
* MISSING VALUE (or obsolete param).param CMIM3_ffperum2 = 
*PMOS capacitor STANDARD
.param CPMOS = 10
.param CPMOS_ffperum2 = 5
*PMOS capacitor LOG
* .param CLOGPMOS = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_1pF_W = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_1pF_L = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_ffperum2 = 
*Ideal SPICE capacitor (for comparisons only)
.param CIDEAL = 12
.param CIDEAL_ffperum2 = 1
*MOM capacitor = fingered WIP
.param CMOM = 13
* MISSING VALUE (or obsolete param).param CLOGPMOS_1pF_W = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_1pF_L = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_ffperum2 = 
******************************************************************
*ESD RESISTORS
*we use n-type poly resistor, non salicided
* .param IO_ESD_Rsheet = 
* MISSING VALUE (or obsolete param).param IO_ESD50_L = 
* MISSING VALUE (or obsolete param).param IO_ESD50_W = 
* MISSING VALUE (or obsolete param).param IO_ESD20_L = 
*should evolve to W<=40u
* .param IO_ESD20_W = 
.param IO_ESDdiode_L = 2.2u
.param IO_ESDdiode_W = 19.2u

*******************************************************************




