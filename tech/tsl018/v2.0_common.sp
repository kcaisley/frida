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
.param technology_name = tsl018
*******************************************************************************
** nominal supply voltages                           
.param std_VDD = 3.3
.param log_VCC = 1.8
******************************************************************************
** MOSFET Device dimensions 
** the HV (=std) true design rule limits, try to keep  small if these rules are too relaxed.  Relaxing is for yield not for matching!
.param std_nmos_Ldesignrule = 0.35u
.param std_nmos_Wdesignrule = 0.22u
.param std_pmos_Ldesignrule = 0.30u
.param std_pmos_Wdesignrule = 0.22u
** the LV (=log) true design rule limits, for logic library
.param log_nmos_Ldesignrule = 0.18u
.param log_nmos_Wdesignrule = 0.22u
.param log_pmos_Ldesignrule = 0.18u
.param log_pmos_Wdesignrule = 0.22u
** the "relaxed" or "safe" rules for analog design and yield
.param std_nmos_Lmin = 0.40u
.param std_pmos_Lmin = 0.35u
**W  to create Strenght 1 resistive-balanced single cascoded inv and switch, in combination with the Lmin.
.param std_pmos_WS1 = 0.5u
.param std_nmos_WS1 = 0.3u
** Lmin for lowVth mosfets
.param std_nmos_lowVth_Lmin = 0.40u
.param std_pmos_lowVth_Lmin = 0.35u
** the effective W/L ratios between PMOS/NMOS single mosfets.  Is effective ratio of mobilities (20221219ba used in switch_np_rcbalanced)
.param std_ratio_rcbalanced = 3.6
** sqrt of the above
.param std_sqrt_rcbalanced = 1.9
** the "relaxed" or "safe" rules for (low voltage) logic design
.param log_nmos_Lmin = 0.2u
.param log_nmos_WS1 = 0.25u
.param log_pmos_Lmin = 0.2u
**value for LF11 not sure; value for XFAB should increase to 0.5u
.param log_pmos_WS1 = 0.45u
** the effective W/L ratios between PMOS/NMOS single mosfets.  Is effective ratio of mobilities (20221219ba used in switch_np_rcbalanced)
.param log_ratio_rcbalanced = 3.6
** sqrt of the above
.param log_sqrt_rcbalanced = 1.9

** RELAXED MOSFET rules for IDENTICAL  nMOSFET and pMOSFET size, e.g. use in C-balanced switches
** minimum L applicable to both N and P
.param std_Lmin = 0.4u
** minimum W applicable to both N and P
.param std_Wmin = 0.3u
** minimum L applicable to both N and P
.param log_Lmin = 0.2u
** minimum W applicable to both N and P
.param log_Wmin = 0.25u

*******************************************************************
*TUNER (current mirror according to BP011) dimensions
**algorithm to define see BP011 20240320baac
.param std_Lptune = 0.8u
**algorithm to define see BP011 20240320baac
.param std_Lntune = 1.2u
**algorithm to define see BP011 20240320baac
.param std_Wtune = 10u
**algorithm to define see BP011 20240320baac
.param log_Lptune = 0.4u
**algorithm to define see BP011 20240320baac
.param log_Lntune = 0.8u
**algorithm to define see BP011 20240320baac
.param log_Wtune = 7u
*******************************************************************
**RH (radhard) parasitics for H-shaped nMOSFETs  //  these need to be estimated for each technology 
.param std_Crhgs = 1.1f
.param std_Crhgd = 1.1f
.param log_Crhgs = 0.9f
.param log_Crhgd = 0.9f
*******************************************************************
*DIODES
*minimum antenna protection diode
* .param q: is the below set of parameters still in use? = 
*20240919ba obsoleting
.param std_Ldiode = 0.5u
*20240919ba obsoleting
.param std_Wdiode = 0.5u
*20240919ba obsoleting
.param log_Ldiode = 0.45u
*20240919ba obsoleting
.param log_Wdiode = 0.45u
*new parameter names
.param std_WLantennadiode = 0.5u
.param log_WLantennadiode = 0.45u
*DFF_POZ diode
.param std_LPOZdiode = 3u
.param std_WPOZdiode = 0.5u
.param log_LPOZdiode = 2u
.param log_WPOZdiode = 0.45u
*p-in-nwell temperature diode
**20180914 increased  to >5 u
.param std_LTempDiode = 6u
**20180914 increased  to >5 u
.param std_WTempDiode = 6u

