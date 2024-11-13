.subckt TG_BETA PPD TG FD SUB W_=2u L_=0.6u Vdep=0.7 Ctgfd=0.1f
*20230310 bart 

*0.7 is the Vth, 0.026 is the thermal voltage=kT/q, 4e-14 is the diode saturation current
vdep  dep  0  Vdep
gt_gate        FD     PPD  
+ cur='v(FD,PPD) * min((1e-5)*max(-(v(PPD,dep)),0), (4e-14)*exp((v(TG,PPD)-0.7)/0.026))'
captgfd TG FD Ctgfd 
*typical values in the order of 0.1 to 1 fF


.ends
