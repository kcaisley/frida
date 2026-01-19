import numpy as np
import pandas as pd
from pathlib import Path
from spicelib import RawRead

"""
Measurement entails reading in the .raw files created by simulation, and performing a series of post-processing and calculations
to find the performance of the circuit block under test. Columnar results are saved along with the original simulation data back to
a .npz file, while reduced dimensional results (including scalar quantities) are written to a .json struct.
"""


def read_traces(raw):
    """Return time and all traces as tuple of numpy arrays."""
    time = raw.get_axis()
    traces = tuple(raw.get_wave(name) for name in raw.get_trace_names() if name.lower() != 'time')
    return (time,) + traces

def write_analysis(raw_file, *variables, outdir=None):
    """
    Write arrays to .raw_a file and all variables to .pkl file.

    Arrays (same length as time) are written to both .raw_a and .pkl
    Scalars are only written to .pkl

    The first variable must be the time array.

    Args:
        raw_file: Path to the raw file (used for naming output files)
        *variables: Variable-length argument list of numpy arrays and scalars
        outdir: Optional output directory. If None, writes to same directory as raw_file

    Usage:
        write_analysis(raw_file, time, vin, vout, qvclk, vdiff, max_error_V, rms_error_V)
        write_analysis(raw_file, time, vin, vout, outdir='/path/to/meas')
    """
    import inspect
    import numpy as np

    # Get variable names from caller's frame
    frame = inspect.currentframe()
    if frame is None or frame.f_back is None:
        raise RuntimeError("Could not inspect calling frame. Variable names unavailable.")
    frame = frame.f_back
    var_dict = {}
    for var in variables:
        found = False
        for var_name, var_value in frame.f_locals.items():
            if var_value is var:
                var_dict[var_name] = var
                found = True
                break
        if not found:
            var_dict[f'var_{len(var_dict)}'] = var

    # Assume first variable is time
    time = variables[0]
    time_len = len(time) if hasattr(time, '__len__') else 0

    # Separate arrays (same length as time) from scalars
    arrays = {}
    for name, value in var_dict.items():
        if isinstance(value, np.ndarray) and len(value) == time_len:
            arrays[name] = value

    # Determine output paths
    import sys
    import json

    raw_path = Path(raw_file)

    # Check for outdir from CLI argument (stored in sys._measure_outdir)
    if outdir is None and hasattr(sys, '_measure_outdir'):
        outdir = sys._measure_outdir

    if outdir is not None:
        # Write to specified output directory
        # Replace sim_ prefix with meas_ for measurement files
        outdir_path = Path(outdir)
        outdir_path.mkdir(parents=True, exist_ok=True)
        base_name = raw_path.stem.replace('sim_', 'meas_', 1)
        json_path = outdir_path / f"{base_name}.json"
        csv_path = outdir_path / f"{base_name}.csv"
    else:
        # Write to same directory as raw_file
        base_name = raw_path.stem.replace('sim_', 'meas_', 1)
        json_path = raw_path.parent / f"{base_name}.json"
        csv_path = raw_path.parent / f"{base_name}.csv"

    # Separate arrays from scalars for CSV
    scalars = {}
    for name, value in var_dict.items():
        if not isinstance(value, np.ndarray) or len(value) != time_len:
            scalars[name] = value

    # Write .json file with scalar metrics only
    with open(json_path, 'w') as f:
        json.dump(scalars, f, indent=2, default=str)

    # Write .csv file with time-series data (arrays)
    if arrays:
        df = pd.DataFrame(arrays)
        df.to_csv(csv_path, index=False)

    return json_path, csv_path


def quantize(signal, bits=1, max=1.2, min=0):
    """Quantize signal to N bits between min and max."""
    levels = 2**bits
    step = (max - min) / levels
    quantized = np.floor((signal - min) / step) * step + min
    return np.clip(quantized, min, max)


def digitize(signal, threshold=None, vdd=1.2):
    """
    Digitize analog signal to binary (1 or 0) based on threshold.

    This is a 1-bit quantizer that converts analog voltages to digital levels.

    Parameters:
        signal: numpy array of analog voltages
        threshold: voltage threshold (default: vdd/2)
        vdd: supply voltage (default: 1.2V)

    Returns:
        numpy array of 1s and 0s
    """
    if threshold is None:
        threshold = vdd / 2
    return np.where(signal > threshold, 1, 0)


