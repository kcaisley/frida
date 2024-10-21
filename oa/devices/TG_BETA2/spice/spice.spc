.subckt TG_BETA2 PPD TG FD SUB W_=2u L_=0.6u Ldiff=10um Vdep=1 Ctgfd=0.1f barrier=0.3
*20230706ba updated to include image lag 
*20230719ba last update
*20230802ba added parameters Ldiff diffusion distance
*20230829ba removed the Ldiff,  moved to ppd
*20230831ba added W_/L_ proportionality

*0.7 is the Vth, 0.026 is the thermal voltage=kT/q, 4e-14 is the diode saturation current

vdep  dep  SUB  Vdep
gt_gate        FD     PPD  
+ cur='(W_/L_) * v(FD,PPD) * min(max((1e-6)*(v(dep,PPD)),0),min((1e-6)*exp((v(dep,PPD)-max(barrier,0))/0.026), (4e-14)*exp((v(TG,PPD)-0.7)/0.026)))'
*+ cur='v(FD,PPD) * max((1e-12)*v(dep,PPD),0) * min((1e-0)*exp(max(v(dep,PPD)-barrier,0)/0.026) , (1e-14)*exp((v(TG,PPD)-0.7)/0.026))'
*+ cur='v(FD,PPD) * min(max((-1e-5)*(v(PPD)-v(dep)),0),min((4e-14)*exp(max(v(dep,PPD)-barrier,0)/0.026), (4e-14)*exp((v(TG,PPD)-0.7)/0.026)))'
*+ cur='v(FD,PPD) * min((4e-14)*exp(max(barrier+v(dep,PPD),0)/0.026), (4e-14)*exp((v(TG,PPD)-0.7)/0.026))'
*+ cur='v(FD,PPD) * min(max((-1e-5)*(v(PPD)-v(dep)),0), (4e-14)*exp(barrier+v(dep,PPD)/0.026), (4e-14)*exp((v(TG,PPD)-0.7)/0.026))'

captgfd TG FD Cparasitic Ctgfd 
*typical value ctgfd in the order of 0.1 to 1 fF

.ends
