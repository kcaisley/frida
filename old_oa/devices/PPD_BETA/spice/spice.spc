.subckt PPD_BETA PPD SUB W_=5u L_=5u
*20230621 bart 

cppd SUB PPD Cparasitic 'W_*L_*0.1e-3' 
* the last factor calibrate it versus measurements
	
.ends
