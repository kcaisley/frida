import math

# let's try to compute the FOM for M. Shin 2012. (ref 10)

def FoM(P, ConvTime, A_um2, DRDB):
    J_per_um2 = (P*ConvTime*A_um2)/(10**((DRDB-1.76)/10))
    fJ_per_um2 = J_per_um2*1e15
    return fJ_per_um2

# it has 2Mpixel, and 200Mpixels/second

# DCD adc convtime time is 1/((512*512*78000)/(16*16*8))=100e-9
# area of 200e-6*200e-6 = 4e-8 = 40000 um^2
# dynamic range is Qnoise limited, so 8*6.02+1.76 ~ 50 dB

DCD = FoM(3600e-6,1e-7,40000,50)
print(DCD*10e15) #2e21

helena = FoM(100e-6,100e-9,2000,60) 
print(helena*10e15) # 3e17