def reconstruct_analog(dcode, weights, vref_range=None):
    """
    Reconstruct analog voltage from digital code using DAC weights.

    Converts a digital code (array of bits) to analog voltage by multiplying
    each bit by its corresponding weight. Useful for analyzing ADC/DAC linearity.

    Parameters:
        dcode: 2D numpy array of shape (n_samples, n_bits) with digital codes (0s and 1s)
               or 1D array if analyzing a single code
        weights: 1D numpy array of length n_bits with weight for each bit position
                 May include mismatch/non-idealities
        vref_range: tuple of (vmin, vmax) for normalization. If None, returns raw weighted sum

    Returns:
        numpy array of reconstructed analog values

    Example:
        >>> dcode = np.array([[0, 0, 1], [0, 1, 0], [1, 1, 1]])  # 3 samples, 3 bits
        >>> weights = np.array([1, 2, 4])  # Binary weights
        >>> reconstruct_analog(dcode, weights)
        array([4, 2, 7])
    """
    # Handle 1D case
    if dcode.ndim == 1:
        dcode = dcode.reshape(1, -1)

    # Convert bits to bipolar (-1, +1) for differential signaling
    # Or just use (0, 1) for unipolar - keeping it flexible
    analog = np.dot(dcode, weights)

    # Normalize to voltage range if specified
    if vref_range is not None:
        vmin, vmax = vref_range
        # Scale from code range to voltage range
        code_min = np.dot(np.zeros_like(weights), weights)
        code_max = np.dot(np.ones_like(weights), weights)
        analog = vmin + (analog - code_min) * (vmax - vmin) / (code_max - code_min)

    return analog.squeeze()


def calculate_inl(vin, dout_analog, return_stats=True):
    """
    Calculate Integral Nonlinearity (INL) for ADC/DAC transfer function.

    INL measures the deviation of the actual transfer function from the best-fit line.

    Parameters:
        vin: numpy array of input voltages (analog reference)
        dout_analog: numpy array of reconstructed output voltages from digital code
        return_stats: if True, also return RMS and worst-case INL

    Returns:
        If return_stats=False:
            inl: numpy array of INL values (same length as vin)
        If return_stats=True:
            inl, inl_rms, inl_max: (array, float, float)

    Example:
        >>> vin = np.linspace(-0.6, 0.6, 100)
        >>> dout = reconstruct_analog(dcode, weights)
        >>> inl, inl_rms, inl_max = calculate_inl(vin, dout)
    """
    # Compute best-fit line using least squares
    coeffs = np.polyfit(vin, dout_analog, 1)  # Linear fit: slope and intercept
    dout_linear = np.polyval(coeffs, vin)

    # INL is deviation from best-fit line
    inl = dout_analog - dout_linear

    # Calculate statistics
    if return_stats:
        inl_rms = np.std(inl)  # RMS INL
        inl_max = np.max(np.abs(inl))  # Worst-case (peak) INL
        return inl, inl_rms, inl_max

    return inl


def calculate_dnl(dout_analog, ideal_lsb=None, return_stats=True):
    """
    Calculate Differential Nonlinearity (DNL) for ADC/DAC.

    DNL measures the difference between actual and ideal code step sizes.
    DNL[i] = (actual_step[i] - ideal_step) / ideal_step

    Parameters:
        dout_analog: numpy array of reconstructed analog values (sorted by code)
        ideal_lsb: ideal LSB step size. If None, computed as mean of all steps
        return_stats: if True, also return RMS and worst-case DNL

    Returns:
        If return_stats=False:
            dnl: numpy array of DNL values in LSB units (length = len(dout_analog) - 1)
        If return_stats=True:
            dnl, dnl_rms, dnl_max: (array, float, float)

    Example:
        >>> dout = reconstruct_analog(dcode, weights)
        >>> dnl, dnl_rms, dnl_max = calculate_dnl(dout)
    """
    # Calculate actual step sizes
    actual_steps = np.diff(dout_analog)

    # Ideal LSB is the average step size (or specified)
    if ideal_lsb is None:
        ideal_lsb = np.mean(actual_steps)

    # DNL in LSB units
    dnl = (actual_steps - ideal_lsb) / ideal_lsb

    # Calculate statistics
    if return_stats:
        dnl_rms = np.std(dnl)  # RMS DNL
        dnl_max = np.max(np.abs(dnl))  # Worst-case (peak) DNL
        return dnl, dnl_rms, dnl_max

    return dnl


