
# This is a test of the design document

import math

#%%
kB = 1.38065e-23
Vref = 1.2
bits = 12
T = 300  # roughly 27 deg C

def calc_snr_volts(Vsignal, Vnoise):
    return 10 * math.log10((Vsignal / Vnoise)**2)

def calc_enob(SNR):
    return (SNR - 1.76)/6.02

# First, we calculate the noise of the ideal ADC
Vinpp_rms = Vref*2 / (2*math.sqrt(2))
V_LSB = (Vref*2) / (2**bits)
Vqnoise_rms = V_LSB/math.sqrt(12)    # 12 unrelated to resolution

SNR_ideal = calc_snr_volts(Vinpp_rms, Vqnoise_rms)
ENOB_ideal = calc_enob(SNR_ideal)

# Next we find the degradation due to sampling and comparator noise
# NOTE: Actually, do I need to calculate the noise for each pseudo differential plate, and add it in quadrature?
Ctot = 500e-15 # just a guess for now, might be closer to 1000fF, but current guess is more pessamistic
Vcompnoise_rms = 120e-6    # for double tailed latch
Vsampnoise_rms = math.sqrt(kB*T/Ctot)
Vnoise_rms = math.sqrt(Vqnoise_rms**2 + Vcompnoise_rms**2 + Vsampnoise_rms**2)

SNR_noise = calc_snr_volts(Vinpp_rms, Vnoise_rms)
ENOB_noise = calc_enob(SNR_noise)

# And finally, we try to estimate worse case DNL from the MSB switching
# See Pelgrom pg299
# To get 64 bit steps 60um/2/0.45um_step = 66.6
C_MSB = (2**10 - 2**7)/64*20e-15                  # Or something like this
C_LSB = 20e-15 / 64                               # around 0.30 aF
Acap = 0.005                                      # mismatch coefficient per sqrt(C fF), from Pelgrom pg768
MSB_mismatch_sigma = Acap/math.sqrt(C_MSB*1e15)   # for Acap, need C_MSB in fF
MSB_mismatch_in_LSB_sigma = MSB_mismatch_sigma*C_MSB/C_LSB
MSB_mismatch_in_LSB_3sigma = 3 * MSB_mismatch_in_LSB_sigma  # around 0.8
Vdist_DNL = V_LSB * MSB_mismatch_in_LSB_3sigma
Vnoise_dist_rms = math.sqrt(Vqnoise_rms**2 + Vcompnoise_rms**2 + Vsampnoise_rms**2 + Vdist_DNL**2)

SNR_tot = calc_snr_volts(Vinpp_rms, Vnoise_dist_rms)
ENOB_tot = calc_enob(SNR_tot)

print(f"LSB voltage: {V_LSB * 1e6:.2f} µV")
print(f"Quantization noise RMS: {Vqnoise_rms * 1e6:.2f} µV")
print(f"SNR_ideal: {SNR_ideal:.2f} dB")
print(f"ENOB_ideal: {ENOB_ideal:.2f} ENOB")
print()

print(f"Sampling noise RMS: {Vsampnoise_rms * 1e6:.2f} µV")
print(f"Comparator noise RMS: {Vcompnoise_rms * 1e6:.2f} µV")
print(f"SNR w/ noise: {SNR_noise:.2f} dB")
print(f"ENOB w/ noise: {ENOB_noise:.2f} ENOB")
print()

print(f"3σ worst-case DNL: {MSB_mismatch_in_LSB_3sigma:.2f} LSB")
print(f"SNR w/ noise & dist: {SNR_tot:.2f} dB")
print(f"ENOB w/ noise & dist: {ENOB_tot:.2f} ENOB")
print()


#%%
weights = [2**10-2**7,
           2**9,
           2**8+2**5,
           2**7+2**5,
           2**6+2**4,
           2**5+2**4,
           2**4+2**3,
           2**3+2**3,
           2**2+2**2,
           2**1+2**2,
           2**0+2**1,
                2**1,
                2**1,
                2**0,
                2**0]

# Print the list of weights for inspection
print("Weights list:", weights)

# Print the sum of the weights to verify total capacitance or code coverage
print("Sum of weights:", sum(weights))

# %% [markdown]
# This is a test, with some markdown
# 
# $$ x+y $$