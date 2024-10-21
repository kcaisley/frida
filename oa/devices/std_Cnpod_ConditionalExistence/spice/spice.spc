.subckt std_cnpod_ConditionalExistence top bottom sub Exists= 1 L_=1u M_ = 1 W_=1u  
*20240415ViS created cell as prototype for cell with conditional existence
	.if (Exists == 1)
		XCpod_conditionalExistence top bottom sub std_Cnpod W_=W_ L_=L_ M_=M_
	.else
		*nothing, empty cell
		XCparasitic top bottom Cparasitic C=1e-12
	.endif
.ends

