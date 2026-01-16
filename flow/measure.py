import numpy as np
from pathlib import Path
from spicelib import RawRead, SpiceEditor
from spicelib.raw.raw_write import RawWrite, Trace

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

def write_analysis(raw_file, *variables):
    """
    Write arrays to .raw_a file and all variables to .pkl file.

    Arrays (same length as time) are written to both .raw_a and .pkl
    Scalars are only written to .pkl

    The first variable must be the time array.

    Usage:
        write_analysis(raw_file, time, vin, vout, qvclk, vdiff, max_error_V, rms_error_V)
    """
    import pickle
    import inspect
    import numpy as np

    # Get variable names from caller's frame
    frame = inspect.currentframe().f_back
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

    # Write .raw_a file with arrays only
    raw_a_path = Path(raw_file).with_suffix('.raw_a')
    # WARNING: 'fastacces' typo is in the spicelib library itself!
    raw_write = RawWrite(fastacces=False, encoding='utf_8')

    # Find and add time trace first
    time_name = None
    for name, data in arrays.items():
        if name.lower() == 'time':
            time_name = name
            raw_write.add_trace(Trace('time', data, whattype='time', numerical_type='double'))
            break

    # Add other array traces
    for name, data in arrays.items():
        if name == time_name:
            continue

        # Determine trace type from name
        if name.startswith('v') or name.startswith('V'):
            whattype = 'voltage'
        elif name.startswith('i') or name.startswith('I'):
            whattype = 'current'
        else:
            whattype = 'voltage'

        raw_write.add_trace(Trace(name, data, whattype=whattype, numerical_type='double'))

    raw_write.save(str(raw_a_path))

    # Write .pkl file with all data (arrays and scalars)
    pkl_path = Path(raw_file).with_suffix('.pkl')
    with open(pkl_path, 'wb') as f:
        pickle.dump(var_dict, f, protocol=pickle.HIGHEST_PROTOCOL)

    import pprint
    print(f"\nSaved {len(arrays)} arrays to {raw_a_path}")
    print(f"Saved {len(var_dict)} variables to {pkl_path}:")
    pprint.pprint(var_dict)

    return raw_a_path, pkl_path


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


def main():
    import argparse
    from flow.plot import load_analysis_module

    parser = argparse.ArgumentParser(description='Run SPICE analysis')
    parser.add_argument('raw_file', type=Path, help='Path to .raw file')
    parser.add_argument('netlist_file', type=Path, help='Path to .sp netlist file')
    parser.add_argument('analysis_file', type=Path, help='Path to analysis.py script')
    args = parser.parse_args()

    raw = RawRead(str(args.raw_file), traces_to_read='*', dialect='ngspice', verbose=False)
    netlist = SpiceEditor(str(args.netlist_file))

    analysis_module = load_analysis_module(args.analysis_file)
    analysis_module.measure(raw, netlist, str(args.raw_file))


if __name__ == '__main__':
    main()
