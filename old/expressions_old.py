def quantize(signal, bits=1, max_val=1.2, min_val=0):
    """
    Quantize signal to N bits between min and max.

    Args:
        signal: numpy array of analog values
        bits: number of quantization bits
        max_val: maximum value
        min_val: minimum value

    Returns:
        Quantized numpy array
    """
    levels = 2**bits
    step = (max_val - min_val) / levels
    quantized = np.floor((signal - min_val) / step) * step + min_val
    return np.clip(quantized, min_val, max_val)


def digitize(signal, threshold=None, vdd=1.2):
    """
    Digitize analog signal to binary (1 or 0) based on threshold.

    Args:
        signal: numpy array of analog voltages
        threshold: voltage threshold (default: vdd/2)
        vdd: supply voltage

    Returns:
        numpy array of 1s and 0s
    """
    if threshold is None:
        threshold = vdd / 2
    return np.where(signal > threshold, 1, 0)


# ============================================================
# CDAC/ADC Linearity Measurements (Custom - not in PyOPUS)
# ============================================================


def calculate_inl(vin, vout):
    """
    Calculate Integral Nonlinearity from best-fit line.

    INL measures deviation from ideal linear transfer function.

    Args:
        vin: Input voltage array (ideal ramp)
        vout: Output voltage array (measured)

    Returns:
        Tuple of (inl_array, inl_max) - INL at each code and maximum |INL|
    """
    coeffs = np.polyfit(vin, vout, 1)
    ideal = np.polyval(coeffs, vin)
    inl = vout - ideal
    return inl, float(np.max(np.abs(inl)))


def calculate_dnl(vout, ideal_lsb=None):
    """
    Calculate Differential Nonlinearity.

    DNL measures difference between actual and ideal step sizes.

    Args:
        vout: Output voltage array
        ideal_lsb: Expected step size (if None, uses mean step)

    Returns:
        Tuple of (dnl_array, dnl_max) - DNL at each step and maximum |DNL|
    """
    steps = np.diff(vout)
    if ideal_lsb is None:
        ideal_lsb = np.mean(steps)
    if ideal_lsb == 0:
        return np.zeros(len(steps)), 0.0
    dnl = (steps - ideal_lsb) / ideal_lsb
    return dnl, float(np.max(np.abs(dnl)))


def extract_settled_values(vout, time, n_codes, settle_fraction=0.9):
    """
    Extract settled output values from stepped waveform.

    Assumes vout has n_codes steps, samples at settle_fraction of each period.

    Args:
        vout: Output voltage waveform
        time: Time array
        n_codes: Number of DAC codes
        settle_fraction: Fraction of period to wait for settling

    Returns:
        Array of settled values at each code
    """
    period = time[-1] / n_codes
    settled_times = [(i + settle_fraction) * period for i in range(n_codes)]
    settled_values = np.interp(settled_times, time, vout)
    return settled_values


def analyze_weights(weights, coarse_weight):
    """
    Gives analysis of weights for where the main scaling structure ends and where fine adjustments (such as capacitor differences, Vref scaling with a resistive divider, or bridge capacitor scaling) begin. The output includes partitioned weights, ratios, and various metrics annotated for design insight.
    This function calculates and displays key metrics including the unit capacitor size (defining the transition from coarse to fine scaling), effective radix between weights, and the percentage of remaining redundancy.
    """
    # Print the list of weights
    print("Weights:", weights)
    # Print the ratio of each weight to the coarse_weight (unit size)
    print("Weight ratios:", [w / coarse_weight for w in weights])

    # Partition each weight into chunks of coarse_weight, with possible remainder
    partitioned_weights = partition_weights(weights, coarse_weight)
    print("Partitioned weights:", partitioned_weights)
    # Print the total number of unit capacitors needed
    print(f"Unit count: {sum([math.ceil(w / coarse_weight) for w in weights])}")
    # Print the sum of all weights
    print(f"Sum: {sum(weights)}")
    # Print the number of weights
    print(f"Length: {len(weights)}")

    # Calculate various metrics for each bit position
    remaining = []  # Remaining total weight after each bit
    method4 = []    # Difference between remaining and current weight
    radix = []      # Ratio of current weight to next weight (effective radix)
    bit = list(range(len(weights)))  # Bit indices

    # Loop through all but the last weight to compute metrics
    for i, cap in enumerate(weights[:-1]):
        remain = sum(weights[i+1:])  # Total weight remaining after this bit
        remaining.append(remain)
        method4.append(remain - weights[i])  # Difference between remaining and current
        radix.append(weights[i] / weights[i+1])  # Effective radix between this and next

    # Print a table of bit index, weight, method4, and radix
    print("\nBit  Weight   Method4  Radix")
    print("-" * 32)
    for a, b, c, d in zip(bit, weights, method4 + [0], radix + [0]):
        print(f"{a:<8} {b:<8} {c:<8.1f} {d:<8.1f}")

    # Return the partitioned weights for further use
    return partitioned_weights



# Super old, scalar code, from analytic.py:
# We can estimate the RMS amplitude of the signal, by assuming it is a peak-to-peak sinusoid
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
    # From Pelgrom pg. 762, when using Acap need C in fF
    # note this already gives the expected variation between two equal sized caps
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