*******************************************************************
*POLY RESISTORS
*for several reasons we use as baseline highly doped n-type, not salicided, typical corner
*sheet resistance
.param std_rpoly_sheet = 400
*strong advice to use unsalicided N+ poly. WARNING: XFAB: uses both RSRNP1 and RSENP1SB! 
*effective W = design W + delta
.param std_deltaW_sheet = 0.055u
*effective L = design L + delta
.param std_deltaL_sheet = 0
*this is the minimum relaxed L
.param std_Lrpoly10 = 1u
.param std_Wrpoly10 = 40u
.param std_Lrpoly100 = 1.8u
*values optimized by simulation  for xs tt +25deg
.param std_Wrpoly100 = 9.2u
.param std_Lrpoly1k = 4.35u
.param std_Wrpoly1k = 2u
.param std_Lrpoly10k = 23.1u
.param std_Wrpoly10k = 1u
.param std_Lrpoly100k = 60.7u
.param std_Wrpoly100k = 0.3u
.param std_Lrpoly1Meg = 363u
*this is the minimum relaxed W
.param std_Wrpoly1Meg = 0.2u


*******************************************************************
*CAPACITORS
*in device Cmodel_WL the constants CMIM, CPOD, CACC, CMIMH etc are used.
*actual cap values in standard cell layout can be derived from the 1pF versions, with fixed L (height) and variable W
*20210321ba IN THE FUTURE one will only use C*_ffperum2 to calculate C value. Perhaps a fringe C must be introduced too.
*The convention is W is direction of the VSS VDD rail, L is orthogonal to the VSS VDD rails
*basic MIM capacitor 
.param CMIM = 0
*model name (experimental)
* .param CMIM_model = 
*new naming
.param CMIM_1pF_W = 66u
*new naming
.param CMIM_1pF_L = 9u
.param CMIM_ffperum2 = 1.7
*POD or NIC capacitor
.param CPOD = 1
*model name (experimental)
* .param CPOD_model = 
.param CPOD_1pF_W = 43u
.param CPOD_1pF_L = 6u
.param CPOD_ffperum2 = 3.8
*std accumulation capacitor
.param CACC = 2
.param CACC_1pF_W = 33u
.param CACC_1pF_L = 6u
.param CACC_ffperum2 = 5
*high density MIMH
.param CMIMH = 3
*model name
* .param CMIMH_model = 
*20221104ba high K removed
.param CMIMH_1pF_W = 40u
*20221104ba high K removed
.param CMIMH_1pF_L = 9u
*20221104ba high K removed
.param CMIMH_ffperum2 = 2.8
*NMOS capacitor STANDARD
.param CNMOS = 4
.param CNMOS_ffperum2 = 5
*accumulation caps in the logic transistor scope
.param CLOGACC = 5
.param CLOGACC_1pF_W = 28u
.param CLOGACC_1pF_L = 5u
.param CLOGACC_ffperum2 = 7
*POD or NIC capacitor in the LOG environment
.param CLOGPOD = 6
.param CLOGPOD_1pF_W = 28u
.param CLOGPOD_1pF_L = 5u
.param CLOGPOD_ffperum2 = 7
*NMOS capacitor LOG
.param CLOGNMOS = 7
.param CLOGNMOS_ffperum2 = 7
*double layer MIM2
.param CMIM2 = 8
*double layer MIM2 model name (INFO only)
* .param CMIM2_model = 
.param CMIM2_1pF_W = 20u
.param CMIM2_1pF_L = 9u
.param CMIM2_ffperum2 = 5.6
*triple layer MIM3
.param CMIM3 = 9
* MISSING VALUE (or obsolete param).param CMIM3_1pF_W = 
* MISSING VALUE (or obsolete param).param CMIM3_1pF_L = 
* MISSING VALUE (or obsolete param).param CMIM3_ffperum2 = 
*PMOS capacitor STANDARD
.param CPMOS = 10
.param CPMOS_ffperum2 = 5
*PMOS capacitor LOG
.param CLOGPMOS = 11
.param CLOGPMOS_1pF_W = 28u
.param CLOGPMOS_1pF_L = 5u
.param CLOGPMOS_ffperum2 = 7
*Ideal SPICE capacitor (for comparisons only)
.param CIDEAL = 12
.param CIDEAL_ffperum2 = 1
*MOM capacitor = fingered WIP
* .param CMOM = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_1pF_W = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_1pF_L = 
* MISSING VALUE (or obsolete param).param CLOGPMOS_ffperum2 = 
******************************************************************
*ESD RESISTORS
*we use n-type poly resistor, non salicided
.param IO_ESD_Rsheet = 400
.param IO_ESD50_L = 5u
.param IO_ESD50_W = 40u
.param IO_ESD20_L = 4u
*should evolve to W<=40u
.param IO_ESD20_W = 80u
.param IO_ESDdiode_L = 2.2u
.param IO_ESDdiode_W = 19.2u

*******************************************************************




