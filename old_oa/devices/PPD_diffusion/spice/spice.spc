.subckt PPD_diffusion PPD SUB TGS W_=5u L_=5u
*20230830 bart dierickx see Notebook 0705

cppd SUB PPD 'W_*L_*0.1e-3' 
	* the last factor calibrate it versus measurements
rdummy TGS PPD 1E50	
	* to ensure DC path to GND
gt_diff     TGS     PPD  
+ cur='6e-7*(1/(L_*L_ + 0.25*W_*W_)) * v(TGS,PPD)* W_*L_'

   * 1/L^2: diffusion time
   * v()*L*W: amount of charge in PPD (current is ~ to)

.ends
