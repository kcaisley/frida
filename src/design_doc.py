
# This is a test of the design document

import math
import numpy as np
import matplotlib.pyplot as plt

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

Vref = 1.2
Nbits = 12
Acap = 0.0085     # mismatch coefficient per sqrt(C fF), from Pelgrom pg768

# We can estimat the RMS amplitude of the signal, by assuming it is a peak-to-peak sinusoid 
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
    """
    Calculates the effective number of bits (ENOB) due to sampling noise for an ADC given reference voltage, total sampling capacitance, and resolution.

    Args:
        Vref (float): Reference voltage of the ADC.
        Ctot (float): Total sampling capacitance.
        Nbits (int): Number of ADC bits.

    Returns:
        float: Effective number of bits (ENOB), reduced only due to sampling noise.
    """
    Vinpp_rms = calc_signal_rms(Vref)
    Vqnoise_rms, Vlsb = calc_qnoise(Vref, Nbits)
    Vsampnoise_rms = calc_sampnoise(Ctot)
    Vnoise_rms = math.sqrt(Vqnoise_rms**2 + Vsampnoise_rms**2)   # only considers quantization and sampling noise
    snr = calc_snr_volts(Vinpp_rms, Vnoise_rms)
    enob = calc_enob(snr)
    return enob

def calc_midcode_sigma_bounds(Ctot, Nbits, Acap):
    """
    Calculates the 3-sigma and 4-sigma bounds for mid-code variation due to capacitor mismatch.

    Args:
        Ctot (float): Total capacitance of the array (F).
        Nbits (int): Number of design bits.
        Acap (float): Mismatch coefficient per sqrt(C fF), from Pelgrom pg. 768

    Returns:
        tuple: (3sigma_bound, 4sigma_bound) in Farads.
    """
    Cu = Ctot / (2 ** Nbits)
    # From Pelgom pg. 762, when using Acap need C in fF
    # note this is actually giving already the expected variation between two equal sized caps
    Cu_delta_sigma_norm = Acap / math.sqrt(Cu * 1e15)

    # extracting the single device variation, it would be 
    Cu_sigma_norm = Cu_delta_sigma_norm / math.sqrt(2)

    # Next, multiplying the Cu normalized stdev by the sqrt of the number of Cu gives the variation of mid-code, in relative to Cu (aka LSB)
    # Note this is actually the expected delta between the MSB vs sum(MSB-1 -> LSB)
    Cmsb_delta_sigma_norm = Cu_sigma_norm * math.sqrt(2**(Nbits-1) + (2**(Nbits-1)- 1))

    # Finally we can multiply by 
    Cmsb_delta_3sigma_norm = 3 * Cmsb_delta_sigma_norm
    Cmsb_delta_4sigma_norm = 4 * Cmsb_delta_sigma_norm
    return Cmsb_delta_sigma_norm, Cmsb_delta_3sigma_norm , Cmsb_delta_4sigma_norm, Cu, Cu_sigma_norm

def calc_mismatch_dnl_noise(Ctot, Nbits, Acap, Vref):
    Vqnoise, Vlsb = calc_qnoise(Vref, Nbits) # we only need the Vlsb value here, but we do print out the Vqnoise for fun
    Cmsb_delta_1sigma_norm, Cmsb_delta_3sigma_norm , Cmsb_delta_4sigma_norm, Cu, Cu_sigma_norm = calc_midcode_sigma_bounds(Ctot, Nbits, Acap) # we only need the 3 and 4 sigma values
    
    Vmmdnl_noise_1sigma = math.sqrt((Vlsb**2 * (Cmsb_delta_1sigma_norm**2)))
    Vmmdnl_noise_3sigma = math.sqrt((Vlsb**2 * (Cmsb_delta_3sigma_norm**2)))
    Vmmdnl_noise_4sigma = math.sqrt((Vlsb**2 * (Cmsb_delta_4sigma_norm**2)))

    # print(f"Ctot = {cap*1e15:.2f} fF, Nbits = {Nbits_dnl}, Acap = {Acap}, Vref = {Vref}")
    # print(f"-> LSB Voltage = {Vlsb*1e6:.4f} µV, Vqnoise = {Vqnoise*1e6:.4f} µV")
    # print(f"-> 3 σΔCmsb/C = {Cmsb_delta_3sigma_norm:.4f} LSB, 4 σΔCmsb/C = {Cmsb_delta_4sigma_norm:.4f} LSB, Cu = {Cu*1e18:.2f} aF, sigma_norm_Cu = {Cu_sigma_norm:.4f}, sigmaCu = {Cu_sigma_norm*Cu*1e18:.4f} aF")
    # print(f"-> 1σ DNL Noise = {Vmmdnl_noise_1sigma*1e6:.2f} µV, 3σ DNL Noise = {Vmmdnl_noise_3sigma*1e6:.2f} µV, 4σ DNL Noise = {Vmmdnl_noise_4sigma*1e6:.2f} µV")
    # print()

    return Vmmdnl_noise_1sigma, Vmmdnl_noise_3sigma, Vmmdnl_noise_4sigma