def calculate_dnl_histogram(dout_analog, return_stats=True):
    """
    Calculate DNL using histogram/code density method.

    This method rounds the output to nearest integer codes, counts occurrences
    of each code, and compares to the ideal uniform distribution. This is the
    method used in the legacy spice.py code.

    DNL[code] = (actual_count[code] / average_count) - 1

    Parameters:
        dout_analog: numpy array of reconstructed analog values
        return_stats: if True, also return RMS and worst-case DNL

    Returns:
        If return_stats=False:
            dnl_hist, code_counts: (DNL array, histogram counts)
        If return_stats=True:
            dnl_hist, code_counts, dnl_rms, dnl_max: (array, dict, float, float)

    Example:
        >>> dout = reconstruct_analog(dcode, weights)
        >>> dnl, counts, dnl_rms, dnl_max = calculate_dnl_histogram(dout)
    """
    # Round to nearest integer code
    dout_rounded = np.round(dout_analog)

    # Count occurrences of each code
    unique_codes, counts = np.unique(dout_rounded, return_counts=True)

    # Calculate ideal count (uniform distribution)
    total_samples = len(dout_analog)
    num_codes = len(unique_codes)
    ideal_count = total_samples / num_codes

    # DNL in LSB units
    dnl_hist = (counts / ideal_count) - 1

    # Create dict for easier lookup by code
    code_counts = dict(zip(unique_codes, counts))

    # Calculate statistics
    if return_stats:
        dnl_rms = np.std(dnl_hist)  # RMS DNL
        dnl_max = np.max(np.abs(dnl_hist))  # Worst-case (peak) DNL
        return dnl_hist, code_counts, dnl_rms, dnl_max

    return dnl_hist, code_counts


def calculate_linearity_error(vin, dout_analog, return_stats=True):
    """
    Calculate linearity error (deviation from best-fit line).

    This is similar to INL but returns the raw error in output units
    rather than normalized to LSB. Useful for visualizing transfer function error.

    Parameters:
        vin: numpy array of input voltages
        dout_analog: numpy array of output values
        return_stats: if True, also return RMS error

    Returns:
        If return_stats=False:
            error: numpy array of errors
        If return_stats=True:
            error, error_rms: (array, float)
    """
    # Compute best-fit line
    coeffs = np.polyfit(vin, dout_analog, 1)
    dout_linear = np.polyval(coeffs, vin)

    # Error is deviation from best-fit
    error = dout_analog - dout_linear

    if return_stats:
        error_rms = np.std(error)
        return error, error_rms

    return error


def round_to_codes(dout_analog):
    """
    Round continuous analog output to discrete integer codes.

    This is useful for analyzing ADC outputs that may have some analog
    variation but should ideally be discrete codes.

    Parameters:
        dout_analog: numpy array of analog output values

    Returns:
        dout_rounded: numpy array of integer codes
    """
    return np.round(dout_analog).astype(int)


def diff(v1, v2):
    """Return differential signal (v1 - v2)."""
    return v1 - v2


def comm(v1, v2):
    """Return common mode signal ((v1 + v2) / 2)."""
    return (v1 + v2) / 2


def lookup_device(netlist, device_name):
    """Return voltage and current signal names for device terminals [d, g, s, b]."""
    nodes = netlist.get_component_nodes(device_name)
    v_names = [f'v({node})' for node in nodes]
    i_names = [f'i({device_name.lower()}:{t})' for t in ['d', 'g', 's', 'b']]
    return v_names, i_names


def rds(raw, netlist, device_name):
    """Calculate output resistance (Vd - Vs) / Id."""
    v_names, i_names = lookup_device(netlist, device_name)
    vd = raw.get_wave(v_names[0])
    vs = raw.get_wave(v_names[2])
    id = raw.get_wave(i_names[0])
    return (vd - vs) / id




