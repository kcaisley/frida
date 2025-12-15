import numpy as np
from pathlib import Path
from spicelib import RawRead, SpiceEditor
from spicelib.raw.raw_write import RawWrite, Trace


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
    from run_plotting import load_analysis_module

    parser = argparse.ArgumentParser(description='Run SPICE analysis')
    parser.add_argument('raw_file', type=Path, help='Path to .raw file')
    parser.add_argument('netlist_file', type=Path, help='Path to .sp netlist file')
    parser.add_argument('analysis_file', type=Path, help='Path to analysis.py script')
    args = parser.parse_args()

    raw = RawRead(str(args.raw_file), traces_to_read='*', dialect='ngspice', verbose=False)
    netlist = SpiceEditor(str(args.netlist_file))

    analysis_module = load_analysis_module(args.analysis_file)
    analysis_module.analyze(raw, netlist, str(args.raw_file))


if __name__ == '__main__':
    main()