def calc_enob_from_mismatch(Ctot, Nbits, Acap, Vref):
    Vinpp_rms = calc_signal_rms(Vref)
    Vqnoise_rms, Vlsb = calc_qnoise(Vref, Nbits)
    Vmmdnl_noise_1sigma, Vmmdnl_noise_3sigma, Vmmdnl_noise_4sigma = calc_mismatch_dnl_noise(Ctot, Nbits, Acap, Vref)
    Vnoise_rms = math.sqrt(Vqnoise_rms**2 + Vmmdnl_noise_3sigma**2)   # only considers quantization and mismatch dnl noise
    snr = calc_snr_volts(Vinpp_rms, Vnoise_rms)
    enob = calc_enob(snr)
    return enob

# -----------------------------------------------

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

# -----------------------------------------------
# Plot 3-sigma and 4-sigma mid-code bounds vs. total capacitance (100 fF to 10 pF)
Ctot_range = np.logspace(-13, -11, 100)  # 100 fF to 10 pF
# Ctot_range = [1e-12, 5e-12, 10e-12]
Nbits_midcode = 12

bounds_1sigma = []
bounds_3sigma = []
bounds_4sigma = []

for cap in Ctot_range:
    b1, b3, b4, Cu, sigmaCu  = calc_midcode_sigma_bounds(cap, Nbits_midcode, Acap)
    bounds_1sigma.append(b1)
    bounds_3sigma.append(b3)
    bounds_4sigma.append(b4)
    # print(f"Ctot = {cap*1e15:.2f} fF: 3σ Bound = {b3:.4f}, 4σ Bound = {b4:.4f}, Cu = {Cu*1e18:.2f} aF, sigma_norm_Cu = {sigmaCu:.4f}, sigmaCu = {sigmaCu*Cu*1e18:.4f} aF")

plt.figure()
plt.plot(Ctot_range * 1e15, bounds_1sigma, label=r"1$\sigma$ Bound")
plt.plot(Ctot_range * 1e15, bounds_3sigma, label=r"3$\sigma$ Bound")
plt.plot(Ctot_range * 1e15, bounds_4sigma, label=r"4$\sigma$ Bound")

# Annotate at specific capacitances
# annotate_Cs = [200e-15, 500e-15, 1e-12, 2e-12, 4e-12]
# for cap in annotate_Cs:
#     x = C * 1e15  # fF
#     b3, b4 = calc_midcode_sigma_bounds(C, Nbits_midcode, Acap)
#     plt.plot(x, b3, 'o', color=plt.gca().lines[0].get_color(), label='_nolegend_')
#     plt.plot(x, b4, 'o', color=plt.gca().lines[1].get_color(), label='_nolegend_')
#     # plt.annotate(f"{b3:.2f}", xy=(x, b3), xytext=(5, -3), textcoords='offset points', fontsize=9)
#     # plt.annotate(f"{b4:.2f}", xy=(x, b4), xytext=(5, -3), textcoords='offset points', fontsize=9)

plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
plt.ylabel(r"Max DNL [LSB] (expected at mid-code)")
plt.title(rf'1$\sigma$, 3$\sigma$, and 4$\sigma$ Mid-code LSB vs. $C_{{\mathrm{{tot}}}}$ ($N_{{\mathrm{{bits}}}}={Nbits_midcode}$)')
plt.grid(True, which="both", ls="--", alpha=0.5)
plt.xscale("log")
plt.legend()
plt.tight_layout()
plt.savefig(f'build/expected_mismatch_{Nbits_midcode}bit.pdf')
plt.close()


# -----------------------------------------------

# Plot mismatch DNL noise (3-sigma and 4-sigma) vs. total capacitance (100 fF to 10 pF) for 12 bits
Ctot_range = np.logspace(-13, -11, 100)  # 100 fF to 10 pF
Nbits_dnl = 12

dnl_noise_1sigma = []
dnl_noise_3sigma = []
dnl_noise_4sigma = []
for cap in Ctot_range:
    d1, d3, d4 = calc_mismatch_dnl_noise(cap, Nbits_dnl, Acap, Vref)
    dnl_noise_1sigma.append(d1*1e6) # multiply each here by 1e6 to get it in microvolts
    dnl_noise_3sigma.append(d3*1e6) # we can't do it later, as: can't multiply sequence by non-int of type 'float'
    dnl_noise_4sigma.append(d4*1e6)