# ========================================================================
# Analytic Functions - compute metrics from circuit parameters
# ========================================================================

def analyze_weights(weights: list[int], threshold: int = 64):
    """
    Gives analysis of weights for where the main scaling structure ends and where
    fine adjustments (such as capacitor differences, Vref scaling with a resistive
    divider, or bridge capacitor scaling) begin. The output includes weight
    ratios, and various metrics annotated for design insight.

    This function calculates and displays key metrics including the unit capacitor
    size (defining the transition from coarse to fine scaling), effective radix
    between weights, and the percentage of remaining redundancy.

    Args:
        weights: List of capacitor weights
        threshold: Coarse/fine split threshold (default: 64)

    Returns:
        dict: Dictionary containing analysis results
    """

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

    return {
        'weights': weights,
        'weight_ratios': [w / threshold for w in weights],
        'sum': sum(weights),
        'length': len(weights),
        'bit': bit,
        'method4': method4 + [0],
        'radix': radix + [0],
        'remaining': remaining
    }


def analyze_signal_rms(Vref):
    """
    Estimate RMS amplitude of signal assuming peak-to-peak sinusoid.

    Args:
        Vref: Reference voltage

    Returns:
        float: RMS signal voltage
    """
    import math
    return Vref * 2 / (2 * math.sqrt(2))


def analyze_qnoise(Vref, Nbits):
    """
    Calculate quantization noise for ADC.

    Args:
        Vref: Reference voltage
        Nbits: Number of bits

    Returns:
        tuple: (Vqnoise_rms, Vlsb)
    """
    import math
    Vlsb = (Vref*2) / (2**Nbits)
    Vqnoise_rms = Vlsb/math.sqrt(12)
    return Vqnoise_rms, Vlsb


def analyze_sampnoise(Ctot):
    """
    Calculate sampling noise from total capacitance.

    Args:
        Ctot: Total sampling capacitance (F)

    Returns:
        float: RMS sampling noise voltage
    """
    import math
    kB = 1.38065e-23    # Boltzmann's constant
    T = 300  # roughly 27 deg C
    Vsampnoise_rms = math.sqrt(kB*T/Ctot)
    return Vsampnoise_rms


def analyze_snr_volts(Vsignal, Vnoise):
    """
    Calculate SNR in dB from signal and noise voltages.

    Args:
        Vsignal: RMS signal voltage
        Vnoise: RMS noise voltage

    Returns:
        float: SNR in dB
    """
    import math
    return 10 * math.log10((Vsignal / Vnoise)**2)


def analyze_enob(SNR):
    """
    Calculate ENOB from SNR.

    Args:
        SNR: Signal-to-noise ratio in dB

    Returns:
        float: Effective number of bits
    """
    return (SNR - 1.76)/6.02


def analyze_enob_from_vref_Ctot_Nbits(Vref, Ctot, Nbits):
    """
    Calculate effective number of bits (ENOB) due to sampling noise.

    Args:
        Vref: Reference voltage of the ADC
        Ctot: Total sampling capacitance (F)
        Nbits: Number of ADC bits

    Returns:
        float: ENOB, reduced only due to sampling noise
    """
    import math
    Vinpp_rms = analyze_signal_rms(Vref)
    Vqnoise_rms, Vlsb = analyze_qnoise(Vref, Nbits)
    Vsampnoise_rms = analyze_sampnoise(Ctot)
    Vnoise_rms = math.sqrt(Vqnoise_rms**2 + Vsampnoise_rms**2)
    snr = analyze_snr_volts(Vinpp_rms, Vnoise_rms)
    enob = analyze_enob(snr)
    return enob


def analyze_midcode_sigma_bounds(Ctot, Nbits, Acap):
    """
    Calculate 3-sigma and 4-sigma bounds for mid-code variation due to capacitor mismatch.

    Args:
        Ctot: Total capacitance of the array (F)
        Nbits: Number of design bits
        Acap: Mismatch coefficient per sqrt(C fF), from Pelgrom pg. 768

    Returns:
        tuple: (sigma, 3sigma, 4sigma, Cu, Cu_sigma_norm) in LSB units or Farads
    """
    import math
    Cu = Ctot / (2 ** Nbits)
    Cu_delta_sigma_norm = Acap / math.sqrt(Cu * 1e15)
    Cu_sigma_norm = Cu_delta_sigma_norm / math.sqrt(2)
    Cmsb_delta_sigma_norm = Cu_sigma_norm * math.sqrt(2**(Nbits-1) + (2**(Nbits-1)- 1))
    Cmsb_delta_3sigma_norm = 3 * Cmsb_delta_sigma_norm
    Cmsb_delta_4sigma_norm = 4 * Cmsb_delta_sigma_norm
    return Cmsb_delta_sigma_norm, Cmsb_delta_3sigma_norm, Cmsb_delta_4sigma_norm, Cu, Cu_sigma_norm


