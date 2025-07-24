
# This is a test of the design document

import math
import numpy as np
import matplotlib.pyplot as plt

Vref = 1.2
Nbits = 12

# We can estimat ethe 
def calc_signal_rms(Vref):
    return Vref * 2 / (2 * math.sqrt(2))


def calc_qnoise(Vref, Nbits):
    Vlsb = (Vref*2) / (2**Nbits)
    Vqnoise_rms = Vlsb/math.sqrt(12)    # value of 12 is unrelated to resolution
    return Vqnoise_rms, Vlsb

def calc_sampnoise(Ctot):
    kB = 1.38065e-23    # Boltzmann's constant
    T = 300  # roughly 27 deg C
    Vsampnoise_rms = math.sqrt(kB*T/Ctot)
    return Vsampnoise_rms

def calc_snr_volts(Vsignal, Vnoise):
    return 10 * math.log10((Vsignal / Vnoise)**2)

def calc_enob(SNR):
    return (SNR - 1.76)/6.02

def calc_enob_from_vref_Ctot_Nbits(Vref, Ctot, Nbits):
    Vinpp_rms = calc_signal_rms(Vref)
    Vqnoise_rms, Vlsb = calc_qnoise(Vref, Nbits)
    Vsampnoise_rms = calc_sampnoise(Ctot)
    Vnoise_rms = math.sqrt(Vqnoise_rms**2 + Vsampnoise_rms**2)   # only considers quantization and sampling noise
    snr = calc_snr_volts(Vinpp_rms, Vnoise_rms)
    enob = calc_enob(snr)
    return enob

Vinpp_rms = calc_signal_rms(Vref)

Vqnoise_rms, Vlsb = calc_qnoise(Vref, Nbits)

SNR_ideal = calc_snr_volts(Vinpp_rms, Vqnoise_rms)
ENOB_ideal = calc_enob(SNR_ideal)

# Next we find the degradation due to sampling and comparator noise
# NOTE: Actually, do I need to calculate the noise for each pseudo differential plate, and add it in quadrature?
Ctot = 500e-15 # just a guess for now, might be closer to 1000fF, but current guess is more pessamistic
Vcompnoise_rms = 120e-6    # for double tailed latch


Vsampnoise_rms = calc_sampnoise(Ctot)

Vnoise_rms = math.sqrt(Vqnoise_rms**2 + Vcompnoise_rms**2 + Vsampnoise_rms**2)

SNR_noise = calc_snr_volts(Vinpp_rms, Vnoise_rms)
ENOB_noise = calc_enob(SNR_noise)

# And finally, we try to estimate worse case DNL from the MSB switching
# See Pelgrom pg299
# To get 64 bit steps 60um/2/0.45um_step = 66.6
C_MSB = (2**10 - 2**7)/64*20e-15                  # Or something like this
C_LSB = 20e-15 / 64                               # around 0.30 aF
Acap = 0.0085                                     # mismatch coefficient per sqrt(C fF), from Pelgrom pg768
MSB_mismatch_sigma = Acap/math.sqrt(C_MSB*1e15)   # for Acap, need C_MSB in fF
MSB_mismatch_in_LSB_sigma = MSB_mismatch_sigma*C_MSB/C_LSB
MSB_mismatch_in_LSB_3sigma = 3 * MSB_mismatch_in_LSB_sigma  # around 0.8
Vdist_DNL = Vlsb * MSB_mismatch_in_LSB_3sigma
Vnoise_dist_rms = math.sqrt(Vqnoise_rms**2 + Vcompnoise_rms**2 + Vsampnoise_rms**2 + Vdist_DNL**2)

SNR_tot = calc_snr_volts(Vinpp_rms, Vnoise_dist_rms)
ENOB_tot = calc_enob(SNR_tot)

# 3σ

# -----------------------------------------------

# visualization of the data above


# Configure LaTeX for all text (requires LaTeX installed)
plt.rcParams.update({
    "text.usetex": True,       # Use LaTeX for text rendering
    "font.family": "serif",   # Use serif (LaTeX default)
    "font.serif": ["Computer Modern Roman"],  # LaTeX default font
    "font.size": 11,          # Base font size
    "axes.titlesize": 12,     # Title font size
    "axes.labelsize": 11,     # Axis label font size
    "xtick.labelsize": 10,    # X-tick label size
    "ytick.labelsize": 10,    # Y-tick label size
    "legend.fontsize": 10,    # Legend font size
})

Nbits_range = np.arange(8, 15)
Vrefs = [1.2, 0.9, 1.8]
labels = [f"Vref = {v} V" for v in Vrefs]

