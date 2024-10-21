*************************************
*
* (c) Caeleste
* 20170918 Wei modified this file with reference to v2.0_lvs_common
* 20220218 Sampsa added high-k capacitor smim_hkc
*************************************

.include "/caeleste/technologies/tsl018/v2.0/v2.0_lvs_common.sp"
********************************************************

.subckt C_param top bottom sub Cmodel=0 W_=0 L_=0 M_=1
*.if(Cmodel == 1)
*	*NIC capacitor
*	Xstd_Cnpod top bottom sub std_Cnpod W_=W_ L_=L_ M_=M_
*.elseif(Cmodel == 2)
*	*accumulation capacitor
*	Xstd_Cnwnmos top bottom std_Cnwnmos W_=W_ L_=L_ M_=M_
*.else
	*MiM capacitor
	Xstd_CMiM top bottom sub std_CMiM W_=W_ L_=L_ M_=M_
*.endif
.ends

.subckt Cmodel_WL top bottom sub Cmodel=0 W_=0 L_=0 M_=1
*.if(Cmodel == 1)
*	*NIC capacitor
*	Xstd_Cnpod top bottom sub std_Cnpod W_=W_ L_=L_ M_=M_
*.elseif(Cmodel == 2)
*	*accumulation capacitor
*	Xstd_Cnwnmos top bottom std_Cnwnmos W_=W_ L_=L_ M_=M_
*.else
	*MiM capacitor
	Xstd_CMiM top bottom sub std_CMiM W_=W_ L_=L_ M_=M_
*.endif
.ends

**** SMIM_HKC capacitor
.subckt Csmim_hkc top bottom M_=1
Xmim_hkc top bottom smim_hkc area=0.0 pj=0 M_=M_
.ends

.subckt smim_hkc A B area=0.0 pj=0 M_=1
C1 A B smim_hkc c='2.5e-15*M_'
.ends
****