def analyze_mismatch_dnl_noise(Ctot, Nbits, Acap, Vref):
    """
    Calculate mismatch-induced DNL noise.

    Args:
        Ctot: Total capacitance (F)
        Nbits: Number of bits
        Acap: Mismatch coefficient
        Vref: Reference voltage

    Returns:
        tuple: (1sigma, 3sigma, 4sigma) DNL noise voltages
    """
    import math
    Vqnoise, Vlsb = analyze_qnoise(Vref, Nbits)
    Cmsb_delta_1sigma_norm, Cmsb_delta_3sigma_norm, Cmsb_delta_4sigma_norm, Cu, Cu_sigma_norm = \
        analyze_midcode_sigma_bounds(Ctot, Nbits, Acap)

    Vmmdnl_noise_1sigma = math.sqrt((Vlsb**2 * (Cmsb_delta_1sigma_norm**2)))
    Vmmdnl_noise_3sigma = math.sqrt((Vlsb**2 * (Cmsb_delta_3sigma_norm**2)))
    Vmmdnl_noise_4sigma = math.sqrt((Vlsb**2 * (Cmsb_delta_4sigma_norm**2)))

    return Vmmdnl_noise_1sigma, Vmmdnl_noise_3sigma, Vmmdnl_noise_4sigma


def analyze_enob_from_mismatch(Ctot, Nbits, Acap, Vref):
    """
    Calculate ENOB considering capacitor mismatch.

    Args:
        Ctot: Total capacitance (F)
        Nbits: Number of bits
        Acap: Mismatch coefficient
        Vref: Reference voltage

    Returns:
        float: ENOB reduced by mismatch
    """
    import math
    Vinpp_rms = analyze_signal_rms(Vref)
    Vqnoise_rms, Vlsb = analyze_qnoise(Vref, Nbits)
    Vmmdnl_noise_1sigma, Vmmdnl_noise_3sigma, Vmmdnl_noise_4sigma = \
        analyze_mismatch_dnl_noise(Ctot, Nbits, Acap, Vref)
    Vnoise_rms = math.sqrt(Vqnoise_rms**2 + Vmmdnl_noise_3sigma**2)
    snr = analyze_snr_volts(Vinpp_rms, Vnoise_rms)
    enob = analyze_enob(snr)
    return enob


def analyze_area(netlist_json):
    """
    Calculate total device area from netlist.

    Args:
        netlist_json: Dictionary containing device parameters

    Returns:
        dict: Dictionary with per-device areas and total area
    """
    device_areas = {}
    total_area = 0.0

    devices = netlist_json.get('devices', {})
    for dev_name, dev_info in devices.items():
        if 'w' in dev_info and 'l' in dev_info:
            area = dev_info['w'] * dev_info['l']
            nf = dev_info.get('nf', 1)
            device_areas[dev_name] = area * nf
            total_area += area * nf

    return {
        'device_areas': device_areas,
        'total_area': total_area
    }