plt.figure()
for Vref_val, label in zip(Vrefs, labels):
    Vqnoise_vals = [calc_qnoise(Vref_val, n)[0] * 1e6 for n in Nbits_range]  # µV
    plt.plot(Nbits_range, Vqnoise_vals, label=label)
    # Get the y-values at N=10 and N=12
    y10 = calc_qnoise(Vref_val, 10)[0] * 1e6
    y12 = calc_qnoise(Vref_val, 12)[0] * 1e6
    plt.annotate(f"{y10:.1f} µV", xy=(10, y10), xytext=(5, -3), textcoords='offset points')
    plt.annotate(f"{y12:.1f} µV", xy=(12, y12), xytext=(5, -3), textcoords='offset points')
    plt.plot([10, 12], [calc_qnoise(Vref_val, 10)[0]*1e6, calc_qnoise(Vref_val, 12)[0]*1e6], 
             'o', markersize=4, color=plt.gca().lines[-1].get_color(), label='_nolegend_')

# Example plot
plt.xlabel(r"Number of Bits ($N_{\mathrm{bits}}$)")
plt.ylabel(r"Quantization Noise RMS ($\mu$V)")
plt.title(r'$\sigma_{V_{\mathrm{qnoise}}}$ vs. Bit Resolution')
plt.grid(True, which="both", ls="--", alpha=0.5)
plt.legend()
plt.yscale("log")
plt.tight_layout()
plt.savefig('build/qnoise.pdf')  # PDF preserves LaTeX text best
plt.close()


# -----------------------------------------------

# Plot sampling noise vs. total capacitance (10 fF to 10 pF)
Ctot_range = np.logspace(-13, -10, 100)  # 10 fF to 10 pF
Vsampnoise_vals = [calc_sampnoise(C) * 1e6 for C in Ctot_range]  # µV

plt.figure()
# Annotate noise values at specific capacitances
annotate_Cs = [200e-15, 500e-15, 1e-12, 2e-12, 4e-12]  # 200fF, 500fF, 1pF, 2pF, 4pF
plt.plot(Ctot_range * 1e15, Vsampnoise_vals)
for C in annotate_Cs:
    x = C * 1e15  # fF
    y = calc_sampnoise(C) * 1e6  # µV
    plt.plot(x, y, 'o', color=plt.gca().lines[-1].get_color(), label='_nolegend_')
    plt.annotate(f"{y:.1f} µV", xy=(x, y), xytext=(5, -3), textcoords='offset points')
    # Annotate X axis value below the point (Doesn't appear to be working?)
    # plt.annotate(f"{x:.0f} fF", xy=(x, 1e-1), xytext=(0, 5), textcoords='offset points',
    #              ha='center', va='bottom', fontsize=9, rotation=0)
plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
plt.ylabel(r"Sampling Noise RMS ($\mu$V)")
plt.title(r'$\sigma_{V_{\mathrm{samp}}}$ vs. Total Capacitance')
plt.grid(True, which="both", ls="--", alpha=0.5)
plt.xscale("log")
plt.yscale("log")
plt.tight_layout()
plt.savefig('build/sampnoise.pdf')
plt.close()

# -----------------------------------------------

# Plot ENOB vs. total capacitance (10 fF to 10 pF) for different Vref values
# This plot essentially tells use that in order for the sampling noise to cause no more than 0.1 ENOB degredation, it must 

Ctot_range = np.logspace(-13, -11, 100)  # 10 fF to 10 pF
Nbits_plot = 12
Vrefs = [1.2, 0.9, 1.8]
labels = [f"Vref = {v} V" for v in Vrefs]

plt.figure()
for Vref_val, label in zip(Vrefs, labels):
    enob_vals = [calc_enob_from_vref_Ctot_Nbits(Vref_val, C, Nbits_plot) for C in Ctot_range]
    plt.plot(Ctot_range * 1e15, enob_vals, label=label)
    # Annotate ENOB at specific capacitances
    for C_annot in [200e-15, 500e-15, 1e-12, 2e-12]:
        x = C_annot * 1e15  # fF
        y = calc_enob_from_vref_Ctot_Nbits(Vref_val, C_annot, Nbits_plot)
        plt.plot(x, y, 'o', color=plt.gca().lines[-1].get_color(), label='_nolegend_')
        plt.annotate(f"{y:.2f}", xy=(x, y), xytext=(5, -3), textcoords='offset points')

plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
plt.ylabel(r"ENOB (reduced by sampling noise)")
plt.title(rf'Degradation of ENOB vs. Sampling Capacitance ($N_{{\mathrm{{bits}}}}={Nbits_plot}$)')
plt.grid(True, which="both", ls="--", alpha=0.5)
plt.xscale("log")
plt.legend()
plt.tight_layout()
plt.savefig(f'build/enob_vs_Ctot_{Nbits_plot}bit.pdf')
plt.close()