plt.figure()
plt.plot(Ctot_range * 1e15, dnl_noise_1sigma, label=r"1$\sigma$ DNL Noise")
plt.plot(Ctot_range * 1e15, dnl_noise_3sigma, label=r"3$\sigma$ DNL Noise")
plt.plot(Ctot_range * 1e15, dnl_noise_4sigma, label=r"4$\sigma$ DNL Noise")
plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
plt.ylabel(r"Mismatch DNL Noise [$\mu$V]")
plt.title(rf'Mismatch DNL Noise vs. $C_{{\mathrm{{tot}}}}$ ($N_{{\mathrm{{bits}}}}={Nbits_dnl}$)')
plt.grid(True, which="both", ls="--", alpha=0.5)
plt.xscale("log")
plt.legend()
plt.tight_layout()
plt.savefig(f'build/mismatch_dnl_noise_{Nbits_dnl}bit.pdf')
plt.close()


# -----------------------------------------------

# Plot ENOB vs. total capacitance (10 fF to 10 pF) for different Vref values
# This plot essentially tells use that in order for the sampling noise to cause no more than 0.1 ENOB degredation, it must 

Ctot_range = np.logspace(-13, -10, 100)  # 10 fF to 100 pF
Nbits = 12
Vref = 1.2
Acap = 0.0085

plt.figure()
enob_vals_sampnoise = []
for Ctot in Ctot_range:
    enob = calc_enob_from_vref_Ctot_Nbits(Vref, Ctot, Nbits)
    enob_vals_sampnoise.append(enob)


enob_vals_mismatchdnl_noise =[] 
for Ctot in Ctot_range:
    enob = calc_enob_from_mismatch(Ctot, Nbits, Acap, Vref)
    enob_vals_mismatchdnl_noise.append(enob)



plt.plot(Ctot_range * 1e15, enob_vals_sampnoise, label="ENOB due to Sampling noise")
plt.plot(Ctot_range * 1e15, enob_vals_mismatchdnl_noise, label="ENOB due to Mismatch DNL noise")

# # Annotate ENOB at specific capacitances
# for C_annot in [200e-15, 500e-15, 1e-12, 2e-12]:
#     x = C_annot * 1e15  # fF
#     y = calc_enob_from_vref_Ctot_Nbits(Vref_val, C_annot, Nbits_plot)
#     plt.plot(x, y, 'o', color=plt.gca().lines[-1].get_color(), label='_nolegend_')
#     plt.annotate(f"{y:.2f}", xy=(x, y), xytext=(5, -3), textcoords='offset points')

plt.xlabel(r"Total Capacitance ($C_{\mathrm{tot}}$) [fF]")
plt.ylabel(r"ENOB")
plt.title(rf'ENOB vs. $C_{{\mathrm{{tot}}}}$: from Sampling or Mismatch DNL Noise')

plt.annotate(
    rf"$N_{{\mathrm{{bits}}}}={Nbits}$" "\n"
    rf"$V_{{\mathrm{{ref}}}}={Vref}$ V" "\n"
    rf"$A_{{C}}={Acap}$",
    xy=(1, 0), xycoords='axes fraction',
    va='top',
    # Shift annotation up and over
    xytext=(-60, 75), textcoords='offset points',fontsize=10,
    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.7)
)

plt.grid(True, which="both", ls="--", alpha=0.5)
plt.xscale("log")
plt.legend(loc='lower right', bbox_to_anchor=(1, 0), frameon=True)
# plt.gca().add_artist(plt.gca().texts[-1])  # Ensure annotation is drawn above the legend
plt.tight_layout()
plt.savefig(f'build/enob_vs_Ctot_{Nbits}bit_compare.pdf')
plt.close()


##

# Data
M_steps = np.array([12, 13, 14, 15, 16, 17, 18, 19, 20])
cu_var_pct = np.array([5.3, 8.5, 12.2, 15.2, 19.2, 23.1, 27.3, 30.4, 32.6])
effective_radix = 12 / M_steps

plt.figure(figsize=(7, 4))
plt.plot(M_steps, cu_var_pct, marker='o', label='Tolerable Cu Variation (percent)')
plt.xlabel('Redundant Steps (M)')
plt.ylabel('Tolerable Cu Variation (%)')
plt.title('Tolerable Unit Cap Variation vs. Redundant Steps')
plt.grid(True, which="both", ls="--", alpha=0.5)

# Annotate effective radix below each x tick
plt.xticks(M_steps)
ax = plt.gca()
ax2 = ax.twiny()
ax2.set_xlim(ax.get_xlim())
ax2.set_xticks(M_steps)
ax2.set_xticklabels([f"{r:.2f}" for r in effective_radix])
ax2.set_xlabel("Effective Radix")

plt.tight_layout()
plt.savefig('build/redun_tolerace.pdf')
plt.close()