def main():
    """Main entry point for measurement script."""
    import argparse
    import sys
    import json
    import re
    from glob import glob
    from tqdm import tqdm
    from flow.plot import load_analysis_module

    parser = argparse.ArgumentParser(description='Run measurements on simulation results')
    parser.add_argument('block_file', type=Path, help='Path to block script (e.g., blocks/comp.py)')
    parser.add_argument('sim_dir', type=Path, help='Directory containing .raw files (e.g., results/sim)')
    parser.add_argument('ckt_dir', type=Path, help='Directory containing subcircuit .json files (e.g., ckt)')
    parser.add_argument('tb_dir', type=Path, help='Directory containing testbench .json files (e.g., results/tb)')
    parser.add_argument('meas_dir', type=Path, help='Output directory for measurements (e.g., results/meas)')
    args = parser.parse_args()

    # Extract cell name from block file (e.g., blocks/comp.py -> comp)
    cell = args.block_file.stem

    # Load analysis module
    analysis_module = load_analysis_module(args.block_file)
    if not hasattr(analysis_module, 'measure'):
        print(f"Error: {args.block_file} does not have a measure() function")
        sys.exit(1)

    # Set output directory in sys for write_analysis() to access
    sys._measure_outdir = str(args.meas_dir)
    args.meas_dir.mkdir(parents=True, exist_ok=True)

    # Find all .raw files for this cell in sim_dir (now with sim_ prefix)
    raw_pattern = str(args.sim_dir / f"sim_{cell}*.raw")
    raw_files = sorted(glob(raw_pattern))

    if not raw_files:
        print(f"No .raw files found matching: {raw_pattern}")
        sys.exit(0)

    print(f"\n{'='*80}")
    print(f"Measuring {cell}")
    print(f"{'='*80}")
    print(f"Found {len(raw_files)} simulation results\n")
    print(f"{'File':<50} {'Status':<10}")
    print(f"{'-'*80}")

    # Process each raw file
    successful = 0
    failed = []

    for raw_file in tqdm(raw_files, desc="Processing simulations"):
        raw_path = Path(raw_file)
        filename = raw_path.name

        try:
            # Parse filename: sim_<cell>_<params>_<tech>_<hash>.raw
            # Example: sim_comp_nmosinput_stdbias_tsmc65_a1b2c3d4e5f6.raw
            stem = raw_path.stem  # Remove .raw extension

            # Extract tech and hash (12 hex chars) from filename
            # Tech is alphanumeric, hash is 12 hex characters at the end
            match = re.search(r'_(\w+)_([0-9a-f]{12})$', stem)
            if not match:
                print(f"{filename:<50} {'✗ No hash':<10}")
                failed.append(raw_path.name)
                continue

            tech = match.group(1)
            hash_hex = match.group(2)

            # Find matching subcircuit .json: ckt_<cell>_<params>_<tech>_<hash>.json
            subckt_pattern = str(args.ckt_dir / f"ckt_{cell}_*_{tech}_{hash_hex}.json")
            subckt_matches = glob(subckt_pattern)

            if not subckt_matches:
                print(f"{filename:<50} {'✗ No subckt':<10}")
                failed.append(raw_path.name)
                continue

            subckt_json_path = Path(subckt_matches[0])

            # Find matching testbench .json: tb_<cell>_<tech>.json
            tb_json_path = args.tb_dir / f"tb_{cell}_{tech}.json"

            if not tb_json_path.exists():
                print(f"{filename:<50} {'✗ No TB':<10}")
                failed.append(raw_path.name)
                continue

            # Load data
            raw = RawRead(str(raw_path), traces_to_read='*', dialect='ngspice', verbose=False)

            with open(subckt_json_path, 'r') as f:
                subckt_json = json.load(f)

            with open(tb_json_path, 'r') as f:
                tb_json = json.load(f)

            # Call measure function
            analysis_module.measure(raw, subckt_json, tb_json, str(raw_path))

            print(f"{filename:<50} {'✓':<10}")
            successful += 1

        except Exception as e:
            print(f"{filename:<50} {'✗ Error':<10}")
            failed.append((raw_path.name, str(e)))
            continue

    # Print summary
    print(f"{'-'*80}")
    print(f"\n{'='*80}")
    print("Measurement Summary")
    print(f"{'='*80}")
    print(f"Total files:     {len(raw_files)}")
    print(f"Successful:      {successful} ({100*successful/len(raw_files):.1f}%)")
    print(f"Failed:          {len(failed)} ({100*len(failed)/len(raw_files):.1f}%)")

    if failed:
        print("\nFailed files:")
        for item in failed:
            if isinstance(item, tuple):
                name, error = item
                print(f"  - {name}: {error}")
            else:
                print(f"  - {item}")

    print(f"\nResults saved to: {args.meas_dir}")
    print(f"{'='*80}")

    return 0 if len(failed) == 0 else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
