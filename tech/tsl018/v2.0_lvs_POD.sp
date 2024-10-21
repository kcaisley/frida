*************************************
*
* (c) Caeleste
* 20170918 Wei modified this file with reference to v2.0_lvs_common 
* 20170610 BS added Cmodel_WL
*************************************

.include "/caeleste/technologies/tsl018/v2.0/v2.0_lvs_common.sp"
********************************************************

.subckt C_param top bottom sub Cmodel=0 W_=0 L_=0 M_=1
*.if(Cmodel == 1)
	*NIC (=POD) capacitor
	Xstd_Cnpod top bottom sub std_Cnpod W_=W_ L_=L_ M_=M_
*.elseif(Cmodel == 2)
*	*accumulation capacitor
*	Xstd_Cnwnmos top bottom std_Cnwnmos W_=W_ L_=L_ M_=M_
*.else
*	*MiM capacitor
*	Xstd_CMiM top bottom sub std_CMiM W_=W_ L_=L_ M_=M_
*.endif
.ends


.subckt Cmodel_WL top bottom sub Cmodel=0 W_=0 L_=0 M_=1
*.if(Cmodel == 1)
	*NIC (=POD) capacitor
	Xstd_Cnpod top bottom sub std_Cnpod W_=W_ L_=L_ M_=M_
*.elseif(Cmodel == 2)
*	*accumulation capacitor
*	Xstd_Cnwnmos top bottom std_Cnwnmos W_=W_ L_=L_ M_=M_
*.else
*	*MiM capacitor
*	Xstd_CMiM top bottom sub std_CMiM W_=W_ L_=L_ M_=M_
*.endif
.ends